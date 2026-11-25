import unittest
import numpy as np
import pandas as pd
import dpi.ciencia.estadistica as e
import dpi.ciencia.transformacion as t


class ContinuidadAnual(unittest.TestCase):
    def test_huecos_y_orden(self):
        s = pd.Series([8., 1., 2., 4.], index=[2004, 2000, 2001, 2003])
        self.assertEqual(e.diferencias_anuales(s).to_dict(), {2001: 1., 2004: 4.})
        self.assertEqual(t.transformar(s).index.tolist(), [2001, 2004])

    def test_glk(self):
        a = pd.Series([1., 2., 8., 9.], index=[2000, 2001, 2003, 2004])
        b = pd.Series([8., 9., 1., 2.], index=a.index)
        self.assertEqual(e.gleichlaufigkeit(a, b, 3), (1., 2))
        self.assertTrue(np.isnan(e.gleichlaufigkeit(a, b, 4)[0]))

    def test_hollstein(self):
        s = pd.Series([1., 2., 0., 4., np.inf, 8., 16.], index=range(2000, 2007))
        self.assertEqual(e._filtro_hollstein(s).index.tolist(), [2001, 2006])
        self.assertEqual(e.t_baillie_pilcher(s, s, 3)[2], 2)

    def test_desfases(self):
        y = [2000, 2001, 2003, 2004, 2005, 2006]
        a = pd.Series([1., 2., 8., 9., 4., 5.], index=y)
        b = pd.Series([8., 9., 1., 2., 6., 7.], index=y)
        r = e.estadisticos_por_desfase(a, b, 0, 3)
        self.assertEqual(r[2][0], e.gleichlaufigkeit(a, b, 3)[0])
        self.assertAlmostEqual(r[3][0], e.t_baillie_pilcher(a, b, 3)[0])

    def test_contiguas(self):
        rng = np.random.default_rng(42)
        for _ in range(100):
            a, b = rng.uniform(.1, 5, (2, 40))
            y = np.arange(1980, 2020)
            glk = 1 - np.mean(np.abs(np.sign(np.diff(a))-np.sign(np.diff(b))))/2
            self.assertAlmostEqual(e.glk_alineado(a, b, anios=y), glk)
            self.assertAlmostEqual(e.tbp_alineado(a, b, anios=y), e.tbp_filtrado(100*np.diff(np.log(a)), 100*np.diff(np.log(b)))[0])
            np.testing.assert_allclose(t.transformar(pd.Series(a,index=y)), np.diff(np.log(a)))

    def test_duplicados(self):
        with self.assertRaises(ValueError):
            e.diferencias_anuales(pd.Series([1,2], index=[2000,2000]))
