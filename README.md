# Observatorio de Inteligencia Turística — Guatemala (Laboratorios 10 y 11)

Tablero Streamlit de ingreso mensual de viajeros a Guatemala (enero 2009 – junio 2026) y flujo MLOps reproducible que produce, valida, registra en MLflow, publica y restaura la **estimación aprobada** que consume el tablero.

Documentos relacionados: memoria técnica [AVANCE_LABORATORIO_11.md](AVANCE_LABORATORIO_11.md) · auditoría [docs/auditoria_final_lab11.md](docs/auditoria_final_lab11.md) · evidencias [docs/guia_evidencias_lab11.md](docs/guia_evidencias_lab11.md) · resumen de entrega [docs/resumen_entrega_lab11.md](docs/resumen_entrega_lab11.md) · contratos de datos [docs/contratos_datos_mlops.md](docs/contratos_datos_mlops.md) · seguridad [docs/seguridad_repositorio.md](docs/seguridad_repositorio.md) · informe [reporte_final_lab11/](reporte_final_lab11/).

---

## 1. Objetivo, alcance y limitaciones

- **Objetivo:** ofrecer a directivos una vista histórica de flujos de viajeros y una estimación retrospectiva aprobada, con su error, su versión y sus límites, producida por un procedimiento auditable.
- **Alcance:** variable `viajeros` (viajeros/mes) para `Total` y siete subseries (tres vías de ingreso y cuatro categorías migratorias). Modelo activo: Promedio Histórico Mensual con reparto proporcional histórico para las subseries.
- **Limitaciones:** describe flujos, no capacidad, impactos ambientales/sociales ni causalidad. 2026 es un año parcial (hasta junio). La estimación aprobada es retrospectiva (2021-04 a 2026-06), no un pronóstico futuro. El cambio metodológico de 2023 y la comparabilidad institucional de ene–feb 2026 no están certificados por la fuente.

## 2. Estructura y fuentes

```
app.py, data_logic.py, ui_components.py, mapa_guatemala.py, styles.css   # tablero
pipeline.py, src/                    # pipeline MLOps (quality_checks, model_engine, monitoring, tracking, restore_version)
config/pipeline_config.yaml          # configuración única del pipeline
tests/                               # pruebas unittest (99)
scripts/lab11/                       # scripts que generan las evidencias del Lab 11
Dockerfile, docker-compose.yml, .dockerignore, .env.example
data/                                # fuentes y versión aprobada (montado en contenedores; no va en la imagen)
evidencias/lab11/                    # evidencias verificadas (tests, Docker, MLflow, recuperación, tablero)
docs/, reporte_final_lab11/, reporte_final_lab10/
```

| Fuente | Columnas | Uso |
|---|---|---|
| `data/series_mensuales.csv` | serie, fecha, viajeros | Modelado, QC-A…F, tablero |
| `data/pais_mensual.csv` | fecha, pais, region, viajeros | Tablero; QC de contexto y monitoreo |
| `data/via_frontera.csv` | fecha, via, frontera, viajeros | Tablero; QC de contexto y monitoreo |
| `data/pronosticos.csv` | serie, modelo, fecha, prediccion | Banco histórico de comparación del Lab 10 (no es la versión aprobada) |
| `data/catch22_pca.csv` | serie, PC1, PC2, cluster | Conservado; sin vista |
| `data/estimaciones_aprobadas.csv` + `.manifest.json` | ver contratos | Única versión que el tablero muestra como aprobada |

**Datos de ejemplo:** las pruebas generan series **sintéticas** en carpetas temporales (`tests/test_mlops_integracion.py::synthetic_series`); nunca leen ni escriben `data/` salvo la prueba Docker opcional, que corre en modo `--no-publish`.

## 3. Requisitos previos

