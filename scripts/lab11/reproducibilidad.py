"""Compara dos ejecuciones registradas en el servidor MLflow (ejercicio 4).

Descarga desde el servidor (no desde archivos locales) las estimaciones candidatas de ambos runs y
compara predicciones con np.allclose(atol=1e-6, rtol=0), métricas y huellas (config, código, datos, commit).
Ignora solo campos volátiles: run_id, tiempos y metadatos de generación.

Uso: python scripts/lab11/reproducibilidad.py <tracking_uri> <run_id_pipeline_1> <run_id_pipeline_2>
Salida: reports/reproducibilidad_lab11.json (copia versionable en evidencias/lab11/reproducibilidad/)
        evidencias/lab11/mlflow/export_runs.json (exportación de runs del experimento)
"""
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

RAIZ = Path(__file__).resolve().parents[2]
ATOL, RTOL = 1e-6, 0.0
VOLATILES = {"run_id", "run.start", "run.end", "mlflow.runName", "mlflow.source.name", "mlflow.user",
             "mlflow.source.type", "mlflow.source.git.commit", "publication.timestamp",
             # El CSV candidato incluye las columnas run_id y fecha_generacion: su hash cambia en cada run.
             # Se compara en su lugar candidate_sin_volatiles.sha256 (ver abajo).
             "candidate.sha256"}
COLUMNAS_VOLATILES = ["run_id", "fecha_generacion"]
METRICAS_VOLATILES = {"pipeline.duration_seconds"}  # tiempo de ejecución


def buscar(client, exp_id, run_tag):
    runs = client.search_runs([exp_id], f"tags.run_id = '{run_tag}'")
    if len(runs) != 1:
        raise SystemExit(f"Se esperaba 1 run con tags.run_id={run_tag}, hay {len(runs)}")
    return runs[0]


def artefactos(client, run_id, path=None):
    out = []
    for a in client.list_artifacts(run_id, path):
        out += artefactos(client, run_id, a.path) if a.is_dir else [a.path]
    return out


