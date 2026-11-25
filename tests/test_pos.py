import tempfile
import unittest
from pathlib import Path

from dpi.formatos.pos import leer_pos, escribir_pos
from dpi.medicion.constantes import DPI_DEFECTO, MM_POR_PULGADA


class TestPos(unittest.TestCase):
    def test_ida_vuelta(self):
        dpi = 254.0
        coords = [(0, 0), (10, 20), (30, 40), (-50, 60)]
        saltos = [False, False, True, False]
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'radio.pos'
            escribir_pos(ruta, coords, saltos, dpi, 2000, 'RAD1',
                         '/datos/imagen.png')
            texto = ruta.read_text(encoding='utf-8')
            self.assertIn('#Imagefile imagen.png', texto)
            self.assertIn('#C Code RAD1', texto)
            self.assertIn('1.0000,2.0000 3.0000,4.0000', texto)
            d, a, c, s = leer_pos(ruta)
            self.assertEqual((d, a, s), (dpi, 2000, saltos))
            for real, esperado in zip(c, coords, strict=True):
                for x, y in zip(real, esperado, strict=True):
                    self.assertAlmostEqual(x, y)

    def test_lectura_sin_metadatos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'antiguo.pos'
            ruta.write_text('# comentario\nSCALE 1\n1,2\n3,4 5,6\n',
                            encoding='utf-8')
            dpi, anio, coords, saltos = leer_pos(ruta)
            self.assertEqual(dpi, DPI_DEFECTO)
            self.assertIsNone(anio)
            self.assertEqual(saltos, [False, False, True])
            self.assertAlmostEqual(coords[0][0], DPI_DEFECTO / MM_POR_PULGADA)

    def test_marcas_finas_y_fecha_ausente(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'radio.pos'
            escribir_pos(ruta, [(0, 0), (10, 0), (20, 0)],
                         [False, 'ew_lw', 'espacio'], 254, None,
                         'RAD', 'imagen.png')
            _, anio, _, saltos = leer_pos(ruta)
            self.assertIsNone(anio)
            self.assertEqual(saltos, [False, True, True])
