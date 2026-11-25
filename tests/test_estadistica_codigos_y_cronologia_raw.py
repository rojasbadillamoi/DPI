"""Regresiones deterministas del núcleo científico, sin interfaz gráfica."""
import unittest

import numpy as np
import pandas as pd

from dpi.ciencia.codigos import clave_codigo_dendro
from dpi.ciencia.cofecha_nucleo import AcumuladosPar, Matriz
from dpi.ciencia.cronologia import _construir_cronologia_desde_series
from dpi.ciencia.estadistica import calcular_eps, pearson


class NucleoCientifico(unittest.TestCase):
    def test_pearson(self):
        x = np.arange(20, dtype=float)
        self.assertAlmostEqual(pearson(x, 3*x + 2), 1)
        self.assertAlmostEqual(pearson(x, -x), -1)
        self.assertTrue(np.isnan(pearson(x, np.ones_like(x))))
        self.assertTrue(np.isnan(pearson(x, x[:-1])))

    def test_eps(self):
        self.assertAlmostEqual(calcular_eps(0.5, 4), 0.8)
        self.assertAlmostEqual(calcular_eps(1.0, 4), 1.0)

    def test_orden_codigos(self):
        nombres = ['COS10A', 'COS2B', 'COS2A', 'COS1A']
        self.assertEqual(sorted(nombres, key=clave_codigo_dendro),
                         ['COS1A', 'COS2A', 'COS2B', 'COS10A'])

    def test_matriz_anual(self):
        m = Matriz.desde_series({'a': pd.Series([1., 3.], index=[2000, 2002]),
                                 'b': pd.Series([2., 4.], index=[2001, 2003])})
        np.testing.assert_array_equal(m.anios, np.arange(2000, 2004))
        np.testing.assert_allclose(m.columna('a'), [1, np.nan, 3, np.nan])
        np.testing.assert_allclose(m.columna('b'), [np.nan, 2, np.nan, 4])

    def test_acumulados_ventanas(self):
        rng = np.random.default_rng(42)
        x, y = rng.normal(size=(2, 40))
        x[5] = np.nan
        y[12] = np.inf
        acumulados = AcumuladosPar(x, y)
        for a in range(0, 30, 3):
            for b in range(a + 3, 41, 4):
                u, v = x[a:b], y[a:b]
                ok = np.isfinite(u) & np.isfinite(v)
                r, n = acumulados.r(a, b)
                self.assertEqual(n, int(ok.sum()))
                if n >= 3:
                    self.assertAlmostEqual(r, np.corrcoef(u[ok], v[ok])[0, 1], places=10)
                else:
                    self.assertTrue(np.isnan(r))

    def test_cronologia_raw(self):
        a = pd.DataFrame({'Ancho_mm': [1., 3.]}, index=[2000, 2002])
        b = pd.DataFrame({'Ancho_mm': [2., 5.]}, index=[2001, 2002])
        cron, meta = _construir_cronologia_desde_series(
            {'COS1A': a, 'COS2A': b}, ['COS1A', 'COS2A'], 'raw', 'spline', 'mean')
        np.testing.assert_array_equal(cron.index, [2000, 2001, 2002])
        np.testing.assert_allclose(cron['Raw'], [1., 2., 4.])
        np.testing.assert_array_equal(cron['N'], [1, 1, 2])
        self.assertEqual(meta['n_anios'], 3)
        self.assertEqual(meta['columna_valor'], 'Raw')
