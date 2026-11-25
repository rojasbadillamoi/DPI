import unittest
from dpi.medicion.calculo import calcular_anillos, anchos_puntos, anios_por_punto, _calcular_anillos
from dpi.medicion.modelo import ModeloMedicion


class CacheMedicion(unittest.TestCase):
    def test_reutilizacion_e_invalidacion(self):
        m = ModeloMedicion()
        m.cargar([(0, 0), (2, 0)], [False, False])
        _calcular_anillos.cache_clear()
        p = m.captura()
        calcular_anillos(p, 2).clear()
        self.assertEqual(anchos_puntos(p, 2), [1.0])
        self.assertEqual(anios_por_punto(p, 2, 2000, 2000, True)[1], {1})
        self.assertEqual(_calcular_anillos.cache_info().misses, 1)
        self.assertEqual(anchos_puntos(p, 1), [2.0])
        m.mover(1, (4, 0))
        self.assertEqual(anchos_puntos(m.captura(), 1), [4.0])
