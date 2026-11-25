import unittest
import pandas as pd
from dpi.ciencia.transformacion import transformar_para_correlacion
class Transformacion(unittest.TestCase):
    def test_sin_transformar(self):
        s = pd.Series([1., 2., 3.], index=[2000,2001,2002])
        for activo, crono in [(False, False),(True, True)]:
            r = transformar_para_correlacion(s, crono, activo=activo, aplicar_serie=False,
                aplicar_crono=False, meta={}, cronologia=None, parametros={})
            pd.testing.assert_series_equal(r,s)
