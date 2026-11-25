import unittest
import numpy as np
from dpi.infraestructura.imagen import preparar_banda_rgb
class Imagen(unittest.TestCase):
    def test_rgb_y_canales(self):
        img = np.array([[[10, 20, 30]]], dtype=np.uint8)
        np.testing.assert_array_equal(preparar_banda_rgb(img, 'RGB', 0, 1), [[[30,20,10]]])
        np.testing.assert_array_equal(preparar_banda_rgb(img, 'R', 5, 2), [[[65,65,65]]])
        np.testing.assert_array_equal(img, [[[10,20,30]]])
