"""Regresiones de la migración a paquetes."""
import importlib
import unittest
from pathlib import Path


class CompatibilidadPaquetes(unittest.TestCase):
    def test_modulos_canonicos(self):
        for nombre in ('dpi.medicion.modelo', 'dpi.medicion.calculo', 'dpi.medicion.marcas', 'dpi.medicion.datos', 'dpi.medicion.sesion', 'dpi.medicion.ewlw', 'dpi.medicion.pith', 'dpi.medicion.intensidad', 'dpi.medicion.grafico', 'dpi.series.modelo', 'dpi.medicion.autodeteccion'):
            with self.subTest(modulo=nombre):
                self.assertIsNotNone(importlib.import_module(nombre))

    def test_infraestructura_canonica(self):
        for nombre in ("dpi.infraestructura.json_seguro", "dpi.infraestructura.imagen"):
            self.assertIsNotNone(importlib.import_module(nombre))

    def test_api_formatos(self):
        for modulo, nombres in {
            "pos": ("leer_pos", "escribir_pos"),
            "wid": ("leer_wid",),
            "tucson": ("leer_tucson_multi", "escribir_tucson"),
            "compacto": ("leer_formato_compacto",),
            "planillas": ("leer_planilla", "escribir_excel"),
            "tabular": ("leer_tabular", "escribir_tabla"),
            "cronologias": ("_leer_cronologia_guardada",),
            "deteccion": ("leer_dendro_auto", "leer_series_auto"),
            "exportacion": ("exportar_serie_2col",),
        }.items():
            nuevo = importlib.import_module("dpi.formatos." + modulo)
            for nombre in nombres:
                self.assertTrue(callable(getattr(nuevo, nombre)))

    def test_cronologia_compatible(self):
        from dpi.ciencia import cronologia, tendencias, autorregresion, estabilizacion
        self.assertIs(cronologia._spline_cook, tendencias._spline_cook)
        self.assertIs(cronologia._residualizar_indice, autorregresion._residualizar_indice)
        self.assertIs(cronologia.estabilizar_varianza, estabilizacion.estabilizar_varianza)

    def test_perfiles_fabrica(self):
        from dpi.medicion.autodeteccion import RUTA_PERFILES_FABRICA
        self.assertEqual(Path(RUTA_PERFILES_FABRICA).resolve(),
                         Path(__file__).resolve().parents[1] / "species_profiles.json")
        self.assertTrue(Path(RUTA_PERFILES_FABRICA).is_file())
