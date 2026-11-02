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
