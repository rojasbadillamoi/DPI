import unittest
from dpi.medicion.ewlw import _calcular_anchos_ewlw_por_anillo as calcular, calcular_anchos_ewlw
class EWLW(unittest.TestCase):
    def test_entrada_tipada(self):
        from dpi.medicion.ewlw import anchos_ewlw_puntos, _calcular_anchos_ewlw_por_anillo
        from dpi.medicion.calculo import puntos_desde_geometria
        c, m = [(0, 0), (2, 0), (4, 0)], [False, 'ew_lw', False]
        for direccion in (True, False):
            self.assertEqual(anchos_ewlw_puntos(puntos_desde_geometria(c, m), 2, direccion),
                             _calcular_anchos_ewlw_por_anillo(c, m, 2, direccion))
    def test_direccion_y_quiebre(self):
        coords=[(0,0),(2,0),(4,0),(8,0),(14,0)]
        marcas=[False,'quiebre_ini','espacio','ew_lw',False]
        self.assertEqual(calcular(coords,marcas,2), [(6,3,3)])
        self.assertEqual(calcular([(0,0),(2,0),(8,0)],[False,'ew_lw',False],2,False),[(4,3,1)])
    def test_ausentes_y_anios(self):
        self.assertEqual(calcular_anchos_ewlw([(0,0),(1,0),(2,0),(4,0)],[False,False,'ew_lw',False],[{'anio':2000},{'anio':2001}],1),([2001],[1],[2001],[2]))
