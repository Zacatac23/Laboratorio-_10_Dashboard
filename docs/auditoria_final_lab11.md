# Auditoría final — Laboratorio 11 (MLOps)

Fecha: 2026-11-02. Entorno: macOS 26.6 arm64, Python 3.12.13 (local) y 3.12.10 (imagen), Docker Engine 29.8.0, Compose v5.5.1.

Matriz cotejada con el enunciado oficial `Laboratorio_11_MLOps_2026.pdf` (incisos 1.1–8.4, restricciones y material a entregar).

Código auditado:

- Commit `bced471` (código idéntico al verificado antes del commit: `code.sha256 = 54c040972bbd601e5c8c83fadee4c03fd8f28bc19c01d73f3ad0eee63cc7800a`).
- Más una corrección **sin commitear** en `src/quality_checks.py` (QC-E con denominador del factor de reparto; inciso 3.1 e) y su prueba, ver §3.

Estados: **Cumple** (implementado y verificado con evidencia observable), **Parcial**, **No cumple**, **No verificable**.

## 1. Matriz por inciso del enunciado

| Inciso | Requisito (enunciado) | Estado | Implementación | Evidencia concreta | Riesgo / observación |
|---|---|---|---|---|---|
| 1.1 | Variable, unidad, agregación; fuentes y columnas; periodos de ajuste y evaluación; parámetros y supuestos incluido el factor de reparto; archivo de resultados del tablero | Cumple | `config/pipeline_config.yaml`, `docs/contratos_datos_mlops.md`, `AVANCE_LABORATORIO_11.md` §1.1 | Parámetros `split.*`, `factor_reparto.*`, `source.*.sha256` del run `run_20261102_001410_ce7eea` (`evidencias/lab11/mlflow/export_runs.json`) | — |
| 1.2 | Diagrama desde la lectura de fuentes hasta la consulta; dónde se valida, se evalúa y se autoriza la publicación | Cumple | `reporte_final_lab11/diagrama_pipeline.dot/.pdf`, `AVANCE` §1.2 | Diagrama coincide con los estados de `src/pipeline.py` (incluye `BLOQUEADO_TRAZABILIDAD`) | — |
| 2.1 | Automatizar lectura, validación, preparación, ajuste, evaluación, estimaciones, almacenamiento y publicación de la versión aprobada | Cumple | `src/pipeline.py` (`TourismMLOpsPipeline`) | 3 corridas en contenedor desde el commit (`evidencias/lab11/docker/docker_verificacion.log`) | — |
| 2.2 | Comando documentado, sin editar intermedios ni depender de una sesión; cambiar un filtro no reajusta el modelo | Cumple | `pipeline.py --publish / --no-publish`; el tablero no importa MLflow ni el pipeline | `test_cli_requiere_publish_o_no_publish`, `DryRun`; `evidencias/lab11/dashboard/capturas_vigente.json`: 24 runs y 31 archivos antes y después de usar filtros | — |
| 2.3 | Configuración con rutas, periodos, parámetros y umbrales; versiones de dependencias; semilla; fórmulas y parámetros | Cumple | `config/pipeline_config.yaml`; `requirements.txt` + `requirements.lock`; semilla 42 (`random_seed`); fórmula del factor de reparto en `docs/contratos_datos_mlops.md` y factores registrados en MLflow | `config.sha256 = d12e42c6…` y artefacto `entorno/environment_<run>.json` (versiones y semilla) | — |
| 3.1 a) | Columnas y tipos: detener si falta una variable o el tipo es incompatible | Cumple | `check_columns_and_types` | `test_qc_a_*`; fallo inyectado «columna ausente» → QC-A FAILED, `FALLIDO_CALIDAD` (`run_20261102_013358_923651`) | — |
| 3.1 b) | Fechas y cobertura: fechas inválidas y periodos sin información | Cumple | `check_dates_and_coverage` | `test_qc_b_*` (5 pruebas) | — |
| 3.1 c) | Unicidad según clave y granularidad | Cumple | `check_uniqueness` (`serie`,`fecha`); contexto `fecha,pais` y `fecha,via,frontera` | Fallo inyectado «clave duplicada» → QC-C FAILED (`run_20261102_013359_fdce92`) | — |
| 3.1 d) | Faltantes permitidos frente a faltantes que impiden estimar | Cumple | `check_missing_values` (obligatorias) frente a contexto no bloqueante | `test_qc_d_valores_faltantes_en_target`, `FuentesMultiples` | — |
| 3.1 e) | Conteos negativos, no finitos y denominadores iguales a cero | Cumple (cambio sin commitear) | `check_values_and_denominators` + `_check_values_and_repartition_denominator` (suma del Total en ajuste) | `DenominadorCeroEnQC` (falla sin el cambio); fallos inyectados «negativo» (`run_20261102_013359_167547`) y «denominador cero» (`run_20261102_013359_c9d842`) → QC-E FAILED | Antes del cambio el denominador cero se detectaba en el modelado (`FALLIDO`), no en QC-E. Debe commitearse |
| 3.1 f) | Regla metodológica del proyecto | Cumple | `check_methodological_rule`: Total mensual = suma de vías (tolerancia 2 %) | `test_qc_f_*` (3); detecta la discrepancia en los fallos inyectados | La regla elegida no es el ejemplo del enunciado (serie mensual frente a presencias diarias); el proyecto no usa presencias diarias |
| 3.2 | Para cada control: qué verifica, cuándo advierte y cuándo detiene; reporte; no imputar ceros; detener antes de reemplazar | Cumple | `reports/quality_report_<run>.json` (descripción, estado, crítico); tabla de controles en README §8 y `AVANCE` §3 | 4 fallos de datos inyectados, versión aprobada intacta por SHA-256 en todos | — |
| 4.1 | Experimento para el destino asignado; id y fecha; commit; fuentes y huellas; periodos; parámetros, métricas, QC; estimaciones, configuración y modelo | Cumple | Experimento `Observatorio_Turismo_Guatemala`; `src/tracking.py`, `src/pipeline.py` | 11 artefactos por run (`ui_04_run_artefactos.png`; `export_runs.json`); runs del commit con `git_commit = bced471` | En contenedor el commit es **declarado** por `GIT_COMMIT`; lo respalda `code.sha256` |
| 4.2 | Dos ejecuciones completas con mismos datos y configuración; resultados equivalentes y tolerancia | Cumple | `scripts/lab11/reproducibilidad.py` | `reports/reproducibilidad_lab11.json` (`run_20261102_001410_ce7eea` vs `run_20261102_001413_338a6e`) y `evidencias/lab11/reproducibilidad/reproducibilidad_commit_bced471.json` (`run_20261102_013222_08ad93` vs `run_20261102_013225_d69796`): máx. diferencia 0.0, tolerancia `atol=1e-6`, REPRODUCIBLE | Holt-Winters difiere entre sistemas operativos (no es el modelo activo) |
| 4.3 | Ejecuciones fallidas y su causa; sin métricas inventadas; evidencia de consulta en MLflow | Cumple | Estados en `pipeline.status`; `failed_stage` y `publication_decision` en la auditoría | Experimento `…_pruebas_controladas` (7 fallidas, sin métricas de evaluación cuando se detienen antes); `export_runs.json` (consulta por API); capturas `ui_01…04` | Rechazo por desempeño probado con datos sintéticos (`test_corrida_rechazada_registra_metricas_reales_sin_publicar`) |
| 5.1 | Ocultar meses observados; respetar el orden temporal; limitaciones de ene–feb 2026 | Cumple | Backtest de origen fijo (ajuste 2009-01–2021-03, evaluación 2021-04–2026-06); `build_evaluation_mask` | `SinFugaTemporal` (2 pruebas); limitaciones de ene–feb 2026 en `AVANCE` §1.1 e informe §6 | Ene–feb 2026 se estiman a 58–59 meses del origen: no reproducen la situación real de inicios de 2026 |
| 5.2 | MAE o RMSE; tratamiento de ceros si se usa MAPE | Cumple | `compute_metrics`: MAE, RMSE y `ape_eps_pct` (+1 en el denominador) | `test_mae_rmse_contra_calculo_manual`, `test_compute_metrics_ape_eps_no_es_mape_clasico` | No se usa MAPE convencional |
| 5.3 | Referencia sencilla en los mismos meses | Cumple | Seasonal Naive lag 12 con la misma máscara | `test_baseline_y_modelo_activo_en_los_mismos_meses`; N=63 para todos | — |
| 5.4 | Regla verificable con QC, integridad y desempeño; umbrales justificados por escala | Cumple | `evaluate_acceptance_rule`; parámetros `acceptance.*` en MLflow | README §8: umbral 150,000 ≈ 54 % del promedio observado (276,685) | Umbral tolerante; justificación documentada |
| 5.5 | No es obligatorio superar la referencia; no modificar la regla; no calcular errores de ene–feb 2026 sin observaciones comparables | Cumple con observación | `require_better_than_baseline: false`; umbrales sin cambios; `excluded_evaluation_periods: []` | El activo supera al baseline en el origen fijo; a 12 meses el baseline gana 6 de 8 cortes (`backtest_cortes_multiples.json`), documentado sin cambiar reglas. Ene–feb 2026 tienen observación y coinciden en las tres fuentes (`sensibilidad_ene_feb_2026.json`) | Su comparabilidad institucional no está certificada por la fuente. Sensibilidad: sin esos meses, MAE activo 81,388.83 (N=61) frente a 80,365.74 (N=63); la decisión no cambia |
| 6.1 | El tablero lee una versión aprobada; el archivo incluye destino, periodo, valor, unidad, id de ejecución, fecha de generación y versión del procedimiento | Cumple | `data_logic.cargar_version_aprobada`; columnas `destino, serie, modelo, fecha, prediccion, unidad_medida, run_id, fecha_generacion, version_procedimiento, estado_aprobacion` | `TableroVersionAprobada` (3 pruebas); cabecera de `data/estimaciones_aprobadas.csv` | — |
| 6.2 | Observado frente a estimado con etiquetas y representación consistente; fecha de actualización; métrica de validación con explicación y periodos | Cumple | Vista V08 y bloque «Estimación aprobada vigente» en `app.py` | `vigente_02`, `vigente_03_observado_vs_aprobada.png`, `capturas_vigente.json` (MAE 80,366; Abr 2021–Jun 2026; 2026-11-02 00:14; v1.0.0) | El `run_id` aparece solo en la ayuda (tooltip), coherente con 6.3 |
| 6.3 | Advertencia comprensible de limitaciones; detalles técnicos en MLflow y documentación; orientación a directivos | Cumple | Aviso y expansor «Límites de esta versión» | `vigente_01`, `vigente_02` | — |
| 6.4 | Reemplazar solo tras validar; conservar la última aprobada si falla; avisar si no existe versión aprobada | Cumple | Publicación atómica después de QC, regla y trazabilidad; estado `ausente` en el tablero | 7 fallos con aprobado intacto (`fallos_controlados.json`); `sin_aprobada_01/02.png` | — |
| 7.1 | Registro por ejecución: inicio y fin, etapas, advertencias, errores y resultado de la publicación | Cumple | `logs/audit_<run_id>.json` (`start_time`, `end_time`, `stages`, `warnings`, `errors`, `published`, `publication_decision`) | `evidencias/lab11/recuperacion/entorno_temporal/audit_*.json` | — |
| 7.2 | Monitoreo de actualización, calidad y resultados | Cumple | `src/monitoring.py` | `fallos_controlados.json` → `monitoreo`: 0 alertas en línea base; 1 alerta por clase inducida | — |
| 7.3 | Una variación elevada genera revisión, no pérdida de precisión; error solo con observaciones comparables | Cumple | Severidad `REVISION` con mensaje «una variación extrema no prueba pérdida de precisión»; el error se actualiza solo con N>0 comparables | `fallos_controlados.json` (Total 2024-07 ×3 → REVISIÓN) | — |
| 7.4 | Prueba controlada sobre copia o sintéticos (columna ausente, duplicado, denominador cero); detectar; aprobado disponible; corregir y re-ejecutar | Cumple | `scripts/lab11/fallos_controlados.py` (copia temporal de `data/`) | 4 fallos de datos + 3 de infraestructura con aprobado intacto; recuperación `run_20261102_013359_237d8b` (versión B `59c2176b…`) | Se corrigió un defecto (URI de MLflow filtrada entre corridas) |
| 7.5 | Conservar una versión anterior aprobada; documentar la restauración; demostrar que el tablero la consulta | Cumple | `data/backup_aprobadas/`, `src/restore_version.py`; README §10 | Restauración a `d5795b8c…` (`fallos_controlados.json`, `restauracion_docker.log`); captura `restaurada_01` | Restauraciones auditadas en `logs/restore_audit.jsonl`, no en MLflow |
| 8.1 | Tablero y entorno del pipeline en Docker (Compose) | Cumple | `Dockerfile`, `docker-compose.yml` (`mlflow`, `dashboard`, `pipeline`) | Log: build, `up --wait`, `ps`, HTTP 200 en `/_stcore/health` y `/health` | Puerto 5000 ocupado por AirPlay en macOS: usar `MLFLOW_PORT` |
| 8.2 | Documentar requisitos, datos institucionales, configuración, build/inicio, pipeline, acceso, registros, detención y restauración | Cumple | `README.md` §3–§7, §10, §12, §13 | — | — |
| 8.3 | Persistencia de MLflow y de versiones aprobadas al recrear contenedores; datos fuera de la imagen | Cumple | Volumen `observatorio_turismo_mlflow_store`; `data/` montado; `.dockerignore` | 16 runs iguales antes de `down` y después de `up`; imagen sin CSV, `.db`, `.env`, claves ni `.git`; `/app/data` vacío | `down -v` borra MLflow (README §6 y §13) |
| 8.4 | Comprobar desde una copia limpia del repositorio | Cumple | `scripts/lab11/docker_verificacion.sh` (sin `--snapshot`) | `git clone` del commit `bced471`: 28 pasos con código 0; mismo `code.sha256` que las corridas previas | La corrección de QC-E aún no está commiteada; tras el commit, repetir el script |
| Restricción | Repositorio privado con acceso a docentes y auxiliares | **No cumple** | — | `docs/seguridad_repositorio.md` | Ver §4 |
| Restricción | Reglas metodológicas: sin imputar ceros, granularidad, sin duplicar visitantes | Cumple | QC-B, QC-C, QC-F | Pruebas QC | — |
| Evaluación | Aportes de todos los integrantes en el historial | Parcial | — | `git shortlog -sne`: Cisco890/Cisco, Zacatac23/Jonatha Josue Zacarias, Mario Rocha, Luis Pedro Lira | Hay commits de los cuatro, con alias mezclados; ver §4 |
| Entrega | Registros de MLflow por medio autorizado; archivos de resultados y metadatos | Parcial | `export_runs.json`, `export_runs_commit_bced471.json`; versión aprobada y manifiesto en `data/` | — | El almacén completo (volumen Docker) se entrega por el medio que autorice el curso |

