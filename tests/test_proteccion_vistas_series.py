import unittest
import pandas as pd
from dpi.series.modelo import ModeloSeries

class LecturaSeries(unittest.TestCase):
    def test_no_se_modifica_por_vista(self):
        m = ModeloSeries()
        m.registrar('A', pd.DataFrame({'Ancho_mm': [1.]}, index=[2000]))
        with self.assertRaises(TypeError):
            m.datos['A'] = pd.DataFrame()
        m.datos['A'].iloc[0, 0] = 9
        self.assertEqual(m.datos['A'].iloc[0, 0], 1.)
