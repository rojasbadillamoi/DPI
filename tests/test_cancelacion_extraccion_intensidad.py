import unittest
import numpy as np
from dpi.medicion.intensidad import extraer_intensidad_por_anillo
class Cancelacion(unittest.TestCase):
    def test_cancelacion_no_entrega_parciales(self):
        r=extraer_intensidad_por_anillo(None,np.zeros((20,20,3),dtype=np.uint8),[(2,5),(5,5)], [False,False],1,cancelado=lambda:True)
        self.assertEqual(r,[])
