"""Componentes visuales y funciones de presentación de la interfaz (UI).
Separa el diseño, plantillas HTML, CSS y gráficos de la lógica de datos.
"""
import os
import streamlit as st
import plotly.graph_objects as go
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


def crear_figura_mapa_regiones(totales_reg, region_actual):
    """Genera la visualización del mapa coroplético estilizado idéntico al mockup."""
    # Determinación de color por rangos
    def get_color(val):
        if val >= 150000:
            return "#1A4B75"
        elif val >= 100000:
            return "#2A6EA6"
        elif val >= 50000:
            return "#4B92C9"
        elif val >= 20000:
            return "#82B8DF"
        else:
            return "#CBE3F3"

    regiones_ordenadas = list(totales_reg.keys()) or ["América Central", "América del Norte", "Europa", "América del Sur", "Otros"]

    # Definición de 5 polígonos territoriales que componen el mapa continuo
    poligonos = [
        # 1. Región Central / Núcleo
        {
            "name": regiones_ordenadas[0] if len(regiones_ordenadas) > 0 else "América Central",
            "x": [0.26, 0.38, 0.44, 0.39, 0.28, 0.24, 0.26],
            "y": [0.52, 0.58, 0.50, 0.32, 0.30, 0.40, 0.52],
            "cx": 0.34, "cy": 0.44
        },
        # 2. Región Norte
        {
            "name": regiones_ordenadas[1] if len(regiones_ordenadas) > 1 else "América del Norte",
            "x": [0.22, 0.32, 0.40, 0.45, 0.36, 0.25, 0.16, 0.22],
            "y": [0.60, 0.78, 0.82, 0.70, 0.59, 0.58, 0.56, 0.60],
            "cx": 0.30, "cy": 0.68
        },
        # 3. Región Este / Noreste
        {
            "name": regiones_ordenadas[2] if len(regiones_ordenadas) > 2 else "Europa",
            "x": [0.44, 0.56, 0.60, 0.52, 0.45, 0.44],
            "y": [0.70, 0.74, 0.56, 0.48, 0.50, 0.70],
            "cx": 0.50, "cy": 0.60
        },
        # 4. Región Sureste
        {
            "name": regiones_ordenadas[3] if len(regiones_ordenadas) > 3 else "América del Sur",
            "x": [0.39, 0.52, 0.58, 0.54, 0.46, 0.38, 0.39],
            "y": [0.32, 0.48, 0.42, 0.26, 0.16, 0.20, 0.32],
            "cx": 0.46, "cy": 0.32
        },
        # 5. Región Sur / Insular
        {
            "name": regiones_ordenadas[4] if len(regiones_ordenadas) > 4 else "Otros Países",
            "x": [0.46, 0.54, 0.66, 0.68, 0.58, 0.48, 0.46],
            "y": [0.16, 0.26, 0.24, 0.14, 0.10, 0.11, 0.16],
            "cx": 0.58, "cy": 0.18
        }
    ]

    fig = go.Figure()

    # Dibujar cada región polígono
    for poly in poligonos:
        nom = poly["name"]
        val = totales_reg.get(nom, 35000)
        c = get_color(val)
        is_sel = (nom == region_actual)

        fig.add_trace(go.Scatter(
            x=poly["x"],
            y=poly["y"],
            fill="toself",
            fillcolor=c,
            mode="lines",
            line=dict(color="#FFFFFF", width=2.2 if not is_sel else 3),
            name=nom,
            text=f"<b>{nom}</b><br>Viajeros: {val:,.0f}",
            hoverinfo="text",
            showlegend=False
        ))

    # Etiqueta / Tooltip badge apuntando a la región seleccionada
    target_poly = next((p for p in poligonos if p["name"] == region_actual), poligonos[0])
    fig.add_annotation(
        x=target_poly["cx"],
        y=target_poly["cy"],
        text=f"<b>{region_actual}</b>",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1.5,
        arrowcolor="#044E4B",
        ax=0,
        ay=-38,
        bgcolor="#044E4B",
        font=dict(color="#FFFFFF", size=12, family="Plus Jakarta Sans"),
        borderpad=6,
        borderwidth=0
    )

    # Leyenda cromática vertical a la derecha (idéntica a la maqueta)
    rangos_leyenda = [
        ("> 150k", "#1A4B75"),
        ("100k – 150k", "#2A6EA6"),
        ("50k – 100k", "#4B92C9"),
        ("20k – 50k", "#82B8DF"),
        ("< 20k", "#CBE3F3")
    ]
    for idx_l, (lbl, col) in enumerate(rangos_leyenda):
        # Punto de color
        fig.add_trace(go.Scatter(
            x=[0.82],
            y=[0.80 - idx_l * 0.14],
            mode="markers",
            marker=dict(size=12, color=col, line=dict(color="#CBD5E1", width=1)),
            hoverinfo="none",
            showlegend=False
        ))
        # Texto del rango
        fig.add_annotation(
            x=0.85,
            y=[0.80 - idx_l * 0.14][0],
            text=lbl,
            showarrow=False,
            xanchor="left",
            font=dict(size=11.5, color="#475569", family="Plus Jakarta Sans")
        )

    fig.update_layout(
        height=320,
        margin=dict(l=0, r=10, t=10, b=0),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.08, 1.08]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.02, 0.92])
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
