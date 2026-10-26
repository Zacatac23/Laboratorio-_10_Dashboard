# Auditoría de código y visualizaciones — Laboratorio 10

Fecha: 25 de octubre de 2026, zona America/Guatemala.
Repositorio revisado: `/home/cisco/universidad/cuarto/segundo_semestre/data_science/lab10/Laboratorio-_10_Dashboard.`
Commit: `b9b2878e2087ce91db2c8a8d04149550d83e9fcf` (`feat: cambios finales`).

Base de evaluación: `Auditoria_Laboratorio_10_Codigo_Visualizaciones.md`, proporcionado por el usuario. No se recibió el PDF original del enunciado: la correspondencia con sus requisitos depende de que el MD lo transcriba correctamente. El documento adjunto se usó como guía de evaluación; sus instrucciones de corregir código no se interpretaron como autorización para modificar la aplicación.

Alcance autorizado: diagnóstico, ejecución de pruebas y reporte. No se corrigió código, no se entrenaron modelos, no se cambiaron dependencias del proyecto ni se hicieron commits o push.

## 1. Resumen ejecutivo

**Estado general: funcional en el recorrido principal, pero con incumplimientos y resultados potencialmente engañosos. NO LISTO PARA ENTREGA.**

La aplicación arranca con los datos presentes. Se probaron filtros, las ocho series y los nueve valores de región disponibles. La navegación por las cuatro pestañas funciona. El vínculo barras de países → serie temporal funciona mediante un clic real en Firefox y se revierte con doble clic en el fondo del gráfico. Existen seis familias de pronóstico en el CSV, con salidas diferentes; los 42 pares serie/modelo tienen los mismos 63 meses de evaluación. MAE y RMSE coinciden con un cálculo independiente.

Los bloqueadores principales son:

1. El requisito de ocho visualizaciones válidas no queda acreditado. Hay siete componentes Plotly al inicio y ocho después de seleccionar un país; el conteo conservador admite seis candidatos informativamente defendibles. El supuesto mapa usa polígonos arbitrarios y omite regiones; la mini gráfica no tiene ejes ni lectura útil y agrega un 8% fijo. No son ocho visualizaciones verificadas que satisfagan simultáneamente los criterios del MD.
2. Se presentan cifras fijas cuando no hay base de cálculo: seleccionar 2009 muestra `+8.4%` pese a no existir 2008. En una copia de prueba sin datos del intervalo aparecen `132,000`, `42,350` y `+12.5%`.
3. La proyección del resumen es una fórmula local de crecimiento de 5%; la mini gráfica usa 8% y los KPI otra fórmula. Ninguna se atribuye a los modelos guardados. En detalle anual la proyección genera febrero y marzo de 2026 a partir de agregados anuales.
4. Dos casillas y el botón de detalle regional no realizan la acción anunciada.
5. En móvil, la barra lateral ocupa 320 de 390 px y no ofrece cierre; el título del banner queda recortado.
6. Faltan las evidencias de procedencia de L1/L2 y una visualización del desempeño más allá de la tabla de métricas. El CSV por sí solo no prueba qué notebook, entrenamiento o versión generó sus resultados.

No es una aplicación completamente rota ni faltan los tres conjuntos de pronósticos. El mayor riesgo está en la exactitud de lo presentado, el conteo de gráficos, la trazabilidad y las interacciones incompletas.

## 2. Inventario técnico y flujo de datos

| Elemento | Evidencia |
|---|---|
| Lenguaje / framework | Python 3.14.7; ejecución probada con Streamlit 1.66.1 y Plotly 7.1.0. |
| Licencias | Metadatos locales de paquetes: Streamlit `Apache-2.0`, Plotly `MIT`. Tecnología admisible de código abierto; no se exige una licencia propia del repositorio para acreditar este criterio. |
| Otras bibliotecas probadas | pandas 2.3.3, NumPy 2.5.1, openpyxl 3.1.5. |
| Dependencias declaradas | `requirements.txt:1`: `streamlit>=1.40`, pandas, numpy, plotly, openpyxl. Solo Streamlit tiene versión mínima; no hay lockfile. |
| Entrada y vistas | `app.py:43`, `app.py:147`: Resumen, Explorar datos, Modelos, Acerca de. |
| Carga y cálculos | `data_logic.py`: cinco CSV, agregación mensual/anual, variación interanual, proyección heurística y métricas. |
| Presentación | `ui_components.py` y `styles.css` — 573 líneas de CSS; configuración en `.streamlit/config.toml`. |
| Preparación de datos | `preparar_datos.py:7`: espera `Base_Migracion_2009-2026jun.xlsx`, hoja `Datos`. El Excel no está en los archivos versionados. |
| Exportación de modelos | `EXPORTAR_DESDE_NOTEBOOKS.md`: ejemplos para extraer resultados ya calculados. Los notebooks y salidas originales de evaluación no están versionados. |
| Pruebas existentes | No se encontraron pruebas automatizadas versionadas. Las de esta revisión se guardaron temporalmente fuera del código del proyecto. |
| Documentación | `README.md` contiene únicamente el nombre del laboratorio. No explica arranque, esquema, fuentes ni modelos. |
| Artefactos adicionales | `catch22_pca.csv` tiene PCA/clusters de 37 series; `app.py:54` lo carga, pero ninguna vista lo utiliza. No se cuenta como visualización ni como modelo visible. |
| Git | Al iniciar: solo `?? __pycache__/`. Historial con siete commits y varias identidades de autor; esto no certifica autoría real ni participación administrativa. |

### Datos e integridad

