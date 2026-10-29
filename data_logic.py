"""Carga validada y cálculos reproducibles; nunca extrapola pronósticos."""
import os
import numpy as np
import pandas as pd

CORTE = pd.Timestamp('2021-04-01')
TODAS = 'Todas las regiones'
ETIQ = {
    'Total': 'Total de viajeros', 'Via_Aérea': 'Vía aérea',
    'Via_Terrestre': 'Vía terrestre', 'Via_Marítima': 'Vía marítima',
    'Tipo_Turista': 'Turistas', 'Tipo_Excursionista': 'Excursionistas',
    'Tipo_Viajero': 'Viajeros (tránsito y comercio fronterizo)',
    'Tipo_Cruceristas': 'Cruceristas',
}
ESQUEMAS = {
    'series_mensuales.csv': ['serie', 'fecha', 'viajeros'],
    'pais_mensual.csv': ['fecha', 'pais', 'region', 'viajeros'],
    'via_frontera.csv': ['fecha', 'via', 'frontera', 'viajeros'],
    'pronosticos.csv': ['serie', 'modelo', 'fecha', 'prediccion'],
    'catch22_pca.csv': ['serie', 'PC1', 'PC2', 'cluster'],
}
CLAVES = {
    'series_mensuales.csv': ['serie', 'fecha'],
    'pais_mensual.csv': ['fecha', 'pais', 'region'],
    'via_frontera.csv': ['fecha', 'via', 'frontera'],
    'pronosticos.csv': ['serie', 'modelo', 'fecha'],
    'catch22_pca.csv': ['serie'],
}


class ErrorDatos(ValueError):
    """Error de entrada que se explica sin stacktrace."""


def seleccion_vigente(puntos, opciones):
    """La interfaz define una selección efectiva: el último punto aún disponible."""
    valor = puntos[-1].get('y') if puntos else None
    return valor if valor in opciones else None


