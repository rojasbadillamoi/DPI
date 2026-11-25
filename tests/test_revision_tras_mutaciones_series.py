import unittest
import pandas as pd
from dpi.series.modelo import ModeloSeries

class Revisiones(unittest.TestCase):
    def test_revision_cambios(self):
        m = ModeloSeries()
        df = pd.DataFrame({'Ancho_mm': [1.]}, index=[2000])
        anterior = m.revision
        for cambio in (lambda: m.registrar('A', df), lambda: m.actualizar('A', df),
                       lambda: m.probar_correccion('A', df), m.descartar_correccion,
                       lambda: m.restablecer('A'), lambda: m.eliminar('A')):
            cambio()
            self.assertGreater(m.revision, anterior)
            anterior = m.revision
