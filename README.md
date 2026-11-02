# Observatorio de Turismo Sostenible — Laboratorio 10

Dashboard de ingreso de viajeros a Guatemala, enero 2009–junio 2026. Describe flujos migratorios/turísticos: no mide capacidad, impactos ambientales/sociales ni causalidad.

## Instalación y ejecución

Versión de Python soportada: **3.12.10** (la misma de la imagen Docker `python:3.12.10-slim`). Dependencias directas con versión exacta en `requirements.txt`; transitivas fijadas en `requirements.lock` (generado con `pip freeze` en Linux; `pip check` sin conflictos). El resumen anterior mencionaba Python 3.14.7: esa combinación no se volvió a probar para el Laboratorio 11.

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -c requirements.lock
python -m streamlit run app.py
```

Abrir http://localhost:8501; detener con Ctrl+C. Las rutas se resuelven desde `app.py`, incluso al iniciar desde otra carpeta. `DATA_DIR` permite usar otro directorio de CSV sin cambiar el código.

## Estructura y navegación

- `app.py`: cuatro pestañas, filtros y enlaces. Resumen: histórico, regiones, distribución mensual regional. Explorar datos: países, evolución del país, vías/fronteras y calendario. Modelos: curvas y errores. Acerca de: fuentes y límites.
- `data_logic.py`: carga validada, agregaciones, variación comparable y métricas sobre pares coincidentes. `ui_components.py`, `styles.css` y `.streamlit/config.toml`: presentación.
- `data/`: cinco CSV originales, conservados byte por byte. `series_mensuales` tiene serie/fecha/viajeros; `pais_mensual`, fecha/pais/region/viajeros; `via_frontera`, fecha/via/frontera/viajeros; `pronosticos`, serie/modelo/fecha/prediccion; `catch22_pca`, serie/PC1/PC2/cluster. PCA se conserva, pero no tiene vista en este tablero.
- `preparar_datos.py`: preparación desde Excel INGUAT declarado; requiere la base original no incluida. No se necesita ejecutarlo para usar los CSV existentes.
- `EXPORTAR_DESDE_NOTEBOOKS.md`: guía de reutilización de salidas ya existentes; no demuestra el entrenamiento original.
- `tests/`: pruebas automatizadas, métricas de referencia y prueba opcional de navegador. `evidencias/`: resultados/capturas de esta corrección.

## Interacciones

El selector lateral permite mostrar/ocultar cada una de las nueve vistas; no cuenta como gráfico. Las barras de país actualizan su historia; las de región actualizan su distribución mensual. Doble clic en el fondo limpia la selección. También hay selectores accesibles. Si se marcan varios puntos se utiliza el último. Cambiar región o fechas descarta selecciones obsoletas; Restablecer filtros recupera los valores iniciales. El treemap desglosa una vía; «Volver a todas las vías» regresa al resumen.

Países/regiones no tienen categoría migratoria. Vías/fronteras solo admite fechas, pues carece de columnas de procedencia. Modelos tiene su propia serie y periodo de evaluación; el filtro lateral no altera las métricas. El último año se identifica como parcial.

## Cálculos y límites

Total = suma observada del intervalo. Variación = porcentaje entre los meses disponibles del año final y los mismos meses del año previo; sin base completa, muestra «Sin datos para comparación». Agregación anual suma observados sin extrapolar ni convertir años en meses. No hay KPI de futuro: las predicciones guardadas terminan en junio 2026.

MAE = promedio de |predicción − observado|; RMSE = raíz del promedio de sus cuadrados. Se usan fechas comunes desde abril 2021 y se informa N, Inicio y Fin. Ambos se expresan en viajeros/mes, con redondeo igual a la auditoría anterior. Datos actuales: 42 pares serie/modelo, 63 meses cada uno, 586 pronósticos negativos. Se preservan valores negativos para reproducir evaluación y se advierte que no representan viajeros posibles.

La fuente Excel, el origen exacto de L1/L2, particiones originales, parámetros y cambio metodológico 2023 están pendientes de documentación. Las fracciones de viajeros se conservan aunque se redondeen visualmente. No existen intervalos de confianza exportados. Una fecha ausente no equivale a cero. Archivo requerido vacío, tipos inválidos, nulos, duplicados y conteos históricos negativos producen un mensaje de validación, sin descartes silenciosos; fallos en archivos opcionales omiten solo sus vistas.

## Pruebas y documentación

```bash
python -B -m unittest discover -s tests -v
```

No entrena modelos ni modifica CSV originales. Los fixtures usan carpetas temporales. Opcionalmente, con Firefox instalado:

```bash
python -B tests/browser_smoke.py "$PWD"
```

La prueba abre servidor/perfil temporales y escribe capturas en `evidencias/`. Consultar `PRUEBAS_LAB10.md`, `VISUALIZACIONES_FINAL.md`, `MODELOS_Y_FUENTES.md`, `AUDITORIA_CORRECCIONES_LAB10.md` y `AJUSTES_PENDIENTES_DOCUMENTO_DISENO.md`. No se certifican entrega administrativa ni PDF de diseño.


---


# MLOps aplicado al Observatorio — Laboratorio 11

Flujo reproducible de preparación de datos, controles de calidad, evaluación temporal, trazabilidad en MLflow, monitoreo, publicación controlada y restauración de versiones aprobadas. Memoria técnica: [AVANCE_LABORATORIO_11.md](AVANCE_LABORATORIO_11.md). Contratos de datos: [docs/contratos_datos_mlops.md](docs/contratos_datos_mlops.md). Estado verificado: [docs/estado_verificacion_mlops.md](docs/estado_verificacion_mlops.md). Seguridad del repositorio: [docs/seguridad_repositorio.md](docs/seguridad_repositorio.md).

## Pipeline batch

```bash
# Exactamente una bandera es obligatoria
python pipeline.py --config config/pipeline_config.yaml --publish      # publica si el candidato es aceptado
python pipeline.py --config config/pipeline_config.yaml --no-publish   # dry-run: no toca la versión aprobada
```

Códigos de salida: `0` aprobado, `1` rechazado por la regla de aceptación, `2` fallo (calidad u otro error), `3` bloqueado porque MLflow no garantiza la trazabilidad.

Cada ejecución (aprobada, rechazada o fallida) queda en MLflow con: `run_id`, inicio/fin y estado (`pipeline.status`), commit real de `git rev-parse HEAD` o `NO_DISPONIBLE`, SHA-256 y ruta lógica de cada fuente usada, configuración y su hash, huella SHA-256 del código, versiones de paquetes, semilla, ventanas de ajuste/evaluación y exclusiones, factores de reparto, perfil del modelo, reporte QC-A…F, regla y umbrales de aceptación, métricas reales del modelo y del baseline en los mismos meses, monitoreo, auditoría y, si se publica, el manifiesto. Un fallo antes de evaluar no registra MAE/RMSE.

**Política de trazabilidad:** el CSV exacto que se publicará y su manifiesto se registran en MLflow y se releen antes del reemplazo atómico. Si MLflow no responde (con reintentos) o un artefacto no queda persistido, no se publica.

## MLflow: una sola estrategia

| Entorno | Tracking | Artefactos | Cómo se elige |
| --- | --- | --- | --- |
| Local | `sqlite:///mlflow_store/mlflow.db` | `mlflow_store/artifacts` | `mlflow.tracking_uri` del YAML |
| Docker Compose | `http://mlflow:5000` (servidor) | `/mlflow/artifacts` servidos por HTTP | `MLFLOW_TRACKING_URI` (tiene prioridad sobre el YAML) |

