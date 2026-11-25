import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from dpi.infraestructura.json_seguro import a_json, guardar_json

class TestJsonRobusto(unittest.TestCase):
    def test_escalar_numpy(self):
        self.assertEqual(a_json(np.array(3)), 3)

    def test_archivo_temporal(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.json'
            guardar_json(p, {'x': np.array(3)})
            self.assertEqual(json.loads(p.read_text()), {'x': 3})
            self.assertEqual(list(Path(d).iterdir()), [p])
