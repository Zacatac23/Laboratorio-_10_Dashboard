# Guía de evidencias — Laboratorio 11

Cada evidencia se generó ejecutando los comandos indicados el 2026-11-01/02 en macOS 26.6 (arm64), Python 3.12.13 y Docker Engine 29.8.0 / Compose v5.5.1. Ninguna cifra ni identificador fue escrito a mano: todos salen de los archivos listados. Para regenerarlas, ver la columna **Comando** (desde la raíz del repositorio, con el entorno virtual activo).

> **Puerto de MLflow.** En macOS el puerto 5000 lo ocupa *AirPlay Receiver* (proceso `ControlCenter`). Las corridas se hicieron con `MLFLOW_PORT=5001`; en otro equipo basta omitir el argumento para usar 5000.

| # | Evidencia (archivo) | Requisito que sustenta | Comando | Privacidad |
|---|---|---|---|---|
| E1 | `evidencias/lab11/tests_unitarios.txt`, `tests_resultados.json` | Suite automatizada (sección 2), PASS/FAIL/SKIP por prueba | `python scripts/lab11/run_tests_evidencia.py` | Sin datos institucionales (fixtures sintéticos en carpetas temporales) |
| E2 | `evidencias/lab11/tests_unitarios_docker.txt`, `tests_resultados_docker.json` | Misma suite + prueba real contra Docker Compose (MLflow persistente) | `MLFLOW_PORT=5001 python scripts/lab11/run_tests_evidencia.py --docker` | Igual que E1; la prueba Docker usa `data/` en modo `--no-publish` |
| E3 | `evidencias/lab11/docker/docker_verificacion.log` | Ejercicio 8: build, imagen sin datos/secretos, `up`, `ps`, salud HTTP, pipeline en contenedor, publicación, `down`/`up` sin `-v` y persistencia | `bash scripts/lab11/docker_verificacion.sh <copia> 5001` (clon del commit `bced471`, sin `--snapshot`) | El log contiene hashes y rutas, no microdatos |
| E4 | `evidencias/lab11/docker/runs_antes_down.json`, `runs_despues_up.json` | Persistencia del almacén MLflow tras recrear contenedores | (generados por E3) | Parámetros y métricas agregadas; sin microdatos |
| E5 | `reports/reproducibilidad_lab11.json` (copia versionada en `evidencias/lab11/reproducibilidad/`) | Ejercicio 4: dos ejecuciones idénticas comparadas con `np.allclose(atol=1e-6, rtol=0)` | `python scripts/lab11/reproducibilidad.py http://127.0.0.1:5001 <run_1> <run_2>` | Agregados por serie |
| E5b | `evidencias/lab11/reproducibilidad/reproducibilidad_commit_bced471.json`, `evidencias/lab11/mlflow/export_runs_commit_bced471.json` | Inciso 4.2 y 8.4: los dos dry-run de la copia limpia del commit `bced471` son idénticos | `python scripts/lab11/reproducibilidad.py http://127.0.0.1:5001 run_20261102_013222_08ad93 run_20261102_013225_d69796` | Agregados por serie |
| E6 | `evidencias/lab11/mlflow/export_runs.json` | Exportación de runs del servidor MLflow de Compose (etiquetas, parámetros, métricas y lista de artefactos) | (generado por E5) | Sin microdatos; los artefactos completos permanecen en el volumen `observatorio_turismo_mlflow_store` |
| E7 | `evidencias/lab11/mlflow/ui_0*.png`, `capturas_mlflow_ui.json` | Capturas reales de la UI MLflow (lista de runs, comparación de dos runs, detalle y artefactos) | `python scripts/lab11/capturas_mlflow.py http://127.0.0.1:5001 <mlflow_id_1> <mlflow_id_2>` | Solo metadatos de ejecución |
| E8 | `evidencias/lab11/evaluacion/backtest_cortes_multiples.{json,csv}` | Ejercicio 5: backtest complementario de 8 orígenes con baseline en los mismos meses | `python scripts/lab11/backtest_cortes_multiples.py` | Métricas agregadas |
| E8b | `evidencias/lab11/evaluacion/sensibilidad_ene_feb_2026.json` | Incisos 5.1 y 5.5: ene–feb 2026 en las tres fuentes y métricas con y sin esos meses (no cambia la regla) | `python scripts/lab11/sensibilidad_ene_feb_2026.py` | Métricas agregadas y dos totales mensuales |
| E9 | `evidencias/lab11/recuperacion/fallos_controlados.{json,log}` y `entorno_temporal/` | Ejercicio 7: cuatro fallos inyectados, contención por SHA-256, recuperación, fallos de escritura y de MLflow, tres monitores, dos versiones y restauración | `python scripts/lab11/fallos_controlados.py http://127.0.0.1:5001` | Corre sobre una copia temporal de `data/`; se guardan JSON de proceso |
| E10 | `evidencias/lab11/recuperacion/restauracion_docker.log` | Restauración con el CLI dentro de Docker (`src.restore_version`), hash antes/después y auditoría | ver comandos dentro del log | Hashes y metadatos |
| E11 | `evidencias/lab11/dashboard/vigente_0*.png`, `capturas_vigente.json` | Ejercicio 6: observado vs aprobado, MAE/periodo/fecha/versión, límites 2026, móvil, filtros sin nuevos runs | `python scripts/lab11/capturas_dashboard.py http://127.0.0.1:8501 <dir_datos> vigente http://127.0.0.1:5001` | Las capturas muestran agregados institucionales: usar solo por medio autorizado |
| E12 | `evidencias/lab11/dashboard/restaurada_01_*.png`, `capturas_restaurada.json` | Tras restaurar, el tablero muestra la versión vigente | `... capturas_dashboard.py http://127.0.0.1:8501 <dir_datos> restaurada` | Igual que E11 |
| E13 | `evidencias/lab11/dashboard/sin_aprobada_0*.png`, `capturas_sin_aprobada.json` | Sin archivo aprobado: aviso claro y vistas históricas utilizables | `... capturas_dashboard.py <url_local> <dir_sin_aprobado> sin_aprobada` | Igual que E11 |
| E14 | `tests/test_lab11_verificacion.py` | Pruebas añadidas: sin fuga temporal, MAE/RMSE manual, baseline en mismos meses, dry-run, fuentes múltiples, aislamiento de URI MLflow, denominador cero en QC-E y puerto Compose | `python -B -m unittest tests.test_lab11_verificacion -v` | Datos sintéticos |
| E15 | `docs/auditoria_final_lab11.md` | Matriz por inciso del enunciado oficial (1.1–8.4) y por criterio de rúbrica | — | — |
| E16 | `reporte_final_lab11/Laboratorio_11_MLOps_Informe_Tecnico.pdf` (+ `.tex`) | Informe técnico | `cd reporte_final_lab11 && pdflatex Laboratorio_11_MLOps_Informe_Tecnico.tex` (dos veces) | Contiene agregados y capturas: repositorio privado / medio autorizado |

## Qué no es evidencia

- Los identificadores `run_20261029_*` citados en versiones anteriores de la memoria son **históricos**: sus artefactos MLflow no están en este equipo ni en el volumen Docker verificado, por lo que no se usan como prueba.
- Los registros MLflow de la etapa anterior (Windows) viven en la máquina donde se generaron; no se re-certifican aquí.
- `evidencias/*.png` y `evidencias/*.json` fuera de `lab11/` corresponden al Laboratorio 10.

## Entrega de registros MLflow por medio autorizado

El almacén completo (SQLite y artefactos) está en el volumen Docker `observatorio_turismo_mlflow_store`. Para entregarlo sin depender de capturas:

```bash
docker run --rm -v observatorio_turismo_mlflow_store:/mlflow -v "$PWD":/out alpine \
  tar czf /out/mlflow_store_lab11.tgz -C /mlflow .
```

El `.tgz` contiene artefactos con estimaciones agregadas; compártase solo por el canal autorizado del curso (no en un repositorio público).
