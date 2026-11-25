import tempfile
import unittest
from pathlib import Path
import pandas as pd
from dpi.formatos.tucson import escribir_tucson, leer_archivo_tucson, leer_tucson_multi, escribir_tucson_merge, exportar_tucson_ewlw

class TucsonTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d)/'a.rwl')
            for start in range(2000, 2010):
                for n in range(1, 25):
                    s = pd.Series([.998, .999, 0., 1.2]*7, index=range(start,start+28)).iloc[:n]
                    s = s.drop(s.index[1:2])
                    escribir_tucson(s,p,'ABCDEFGH')
                    df, sid = leer_archivo_tucson(p)
                    self.assertEqual(sid,'ABCDEFGH')
                    self.assertEqual(df.index.tolist(),s.index.tolist())
                    self.assertEqual(df.Ancho_mm.tolist(),s.tolist())
                    self.assertTrue(all(len(l)<=72 for l in Path(p).read_text().splitlines()))
    def test_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d)/'a.rwl')
            df = pd.DataFrame({'Ancho_mm':[.998,.999]},index=[2000,2003])
            escribir_tucson_merge({'A':df,'B':df},p)
            self.assertEqual( leer_tucson_multi(p)['B'].index.tolist(),[2000,2003])
            with self.assertRaises(ValueError):
                escribir_tucson_merge({'ABCDEFGH1':df,'ABCDEFGH2':df},p)
            with self.assertRaises(ValueError):
                leer_archivo_tucson(p)
    def test_ewlw(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d)/'a.rwl')
            exportar_tucson_ewlw('ABCDEFGH',[2000,2001,2003],[(2,.999,1.001),(2,None,None),(2,.998,1.002)],p)
            df,sid = leer_archivo_tucson(str(Path(d)/'a_EW.rwl'))
            self.assertEqual(sid,'ABCDE_EW')
            self.assertEqual(df.index.tolist(),[2000,2003])
            self.assertEqual(df.Ancho_mm.tolist(),[.999,.998])
    def test_precision_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'a.rwl'
            p.write_text('A       2000   100  9999   200\nA       2000   300\nA       2003   999\n')
            df,_ = leer_archivo_tucson(p)
            self.assertEqual(df.Ancho_mm.tolist(),[2.,2.])
            self.assertEqual(df.index.tolist(),[2000,2002])