| Archivo | Filas | Esquema / cobertura | Comprobación |
|---|---:|---|---|
| `data/series_mensuales.csv` | 1,680 | 8 series × 210 meses, enero 2009–junio 2026; `serie, fecha, viajeros` | Sin nulos, claves duplicadas, fechas inválidas, valores no finitos o viajeros negativos. |
| `data/pais_mensual.csv` | 23,887 | `fecha, pais, region, viajeros`; mismo intervalo | Sin nulos, claves duplicadas, fechas inválidas o viajeros negativos. |
| `data/via_frontera.csv` | 3,857 | `fecha, via, frontera, viajeros`; mismo intervalo | Sin nulos, claves duplicadas, fechas inválidas o viajeros negativos. |
| `data/pronosticos.csv` | 2,646 | `serie, modelo, fecha, prediccion`; abril 2021–junio 2026 | 42 pares serie/modelo × 63 meses. Sin nulos, duplicados o fechas inválidas; **586 predicciones negativas**. |
| `data/catch22_pca.csv` | 37 | `serie, PC1, PC2, cluster` | Sin nulos ni series duplicadas; no hay vista que use sus resultados. |

Las sumas mensuales por países y fronteras coinciden con `Total` dentro de precisión flotante (máxima diferencia ≈ `5.82e-11`). También concilian las desagregaciones por vía y tipo de viajero. Es una fortaleza real de consistencia interna; no certifica correspondencia con el Excel original ausente.

Hay cantidades fraccionarias de viajeros, verificadas con tolerancia absoluta `1e-8` y tolerancia relativa cero: 828 registros en series, 4,536 en países y 819 en vías. No se puede concluir que sean datos falsos: podrían ser ajustes o estimaciones de la fuente. Hace falta documentar su significado; la interfaz redondea a personas enteras sin explicar esa procedencia.

Flujo observado: supuesto Excel INGUAT → `preparar_datos.py` → tres CSV históricos → `leer_archivo` / `cargar_todo` → filtros y estado de Streamlit → gráficos Plotly. Por separado: notebooks ausentes → `pronosticos.csv` → alineación temporal → MAE/RMSE y curvas. El resumen usa `calcular_proyeccion`, no las predicciones de ese CSV.

`leer_archivo:32` elimina fechas o predicciones no convertibles y normaliza etiquetas sin informar al usuario cuántas filas se descartaron. En los datos actuales no se detectaron descartes por fechas o nulos; el riesgo aparece con nuevos archivos. La validación de columnas, tabla vacía y cobertura de evaluación es insuficiente.

### Reproducción

Desde la raíz que contiene `app.py`, `.streamlit/` y `data/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Abrir `http://localhost:8501`. Los CSV ya existen: no es necesario ejecutar el preparador ni entrenar modelos para arrancar.

La auditoría usó `/tmp/lab10-auditoria-venv` con `--system-site-packages`; instaló allí Streamlit y Plotly y reutilizó bibliotecas presentes. Esto verifica funcionamiento con las versiones indicadas, **no una instalación mínima completamente aislada ni todas las versiones admitidas por `>=1.40`**. El servidor y Firefox de prueba ya fueron detenidos.

## 3. Matriz C01–C27

Estados: CUMPLE = comprobado para el alcance indicado; PARCIAL = implementación útil con una carencia concreta; NO CUMPLE = contradicción comprobada; NO VERIFICABLE = falta evidencia externa o prueba suficiente.

