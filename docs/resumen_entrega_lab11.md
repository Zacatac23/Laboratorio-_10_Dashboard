# Resumen de entrega — Laboratorio 11

Fecha de verificación: 2026-11-02. Detalle por requisito: [auditoria_final_lab11.md](auditoria_final_lab11.md). Índice de evidencias: [guia_evidencias_lab11.md](guia_evidencias_lab11.md).

## Implementación definitiva

- Pipeline batch `pipeline.py` → `src/pipeline.py` con QC-A…F, split temporal del YAML, Promedio Histórico Mensual (activo), Seasonal Naive (baseline) y Holt-Winters (referencia), regla de aceptación predefinida, registro verificado en MLflow, publicación atómica con respaldo y manifiesto, monitoreo y restauración (`src/restore_version.py`).
- Tablero Streamlit que solo muestra la versión aprobada verificada por SHA-256 y `run_id`.
- Docker Compose con `mlflow` (volumen persistente), `dashboard` y `pipeline`.

## Cambios de esta etapa (sin commitear al momento de verificar)

| Archivo | Tipo |
|---|---|
| `src/pipeline.py` | Corrección: restituir `MLFLOW_TRACKING_URI`/`MLFLOW_EXPERIMENT_ID` tras cada corrida |
| `docker-compose.yml` | Corrección: `--allowed-hosts` con `${MLFLOW_PORT:-5000}` |
| `styles.css` | Corrección visual: valores de métricas sin truncar |
| `tests/test_mlops_integracion.py` | Prueba Docker con `MLFLOW_PORT` |
| `tests/test_lab11_verificacion.py` | Nuevo (10 pruebas) |
| `scripts/lab11/` | Nuevos: `run_tests_evidencia.py`, `_runner_estructurado.py`, `docker_verificacion.sh`, `reproducibilidad.py`, `fallos_controlados.py`, `backtest_cortes_multiples.py`, `capturas_dashboard.py`, `capturas_mlflow.py` |
| `README.md`, `AVANCE_LABORATORIO_11.md` | Reescritos con resultados reales |
| `docs/auditoria_final_lab11.md`, `docs/guia_evidencias_lab11.md`, `docs/resumen_entrega_lab11.md` | Nuevos |
| `evidencias/lab11/` | Nuevas evidencias |
| `reporte_final_lab11/` | Informe PDF, fuente `.tex` y diagrama `.dot`/`.pdf` |

## Comandos reproducibles

```bash
python -m pip install -r requirements.txt -c requirements.lock
python scripts/lab11/run_tests_evidencia.py                       # suite + evidencia
MLFLOW_PORT=5001 python scripts/lab11/run_tests_evidencia.py --docker
bash scripts/lab11/docker_verificacion.sh /tmp/obs_limpia 5001    # tras commitear (sin --snapshot)
python scripts/lab11/reproducibilidad.py http://127.0.0.1:5001 <run_1> <run_2>
python scripts/lab11/fallos_controlados.py http://127.0.0.1:5001
python scripts/lab11/backtest_cortes_multiples.py
```

(En equipos donde el puerto 5000 esté libre, omitir `5001`/`MLFLOW_PORT`.)

## Identificadores reales

| Uso | Run del pipeline | ID MLflow | Estado |
|---|---|---|---|
| Reproducibilidad 1 | `run_20261102_001410_ce7eea` | `7787c39f59d64cf69394bde8de3ea709` | APROBADO_NO_PUBLICADO |
| Reproducibilidad 2 | `run_20261102_001413_338a6e` | `575d18e094f245f1bf51697e3cd11381` | APROBADO_NO_PUBLICADO |
| Publicación en copia limpia (Docker) | `run_20261102_001416_15b4a2` | `255d7914ecb045edb435d5a6a7458da0` | APROBADO_PUBLICADO |
| Versión aprobada versionada en `data/` (versión A) | `run_20261101_222030_d65c3b` | (registrado en la etapa previa, otro equipo) | APROBADO |
| Recuperación tras fallos (copia temporal, versión B) | `run_20261102_001003_405131` | ver `fallos_controlados.json` | APROBADO_PUBLICADO |

