"""
modulo_intensidad_nucleo.py — Extracción de Blue/Red/Green Intensity (BI/RI/GI)

Implementa el método de Maxwell et al. (2017) y CooRecorder:
  - Recorre el camino medido segmento a segmento
  - Promedia los píxeles del canal en una banda perpendicular al camino
  - Agrega por anillo: mean, min, max de cada canal (R, G, B)
  - Exporta como .rwl estándar (valores escalados 0-255 → × 1000)
  - Los quiebres (es_salto="espacio"/"quiebre_ini") se excluyen del promedio
    pero no cortan el anillo

Referencia:
  Maxwell, J.T. et al. (2017). Blue intensity: A pilot study to develop
  a new proxy for reconstructing past climate from tree rings.
  Dendrochronologia, 44, 1-7.
"""

import math
import logging
import numpy as np
from dpi.medicion.calculo import calcular_anillos, puntos_desde_geometria

logger = logging.getLogger(__name__)

# Canales disponibles
CANALES = {
    "Blue":  0,   # índice en BGR de OpenCV
    "Green": 1,
    "Red":   2,
    "Gray":  None,   # canal gris = promedio ponderado luminancia
}


# =============================================================================
# EXTRACCIÓN DE INTENSIDAD POR ANILLO
# =============================================================================