## 2. Resumen por criterio ponderado

No se asigna nota: el estado refleja solo lo verificado.

| Criterio (peso) | Estado verificado | Evidencia principal | Pendiente |
|---|---|---|---|
| Pipeline reproducible y configuración (20) | Cumple | Pipeline en contenedor desde el commit; reproducibilidad 0.0 en dos pares de corridas | — |
| Controles automáticos de calidad (15) | Cumple | QC-A…F, `test_quality_checks.py` (18 pruebas), `DenominadorCeroEnQC`, 4 fallos inyectados | Commitear la corrección de QC-E |
| Registro y trazabilidad en MLflow (15) | Cumple | 11 artefactos por run, UI, exportación, persistencia | — |
| Validación temporal y regla de aceptación (15) | Cumple con riesgo declarado | Mismos meses, sin fuga, regla predefinida, sensibilidad ene–feb 2026 | Baseline mejor a 12 meses en 6 de 8 cortes |
| Integración y publicación controlada (10) | Cumple | 7 capturas reales + pruebas | — |
| Monitoreo y recuperación (15) | Cumple | 3 monitores, 7 fallos, 2 versiones, restauración | — |
| Docker y documentación (10) | Cumple | Copia limpia del commit `bced471`, README, informe | Repositorio público |

## 3. Cambios de esta etapa

