import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from dpi.infraestructura.escritura import ruta_atomica
from dpi.formatos.tabular import escribir_tabla
from dpi.infraestructura.json_seguro import a_json
from dpi.series.modelo import ModeloSeries

class EscrituraAtomica(unittest.TestCase):
    def test_error_conserva_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "serie.csv"
            ruta.write_text("original")
            with self.assertRaises(RuntimeError):
                with ruta_atomica(ruta) as temporal:
                    Path(temporal).write_text("incompleto")
                    raise RuntimeError("fallo")
            self.assertEqual(ruta.read_text(), "original")
            self.assertEqual(list(Path(carpeta).iterdir()), [ruta])

    def test_exportacion_fallida(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "serie.csv"
            ruta.write_text("original")
            def fallo(df, destino, **kwargs):
                Path(destino).write_text("incompleto")
                raise OSError("fallo")
            with patch.object(pd.DataFrame, "to_csv", fallo), self.assertRaises(OSError):
                escribir_tabla(pd.DataFrame({"a": [1]}), str(ruta))
            self.assertEqual(ruta.read_text(), "original")

    def test_tipo_desconocido(self):
        with self.assertRaises(TypeError):
            a_json(object())

    def test_columnas_duplicadas(self):
        with self.assertRaises(ValueError):
            ModeloSeries().registrar("A", pd.DataFrame([[1, 2]], columns=["Ancho_mm", "Ancho_mm"], index=[2000]))
