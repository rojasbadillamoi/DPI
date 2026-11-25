"""Cálculos geométricos de medición, sin Qt."""
from dataclasses import dataclass
from functools import lru_cache
import math
from dpi.medicion.modelo import PuntoMedicion, TipoMarca


def anchos_anillos(coords, marcas, ppm):
    """Adaptador para consumidores del formato histórico."""
    puntos = puntos_desde_geometria(coords, marcas)
    return anchos_puntos(puntos, ppm)


@dataclass(frozen=True, slots=True)
class AnilloMedido:
    indice_inicio: int
    indice_fin: int
    ancho_mm: float
    segmentos: tuple[int, ...] = ()  # índices finales de segmentos que suman ancho
    completo: bool = True


def calcular_anillos(puntos, ppm):
    """Devuelve una lista independiente de los anillos calculados."""
    return list(_calcular_anillos(tuple(puntos), ppm))


@lru_cache(maxsize=16)
def _calcular_anillos(puntos, ppm):
    """Reutiliza el cálculo mientras no cambien los puntos o la escala."""
    if not math.isfinite(ppm) or ppm <= 0:
        raise ValueError('Escala de medición inválida')
    anillos = []
    acum = 0.0
    inicio = 0
    segmentos = []
    for i, (anterior, actual) in enumerate(zip(puntos, puntos[1:]), 1):
        tipo = actual.tipo
        if tipo is TipoMarca.SALTO:
            if acum > 0:
                anillos.append(AnilloMedido(inicio, segmentos[-1], acum, tuple(segmentos), False))
            acum = 0.0
            segmentos = []
            inicio = i
        elif tipo is not TipoMarca.ESPACIO:
            acum += math.dist(anterior.coordenada, actual.coordenada) / ppm
            segmentos.append(i)
            if tipo is TipoMarca.NORMAL:
                anillos.append(AnilloMedido(inicio, i, acum, tuple(segmentos)))
                acum = 0.0
                segmentos = []
                inicio = i
    if acum > 0:
        anillos.append(AnilloMedido(inicio, segmentos[-1], acum, tuple(segmentos), False))
    return tuple(anillos)


def puntos_desde_geometria(coords, marcas):
    """Adaptador único de coordenadas/marcas históricas al modelo tipado."""
    return tuple(PuntoMedicion(c, m) for c, m in zip(coords, marcas, strict=True))


def anchos_puntos(puntos, ppm):
    return [a.ancho_mm for a in _calcular_anillos(tuple(puntos), ppm)]


def anios_por_punto(puntos, ppm, medula, corteza, med_a_cor):
    """Años de los puntos y conjunto de índices que cierran un anillo."""
    cierres = {a.indice_fin for a in _calcular_anillos(tuple(puntos), ppm)}
    n = 0
    anios = []
    for i in range(len(puntos)):
        n += i in cierres
        if i == 0:
            anios.append(medula - 1 if med_a_cor else corteza)
        else:
            anios.append(medula + n - 1 if med_a_cor else corteza - n + 1)
    return anios, cierres


def anios_medicion(n, medula, corteza, med_a_cor):
    return [medula + i if med_a_cor else corteza - i for i in range(n)]


def dist_punto_segmento(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    l2 = (x1 - x2) ** 2 + (y1 - y2) ** 2
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
    return math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)))


def segmento_mas_cercano(coords, x: float, y: float, tol: float) -> tuple[int, float, float] | None:
    """
    Devuelve (idx_segmento, t, d_px) del segmento del camino más cercano al punto
    (x, y), donde idx_segmento es el índice del punto inicial del segmento,
    t es la proyección paramétrica [0,1] sobre ese segmento, y d_px es la
    distancia en px de escena.
    Devuelve None si no hay segmentos o el más cercano supera la tolerancia.
    """
    if len(coords) < 2:
        return None
    mejor_d, mejor_idx, mejor_t = float("inf"), -1, 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        l2 = (x2-x1)**2 + (y2-y1)**2
        if l2 < 1e-9:
            continue
        t = max(0.0, min(1.0, ((x-x1)*(x2-x1) + (y-y1)*(y2-y1)) / l2))
        px, py = x1 + t*(x2-x1), y1 + t*(y2-y1)
        d = math.hypot(x-px, y-py)
        if d < mejor_d:
            mejor_d, mejor_idx, mejor_t = d, i, t
    if mejor_idx == -1 or mejor_d > tol:
        return None
    return mejor_idx, mejor_t, mejor_d

def indice_punto_mas_cercano(coordenadas, x, y, tol):
    """Índice del punto más cercano dentro de la tolerancia estricta."""
    mejor_idx, mejor_d = None, float("inf")
    for i, (px, py) in enumerate(coordenadas):
        d = math.hypot(px - x, py - y)
        if d < tol and d < mejor_d:
            mejor_d, mejor_idx = d, i
    return mejor_idx


def posicion_insercion(coords, ancla, punto):
    """Posición adyacente al ancla, según la distancia a sus vecinos."""
    if not 0 <= ancla < len(coords):
        raise IndexError('Ancla inválida')
    if ancla == len(coords) - 1:
        return len(coords)
    if ancla == 0:
        return 0
    return ancla + 1 if math.dist(punto, coords[ancla+1]) < math.dist(punto, coords[ancla-1]) else ancla


def ordenar_extremos_espacio(coords, p1, s1, p2, s2):
    if s1 > s2 or (s1 == s2 and math.dist(p1, coords[s1]) > math.dist(p2, coords[s1])):
        return p2, s2, p1, s1
    return p1, s1, p2, s2


def escala_desde_dpi(dpi):
    from dpi.medicion.constantes import MM_POR_PULGADA
    if not math.isfinite(dpi) or dpi <= 0:
        raise ValueError('DPI inválido')
    return dpi / MM_POR_PULGADA
