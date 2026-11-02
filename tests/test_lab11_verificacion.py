"""Pruebas complementarias de la verificación final del Laboratorio 11.

Cubren requisitos que no tenían una prueba explícita:
- El modelo activo, los baselines y los factores no usan meses del periodo evaluado (sin fuga).
- MAE/RMSE contra un cálculo manual y baseline evaluado exactamente en los mismos meses.
- El modo dry-run (--no-publish) no altera la versión aprobada vigente.
- Fuentes múltiples: las tres fuentes se registran con hash y las de contexto pasan por QC.

Todo corre sobre datos sintéticos en carpetas temporales (PipelineSandbox); no se tocan
data/, reports/, logs/ ni el almacén MLflow del repositorio.
"""
import os
import shutil
import unittest

import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from tests.test_mlops_integracion import EnvIsolation, PipelineSandbox, synthetic_series  # noqa: E402
from src.model_engine import (  # noqa: E402
    build_evaluation_mask,
    calculate_repartition_factors,
    compute_metrics,
    fit_and_predict_historical_mean,
    fit_and_predict_holt_winters,
    fit_and_predict_seasonal_naive,
)
from src.monitoring import file_sha256  # noqa: E402

TRAIN_END = pd.Timestamp("2018-12-01")


def _split(df):
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    train = df[df["fecha"] <= TRAIN_END]
    evalu = df[df["fecha"] > TRAIN_END]
    s_train = train[train["serie"] == "Total"].set_index("fecha")["viajeros"].sort_index()
    s_eval = evalu[evalu["serie"] == "Total"].set_index("fecha")["viajeros"].sort_index()
    return train, s_train, s_eval


class SinFugaTemporal(EnvIsolation):
    """Alterar por completo los meses evaluados no debe cambiar ningún parámetro ni predicción."""

    def test_parametros_y_predicciones_no_dependen_de_meses_evaluados(self):
        base = synthetic_series()
        alterada = base.copy()
        fechas = pd.to_datetime(alterada["fecha"])
        # Multiplica por 10 y suma ruido SOLO en el periodo evaluado (2019-2020)
        rng = np.random.default_rng(0)
        mask = fechas > TRAIN_END
        alterada.loc[mask, "viajeros"] = alterada.loc[mask, "viajeros"] * 10 + rng.uniform(0, 5000, mask.sum())

        tr_a, s_tr_a, s_ev_a = _split(base)
        tr_b, s_tr_b, s_ev_b = _split(alterada)
        self.assertFalse(np.allclose(s_ev_a.to_numpy(), s_ev_b.to_numpy()), "la alteración debe ser real")
        eval_dates = s_ev_a.index

        pd.testing.assert_series_equal(fit_and_predict_historical_mean(s_tr_a, eval_dates),
                                       fit_and_predict_historical_mean(s_tr_b, eval_dates))
        pd.testing.assert_series_equal(fit_and_predict_seasonal_naive(s_tr_a, eval_dates),
                                       fit_and_predict_seasonal_naive(s_tr_b, eval_dates))
        hw_a, _ = fit_and_predict_holt_winters(s_tr_a, eval_dates)
        hw_b, _ = fit_and_predict_holt_winters(s_tr_b, eval_dates)
        np.testing.assert_allclose(hw_a.to_numpy(), hw_b.to_numpy(), atol=1e-9, rtol=0)
        secundarias = [s for s in base["serie"].unique() if s != "Total"]
        self.assertEqual(calculate_repartition_factors(tr_a, "Total", secundarias),
                         calculate_repartition_factors(tr_b, "Total", secundarias))

    def test_pipeline_completo_sin_fuga(self):
        """Mismo resultado de estimación con meses evaluados alterados; solo cambian las métricas."""
        box = PipelineSandbox()
        try:
            r1 = box.run(publish=False)
            alterada = synthetic_series()
            mask = pd.to_datetime(alterada["fecha"]) > TRAIN_END
            alterada.loc[mask, "viajeros"] *= 3
            box.write_series(alterada)
            r2 = box.run(publish=False)
            self.assertEqual(r1["status"], r2["status"])
            reports = sorted((box.tmp / "reports").glob("estimaciones_candidatas_*.csv"))
            self.assertEqual(len(reports), 2)
            a, b = (pd.read_csv(p) for p in reports)
            np.testing.assert_allclose(a["prediccion"].to_numpy(), b["prediccion"].to_numpy(), atol=1e-6, rtol=0)
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)


class MetricasYBaseline(EnvIsolation):
    def test_mae_rmse_contra_calculo_manual(self):
        idx = pd.date_range("2020-01-01", periods=3, freq="MS")
        y = pd.Series([10.0, 20.0, 30.0], index=idx)
        p = pd.Series([12.0, 18.0, 33.0], index=idx)
        m = compute_metrics(y, p)
        self.assertEqual(m["n"], 3)
        self.assertAlmostEqual(m["mae"], round(7 / 3, 2))
        self.assertAlmostEqual(m["rmse"], round(float(np.sqrt(17 / 3)), 2))

    def test_meses_sin_observacion_no_se_evaluan(self):
        idx = pd.date_range("2020-01-01", periods=4, freq="MS")
        y = pd.Series([10.0, np.nan, 30.0, np.inf], index=idx)
        p = pd.Series([12.0, 999.0, 33.0, 5.0], index=idx)
        ev, info = build_evaluation_mask(y)
        m = compute_metrics(y, p, evaluable_index=ev)
        self.assertEqual(m["n"], 2)
        self.assertEqual(info["n_missing_or_nonfinite"], 2)
        self.assertAlmostEqual(m["mae"], 2.5)

    def test_baseline_y_modelo_activo_en_los_mismos_meses(self):
        box = PipelineSandbox()
        try:
            res = box.run(publish=False)
            run = MlflowClient(box.tracking_uri).get_run(res["mlflow_run_id"])
            mt = run.data.metrics
            n_eval = mt["eval.n_evaluable"]
            self.assertGreater(n_eval, 0)
            for pref in ("active", "snaive", "hmean", "hw"):
                self.assertEqual(mt[f"eval.{pref}.n"], n_eval, pref)
            self.assertAlmostEqual(mt["eval.active_minus_baseline.mae"],
                                   mt["eval.active.mae"] - mt["eval.snaive.mae"], places=6)
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)


