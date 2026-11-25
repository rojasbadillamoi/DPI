import tempfile
import unittest
from pathlib import Path
import pandas as pd
from dpi.formatos.exportacion import exportar_serie_2col


class ExportarDosColumnas(unittest.TestCase):
    def test_texto_y_csv(self):
        s = pd.Series([1.25, float('nan'), 2.5], index=[2000, 2001, 2002])
        with tempfile.TemporaryDirectory() as tmp:
            for ext, sep in [('txt', '\t'), ('csv', ';')]:
                ruta = Path(tmp) / ('serie.' + ext)
                self.assertEqual(exportar_serie_2col(s, ruta, 'R'), 2)
                self.assertEqual(ruta.read_text(encoding='utf-8').splitlines(),
                                 [f'Anio{sep}Valor', f'2000{sep}1,250000', f'2002{sep}2,500000'])
