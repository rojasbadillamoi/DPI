#!/usr/bin/env python3
"""Construye el .deb de DPI para Debian/Ubuntu.

Paquete NATIVO: instala el código y declara las dependencias como paquetes del
sistema, en vez de empacar un intérprete entero. Pesa ~1 MB en vez de ~400 MB,
y usa el Qt del sistema, que es lo que hace que el tema claro/oscuro del
escritorio se respete.

Uso:   python3 construir_deb.py [carpeta_de_salida]

Empaqueta el código de SU PROPIA carpeta, así que basta con dejarlo junto a los
módulos y correrlo. Requiere dpkg-deb y fakeroot (vienen con Debian/Ubuntu).
"""
import os, shutil, subprocess, sys
from pathlib import Path

# La carpeta donde vive este script es la que se empaqueta. Antes apuntaba a
# una ruta fija y eso arriesgaba construir el .deb desde una copia vieja.
ORIGEN = Path(__file__).resolve().parent
SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else ORIGEN.parent / "paquetes"

# El identificador de escritorio TIENE que ser el mismo que el programa declara
# con setDesktopFileName() (run_dpi.py y main_anillos.py). Si no coinciden, en
# Wayland el ícono no aparece en el dock.
APP_ID = "moicedrus-dpi"

# Nombre del paquete Debian. La Policy 5.6.1 solo admite minúsculas, dígitos,
# «+», «-» y «.»: ni mayúsculas, ni espacios, ni guión bajo. Por eso
# «DendroPixel Interface_DPI» no se puede usar tal cual como nombre de paquete;
# el nombre visible y completo va en el campo Description y en el menú.
PAQUETE = "dendro-pixel-interface-dpi"

sys.path.insert(0, str(ORIGEN))
from constantes import VERSION, APP_NOMBRE  # noqa

RAIZ = SALIDA / f"{PAQUETE}_{VERSION}"
if RAIZ.exists():
    shutil.rmtree(RAIZ)

LIB = RAIZ / "usr/lib" / PAQUETE
BIN = RAIZ / "usr/bin"
APPS = RAIZ / "usr/share/applications"
DOC = RAIZ / "usr/share/doc" / PAQUETE
DEBIAN = RAIZ / "DEBIAN"
for d in (LIB, BIN, APPS, DOC, DEBIAN):
    d.mkdir(parents=True, exist_ok=True)

# ── 1. Código fuente ──────────────────────────────────────────────────────
#  · instalar_lanzador_linux.py sirve para instalar a mano desde el código;
#    con el .deb el lanzador ya queda puesto y tenerlo dentro confunde.
#  · construir_deb.py es esta misma herramienta, no parte del programa.
_FUERA = {"instalar_lanzador_linux.py", "construir_deb.py"}
modulos = sorted(p.name for p in ORIGEN.glob("*.py") if p.name not in _FUERA)
for nombre in modulos:
    shutil.copy2(ORIGEN / nombre, LIB / nombre)
shutil.copy2(ORIGEN / "species_profiles.json", LIB / "species_profiles.json")
shutil.copy2(ORIGEN / "dpi.ico", LIB / "dpi.ico")
print(f"código: {len(modulos)} módulos")

# ── 2. Íconos ─────────────────────────────────────────────────────────────
# Se parte del PNG grande (1783x1787) y no del .ico, cuyo mayor tamaño interno
# es 256: reducir desde el original da mejor resultado que ampliar desde el
# .ico, y permite ofrecer 512 para pantallas HiDPI.
from PIL import Image

# El PNG grande ha viajado con dos nombres distintos entre carpetas; se prueban
# ambos y se cae al .ico solo si no hay ninguno.
_CANDIDATOS = ("dpi_icon.png", "DPI.png", "dpi.png", "dpi.ico")
_ruta_icono = next((ORIGEN / n for n in _CANDIDATOS if (ORIGEN / n).exists()), None)
if _ruta_icono is None:
    sys.exit("No encuentro el ícono: se esperaba alguno de " + ", ".join(_CANDIDATOS))
fuente = Image.open(_ruta_icono).convert("RGBA")