- Python **3.12.10** (imagen Docker). Verificado también con 3.12.13 en macOS.
- Docker Engine ≥ 24 y Docker Compose v2 (verificado con Engine 29.8.0 / Compose v5.5.1).
- ~2 GB libres (imagen de 1.61 GB y volumen MLflow de pocos MB, medidos en la verificación).
- Acceso autorizado a los CSV institucionales en `data/` (ver §12).

## 4. Configuración

`config/pipeline_config.yaml` (comentado en el propio archivo):

| Bloque | Claves principales | Significado |
|---|---|---|
| `pipeline` | `random_seed: 42`, `version: 1.0.0` | Semilla y versión del procedimiento |
| `paths` | `raw_data_dir`, `output_dir`, `backup_dir`, `reports_dir`, `logs_dir` | Rutas relativas al repositorio |
| `scope` | `target_series`, `secondary_series` | Serie objetivo y subseries |
| `temporal_split` | `train_start/end`, `eval_start/end`, `excluded_evaluation_periods` | Ajuste 2009-01–2021-03, evaluación 2021-04–2026-06, sin exclusiones |
| `models` | `active_model: historical_mean`, parámetros de Holt-Winters | Modelo activo y referencias |
| `quality_thresholds` | `methodological_tolerance_pct: 0.02`, `max_mae_tolerance: 150000`, `max_rmse_tolerance: 180000` | QC-F y regla de aceptación |
| `monitoring` | `expected_coverage_end`, `max_relative_variation_alert: 0.50`, `quality.*` | Umbrales de monitoreo |
| `mlflow` | `tracking_uri`, `experiment_name`, `connect_retries` | Estrategia de tracking |

Variables de entorno (ver [.env.example](.env.example)): `MLFLOW_TRACKING_URI` (prioridad sobre el YAML), `MLFLOW_CONNECT_RETRIES`, `MLFLOW_CONNECT_DELAY`, `GIT_COMMIT` (commit declarado en contenedor), `OBS_DATA_DIR`, `OBS_LOGS_DIR`, `OBS_REPORTS_DIR`, `OBS_MLFLOW_STORE`, `MLFLOW_PORT`, `DASHBOARD_PORT`, `RESTORE_OPERATOR`, `TZ`, `DATA_DIR` (tablero).

## 5. Instalación local y ejecución del pipeline

```bash
python3.12 -m venv .venv
source .venv/bin/activate              # PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -c requirements.lock

python pipeline.py --config config/pipeline_config.yaml --no-publish   # dry-run: no toca la versión aprobada
python pipeline.py --config config/pipeline_config.yaml --publish      # publica si el candidato es aceptado
python -m streamlit run app.py                                          # tablero en http://localhost:8501
```

Exactamente una de `--publish`/`--no-publish` es obligatoria. Códigos de salida: `0` aprobado, `1` rechazado, `2` fallo, `3` bloqueado por trazabilidad. En local, MLflow usa `sqlite:///mlflow_store/mlflow.db` (UI: `mlflow ui --backend-store-uri sqlite:///mlflow_store/mlflow.db --port 5000`).

## 6. Docker Compose

```bash
docker compose up -d --build                                          # mlflow (127.0.0.1:5000) y dashboard (127.0.0.1:8501)
docker compose ps
GIT_COMMIT=$(git rev-parse HEAD) docker compose run --rm pipeline     # pipeline con publicación controlada
docker compose run --rm pipeline python pipeline.py --config config/pipeline_config.yaml --no-publish
docker compose down                                                   # parada segura: datos, respaldos y MLflow persisten
```

- **No usar `docker compose down -v`**: borra el volumen `observatorio_turismo_mlflow_store` (base y artefactos MLflow).
- La imagen no contiene datos (`.dockerignore` es lista blanca de código); `data/`, `logs/` y `reports/` se montan desde el host. El tablero monta `data/` en solo lectura.
- En PowerShell: `$env:GIT_COMMIT = git rev-parse HEAD`. Sin la variable, el commit queda `NO_DISPONIBLE`.
- Verificación automatizada desde copia limpia: `bash scripts/lab11/docker_verificacion.sh <dir_copia> [puerto_mlflow] [--snapshot]`.

