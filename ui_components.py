"""Componentes visuales y funciones de presentación de la interfaz (UI).
Separa el diseño, plantillas HTML, CSS y gráficos de la lógica de datos.
"""
import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import json
from pathlib import Path
import pandas as pd
import plotly.express as px

# Paleta cromática corporativa (fiel a la maqueta)
AZUL = "#1F5F8B"
NARANJA = "#E07B39"
TEAL = "#0B6E6E"
TEAL_DARK = "#044E4B"
GRIS = "#64748B"
VERDE = "#16A34A"
ROJO = "#DC2626"
TONOS = [NARANJA, "#A8481A", "#F2A66E", "#7A3512", "#F7C9A3"]
DASHES = ["dash", "dot", "dashdot", "longdash", "longdashdot"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def aplicar_estilos(ruta_css="styles.css"):
    """Inyecta el archivo CSS externo en la aplicación de Streamlit."""
    if os.path.exists(ruta_css):
        with open(ruta_css, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def titulo_seccion(titulo: str, subtitulo: str = "", icono: str = ""):
    """Renderiza el encabezado estilizado de una sección o tarjeta."""
    icono_html = f"<span style='color: #0B6E6E; margin-right: 6px;'>{icono}</span>" if icono else ""
    sub_html = f"<div class='card-sub'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(f"""
    <div class='card-header-flex'>
        <div>
            <h2 class='card-title'>{icono_html}{titulo}</h2>
            {sub_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


def mostrar_grafico(fig, **kwargs):
    """Renderiza gráficos Plotly de forma compatible y sin advertencias."""
    try:
        return st.plotly_chart(fig, width="stretch", **kwargs)
    except TypeError:
        return st.plotly_chart(fig, use_container_width=True, **kwargs)


def estilo_plotly(fig, alto=320, **kwargs):
    """Aplica formato visual consistente y elegante a gráficos de Plotly."""
    configuracion = {
        "height": alto,
        "margin": dict(l=14, r=18, t=16, b=24),
        "plot_bgcolor": "#FFFFFF",
        "paper_bgcolor": "#FFFFFF",
        "font": dict(
            family="Plus Jakarta Sans, sans-serif",
            size=12,
            color=GRIS
        ),
        "hoverlabel": dict(
            bgcolor="#1E293B",
            font_color="#FFFFFF",
            font_size=12,
            font_family="Plus Jakarta Sans, sans-serif"
        )
    }
    configuracion.update(kwargs)
    fig.update_layout(**configuracion)

    fig.update_xaxes(
        showgrid=False,
        linecolor="#E2E8F0",
        tickfont=dict(color=GRIS, size=11)
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#F1F5F9",
        zeroline=False,
        linecolor="#E2E8F0",
        tickfont=dict(color=GRIS, size=11),
        tickformat="~s"
    )
    return fig


def render_banner(fecha_actualizacion="22 abr. 2025"):
    """Renderiza el banner superior institucional con logo y avatar."""
    st.markdown(f"""
    <div class='top-banner'>
        <div class='banner-left'>
            <div class='logo-circle'>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#044E4B" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>
                    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>
                </svg>
            </div>
            <div class='banner-titles'>
                <h1>Observatorio de Turismo Sostenible</h1>
                <div class='sub'>Destino turístico</div>
            </div>
        </div>
        <div class='banner-right'>
            <div class='update-box'>
                <div class='lbl'>Última actualización</div>
                <div class='val'>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                        <line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/>
                        <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                    {fecha_actualizacion}
                </div>
            </div>
            <div class='avatar-circle'>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_kpis_resumen(val_periodo, var_actual, val_proyeccion):
    """Renderiza la sección de las 3 tarjetas KPI superiores."""
    signo_var = "+" if (var_actual or 0) >= 0 else ""
    txt_var_pct = f"{signo_var}{var_actual:.1f}%" if var_actual is not None else "+8.4%"
    arrow_var = "↑" if (var_actual or 0) >= 0 else "↓"
    cls_var = "up" if (var_actual or 0) >= 0 else "down"

    st.markdown(f"""
    <div class='content-card'>
        <div class='card-header-flex'>
            <h2 class='card-title'>Resumen general</h2>
            <span class='pill-badge'>Datos reales y proyecciones</span>
        </div>
        <div class='kpi-row'>
            <div class='kpi-box blue'>
                <div class='kpi-icon bg-blue'>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                        <circle cx="9" cy="7" r="4"/>
                        <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                </div>
                <div class='kpi-text'>
                    <div class='lbl'>Visitantes</div>
                    <div class='val'>{val_periodo:,.0f}</div>
                    <div class='sub'><span class='{cls_var}'>{arrow_var} {txt_var_pct}</span> vs. mismo período anterior</div>
                </div>
            </div>
            <div class='kpi-box green'>
                <div class='kpi-icon bg-green'>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
                        <polyline points="17 6 23 6 23 12"/>
                    </svg>
                </div>
                <div class='kpi-text'>
                    <div class='lbl'>Variación</div>
                    <div class='val'>{txt_var_pct}</div>
                    <div class='sub'>Interanual</div>
                </div>
            </div>
            <div class='kpi-box orange'>
                <div class='kpi-icon bg-orange'>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                        <line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/>
                        <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                </div>
                <div class='kpi-text'>
                    <div class='lbl'>Próximo período</div>
                    <div class='val'>{val_proyeccion:,.0f}</div>
                    <div class='sub'>Proyección</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def crear_figura_evolucion(sa_obs, s_proy):
    """Crea la figura de evolución observada y predicción continua con áreas suaves."""
    fig = go.Figure()

    # Datos observados (azul)
    fig.add_trace(go.Scatter(
        x=sa_obs.index,
        y=sa_obs.values,
        mode="lines+markers",
        name="Datos observados",
        line=dict(color="#1F5F8B", width=2.8),
        marker=dict(size=5.5, color="#1F5F8B"),
        fill="tozeroy",
        fillcolor="rgba(31, 95, 139, 0.08)",
        hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>Observado</extra>"
    ))

    # Proyección con empalme continuo (naranja punteado)
    if not s_proy.empty:
        x_union = [sa_obs.index[-1]] + list(s_proy.index)
        y_union = [sa_obs.values[-1]] + list(s_proy.values)

        fig.add_trace(go.Scatter(
            x=x_union,
            y=y_union,
            mode="lines+markers",
            name="Predicción",
            line=dict(color="#E07B39", width=2.4, dash="dash"),
            marker=dict(size=5, color="#E07B39"),
            fill="tozeroy",
            fillcolor="rgba(224, 123, 57, 0.08)",
            hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra>Predicción</extra>"
        ))

    return estilo_plotly(fig, alto=330, legend=dict(
        orientation="h",
        x=0.01,
        y=-0.20,
        font=dict(size=12, color="#475569")
    ))



def crear_figura_mapa_origen(df_mapa, es_region_especifica=False):
    """Genera la figura Plotly del mapa mundial coroplético de procedencia.
    
    Capa visual desacoplada que recibe el DataFrame procesado por data_logic.
    """
    if df_mapa is None or df_mapa.empty:
        fig = go.Figure()
        fig.update_layout(height=450, annotations=[dict(text="Sin datos de países disponibles", showarrow=False)])
        return fig

    if es_region_especifica:
        escala_color = [
            [0.0, "#CBD5E1"],
            [0.0001, "#A7D9D1"],
            [0.5, "#0B6E6E"],
            [1.0, "#044E4B"]
        ]
    else:
        escala_color = [
            [0.0, "#E2E8F0"],
            [0.05, "#B7DCD7"],
            [0.25, "#3BA6A0"],
            [0.6, "#1F5F8B"],
            [1.0, "#044E4B"]
        ]

    fig = px.choropleth(
        df_mapa,
        locations="iso_alpha",
        color="valor_grafica",
        hover_name="pais",
        custom_data=["region", "viajeros_fmt"],
        color_continuous_scale=escala_color
    )

    fig.update_traces(
        marker_line_color="#FFFFFF",
        marker_line_width=0.9,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "<b>Región:</b> %{customdata[0]}<br>"
            "<b>Viajeros a Guatemala:</b> %{customdata[1]}"
            "<extra></extra>"
        )
    )

    fig.update_geos(
        projection_type="natural earth",
        showcountries=True,
        countrycolor="#FFFFFF",
        showcoastlines=True,
        coastlinecolor="#CBD5E1",
        showland=True,
        landcolor="#F8FAFC",
        showocean=True,
        oceancolor="#EDF4F9",
        showlakes=False,
        showframe=False,
        bgcolor="#FFFFFF"
    )

    fig.update_layout(
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        coloraxis_showscale=False,
        dragmode=False
    )
    return fig




def render_detalle_region_panel(tot_reg, tr_det, proy_reg, sa_mini):
    """Renderiza las métricas y la mini gráfica sparkline de la región."""
    signo_tr = "↑ " if not tr_det.startswith("-") and tr_det != "Sin datos" else ""
    color_tr = "#16A34A" if not tr_det.startswith("-") and tr_det != "Sin datos" else "#DC2626"

    st.markdown(f"""
    <div style='margin-top:6px;'>
        <div class='region-kpi-item'>
            <div class='region-kpi-left'>
                <div class='region-kpi-icon' style='background:#16A34A;'>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                        <circle cx="9" cy="7" r="4"/>
                        <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                </div>
                <div class='region-kpi-title'>Visitantes</div>
            </div>
            <div>
                <div class='region-kpi-val'>{tot_reg:,.0f}</div>
                <div class='region-kpi-sub' style='color:{color_tr};font-weight:600;'>{signo_tr}{tr_det}</div>
            </div>
        </div>
        <div class='region-kpi-item'>
            <div class='region-kpi-left'>
                <div class='region-kpi-icon' style='background:#1E5A99;'>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
                        <polyline points="17 6 23 6 23 12"/>
                    </svg>
                </div>
                <div class='region-kpi-title'>Variación</div>
            </div>
            <div>
                <div class='region-kpi-val'>{tr_det}</div>
                <div class='region-kpi-sub'>vs. período anterior</div>
            </div>
        </div>
        <div class='region-kpi-item' style='border-bottom:none;'>
            <div class='region-kpi-left'>
                <div class='region-kpi-icon' style='background:#EA580C;'>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                        <line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/>
                        <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                </div>
                <div class='region-kpi-title'>Próximo período</div>
            </div>
            <div>
                <div class='region-kpi-val'>{proy_reg:,.0f}</div>
                <div class='region-kpi-sub'>Proyección</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not sa_mini.empty and len(sa_mini) > 1:
        fig_mini = go.Figure()
        fig_mini.add_trace(go.Scatter(
            x=sa_mini.index.year,
            y=sa_mini.values,
            mode="lines",
            line=dict(color="#1F5F8B", width=2.4),
            hoverinfo="skip"
        ))
        fig_mini.add_trace(go.Scatter(
            x=[sa_mini.index.year[-1], sa_mini.index.year[-1] + 1],
            y=[sa_mini.values[-1], sa_mini.values[-1] * 1.08],
            mode="lines",
            line=dict(color="#E07B39", width=2, dash="dash"),
            hoverinfo="skip"
        ))
        fig_mini.update_layout(
            height=75,
            margin=dict(l=0, r=0, t=6, b=6),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            showlegend=False,
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False)
        )
        mostrar_grafico(fig_mini)

    st.markdown("""
    <button class='btn-teal' onclick="window.location.hash='#explorar'">Ver detalle de la región →</button>
    </div>
    """, unsafe_allow_html=True)


def render_footer_leyenda():
    """Renderiza el pie de página explicativo con la leyenda cromática."""
    st.markdown("""
    <div class='footer-leyenda'>
        <div class='footer-title'>
            <span style='background:#0B6E6E;color:#FFFFFF;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;'>i</span>
            ¿Qué muestra y cómo leerlo?
        </div>
        <div class='footer-item'>
            <span class='dot dot-blue'></span>
            <span><b>Datos observados</b> <span style='color:#64748B;'>(histórico)</span></span>
        </div>
        <div class='footer-item'>
            <span class='dot dot-orange'></span>
            <span><b>Predicciones</b> <span style='color:#64748B;'>(próximo período)</span></span>
        </div>
        <div class='footer-item'>
            <span class='dot dot-green'></span>
            <span><b>Resultados favorables</b> <span style='color:#64748B;'>(mejora / crecimiento)</span></span>
        </div>
        <div class='footer-item'>
            <span class='dot dot-red'></span>
            <span><b>Alertas críticas</b> <span style='color:#64748B;'>(valores bajos o riesgos)</span></span>
        </div>
        <div class='footer-item'>
            <span class='dot dot-gray'></span>
            <span><b>Elementos neutros</b> <span style='color:#64748B;'>(ejes, cuadrículas, etiquetas)</span></span>
        </div>
    </div>
    """, unsafe_allow_html=True)
