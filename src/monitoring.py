"""Monitoreo operativo, publicación atómica y respaldos (Laboratorio 11).

Controles de monitoreo (ninguno inventa métricas):
1. Actualización: última observación real de cada fuente frente a la cobertura
   configurada (monitoring.expected_coverage_end) y última estimación producida
   frente a temporal_split.eval_end. No se usa la fecha de hoy.
2. Calidad: cobertura, tasa de nulos y duplicados con umbrales explícitos y, si
   existe, comparación con el JSON de monitoreo de la ejecución previa.
3. Resultados: no finitos, negativos y variaciones relativas mayores al umbral
   (intermensual por defecto). Base cero → variación no definida, sin dividir.
El error predictivo solo se recalcula con observaciones comparables (N>0).
"""
from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import numpy as np
import pandas as pd

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

BACKUP_PREFIX = "estimaciones_aprobadas_backup_"
MANIFEST_SUFFIX = ".manifest.json"
# Claves y agrupación de cobertura por fuente conocida
SOURCE_KEYS = {
    "series_mensuales.csv": (["serie", "fecha"], "serie"),
    "pais_mensual.csv": (["fecha", "pais"], None),
    "via_frontera.csv": (["fecha", "via", "frontera"], None),
}


@dataclass
class StageLog:
    stage_name: str
    status: str  # 'COMPLETED', 'FAILED', 'SKIPPED'
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
    # IN_PROGRESS | APROBADO_PUBLICADO | APROBADO_NO_PUBLICADO | RECHAZADO |
    # FALLIDO_CALIDAD | FALLIDO | BLOQUEADO_TRAZABILIDAD
    status: str = "IN_PROGRESS"
    failed_stage: Optional[str] = None
    publication_decision: str = "NO_PUBLICADO"
    mlflow_run_id: Optional[str] = None
    tracking_uri: Optional[str] = None

    def add_stage(self, stage: StageLog):
        self.stages.append(stage)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Monitoreo
# ---------------------------------------------------------------------------

def normalize_series_labels(serie: pd.Series) -> pd.Series:
    return (
        serie.astype(str)
        .str.replace(r"Via_A.*rea", "Via_Aérea", regex=True)
        .str.replace(r"Via_Mar.*tima", "Via_Marítima", regex=True)
    )


def _alert(control: str, severidad: str, mensaje: str, accion: str) -> Dict[str, str]:
    """severidad: ALERTA (acción requerida) | REVISION (revisar) | INFO."""
    return {"control": control, "severidad": severidad, "mensaje": mensaje, "accion": accion}


def _date_str(value) -> Optional[str]:
    return None if value is None or pd.isna(value) else str(pd.Timestamp(value).date())


def source_profile(df: pd.DataFrame, name: str, value_col: str = "viajeros") -> Dict[str, Any]:
    """Perfil reproducible de una fuente: filas, nulos, duplicados, cobertura y última observación."""
    key_cols, group_col = SOURCE_KEYS.get(name, (["fecha"], None))
    n = int(len(df))
    required = key_cols + [value_col]
    present = [c for c in required if c in df.columns]
    null_rows = int(df[present].isna().any(axis=1).sum()) if n and present else 0
    keys_ok = all(c in df.columns for c in key_cols)
    dups = int(df.duplicated(subset=key_cols).sum()) if n and keys_ok else 0

    fechas = pd.to_datetime(df["fecha"], errors="coerce") if "fecha" in df else pd.Series(dtype="datetime64[ns]")
    valores = pd.to_numeric(df[value_col], errors="coerce") if value_col in df else pd.Series(np.nan, index=df.index)
    observed = valores.notna() & fechas.notna()
    first, last = (fechas[observed].min(), fechas[observed].max()) if observed.any() else (None, None)

    per_group: Dict[str, Optional[str]] = {}
    if first is not None:
        months = len(pd.period_range(first, last, freq="M"))
        if group_col and group_col in df:
            groups = normalize_series_labels(df.loc[observed, group_col])
            periods = fechas[observed].dt.to_period("M")
            present_pairs = pd.DataFrame({"g": groups, "p": periods}).drop_duplicates()
            expected = months * present_pairs["g"].nunique()
            coverage = len(present_pairs) / expected if expected else 0.0
            last_by = fechas[observed].groupby(groups).max()
            per_group = {str(k): _date_str(v) for k, v in last_by.items()}
        else:
            coverage = fechas[observed].dt.to_period("M").nunique() / months
    else:
        coverage = 0.0

    return {
        "fuente": name,
        "filas": n,
        "columnas_faltantes": sorted(set(required) - set(df.columns)),
        "filas_con_nulos": null_rows,
        "tasa_nulos": round(null_rows / n, 6) if n else 0.0,
        "claves_duplicadas": dups,
        "tasa_duplicados": round(dups / n, 6) if n else 0.0,
        "primera_observacion": _date_str(first),
        "ultima_observacion_real": _date_str(last),
        "cobertura": round(float(coverage), 6),
        "ultima_observacion_por_serie": per_group,
    }


