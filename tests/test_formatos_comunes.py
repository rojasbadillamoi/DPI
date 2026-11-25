import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from dpi.formatos.deteccion import leer_series_auto
from dpi.formatos.tucson import escribir_tucson_merge, exportar_tucson_ewlw, leer_archivo_tucson
from dpi.formatos.tabular import escribir_tabla
class Formatos(unittest.TestCase):
    def test_auto_tucson_y_tabla(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'series.rwl'; df=pd.DataFrame({'Ancho_mm':[1.,2.]},index=[2000,2002])
            escribir_tucson_merge({'A':df,'B':df},str(p))
            self.assertEqual(set(leer_series_auto(str(p))),{'A','B'})
            p=Path(d)/'series.csv'; escribir_tabla(pd.DataFrame({'Anio':[2000,2002], 'A':[1.2,2.3], 'B':[4.2,5.3]}),str(p))
            self.assertEqual(len(leer_series_auto(str(p))),2)
    def test_ewlw_extension_y_ausencia(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'medicion.csv'
            exportar_tucson_ewlw('R',[2000,2001,2002],[(1,.4,.6),(1,None,None),(2,1,1)],str(p),sufijos=('_ew','_lw'),extension='.rwl')
            df,_=leer_archivo_tucson(str(Path(d)/'medicion_ew.rwl'))
            self.assertEqual(list(df.index),[2000,2002])
