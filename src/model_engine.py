"""Modelado, factores de reparto, evaluación temporal y aceptación (Laboratorio 11).

Reglas:
- Entrenamiento solo con datos hasta el corte temporal correspondiente (sin fuga).
- Backtest de origen fijo: train hasta train_end; estimaciones en eval_start..eval_end.
- MAE/RMSE solo en meses idénticos comparables; N=0 → métricas NaN (no ceros inventados).
- Pronósticos negativos no se recortan antes de medir; la salida aprobada sí exige dominio ≥ 0.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

VIA_SERIES = ("Via_Aérea", "Via_Terrestre", "Via_Marítima")
TIPO_SERIES = ("Tipo_Turista", "Tipo_Excursionista", "Tipo_Cruceristas", "Tipo_Viajero")
APPROVED_COLUMNS = [
    "destino", "serie", "modelo", "fecha", "prediccion", "unidad_medida",
    "run_id", "fecha_generacion", "version_procedimiento", "estado_aprobacion",
]


def calculate_repartition_factors(
    df_train: pd.DataFrame,
    target_series: str = "Total",
    required_series: Optional[Sequence[str]] = None,
) -> Dict[str, float]:
    """Factores f_i solo con Train. Prohíbe fallback silencioso a 0.0 en series obligatorias."""
    totales = df_train.groupby("serie")["viajeros"].sum()
    total_viajeros = float(totales.get(target_series, 0.0))
    if total_viajeros <= 0:
        raise ValueError(
            f"Total de viajeros en entrenamiento es {total_viajeros}; denominador inválido."
        )

    factors = {serie: float(suma / total_viajeros) for serie, suma in totales.items()}
    required = list(required_series or [])
    faltantes = [s for s in required if s not in factors]
    if faltantes:
        raise ValueError(
            f"Series obligatorias ausentes en Train para factores de reparto: {faltantes}. "
            "No se asigna 0.0 por omisión."
        )
    return factors


def verify_repartition_groups(factors: Dict[str, float], atol: float = 0.05) -> Dict[str, Any]:
    """Verifica cobertura de grupos Via_* y Tipo_* por separado (no una sola partición)."""
    report: Dict[str, Any] = {"via_sum": None, "tipo_sum": None, "warnings": []}
    via_vals = [factors[s] for s in VIA_SERIES if s in factors]
    tipo_vals = [factors[s] for s in TIPO_SERIES if s in factors]
    if len(via_vals) == len(VIA_SERIES):
        report["via_sum"] = float(sum(via_vals))
        if abs(report["via_sum"] - 1.0) > atol:
            report["warnings"].append(
                f"Suma de factores Via_* = {report['via_sum']:.4f} (tol ±{atol})."
            )
    if len(tipo_vals) == len(TIPO_SERIES):
        report["tipo_sum"] = float(sum(tipo_vals))
        if abs(report["tipo_sum"] - 1.0) > atol:
            report["warnings"].append(
                f"Suma de factores Tipo_* = {report['tipo_sum']:.4f} (tol ±{atol})."
            )
    return report


def fit_and_predict_seasonal_naive(
    train_series: pd.Series, eval_dates: pd.DatetimeIndex, lag: int = 12
) -> pd.Series:
    """Baseline Seasonal Naive; historial de evaluación solo con predicciones previas (OOS)."""
    history = train_series.sort_index().copy()
    preds = []
    for dt in eval_dates:
        lag_date = dt - pd.DateOffset(months=lag)
        val = history.loc[lag_date] if lag_date in history.index else history.iloc[-1]
        preds.append(float(val))
        history.loc[dt] = float(val)
    return pd.Series(preds, index=eval_dates, dtype=float)


def fit_and_predict_historical_mean(
    train_series: pd.Series, eval_dates: pd.DatetimeIndex
) -> pd.Series:
    """Promedio histórico por mes calendario, solo con Train."""
    monthly_means = train_series.groupby(train_series.index.month).mean().to_dict()
    fallback = float(train_series.mean())
    preds = [float(monthly_means.get(dt.month, fallback)) for dt in eval_dates]
    return pd.Series(preds, index=eval_dates, dtype=float)


def fit_and_predict_holt_winters(
    train_series: pd.Series,
    eval_dates: pd.DatetimeIndex,
    seasonal_periods: int = 12,
    trend: str = "add",
    seasonal: str = "add",
    clip_negative: bool = False,
) -> Tuple[pd.Series, Any]:
    """Holt-Winters aditivo. Por defecto NO recorta negativos (evaluación fiel)."""
    ts = train_series.asfreq("MS")
    model = ExponentialSmoothing(
        ts,
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    )
    fitted = model.fit(optimized=True)
    forecast = fitted.forecast(steps=len(eval_dates))
    forecast.index = eval_dates
    if clip_negative:
        forecast = forecast.clip(lower=0.0)
    return forecast.astype(float), fitted


def build_evaluation_mask(
    y_true: pd.Series,
    excluded_periods: Optional[Iterable[Dict[str, str]]] = None,
) -> Tuple[pd.DatetimeIndex, Dict[str, Any]]:
    """Meses evaluables: observación finita presente; exclusiones YAML solo si se declaran."""
    y_true = y_true.sort_index()
    n_total = int(len(y_true))
    comparable = y_true[np.isfinite(y_true.to_numpy(dtype=float, na_value=np.nan))]
    excluded_applied: List[Dict[str, str]] = []
    idx = comparable.index
    for item in excluded_periods or []:
        start = pd.Timestamp(item["start"])
        end = pd.Timestamp(item["end"])
        reason = item.get("reason", "exclusión configurada")
        mask_ex = (idx >= start) & (idx <= end)
        if mask_ex.any():
            excluded_applied.append(
                {
                    "start": str(start.date()),
                    "end": str(end.date()),
                    "reason": reason,
                    "n_months": str(int(mask_ex.sum())),
                }
            )
            idx = idx[~mask_ex]
    info = {
        "n_total": n_total,
        "n_evaluable": int(len(idx)),
        "n_missing_or_nonfinite": n_total - int(len(comparable)),
        "excluded_periods": excluded_applied,
        "excluded_months": [d.strftime("%Y-%m") for d in sorted(set(comparable.index) - set(idx))],
    }
    return pd.DatetimeIndex(idx), info


def compute_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    epsilon: float = 1.0,
    evaluable_index: Optional[pd.DatetimeIndex] = None,
) -> Dict[str, Any]:
    """MAE y RMSE en meses idénticos comparables.

    La métrica relativa usa denominador |y|+epsilon (NO es MAPE convencional).
    Se reporta como `ape_eps_pct` para evitar confusión.
    Si N=0 no se sustituyen métricas por ceros.
    """
    if evaluable_index is None:
        evaluable_index, _ = build_evaluation_mask(y_true)

    common = (
        y_true.dropna().index
        .intersection(y_pred.dropna().index)
        .intersection(evaluable_index)
    )
    if len(common) == 0:
        return {
            "mae": float("nan"),
            "rmse": float("nan"),
            "ape_eps_pct": float("nan"),
            "mape_note": "ape_eps_pct usa |y|+epsilon; no es MAPE convencional",
            "n": 0,
        }

    yt = y_true.loc[common].to_numpy(dtype=float)
    yp = y_pred.loc[common].to_numpy(dtype=float)
    errors = yt - yp
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    ape_eps = float(np.mean(np.abs(errors) / (np.abs(yt) + epsilon)) * 100.0)
    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "ape_eps_pct": round(ape_eps, 2),
        "mape_note": "ape_eps_pct usa |y|+epsilon; no es MAPE convencional",
        "n": int(len(common)),
    }


def validate_estimates_frame(
    df: pd.DataFrame,
    required_series: Sequence[str],
    require_non_negative: bool = True,
    require_approved_state: bool = False,
) -> Dict[str, Any]:
    """Valida integridad del DataFrame completo de estimaciones (todas las filas)."""
    reasons: List[str] = []
    missing_cols = [c for c in APPROVED_COLUMNS if c not in df.columns]
    if missing_cols:
        reasons.append(f"Faltan columnas de esquema: {missing_cols}.")
        return {"ok": False, "reasons": reasons}

    if df.empty:
        reasons.append("El DataFrame de estimaciones está vacío.")

    for col in ("destino", "serie", "modelo", "unidad_medida", "run_id", "version_procedimiento"):
        if df[col].map(_blank).any():
            reasons.append(f"Etiquetas vacías en columna '{col}'.")

    fechas = pd.to_datetime(df["fecha"], errors="coerce")
    if fechas.isna().any() or (fechas.dt.day != 1).any():
        reasons.append("Fechas inválidas o no normalizadas al día 1.")

    pred = pd.to_numeric(df["prediccion"], errors="coerce")
    if pred.isna().any() or np.isinf(pred.to_numpy(dtype=float, na_value=np.nan)).any():
        reasons.append("Hay predicciones nulas o no finitas.")
    if require_non_negative and (pred < 0).any():
        reasons.append(f"Hay {(pred < 0).sum()} predicciones negativas no permitidas en salida.")

    dups = int(df.duplicated(subset=["destino", "serie", "fecha"]).sum())
    if dups:
        reasons.append(f"Claves duplicadas (destino, serie, fecha): {dups} filas.")

    presentes = set(df["serie"].unique())
    faltan = [s for s in required_series if s not in presentes]
    if faltan:
        reasons.append(f"Faltan series secundarias/obligatorias en la salida: {faltan}.")

    if require_approved_state and not (df["estado_aprobacion"] == "APROBADO").all():
        reasons.append("Estado de aprobación inconsistente para publicación.")

    return {"ok": len(reasons) == 0, "reasons": reasons, "n_rows": int(len(df))}


def _blank(value: Any) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null"}


def evaluate_acceptance_rule(
    metrics_model: Dict[str, Any],
    metrics_baseline: Dict[str, Any],
    quality_passed: bool,
    forecast_series: pd.Series,
    config: Dict[str, Any],
    estimates_df: Optional[pd.DataFrame] = None,
    required_series: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Aceptación conjunta: QC, integridad completa, dominio y métricas admisibles."""
    reasons: List[str] = []
    thr = config.get("quality_thresholds", {}).get("metrics_acceptance", {})
    max_mae = float(thr.get("max_mae_tolerance", 150000.0))
    use_rmse = bool(thr.get("enforce_rmse_tolerance", True))
    max_rmse = thr.get("max_rmse_tolerance")
    permit_neg_eval = bool(thr.get("permit_negative_forecasts_in_evaluation", True))
    require_better = bool(thr.get("require_better_than_baseline", False))

    if not quality_passed:
        reasons.append("Fallaron controles de calidad de datos críticos.")

    if forecast_series.isna().any() or np.isinf(forecast_series.to_numpy(dtype=float, na_value=np.nan)).any():
        reasons.append("Las estimaciones del modelo contienen nulos o no finitos.")

    # Negativos en evaluación: se documentan; no se recortan silenciosamente.
    neg_eval = int((forecast_series < 0).sum())
    if neg_eval and not permit_neg_eval:
        reasons.append(f"Evaluación con {neg_eval} predicciones negativas no permitidas por configuración.")

    n = int(metrics_model.get("n", 0) or 0)
    if n == 0:
        reasons.append("No hay meses evaluables (N=0); no se inventan métricas.")
    else:
        mae_val = metrics_model.get("mae", float("inf"))
        if not np.isfinite(mae_val) or float(mae_val) > max_mae:
            reasons.append(
                f"MAE ({mae_val}) excede la tolerancia máxima admisible ({max_mae})."
            )
        if use_rmse and max_rmse is not None:
            rmse_val = metrics_model.get("rmse", float("inf"))
            if not np.isfinite(rmse_val) or float(rmse_val) > float(max_rmse):
                reasons.append(
                    f"RMSE ({rmse_val}) excede la tolerancia configurada ({max_rmse})."
                )

    mae_base = metrics_baseline.get("mae", float("inf"))
    mae_val = metrics_model.get("mae", float("inf"))
    beats_baseline = bool(
        np.isfinite(mae_val) and np.isfinite(mae_base) and float(mae_val) <= float(mae_base)
    )
    if require_better and not beats_baseline:
        reasons.append(
            f"El modelo no supera al baseline (MAE modelo {mae_val} > baseline {mae_base})."
        )

    frame_check = {"ok": True, "reasons": []}
    if estimates_df is not None:
        # Para aceptar publicación: dominio no negativo en el frame candidato ya recortado
        frame_check = validate_estimates_frame(
            estimates_df,
            required_series=required_series or [],
            require_non_negative=True,
            require_approved_state=False,
        )
        if not frame_check["ok"]:
            reasons.extend([f"Integridad de salida: {r}" for r in frame_check["reasons"]])

    is_accepted = len(reasons) == 0
    return {
        "is_accepted": is_accepted,
        "reasons": reasons,
        "metrics_model": metrics_model,
        "metrics_baseline": metrics_baseline,
        "beats_baseline": beats_baseline,
        "max_mae_threshold": max_mae,
        "max_rmse_threshold": float(max_rmse) if max_rmse is not None else None,
        "negative_predictions_in_eval": neg_eval,
        "frame_validation": frame_check,
        "note": (
            "No es obligatorio superar el baseline; beats_baseline queda documentado. "
            "Umbral MAE inicial 150000 según configuración, sin ajuste post-hoc."
        ),
    }


def apply_domain_non_negative(series: pd.Series) -> pd.Series:
    """Política de dominio para publicación: viajeros ≥ 0."""
    return series.clip(lower=0.0)