def monitor_freshness(
    profiles: Dict[str, Dict[str, Any]],
    results_df: Optional[pd.DataFrame],
    expected_sources_end: pd.Timestamp,
    expected_output_end: pd.Timestamp,
) -> Dict[str, Any]:
    alerts: List[Dict[str, str]] = []
    fuentes = {}
    for name, prof in profiles.items():
        last = prof.get("ultima_observacion_real")
        ok = last is not None and pd.Timestamp(last) >= expected_sources_end
        atrasadas = {
            s: d for s, d in prof.get("ultima_observacion_por_serie", {}).items()
            if d is None or pd.Timestamp(d) < expected_sources_end
        }
        fuentes[name] = {
            "ultima_observacion_real": last,
            "esperado": _date_str(expected_sources_end),
            "estado": "OK" if ok and not atrasadas else "ALERTA",
            "series_atrasadas": atrasadas,
        }
        if not ok:
            alerts.append(_alert(
                "actualizacion", "ALERTA",
                f"{name}: última observación real {last or 'ninguna'} no alcanza la cobertura "
                f"configurada {expected_sources_end:%Y-%m}.",
                "Verificar la entrega institucional o corregir monitoring.expected_coverage_end; "
                "no presentar la salida como actualizada.",
            ))
        elif atrasadas:
            alerts.append(_alert(
                "actualizacion", "ALERTA",
                f"{name}: series sin datos hasta {expected_sources_end:%Y-%m}: {atrasadas}.",
                "Revisar la carga de esas series antes de usar sus estimaciones.",
            ))
        if last is not None and pd.Timestamp(last) > expected_sources_end:
            alerts.append(_alert(
                "actualizacion", "INFO",
                f"{name}: hay observaciones hasta {last}, posteriores a la cobertura configurada.",
                "Actualizar expected_coverage_end y las ventanas temporales en una corrida planificada.",
            ))

    if results_df is None or results_df.empty:
        salida = {"estado": "NO_DISPONIBLE", "motivo": "La ejecución no produjo estimaciones."}
    else:
        last_est = pd.to_datetime(results_df["fecha"], errors="coerce").max()
        ok = pd.notna(last_est) and last_est >= expected_output_end
        salida = {
            "ultima_estimacion_producida": _date_str(last_est),
            "esperado": _date_str(expected_output_end),
            "estado": "OK" if ok else "ALERTA",
        }
        if not ok:
            alerts.append(_alert(
                "actualizacion", "ALERTA",
                f"La última estimación producida ({_date_str(last_est)}) no alcanza "
                f"{expected_output_end:%Y-%m} (fin configurado de la ventana).",
                "Revisar temporal_split y el modelo antes de aprobar.",
            ))
    return {"fuentes": fuentes, "salida": salida, "alertas": alerts}


