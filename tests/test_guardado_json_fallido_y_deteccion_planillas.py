"""Regresiones de persistencia y detección de formatos."""
import tempfile
import unittest
from pathlib import Path
from dpi.infraestructura.json_seguro import guardar_json
from dpi.formatos.planillas import es_planilla


class TestGuardadoJsonYPlanillas(unittest.TestCase):
    def test_json_fallido_conserva_destino(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "datos.json"
            ruta.write_text("original", encoding="utf-8")
            with self.assertRaises(TypeError):
                guardar_json(ruta, {"dato": object()})
            self.assertEqual(ruta.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(carpeta).iterdir()), [ruta])

    def test_planilla_ruta_relativa_oculta(self):
        self.assertTrue(es_planilla(".datos/serie.xlsx"))
        self.assertTrue(es_planilla(Path("serie.ODS")))
        self.assertTrue(es_planilla(".xls"))
        self.assertFalse(es_planilla("serie.csv"))
