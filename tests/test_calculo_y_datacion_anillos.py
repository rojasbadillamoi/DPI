import unittest
from dpi.medicion.calculo import calcular_anillos, anios_por_punto
from dpi.medicion.modelo import ModeloMedicion

class Anillos(unittest.TestCase):
    def test_quiebre_y_ewlw(self):
        m = ModeloMedicion()
        m.cargar([(i, 0) for i in range(7)],
                 [False, 'ew_lw', False, True, 'quiebre_ini', 'espacio', False])
        p = m.captura()
        self.assertEqual([a.ancho_mm for a in calcular_anillos(p, 2)], [1., 1.])
        anios, cierres = anios_por_punto(p, 2, 2000, 2001, True)
        self.assertEqual(cierres, {2, 6})
        self.assertEqual([anios[i] for i in sorted(cierres)], [2000, 2001])
