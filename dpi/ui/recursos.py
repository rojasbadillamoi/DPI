"""Recursos de Qt y rutas de distribución."""
import os as _os
import sys as _sys


# Nombres y ubicaciones posibles del ícono. Se prueban en orden porque el
# archivo vive en la raíz al correr desde el código fuente, y dentro de
# "iconos/" en el empaquetado de Windows.
_CANDIDATOS_ICONO = (
    _os.path.join("iconos", "dpi.ico"),
    "dpi.ico",
    "dpi_icon.ico",
    _os.path.join("iconos", "dpi_icon.ico"),
    "dpi.png",
    _os.path.join("iconos", "dpi.png"),
)


def _base_recursos() -> str:
    """Carpeta donde buscar recursos: _MEIPASS si está empaquetado, si no
    la carpeta de este archivo."""
    base = getattr(_sys, "_MEIPASS", None)
    if base:
        return base
    return _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))


def ruta_icono() -> str:
    """Ruta absoluta al ícono de la aplicación, o cadena vacía si no existe."""
    base = _base_recursos()
    for nombre in _CANDIDATOS_ICONO:
        ruta = _os.path.join(base, nombre)
        if _os.path.exists(ruta):
            return ruta
    return ""


def icono_app():
    """QIcon de la aplicación (vacío si no se encontró el archivo)."""
    from PyQt6.QtGui import QIcon
    ruta = ruta_icono()
    return QIcon(ruta) if ruta else QIcon()


def pixmap_icono(lado: int = 200):
    """QPixmap del ícono al tamaño pedido, tomando la MAYOR resolución
    interna disponible. QPixmap(archivo.ico) carga solo la variante de
    16x16, que al escalarla sale pixelada."""
    from PyQt6.QtCore import Qt, QSize
    from PyQt6.QtGui import QPixmap
    ruta = ruta_icono()
    if not ruta:
        return QPixmap()
    ico = icono_app()
    tamanos = ico.availableSizes()
    if tamanos:
        mayor = max(tamanos, key=lambda s: s.width() * s.height())
        pix = ico.pixmap(mayor)
    else:
        pix = QPixmap(ruta)
    if pix.isNull():
        return pix
    return pix.scaled(QSize(lado, lado),
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)
