"""Pruebas controladas de fallo, monitoreo y restauración (ejercicio 7) sobre una COPIA temporal.

No modifica data/ del repositorio: copia los CSV y la versión aprobada vigente a una carpeta temporal,
inyecta fallos uno por uno, verifica detección y contención (SHA-256 del aprobado), corrige, publica
una segunda versión, demuestra las tres clases de monitoreo y restaura la versión anterior con
src.restore_version, comprobando hash, manifiesto y lectura desde el tablero (data_logic).

Uso: python scripts/lab11/fallos_controlados.py <tracking_uri>
     (p. ej. http://127.0.0.1:5001 para registrar en el MLflow de Docker Compose)
Salida: evidencias/lab11/recuperacion/fallos_controlados.json (+ log por stdout)
"""
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.chdir(RAIZ)  # el pipeline resuelve config relativa al repo

from data_logic import cargar_version_aprobada  # noqa: E402
from src.monitoring import run_monitoring  # noqa: E402
from src.pipeline import TourismMLOpsPipeline  # noqa: E402
from src.restore_version import list_backups, restore_backup  # noqa: E402

EXPERIMENTO = "Observatorio_Turismo_Guatemala_pruebas_controladas"
SALIDA = RAIZ / "evidencias" / "lab11" / "recuperacion"
FUENTES = ["series_mensuales.csv", "pais_mensual.csv", "via_frontera.csv", "pronosticos.csv"]


