"""Dashboard de flujos de viajeros; reutiliza salidas guardadas, sin entrenar modelos."""
import os
from pathlib import Path
from html import escape
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from data_logic import (cargar_todo, agrupar_serie, calcular_variacion_interanual,
    calcular_metricas_error, preparar_datos_mapa_origen, seleccion_vigente, ErrorDatos, ETIQ, TODAS, CORTE)
from ui_components import (aplicar_estilos, mostrar_grafico, estilo_plotly,
    render_banner, render_kpis_resumen, crear_figura_evolucion, crear_figura_mapa_origen,
    titulo_seccion, render_footer_leyenda,
    AZUL, NARANJA, TEAL, TEAL_DARK, GRIS, VERDE, ROJO, TONOS, DASHES, MESES)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Observatorio de Turismo Sostenible', layout='wide', initial_sidebar_state='auto')
aplicar_estilos(ROOT / 'styles.css')
mensajes = []
try:
    series, pais, vf, pron, pca, idx, regiones = cargar_todo(os.environ.get('DATA_DIR', str(ROOT / 'data')), mensajes)
except ErrorDatos as exc:
    st.error(str(exc))
    st.stop()

VISTAS = {
    'V01': 'Evolución histórica', 'V02': 'Regiones de procedencia',
    'V03': 'Estacionalidad regional', 'V04': 'Países de origen',
    'V05': 'Evolución del país', 'V06': 'Vías y fronteras',
    'V07': 'Calendario mensual', 'V08': 'Observado y pronósticos',
    'V09': 'Errores por modelo',
}
min_anio, max_anio = int(series.fecha.dt.year.min()), int(series.fecha.dt.year.max())
default_anios = (max(min_anio, max_anio - 4), max_anio)


def limpiar_selecciones():
    st.session_state['revision'] = st.session_state.get('revision', 0) + 1
    st.session_state['vias_revision'] = st.session_state.get('vias_revision', 0) + 1
    st.session_state.pop('pais_detalle', None)
    st.session_state['region_detalle'] = st.session_state.get('reg', TODAS)


def reiniciar_filtros():
    for clave, valor in dict(anios=default_anios, reg=TODAS, cat='Total', detalle='Mensual',
            vistas=list(VISTAS), topn=10, serie_mod='Total', metrica='MAE (Error medio)').items():
        st.session_state[clave] = valor
    st.session_state.pop('modelos', None)
    limpiar_selecciones()


def enlazar(origen, destino, opciones):
    puntos = st.session_state.get(origen, {}).get('selection', {}).get('points', [])
    st.session_state[destino] = seleccion_vigente(puntos, opciones)


def mostrar(fig, identidad):
    return mostrar_grafico(fig, key='viz_' + identidad)


with st.sidebar:
    st.header('Filtros de históricos')
    if min_anio < max_anio:
        a0, a1 = st.slider('Rango de años', min_anio, max_anio, default_anios,
                           key='anios', on_change=limpiar_selecciones)
    else:
        a0 = a1 = min_anio
        st.caption(f'Único año disponible: {min_anio}')
    reg = st.selectbox('Región de procedencia', [TODAS] + regiones, key='reg', on_change=limpiar_selecciones)
    categorias = [x for x in ETIQ if x in set(series.serie)]
    if st.session_state.get('cat') not in categorias:
        st.session_state['cat'] = categorias[0]
    cat = st.selectbox('Categoría', categorias, format_func=ETIQ.get, key='cat', disabled=reg != TODAS)
    detalle = st.selectbox('Detalle temporal', ['Mensual', 'Anual'], key='detalle')
    visibles = st.multiselect('Gráficas a mostrar', list(VISTAS), default=list(VISTAS),
                             format_func=VISTAS.get, key='vistas')
    st.button('Restablecer filtros', on_click=reiniciar_filtros, key='reset_global')
    st.caption('Países y regiones no tienen categoría migratoria. Vías/fronteras solo usan fechas. '
               'Modelos tiene su propia serie y periodo de evaluación, independientes de estos filtros.')

