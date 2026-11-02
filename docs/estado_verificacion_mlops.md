# Estado de verificación MLOps (etapa pipeline / gobernanza)

Fecha de ejecución de pruebas: 2026-11-01.  
Especificación: `01_pipeline_gobernanza.md`.  
PDF `Laboratorio_11_MLOps_2026.pdf`: **no encontrado** en el repositorio.

## Comandos ejecutados

```bash
source .venv/bin/activate
python -m pip install -q statsmodels scikit-learn pyyaml 'mlflow>=3.0.0'
python -B -m unittest discover -s tests -v
python pipeline.py --config config/pipeline_config.yaml --no-publish
```

## Resultados de `unittest`

- **Comando:** `python -B -m unittest discover -s tests -v`
- **Resultado:** `Ran 61 tests in 11.604s` — **OK** (0 fallos)
- Log guardado en `/tmp/lab11_unittest.log` (sesión local)

Incluye:

- Controles QC-A…F (faltantes, tipos, huecos sin imputar a cero, duplicados, infinitos, negativos, denominador cero, NO_VERIFICABLE, bloqueo por discrepancia metodológica).
- Factores sin fuga / sin fallback a 0.0 / denominador cero.
- Métricas con `ape_eps_pct` (no MAPE convencional) y `N=0` sin ceros inventados.
- Exclusión fundamentada de meses y no exclusión automática de meses comparables.
- Rechazo por MAE, documentación de baseline sin exigirlo.
- Publicación atómica con respaldo; fallo de `os.replace` preserva hash del aprobado.
- CLI exige `--publish` o `--no-publish`.

## Dry-run del pipeline

- **Comando:** `python pipeline.py --config config/pipeline_config.yaml --no-publish`
- **Run:** `run_20261101_192802_6ae0bf`
- QC-A…F sobre `series_mensuales.csv`: PASSED; controles de contexto sobre país/vía: PASSED (no usados en modelado).
- Train: 2009-01–2021-03 (N=147). Eval backtest origen fijo: 2021-04–2026-06 (N=63 evaluables; exclusiones=[]).
- Modelo activo configurado: Promedio Histórico Mensual — MAE 80365.74, RMSE 94175.26, APE_eps% 38.67 (N=63).
- Holt-Winters (referencia, no activo): MAE 303103.75 (superaría umbral MAE/RMSE si se activara sin cambiar reglas).
- Decisión: APROBADO; **no publicado** por `--no-publish`.
- Hash SHA-256 de `data/estimaciones_aprobadas.csv` **antes y después idéntico:**  
  `311a1bd68da579b484d495493a6a46f414874ef963bf776dc89bc02c5eeb0862`
- Artefactos generados (sin reemplazar aprobado):
  - `reports/quality_report_run_20261101_192802_6ae0bf.json`
  - `reports/estimaciones_candidatas_run_20261101_192802_6ae0bf.csv`
  - `reports/acceptance_run_20261101_192802_6ae0bf.json`
  - `logs/audit_run_20261101_192802_6ae0bf.json`

## Cambios principales de esta etapa

| Archivo | Cambio |
| --- | --- |
| `docs/contratos_datos_mlops.md` | Contratos, claves, roles observado/backtest/futuro |
| `src/quality_checks.py` | QC-A…F con PASSED/WARNING/FAILED/NO_VERIFICABLE |
| `src/model_engine.py` | Evaluación comparable, ape_eps, factores estrictos, validación de salida |
| `src/monitoring.py` | Publicación atómica + candado `fcntl` + fsync |
| `src/pipeline.py` | Orquestación, CLI mutuamente excluyente, candidatos siempre |
| `config/pipeline_config.yaml` | Ventanas YAML, umbrales, exclusiones explícitas |
| `tests/test_quality_checks.py` | Cobertura ampliada QC |
| `tests/test_mlops_pipeline.py` | Modelado, aceptación, publicación |
| `.dockerignore` | Excluye `data/` (CSV no van a la imagen) |
| `README.md` | Flags `--publish` / `--no-publish` obligatorias |

