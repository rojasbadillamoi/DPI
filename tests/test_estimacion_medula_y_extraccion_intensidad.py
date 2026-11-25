"""Verifica que los algoritmos separados de Qt se pueden usar por sí solos."""
import unittest
import numpy as np
from dpi.medicion.pith import ajuste_degenerado, estimar_anillos_faltantes
from dpi.medicion.intensidad import extraer_intensidad_por_anillo


class TestEstimacionMedulaEIntensidad(unittest.TestCase):
    def test_medula(self):
        resultado = estimar_anillos_faltantes(10., [2., 2., 2.])
        self.assertEqual(resultado['n_media'], 5.)
        self.assertTrue(ajuste_degenerado([(0.,0.), (1.,0.)], 51.))
        self.assertFalse(ajuste_degenerado([(0.,0.), (1.,0.)], 50.))

    def test_intensidad(self):
        img = np.zeros((20,20,3), dtype=np.uint8)
        img[:,:,0] = 60
        r = extraer_intensidad_por_anillo(None, img, [(4,10),(12,10)],
                                          [False,False], 2., banda_px=2, canales=['B'])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['B_mean'], 60.)
        self.assertEqual(r[0]['B_min'], 60.)
        self.assertEqual(r[0]['B_max'], 60.)