class DryRun(EnvIsolation):
    def test_no_publish_no_altera_version_aprobada(self):
        box = PipelineSandbox()
        try:
            r_pub = box.run(publish=True)
            self.assertEqual(r_pub["status"], "APROBADO_PUBLICADO")
            sha = file_sha256(str(box.approved))
            manifest = box.data / "estimaciones_aprobadas.manifest.json"
            sha_m = file_sha256(str(manifest))
            backups_antes = sorted(os.listdir(box.data / "backup_aprobadas")) if (box.data / "backup_aprobadas").exists() else []
            r_dry = box.run(publish=False)
            self.assertEqual(r_dry["status"], "APROBADO_NO_PUBLICADO")
            self.assertEqual(file_sha256(str(box.approved)), sha)
            self.assertEqual(file_sha256(str(manifest)), sha_m)
            backups_despues = sorted(os.listdir(box.data / "backup_aprobadas")) if (box.data / "backup_aprobadas").exists() else []
            self.assertEqual(backups_antes, backups_despues)
            run = MlflowClient(box.tracking_uri).get_run(r_dry["mlflow_run_id"])
            self.assertEqual(run.data.tags["publication.status"], "NO_PUBLICADO")
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)


class FuentesMultiples(EnvIsolation):
    def _contexto(self, box, duplicar_pais=False):
        fechas = pd.date_range("2015-01-01", "2020-12-01", freq="MS").strftime("%Y-%m-%d")
        pais = pd.DataFrame([{"fecha": f, "pais": p, "region": "R", "viajeros": 10.0}
                             for f in fechas for p in ("A", "B")])
        if duplicar_pais:
            pais = pd.concat([pais, pais.iloc[[0]]], ignore_index=True)
        via = pd.DataFrame([{"fecha": f, "via": v, "frontera": "F1", "viajeros": 5.0}
                            for f in fechas for v in ("Aérea", "Terrestre")])
        pais.to_csv(box.data / "pais_mensual.csv", index=False)
        via.to_csv(box.data / "via_frontera.csv", index=False)

    def test_tres_fuentes_registradas_con_hash_y_qc_de_contexto(self):
        box = PipelineSandbox()
        try:
            self._contexto(box)
            res = box.run(publish=False)
            params = MlflowClient(box.tracking_uri).get_run(res["mlflow_run_id"]).data.params
            for clave, archivo in (("series", "series_mensuales.csv"), ("pais", "pais_mensual.csv"),
                                   ("via", "via_frontera.csv")):
                self.assertEqual(params[f"source.{clave}.sha256"], file_sha256(str(box.data / archivo)), clave)
            import json
            qc = json.loads(next((box.tmp / "reports").glob("quality_report_*.json")).read_text(encoding="utf-8"))
            texto = json.dumps(qc, ensure_ascii=False)
            self.assertIn("pais_mensual.csv", texto)
            self.assertIn("via_frontera.csv", texto)
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)

    def test_duplicado_en_fuente_de_contexto_advierte_sin_bloquear(self):
        box = PipelineSandbox()
        try:
            self._contexto(box, duplicar_pais=True)
            res = box.run(publish=False)
            self.assertEqual(res["status"], "APROBADO_NO_PUBLICADO")
            import json
            qc = json.loads(next((box.tmp / "reports").glob("quality_report_*.json")).read_text(encoding="utf-8"))
            estados = [c for c in qc["checks"] if "pais_mensual" in json.dumps(c, ensure_ascii=False)
                       and c["status"] == "WARNING"]
            self.assertTrue(estados, "el duplicado en contexto debe generar WARNING")
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)


class AislamientoTrackingURI(EnvIsolation):
    """Regresión: una corrida no debe dejar MLFLOW_TRACKING_URI fijada para la siguiente del mismo proceso."""

    def test_segunda_corrida_respeta_su_config_y_bloquea_si_mlflow_cae(self):
        from src.tracking import TraceabilityError
        box = PipelineSandbox()
        try:
            r1 = box.run(publish=True)
            self.assertEqual(r1["status"], "APROBADO_PUBLICADO")
            self.assertNotIn("MLFLOW_TRACKING_URI", os.environ)
            self.assertNotIn("MLFLOW_EXPERIMENT_ID", os.environ)
            sha = file_sha256(str(box.approved))
            with self.assertRaises(TraceabilityError):
                box.run(publish=True, **{"mlflow.tracking_uri": "http://127.0.0.1:9",
                                         "mlflow.connect_retries": 1, "mlflow.connect_retry_delay_seconds": 0})
            self.assertEqual(file_sha256(str(box.approved)), sha)
        finally:
            shutil.rmtree(box.tmp, ignore_errors=True)


class ComposePuertoMLflow(unittest.TestCase):
    def test_allowed_hosts_incluye_puerto_publicado_configurable(self):
        from pathlib import Path
        texto = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
        linea = next(l for l in texto.splitlines() if "--allowed-hosts=" in l)
        self.assertIn("127.0.0.1:${MLFLOW_PORT:-5000}", linea)
        self.assertIn("localhost:${MLFLOW_PORT:-5000}", linea)
        self.assertIn("mlflow:5000", linea)


if __name__ == "__main__":
    unittest.main()
