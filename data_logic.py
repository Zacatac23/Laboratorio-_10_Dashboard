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


# =====================================================
# LÓGICA DE DATOS: MAPA MUNDIAL DE ORIGEN
# =====================================================

PAIS_A_ISO3 = {
    'Afganistán': 'AFG', 'Albania': 'ALB', 'Alemania': 'DEU', 'Andorra': 'AND', 'Angola': 'AGO',
    'Anguila': 'AIA', 'Antigua Y Barbuda': 'ATG', 'Antigua y Barbuda': 'ATG', 'Arabia Saudita': 'SAU',
    'Argelia': 'DZA', 'Argentina': 'ARG', 'Armenia': 'ARM', 'Aruba': 'ABW', 'Australia': 'AUS',
    'Austria': 'AUT', 'Azerbaiyán': 'AZE', 'Bahamas': 'BHS', 'Bahrein': 'BHR', 'Bangladesh': 'BGD',
    'Barbados': 'BRB', 'Belice': 'BLZ', 'Benin': 'BEN', 'Bermuda': 'BMU', 'Bielorrusia': 'BLR',
    'Bolivia (Estado Plurinacional De)': 'BOL', 'Bolivia (Estado Plurinacional de)': 'BOL',
    'Bosnia y Herzegovina': 'BIH', 'Botswana': 'BWA', 'Brasil': 'BRA', 'Brunei Darussalam': 'BRN',
    'Bulgaria': 'BGR', 'Burkina Faso': 'BFA', 'Burundi': 'BDI', 'Bután': 'BTN', 'Bélgica': 'BEL',
    'Cabo Verde': 'CPV', 'Camboya': 'KHM', 'Camerún': 'CMR', 'Canadá': 'CAN', 'Chad': 'TCD',
    'Chile': 'CHL', 'China': 'CHN', 'China, Hong Kong Región Administrativa Especial': 'HKG',
    'China, Macao, Región Administrativa Especial': 'MAC', 'Chipre': 'CYP', 'Colombia': 'COL',
    'Comoras': 'COM', 'Congo': 'COG', 'Costa Rica': 'CRI', 'Croacia': 'HRV', 'Cuba': 'CUB',
    "Côte D'ivoire": 'CIV', "Côte d'Ivoire": 'CIV', 'Dinamarca': 'DNK', 'Djibouti': 'DJI',
    'Dominica': 'DMA', 'Ecuador': 'ECU', 'Egipto': 'EGY', 'El Salvador': 'SLV',
    'Emiratos Árabes Unidos': 'ARE', 'Eritrea': 'ERI', 'Eslovaquia': 'SVK', 'Eslovenia': 'SVN',
    'España': 'ESP', 'Estado de Palestina': 'PSE', 'Estados Unidos de América': 'USA',
    'Estonia': 'EST', 'Etiopía': 'ETH', 'Federación De Rusia': 'RUS', 'Federación de Rusia': 'RUS',
    'Fiji': 'FJI', 'Filipinas': 'PHL', 'Finlandia': 'FIN', 'Francia': 'FRA', 'Gabón': 'GAB',
    'Gambia': 'GMB', 'Georgia': 'GEO', 'Ghana': 'GHA', 'Gibraltar': 'GIB', 'Granada': 'GRD',
    'Grecia': 'GRC', 'Groenlandia': 'GRL', 'Guadalupe': 'GLP', 'Guam': 'GUM', 'Guatemala': 'GTM',
    'Guayana francés': 'GUF', 'Guinea': 'GIN', 'Guinea Ecuatorial': 'GNQ', 'Guinea-Bissau': 'GNB',
    'Guyana': 'GUY', 'Haití': 'HTI', 'Honduras': 'HND', 'Hungría': 'HUN', 'India': 'IND',
    'Indonesia': 'IDN', 'Irak': 'IRQ', 'Irlanda': 'IRL', 'Irán (República Islámica Del)': 'IRN',
    'Irán (República Islámica del)': 'IRN', 'Islandia': 'ISL', 'Islas Caimán': 'CYM',
    'Islas Feroe': 'FRO', 'Islas Marshall': 'MHL', 'Islas Turcas y Caicos': 'TCA',
    'Islas Vírgenes Americanas': 'VIR', 'Islas Vírgenes Británicas': 'VGB', 'Israel': 'ISR',
    'Italia': 'ITA', 'Jamaica': 'JAM', 'Japón': 'JPN', 'Jordania': 'JOR', 'Katar': 'QAT',
    'Kazajstán': 'KAZ', 'Kenia': 'KEN', 'Kirguistán': 'KGZ', 'Kiribati': 'KIR', 'Kuwait': 'KWT',
    'La ex República Yugoslava de Macedonia': 'MKD', 'Lesoto': 'LSO', 'Letonia': 'LVA',
    'Liberia': 'LBR', 'Libia': 'LBY', 'Liechtenstein': 'LIE', 'Lituania': 'LTU',
    'Luxemburgo': 'LUX', 'Líbano': 'LBN', 'Madagascar': 'MDG', 'Malasia': 'MYS', 'Malawi': 'MWI',
    'Maldivas': 'MDV', 'Malta': 'MLT', 'Malí': 'MLI', 'Marruecos': 'MAR', 'Martinica': 'MTQ',
    'Mauricio': 'MUS', 'Mauritania': 'MRT', 'Mayotte': 'MYT',
    'Micronesia (Estados Federados De)': 'FSM', 'Micronesia (Estados Federados de)': 'FSM',
    'Mongolia': 'MNG', 'Montenegro': 'MNE', 'Montserrat': 'MSR', 'Mozambique': 'MOZ',
    'México': 'MEX', 'Mónaco': 'MCO', 'Namibia': 'NAM', 'Nauru': 'NRU', 'Nepal': 'NPL',
    'Nicaragua': 'NIC', 'Nigeria': 'NGA', 'Niue': 'NIU', 'Noruega': 'NOR',
    'Nueva Caledonia': 'NCL', 'Nueva Zelanda': 'NZL', 'Níger': 'NER', 'Omán': 'OMN',
    'Pakistán': 'PAK', 'Palau': 'PLW', 'Panamá': 'PAN', 'Papúa Nueva Guinea': 'PNG',
    'Paraguay': 'PRY', 'Países Bajos': 'NLD', 'Perú': 'PER', 'Pitcairn': 'PCN',
    'Polinesia francés': 'PYF', 'Polonia': 'POL', 'Portugal': 'PRT', 'Puerto Rico': 'PRI',
    'Reino Unido De Gran Bretaña E Irlanda Del Norte': 'GBR',
    'Reino Unido de Gran Bretaña e Irlanda del Norte': 'GBR', 'República Centroafricana': 'CAF',
    'República Checa': 'CZE', 'República De Corea': 'KOR', 'República De Moldova': 'MDA',
    'República Democrática Popular Lao': 'LAO', 'República Democrática del Congo': 'COD',
    'República Dominicana': 'DOM', 'República Popular Democrática de Corea': 'PRK',
    'República Unida de Tanzania': 'TZA', 'República de Corea': 'KOR',
    'República de Kazajistán': 'KAZ', 'República de Moldova': 'MDA',
    'República Árabe Siria': 'SYR', 'Ruanda': 'RWA', 'Rumania': 'ROU', 'Réunion': 'REU',
    'Samoa': 'WSM', 'San Cristóbal Y Nieves': 'KNA', 'San Cristóbal y Nieves': 'KNA',
    'San Marino': 'SMR', 'San Vicente y las Granadinas': 'VCT', 'Santa Lucía': 'LCA',
    'Santo Tomé y Príncipe': 'STP', 'Senegal': 'SEN', 'Serbia': 'SRB', 'Seychelles': 'SYC',
    'Sierra Leona': 'SLE', 'Singapur': 'SGP', 'Somalia': 'SOM', 'Sri Lanka': 'LKA',
    'Sudáfrica': 'ZAF', 'Sudán': 'SDN', 'Suecia': 'SWE', 'Suiza': 'CHE', 'Suriname': 'SUR',
    'Swazilandia': 'SWZ', 'Tailandia': 'THA', 'Taiwan': 'TWN', 'Tayikistán': 'TJK',
    'Timor-Leste': 'TLS', 'Togo': 'TGO', 'Tonga': 'TON', 'Trinidad Y Tobago': 'TTO',
    'Trinidad y Tobago': 'TTO', 'Turkmenistán': 'TKM', 'Turquía': 'TUR', 'Tuvalu': 'TUV',
    'Túnez': 'TUN', 'Ucrania': 'UKR', 'Uganda': 'UGA', 'Uruguay': 'URY', 'Uzbekistán': 'UZB',
    'Vanuatu': 'VUT', 'Venezuela (República Bolivariana De)': 'VEN',
    'Venezuela (República Bolivariana de)': 'VEN', 'Viet Nam': 'VNM', 'Yemen': 'YEM',
    'Zambia': 'ZMB'
}