render_banner(series.fecha.max())
st.caption(f'Intervalo histórico seleccionado: {a0}–{a1}. Unidad: viajeros. '
           f'Cobertura disponible: {series.fecha.min():%Y-%m} a {series.fecha.max():%Y-%m}; consulte Acerca de.')
if mensajes:
    with st.expander('Avisos de calidad y disponibilidad de datos'):
        for mensaje in mensajes:
            st.warning(mensaje)
if series.fecha.max().month < 12 and a0 <= max_anio <= a1:
    st.info(f'{max_anio} es un año parcial: los datos llegan a {MESES[series.fecha.max().month - 1]}. '
            'Su total anual no equivale a un año completo; no se anualiza.')
tab_res, tab_exp, tab_mod, tab_ac = st.tabs(['Resumen', 'Explorar datos', 'Modelos', 'Acerca de'])

periodo_pais = pais[pais.fecha.dt.year.between(a0, a1)]
p = periodo_pais if reg == TODAS else periodo_pais[periodo_pais.region == reg]
if reg == TODAS:
    s_all = series[series.serie == cat].set_index('fecha').viajeros.sort_index()
    nombre = ETIQ[cat]
else:
    s_all = pais[pais.region == reg].groupby('fecha').viajeros.sum().sort_index()
    nombre = f'Viajeros de {reg}'
s_rng = s_all[s_all.index.year.to_series(index=s_all.index).between(a0, a1)]
revision = st.session_state.get('revision', 0)

with tab_res:
    render_kpis_resumen(float(s_rng.sum()) if not s_rng.empty else None,
                        calcular_variacion_interanual(s_all, a1), a1)
    st.caption('Próximo periodo: no disponible con los modelos exportados. No se extrapolan valores futuros.')
    if 'V01' in visibles:
        st.subheader(f'Evolución histórica — {nombre}')
        st.caption('¿Cómo cambia el volumen? Permite planificar según lo observado; no explica las causas de sus cambios.')
        if s_rng.empty:
            st.info('Sin datos para este intervalo y selección.')
        else:
            mostrar(crear_figura_evolucion(agrupar_serie(s_rng, detalle), detalle), 'V01')
    if 'V02' in visibles:
        st.subheader('Regiones de procedencia')
        st.caption('¿Qué mercados aportan más viajeros? Se muestran todas las regiones, incluido Sin dato. '
                   'Esta comparación usa el intervalo, no restringe las barras a una sola región. '
                   'Haz clic en una barra para cambiar la estacionalidad regional; doble clic en el fondo para limpiar. '
                   'Si seleccionas varias, se utiliza la última.')
        totales = periodo_pais.groupby('region').viajeros.sum().sort_values()
        if totales.empty:
            st.info('Sin datos regionales para el intervalo.')
        else:
            modo_v02 = st.radio('Vista de procedencia', ['Barras comparativas', 'Mapa mundial interactivo'],
                                horizontal=True, key='modo_v02', label_visibility='collapsed')
            if modo_v02 == 'Mapa mundial interactivo':
                df_mapa, es_reg_esp = preparar_datos_mapa_origen(pais, a0, a1, reg)
                fig_mapa = crear_figura_mapa_origen(df_mapa, es_reg_esp)
                mostrar(fig_mapa, 'V02')
                st.caption('Distribución geográfica mundial. Pasa el cursor sobre cada país para ver su procedencia hacia Guatemala.')
            else:
                key_region = f'barras_regiones_{revision}'
                fig = go.Figure(go.Bar(x=totales.values, y=totales.index, orientation='h', marker_color=TEAL,
                    hovertemplate='%{y}: %{x:,.0f} viajeros<extra></extra>'))
                fig.update_layout(clickmode='event+select')
                mostrar_grafico(estilo_plotly(fig, 380, xaxis_title='Viajeros', yaxis_title='Región de procedencia'),
                    key=key_region, on_select=lambda: enlazar(key_region, 'region_detalle', list(totales.index)), selection_mode='points')
    if 'V03' in visibles:
        st.subheader('Estacionalidad de una región')
        opciones = sorted(periodo_pais.region.unique())
        if not opciones:
            st.info('Sin registros regionales en este intervalo.')
        else:
            if st.session_state.get('region_detalle') not in opciones and st.session_state.get('region_detalle') is not None:
                st.session_state['region_detalle'] = reg if reg in opciones else opciones[0]
            if 'region_detalle' not in st.session_state:
                st.session_state['region_detalle'] = reg if reg in opciones else opciones[0]
            rd = st.selectbox('Región del detalle', opciones, key='region_detalle', index=None,
                              placeholder='Selecciona una región o una barra')
            st.caption('¿Qué meses presentan mayor demanda y variabilidad? Cada punto es un mes observado de un año. '
                       'Las cajas resumen la distribución; no son intervalos de confianza ni predicciones. '
                       'Este selector permite comparar otra procedencia sin alterar el filtro global.')
            if rd is None:
                st.info('Selecciona una región para ver su distribución mensual.')
            else:
                regional = periodo_pais[periodo_pais.region == rd].groupby('fecha', as_index=False).viajeros.sum()
                regional['Mes'] = regional.fecha.dt.month.map(lambda m: MESES[m - 1])
                regional['Año'] = regional.fecha.dt.year.astype(str)
                fig = px.box(regional, x='Mes', y='viajeros', points='all', hover_data=['Año'],
                             category_orders={'Mes': MESES}, color_discrete_sequence=[AZUL])
                mostrar(estilo_plotly(fig, 340, yaxis_title='Viajeros/mes', xaxis_title=f'Mes — {rd}'), 'V03')

