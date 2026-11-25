import unittest
from dpi.medicion.calculo import segmento_mas_cercano
class Segmentos(unittest.TestCase):
    def test_proyeccion(self):
        self.assertEqual(segmento_mas_cercano([(0,0),(2,0)],1,1,2),(0,.5,1.))
        self.assertIsNone(segmento_mas_cercano([(0,0),(2,0)],1,1,.5))