def extraer_intensidad_por_anillo(
    signal_progreso,            # Signal(int, str) o None
    imagen_bgr: np.ndarray,
    coordenadas: list,
    es_salto: list,
    pixeles_por_mm: float,
    banda_px: int = 10,
    canales: list | None = None,
    porcentaje: float = 1.0,    # fracción del anillo a medir (0-1)
    alineacion: str = "centro", # "ew" | "centro" | "lw"
    med_a_cor: bool = True,
    cancelado=None,
) -> list[dict]:
    """
    Extrae B/G/R/Gray Intensity por anillo de forma eficiente en memoria.

    Usa aritmética vectorizada NumPy: en lugar de acumular listas de píxeles,
    calcula mean/min/max por segmento y los combina con promedio ponderado
    por longitud. Reduce el uso de RAM en 10-50x respecto a acumular píxeles.

    signal_progreso: Signal(int, str) de Qt o None. Emite avance por anillo.
    canales: lista de 'B','G','R','Gray' a calcular. None = todos.
    """
    import cv2 as _cv2

    if not 0 < porcentaje <= 1 or alineacion not in ("ew", "centro", "lw"):
        raise ValueError("Recorte de intensidad inválido")
    if not med_a_cor:
        alineacion = {"ew": "lw", "lw": "ew", "centro": "centro"}[alineacion]
    if canales is None:
        canales = ["B", "G", "R", "Gray"]

    h, w = imagen_bgr.shape[:2]
    n = len(coordenadas)
    if n < 2:
        return []

    # Preparar canales solicitados como arrays contiguos
    ch_arrays = {}
    if "B" in canales:    ch_arrays["B"]    = np.ascontiguousarray(imagen_bgr[:, :, 0])
    if "G" in canales:    ch_arrays["G"]    = np.ascontiguousarray(imagen_bgr[:, :, 1])
    if "R" in canales:    ch_arrays["R"]    = np.ascontiguousarray(imagen_bgr[:, :, 2])
    if "Gray" in canales: ch_arrays["Gray"] = _cv2.cvtColor(imagen_bgr, _cv2.COLOR_BGR2GRAY)

    resultados = []

    # Acumuladores por anillo: suma ponderada y conteo de píxeles
    # Guardar (sum, sum_sq, min_val, max_val, count) por canal
    def _nuevo_acum():
        return {ch: [0.0, float('inf'), float('-inf'), 0] for ch in ch_arrays}
        # [suma, min, max, count]

    def _cerrar_anillo(acum, indice):
        if not any(v[3] > 0 for v in acum.values()):
            return
        entry = {"indice_anillo": indice}
        for ch, (s, mn, mx, cnt) in acum.items():
            entry[f"{ch}_mean"] = s / cnt if cnt > 0 else 0.0
            entry[f"{ch}_min"]  = mn
            entry[f"{ch}_max"]  = mx
        resultados.append(entry)

    def _muestrar_segmento(x0, y0, x1, y1, acum):
        """Muestrea la banda perpendicular al segmento y actualiza acum."""
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len <= 0:
            return
        ux = (x1 - x0) / seg_len
        uy = (y1 - y0) / seg_len
        perp_x, perp_y = -uy, ux

        n_s = max(2, int(seg_len))
        ts = np.linspace(0.0, 1.0, n_s)
        xs_c = (x0 + ts * (x1 - x0)).reshape(1, -1)  # (1, n_s)
        ys_c = (y0 + ts * (y1 - y0)).reshape(1, -1)

        offs = np.arange(-banda_px, banda_px + 1).reshape(-1, 1)  # (2b+1, 1)
        xs_all = (xs_c + offs * perp_x).ravel()
        ys_all = (ys_c + offs * perp_y).ravel()

        mask = ((xs_all >= 0) & (xs_all < w) &
                (ys_all >= 0) & (ys_all < h))
        xi = xs_all[mask].astype(np.int32)
        yi = ys_all[mask].astype(np.int32)
        if len(xi) == 0:
            return

        for ch, arr in ch_arrays.items():
            vals = arr[yi, xi].astype(np.float32)
            s, mn, mx, cnt = acum[ch]
            acum[ch] = [s + float(vals.sum()),
                        min(mn, float(vals.min())),
                        max(mx, float(vals.max())),
                        cnt + len(vals)]

    anillos = segmentos_banda_intensidad(coordenadas, es_salto)
    for indice, segmentos in enumerate(anillos):
        if cancelado is not None and cancelado():
            return []
        acum = _nuevo_acum()
        longitud = sum(math.dist(coordenadas[ip], coordenadas[ic]) for ip, ic in segmentos)
        recorte = 1.0 - porcentaje
        inicio = 0.0 if alineacion == "ew" else longitud * (recorte if alineacion == "lw" else recorte / 2)
        fin = inicio + longitud * porcentaje
        pos = 0.0
        for ip, ic in segmentos:
            if cancelado is not None and cancelado():
                return []
            x0, y0 = coordenadas[ip]
            x1, y1 = coordenadas[ic]
            largo = math.dist((x0,y0), (x1,y1))
            desde, hasta = max(pos, inicio), min(pos + largo, fin)
            if largo > 0 and hasta > desde:
                t0, t1 = (desde-pos)/largo, (hasta-pos)/largo
                _muestrar_segmento(x0+t0*(x1-x0), y0+t0*(y1-y0),
                                   x0+t1*(x1-x0), y0+t1*(y1-y0), acum)
            pos += largo
        _cerrar_anillo(acum, indice)
        if signal_progreso is not None:
            signal_progreso.emit(int(100 * (indice + 1) / len(anillos)),
                                 f"Anillo {indice+1}/{len(anillos)} · banda {banda_px}px")
    return resultados


def valores_intensidad(datos, canal, metrica):
    """Extrae una métrica o razón de canales, común a todos los formatos."""
    if canal in ("B_R", "B_G"):
        otro = "R" if canal == "B_R" else "G"
        return [d.get("B_mean", 0.0) / d.get(f"{otro}_mean", 1.0)
                if d.get(f"{otro}_mean", 1.0) > 0 else 0.0 for d in datos]
    return [d.get(f"{canal}_{metrica}", 0.0) for d in datos]


def segmentos_banda_intensidad(coords, saltos):
    """Un grupo por anillo geométrico, incluso si no admite muestras."""
    puntos = puntos_desde_geometria(coords, saltos)
    return [[(i-1, i) for i in a.segmentos if not puntos[i].tipo.excluye_intensidad]
            for a in calcular_anillos(puntos, 1)]