| ID | Estado | Evidencia / archivo y componente | Prueba y problema | Acción |
|---|---|---|---|---|
| C01 | CUMPLE | `app.py:410`, históricos por país, región y vía | Tablero sobre ingreso de viajeros a Guatemala. El alcance realmente medido es flujo migratorio/turístico; no demuestra por sí solo sostenibilidad ambiental o social. | Mantener explícito ese alcance. |
| C02 | PARCIAL | `app.py:147`, `app.py:386` | Navegación entendible; MAE/RMSE sin guía suficiente, mapa ambiguo y proyecciones sin horizonte definido. | Explicar errores en viajeros, procedencia y uso para decisiones. |
| C03 | CUMPLE | `requirements.txt:1`, metadatos de Streamlit/Plotly | Versiones y licencias comprobadas localmente. | Documentarlas en README. |
| C04 | CUMPLE | `app.py:80`, `app.py:269`, `app.py:380` | T12, T14, T15: filtros y selección de modelos producen resultados sin editar código; clic real en país B04. | Conservar y aclarar alcance de cada filtro. |
| C05 | CUMPLE | `data/pronosticos.csv`, `app.py:389` | Se visualizan seis conjuntos de modelos de familias diferentes; las 15 comparaciones por parejas no son copias idénticas. Esto acredita salidas operativas distintas, no su procedencia de entrenamiento. | Mantener; completar C06. |
| C06 | NO VERIFICABLE | `EXPORTAR_DESDE_NOTEBOOKS.md:6`, `:16` | El instructivo declara origen L1/L2; faltan notebooks, versiones y resultados originales. No se encontró entrenamiento en el código del dashboard. | Aportar notebooks/enlaces a commits y manifiesto de exportación. No entrenar sustitutos. |
| C07 | CUMPLE | `app.py:380`, `app.py:391` | T14: las ocho series muestran sus 5 o 6 modelos disponibles; nombres visibles. | Aclarar que son pronósticos del periodo de evaluación, no del futuro posterior a junio 2026. |
| C08 | PARCIAL | `app.py:385`, `data_logic.py:92` | MAE/RMSE correctos para 42 pares. La evaluación solo tiene tabla: faltan vistas gráficas de errores/desempeño y evidencia de correspondencia con L1/L2. | Usar los errores de los pronósticos existentes para una vista pertinente, sin reentrenar. |
| C09 | PARCIAL | `app.py:383`, `app.py:387` | La comparación actual usa mismo objetivo, fechas y unidad por serie; 63 pares completos por modelo. La tabla no sigue el multiselect y faltan metadatos originales de entrenamiento/evaluación. | Explicar conjunto de prueba, unidades, procedencia y sincronizar o aclarar la tabla. |
| C10 | NO CUMPLE | Inventario V01–V08 | Hay 7 componentes al inicio y 8 con selección; solo 6 candidatos defendibles en conteo conservador. No se acreditan ocho válidos. | Reemplazar las vistas problemáticas y completar ocho gráficos con función e interacción útiles. |
| C11 | CUMPLE | `app.py:281`, `app.py:292`, `app.py:303` | B04 y B05: barras → serie de país; evento real y reversión comprobados en Firefox. Se trata de dos gráficos enlazados, no de dos parejas distintas. | Conservar. |
| C12 | CUMPLE | `barras_pais`, `on_select="rerun"` | Clic en El Salvador muestra su evolución; doble clic en fondo elimina selección. No depende solo del dropdown global. | Añadir instrucciones para deseleccionar. |
| C13 | PARCIAL | `app.py:117`, `app.py:172` | T03: Visitantes oculta evolución. T02: Variación y Próx. período no alteran gráficos ni contenido. | Conectar las dos casillas o retirarlas; ofrecer selección coherente de vistas. |
| C14 | PARCIAL | `app.py:109`, `data_logic.py:65`, `:77` | T05/T06: mensual → anual → mensual funciona para observados; B10 comprueba detalle del treemap. La proyección anual produce fechas mensuales y usa cantidades de años como base mensual. | Corregir frecuencia/horizonte y distinguir el año 2026 incompleto. |
| C15 | PARCIAL | `ui_components.py:219`, `app.py:328`, `app.py:347` | Líneas/barras/treemap/heatmap corresponden a preguntas reales. El mapa no representa geografía real y omite regiones. | Usar geografía verificable o barras por región; no etiquetar polígonos arbitrarios como mapa geográfico. |
| C16 | PARCIAL | `app.py:177`, `app.py:263`, `ui_components.py:414` | Hay títulos y subtítulos; mini gráfica sin ejes/leyenda; modelos sin explicación ejecutiva de error, horizonte o incertidumbre. | Explicar cada gráfico, unidades, lectura y decisión posible. |
| C17 | PARCIAL | `styles.css:49`, `:198`, `ui_components.py:442` | Escritorio con paleta y jerarquía coherentes; botón sin acción, tarjetas HTML separadas de algunos gráficos y móvil obstruido. | Usar contenedores de Streamlit y adaptar navegación/espaciado al ancho disponible. |
| C18 | PARCIAL | `ui_components.py:10`, `:17`, `:447` | Observado azul y predicho naranja con trazos distintos. Todos los cinco territorios del mapa inicial quedan en la misma clase >150k; mini gráfica sin leyenda; no se certificó accesibilidad completa. | Escala adecuada al intervalo y explicación consistente; comprobar contraste y daltonismo. |
| C19 | NO CUMPLE | `ui_components.py:442`, `styles.css:211` | B03: botón no navega; T02: dos controles inertes; B07: menú móvil tapa contenido y no tiene cierre. | Acciones reales, feedback y menú adaptable. |
| C20 | PARCIAL | `styles.css:54`, `:201`, `ui_components.py:64` | Escritorio legible en general. B07: encabezado recortado y solo 70 px fuera del menú móvil; B08: año de heatmap se presenta como `2.024k`. | Ajustes responsive y eje de años categórico o formato entero. |
| C21 | NO CUMPLE | `app.py:164`, `:167`, `:245`, `data_logic.py:101` | T12: 2009 inventa variación +8.4%. T19 vacío: cifras fijas y excepción al no haber pares de evaluación. | Mostrar «Sin datos» y no calcular ni dibujar resultados sin soporte. |
| C22 | NO CUMPLE | `data_logic.py:83`, `ui_components.py:118`, `:425` | Las curvas distinguen colores, pero las cifras de respaldo y crecimientos fijos se presentan como indicadores/predicciones sin explicación ni atribución. | Separar observado, escenario hipotético y pronóstico exportado; eliminar valores de relleno. |
| C23 | PARCIAL | `app.py:410`, `ui_components.py:447` | Hay contexto general; faltan límites de los pronósticos y advertencia sobre valores negativos. No se encontraron recomendaciones causales explícitas que auditar. | Añadir lectura responsable y límites; no prometer recomendaciones que no existen. |
| C24 | PARCIAL | T01, T12–T15 y T19 | Datos actuales: arranque y recorridos probados sin excepciones. CSV vacío, esquema incorrecto y fechas sin solapamiento producen errores no manejados. | Validación de esquema/cobertura y mensajes de error informativos. |
| C25 | PARCIAL | `app.py:235`, `:281`, `:383` | Enlace real correcto; dos casillas inertes; detalle conserva Centro al elegir Asia; solo se usa el primer punto de una selección múltiple. | Definir selección única o comportamiento múltiple; sincronizar/explicar filtros locales. |
| C26 | PARCIAL | `app.py:177`, `:263`, `:323`, `:342` | Se responde cuánto, de dónde y cuándo; no hay preguntas directivas explícitas y el mapa ofrece una representación espacial injustificable. | Formular preguntas contestables y vincularlas a vistas y decisiones. |
| C27 | PARCIAL | `app.py:128`, `:416`, `:423` | Acerca de indica 2009–junio 2026 y corte metodológico declarado; el banner dice actualización 22 abr. 2025. Sin fuente verificable del corte 2023 ni límites sobre proyecciones/negativos. | Fecha derivada de los datos o fecha de publicación real; fuente y alcance verificables. |

