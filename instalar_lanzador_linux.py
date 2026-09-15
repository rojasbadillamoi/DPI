#!/usr/bin/env python3
"""
DPI — Instalador del lanzador de escritorio (Linux)
====================================================

Deja DPI disponible en el menú de aplicaciones y hace que el ícono salga en
el dock, también en Wayland.

    python3 instalar_lanzador_linux.py

No hay que editar rutas: el script averigua dónde está la carpeta del
proyecto y qué intérprete se está usando, y arma todo con esos datos. Se
puede mover la carpeta después; en ese caso, volver a correrlo.

QUÉ HACE Y POR QUÉ
------------------
En X11 el gestor de ventanas tomaba el ícono directamente de la ventana. En
Wayland eso no es posible: el compositor busca un archivo `.desktop` cuyo
nombre coincida con el identificador que declara la aplicación —acá,
`moicedrus-dpi`, fijado con `setDesktopFileName`— y saca el ícono de ahí. Por
eso hacen falta tres piezas:

1. El ícono en PNG, en el árbol estándar de iconos del usuario.
2. El archivo `.desktop`, en la carpeta de aplicaciones del usuario.
3. El identificador declarado en el código, que ya viene puesto.

Todo se instala para el usuario, en ~/.local. No pide contraseña ni toca el
sistema.

    python3 instalar_lanzador_linux.py --quitar    para desinstalar
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ID = "moicedrus-dpi"
NOMBRE = "Dendro Pixel Interface"
COMENTARIO = "Medición y co-datación dendrocronológica"
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def _dir_iconos(tam: int) -> Path:
    return (Path.home() / ".local/share/icons/hicolor"
            / f"{tam}x{tam}/apps")


def _dir_apps() -> Path:
    return Path.home() / ".local/share/applications"


def _buscar_ico(base: Path) -> Path | None:
    for rel in ("dpi.ico", "iconos/dpi.ico", "dpi.png", "iconos/dpi.png"):
        p = base / rel
        if p.exists():
            return p
    return None


def _instalar_iconos(base: Path) -> list[Path]:
    """Extrae el .ico a PNG en cada tamaño del árbol hicolor.

    Se instalan varios tamaños porque el dock, el menú y el conmutador de
    ventanas piden resoluciones distintas; si solo existe una, el sistema la
    reescala y se ve borrosa.
    """
    origen = _buscar_ico(base)
    if origen is None:
        print("  ! No encontré dpi.ico ni dpi.png en la carpeta del proyecto.")
        return []
    escritos = []
    try:
        from PIL import Image
        img = Image.open(origen)
        disponibles = sorted(getattr(img, "info", {}).get("sizes", []) or
                             [img.size], key=lambda s: s[0])
    except Exception:
        img = None
        disponibles = []

    for tam in TAMANOS:
        destino = _dir_iconos(tam)
        destino.mkdir(parents=True, exist_ok=True)
        salida = destino / f"{APP_ID}.png"
        try:
            if img is not None:
                # De cada tamaño se parte del más grande disponible: reducir
                # conserva detalle, ampliar lo inventa.
                mayor = max(disponibles, key=lambda s: s[0]) if disponibles \
                    else img.size
                try:
                    img.size = mayor
                except Exception:
                    pass
                copia = img.convert("RGBA").resize((tam, tam),
                                                   Image.LANCZOS)
                copia.save(salida)
            else:
                shutil.copy(origen, salida)
            escritos.append(salida)
        except Exception as e:
            print(f"  ! No pude escribir {salida}: {e}")
    return escritos


def _escribir_desktop(base: Path) -> Path:
    lanzador = base / "run_dpi.py"
    if not lanzador.exists():
        lanzador = base / "main_anillos.py"
    # sys.executable es el intérprete con el que se corrió este script, o sea
    # el mismo entorno donde están PyQt6 y las demás dependencias.
    exec_line = f'{sys.executable} "{lanzador}"'
    contenido = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={NOMBRE}
GenericName=Dendrocronología
Comment={COMENTARIO}
Exec={exec_line}
Path={base}
Icon={APP_ID}
Terminal=false
Categories=Science;Education;Graphics;
Keywords=dendro;anillos;tree-ring;cofecha;dendrochronology;
StartupNotify=true
StartupWMClass={APP_ID}
"""
    d = _dir_apps()
    d.mkdir(parents=True, exist_ok=True)
    ruta = d / f"{APP_ID}.desktop"
    ruta.write_text(contenido, encoding="utf-8")
    os.chmod(ruta, 0o755)
    return ruta


def _refrescar():
    for cmd in (["update-desktop-database", str(_dir_apps())],
                ["gtk-update-icon-cache", "-f", "-t",
                 str(Path.home() / ".local/share/icons/hicolor")]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=False,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            except Exception:
                pass


def instalar():
    base = Path(__file__).resolve().parent
    print(f"Carpeta del proyecto: {base}")
    print(f"Intérprete:           {sys.executable}\n")

    iconos = _instalar_iconos(base)
    print(f"  Iconos instalados: {len(iconos)} tamaños")
    ruta = _escribir_desktop(base)
    print(f"  Lanzador:          {ruta}")
    _refrescar()
    print("\nListo. Puede que haya que cerrar y volver a iniciar sesión para")
    print("que el dock tome el ícono por primera vez.")
    print("\nSi mueves la carpeta del proyecto, vuelve a correr este script.")


def quitar():
    ruta = _dir_apps() / f"{APP_ID}.desktop"
    if ruta.exists():
        ruta.unlink()
        print(f"  Eliminado {ruta}")
    n = 0
    for tam in TAMANOS:
        p = _dir_iconos(tam) / f"{APP_ID}.png"
        if p.exists():
            p.unlink()
            n += 1
    print(f"  Eliminados {n} iconos")
    _refrescar()
    print("Desinstalado.")


if __name__ == "__main__":
    if "--quitar" in sys.argv:
        quitar()
    else:
        instalar()
