"""Lógica de datos, carga, agregaciones, variaciones y proyecciones.
Separa el procesamiento analítico de la capa visual y de presentación.
"""
import os
import numpy as np
import pandas as pd

CORTE = pd.Timestamp("2021-04-01")  # Periodo de prueba de modelos
TODAS = "Todas las regiones"
ETIQ = {
    "Total": "Total de viajeros",
    "Via_Aérea": "Vía aérea",
    "Via_Terrestre": "Vía terrestre",
    "Via_Marítima": "Vía marítima",
    "Tipo_Turista": "Turistas",
    "Tipo_Excursionista": "Excursionistas",
    "Tipo_Viajero": "Viajeros (tránsito y comercio fronterizo)",
    "Tipo_Cruceristas": "Cruceristas"
}


def leer_archivo(nombre, data_dir="data"):
    """Carga un CSV normalizando codificaciones y nombres de series/regiones."""
    ruta = os.path.join(data_dir, nombre)
    if not os.path.exists(ruta):
        return None
    try:
        df = pd.read_csv(ruta)
    except Exception:
        df = pd.read_csv(ruta, encoding="latin1")

    if "fecha" in df:
        df = df[df["fecha"].astype(str).str.lower() != "fecha"]
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha"])
    if "prediccion" in df:
        df["prediccion"] = pd.to_numeric(df["prediccion"], errors="coerce")
        df = df.dropna(subset=["prediccion"])
    if "serie" in df:
        df["serie"] = (df["serie"]
                       .str.replace("Via_A.*rea", "Via_Aérea", regex=True)
                       .str.replace("Via_Mar.*tima", "Via_Marítima", regex=True))
    if "region" in df:
        df["region"] = (df["region"]
                       .str.replace("Am.*rica", "América", regex=True)
                       .str.replace("Ocean.*a", "Oceanía", regex=True)
                       .str.replace("Pa.*ses", "Países", regex=True))
    return df


def cargar_todo(data_dir="data"):
    """Carga y valida los datasets requeridos."""
    series = leer_archivo("series_mensuales.csv", data_dir)
    pais = leer_archivo("pais_mensual.csv", data_dir)
    vf = leer_archivo("via_frontera.csv", data_dir)
    pron = leer_archivo("pronosticos.csv", data_dir)
    pca = leer_archivo("catch22_pca.csv", data_dir)

    idx = pd.date_range(series.fecha.min(), series.fecha.max(), freq="MS") if series is not None else None
    regiones = sorted([r for r in pais["region"].dropna().unique() if r not in ["0", "Sin dato"]]) if pais is not None else []

    return series, pais, vf, pron, pca, idx, regiones


def agrupar_serie(s, nivel):
    """Agrupa una serie por mes o por año."""
    return s.resample("YS" if nivel in ["Año", "Anual"] else "MS").sum()


def calcular_variacion_interanual(s, anio):
    """Calcula el porcentaje de cambio interanual comparando los mismos meses disponibles."""
    cur = s[s.index.year == anio]
    prev = s[(s.index.year == anio - 1) & (s.index.month.isin(cur.index.month))]
    return (cur.sum() / prev.sum() - 1) * 100 if len(cur) and prev.sum() > 0 else None


def calcular_proyeccion(s, meses_adelante=18):
    """Calcula la proyección temporal futura con factor de estacionalidad."""
    if s.empty:
        return pd.Series(dtype=float)
    fechas_futuras = pd.date_range(s.index.max() + pd.DateOffset(months=1), periods=meses_adelante, freq="MS")
    ultimos_12 = s.iloc[-12:] if len(s) >= 12 else s
    crec = 1.05  # Crecimiento estimado anual (5%)
    valores = []
    for i in range(meses_adelante):
        base = ultimos_12.iloc[i % len(ultimos_12)]
        factor = crec ** ((i + 1) / 12)
        valores.append(base * factor)
    return pd.Series(valores, index=fechas_futuras)


def calcular_metricas_error(series, pron, ms, corte=CORTE):
    """Calcula la tabla de MAE y RMSE sobre el periodo de prueba para la serie dada."""
    real = series[(series.serie == ms) & (series.fecha >= corte)].set_index("fecha")["viajeros"]
    filas = []
    pm = pron[pron.serie == ms]
    for m, g in pm.groupby("modelo"):
        e = g.set_index("fecha")["prediccion"].reindex(real.index) - real
        filas.append({
            "Modelo": m,
            "MAE (Error medio)": round(e.abs().mean()),
            "RMSE": round(float(np.sqrt((e ** 2).mean())))
        })
    return pd.DataFrame(filas).sort_values("MAE (Error medio)").reset_index(drop=True)
