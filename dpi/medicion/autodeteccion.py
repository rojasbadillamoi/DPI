"""
modulo_autodeteccion.py — Detección automática de límites de anillos

Pipeline:
  1. Usuario marca médula y corteza con 2 clics (modo MODO_AUTODETECT)
  2. Se extrae el perfil de intensidad a lo largo de esa línea,
     promediando una banda de N píxeles de ancho (configurable)
  3. Se detectan mínimos/máximos locales según parámetros de especie
  4. Se colocan los puntos automáticamente en la VistaInteractiva
  5. El usuario corrige con las herramientas existentes

Perfiles de especie se guardan en species_profiles.json junto al ejecutable.
"""

import os
import math
import logging

import cv2
import numpy as np
from scipy.signal import find_peaks, savgol_filter

import dpi.infraestructura.json_seguro as _js

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Rutas del archivo de perfiles
# ------------------------------------------------------------------
# Hay DOS archivos, y la distinción importa:
#
#   · el de FÁBRICA viaja junto al programa y es de solo lectura. Cuando DPI
#     se instala con el .deb o con el instalador de Windows queda en una
#     carpeta del sistema que pertenece a root (/usr/lib/... o Program Files).
#   · el del USUARIO vive en su carpeta personal y es donde se guarda todo lo
#     que afine.
#
# Antes había uno solo, el de al lado del programa. Corriendo desde el código
# fuente funcionaba, pero instalado el usuario no tiene permiso de escritura
# ahí: creaba un perfil de especie, pulsaba guardar, no veía ningún error
# —el fallo solo iba al registro— y al reiniciar el perfil no estaba.
_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUTA_PERFILES_FABRICA = os.path.join(_DIR, "species_profiles.json")


def _carpeta_config() -> str:
    """Carpeta de configuración del usuario, según el estándar de cada sistema."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = (os.environ.get("XDG_CONFIG_HOME")
                or os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "moicedrus-dpi")


RUTA_PERFILES = os.path.join(_carpeta_config(), "species_profiles.json")

# Perfil por defecto (coníferas con escáner plano)
PERFIL_DEFECTO = {
    "canal":           "gray",   # "gray" | "red" | "green" | "blue"
    "invertir":        False,    # True si los límites son claros (madera temprana oscura)
    "suavizado":       7,        # Ventana Savitzky-Golay (px, impar)
    "prominencia":     12.0,     # Prominencia mínima del pico (0-255)
    "anchura_min_px":  15,       # Ancho mínimo del anillo en píxeles
    "anchura_max_px":  3000,     # Ancho máximo del anillo en píxeles
    "banda_px":        5,        # Semi-ancho de la banda de muestreo
}


# =============================================================================
# GESTIÓN DE PERFILES DE ESPECIE
# =============================================================================

def _leer(ruta: str) -> dict:
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = _js.cargar_json(f)
        return datos if isinstance(datos, dict) else {}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as exc:
        logger.warning("No se pudo leer %s: %s", ruta, exc)
        return {}


def cargar_perfiles() -> dict:
    """Perfiles de fábrica más los del usuario, que mandan sobre los de fábrica.

    Se combinan en vez de elegir uno: así el usuario conserva lo suyo y además
    recibe los perfiles nuevos que traiga cada versión del programa. Si edita
    un perfil de fábrica, su versión es la que vale.
    """
    perfiles = {"Conífera (defecto)": PERFIL_DEFECTO.copy()}
    perfiles.update(_leer(RUTA_PERFILES_FABRICA))
    perfiles.update(_leer(RUTA_PERFILES))
    return perfiles


def guardar_perfiles(perfiles: dict):
    """Guarda los perfiles en la carpeta del usuario.

    Escritura atómica: son ajustes que se afinan especie por especie, y
    perderlos por un guardado a medias obliga a rehacer ese trabajo a mano.
    """
    try:
        os.makedirs(os.path.dirname(RUTA_PERFILES), exist_ok=True)
        _js.guardar_json(RUTA_PERFILES, perfiles)
    except Exception as exc:
        logger.error("No se pudo guardar %s: %s", RUTA_PERFILES, exc)
        raise


# =============================================================================
# EXTRACCIÓN DE PERFIL DE INTENSIDAD
# =============================================================================

def extraer_perfil(
    imagen_bgr: np.ndarray,
    p_inicio: tuple[float, float],
    p_fin: tuple[float, float],
    canal: str,
    banda_px: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extrae el perfil de intensidad a lo largo del segmento p_inicio→p_fin.

    Promedia `banda_px` píxeles a cada lado de la línea (perpendicular)
    para reducir el ruido de la textura local.

    Devuelve:
        distancias_px : posición a lo largo del radio (en píxeles)
        intensidades  : valor de intensidad promediado (0-255 float)
    """
    h, w = imagen_bgr.shape[:2]

    # Canal de imagen
    if canal == "gray":
        img = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY).astype(float)
    elif canal == "red":
        img = imagen_bgr[:, :, 2].astype(float)
    elif canal == "green":
        img = imagen_bgr[:, :, 1].astype(float)
    elif canal == "blue":
        img = imagen_bgr[:, :, 0].astype(float)
    else:
        img = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY).astype(float)

    x0, y0 = p_inicio
    x1, y1 = p_fin
    longitud = math.hypot(x1 - x0, y1 - y0)
    if longitud < 2:
        return np.array([]), np.array([])

    n_muestras = int(longitud)
    # Vector unitario a lo largo del radio
    ux = (x1 - x0) / longitud
    uy = (y1 - y0) / longitud
    # Vector perpendicular
    px_v = -uy
    py_v = ux

    distancias = np.arange(n_muestras, dtype=float)
    intensidades = np.zeros(n_muestras, dtype=float)
    conteo = np.zeros(n_muestras, dtype=int)

    for offset in range(-banda_px, banda_px + 1):
        xs = x0 + distancias * ux + offset * px_v
        ys = y0 + distancias * uy + offset * py_v
        # Solo píxeles dentro de la imagen
        mask = (xs >= 0) & (xs < w - 1) & (ys >= 0) & (ys < h - 1)
        xi = xs[mask].astype(int)
        yi = ys[mask].astype(int)
        intensidades[mask] += img[yi, xi]
        conteo[mask] += 1

    validos = conteo > 0
    intensidades[validos] /= conteo[validos]
    return distancias[validos], intensidades[validos]


