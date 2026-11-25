"""Cálculo de estimación de médula, independiente de Qt."""
import math
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def ajuste_degenerado(puntos, radio):
    """Detecta un radio mayor que 50 veces la separación máxima medida."""
    seg_max = 0.0
    for i, p_i in enumerate(puntos):
        for p_j in puntos[i + 1:]:
            seg_max = max(seg_max, math.hypot(p_j[0]-p_i[0], p_j[1]-p_i[1]))
    return seg_max > 0 and radio > seg_max * 50


def ajustar_circulo_minimos_cuadrados(
    puntos: list[tuple[float, float]]
) -> tuple[float, float, float] | None:
    """
    Ajusta el mejor círculo a N≥3 puntos por mínimos cuadrados algebraicos
    (ajuste lineal algebraico, centrado y escalado).

    Devuelve (cx, cy, radio) en las mismas unidades que los puntos,
    o None si los puntos son colineales o insuficientes.
    """
    if len(puntos) < 3:
        return None

    pts = np.asarray(puntos, dtype=float)
    if pts.shape != (len(puntos), 2) or not np.isfinite(pts).all():
        return None
    origen = pts.mean(axis=0)
    x, y = (pts - origen).T
    escala = max(np.max(np.abs(x)), np.max(np.abs(y)))
    if not np.isfinite(escala) or escala <= 0:
        return None
    x, y = x / escala, y / escala
    A = np.column_stack([2*x, 2*y, np.ones(len(x))])
    b = x**2 + y**2
    try:
        result, _, rango, _ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rango != 3:
        return None
    cx, cy, c = result
    r2 = cx**2 + cy**2 + c
    if not math.isfinite(r2) or r2 <= 0:
        return None
    centro = origen + escala * np.array([cx, cy])
    return float(centro[0]), float(centro[1]), float(escala * math.sqrt(r2))


def estimar_anillos_faltantes(
    distancia_faltante_mm: float,
    anchos_internos_mm: list[float],
    serie_ref: pd.Series | None = None,
    anio_inicio_serie: int | None = None,
) -> dict:
    """
    Estima el número de anillos faltantes entre el borde interno medido
    y la médula, usando los anchos de los N anillos más internos.

    Parámetros
    ----------
    distancia_faltante_mm : distancia desde el primer punto medido hasta
                            el centro estimado del árbol, en mm.
    anchos_internos_mm    : anchos (mm) de los N anillos más internos,
                            ordenados de más externo a más interno (último = más
                            cercano a la médula).
    serie_ref             : Serie de pandas con índice=año y valores=ancho_mm.
                            Si se proporciona, se usan anchos relativos en vez
                            del promedio.
    anio_inicio_serie     : año del primer anillo medido. Necesario para
                            alinear la serie de referencia hacia atrás.

    Devuelve un dict con:
      - n_media      : estimación usando ancho promedio
      - n_tendencia  : estimación usando regresión lineal (tendencia)
      - n_referencia : estimación usando serie de referencia (None si no hay ref)
      - ancho_medio  : ancho promedio usado (mm)
      - ancho_tendencia_en0 : ancho extrapolado en el anillo más interno
      - incertidumbre_min : mínimo razonable (percentil 25 de los anchos)
      - incertidumbre_max : máximo razonable (percentil 75 de los anchos)
    """
    if not anchos_internos_mm or distancia_faltante_mm <= 0:
        return {}

    arr = np.array(anchos_internos_mm, dtype=float)
    arr = arr[arr > 0]
    if len(arr) == 0:
        return {}

    # ── Método 1: promedio simple ─────────────────────────────────────────
    ancho_medio = float(np.mean(arr))
    n_media = distancia_faltante_mm / ancho_medio if ancho_medio > 0 else 0

    # ── Método 2: tendencia lineal extrapolada ────────────────────────────
    # Regresión sobre los anchos internos; extrapolamos hacia el centro
    n = len(arr)
    xs = np.arange(n, dtype=float)   # 0 = más externo, n-1 = más interno
    if n >= 3:
        coef = np.polyfit(xs, arr, 1)   # coef[0]=pendiente, coef[1]=intercepto
        # Extrapolamos más allá de n-1 (hacia la médula)
        # Ancho estimado en posición k > n-1: max(0.1, poly(k))
        # Suma acumulada hasta llegar a distancia_faltante_mm
        ancho_en_ultimo = float(np.polyval(coef, n - 1))
        pendiente = float(coef[0])
        # Si la tendencia es decreciente (anillos más estrechos hacia centro),
        # tiene sentido físico — los árboles jóvenes pueden crecer más rápido.
        # Acumulamos hacia atrás hasta cubrir la distancia.
        acum = 0.0
        k = 0
        while acum < distancia_faltante_mm and k < 500:
            ancho_k = max(0.05, np.polyval(coef, (n - 1) + k))
            acum += ancho_k
            k += 1
        n_tendencia = float(k)
        ancho_tendencia_en0 = float(np.polyval(coef, n - 1))
    else:
        n_tendencia = n_media
        ancho_tendencia_en0 = ancho_medio

    # ── Método 3: serie de referencia ────────────────────────────────────
    n_referencia = None
    if serie_ref is not None and anio_inicio_serie is not None and len(serie_ref) >= 5:
        try:
            # Calcular factor de escala: promedio de anchos propios / promedio
            # de la referencia en el mismo rango de años disponibles
            ref_clip = serie_ref.clip(lower=0.01)
            ref_media_global = float(ref_clip.mean())
            escala = ancho_medio / ref_media_global if ref_media_global > 0 else 1.0

            # Ir hacia atrás desde anio_inicio_serie usando los anchos
            # relativos de la referencia, escalados
            acum = 0.0
            k = 0
            anio_actual = anio_inicio_serie - 1
            while acum < distancia_faltante_mm and k < 500:
                if anio_actual in ref_clip.index:
                    ancho_k = float(ref_clip.loc[anio_actual]) * escala
                else:
                    # Fuera del rango de la referencia: usar el promedio escalado
                    ancho_k = ancho_medio
                ancho_k = max(0.05, ancho_k)
                acum += ancho_k
                k += 1
                anio_actual -= 1
            n_referencia = float(k)
        except Exception as exc:
            logger.warning("Error en estimación por referencia: %s", exc)

    # ── Incertidumbre ─────────────────────────────────────────────────────
    p25 = float(np.percentile(arr, 25))
    p75 = float(np.percentile(arr, 75))
    inc_max = distancia_faltante_mm / p25 if p25 > 0 else n_media * 1.5
    inc_min = distancia_faltante_mm / p75 if p75 > 0 else n_media * 0.5

    return {
        "n_media":              round(n_media, 1),
        "n_tendencia":          round(n_tendencia, 1),
        "n_referencia":         round(n_referencia, 1) if n_referencia is not None else None,
        "ancho_medio":          round(ancho_medio, 3),
        "ancho_tendencia_en0":  round(ancho_tendencia_en0, 3),
        "incertidumbre_min":    round(inc_min, 1),
        "incertidumbre_max":    round(inc_max, 1),
    }


def distancia_faltante_dap(coords, saltos, radio_px):
    """Radio menos longitud medida, con las mismas reglas geométricas."""
    from dpi.medicion.calculo import calcular_anillos, puntos_desde_geometria
    if not math.isfinite(radio_px) or radio_px < 0:
        raise ValueError('Radio DAP inválido')
    longitud = sum(a.ancho_mm for a in calcular_anillos(puntos_desde_geometria(coords, saltos), 1))
    return max(0.0, radio_px - longitud)
