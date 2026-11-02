# Auditoría final — Laboratorio 11 (MLOps)

Fecha: 2026-11-02. Entorno: macOS 26.6 arm64, Python 3.12.13 (local) y 3.12.10 (imagen), Docker Engine 29.8.0, Compose v5.5.1. Código auditado: commit base `4d8f5ba` **más los cambios de esta etapa sin commitear** (ver «Cambios de esta etapa»). Huella del código ejecutado en Docker: `code.sha256 = 54c040972bbd601e5c8c83fadee4c03fd8f28bc19c01d73f3ad0eee63cc7800a`.

> **Limitación de la matriz.** El enunciado oficial `Laboratorio_11_MLOps_2026.pdf` **no está en el repositorio** ni fue proporcionado. La numeración de incisos sigue la memoria `AVANCE_LABORATORIO_11.md` y los requisitos explícitos de las instrucciones de verificación; para los ejercicios 6 y 8, que la memoria no subdivide, se listan los requisitos sin inventar números (columna «Inciso»: *por cotejar*). Antes de entregar, un integrante debe cotejar esta matriz con el PDF oficial.

Estados: **Cumple** (implementado y verificado con evidencia observable), **Parcial**, **No cumple**, **No verificable**.

## 1. Matriz por requisito

| Inciso | Requisito | Estado | Implementación | Evidencia concreta | Riesgo | Acción / observación |
|---|---|---|---|---|---|---|
| 1.1 | Variable, unidad, agregación, fuentes y columnas, periodos, supuestos, factores de reparto y archivo del tablero | Cumple | `config/pipeline_config.yaml`, `docs/contratos_datos_mlops.md`, `src/model_engine.py::calculate_repartition_factors` | Parámetros `split.*`, `factor_reparto.*`, `source.*.sha256` del run `run_20261102_001410_ce7eea` (`evidencias/lab11/mlflow/export_runs.json`) | Comparabilidad ene–feb 2026 sin certificar por la fuente | Memoria corregida: ene–feb 2026 sí se evalúan |
| 1.2 | Diagrama real del pipeline con puntos de validación, evaluación, aprobación y consulta | Cumple | `AVANCE_LABORATORIO_11.md` §1.2 (Mermaid), informe §3 | Diagrama coincide con estados de `src/pipeline.py` (incluye `BLOQUEADO_TRAZABILIDAD`) | — | Diagrama anterior mostraba Holt-Winters como modelo principal; corregido |
| 2.1 | Automatización integral sin depender de la sesión del tablero | Cumple | `src/pipeline.py` (`TourismMLOpsPipeline`) | 3 corridas en contenedor por run de verificación (`evidencias/lab11/docker/docker_verificacion.log`) | — | — |
| 2.2 | Comando documentado de ejecución con/sin publicación | Cumple | `pipeline.py --publish / --no-publish` (mutuamente excluyentes) | `test_cli_requiere_publish_o_no_publish`, `test_codigos_de_salida_del_cli`; `DryRun` | — | — |
| 2.3 | Archivo de configuración con rutas, periodos, semilla, umbrales | Cumple | `config/pipeline_config.yaml` | `config.sha256 = d12e42c6…` registrado en MLflow; YAML exacto como artefacto `configuracion/` | — | — |
| QC-A | Columnas y tipos | Cumple | `check_columns_and_types` | `test_qc_a_*` (4 pruebas); fallo inyectado «columna ausente» → QC-A FAILED, `FALLIDO_CALIDAD` (`fallos_controlados.json`) | — | — |
| QC-B | Fechas y cobertura sin imputar ceros | Cumple | `check_dates_and_coverage` | `test_qc_b_*` (5 pruebas) | — | — |
| QC-C | Unicidad de claves | Cumple | `check_uniqueness` | `test_qc_c_unicidad_detecta_duplicados`; fallo inyectado «clave duplicada» → QC-C FAILED | — | — |
| QC-D | Valores faltantes | Cumple | `check_missing_values` | `test_qc_d_valores_faltantes_en_target`; monitoreo de nulos | — | — |
| QC-E | Valores válidos y denominadores | Parcial | `check_values_and_denominators` | `test_qc_e_*` (3); fallo inyectado «negativo» → QC-E FAILED | En el pipeline QC-E se invoca **sin** `denominator_cols`; el denominador cero se detecta después, en factores (`FALLIDO`, etapa de modelado) | Funciona la contención (aprobado intacto), pero no como QC. Opcional: pasar el Total de entrenamiento como denominador a QC-E |
| QC-F | Regla metodológica Total = suma de vías | Cumple | `check_methodological_rule` | `test_qc_f_*` (3); detecta discrepancias en los fallos inyectados | — | — |
| 3.2 | Reporte estructurado y contención ante fallo | Cumple | `reports/quality_report_<run>.json`, artefacto `calidad/` | 4 fallos inyectados, aprobado intacto por SHA-256 en todos | — | — |
| 4.1 | Registro en MLflow de commit, huellas, YAML, periodos, parámetros, factores, QC, métricas, candidatos, decisión, auditoría y modelo | Cumple | `src/tracking.py`, `src/pipeline.py` | 11 artefactos por run (captura `ui_04_run_artefactos.png`; `export_runs.json`) | En contenedor el commit es **declarado** (`GIT_COMMIT`); el código de esta etapa no está commiteado | Tras el commit, repetir `docker_verificacion.sh` sin `--snapshot` para que commit y código coincidan |
| 4.2 | Dos ejecuciones completas reproducibles | Cumple | `scripts/lab11/reproducibilidad.py` | `reports/reproducibilidad_lab11.json`: `run_20261102_001410_ce7eea` vs `run_20261102_001413_338a6e`, máx. diferencia 0.0, estado REPRODUCIBLE | Holt-Winters difiere entre SO (302,827.47 Linux vs 178,765.59 Windows histórico) | No es el modelo activo; documentado |
| 4.2b | Runs visibles en el servidor MLflow que usa Docker | Cumple | Servicio `mlflow` de Compose | Capturas `evidencias/lab11/mlflow/ui_01…04.png`; prueba `DockerCompose` PASS | — | — |
| 4.3 | Identificación de ejecuciones fallidas y rechazadas | Cumple | Estados en `pipeline.status` | Experimento `…_pruebas_controladas` (fallidas); `test_corrida_rechazada_registra_metricas_reales_sin_publicar` | Rechazo por desempeño probado con datos sintéticos, no con datos reales | Con datos reales el candidato activo se aprueba; no se alteraron umbrales para forzar un rechazo |
| 5.1 | Protocolo temporal sin fuga | Cumple | `build_evaluation_mask`, split del YAML | `SinFugaTemporal` (2 pruebas) | — | — |
| 5.2 | MAE, RMSE y métrica relativa bien nombrada | Cumple | `compute_metrics` (`ape_eps_pct`) | `test_mae_rmse_contra_calculo_manual`, `test_compute_metrics_ape_eps_no_es_mape_clasico` | — | Memoria corregida (ya no se llama MAPE) |
| 5.3 | Baseline en exactamente los mismos meses | Cumple | Métricas `eval.snaive.*` con la misma máscara | `test_baseline_y_modelo_activo_en_los_mismos_meses`; N=63 para todos | **A 12 meses el baseline gana en 6 de 8 cortes** (`backtest_cortes_multiples.json`) | Riesgo metodológico declarado; no se cambió el modelo post-hoc |
| 5.4 | Regla de aceptación predefinida y justificada | Cumple | `evaluate_acceptance_rule` | Parámetros `acceptance.*` en MLflow; README §8 | Umbral 150,000 ≈ 54 % del promedio observado (276,685): tolerante | Justificación documentada; revisar con la institución para próximas versiones |
| 6 (por cotejar) | El tablero consulta solo la versión aprobada verificada | Cumple | `data_logic.cargar_version_aprobada` | `TableroVersionAprobada` (3 pruebas); captura `vigente_02` | — | — |
| 6 (por cotejar) | Observado vs estimado diferenciados | Cumple | V08 en `app.py` | `vigente_03_observado_vs_aprobada.png` | — | — |
| 6 (por cotejar) | Fecha de generación, versión/run y MAE de la misma versión | Cumple | Bloque «Estimación aprobada vigente» | `vigente_02`, `vigente_04` (móvil), `capturas_vigente.json` (MAE 80,366; Abr 2021–Jun 2026; 2026-11-02 00:14; v1.0.0) | El `run_id` solo aparece en la ayuda (tooltip) | — |
| 6 (por cotejar) | Nota de 2026 parcial y límites sin afirmaciones causales | Cumple | Aviso y expansor «Límites de esta versión» | `vigente_01`, `vigente_02` | — | — |
| 6 (por cotejar) | Sin archivo aprobado: mensaje claro y vistas históricas | Cumple | Estado `ausente` | `sin_aprobada_01/02.png` (9 gráficos en Resumen) | — | — |
| 6 (por cotejar) | Tras publicar/restaurar se muestra la versión vigente | Cumple | Sin caché | `vigente_02` (2026-11-02 00:14) y `restaurada_01` (2026-11-01 22:20) | — | — |
| 6 (por cotejar) | Filtros no ejecutan modelado ni nuevos runs | Cumple | El tablero no importa MLflow ni el pipeline | `capturas_vigente.json`: 24 runs y 31 archivos antes y después | — | — |
| 7.1 | Monitoreo de actualización, calidad y resultados | Cumple | `src/monitoring.py` | `fallos_controlados.json` → `monitoreo`: 1 alerta por clase, 0 en línea base | — | — |
| 7.2 / 7.4 | Prueba controlada de fallo, contención, corrección y recuperación | Cumple | `scripts/lab11/fallos_controlados.py`, `src/test_controlled_failure.py` | 4 fallos de datos + 3 de infraestructura, aprobado intacto en todos; recuperación `run_20261102_001003_405131` | — | Se corrigió un defecto (URI MLflow filtrada entre corridas) |
| 7.3 | Respaldo y restauración de versión anterior | Cumple | `src/restore_version.py` | `restauracion_docker.log` (hash vuelve a `d5795b8c…`), `restore_audit.jsonl`; captura `restaurada_01` | Restauraciones se auditan en local, no en MLflow | — |
| 8 (por cotejar) | Imagen sin datos, secretos ni `mlflow.db` | Cumple | `Dockerfile`, `.dockerignore` | Inspección en `docker_verificacion.log` (búsqueda vacía, `/app/data` vacío, uid 1000) | — | — |
| 8 (por cotejar) | `build`, `up`, `ps`, tablero y MLflow accesibles | Cumple | `docker-compose.yml` | Log: HTTP 200 en `/_stcore/health` y `/health` | Puerto 5000 ocupado en macOS | Corregido `--allowed-hosts`; usar `MLFLOW_PORT` |
| 8 (por cotejar) | Pipeline en contenedor conectado a MLflow (con y sin publicación) | Cumple | Servicio `pipeline` | 2 dry-run + 1 publicación por verificación | — | — |
| 8 (por cotejar) | Persistencia tras `down`/`up` sin `-v` | Cumple | Volumen `observatorio_turismo_mlflow_store` | `runs_antes_down.json` = `runs_despues_up.json` (9 runs) | `down -v` borra MLflow | Documentado en README §6 y §13 |
| 8 (por cotejar) | Ejecución desde copia limpia | Parcial | `scripts/lab11/docker_verificacion.sh` | Copia por `git clone` + cambios sin commitear (`--snapshot`) | La copia no es un commit puro porque esta etapa no puede commitear | Tras el commit: `bash scripts/lab11/docker_verificacion.sh <dir> [puerto]` (sin `--snapshot`) |
| 8 (por cotejar) | Documentación (README) | Cumple | `README.md` 13 secciones | — | — | — |

