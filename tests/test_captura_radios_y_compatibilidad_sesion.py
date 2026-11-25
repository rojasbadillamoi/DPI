import tempfile
import unittest
from pathlib import Path

from dpi.medicion.modelo import ModeloMedicion, PuntoMedicion, RadioMedicion
from dpi.medicion.datos import mediciones_radio
from dpi.medicion.sesion import guardar_sesion, leer_sesion


class TestCapturaRadiosYCompatibilidadSesion(unittest.TestCase):
    def test_captura_y_recalibracion(self):
        m = ModeloMedicion()
        m.cargar([(0, 0), (2, 0), (6, 0)], [False] * 3)
        r = RadioMedicion("R", m.captura(), 2000, 2001, 0)
        m.mover(1, (8, 0))
        self.assertEqual(r.coordenadas[1], (2., 0.))
        self.assertEqual([d["ancho_mm"] for d in mediciones_radio(r, 2)], [1., 2.])
        self.assertEqual([d["ancho_mm"] for d in mediciones_radio(r, 1)], [2., 4.])
        m.restaurar(r.puntos)
        self.assertIs(m.captura()[0], r.puntos[0])

    def test_sesion_tipificada_y_compatibilidad(self):
        with tempfile.TemporaryDirectory() as tmp:
            imagen = Path(tmp) / "arbol.png"
            r = RadioMedicion("R", (PuntoMedicion((0, 0)), PuntoMedicion((2, 0))),
                              2000, 2000, 0, {2000: "tipo"})
            guardar_sesion(imagen, 2, {"R": r}, r)
            sesion = leer_sesion(imagen)
            self.assertEqual(sesion["caminos_guardados"]["R"], r)
            self.assertEqual(sesion["camino_activo"], r)
            self.assertEqual(leer_sesion(imagen)["caminos_guardados"]["R"], r)

    def test_legacy_sin_geometria(self):
        with tempfile.TemporaryDirectory() as tmp:
            imagen = Path(tmp) / "arbol.png"
            historico = {"datos_medidos": [{"anio": 2000, "ancho_mm": 3.}]}
            guardar_sesion(imagen, 2, {"R": historico}, {})
            sesion = leer_sesion(imagen)
            r = sesion["caminos_guardados"]["R"]
            self.assertIsNone(sesion["camino_activo"])
            self.assertEqual(mediciones_radio(r, 100), historico["datos_medidos"])
            guardar_sesion(imagen, 2, {"R": r}, {})
            self.assertEqual(leer_sesion(imagen)["caminos_guardados"]["R"], r)

    def test_rechaza_puntos_invalidos(self):
        with self.assertRaises(ValueError):
            RadioMedicion("R", ((0, 0),), 2000, 2000, 0)