| Archivo | Cambio | Prueba | Commit |
|---|---|---|---|
| `src/pipeline.py` | `run()` restituye `MLFLOW_TRACKING_URI`/`MLFLOW_EXPERIMENT_ID` al terminar | `AislamientoTrackingURI` (falla sin la corrección) | `571b479` |
| `docker-compose.yml` | `--allowed-hosts` incluye `${MLFLOW_PORT:-5000}` | `ComposePuertoMLflow` | `571b479` |
| `styles.css` | Valores de `st.metric` sin truncar | Captura `vigente_02` | `571b479` |
| `tests/`, `scripts/lab11/`, documentación, evidencias, informe | Pruebas, scripts de evidencia y documentación | Suite completa | `bced471` |
| `src/quality_checks.py` | QC-E verifica el denominador del factor de reparto (inciso 3.1 e) | `DenominadorCeroEnQC` (falla sin el cambio) | **sin commitear** |
| `tests/test_lab11_verificacion.py` | Prueba `DenominadorCeroEnQC` | Suite de 100 pruebas | **sin commitear** |
| `scripts/lab11/sensibilidad_ene_feb_2026.py` | Sensibilidad de la evaluación a ene–feb 2026 (no cambia la regla) | `evidencias/lab11/evaluacion/sensibilidad_ene_feb_2026.json` | **sin commitear** |

