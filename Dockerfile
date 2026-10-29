# Dockerfile para Observatorio de Inteligencia Turística (Laboratorio 11)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR="/app/data"

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto (sin incluir microdatos institucionales)
COPY app.py data_logic.py ui_components.py mapa_guatemala.py pipeline.py styles.css guatemala-departments.geojson ./
COPY .streamlit/ .streamlit/
COPY config/ config/
COPY src/ src/
COPY tests/ tests/

# Crear directorios de montaje para persistencia
RUN mkdir -p data logs reports mlruns

EXPOSE 8501 5000

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

