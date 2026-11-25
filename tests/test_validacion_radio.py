import unittest
from dpi.ciencia.indice_anual import validar_anios
from dpi.medicion.modelo import RadioMedicion
class Validacion(unittest.TestCase):
    def test_bool(self):
        with self.assertRaises(ValueError): validar_anios([True,2000])
    def test_radio(self):
        for kw in [{'medula':1},{'anomalias':{'2000':'a'}},{'datos_historicos':((2000,float('nan')),)}]:
            with self.assertRaises(ValueError): RadioMedicion('R',(),2000,2000,0,**kw)
