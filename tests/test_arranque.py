"""Regresiones de arranque y códigos de salida del lanzador."""
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_dpi


class TestLanzador(unittest.TestCase):
    def test_codigo_qt(self):
        for codigo in (0, 7):
            with self.subTest(codigo=codigo), patch.object(run_dpi, "main", return_value=codigo):
                self.assertEqual(run_dpi.ejecutar(), codigo)

    def test_system_exit_se_propaga(self):
        with patch.object(run_dpi, "main", side_effect=SystemExit(3)):
            with self.assertRaises(SystemExit) as cm:
                run_dpi.ejecutar()
            self.assertEqual(cm.exception.code, 3)

    def test_error_genera_registro(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "dpi" / "crash_log.txt"
            with (patch.object(run_dpi, "main", side_effect=RuntimeError("fallo de prueba")),
                  patch.object(run_dpi, "_ruta_registro_error", return_value=ruta),
                  self.assertLogs(level="ERROR")):
                self.assertEqual(run_dpi.ejecutar(), 1)
            self.assertIn("RuntimeError: fallo de prueba", ruta.read_text(encoding="utf-8"))

    def test_error_sin_permiso_de_registro(self):
        with (patch.object(run_dpi, "main", side_effect=RuntimeError("fallo de prueba")),
              patch.object(run_dpi, "_ruta_registro_error", side_effect=PermissionError("sin permiso")),
              self.assertLogs(level="ERROR") as logs):
            self.assertEqual(run_dpi.ejecutar(), 1)
        self.assertIn("RuntimeError: fallo de prueba", "\n".join(logs.output))


class TestImportaciones(unittest.TestCase):
    def test_modulos_de_arranque(self):
        for nombre in ("dpi.ui.medicion.tareas", "modulo_vista_medicion",
                       "modulo_medicion", "modulo_codatacion", "main_anillos"):
            with self.subTest(modulo=nombre):
                importlib.import_module(nombre)


if __name__ == "__main__":
    unittest.main()