UI local: `mlflow ui --backend-store-uri sqlite:///mlflow_store/mlflow.db --port 5000`. En Compose: http://localhost:5000.

## Docker Compose

```bash
docker compose up -d --build                 # MLflow (127.0.0.1:5000) y tablero (127.0.0.1:8501)
GIT_COMMIT=$(git rev-parse HEAD) docker compose run --rm pipeline            # publica si se aprueba
docker compose run --rm pipeline python pipeline.py --config config/pipeline_config.yaml --no-publish
docker compose down                          # detiene; datos, respaldos y MLflow persisten
```

En PowerShell: `$env:GIT_COMMIT = git rev-parse HEAD` antes de `docker compose run`. Sin esa variable, el commit queda registrado como `NO_DISPONIBLE` (la imagen no incluye `.git`). Un commit declarado así se marca como «no verificado en contenedor».

- La imagen **no contiene datos**: `.dockerignore` es una lista blanca de código. `data/`, `logs/` y `reports/` se montan desde el host; las rutas se cambian con `OBS_DATA_DIR`, `OBS_LOGS_DIR`, `OBS_REPORTS_DIR` (ver [.env.example](.env.example)). El tablero monta `data/` en solo lectura.
- MLflow guarda SQLite y artefactos en el volumen `mlflow_store` (o la ruta en `OBS_MLFLOW_STORE`). El servicio `pipeline` espera al healthcheck (`/health`) del servidor y además reintenta la conexión (`MLFLOW_CONNECT_RETRIES`).
- **No usar `docker compose down -v`**: borra el volumen con la base y los artefactos de MLflow. Los respaldos de versiones aprobadas viven en `data/backup_aprobadas/` del host.
- Contenedores sin privilegios (usuario `app`, uid 1000) y puertos publicados solo en `127.0.0.1`. Zona horaria: `TZ` (por defecto `America/Guatemala`), para que la fecha de generación no quede en UTC.