def preparar_datos_mapa_origen(pais_df, anio_inicio, anio_fin, region_seleccionada="Todas las regiones"):
    """Filtra y prepara los datos para el mapa de origen de viajeros.
    
    Retorna:
        tuple: (df_procesado, es_region_especifica)
    """
    if pais_df is None or pais_df.empty:
        return pd.DataFrame(), False

    # Filtrar por rango temporal
    filtro = (pais_df.fecha.dt.year >= anio_inicio) & (pais_df.fecha.dt.year <= anio_fin)
    df_filtrado = pais_df[filtro].copy()
    if df_filtrado.empty:
        df_filtrado = pais_df.copy()

    # Agrupar por país y región
    agrupado = df_filtrado.groupby(["pais", "region"], as_index=False)["viajeros"].sum()
    agrupado["iso_alpha"] = agrupado["pais"].map(PAIS_A_ISO3)
    agrupado = agrupado.dropna(subset=["iso_alpha"]).copy()

    # Determinar foco de la región seleccionada
    es_region_especifica = bool(
        region_seleccionada
        and region_seleccionada != "Todas las regiones"
        and region_seleccionada in set(agrupado["region"])
    )

    if es_region_especifica:
        agrupado["en_region"] = agrupado["region"] == region_seleccionada
        agrupado["valor_grafica"] = agrupado.apply(
            lambda r: r["viajeros"] if r["en_region"] else 0,
            axis=1
        )
    else:
        agrupado["en_region"] = True
        agrupado["valor_grafica"] = agrupado["viajeros"]

    agrupado["viajeros_fmt"] = agrupado["viajeros"].apply(lambda v: f"{v:,.0f}")
    return agrupado, es_region_especifica

