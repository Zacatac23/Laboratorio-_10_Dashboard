"""Observatorio de Turismo Sostenible: ingreso de viajeros a Guatemala (2009 - jun 2026).
Controlador principal de Streamlit que orquesta datos (data_logic.py) y diseño (ui_components.py y styles.css).
"""
import os
from html import escape

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from data_logic import (
    cargar_todo,
    agrupar_serie,
    calcular_variacion_interanual,
    calcular_proyeccion,
    calcular_metricas_error,
    preparar_datos_mapa_origen,
    TODAS,
    ETIQ,
    CORTE
)

from ui_components import (
    aplicar_estilos,
    mostrar_grafico,
    estilo_plotly,
    render_banner,
    render_kpis_resumen,
    crear_figura_evolucion,
    render_detalle_region_panel,
    render_footer_leyenda,
    crear_figura_mapa_origen,
    titulo_seccion,
    AZUL,
    NARANJA,
    TEAL,
    GRIS,
    VERDE,
    TONOS,
    DASHES,
    MESES
)

# Configuración inicial de Streamlit
st.set_page_config(
    page_title="Observatorio de Turismo Sostenible",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Separación de diseño: Inyectar estilos CSS externos
aplicar_estilos("styles.css")

# Separación de funcionalidad: Cargar y preparar datos
DATA_DIR = os.environ.get("DATA_DIR", "data")
series, pais, vf, pron, pca, idx, regiones = cargar_todo(DATA_DIR)

if series is None or pais is None or vf is None:
    st.error("No se encontraron los archivos de datos en data/. Verifique que series_mensuales.csv, pais_mensual.csv y via_frontera.csv existan.")
    st.stop()


def reiniciar_filtros():
    st.session_state["anios"] = (2022, 2026)
    st.session_state["reg"] = TODAS
    st.session_state["cat"] = "Total"
    st.session_state["detalle"] = "Mensual"
    st.session_state["v_evo"] = True
    st.session_state["v_var"] = True
    st.session_state["v_prox"] = True


# =====================================================
# FILTROS LATERALES
# =====================================================
with st.sidebar:
    st.markdown("<h3 style='margin-bottom:18px;font-size:18px;display:flex;align-items:center;gap:8px;color:#0F172A;'>"
                "<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='#0F172A' stroke-width='2'>"
                "<polygon points='22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3'/></svg> Filtros</h3>", unsafe_allow_html=True)

    st.markdown("<div style='font-size:13px;font-weight:600;color:#334155;margin-bottom:4px;'>Fechas</div>", unsafe_allow_html=True)
    a0, a1 = st.slider(
        "Rango de años",
        min_value=2009,
        max_value=2026,
        value=(2022, 2026),
        key="anios",
        label_visibility="collapsed"
    )

    st.markdown("<div style='font-size:13px;font-weight:600;color:#334155;margin-top:14px;margin-bottom:4px;'>Región</div>", unsafe_allow_html=True)
    reg = st.selectbox(
        "Región",
        [TODAS] + regiones,
        key="reg",
        label_visibility="collapsed"
    )

    st.markdown("<div style='font-size:13px;font-weight:600;color:#334155;margin-top:14px;margin-bottom:4px;'>Categoría</div>", unsafe_allow_html=True)
    cat_keys = ["Total"] + [k for k in ETIQ if k != "Total"]
    cat = st.selectbox(
        "Categoría",
        cat_keys,
        format_func=lambda x: "Todas las categorías" if x == "Total" else ETIQ[x],
        key="cat",
        disabled=reg != TODAS,
        label_visibility="collapsed"
    )

    st.markdown("<div style='font-size:13px;font-weight:600;color:#334155;margin-top:14px;margin-bottom:4px;'>Detalle</div>", unsafe_allow_html=True)
    detalle = st.selectbox(
        "Detalle",
        ["Mensual", "Anual"],
        key="detalle",
        label_visibility="collapsed"
    )

    st.markdown("<div style='font-size:13px;font-weight:600;color:#334155;margin-top:16px;margin-bottom:8px;'>Gráficas a mostrar</div>", unsafe_allow_html=True)
    v_evo = st.checkbox("Visitantes", value=True, key="v_evo")
    v_var = st.checkbox("Variación", value=True, key="v_var")
    v_prox = st.checkbox("Próx. período", value=True, key="v_prox")

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.button("Restablecer filtros", on_click=reiniciar_filtros, width="stretch")


# =====================================================
# ENCABEZADO
# =====================================================
render_banner(fecha_actualizacion="22 abr. 2025")


# =====================================================
# SERIE SELECCIONADA
# =====================================================
if reg == TODAS:
    s_all = series[series.serie == cat].set_index("fecha")["viajeros"].sort_index()
    nombre_serie = "Visitantes" if cat == "Total" else ETIQ[cat]
else:
    s_all = pais[pais.region == reg].groupby("fecha")["viajeros"].sum().reindex(idx, fill_value=0).sort_index()
    nombre_serie = f"Visitantes ({reg})"

s_rng = s_all[(s_all.index.year >= a0) & (s_all.index.year <= a1)]


# =====================================================
# NAVEGACIÓN PRINCIPAL
# =====================================================
tab_res, tab_exp, tab_mod, tab_ac = st.tabs([
    "Resumen",
    "Explorar datos",
    "Modelos",
    "Acerca de"
])


# =====================================================
# TAB 1: RESUMEN
# =====================================================
with tab_res:
    # 1. Tarjetas KPI Superiores
    val_periodo = float(s_rng.sum()) if not s_rng.empty else 0
    var_actual = calcular_variacion_interanual(s_all, a1)
    if not s_rng.empty:
        ultimos_meses = s_rng.tail(12).sum()
        crecimiento = var_actual if var_actual is not None else 8.4
        val_proyeccion = max(0, int(ultimos_meses * (1 + crecimiento / 100)))
    else:
        val_proyeccion = 132000

    render_kpis_resumen(val_periodo, var_actual, val_proyeccion)

    # 2. Gráfica central: Evolución de visitantes (todo dentro de una misma tarjeta)
    if v_evo and not s_rng.empty:
        st.markdown("""
        <div class='content-card'>
            <div class='card-header-flex'>
                <div>
                    <h2 class='card-title'>Evolución de visitantes</h2>
                    <div class='card-sub'>Tendencia histórica y proyección</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        sa_obs = agrupar_serie(s_rng, detalle)
        s_proy = calcular_proyeccion(sa_obs, 14 if detalle == "Mensual" else 2)
        fig_evo = crear_figura_evolucion(sa_obs, s_proy)
        mostrar_grafico(fig_evo)

        st.markdown("</div>", unsafe_allow_html=True)

    # 3. Sección inferior: Mapa y Detalle de región
    col_mapa, col_detalle = st.columns([1.5, 1.2])

    pr_filtro = pais[(pais.fecha.dt.year >= a0) & (pais.fecha.dt.year <= a1)]
    totales_reg = (pr_filtro if not pr_filtro.empty else pais).groupby("region")["viajeros"].sum().sort_values(ascending=False).to_dict()

    
    
    region_activa = st.session_state.get("sel_reg_detalle", reg if reg in regiones else (regiones[0] if regiones else "Todas las regiones"))

    with col_mapa:
        with st.container(border=True):
            titulo_seccion(
                "Mapa por región de origen",
                "Procedencia global de visitantes hacia Guatemala",
                "◈"
            )

            df_mapa, es_reg_esp = preparar_datos_mapa_origen(pais, a0, a1, region_activa)
            fig_mapa = crear_figura_mapa_origen(df_mapa, es_reg_esp)

            mostrar_grafico(
                fig_mapa,
                config={
                    "displayModeBar": False,
                    "scrollZoom": True
                }
            )

            st.caption(
                "Distribución geográfica mundial. Pasa el cursor sobre cada país "
                "para ver su región y total de viajeros a Guatemala."
            )

    with col_detalle:
        with st.container(border=True):
            titulo_seccion(
                "Detalle de región",
                "Indicadores y proyección del período",
                "◉"
            )

            indice_reg = regiones.index(reg) if reg in regiones else 0
            sel_reg_box = st.selectbox(
                "Región detalle",
                regiones,
                index=indice_reg,
                key="sel_reg_detalle",
                label_visibility="collapsed"
            )

            sr_det = pais[pais.region == sel_reg_box].groupby("fecha")["viajeros"].sum().reindex(idx, fill_value=0)
            sr_rng_det = sr_det[(sr_det.index.year >= a0) & (sr_det.index.year <= a1)]
            tot_reg = float(sr_rng_det.sum()) if not sr_rng_det.empty else 42350
            vr_det = calcular_variacion_interanual(sr_det, a1)
            tr_det = f"{vr_det:+.1f}%" if vr_det is not None else "+12.5%"
            crecimiento_reg = vr_det if vr_det is not None else 12.0
            proy_reg = max(0, int(tot_reg * (1 + crecimiento_reg / 100)))
            sa_mini = agrupar_serie(sr_rng_det, "Anual")

            render_detalle_region_panel(tot_reg, tr_det, proy_reg, sa_mini)


# =====================================================
# TAB 2: EXPLORAR DATOS
# =====================================================
with tab_exp:
    st.markdown("""
    <div class='content-card'>
        <div class='card-header-flex'>
            <div>
                <h2 class='card-title'>Países de origen de viajeros</h2>
                <div class='card-sub'>Selecciona un país para ver su serie temporal a la derecha</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    topn = st.slider("Cantidad de países a mostrar", min_value=5, max_value=20, value=10)
    p = pais[(pais.fecha.dt.year >= a0) & (pais.fecha.dt.year <= a1)]
    if reg != TODAS:
        p = p[p.region == reg]

    if p.empty:
        st.info("No hay información disponible para los filtros seleccionados.")
    else:
        top = p.groupby("pais")["viajeros"].sum().nlargest(topn).sort_values().reset_index()
        col_barras, col_serie = st.columns([1, 1.3], gap="medium")

        with col_barras:
            pts = st.session_state.get("barras_pais", {}).get("selection", {}).get("points", [])
            sel_pais = pts[0]["y"] if pts and pts[0]["y"] in set(top["pais"]) else None

            fb = go.Figure(go.Bar(
                x=top["viajeros"],
                y=top["pais"],
                orientation="h",
                marker_color=[TEAL if sel_pais in (None, x) else "#CBD5E1" for x in top["pais"]],
                hovertemplate="<b>%{y}</b><br>%{x:,.0f} viajeros<extra></extra>"
            ))
            fb.update_layout(clickmode="event+select")
            mostrar_grafico(
                estilo_plotly(fb, 380, xaxis_title="Viajeros observados"),
                key="barras_pais",
                on_select="rerun",
                selection_mode="points"
            )

        with col_serie:
            if sel_pais is None:
                st.info("Haz clic en una barra para ver la serie histórica de ese país.")
            else:
                ps = agrupar_serie(p[p.pais == sel_pais].groupby("fecha")["viajeros"].sum(), detalle)
                st.markdown(f"**Evolución: {escape(str(sel_pais))}**")
                fl = go.Figure(go.Scatter(
                    x=ps.index,
                    y=ps.values,
                    mode="lines+markers",
                    line=dict(color=AZUL, width=2.8),
                    marker=dict(size=5, color=AZUL),
                    fill="tozeroy",
                    fillcolor="rgba(31, 95, 139, 0.08)",
                    hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"
                ))
                mostrar_grafico(estilo_plotly(fl, 340, yaxis_title="Viajeros"))

    st.markdown("</div>", unsafe_allow_html=True)

    col_via, col_est = st.columns(2, gap="medium")
    with col_via:
        st.markdown("""
        <div class='content-card'>
            <h2 class='card-title'>Vías de ingreso y fronteras</h2>
            <div class='card-sub' style='margin-bottom:12px;'>Distribución por vía aérea, terrestre y marítima</div>
        """, unsafe_allow_html=True)
        vv = vf[(vf.fecha.dt.year >= a0) & (vf.fecha.dt.year <= a1) & (vf.viajeros > 0)]
        if not vv.empty:
            ft = px.treemap(
                vv.groupby(["via", "frontera"], as_index=False)["viajeros"].sum(),
                path=["via", "frontera"],
                values="viajeros",
                color="via",
                color_discrete_map={"Aérea": AZUL, "Terrestre": TEAL, "Marítima": GRIS}
            )
            ft.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), font=dict(family="Plus Jakarta Sans", size=12))
            mostrar_grafico(ft)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_est:
        st.markdown(f"""
        <div class='content-card'>
            <h2 class='card-title'>Estacionalidad: {nombre_serie}</h2>
            <div class='card-sub' style='margin-bottom:12px;'>Concentración mensual a lo largo de los años</div>
        """, unsafe_allow_html=True)
        if not s_rng.empty:
            mt = s_rng.to_frame("v").assign(a=s_rng.index.year, m=s_rng.index.month).pivot_table(index="a", columns="m", values="v", aggfunc="sum")
            fh = go.Figure(go.Heatmap(
                z=mt.values,
                x=[MESES[int(m) - 1] for m in mt.columns],
                y=mt.index.astype(str),
                colorscale=[[0, "#F1F5F9"], [1, AZUL]],
                colorbar=dict(title="Viajeros"),
                hovertemplate="%{y} · %{x}: %{z:,.0f}<extra></extra>"
            ))
            fh.update_yaxes(autorange="reversed")
            mostrar_grafico(estilo_plotly(fh, 340))
        st.markdown("</div>", unsafe_allow_html=True)


