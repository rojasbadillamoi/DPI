import unittest
import pandas as pd
from dpi.series.modelo import ModeloSeries


class TestEdicionSeries(unittest.TestCase):
    def test_editar_y_restaurar(self):
        m = ModeloSeries()
        original = pd.DataFrame({'Ancho_mm': [1., 2.]}, index=[2000, 2001])
        m.registrar('A', original)
        self.assertTrue(m.desplazar('A', 3))
        self.assertEqual(list(m.datos['A'].index), [2003, 2004])
        m.actualizar('A', pd.DataFrame({'Ancho_mm': [9.]}, index=[2003]))
        pd.testing.assert_frame_equal(m.originales['A'], original)
        m.restablecer('A')
        pd.testing.assert_frame_equal(m.datos['A'], original)
        with self.assertRaises(ValueError):
            m.actualizar('A', pd.DataFrame({'otro': [1]}))
        pd.testing.assert_frame_equal(m.datos['A'], original)
