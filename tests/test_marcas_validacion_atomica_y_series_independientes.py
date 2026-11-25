import unittest
import pandas as pd
from dpi.medicion.modelo import ModeloMedicion, PuntoMedicion, TipoMarca
from dpi.medicion.marcas import _es_amarillo, _es_salto_real, _es_ewlw
from dpi.series.modelo import ModeloSeries


class TestModelosDatos(unittest.TestCase):
    def test_marcas_tipadas(self):
        m = ModeloMedicion()
        for t in TipoMarca:
            m.agregar((1, 2), t)
            self.assertEqual(m.marcas[-1], t.value)
            self.assertEqual(_es_amarillo(t), _es_amarillo(t.value))
        self.assertTrue(_es_salto_real(TipoMarca.SALTO))
        self.assertTrue(_es_ewlw(TipoMarca.EW_LW))

    def test_validacion_atomica(self):
        m = ModeloMedicion()
        m.agregar((1, 2))
        antes = m.captura()
        for op in (lambda: m.mover(0, (float('nan'), 2)),
                   lambda: m.marcar(0, 1),
                   lambda: m.restaurar([None]),
                   lambda: m.cargar([(1, 2), (3, float('inf'))], [False, True])):
            with self.assertRaises(ValueError):
                op()
            self.assertEqual(m.captura(), antes)
        p = PuntoMedicion([1, 2], False)
        self.assertEqual(p.coordenada, (1., 2.))

    def test_series_independientes(self):
        m = ModeloSeries()
        df = pd.DataFrame({'Ancho_mm': [1., 2.]}, index=[2000, 2002])
        m.registrar('A', df)
        copia = m.datos['A']
        copia.iloc[0, 0] = 9
        self.assertEqual(m.datos['A'].iloc[0, 0], 1)
        m.actualizar('A', copia)
        self.assertEqual(m.datos['A'].iloc[0, 0], 9)
        self.assertEqual(m.originales['A'].iloc[0, 0], 1)
        self.assertEqual(df.iloc[0, 0], 1)
        m.restablecer('A')
        pd.testing.assert_frame_equal(m.datos['A'], df)
        with self.assertRaises(ValueError):
            m.registrar('A', pd.DataFrame({'otro': [1]}))
        pd.testing.assert_frame_equal(m.datos['A'], df)
        m.eliminar('A')
        self.assertFalse(m.datos or m.originales)
