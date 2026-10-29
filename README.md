# Observatorio de Turismo Sostenible — Laboratorio 10

Dashboard de ingreso de viajeros a Guatemala, enero 2009–junio 2026. Describe flujos migratorios/turísticos: no mide capacidad, impactos ambientales/sociales ni causalidad.

## Instalación y ejecución

Entorno probado desde cero: Python 3.14.7; versiones directas fijadas en `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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

Flujo reproducible de preparación de datos, ejecución de modelos, controles automáticos de calidad, evaluación temporal, trazabilidad en MLflow y publicación controlada de resultados para el Observatorio de Inteligencia Turística de Guatemala.

Consulte la memoria técnica completa en [AVANCE_LABORATORIO_11.md](file:///c:/Users/jonat/Desktop/Laboratorio-_10_Dashboard/AVANCE_LABORATORIO_11.md).

## Ejecución del Pipeline MLOps

El pipeline desacopla totalmente el cómputo y calibración de la interfaz de usuario:

```bash
# 1. Ejecución completa con validación, evaluación y publicación controlada
python pipeline.py --config config/pipeline_config.yaml --publish

# 2. Modo evaluación sin alterar la versión aprobada vigente (dry-run)
python pipeline.py --config config/pipeline_config.yaml --no-publish
```

## Servidor de Trazabilidad MLflow Tracking

Para consultar los experimentos, parámetros, métricas, huellas SHA-256 de datos, commit Git y artefactos:

```bash
mlflow ui --port 5000 --backend-store-uri sqlite:///mlflow.db
```
Abrir http://localhost:5000 en el navegador.

## Despliegue Contenerizado con Docker Compose

```bash
# Construir y levantar el Tablero (puerto 8501) y MLflow UI (puerto 5000)
docker compose up -d

# Ejecutar el pipeline dentro del contenedor
docker compose run --rm pipeline

# Detener los servicios
docker compose down
```

## Pruebas de Calidad, Fallo Controlado y Recuperación

```bash
# Ejecutar todas las pruebas unitarias (41 pruebas de Lab 10 y Lab 11)
python -B -m unittest discover -s tests -v

# Demostración controlada de inyección de anomalías, contención y recuperación (Ej. 7.4)
python -m src.test_controlled_failure
```
