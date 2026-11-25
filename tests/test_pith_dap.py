import unittest
from dpi.medicion.pith import distancia_faltante_dap
class DAP(unittest.TestCase):
    def test_marcas(self):
        self.assertEqual(distancia_faltante_dap([(i,0) for i in range(6)],[False,'ew_lw','quiebre_ini','espacio',False,True],10),7)