## 7. Acceso y ubicación de salidas

| Recurso | Ubicación |
|---|---|
| Tablero | http://localhost:8501 |
| MLflow UI | http://localhost:5000 (o `MLFLOW_PORT`) |
| Versión aprobada | `data/estimaciones_aprobadas.csv` y `.manifest.json` |
| Respaldos | `data/backup_aprobadas/` |
| Reportes por run (QC, candidatos, aceptación, monitoreo) | `reports/` |
| Auditoría por run y de restauraciones | `logs/audit_<run_id>.json`, `logs/restore_audit.jsonl` |
| Almacén MLflow | local `mlflow_store/`; Docker volumen `observatorio_turismo_mlflow_store` |

## 8. Controles de calidad y regla de aceptación

| Control | Detiene la ejecución si… |
|---|---|
| QC-A Columnas y tipos | falta `serie`/`fecha`/`viajeros` o un tipo no es convertible |
| QC-B Fechas y cobertura | fecha inválida, día ≠ 1, hueco en la serie objetivo o ventana incompleta (no se imputa cero) |
| QC-C Unicidad | hay claves (`serie`,`fecha`) duplicadas |
| QC-D Faltantes | hay nulos en columnas indispensables |
| QC-E Valores | hay NaN, infinitos o negativos (el cero es válido) |
| QC-F Regla metodológica | Total difiere más de 2 % de Aérea+Terrestre+Marítima, o faltan insumos (`NO_VERIFICABLE`) |

Las fuentes de contexto (`pais_mensual`, `via_frontera`) generan **advertencias**, no bloqueos (`context_sources_critical: false`). Un Total de entrenamiento igual a cero detiene la corrida en el cálculo de factores.

**Regla de aceptación (predefinida):** QC críticos aprobados + salida íntegra (todas las series, finita, no negativa) + MAE ≤ 150,000 + RMSE ≤ 180,000 viajeros/mes. Superar al baseline Seasonal Naive se registra pero no es obligatorio. Los umbrales se fijaron antes de evaluar y no se ajustan después: el Total observado en el periodo evaluado promedia 276,685 viajeros/mes (mediana 279,790; rango 74,914–526,190), así que 150 mil acota errores de alrededor de la mitad del nivel típico y descarta candidatos claramente degradados (Holt-Winters, 302,827, se rechazaría).

## 9. Validación temporal y métricas

- Backtest de origen fijo: ajuste 2009-01–2021-03, evaluación de los 63 meses 2021-04–2026-06 con observación; **ene–feb 2026 se evalúan** (tienen dato). Ningún parámetro usa meses evaluados (prueba `SinFugaTemporal`).
- MAE y RMSE en viajeros/mes; `ape_eps_pct = mean(|e|/(|y|+1))·100` (no es MAPE convencional).
- Resultado vigente: MAE 80,365.74 · RMSE 94,175.26 (N=63) frente a Seasonal Naive 235,730.91 · 253,203.39 en los mismos meses.
- Backtest complementario de 8 cortes a 12 meses: el baseline supera al modelo activo en 6 de 8 (riesgo documentado en la auditoría).

## 10. Auditoría de runs, equivalencia y recuperación

```bash
# Equivalencia de dos runs registrados (descarga artefactos del servidor y compara con np.allclose)
python scripts/lab11/reproducibilidad.py http://127.0.0.1:5000 <run_id_1> <run_id_2>

# Respaldos y restauración
python -m src.restore_version --list
python -m src.restore_version --backup <archivo.csv> --reason "motivo" [--operator nombre]
docker compose run --rm --no-deps pipeline python -m src.restore_version --list
```

En la UI de MLflow: experimento `Observatorio_Turismo_Guatemala`, filtrar por `tags.pipeline.status`, revisar parámetros `*.sha256` y artefactos (`estimaciones/`, `aceptacion/`, `calidad/`, `auditoria/`). Tras publicar o restaurar, recargar el tablero: la pestaña Modelos muestra la fecha de generación y el `run_id` (ayuda de «Versión del procedimiento») de la versión vigente.

