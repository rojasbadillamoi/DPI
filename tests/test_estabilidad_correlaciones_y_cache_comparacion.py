import unittest
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import correlaciones_pares


class TestEstabilidadCorrelacionesYCache(unittest.TestCase):
    def test_desplazamiento(self):
        x = np.arange(30, dtype=float)
        np.testing.assert_allclose(correlaciones_pares(np.c_[1e12+x, 1e12-x]), [-1])

    def test_no_finitos_y_constantes(self):
        x = np.arange(30, dtype=float)
        y = x.copy(); y[3] = np.inf
        np.testing.assert_allclose(correlaciones_pares(np.c_[x, y, np.ones(30)]), [1])

    def test_solape_local(self):
        x = np.r_[1e15, np.arange(20.)]
        y = np.r_[np.nan, np.arange(20.)]
        np.testing.assert_allclose(correlaciones_pares(np.c_[x, y]), [1])

    def test_cache(self):
        from dpi.ciencia.comparacion_nucleo import clave_cache_comparacion
        df = pd.DataFrame({'Ancho_mm': [1., 2., 3.]}, index=[2000, 2001, 2002])
        args = dict(revision=None, series={'a': df}, nombre_crono='c',
                    cronologia=df.copy(), meta={})
        def firma(**cambios):
            return clave_cache_comparacion(['a'], **(args | cambios))
        inicial = firma()
        self.assertEqual(inicial, firma())
        df.iloc[:, 0] = [3., 2., 1.]
        self.assertNotEqual(inicial, firma())
        inicial = firma()
        args['meta']['columna_valor'] = 'Ancho_mm'
        self.assertNotEqual(inicial, firma())
        self.assertNotEqual(firma(revision=1), firma(revision=2))
        self.assertNotEqual(firma(cofecha=(True,)), firma(cofecha=(False,)))
