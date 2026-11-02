# Observatorio de Inteligencia Turística (Laboratorio 11)
# Imagen única para tablero, servidor MLflow y pipeline batch.
# No contiene datos: data/, logs/, reports/ y el almacén MLflow se montan como volúmenes
# (ver .dockerignore, que funciona como lista blanca de código).
FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    DATA_DIR="/app/data"

WORKDIR /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock && pip check

COPY app.py data_logic.py ui_components.py mapa_guatemala.py pipeline.py styles.css guatemala-departments.geojson ./
COPY .streamlit/config.toml .streamlit/config.toml
COPY config/ config/
COPY src/ src/

# Usuario sin privilegios; puntos de montaje vacíos y con dueño correcto
RUN useradd --create-home --uid 1000 app \
    && mkdir -p data logs reports /mlflow \
    && chown -R app:app /app/data /app/logs /app/reports /mlflow
USER app

EXPOSE 8501 5000

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
