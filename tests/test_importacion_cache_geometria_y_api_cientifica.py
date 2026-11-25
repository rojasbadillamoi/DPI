import unittest



class ImportacionAtomica(unittest.TestCase):
    def test_lote_invalido(self):
        import pandas as pd
        from dpi.series.modelo import ModeloSeries
        m = ModeloSeries()
        with self.assertRaises(ValueError):
            m.registrar_lote({'A': pd.DataFrame({'Ancho_mm':[1]}, index=[2000]), 'B': pd.DataFrame()})
        self.assertEqual(len(m.datos), 0)
        self.assertEqual(m.revision, 0)


class CacheGeometria(unittest.TestCase):
    def test_cambio_escala_y_marcas(self):
        from dpi.medicion.calculo import anchos_anillos
        self.assertEqual(anchos_anillos([(0,0),(4,0)], [False,False], 2), [2.])
        self.assertEqual(anchos_anillos([(0,0),(4,0)], [False,False], 4), [1.])
        self.assertEqual(anchos_anillos([(0,0),(4,0)], [False,True], 2), [])


class TestGeometriaAnchosYApiCientifica(unittest.TestCase):
    def test_geometria(self):
        from dpi.medicion.calculo import posicion_insercion, ordenar_extremos_espacio, escala_desde_dpi
        coords = [(0,0),(2,0),(4,0)]
        self.assertEqual(posicion_insercion(coords, 1, (3.9,0)), 2)
        self.assertEqual(posicion_insercion(coords, 1, (.1,0)), 1)
        self.assertEqual(ordenar_extremos_espacio(coords, (1.8,0), 0, (.2,0), 0), ((.2,0), 0, (1.8,0), 0))
        self.assertAlmostEqual(escala_desde_dpi(254), 10.)
        with self.assertRaises(ValueError):
            escala_desde_dpi(0)

    def test_anchos_fisicos(self):
        import pandas as pd
        from dpi.series.modelo import validar_anchos_fisicos
        for valores in ([-1.,2.], [True,False]):
            with self.assertRaises(ValueError):
                validar_anchos_fisicos(pd.Series(valores))
        validar_anchos_fisicos(pd.Series([0., 1., float('nan')]))

    def test_api_ciencia(self):
        from dpi.ciencia import datacion, alineamiento, correcciones, diagnostico
        self.assertIs(datacion.alineamiento_optimo_anillos, alineamiento.alineamiento_optimo_anillos)
        self.assertIs(datacion.buscar_correcciones, correcciones.buscar_correcciones)
        self.assertIs(datacion.diagnosticar_datacion, diagnostico.diagnosticar_datacion)

    def test_candidatos(self):
        import pandas as pd
        from dpi.series.cronologias import candidatos_cronologias
        candidatos = candidatos_cronologias({'': pd.DataFrame({'Indice':[1.,2.], 'EPS':[.9,.9]}, index=[2000,2001])}, 'A')
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0][1], 'A')
        self.assertEqual(list(candidatos[0][2].Ancho_mm), [1.,2.])
