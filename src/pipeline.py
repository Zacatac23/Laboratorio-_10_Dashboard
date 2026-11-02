"""Pipeline MLOps reproducible — Observatorio de Inteligencia Turística (Lab 11).

Etapas: verificación de MLflow → lectura → QC → split temporal → modelado/factores →
evaluación → aceptación → monitoreo → verificación de artefactos en MLflow →
publicación atómica (opcional).

Política de trazabilidad: el contenido exacto que se publica (CSV y manifiesto) se
registra en MLflow y se relee antes del reemplazo; si MLflow no está disponible o el
registro falla, no se publica. Un fallo antes de evaluar no registra MAE/RMSE.

pais_mensual y via_frontera son contexto (QC y monitoreo); el modelado usa solo
series_mensuales.

Códigos de salida del CLI: 0 aprobado, 1 rechazado, 2 fallo, 3 bloqueado por trazabilidad.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import mlflow
import numpy as np
import pandas as pd
import yaml

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
    verify_repartition_groups,
)
from src.monitoring import (
    ExecutionAudit,
    StageLog,
    estimates_csv_bytes,
    file_sha256,
    load_previous_monitoring,
    manifest_path_for,
    normalize_series_labels,
    publish_approved_atomically,
    resolve_paths,
    run_monitoring,
    save_json,
)
from src.quality_checks import QualityControlError, execute_all_quality_checks
from src.tracking import (
    TraceabilityError,
    connect_settings,
    code_fingerprint,
    ensure_tracking_available,
    environment_info,
    git_info,
    resolve_tracking_uri,
    setup_experiment,
    verify_artifacts_logged,
)

MODEL_LABELS = {
    "historical_mean": "Promedio Histórico Mensual",
    "seasonal_naive": "Seasonal Naive (Lag 12)",
    "holt_winters": "Holt-Winters Aditivo",
}
BASELINE_LABEL = MODEL_LABELS["seasonal_naive"]


def load_config(config_path: str) -> Dict[str, Any]:
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _jsonable(value: Any) -> Any:
    """NaN/inf → None y tipos numpy → Python, para JSON válido."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Index)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _date(value) -> Optional[str]:
    return None if value is None or pd.isna(value) else str(pd.Timestamp(value).date())


