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


def render_banner(corte):
    from html import escape
    fecha = f'{MESES[corte.month - 1]} {corte.year}'
    st.markdown(f"""<div class='top-banner'>
      <div class='banner-left'><div class='banner-titles'>
      <h1>Observatorio de Turismo Sostenible</h1>
      <div class='sub'>Ingreso de viajeros a Guatemala · regiones de procedencia</div>
      </div></div><div class='banner-right'><div class='update-box'>
      <div class='lbl'>Datos hasta</div><div class='val'>{escape(fecha)}</div>
      </div></div></div>""", unsafe_allow_html=True)


def render_kpis_resumen(total, variacion, anio):
    c1, c2 = st.columns(2)
    c1.metric('Viajeros en el intervalo seleccionado', f'{total:,.0f}' if total is not None else 'Sin datos')
    c2.metric(f'Variación interanual de {anio}', f'{variacion:+.1f}%' if variacion is not None else 'Sin datos para comparación')
    st.caption('El total acumula el intervalo; la variación compara los meses disponibles del año final '
               'con esos mismos meses del año anterior. No es la variación del intervalo completo.')


def crear_figura_evolucion(observados, nivel='Mensual'):
    fig = go.Figure(go.Scatter(x=observados.index, y=observados.values,
        mode='lines+markers', name='Observado', line=dict(color=AZUL, width=2.5),
        connectgaps=False, hovertemplate='%{x|%Y-%m}: %{y:,.0f} viajeros<extra>Observado</extra>'))
    return estilo_plotly(fig, alto=330, xaxis_title='Año' if nivel == 'Anual' else 'Mes',
                         yaxis_title='Viajeros/año' if nivel == 'Anual' else 'Viajeros/mes')


def render_footer_leyenda():
    st.caption('Azul y línea continua: observado. Naranja y trazos: pronósticos exportados del periodo de evaluación. '
               'Los flujos de viajeros no miden por sí solos sostenibilidad ambiental/social ni demuestran causalidad.')