def monitor_quality(
    profiles: Dict[str, Dict[str, Any]],
    previous: Optional[Dict[str, Any]],
    qcfg: Dict[str, Any],
) -> Dict[str, Any]:
    max_null = float(qcfg.get("max_null_rate", 0.0))
    max_dup = float(qcfg.get("max_duplicate_rate", 0.0))
    min_cov = float(qcfg.get("min_coverage_ratio", 1.0))
    max_drop = float(qcfg.get("max_row_drop_ratio_vs_previous", 0.0))
    max_null_inc = float(qcfg.get("max_null_rate_increase_vs_previous", 0.0))
    max_dup_inc = float(qcfg.get("max_duplicate_rate_increase_vs_previous", 0.0))
    prev_profiles = (previous or {}).get("perfiles", {})
    alerts: List[Dict[str, str]] = []
    detalle = {}

    for name, prof in profiles.items():
        hallazgos = []
        if prof["columnas_faltantes"]:
            hallazgos.append(f"faltan columnas {prof['columnas_faltantes']}")
        if prof["tasa_nulos"] > max_null:
            hallazgos.append(f"tasa de nulos {prof['tasa_nulos']:.4f} > {max_null}")
        if prof["tasa_duplicados"] > max_dup:
            hallazgos.append(f"tasa de duplicados {prof['tasa_duplicados']:.4f} > {max_dup}")
        if prof["cobertura"] < min_cov:
            hallazgos.append(f"cobertura {prof['cobertura']:.4f} < {min_cov}")

        comparacion: Dict[str, Any] = {"estado": "SIN_EJECUCION_PREVIA"}
        prev = prev_profiles.get(name)
        if prev:
            comparacion = {"run_id_previo": previous.get("run_id"), "filas_previas": prev.get("filas")}
            if prev.get("filas"):
                drop = (prev["filas"] - prof["filas"]) / prev["filas"]
                comparacion["caida_filas"] = round(drop, 6)
                if drop > max_drop:
                    hallazgos.append(f"filas {prev['filas']} → {prof['filas']} (caída {drop:.2%})")
            null_inc = prof["tasa_nulos"] - float(prev.get("tasa_nulos", 0.0))
            dup_inc = prof["tasa_duplicados"] - float(prev.get("tasa_duplicados", 0.0))
            comparacion.update({"aumento_tasa_nulos": round(null_inc, 6), "aumento_tasa_duplicados": round(dup_inc, 6)})
            if null_inc > max_null_inc:
                hallazgos.append(f"tasa de nulos aumentó {null_inc:.4f} frente a la ejecución previa")
            if dup_inc > max_dup_inc:
                hallazgos.append(f"tasa de duplicados aumentó {dup_inc:.4f} frente a la ejecución previa")
            prev_last, last = prev.get("ultima_observacion_real"), prof.get("ultima_observacion_real")
            if prev_last and (last is None or pd.Timestamp(last) < pd.Timestamp(prev_last)):
                hallazgos.append(f"última observación retrocedió de {prev_last} a {last}")

        detalle[name] = {"perfil": prof, "comparacion_previa": comparacion,
                         "estado": "ALERTA" if hallazgos else "OK", "hallazgos": hallazgos}
        if hallazgos:
            alerts.append(_alert(
                "calidad", "ALERTA", f"{name}: " + "; ".join(hallazgos) + ".",
                "Corregir la fuente en origen; no editar estimaciones aprobadas a mano.",
            ))
    return {
        "umbrales": {"max_null_rate": max_null, "max_duplicate_rate": max_dup, "min_coverage_ratio": min_cov,
                     "max_row_drop_ratio_vs_previous": max_drop},
        "fuentes": detalle,
        "alertas": alerts,
    }