def main():
    uri, r1, r2 = sys.argv[1:4]
    client = MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name("Observatorio_Turismo_Guatemala")
    runs = [buscar(client, exp.experiment_id, r) for r in (r1, r2)]
    tmp = Path(tempfile.mkdtemp())
    preds = []
    for run in runs:
        tag = run.data.tags["run_id"]
        rel = f"estimaciones/estimaciones_candidatas_{tag}.csv"
        local = client.download_artifacts(run.info.run_id, rel, str(tmp / tag))
        preds.append(pd.read_csv(local))
    a, b = preds
    import hashlib
    hash_sin_vol = [hashlib.sha256(p.drop(columns=COLUMNAS_VOLATILES).to_csv(index=False, lineterminator="\n")
                                   .encode("utf-8")).hexdigest() for p in preds]
    clave = ["serie", "fecha"]
    m = a.merge(b, on=clave, suffixes=("_1", "_2"), how="outer", indicator=True)
    solo_uno = int((m["_merge"] != "both").sum())
    por_serie = []
    for serie, g in m[m["_merge"] == "both"].groupby("serie"):
        d = (g["prediccion_1"] - g["prediccion_2"]).abs()
        por_serie.append({"serie": serie, "n": int(len(g)), "max_abs_diff": float(d.max()),
                          "allclose": bool(np.allclose(g["prediccion_1"], g["prediccion_2"], atol=ATOL, rtol=RTOL))})
    p1, p2 = runs[0].data.params, runs[1].data.params
    huellas = {k: {"run_1": p1.get(k), "run_2": p2.get(k), "igual": p1.get(k) == p2.get(k)}
               for k in sorted(set(p1) | set(p2)) if k.endswith(".sha256")}
    params_dif = {k: (p1.get(k), p2.get(k)) for k in sorted(set(p1) | set(p2))
                  if p1.get(k) != p2.get(k) and k not in VOLATILES}
    m1, m2 = runs[0].data.metrics, runs[1].data.metrics
    metricas = {k: {"run_1": m1.get(k), "run_2": m2.get(k), "igual": m1.get(k) == m2.get(k)}
                for k in sorted(set(m1) | set(m2)) if k not in METRICAS_VOLATILES}
    t1, t2 = runs[0].data.tags, runs[1].data.tags
    commit = {"run_1": t1.get("git.commit"), "run_2": t2.get("git.commit"),
              "fuente": t1.get("git.commit_source"), "igual": t1.get("git.commit") == t2.get("git.commit")}
    huellas["candidate_sin_volatiles.sha256 (recalculado)"] = {
        "run_1": hash_sin_vol[0], "run_2": hash_sin_vol[1], "igual": hash_sin_vol[0] == hash_sin_vol[1],
        "nota": f"CSV candidato descargado de MLflow sin las columnas {COLUMNAS_VOLATILES}"}
    huellas["candidate.sha256"]["nota"] = "Incluye run_id y fecha_generacion: distinto por diseño (volátil)"
    huellas["candidate.sha256"]["igual_requerido"] = False
    ok = (solo_uno == 0 and all(s["allclose"] for s in por_serie) and all(h["igual"] for h in huellas.values() if h.get("igual_requerido", True))
          and all(v["igual"] for v in metricas.values()) and not params_dif and commit["igual"])
    fechas = pd.to_datetime(a["fecha"])
    out = {
        "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tracking_uri": uri,
        "experimento": {"nombre": exp.name, "id": exp.experiment_id},
        "runs": [{"run_id_pipeline": r.data.tags["run_id"], "mlflow_run_id": r.info.run_id,
                  "pipeline.status": r.data.tags.get("pipeline.status"),
                  "inicio": r.data.tags.get("run.start")} for r in runs],
        "commit": commit,
        "huellas_sha256": huellas,
        "parametros_no_volatiles_distintos": params_dif,
        "rango_temporal_estimaciones": {"inicio": str(fechas.min().date()), "fin": str(fechas.max().date())},
        "tolerancia": {"atol": ATOL, "rtol": RTOL,
                       "justificacion": ("Las predicciones se publican redondeadas a 2 decimales "
                                         "(round_predictions_decimals=2); 1e-6 viajeros es muy inferior a esa "
                                         "resolución, así que cualquier diferencia real sería detectada.")},
        "filas_solo_en_un_run": solo_uno,
        "comparacion_por_serie": por_serie,
        "max_abs_diff_global": max(s["max_abs_diff"] for s in por_serie),
        "metricas": metricas,
        "campos_ignorados_por_volatiles": sorted(VOLATILES | METRICAS_VOLATILES) + [f"columna CSV {c}" for c in COLUMNAS_VOLATILES],
        "estado": "REPRODUCIBLE" if ok else "DIFERENCIAS_DETECTADAS",
    }
    destino = RAIZ / "reports" / "reproducibilidad_lab11.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(out, ensure_ascii=False, indent=2)
    destino.write_text(texto, encoding="utf-8")
    copia = RAIZ / "evidencias" / "lab11" / "reproducibilidad" / "reproducibilidad_lab11.json"
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.write_text(texto, encoding="utf-8")

    export = []
    for r in client.search_runs([exp.experiment_id], order_by=["attributes.start_time ASC"]):
        export.append({"mlflow_run_id": r.info.run_id, "status": r.info.status,
                       "start_time_ms": r.info.start_time, "end_time_ms": r.info.end_time,
                       "tags": {k: v for k, v in r.data.tags.items() if not k.startswith("mlflow.")},
                       "params": r.data.params, "metrics": r.data.metrics,
                       "artefactos": artefactos(client, r.info.run_id)})
    exp_dir = RAIZ / "evidencias" / "lab11" / "mlflow"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "export_runs.json").write_text(json.dumps({"tracking_uri": uri, "experimento": exp.name,
                                                          "runs": export}, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({k: out[k] for k in ("runs", "commit", "estado", "max_abs_diff_global",
                                          "filas_solo_en_un_run", "parametros_no_volatiles_distintos")},
                     ensure_ascii=False, indent=1))
    print("runs exportados:", len(export))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