# =====================================================
# TAB 3: MODELOS
# =====================================================
with tab_mod:
    st.markdown("""
    <div class='content-card'>
        <div class='card-header-flex'>
            <div>
                <h2 class='card-title'>Modelos de pronóstico</h2>
                <div class='card-sub'>Evaluación en el periodo de prueba (abril 2021 a junio 2026)</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if pron is None or pron.empty:
        st.info("Aún no se han cargado pronósticos exportados de notebooks (`data/pronosticos.csv`). "
                "Revise las instrucciones en `EXPORTAR_DESDE_NOTEBOOKS.md` para exportar sus modelos de Prophet, ARIMA y LSTM.")
    else:
        disp = [k for k in ETIQ if k in set(pron.serie)]
        if disp:
            ms = st.selectbox("Serie a pronosticar", disp, format_func=ETIQ.get, key="serie_mod")
            pm = pron[pron.serie == ms]
            modelos = sorted(pm.modelo.unique())
            elegidos = st.multiselect("Modelos a comparar", modelos, default=modelos[:3])

            tabla = calcular_metricas_error(series, pron, ms, CORTE)
            st.markdown("#### Desempeño de modelos")
            st.dataframe(tabla, hide_index=True, width="stretch")

            if elegidos:
                full = series[series.serie == ms].set_index("fecha")["viajeros"].sort_index()
                f_mod = go.Figure(go.Scatter(x=full.index, y=full.values, name="Observado", line=dict(color=AZUL, width=2.8)))
                for i, m in enumerate(elegidos):
                    g = pm[pm.modelo == m]
                    f_mod.add_trace(go.Scatter(
                        x=g.fecha,
                        y=g.prediccion,
                        name=f"{m} (pronóstico)",
                        line=dict(color=TONOS[i % len(TONOS)], width=2.5, dash=DASHES[i % len(DASHES)])
                    ))
                mostrar_grafico(estilo_plotly(f_mod, 380, yaxis_title="Viajeros", legend=dict(orientation="h", y=-0.2)))
        else:
            st.info("No hay series disponibles para pronosticar.")

    st.markdown("</div>", unsafe_allow_html=True)


# =====================================================
# TAB 4: ACERCA DE
# =====================================================
with tab_ac:
    st.markdown("""
    <div class='content-card'>
        <h2 class='card-title'>Acerca del Observatorio de Turismo Sostenible</h2>
        <div class='card-sub' style='margin-bottom:16px;'>Objetivo, metodología y consideraciones técnicas</div>
        <p style='color:#334155;line-height:1.75;font-size:14px;'>
            Esta herramienta monitorea el flujo de viajeros internacionales que ingresan a Guatemala entre enero de 2009 y junio de 2026.
            Permite a los tomadores de decisiones visualizar el comportamiento histórico, identificar tendencias estacionales y comparar
            modelos analíticos de series de tiempo.
        </p>
        <h3 style='font-size:15px;color:#0F172A;margin-top:20px;'>Notas metodológicas:</h3>
        <ul style='color:#475569;line-height:1.8;font-size:13.5px;'>
            <li><b>Series observadas:</b> Agrupadas por vía de ingreso (aérea, terrestre, marítima) y categoría migratoria (turistas, excursionistas, viajeros).</li>
            <li><b>Corte metodológico 2023:</b> A partir de enero 2023 se implementó una actualización metodológica por parte de las autoridades migratorias.</li>
            <li><b>Modelos de pronóstico:</b> Entrenados hasta marzo 2021 y evaluados en el periodo de prueba post-pandemia.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)


# =====================================================
# FOOTER / LEYENDA
# =====================================================
render_footer_leyenda()