with tab_exp:
    if 'V04' in visibles or 'V05' in visibles:
        st.subheader('Países de origen de viajeros')
        st.caption('¿Qué mercados de origen concentran el flujo y cómo evolucionan? '
                   'Haz clic en una barra para ver su historia; doble clic en el fondo para limpiar. '
                   'Si seleccionas varias, se utiliza la última. También puedes usar el selector de país.')
        topn = st.slider('Cantidad de países a mostrar', 5, 20, 10, key='topn')
        if p.empty:
            st.info('Sin información para los filtros seleccionados.')
        else:
            top = p.groupby('pais').viajeros.sum().nlargest(topn).sort_values()
            opciones_pais = list(top.index)
            if 'pais_detalle' not in st.session_state:
                st.session_state['pais_detalle'] = opciones_pais[-1]
            elif st.session_state['pais_detalle'] not in opciones_pais and st.session_state['pais_detalle'] is not None:
                st.session_state['pais_detalle'] = None
            if 'V04' in visibles:
                key_pais = f'barras_pais_{revision}'
                sel = st.session_state.get('pais_detalle')
                fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation='h',
                    marker_color=TEAL,
                    hovertemplate='%{y}: %{x:,.0f} viajeros<extra></extra>'))
                fig.update_layout(clickmode='event+select')
                mostrar_grafico(estilo_plotly(fig, 380, xaxis_title='Viajeros observados', yaxis_title='País'),
                    key=key_pais, on_select=lambda: enlazar(key_pais, 'pais_detalle', opciones_pais), selection_mode='points')
            if 'V05' in visibles:
                elegido = st.selectbox('País del detalle', opciones_pais, key='pais_detalle', index=None,
                                       placeholder='Selecciona un país o una barra')
                if elegido is None:
                    st.info('Selecciona un país para ver su evolución histórica.')
                else:
                    st.markdown(f'**Evolución: {elegido}**')
                    ps = p[p.pais == elegido].groupby('fecha').viajeros.sum()
                    mostrar(crear_figura_evolucion(agrupar_serie(ps, detalle), detalle), 'V05')
    if 'V06' in visibles:
        st.subheader('Vías de ingreso y fronteras')
        st.caption('¿Dónde se concentra el ingreso? Haz clic en una vía para desglosar sus fronteras; '
                   'usa «Volver a todas las vías» para regresar. Solo aplica el rango de fechas: este CSV no contiene país, región ni categoría.')
        vv = vf[vf.fecha.dt.year.between(a0, a1) & (vf.viajeros > 0)]
        if vv.empty:
            st.info('Sin datos de vías/fronteras para este intervalo.')
        else:
            fig = px.treemap(vv.groupby(['via', 'frontera'], as_index=False).viajeros.sum(),
                path=[px.Constant('Todas las vías'), 'via', 'frontera'], values='viajeros', color='via',
                color_discrete_map={'Aérea': AZUL, 'Terrestre': TEAL, 'Marítima': GRIS})
            fig.update_traces(hovertemplate='%{label}: %{value:,.0f} viajeros<extra></extra>')
            if st.button('Volver a todas las vías', key='reset_vias'):
                st.session_state['vias_revision'] = st.session_state.get('vias_revision', 0) + 1
            mostrar(estilo_plotly(fig, 400), f"V06_{st.session_state.get('vias_revision', 0)}")
    if 'V07' in visibles:
        st.subheader(f'Calendario mensual — {nombre}')
        st.caption('¿Qué meses y años concentran más viajeros? Pasa el cursor para consultar cada cifra. '
                   'Las celdas sin observación quedan vacías; no equivalen a cero.')
        if s_rng.empty:
            st.info('Sin datos para construir el calendario.')
        else:
            mt = s_rng.to_frame('v').assign(a=s_rng.index.year, m=s_rng.index.month).pivot_table(index='a', columns='m', values='v', aggfunc='sum')
            fig = go.Figure(go.Heatmap(z=mt.values, x=[MESES[m-1] for m in mt.columns],
                y=[str(x) for x in mt.index], colorscale=[[0, '#F1F5F9'], [1, AZUL]],
                colorbar=dict(title='Viajeros/mes'), hovertemplate='%{y} · %{x}: %{z:,.0f} viajeros<extra></extra>', hoverongaps=False))
            fig = estilo_plotly(fig, 350, xaxis_title='Mes', yaxis_title='Año')
            fig.update_yaxes(type='category', autorange='reversed', tickformat=None)
            mostrar(fig, 'V07')