# El original no es exactamente cuadrado; se centra en un lienzo cuadrado
# transparente para que no quede deformado al reducir.
lado_max = max(fuente.size)
cuadrado = Image.new("RGBA", (lado_max, lado_max), (0, 0, 0, 0))
cuadrado.paste(fuente, ((lado_max - fuente.width) // 2,
                        (lado_max - fuente.height) // 2))

tamanos = [16, 24, 32, 48, 64, 128, 256, 512]
for lado in tamanos:
    destino = RAIZ / f"usr/share/icons/hicolor/{lado}x{lado}/apps"
    destino.mkdir(parents=True, exist_ok=True)
    cuadrado.resize((lado, lado), Image.LANCZOS).save(destino / f"{APP_ID}.png")

# Copia en pixmaps para los entornos de escritorio antiguos que todavía la
# buscan ahí en vez de en el árbol hicolor.
pix = RAIZ / "usr/share/pixmaps"
pix.mkdir(parents=True, exist_ok=True)
cuadrado.resize((256, 256), Image.LANCZOS).save(pix / f"{APP_ID}.png")
print(f"íconos: {len(tamanos)} tamaños desde {_ruta_icono.name} "
      f"{fuente.size} -> {tamanos}")

# ── 3. Lanzador ───────────────────────────────────────────────────────────
lanzador = BIN / "dpi"
lanzador.write_text(
    "#!/bin/sh\n"
    "# Lanzador de Dendro Pixel Interface\n"
    f'exec python3 /usr/lib/{PAQUETE}/run_dpi.py "$@"\n')
lanzador.chmod(0o755)

# ── 4. Entrada de escritorio ──────────────────────────────────────────────
# El nombre del archivo TIENE que ser APP_ID.desktop: en Wayland el compositor
# no puede leer el ícono desde la ventana y lo busca por este nombre, que es el
# que la aplicación declara con setDesktopFileName().
(APPS / f"{APP_ID}.desktop").write_text(
    "[Desktop Entry]\n"
    "Type=Application\n"
    f"Name={APP_NOMBRE}\n"
    "GenericName=Dendrocronología\n"
    "Comment=Medición de anillos de crecimiento y co-datación\n"
    "Exec=dpi %f\n"
    f"Icon={APP_ID}\n"
    "Terminal=false\n"
    # Una sola categoría PRINCIPAL (Science). Con varias, el menú del
    # escritorio muestra la aplicación repetida una vez por categoría.
    # Geoscience es categoría adicional y requiere Science, así que es válida.
    "Categories=Science;Geoscience;\n"
    "Keywords=dendrocronologia;anillos;arboles;cofechado;tree-ring;\n"
    "StartupNotify=true\n", encoding="utf-8")

# ── 4 bis. Metadatos AppStream ────────────────────────────────────────────
# Esto es lo que lee el Centro de Software de Ubuntu (GNOME Software). NO lee
# el archivo «control» de Debian: sin este XML la aplicación aparece sin
# licencia, sin sitio web y sin fecha de última actualización.
#
# La fecha de publicación se toma de CITATION.cff para no tener dos fuentes
# que se contradigan.
import re as _re
_cff = (ORIGEN / "CITATION.cff").read_text(encoding="utf-8")
_m = _re.search(r'^date-released:\s*"?(\d{4}-\d{2}-\d{2})"?', _cff, _re.M)
FECHA = _m.group(1) if _m else "1970-01-01"

# Identificador en notación de dominio invertido, que es lo que pide AppStream.
# El <launchable> lo conecta con el .desktop, que conserva su propio nombre
# porque tiene que coincidir con setDesktopFileName().
# Todo en minúsculas: AppStream lo pide así, y cambiar el identificador una vez
# publicado hace que el Centro de Software lo trate como otra aplicación.
APPSTREAM_ID = "io.github.rojasbadillamoi.dpi"

METAINFO = RAIZ / "usr/share/metainfo"
METAINFO.mkdir(parents=True, exist_ok=True)
(METAINFO / f"{APPSTREAM_ID}.metainfo.xml").write_text(
    f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{APPSTREAM_ID}</id>
  <launchable type="desktop-id">{APP_ID}.desktop</launchable>

  <name>{APP_NOMBRE}</name>
  <summary>Medición de anillos de crecimiento y co-datación</summary>
  <summary xml:lang="en">Tree-ring measurement and crossdating</summary>

  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-3.0-or-later</project_license>

  <developer id="io.github.rojasbadillamoi">
    <name>Moisés E. Rojas-Badilla</name>
  </developer>

  <description>
    <p>
      Programa de escritorio para medir el ancho de los anillos de crecimiento
      sobre imagen digitalizada, co-datar series dendrocronológicas y controlar
      la calidad del fechado, todo en un mismo lugar.
    </p>
    <p>Incluye:</p>
    <ul>
      <li>Medición sobre la imagen, con detección automática de límites de anillo configurable por especie.</li>
      <li>Intensidad de madera (Blue Intensity) y estimación de médula faltante.</li>
      <li>Co-datación por correlación móvil, con un localizador del año donde se rompe la datación.</li>
      <li>Diagrama de skeleton-plot digital.</li>
      <li>Control de calidad compatible con COFECHA sobre la colección completa.</li>
      <li>Construcción de cronologías con estadísticos de señal común (Rbar entre árboles, EPS y SSS).</li>
      <li>Exportación de figuras para publicar en PNG, SVG y PDF.</li>
    </ul>
    <p>
      Las series se exportan en formato Tucson, compatible con COFECHA, ARSTAN,
      CDendro y dplR.
    </p>
    <p>
      Parte de la MoiCedrus Dendrochronological Suite, desarrollada por
      Moisés E. Rojas-Badilla.
    </p>
  </description>

  <categories>
    <category>Science</category>
    <category>Geoscience</category>
  </categories>

  <keywords>
    <keyword>dendrocronología</keyword>
    <keyword>anillos</keyword>
    <keyword>árboles</keyword>
    <keyword>cofechado</keyword>
    <keyword>dendrochronology</keyword>
    <keyword>tree rings</keyword>
    <keyword>crossdating</keyword>
    <keyword>COFECHA</keyword>
  </keywords>

  <url type="homepage">https://rojasbadillamoi.github.io/</url>
  <url type="bugtracker">https://github.com/rojasbadillamoi/DPI/issues</url>
  <url type="vcs-browser">https://github.com/rojasbadillamoi/DPI</url>

  <releases>
    <release version="{VERSION}" date="{FECHA}"/>
  </releases>

  <!-- Sin contenido sensible. GNOME Software muestra un aviso si falta. -->
  <content_rating type="oars-1.1"/>
</component>
""", encoding="utf-8")

# ── 5. Metadatos del paquete ──────────────────────────────────────────────
# matplotlib va en Depends y no en Recommends: sin él la descarga de figuras
# —una función del programa, no un extra— queda inaccesible, y un paquete no
# debería instalarse en un estado donde parte de la interfaz no funciona.
DEPENDS = ", ".join([
    "python3 (>= 3.10)", "python3-pyqt6", "python3-pyqtgraph", "python3-numpy",
    "python3-pandas", "python3-scipy", "python3-opencv", "python3-pil",
    "python3-openpyxl", "python3-matplotlib",
])
(DEBIAN / "control").write_text(
    f"Package: {PAQUETE}\n"
    f"Version: {VERSION}\n"
    "Section: science\n"
    "Priority: optional\n"
    "Architecture: all\n"
    f"Depends: {DEPENDS}\n"
    "Maintainer: Moisés Rojas-Badilla <rjsw@st-andrews.ac.uk>\n"
    "Homepage: https://rojasbadillamoi.github.io/\n"
    f"Description: {APP_NOMBRE} (DPI) - medicion de anillos y co-datacion\n"
    " Programa de escritorio para medir el ancho de los anillos de\n"
    " crecimiento sobre imagen digitalizada, co-datar series y controlar\n"
    " la calidad del fechado.\n"
    " .\n"
    " Incluye deteccion automatica de limites de anillo, intensidad de\n"
    " madera (Blue Intensity), estimacion de medula faltante, un\n"
    " localizador del anio donde se rompe la datacion, control de calidad\n"
    " compatible con COFECHA y construccion de cronologias.\n"
    " .\n"
    " Parte de la MoiCedrus Dendrochronological Suite, desarrollada por\n"
    " Moises E. Rojas-Badilla.\n", encoding="utf-8")

(DOC / "copyright").write_text(
    "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
    f"Upstream-Name: {APP_NOMBRE}\n"
    "Source: https://github.com/rojasbadillamoi/DPI\n\n"
    "Files: *\n"
    "Copyright: 2026 Moises Rojas-Badilla\n"
    "License: GPL-3.0+\n", encoding="utf-8")

shutil.copy2(ORIGEN / "CHANGELOG.md", DOC / "changelog.md")
subprocess.run(["gzip", "-9n", str(DOC / "changelog.md")], check=True)

# postinst/postrm: refrescar las cachés de iconos y de menú
(DEBIAN / "postinst").write_text(
    "#!/bin/sh\nset -e\n"
    "if [ -x /usr/bin/gtk-update-icon-cache ]; then\n"
    "    gtk-update-icon-cache -q /usr/share/icons/hicolor || true\n"
    "fi\n"
    "if [ -x /usr/bin/update-desktop-database ]; then\n"
    "    update-desktop-database -q /usr/share/applications || true\n"
    "fi\n"
    "exit 0\n")
(DEBIAN / "postinst").chmod(0o755)
shutil.copy2(DEBIAN / "postinst", DEBIAN / "postrm")

# ── 6. Construir ──────────────────────────────────────────────────────────
deb = SALIDA / f"{PAQUETE}_{VERSION}_all.deb"
subprocess.run(["fakeroot", "dpkg-deb", "--build", str(RAIZ), str(deb)],
               check=True)
print(f"\n.deb construido: {deb}  ({deb.stat().st_size/1024:.0f} KB)")
