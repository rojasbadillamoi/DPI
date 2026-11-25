import unittest
import numpy as np
from dpi.medicion.intensidad import extraer_intensidad_por_anillo as extraer
class Intensidad(unittest.TestCase):
    def test_indice_sin_muestras(self):
        img=np.full((20,20,3),70,dtype=np.uint8)
        r=extraer(None,img,[(2,5),(5,5),(5,5),(12,5)],[False]*4,1,0,['B'])
        self.assertEqual([d['indice_anillo'] for d in r],[0,2])
    def test_limite_ewlw(self):
        img=np.full((20,20,3),70,dtype=np.uint8)
        r=extraer(None,img,[(2,5),(5,5),(8,5),(12,5)],[False,False,'ew_lw',False],1,0,['B'])
        self.assertEqual([d['indice_anillo'] for d in r],[0,1])