## 4. INCUMPLIMIENTOS ABIERTOS

| Requisito | Causa | Consecuencia | Acción necesaria |
|---|---|---|---|
| Repositorio privado con acceso a docentes (restricción del enunciado) | Los remotos `Zacatac23/Laboratorio-_10_Dashboard` y `luispedrolira/lab10-data` son públicos (`docs/seguridad_repositorio.md`) | Datos institucionales y evidencias expuestos | El dueño cambia la visibilidad e invita a docentes y auxiliares; el equipo decide si deja de versionar los CSV |
| Commit de la corrección de QC-E | Esta etapa no hace commits | El código de `bced471` detecta el denominador cero en el modelado, no en QC-E | Commitear `src/quality_checks.py`, la prueba, el script de sensibilidad y la documentación; luego `bash scripts/lab11/docker_verificacion.sh <dir> [puerto]` |
| Entrega de registros de MLflow por medio autorizado | El almacén completo vive en el volumen Docker local | Solo se versiona la exportación JSON de runs | Exportar el volumen (`docker run --rm -v observatorio_turismo_mlflow_store:/m -v "$PWD":/o alpine tar czf /o/mlflow_store.tgz -C /m .`) y entregarlo por el medio autorizado, sin publicarlo |
| Contribución identificable de todos los integrantes | El historial mezcla alias (`Cisco`, `Cisco890`, `Zacatac23`, `Jonatha Josue Zacarias`) con nombres | No es evidente qué integrante hizo cada aporte | Cada integrante configura `user.name`/`user.email` reconocibles; documentar el alias de cada uno si el curso lo pide |
