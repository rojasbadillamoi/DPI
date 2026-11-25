"""Pruebas de integración gráfica; requieren el entorno Qt real."""
import importlib.util
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PyQt6') and importlib.util.find_spec('pyqtgraph'),
                     'Requiere PyQt6 y pyqtgraph')
class TestIntegracionWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_grafico_independiente(self):
        import pyqtgraph as pg
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QComboBox, QSpinBox, QLabel
        from modulo_grafico_medicion_ui import GraficoMedicion
        plot = pg.PlotWidget()
        combo, spin, total, ventanas = QComboBox(), QSpinBox(), QLabel(), QLabel()
        spin.setValue(10)
        g = GraficoMedicion(plot, combo, spin, total, ventanas, lambda: 'difflog', lambda anio: False)
        entradas = [('A', [2000,2001], [1.,2.], '#00ff00', Qt.PenStyle.SolidLine)]
        for _ in range(2):
            g.actualizar(entradas, None, '')
            self.assertIn('A', g._plot_items)
            self.assertIsNotNone(g._graf_vline.scene())
        plot.close()

    def test_panel_codatacion(self):
        from PyQt6.QtWidgets import QWidget
        from modulo_codatacion import PanelCodatacion
        padre = QWidget()
        panel = PanelCodatacion(padre)
        self.assertIsNotNone(panel.lista_series)
        self.assertEqual(len(panel.modelo_series.datos), 0)
        panel.close()
        padre.close()

    def test_pestana_medicion(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from PyQt6.QtWidgets import QWidget
        from modulo_medicion import PestanaImagen
        padre = QWidget()
        with TemporaryDirectory() as directorio:
            ruta = str(Path(directorio) / 'prueba.png')
            with patch.object(PestanaImagen, '_cargar_imagen'):
                pestana = PestanaImagen(ruta, padre)
            self.assertIs(pestana.vista.modelo_medicion, pestana.modelo_sesion.activo)
            pestana.vista.modelo_medicion.cargar([(0,0),(2,0)], [False,False])
            pestana.vista.pixeles_por_mm = 2.
            pestana.vista.recalcular_todas_las_distancias()
            self.assertEqual(len(pestana.datos_medidos), 1)
            self.assertAlmostEqual(pestana.datos_medidos[0]['ancho_mm'], 1.)
            pestana._timer_autoguardado.stop()
            pestana.close()
        padre.close()

    def test_vista_sin_pestana(self):
        from PyQt6.QtWidgets import QGraphicsScene
        from modulo_vista_medicion import VistaInteractiva
        from dpi.medicion.modelo import ModeloMedicion
        modelo = ModeloMedicion()
        escena = QGraphicsScene()
        vista = VistaInteractiva(escena, modelo=modelo, datacion=lambda: (2000, 2001, True))
        modelo.cargar([(0,0),(2,0),(4,0)], [False]*3)
        vista.pixeles_por_mm = 2.
        vista.redibujar_todo()
        self.assertEqual(vista.mapa_anio_coordenada(), {2000:(2.,0.), 2001:(4.,0.)})
        self.assertIs(vista.modelo_medicion, modelo)
        vista.close()

    def test_entrada_externa_no_sobrescribe(self):
        import pandas as pd
        from PyQt6.QtWidgets import QWidget
        from modulo_codatacion import PanelCodatacion
        padre = QWidget()
        panel = PanelCodatacion(padre)
        original = pd.DataFrame({'Ancho_mm':[1.,2.]}, index=[2000,2001])
        self.assertTrue(panel.agregar_serie_externa('A', original))
        self.assertFalse(panel.agregar_serie_externa('A', original * 2))
        pd.testing.assert_frame_equal(panel.modelo_series.originales['A'], original)
        panel.close()
        padre.close()
