import unittest
from dpi.medicion.datos import (mediciones_desde_anchos, mediciones_radio,
                                   normalizar_radio)


class TestFuenteUnicaMedicion(unittest.TestCase):
    def test_direcciones(self):
        self.assertEqual(mediciones_desde_anchos([1., 2.], 2000, 2001, True),
                         [{"anio": 2000, "ancho_mm": 1.}, {"anio": 2001, "ancho_mm": 2.}])
        self.assertEqual([d["anio"] for d in mediciones_desde_anchos([1., 2.], 2000, 2001, False)],
                         [2001, 2000])

    def test_migracion_y_recalibracion(self):
        radio = {"coords": [(0, 0), (2, 0), (6, 0)], "es_salto": [False]*3,
                 "datos_medidos": [{"anio": 2001, "ancho_mm": 99},
                                   {"anio": 2000, "ancho_mm": 99}]}
        nuevo = normalizar_radio(radio)
        self.assertNotIn("datos_medidos", nuevo)
        self.assertIn("datos_medidos", radio)
        self.assertEqual(nuevo["dir_idx"], 1)
        self.assertEqual([d["ancho_mm"] for d in mediciones_radio(nuevo, 2)], [1., 2.])
        self.assertEqual([d["ancho_mm"] for d in mediciones_radio(nuevo, 1)], [2., 4.])
        self.assertEqual([d["anio"] for d in mediciones_radio(nuevo, 2)], [2001, 2000])

    def test_legacy_sin_geometria(self):
        radio = {"datos_medidos": [{"anio": 2000, "ancho_mm": 3.}]}
        salida = mediciones_radio(radio, 2)
        salida[0]["ancho_mm"] = 9
        self.assertEqual(mediciones_radio(radio, 2)[0]["ancho_mm"], 3.)
