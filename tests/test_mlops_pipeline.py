"""Pruebas Unitarias del Pipeline MLOps y Reproducibilidad Numérica (Laboratorio 11 - Ejercicios 2, 4 y 5)."""
import unittest
import pandas as pd
import numpy as np
from src.model_engine import (
    calculate_repartition_factors,
    fit_and_predict_seasonal_naive,
    fit_and_predict_historical_mean,
    compute_metrics,
    evaluate_acceptance_rule
)


class TestMLOpsPipeline(unittest.TestCase):
    def setUp(self):
        # Datos de entrenamiento controlados
        train_dates = pd.date_range("2015-01-01", "2018-12-01", freq="MS")
        self.s_train = pd.Series([100.0 + (dt.month * 10) for dt in train_dates], index=train_dates)
        self.eval_dates = pd.date_range("2019-01-01", "2019-12-01", freq="MS")
        self.s_eval_true = pd.Series([105.0 + (dt.month * 10) for dt in self.eval_dates], index=self.eval_dates)

    def test_repartition_factors_deterministic(self):
        df_train = pd.DataFrame({
            "serie": ["Total", "Via_Aérea", "Via_Terrestre"] * 2,
            "viajeros": [100.0, 60.0, 40.0, 100.0, 60.0, 40.0]
        })
        factors = calculate_repartition_factors(df_train, target_series="Total")
        self.assertAlmostEqual(factors["Total"], 1.0)
        self.assertAlmostEqual(factors["Via_Aérea"], 0.6)
        self.assertAlmostEqual(factors["Via_Terrestre"], 0.4)

    def test_reproducibility_runs_identical(self):
        """Comprueba que dos llamadas independientes con la misma configuración producen resultados idénticos (Ej. 4.2)."""
        pred1 = fit_and_predict_historical_mean(self.s_train, self.eval_dates)
        pred2 = fit_and_predict_historical_mean(self.s_train, self.eval_dates)
        np.testing.assert_array_almost_equal(pred1.values, pred2.values, decimal=6)

    def test_compute_metrics_handles_zeros(self):
        """Comprueba que compute_metrics calcula MAE, RMSE y MAPE con protección contra ceros (Ej. 5.2)."""
        y_true = pd.Series([0.0, 10.0, 20.0], index=self.eval_dates[:3])
        y_pred = pd.Series([2.0, 12.0, 22.0], index=self.eval_dates[:3])
        m = compute_metrics(y_true, y_pred, epsilon=1.0)
        self.assertAlmostEqual(m["mae"], 2.0)
        self.assertAlmostEqual(m["rmse"], 2.0)
        self.assertTrue(np.isfinite(m["mape"]))

    def test_acceptance_rule_rejection_on_high_mae(self):
        """Comprueba que la regla de aceptación rechaza candidatos que superan el umbral (Ej. 5.4)."""
        metrics_bad = {"mae": 500.0, "rmse": 600.0, "n": 12}
        metrics_base = {"mae": 100.0, "rmse": 120.0, "n": 12}
        config = {
            "quality_thresholds": {
                "metrics_acceptance": {
                    "max_mae_tolerance": 200.0,
                    "permit_negative_forecasts": False
                }
            }
        }
        res = evaluate_acceptance_rule(
            metrics_model=metrics_bad,
            metrics_baseline=metrics_base,
            quality_passed=True,
            forecast_series=pd.Series([100.0] * 12),
            config=config
        )
        self.assertFalse(res["is_accepted"])
        self.assertTrue(any("excede la tolerancia" in r for r in res["reasons"]))


if __name__ == "__main__":
    unittest.main()