Fallos controlados (experimento `Observatorio_Turismo_Guatemala_pruebas_controladas`): `run_20261102_001002_4cea5b` (columna ausente), `run_20261102_001002_5ddc24` (duplicado), `run_20261102_001002_ee857d` (negativo), `run_20261102_001003_553f9b` (denominador cero), `run_20261102_001003_ec1d34` (escritura), `run_20261102_001004_d59228` (MLflow caído, solo auditoría local), `run_20261102_001004_4cceaf` (artefacto no persistido).

## Hashes usados

| Objeto | SHA-256 |
|---|---|
| `data/series_mensuales.csv` | `a178eb0207546ad92e7c64451ac00d353eaca1d0a2e91e46e9dace4536fba259` |
| `data/pais_mensual.csv` | `f767f19a6ed00ac72b61fbe46693e4892e49a7104da63e79cad189359b551dd8` |
| `data/via_frontera.csv` | `a7eb9d045566e829069ffc9bf31597f2168f5af5f1d11182d1709ef284e29359` |
| `config/pipeline_config.yaml` | `d12e42c69a09d6da2733b4b54ce518d661b71eba164b131b818ea1f4ec1fc0c7` |
| Código ejecutado en Docker (`code.sha256`) | `54c040972bbd601e5c8c83fadee4c03fd8f28bc19c01d73f3ad0eee63cc7800a` |
| Versión aprobada A (`data/estimaciones_aprobadas.csv`) | `d5795b8c1b305fa47f98d02ed26dafba15be365094b9b755d55de644506ed872` |
| Commit base declarado | `4d8f5ba4cc1d69ed7338ecbb8d7911fd0e858302` |

## Decisión

Candidato activo (Promedio Histórico Mensual) **APROBADO**: QC críticos aprobados, salida íntegra, MAE 80,365.74 ≤ 150,000 y RMSE 94,175.26 ≤ 180,000 (N=63, 2021-04 a 2026-06). Baseline en los mismos meses: MAE 235,730.91.

## Pruebas

- Sin Docker: 99 pruebas — 98 PASS, 0 FAIL, 1 SKIP (prueba Compose; requiere `RUN_DOCKER_TESTS=1`).
- Con Docker (`RUN_DOCKER_TESTS=1`, `MLFLOW_PORT=5001`): 99 pruebas — 99 PASS.
- Evidencia: `evidencias/lab11/tests_unitarios.txt`, `tests_unitarios_docker.txt` y sus JSON.

## Evidencias

`evidencias/lab11/` → `docker/`, `mlflow/`, `reproducibilidad/`, `evaluacion/`, `recuperacion/`, `dashboard/`, `tests_*`. Informe: `reporte_final_lab11/Laboratorio_11_MLOps_Informe_Tecnico.pdf`.

## Bloqueos y decisiones pendientes de autorización humana

1. **Enunciado oficial** `Laboratorio_11_MLOps_2026.pdf` no disponible: cotejar la matriz de auditoría.
2. **Commit:** los cambios de esta etapa deben commitearse (por el equipo; no se hizo en esta etapa). Después, repetir `docker_verificacion.sh` sin `--snapshot` y `reproducibilidad.py` para que el commit registrado coincida con el código.
3. **Privacidad:** cambiar a privados `Zacatac23/Laboratorio-_10_Dashboard` y `luispedrolira/lab10-data`; decidir si se dejan de versionar los CSV institucionales. Las capturas y el almacén MLflow solo deben compartirse por medio autorizado.
4. **Autoría:** cada integrante debe aportar commits identificables.
5. **Metodología (decisión del equipo):** a 12 meses el baseline supera al modelo activo en 6 de 8 cortes; evaluar otro modelo en una versión futura con reglas fijadas de antemano.
6. **Entorno local (macOS):** la carpeta del proyecto está en iCloud con «Optimizar almacenamiento» y solo hay ~11 GiB libres; macOS desalojó archivos (incluido un pack de `.git` y el `.venv`), lo que causó lecturas colgadas. Marcar la carpeta como «Mantener descargado» o moverla fuera de iCloud.
