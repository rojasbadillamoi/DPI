import unittest
import numpy as np
from dpi.medicion.pith import ajustar_circulo_minimos_cuadrados as ajustar
class Circulo(unittest.TestCase):
    def test_centros(self):
        for x,y in [(0,0),(10,-3),(1e9,1e9)]:
            np.testing.assert_allclose(ajustar([(x+2,y),(x,y+2),(x-2,y),(x,y-2)]), [x,y,2], atol=1e-7, rtol=0)
    def test_degenerados(self):
        for p in [[(0,0),(1,1),(2,2)],[(0,0)]*3,[(0,0),(1,2),(float('nan'),1)]]:
            self.assertIsNone(ajustar(p))