def sha(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def hashes_repo_data():
    return {p.name: sha(p) for p in sorted((RAIZ / "data").glob("*")) if p.is_file()}


class Entorno:
    def __init__(self, uri):
        self.tmp = Path(tempfile.mkdtemp(prefix="lab11_fallos_"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        for f in FUENTES + ["estimaciones_aprobadas.csv", "estimaciones_aprobadas.manifest.json"]:
            shutil.copy2(RAIZ / "data" / f, self.data / f)
        self.original_series = pd.read_csv(self.data / "series_mensuales.csv")
        cfg = yaml.safe_load((RAIZ / "config" / "pipeline_config.yaml").read_text(encoding="utf-8"))
        cfg["paths"].update(raw_data_dir=str(self.data), output_dir=str(self.data),
                            backup_dir=str(self.data / "backup_aprobadas"), reports_dir=str(self.tmp / "reports"),
                            logs_dir=str(self.tmp / "logs"), publish_lock_file=str(self.tmp / "logs" / "publish.lock"))
        cfg["mlflow"].update(tracking_uri=uri, experiment_name=EXPERIMENTO, connect_retries=2,
                             connect_retry_delay_seconds=1)
        self.cfg = cfg
        self.cfg_path = self.tmp / "config.yaml"
        self.cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    @property
    def aprobado(self):
        return self.data / "estimaciones_aprobadas.csv"

    @property
    def manifiesto(self):
        return self.data / "estimaciones_aprobadas.manifest.json"

    def backups(self):
        d = self.data / "backup_aprobadas"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []

    def escribir_series(self, df):
        df.to_csv(self.data / "series_mensuales.csv", index=False)

    def ejecutar(self, publish=True):
        pipe = TourismMLOpsPipeline(str(self.cfg_path), publish=publish)
        out = {"run_id": pipe.run_id}
        try:
            res = pipe.run()
            out.update(estado=res["status"], mlflow_run_id=res.get("mlflow_run_id"), excepcion=None)
        except Exception as exc:  # noqa: BLE001
            out.update(excepcion=f"{type(exc).__name__}: {exc}")
            audit = Path(pipe.audit_path) if getattr(pipe, "audit_path", None) else None
            if audit and audit.exists():
                a = json.loads(audit.read_text(encoding="utf-8"))
                out.update(estado=a.get("status"), mlflow_run_id=a.get("mlflow_run_id"),
                           etapa_fallida=a.get("failed_stage"))
        qc = self.tmp / "reports" / f"quality_report_{pipe.run_id}.json"
        if qc.exists():
            q = json.loads(qc.read_text(encoding="utf-8"))
            out["qc_no_aprobados"] = [{"id": c["check_id"], "estado": c["status"], "detalle": c["details"][:200]}
                                      for c in q["checks"] if c["status"] not in ("PASSED",)]
        out["audit_local"] = str(Path(pipe.audit_path).relative_to(self.tmp)) if getattr(pipe, "audit_path", None) else None
        return out


def main():
    uri = sys.argv[1]
    data_repo_antes = hashes_repo_data()
    e = Entorno(uri)
    ev = {"generado": datetime.now().astimezone().isoformat(timespec="seconds"), "tracking_uri": uri,
          "experimento_mlflow": EXPERIMENTO, "entorno_temporal": str(e.tmp),
          "nota": "Copia temporal de data/; los datos institucionales del repositorio no se modifican."}
    v_a = {"sha256_csv": sha(e.aprobado), "sha256_manifiesto": sha(e.manifiesto),
           "run_id": pd.read_csv(e.aprobado)["run_id"].iloc[0]}
    ev["version_aprobada_inicial_A"] = v_a
    print("Versión aprobada inicial A:", v_a)

    # ---- 1. Inyección de fallos (uno por uno) -------------------------------------------------
    s = e.original_series
    tren = pd.to_datetime(s["fecha"]).between(e.cfg["temporal_split"]["train_start"], e.cfg["temporal_split"]["train_end"])
    inyecciones = {
        "columna_indispensable_ausente (viajeros)": s.drop(columns=["viajeros"]),
        "clave_duplicada (serie,fecha)": pd.concat([s, s.iloc[[10]]], ignore_index=True),
        "conteo_negativo (Total 2015-03 = -500)": s.assign(viajeros=s["viajeros"].where(
            ~((s["serie"] == "Total") & (s["fecha"] == "2015-03-01")), -500.0)),
        "denominador_cero (todas las series = 0 en Train)": s.assign(viajeros=s["viajeros"].where(~tren, 0.0)),
    }
    ev["fallos_inyectados"] = []
    for nombre, df in inyecciones.items():
        print(f"\n=== Inyección: {nombre}")
        backups_antes = e.backups()
        e.escribir_series(df)
        r = e.ejecutar(publish=True)
        r.update(falla=nombre, sha256_aprobado_despues=sha(e.aprobado),
                 aprobado_intacto=sha(e.aprobado) == v_a["sha256_csv"] and sha(e.manifiesto) == v_a["sha256_manifiesto"],
                 candidato_no_publicado=e.backups() == backups_antes and sha(e.aprobado) == v_a["sha256_csv"])
        print({k: r[k] for k in ("estado", "excepcion", "aprobado_intacto")})
        ev["fallos_inyectados"].append(r)

    # ---- 2. Corrección y recuperación: publica la versión B -----------------------------------
    print("\n=== Corrección: se restituye series_mensuales.csv original y se re-ejecuta")
    e.escribir_series(e.original_series)
    r = e.ejecutar(publish=True)
    v_b = {"sha256_csv": sha(e.aprobado), "sha256_manifiesto": sha(e.manifiesto),
           "run_id": pd.read_csv(e.aprobado)["run_id"].iloc[0]}
    ev["recuperacion"] = dict(r, version_B=v_b, respaldos=e.backups(),
                              versiones_distintas=v_b["sha256_csv"] != v_a["sha256_csv"])
    print(ev["recuperacion"]["estado"], v_b)

    # ---- 3. Fallo de escritura y de trazabilidad (no deben dejar salida parcial) ----------------
    fallos_infra = []
    print("\n=== Fallo de escritura simulado (os.replace) durante la publicación")
    with mock.patch("src.monitoring.os.replace", side_effect=OSError("fallo simulado de escritura")):
        r = e.ejecutar(publish=True)
    r.update(falla="escritura (os.replace lanza OSError)", aprobado_intacto=sha(e.aprobado) == v_b["sha256_csv"]
             and sha(e.manifiesto) == v_b["sha256_manifiesto"],
             temporales_residuales=[p.name for p in e.data.glob("*.tmp")])
    fallos_infra.append(r)
    print({k: r[k] for k in ("estado", "excepcion", "aprobado_intacto", "temporales_residuales")})

    print("\n=== MLflow inaccesible (trazabilidad no garantizada)")
    cfg_mal = copy.deepcopy(e.cfg)
    cfg_mal["mlflow"].update(tracking_uri="http://127.0.0.1:9", connect_retries=1, connect_retry_delay_seconds=0)
    e.cfg_path.write_text(yaml.safe_dump(cfg_mal, allow_unicode=True), encoding="utf-8")
    r = e.ejecutar(publish=True)
    e.cfg_path.write_text(yaml.safe_dump(e.cfg, allow_unicode=True), encoding="utf-8")
    r.update(falla="MLflow inaccesible (http://127.0.0.1:9)", aprobado_intacto=sha(e.aprobado) == v_b["sha256_csv"])
    fallos_infra.append(r)
    print({k: r[k] for k in ("estado", "excepcion", "aprobado_intacto")})

    print("\n=== Fallo al persistir artefactos en MLflow")
    with mock.patch("src.pipeline.verify_artifacts_logged", side_effect=RuntimeError("artefacto no persistido (simulado)")):
        r = e.ejecutar(publish=True)
    r.update(falla="artefactos no persistidos en MLflow", aprobado_intacto=sha(e.aprobado) == v_b["sha256_csv"])
    fallos_infra.append(r)
    print({k: r[k] for k in ("estado", "excepcion", "aprobado_intacto")})
    ev["fallos_infraestructura"] = fallos_infra

    # ---- 4. Monitoreo: tres clases --------------------------------------------------------------
    print("\n=== Monitoreo")
    frames = {f: pd.read_csv(e.data / f) for f in ("series_mensuales.csv", "pais_mensual.csv", "via_frontera.csv")}
    resultados = pd.read_csv(e.aprobado)
    base = run_monitoring(e.cfg, "mon_base", frames, resultados)

    atrasada = dict(frames)
    sm = frames["series_mensuales.csv"]
    atrasada["series_mensuales.csv"] = sm[pd.to_datetime(sm["fecha"]) <= "2026-04-01"]
    m_act = run_monitoring(e.cfg, "mon_actualizacion", atrasada, resultados)

    degradada = dict(frames)
    degradada["series_mensuales.csv"] = pd.concat([sm, sm.iloc[:25]], ignore_index=True)
    m_cal = run_monitoring(e.cfg, "mon_calidad", degradada, resultados, previous=base)

    salto = resultados.copy()
    i = salto.index[(salto["serie"] == "Total") & (salto["fecha"] == "2024-07-01")]
    salto.loc[i, "prediccion"] = salto.loc[i, "prediccion"] * 3
    m_res = run_monitoring(e.cfg, "mon_resultados", frames, salto)

    def resumen(m):
        return {"all_healthy": m["all_healthy"], "alerts_count": m["alerts_count"],
                "alertas_accionables": [a for a in m["alertas"] if a["severidad"] != "INFO"][:6]}
    ev["monitoreo"] = {
        "linea_base_datos_vigentes": resumen(base),
        "actualizacion (series truncada a 2026-04; cobertura esperada 2026-06)": resumen(m_act),
        "calidad (25 filas duplicadas vs ejecución previa)": resumen(m_cal),
        "resultados (Total 2024-07 multiplicado x3)": resumen(m_res),
    }
    for k, v in ev["monitoreo"].items():
        print(k, "->", v["alerts_count"], "alertas;", [a["control"] for a in v["alertas_accionables"]])

    # ---- 5. Restauración de la versión anterior (A) ----------------------------------------------
    print("\n=== Restauración de la versión A")
    req = [e.cfg["scope"]["target_series"]] + list(e.cfg["scope"]["secondary_series"])
    listado = list_backups(str(e.data / "backup_aprobadas"), req)
    candidato = next(b for b in listado if v_a["run_id"] in b.get("archivo", b.get("name", "")) or
                     b.get("run_id") == v_a["run_id"])
    nombre = candidato.get("archivo") or candidato.get("name")
    tablero_antes = cargar_version_aprobada(str(e.data))
    res = restore_backup(nombre, str(e.aprobado), str(e.data / "backup_aprobadas"),
                         str(e.tmp / "logs" / "publish.lock"), str(e.tmp / "logs"), req,
                         reason="Prueba controlada Lab 11: volver a la versión A", operator="verificacion_lab11")
    tablero = cargar_version_aprobada(str(e.data))
    ev["restauracion"] = {
        "respaldos_listados": [{k: v for k, v in b.items() if k != "df"} for b in listado],
        "respaldo_restaurado": nombre,
        "resultado": {k: v for k, v in res.items() if isinstance(v, (str, int, float, bool, type(None), list, dict))},
        "sha256_csv_tras_restaurar": sha(e.aprobado),
        "coincide_con_A": sha(e.aprobado) == v_a["sha256_csv"],
        "manifiesto_coincide_con_A": sha(e.manifiesto) == v_a["sha256_manifiesto"],
        "tablero_antes": {"estado": tablero_antes["estado"], "sha256": tablero_antes["sha256"],
                          "run_id": (tablero_antes.get("manifiesto") or {}).get("run_id")},
        "tablero_despues": {"estado": tablero["estado"], "sha256": tablero["sha256"],
                            "metadatos_verificados": tablero["metadatos_verificados"],
                            "run_id": (tablero.get("manifiesto") or {}).get("run_id")},
        "auditoria_restauracion": (e.tmp / "logs" / "restore_audit.jsonl").read_text(encoding="utf-8").strip().splitlines(),
    }
    print({k: ev["restauracion"][k] for k in ("respaldo_restaurado", "coincide_con_A", "manifiesto_coincide_con_A")},
          ev["restauracion"]["tablero_despues"])

    # ---- 6. Datos del repositorio intactos --------------------------------------------------------
    ev["data_repositorio_intacta"] = hashes_repo_data() == data_repo_antes
    ev["aprobado_repositorio_sha256"] = data_repo_antes.get("estimaciones_aprobadas.csv")
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "fallos_controlados.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2, default=str),
                                                    encoding="utf-8")
    # Copia de auditorías y reportes del entorno temporal (no contienen microdatos: son JSON de proceso)
    dest = SALIDA / "entorno_temporal"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for p in list((e.tmp / "logs").glob("*.json*")) + list((e.tmp / "reports").glob("*.json")):
        shutil.copy2(p, dest / p.name)
    print("\ndata/ del repositorio intacta:", ev["data_repositorio_intacta"])
    print("Evidencia:", SALIDA / "fallos_controlados.json")
    shutil.rmtree(e.tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
