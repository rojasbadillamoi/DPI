import unittest, ast
from pathlib import Path
class ContratosConstruccion(unittest.TestCase):
    def test_fabricas_no_mutan_propietario(self):
        for nombre in ('modulo_medicion_ui.py','modulo_codatacion_ui.py'):
            t=ast.parse((Path(__file__).resolve().parents[1]/nombre).read_text(encoding='utf-8'))
            for n in t.body:
                if isinstance(n,ast.FunctionDef) and n.name.startswith('construir_'):
                    self.assertEqual(n.args.args[0].arg,'parent')
                    self.assertFalse(any(isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=='parent' for x in ast.walk(n)))
