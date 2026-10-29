"""Pipeline MLOps Reproducible — Observatorio de Inteligencia Turística (Laboratorio 11).
Ejecuta de forma secuencial y atómica:
1. Lectura y huella digital de fuentes.
2. Controles de calidad automatizados (Gate 1).
3. Preparación y división temporal estricta.
4. Ajuste de modelo, factores de reparto y baselines.
5. Evaluación temporal retrospectiva.
6. Regla de aceptación de versión candidata (Gate 2).
7. Publicación controlada con respaldo histórico.
8. Verificaciones de monitoreo.
9. Trazabilidad integral en MLflow Tracking.
"""
import os
import sys
import uuid
import hashlib
import argparse
import subprocess
from datetime import datetime
from typing import Dict, Any, Tuple
import yaml
import numpy as np
import pandas as pd
import mlflow

from src.quality_checks import execute_all_quality_checks, QualityControlError
from src.model_engine import (
    calculate_repartition_factors,
    fit_and_predict_seasonal_naive,
    fit_and_predict_historical_mean,
    fit_and_predict_holt_winters,
    compute_metrics,
    evaluate_acceptance_rule
)
from src.monitoring import (
    ExecutionAudit,
    StageLog,
    verify_monitoring,
    backup_approved_version
)


def get_git_commit_hash() -> str:
    """Obtiene el hash del commit actual de Git para trazabilidad."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode("ascii").strip()
        return commit
    except Exception:
        return "git-unavailable-or-not-committed"


def compute_file_sha256(filepath: str) -> str:
    """Calcula la huella digital SHA-256 de un archivo para validar inmutabilidad."""
    if not os.path.isfile(filepath):
        return "file-not-found"
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def load_config(config_path: str) -> Dict[str, Any]:
    """Carga y valida el archivo de configuración YAML."""
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


class TourismMLOpsPipeline:
    def __init__(self, config_path: str, publish: bool = True):
        self.config_path = config_path
        self.publish = publish
        self.config = load_config(config_path)
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.start_time = datetime.now()
        self.git_commit = get_git_commit_hash()
        
        # Auditoría
        self.audit = ExecutionAudit(
            run_id=self.run_id,
            git_commit=self.git_commit,
            start_time=self.start_time.isoformat()
        )
        
        # Rutas
        self.data_dir = self.config.get("paths", {}).get("raw_data_dir", "data")
        self.series_path = os.path.join(self.data_dir, self.config.get("paths", {}).get("series_file", "series_mensuales.csv"))
        self.approved_path = os.path.join(self.data_dir, self.config.get("paths", {}).get("approved_file", "estimaciones_aprobadas.csv"))
        self.backup_dir = self.config.get("paths", {}).get("backup_dir", "data/backup_aprobadas")
        self.reports_dir = self.config.get("paths", {}).get("reports_dir", "reports")
        self.logs_dir = self.config.get("paths", {}).get("logs_dir", "logs")
        
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Semilla
        np.random.seed(self.config.get("pipeline", {}).get("random_seed", 42))

    def run(self) -> Dict[str, Any]:
        """Ejecuta el pipeline completo bajo control estricto de calidad y trazabilidad."""
        print(f"\n=======================================================")
        print(f"Iniciando Pipeline MLOps: {self.run_id}")
        print(f"Commit Git: {self.git_commit}")
        print(f"Timestamp: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=======================================================")
        
        # Configurar MLflow
        mlflow_cfg = self.config.get("mlflow", {})
        tracking_uri = mlflow_cfg.get("tracking_uri", "sqlite:///mlflow.db")
        exp_name = mlflow_cfg.get("experiment_name", "Observatorio_Turismo_Guatemala")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(exp_name)

        run_output = {}
        with mlflow.start_run(run_name=self.run_id) as mlrun:
            mlflow.set_tag("pipeline.name", self.config.get("pipeline", {}).get("name", "turismo_pipeline"))
            mlflow.set_tag("git.commit", self.git_commit)
            mlflow.set_tag("destination", self.config.get("pipeline", {}).get("destination", "Guatemala"))
            mlflow.set_tag("run_id", self.run_id)
            
            try:
                # -------------------------------------------------------------
                # Etapa 1: Lectura e Identificación de Fuentes
                # -------------------------------------------------------------
                t0 = datetime.now()
                source_sha = compute_file_sha256(self.series_path)
                mlflow.log_param("source.series_file", self.series_path)
                mlflow.log_param("source.sha256", source_sha)
                
                print(f"[1/8] Lectura de fuentes: {self.series_path} (SHA-256: {source_sha[:12]}...)")
                df_series = pd.read_csv(self.series_path)
                self.audit.add_stage(StageLog("Lectura de fuentes", "COMPLETED", t0.isoformat(), datetime.now().isoformat()))

                # -------------------------------------------------------------
                # Etapa 2: Controles de Calidad de Datos (Gate 1)
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[2/8] Ejecutando controles automáticos de calidad...")
                quality_report = execute_all_quality_checks(
                    df_series, self.run_id, t0.isoformat(), self.config
                )
                
                # Guardar reporte de calidad
                quality_report_path = os.path.join(self.reports_dir, f"quality_report_{self.run_id}.json")
                import json
                with open(quality_report_path, "w", encoding="utf-8") as f:
                    json.dump(quality_report.to_dict(), f, indent=2, ensure_ascii=False)
                mlflow.log_artifact(quality_report_path, artifact_path="quality_reports")
                
                # Métricas de calidad en MLflow
                mlflow.log_metric("qc.critical_passed", 1 if quality_report.critical_passed else 0)
                mlflow.log_metric("qc.warnings_count", quality_report.warnings_count)
                mlflow.log_metric("qc.errors_count", quality_report.errors_count)
                
                for res in quality_report.checks:
                    print(f"  - [{res.status}] {res.check_id} {res.name}: {res.details}")
                    if res.status == 'WARNING':
                        self.audit.warnings.append(f"{res.check_id}: {res.details}")

                if not quality_report.critical_passed:
                    err_msg = f"Fallo crítico en controles de calidad ({quality_report.errors_count} errores). El pipeline se detiene para preservar la versión aprobada existente."
                    self.audit.errors.append(err_msg)
                    self.audit.add_stage(StageLog("Controles de calidad", "FAILED", t0.isoformat(), datetime.now().isoformat(), err_msg))
                    self.audit.status = "ABORTED_QUALITY_FAILURE"
                    mlflow.set_tag("pipeline.status", "FAILED_QUALITY_CHECK")
                    raise QualityControlError(err_msg)
                    
                self.audit.add_stage(StageLog("Controles de calidad", "COMPLETED", t0.isoformat(), datetime.now().isoformat(), "6 controles validados"))

                # -------------------------------------------------------------
                # Etapa 3: Preparación y División Temporal Estricta
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[3/8] Preparación de datos y división temporal...")
                df_series['fecha'] = pd.to_datetime(df_series['fecha'])
                df_series['viajeros'] = pd.to_numeric(df_series['viajeros'])
                
                # Normalizar etiquetas ortográficas
                df_series['serie'] = df_series['serie'].str.replace('Via_A.*rea', 'Via_Aérea', regex=True).str.replace('Via_Mar.*tima', 'Via_Marítima', regex=True)
                
                t_cfg = self.config.get("temporal_split", {})
                train_start = pd.to_datetime(t_cfg.get("train_start", "2009-01-01"))
                train_end = pd.to_datetime(t_cfg.get("train_end", "2021-03-01"))
                eval_start = pd.to_datetime(t_cfg.get("eval_start", "2021-04-01"))
                eval_end = pd.to_datetime(t_cfg.get("eval_end", "2026-06-01"))
                
                mlflow.log_param("split.train_start", str(train_start.date()))
                mlflow.log_param("split.train_end", str(train_end.date()))
                mlflow.log_param("split.eval_start", str(eval_start.date()))
                mlflow.log_param("split.eval_end", str(eval_end.date()))
                
                train_mask = df_series['fecha'].between(train_start, train_end)
                eval_mask = df_series['fecha'].between(eval_start, eval_end)
                
                df_train = df_series[train_mask].copy()
                df_eval = df_series[eval_mask].copy()
                
                target_serie = self.config.get("scope", {}).get("target_series", "Total")
                s_train = df_train[df_train['serie'] == target_serie].set_index('fecha')['viajeros'].sort_index()
                s_eval = df_eval[df_eval['serie'] == target_serie].set_index('fecha')['viajeros'].sort_index()
                
                print(f"  Datos de ajuste: {train_start:%Y-%m} a {train_end:%Y-%m} (N={len(s_train)})")
                print(f"  Datos de evaluación: {eval_start:%Y-%m} a {eval_end:%Y-%m} (N={len(s_eval)})")
                self.audit.add_stage(StageLog("Preparación y división temporal", "COMPLETED", t0.isoformat(), datetime.now().isoformat()))

                # -------------------------------------------------------------
                # Etapa 4: Ajuste del Modelo, Baselines y Factores de Reparto
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[4/8] Ajuste de modelo, baselines y factores de reparto...")
                
                # 4a. Factores de reparto históricos (calculados solo en Train)
                repartition_factors = calculate_repartition_factors(df_train, target_series=target_serie)
                for s_name, factor in repartition_factors.items():
                    mlflow.log_param(f"factor_reparto.{s_name}", round(factor, 5))
                print(f"  Factores de reparto calculados en Train: { {k: round(v, 4) for k, v in repartition_factors.items()} }")
                
                # 4b. Baselines
                eval_dates = s_eval.index
                pred_snaive = fit_and_predict_seasonal_naive(s_train, eval_dates, lag=12)
                pred_hmean = fit_and_predict_historical_mean(s_train, eval_dates)
                
                # 4c. Modelos disponibles
                hw_cfg = self.config.get("models", {}).get("holt_winters", {})
                pred_hw, fitted_hw = fit_and_predict_holt_winters(
                    s_train, eval_dates,
                    seasonal_periods=hw_cfg.get("seasonal_periods", 12),
                    trend=hw_cfg.get("trend", "add"),
                    seasonal=hw_cfg.get("seasonal", "add")
                )
                
                active_model_name = self.config.get("models", {}).get("active_model", "holt_winters")
                if active_model_name == "historical_mean":
                    chosen_pred = pred_hmean
                    chosen_model_label = "Promedio Histórico Mensual"
                elif active_model_name == "seasonal_naive":
                    chosen_pred = pred_snaive
                    chosen_model_label = "Seasonal Naive (Lag 12)"
                else:
                    chosen_pred = pred_hw
                    chosen_model_label = "Holt-Winters Aditivo"

                mlflow.log_param("model.active", chosen_model_label)
                mlflow.log_param("model.seasonal_periods", hw_cfg.get("seasonal_periods", 12))
                self.audit.add_stage(StageLog("Ajuste de modelo y parámetros", "COMPLETED", t0.isoformat(), datetime.now().isoformat()))

                # -------------------------------------------------------------
                # Etapa 5: Evaluación Temporal Formal
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[5/8] Evaluación temporal formal...")
                metrics_hw = compute_metrics(s_eval, pred_hw)
                metrics_snaive = compute_metrics(s_eval, pred_snaive)
                metrics_hmean = compute_metrics(s_eval, pred_hmean)
                
                metrics_active = compute_metrics(s_eval, chosen_pred)

                print(f"  Modelo Activo ({chosen_model_label}) -> MAE: {metrics_active['mae']:,.2f} | RMSE: {metrics_active['rmse']:,.2f} | MAPE: {metrics_active['mape']:.2f}% (N={metrics_active['n']})")
                print(f"  Holt-Winters      -> MAE: {metrics_hw['mae']:,.2f} | RMSE: {metrics_hw['rmse']:,.2f} | MAPE: {metrics_hw['mape']:.2f}% (N={metrics_hw['n']})")
                print(f"  Seasonal Naive    -> MAE: {metrics_snaive['mae']:,.2f} | RMSE: {metrics_snaive['rmse']:,.2f} | MAPE: {metrics_snaive['mape']:.2f}% (N={metrics_snaive['n']})")
                print(f"  Promedio Histórico-> MAE: {metrics_hmean['mae']:,.2f} | RMSE: {metrics_hmean['rmse']:,.2f} | MAPE: {metrics_hmean['mape']:.2f}% (N={metrics_hmean['n']})")
                
                mlflow.log_metric("eval.active.mae", metrics_active["mae"])
                mlflow.log_metric("eval.active.rmse", metrics_active["rmse"])
                mlflow.log_metric("eval.active.mape", metrics_active["mape"])
                mlflow.log_metric("eval.hw.mae", metrics_hw["mae"])
                mlflow.log_metric("eval.hw.rmse", metrics_hw["rmse"])
                mlflow.log_metric("eval.snaive.mae", metrics_snaive["mae"])
                mlflow.log_metric("eval.snaive.rmse", metrics_snaive["rmse"])
                mlflow.log_metric("eval.hmean.mae", metrics_hmean["mae"])
                mlflow.log_metric("eval.hmean.rmse", metrics_hmean["rmse"])
                self.audit.add_stage(StageLog("Evaluación temporal", "COMPLETED", t0.isoformat(), datetime.now().isoformat()))

                # -------------------------------------------------------------
                # Etapa 6: Regla de Aceptación (Gate 2)
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[6/8] Evaluando regla de aceptación de versión candidata...")
                acceptance_result = evaluate_acceptance_rule(
                    metrics_model=metrics_active,
                    metrics_baseline=metrics_snaive,
                    quality_passed=quality_report.critical_passed,
                    forecast_series=chosen_pred,
                    config=self.config
                )
                
                is_accepted = acceptance_result["is_accepted"]
                mlflow.log_metric("acceptance.is_accepted", 1 if is_accepted else 0)
                mlflow.set_tag("acceptance.decision", "APPROVED" if is_accepted else "REJECTED")
                
                print(f"  Decisión de aceptación: {'APROBADO' if is_accepted else 'RECHAZADO'}")
                if not is_accepted:
                    print(f"  Causas de rechazo: {acceptance_result['reasons']}")
                    for r in acceptance_result['reasons']:
                        self.audit.warnings.append(f"Aceptación: {r}")
                self.audit.add_stage(StageLog("Regla de aceptación", "COMPLETED", t0.isoformat(), datetime.now().isoformat(), f"Aprobado: {is_accepted}"))

                # -------------------------------------------------------------
                # Etapa 7: Generación de Estimaciones y Publicación Controlada
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[7/8] Generación de estimaciones y publicación controlada...")
                
                # Construir DataFrame enriquecido de estimaciones
                destination = self.config.get("pipeline", {}).get("destination", "Guatemala")
                unit = self.config.get("scope", {}).get("unit_of_measure", "viajeros/mes")
                proc_version = self.config.get("pipeline", {}).get("version", "1.0.0")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                rows = []
                # 1. Total
                for dt, val in chosen_pred.items():
                    rows.append({
                        "destino": destination,
                        "serie": target_serie,
                        "modelo": chosen_model_label,
                        "fecha": dt.strftime("%Y-%m-%d"),
                        "prediccion": round(float(val), 2),
                        "unidad_medida": unit,
                        "run_id": self.run_id,
                        "fecha_generacion": now_str,
                        "version_procedimiento": proc_version,
                        "estado_aprobacion": "APROBADO" if is_accepted else "CANDIDATO_RECHAZADO"
                    })
                    
                # 2. Desagregaciones por factor de reparto
                secondary_series = self.config.get("scope", {}).get("secondary_series", [])
                for s_sec in secondary_series:
                    factor = repartition_factors.get(s_sec, 0.0)
                    for dt, val_tot in chosen_pred.items():
                        pred_sec = round(float(val_tot * factor), 2)
                        rows.append({
                            "destino": destination,
                            "serie": s_sec,
                            "modelo": f"{chosen_model_label} + Reparto Histórico",
                            "fecha": dt.strftime("%Y-%m-%d"),
                            "prediccion": pred_sec,
                            "unidad_medida": unit,
                            "run_id": self.run_id,
                            "fecha_generacion": now_str,
                            "version_procedimiento": proc_version,
                            "estado_aprobacion": "APROBADO" if is_accepted else "CANDIDATO_RECHAZADO"
                        })
                        
                df_estimaciones = pd.DataFrame(rows)
                
                # Guardar siempre copia de la corrida como artefacto
                candidate_path = os.path.join(self.reports_dir, f"estimaciones_candidatas_{self.run_id}.csv")
                df_estimaciones.to_csv(candidate_path, index=False, encoding="utf-8")
                mlflow.log_artifact(candidate_path, artifact_path="estimaciones")
                
                # Publicar solo si fue ACEPTADO y la bandera publish está activa
                published = False
                if is_accepted and self.publish:
                    # Crear respaldo de la versión actual aprobada
                    backup_file = backup_approved_version(self.approved_path, self.backup_dir, self.run_id)
                    if backup_file:
                        print(f"  Copia de seguridad creada: {backup_file}")
                        
                    # Reemplazo atómico de la versión aprobada
                    df_estimaciones.to_csv(self.approved_path, index=False, encoding="utf-8")
                    published = True
                    self.audit.published = True
                    print(f"  Versión aprobada publicada exitosamente en: {self.approved_path}")
                elif not is_accepted:
                    print("  AVISO: La versión candidata NO fue aprobada. Se preserva intacta la versión previa en el tablero.")
                else:
                    print("  AVISO: Pipeline ejecutado con publish=False; no se sobrescribió la versión vigente del tablero.")
                    
                self.audit.add_stage(StageLog("Publicación", "COMPLETED", t0.isoformat(), datetime.now().isoformat(), f"Publicado: {published}"))

                # -------------------------------------------------------------
                # Etapa 8: Monitoreo y Verificaciones Continuas
                # -------------------------------------------------------------
                t0 = datetime.now()
                print("[8/8] Ejecutando verificaciones de monitoreo continuo...")
                mon_result = verify_monitoring(df_series, df_estimaciones, self.config)
                
                for alert in mon_result.get("alerts", []):
                    print(f"  [ALERTA MONITOREO] {alert}")
                    self.audit.warnings.append(alert)
                    
                mlflow.log_metric("monitoring.healthy", 1 if mon_result["all_healthy"] else 0)
                mlflow.log_metric("monitoring.alerts_count", mon_result["alerts_count"])
                self.audit.add_stage(StageLog("Monitoreo continuo", "COMPLETED", t0.isoformat(), datetime.now().isoformat()))

                # Finalizar auditoría
                self.audit.end_time = datetime.now().isoformat()
                self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
                self.audit.status = "SUCCESS"
                
                audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
                self.audit.save(audit_path)
                mlflow.log_artifact(audit_path, artifact_path="audit_logs")
                mlflow.log_artifact(self.config_path, artifact_path="configuration")
                
                print(f"\nPipeline finalizado exitosamente en {self.audit.duration_seconds} segundos.")
                print(f"Estado de publicación: {'PUBLICADO' if published else 'PRESERVADA_ANTERIOR'}")
                print(f"=======================================================\n")
                
                run_output = {
                    "status": "SUCCESS",
                    "run_id": self.run_id,
                    "published": published,
                    "is_accepted": is_accepted,
                    "metrics": metrics_hw,
                    "audit_file": audit_path
                }
                return run_output

            except Exception as exc:
                self.audit.end_time = datetime.now().isoformat()
                self.audit.duration_seconds = round((datetime.now() - self.start_time).total_seconds(), 2)
                self.audit.status = "FAILED"
                self.audit.errors.append(str(exc))
                
                audit_path = os.path.join(self.logs_dir, f"audit_{self.run_id}.json")
                self.audit.save(audit_path)
                
                mlflow.set_tag("pipeline.status", "FAILED")
                mlflow.log_param("pipeline.error", str(exc))
                print(f"\n[ERROR CRÍTICO] Pipeline falló: {exc}")
                print("Se conservan los datos aprobados vigentes sin alteraciones.\n")
                raise exc


def main():
    parser = argparse.ArgumentParser(description="Pipeline MLOps para el Observatorio de Inteligencia Turística")
    parser.add_argument("--config", default="config/pipeline_config.yaml", help="Ruta al archivo de configuración YAML")
    parser.add_argument("--publish", action="store_true", default=True, help="Autorizar la publicación si es aprobada")
    parser.add_argument("--no-publish", dest="publish", action="store_false", help="Solo evaluar sin publicar al tablero")
    args = parser.parse_args()

    pipeline = TourismMLOpsPipeline(config_path=args.config, publish=args.publish)
    pipeline.run()


if __name__ == "__main__":
    main()
