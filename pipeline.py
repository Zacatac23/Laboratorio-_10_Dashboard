"""Entrypoint raíz para la ejecución del Pipeline MLOps (Laboratorio 11).
Uso:
    python pipeline.py
    python pipeline.py --config config/pipeline_config.yaml --publish
    python pipeline.py --no-publish
"""
from src.pipeline import main

if __name__ == "__main__":
    main()

