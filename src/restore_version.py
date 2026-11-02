"""Restauración segura de una versión aprobada desde el directorio de respaldos.

Uso:
    python -m src.restore_version --list
    python -m src.restore_version --backup <archivo.csv> --reason "motivo" [--operator nombre]

Antes de restaurar se valida: nombre/ruta dentro de backup_dir (sin path traversal
ni enlaces externos), CSV legible con esquema completo, todas las filas APROBADO,
un único run_id y, si existe manifiesto, hash SHA-256 y run_id coincidentes. La
versión vigente se respalda primero y el reemplazo es atómico. Solo se tocan
estimaciones_aprobadas.csv y su manifiesto; las fuentes institucionales no.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import yaml

from src.model_engine import validate_estimates_frame
from src.monitoring import (
    BACKUP_PREFIX,
    _fsync_dir,
    _write_fsync,
    backup_approved_version,
    exclusive_publish_lock,
    file_sha256,
    manifest_path_for,
    resolve_paths,
)

BACKUP_NAME_RE = re.compile(rf"^{BACKUP_PREFIX}[A-Za-z0-9_-]+\.csv$")
RESTORE_AUDIT_FILE = "restore_audit.jsonl"


class RestoreError(RuntimeError):
    """La restauración se rechaza sin modificar la versión vigente."""


def resolve_backup_path(backup_dir: str, name: str) -> Path:
    """Acepta solo un nombre simple de respaldo dentro de backup_dir."""
    if not name or name != os.path.basename(name) or "/" in name or "\\" in name:
        raise RestoreError(f"Nombre de respaldo no permitido (use solo el nombre del archivo): {name!r}")
    if not BACKUP_NAME_RE.fullmatch(name):
        raise RestoreError(f"El nombre no corresponde a un respaldo de estimaciones aprobadas: {name!r}")
    base = Path(backup_dir).resolve()
    candidate = (base / name).resolve()
    if candidate.parent != base:
        raise RestoreError("El respaldo resuelve fuera del directorio permitido.")
    if not candidate.is_file():
        raise RestoreError(f"No existe el respaldo {name} en {backup_dir}.")
    return candidate


def validate_backup(path: Path, required_series: Sequence[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {"archivo": path.name, "sha256": file_sha256(str(path)), "tiene_manifiesto": False}
    reasons: List[str] = []
    try:
        df = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        info.update(ok=False, motivos=[f"CSV ilegible: {exc}"])
        return info
    check = validate_estimates_frame(
        df, required_series=required_series, require_non_negative=True, require_approved_state=True
    )
    reasons.extend(check["reasons"])
    run_ids = df["run_id"].dropna().astype(str).unique().tolist() if "run_id" in df else []
    if len(run_ids) != 1:
        reasons.append(f"Debe contener exactamente un run_id; tiene {len(run_ids)}.")
    run_id = run_ids[0] if run_ids else None

    manifest_file = Path(manifest_path_for(str(path)))
    if manifest_file.is_file():
        info["tiene_manifiesto"] = True
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            reasons.append(f"Manifiesto ilegible: {exc}")
        else:
            if manifest.get("csv_sha256") != info["sha256"]:
                reasons.append("El SHA-256 del CSV no coincide con su manifiesto.")
            if run_id and manifest.get("run_id") != run_id:
                reasons.append("El run_id del manifiesto no coincide con el CSV.")
            if manifest.get("estado_aprobacion") != "APROBADO":
                reasons.append("El manifiesto no declara estado APROBADO.")
            info["mae"] = (manifest.get("metricas") or {}).get("mae")
    info.update(
        ok=not reasons,
        motivos=reasons,
        run_id=run_id,
        filas=int(len(df)),
        fecha_generacion=str(df["fecha_generacion"].iloc[0]) if "fecha_generacion" in df and len(df) else None,
    )
    return info


def list_backups(backup_dir: str, required_series: Sequence[str]) -> List[Dict[str, Any]]:
    if not os.path.isdir(backup_dir):
        return []
    names = sorted((n for n in os.listdir(backup_dir) if BACKUP_NAME_RE.fullmatch(n)), reverse=True)
    return [validate_backup(Path(backup_dir) / n, required_series) for n in names]


def _current_run_id(path: str) -> Optional[str]:
    try:
        return str(pd.read_csv(path, usecols=["run_id"], nrows=1)["run_id"].iloc[0])
    except (OSError, ValueError, IndexError, KeyError, pd.errors.ParserError):
        return None


def _operator(explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    if os.environ.get("RESTORE_OPERATOR"):
        return os.environ["RESTORE_OPERATOR"]
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "no_disponible"


def restore_backup(
    name: str,
    approved_path: str,
    backup_dir: str,
    lock_path: str,
    logs_dir: str,
    required_series: Sequence[str],
    reason: str,
    operator: Optional[str] = None,
) -> Dict[str, Any]:
    if not reason or not reason.strip():
        raise RestoreError("Debe indicar el motivo de la restauración (--reason).")
    source = resolve_backup_path(backup_dir, name)
    approved_dir = os.path.dirname(approved_path) or "."
    approved_manifest = manifest_path_for(approved_path)
    temp_csv = f"{approved_path}.restore.tmp"
    temp_manifest = f"{approved_manifest}.restore.tmp"

    with exclusive_publish_lock(lock_path):
        info = validate_backup(source, required_series)
        if not info["ok"]:
            raise RestoreError("Respaldo inválido; no se restaura: " + "; ".join(info["motivos"]))
        current_sha = file_sha256(approved_path)
        if current_sha == info["sha256"]:
            raise RestoreError("La versión seleccionada ya es la vigente; no se modifica nada.")
        current_run = _current_run_id(approved_path)
        try:
            _write_fsync(temp_csv, source.read_bytes())
            if file_sha256(temp_csv) != info["sha256"]:
                raise RestoreError("La copia temporal no coincide con el hash validado.")
            source_manifest = Path(manifest_path_for(str(source)))
            if source_manifest.is_file():
                _write_fsync(temp_manifest, source_manifest.read_bytes())
            safety = backup_approved_version(approved_path, backup_dir, label="prerestauracion")
            os.replace(temp_csv, approved_path)
            if os.path.isfile(temp_manifest):
                os.replace(temp_manifest, approved_manifest)
            elif os.path.isfile(approved_manifest):
                os.remove(approved_manifest)  # no describe la versión restaurada
            _fsync_dir(approved_dir)
        finally:
            for tmp in (temp_csv, temp_manifest):
                if os.path.isfile(tmp):
                    os.remove(tmp)

    record = {
        "evento": "RESTAURACION",
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "operador": _operator(operator),
        "motivo": reason.strip(),
        "respaldo_origen": source.name,
        "run_id_restaurado": info["run_id"],
        "sha256_restaurado": info["sha256"],
        "manifiesto_restaurado": info["tiene_manifiesto"],
        "run_id_reemplazado": current_run,
        "sha256_reemplazado": current_sha,
        "respaldo_seguridad": os.path.basename(safety) if safety else None,
        "sha256_vigente_verificado": file_sha256(approved_path),
    }
    os.makedirs(logs_dir, exist_ok=True)
    with open(os.path.join(logs_dir, RESTORE_AUDIT_FILE), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _settings(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    scope = config.get("scope", {})
    paths = resolve_paths(config)
    paths["required_series"] = [scope.get("target_series", "Total")] + list(scope.get("secondary_series", []))
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lista o restaura respaldos validados de estimaciones aprobadas.")
    parser.add_argument("--config", default="config/pipeline_config.yaml")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="Lista respaldos y su validación")
    action.add_argument("--backup", help="Nombre del archivo de respaldo a restaurar")
    parser.add_argument("--reason", help="Motivo de la restauración (obligatorio con --backup)")
    parser.add_argument("--operator", help="Persona u operador responsable (por defecto, usuario del sistema)")
    args = parser.parse_args(argv)
    s = _settings(args.config)

    if args.list:
        backups = list_backups(s["backup_dir"], s["required_series"])
        if not backups:
            print(f"No hay respaldos en {s['backup_dir']}.")
            return 0
        print(f"Respaldos en {s['backup_dir']} (más reciente primero):")
        for b in backups:
            estado = "VÁLIDO" if b["ok"] else "INVÁLIDO: " + "; ".join(b["motivos"])
            manifiesto = "con manifiesto" if b["tiene_manifiesto"] else "sin manifiesto"
            print(f"- {b['archivo']}\n    run_id={b.get('run_id')} | generado={b.get('fecha_generacion')} | "
                  f"{manifiesto} | sha256={str(b['sha256'])[:16]}… | {estado}")
        return 0

    try:
        record = restore_backup(
            args.backup, s["approved"], s["backup_dir"], s["lock"], s["logs_dir"],
            s["required_series"], reason=args.reason or "", operator=args.operator,
        )
    except RestoreError as exc:
        print(f"[RECHAZADO] {exc}")
        return 2
    print("Restauración completada:")
    for key, value in record.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