## Fallos abiertos / pendientes

- Ningún test fallido en esta corrida.
- No se ejecutó en esta etapa la batería de recuperación ante fallo controlado del tercer archivo de instrucciones ni la integración MLflow/dashboard del segundo archivo (`02_integracion_mlflow_dashboard.md`).
- El umbral `max_mae_tolerance: 150000` se mantiene sin ajuste post-hoc; Holt-Winters actual no pasaría ese umbral si se eligiera como `active_model`.
- Ene/feb 2026 **tienen** observación comparable y **no** se excluyen automáticamente; `excluded_evaluation_periods` está vacío a propósito.

## Criterios de aceptación de la etapa

| Criterio | Estado |
| --- | --- |
| QC-A…F con crítico/advertencia verificable | Cumple (tests + dry-run) |
| Aprobados solo tras validar todas las filas | Cumple (`validate_estimates_frame`) |
| Publicación atómica con tests de fallo | Cumple |
| Sin fuga temporal en eval/factores | Cumple |
| Histórico / backtest / futuro explícitos | Cumple (`docs/contratos_datos_mlops.md`) |

---

# Estado de verificación MLOps (etapa integración MLflow, monitoreo, restauración y tablero)

Fecha: 2026-11-01. Especificación: `02_integracion_mlflow_dashboard.md`. Se partió del estado anterior (61 pruebas OK en Windows con el código de `299ec7c`).

Entorno real de esta verificación: Windows 11, Python 3.12.10 en `.venv` y dependencias instaladas con `pip install -r requirements.txt -c requirements.lock` (`pip check` sin conflictos). Docker Desktop con Engine 29.8.0 e imagen `python:3.12.10-slim`.

## Comandos ejecutados y resultados

| Comando | Resultado observado |
| --- | --- |
| `python -B -m unittest discover -s tests -v` | `Ran 89 tests` — **OK (skipped=1)**. 27 en test_lab10, 18 en test_quality_checks, 16 en test_mlops_pipeline y 28 en test_mlops_integracion. La omitida es la prueba Docker, que solo corre con `RUN_DOCKER_TESTS=1`. |
| `RUN_DOCKER_TESTS=1 python -B -m unittest tests.test_mlops_integracion.DockerCompose -v` | **OK** (46 s): un pipeline en contenedor registró en el MLflow de Compose; se recreó el contenedor `mlflow` y el run, sus métricas y el artefacto `aceptacion/` se releyeron. |
| `python pipeline.py --config config/pipeline_config.yaml --no-publish` (local, SQLite) | `run_20261101_215008_9859c2`, estado `APROBADO_NO_PUBLICADO`. Se registraron y releyeron 11 artefactos. El hash de la versión aprobada no cambió. |
| `docker compose build` + inspección de la imagen | Ningún `*.csv` en la imagen; `/app/data` vacío; usuario `app` (uid 1000); `mlflow 3.17.2` y `statsmodels 0.15.0`. |
| `docker compose up -d` | Servidor `mlflow` *healthy*; tablero responde `/_stcore/health` con HTTP 200. |
| `docker compose run --rm pipeline python pipeline.py … --no-publish` | `run_20261102_041032_d25b1c` en `http://mlflow:5000`. El nombre está en UTC porque esta corrida fue anterior a fijar `TZ` en Compose. Artefactos descargados desde el host por `mlflow-artifacts:/1`. |
| `GIT_COMMIT=$(git rev-parse HEAD) docker compose run --rm pipeline` (publicación real) | `run_20261101_222030_d65c3b` (MLflow `c70a73b4e3d34b949611586d88604947`), estado `APROBADO_PUBLICADO`. `data/estimaciones_aprobadas.csv` pasó de `fe20b3db…` a `d5795b8c…`. La versión anterior (`run_20261029_155430_020086`, sin manifiesto) quedó en `data/backup_aprobadas/`. El manifiesto declara MAE 80365.74, RMSE 94175.26, N=63, evaluación 2021-04-01 a 2026-06-01 y `fecha_generacion` 2026-11-01 22:20:30 -0600. |
| `docker compose run --rm --no-deps pipeline python -m src.restore_version --list` | Lista el respaldo anterior como **VÁLIDO, sin manifiesto**. |
| `docker compose down` → `docker compose up -d --wait` | MLflow conserva los mismos **3 runs** antes y después; el volumen `observatorio_turismo_mlflow_store` y `data/backup_aprobadas/` persisten. |
| Tablero (AppTest sobre `data/` real) | 0 excepciones y 9 gráficos. Muestra «Error medio (MAE) — Total de viajeros: 80,366 viajeros/mes», «Periodo evaluado: Abr 2021 – Jun 2026», «Generada el 2026-11-01 22:20» y «v1.0.0». Las curvas se etiquetan «Observado», «Estimación aprobada (retrospectiva)» y «… (banco Lab 10)». No hay pronóstico futuro en la versión. |
| `python -m src.test_controlled_failure` | Pasa. La corrida corrupta termina en `FALLIDO_CALIDAD` y la recuperación en `APROBADO_PUBLICADO`, ambas sobre una copia temporal. El hash de `data/estimaciones_aprobadas.csv` real no cambió. |