with tab_mod:
    st.subheader('Modelos de pronóstico: evaluación histórica')
    st.caption('Esta sección utiliza su propia serie y todos los pares de evaluación desde abril de 2021; '
               'los filtros laterales de históricos no cambian sus métricas. No son pronósticos para fechas posteriores al archivo exportado.')
    st.info('Origen L1/L2 declarado en la guía de exportación; pendiente de verificar con notebooks o enlaces versionados. '
            'No se entrenan modelos en este dashboard. No hay intervalos de confianza exportados.')
    if pron is None or pron.empty:
        st.info('No hay pronósticos válidos disponibles. Revise data/pronosticos.csv y los avisos de carga.')
    else:
        disponibles = [s for s in ETIQ if s in set(pron.serie)]
        if st.session_state.get('serie_mod') not in disponibles:
            st.session_state['serie_mod'] = disponibles[0]
        ms = st.selectbox('Serie a evaluar', disponibles, format_func=ETIQ.get, key='serie_mod')
        pm = pron[pron.serie == ms]
        modelos = sorted(pm.modelo.unique())
        if 'modelos' in st.session_state:
            st.session_state['modelos'] = [m for m in st.session_state['modelos'] if m in modelos]
        preferidos = [m for m in ['ARIMA/SARIMA (mejor)', 'Prophet', 'LSTM'] if m in modelos]
        elegidos = st.multiselect('Modelos a comparar', modelos, default=preferidos or modelos[:3], key='modelos')
        tabla = calcular_metricas_error(series, pron, ms, CORTE)
        tabla = tabla[tabla.Modelo.isin(elegidos)]
        st.caption(f'Pronósticos exportados de esta serie: {pm.fecha.min():%Y-%m} a {pm.fecha.max():%Y-%m}. '
                   'MAE: error absoluto promedio; RMSE: da mayor peso a errores grandes. Ambos en viajeros/mes; menor es mejor. '
                   'N indica cuántos meses observados y pronosticados coinciden. No se limitan los ejes ni se recortan predicciones.')
        negativos = pm.assign(Negativos=pm.prediccion.lt(0)).groupby('modelo').Negativos.sum().reindex(elegidos)
        if negativos.sum():
            st.warning('Algunos pronósticos son negativos y no son físicamente interpretables como viajeros. '
                       'Se conservan en gráficos y métricas originales. Por modelo seleccionado: ' +
                       '; '.join(f'{m}: {int(n)}' for m, n in negativos.items()))
        st.dataframe(tabla, hide_index=True, width='stretch')
        if not elegidos:
            st.info('Selecciona al menos un modelo para mostrar resultados y errores.')
        else:
            if (tabla.N == 0).any():
                st.warning('Hay modelos no evaluables: no existen fechas comunes con los datos observados. No se inventan métricas.')
            if tabla.N.nunique() > 1:
                st.warning('Las coberturas difieren entre modelos: compare solo periodos comunes; revise N, Inicio y Fin.')
            if 'V08' in visibles:
                st.subheader('Observado frente a pronósticos exportados')
                st.caption('¿Qué modelos reproducen mejor la trayectoria observada? Las curvas son evaluación retrospectiva; no demuestran causalidad.')
                full = series[(series.serie == ms) & (series.fecha >= CORTE)]
                fig = go.Figure(go.Scatter(x=full.fecha, y=full.viajeros, name='Observado', line=dict(color=AZUL, width=2.8)))
                for i, modelo in enumerate(elegidos):
                    g = pm[pm.modelo == modelo]
                    fig.add_trace(go.Scatter(x=g.fecha, y=g.prediccion, name=f'{modelo} (evaluación)',
                        line=dict(color=TONOS[i % len(TONOS)], dash=DASHES[i % len(DASHES)])))
                mostrar(estilo_plotly(fig, 420, xaxis_title='Mes de evaluación', yaxis_title='Viajeros/mes',
                                      legend=dict(orientation='h', y=-.3)), 'V08')
            if 'V09' in visibles:
                st.subheader('Desempeño por modelo')
                st.caption('¿Qué modelo comete menos error? Compara la magnitud de errores sobre pares disponibles; '
                           'no mide incertidumbre futura ni sustituye validar el origen de los modelos.')
                metrica = st.selectbox('Métrica de error', ['MAE (Error medio)', 'RMSE'], key='metrica')
                evaluables = tabla[tabla.N > 0].sort_values(metrica)
                if evaluables.empty:
                    st.info('No evaluable: no hay pares reales/pronosticados para comparar errores.')
                else:
                    fig = px.bar(evaluables, x=metrica, y='Modelo', orientation='h',
                        hover_data=['N', 'Inicio', 'Fin'], color_discrete_sequence=[TEAL])
                    mostrar(estilo_plotly(fig, 350, xaxis_title=f'{metrica} — viajeros/mes'), 'V09')

