"""Trazabilidad MLflow: URI único, disponibilidad verificable y metadatos reproducibles.

Política: si no se puede garantizar el registro en MLflow, el pipeline no publica
(TraceabilityError). No se usa una cola local alternativa.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
import time
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import mlflow
from mlflow.tracking import MlflowClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACKING_URI = "sqlite:///mlflow_store/mlflow.db"
CODE_FILES = ("pipeline.py", "src/*.py")
CODE_PATHSPEC = ("src", "pipeline.py", "config", "requirements.txt", "requirements.lock", "Dockerfile")
PACKAGES = (
    "mlflow", "pandas", "numpy", "statsmodels", "scipy", "streamlit", "plotly", "PyYAML", "SQLAlchemy",
)


class TraceabilityError(RuntimeError):
    """MLflow no garantiza el registro exigido; la publicación debe bloquearse."""


def resolve_tracking_uri(config: Dict[str, Any]) -> Tuple[str, str]:
    """MLFLOW_TRACKING_URI (entorno) tiene prioridad sobre el YAML."""
    env_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if env_uri:
        return env_uri, "entorno:MLFLOW_TRACKING_URI"
    return config.get("mlflow", {}).get("tracking_uri", DEFAULT_TRACKING_URI), "config:mlflow.tracking_uri"


def is_remote_uri(uri: str) -> bool:
    return uri.startswith(("http://", "https://"))


def connect_settings(config: Dict[str, Any]) -> Tuple[int, float]:
    cfg = config.get("mlflow", {})
    retries = int(os.environ.get("MLFLOW_CONNECT_RETRIES", cfg.get("connect_retries", 5)))
    delay = float(os.environ.get("MLFLOW_CONNECT_DELAY", cfg.get("connect_retry_delay_seconds", 3)))
    return max(1, retries), max(0.0, delay)


def ensure_tracking_available(uri: str, retries: int = 5, delay: float = 3.0) -> None:
    """Comprueba el servidor (/health) y la consulta al backend; no oculta errores."""
    if uri.startswith("sqlite:///"):
        db_path = uri[len("sqlite:///"):]
        if db_path and db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if is_remote_uri(uri):
                with urllib.request.urlopen(uri.rstrip("/") + "/health", timeout=5) as resp:
                    if resp.status != 200:
                        raise TraceabilityError(f"/health respondió {resp.status}")
            MlflowClient(tracking_uri=uri).search_experiments(max_results=1)
            return
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de conexión/backend cuenta
            last_error = exc
            print(f"  [MLflow] intento {attempt}/{retries} sin conexión a {uri}: {exc}")
            if attempt < retries:
                time.sleep(delay)
    raise TraceabilityError(
        f"MLflow no disponible en {uri} tras {retries} intentos: {last_error}. "
        "Se bloquea la ejecución para no publicar una versión sin trazabilidad."
    )


def setup_experiment(uri: str, name: str, artifact_location: str | None) -> str:
    """Fija URI/experimento. En local se usa artifact_location explícito; en servidor, el del servidor."""
    mlflow.set_tracking_uri(uri)
    client = MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name(name)
    if exp is None:
        if is_remote_uri(uri) or not artifact_location:
            exp_id = client.create_experiment(name)
        else:
            root = Path(artifact_location)
            root = root if root.is_absolute() else Path.cwd() / root
            root.mkdir(parents=True, exist_ok=True)
            exp_id = client.create_experiment(name, artifact_location=root.resolve().as_uri())
    else:
        exp_id = exp.experiment_id
    mlflow.set_experiment(experiment_id=exp_id)
    return exp_id


def _git(args: List[str]) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL, text=True
    ).strip()


def git_info() -> Dict[str, Any]:
    """Commit real de `git rev-parse HEAD`; si no hay repositorio, ausencia explícita.

    En contenedores (sin .git) puede declararse GIT_COMMIT; se marca como declarado,
    no verificado. Nunca se inventa un hash.
    """
    try:
        commit = _git(["rev-parse", "HEAD"])
        dirty = bool(_git(["status", "--porcelain", "--untracked-files=no", "--", *CODE_PATHSPEC]))
        return {"commit": commit, "source": "git rev-parse HEAD", "code_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        declared = os.environ.get("GIT_COMMIT", "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}", declared):
            return {"commit": declared, "source": "declarado en GIT_COMMIT (no verificado en contenedor)",
                    "code_dirty": None}
        return {"commit": "NO_DISPONIBLE", "source": "sin repositorio git ni GIT_COMMIT válido",
                "code_dirty": None}


def code_fingerprint() -> Dict[str, Any]:
    """SHA-256 del código del pipeline: versión verificable aun sin git."""
    files = sorted({p for pattern in CODE_FILES for p in PROJECT_ROOT.glob(pattern) if p.is_file()})
    per_file, total = {}, hashlib.sha256()
    for path in files:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        per_file[rel] = digest
        total.update(f"{rel}:{digest}\n".encode("utf-8"))
    return {"sha256": total.hexdigest(), "files": per_file, "line_endings": "normalizados a LF"}


def environment_info(seed: int) -> Dict[str, Any]:
    versions = {}
    for pkg in PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = "no instalado"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "random_seed": seed,
        "packages": versions,
    }


def verify_artifacts_logged(run_id: str, expected: Iterable[str]) -> None:
    """Relee el listado de artefactos del run; falla si alguno no quedó persistido."""
    client = MlflowClient()
    missing = []
    for rel in expected:
        folder, _, name = rel.rpartition("/")
        try:
            names = {Path(f.path).name for f in client.list_artifacts(run_id, folder or None)}
        except Exception as exc:  # noqa: BLE001
            raise TraceabilityError(f"No se pudo listar artefactos de MLflow ({folder}): {exc}") from exc
        if name not in names:
            missing.append(rel)
    if missing:
        raise TraceabilityError(f"Artefactos no persistidos en MLflow: {missing}")
