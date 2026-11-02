"""Sensibilidad de la evaluación a enero y febrero de 2026 (enunciado 5.1 y 5.5).

No cambia la regla de aceptación, no publica y no escribe en data/. Reproduce el backtest de
origen fijo del pipeline (ajuste y evaluación tomados del YAML) y calcula MAE/RMSE de los tres
procedimientos en dos conjuntos de meses:
  1. los meses que evalúa el pipeline (incluyen ene–feb 2026, porque tienen observación);
  2. los mismos meses sin ene–feb 2026.
También verifica que ene–feb 2026 tengan el mismo valor en las tres fuentes institucionales.

Salida: evidencias/lab11/evaluacion/sensibilidad_ene_feb_2026.json
Uso: python scripts/lab11/sensibilidad_ene_feb_2026.py
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.model_engine import (  # noqa: E402
    build_evaluation_mask, compute_metrics, fit_and_predict_historical_mean,
    fit_and_predict_holt_winters, fit_and_predict_seasonal_naive)
from src.monitoring import file_sha256, normalize_series_labels  # noqa: E402

MESES = [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")]
SALIDA = RAIZ / "evidencias" / "lab11" / "evaluacion"


def main():
    cfg = yaml.safe_load((RAIZ / "config" / "pipeline_config.yaml").read_text(encoding="utf-8"))
    t = cfg["temporal_split"]
    acc = cfg["quality_thresholds"]["metrics_acceptance"]
    datos = RAIZ / "data"
    df = pd.read_csv(datos / "series_mensuales.csv")
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["serie"] = normalize_series_labels(df["serie"])
    s = df[df["serie"] == "Total"].set_index("fecha")["viajeros"].astype(float).sort_index()

    fuentes = {}
    for nombre in ("pais_mensual.csv", "via_frontera.csv"):
        ctx = pd.read_csv(datos / nombre, parse_dates=["fecha"]).groupby("fecha")["viajeros"].sum()
        fuentes[nombre] = {m.strftime("%Y-%m"): float(ctx.get(m, float("nan"))) for m in MESES}
    fuentes["series_mensuales.csv (Total)"] = {m.strftime("%Y-%m"): float(s.get(m, float("nan"))) for m in MESES}
    coinciden = all(
        abs(fuentes[n][k] - fuentes["series_mensuales.csv (Total)"][k]) < 0.5
        for n in ("pais_mensual.csv", "via_frontera.csv") for k in fuentes[n]
    )

    train = s[(s.index >= t["train_start"]) & (s.index <= t["train_end"])]
    fechas = pd.date_range(t["eval_start"], t["eval_end"], freq="MS")
    y = s.reindex(fechas)
    ev, _ = build_evaluation_mask(y)
    ev_sin = ev[~ev.isin(MESES)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hw, _ = fit_and_predict_holt_winters(train, fechas)
    preds = {"promedio_historico_mensual (activo)": fit_and_predict_historical_mean(train, fechas),
             "seasonal_naive_lag12 (baseline)": fit_and_predict_seasonal_naive(train, fechas),
             "holt_winters (referencia)": hw}
    resultados = []
    for modelo, p in preds.items():
        for conjunto, idx in (("meses del pipeline (incluye ene-feb 2026)", ev),
                              ("mismos meses sin ene-feb 2026", ev_sin)):
            m = compute_metrics(y, p, evaluable_index=idx)
            resultados.append({"modelo": modelo, "conjunto": conjunto, "n": m["n"],
                               "mae": round(m["mae"], 2), "rmse": round(m["rmse"], 2)})
    errores_meses = {
        m.strftime("%Y-%m"): {"observado": float(y[m]),
                              "activo": round(float(preds["promedio_historico_mensual (activo)"][m]), 2),
                              "baseline": round(float(preds["seasonal_naive_lag12 (baseline)"][m]), 2)}
        for m in MESES if m in y.index
    }
    out = {
        "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "proposito": ("Análisis de sensibilidad. No modifica la regla de aceptación ni los periodos del YAML; "
                      "la decisión oficial es la del pipeline."),
        "fuentes_sha256": {n: file_sha256(str(datos / n))
                           for n in ("series_mensuales.csv", "pais_mensual.csv", "via_frontera.csv")},
        "ajuste": [t["train_start"], t["train_end"]], "evaluacion": [t["eval_start"], t["eval_end"]],
        "excluded_evaluation_periods_yaml": t.get("excluded_evaluation_periods", []),
        "ene_feb_2026_por_fuente": fuentes, "ene_feb_2026_coinciden_entre_fuentes": coinciden,
        "ene_feb_2026_detalle": errores_meses,
        "umbrales_regla": {k: acc.get(k) for k in ("max_mae_tolerance", "max_rmse_tolerance")},
        "nota_holt_winters": ("Holt-Winters varía entre sistemas operativos (statsmodels); el valor de este archivo "
                              "corresponde a la máquina donde se ejecutó el script. No es el modelo activo."),
        "resultados": resultados,
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "sensibilidad_ene_feb_2026.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("ene_feb_2026_coinciden_entre_fuentes", "umbrales_regla",
                                          "ene_feb_2026_detalle", "resultados")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