def monitor_results(
    results_df: Optional[pd.DataFrame], threshold: float = 0.50, comparison: str = "intermensual"
) -> Dict[str, Any]:
    if results_df is None or results_df.empty:
        return {"estado": "NO_DISPONIBLE", "motivo": "Sin estimaciones que revisar.", "alertas": []}
    if comparison not in ("intermensual", "interanual"):
        raise ValueError(f"variation_comparison no soportado: {comparison}")
    lag = 1 if comparison == "intermensual" else 12
    df = results_df[["serie", "fecha", "prediccion"]].copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["prediccion"] = pd.to_numeric(df["prediccion"], errors="coerce")
    finite = np.isfinite(df["prediccion"].to_numpy(dtype=float, na_value=np.nan))
    no_finitos = int((~finite).sum())
    negativos = int((df["prediccion"] < 0).sum())
    alerts: List[Dict[str, str]] = []
    if no_finitos:
        alerts.append(_alert("resultados", "ALERTA", f"{no_finitos} estimaciones nulas o no finitas.",
                             "Bloquear uso de la salida y revisar el modelo."))
    if negativos:
        alerts.append(_alert("resultados", "ALERTA", f"{negativos} estimaciones negativas.",
                             "Revisar dominio del modelo; viajeros no puede ser negativo."))

    # Emparejar por fecha (no por posición) con el mes t-1 o t-12 de la misma serie
    prev = df.assign(fecha=df["fecha"] + pd.DateOffset(months=lag)).rename(columns={"prediccion": "anterior"})
    pares = df[finite].merge(prev, on=["serie", "fecha"], how="inner")
    pares = pares[np.isfinite(pares["anterior"].to_numpy(dtype=float))]
    base_cero = pares[(pares["anterior"] == 0) & (pares["prediccion"] != 0)]
    validos = pares[pares["anterior"] != 0].copy()
    validos["variacion"] = (validos["prediccion"] - validos["anterior"]) / validos["anterior"].abs()
    excesos = validos[validos["variacion"].abs() > threshold].sort_values(
        "variacion", key=lambda s: s.abs(), ascending=False
    )
    ejemplos = [
        f"{r.serie} {r.fecha:%Y-%m}: {r.variacion:+.1%}" for r in excesos.head(5).itertuples()
    ]
    if len(excesos):
        alerts.append(_alert(
            "resultados", "REVISION",
            f"{len(excesos)} variaciones {comparison}es mayores a {threshold:.0%} "
            f"en {excesos['serie'].nunique()} series. Ejemplos: {ejemplos}.",
            "Revisión visual por el equipo técnico; una variación extrema no prueba pérdida de precisión.",
        ))
    if len(base_cero):
        alerts.append(_alert(
            "resultados", "REVISION",
            f"{len(base_cero)} variaciones no definidas: el valor anterior es 0 y el actual no "
            f"(ej.: {[f'{r.serie} {r.fecha:%Y-%m}' for r in base_cero.head(3).itertuples()]}).",
            "Confirmar si el cero anterior es real; no se calcula porcentaje sobre base cero.",
        ))
    return {
        "estado": "ALERTA" if (no_finitos or negativos) else ("REVISION" if alerts else "OK"),
        "comparacion": comparison,
        "umbral_variacion": threshold,
        "negativos": negativos,
        "no_finitos": no_finitos,
        "pares_comparados": int(len(validos)),
        "variaciones_sobre_umbral": int(len(excesos)),
        "variaciones_base_cero": int(len(base_cero)),
        "variacion_maxima_abs": round(float(validos["variacion"].abs().max()), 6) if len(validos) else None,
        "ejemplos": ejemplos,
        "alertas": alerts,
    }