# =============================================================================
# DETECCIÓN DE PICOS
# =============================================================================

def detectar_limites(
    distancias: np.ndarray,
    intensidades: np.ndarray,
    perfil: dict,
) -> np.ndarray:
    """
    Detecta los límites de anillos en el perfil de intensidad.

    Devuelve array de posiciones en píxeles (a lo largo del radio)
    donde se encuentran los límites detectados.
    """
    if len(intensidades) < 10:
        return np.array([])

    señal = intensidades.copy()

    # Invertir si los límites son más claros que el interior
    if perfil.get("invertir", False):
        señal = 255.0 - señal

    # Suavizado Savitzky-Golay para preservar la forma de los picos
    ventana = perfil.get("suavizado", 7)
    ventana = max(3, ventana if ventana % 2 == 1 else ventana + 1)
    if len(señal) > ventana:
        try:
            señal = savgol_filter(señal, window_length=ventana, polyorder=2)
        except Exception:
            pass

    # Invertir para buscar mínimos como picos
    señal_inv = -señal

    prominencia = perfil.get("prominencia", 12.0)
    ancho_min   = perfil.get("anchura_min_px", 15)
    ancho_max   = perfil.get("anchura_max_px", 3000)

    picos, props = find_peaks(
        señal_inv,
        prominence=prominencia,
        distance=ancho_min,
        width=(1, ancho_max),
    )

    if len(picos) == 0:
        return np.array([])

    return distancias[picos]


# =============================================================================
# CONVERSIÓN DE POSICIONES → COORDENADAS DE ESCENA
# =============================================================================

def posiciones_a_coordenadas(
    posiciones_px: np.ndarray,
    p_inicio: tuple[float, float],
    p_fin: tuple[float, float],
) -> list[tuple[float, float]]:
    """
    Convierte posiciones a lo largo del radio (en píxeles de imagen)
    a coordenadas (x, y) de la escena Qt.
    """
    x0, y0 = p_inicio
    x1, y1 = p_fin
    longitud = math.hypot(x1 - x0, y1 - y0)
    if longitud == 0:
        return []
    ux = (x1 - x0) / longitud
    uy = (y1 - y0) / longitud
    return [(x0 + d * ux, y0 + d * uy) for d in posiciones_px]