Los estados C05/C07 no certifican que los algoritmos hayan sido entrenados correctamente. C06 mantiene explícitamente esa incertidumbre. Tampoco se transforma la ausencia de prueba en una aprobación.

## 4. Inventario V01–V08 y conteo estricto

| ID | Sección / archivo | Tipo y pregunta | Datos / interacción comprobada | Independiente / conteo |
|---|---|---|---|---|
| V01 | Resumen; `app.py:183`, `ui_components.py:177` | Línea histórica y proyección: ¿cómo evoluciona la demanda? | Serie/fecha/viajeros; filtros, granularidad y ocultamiento probados con AppTest. Observados correctos; proyección heurística y modo anual defectuosos. | Sí; candidato con corrección pendiente. No contar sus dos trazas como dos gráficos. |
| V02 | Resumen; `ui_components.py:219` | Supuesto mapa regional: ¿de dónde proceden? | Totales reales asignados a cinco polígonos fijos por orden del ranking. Sin coordenadas, GeoJSON ni evento de selección enlazado. | No admitido en conteo conservador: representación espacial engañosa y categorías omitidas. |
| V03 | Detalle regional; `ui_components.py:414` | Mini línea anual y extensión: tendencia de región | Datos anuales más crecimiento fijo 8%; `hoverinfo="skip"`, sin ejes, marcas o leyenda. Se muestra con más de un año. | Ambiguo; se excluye conservadoramente por lectura/interacción informativa no acreditada. Ser Plotly y tener barra de herramientas no basta. |
| V04 | Explorar; `app.py:284` | Barras: ¿qué países aportan más viajeros? | País/viajeros; top 5–20, rango, región y clic real. | Sí; cuenta como candidato válido. |
| V05 | Explorar; `app.py:303` | Línea de país: ¿cuándo llegan los viajeros seleccionados? | País/fecha/viajeros; aparece con clic real, desaparece al limpiar; mensual/anual. | Sí; candidato válido condicional a seleccionar país. No existe como gráfico en el estado inicial. |
| V06 | Explorar; `app.py:328` | Treemap: ¿por qué vías y fronteras ingresan? | Vía/frontera/viajeros; filtros temporales y clic real `level: null → Terrestre`. | Sí; candidato válido. Retorno del treemap no se verificó directamente; el cambio reversible de detalle temporal sí se probó aparte. |
| V07 | Explorar; `app.py:345` | Heatmap: ¿en qué meses se concentra la demanda? | Año/mes/viajeros; filtros y hover real `2.024k · Mar: 349,965`. | Sí; candidato válido, con formato del año por corregir. |
| V08 | Modelos; `app.py:391` | Líneas observado/modelos: ¿qué pronóstico se aproxima al histórico? | Serie/modelo/fecha/predicción; ocho series y selección 0–6 modelos probadas; vista de navegador accesible. | Sí; un candidato válido para resultados. Las seis curvas no equivalen a seis gráficos ni sustituyen una vista específica de desempeño. |

**Recuento:** 8 componentes candidatos posibles; 7 renderizados al inicio; 8 tras seleccionar un país. **Conteo conservador: 6 candidatos admisibles, con correcciones pendientes, no ocho visualizaciones plenamente aprobadas.** Si un evaluador aceptara la mini línea serían 7; si además aceptara el mapa se llegaría a 8 componentes, pero persisten sus problemas de exactitud y uso. El estado C10 no se aprueba por esa interpretación permisiva.

Excluidos adicionalmente: tarjetas KPI, tabla MAE/RMSE, controles, textos, pestañas y estados alternativos del mismo gráfico. El CSV PCA no está visualizado y no añade un noveno componente.

La interacción de hover/zoom no se ensayó individualmente para todas las figuras: hay evidencia de renderización, filtros y especificación Plotly para las seis candidatas; clic entre países, selección reversible, hover del heatmap y descenso del treemap sí se comprobaron en navegador. Por eso el conteo tampoco afirma ocho interacciones visuales verificadas.

## 5. Pruebas de enlaces

### A. Barras de países → evolución de país: CUMPLE

- Origen: `barras_pais`, `app.py:292`, evento de selección de puntos con `on_select="rerun"`.
- Estado: `st.session_state["barras_pais"]["selection"]["points"]`, lectura en `app.py:281`; primer país válido de las barras actuales.
- Destino: `app.py:303`, serie temporal agrupada para ese país dentro de los filtros de fecha/región vigentes.
- Antes: mensaje «Haz clic en una barra…», 7 gráficos en el árbol de la aplicación.
- Acción real: clic en la barra El Salvador en Firefox, viewport 1440×1000.
- Después: título «Evolución: El Salvador», línea con su historia y 8 gráficos.
- Limpieza real: doble clic en el fondo del gráfico de barras; vuelve el mensaje y se retira la línea. Repetir un clic sobre la misma barra no limpió la selección.
- Selección múltiple simulada con AppTest: dos países seleccionados; solo se muestra el primero. Documentar selección única o dar comportamiento explícito a múltiples puntos.
- Filtro sin coincidencias: la guarda de pertenencia al top evita usar un país que ya no aparece; no se completó un caso de interacción real que deje la selección fuera del top.
- Navegación: se recorrieron las cuatro pestañas. No se certificó una secuencia extensa de selección + cambio de cada filtro + retorno de pestaña.
- Evidencia: `browser_results.json` B04/B05; `desktop_explorar_antes.png`, `desktop_explorar_despues.png`; T09–T11 prueban también la lógica con estado simulado, que no se confunde con el clic real.

