"""La aplicación usa los paquetes canónicos, no los adaptadores históricos."""
import ast
from pathlib import Path
import unittest

RAIZ = Path(__file__).resolve().parents[1]

class ImportacionesPaquetes(unittest.TestCase):
    def test_importaciones_canonicas(self):
        adaptadores = {'modulo_modelo_medicion', 'modulo_modelo_series', 'modulo_configuracion_ui', 'modulo_autodeteccion', 'constantes', 'modulo_grafico_medicion', 'modulo_worker_medicion', 'modulo_intensidad_nucleo', 'modulo_pith_nucleo', 'modulo_ewlw', 'modulo_datos_medicion', 'modulo_imagen', 'json_seguro', 'modulo_formatos', 'modulo_marcas_medicion', 'modulo_render_medicion', 'modulo_sesion_medicion', 'modulo_calculo_medicion'}
        for p in [*RAIZ.glob("*.py"), *(RAIZ / "dpi").rglob("*.py"), *(RAIZ / "tests").rglob("*.py")]:
            for nodo in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                nombres = ([a.name for a in nodo.names] if isinstance(nodo, ast.Import)
                           else [nodo.module] if isinstance(nodo, ast.ImportFrom) else [])
                for nombre in nombres:
                    self.assertNotIn(nombre, adaptadores, (p, nombre))
