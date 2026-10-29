"""Módulo de Monitoreo y Recuperación (Laboratorio 11).
Implementa auditoría de ejecución, verificaciones de monitoreo continuo
(actualización, calidad, resultados con alertas de variación) y mecanismos de rollback.
"""
import os
import shutil
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


@dataclass
class StageLog:
    stage_name: str
    status: str  # 'STARTED', 'COMPLETED', 'FAILED', 'SKIPPED'
    start_time: str
    end_time: Optional[str] = None
    details: str = ""


@dataclass
class ExecutionAudit:
    run_id: str
    git_commit: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    stages: List[StageLog] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    published: bool = False
    status: str = "IN_PROGRESS"  # 'SUCCESS', 'FAILED', 'ABORTED'

    def add_stage(self, stage: StageLog):
        self.stages.append(stage)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def verify_monitoring(sources_df: pd.DataFrame, results_df: pd.DataFrame,
                        config: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta las tres verificaciones mínimas de monitoreo (Ejercicio 7.2).
    1. Actualización: comprueba si fuentes y resultados corresponden al último período esperado.
    2. Calidad: detecta cambios relevantes en faltantes, duplicados o cobertura.
    3. Resultados: detecta estimaciones negativas, no finitas o variaciones que excedan el umbral.
    """
    alerts = []
    checks = {}
    
    # 1. Verificación de Actualización
    max_fecha_fuente = pd.to_datetime(sources_df['fecha']).max()
    max_fecha_resultado = pd.to_datetime(results_df['fecha']).max()
    eval_end_cfg = pd.to_datetime(config.get('temporal_split', {}).get('eval_end', max_fecha_fuente))
    
    fuente_actualizada = max_fecha_fuente >= eval_end_cfg
    resultado_actualizado = max_fecha_resultado >= eval_end_cfg
    checks['actualizacion'] = {
        "status": "OK" if (fuente_actualizada and resultado_actualizado) else "ALERT",
        "max_fecha_fuente": str(max_fecha_fuente.date()),
        "max_fecha_resultado": str(max_fecha_resultado.date()),
        "esperado": str(eval_end_cfg.date())
    }
    if not (fuente_actualizada and resultado_actualizado):
        alerts.append(f"Monitoreo Actualización: Las fuentes ({max_fecha_fuente:%Y-%m}) o resultados ({max_fecha_resultado:%Y-%m}) no alcanzan el periodo esperado {eval_end_cfg:%Y-%m}.")

    # 2. Verificación de Calidad
    nulos_fuente = int(sources_df.isna().sum().sum())
    dups_fuente = int(sources_df.duplicated(subset=['serie', 'fecha']).sum())
    checks['calidad'] = {
        "status": "OK" if (nulos_fuente == 0 and dups_fuente == 0) else "ALERT",
        "nulos_fuente": nulos_fuente,
        "duplicados_fuente": dups_fuente
    }
    if nulos_fuente > 0 or dups_fuente > 0:
        alerts.append(f"Monitoreo Calidad: Se encontraron anomalías en fuentes (nulos: {nulos_fuente}, duplicados: {dups_fuente}).")

    # 3. Verificación de Resultados
    valores_est = pd.to_numeric(results_df['prediccion'], errors='coerce')
    negativos = int((valores_est < 0).sum())
    no_finitos = int(np.isinf(valores_est).sum() + valores_est.isna().sum())
    
    # Detección de variaciones elevadas (> umbral configurado)
    umbral_var = config.get('monitoring', {}).get('max_relative_variation_alert', 0.50)
    variacion_extrema = False
    ejemplos_var = []
    
    # Calcular cambio intermensual o interanual en la estimación
    res_sorted = results_df.sort_values('fecha').reset_index(drop=True)
    if 'serie' in res_sorted.columns:
        tot = res_sorted[res_sorted['serie'] == 'Total']
        if len(tot) > 1:
            diffs = tot['prediccion'].pct_change().abs()
            excesos = diffs[diffs > umbral_var]
            if not excesos.empty:
                variacion_extrema = True
                ejemplos_var = [f"Fecha {tot.loc[idx, 'fecha']}: variación {diffs.loc[idx]*100:.1f}%" for idx in excesos.head(3).index]
                
    checks['resultados'] = {
        "status": "ALERT" if (negativos > 0 or no_finitos > 0 or variacion_extrema) else "OK",
        "negativos": negativos,
        "no_finitos": no_finitos,
        "variacion_extrema_detectada": variacion_extrema,
        "umbral_variacion": umbral_var
    }
    if negativos > 0:
        alerts.append(f"Monitoreo Resultados: Se encontraron {negativos} estimaciones negativas.")
    if no_finitos > 0:
        alerts.append(f"Monitoreo Resultados: Se encontraron {no_finitos} estimaciones no finitas o NaN.")
    if variacion_extrema:
        alerts.append(f"Monitoreo Resultados (Alerta de revisión): Se detectaron variaciones superiores al {umbral_var*100:.0f}%. "
                      f"No demuestra pérdida de precisión per se, pero requiere revisión visual de directivos: {ejemplos_var}")

    return {
        "all_healthy": len(alerts) == 0,
        "alerts_count": len(alerts),
        "alerts": alerts,
        "checks": checks
    }


def backup_approved_version(current_approved_path: str, backup_dir: str, run_id: str) -> Optional[str]:
    """Crea una copia de seguridad con fecha y run_id de la versión aprobada actual."""
    if not os.path.isfile(current_approved_path):
        return None
        
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"estimaciones_aprobadas_backup_{ts}_{run_id[:8]}.csv"
    dest_path = os.path.join(backup_dir, backup_filename)
    
    shutil.copy2(current_approved_path, dest_path)
    return dest_path


def restore_approved_version(backup_filename: str, approved_path: str, backup_dir: str) -> bool:
    """Restaura una versión previamente aprobada desde el directorio de copias de seguridad."""
    src = os.path.join(backup_dir, backup_filename)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Copia de respaldo no encontrada: {src}")
        
    shutil.copy2(src, approved_path)
    return True

