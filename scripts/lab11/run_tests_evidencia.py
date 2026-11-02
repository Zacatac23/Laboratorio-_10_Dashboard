"""Ejecuta la suite unittest y guarda evidencia textual + reporte PASS/FAIL/SKIP.

Uso: python scripts/lab11/run_tests_evidencia.py [--docker]
Salida: evidencias/lab11/tests_unitarios.txt y evidencias/lab11/tests_resultados.json
"""
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "evidencias" / "lab11"
# (sin parseo textual)
_ = re.compile(r"^(\w+) \(([\w.]+)\)(?:\s*\n?.*?)? \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$")


def main() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
    env = dict(os.environ)
    if "--docker" in sys.argv:
        env["RUN_DOCKER_TESTS"] = "1"
    inicio = datetime.now().astimezone()
    proc = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, env=env)
    fin = datetime.now().astimezone()
    salida = proc.stderr  # unittest escribe el reporte en stderr

    # Estado por prueba: segunda pasada con runner estructurado (los avisos de Streamlit
    # se intercalan en stderr y hacen poco fiable parsear la salida textual).
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "r.json"
        proc2 = subprocess.run([sys.executable, "-B", str(RAIZ / "scripts/lab11/_runner_estructurado.py"), str(destino)],
                               cwd=RAIZ, capture_output=True, text=True, env=env)
        estructura = json.loads(destino.read_text(encoding="utf-8"))
    resultados = estructura["filas"]
    m_ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", salida)
    resumen = {
        "comando": " ".join(["python"] + cmd[1:]),
        "RUN_DOCKER_TESTS": env.get("RUN_DOCKER_TESTS", ""),
        "inicio": inicio.isoformat(timespec="seconds"),
        "fin": fin.isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "tests_ejecutados_unittest": int(m_ran.group(1)) if m_ran else None,
        "duracion_s": float(m_ran.group(2)) if m_ran else None,
        "PASS": sum(r["estado"] == "PASS" for r in resultados),
        "FAIL": sum(r["estado"] == "FAIL" for r in resultados),
        "ERROR": sum(r["estado"] == "ERROR" for r in resultados),
        "tests_runner_estructurado": estructura["testsRun"],
        "codigo_salida_runner_estructurado": proc2.returncode,
        "SKIP": sum(r["estado"] == "SKIP" for r in resultados),
        "codigo_salida": proc.returncode,
    }
    sufijo = "_docker" if "--docker" in sys.argv else ""
    resumen["log"] = f"evidencias/lab11/tests_unitarios{sufijo}.txt"
    (SALIDA / f"tests_resultados{sufijo}.json").write_text(
        json.dumps({"resumen": resumen, "resultados": resultados}, ensure_ascii=False, indent=2), encoding="utf-8")
    cab = "\n".join(f"{k}: {v}" for k, v in resumen.items())
    (SALIDA / f"tests_unitarios{sufijo}.txt").write_text(
        f"{cab}\n\n===== STDOUT =====\n{proc.stdout}\n===== STDERR (reporte unittest) =====\n{salida}", encoding="utf-8")
    print(cab)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
