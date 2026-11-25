#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_dpi.py — Lanzador de DPI con splash screen.

Punto de entrada principal. Muestra el ícono como splash mientras
se cargan los módulos pesados.

Uso:  python run_dpi.py
"""

import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def crear_splash(app):
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
    from PyQt6.QtCore import Qt

    W, H = 320, 370
    pixmap = QPixmap(W, H)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(0, 0, W, H, QColor("#2b2b2b"))

    # Ícono centrado (200px), tomando la mayor resolución interna del .ico
    from dpi.version import APP_NOMBRE, APP_SUITE, VERSION
    from dpi.ui.recursos import pixmap_icono
    s = pixmap_icono(200)
    if not s.isNull():
        p.drawPixmap((W - s.width()) // 2, 25, s)

    # Subtítulo
    p.setPen(QColor(255, 200, 150, 200))
    p.setFont(QFont("Arial", 12))
    p.drawText(0, 245, W, 20, Qt.AlignmentFlag.AlignCenter,
               f"{APP_NOMBRE} {VERSION}")

    # Suite
    p.setPen(QColor(150, 150, 150, 140))
    p.setFont(QFont("Arial", 9))
    p.drawText(0, 268, W, 18, Qt.AlignmentFlag.AlignCenter, APP_SUITE)

    # Barra inferior
    p.fillRect(0, H - 28, W, 28, QColor(0, 0, 0, 100))
    p.setPen(QPen(QColor("#FF8C00")))
    p.drawLine(0, H - 28, W, H - 28)

    p.end()
    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()
    return splash


def splash_msg(splash, msg):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication
    splash.showMessage(f"  {msg}",
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                       QColor(200, 200, 200))
    QApplication.processEvents()


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon

    from dpi.ui.recursos import icono_app, ruta_icono
    app = QApplication(sys.argv)
    if ruta_icono():
        app.setWindowIcon(icono_app())
    # Identificador de escritorio. En Wayland el compositor no puede leer el
    # ícono desde la ventana como hacía X11: busca un archivo .desktop cuyo
    # nombre coincida con este identificador y saca el ícono de ahí. Sin esta
    # línea el ícono sale en la ventana pero no en el dock.
    app.setDesktopFileName("moicedrus-dpi")

    splash = crear_splash(app)

    splash_msg(splash, "Cargando numpy y opencv...")
    import numpy; import cv2  # noqa

    splash_msg(splash, "Cargando motor de gráficos...")
    import pyqtgraph  # noqa

    splash_msg(splash, "Cargando interfaz de medición...")
    from modulo_medicion import PestanaImagen  # noqa
    from modulo_exportacion_medicion_ui import ExportadorDendro  # noqa

    splash_msg(splash, "Cargando co-datación...")
    from modulo_codatacion import PanelCodatacion  # noqa

    splash_msg(splash, "Preparando ventana principal...")
    from main_anillos import VentanaAnillos, configurar_aplicacion
    configurar_aplicacion(app)
    ventana = VentanaAnillos()
    ventana.show()
    splash.finish(ventana)
    return app.exec()


def _ruta_registro_error():
    """Registro por usuario, independiente del directorio de instalación."""
    return Path.home() / ".dpi" / "crash_log.txt"


def ejecutar():
    """Conserva el código de salida de Qt y señala errores de arranque."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        return main()
    except Exception:
        import traceback
        logging.exception("Error fatal de DPI")
        try:
            log = _ruta_registro_error()
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            logging.exception("No se pudo escribir el registro de errores")
        return 1


if __name__ == "__main__":
    sys.exit(ejecutar())