## Hallazgos de reproducibilidad (resultados reales)

- **Modelo activo (Promedio Histórico Mensual):** MAE 80365.74, RMSE 94175.26 y N=63, idénticos en la etapa anterior, en Windows y en Linux (Docker).
- **Holt-Winters (referencia, no activo) no es reproducible entre entornos.** La etapa anterior registró MAE 303103.75 en otro entorno. Con statsmodels 0.15.0 se obtuvo 178765.59 en Windows y 178997.90 en Linux con las mismas versiones de paquetes. La diferencia sale del optimizador numérico y es una razón más para fijar versiones. Los parámetros ajustados se registran en `modelo/model_<run>.json`.
- **El SHA-256 de los CSV depende del sistema operativo** del clon: con `core.autocrlf` en Windows, el checkout convierte LF→CRLF. Por ejemplo, la versión aprobada `run_20261029…` tiene `311a1bd6…` en Linux y `fe20b3db…` en Windows. El pipeline registra el hash de los bytes que realmente leyó. La versión publicada se serializa siempre con LF. Se recomienda evaluar un `.gitattributes` con `*.csv -text`; no se aplicó porque alteraría los archivos locales de cada clon.

## Cambios de esta etapa

| Archivo | Cambio |
| --- | --- |
| `src/tracking.py` (nuevo) | URI único (`MLFLOW_TRACKING_URI` > YAML), verificación con reintentos (`/health` y consulta al backend), commit real o `NO_DISPONIBLE`, huella del código, versiones de paquetes y relectura de artefactos |
| `src/pipeline.py` | Bloquea si no hay MLflow; registra fuentes, configuración, modelo, QC, aceptación, monitoreo, auditoría y manifiesto **antes** de publicar y verifica que existan; estados explícitos (`APROBADO_PUBLICADO`, `APROBADO_NO_PUBLICADO`, `RECHAZADO`, `FALLIDO_CALIDAD`, `FALLIDO`, `BLOQUEADO_TRAZABILIDAD`); fallos sin métricas inventadas; códigos de salida 0/1/2/3; usa `paths.output_dir` |
| `src/monitoring.py` | Tres controles con cobertura configurada, comparación con la ejecución previa, variación por fecha sin dividir entre cero y error solo con pares comparables; JSON por `run_id` con etapas y decisión; manifiesto y respaldo conjunto; bloqueo `msvcrt` en Windows |
| `src/restore_version.py` (nuevo) | CLI `--list` y `--backup`; valida ruta, esquema, estado y hash; respaldo previo, reemplazo atómico y auditoría `logs/restore_audit.jsonl` |
| `data_logic.py`, `app.py` | `cargar_version_aprobada` con estados ausente, inaccesible, inválida y ok, y verificación del manifiesto por SHA-256; bloque directivo de MAE, periodo, fecha de generación y versión; límites; banco Lab 10 rotulado aparte; sin caché |
| `config/pipeline_config.yaml` | `expected_coverage_end`, umbrales de calidad, comparación intermensual justificada, estrategia MLflow local y reintentos |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example` | Imagen sin datos (lista blanca), usuario no root, `mlflow server` con `--serve-artifacts`, healthcheck, volumen persistente, montajes configurables, `TZ`, puertos en 127.0.0.1 |
| `requirements.txt`, `requirements.lock` | Versiones exactas; lock generado en Linux 3.12.10. Se retiró `scikit-learn` de las directas porque no se importa; sigue como transitiva de MLflow |
| `.gitignore` | Secretos, almacén MLflow, `*.db`, temporales |
| `src/test_controlled_failure.py` | Salida en carpeta temporal y nuevos estados |
| `tests/test_mlops_integracion.py` (nuevo) | 28 pruebas: trazabilidad aprobada/rechazada/fallida, bloqueo por MLflow, CLI, servidor MLflow HTTP con reinicio, monitoreo, restauración y rutas inseguras, tablero ausente/válido/actualizado/restaurado/inválido, configuración Docker y Compose real (opcional) |
| `README.md`, `docs/seguridad_repositorio.md` (nuevo) | Rutas relativas, Python 3.12.10, operación, auditoría de seguridad y acciones manuales |

## Pendientes y problemas abiertos

- **Repositorios públicos** (`Zacatac23/Laboratorio-_10_Dashboard`, `luispedrolira/lab10-data`): requiere acción manual de cada dueño (ver `docs/seguridad_repositorio.md`). No se cambió la visibilidad ni el historial.
- Los CSV institucionales siguen versionados; dejar de versionarlos es una decisión del equipo.
- En contenedor, el commit es el **declarado** en `GIT_COMMIT` y se marca así en MLflow; sin la variable queda `NO_DISPONIBLE`.
- Entre el reemplazo del CSV y el del manifiesto hay una ventana mínima en la que el tablero muestra «No verificable» en lugar del MAE. Falla cerrada, documentada.
- Si el registro de cierre en MLflow falla **después** de publicar, el run queda con `pipeline.status=PUBLICANDO`. El contenido publicado ya estaba registrado y verificado; la auditoría local anota el fallo. No se observó en estas corridas.
- Las restauraciones se auditan localmente (`logs/restore_audit.jsonl`), no en MLflow.
- El bloqueo `msvcrt` de Windows no se probó con procesos concurrentes; en Linux y Docker se usa `fcntl`.
- El README del Lab 10 cita documentos que no existen en el repositorio (`PRUEBAS_LAB10.md`, `VISUALIZACIONES_FINAL.md`, etc.). No se reescribió esa sección.
- Streamlit emite en log un aviso del widget `modelos` («default value but also … Session State»). Ya existía en la línea base del Lab 10 y no afecta las pruebas.
- Capturas de pantalla y reporte final: corresponden a `03_verificacion_evidencias_entrega.md`.

## Criterios de aceptación de la etapa

| Criterio | Estado |
| --- | --- |
| Un run originado desde Docker aparece con métricas y artefactos en la UI MLflow de Compose | Cumple (`run_20261101_222030_d65c3b` y prueba `DockerCompose`) |
| La base de tracking y los respaldos sobreviven la recreación de contenedores | Cumple (`down`/`up` con 3 runs; `rm -sf mlflow` en la prueba) |
| El tablero usa exclusivamente una versión validada y muestra métrica, versión, fecha y limitaciones | Cumple (AppTest real y pruebas sintéticas) |
| Recuperación segura desde un backup histórico, probada con datos sintéticos | Cumple (pruebas `Restauracion`, `TrazabilidadMLflow` y `TableroVersionAprobada`) |
| README sin rutas de una computadora particular; dependencias con versión reproducible | Cumple |
| Repositorio y datos auditados; acciones manuales de privacidad identificadas | Cumple la auditoría; las acciones manuales siguen pendientes |