def monitor_predictive_error(observed_df: Optional[pd.DataFrame], results_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """MAE por serie solo sobre meses con observación y estimación finitas."""
    if observed_df is None or results_df is None or results_df.empty:
        return {"actualizado": False, "motivo": "Sin estimaciones u observaciones disponibles.", "por_serie": {}}
    obs = observed_df[["serie", "fecha", "viajeros"]].copy()
    obs["serie"] = normalize_series_labels(obs["serie"])
    obs["fecha"] = pd.to_datetime(obs["fecha"], errors="coerce")
    obs["viajeros"] = pd.to_numeric(obs["viajeros"], errors="coerce")
    est = results_df[["serie", "fecha", "prediccion"]].copy()
    est["fecha"] = pd.to_datetime(est["fecha"], errors="coerce")
    est["prediccion"] = pd.to_numeric(est["prediccion"], errors="coerce")
    pares = est.merge(obs, on=["serie", "fecha"], how="inner")
    pares = pares[np.isfinite(pares[["prediccion", "viajeros"]].to_numpy(dtype=float)).all(axis=1)]
    if pares.empty:
        return {"actualizado": False, "motivo": "Sin observaciones comparables; no se actualiza el error.",
                "por_serie": {}}
    por_serie = {}
    for serie, g in pares.groupby("serie"):
        err = g["prediccion"] - g["viajeros"]
        por_serie[str(serie)] = {
            "n": int(len(g)),
            "mae": round(float(err.abs().mean()), 2),
            "rmse": round(float(np.sqrt((err ** 2).mean())), 2),
            "inicio": _date_str(g["fecha"].min()),
            "fin": _date_str(g["fecha"].max()),
        }
    return {"actualizado": True, "n_pares": int(len(pares)), "por_serie": por_serie}


def load_previous_monitoring(reports_dir: str, exclude_run_id: str) -> Optional[Dict[str, Any]]:
    """Perfiles de fuentes de la ejecución previa más reciente con JSON de monitoreo."""
    candidates = [
        p for p in glob.glob(os.path.join(reports_dir, "monitoring_*.json"))
        if exclude_run_id not in os.path.basename(p)
    ]
    for path in sorted(candidates, key=os.path.getmtime, reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            perfiles = {k: v["perfil"] for k, v in data.get("calidad", {}).get("fuentes", {}).items()}
            if perfiles:
                return {"run_id": data.get("run_id"), "archivo": os.path.basename(path), "perfiles": perfiles}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def run_monitoring(
    config: Dict[str, Any],
    run_id: str,
    source_frames: Dict[str, pd.DataFrame],
    results_df: Optional[pd.DataFrame] = None,
    previous: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mcfg = config.get("monitoring", {})
    t_cfg = config.get("temporal_split", {})
    expected_sources = pd.Timestamp(mcfg.get("expected_coverage_end") or t_cfg.get("eval_end"))
    expected_output = pd.Timestamp(t_cfg.get("eval_end") or expected_sources)
    threshold = float(mcfg.get("max_relative_variation_alert", 0.50))
    comparison = mcfg.get("variation_comparison", "intermensual")

    profiles = {name: source_profile(df, name) for name, df in source_frames.items() if df is not None}
    actualizacion = monitor_freshness(profiles, results_df, expected_sources, expected_output)
    calidad = monitor_quality(profiles, previous, mcfg.get("quality", {}))
    resultados = monitor_results(results_df, threshold, comparison)
    error = monitor_predictive_error(source_frames.get("series_mensuales.csv"), results_df)
    alerts = actualizacion.pop("alertas") + calidad.pop("alertas") + resultados.pop("alertas")
    accionables = [a for a in alerts if a["severidad"] != "INFO"]
    return {
        "run_id": run_id,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "configuracion": {
            "cobertura_esperada_fuentes": _date_str(expected_sources),
            "cobertura_esperada_salidas": _date_str(expected_output),
            "comparacion_variacion": comparison,
            "umbral_variacion": threshold,
            "ejecucion_previa_comparada": (previous or {}).get("run_id"),
        },
        "actualizacion": actualizacion,
        "calidad": calidad,
        "resultados": resultados,
        "error_predictivo": error,
        "alertas": alerts,
        "alerts_count": len(accionables),
        "all_healthy": not accionables,
    }


def save_json(data: Dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
    return path


# ---------------------------------------------------------------------------
# Publicación, respaldos y bloqueo
# ---------------------------------------------------------------------------

def resolve_paths(config: Dict[str, Any]) -> Dict[str, str]:
    """Rutas de entrada/salida compartidas por pipeline y restauración."""
    paths = config.get("paths", {})
    data_dir = paths.get("raw_data_dir", "data")
    output_dir = paths.get("output_dir", data_dir)
    logs_dir = paths.get("logs_dir", "logs")
    return {
        "data_dir": data_dir,
        "output_dir": output_dir,
        "approved": os.path.join(output_dir, paths.get("approved_file", "estimaciones_aprobadas.csv")),
        "backup_dir": paths.get("backup_dir", os.path.join(output_dir, "backup_aprobadas")),
        "reports_dir": paths.get("reports_dir", "reports"),
        "logs_dir": logs_dir,
        "lock": paths.get("publish_lock_file", os.path.join(logs_dir, "publish.lock")),
    }


def file_sha256(filepath: str) -> Optional[str]:
    """Huella SHA-256 de un archivo; None si no existe."""
    if not os.path.isfile(filepath):
        return None
    sha = hashlib.sha256()
    with open(filepath, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def manifest_path_for(csv_path: str) -> str:
    return os.path.splitext(csv_path)[0] + MANIFEST_SUFFIX


def estimates_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialización única (LF, UTF-8) para candidato, artefacto MLflow y versión publicada."""
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


@contextlib.contextmanager
def exclusive_publish_lock(lock_path: str) -> Iterator[None]:
    """Exclusión mutua entre publicación y restauración (fcntl en POSIX, msvcrt en Windows)."""
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()


def _write_fsync(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: str) -> None:
    dir_fd = None
    try:
        dir_fd = os.open(path or ".", os.O_RDONLY)
        os.fsync(dir_fd)
    except (AttributeError, OSError):
        pass  # Windows no permite fsync de directorios
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def _safe_token(text: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(text))[:64] or "desconocido"


def backup_approved_version(current_approved_path: str, backup_dir: str, label: Optional[str] = None) -> Optional[str]:
    """Copia la versión vigente (CSV y manifiesto si existe); el nombre lleva el run de origen.

    Debe llamarse dentro de exclusive_publish_lock.
    """
    if not os.path.isfile(current_approved_path):
        return None
    try:
        origin = pd.read_csv(current_approved_path, usecols=["run_id"], nrows=1)["run_id"].iloc[0]
    except (ValueError, IndexError, KeyError, OSError, pd.errors.ParserError):
        origin = "desconocido"
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = f"_{_safe_token(label)}" if label else ""
    dest_path = os.path.join(backup_dir, f"{BACKUP_PREFIX}{ts}_{_safe_token(origin)}{suffix}.csv")
    shutil.copy2(current_approved_path, dest_path)
    manifest = manifest_path_for(current_approved_path)
    if os.path.isfile(manifest):
        shutil.copy2(manifest, manifest_path_for(dest_path))
    return dest_path


def publish_approved_atomically(
    df: pd.DataFrame,
    approved_path: str,
    backup_dir: str,
    run_id: str,
    lock_path: Optional[str] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Temporal + fsync + verificación + respaldo + os.replace (CSV y luego manifiesto).

    Si falla antes del reemplazo, la versión aprobada previa queda intacta. Entre el
    reemplazo del CSV y el del manifiesto, el tablero detecta hash distinto y no
    muestra metadatos no verificados (falla cerrada).
    """
    approved_dir = os.path.dirname(approved_path) or "."
    os.makedirs(approved_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    lock = lock_path or os.path.join(approved_dir, ".publish.lock")
    manifest_path = manifest_path_for(approved_path)
    temp_csv = f"{approved_path}.{run_id}.tmp"
    temp_manifest = f"{manifest_path}.{run_id}.tmp"
    data = estimates_csv_bytes(df)
    expected_sha = hashlib.sha256(data).hexdigest()

    with exclusive_publish_lock(lock):
        prev_hash = file_sha256(approved_path)
        try:
            _write_fsync(temp_csv, data)
            probe = pd.read_csv(temp_csv)
            if probe.empty or list(probe.columns) != list(df.columns) or len(probe) != len(df):
                raise ValueError("Verificación del CSV temporal falló (vacío, columnas o filas distintas).")
            if file_sha256(temp_csv) != expected_sha:
                raise ValueError("El hash del CSV temporal no coincide con el contenido preparado.")
            if manifest is not None:
                manifest = dict(manifest, csv_sha256=expected_sha)
                _write_fsync(temp_manifest, json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"))

            backup_file = backup_approved_version(approved_path, backup_dir)
            os.replace(temp_csv, approved_path)
            if manifest is not None:
                os.replace(temp_manifest, manifest_path)
            elif os.path.isfile(manifest_path):
                os.remove(manifest_path)  # el manifiesto anterior ya no describe el CSV vigente
            _fsync_dir(approved_dir)
            return {
                "published": True,
                "approved_path": approved_path,
                "manifest_path": manifest_path if manifest is not None else None,
                "backup_file": backup_file,
                "previous_sha256": prev_hash,
                "new_sha256": file_sha256(approved_path),
            }
        finally:
            for tmp in (temp_csv, temp_manifest):
                if os.path.isfile(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
