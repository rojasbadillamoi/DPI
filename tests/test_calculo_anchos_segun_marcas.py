import unittest
from dpi.medicion.modelo import ModeloMedicion
from dpi.medicion.calculo import anchos_anillos, anchos_puntos


class TestAnchosTipados(unittest.TestCase):
    def test_marcas(self):
        m = ModeloMedicion()
        m.cargar([(i, 0) for i in range(7)],
                 [False, 'ew_lw', False, True, 'quiebre_ini', 'espacio', False])
        self.assertEqual(anchos_puntos(m.captura(), 2), [1., 1.])
        self.assertEqual(anchos_anillos(m.coordenadas, m.marcas, 2), [1., 1.])
        for escala in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                anchos_puntos(m.captura(), escala)
        with self.assertRaises(ValueError):
            anchos_anillos([(0, 0)], [], 1)
