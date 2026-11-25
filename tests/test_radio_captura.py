import unittest
from dpi.medicion.modelo import ModeloMedicion, RadioMedicion

class TestRadioCaptura(unittest.TestCase):
    def test_captura_independiente(self):
        m = ModeloMedicion()
        m.cargar([(0,0),(1,0)], [False, False])
        r = RadioMedicion('A', m.captura(), 2000, 2000, 0, {2000: 'tipo'})
        m.limpiar()
        self.assertEqual(len(r.a_dict()['coords']), 2)
        self.assertEqual(r.a_dict(activo=True)['anomalias'], {2000: 'tipo'})
        d = r.a_dict()
        d['anomalias'].clear()
        self.assertEqual(r.a_dict()['anomalias'], {2000: 'tipo'})