## Monitoreo

`reports/monitoring_<run_id>.json` en cada ejecución (también en las fallidas):

1. **Actualización:** última observación real de cada fuente frente a `monitoring.expected_coverage_end` (cobertura declarada de la entrega, no la fecha de hoy) y última estimación producida frente a `temporal_split.eval_end`.
2. **Calidad:** cobertura, tasa de nulos y duplicados con umbrales en `monitoring.quality`, y comparación con el JSON de la ejecución previa si existe.
3. **Resultados:** no finitos, negativos y variación **intermensual** mayor a 0.50. En el Total observado 2009–2019, el percentil 95 de la variación intermensual fue 32.4 % y solo 2 de 131 meses superaron 50 %. Una base cero se informa como variación no definida, sin dividir. Una alerta de variación es de revisión, no prueba pérdida de precisión.

El error predictivo solo se recalcula con meses que tienen observación y estimación.

## Restauración de una versión aprobada

Cada publicación respalda la versión vigente (CSV y manifiesto) en `data/backup_aprobadas/`. El nombre incluye el `run_id` de origen.

```bash
python -m src.restore_version --list
python -m src.restore_version --backup <archivo.csv> --reason "motivo" [--operator nombre]
# En Docker: docker compose run --rm --no-deps pipeline python -m src.restore_version --list
```

Antes de restaurar se valida el nombre y la ruta (sin `..`, rutas absolutas ni enlaces fuera del directorio), el esquema completo, que todas las filas estén `APROBADO`, que haya un único `run_id` y, si existe manifiesto, el SHA-256. La versión vigente se respalda (`..._prerestauracion.csv`) y el reemplazo es atómico. La auditoría queda en `logs/restore_audit.jsonl`. Las fuentes institucionales no se modifican.

## Tablero

La pestaña Modelos lee solo `data/estimaciones_aprobadas.csv` y su manifiesto `estimaciones_aprobadas.manifest.json`. Las métricas solo se muestran si el SHA-256 y el `run_id` del manifiesto coinciden con el CSV. Muestra el MAE de la versión aprobada, el periodo evaluado real, la fecha de generación (no el último mes de datos) y la versión del procedimiento. `pronosticos.csv` se presenta aparte como «Banco histórico de comparación (Lab 10)». Si la versión falta o es inválida, aparece un aviso y las vistas históricas siguen funcionando. No hay caché: una publicación o restauración se ve al recargar la página.

## Pruebas

```bash
python -B -m unittest discover -s tests -v                           # 89 pruebas (1 omitida sin Docker)
RUN_DOCKER_TESTS=1 python -B -m unittest tests.test_mlops_integracion.DockerCompose -v
python -m src.test_controlled_failure                                 # fallo controlado y recuperación
```
