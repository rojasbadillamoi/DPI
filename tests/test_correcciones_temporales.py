import unittest
import pandas as pd
from dpi.series.modelo import ModeloSeries


class CorreccionesTemporales(unittest.TestCase):
    def setUp(self):
        self.m = ModeloSeries()
        self.original = pd.DataFrame({'Ancho_mm': [1., 2.]}, index=[2000, 2001])
        self.editada = self.original * 2
        self.corregida = self.original * 3
        self.m.registrar('A', self.original)
        self.m.actualizar('A', self.editada)

    def test_descartar_recupera_edicion_previa(self):
        self.m.probar_correccion('A', self.corregida)
        self.assertEqual(self.m.nombre_en_prueba, 'A')
        pd.testing.assert_frame_equal(self.m.datos['A'], self.corregida)
        self.assertTrue(self.m.descartar_correccion())
        pd.testing.assert_frame_equal(self.m.datos['A'], self.editada)
        self.assertIsNone(self.m.nombre_en_prueba)
        self.assertFalse(self.m.descartar_correccion())

    def test_confirmar_conserva_original(self):
        self.m.probar_correccion('A', self.corregida)
        self.assertTrue(self.m.confirmar_correccion())
        pd.testing.assert_frame_equal(self.m.datos['A'], self.corregida)
        pd.testing.assert_frame_equal(self.m.originales['A'], self.original)
        self.assertFalse(self.m.confirmar_correccion())
        self.m.restablecer('A')
        pd.testing.assert_frame_equal(self.m.datos['A'], self.original)

    def test_prueba_invalida_no_muta(self):
        with self.assertRaises(ValueError):
            self.m.probar_correccion('A', pd.DataFrame({'otra': [1]}))
        self.assertIsNone(self.m.nombre_en_prueba)
        pd.testing.assert_frame_equal(self.m.datos['A'], self.editada)

    def test_no_sobrescribir_prueba(self):
        self.m.probar_correccion('A', self.corregida)
        for accion in (lambda: self.m.probar_correccion('A', self.editada),
                       lambda: self.m.actualizar('A', self.editada),
                       lambda: self.m.registrar('A', self.editada),
                       lambda: self.m.eliminar('A'),
                       lambda: self.m.restablecer('A'),
                       lambda: self.m.desplazar('A', 1)):
            with self.assertRaises(ValueError):
                accion()
        self.m.descartar_correccion()
        pd.testing.assert_frame_equal(self.m.datos['A'], self.editada)

    def test_copias_independientes(self):
        self.m.probar_correccion('A', self.corregida)
        self.corregida.iloc[0, 0] = 99
        self.assertEqual(self.m.datos['A'].iloc[0, 0], 3.)
        self.m.descartar_correccion()
        pd.testing.assert_frame_equal(self.m.originales['A'], self.original)