## 2. Resumen por criterio ponderado de la rúbrica

No se asigna nota: el estado refleja solo lo verificado.

| Criterio (peso) | Estado verificado | Evidencia principal | Pendiente |
|---|---|---|---|
| Pipeline reproducible (20) | Cumple | Pipeline en contenedor; reproducibilidad 0.0 | Re-verificar tras commit (commit declarado = código) |
| Calidad de datos (15) | Cumple con observación | QC-A…F, 18 pruebas en `test_quality_checks.py`, fallos inyectados | Denominador cero detectado fuera de QC-E |
| MLflow (15) | Cumple | 11 artefactos por run, UI, exportación, persistencia | — |
| Evaluación temporal y aceptación (15) | Cumple con riesgo declarado | Mismos meses, sin fuga, regla predefinida | Baseline mejor a 12 meses en 6/8 cortes; cotejar con enunciado |
| Integración con tablero (10) | Cumple | 7 capturas reales + pruebas | — |
| Monitoreo y restauración (15) | Cumple | 3 monitores, 7 fallos, 2 versiones, restauración | — |
| Docker y documentación (10) | Cumple con observación | Log de 28 pasos, README, informe | Copia limpia con cambios sin commitear; repo público |

## 3. Cambios de esta etapa (corrigen defectos encontrados)

