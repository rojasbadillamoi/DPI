"""Regresiones de persistencia sin interfaz gráfica."""
import json
import tempfile
import unittest
from pathlib import Path

from dpi.medicion.sesion import (
    VERSION_FORMATO, guardar_sesion, leer_sesion, normalizar_sesion, ruta_sesion,
)


class TestSesionMedicion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.imagen = Path(self.tmp.name) / "árbol.png"
        self.radio = {"coords": [[0, 0], [10, 0]], "es_salto": [False, False],
                      "anio_medula": 2000, "anio_corteza": 2000, "dir_idx": 0}

    def test_ida_vuelta(self):
        activo = dict(self.radio, codigo="R1")
        guardar_sesion(self.imagen, 10, {"R1": self.radio}, activo)
        datos = leer_sesion(self.imagen)
        self.assertEqual(datos["version_formato"], VERSION_FORMATO)
        self.assertEqual(datos["pixeles_por_mm"], 10)
        self.assertEqual(datos["camino_activo"].coordenadas, ((0., 0.), (10., 0.)))
        self.assertEqual(datos["caminos_guardados"]["R1"].marcas, (False, False))
        self.assertFalse(datos["camino_activo"].datos_historicos)
        self.assertEqual(Path(ruta_sesion(self.imagen)).name, ".árbol.png_dpi.json")

    def test_migracion_legacy(self):
        radio = {"datos_medidos": [{"anio": 2002, "ancho_mm": 1.0},
                                  {"anio": 2001, "ancho_mm": 1.2}]}
        datos = normalizar_sesion({"caminos_guardados": {"R": radio}})
        migrado = datos["caminos_guardados"]["R"]
        self.assertEqual(migrado["dir_idx"], 1)
        self.assertEqual(migrado["anio_medula"], 2001)
        self.assertEqual(migrado["anio_corteza"], 2002)
        self.assertEqual(migrado["datos_medidos"], radio["datos_medidos"])
        self.assertEqual(migrado["coords"], [])
        self.assertNotIn("dir_idx", radio)

    def test_rechaza_datos_invalidos(self):
        for datos in (
            {"pixeles_por_mm": 0}, {"pixeles_por_mm": float("nan")},
            {"pixeles_por_mm": True}, {"version_formato": 99},
            {"camino_activo": []}, {"caminos_guardados": []},
            {"camino_activo": dict(self.radio, dir_idx=2)},
            {"camino_activo": dict(self.radio, anio_medula=1.5)},
            {"camino_activo": dict(self.radio, es_salto=[False])},
            {"camino_activo": dict(self.radio, es_salto=[False, "mal"] )},
            {"camino_activo": dict(self.radio, coords=[[0, 0], [float("inf"), 0]])},
        ):
            with self.subTest(datos=datos), self.assertRaises(ValueError):
                normalizar_sesion(datos)

    def test_rechaza_anios_historicos_duplicados(self):
        radio = {"datos_medidos": [{"anio": 2000, "ancho_mm": 1.0},
                                  {"anio": 2000, "ancho_mm": 2.0}]}
        with self.assertRaises(ValueError):
            normalizar_sesion({"caminos_guardados": {"R": radio}})

    def test_guardado_invalido_conserva_archivo(self):
        guardar_sesion(self.imagen, 10, {}, self.radio)
        ruta = Path(ruta_sesion(self.imagen))
        anterior = ruta.read_bytes()
        with self.assertRaises(ValueError):
            guardar_sesion(self.imagen, -1, {}, self.radio)
        self.assertEqual(ruta.read_bytes(), anterior)

    def test_ausente_y_json_corrupto(self):
        self.assertIsNone(leer_sesion(self.imagen))
        Path(ruta_sesion(self.imagen)).write_text("{", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            leer_sesion(self.imagen)

    def test_activo_sin_geometria_no_se_descarta(self):
        with self.assertRaises(ValueError):
            normalizar_sesion({"camino_activo": {"datos_medidos": [
                {"anio": 2000, "ancho_mm": 1.0}]}})
