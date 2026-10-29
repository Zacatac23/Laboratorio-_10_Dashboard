"""Pruebas Unitarias de los Seis Controles de Calidad (Laboratorio 11 - Ejercicio 3)."""
import unittest
import pandas as pd
import numpy as np
from src.quality_checks import (
    check_columns_and_types,
    check_dates_and_coverage,
    check_uniqueness,
    check_missing_values,
    check_values_and_denominators,
    check_methodological_rule,
    execute_all_quality_checks
)


class TestQualityChecks(unittest.TestCase):
    def setUp(self):
        # Base limpia de prueba
        fechas = pd.date_range("2021-01-01", "2021-12-01", freq="MS")
        self.df_clean = pd.DataFrame({
            "serie": ["Total"] * len(fechas),
            "fecha": fechas,
            "viajeros": [1000.0 + i * 50 for i in range(len(fechas))]
        })

    def test_qc_a_columnas_y_tipos_valido(self):
        schema = {"serie": "string", "fecha": "datetime", "viajeros": "numeric"}
        res = check_columns_and_types(self.df_clean, schema)
        self.assertEqual(res.status, "PASSED")
        self.assertTrue(res.is_critical)

    def test_qc_a_falta_columna_indispensable(self):
        df_mal = self.df_clean.drop(columns=["viajeros"])
        schema = {"serie": "string", "fecha": "datetime", "viajeros": "numeric"}
        res = check_columns_and_types(df_mal, schema)
        self.assertEqual(res.status, "FAILED")
        self.assertIn("viajeros", res.details)

    def test_qc_a_tipo_incompatible(self):
        df_mal = self.df_clean.copy()
        df_mal["viajeros"] = ["mil", "dos_mil"] + [100.0] * (len(df_mal) - 2)
        schema = {"serie": "string", "fecha": "datetime", "viajeros": "numeric"}
        res = check_columns_and_types(df_mal, schema)
        self.assertEqual(res.status, "FAILED")

    def test_qc_b_fechas_dia_no_primero(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[0, "fecha"] = pd.Timestamp("2021-01-15")
        res = check_dates_and_coverage(df_mal, target_series="Total")
        self.assertEqual(res.status, "FAILED")
        self.assertIn("primer día del mes", res.details)

    def test_qc_b_hueco_temporal_en_secuencia(self):
        # Omitir un mes (febrero)
        df_mal = self.df_clean[self.df_clean["fecha"] != "2021-02-01"].copy()
        res = check_dates_and_coverage(df_mal, target_series="Total")
        self.assertEqual(res.status, "FAILED")
        self.assertIn("Huecos temporales", res.details)

    def test_qc_c_unicidad_detecta_duplicados(self):
        df_mal = pd.concat([self.df_clean, self.df_clean.iloc[0:1]], ignore_index=True)
        res = check_uniqueness(df_mal, key_cols=["serie", "fecha"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("claves duplicadas", res.details)

    def test_qc_d_valores_faltantes_en_target(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[2, "viajeros"] = np.nan
        res = check_missing_values(df_mal, mandatory_cols=["serie", "fecha", "viajeros"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("viajeros", res.details)

    def test_qc_e_conteo_negativo_historico(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[3, "viajeros"] = -150.0
        res = check_values_and_denominators(df_mal, value_cols=["viajeros"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("Conteos negativos", res.details)

    def test_qc_e_denominador_igual_a_cero(self):
        df_den = pd.DataFrame({"total": [100, 0, 50], "sub": [10, 0, 5]})
        res = check_values_and_denominators(df_den, value_cols=["sub"], denominator_cols=["total"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("Denominadores iguales a cero", res.details)

    def test_qc_f_regla_metodologica_conciliacion(self):
        fechas = pd.date_range("2021-01-01", "2021-03-01", freq="MS")
        rows = []
        for f in fechas:
            rows.append({"fecha": f, "serie": "Total", "viajeros": 1000.0})
            rows.append({"fecha": f, "serie": "Via_Aérea", "viajeros": 600.0})
            rows.append({"fecha": f, "serie": "Via_Terrestre", "viajeros": 350.0})
            rows.append({"fecha": f, "serie": "Via_Marítima", "viajeros": 50.0})
        df_conciliable = pd.DataFrame(rows)
        res = check_methodological_rule(df_conciliable)
        self.assertEqual(res.status, "PASSED")


if __name__ == "__main__":
    unittest.main()

