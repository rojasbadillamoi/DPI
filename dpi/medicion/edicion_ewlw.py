"""Planificación geométrica de una inserción EW/LW, sin Qt."""
from dpi.medicion.marcas import _es_amarillo, _es_ewlw


def planificar_ewlw(coords, marcas, seg_idx, t):
    """Devuelve (índice, coordenada, mensaje de rechazo)."""
    val_seg = marcas[seg_idx + 1] if seg_idx + 1 < len(marcas) else False
    if _es_amarillo(val_seg):
        return None, None, "🍂 No se puede insertar EW/LW en un tramo de quiebre o salto."
    ini_anillo = seg_idx
    while ini_anillo > 0 and marcas[ini_anillo] is not False:
        ini_anillo -= 1
    fin_anillo = seg_idx + 1
    while fin_anillo < len(coords) and marcas[fin_anillo] is not False:
        fin_anillo += 1
    for j in range(ini_anillo + 1, fin_anillo):
        if j < len(marcas) and _es_ewlw(marcas[j]):
            return None, None, "🍂 Este anillo ya tiene un límite EW/LW. Usa 🖐 Mover para reposicionarlo."
    x1, y1 = coords[seg_idx]
    x2, y2 = coords[seg_idx + 1]
    return seg_idx + 1, (x1 + t * (x2 - x1), y1 + t * (y2 - y1)), None
