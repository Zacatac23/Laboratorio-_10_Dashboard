"""Backtest de cortes múltiples (complementario; no cambia la regla de aceptación ni publica).

Para cada origen t se ajusta con datos de 2009-01 a t y se estiman los 12 meses siguientes.
Modelo activo (Promedio Histórico Mensual) y baselines se evalúan en EXACTAMENTE los mismos meses.
Solo lee data/series_mensuales.csv. Salida: evidencias/lab11/evaluacion/backtest_cortes_multiples.{json,csv}

Uso: python scripts/lab11/backtest_cortes_multiples.py
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.model_engine import (  # noqa: E402
    build_evaluation_mask, compute_metrics, fit_and_predict_historical_mean,
    fit_and_predict_holt_winters, fit_and_predict_seasonal_naive)
from src.monitoring import file_sha256, normalize_series_labels  # noqa: E402

ORIGENES = ["2016-12-01", "2017-12-01", "2018-12-01", "2019-12-01", "2022-12-01", "2023-12-01",
            "2024-12-01", "2025-06-01"]
HORIZONTE = 12
SALIDA = RAIZ / "evidencias" / "lab11" / "evaluacion"


def main():
    ruta = RAIZ / "data" / "series_mensuales.csv"
    df = pd.read_csv(ruta)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["serie"] = normalize_series_labels(df["serie"])
    s = df[df["serie"] == "Total"].set_index("fecha")["viajeros"].astype(float).sort_index()
    filas = []
    for o in ORIGENES:
        o = pd.Timestamp(o)
        train = s[(s.index >= "2009-01-01") & (s.index <= o)]
        fechas = pd.date_range(o + pd.DateOffset(months=1), periods=HORIZONTE, freq="MS")
        y = s.reindex(fechas)
        ev, info = build_evaluation_mask(y)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            hw, _ = fit_and_predict_holt_winters(train, fechas)
        preds = {"promedio_historico_mensual (activo)": fit_and_predict_historical_mean(train, fechas),
                 "seasonal_naive_lag12 (baseline)": fit_and_predict_seasonal_naive(train, fechas),
                 "holt_winters (referencia)": hw}
        for modelo, p in preds.items():
            m = compute_metrics(y, p, evaluable_index=ev)
            filas.append({"origen": o.strftime("%Y-%m"), "eval_inicio": fechas[0].strftime("%Y-%m"),
                          "eval_fin": fechas[-1].strftime("%Y-%m"), "n_train": len(train),
                          "n_evaluable": info["n_evaluable"], "modelo": modelo,
                          "mae": m["mae"], "rmse": m["rmse"], "ape_eps_pct": m["ape_eps_pct"], "n": m["n"]})
    tabla = pd.DataFrame(filas)
    SALIDA.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(SALIDA / "backtest_cortes_multiples.csv", index=False)
    resumen = (tabla.groupby("modelo")[["mae", "rmse"]].mean().round(2)
               .rename(columns={"mae": "mae_promedio_cortes", "rmse": "rmse_promedio_cortes"}))
    out = {
        "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fuente": "data/series_mensuales.csv", "fuente_sha256": file_sha256(str(ruta)),
        "protocolo": ("Origen móvil, entrenamiento expansivo desde 2009-01, horizonte 12 meses, sin reajuste "
                      "dentro del horizonte. Mismos meses para todos los modelos. Complementario al backtest "
                      "de origen fijo del pipeline; no altera la regla de aceptación."),
        "nota_covid": ("Los cortes 2019-12 (evalúa 2020) incluyen el colapso por COVID-19; los posteriores a "
                       "2021 entrenan con esos meses atípicos."),
        "origenes": ORIGENES, "horizonte_meses": HORIZONTE,
        "resultados": filas, "resumen_por_modelo": resumen.reset_index().to_dict(orient="records"),
    }
    (SALIDA / "backtest_cortes_multiples.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
    print(tabla.to_string(index=False))
    print(resumen.to_string())


if __name__ == "__main__":
    main()
