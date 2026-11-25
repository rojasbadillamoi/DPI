import unittest
from dpi.medicion.pith import ajuste_degenerado, distancia_faltante_dap
from dpi.medicion.ewlw import calcular_anchos_ewlw
from dpi.medicion.intensidad import valores_intensidad, segmentos_banda_intensidad


class TestCalculosDapEwlwEIntensidad(unittest.TestCase):
    def test_dap(self):
        self.assertEqual(distancia_faltante_dap([(0,0),(3,4),(6,8)], [False,False,True], 10), 5)
        self.assertEqual(distancia_faltante_dap([(0,0),(3,4)], [False,False], 2), 0)

    def test_ewlw_exportacion(self):
        self.assertEqual(calcular_anchos_ewlw([(0,0),(2,0),(4,0)], [False,'ew_lw',False], [{'anio':2000}], 2), ([2000],[1.0],[2000],[1.0]))

    def test_metricas_intensidad(self):
        datos = [{'B_mean':12, 'R_mean':3, 'G_mean':0}]
        self.assertEqual(valores_intensidad(datos, 'B_R', 'mean'), [4])
        self.assertEqual(valores_intensidad(datos, 'B_G', 'mean'), [0])
        self.assertEqual(valores_intensidad(datos, 'B', 'mean'), [12])

    def test_segmentos_banda(self):
        self.assertEqual(segmentos_banda_intensidad([(i,0) for i in range(6)], [False,'ew_lw',False,True,'espacio',False]), [[(0,1),(1,2)],[(4,5)]])
