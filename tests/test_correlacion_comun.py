import unittest
import numpy as np
from dpi.ciencia.estadistica import pearson, pearson_desde_sumas
from dpi.ciencia.cofecha_nucleo import AcumuladosPar, r_de_sumas, r_quitando_cada_punto
from dpi.ciencia.quiebres import _acumulados_por_desfase
from dpi.medicion.grafico import correlacion_deslizante
from dpi.ciencia.transformacion import DIFFLOG


class TestCorrelacionComun(unittest.TestCase):
    def test_pearson_estable(self):
        x = 1e12 + np.arange(30.)
        y = 1e12 - np.arange(30.)
        self.assertAlmostEqual(pearson(x, y), -1.0, places=12)
        self.assertAlmostEqual(pearson([-1e308, 0., 1e308], [1., 2., 3.]), 1.)
        self.assertAlmostEqual(pearson([1e-300, 2e-300, 3e-300], [1., 2., 3.]), 1.)
        self.assertTrue(np.isnan(pearson([1., 1.], [1., 2.])))
        self.assertTrue(np.isnan(pearson([1., np.nan], [1., 2.])))
        self.assertTrue(np.isnan(pearson([1., 1. + 1e-10], [1., 2.], tolerancia=1e-9)))

    def test_sumas_escalar_vector(self):
        x = np.array([1., 4., 2., 7., 5.])
        y = np.array([2., 3., 6., 8., 9.])
        s = (len(x), x.sum(), y.sum(), x @ x, y @ y, x @ y)
        r = pearson(x, y)
        self.assertAlmostEqual(pearson_desde_sumas(*s), r)
        np.testing.assert_allclose(pearson_desde_sumas(*[np.array([v, v]) for v in s]), [r, r])

    def test_acumulados_estables(self):
        x = 1e12 + np.arange(30.)
        y = 1e12 - np.arange(30.)
        y[7] = np.nan
        a = AcumuladosPar(x, y)
        r, n = a.r(2, 25)
        self.assertEqual(n, 22)
        self.assertAlmostEqual(r, -1., places=12)

    def test_bloques_desfases_combinables(self):
        rng = np.random.default_rng(24)
        x = 1e12 + rng.normal(size=60)
        y = 1e12 + rng.normal(size=60)
        a = _acumulados_por_desfase(x, y, 2)
        r, n = r_de_sumas(a[1].sumas(0, 25), a[-1].sumas(25, 60))
        esperado = pearson(x, np.r_[y[1:26], y[24:59]])
        self.assertEqual(n, 60)
        self.assertAlmostEqual(r, esperado, places=10)

    def test_quitar_punto(self):
        rng = np.random.default_rng(42)
        x = 1e12 + rng.normal(size=30)
        y = 1e12 + rng.normal(size=30)
        pos, efecto, r = r_quitando_cada_punto(x, y)
        np.testing.assert_array_equal(pos, np.arange(30))
        self.assertAlmostEqual(r, pearson(x, y), places=12)
        esperado = [r - pearson(np.delete(x, i), np.delete(y, i)) for i in pos]
        np.testing.assert_allclose(efecto, esperado, atol=1e-12)

    def test_ventanas_medicion(self):
        anios = np.arange(2000, 2031)
        x = np.exp(np.sin(np.arange(31.)))
        centros, rs = correlacion_deslizante(anios, x, anios, x, 10, DIFFLOG)
        self.assertEqual(centros, [2006, 2011, 2016, 2021, 2026])
        np.testing.assert_allclose(rs, np.ones(5))
        centros, rs = correlacion_deslizante(anios, x, anios, x, 50, DIFFLOG)
        self.assertEqual(centros, [2016])
        np.testing.assert_allclose(rs, [1.])
