import unittest
from io import StringIO
import pandas as pd
from dpi.series.modelo import ModeloSeries
from dpi.infraestructura.json_seguro import cargar_json, a_json
class TestSeriesDuplicadasYJson(unittest.TestCase):
    def test_duplicado(self):
        m=ModeloSeries();df=pd.DataFrame({'Ancho_mm':[1]},index=[2000]);m.registrar('A',df)
        with self.assertRaises(ValueError): m.registrar('A',df*2)
        self.assertEqual(m.originales['A'].iloc[0,0],1)
        m.reemplazar('A',df*2);self.assertEqual(m.originales['A'].iloc[0,0],2)
    def test_json(self):
        with self.assertRaises(ValueError): cargar_json(StringIO('{"a":{"x":1,"x":2}}'))
        self.assertIsNone(a_json(pd.NA));self.assertIsNone(a_json(pd.NaT))
