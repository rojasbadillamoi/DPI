import unittest
import pandas as pd
from dpi.series.modelo import ModeloSeries

class TestOriginalesProtegidos(unittest.TestCase):
    def test_copia_y_asociacion(self):
        m = ModeloSeries()
        m.registrar('A', pd.DataFrame({'Ancho_mm': [1.]}, index=[2000]))
        copia = m.originales['A']
        copia.iloc[0,0] = 9.
        self.assertEqual(m.originales['A'].iloc[0,0], 1.)
        with self.assertRaises(TypeError):
            m.originales['A'] = pd.DataFrame()
        m.restablecer('A')
        self.assertEqual(m.datos['A'].iloc[0,0], 1.)
