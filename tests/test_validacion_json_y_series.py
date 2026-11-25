import io
import unittest

import pandas as pd

from dpi.infraestructura.json_seguro import cargar_json
from dpi.series.modelo import ModeloSeries


class ValidacionJsonYSeries(unittest.TestCase):
    def test_constantes_json_no_estandar(self):
        for valor in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                cargar_json(io.StringIO('{"valor": ' + valor + '}'))

    def test_null_json_valido(self):
        self.assertEqual(cargar_json(io.StringIO('{"valor": null}')), {'valor': None})

    def test_serie_sin_datos(self):
        modelo = ModeloSeries()
        datos = pd.DataFrame({'Ancho_mm': [float('nan'), float('nan')]}, index=[2000, 2001])
        with self.assertRaises(ValueError):
            modelo.registrar('vacia', datos)
        self.assertNotIn('vacia', modelo.datos)

    def test_serie_con_dato_y_hueco(self):
        modelo = ModeloSeries()
        datos = pd.DataFrame({'Ancho_mm': [1.0, float('nan')]}, index=[2000, 2001])
        modelo.registrar('valida', datos)
        self.assertEqual(modelo.datos['valida'].loc[2000, 'Ancho_mm'], 1.0)
