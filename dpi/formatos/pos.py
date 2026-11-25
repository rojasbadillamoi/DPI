"""Operaciones extraídas sin modificar sus algoritmos."""
import os
from dpi.infraestructura.escritura import ruta_atomica
import re
import numpy as np
from dpi.medicion.constantes import DPI_DEFECTO, MM_POR_PULGADA

def leer_pos(ruta: str) -> tuple[float, int | None, list, list]:
    """Parsea un archivo .pos de CooRecorder y devuelve (dpi, anio, coords_px, saltos)."""
    dpi = DPI_DEFECTO
    anio_datado = None
    coords_px: list[tuple[float, float]] = []
    saltos: list[bool] = []

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.strip()
            if not ln:
                continue
            if ln.startswith("#DPI"):
                try:
                    dpi = float(ln.split()[1].replace(",", "."))
                except (IndexError, ValueError) as exc:
                    raise ValueError("DPI inválido en POS") from exc
                if not np.isfinite(dpi) or dpi <= 0:
                    raise ValueError("DPI inválido en POS")
            elif ln.startswith("#C DATED"):
                try:
                    anio_datado = int(ln.split()[2])
                except (IndexError, ValueError):
                    pass
            elif ln.startswith("#") or ln.startswith("SCALE") or ln.startswith("DATED"):
                continue
            else:
                for i, token in enumerate(ln.split()):
                    token_limpio = re.sub(r"[^\d.,-]", "", token)
                    if "," not in token_limpio:
                        continue
                    try:
                        x_mm, y_mm = map(float, token_limpio.split(",", 1))
                        coords_px.append((x_mm * (dpi / MM_POR_PULGADA), y_mm * (dpi / MM_POR_PULGADA)))
                        saltos.append(False if not saltos else i > 0)
                    except ValueError:
                        pass

    return dpi, anio_datado, coords_px, saltos


def escribir_pos(ruta, coords_px, saltos, dpi, anio_corteza, codigo, ruta_imagen):
    """Escribe la medición en formato .pos (CooRecorder).

    Las coordenadas internas están en píxeles de la imagen; el .pos las
    guarda en MILÍMETROS (x_mm = x_px / pixeles_por_mm). El parser de
    este programa vuelve a convertir mm→px con el DPI, así que el
    archivo es re-importable aquí y compatible con CooRecorder.

    Los "saltos" (gaps entre anillos) se codifican poniendo el punto del
    salto en el MISMO renglón que el punto anterior, que es la convención
    que lee `leer_pos`. Nota: los tipos finos de salto (EW/LW,
    espacio, quiebre) se colapsan a "gap" en el .pos; la fidelidad total
    de esos tipos vive en el estado JSON del programa.
    """
    ppm = dpi / MM_POR_PULGADA  # píxeles por mm
    if not np.isfinite(ppm) or ppm <= 0:
        raise ValueError("DPI inválido en POS")
    if len(coords_px) != len(saltos) or not np.isfinite(coords_px).all():
        raise ValueError("Geometría inválida en POS")
    lineas = [
        "#DENDRO (formato de coordenadas compatible CooRecorder/Cybis)",
        f"#Imagefile {os.path.basename(ruta_imagen)}",
        f"#DPI {dpi:.1f}",
        "#Todas las coordenadas en milímetros (mm)",
        "SCALE 1",
    ]
    if anio_corteza is not None:
        lineas.append(f"#C DATED {int(anio_corteza)}")
    lineas.append(f"#C Code {codigo}")

    buffer_linea: list[str] = []
    for i, (x_px, y_px) in enumerate(coords_px):
        x_mm = x_px / ppm
        y_mm = y_px / ppm
        token = f"{x_mm:.4f},{y_mm:.4f}"
        es_salto_i = bool(saltos[i]) if i < len(saltos) else False
        if i > 0 and es_salto_i and buffer_linea:
            # Salto/gap: se anexa al renglón anterior (i>0 en la línea)
            buffer_linea.append(token)
        else:
            if buffer_linea:
                lineas.append(" ".join(buffer_linea))
            buffer_linea = [token]
    if buffer_linea:
        lineas.append(" ".join(buffer_linea))

    with ruta_atomica(ruta) as temporal:
        with open(temporal, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
