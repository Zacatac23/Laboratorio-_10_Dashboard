"""Pruebas de los controles QC-A … QC-F (Laboratorio 11)."""
import unittest

import numpy as np
import pandas as pd

from src.quality_checks import (
    check_columns_and_types,
    check_dates_and_coverage,
    check_uniqueness,
    check_missing_values,
    check_values_and_denominators,
    check_methodological_rule,
    execute_all_quality_checks,
)


class TestQualityChecks(unittest.TestCase):
    def setUp(self):
        fechas = pd.date_range("2021-01-01", "2021-12-01", freq="MS")
        self.df_clean = pd.DataFrame(
            {
                "serie": ["Total"] * len(fechas),
                "fecha": fechas,
                "viajeros": [1000.0 + i * 50 for i in range(len(fechas))],
            }
        )
        self.schema = {"serie": "string", "fecha": "datetime", "viajeros": "numeric"}

    def test_qc_a_columnas_y_tipos_valido(self):
        res = check_columns_and_types(self.df_clean, self.schema)
        self.assertEqual(res.status, "PASSED")

    def test_qc_a_falta_columna_indispensable(self):
        res = check_columns_and_types(self.df_clean.drop(columns=["viajeros"]), self.schema)
        self.assertEqual(res.status, "FAILED")
        self.assertIn("viajeros", res.details)

    def test_qc_a_tipo_incompatible(self):
        df_mal = self.df_clean.copy()
        df_mal["viajeros"] = ["mil", "dos_mil"] + [100.0] * (len(df_mal) - 2)
        res = check_columns_and_types(df_mal, self.schema)
        self.assertEqual(res.status, "FAILED")

    def test_qc_a_nulo_no_se_acepta_como_texto_nan(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[0, "serie"] = np.nan
        res = check_columns_and_types(df_mal, self.schema)
        self.assertEqual(res.status, "FAILED")
        self.assertIn("nulos", res.details.lower())

    def test_qc_b_fechas_dia_no_primero(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[0, "fecha"] = pd.Timestamp("2021-01-15")
        res = check_dates_and_coverage(df_mal, target_series="Total")
        self.assertEqual(res.status, "FAILED")

    def test_qc_b_hueco_temporal_en_secuencia(self):
        df_mal = self.df_clean[self.df_clean["fecha"] != "2021-02-01"].copy()
        res = check_dates_and_coverage(df_mal, target_series="Total")
        self.assertEqual(res.status, "FAILED")
        self.assertIn("Huecos temporales", res.details)

    def test_qc_b_hueco_no_se_imputa_cero(self):
        """Un mes ausente falla; no aparece como fila con viajeros=0."""
        df_mal = self.df_clean[self.df_clean["fecha"] != "2021-02-01"].copy()
        self.assertFalse(((df_mal["fecha"] == "2021-02-01") & (df_mal["viajeros"] == 0)).any())
        res = check_dates_and_coverage(df_mal, target_series="Total")
        self.assertEqual(res.status, "FAILED")

    def test_qc_b_cero_legitimo_permitido(self):
        df = self.df_clean.copy()
        df.loc[1, "viajeros"] = 0.0
        res = check_values_and_denominators(df, value_cols=["viajeros"])
        self.assertEqual(res.status, "PASSED")

    def test_qc_b_ventana_requerida_faltante(self):
        res = check_dates_and_coverage(
            self.df_clean,
            target_series="Total",
            required_start="2020-01-01",
            required_end="2021-12-01",
            require_full_required_window=True,
        )
        self.assertEqual(res.status, "FAILED")
        self.assertIn("indispensables", res.details)

    def test_qc_c_unicidad_detecta_duplicados(self):
        df_mal = pd.concat([self.df_clean, self.df_clean.iloc[0:1]], ignore_index=True)
        res = check_uniqueness(df_mal, key_cols=["serie", "fecha"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("key_samples", res.diagnostics)

    def test_qc_d_valores_faltantes_en_target(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[2, "viajeros"] = np.nan
        res = check_missing_values(df_mal, mandatory_cols=["serie", "fecha", "viajeros"])
        self.assertEqual(res.status, "FAILED")

    def test_qc_e_conteo_negativo_historico(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[3, "viajeros"] = -150.0
        res = check_values_and_denominators(df_mal, value_cols=["viajeros"])
        self.assertEqual(res.status, "FAILED")

    def test_qc_e_infinito(self):
        df_mal = self.df_clean.copy()
        df_mal.loc[3, "viajeros"] = np.inf
        res = check_values_and_denominators(df_mal, value_cols=["viajeros"])
        self.assertEqual(res.status, "FAILED")
        self.assertIn("Infinitos", res.details)

    def test_qc_e_denominador_igual_a_cero(self):
        df_den = pd.DataFrame({"total": [100, 0, 50], "sub": [10, 0, 5]})
        res = check_values_and_denominators(df_den, value_cols=["sub"], denominator_cols=["total"])
        self.assertEqual(res.status, "FAILED")

    def test_qc_f_regla_metodologica_conciliacion(self):
        fechas = pd.date_range("2021-01-01", "2021-03-01", freq="MS")
        rows = []
        for f in fechas:
            rows.extend(
                [
                    {"fecha": f, "serie": "Total", "viajeros": 1000.0},
                    {"fecha": f, "serie": "Via_Aérea", "viajeros": 600.0},
                    {"fecha": f, "serie": "Via_Terrestre", "viajeros": 350.0},
                    {"fecha": f, "serie": "Via_Marítima", "viajeros": 50.0},
                ]
            )
        res = check_methodological_rule(pd.DataFrame(rows))
        self.assertEqual(res.status, "PASSED")

    def test_qc_f_discrepancia_material_bloquea(self):
        fechas = pd.date_range("2021-01-01", "2021-03-01", freq="MS")
        rows = []
        for f in fechas:
            rows.extend(
                [
                    {"fecha": f, "serie": "Total", "viajeros": 1000.0},
                    {"fecha": f, "serie": "Via_Aérea", "viajeros": 900.0},
                    {"fecha": f, "serie": "Via_Terrestre", "viajeros": 900.0},
                    {"fecha": f, "serie": "Via_Marítima", "viajeros": 900.0},
                ]
            )
        res = check_methodological_rule(pd.DataFrame(rows), tolerance_pct=0.02)
        self.assertEqual(res.status, "FAILED")
        self.assertTrue(res.is_critical)

    def test_qc_f_sin_insumos_no_verificable(self):
        res = check_methodological_rule(self.df_clean)
        self.assertEqual(res.status, "NO_VERIFICABLE")
        self.assertTrue(res.is_critical)

    def test_execute_all_bloquea_por_qc_f(self):
        fechas = pd.date_range("2021-01-01", "2021-03-01", freq="MS")
        rows = []
        for f in fechas:
            rows.extend(
                [
                    {"fecha": f, "serie": "Total", "viajeros": 100.0},
                    {"fecha": f, "serie": "Via_Aérea", "viajeros": 80.0},
                    {"fecha": f, "serie": "Via_Terrestre", "viajeros": 80.0},
                    {"fecha": f, "serie": "Via_Marítima", "viajeros": 80.0},
                ]
            )
        df = pd.DataFrame(rows)
        config = {
            "temporal_split": {"train_start": "2021-01-01", "eval_end": "2021-03-01"},
            "scope": {"target_series": "Total"},
            "quality_thresholds": {"methodological_fail_on_discrepancy": True},
        }
        report = execute_all_quality_checks(df, "run_test", "2026-01-01T00:00:00", config)
        self.assertFalse(report.critical_passed)


if __name__ == "__main__":
    unittest.main()
