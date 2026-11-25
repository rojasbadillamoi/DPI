"""Configuración Qt y preferencias de carpetas, sin cambiar claves históricas."""
import os
from PyQt6.QtCore import QSettings


def ajustes_ui(*, ventana_principal=False):
    return QSettings("MoiCedrus", "DendroAnillos" if ventana_principal else "DPI")


def ultima_carpeta(clave: str, nueva_ruta: str | None = None) -> str:
    cfg = ajustes_ui()
    if nueva_ruta is not None:
        carpeta = os.path.dirname(nueva_ruta)
        cfg.setValue(clave, carpeta)
        return carpeta
    return cfg.value(clave, "")


def carpeta_medicion(nueva_ruta=None):
    return ultima_carpeta("ultima_carpeta", nueva_ruta)


def carpeta_codatacion(nueva_ruta=None):
    return ultima_carpeta("ultima_carpeta_codatacion", nueva_ruta)
