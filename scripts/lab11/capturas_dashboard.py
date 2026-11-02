"""Capturas reales del tablero con Google Chrome headless (CDP), ejercicio 6.

Uso:
  python scripts/lab11/capturas_dashboard.py <url_tablero> <dir_datos_que_lee_el_tablero> <escenario> [mlflow_uri]
Escenarios:
  vigente       Resumen, versión aprobada (MAE/periodo/fecha/versión + límites), observado vs aprobada,
                móvil y prueba de que cambiar filtros no crea runs en MLflow ni archivos de salida.
  restaurada    Versión aprobada mostrada tras una restauración.
  sin_aprobada  Tablero sin estimaciones_aprobadas.csv: aviso y vistas históricas utilizables.
Salida: evidencias/lab11/dashboard/<escenario>_*.png y capturas_<escenario>.json (descripción, run y hash).
"""
import base64
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from websockets.sync.client import connect

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "evidencias" / "lab11" / "dashboard"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Navegador:
    def __init__(self):
        self.puerto = puerto_libre()
        self.perfil = Path(tempfile.mkdtemp(prefix="lab11_chrome_"))
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={self.puerto}",
                                      f"--user-data-dir={self.perfil}", "--no-first-run", "--disable-gpu",
                                      "--hide-scrollbars", "--disable-extensions", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                paginas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.puerto}/json/list", timeout=1))
                ws = next(p["webSocketDebuggerUrl"] for p in paginas if p["type"] == "page")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        else:
            raise RuntimeError("Chrome no inició")
        self.ws = connect(ws, max_size=None, open_timeout=10)
        self.n = 0

    def cmd(self, metodo, params=None):
        self.n += 1
        ident = self.n
        self.ws.send(json.dumps({"id": ident, "method": metodo, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv(timeout=60))
            if r.get("id") == ident:
                if "error" in r:
                    raise RuntimeError(json.dumps(r["error"]))
                return r.get("result", {})

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", {"expression": f"JSON.stringify({expr})", "awaitPromise": True,
                                         "returnByValue": True})
        if "exceptionDetails" in r:
            raise RuntimeError(str(r["exceptionDetails"]))
        return json.loads(r["result"]["value"]) if r["result"].get("value") is not None else None

    def esperar(self, expr, segundos=40):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            try:
                if self.js(expr):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.3)
        return False

    def viewport(self, ancho, alto, movil=False):
        self.cmd("Emulation.setDeviceMetricsOverride", {"width": ancho, "height": alto, "deviceScaleFactor": 1,
                                                        "mobile": movil})

    def abrir(self, url):
        self.cmd("Page.enable")
        self.cmd("Page.navigate", {"url": url})
        ok = self.esperar("document.querySelectorAll('[role=tab]').length>=4 && "
                          "document.querySelectorAll('.js-plotly-plot').length>=1", 60)
        self.estable()
        return ok

    def estable(self, segundos=1.5):
        # Espera a que Streamlit termine de ejecutar el script (sin indicador de ejecución)
        self.esperar("!document.querySelector('[data-testid=stStatusWidget] [data-testid=stStatusWidgetRunningIcon]')", 20)
        time.sleep(segundos)

    def pestana(self, etiqueta):
        self.js("(()=>{const t=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==="
                + json.dumps(etiqueta) + ");t.click();return true})()")
        self.estable()

    def ir_a_texto(self, texto, selector="h1,h2,h3,h4,h5,p,summary,span"):
        return self.js("(()=>{const el=[...document.querySelectorAll(" + json.dumps(selector) + ")].find(x=>"
                       "x.offsetParent!==null && x.innerText && x.innerText.trim().startsWith(" + json.dumps(texto)
                       + "));if(!el)return false;el.scrollIntoView({block:'start'});"
                       "const c=document.querySelector('[data-testid=stMain]')||document.scrollingElement;"
                       "return true})()")

    def clic_texto(self, texto, selector="button,summary,label,p"):
        return self.js("(()=>{const el=[...document.querySelectorAll(" + json.dumps(selector) + ")].find(x=>"
                       "x.offsetParent!==null && x.innerText && x.innerText.trim()===" + json.dumps(texto)
                       + ");if(!el)return false;el.click();return true})()")

    def captura(self, nombre):
        r = self.cmd("Page.captureScreenshot", {"format": "png"})
        ruta = SALIDA / nombre
        ruta.write_bytes(base64.b64decode(r["data"]))
        return str(ruta.relative_to(RAIZ))

    def metricas_visibles(self):
        return self.js("[...document.querySelectorAll('[data-testid=stMetric]')].filter(x=>x.offsetParent!==null)"
                       ".map(x=>x.innerText.replace(/\\n+/g,' | '))")

    def textos_visibles(self, selector):
        return self.js("[...document.querySelectorAll(" + json.dumps(selector) + ")].filter(x=>x.offsetParent!==null)"
                       ".map(x=>x.innerText.trim()).filter(Boolean)")

    def cerrar(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            self.proc.wait(10)
            shutil.rmtree(self.perfil, ignore_errors=True)


def version_en_disco(data_dir):
    csv = Path(data_dir) / "estimaciones_aprobadas.csv"
    if not csv.exists():
        return {"archivo": "ausente"}
    import pandas as pd
    df = pd.read_csv(csv, usecols=["run_id", "fecha_generacion"])
    return {"run_id": str(df.run_id.iloc[0]), "fecha_generacion": str(df.fecha_generacion.iloc[0]),
            "sha256_csv": hashlib.sha256(csv.read_bytes()).hexdigest()}


def contar_runs(uri):
    req = urllib.request.Request(uri.rstrip("/") + "/api/2.0/mlflow/experiments/search",
                                 data=json.dumps({"max_results": 1000}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    exps = json.load(urllib.request.urlopen(req)).get("experiments", [])
    ids = [e["experiment_id"] for e in exps]
    req = urllib.request.Request(uri.rstrip("/") + "/api/2.0/mlflow/runs/search",
                                 data=json.dumps({"experiment_ids": ids, "max_results": 1000}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    return len(json.load(urllib.request.urlopen(req)).get("runs", []))


def archivos_salida(data_dir):
    base = Path(data_dir).parent
    return sorted(str(p.relative_to(base)) for d in ("reports", "logs") if (base / d).exists()
                  for p in (base / d).rglob("*") if p.is_file())


def main():
    url, data_dir, escenario = sys.argv[1:4]
    mlflow_uri = sys.argv[4] if len(sys.argv) > 4 else None
    SALIDA.mkdir(parents=True, exist_ok=True)
    nav = Navegador()
    registro = {"escenario": escenario, "url": url, "datos_leidos_por_tablero": data_dir,
                "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
                "version_en_disco": version_en_disco(data_dir), "navegador": "Google Chrome headless (CDP)",
                "capturas": []}

    def anotar(archivo, descripcion, **extra):
        registro["capturas"].append({"archivo": archivo, "descripcion": descripcion,
                                     "run_id_version_aprobada": registro["version_en_disco"].get("run_id"), **extra})
        print("captura:", archivo)

    try:
        nav.viewport(1440, 1000)
        assert nav.abrir(url), "el tablero no cargó"
        if escenario == "vigente":
            anotar(nav.captura("vigente_01_resumen_escritorio.png"),
                   "Pestaña Resumen (escritorio 1440x1000): KPIs históricos y aviso de año parcial 2026.",
                   avisos=nav.textos_visibles("[data-testid=stAlertContentInfo]"))
            nav.pestana("Modelos")
            nav.ir_a_texto("Estimación aprobada vigente")
            nav.clic_texto("Límites de esta versión", "summary,p")
            nav.estable(1)
            nav.ir_a_texto("Estimación aprobada vigente")
            anotar(nav.captura("vigente_02_modelos_version_aprobada.png"),
                   "Pestaña Modelos: MAE de la versión aprobada, periodo evaluado, fecha de generación, versión y "
                   "límites (2026 parcial, comparabilidad).", metricas=nav.metricas_visibles())
            nav.ir_a_texto("Observado, estimación aprobada y banco Lab 10")
            nav.estable(1)
            anotar(nav.captura("vigente_03_observado_vs_aprobada.png"),
                   "Gráfico V08: serie observada (azul) frente a la estimación aprobada retrospectiva (verde) y "
                   "banco Lab 10 (líneas discontinuas), diferenciados por leyenda, color y estilo.")
            # Filtros: no deben modelar ni iniciar runs
            antes = {"runs_mlflow": contar_runs(mlflow_uri) if mlflow_uri else None,
                     "archivos_reports_logs": archivos_salida(data_dir)}
            nav.pestana("Resumen")
            acciones = {"radio_mapa": nav.clic_texto("Mapa mundial interactivo", "label,p")}
            nav.estable(2)
            acciones["restablecer_filtros"] = nav.clic_texto("Restablecer filtros", "button,p")
            nav.estable(2)
            nav.pestana("Explorar datos")
            nav.pestana("Modelos")
            nav.estable(2)
            despues = {"runs_mlflow": contar_runs(mlflow_uri) if mlflow_uri else None,
                       "archivos_reports_logs": archivos_salida(data_dir)}
            registro["filtros_sin_modelado"] = {
                "acciones": acciones, "antes": {"runs_mlflow": antes["runs_mlflow"],
                                                "n_archivos": len(antes["archivos_reports_logs"])},
                "despues": {"runs_mlflow": despues["runs_mlflow"], "n_archivos": len(despues["archivos_reports_logs"])},
                "sin_cambios": antes == despues}
            print("filtros:", registro["filtros_sin_modelado"])
            nav.viewport(390, 844, movil=True)
            nav.abrir(url)
            nav.pestana("Modelos")
            nav.ir_a_texto("Estimación aprobada vigente")
            nav.estable(1)
            anotar(nav.captura("vigente_04_movil_modelos.png"),
                   "Vista móvil (390x844): bloque de la versión aprobada vigente.", metricas=nav.metricas_visibles())
        elif escenario == "restaurada":
            nav.pestana("Modelos")
            nav.ir_a_texto("Estimación aprobada vigente")
            nav.estable(1)
            anotar(nav.captura("restaurada_01_modelos_version_restaurada.png"),
                   "Tras restaurar el respaldo anterior: el tablero muestra la versión restaurada (fecha de "
                   "generación y MAE de esa versión).", metricas=nav.metricas_visibles())
        elif escenario == "sin_aprobada":
            nav.pestana("Modelos")
            nav.ir_a_texto("Estimación aprobada vigente")
            nav.estable(1)
            anotar(nav.captura("sin_aprobada_01_modelos_aviso.png"),
                   "Sin estimaciones_aprobadas.csv: aviso informativo, sin métricas inventadas.",
                   avisos=nav.textos_visibles("[data-testid=stAlertContentInfo],[data-testid=stAlertContentWarning]"))
            nav.pestana("Resumen")
            anotar(nav.captura("sin_aprobada_02_resumen_utilizable.png"),
                   "Sin versión aprobada: la vista histórica Resumen sigue funcionando.",
                   graficos=nav.js("document.querySelectorAll('.js-plotly-plot').length"))
        else:
            raise SystemExit(f"escenario desconocido: {escenario}")
    finally:
        nav.cerrar()
    (SALIDA / f"capturas_{escenario}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
