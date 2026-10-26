
"""
Mapa interactivo de los departamentos de Guatemala.

Responsabilidades:
- Cargar el archivo GeoJSON.
- Dibujar los 22 departamentos.
- Mantener las proporciones geográficas.
- Mostrar los nombres al pasar el cursor.
- Generar una figura lista para Streamlit.
"""

import json
from pathlib import Path

import plotly.graph_objects as go


RUTA_GEOJSON = (
    Path(__file__).resolve().parent
    / "guatemala-departments.geojson"
)

COLORES = [
    "#0B6E6E",
    "#16817F",
    "#279390",
    "#3BA6A0",
    "#5CB7AE",
    "#83C9BF",
    "#A3DAD0"
]


def cargar_geojson():
    """Lee el GeoJSON de Guatemala."""

    if not RUTA_GEOJSON.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo: {RUTA_GEOJSON}"
        )

    with open(
        RUTA_GEOJSON,
        "r",
        encoding="utf-8-sig"
    ) as archivo:
        datos = json.load(archivo)

    if datos.get("type") != "FeatureCollection":
        raise ValueError(
            "El archivo no contiene una colección GeoJSON válida."
        )

    return datos


def obtener_poligonos(geometria):
    """Extrae polígonos de geometrías Polygon y MultiPolygon."""

    tipo = geometria.get("type")
    coordenadas = geometria.get("coordinates", [])

    if tipo == "Polygon":
        return [coordenadas]

    if tipo == "MultiPolygon":
        return coordenadas

    return []


def crear_mapa_guatemala():
    """Genera el mapa vectorial de los departamentos."""

    geojson = cargar_geojson()

    fig = go.Figure()

    todas_longitudes = []
    todas_latitudes = []

    for indice, feature in enumerate(geojson["features"]):

        nombre = feature.get("properties", {}).get(
            "shapeName",
            f"Departamento {indice + 1}"
        )

        geometria = feature.get("geometry") or {}
        poligonos = obtener_poligonos(geometria)

        color = COLORES[indice % len(COLORES)]

        for poligono in poligonos:
            if not poligono:
                continue

            # El primer anillo es el contorno exterior.
            exterior = poligono[0]

            if len(exterior) < 3:
                continue

            longitudes = [p[0] for p in exterior]
            latitudes = [p[1] for p in exterior]

            todas_longitudes.extend(longitudes)
            todas_latitudes.extend(latitudes)

            
            fig.add_trace(
                go.Scatter(
                    x=longitudes,
                    y=latitudes,
                    mode="lines",
                    fill="toself",
                    fillcolor=color,
                    line=dict(
                        color="#FFFFFF",
                        width=1.25
                    ),
                    name=nombre,
                    text=[nombre] * len(longitudes),
                    hoveron="fills",
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "País: Guatemala<br>"
                        "División: Departamento<br>"
                        "Indicador: Límites geográficos"
                        "<extra></extra>"
                    ),
                    showlegend=False
                )
            )


            # Dibujar huecos interiores, si existen.
            # El fondo se mantiene blanco.
            for anillo in poligono[1:]:
                fig.add_trace(
                    go.Scatter(
                        x=[p[0] for p in anillo],
                        y=[p[1] for p in anillo],
                        mode="lines",
                        fill="toself",
                        fillcolor="#FFFFFF",
                        line=dict(
                            color="#FFFFFF",
                            width=1
                        ),
                        hoverinfo="skip",
                        showlegend=False
                    )
                )

    if not todas_longitudes or not todas_latitudes:
        raise ValueError(
            "El GeoJSON no contiene coordenadas válidas."
        )

    min_lon = min(todas_longitudes)
    max_lon = max(todas_longitudes)
    min_lat = min(todas_latitudes)
    max_lat = max(todas_latitudes)

    centro_lat = (min_lat + max_lat) / 2

    # Ajuste aproximado de longitud a latitud
    # para evitar que el mapa se vea deformado.
    import math

    factor = math.cos(math.radians(centro_lat))

    centro_lon = (min_lon + max_lon) / 2
    centro_y = (min_lat + max_lat) / 2

    ancho = (max_lon - min_lon) * factor
    alto = max_lat - min_lat

    # Proporción del área de dibujo.
    # Se deja espacio alrededor del mapa.
    proporcion_panel = 1.08

    alto_final = max(alto, ancho / proporcion_panel) * 1.12
    ancho_final = alto_final * proporcion_panel

    rango_lon = ancho_final / factor

    fig.update_layout(
        height=520,
        margin=dict(
            l=8,
            r=8,
            t=8,
            b=8
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        showlegend=False,
        hovermode="closest",
        dragmode=False,

        xaxis=dict(
            visible=False,
            range=[
                centro_lon - rango_lon / 2,
                centro_lon + rango_lon / 2
            ],
            fixedrange=True,
            constrain="domain"
        ),

        yaxis=dict(
            visible=False,
            range=[
                centro_y - alto_final / 2,
                centro_y + alto_final / 2
            ],
            fixedrange=True,
            scaleanchor="x",
            scaleratio=1 / factor,
            constrain="domain"
        )
    )

    return fig
