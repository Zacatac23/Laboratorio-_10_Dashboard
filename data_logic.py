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
            df = pd.read_csv(ruta)
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
