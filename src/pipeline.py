"""Pipeline MLOps reproducible — Observatorio de Inteligencia Turística (Lab 11).

Etapas: lectura → QC → split temporal → modelado/factores → evaluación →
aceptación → publicación atómica (opcional) → monitoreo → auditoría/MLflow.

pais_mensual y via_frontera son contexto; el modelado usa solo series_mensuales.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

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
    file_sha256,
    publish_approved_atomically,
    verify_monitoring,
)
from src.quality_checks import QualityControlError, execute_all_quality_checks


def get_git_commit_hash() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode("ascii")
            .strip()
        )
    except Exception:
        return "git-unavailable-or-not-committed"


def compute_file_sha256(filepath: str) -> str:
    return file_sha256(filepath) or "file-not-found"


def load_config(config_path: str) -> Dict[str, Any]:
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TourismMLOpsPipeline:
    def __init__(self, config_path: str, publish: bool):
        self.config_path = config_path
        self.publish = bool(publish)
        self.config = load_config(config_path)
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.start_time = datetime.now()
        self.git_commit = get_git_commit_hash()
        self.audit = ExecutionAudit(
            run_id=self.run_id,
            git_commit=self.git_commit,
            start_time=self.start_time.isoformat(),
        )

        paths = self.config.get("paths", {})
        self.data_dir = paths.get("raw_data_dir", "data")
        self.series_path = os.path.join(self.data_dir, paths.get("series_file", "series_mensuales.csv"))
        self.pais_path = os.path.join(self.data_dir, paths.get("pais_file", "pais_mensual.csv"))
        self.via_path = os.path.join(self.data_dir, paths.get("via_frontera_file", "via_frontera.csv"))
        self.approved_path = os.path.join(self.data_dir, paths.get("approved_file", "estimaciones_aprobadas.csv"))
        self.backup_dir = paths.get("backup_dir", "data/backup_aprobadas")
        self.reports_dir = paths.get("reports_dir", "reports")
        self.logs_dir = paths.get("logs_dir", "logs")
        self.lock_path = paths.get("publish_lock_file", os.path.join(self.logs_dir, "publish.lock"))

        for path in (self.reports_dir, self.logs_dir, self.backup_dir):
            os.makedirs(path, exist_ok=True)
        np.random.seed(self.config.get("pipeline", {}).get("random_seed", 42))

    def _save_quality_and_audit_early(self, quality_report, t0, err_msg: str) -> str:
        quality_report_path = os.path.join(self.reports_dir, f"quality_report_{self.run_id}.json")
        with open(quality_report_path, "w", encoding="utf-8") as handle:
            json.dump(quality_report.to_dict(), handle, indent=2, ensure_ascii=False)
        self.audit.errors.append(err_msg)
        self.audit.add_stage(
            StageLog("Controles de calidad", "FAILED", t0.isoformat(), datetime.now().isoformat(), err_msg)
        )
        self.audit.status = "ABORTED_QUALITY_FAILURE"
        self.audit.end_time = datetime.now().isoformat()
        self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
        audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
        self.audit.save(audit_path)
        return quality_report_path

    def _build_estimates_frame(
        self,
        chosen_pred: pd.Series,
        chosen_model_label: str,
        factors: Dict[str, float],
        estado: str,
    ) -> pd.DataFrame:
        destination = self.config.get("pipeline", {}).get("destination", "Guatemala")
        unit = self.config.get("scope", {}).get("unit_of_measure", "viajeros/mes")
        proc_version = self.config.get("pipeline", {}).get("version", "1.0.0")
        decimals = int(
            self.config.get("quality_thresholds", {})
            .get("metrics_acceptance", {})
            .get("round_predictions_decimals", 2)
        )
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target = self.config.get("scope", {}).get("target_series", "Total")
        secondary = self.config.get("scope", {}).get("secondary_series", [])

        # Dominio ≥ 0 solo al materializar filas de salida (no altera métricas previas)
        pred_pub = apply_domain_non_negative(chosen_pred)
        rows = []
        for dt, val in pred_pub.items():
            rows.append(
                {
                    "destino": destination,
                    "serie": target,
                    "modelo": chosen_model_label,
                    "fecha": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                    "prediccion": round(float(val), decimals),
                    "unidad_medida": unit,
                    "run_id": self.run_id,
                    "fecha_generacion": now_str,
                    "version_procedimiento": proc_version,
                    "estado_aprobacion": estado,
                }
            )
        for serie in secondary:
            if serie not in factors:
                raise ValueError(f"Factor de reparto ausente para serie obligatoria '{serie}'.")
            factor = factors[serie]
            for dt, val_tot in pred_pub.items():
                rows.append(
                    {
                        "destino": destination,
                        "serie": serie,
                        "modelo": f"{chosen_model_label} + Reparto Histórico",
                        "fecha": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                        "prediccion": round(float(val_tot) * float(factor), decimals),
                        "unidad_medida": unit,
                        "run_id": self.run_id,
                        "fecha_generacion": now_str,
                        "version_procedimiento": proc_version,
                        "estado_aprobacion": estado,
                    }
                )
        return pd.DataFrame(rows)

    def run(self) -> Dict[str, Any]:
        print("\n=======================================================")
        print(f"Iniciando Pipeline MLOps: {self.run_id}")
        print(f"Commit Git: {self.git_commit}")
        print(f"Publicación solicitada: {self.publish}")
        print(f"Timestamp: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=======================================================")

        mlflow_cfg = self.config.get("mlflow", {})
        mlflow.set_tracking_uri(mlflow_cfg.get("tracking_uri", "sqlite:///mlflow.db"))
        mlflow.set_experiment(mlflow_cfg.get("experiment_name", "Observatorio_Turismo_Guatemala"))

        with mlflow.start_run(run_name=self.run_id):
            mlflow.set_tag("pipeline.name", self.config.get("pipeline", {}).get("name", "turismo_pipeline"))
            mlflow.set_tag("git.commit", self.git_commit)
            mlflow.set_tag("destination", self.config.get("pipeline", {}).get("destination", "Guatemala"))
            mlflow.set_tag("run_id", self.run_id)
            mlflow.set_tag("publish.requested", str(self.publish))
            mlflow.set_tag(
                "evaluation.mode",
                self.config.get("temporal_split", {}).get("evaluation_mode", "fixed_origin_backtest"),
            )

            try:
                # 1. Lectura
                t0 = datetime.now()
                source_sha = compute_file_sha256(self.series_path)
                mlflow.log_param("source.series_file", self.series_path)
                mlflow.log_param("source.sha256", source_sha)
                print(f"[1/8] Lectura: {self.series_path} (SHA-256: {source_sha[:12]}...)")
                df_series = pd.read_csv(self.series_path)
                pais_df = pd.read_csv(self.pais_path) if os.path.isfile(self.pais_path) else None
                via_df = pd.read_csv(self.via_path) if os.path.isfile(self.via_path) else None
                if pais_df is not None:
                    mlflow.log_param("source.pais.sha256", compute_file_sha256(self.pais_path)[:16])
                if via_df is not None:
                    mlflow.log_param("source.via.sha256", compute_file_sha256(self.via_path)[:16])
                self.audit.add_stage(
                    StageLog("Lectura de fuentes", "COMPLETED", t0.isoformat(), datetime.now().isoformat())
                )

                # 2. QC Gate 1
                t0 = datetime.now()
                print("[2/8] Controles automáticos de calidad...")
                quality_report = execute_all_quality_checks(
                    df_series, self.run_id, t0.isoformat(), self.config, pais_df=pais_df, via_df=via_df
                )
                quality_report_path = os.path.join(self.reports_dir, f"quality_report_{self.run_id}.json")
                with open(quality_report_path, "w", encoding="utf-8") as handle:
                    json.dump(quality_report.to_dict(), handle, indent=2, ensure_ascii=False)
                mlflow.log_artifact(quality_report_path, artifact_path="quality_reports")
                mlflow.log_metric("qc.critical_passed", 1 if quality_report.critical_passed else 0)
                mlflow.log_metric("qc.warnings_count", quality_report.warnings_count)
                mlflow.log_metric("qc.errors_count", quality_report.errors_count)

                for res in quality_report.checks:
                    print(f"  - [{res.status}] {res.check_id} {res.name}: {res.details}")
                    if res.status == "WARNING":
                        self.audit.warnings.append(f"{res.check_id}: {res.details}")

                if not quality_report.critical_passed:
                    err_msg = (
                        f"Fallo crítico en calidad ({quality_report.errors_count} errores). "
                        "No se modela ni publica; se preserva estimaciones_aprobadas.csv."
                    )
                    self._save_quality_and_audit_early(quality_report, t0, err_msg)
                    mlflow.set_tag("pipeline.status", "FAILED_QUALITY_CHECK")
                    mlflow.log_artifact(
                        os.path.join(self.logs_dir, f"audit_{self.run_id}.json"),
                        artifact_path="audit_logs",
                    )
                    raise QualityControlError(err_msg)

                self.audit.add_stage(
                    StageLog(
                        "Controles de calidad",
                        "COMPLETED",
                        t0.isoformat(),
                        datetime.now().isoformat(),
                        "QC críticos aprobados",
                    )
                )

                # 3. Split temporal (solo YAML)
                t0 = datetime.now()
                print("[3/8] Preparación y división temporal (YAML)...")
                df_series = df_series.copy()
                df_series["fecha"] = pd.to_datetime(df_series["fecha"])
                df_series["viajeros"] = pd.to_numeric(df_series["viajeros"])
                df_series["serie"] = (
                    df_series["serie"]
                    .astype(str)
                    .str.replace(r"Via_A.*rea", "Via_Aérea", regex=True)
                    .str.replace(r"Via_Mar.*tima", "Via_Marítima", regex=True)
                )

                t_cfg = self.config["temporal_split"]
                train_start = pd.to_datetime(t_cfg["train_start"])
                train_end = pd.to_datetime(t_cfg["train_end"])
                eval_start = pd.to_datetime(t_cfg["eval_start"])
                eval_end = pd.to_datetime(t_cfg["eval_end"])
                for key, value in {
                    "split.train_start": train_start,
                    "split.train_end": train_end,
                    "split.eval_start": eval_start,
                    "split.eval_end": eval_end,
                }.items():
                    mlflow.log_param(key, str(pd.Timestamp(value).date()))

                df_train = df_series[df_series["fecha"].between(train_start, train_end)].copy()
                df_eval = df_series[df_series["fecha"].between(eval_start, eval_end)].copy()
                target = self.config["scope"]["target_series"]
                s_train = df_train[df_train["serie"] == target].set_index("fecha")["viajeros"].sort_index()
                s_eval = df_eval[df_eval["serie"] == target].set_index("fecha")["viajeros"].sort_index()
                print(f"  Train: {train_start:%Y-%m}–{train_end:%Y-%m} (N={len(s_train)})")
                print(f"  Eval (backtest origen fijo): {eval_start:%Y-%m}–{eval_end:%Y-%m} (N={len(s_eval)})")
                self.audit.add_stage(
                    StageLog("Preparación y división temporal", "COMPLETED", t0.isoformat(), datetime.now().isoformat())
                )

                # 4. Modelos y factores
                t0 = datetime.now()
                print("[4/8] Modelo, baselines y factores de reparto...")
                secondary = self.config["scope"]["secondary_series"]
                factors = calculate_repartition_factors(
                    df_train, target_series=target, required_series=secondary
                )
                group_tol = float(self.config.get("repartition_factors", {}).get("group_tolerance", 0.05))
                group_rep = verify_repartition_groups(factors, atol=group_tol)
                for warning in group_rep.get("warnings", []):
                    self.audit.warnings.append(warning)
                    print(f"  [AVISO reparto] {warning}")
                for name, factor in factors.items():
                    mlflow.log_param(f"factor_reparto.{name}", round(factor, 5))

                eval_dates = s_eval.index
                pred_snaive = fit_and_predict_seasonal_naive(s_train, eval_dates, lag=12)
                pred_hmean = fit_and_predict_historical_mean(s_train, eval_dates)
                hw_cfg = self.config.get("models", {}).get("holt_winters", {})
                pred_hw, _ = fit_and_predict_holt_winters(
                    s_train,
                    eval_dates,
                    seasonal_periods=hw_cfg.get("seasonal_periods", 12),
                    trend=hw_cfg.get("trend", "add"),
                    seasonal=hw_cfg.get("seasonal", "add"),
                    clip_negative=bool(hw_cfg.get("clip_negative_for_evaluation", False)),
                )

                active = self.config.get("models", {}).get("active_model", "historical_mean")
                if active == "historical_mean":
                    chosen_pred, chosen_label = pred_hmean, "Promedio Histórico Mensual"
                elif active == "seasonal_naive":
                    chosen_pred, chosen_label = pred_snaive, "Seasonal Naive (Lag 12)"
                else:
                    chosen_pred, chosen_label = pred_hw, "Holt-Winters Aditivo"
                mlflow.log_param("model.active", chosen_label)
                self.audit.add_stage(
                    StageLog("Ajuste de modelo y parámetros", "COMPLETED", t0.isoformat(), datetime.now().isoformat())
                )

                # 5. Evaluación
                t0 = datetime.now()
                print("[5/8] Evaluación temporal (meses comparables)...")
                evaluable_idx, eval_info = build_evaluation_mask(
                    s_eval, excluded_periods=t_cfg.get("excluded_evaluation_periods") or []
                )
                mlflow.log_metric("eval.n_total", eval_info["n_total"])
                mlflow.log_metric("eval.n_evaluable", eval_info["n_evaluable"])
                print(
                    f"  Meses total={eval_info['n_total']} | evaluables={eval_info['n_evaluable']} | "
                    f"excluidos={eval_info['excluded_months']}"
                )

                metrics_hw = compute_metrics(s_eval, pred_hw, evaluable_index=evaluable_idx)
                metrics_snaive = compute_metrics(s_eval, pred_snaive, evaluable_index=evaluable_idx)
                metrics_hmean = compute_metrics(s_eval, pred_hmean, evaluable_index=evaluable_idx)
                metrics_active = compute_metrics(s_eval, chosen_pred, evaluable_index=evaluable_idx)

                def _fmt(m):
                    if m["n"] == 0:
                        return "N=0 (sin métricas)"
                    return (
                        f"MAE={m['mae']:,.2f} | RMSE={m['rmse']:,.2f} | "
                        f"APE_eps%={m['ape_eps_pct']:.2f} (N={m['n']})"
                    )

                print(f"  Activo ({chosen_label}): {_fmt(metrics_active)}")
                print(f"  Nota: {metrics_active.get('mape_note')}")
                print(f"  HW: {_fmt(metrics_hw)}")
                print(f"  Seasonal Naive: {_fmt(metrics_snaive)}")
                print(f"  Promedio histórico: {_fmt(metrics_hmean)}")
                for prefix, metrics in (
                    ("active", metrics_active),
                    ("hw", metrics_hw),
                    ("snaive", metrics_snaive),
                    ("hmean", metrics_hmean),
                ):
                    if metrics["n"] > 0:
                        mlflow.log_metric(f"eval.{prefix}.mae", metrics["mae"])
                        mlflow.log_metric(f"eval.{prefix}.rmse", metrics["rmse"])
                        mlflow.log_metric(f"eval.{prefix}.ape_eps_pct", metrics["ape_eps_pct"])
                    mlflow.log_metric(f"eval.{prefix}.n", metrics["n"])
                self.audit.add_stage(
                    StageLog("Evaluación temporal", "COMPLETED", t0.isoformat(), datetime.now().isoformat())
                )

                # 6–7. Candidato, aceptación, publicación
                t0 = datetime.now()
                print("[6/8] Candidato e integridad de salida completa...")
                df_candidate = self._build_estimates_frame(
                    chosen_pred, chosen_label, factors, estado="CANDIDATO"
                )
                required_out = [target] + list(secondary)
                integrity = validate_estimates_frame(
                    df_candidate, required_series=required_out, require_non_negative=True
                )
                if not integrity["ok"]:
                    raise ValueError("Integridad de salida fallida: " + "; ".join(integrity["reasons"]))

                print("[7/8] Regla de aceptación y publicación controlada...")
                acceptance = evaluate_acceptance_rule(
                    metrics_model=metrics_active,
                    metrics_baseline=metrics_snaive,
                    quality_passed=quality_report.critical_passed,
                    forecast_series=chosen_pred,
                    config=self.config,
                    estimates_df=df_candidate,
                    required_series=required_out,
                )
                is_accepted = bool(acceptance["is_accepted"])
                mlflow.log_metric("acceptance.is_accepted", 1 if is_accepted else 0)
                mlflow.set_tag("acceptance.decision", "APPROVED" if is_accepted else "REJECTED")
                mlflow.set_tag("acceptance.beats_baseline", str(acceptance["beats_baseline"]))
                print(f"  Decisión: {'APROBADO' if is_accepted else 'RECHAZADO'}")
                print(f"  Documentado beats_baseline={acceptance['beats_baseline']} (no obligatorio).")
                if not is_accepted:
                    for reason in acceptance["reasons"]:
                        print(f"  - {reason}")
                        self.audit.warnings.append(f"Aceptación: {reason}")

                estado_final = "APROBADO" if is_accepted else "CANDIDATO_RECHAZADO"
                df_estimaciones = self._build_estimates_frame(
                    chosen_pred, chosen_label, factors, estado=estado_final
                )
                # Revalidar tras marcar estado
                integrity2 = validate_estimates_frame(
                    df_estimaciones,
                    required_series=required_out,
                    require_non_negative=True,
                    require_approved_state=is_accepted,
                )
                if is_accepted and not integrity2["ok"]:
                    is_accepted = False
                    estado_final = "CANDIDATO_RECHAZADO"
                    df_estimaciones["estado_aprobacion"] = estado_final
                    acceptance["reasons"].extend(integrity2["reasons"])
                    print("  Rechazo por fallo de integridad post-factores.")

                candidate_path = os.path.join(self.reports_dir, f"estimaciones_candidatas_{self.run_id}.csv")
                acceptance_path = os.path.join(self.reports_dir, f"acceptance_{self.run_id}.json")
                df_estimaciones.to_csv(candidate_path, index=False, encoding="utf-8")
                with open(acceptance_path, "w", encoding="utf-8") as handle:
                    json.dump(acceptance, handle, indent=2, ensure_ascii=False, default=str)
                mlflow.log_artifact(candidate_path, artifact_path="estimaciones")
                mlflow.log_artifact(acceptance_path, artifact_path="acceptance")

                published = False
                prev_hash = file_sha256(self.approved_path)
                if is_accepted and self.publish:
                    pub = publish_approved_atomically(
                        df_estimaciones,
                        approved_path=self.approved_path,
                        backup_dir=self.backup_dir,
                        run_id=self.run_id,
                        lock_path=self.lock_path,
                    )
                    published = True
                    self.audit.published = True
                    mlflow.log_param("publish.previous_sha256", pub.get("previous_sha256") or "none")
                    mlflow.log_param("publish.new_sha256", pub.get("new_sha256") or "none")
                    print(f"  Publicado atómicamente: {self.approved_path}")
                    if pub.get("backup_file"):
                        print(f"  Respaldo: {pub['backup_file']}")
                elif not is_accepted:
                    print("  Candidato rechazado: no se altera estimaciones_aprobadas.csv.")
                    if prev_hash:
                        print(f"  Hash vigente preservado: {prev_hash[:16]}...")
                else:
                    print("  --no-publish: dry-run; versión aprobada intacta; candidato en reports/.")

                self.audit.add_stage(
                    StageLog(
                        "Aceptación y publicación",
                        "COMPLETED",
                        t0.isoformat(),
                        datetime.now().isoformat(),
                        f"aceptado={is_accepted}; publicado={published}",
                    )
                )

                # 8. Monitoreo
                t0 = datetime.now()
                print("[8/8] Monitoreo...")
                mon = verify_monitoring(df_series, df_estimaciones, self.config)
                for alert in mon.get("alerts", []):
                    print(f"  [ALERTA] {alert}")
                    self.audit.warnings.append(alert)
                mlflow.log_metric("monitoring.healthy", 1 if mon["all_healthy"] else 0)
                mlflow.log_metric("monitoring.alerts_count", mon["alerts_count"])
                self.audit.add_stage(
                    StageLog("Monitoreo continuo", "COMPLETED", t0.isoformat(), datetime.now().isoformat())
                )

                self.audit.end_time = datetime.now().isoformat()
                self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
                self.audit.status = "SUCCESS"
                audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
                self.audit.save(audit_path)
                mlflow.log_artifact(audit_path, artifact_path="audit_logs")
                mlflow.log_artifact(self.config_path, artifact_path="configuration")
                mlflow.set_tag("pipeline.status", "SUCCESS")

                print(f"\nPipeline OK en {self.audit.duration_seconds}s | publicado={published}")
                print("=======================================================\n")
                return {
                    "status": "SUCCESS",
                    "run_id": self.run_id,
                    "published": published,
                    "is_accepted": is_accepted,
                    "metrics": metrics_active,
                    "eval_info": eval_info,
                    "audit_file": audit_path,
                    "approved_sha256": file_sha256(self.approved_path),
                }

            except Exception as exc:
                self.audit.end_time = datetime.now().isoformat()
                self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
                if self.audit.status == "IN_PROGRESS":
                    self.audit.status = "FAILED"
                if str(exc) not in self.audit.errors:
                    self.audit.errors.append(str(exc))
                audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
                self.audit.save(audit_path)
                try:
                    mlflow.set_tag("pipeline.status", "FAILED")
                    mlflow.log_param("pipeline.error", str(exc)[:500])
                    if os.path.isfile(audit_path):
                        mlflow.log_artifact(audit_path, artifact_path="audit_logs")
                except Exception:
                    pass
                print(f"\n[ERROR] Pipeline falló: {exc}")
                print("Se conserva la versión aprobada vigente sin alteraciones.\n")
                raise


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline MLOps del Observatorio. Debe indicar --publish o --no-publish."
    )
    parser.add_argument("--config", default="config/pipeline_config.yaml")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--publish",
        action="store_true",
        help="Si el candidato es aceptado, publica atómicamente estimaciones_aprobadas.csv",
    )
    group.add_argument(
        "--no-publish",
        action="store_true",
        help="Dry-run: evalúa y guarda candidato/reportes sin alterar la versión aprobada",
    )
    args = parser.parse_args(argv)
    publish = bool(args.publish)
    TourismMLOpsPipeline(config_path=args.config, publish=publish).run()


if __name__ == "__main__":
    main()
