import unittest
from dpi.medicion.calculo import calcular_anillos, puntos_desde_geometria
class Segmentacion(unittest.TestCase):
    def test_segmentos(self):
        p = puntos_desde_geometria([(i,0) for i in range(8)], [False,'ew_lw',True,'quiebre_ini','espacio',False,'ew_lw',False])
        a = calcular_anillos(p,1)
        self.assertEqual([r.segmentos for r in a], [(1,), (3,5), (6,7)])
        self.assertEqual([r.completo for r in a], [False,True,True])
        self.assertEqual([r.ancho_mm for r in a], [1,2,2])
