"""Regresiones científicas y de integración acumuladas (21–33)."""
import importlib.util
import math
import os
import unittest
import numpy as np
from dpi.medicion.calculo import calcular_anillos, puntos_desde_geometria
from dpi.medicion.ewlw import _calcular_anchos_ewlw_por_anillo
from dpi.medicion.intensidad import segmentos_banda_intensidad, extraer_intensidad_por_anillo
from dpi.medicion.pith import distancia_faltante_dap


class GeometriaComun(unittest.TestCase):
    def test_invariantes(self):
        coords = [(i*2, 5) for i in range(10)]
        marcas = [False, 'ew_lw', False, True, 'quiebre_ini', 'espacio', 'ew_lw', False, 'ew_lw', False]
        puntos = puntos_desde_geometria(coords, marcas)
        anillos = calcular_anillos(puntos, 2)
        partes = _calcular_anchos_ewlw_por_anillo(coords, marcas, 2)
        self.assertEqual([a.ancho_mm for a in anillos], [t[0] for t in partes])
        for total, ew, lw in partes:
            self.assertAlmostEqual(total, ew+lw)
        self.assertAlmostEqual(distancia_faltante_dap(coords, marcas, 100), 100-2*sum(a.ancho_mm for a in anillos))
        self.assertEqual(len(segmentos_banda_intensidad(coords, marcas)), len(anillos))
        r=extraer_intensidad_por_anillo(None,np.full((24,30,3),42,dtype=np.uint8),coords,marcas,2,0,['B'])
        self.assertEqual([d['indice_anillo'] for d in r],list(range(len(anillos))))
        self.assertTrue(all(d['B_mean']==42 for d in r))


@unittest.skipUnless(importlib.util.find_spec('PyQt6') is not None, 'Requiere PyQt6')
class CicloTareasQt(unittest.TestCase):
    def test_finalizacion(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication, QWidget
        from PyQt6.QtCore import QEventLoop, QTimer
        from dpi.ui.medicion.tareas import GestorTareasMedicion
        app = QApplication.instance() or QApplication([])
        padre = QWidget()
        gestor = GestorTareasMedicion(padre)
        salidas = []
        loop = QEventLoop()
        def recibir(tipo, valor=None):
            salidas.append((tipo,valor))
            QTimer.singleShot(0,loop.quit)
        self.assertTrue(gestor.iniciar('Prueba',lambda p,c: 7,
            lambda x: recibir('ok',x),lambda e: recibir('error',e),lambda: recibir('cancelado')))
        self.assertFalse(gestor.iniciar('Duplicada',lambda p,c: None,lambda x: None,lambda e: None,lambda: None))
        QTimer.singleShot(5000,loop.quit)
        loop.exec()
        self.assertEqual(salidas,[('ok',7)])
        self.assertFalse(gestor.en_curso)
        self.assertTrue(gestor.iniciar('Cancelar',lambda p,c: 99,
            lambda x: recibir('ok',x),lambda e: recibir('error',e),lambda: recibir('cancelado')))
        gestor.cancelar()
        QTimer.singleShot(5000,loop.quit)
        loop.exec()
        self.assertEqual(salidas[-1],('cancelado',None))
        self.assertFalse(gestor.en_curso)
        padre.close()

    def test_callback_puede_encadenar_tareas(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt6.QtWidgets import QApplication, QWidget
        from PyQt6.QtCore import QEventLoop, QTimer
        from dpi.ui.medicion.tareas import GestorTareasMedicion
        app = QApplication.instance() or QApplication([])
        padre = QWidget()
        gestor = GestorTareasMedicion(padre)
        loop = QEventLoop()
        salidas = []
        def error(e):
            salidas.append(e)
            loop.quit()
        def segunda(x):
            salidas.append(x)
            loop.quit()
        def primera(x):
            salidas.append(x)
            salidas.append(gestor.iniciar('Segunda', lambda p,c: 2, segunda, error, loop.quit))
        gestor.iniciar('Primera', lambda p,c: 1, primera, error, loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        self.assertEqual(salidas, [1, True, 2])
        self.assertFalse(gestor.en_curso)
        padre.close()