| Archivo | Cambio | Prueba |
|---|---|---|
| `src/pipeline.py` | `run()` restituye `MLFLOW_TRACKING_URI`/`MLFLOW_EXPERIMENT_ID` al terminar (antes, una segunda corrida en el mismo proceso ignoraba la URI del YAML y podía publicar con un servidor caído) | `AislamientoTrackingURI` (falla sin la corrección) |
| `docker-compose.yml` | `--allowed-hosts` incluye `${MLFLOW_PORT:-5000}` | `ComposePuertoMLflow`; UI accesible en 5001 |
| `tests/test_mlops_integracion.py` | La prueba Docker usa `MLFLOW_PORT` | `DockerCompose` PASS con 5001 |
| `styles.css` | Valores de `st.metric` sin truncar | Capturas `vigente_02` (antes «80,366 viajer…») |
| `tests/test_lab11_verificacion.py` | 10 pruebas nuevas | Suite 99 |
| `scripts/lab11/*` | Scripts de evidencia | `docs/guia_evidencias_lab11.md` |
| `README.md`, `AVANCE_LABORATORIO_11.md` | Reescritos con resultados reales | — |

## 4. INCUMPLIMIENTOS ABIERTOS

| Requisito | Causa | Consecuencia | Acción necesaria |
|---|---|---|---|
| Cotejo de la matriz con el enunciado oficial | `Laboratorio_11_MLOps_2026.pdf` no disponible | Incisos de ejercicios 6 y 8 sin numeración oficial | Un integrante coteja y ajusta esta matriz |
| Repositorio privado | Los remotos `Zacatac23/Laboratorio-_10_Dashboard` y `luispedrolira/lab10-data` son públicos (ver `docs/seguridad_repositorio.md`) | Datos institucionales y evidencias expuestos | El dueño cambia la visibilidad; el equipo decide si deja de versionar los CSV |
| Commit de los cambios de esta etapa y verificación desde commit puro | Esta etapa no hace commits | Runs con commit declarado `4d8f5ba` y código modificado (identificado por `code.sha256`) | Commitear, luego `bash scripts/lab11/docker_verificacion.sh <dir> [puerto]` y `reproducibilidad.py` con los nuevos runs |
| Contribución identificable de todos los integrantes | El historial mezcla alias (`Cisco`, `Cisco890`, `Zacatac23`, `Jonatha Josue Zacarias`) con nombres | No es evidente qué integrante hizo cada aporte | Cada integrante configura `user.name`/`user.email` reconocibles y hace commits propios |
