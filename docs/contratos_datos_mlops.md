# Contratos de datos MLOps

Especificación aplicada: `01_pipeline_gobernanza.md` y el enunciado oficial `Laboratorio_11_MLOps_2026.pdf` (ejercicios 1.1–8.4; matriz en `docs/auditoria_final_lab11.md`).

## Distinción de roles temporales

| Concepto | Definición en este pipeline |
| --- | --- |
| Observado | Valor de `viajeros` en `series_mensuales.csv` (y desagregaciones) |
| Estimación retrospectiva (backtest) | Predicción generada para meses ya observados, entrenando solo hasta el corte de train del YAML |
| Proyección futura auténtica | Predicción para meses posteriores al último mes observado; **este pipeline no la produce** (eval termina en el último mes con dato) |

No se denomina «pronóstico futuro» a una estimación que termina en junio 2026 si ese mes ya está en las fuentes.

## Fuentes institucionales (solo lectura)

Los CSV de origen **no se modifican**, no se suben a servicios externos y **no se copian** a la imagen Docker (se montan por volumen).

### 1. `data/series_mensuales.csv` — fuente principal del modelado

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `serie` | string no vacío | sí |
| `fecha` | fecha mensual al día 1 (`YYYY-MM-01`) | sí |
| `viajeros` | numérico finito ≥ 0 | sí |

- **Clave única:** (`serie`, `fecha`).
- **Granularidad:** mensual.
- **Unidad:** `viajeros/mes`.
- **Cobertura declarada:** 2009-01 a 2026-06 (210 meses por serie; 8 series).
- **Uso en pipeline:** única entrada de modelado, evaluación y factores de reparto.
- **Política de huecos:** un mes ausente **no** se imputa a cero. Si falta un mes indispensable dentro de la ventana de train/eval del YAML, el control QC-B falla y se aborta.

Series esperadas: `Total`, `Via_Aérea`, `Via_Terrestre`, `Via_Marítima`, `Tipo_Turista`, `Tipo_Excursionista`, `Tipo_Cruceristas`, `Tipo_Viajero`.

Grupos de reparto **separados** (no son una sola partición exclusiva):

- Vías: `Via_Aérea`, `Via_Terrestre`, `Via_Marítima` (comparables entre sí frente a `Total`).
- Tipos: `Tipo_*` (comparables entre sí; no se suman con las vías como si fueran mutuamente excluyentes).

### 2. `data/pais_mensual.csv` — contexto / tablero

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `fecha` | mensual día 1 | sí |
| `pais` | string | sí |
| `region` | string | sí |
| `viajeros` | numérico ≥ 0 | sí |

- **Clave única comprobada:** (`fecha`, `pais`) — en los datos actuales no hay duplicados; `region` es atributo del país en cada fila.
- **Uso en pipeline:** **no participa** en el cálculo de estimaciones ni en factores. Se documenta y puede validarse de forma opcional. El tablero sí la usa.

### 3. `data/via_frontera.csv` — contexto / tablero

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `fecha` | mensual día 1 | sí |
| `via` | string | sí |
| `frontera` | string | sí |
| `viajeros` | numérico ≥ 0 | sí |

- **Clave única:** (`fecha`, `via`, `frontera`).
- **Uso en pipeline:** **no participa** en el modelado. Solo contexto y tablero.

## Ventanas temporales (solo YAML)

Leídas exclusivamente de `config/pipeline_config.yaml`:

- Train: `temporal_split.train_start` … `train_end` (inicial: 2009-01-01 … 2021-03-01).
- Eval / backtest de origen fijo: `eval_start` … `eval_end` (inicial: 2021-04-01 … 2026-06-01).
- Meses sin observación comparable se excluyen de MAE/RMSE. `excluded_evaluation_periods` permite exclusiones metodológicas **explícitas** con motivo; no se excluyen automáticamente meses que sí tienen observación comparable.

## Esquema de resultados aprobados

Archivo: `data/estimaciones_aprobadas.csv`

| Campo | Descripción |
| --- | --- |
| `destino` | Territorio (p. ej. Guatemala) |
| `serie` | Serie estimada |
| `modelo` | Nombre del procedimiento |
| `fecha` | Mes (`YYYY-MM-DD`, día 1) |
| `prediccion` | Estimación en viajeros/mes (dominio ≥ 0 en versión aprobada) |
| `unidad_medida` | `viajeros/mes` |
| `run_id` | Identificador de la corrida |
| `fecha_generacion` | Timestamp de generación |
| `version_procedimiento` | Versión del pipeline |
| `estado_aprobacion` | `APROBADO` u otro estado de candidato |

Clave de integridad de salida: (`destino`, `serie`, `fecha`).

Artefactos candidatos (no publicados): `reports/estimaciones_candidatas_<run_id>.csv`.  
Reportes de calidad: `reports/quality_report_<run_id>.json`.  
Respaldos: `data/backup_aprobadas/`.
