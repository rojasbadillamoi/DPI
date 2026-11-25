import unittest
from dpi.infraestructura.json_seguro import a_json, restaurar_claves_int

class Claves(unittest.TestCase):
    def test_colisiones(self):
        with self.assertRaises(ValueError):
            a_json({1990: 1, '1990': 2})
        with self.assertRaises(ValueError):
            restaurar_claves_int({'01': 1, '1': 2})
