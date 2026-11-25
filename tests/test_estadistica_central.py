import unittest

import numpy as np
import pandas as pd
import dpi.ciencia.estadistica as e


class TestEstadisticaCentral(unittest.TestCase):
    def test_pares_indices_y_oraculo(self):
        rng = np.random.default_rng(1451)
        mat = rng.normal(size=(80, 5)) + 1e9
        mat[::3, 0] = np.nan
        mat[::4, 1] = np.inf
        mat[:, 3] = 1
        mat[:75, 4] = np.nan
        ii, jj, rs = e.correlaciones_pares(mat, devolver_indices=True)
        esperados = []
        for i in range(mat.shape[1]):
            for j in range(i + 1, mat.shape[1]):
                ok = np.isfinite(mat[:, i]) & np.isfinite(mat[:, j])
                if ok.sum() >= 10:
                    r = e.pearson(mat[ok, i], mat[ok, j])
                    if np.isfinite(r):
                        esperados.append((i, j, r))
        self.assertEqual(list(zip(ii, jj)), [(i, j) for i, j, _ in esperados])
        np.testing.assert_allclose(rs, [r for _, _, r in esperados], atol=1e-12)
        np.testing.assert_array_equal(rs, e.correlaciones_pares(mat))
        for forma in ((0, 3), (3, 1)):
            self.assertEqual(tuple(len(a) for a in e.correlaciones_pares(
                np.empty(forma), devolver_indices=True)), (0, 0, 0))

    def test_rbar_global_y_arboles(self):
        nombres = ['QLH107A', 'QLH107B', 'QLH108A']
        x = np.arange(1., 31.)
        mat = np.c_[x, x + np.sin(x), x[::-1] + np.cos(x)]
        mat[3, 1] = np.nan
        mat[5, 2] = np.inf
        series = {n: pd.DataFrame({'Ancho_mm': mat[:, i]},
                                  index=np.arange(1900, 1930))
                  for i, n in enumerate(nombres)}
        ii, jj, rs = e.correlaciones_pares(mat, devolver_indices=True)
        self.assertAlmostEqual(e.calcular_rbar(series, nombres), rs.mean())
        stats = e.rbar_entre_arboles(series, nombres)
        dentro = (ii == 0) & (jj == 1)
        self.assertEqual(stats['n_pares_wt'], 1)
        self.assertEqual(stats['n_pares_bt'], 2)
        self.assertAlmostEqual(stats['rbar_wt'], rs[dentro].mean())
        self.assertAlmostEqual(stats['rbar_bt'], rs[~dentro].mean())

    def test_eps(self):
        self.assertAlmostEqual(e.calcular_eps(0.5, 4), 0.8)
        self.assertAlmostEqual(e.calcular_eps(0.5, 2.5), 1.25 / 1.75)
        for r, n in [(-0.5, 3), (0.5, 1), (0.5, np.inf), (np.nan, 4)]:
            self.assertTrue(np.isnan(e.calcular_eps(r, n)))

    def test_ventanas_moviles(self):
        anios = np.r_[np.arange(1900, 1910), np.arange(1912, 1930)]
        x = np.arange(len(anios), dtype=float)
        a = pd.Series(10 + x + np.sin(x), index=anios)
        b = pd.Series(20 + x + np.cos(x), index=anios)
        years, rs = e._r_movil(a, b, list(anios), 5)
        stats = e._stats_movil(a, b, list(anios), 5)
        self.assertTrue(years)
        self.assertEqual(years, stats[0])
        np.testing.assert_array_equal(rs, stats[1])
        for y, r in zip(years, rs):
            ventana = [z for z in anios if 0 < abs(z-y) <= 5]
            self.assertAlmostEqual(r, e.pearson(a.loc[ventana], b.loc[ventana]))


if __name__ == '__main__':
    unittest.main()
