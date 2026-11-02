"""Capturas reales de la UI de MLflow (servidor de Docker Compose) con Chrome headless.

Uso: python scripts/lab11/capturas_mlflow.py <mlflow_url> <mlflow_run_id_1> <mlflow_run_id_2>
Salida: evidencias/lab11/mlflow/ui_*.png y capturas_mlflow_ui.json
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capturas_dashboard import Navegador  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "evidencias" / "lab11" / "mlflow"


def main():
    url, r1, r2 = sys.argv[1:4]
    SALIDA.mkdir(parents=True, exist_ok=True)
    nav = Navegador()
    reg = {"generado": datetime.now().astimezone().isoformat(timespec="seconds"), "mlflow_url": url, "capturas": []}

    def ir(ruta, nombre, descripcion, espera_texto, desplazar_a=None):
        nav.cmd("Page.navigate", {"url": url.rstrip("/") + ruta})
        ok = nav.esperar(f"document.body && document.body.innerText.includes({json.dumps(espera_texto)})", 40)
        time.sleep(2.5)
        if desplazar_a:
            nav.js("(()=>{const el=[...document.querySelectorAll('h1,h2,h3,h4,span,div,button')].find(x=>"
                   "x.childElementCount===0 && x.innerText && x.innerText.trim()===" + json.dumps(desplazar_a) + ");"
                   "if(el){el.scrollIntoView({block:'start'});return true}return false})()")
            time.sleep(1.5)
        r = nav.cmd("Page.captureScreenshot", {"format": "png"})
        import base64
        (SALIDA / nombre).write_bytes(base64.b64decode(r["data"]))
        reg["capturas"].append({"archivo": f"evidencias/lab11/mlflow/{nombre}", "ruta_ui": ruta,
                                "descripcion": descripcion, "texto_esperado_encontrado": ok})
        print(nombre, ok)

    try:
        nav.viewport(1600, 1000)
        nav.cmd("Page.enable")
        ir("/#/experiments/1/runs", "ui_01_experimento_runs.png",
           "Experimento Observatorio_Turismo_Guatemala en el servidor MLflow de Docker Compose: lista de runs.",
           "run_2026")
        ir(f"/#/compare-runs?runs={json.dumps([r1, r2])}&experiments=[\"1\"]", "ui_02_comparacion_dos_runs.png",
           "Comparación de las dos ejecuciones dry-run usadas para reproducibilidad (tabla de detalles y "
           "parámetros; el gráfico de coordenadas paralelas requiere WebGL, no disponible en Chrome headless).",
           "eval.active.mae", desplazar_a="Run details")
        ir(f"/#/experiments/1/runs/{r1}", "ui_03_run_detalle.png",
           "Detalle de un run: parámetros (huellas SHA-256, split, factores), métricas y etiquetas.", "Parameters")
        ir(f"/#/experiments/1/runs/{r1}/artifacts", "ui_04_run_artefactos.png",
           "Artefactos registrados del run (configuración, fuentes, calidad, modelo, estimaciones, aceptación, "
           "monitoreo, auditoría).", "aceptacion")
    finally:
        nav.cerrar()
    (SALIDA / "capturas_mlflow_ui.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