### B. Mapa → detalle regional: NO CUMPLE como vínculo anunciado

`app.py:221` dice que el mapa se enlaza con el detalle, pero `app.py:213` dibuja el mapa sin `on_select` ni callback. El detalle depende de un selectbox separado (`app.py:235`), no de un clic sobre el gráfico. El mapa contiene únicamente trazas Scatter y una anotación.

Además, al cambiar el filtro global a Asia, AppTest observó que el detalle seguía en América Del Centro (T07). El `index` recalculado no sustituye el estado ya existente de `sel_reg_detalle`. Este segundo vínculo no se debe anunciar como funcionando. El enlace A sí satisface la exigencia de al menos dos gráficos conectados; no se exige una segunda pareja para C11.

## 6. Auditoría de modelos M1–M3 y adicionales

Se eligieron ARIMA/SARIMA, Prophet y LSTM para examinar tres familias. También están Holt-Winters, Seasonal Naive y Suavizado Exponencial de Holt. Hay cinco familias en las ocho series; LSTM solo en `Total` y `Tipo_Turista`.

| Campo | M1 ARIMA/SARIMA (mejor) | M2 Prophet | M3 LSTM |
|---|---|---|---|
| Identidad operativa | Regresión/pronóstico de viajeros mensuales; no se conservan órdenes ARIMA o especificaciones. | Regresión/pronóstico mensual; sin parámetros/componentes exportados. | Pronóstico mensual; arquitectura, ventanas y escalado ausentes. |
| Procedencia | Atribuido a L1 por guía de exportación; no verificable sin notebook/enlace versionado. | Igual: declarado L1, sin evidencia del cálculo original. | Declarado L2; no está el notebook ni `mejor_lstm_por_serie`. |
| Entrada al dashboard | CSV con `serie, modelo, fecha, prediccion`, más observados para evaluar. No hace inferencia desde variables originales. | Igual. | Igual. |
| Salida existente | 8 series × 63 meses = 504 valores. | 8 × 63 = 504 valores. | 2 × 63 = 126 valores. |
| Objetivo / unidad | Viajeros por mes en la serie elegida. | Igual. | Igual, solo dos series disponibles. |
| Evaluación visible en Total | MAE 116,033; RMSE 134,416. | MAE 97,588; RMSE 107,975. | MAE 135,961; RMSE 153,091. |
| Comparabilidad | Los tres tienen los mismos 63 meses en Total y Tipo_Turista. Corte de prueba declarado: abril 2021; entrenamiento hasta marzo 2021 no verificable. | Misma tarea/fechas/unidad. | Misma tarea/fechas/unidad donde existe. |
| Visualización | Curva conjunta y tabla; sin gráfico específico de residuos/error. | Igual. | Igual. |
| Limitaciones | 128 predicciones negativas en las ocho series; sin intervalos ni metadatos originales. | 6 negativas. | Ninguna negativa en las salidas guardadas; no implica calidad suficiente. |

Resultados de los demás modelos en `Total`: Holt-Winters MAE 303,212 / RMSE 328,153; Seasonal Naive 235,731 / 253,203; Holt 196,844 / 217,086. Negativas en todos sus registros: Holt-Winters 282, Holt 170, Seasonal Naive 0. Total de negativas: 586/2,646, aproximadamente 22.1%.

La auditoría recalculó MAE y RMSE para las 42 combinaciones y verificó igualdad con la tabla del programa, incluyendo su redondeo. Cada combinación actual tiene 63 pares; no hay fechas faltantes que alteren ahora la comparabilidad. Las 15 comparaciones posibles entre familias tienen al menos alguna salida diferente: no son copias completas con etiquetas distintas. Eso no reemplaza la evidencia del entrenamiento original.

No se exige una matriz de confusión para estos pronósticos ni un formato específico de evaluación. La vista de errores propuesta ayudaría a explorar el desempeño y a cubrir el mínimo de gráficos; la falta de un gráfico de residuos concreto no se presenta como infracción textual independiente del PDF ausente. El estado parcial también responde a la falta de trazabilidad y contextualización verificable de las evaluaciones.

No recortar las predicciones negativas a cero de forma silenciosa: cambiaría resultados y métricas previas. Conservar el valor para evaluación, explicar la limitación y decidir cualquier transformación con evidencia de L1/L2.

La función `calcular_metricas_error` carece de guarda para cero pares válidos: el promedio da NaN y `round` falla. Esto se reprodujo desplazando fechas cien años en una copia temporal, sin modificar los CSV originales.

Faltantes concretos para trazabilidad: notebooks L1/L2 o enlaces a versiones inmutables, identificación de las ejecuciones que exportaron los CSV, parámetros/ventanas y transformaciones utilizadas, fechas de entrenamiento/prueba, métricas originales y fuente del Excel. No es obligatorio subir binarios si los resultados guardados y su origen verificable son suficientes para reutilización.

## 7. Pruebas funcionales y UX ejecutadas

