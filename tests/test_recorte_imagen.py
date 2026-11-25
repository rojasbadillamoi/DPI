import unittest
import numpy as np
from dpi.medicion.intensidad import extraer_intensidad_por_anillo as extraer
class Recorte(unittest.TestCase):
    def test_gradiente(self):
        img=np.zeros((25,25,3),dtype=np.uint8);img[:,:,0]=np.arange(25)
        args=(None,img,[(2,10),(18,10)],[False,False],1,0,['B'],.5)
        r=extraer(*args,'centro')[0]
        self.assertEqual((r['B_min'],r['B_max']),(6,14))
        self.assertEqual(extraer(*args,'ew',False)[0]['B_min'],10)
