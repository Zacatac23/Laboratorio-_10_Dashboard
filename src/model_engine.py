"""Módulo de Modelado, Cálculo de Factores de Reparto y Evaluación Temporal (Laboratorio 11).
Respeta estrictamente el orden temporal (sin data leakage del futuro).
"""
import math
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def calculate_repartition_factors(df_train: pd.DataFrame, target_series: str = 'Total') -> Dict[str, float]:
    """Calcula el factor de reparto histórico para cada serie secundaria con respecto al Total.
    Fórmula:
        f_i = sum(viajeros_i, t in Train) / sum(viajeros_Total, t in Train)
    Se calcula EXCLUSIVAMENTE sobre el período de ajuste (Train) para no contaminar la evaluación.
    """
    totales_por_serie = df_train.groupby('serie')['viajeros'].sum()
    total_viajeros = totales_por_serie.get(target_series, 0.0)
    
    if total_viajeros <= 0:
        raise ValueError(f"Total de viajeros en período de entrenamiento es {total_viajeros}; denominador inválido.")
        
    factors = {}
    for serie, suma in totales_por_serie.items():
        factors[serie] = float(suma / total_viajeros)
        
    return factors


def fit_and_predict_seasonal_naive(train_series: pd.Series, eval_dates: pd.DatetimeIndex, lag: int = 12) -> pd.Series:
    """Baseline 1: Seasonal Naive.
    y_hat_t = y_(t - 12) si t - 12 está disponible; de lo contrario último valor conocido.
    """
    history = train_series.copy()
    predictions = []
    
    for dt in eval_dates:
        target_lag_date = dt - pd.DateOffset(months=lag)
        if target_lag_date in history.index:
            val = history.loc[target_lag_date]
        else:
            val = history.iloc[-1]
        predictions.append(val)
        # Modo out-of-sample estricto: añadimos la predicción para recursión si horizonte > lag
        history.loc[dt] = val
        
    return pd.Series(predictions, index=eval_dates)


def fit_and_predict_historical_mean(train_series: pd.Series, eval_dates: pd.DatetimeIndex) -> pd.Series:
    """Baseline 2: Promedio histórico mensual por mes calendario (1 al 12).
    Calculado únicamente con los datos del período de ajuste.
    """
    monthly_means = train_series.groupby(train_series.index.month).mean().to_dict()
    predictions = [monthly_means.get(dt.month, train_series.mean()) for dt in eval_dates]
    return pd.Series(predictions, index=eval_dates)


def fit_and_predict_holt_winters(train_series: pd.Series, eval_dates: pd.DatetimeIndex,
                                seasonal_periods: int = 12,
                                trend: str = "add",
                                seasonal: str = "add") -> Tuple[pd.Series, Any]:
    """Modelo Principal: Suavizamiento Exponencial Holt-Winters aditivo.
    Ajustado sobre la serie mensual regular en el período de ajuste.
    """
    ts = train_series.asfreq('MS')
    model = ExponentialSmoothing(
        ts,
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_periods,
        initialization_method="estimated"
    )
    fitted = model.fit(optimized=True)
    forecast = fitted.forecast(steps=len(eval_dates))
    forecast.index = eval_dates
    # Restricción de dominio físico: viajeros no pueden ser negativos
    forecast = forecast.clip(lower=0.0)
    return forecast, fitted


def compute_metrics(y_true: pd.Series, y_pred: pd.Series, epsilon: float = 1.0) -> Dict[str, float]:
    """Calcula métricas formales de desempeño: MAE, RMSE y MAPE seguro.
    Para MAPE, ante valores observados iguales o cercanos a cero, se aplica:
        APE = |y - y_hat| / (|y| + epsilon)
    garantizando estabilidad numérica y evitando denominadores iguales a cero.
    """
    common_idx = y_true.dropna().index.intersection(y_pred.dropna().index)
    if len(common_idx) == 0:
        return {"mae": float("nan"), "rmse": float("nan"), "mape": float("nan"), "n": 0}
        
    yt = y_true.loc[common_idx].to_numpy(dtype=float)
    yp = y_pred.loc[common_idx].to_numpy(dtype=float)
    errors = yt - yp
    
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    # MAPE protegido con epsilon contra ceros
    mape = float(np.mean(np.abs(errors) / (np.abs(yt) + epsilon)) * 100.0)
    
    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "mape": round(mape, 2),
        "n": len(common_idx)
    }


def evaluate_acceptance_rule(metrics_model: Dict[str, float],
                             metrics_baseline: Dict[str, float],
                             quality_passed: bool,
                             forecast_series: pd.Series,
                             config: Dict[str, Any]) -> Dict[str, Any]:
    """Evalúa la regla de aceptación formal para autorizar o rechazar la publicación (Ejercicio 5.4).
    Criterios verificables:
    1. Calidad: 100% de controles de calidad críticos aprobados.
    2. Integridad: 0 valores no finitos o nulos en las estimaciones.
    3. Físicamente válido: 0 valores negativos si permit_negative_forecasts es False.
    4. Desempeño: MAE <= max_mae_tolerance.
    5. Evaluación comparativa documentada frente a baseline.
    """
    reasons = []
    thresholds = config.get('quality_thresholds', {}).get('metrics_acceptance', {})
    max_mae = thresholds.get('max_mae_tolerance', 150000.0)
    permit_neg = thresholds.get('permit_negative_forecasts', False)
    require_better = thresholds.get('require_better_than_baseline', False)
    
    # 1. Controles críticos
    if not quality_passed:
        reasons.append("Fallaron controles de calidad de datos críticos.")
        
    # 2. Integridad
    if forecast_series.isna().any() or np.isinf(forecast_series).any():
        reasons.append("Las estimaciones contienen valores nulos o no finitos.")
        
    # 3. Negativos
    if not permit_neg and (forecast_series < 0).any():
        neg_count = int((forecast_series < 0).sum())
        reasons.append(f"Se generaron {neg_count} estimaciones con valores negativos no permitidos.")
        
    # 4. Umbral de tolerancia MAE
    mae_val = metrics_model.get('mae', float('inf'))
    if mae_val > max_mae:
        reasons.append(f"MAE ({mae_val}) excede la tolerancia máxima admisible ({max_mae}).")
        
    # 5. Desempeño vs Baseline
    mae_base = metrics_baseline.get('mae', float('inf'))
    beats_baseline = mae_val <= mae_base
    if require_better and not beats_baseline:
        reasons.append(f"El modelo no supera al baseline de referencia (Modelo MAE: {mae_val} > Baseline MAE: {mae_base}).")
        
    is_accepted = len(reasons) == 0
    
    return {
        "is_accepted": is_accepted,
        "reasons": reasons,
        "metrics_model": metrics_model,
        "metrics_baseline": metrics_baseline,
        "beats_baseline": beats_baseline,
        "max_mae_threshold": max_mae
    }

