# Exportar resultados de los Laboratorios 1 y 2 (sin entrenar nada nuevo)

Pegue cada celda al FINAL del notebook correspondiente, ejecútela y copie los CSV a `data/`.
Si algún nombre de variable difiere en su notebook, ajústelo.

## Laboratorio 1 → `data/pronosticos.csv` (parte Lab 1)
```python
fcs = {"Total": fc_total, "Via_Aérea": fc_aerea, "Via_Terrestre": fc_terrestre, "Via_Marítima": fc_maritima,
       "Tipo_Turista": fc_turista, "Tipo_Excursionista": fc_excursionista,
       "Tipo_Viajero": fc_viajero, "Tipo_Cruceristas": fc_cruceristas}
filas = [{"serie": s, "modelo": m, "fecha": f, "prediccion": float(v)}
         for s, d in fcs.items() for m, ser in d.items() for f, v in ser.items()]
pd.DataFrame(filas).to_csv("pronosticos_lab1.csv", index=False)
```

## Laboratorio 2 → `data/pronosticos.csv` (parte LSTM) y `data/catch22_pca.csv`
```python
filas = [{"serie": s, "modelo": "LSTM", "fecha": f, "prediccion": float(v)}
         for s, r in mejor_lstm_por_serie.items() for f, v in r["forecast"].items()]
pd.DataFrame(filas).to_csv("pronosticos_lstm.csv", index=False)

out = pca_df.copy()
out["cluster"] = clusters_df.reindex(out.index).values
out.index.name = "serie"
out.reset_index().to_csv("catch22_pca.csv", index=False)
```

## Unir (en cualquier terminal)
```python
import pandas as pd
pd.concat([pd.read_csv("pronosticos_lab1.csv"), pd.read_csv("pronosticos_lstm.csv")]).to_csv("data/pronosticos.csv", index=False)
```
El tablero calcula MAE y RMSE directamente desde estos pronósticos y los datos reales, así que las cifras siempre son consistentes.
