import unittest
from dpi.medicion.modelo import RadioMedicion


class RadioInvariantes(unittest.TestCase):
    def test_metadatos_invalidos(self):
        for medula, corteza, direccion in [(2000, 2001, 2), (True, 2001, 0), (2000, 2001.5, 0)]:
            with self.subTest(medula=medula, corteza=corteza, direccion=direccion):
                with self.assertRaises(ValueError):
                    RadioMedicion('R', (), medula, corteza, direccion)
