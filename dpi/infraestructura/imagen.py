"""Lectura de metadatos de imágenes sin Qt."""
import logging
from PIL import Image
logger = logging.getLogger(__name__)

def detectar_dpi(ruta: str) -> float | None:
    """Detecta DPI de la imagen desde metadatos. Robusto a múltiples formatos.

    Estrategia (en orden, devuelve el primer valor válido encontrado):
      1. PIL `img.info['dpi']` — Funciona para la mayoría de JPEG/PNG.
      2. EXIF moderno via `img.getexif()` — la nueva API de PIL (más
         confiable que `_getexif()` para JPGs de scanner).
      3. TIFF tags (XResolution=282 + ResolutionUnit=296).
      4. EXIF legacy via `_getexif()` (deprecated pero algunos archivos
         viejos lo necesitan).
      5. ExifTags por nombre (fallback) — algunos JPGs raros.

    Bug histórico: JPGs de scanner viejo o de scanners no estándar (que
    guardan DPI en EXIF en vez de JFIF) no eran detectados. Ahora se
    prueban múltiples métodos en cascada.

    Bug 2026-05 — DecompressionBombError: PIL rechaza por defecto
    imágenes con más de ~178 MP (protección anti-bomba). Esto hacía
    fallar la detección en escaneos grandes (>= 16000x16000 px a
    2400 DPI). Subimos el límite antes de abrir.
    """
    # Desactivar el límite anti-bomba de PIL.
    # Las imágenes de escáneres a 2400 DPI rutinariamente superan
    # 178 MP (un disco de 17 cm = 16000x16000 = 256 MP). Para SOLO
    # leer metadatos del header esto es seguro.
    limite_previo = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None

    try:
        with Image.open(ruta) as img:
            # ── Método 1: info['dpi'] (JPEG con JFIF, PNG con pHYs) ─────
            dpi_info = img.info.get("dpi")
            if dpi_info:
                try:
                    val = float(dpi_info[0])
                    if 50 < val < 30000:   # rango sano para descartar valores corruptos
                        return val
                except (TypeError, ValueError, IndexError):
                    pass

            # ── Método 2: EXIF moderno (img.getexif()) ──────────────────
            # API recomendada por PIL >=9.0. Más confiable que _getexif()
            # para JPGs de scanners modernos.
            try:
                exif_dict = img.getexif()
                if exif_dict:
                    # 0x011A = XResolution
                    x_res = exif_dict.get(0x011A)
                    # 0x0128 = ResolutionUnit (2=pulgada, 3=cm)
                    res_unit = exif_dict.get(0x0128, 2)
                    if x_res is not None:
                        if isinstance(x_res, tuple) and len(x_res) >= 2 and x_res[1]:
                            val = float(x_res[0]) / float(x_res[1])
                        else:
                            val = float(x_res)
                        if res_unit == 3:  # cm → pulgada
                            val = val * 2.54
                        if 50 < val < 30000:
                            return val
            except Exception:
                pass

            # ── Método 3: TIFF tags ─────────────────────────────────────
            if hasattr(img, 'tag_v2'):
                try:
                    from PIL.TiffImagePlugin import IFDRational
                    x_res = img.tag_v2.get(282)
                    if x_res is not None:
                        if isinstance(x_res, IFDRational):
                            val = float(x_res)
                        elif isinstance(x_res, tuple) and len(x_res) >= 2:
                            val = float(x_res[0]) / float(x_res[1]) if x_res[1] else 0
                        else:
                            val = float(x_res)
                        if val > 0:
                            res_unit = img.tag_v2.get(296, 2)
                            if res_unit == 3:  # cm → pulgada
                                val = val * 2.54
                            if 50 < val < 30000:
                                return val
                except Exception:
                    pass

            # ── Método 4: EXIF legacy (_getexif) ────────────────────────
            # Algunos archivos antiguos solo responden a este método.
            try:
                exif = getattr(img, '_getexif', lambda: None)()
                if exif and 0x011A in exif:
                    x_res = exif[0x011A]
                    res_unit = exif.get(0x0128, 2)
                    if isinstance(x_res, tuple) and len(x_res) >= 2 and x_res[1]:
                        val = float(x_res[0]) / float(x_res[1])
                    else:
                        val = float(x_res)
                    if res_unit == 3:
                        val = val * 2.54
                    if 50 < val < 30000:
                        return val
            except Exception:
                pass

            # ── Método 5: ExifTags por nombre (último fallback) ─────────
            # Algunos JPGs raros (scanners viejos, software no estándar)
            # solo exponen los tags por nombre y no por código numérico.
            try:
                from PIL.ExifTags import TAGS
                exif_dict = img.getexif()
                if exif_dict:
                    for tag, value in exif_dict.items():
                        tag_name = TAGS.get(tag, "")
                        if tag_name == "XResolution":
                            if isinstance(value, tuple) and len(value) >= 2 and value[1]:
                                val = float(value[0]) / float(value[1])
                            else:
                                val = float(value)
                            if 50 < val < 30000:
                                return val
            except Exception:
                pass

    except Exception as exc:
        logger.debug("No se pudo leer DPI de %s: %s", ruta, exc)
    finally:
        Image.MAX_IMAGE_PIXELS = limite_previo
    return None


def preparar_banda_rgb(img, banda, brillo, contraste):
    """Convierte BGR a RGB con la LUT original de medición, sin Qt."""
    import cv2
    import numpy as np
    # ── Construir LUT de 256 entradas (O(256), no O(pixeles)) ──
    lut = np.arange(256, dtype=np.float32)
    lut = contraste * lut + brillo
    lut = np.clip(lut, 0, 255).astype(np.uint8)

    sin_ajuste = (brillo == 0 and contraste == 1.0)

    # ── Extraer canal y aplicar ──
    if banda == "RGB":
        if sin_ajuste:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            rgb = cv2.LUT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), lut)
    else:
        if banda == "R":
            gray = img[:, :, 2]
        elif banda == "G":
            gray = img[:, :, 1]
        elif banda == "B":
            gray = img[:, :, 0]
        else:  # Gris
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if not sin_ajuste:
            gray = cv2.LUT(gray, lut)
        rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        del gray

    return rgb


def leer_imagen_bgr(ruta):
    """Decodifica una imagen o informa un error explícito."""
    import cv2
    imagen = cv2.imread(ruta)
    if imagen is None:
        raise ValueError('No se pudo abrir la imagen')
    return imagen
