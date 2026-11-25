import unittest
import pandas as pd
from dpi.ciencia.indice_anual import validar_anios
from dpi.series.modelo import ModeloSeries

class Anios(unittest.TestCase):
    def test_invalidos(self):
        for idx in ([2**53], [1, 1], [1.5], [float('inf')]):
            with self.assertRaises(ValueError):
                validar_anios(idx)
    def test_desfase(self):
        m = ModeloSeries()
        m.registrar('A', pd.DataFrame({'Ancho_mm': [1.]}, index=[2000]))
        for valor in (False, 0., None, ''):
            with self.assertRaises(ValueError):
                m.desplazar('A', valor)
