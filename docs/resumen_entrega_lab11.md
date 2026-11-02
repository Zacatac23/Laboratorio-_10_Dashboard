# Resumen de entrega — Laboratorio 11

Fecha de verificación: 2026-11-02. Enunciado: `Laboratorio_11_MLOps_2026.pdf`. Detalle por inciso: [auditoria_final_lab11.md](auditoria_final_lab11.md). Índice de evidencias: [guia_evidencias_lab11.md](guia_evidencias_lab11.md).

## Implementación definitiva

- Pipeline batch `pipeline.py` → `src/pipeline.py` con QC-A…F, split temporal del YAML, Promedio Histórico Mensual (activo), Seasonal Naive (baseline) y Holt-Winters (referencia), regla de aceptación predefinida, registro verificado en MLflow, publicación atómica con respaldo y manifiesto, monitoreo y restauración (`src/restore_version.py`).
- Tablero Streamlit que solo muestra la versión aprobada verificada por SHA-256 y `run_id`.
- Docker Compose con `mlflow` (volumen persistente), `dashboard` y `pipeline`.

## Cambios de esta etapa

Commiteados por el equipo en `571b479` (correcciones de pipeline, Compose y estilos) y `bced471` (pruebas, scripts, documentación, evidencias e informe).

Pendientes de commit tras cotejar con el enunciado oficial:

| Archivo | Tipo |
|---|---|
| `src/quality_checks.py` | Corrección (inciso 3.1 e): QC-E verifica el denominador del factor de reparto |
| `tests/test_lab11_verificacion.py` | Prueba `DenominadorCeroEnQC` (suite: 100 pruebas) |
| `scripts/lab11/sensibilidad_ene_feb_2026.py` | Nuevo: sensibilidad de la evaluación a ene–feb 2026 |
| `README.md`, `AVANCE_LABORATORIO_11.md`, `docs/*.md`, `reporte_final_lab11/*` | Matriz e informe con la numeración oficial |
| `evidencias/lab11/` | Verificación Docker desde el commit `bced471`, fallos controlados y pruebas re-ejecutados, sensibilidad |

## Comandos reproducibles

```bash
python -m pip install -r requirements.txt -c requirements.lock
python scripts/lab11/run_tests_evidencia.py                       # suite + evidencia
MLFLOW_PORT=5001 python scripts/lab11/run_tests_evidencia.py --docker
bash scripts/lab11/docker_verificacion.sh /tmp/obs_limpia 5001    # clon limpio del último commit
python scripts/lab11/reproducibilidad.py http://127.0.0.1:5001 <run_1> <run_2>
python scripts/lab11/fallos_controlados.py http://127.0.0.1:5001
python scripts/lab11/backtest_cortes_multiples.py
python scripts/lab11/sensibilidad_ene_feb_2026.py
```

(En equipos donde el puerto 5000 esté libre, omitir `5001`/`MLFLOW_PORT`.)

## Identificadores reales

| Uso | Run del pipeline | ID MLflow | Estado |
|---|---|---|---|
| Reproducibilidad 1 | `run_20261102_001410_ce7eea` | `7787c39f59d64cf69394bde8de3ea709` | APROBADO_NO_PUBLICADO |
| Reproducibilidad 2 | `run_20261102_001413_338a6e` | `575d18e094f245f1bf51697e3cd11381` | APROBADO_NO_PUBLICADO |
| Publicación en copia limpia (Docker, antes del commit) | `run_20261102_001416_15b4a2` | `255d7914ecb045edb435d5a6a7458da0` | APROBADO_PUBLICADO |
| Copia limpia del commit `bced471`: dry-run 1 | `run_20261102_013222_08ad93` | `3e1a9132d2fa477bbd8fdfe61cf61576` | APROBADO_NO_PUBLICADO |
| Copia limpia del commit `bced471`: dry-run 2 | `run_20261102_013225_d69796` | `292cbce066cc4f6eb286f3b9a582c7ae` | APROBADO_NO_PUBLICADO |
| Copia limpia del commit `bced471`: publicación | `run_20261102_013228_107c2c` | `5b66ca9cffb24a019dbcc52e87884e14` | APROBADO_PUBLICADO |
| Versión aprobada versionada en `data/` (versión A) | `run_20261101_222030_d65c3b` | (registrado en la etapa previa, otro equipo) | APROBADO |
| Recuperación tras fallos (copia temporal, versión B) | `run_20261102_013359_237d8b` | `57abd5176cbb4a7d9b1006ba13a2b04b` | APROBADO_PUBLICADO |

