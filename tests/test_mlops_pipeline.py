"""Pruebas de modelado, aceptación y publicación atómica (Laboratorio 11)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from src.model_engine import (
    apply_domain_non_negative,
    build_evaluation_mask,
    calculate_repartition_factors,
    compute_metrics,
    evaluate_acceptance_rule,
    fit_and_predict_historical_mean,
    fit_and_predict_holt_winters,
    fit_and_predict_seasonal_naive,
    validate_estimates_frame,
)
from src.monitoring import file_sha256, publish_approved_atomically


class TestMLOpsPipeline(unittest.TestCase):
    def setUp(self):
        train_dates = pd.date_range("2015-01-01", "2018-12-01", freq="MS")
        self.s_train = pd.Series([100.0 + (dt.month * 10) for dt in train_dates], index=train_dates)
        self.eval_dates = pd.date_range("2019-01-01", "2019-12-01", freq="MS")
        self.s_eval_true = pd.Series([105.0 + (dt.month * 10) for dt in self.eval_dates], index=self.eval_dates)

    def test_repartition_factors_deterministic(self):
        df_train = pd.DataFrame(
            {
                "serie": ["Total", "Via_Aérea", "Via_Terrestre"] * 2,
                "viajeros": [100.0, 60.0, 40.0, 100.0, 60.0, 40.0],
            }
        )
        factors = calculate_repartition_factors(
            df_train, target_series="Total", required_series=["Via_Aérea", "Via_Terrestre"]
        )
        self.assertAlmostEqual(factors["Total"], 1.0)
        self.assertAlmostEqual(factors["Via_Aérea"], 0.6)

    def test_repartition_sin_fallback_silencioso(self):
        df_train = pd.DataFrame({"serie": ["Total", "Via_Aérea"], "viajeros": [100.0, 60.0]})
        with self.assertRaises(ValueError):
            calculate_repartition_factors(
                df_train, target_series="Total", required_series=["Via_Aérea", "Via_Terrestre"]
            )

    def test_repartition_denominador_cero(self):
        df_train = pd.DataFrame({"serie": ["Total", "Via_Aérea"], "viajeros": [0.0, 0.0]})
        with self.assertRaises(ValueError):
            calculate_repartition_factors(df_train, target_series="Total")

    def test_reproducibility_runs_identical(self):
        pred1 = fit_and_predict_historical_mean(self.s_train, self.eval_dates)
        pred2 = fit_and_predict_historical_mean(self.s_train, self.eval_dates)
        np.testing.assert_array_almost_equal(pred1.values, pred2.values, decimal=6)

    def test_seasonal_naive_sin_fuga_futuro(self):
        pred = fit_and_predict_seasonal_naive(self.s_train, self.eval_dates, lag=12)
        # Primer mes eval usa train (2018-01), no un valor futuro real
        expected = float(self.s_train.loc[pd.Timestamp("2018-01-01")])
        self.assertAlmostEqual(float(pred.iloc[0]), expected)

    def test_holt_winters_no_recorta_en_evaluacion(self):
        # Serie decreciente fuerte para provocar negativos posibles
        idx = pd.date_range("2010-01-01", periods=48, freq="MS")
        s = pd.Series(np.linspace(500, 10, len(idx)), index=idx)
        eval_idx = pd.date_range("2014-01-01", periods=12, freq="MS")
        pred, _ = fit_and_predict_holt_winters(s, eval_idx, clip_negative=False)
        # La política de dominio se aplica aparte
        clipped = apply_domain_non_negative(pred)
        self.assertTrue((clipped >= 0).all())

    def test_compute_metrics_ape_eps_no_es_mape_clasico(self):
        y_true = pd.Series([0.0, 10.0, 20.0], index=self.eval_dates[:3])
        y_pred = pd.Series([2.0, 12.0, 22.0], index=self.eval_dates[:3])
        m = compute_metrics(y_true, y_pred, epsilon=1.0)
        self.assertAlmostEqual(m["mae"], 2.0)
        self.assertIn("ape_eps_pct", m)
        self.assertIn("no es MAPE convencional", m["mape_note"])
        self.assertTrue(np.isfinite(m["ape_eps_pct"]))

    def test_compute_metrics_n_cero_sin_ceros_inventados(self):
        y_true = pd.Series([np.nan, np.nan], index=self.eval_dates[:2])
        y_pred = pd.Series([1.0, 2.0], index=self.eval_dates[:2])
        m = compute_metrics(y_true, y_pred)
        self.assertEqual(m["n"], 0)
        self.assertTrue(np.isnan(m["mae"]))
        self.assertTrue(np.isnan(m["rmse"]))

    def test_exclusion_fundamentada_de_meses(self):
        y_true = self.s_eval_true.copy()
        idx, info = build_evaluation_mask(
            y_true,
            excluded_periods=[
                {
                    "start": "2019-01-01",
                    "end": "2019-02-01",
                    "reason": "prueba de exclusión metodológica",
                }
            ],
        )
        self.assertEqual(info["n_evaluable"], 10)
        self.assertEqual(info["excluded_months"], ["2019-01", "2019-02"])
        m = compute_metrics(y_true, y_true, evaluable_index=idx)
        self.assertEqual(m["n"], 10)

    def test_no_excluye_mes_comparable_automaticamente(self):
        y_true = self.s_eval_true.copy()
        idx, info = build_evaluation_mask(y_true, excluded_periods=[])
        self.assertEqual(info["n_evaluable"], 12)
        self.assertEqual(info["excluded_months"], [])

    def test_acceptance_rule_rejection_on_high_mae(self):
        metrics_bad = {"mae": 500.0, "rmse": 600.0, "n": 12}
        metrics_base = {"mae": 100.0, "rmse": 120.0, "n": 12}
        config = {
            "quality_thresholds": {
                "metrics_acceptance": {
                    "max_mae_tolerance": 200.0,
                    "enforce_rmse_tolerance": False,
                    "permit_negative_forecasts_in_evaluation": True,
                }
            }
        }
        res = evaluate_acceptance_rule(
            metrics_model=metrics_bad,
            metrics_baseline=metrics_base,
            quality_passed=True,
            forecast_series=pd.Series([100.0] * 12),
            config=config,
        )
        self.assertFalse(res["is_accepted"])
        self.assertTrue(any("excede la tolerancia" in r for r in res["reasons"]))

    def test_acceptance_documenta_baseline_sin_exigirlo(self):
        config = {
            "quality_thresholds": {
                "metrics_acceptance": {
                    "max_mae_tolerance": 1000.0,
                    "enforce_rmse_tolerance": False,
                    "require_better_than_baseline": False,
                }
            }
        }
        res = evaluate_acceptance_rule(
            metrics_model={"mae": 50.0, "rmse": 60.0, "n": 12},
            metrics_baseline={"mae": 10.0, "rmse": 12.0, "n": 12},
            quality_passed=True,
            forecast_series=pd.Series([1.0] * 12),
            config=config,
        )
        self.assertTrue(res["is_accepted"])
        self.assertFalse(res["beats_baseline"])

    def test_validate_estimates_requiere_series_secundarias(self):
        df = pd.DataFrame(
            [
                {
                    "destino": "Guatemala",
                    "serie": "Total",
                    "modelo": "X",
                    "fecha": "2021-04-01",
                    "prediccion": 1.0,
                    "unidad_medida": "viajeros/mes",
                    "run_id": "r1",
                    "fecha_generacion": "2026-01-01 00:00:00",
                    "version_procedimiento": "1.0.0",
                    "estado_aprobacion": "APROBADO",
                }
            ]
        )
        out = validate_estimates_frame(df, required_series=["Total", "Via_Aérea"])
        self.assertFalse(out["ok"])

    def test_publicacion_atomica_crea_respaldo(self):
        with tempfile.TemporaryDirectory() as tmp:
            approved = Path(tmp) / "estimaciones_aprobadas.csv"
            backup_dir = Path(tmp) / "backup"
            prev = pd.DataFrame(
                {
                    "destino": ["Guatemala"],
                    "serie": ["Total"],
                    "modelo": ["prev"],
                    "fecha": ["2021-04-01"],
                    "prediccion": [1.0],
                    "unidad_medida": ["viajeros/mes"],
                    "run_id": ["old"],
                    "fecha_generacion": ["2020-01-01 00:00:00"],
                    "version_procedimiento": ["0.9.0"],
                    "estado_aprobacion": ["APROBADO"],
                }
            )
            prev.to_csv(approved, index=False)
            prev_hash = file_sha256(str(approved))
            nuevo = prev.copy()
            nuevo["prediccion"] = [99.0]
            nuevo["run_id"] = ["new"]
            result = publish_approved_atomically(
                nuevo, str(approved), str(backup_dir), run_id="run_test_pub"
            )
            self.assertTrue(result["published"])
            self.assertIsNotNone(result["backup_file"])
            self.assertTrue(Path(result["backup_file"]).is_file())
            self.assertEqual(file_sha256(str(approved)), result["new_sha256"])
            self.assertNotEqual(prev_hash, result["new_sha256"])
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_fallo_escritura_preserva_hash_aprobado(self):
        with tempfile.TemporaryDirectory() as tmp:
            approved = Path(tmp) / "estimaciones_aprobadas.csv"
            backup_dir = Path(tmp) / "backup"
            prev = pd.DataFrame(
                {
                    "destino": ["Guatemala"],
                    "serie": ["Total"],
                    "modelo": ["prev"],
                    "fecha": ["2021-04-01"],
                    "prediccion": [1.0],
                    "unidad_medida": ["viajeros/mes"],
                    "run_id": ["old"],
                    "fecha_generacion": ["2020-01-01 00:00:00"],
                    "version_procedimiento": ["0.9.0"],
                    "estado_aprobacion": ["APROBADO"],
                }
            )
            prev.to_csv(approved, index=False)
            prev_hash = file_sha256(str(approved))
            nuevo = prev.copy()
            nuevo["prediccion"] = [42.0]

            real_replace = os.replace

            def boom(src, dst):
                raise OSError("fallo simulado al reemplazar")

            with mock.patch("src.monitoring.os.replace", side_effect=boom):
                with self.assertRaises(OSError):
                    publish_approved_atomically(
                        nuevo, str(approved), str(backup_dir), run_id="run_fail"
                    )
            self.assertEqual(file_sha256(str(approved)), prev_hash)
            # No deben quedar temporales
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_cli_requiere_publish_o_no_publish(self):
        from src.pipeline import main

        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
