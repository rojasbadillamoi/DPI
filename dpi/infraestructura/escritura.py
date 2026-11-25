"""Escritura atómica de un archivo, conservando su extensión."""
from contextlib import contextmanager
import os
import tempfile


@contextmanager
def ruta_atomica(ruta):
    destino = os.path.abspath(os.fspath(ruta))
    carpeta, nombre = os.path.split(destino)
    fd, temporal = tempfile.mkstemp(prefix=".dpi-", suffix=os.path.splitext(nombre)[1], dir=carpeta)
    os.close(fd)
    try:
        yield temporal
        os.replace(temporal, destino)
    finally:
        try:
            os.unlink(temporal)
        except FileNotFoundError:
            pass