Fallos controlados (experimento `Observatorio_Turismo_Guatemala_pruebas_controladas`, código con la corrección de QC-E): `run_20261102_013358_923651` (columna ausente, QC-A), `run_20261102_013359_fdce92` (duplicado, QC-C), `run_20261102_013359_167547` (negativo, QC-E), `run_20261102_013359_c9d842` (denominador cero, QC-E), `run_20261102_013400_1b5114` (escritura), `run_20261102_013401_5f3159` (MLflow caído, solo auditoría local), `run_20261102_013401_20a4e1` (artefacto no persistido).

## Hashes usados

| Objeto | SHA-256 |
|---|---|
| `data/series_mensuales.csv` | `a178eb0207546ad92e7c64451ac00d353eaca1d0a2e91e46e9dace4536fba259` |
| `data/pais_mensual.csv` | `f767f19a6ed00ac72b61fbe46693e4892e49a7104da63e79cad189359b551dd8` |
| `data/via_frontera.csv` | `a7eb9d045566e829069ffc9bf31597f2168f5af5f1d11182d1709ef284e29359` |
| `config/pipeline_config.yaml` | `d12e42c69a09d6da2733b4b54ce518d661b71eba164b131b818ea1f4ec1fc0c7` |
| Código ejecutado en Docker (`code.sha256`) | `54c040972bbd601e5c8c83fadee4c03fd8f28bc19c01d73f3ad0eee63cc7800a` |
| Versión aprobada A (`data/estimaciones_aprobadas.csv`) | `d5795b8c1b305fa47f98d02ed26dafba15be365094b9b755d55de644506ed872` |
| Commit verificado desde copia limpia | `bced471e35b393335f309a95c4a5afd8f792e6a9` |

## Decisión

Candidato activo (Promedio Histórico Mensual) **APROBADO**: QC críticos aprobados, salida íntegra, MAE 80,365.74 ≤ 150,000 y RMSE 94,175.26 ≤ 180,000 (N=63, 2021-04 a 2026-06). Baseline en los mismos meses: MAE 235,730.91. Sin ene–feb 2026 (sensibilidad, no cambia la regla): activo 81,388.83 y baseline 236,852.07 (N=61); la decisión no cambia.

## Pruebas

- Sin Docker: 100 pruebas — 99 PASS, 0 FAIL, 1 SKIP (prueba Compose; requiere `RUN_DOCKER_TESTS=1`).
- Con Docker (`RUN_DOCKER_TESTS=1`, `MLFLOW_PORT=5001`): 100 pruebas — 100 PASS.
- Evidencia: `evidencias/lab11/tests_unitarios.txt`, `tests_unitarios_docker.txt` y sus JSON.

## Evidencias

`evidencias/lab11/` → `docker/`, `mlflow/`, `reproducibilidad/`, `evaluacion/`, `recuperacion/`, `dashboard/`, `tests_*`. Informe: `reporte_final_lab11/Laboratorio_11_MLOps_Informe_Tecnico.pdf`.

## Bloqueos y decisiones pendientes de autorización humana

1. **Commit de la corrección de QC-E** y de la documentación cotejada con el enunciado (lo hace el equipo). Después, repetir `bash scripts/lab11/docker_verificacion.sh <dir> 5001`.
2. **Privacidad (restricción del enunciado):** cambiar a privados `Zacatac23/Laboratorio-_10_Dashboard` y `luispedrolira/lab10-data` y dar acceso a docentes y auxiliares; decidir si se dejan de versionar los CSV institucionales. Las capturas y el almacén MLflow solo se comparten por medio autorizado.
3. **Registros de MLflow:** exportar el volumen `observatorio_turismo_mlflow_store` (comando en `docs/auditoria_final_lab11.md` §4) y entregarlo por el medio autorizado.
4. **Autoría:** hay commits de los cuatro integrantes, con alias mezclados; cada integrante debe usar un `user.name` reconocible.
5. **Metodología (decisión del equipo):** a 12 meses el baseline supera al modelo activo en 6 de 8 cortes; evaluar otro modelo en una versión futura con reglas fijadas de antemano. La comparabilidad institucional de ene–feb 2026 no está certificada por la fuente.
6. **Entorno local (macOS):** la carpeta del proyecto está en iCloud con «Optimizar almacenamiento»; macOS desalojó archivos (incluido un pack de `.git` y el `.venv`), lo que causó lecturas colgadas. Marcar la carpeta como «Mantener descargado» o moverla fuera de iCloud.
