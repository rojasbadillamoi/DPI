import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from dpi.formatos.pos import leer_pos, escribir_pos
from dpi.ciencia.cofecha_nucleo import Matriz, z_leave_one_out

class TestValidacionPosMatrizYVarianza(unittest.TestCase):
    def test_dpi_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.pos'
            for valor in ('0', '-100', 'nan', 'inf'):
                p.write_text('#DPI ' + valor + '\n0,0\n1,1\n')
                with self.assertRaises(ValueError):
                    leer_pos(p)
            with self.assertRaises(ValueError):
                escribir_pos(p, [(0,0)], [False], 0, None, 'a', 'a.png')

    def test_indices(self):
        for idx in ([1.5, 2.5], [1, 1], [1, 100_000_000]):
            with self.assertRaises(ValueError):
                Matriz.desde_series({'a': pd.Series([1., 2.], index=idx)})

    def test_varianza(self):
        mat = 1e12 + np.arange(5., dtype=float)[None, :]
        z = z_leave_one_out(mat)
        self.assertAlmostEqual(z[0,0], -2.5 / np.std([1.,2.,3.,4.]))
