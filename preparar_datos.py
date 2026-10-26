"""Convierte el Excel del INGUAT en CSV livianos para el tablero.
Uso:  python preparar_datos.py Base_Migracion_2009-2026jun.xlsx
"""
import sys
import pandas as pd

ruta = sys.argv[1] if len(sys.argv) > 1 else "Base_Migracion_2009-2026jun.xlsx"
df = pd.read_excel(ruta, sheet_name="Datos")
df["fecha"] = pd.to_datetime(dict(year=df["Año"], month=df["Mes cod"], day=1))
df = df.rename(columns={"Vía": "via", "Frontera": "frontera", "País": "pais",
                        "Región dos": "region", "Tipo de Viajero": "tipo", "Viajero": "viajeros"})
df["region"] = df["region"].replace({"0": "Sin dato", "Cruceros": "Cruceristas"})

# Las mismas 8 series mensuales del Laboratorio 1 (meses sin registro = 0)
meses = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="MS")
def serie(nombre, filtro=None):
    d = df if filtro is None else df[filtro]
    s = d.groupby("fecha")["viajeros"].sum().reindex(meses, fill_value=0)
    return pd.DataFrame({"serie": nombre, "fecha": meses, "viajeros": s.values})

partes = [serie("Total")]
partes += [serie(f"Via_{v}", df["via"] == v) for v in ["Aérea", "Terrestre", "Marítima"]]
partes += [serie(f"Tipo_{t}", df["tipo"] == t) for t in sorted(df["tipo"].unique())]
pd.concat(partes).to_csv("data/series_mensuales.csv", index=False)
df.groupby(["fecha", "pais", "region"], as_index=False)["viajeros"].sum().to_csv("data/pais_mensual.csv", index=False)
df.groupby(["fecha", "via", "frontera"], as_index=False)["viajeros"].sum().to_csv("data/via_frontera.csv", index=False)
print("Listo: data/series_mensuales.csv, pais_mensual.csv, via_frontera.csv")