def leer_archivo(nombre, data_dir='data', diagnosticos=None):
    ruta = os.path.join(data_dir, nombre)
    if not os.path.isfile(ruta):
        return None
    try:
        try:
            df = pd.read_csv(ruta, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(ruta, encoding='latin1')
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise ErrorDatos(f'{nombre}: no se pudo leer el CSV. Revise su formato.') from exc
    faltantes = set(ESQUEMAS[nombre]) - set(df.columns)
    if faltantes:
        raise ErrorDatos(f'{nombre}: faltan columnas: {", ".join(sorted(faltantes))}.')
    if df.empty:
        raise ErrorDatos(f'{nombre}: el archivo está vacío; agregue registros válidos.')
    if df[ESQUEMAS[nombre]].isna().any().any():
        raise ErrorDatos(f'{nombre}: hay valores nulos; no se descartaron filas.')
    if 'fecha' in df:
        fechas = pd.to_datetime(df.fecha, errors='coerce')
        invalidas = int(fechas.isna().sum())
        if invalidas:
            raise ErrorDatos(f'{nombre}: {invalidas} fechas inválidas; no se descartaron filas.')
        if (fechas.dt.day != 1).any() or (fechas != fechas.dt.normalize()).any():
            raise ErrorDatos(f'{nombre}: se requieren fechas mensuales al primer día del mes.')
        df['fecha'] = fechas
    for col in ['viajeros', 'prediccion', 'PC1', 'PC2', 'cluster']:
        if col in df:
            valores = pd.to_numeric(df[col], errors='coerce')
            if not np.isfinite(valores).all():
                raise ErrorDatos(f'{nombre}: {col} contiene números inválidos o no finitos.')
            if col == 'viajeros' and (valores < 0).any():
                raise ErrorDatos(f'{nombre}: viajeros contiene conteos negativos.')
            df[col] = valores
    for col in ['serie', 'pais', 'region', 'via', 'frontera', 'modelo']:
        if col in df:
            df[col] = df[col].astype(str).str.strip()
            if df[col].eq('').any():
                raise ErrorDatos(f'{nombre}: {col} contiene etiquetas vacías.')
    cambios = 0
    for col, patrones in {
        'serie': [('Via_A.*rea', 'Via_Aérea'), ('Via_Mar.*tima', 'Via_Marítima')],
        'region': [('Am.*rica', 'América'), ('Ocean.*a', 'Oceanía'), ('Pa.*ses', 'Países')],
    }.items():
        if col in df:
            antes = df[col].copy()
            for patron, reemplazo in patrones:
                df[col] = df[col].str.replace(patron, reemplazo, regex=True)
            cambios += int((antes != df[col]).sum())
    if cambios and diagnosticos is not None:
        diagnosticos.append(f'{nombre}: {cambios} etiquetas normalizadas; no se eliminaron filas.')
    if nombre in ['series_mensuales.csv', 'pronosticos.csv']:
        desconocidas = set(df.serie) - set(ETIQ)
        if desconocidas:
            raise ErrorDatos(f'{nombre}: series desconocidas: {", ".join(sorted(desconocidas))}.')
    if df.duplicated(CLAVES[nombre]).any():
        raise ErrorDatos(f'{nombre}: hay claves duplicadas; corrija el origen antes de cargar.')
    return df.sort_values('fecha').reset_index(drop=True) if 'fecha' in df else df


def cargar_todo(data_dir='data', diagnosticos=None):
    mensajes = diagnosticos if diagnosticos is not None else []
    datasets = []
    for nombre in ESQUEMAS:
        obligatorio = nombre in ['series_mensuales.csv', 'pais_mensual.csv', 'via_frontera.csv']
        try:
            df = leer_archivo(nombre, data_dir, mensajes)
        except ErrorDatos as exc:
            if obligatorio:
                raise
            mensajes.append(str(exc))
            df = None
        if df is None:
            if obligatorio:
                raise ErrorDatos(f'Falta {nombre} en {data_dir}. Restaure el CSV requerido.')
            mensajes.append(f'{nombre}: no disponible; se omitirán las vistas dependientes.')
        datasets.append(df)
    series, pais, vf, pron, pca = datasets
    for serie, grupo in series.groupby('serie'):
        esperadas = pd.date_range(grupo.fecha.min(), grupo.fecha.max(), freq='MS')
        faltan = len(esperadas.difference(grupo.fecha))
        if faltan:
            mensajes.append(f'{serie}: faltan {faltan} meses; no se rellenan con ceros.')
    idx = pd.date_range(series.fecha.min(), series.fecha.max(), freq='MS')
    regiones = sorted(pais.region.unique())
    return series, pais, vf, pron, pca, idx, regiones


def agrupar_serie(s, nivel):
    if s.empty:
        return s.copy()
    return s.sort_index().resample('YS' if nivel in ['Año', 'Anual'] else 'MS').sum(min_count=1)


def calcular_variacion_interanual(s, anio):
    """Compara los mismos meses observados del año elegido y el anterior."""
    actual = s[s.index.year == anio].dropna()
    previo = s[(s.index.year == anio - 1) & s.index.month.isin(actual.index.month)].dropna()
    if actual.empty or set(actual.index.month) != set(previo.index.month) or previo.sum() <= 0:
        return None
    return float((actual.sum() / previo.sum() - 1) * 100)


def errores_modelos(series, pron, ms, corte=CORTE):
    columnas = ['fecha', 'modelo', 'observado', 'prediccion', 'error']
    if pron is None or pron.empty:
        return pd.DataFrame(columns=columnas)
    real = series[(series.serie == ms) & (series.fecha >= corte)][['fecha', 'viajeros']]
    pred = pron[(pron.serie == ms) & (pron.fecha >= corte)][['fecha', 'modelo', 'prediccion']]
    pares = pred.merge(real.rename(columns={'viajeros': 'observado'}), on='fecha', how='inner')
    pares = pares[np.isfinite(pares[['prediccion', 'observado']]).all(axis=1)].copy()
    pares['error'] = pares.prediccion - pares.observado
    return pares[columnas]


def calcular_metricas_error(series, pron, ms, corte=CORTE):
    columnas = ['Modelo', 'MAE (Error medio)', 'RMSE', 'N', 'Inicio', 'Fin', 'Estado']
    if pron is None or pron.empty:
        return pd.DataFrame(columns=columnas)
    pares = errores_modelos(series, pron, ms, corte)
    filas = []
    for modelo in sorted(pron.loc[pron.serie == ms, 'modelo'].unique()):
        g = pares[pares.modelo == modelo]
        filas.append({'Modelo': modelo,
            'MAE (Error medio)': round(g.error.abs().mean()) if len(g) else None,
            'RMSE': round(float(np.sqrt((g.error ** 2).mean()))) if len(g) else None,
            'N': len(g), 'Inicio': g.fecha.min() if len(g) else None,
            'Fin': g.fecha.max() if len(g) else None,
            'Estado': 'Evaluable' if len(g) else 'No evaluable: sin fechas comunes'})
    return pd.DataFrame(filas, columns=columnas).sort_values('MAE (Error medio)', na_position='last').reset_index(drop=True)


def cargar_estimaciones_aprobadas(data_dir='data'):
    """Carga el archivo de estimaciones aprobadas por el pipeline de MLOps con metadatos de gobernanza (Laboratorio 11)."""
    ruta = os.path.join(data_dir, 'estimaciones_aprobadas.csv')
    if not os.path.isfile(ruta):
        return None
    try:
        df = pd.read_csv(ruta)
        if 'fecha' in df:
            df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    except Exception:
        return None


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

