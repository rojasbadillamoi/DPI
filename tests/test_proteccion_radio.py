import unittest
from dpi.medicion.sesion import normalizar_sesion

class TestMetadatosRadio(unittest.TestCase):
    def test_anomalias_y_extremos(self):
        r = normalizar_sesion({'camino_activo': {'coordenadas': [(0,0),(1,0)],
            'es_salto': [False, False], 'anomalias': {'2000': 'tipo'}, 'medula': True}})
        self.assertEqual(r['camino_activo']['anomalias'], {2000: 'tipo'})
        self.assertTrue(r['camino_activo']['medula'])

    def test_anomalia_invalida(self):
        with self.assertRaises(ValueError):
            normalizar_sesion({'camino_activo': {'anomalias': {'no-anio': 'tipo'}}})
