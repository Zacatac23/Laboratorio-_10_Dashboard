"""Integración MLflow, monitoreo, restauración, tablero y Docker (Laboratorio 11).

Todas las pruebas usan datos sintéticos o copias en carpetas temporales; no
modifican data/, reports/, logs/ ni el almacén MLflow del repositorio.
La prueba contra Docker Compose solo corre con RUN_DOCKER_TESTS=1.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from mlflow.tracking import MlflowClient  # noqa: E402

from data_logic import cargar_version_aprobada  # noqa: E402
from src.monitoring import (  # noqa: E402
    file_sha256,
    manifest_path_for,
    monitor_freshness,
    monitor_predictive_error,
    monitor_quality,
    monitor_results,
    publish_approved_atomically,
    run_monitoring,
    source_profile,
)
from src.pipeline import TourismMLOpsPipeline, main as pipeline_main  # noqa: E402
from src.quality_checks import QualityControlError  # noqa: E402
from src.restore_version import (  # noqa: E402
    RestoreError,
    list_backups,
    main as restore_main,
    restore_backup,
)
from src.tracking import TraceabilityError  # noqa: E402

SERIES_SHARES = {
    "Via_Aérea": 0.50, "Via_Terrestre": 0.45, "Via_Marítima": 0.05,
    "Tipo_Turista": 0.60, "Tipo_Excursionista": 0.25, "Tipo_Cruceristas": 0.05, "Tipo_Viajero": 0.10,
}
REQUIRED = ["Total"] + list(SERIES_SHARES)


def synthetic_series(start="2015-01-01", end="2020-12-01", scale=1.0) -> pd.DataFrame:
    fechas = pd.date_range(start, end, freq="MS")
    total = scale * (1000 + 300 * np.sin(2 * np.pi * fechas.month / 12) + np.arange(len(fechas)))
    rows = [{"serie": "Total", "fecha": f.strftime("%Y-%m-%d"), "viajeros": round(v, 2)} for f, v in zip(fechas, total)]
    for serie, share in SERIES_SHARES.items():
        rows += [{"serie": serie, "fecha": f.strftime("%Y-%m-%d"), "viajeros": round(v * share, 2)}
                 for f, v in zip(fechas, total)]
    return pd.DataFrame(rows)


class PipelineSandbox:
    """Carpeta temporal con datos, configuración y tracking MLflow propios."""

    def __init__(self, tracking_uri=None):
        self.tmp = Path(tempfile.mkdtemp(prefix="lab11_mlops_"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        cfg = yaml.safe_load((ROOT / "config" / "pipeline_config.yaml").read_text(encoding="utf-8"))
        cfg["paths"].update(
            raw_data_dir=str(self.data), output_dir=str(self.data),
            backup_dir=str(self.data / "backup_aprobadas"), reports_dir=str(self.tmp / "reports"),
            logs_dir=str(self.tmp / "logs"), publish_lock_file=str(self.tmp / "logs" / "publish.lock"),
        )
        cfg["temporal_split"].update(train_start="2015-01-01", train_end="2018-12-01",
                                     eval_start="2019-01-01", eval_end="2020-12-01",
                                     excluded_evaluation_periods=[])
        cfg["monitoring"]["expected_coverage_end"] = "2020-12-01"
        cfg["mlflow"].update(
            tracking_uri=tracking_uri or f"sqlite:///{(self.tmp / 'mlflow' / 'mlflow.db').as_posix()}",
            artifact_location=str(self.tmp / "mlflow" / "artifacts"),
            connect_retries=1, connect_retry_delay_seconds=0,
        )
        self.cfg = cfg
        self.write_series(synthetic_series())

    @property
    def approved(self) -> Path:
        return self.data / "estimaciones_aprobadas.csv"

    @property
    def tracking_uri(self) -> str:
        return self.cfg["mlflow"]["tracking_uri"]

    def write_series(self, df):
        df.to_csv(self.data / "series_mensuales.csv", index=False)

    def config_path(self, **overrides) -> str:
        cfg = json.loads(json.dumps(self.cfg))
        for dotted, value in overrides.items():
            node = cfg
            *parents, leaf = dotted.split(".")
            for key in parents:
                node = node[key]
            node[leaf] = value
        path = self.tmp / f"config_{len(list(self.tmp.glob('config_*.yaml')))}.yaml"
        path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        return str(path)

    def run(self, publish=True, **overrides):
        return TourismMLOpsPipeline(self.config_path(**overrides), publish=publish).run()

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def all_artifacts(client, run_id, path=None):
    out = []
    for item in client.list_artifacts(run_id, path):
        out.extend(all_artifacts(client, run_id, item.path) if item.is_dir else [item.path])
    return out


class EnvIsolation(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in ("MLFLOW_TRACKING_URI", "MLFLOW_CONNECT_RETRIES", "MLFLOW_CONNECT_DELAY", "GIT_COMMIT"):
            os.environ.pop(var, None)


# ---------------------------------------------------------------------------
class TrazabilidadMLflow(EnvIsolation):
    def setUp(self):
        super().setUp()
        self.box = PipelineSandbox()
        self.addCleanup(self.box.cleanup)

    def client(self):
        return MlflowClient(tracking_uri=self.box.tracking_uri)

    def test_corrida_aprobada_publicada_registra_trazabilidad_completa(self):
        result = self.box.run(publish=True)
        self.assertEqual(result["status"], "APROBADO_PUBLICADO")
        run = self.client().get_run(result["mlflow_run_id"])
        self.assertEqual(run.info.status, "FINISHED")
        tags, params, metrics = run.data.tags, run.data.params, run.data.metrics
        self.assertEqual(tags["pipeline.status"], "APROBADO_PUBLICADO")
        self.assertEqual(tags["publication.status"], "PUBLICADO")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        expected_commit = head.stdout.strip() if head.returncode == 0 else "NO_DISPONIBLE"
        self.assertEqual(tags["git.commit"], expected_commit)
        self.assertEqual(params["source.series.sha256"], file_sha256(str(self.box.data / "series_mensuales.csv")))
        self.assertRegex(params["config.sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(params["code.sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(params["split.train_end"], "2018-12-01")
        self.assertIn("factor_reparto.Via_Aérea", params)
        for key in ("eval.active.mae", "eval.active.rmse", "eval.snaive.mae", "acceptance.is_accepted"):
            self.assertIn(key, metrics)
        folders = {p.split("/")[0] for p in all_artifacts(self.client(), run.info.run_id)}
        self.assertTrue({"configuracion", "fuentes", "calidad", "modelo", "aceptacion", "estimaciones",
                         "monitoreo", "auditoria", "publicacion", "reproducibilidad"} <= folders)
        manifest = json.loads(Path(manifest_path_for(str(self.box.approved))).read_text(encoding="utf-8"))
        self.assertEqual(manifest["csv_sha256"], file_sha256(str(self.box.approved)))
        self.assertEqual(manifest["mlflow_run_id"], run.info.run_id)
        self.assertEqual(manifest["metricas"]["mae"], metrics["eval.active.mae"])
        self.assertEqual(params["publish.new_sha256"], manifest["csv_sha256"])
        # El candidato registrado es byte a byte el archivo publicado
        candidate = Path(result["audit_file"]).parents[1] / "reports" / f"estimaciones_candidatas_{result['run_id']}.csv"
        self.assertEqual(file_sha256(str(candidate)), file_sha256(str(self.box.approved)))

    def test_corrida_rechazada_registra_metricas_reales_sin_publicar(self):
        result = self.box.run(publish=True, **{"quality_thresholds.metrics_acceptance.max_mae_tolerance": 0.001})
        self.assertEqual(result["status"], "RECHAZADO")
        self.assertFalse(self.box.approved.exists())
        run = self.client().get_run(result["mlflow_run_id"])
        self.assertEqual(run.info.status, "FINISHED")
        self.assertEqual(run.data.tags["pipeline.status"], "RECHAZADO")
        self.assertEqual(run.data.tags["acceptance.decision"], "REJECTED")
        self.assertEqual(run.data.tags["publication.status"], "NO_PUBLICADO")
        self.assertGreater(run.data.metrics["eval.active.mae"], 0.001)
        self.assertNotIn("publicacion", {p.split("/")[0] for p in all_artifacts(self.client(), run.info.run_id)})

    def test_corrida_fallida_por_calidad_no_inventa_metricas(self):
        self.box.run(publish=True)
        sha_before = file_sha256(str(self.box.approved))
        bad = synthetic_series()
        bad.loc[0, "viajeros"] = -50
        self.box.write_series(bad)
        with self.assertRaises(QualityControlError):
            self.box.run(publish=True)
        self.assertEqual(file_sha256(str(self.box.approved)), sha_before)
        client = self.client()
        exp = client.get_experiment_by_name(self.box.cfg["mlflow"]["experiment_name"])
        failed = client.search_runs([exp.experiment_id], "tags.`pipeline.status` = 'FALLIDO_CALIDAD'")
        self.assertEqual(len(failed), 1)
        run = failed[0]
        self.assertEqual(run.info.status, "FAILED")
        self.assertFalse([k for k in run.data.metrics if k.startswith("eval.")])
        self.assertEqual(run.data.metrics["qc.critical_passed"], 0)
        self.assertEqual(run.data.tags["pipeline.failed_stage"], "Controles de calidad QC-A…F")
        arts = all_artifacts(client, run.info.run_id)
        self.assertTrue(any(a.startswith("fallo/error_") for a in arts))
        self.assertTrue(any(a.startswith("monitoreo/") for a in arts))
        self.assertTrue(any(a.startswith("calidad/") for a in arts))

    def test_mlflow_no_disponible_bloquea_publicacion(self):
        self.box.run(publish=True)
        sha_before = file_sha256(str(self.box.approved))
        os.environ["MLFLOW_TRACKING_URI"] = "http://127.0.0.1:9"
        os.environ["MLFLOW_CONNECT_RETRIES"] = "1"
        os.environ["MLFLOW_CONNECT_DELAY"] = "0"
        pipe = TourismMLOpsPipeline(self.box.config_path(), publish=True)
        with self.assertRaises(TraceabilityError):
            pipe.run()
        self.assertEqual(file_sha256(str(self.box.approved)), sha_before)
        audit = json.loads(Path(pipe.audit_path).read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "BLOQUEADO_TRAZABILIDAD")
        self.assertFalse(audit["published"])

    def test_fallo_al_persistir_artefactos_impide_publicacion_no_trazable(self):
        with mock.patch("src.pipeline.verify_artifacts_logged",
                        side_effect=TraceabilityError("Artefactos no persistidos en MLflow")):
            with self.assertRaises(TraceabilityError):
                self.box.run(publish=True)
        self.assertFalse(self.box.approved.exists())
        exp = self.client().get_experiment_by_name(self.box.cfg["mlflow"]["experiment_name"])
        run = self.client().search_runs([exp.experiment_id])[0]
        self.assertEqual(run.info.status, "FAILED")
        self.assertEqual(run.data.tags["pipeline.status"], "BLOQUEADO_TRAZABILIDAD")
        self.assertEqual(run.data.tags["publication.status"], "NO_PUBLICADO")

    def test_codigos_de_salida_del_cli(self):
        cfg = self.box.config_path()
        with self.assertRaises(SystemExit) as ok:
            pipeline_main(["--config", cfg, "--no-publish"])
        self.assertEqual(ok.exception.code, 0)
        self.assertFalse(self.box.approved.exists())
        with self.assertRaises(SystemExit) as rejected:
            pipeline_main(["--config", self.box.config_path(
                **{"quality_thresholds.metrics_acceptance.max_mae_tolerance": 0.001}), "--publish"])
        self.assertEqual(rejected.exception.code, 1)
        os.environ.update(MLFLOW_TRACKING_URI="http://127.0.0.1:9", MLFLOW_CONNECT_RETRIES="1",
                          MLFLOW_CONNECT_DELAY="0")
        with self.assertRaises(SystemExit) as blocked:
            pipeline_main(["--config", cfg, "--publish"])
        self.assertEqual(blocked.exception.code, 3)

    def test_dos_versiones_respaldo_restauracion_y_lectura_del_tablero(self):
        v1 = self.box.run(publish=True)
        sha_v1 = file_sha256(str(self.box.approved))
        self.box.write_series(synthetic_series(scale=1.3))
        v2 = self.box.run(publish=True)
        sha_v2 = file_sha256(str(self.box.approved))
        self.assertNotEqual(sha_v1, sha_v2)
        self.assertEqual(cargar_version_aprobada(str(self.box.data))["df"].run_id.iloc[0], v2["run_id"])

        backups = list_backups(str(self.box.data / "backup_aprobadas"), REQUIRED)
        backup_v1 = next(b for b in backups if b["run_id"] == v1["run_id"])
        self.assertTrue(backup_v1["ok"], backup_v1["motivos"])
        self.assertTrue(backup_v1["tiene_manifiesto"])
        self.assertIn(v1["run_id"], backup_v1["archivo"])

        record = restore_backup(
            backup_v1["archivo"], str(self.box.approved), str(self.box.data / "backup_aprobadas"),
            str(self.box.tmp / "logs" / "publish.lock"), str(self.box.tmp / "logs"), REQUIRED,
            reason="Prueba: volver a la versión previa", operator="pruebas",
        )
        self.assertEqual(file_sha256(str(self.box.approved)), sha_v1)
        self.assertEqual(record["run_id_restaurado"], v1["run_id"])
        self.assertEqual(record["run_id_reemplazado"], v2["run_id"])
        leida = cargar_version_aprobada(str(self.box.data))
        self.assertEqual(leida["estado"], "ok")
        self.assertEqual(leida["df"].run_id.iloc[0], v1["run_id"])
        self.assertTrue(leida["metadatos_verificados"])
        self.assertEqual(leida["manifiesto"]["run_id"], v1["run_id"])
        # La versión reemplazada quedó respaldada y es restaurable
        self.assertTrue(any(b["run_id"] == v2["run_id"] and b["ok"]
                            for b in list_backups(str(self.box.data / "backup_aprobadas"), REQUIRED)))


# ---------------------------------------------------------------------------
class ServidorMLflowHTTP(EnvIsolation):
    """Mismo esquema que Compose: servidor HTTP con SQLite y artefactos servidos."""

    def _start(self, store: Path, port: int):
        proc = subprocess.Popen(
            [sys.executable, "-m", "mlflow", "server", "--host", "127.0.0.1", "--port", str(port),
             "--workers", "1", "--backend-store-uri", f"sqlite:///{(store / 'mlflow.db').as_posix()}",
             "--artifacts-destination", str(store / "artifacts"), "--serve-artifacts"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                    if resp.status == 200:
                        return proc
            except OSError:
                time.sleep(1)
        proc.kill()
        self.skipTest("No se pudo iniciar mlflow server en este entorno")

    def test_artefactos_por_http_persisten_tras_reiniciar_servidor(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        uri = f"http://127.0.0.1:{port}"
        box = PipelineSandbox(tracking_uri=uri)
        self.addCleanup(box.cleanup)
        store = box.tmp / "mlflow_server"
        store.mkdir()
        server = self._start(store, port)
        try:
            result = box.run(publish=True)
        finally:
            server.terminate()
            server.wait(timeout=30)
        server = self._start(store, port)  # "recrear contenedor": misma base y artefactos
        try:
            client = MlflowClient(tracking_uri=uri)
            run = client.get_run(result["mlflow_run_id"])
            self.assertEqual(run.data.tags["pipeline.status"], "APROBADO_PUBLICADO")
            self.assertTrue(run.info.artifact_uri.startswith("mlflow-artifacts:"))
            local = client.download_artifacts(run.info.run_id, "estimaciones", str(box.tmp / "descarga"))
            csv = next(Path(local).glob("*.csv"))
            self.assertEqual(file_sha256(str(csv)), file_sha256(str(box.approved)))
        finally:
            server.terminate()
            server.wait(timeout=30)


# ---------------------------------------------------------------------------
class Monitoreo(unittest.TestCase):
    def results(self, values, serie="Total", start="2020-01-01"):
        fechas = pd.date_range(start, periods=len(values), freq="MS")
        return pd.DataFrame({"serie": serie, "fecha": fechas.strftime("%Y-%m-%d"), "prediccion": values})

    def test_actualizacion_usa_cobertura_configurada_y_no_hoy(self):
        df = synthetic_series(end="2020-10-01")
        prof = {"series_mensuales.csv": source_profile(df, "series_mensuales.csv")}
        out = monitor_freshness(prof, None, pd.Timestamp("2020-12-01"), pd.Timestamp("2020-12-01"))
        self.assertEqual(out["fuentes"]["series_mensuales.csv"]["estado"], "ALERTA")
        self.assertTrue(any(a["control"] == "actualizacion" and a["severidad"] == "ALERTA" for a in out["alertas"]))
        self.assertEqual(out["salida"]["estado"], "NO_DISPONIBLE")
        ok = monitor_freshness(prof, None, pd.Timestamp("2020-10-01"), pd.Timestamp("2020-10-01"))
        self.assertEqual(ok["fuentes"]["series_mensuales.csv"]["estado"], "OK")

    def test_actualizacion_detecta_serie_atrasada_y_salida_corta(self):
        df = synthetic_series()
        df = df[~((df.serie == "Tipo_Cruceristas") & (df.fecha > "2020-08-01"))]
        prof = {"series_mensuales.csv": source_profile(df, "series_mensuales.csv")}
        out = monitor_freshness(prof, self.results([1.0] * 6), pd.Timestamp("2020-12-01"), pd.Timestamp("2020-12-01"))
        self.assertIn("Tipo_Cruceristas", out["fuentes"]["series_mensuales.csv"]["series_atrasadas"])
        self.assertEqual(out["salida"]["ultima_estimacion_producida"], "2020-06-01")
        self.assertEqual(out["salida"]["estado"], "ALERTA")

    def test_calidad_nulos_duplicados_cobertura_y_ejecucion_previa(self):
        base = synthetic_series()
        prev = {"run_id": "run_prev", "perfiles": {"series_mensuales.csv": source_profile(base, "series_mensuales.csv")}}
        bad = base.iloc[: len(base) - 40]
        bad = bad[~((bad.serie == "Total") & (bad.fecha == "2017-06-01"))]
        bad = pd.concat([bad, bad.iloc[:3]], ignore_index=True)
        bad.loc[5, "viajeros"] = np.nan
        prof = {"series_mensuales.csv": source_profile(bad, "series_mensuales.csv")}
        out = monitor_quality(prof, prev, {"max_null_rate": 0.0, "max_duplicate_rate": 0.0, "min_coverage_ratio": 1.0})
        hallazgos = " ".join(out["fuentes"]["series_mensuales.csv"]["hallazgos"])
        for texto in ("nulos", "duplicados", "cobertura", "caída"):
            self.assertIn(texto, hallazgos)
        self.assertEqual(out["fuentes"]["series_mensuales.csv"]["comparacion_previa"]["run_id_previo"], "run_prev")
        limpio = monitor_quality({"series_mensuales.csv": source_profile(base, "series_mensuales.csv")}, prev, {})
        self.assertFalse(limpio["alertas"])

    def test_resultados_variacion_extrema_es_alerta_de_revision(self):
        out = monitor_results(self.results([100, 110, 200, 190]), threshold=0.50)
        self.assertEqual(out["comparacion"], "intermensual")
        self.assertEqual(out["variaciones_sobre_umbral"], 1)
        self.assertEqual(out["alertas"][0]["severidad"], "REVISION")
        self.assertIn("no prueba pérdida de precisión", out["alertas"][0]["accion"])

    def test_resultados_base_cero_sin_division(self):
        out = monitor_results(self.results([0.0, 50.0, 0.0, 0.0, 10.0]), threshold=0.50)
        self.assertEqual(out["variaciones_base_cero"], 2)
        self.assertTrue(np.isfinite(out["variacion_maxima_abs"]))
        self.assertTrue(any("base cero" in a["accion"] for a in out["alertas"]))

    def test_resultados_negativos_no_finitos_e_interanual(self):
        out = monitor_results(self.results([10.0, -1.0, np.inf, np.nan]))
        self.assertEqual(out["negativos"], 1)
        self.assertEqual(out["no_finitos"], 2)
        self.assertEqual(out["estado"], "ALERTA")
        anual = monitor_results(self.results([100.0] * 12 + [300.0] + [100.0] * 11), threshold=0.5,
                                comparison="interanual")
        self.assertEqual(anual["pares_comparados"], 12)
        self.assertEqual(anual["variaciones_sobre_umbral"], 1)

    def test_error_predictivo_solo_con_observaciones_comparables(self):
        obs = synthetic_series(end="2020-06-01")
        futuro = self.results([1000.0] * 3, start="2021-01-01")
        self.assertFalse(monitor_predictive_error(obs, futuro)["actualizado"])
        pares = self.results([1000.0] * 3, start="2020-01-01")
        out = monitor_predictive_error(obs, pares)
        self.assertTrue(out["actualizado"])
        self.assertEqual(out["por_serie"]["Total"]["n"], 3)

    def test_run_monitoring_sin_salida_reporta_fuentes(self):
        cfg = yaml.safe_load((ROOT / "config" / "pipeline_config.yaml").read_text(encoding="utf-8"))
        cfg["monitoring"]["expected_coverage_end"] = "2020-12-01"
        rep = run_monitoring(cfg, "run_x", {"series_mensuales.csv": synthetic_series()}, None, None)
        self.assertEqual(rep["resultados"]["estado"], "NO_DISPONIBLE")
        self.assertFalse(rep["error_predictivo"]["actualizado"])
        self.assertIn("series_mensuales.csv", rep["calidad"]["fuentes"])


# ---------------------------------------------------------------------------
def approved_frame(run_id, value, fecha_generacion="2026-11-01 10:00:00", estado="APROBADO"):
    fechas = pd.date_range("2021-04-01", "2026-06-01", freq="MS").strftime("%Y-%m-%d")
    rows = [{"destino": "Guatemala", "serie": s, "modelo": "Sintético", "fecha": f, "prediccion": value,
             "unidad_medida": "viajeros/mes", "run_id": run_id, "fecha_generacion": fecha_generacion,
             "version_procedimiento": "9.9.9", "estado_aprobacion": estado}
            for s in REQUIRED for f in fechas]
    return pd.DataFrame(rows)


def manifest_for(run_id, mae):
    return {"schema_version": 1, "estado_aprobacion": "APROBADO", "run_id": run_id,
            "metricas": {"serie": "Total", "mae": mae, "rmse": mae, "n": 63},
            "periodo_evaluacion": {"inicio": "2021-04-01", "fin": "2026-06-01", "n_evaluable": 63},
            "corte_datos_observados": "2026-06-01", "metricas_por_serie": {"series": {}}}


class Restauracion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lab11_restore_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.approved = self.tmp / "data" / "estimaciones_aprobadas.csv"
        self.backups = self.tmp / "data" / "backup_aprobadas"
        self.lock = str(self.tmp / "logs" / "publish.lock")
        publish_approved_atomically(approved_frame("run_v1", 100.0), str(self.approved), str(self.backups),
                                    "run_v1", self.lock, manifest_for("run_v1", 111.0))
        publish_approved_atomically(approved_frame("run_v2", 200.0), str(self.approved), str(self.backups),
                                    "run_v2", self.lock, manifest_for("run_v2", 222.0))
        self.backup_v1 = next(p.name for p in self.backups.glob("*.csv"))

    def restore(self, name, reason="motivo de prueba"):
        return restore_backup(name, str(self.approved), str(self.backups), self.lock,
                              str(self.tmp / "logs"), REQUIRED, reason=reason, operator="pruebas")

    def test_restauracion_valida_atomica_con_auditoria(self):
        record = self.restore(self.backup_v1)
        self.assertEqual(record["run_id_restaurado"], "run_v1")
        self.assertEqual(record["operador"], "pruebas")
        leida = cargar_version_aprobada(str(self.approved.parent))
        self.assertEqual(leida["df"].run_id.iloc[0], "run_v1")
        self.assertTrue(leida["metadatos_verificados"])
        self.assertEqual(leida["manifiesto"]["metricas"]["mae"], 111.0)
        lines = (self.tmp / "logs" / "restore_audit.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[-1])["run_id_reemplazado"], "run_v2")
        self.assertTrue(any("prerestauracion" in p.name for p in self.backups.glob("*.csv")))
        self.assertFalse(list(self.approved.parent.glob("*.tmp")))

    def test_rechaza_rutas_inseguras(self):
        sha = file_sha256(str(self.approved))
        outside = self.tmp / "estimaciones_aprobadas_backup_x.csv"
        shutil.copy2(self.backups / self.backup_v1, outside)
        for name in ("../estimaciones_aprobadas_backup_x.csv", "..\\estimaciones_aprobadas_backup_x.csv",
                     str(outside), "estimaciones_aprobadas.csv", "", "backup_aprobadas/" + self.backup_v1):
            with self.subTest(name=name), self.assertRaises(RestoreError):
                self.restore(name)
        self.assertEqual(file_sha256(str(self.approved)), sha)

    def test_rechaza_enlace_que_sale_del_directorio(self):
        target = self.tmp / "afuera.csv"
        shutil.copy2(self.backups / self.backup_v1, target)
        link = self.backups / "estimaciones_aprobadas_backup_enlace.csv"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("El sistema no permite crear enlaces simbólicos")
        with self.assertRaisesRegex(RestoreError, "fuera del directorio"):
            self.restore(link.name)

    def test_rechaza_respaldos_invalidos_sin_tocar_vigente(self):
        sha = file_sha256(str(self.approved))
        casos = {
            "ilegible": b"\x00\x01no,es\ncsv\"",
            "sin_columnas": approved_frame("run_z", 1.0).drop(columns=["run_id"]).to_csv(index=False).encode(),
            "rechazado": approved_frame("run_r", 1.0, estado="CANDIDATO_RECHAZADO").to_csv(index=False).encode(),
            "negativo": approved_frame("run_n", -5.0).to_csv(index=False).encode(),
        }
        for nombre, contenido in casos.items():
            path = self.backups / f"estimaciones_aprobadas_backup_{nombre}.csv"
            path.write_bytes(contenido)
            with self.subTest(caso=nombre), self.assertRaisesRegex(RestoreError, "inválido"):
                self.restore(path.name)
        # Hash del manifiesto inconsistente con el CSV
        alterado = self.backups / self.backup_v1
        alterado.write_bytes(alterado.read_bytes().replace(b"100.0", b"101.0"))
        with self.assertRaisesRegex(RestoreError, "SHA-256"):
            self.restore(self.backup_v1)
        self.assertEqual(file_sha256(str(self.approved)), sha)

    def test_motivo_obligatorio_y_version_ya_vigente(self):
        with self.assertRaisesRegex(RestoreError, "motivo"):
            self.restore(self.backup_v1, reason=" ")
        self.restore(self.backup_v1)
        with self.assertRaisesRegex(RestoreError, "ya es la vigente"):
            self.restore(self.backup_v1)

    def test_cli_list_y_backup(self):
        cfg = yaml.safe_load((ROOT / "config" / "pipeline_config.yaml").read_text(encoding="utf-8"))
        cfg["paths"].update(output_dir=str(self.approved.parent), backup_dir=str(self.backups),
                            logs_dir=str(self.tmp / "logs"), publish_lock_file=self.lock)
        cfg_path = self.tmp / "cfg.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        with mock.patch("sys.stdout") as out:
            self.assertEqual(restore_main(["--config", str(cfg_path), "--list"]), 0)
        self.assertIn("run_v1", "".join(str(c) for c in out.write.call_args_list))
        with mock.patch("sys.stdout"):
            self.assertEqual(restore_main(["--config", str(cfg_path), "--backup", "../x.csv", "--reason", "r"]), 2)
            self.assertEqual(restore_main(["--config", str(cfg_path), "--backup", self.backup_v1,
                                           "--reason", "prueba CLI", "--operator", "cli"]), 0)
        self.assertEqual(cargar_version_aprobada(str(self.approved.parent))["df"].run_id.iloc[0], "run_v1")


# ---------------------------------------------------------------------------
class TableroVersionAprobada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from streamlit.testing.v1 import AppTest
        cls.AppTest = AppTest

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lab11_app_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        shutil.copytree(ROOT / "data", self.data,
                        ignore=shutil.ignore_patterns("estimaciones_aprobadas*", "backup_aprobadas"))
        self.approved = self.data / "estimaciones_aprobadas.csv"
        self.backups = self.data / "backup_aprobadas"
        patcher = mock.patch.dict(os.environ, {"DATA_DIR": str(self.data)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def app(self):
        at = self.AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.get("plotly_chart")), 9)  # vistas históricas intactas
        return at

    def metric(self, at, prefix):
        return next(m.value for m in at.metric if m.label.startswith(prefix))

    def publish(self, run_id, value, mae):
        publish_approved_atomically(approved_frame(run_id, value), str(self.approved), str(self.backups),
                                    run_id, str(self.tmp / "publish.lock"), manifest_for(run_id, mae))

    def test_sin_version_aprobada_aviso_informativo(self):
        at = self.app()
        self.assertTrue(any("Aún no hay una versión aprobada" in i.value for i in at.info))
        self.assertFalse(any(m.label.startswith("Error medio") for m in at.metric))
        self.assertFalse(self.approved.exists())  # no se fabrica ningún archivo

    def test_version_valida_actualizacion_y_restauracion(self):
        self.publish("run_v1", 100.0, 11111.0)
        at = self.app()
        self.assertEqual(self.metric(at, "Error medio"), "11,111 viajeros/mes")
        self.assertEqual(self.metric(at, "Versión del procedimiento"), "v9.9.9")
        self.assertEqual(self.metric(at, "Periodo evaluado"), "Abr 2021 – Jun 2026")
        self.assertEqual(self.metric(at, "Generada el"), "2026-11-01 10:00")
        # Nueva publicación: la misma sesión ve el cambio al recargar (sin caché obsoleta)
        self.publish("run_v2", 200.0, 22222.0)
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(self.metric(at, "Error medio"), "22,222 viajeros/mes")
        backup_v1 = next(b["archivo"] for b in list_backups(str(self.backups), REQUIRED) if b["run_id"] == "run_v1")
        restore_backup(backup_v1, str(self.approved), str(self.backups), str(self.tmp / "publish.lock"),
                       str(self.tmp / "logs"), REQUIRED, reason="prueba tablero", operator="pruebas")
        at.run()
        self.assertEqual(self.metric(at, "Error medio"), "11,111 viajeros/mes")

    def test_version_invalida_o_manifiesto_inconsistente(self):
        approved_frame("run_r", 1.0, estado="CANDIDATO_RECHAZADO").to_csv(self.approved, index=False)
        at = self.app()
        self.assertTrue(any("no es válida" in w.value for w in at.warning))
        self.assertFalse(any(m.label.startswith("Error medio") for m in at.metric))
        self.approved.write_text("", encoding="utf-8")
        self.assertTrue(any("no es válida" in w.value for w in self.app().warning))
        self.publish("run_v1", 100.0, 11111.0)
        self.approved.write_bytes(self.approved.read_bytes().replace(b"100.0", b"150.0"))
        at = self.app()
        self.assertEqual(self.metric(at, "Error medio"), "No verificable")
        self.assertTrue(any("huella distinta" in w.value for w in at.warning))


# ---------------------------------------------------------------------------
class DockerConfiguracion(unittest.TestCase):
    """Comprobación estática: los datos se montan, no se copian a la imagen."""

    def test_imagen_sin_datos_y_montajes_configurables(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(ignore[[l.strip() for l in ignore].index("*")].strip(), "*")  # lista blanca
        incluidos = [l[1:] for l in ignore if l.startswith("!")]
        self.assertFalse([p for p in incluidos if p == "data" or p.startswith("data/") or p.endswith((".csv", ".db", ".pdf"))])
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        copies = " ".join(l for l in dockerfile.splitlines() if l.startswith("COPY"))
        self.assertNotRegex(copies, r"\bdata\b|\.csv|\. \.|mlflow\.db")
        self.assertIn("USER app", dockerfile)
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        svc = compose["services"]
        self.assertEqual(svc["pipeline"]["environment"]["MLFLOW_TRACKING_URI"], "http://mlflow:5000")
        self.assertEqual(svc["pipeline"]["depends_on"]["mlflow"]["condition"], "service_healthy")
        self.assertIn("${OBS_DATA_DIR:-./data}:/app/data", svc["pipeline"]["volumes"])
        self.assertIn("${OBS_DATA_DIR:-./data}:/app/data:ro", svc["dashboard"]["volumes"])
        cmd = " ".join(svc["mlflow"]["command"])
        self.assertIn("sqlite:////mlflow/mlflow.db", cmd)
        self.assertIn("--artifacts-destination=/mlflow/artifacts", cmd)
        self.assertIn("${OBS_MLFLOW_STORE:-mlflow_store}:/mlflow", svc["mlflow"]["volumes"])
        self.assertIn("mlflow_store", compose["volumes"])
        self.assertIn("healthcheck", svc["mlflow"])

    def test_dependencias_fijadas(self):
        reqs = [l for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[\w.]+", r) for r in reqs), reqs)
        lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        for r in reqs:
            self.assertIn(r.lower(), lock.lower())


@unittest.skipUnless(os.environ.get("RUN_DOCKER_TESTS") == "1", "Requiere Docker; activar con RUN_DOCKER_TESTS=1")
class DockerCompose(unittest.TestCase):
    """Ejecución real: pipeline en contenedor → servidor MLflow de Compose (modo --no-publish)."""

    def compose(self, *args, timeout=900):
        return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")

    def test_pipeline_en_contenedor_registra_en_mlflow_compose_y_persiste(self):
        self.assertEqual(self.compose("up", "-d", "--build", "mlflow").returncode, 0)
        out = self.compose("run", "--rm", "pipeline", "python", "pipeline.py", "--config",
                           "config/pipeline_config.yaml", "--no-publish")
        self.assertEqual(out.returncode, 0, out.stdout[-2000:] + out.stderr[-2000:])
        run_name = re.search(r"Iniciando Pipeline MLOps: (run_\w+)", out.stdout).group(1)
        # Recrear el contenedor del servidor: la base y los artefactos deben seguir ahí
        self.assertEqual(self.compose("rm", "-sf", "mlflow").returncode, 0)
        self.assertEqual(self.compose("up", "-d", "--wait", "mlflow").returncode, 0)
        client = MlflowClient(tracking_uri="http://127.0.0.1:5000")
        exp = client.get_experiment_by_name("Observatorio_Turismo_Guatemala")
        runs = client.search_runs([exp.experiment_id], f"attributes.run_name = '{run_name}'")
        self.assertEqual(len(runs), 1)
        self.assertIn("eval.active.mae", runs[0].data.metrics)
        local = client.download_artifacts(runs[0].info.run_id, "aceptacion", tempfile.mkdtemp())
        self.assertTrue(list(Path(local).glob("acceptance_*.json")))


if __name__ == "__main__":
    unittest.main()