with tab_ac:
    st.subheader('Acerca del observatorio')
    st.write('El tablero describe ingresos de viajeros a Guatemala por fecha, procedencia, vía y categoría. '
             'Las regiones son de procedencia, no destinos dentro de Guatemala. Incluye categorías migratorias '
             'como tránsito, comercio fronterizo y cruceristas; viajeros no equivale exclusivamente a turistas.')
    st.write(f'Cobertura verificada en series_mensuales.csv: {series.fecha.min():%Y-%m} a {series.fecha.max():%Y-%m}. '
             'Los archivos pais_mensual.csv y via_frontera.csv respaldan las desagregaciones. '
             'preparar_datos.py declara un Excel INGUAT como origen, pero el Excel y su trazabilidad no están en este repositorio.')
    st.write('Los CSV contienen cantidades fraccionarias que se muestran redondeadas; su significado en la fuente está pendiente de documentar. '
             'No se certifica el cambio metodológico de 2023 sin la fuente original. La cobertura geográfica/temporal '
             'y los faltantes limitan las comparaciones; meses ausentes no se completan con datos inventados.')
    st.write('pronosticos.csv contiene resultados preexistentes de seis familias de modelos. El origen L1/L2 está declarado, '
             'no verificado. Los artefactos de entrenamiento, parámetros, particiones originales e intervalos de confianza '
             'no están disponibles. Las métricas se recalculan con pares de meses coincidentes desde abril de 2021.')
    st.write('No existen variables ambientales, sociales, capacidad disponible ni evidencia causal en estos CSV. '
             'Los cambios de flujo orientan la exploración y planificación; no certifican sostenibilidad ni causas de crecimiento.')
render_footer_leyenda()
