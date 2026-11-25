import unittest
import pandas as pd
from dpi.ciencia.comparacion_nucleo import comparar_serie, SeriePreparada
class Comparacion(unittest.TestCase):
    def test_sin_solape_posible(self):
        a = pd.Series([1.,2.], index=[2000,2001])
        r = comparar_serie('A', SeriePreparada(a,a,a), SeriePreparada(a,a,a))
        self.assertEqual(r['nombre_serie'],'A')
        self.assertEqual(r['shifts'],[])

    def test_comparacion_con_solape(self):
        import numpy as np
        a = pd.Series(np.exp(np.sin(np.arange(60))), index=range(1900,1960))
        r = comparar_serie('A', SeriePreparada(a,a,a), SeriePreparada(a,a,a))
        self.assertEqual(r['mejor_shift'], 0)
        self.assertAlmostEqual(r['mejor_r'], 1.)
        self.assertIs(r['serie_a'], a)

    def test_resumen_comun(self):
        from dpi.ciencia.comparacion_nucleo import resumir_desfases
        a = pd.Series([1.,2.], index=[2000,2001])
        resultado = resumir_desfases('A', [0, 1], [0.1, 0.9], [0.5, 0.9], [1., 8.], [20, 20], a, a)
        self.assertEqual(resultado['mejor_shift'], 1)
        self.assertIs(resultado['serie_a'], a)
        self.assertEqual(resumir_desfases('A', [], [], [], [], [], a, a)['shifts'], [])

    def test_serie_vacia(self):
        a = pd.Series(dtype=float)
        self.assertEqual(comparar_serie('A', SeriePreparada(a,a,a), SeriePreparada(a,a,a))['shifts'], [])

    def test_desfase_positivo(self):
        import numpy as np
        from dpi.ciencia.comparacion_nucleo import analizar_desfases
        rng = np.random.default_rng(47)
        a = pd.Series(rng.uniform(1, 5, 70), index=range(100,170))
        b = pd.Series(a.values.copy(), index=range(2000,2070))
        shifts, rs, glks, tbps, ns = analizar_desfases(a, b, a, b)
        self.assertEqual(shifts[int(np.argmax(rs))], 1900)
        self.assertAlmostEqual(max(rs), 1.)