class TourismMLOpsPipeline:
    def __init__(self, config_path: str, publish: bool):
        self.config_path = config_path
        self.publish = bool(publish)
        self.config = load_config(config_path)
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.start_time = datetime.now()
        self.git = git_info()
        self.git_commit = self.git["commit"]
        self.audit = ExecutionAudit(
            run_id=self.run_id, git_commit=self.git_commit, start_time=self.start_time.isoformat()
        )

        p = resolve_paths(self.config)
        paths = self.config.get("paths", {})
        self.data_dir = p["data_dir"]
        self.series_path = os.path.join(self.data_dir, paths.get("series_file", "series_mensuales.csv"))
        self.pais_path = os.path.join(self.data_dir, paths.get("pais_file", "pais_mensual.csv"))
        self.via_path = os.path.join(self.data_dir, paths.get("via_frontera_file", "via_frontera.csv"))
        self.approved_path = p["approved"]
        self.manifest_path = manifest_path_for(self.approved_path)
        self.backup_dir = p["backup_dir"]
        self.reports_dir = p["reports_dir"]
        self.logs_dir = p["logs_dir"]
        self.lock_path = p["lock"]
        self.audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
        self.monitoring_path = os.path.join(self.reports_dir, f"monitoring_{self.run_id}.json")
        for path in (self.reports_dir, self.logs_dir, self.backup_dir):
            os.makedirs(path, exist_ok=True)

        self.seed = int(self.config.get("pipeline", {}).get("random_seed", 42))
        np.random.seed(self.seed)
        self.stage = "Inicio"
        self.logged_artifacts: List[str] = []
        self.local_outputs: List[str] = []
        self.source_frames: Dict[str, pd.DataFrame] = {}
        self.monitoring: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ utilidades
    @contextlib.contextmanager
    def _stage(self, name: str) -> Iterator[List[str]]:
        """Registra inicio/fin/estado de cada etapa en la auditoría."""
        self.stage = name
        notes: List[str] = []
        t0 = datetime.now().isoformat()
        try:
            yield notes
        except Exception as exc:
            self.audit.add_stage(StageLog(name, "FAILED", t0, datetime.now().isoformat(), str(exc)[:500]))
            raise
        self.audit.add_stage(StageLog(name, "COMPLETED", t0, datetime.now().isoformat(), "; ".join(notes)))

    def _log_artifact(self, local_path: str, artifact_dir: str) -> None:
        mlflow.log_artifact(local_path, artifact_path=artifact_dir)
        self.logged_artifacts.append(f"{artifact_dir}/{os.path.basename(local_path)}")

    def _save_and_log(self, data: Dict[str, Any], local_path: str, artifact_dir: str) -> str:
        save_json(_jsonable(data), local_path)
        self.local_outputs.append(local_path)
        self._log_artifact(local_path, artifact_dir)
        return local_path

    def _source_entry(self, path: str, role: str, frame: pd.DataFrame) -> Dict[str, Any]:
        return {
            "nombre": os.path.basename(path),
            "rol": role,
            "ruta_logica": path.replace("\\", "/"),
            "sha256": file_sha256(path),
            "bytes": os.path.getsize(path),
            "filas": int(len(frame)),
        }

    def _finish_audit(self, status: str) -> None:
        self.audit.status = status
        self.audit.end_time = datetime.now().isoformat()
        self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
        self.audit.save(self.audit_path)

    def _write_monitoring(self, results_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        previous = load_previous_monitoring(self.reports_dir, exclude_run_id=self.run_id)
        report = run_monitoring(self.config, self.run_id, self.source_frames, results_df, previous)
        report["ejecucion"] = self.audit.to_dict()
        save_json(_jsonable(report), self.monitoring_path)
        if self.monitoring_path not in self.local_outputs:
            self.local_outputs.append(self.monitoring_path)
        self.monitoring = report
        return report

    def _refresh_monitoring_execution(self) -> None:
        if self.monitoring is not None:
            self.monitoring["ejecucion"] = self.audit.to_dict()
            save_json(_jsonable(self.monitoring), self.monitoring_path)

    # ------------------------------------------------------------------ ejecución
    def run(self) -> Dict[str, Any]:
        # mlflow.set_tracking_uri() escribe MLFLOW_TRACKING_URI en os.environ. Como esa variable
        # tiene prioridad sobre el YAML (resolve_tracking_uri), una ejecución previa en el mismo
        # proceso fijaría la URI de las siguientes e ignoraría su configuración (p. ej. un servidor
        # caído no bloquearía la publicación). Se restituye el valor original al terminar.
        # Igual con MLFLOW_EXPERIMENT_ID, que mlflow.set_experiment() también escribe.
        claves = ("MLFLOW_TRACKING_URI", "MLFLOW_EXPERIMENT_ID")
        env_previo = {k: os.environ.get(k) for k in claves}
        try:
            return self._run()
        finally:
            for clave, valor in env_previo.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor

    def _run(self) -> Dict[str, Any]:
        print("\n=======================================================")
        print(f"Iniciando Pipeline MLOps: {self.run_id}")
        print(f"Commit Git: {self.git_commit} ({self.git['source']})")
        print(f"Publicación solicitada: {self.publish}")
        print("=======================================================")

        mlflow_cfg = self.config.get("mlflow", {})
        uri, uri_source = resolve_tracking_uri(self.config)
        self.audit.tracking_uri = uri
        experiment = mlflow_cfg.get("experiment_name", "Observatorio_Turismo_Guatemala")
        try:
            with self._stage("Verificación de trazabilidad (MLflow)") as notes:
                retries, delay = connect_settings(self.config)
                ensure_tracking_available(uri, retries, delay)
                setup_experiment(uri, experiment, mlflow_cfg.get("artifact_location"))
                notes.append(f"{uri} ({uri_source})")
        except Exception as exc:  # noqa: BLE001
            err = exc if isinstance(exc, TraceabilityError) else TraceabilityError(str(exc))
            self.audit.errors.append(str(err))
            self.audit.failed_stage = self.stage
            self.audit.publication_decision = "NO_PUBLICADO: MLflow no disponible (trazabilidad no garantizada)"
            self._finish_audit("BLOQUEADO_TRAZABILIDAD")
            print(f"\n[BLOQUEADO] {err}\nAuditoría local: {self.audit_path}\n")
            raise err from exc
        print(f"[0/9] MLflow: {uri} ({uri_source}), experimento '{experiment}'")

        with mlflow.start_run(run_name=self.run_id) as active:
            self.audit.mlflow_run_id = active.info.run_id
            try:
                return self._execute(active.info.run_id, uri_source, experiment)
            except Exception as exc:
                self._record_failure(exc)
                raise

    def _execute(self, mlflow_run_id: str, uri_source: str, experiment: str) -> Dict[str, Any]:
        cfg = self.config
        scope, t_cfg = cfg["scope"], cfg["temporal_split"]
        target, secondary = scope["target_series"], list(scope.get("secondary_series", []))
        pipe_cfg = cfg.get("pipeline", {})
        proc_version = pipe_cfg.get("version", "1.0.0")

        mlflow.set_tags({
            "run_id": self.run_id,
            "run.start": self.start_time.isoformat(timespec="seconds"),
            "pipeline.name": pipe_cfg.get("name", "turismo_pipeline"),
            "pipeline.status": "EN_CURSO",
            "destination": pipe_cfg.get("destination", "Guatemala"),
            "git.commit": self.git["commit"],
            "git.commit_source": self.git["source"],
            "git.code_dirty": str(self.git["code_dirty"]),
            "publish.requested": str(self.publish),
            "tracking.uri_source": uri_source,
            "evaluation.mode": t_cfg.get("evaluation_mode", "fixed_origin_backtest"),
        })
        code = code_fingerprint()
        env = environment_info(self.seed)
        config_sha = file_sha256(self.config_path)
        mlflow.log_params({
            "procedure.version": proc_version,
            "code.sha256": code["sha256"],
            "config.sha256": config_sha,
            "random_seed": self.seed,
            "python.version": env["python"],
        })
        self._log_artifact(self.config_path, "configuracion")
        self._save_and_log(env, os.path.join(self.reports_dir, f"environment_{self.run_id}.json"), "reproducibilidad")
        self._save_and_log(code, os.path.join(self.reports_dir, f"code_fingerprint_{self.run_id}.json"),
                           "reproducibilidad")

        # 1. Lectura ---------------------------------------------------------
        with self._stage("Lectura de fuentes") as notes:
            df_series = pd.read_csv(self.series_path)
            self.source_frames["series_mensuales.csv"] = df_series
            sources = [dict(self._source_entry(self.series_path, "modelado", df_series), clave="series")]
            for path, key, short in ((self.pais_path, "pais_mensual.csv", "pais"),
                                     (self.via_path, "via_frontera.csv", "via")):
                if os.path.isfile(path):
                    frame = pd.read_csv(path)
                    self.source_frames[key] = frame
                    sources.append(dict(self._source_entry(path, "contexto (QC y monitoreo)", frame), clave=short))
            for entry in sources:
                mlflow.log_param(f"source.{entry['clave']}.sha256", entry["sha256"])
                mlflow.log_param(f"source.{entry['clave']}.path", entry["ruta_logica"])
            self._save_and_log({"fuentes": sources}, os.path.join(self.reports_dir, f"sources_{self.run_id}.json"),
                               "fuentes")
            notes.append(", ".join(f"{s['nombre']}={s['sha256'][:12]}" for s in sources))
            print(f"[1/9] Lectura: {notes[0]}")

        # 2. QC ----------------------------------------------------------------
        with self._stage("Controles de calidad QC-A…F") as notes:
            print("[2/9] Controles automáticos de calidad...")
            qr = execute_all_quality_checks(
                df_series, self.run_id, datetime.now().isoformat(), cfg,
                pais_df=self.source_frames.get("pais_mensual.csv"),
                via_df=self.source_frames.get("via_frontera.csv"),
            )
            self._save_and_log(qr.to_dict(), os.path.join(self.reports_dir, f"quality_report_{self.run_id}.json"),
                               "calidad")
            mlflow.log_metrics({
                "qc.critical_passed": 1 if qr.critical_passed else 0,
                "qc.warnings_count": qr.warnings_count,
                "qc.errors_count": qr.errors_count,
            })
            for res in qr.checks:
                print(f"  - [{res.status}] {res.check_id} {res.name}: {res.details}")
                if res.status == "WARNING":
                    self.audit.warnings.append(f"{res.check_id}: {res.details}")
            if not qr.critical_passed:
                raise QualityControlError(
                    f"Fallo crítico en calidad ({qr.errors_count} errores). "
                    "No se modela ni publica; se preserva estimaciones_aprobadas.csv."
                )
            notes.append("QC críticos aprobados")

        # 3. Split temporal ---------------------------------------------------------
        with self._stage("Preparación y división temporal"):
            print("[3/9] Preparación y división temporal (YAML)...")
            df_series = df_series.copy()
            df_series["fecha"] = pd.to_datetime(df_series["fecha"])
            df_series["viajeros"] = pd.to_numeric(df_series["viajeros"])
            df_series["serie"] = normalize_series_labels(df_series["serie"])
            train_start, train_end = pd.Timestamp(t_cfg["train_start"]), pd.Timestamp(t_cfg["train_end"])
            eval_start, eval_end = pd.Timestamp(t_cfg["eval_start"]), pd.Timestamp(t_cfg["eval_end"])
            df_train = df_series[df_series["fecha"].between(train_start, train_end)].copy()
            df_eval = df_series[df_series["fecha"].between(eval_start, eval_end)].copy()
            s_train = df_train[df_train["serie"] == target].set_index("fecha")["viajeros"].sort_index()
            s_eval = df_eval[df_eval["serie"] == target].set_index("fecha")["viajeros"].sort_index()
            excluded_cfg = t_cfg.get("excluded_evaluation_periods") or []
            mlflow.log_params({
                "split.train_start": _date(train_start), "split.train_end": _date(train_end),
                "split.eval_start": _date(eval_start), "split.eval_end": _date(eval_end),
                "split.n_train": len(s_train), "split.excluded_periods_config": json.dumps(excluded_cfg)[:500],
            })
            print(f"  Train: {train_start:%Y-%m}–{train_end:%Y-%m} (N={len(s_train)})")
            print(f"  Eval (backtest origen fijo): {eval_start:%Y-%m}–{eval_end:%Y-%m} (N={len(s_eval)})")

        # 4. Modelos y factores --------------------------------------------------------
        with self._stage("Ajuste de modelo, baselines y factores") as notes:
            print("[4/9] Modelo, baselines y factores de reparto...")
            factors = calculate_repartition_factors(df_train, target_series=target, required_series=secondary)
            group_tol = float(cfg.get("repartition_factors", {}).get("group_tolerance", 0.05))
            for warning in verify_repartition_groups(factors, atol=group_tol).get("warnings", []):
                self.audit.warnings.append(warning)
                print(f"  [AVISO reparto] {warning}")
            mlflow.log_params({f"factor_reparto.{k}": round(v, 6) for k, v in factors.items()})

            eval_dates = s_eval.index
            hw_cfg = cfg.get("models", {}).get("holt_winters", {})
            pred_snaive = fit_and_predict_seasonal_naive(s_train, eval_dates, lag=12)
            pred_hmean = fit_and_predict_historical_mean(s_train, eval_dates)
            pred_hw, hw_fit = fit_and_predict_holt_winters(
                s_train, eval_dates,
                seasonal_periods=hw_cfg.get("seasonal_periods", 12),
                trend=hw_cfg.get("trend", "add"),
                seasonal=hw_cfg.get("seasonal", "add"),
                clip_negative=bool(hw_cfg.get("clip_negative_for_evaluation", False)),
            )
            active = cfg.get("models", {}).get("active_model", "historical_mean")
            preds = {"historical_mean": pred_hmean, "seasonal_naive": pred_snaive, "holt_winters": pred_hw}
            if active not in preds:
                raise ValueError(f"models.active_model desconocido: {active}")
            chosen_pred, chosen_label = preds[active], MODEL_LABELS[active]
            mlflow.log_params({"model.active": chosen_label, "model.baseline": BASELINE_LABEL})
            mlflow.log_params({f"model.holt_winters.{k}": v for k, v in hw_cfg.items() if k != "description"})
            model_doc = {
                "modelo_activo": chosen_label,
                "reproduccion": "Ajustar con series_mensuales (serie objetivo) entre train_start y train_end.",
                "factores_reparto": factors,
                "promedio_historico_mensual": {
                    int(m): float(v) for m, v in s_train.groupby(s_train.index.month).mean().items()
                },
                "seasonal_naive_lag12_valores_base": {
                    _date(d): float(v) for d, v in s_train.iloc[-12:].items()
                },
                "holt_winters_referencia": {
                    k: _jsonable(np.asarray(v).tolist() if hasattr(v, "__len__") else v)
                    for k, v in hw_fit.params.items()
                },
            }
            self._save_and_log(model_doc, os.path.join(self.reports_dir, f"model_{self.run_id}.json"), "modelo")
            notes.append(chosen_label)

        # 5. Evaluación ------------------------------------------------------------
        with self._stage("Evaluación temporal") as notes:
            print("[5/9] Evaluación temporal (meses comparables)...")
            evaluable_idx, eval_info = build_evaluation_mask(s_eval, excluded_periods=excluded_cfg)
            metrics = {
                "active": compute_metrics(s_eval, chosen_pred, evaluable_index=evaluable_idx),
                "hw": compute_metrics(s_eval, pred_hw, evaluable_index=evaluable_idx),
                "snaive": compute_metrics(s_eval, pred_snaive, evaluable_index=evaluable_idx),
                "hmean": compute_metrics(s_eval, pred_hmean, evaluable_index=evaluable_idx),
            }
            mlflow.log_metrics({"eval.n_total": eval_info["n_total"], "eval.n_evaluable": eval_info["n_evaluable"]})
            mlflow.log_param("eval.excluded_months", json.dumps(eval_info["excluded_months"])[:500])
            for prefix, m in metrics.items():
                mlflow.log_metric(f"eval.{prefix}.n", m["n"])
                if m["n"] > 0:  # sin pares comparables no se registran errores
                    mlflow.log_metrics({f"eval.{prefix}.mae": m["mae"], f"eval.{prefix}.rmse": m["rmse"],
                                        f"eval.{prefix}.ape_eps_pct": m["ape_eps_pct"]})
            if metrics["active"]["n"] > 0 and metrics["snaive"]["n"] > 0:
                mlflow.log_metric("eval.active_minus_baseline.mae", metrics["active"]["mae"] - metrics["snaive"]["mae"])
            for prefix, label in (("active", chosen_label), ("hw", "HW"), ("snaive", "Seasonal Naive"),
                                  ("hmean", "Promedio histórico")):
                m = metrics[prefix]
                txt = "N=0 (sin métricas)" if m["n"] == 0 else (
                    f"MAE={m['mae']:,.2f} | RMSE={m['rmse']:,.2f} | APE_eps%={m['ape_eps_pct']:.2f} (N={m['n']})")
                print(f"  {label}: {txt}")
            notes.append(f"N evaluable={eval_info['n_evaluable']}")

        # 6. Candidato y aceptación ---------------------------------------------------
        with self._stage("Candidato, integridad y regla de aceptación") as notes:
            print("[6/9] Candidato, integridad y regla de aceptación...")
            required_out = [target] + secondary
            df_candidate = self._build_estimates_frame(chosen_pred, chosen_label, factors, "CANDIDATO")
            integrity = validate_estimates_frame(df_candidate, required_series=required_out, require_non_negative=True)
            if not integrity["ok"]:
                raise ValueError("Integridad de salida fallida: " + "; ".join(integrity["reasons"]))
            acceptance = evaluate_acceptance_rule(
                metrics_model=metrics["active"], metrics_baseline=metrics["snaive"],
                quality_passed=qr.critical_passed, forecast_series=chosen_pred, config=cfg,
                estimates_df=df_candidate, required_series=required_out,
            )
            is_accepted = bool(acceptance["is_accepted"])
            estado = "APROBADO" if is_accepted else "CANDIDATO_RECHAZADO"
            df_out = self._build_estimates_frame(chosen_pred, chosen_label, factors, estado)
            if is_accepted:
                check = validate_estimates_frame(df_out, required_series=required_out,
                                                 require_non_negative=True, require_approved_state=True)
                if not check["ok"]:
                    is_accepted, estado = False, "CANDIDATO_RECHAZADO"
                    df_out["estado_aprobacion"] = estado
                    acceptance["is_accepted"] = False
                    acceptance["reasons"].extend(check["reasons"])
            acceptance["baseline_model"] = BASELINE_LABEL
            acceptance["comparacion_mismos_meses"] = True
            thr = cfg.get("quality_thresholds", {}).get("metrics_acceptance", {})
            mlflow.log_params({f"acceptance.{k}": v for k, v in thr.items()})
            mlflow.log_metric("acceptance.is_accepted", 1 if is_accepted else 0)
            mlflow.set_tags({"acceptance.decision": "APPROVED" if is_accepted else "REJECTED",
                             "acceptance.beats_baseline": str(acceptance["beats_baseline"])})
            self._save_and_log(acceptance, os.path.join(self.reports_dir, f"acceptance_{self.run_id}.json"),
                               "aceptacion")
            candidate_path = os.path.join(self.reports_dir, f"estimaciones_candidatas_{self.run_id}.csv")
            with open(candidate_path, "wb") as handle:
                handle.write(estimates_csv_bytes(df_out))
            self.local_outputs.append(candidate_path)
            self._log_artifact(candidate_path, "estimaciones")
            mlflow.log_param("candidate.sha256", file_sha256(candidate_path))
            print(f"  Decisión: {'APROBADO' if is_accepted else 'RECHAZADO'} "
                  f"(beats_baseline={acceptance['beats_baseline']}, no obligatorio)")
            for reason in acceptance["reasons"]:
                print(f"  - {reason}")
                self.audit.warnings.append(f"Aceptación: {reason}")
            notes.append(estado)

        # 7. Monitoreo ------------------------------------------------------------
        with self._stage("Monitoreo (actualización, calidad, resultados)") as notes:
            print("[7/9] Monitoreo...")
            mon = self._write_monitoring(df_out)
            for alert in mon["alertas"]:
                print(f"  [{alert['severidad']}] {alert['control']}: {alert['mensaje']}")
                if alert["severidad"] != "INFO":
                    self.audit.warnings.append(f"Monitoreo {alert['control']}: {alert['mensaje']}")
            mlflow.log_metrics({"monitoring.healthy": 1 if mon["all_healthy"] else 0,
                                "monitoring.alerts_count": mon["alerts_count"]})
            notes.append(f"alertas accionables={mon['alerts_count']}")

        # 8. Decisión y registro previo a publicar ------------------------------------------
        will_publish = is_accepted and self.publish
        if will_publish:
            decision = "PUBLICAR"
        elif is_accepted:
            decision = "NO_PUBLICADO: ejecución --no-publish (dry-run)"
        else:
            decision = "NO_PUBLICADO: candidato rechazado por la regla de aceptación"
        self.audit.publication_decision = decision
        manifest = None
        with self._stage("Registro verificado en MLflow") as notes:
            print("[8/9] Registro y verificación de artefactos en MLflow...")
            if is_accepted:
                manifest = self._build_manifest(
                    df_out, chosen_label, metrics, eval_info, evaluable_idx, acceptance, mon,
                    sources, config_sha, code, s_train, df_series, target, mlflow_run_id, experiment,
                )
                manifest["csv_sha256"] = file_sha256(candidate_path)
                self._save_and_log(manifest, os.path.join(self.reports_dir, f"manifest_{self.run_id}.json"),
                                   "publicacion" if will_publish else "manifiesto_candidato")
            self._refresh_monitoring_execution()
            self._log_artifact(self.monitoring_path, "monitoreo")
            self.audit.save(self.audit_path)
            self._log_artifact(self.audit_path, "auditoria")
            mlflow.set_tag("publication.decision", decision)
            mlflow.set_tag("pipeline.status", "PUBLICANDO" if will_publish else "CERRANDO")
            verify_artifacts_logged(mlflow_run_id, self.logged_artifacts)
            notes.append(f"{len(self.logged_artifacts)} artefactos releídos")

        # 9. Publicación ---------------------------------------------------------------
        published, pub = False, {}
        if will_publish:
            with self._stage("Publicación atómica") as notes:
                print("[9/9] Publicación atómica...")
                pub = publish_approved_atomically(
                    df_out, approved_path=self.approved_path, backup_dir=self.backup_dir,
                    run_id=self.run_id, lock_path=self.lock_path, manifest=manifest,
                )
                if pub["new_sha256"] != manifest["csv_sha256"]:
                    raise RuntimeError("El archivo publicado no coincide con el artefacto registrado en MLflow.")
                published = True
                self.audit.published = True
                notes.append(f"sha256={pub['new_sha256'][:16]}; respaldo={pub.get('backup_file')}")
                print(f"  Publicado: {self.approved_path}")
                if pub.get("backup_file"):
                    print(f"  Respaldo de la versión previa: {pub['backup_file']}")
        else:
            print(f"[9/9] {decision}. Versión aprobada intacta.")

        status = "APROBADO_PUBLICADO" if published else ("APROBADO_NO_PUBLICADO" if is_accepted else "RECHAZADO")
        self.audit.publication_decision = "PUBLICADO" if published else decision
        self._finish_audit(status)
        self._refresh_monitoring_execution()
        try:  # registro de cierre: el contenido publicado ya quedó registrado y verificado
            mlflow.set_tags({"pipeline.status": status, "run.end": self.audit.end_time,
                             "publication.status": "PUBLICADO" if published else "NO_PUBLICADO"})
            if published:
                mlflow.log_params({"publish.previous_sha256": pub.get("previous_sha256") or "ninguno",
                                   "publish.new_sha256": pub["new_sha256"],
                                   "publish.backup_file": os.path.basename(pub.get("backup_file") or "ninguno")})
            mlflow.log_metric("pipeline.duration_seconds", self.audit.duration_seconds)
            self._log_artifact(self.audit_path, "auditoria")
            self._log_artifact(self.monitoring_path, "monitoreo")
        except Exception as exc:  # noqa: BLE001
            self.audit.warnings.append(f"Registro de cierre en MLflow incompleto: {exc}")
            self.audit.save(self.audit_path)
            print(f"  [AVISO] Registro de cierre en MLflow incompleto: {exc}")

        print(f"\nPipeline {status} en {self.audit.duration_seconds}s | publicado={published}")
        print("=======================================================\n")
        return {
            "status": status,
            "run_id": self.run_id,
            "mlflow_run_id": mlflow_run_id,
            "published": published,
            "is_accepted": is_accepted,
            "decision": self.audit.publication_decision,
            "metrics": metrics["active"],
            "eval_info": eval_info,
            "audit_file": self.audit_path,
            "monitoring_file": self.monitoring_path,
            "approved_sha256": file_sha256(self.approved_path),
        }

    def _record_failure(self, exc: Exception) -> None:
        if isinstance(exc, QualityControlError):
            status = "FALLIDO_CALIDAD"
        elif isinstance(exc, TraceabilityError):
            status = "BLOQUEADO_TRAZABILIDAD"
        else:
            status = "FALLIDO"
        self.audit.failed_stage = self.stage
        self.audit.published = False
        self.audit.publication_decision = f"NO_PUBLICADO: {status.lower()} en etapa '{self.stage}'"
        if str(exc) not in self.audit.errors:
            self.audit.errors.append(str(exc))
        self._finish_audit(status)
        if self.monitoring is not None:
            self._refresh_monitoring_execution()
        elif self.source_frames:  # el monitoreo de fuentes informa aunque no haya salida
            try:
                self._write_monitoring(None)
            except Exception as mon_exc:  # noqa: BLE001
                self.audit.warnings.append(f"Monitoreo no disponible tras el fallo: {mon_exc}")
                self.audit.save(self.audit_path)
        error_path = os.path.join(self.logs_dir, f"error_{self.run_id}.json")
        save_json({
            "run_id": self.run_id,
            "estado": status,
            "etapa": self.stage,
            "tipo_error": type(exc).__name__,
            "mensaje": str(exc),
            "publicado": False,
            "version_aprobada_vigente_sha256": file_sha256(self.approved_path),
            "metricas": "Solo se registraron métricas calculadas antes del fallo; no se sustituyen por 0.",
            "reportes_disponibles": [p.replace("\\", "/") for p in self.local_outputs if os.path.isfile(p)],
        }, error_path)
        try:
            mlflow.set_tags({"pipeline.status": status, "pipeline.failed_stage": self.stage,
                             "publication.status": "NO_PUBLICADO", "run.end": self.audit.end_time})
            mlflow.log_param("pipeline.error", str(exc)[:500])
            self._log_artifact(error_path, "fallo")
            self._log_artifact(self.audit_path, "auditoria")
            if self.monitoring is not None:
                self._log_artifact(self.monitoring_path, "monitoreo")
        except Exception as log_exc:  # noqa: BLE001
            self.audit.warnings.append(f"Registro del fallo en MLflow incompleto: {log_exc}")
            self.audit.save(self.audit_path)
        print(f"\n[{status}] Etapa '{self.stage}': {exc}")
        print("Se conserva la versión aprobada vigente sin alteraciones.\n")

    # ------------------------------------------------------------------ salidas
    def _build_estimates_frame(self, chosen_pred: pd.Series, label: str, factors: Dict[str, float],
                               estado: str) -> pd.DataFrame:
        pipe = self.config.get("pipeline", {})
        scope = self.config.get("scope", {})
        decimals = int(self.config.get("quality_thresholds", {}).get("metrics_acceptance", {})
                       .get("round_predictions_decimals", 2))
        common = {
            "destino": pipe.get("destination", "Guatemala"),
            "unidad_medida": scope.get("unit_of_measure", "viajeros/mes"),
            "run_id": self.run_id,
            "fecha_generacion": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "version_procedimiento": pipe.get("version", "1.0.0"),
            "estado_aprobacion": estado,
        }
        # Dominio ≥ 0 solo al materializar la salida (no altera métricas previas)
        pred_pub = apply_domain_non_negative(chosen_pred)
        rows = []
        for serie, factor, modelo in [(scope.get("target_series", "Total"), 1.0, label)] + [
            (s, factors.get(s), f"{label} + Reparto Histórico") for s in scope.get("secondary_series", [])
        ]:
            if factor is None:
                raise ValueError(f"Factor de reparto ausente para serie obligatoria '{serie}'.")
            for dt, val in pred_pub.items():
                rows.append({"destino": common["destino"], "serie": serie, "modelo": modelo,
                             "fecha": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                             "prediccion": round(float(val) * float(factor), decimals),
                             **{k: v for k, v in common.items() if k != "destino"}})
        columns = ["destino", "serie", "modelo", "fecha", "prediccion", "unidad_medida", "run_id",
                   "fecha_generacion", "version_procedimiento", "estado_aprobacion"]
        return pd.DataFrame(rows, columns=columns)

    def _build_manifest(self, df_out, label, metrics, eval_info, evaluable_idx, acceptance, mon, sources,
                        config_sha, code, s_train, df_series, target, mlflow_run_id, experiment) -> Dict[str, Any]:
        t_cfg = self.config["temporal_split"]
        observed_target = df_series[(df_series["serie"] == target) & df_series["viajeros"].notna()]
        corte = observed_target["fecha"].max()
        fechas = pd.to_datetime(df_out["fecha"])
        m, b = metrics["active"], metrics["snaive"]
        return _jsonable({
            "schema_version": 1,
            "estado_aprobacion": "APROBADO",
            "run_id": self.run_id,
            "mlflow_run_id": mlflow_run_id,
            "mlflow_experiment": experiment,
            "fecha_generacion": str(df_out["fecha_generacion"].iloc[0]),
            "fecha_generacion_utc_offset": self.start_time.astimezone().strftime("%z"),
            "version_procedimiento": str(df_out["version_procedimiento"].iloc[0]),
            "modelo": label,
            "destino": str(df_out["destino"].iloc[0]),
            "unidad_medida": str(df_out["unidad_medida"].iloc[0]),
            "series": sorted(df_out["serie"].unique().tolist()),
            "n_filas": int(len(df_out)),
            "rango_estimaciones": {"inicio": _date(fechas.min()), "fin": _date(fechas.max())},
            "tipo_estimaciones": "retrospectiva (backtest de origen fijo)",
            "corte_datos_observados": _date(corte),
            "incluye_pronostico_futuro": bool((fechas > corte).any()),
            "periodo_ajuste": {"inicio": t_cfg["train_start"], "fin": t_cfg["train_end"], "n": int(len(s_train))},
            "periodo_evaluacion": {
                "inicio": _date(evaluable_idx.min()) if len(evaluable_idx) else None,
                "fin": _date(evaluable_idx.max()) if len(evaluable_idx) else None,
                "n_evaluable": eval_info["n_evaluable"],
                "meses_excluidos": eval_info["excluded_months"],
                "exclusiones": eval_info["excluded_periods"],
            },
            "metricas": {"serie": target, "mae": m["mae"], "rmse": m["rmse"], "ape_eps_pct": m["ape_eps_pct"],
                         "n": m["n"]},
            "baseline": {"modelo": BASELINE_LABEL, "mae": b["mae"], "rmse": b["rmse"], "n": b["n"],
                         "mismos_meses": True, "supera_baseline": acceptance["beats_baseline"]},
            "metricas_por_serie": {
                "nota": "Diagnóstico sobre los valores publicados (≥0) frente a lo observado; no es criterio de aceptación.",
                "series": mon["error_predictivo"].get("por_serie", {}),
            },
            "regla_aceptacion": {"max_mae": acceptance["max_mae_threshold"],
                                 "max_rmse": acceptance["max_rmse_threshold"],
                                 "nota": acceptance["note"]},
            "trazabilidad": {
                "git_commit": self.git["commit"],
                "git_commit_source": self.git["source"],
                "codigo_sha256": code["sha256"],
                "config_sha256": config_sha,
                "fuentes": [{k: s[k] for k in ("nombre", "rol", "ruta_logica", "sha256")} for s in sources],
            },
        })


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline MLOps del Observatorio. Debe indicar --publish o --no-publish."
    )
    parser.add_argument("--config", default="config/pipeline_config.yaml")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--publish", action="store_true",
                       help="Si el candidato es aceptado, publica atómicamente estimaciones_aprobadas.csv")
    group.add_argument("--no-publish", action="store_true",
                       help="Dry-run: evalúa y registra sin alterar la versión aprobada")
    args = parser.parse_args(argv)
    try:
        result = TourismMLOpsPipeline(config_path=args.config, publish=bool(args.publish)).run()
    except TraceabilityError:
        sys.exit(3)
    except QualityControlError:
        sys.exit(2)
    except Exception:  # noqa: BLE001 - el detalle ya quedó en auditoría y consola
        import traceback
        traceback.print_exc()
        sys.exit(2)
    sys.exit(0 if result["is_accepted"] else 1)


if __name__ == "__main__":
    main()
