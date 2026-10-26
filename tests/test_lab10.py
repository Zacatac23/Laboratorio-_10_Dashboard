"""Pruebas sin entrenamiento y sin modificar los CSV del repositorio."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_logic import (cargar_todo, leer_archivo, ErrorDatos, agrupar_serie,
    calcular_variacion_interanual, calcular_metricas_error)


class Datos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.p, cls.v, cls.f, *_ = cargar_todo(ROOT / 'data')

    def fixture(self, archivo, transformacion):
        with tempfile.TemporaryDirectory() as tmp:
            df = pd.read_csv(ROOT / 'data' / archivo)
            transformacion(df).to_csv(Path(tmp) / archivo, index=False)
            with self.assertRaises(ErrorDatos):
                leer_archivo(archivo, tmp)

    def test_01_datos_actuales(self):
        self.assertEqual(len(self.s), 1680)
        self.assertEqual(len(self.f), 2646)
        self.assertEqual(int(self.f.prediccion.lt(0).sum()), 586)

    def test_02_metricas_42_pares_sin_regresion(self):
        golden = json.loads((ROOT / 'tests/metricas_referencia.json').read_text())
        for serie, modelos in golden.items():
            tabla = calcular_metricas_error(self.s, self.f, serie).set_index('Modelo')
            for modelo, valores in modelos.items():
                with self.subTest(serie=serie, modelo=modelo):
                    self.assertEqual(tabla.loc[modelo, ['MAE (Error medio)', 'RMSE', 'N']].tolist(), valores)

    def test_03_2009_sin_comparacion(self):
        s = self.s[self.s.serie == 'Total'].set_index('fecha').viajeros
        self.assertIsNone(calcular_variacion_interanual(s, 2009))

    def test_04_anual_sin_fechas_mensuales(self):
        s = self.s[self.s.serie == 'Total'].set_index('fecha').viajeros
        a = agrupar_serie(s, 'Anual')
        self.assertTrue((a.index.month == 1).all())
        self.assertAlmostEqual(s.sum(), a.sum())

    def test_05_pronosticos_sin_solapamiento(self):
        f = self.f.copy(); f.fecha += pd.DateOffset(years=100)
        t = calcular_metricas_error(self.s, f, 'Total')
        self.assertTrue(t.N.eq(0).all())
        self.assertTrue(t['MAE (Error medio)'].isna().all())

    def test_06_serie_sin_modelo(self):
        self.assertTrue(calcular_metricas_error(self.s, self.f, 'NoExiste').empty)

    def test_07_csv_vacio(self):
        self.fixture('series_mensuales.csv', lambda d: d.iloc[:0])

    def test_08_fecha_faltante(self):
        self.fixture('series_mensuales.csv', lambda d: d.drop(columns='fecha'))

    def test_09_fecha_invalida(self):
        self.fixture('series_mensuales.csv', lambda d: d.assign(fecha='no-fecha'))

    def test_10_infinito(self):
        self.fixture('series_mensuales.csv', lambda d: d.assign(viajeros=np.inf))

    def test_11_duplicados(self):
        self.fixture('series_mensuales.csv', lambda d: pd.concat([d, d.iloc[:1]]))

    def test_12_negativo_historico(self):
        self.fixture('series_mensuales.csv', lambda d: d.assign(viajeros=-1))

    def test_13_archivo_ausente(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ErrorDatos, 'Falta series_mensuales.csv'):
                cargar_todo(tmp)

    def test_14_nulos(self):
        self.fixture('pais_mensual.csv', lambda d: d.assign(region=None))

    def test_15_conciliacion(self):
        total = self.s[self.s.serie == 'Total'].set_index('fecha').viajeros
        for df in [self.p, self.v]:
            self.assertTrue(np.allclose(total, df.groupby('fecha').viajeros.sum()))

    def test_27_cero_uno_multiples_y_obsoleto(self):
        from data_logic import seleccion_vigente
        self.assertIsNone(seleccion_vigente([], ['Asia', 'Europa']))
        self.assertEqual(seleccion_vigente([{'y': 'Asia'}], ['Asia', 'Europa']), 'Asia')
        self.assertEqual(seleccion_vigente([{'y': 'Asia'}, {'y': 'Europa'}], ['Asia', 'Europa']), 'Europa')
        self.assertIsNone(seleccion_vigente([{'y': 'No disponible'}], ['Asia']))


class Dashboard(unittest.TestCase):
    def app(self):
        at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_16_inicio_nueve_vistas(self):
        at = self.app()
        self.assertEqual(len(at.get('plotly_chart')), 9)
        self.assertEqual(len(at.tabs), 4)

    def test_17_todas_las_vistas_ocultables(self):
        at = self.app()
        ids = list(at.multiselect(key='vistas').value)
        for identidad in ids:
            at.multiselect(key='vistas').set_value([x for x in ids if x != identidad]).run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(len(at.get('plotly_chart')), 8, identidad)
        at.multiselect(key='vistas').set_value([]).run()
        self.assertEqual(len(at.get('plotly_chart')), 0)

    def test_18_mensual_anual_regreso(self):
        at = self.app()
        for nivel in ['Anual', 'Mensual']:
            at.selectbox(key='detalle').select(nivel).run()
            self.assertEqual(len(at.exception), 0)
            fig = json.loads(next(g for g in at.get('plotly_chart') if g.key == 'viz_V01').proto.spec)
            self.assertEqual(len(fig['data']), 1)
            if nivel == 'Anual':
                self.assertTrue(all(pd.Timestamp(x).month == 1 for x in fig['data'][0]['x']))

    def test_19_region_global_y_reset(self):
        at = self.app()
        at.selectbox(key='reg').select('Asia').run()
        self.assertEqual(at.selectbox(key='region_detalle').value, 'Asia')
        at.multiselect(key='vistas').set_value(['V01']).run()
        at.button(key='reset_global').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.get('plotly_chart')), 9)
        self.assertEqual(at.selectbox(key='reg').value, 'Todas las regiones')

    def test_20_2009_no_inventa_porcentaje(self):
        at = self.app()
        at.slider(key='anios').set_range(2009, 2009).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.metric[1].value, 'Sin datos para comparación')

    def test_21_cero_modelos(self):
        at = self.app()
        at.multiselect(key='modelos').set_value([]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.get('plotly_chart')), 7)
        self.assertTrue(any('al menos un modelo' in x.value for x in at.info))

    def test_22_modelos_metricas_y_negativos(self):
        at = self.app()
        from data_logic import ETIQ
        for serie in ETIQ:
            at.selectbox(key='serie_mod').select(serie).run()
            self.assertEqual(len(at.exception), 0)
        at.selectbox(key='serie_mod').select('Total').run()
        at.multiselect(key='modelos').set_value(['Holt-Winters']).run()
        at.selectbox(key='metrica').select('RMSE').run()
        self.assertEqual(len(at.dataframe[0].value), 1)
        self.assertTrue(any('negativos' in w.value for w in at.warning))

    def test_23_heatmap_anios(self):
        at = self.app()
        fig = json.loads(next(g for g in at.get('plotly_chart') if g.key == 'viz_V07').proto.spec)
        self.assertEqual(fig['layout']['yaxis']['type'], 'category')
        self.assertIsNone(fig['layout']['yaxis'].get('tickformat'))

    def test_24_filtros_sin_filas(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT / 'data', Path(tmp) / 'data')
            dat = Path(tmp) / 'data'
            for name in ['pais_mensual.csv', 'via_frontera.csv']:
                d = pd.read_csv(dat / name)
                d[pd.to_datetime(d.fecha).dt.year == 2009].to_csv(dat / name, index=False)
            with patch.dict(os.environ, {'DATA_DIR': str(dat)}):
                at = self.app()
                self.assertTrue(any('Sin' in i.value for i in at.info))

    def test_25_error_csv_sin_stacktrace(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'DATA_DIR': tmp}):
                at = self.app()
                self.assertEqual(len(at.error), 1)

    def test_26_modelos_opcionales(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT / 'data', Path(tmp) / 'data')
            (Path(tmp) / 'data/pronosticos.csv').unlink()
            with patch.dict(os.environ, {'DATA_DIR': str(Path(tmp) / 'data')}):
                at = self.app()
                self.assertTrue(any('No hay pronósticos' in i.value for i in at.info))


if __name__ == '__main__':
    unittest.main()
