"""Comprueba dependencias locales directas y transitivas sin cargar Qt."""
import ast
from importlib.util import resolve_name
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def importaciones(ruta):
    paquete = ".".join(ruta.relative_to(RAIZ).parent.parts)
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            yield from (a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            if nodo.level:
                modulo = resolve_name("." * nodo.level + modulo, paquete)
            if modulo:
                yield modulo
                for alias in nodo.names:
                    yield modulo + "." + alias.name


class DependenciasCientificas(unittest.TestCase):
    def test_importaciones_sin_interfaz(self):
        pendientes = [p for paquete in ("ciencia", "medicion", "series", "formatos", "infraestructura")
                      for p in (RAIZ / "dpi" / paquete).rglob("*.py")]
        visitados = set()
        while pendientes:
            ruta = pendientes.pop()
            if ruta in visitados:
                continue
            visitados.add(ruta)
            for nombre in importaciones(ruta):
                self.assertFalse(nombre.startswith(("PyQt", "PySide", "pyqtgraph", "tkinter", "dpi.ui"))
                                 or nombre.endswith("_ui"), (ruta, nombre))
                local = RAIZ / (nombre.replace(".", "/") + ".py")
                if local.is_file():
                    pendientes.append(local)
                inicializador = local.with_suffix("") / "__init__.py"
                if inicializador.is_file():
                    pendientes.append(inicializador)