## 11. Pruebas y fallo controlado sin tocar producción

```bash
python -B -m unittest discover -s tests -v                                   # 99 pruebas (1 omitida sin Docker)
RUN_DOCKER_TESTS=1 python -B -m unittest tests.test_mlops_integracion.DockerCompose -v
python scripts/lab11/run_tests_evidencia.py [--docker]                       # suite + evidencia PASS/FAIL/SKIP
python scripts/lab11/fallos_controlados.py http://127.0.0.1:5000             # fallos, monitoreo y restauración en copia temporal
python -m src.test_controlled_failure                                        # prueba original (copia temporal)
```

Todos los fixtures viven en carpetas temporales; los scripts de fallo copian `data/` a un directorio temporal y verifican al final que `data/` del repositorio no cambió.

## 12. Datos institucionales, repositorio y permisos

- El repositorio debe ser **privado** (hoy los repositorios remotos son públicos: ver [docs/seguridad_repositorio.md](docs/seguridad_repositorio.md); el cambio de visibilidad lo hace cada dueño).
- `.gitignore` excluye secretos (`.env`, claves), el almacén MLflow (`mlflow_store/`, `mlruns/`, `*.db`), `logs/`, `reports/` y `data/backup_aprobadas/`. `.dockerignore` impide que datos o secretos entren a la imagen.
- Las capturas y artefactos MLflow contienen agregados institucionales: compartir solo por el medio autorizado del curso.
- Cada integrante debe contribuir con commits identificables (autor y correo propios).

## 13. Limitaciones conocidas y solución de problemas

| Síntoma | Causa / acción |
|---|---|
| `BLOQUEADO_TRAZABILIDAD` (código 3) | MLflow no responde: `docker compose up -d mlflow` y reintentar; revisar `MLFLOW_TRACKING_URI` |
| Tablero: «Aún no hay una versión aprobada…» | Falta `data/estimaciones_aprobadas.csv`: ejecutar el pipeline con `--publish` o restaurar un respaldo |
| Tablero: métricas «No verificable» | El manifiesto no coincide con el CSV: restaurar un respaldo válido |
| Puerto 5000 ocupado (macOS AirPlay Receiver) | `MLFLOW_PORT=5001 docker compose up -d`; el compose acepta ese puerto en `--allowed-hosts` |
| Puerto 8501 ocupado | `DASHBOARD_PORT=8502` |
| Volumen MLflow vacío | Se perdió el almacén (p. ej. `down -v`): restaurar desde el `.tgz` exportado (ver guía de evidencias) o re-ejecutar el pipeline |
| Hash de CSV distinto en Windows | `core.autocrlf` convierte LF→CRLF; el pipeline registra el hash de los bytes leídos |
| Rutas Windows/Linux | Las rutas del YAML son relativas con `/`; en PowerShell usar `$env:VAR=...` |
| Lecturas que se cuelgan en macOS | La carpeta está en iCloud con «Optimizar almacenamiento»: marcar «Mantener descargado» o crear el `.venv` fuera de iCloud |
| Holt-Winters da otro MAE en otro equipo | Optimizador numérico de statsmodels; no es el modelo activo |

### Tablero (Laboratorio 10)

Cuatro pestañas (Resumen, Explorar datos, Modelos, Acerca de), nueve vistas ocultables y filtros laterales que solo afectan los históricos. La pestaña Modelos lee únicamente la versión aprobada y su manifiesto; `pronosticos.csv` se presenta aparte como banco histórico. Cambiar filtros no entrena modelos ni crea runs (verificado: 24 runs antes y después). Variación interanual solo con meses comparables; una fecha ausente no equivale a cero. Prueba de navegador opcional del Lab 10: `python -B tests/browser_smoke.py "$PWD"` (Firefox).
