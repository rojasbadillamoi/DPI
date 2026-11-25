"""Regresiones de la media biweight común a cronología y COFECHA."""
import unittest

import numpy as np

from dpi.ciencia.estadistica import media_biweight
from dpi.ciencia.cronologia import _biweight_mean
from dpi.ciencia.cofecha_nucleo import Maestro, _media_biweight


def _referencia(x, c=9.0, minimo=6):
    """Oráculo escalar de la implementación histórica de cronología."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return np.nan
    m = np.median(x)
    mad = np.median(np.abs(x - m))
    if x.size < minimo or mad == 0:
        return m
    u = (x - m) / (c * mad + 1e-6)
    w = np.where(np.abs(u) <= 1, (1 - u ** 2) ** 2, 0.0)
    return np.sum(w * x) / w.sum() if w.sum() > 0 else m


class TestMediaBiweight(unittest.TestCase):
    def test_equivalencia_vectorizada(self):
        rng = np.random.default_rng(2026)
        mat = rng.normal(1.0, 0.2, size=(120, 15))
        mat[::3, :8] = np.nan
        mat[::5, 0] = np.inf
        mat[::7, 1] = -np.inf
        mat[::11, -1] = 1000
        esperado = np.array([_referencia(fila) for fila in mat])
        for obtenido in (media_biweight(mat, axis=1),
                         media_biweight(mat.T, axis=0),
                         _media_biweight(mat),
                         np.array([_biweight_mean(fila) for fila in mat])):
            np.testing.assert_allclose(obtenido, esperado, rtol=1e-13,
                                       atol=1e-13, equal_nan=True)

    def test_casos_limite(self):
        self.assertTrue(np.isnan(media_biweight([])))
        self.assertTrue(np.isnan(media_biweight([np.nan, np.inf, -np.inf])))
        self.assertEqual(media_biweight([1, 2, 100, np.inf]), 2)
        self.assertEqual(media_biweight([1, 1, 1, 1, 1, 1.0000001]), 1)
        self.assertEqual(media_biweight([2] * 8), 2)
        np.testing.assert_array_equal(media_biweight(np.empty((3, 0)), axis=1),
                                      np.full(3, np.nan))
        self.assertEqual(media_biweight(np.empty((0, 3)), axis=1).shape, (0,))
        self.assertEqual(media_biweight([1, 2, 3, 4, 5, 90], minimo=7), 3.5)
        with self.assertRaises(ValueError):
            media_biweight([1, 2, 3], c=0)

    def test_maestro_leave_one_out(self):
        rng = np.random.default_rng(24)
        mat = rng.normal(size=(40, 9))
        mat[::4, :3] = np.nan
        maestro = Maestro(mat, robusto=True)
        np.testing.assert_allclose(maestro.valores, [_referencia(f) for f in mat])
        for j in range(mat.shape[1]):
            esperado = [_referencia(f) for f in np.delete(mat, j, axis=1)]
            np.testing.assert_allclose(maestro.excluyendo(j), esperado,
                                       rtol=1e-13, atol=1e-13, equal_nan=True)


if __name__ == "__main__":
    unittest.main()