Métodos: análisis de todos los archivos de código, AST de los cuatro `.py`, validación de los cinco CSV crudos, llamadas directas a funciones, AppTest de Streamlit y Firefox 156.0 con clics reales mediante WebDriver BiDi. La automatización del navegador se basó en la [documentación de Mozilla para crear una conexión BiDi](https://developer.mozilla.org/en-US/docs/Web/WebDriver/How_to/Create_BiDi_connection). La fuente externa describe el método de prueba; los hallazgos proceden del repositorio y de su ejecución.

| Prueba | Procedimiento / evidencia | Resultado |
|---|---|---|
| Inicio | T01, B01: ejecutar `app.py` con CSV actuales | Sin excepciones; 4 pestañas, 7 gráficos iniciales. Primer arranque de AppTest medido en esta batería: ~0.48 s, después de una ejecución previa; no es benchmark de instalación o carga fría. |
| Navegación | B03/B06 y recorrido real por las cuatro pestañas | Pestañas accesibles; botón HTML de detalle no navega. |
| Fechas/categorías | T12: 8 categorías con año 2009 | Sin excepciones; detectado +8.4% fijo al no existir año anterior. |
| Combinación región/año | T15: 9 regiones con 2026 | Sin excepciones. El detalle regional conserva su estado independiente. |
| Restaurar | T04: alterar casillas y restaurar | Restablece las 7 claves del sidebar y recupera gráficos iniciales. T08: no restablece selección local de detalle. |
| Mostrar/ocultar | T02/T03 | Visitantes funciona; Variación y Próx. período no modifican figuras ni HTML de contenido. |
| Enlace entre gráficos | B04/B05, T09–T11 | Clic real y reversión correctos; múltiples puntos solo usan el primero. |
| Detalle temporal | T05/T06 | Observados cambian mensual/anual y regresan; proyección anual incorrecta. |
| Detalle de treemap | B10 | Clic en Terrestre cambia `level` a `Terrestre`; regreso no ensayado directamente. |
| Hover | B08 | Heatmap muestra valor real; año usa abreviatura `2.024k`, difícil de leer. |
| Modelos | T14: recorrer las 8 series y elegir todos los disponibles | Sin excepciones; 5 o 6 modelos más observado según serie. |
| Selección vacía de modelos | T13 | No falla, pero desaparece el gráfico sin mensaje específico; la tabla permanece con todos los modelos. |
| Cálculo de errores | T18, 42 pares; comparación con cálculo independiente | MAE/RMSE iguales; todas las parejas tienen 63 fechas. |
| Falta archivo histórico | T19, copia temporal sin `series_mensuales.csv` | Mensaje comprensible y detención; sin excepción. |
| Falta archivo de predicciones | T19, copia sin `pronosticos.csv` | Mensaje informativo; histórico sigue funcionando. |
| CSV histórico vacío | T19, solo encabezados en copia | Falla: `Neither start nor end can be NaT` en `cargar_todo`. |
| Esquema incorrecto | T19, columna fecha renombrada en copia | Falla: `'DataFrame' object has no attribute 'fecha'`. |
| Pronósticos sin solapamiento | T19, fechas desplazadas en copia | Falla: `cannot convert float NaN to integer` en métricas. |
| Filtros sin información | T19, copia con histórico solo de 2009 y filtro por defecto 2022–2026 | Exploración da aviso, pero resumen presenta valores de relleno y mapa usa todo el histórico; después la evaluación sin pares falla. Este caso es una prueba de robustez, no un fallo observado con los CSV actuales. |
| Escritorio | Firefox 1440×1000 y capturas después de aplicar CSS | Estructura general utilizable; algunas tarjetas solo agrupan títulos y no envuelven al gráfico de Streamlit. |
| Móvil | B07, 390×844 | Sidebar 320 px, sin botón de cierre; cubre contenido. Título tiene `y≈-31.4`, altura 115.2 dentro de banner de 76 px: recorte confirmado. |
| Accesibilidad | Inspección visual/DOM | Etiquetas y trazos distintos ayudan; menú móvil bloqueante y mini gráfica sin lectura. No se certifican teclado, lector de pantalla, contraste completo ni daltonismo. |
| Rendimiento | Batería de AppTest ~13.1 s en total, varias decenas de reruns | No se observaron bloqueos en los recorridos probados; no se probó concurrencia ni carga. Cada rerun vuelve a leer CSV y construir vistas; no hay cache. |

Los escenarios destructivos se hicieron exclusivamente sobre copias en `/tmp/lab10-audit-evidence/fixtures/`. Los originales no se tocaron. La auditoría no afirma haber probado todas las combinaciones de filtros ni todos los tamaños de pantalla.

Evidencia temporal:

- [Resultados AppTest y datos](/tmp/lab10-audit-evidence/results.json).
- [Resultados del navegador](/tmp/lab10-audit-evidence/browser_results.json).
- [Script de pruebas reproducible](/tmp/lab10_audit_checks.py).
- [Script de navegador](/tmp/lab10_browser_audit.py).
- [Resumen escritorio](/tmp/lab10-audit-evidence/desktop_resumen.png).
- [Explorar antes](/tmp/lab10-audit-evidence/desktop_explorar_antes.png) y [después del clic](/tmp/lab10-audit-evidence/desktop_explorar_despues.png).
- [Detalle del treemap](/tmp/lab10-audit-evidence/desktop_treemap_detalle.png).
- [Modelos](/tmp/lab10-audit-evidence/desktop_modelos.png), [Acerca de](/tmp/lab10-audit-evidence/desktop_acerca.png) y [móvil](/tmp/lab10-audit-evidence/mobile_resumen.png).

Los recursos en `/tmp` son evidencia de esta sesión, no archivos versionados ni una publicación permanente.

## 8. Riesgo por bloques de la rúbrica 30/50/20

| Bloque | Riesgo cualitativo | Motivo |
|---|---|---|
| Diseño y UX — 30 puntos | Alto | Escritorio coherente y legible en general, pero móvil bloqueado, botón inerte, mapa ambiguo y controles que no cumplen lo anunciado. |
| Visualizaciones y análisis — 50 puntos | Alto | Enlace real sí existe y los modelos sí muestran resultados; no se acreditan ocho vistas válidas, faltan gráficos de desempeño, origen L1/L2 y exactitud de proyecciones/indicadores. |
| Funcionamiento e interactividad — 20 puntos | Alto | Arranque y rutas principales estables, pero fallan controles anunciados y manejo de entradas vacías/esquema/cobertura; resultados de relleno agravan el impacto. |

No se inventan puntos por subcriterio ni una nota oficial. El peso del bloque B hace especialmente urgente resolver conteo, exactitud y evidencia de modelos.

## 9. Hallazgos priorizados y acciones concretas

| ID / severidad | Evidencia y requisito | Corrección propuesta / dependencia |
|---|---|---|
| H01 CRÍTICO — valores de relleno | `ui_components.py:118`: +8.4% si no hay variación; `app.py:164`, `:167`: crecimiento fijo y 132000; `app.py:245`, `:247`, `:248`: 42350, +12.5%, 12%. T12 lo reproduce con datos reales de 2009; T19 amplía el caso vacío. C21/C22. | Conservar `None`/estado sin cálculo; mostrar «Sin datos» y omitir inferencias. Nunca sustituir ausencia de evidencia con cifras de muestra. |
| H02 ALTO — proyección temporal inválida y no atribuida | `data_logic.py:81` crea frecuencia mensual aunque la entrada sea anual; `:83` fija 5%; `ui_components.py:425` fija 8%. T05 da febrero/marzo de 2026 después del agregado 2026. C06/C14/C22. | Usar resultados ya exportados si existen para el horizonte, o retirar predicción futura y explicar cobertura. Si se admite un escenario, etiquetarlo, justificar tasa y frecuencia y separarlo de los modelos evaluados. No entrenar modelos nuevos para tapar el faltante. |
| H03 ALTO — ocho vistas no acreditadas | V01–V08: seis candidatos admisibles conservadoramente. C10. | Reemplazar mapa por representación correcta; volver útil/verificable la vista regional o reemplazarla por un gráfico pertinente, por ejemplo errores de modelos existentes. Confirmar recuento sin KPI/tablas/trazas duplicadas. |
| H04 ALTO — geografía arbitraria y omisiones | `ui_components.py:234` asigna ranking a cinco polígonos fijos; `:280` ofrece respaldo de 35000. En 2022–2026 existen 10 categorías incluyendo Sin dato; solo se pintan las primeras 5. Todas superan 150k, de modo que la escala inicial queda saturada. C15/C18. | Mapa real con correspondencia geográfica demostrable y categorías completas, o barras regionales. Fuente cartográfica necesaria solo si se conserva un mapa. Retirar respaldo 35000 y aclarar grupos no geográficos como Cruceristas. |
| H05 ALTO — controles sin acción | `app.py:118`, `:119`: claves leídas solo al crear/restaurar widgets; T02 compara figuras/HTML idénticos. `ui_components.py:442`: atributo onclick desaparece en el DOM; B02/B03 comprueban botón inerte. C13/C19/C25. | Conectar a contenedores o trazas reales; reemplazar navegación HTML por un mecanismo funcional de Streamlit. |
| H06 ALTO — móvil obstruido | `styles.css:54`, `:55`, `:198`, `:201`, `:211`, `:378`: banner fijo, sidebar fijo sin cierre y 3 columnas KPI sin reglas responsive. B07 y captura móvil. C17/C19/C20. | Permitir colapsar el sidebar; media queries o disposición adaptable para banner, KPI, tarjetas y columnas. Verificar teclado y móvil de nuevo. |
| H07 ALTO — trazabilidad incompleta | Solo hay CSV y guía de exportación; no están notebooks, parámetros ni métricas originales. C06/C08/C09. | Incorporar evidencia ya existente de L1/L2 con commit/fecha, esquema y particiones. No exigir binarios si la exportación verificable basta. |
| H08 ALTO — errores no manejados | `data_logic.py:59`, `:60`, `:98`, `:101`. T19 reproduce NaT, columna faltante y NaN sin pares. C21/C24. | Validar esquema, vacíos, tipos y fechas antes de usar atributos/cálculos; alinear pares válidos y comunicar su cantidad; devolver estado sin evaluación si n=0. |
| H09 ALTO — evaluaciones negativas sin contexto | 586 predicciones de viajeros <0; `app.py:393` las dibuja sin advertencia. C22/C23/C27. | Explicar limitación del modelo, señalar valores no plausibles y mantener métricas originales. Cualquier ajuste debe ser explícito y comparable, no clipping silencioso. |
| H10 MEDIO — filtros y períodos incoherentes | `app.py:234`: detalle permanece en Centro al elegir Asia; `:326` vías no filtra región porque no tiene esa dimensión; modelos usan selector independiente; `:194` recurre a todo el histórico si el periodo queda vacío. C19/C21/C25/C27. | Sincronizar filtros compatibles y rotular los que no aplican; en vacío no volver a datos fuera del intervalo. No inventar cruce región/frontera ausente del esquema. |
| H11 MEDIO — KPI y años con lectura engañosa | `app.py:160` acumula todo el rango, pero `:161` calcula variación solo del último año; texto `vs. mismo período anterior` sugiere otra base. Agregado 2026 es solo enero–junio. `ui_components.py:64` aplica `~s` al año: B08 muestra 2.024k. C16/C20/C22. | Indicar total acumulado versus variación interanual del año final; marcar YTD/meses disponibles; año categórico o entero, sin abreviatura SI. |
| H12 MEDIO — fecha y documentación | `app.py:128` fija actualización de abril 2025 pese a datos hasta junio 2026; README mínimo. Se declara corte metodológico 2023 sin fuente disponible. C27. | Fecha real de extracción/publicación y referencias comprobables. Documentar instalación, fuentes, evaluación y límites. |
| H13 MEDIO — desempeño sin vista propia | `app.py:385` solo tabla y `:391` curvas de nivel. C08/C09. | Añadir visualización de errores o desempeño usando observados y predicciones existentes, con mismos 63 meses y unidades. Esta adición debe responder una pregunta y no inflar artificialmente el conteo. |
| H14 BAJO — cobertura de versiones y mantenimiento | `requirements.txt:1` admite versiones no ensayadas; `mostrar_grafico` adapta width, otros widgets no tienen esa guarda; CSS depende de atributos internos del framework. | Fijar un entorno probado o probar mínimo declarado y documentarlo. La incompatibilidad con 1.40 no fue ejecutada: se reporta como riesgo, no fallo confirmado. |

Orden recomendado: retirar resultados sin evidencia y corregir proyección/frecuencia → resolver gráficos y desempeño con artefactos existentes → controles y datos vacíos → trazabilidad y contexto → móvil y pulido de presentación. No hace falta reescribir toda la arquitectura para atender estos puntos.

## 10. Cambios realizados

- Ningún archivo de implementación o datos del repositorio fue editado por esta auditoría.
- No se hicieron commit, push, rebase ni cambios al índice de Git.
- Se creó un entorno Python temporal, scripts de prueba, copias de datos para escenarios adversos, JSON y capturas en `/tmp`.
- Este informe describe propuestas; no afirma que estén implementadas.

## 11. Verificaciones pendientes

1. **Enunciado original:** contrastar el MD con las tres páginas del PDF antes de emitir una certificación formal de cumplimiento textual.
2. **L1/L2:** obtener notebooks o enlaces versionados, salidas originales, parámetros y particiones; rastrear cada combinación de predicciones hasta esa evidencia.
3. **Fuente histórica:** aportar el Excel/base original y su contexto para comprobar fracciones de viajeros y el cambio metodológico declarado en 2023.
4. **Instalación limpia:** crear un entorno sin paquetes del sistema, instalar solo requirements y ejecutar. Si se mantiene mínimo 1.40, ensayarlo expresamente con una versión compatible de Python.
5. **Interacciones restantes:** ensayar retorno del treemap, selección + cambio de filtros/top N/pestañas, ausencia de coincidencias y selección múltiple real. Se verificó el vínculo básico y su limpieza, no toda esa matriz.
6. **Accesibilidad completa:** teclado, foco visible, lector de pantalla, contraste por componente y diferenciación para daltonismo. Corregir primero la obstrucción móvil confirmada.
7. **Pruebas posteriores a correcciones:** volver a contar vistas válidas, verificar que cada una responde una pregunta diferente y comprobar escenarios adversos sin cifras de relleno.
8. **Rendimiento:** concurrencia, latencia de interacciones en equipo objetivo y carga de datasets más grandes, si se consideran parte de la entrega.
9. **Documento de diseño/administración:** no hay PDF de diseño versionado en el inventario revisado. Los apartados 4.1–4.6 requieren ese documento. Canvas, inscripción de grupo, entrega del avance, fechas de entrega y autoría real no pueden certificarse desde el código o los nombres de Git. Las fechas administrativas citadas por el MD no se verificaron con la plataforma ni el PDF original.

## 12. Checklist final

| Exigencia importante | Estado |
|---|---|
| Dashboard de turismo de Guatemala y exploración autónoma | CUMPLE |
| Framework libre y abierto | CUMPLE |
| Arranque con los datos y versiones probados | CUMPLE |
| Resultados de al menos tres modelos distintos disponibles en la interfaz | CUMPLE |
| Procedencia y reutilización de L1/L2 | NO VERIFICABLE |
| Evaluación y comparación bien contextualizadas de modelos | PARCIAL |
| Ocho visualizaciones válidas distintas | NO CUMPLE |
| Dos gráficos conectados mediante interacción real | CUMPLE |
| Selección efectiva de todas las vistas anunciadas | PARCIAL |
| Subir y bajar detalle sin errores analíticos | PARCIAL |
| Fidelidad de mapa, indicadores y proyecciones | NO CUMPLE |
| Ausencia de cifras inventadas ante datos insuficientes | NO CUMPLE |
| Manejo robusto de datos vacíos/esquema/fechas | NO CUMPLE |
| Navegación y controles completos | PARCIAL |
| Diseño usable en escritorio | PARCIAL |
| Diseño usable en móvil de 390 px | NO CUMPLE |
| Fuentes, alcance y limitaciones visibles | PARCIAL |
| Diseño PDF y requisitos administrativos | NO VERIFICABLE; fuera del dictamen de código |

**Dictamen: NO LISTO: no se acreditan ocho visualizaciones válidas; hay indicadores de relleno y proyecciones temporalmente incorrectas, controles inertes, problemas móviles, errores ante entradas incompletas y falta evidencia de origen de los modelos.**

Este dictamen evalúa el código/dashboard frente al MD suministrado. No certifica el documento de diseño, la transcripción del enunciado original ni el cumplimiento de entregas administrativas.
