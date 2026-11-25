"""Regresiones de proyección de eventos y lectura JSON."""
import io
import unittest
from dpi.infraestructura.json_seguro import cargar_json
from dpi.medicion.anomalias import tabla_eventos


class TestEventosAnomaliasYLimitesJson(unittest.TestCase):
    def test_eventos_binarios(self):
        tabla = tabla_eventos([1999, 2000, 2001], {2000: "fuego", 2001: "helada"},
                              [("fuego", "Fuego"), ("helada", "Helada")])
        self.assertEqual(list(tabla.columns), ["Año", "Fuego", "Helada"])
        self.assertEqual(tabla.values.tolist(), [[1999, 0, 0], [2000, 1, 0], [2001, 0, 1]])

    def test_json_fuera_de_rango(self):
        for literal in ("1e999", "-1e999", "Infinity", "NaN"):
            with self.subTest(literal=literal), self.assertRaises(ValueError):
                cargar_json(io.StringIO(literal))
        self.assertEqual(cargar_json(io.StringIO("1e2")), 100.0)
