"""Regresiones de operaciones extraídas y sin Qt."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from dpi.medicion.calculo import indice_punto_mas_cercano
from dpi.series.modelo import ModeloSeries
from dpi.series.importacion import importar_archivo
from dpi.series.comparacion import preparar_serie
from dpi.ciencia import modelos_nulos, quiebres
from dpi.ciencia.prioridad import clave_prioridad_correccion


class TestUtilidadesGeometriaSeriesYCiencia(unittest.TestCase):
    def test_punto_cercano(self):
        self.assertEqual(indice_punto_mas_cercano([(0, 0), (2, 0)], 1, 0, 2), 0)
        self.assertIsNone(indice_punto_mas_cercano([(0, 0)], 1, 0, 1))

    def test_importar_sin_sobrescribir(self):
        modelo = ModeloSeries()
        df = pd.DataFrame({"Ancho_mm": [1., 2.]}, index=[2000, 2001])
        modelo.registrar("A", df)
        with patch("dpi.series.importacion.leer_series_auto", return_value={"A": df * 2, "B": df}):
            self.assertEqual(list(importar_archivo(modelo, "x")), [("A", False), ("B", True)])
        pd.testing.assert_frame_equal(modelo.datos["A"], df)
        pd.testing.assert_frame_equal(modelo.datos["B"], df)

    def test_preparar_serie_vacia(self):
        def no_llamar(serie):
            self.fail("No debe transformar una serie vacía")
        resultado = preparar_serie(pd.Series([np.nan]), no_llamar, no_llamar)
        self.assertTrue(resultado.cruda.empty)

    def test_nulo_inyectado(self):
        series = {str(i): i for i in range(10)}
        def localizar(s, c, **kwargs):
            return {"ganancia": float(s)}
        resultado = modelos_nulos.nulo_de_coleccion(localizar, series, None, excluir="0")
        self.assertEqual(resultado["n"], 9)
        self.assertAlmostEqual(resultado["umbral"], np.percentile(range(1, 10), 95))
        with patch.object(quiebres, "localizar_quiebre", localizar):
            self.assertEqual(quiebres.nulo_de_coleccion(series, None, excluir="0"), resultado)

    def test_prioridad(self):
        candidato = {"anio": 2000, "r_verificada": .8, "plausibilidad": .5}
        self.assertAlmostEqual(clave_prioridad_correccion(candidato, 2000), .6)
        self.assertAlmostEqual(clave_prioridad_correccion(candidato, 2060), .2)
