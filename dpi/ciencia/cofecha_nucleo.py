"""
MoiCedrus — DPI · Núcleo vectorizado del análisis tipo COFECHA
==============================================================

Este módulo contiene la maquinaria numérica del análisis de cofechado. Se
separó de `dpi.ciencia.cofecha.py` (que conserva la API pública y las funciones
de una sola serie) porque la versión anterior escalaba de forma cuadrática y
se volvía inusable con colecciones reales: 48 series tardaban 41 s y 1600
habrían tardado horas.

Las tres ideas que hacen la diferencia:

1. **Una sola matriz alineada.** Todas las series se vuelcan a un arreglo
   (años × series) con NaN fuera de su extensión. Así los estadísticos por
   año son operaciones de numpy sobre filas completas, no bucles de Python
   con búsquedas en pandas.

2. **Leave-one-out exacto.** Por defecto el maestro es una media aritmética:
   se resta la contribución de cada serie a las sumas y los conteos por año.
   El modo robusto biweight recalcula el maestro para cada exclusión.
   Ver `verificar_leave_one_out` para comprobar la equivalencia numérica.

3. **Sumas acumuladas para las correlaciones por segmento.** Para cada
   desfase se acumulan Σx, Σy, Σx², Σy², Σxy sobre las posiciones válidas.
   Con eso la correlación de CUALQUIER ventana sale en tiempo constante, y
   los 21 desfases × N segmentos dejan de ser el cuello de botella.
"""

from __future__ import annotations

import numpy as np
from dpi.ciencia.indice_anual import validar_anios
from dpi.ciencia.estadistica import (pearson, pearson_desde_sumas,
                                centrar_escalar_correlacion,
                                BIWEIGHT_C, media_biweight)


# ---------------------------------------------------------------------------
# Matriz alineada
# ---------------------------------------------------------------------------

class Matriz:
    """Colección de series volcada a un arreglo (años × series).

    `valores[i, j]` es el valor de la serie `j` en el año `anios[i]`, o NaN si
    esa serie no cubre ese año.
    """

    __slots__ = ("anios", "nombres", "valores", "indice_nombre")

    def __init__(self, anios: np.ndarray, nombres: list[str],
                 valores: np.ndarray):
        self.anios = anios
        self.nombres = nombres
        self.valores = valores
        self.indice_nombre = {n: j for j, n in enumerate(nombres)}

    @classmethod
    def desde_series(cls, series: dict) -> "Matriz":
        nombres = list(series.keys())
        if not nombres or not any(len(s) for s in series.values()):
            raise ValueError("No hay series para alinear.")
        indices = {}
        for nombre, s in series.items():
            indices[nombre] = validar_anios(s.index)
        primero = min(int(idx.min()) for idx in indices.values() if idx.size)
        ultimo = max(int(idx.max()) for idx in indices.values() if idx.size)
        if (ultimo - primero + 1) * len(nombres) > 25_000_000:
            raise ValueError("Matriz anual demasiado grande")
        anios = np.arange(primero, ultimo + 1, dtype=np.int64)
        valores = np.full((anios.size, len(nombres)), np.nan, dtype=float)
        for j, n in enumerate(nombres):
            s = series[n]
            if not len(s):
                continue
            pos = indices[n] - primero
            v = np.asarray(s.to_numpy(), dtype=float)
            bueno = (pos >= 0) & (pos < anios.size) & np.isfinite(v)
            valores[pos[bueno], j] = v[bueno]
        return cls(anios, nombres, valores)

    @property
    def n_series(self) -> int:
        return len(self.nombres)

    def columna(self, nombre: str) -> np.ndarray:
        return self.valores[:, self.indice_nombre[nombre]]


# ---------------------------------------------------------------------------
# Maestro biweight y sus versiones leave-one-out
# ---------------------------------------------------------------------------

class Maestro:
    """Maestro de la colección, con leave-one-out exacto.

    Por defecto promedia de forma ARITMÉTICA, que es lo que hace COFECHA: el
    manual de Holmes dice que las series transformadas se acumulan y la suma
    se divide por el número de series de cada año. Con una media aritmética
    el leave-one-out es exacto y de tiempo constante:

        m₋ⱼ = (Σx − xⱼ) / (n − 1)

    de modo que los maestros de las 1600 series salen del mismo par de sumas
    por año que el maestro global.

    Con `robusto=True` se usa en cambio una media biweight, que resiste mejor
    a una serie aberrante pero NO es lo que hace COFECHA. En ese caso el
    leave-one-out se recalcula de verdad para cada serie, porque el biweight
    tiene un umbral duro (|u| < 1) y quitar una serie puede cambiar qué
    observaciones reciben peso cero: aproximarlo con los pesos de la muestra
    completa producía errores de hasta 1.09 en el maestro. El costo es
    cuadrático, así que conviene reservarlo para colecciones chicas.
    """

    __slots__ = ("valores", "mat", "robusto", "num", "den", "conteo", "_cache")

    def __init__(self, mat: np.ndarray, robusto: bool = False):
        self.mat = mat
        self.robusto = bool(robusto)
        finito = np.isfinite(mat)
        self.conteo = finito.sum(axis=1)
        x0 = np.where(finito, mat, 0.0)
        self.num = x0.sum(axis=1)
        self.den = finito.sum(axis=1).astype(float)
        self._cache = {}
        if self.robusto:
            self.valores = _media_biweight(mat)
        else:
            with np.errstate(invalid="ignore", divide="ignore"):
                self.valores = np.where(self.den > 0, self.num / self.den,
                                        np.nan)

    def excluyendo(self, j: int) -> np.ndarray:
        """Maestro sin la serie `j`."""
        if self.robusto:
            if j not in self._cache:
                self._cache[j] = _media_biweight(
                    np.delete(self.mat, j, axis=1))
            return self._cache[j]
        col = self.mat[:, j]
        hay = np.isfinite(col)
        num = self.num - np.where(hay, col, 0.0)
        den = self.den - hay
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 0, num / den, np.nan)


def _media_biweight(mat: np.ndarray, c: float = BIWEIGHT_C) -> np.ndarray:
    """Adaptador por filas para el maestro robusto de COFECHA."""
    return media_biweight(mat, c=c, axis=1)


def verificar_leave_one_out(mat: np.ndarray, muestras: int = 12,
                             robusto: bool = False):
    """Compara el leave-one-out rápido contra recalcular el maestro entero.

    Devuelve (error_máximo, error_medio). Con media aritmética debe dar cero
    salvo redondeo; sirve como prueba de regresión, no se usa en producción.
    """
    m = Maestro(mat, robusto=robusto)
    rng = np.random.default_rng(0)
    cols = rng.choice(mat.shape[1], size=min(muestras, mat.shape[1]),
                      replace=False)
    errores = []
    for j in cols:
        aprox = m.excluyendo(int(j))
        exacto = Maestro(np.delete(mat, j, axis=1), robusto=robusto).valores
        ok = np.isfinite(aprox) & np.isfinite(exacto)
        if ok.any():
            errores.append(np.abs(aprox[ok] - exacto[ok]))
    if not errores:
        return float("nan"), float("nan")
    todos = np.concatenate(errores)
    return float(todos.max()), float(todos.mean())


# ---------------------------------------------------------------------------
# Correlaciones por ventana mediante sumas acumuladas
# ---------------------------------------------------------------------------

class AcumuladosPar:
    """Sumas acumuladas de un par de vectores alineados.

    Permite la correlación de cualquier ventana [a, b) en tiempo constante:
    se restan las acumuladas en los extremos y se aplica la fórmula de
    Pearson. Las posiciones sin dato en alguno de los dos vectores aportan
    cero y no cuentan en n.
    """

    __slots__ = ("n", "sx", "sy", "sxx", "syy", "sxy", "_x", "_y")

    def __init__(self, x: np.ndarray, y: np.ndarray):
        self._x = np.asarray(x, dtype=float).copy()
        self._y = np.asarray(y, dtype=float).copy()
        x, y = self._x, self._y
        ok = np.isfinite(x) & np.isfinite(y)
        xv = np.where(ok, x, 0.0)
        yv = np.where(ok, y, 0.0)
        cero = np.zeros(1)
        self.n = np.concatenate([cero, np.cumsum(ok.astype(float))])
        self.sx = np.concatenate([cero, np.cumsum(xv)])
        self.sy = np.concatenate([cero, np.cumsum(yv)])
        self.sxx = np.concatenate([cero, np.cumsum(xv * xv)])
        self.syy = np.concatenate([cero, np.cumsum(yv * yv)])
        self.sxy = np.concatenate([cero, np.cumsum(xv * yv)])

    def sumas(self, a: int, b: int):
        """Sumas crudas de la ventana [a, b): (n, Sx, Sy, Sxx, Syy, Sxy).

        Se exponen para poder COMBINAR ventanas que vienen de desfases
        distintos: la correlación conjunta de dos tramos alineados cada uno
        con su propio desfase es la fórmula de Pearson aplicada a la suma de
        sus sumas. Eso es lo que permite evaluar un quiebre en tiempo
        constante.
        """
        return (self.n[b] - self.n[a],
                self.sx[b] - self.sx[a],
                self.sy[b] - self.sy[a],
                self.sxx[b] - self.sxx[a],
                self.syy[b] - self.syy[a],
                self.sxy[b] - self.sxy[a])

    def r(self, a: int, b: int):
        """Correlación y tamaño de muestra de la ventana [a, b)."""
        n, sx, sy, sxx, syy, sxy = self.sumas(a, b)
        if n < 3:
            return float("nan"), int(n)
        r = pearson_desde_sumas(n, sx, sy, sxx, syy, sxy)
        vx = sxx - sx * (sx / n)
        vy = syy - sy * (sy / n)
        tol = 64 * np.finfo(float).eps
        if (not np.isfinite(r) or vx <= tol * self.sxx[b]
                or vy <= tol * self.syy[b]):
            x, y = self._x[a:b], self._y[a:b]
            ok = np.isfinite(x) & np.isfinite(y)
            r = pearson(x[ok], y[ok])
        return r, int(n)


def r_quitando_cada_punto(x: np.ndarray, y: np.ndarray):
    """Efecto de cada observación sobre la correlación, en O(n).

    Es la sección [B] de COFECHA. En vez de recalcular la correlación n veces
    (O(n²)), se restan las contribuciones del punto i a las sumas totales y
    se reevalúa la fórmula de Pearson. Devuelve (posiciones, efectos, r_total)
    donde `efecto[i] = r_total − r_sin_i`: positivo si incluir ese año SUBE la
    correlación.
    """
    ok = np.isfinite(x) & np.isfinite(y)
    xv, yv = x[ok], y[ok]
    n = xv.size
    if n < 5:
        return np.array([], dtype=int), np.array([]), float("nan")

    xv = centrar_escalar_correlacion(xv)[0]
    yv = centrar_escalar_correlacion(yv)[0]
    sx, sy = xv.sum(), yv.sum()
    sxx, syy, sxy = (xv * xv).sum(), (yv * yv).sum(), (xv * yv).sum()
    r_total = pearson(xv, yv)
    if not np.isfinite(r_total):
        return np.array([], dtype=int), np.array([]), float("nan")

    r_sin = pearson_desde_sumas(n - 1, sx - xv, sy - yv, sxx - xv * xv,
                                syy - yv * yv, sxy - xv * yv)
    # Los casos degenerados se recalculan con centrado local.
    for i in np.flatnonzero(~np.isfinite(r_sin)):
        r_sin[i] = pearson(np.delete(x[ok], i), np.delete(y[ok], i))
    efecto = r_total - r_sin
    return np.flatnonzero(ok), efecto, r_total


# ---------------------------------------------------------------------------
# Estadísticos por año con leave-one-out
# ---------------------------------------------------------------------------

def z_leave_one_out(mat: np.ndarray, minimo: int = 4):
    """Puntaje z de cada valor respecto de las OTRAS series de ese año.

    COFECHA compara cada anillo con la media de las demás series del mismo
    año, no con una media que incluya al propio valor. Con las sumas por fila
    eso sale en forma cerrada y de una sola vez para toda la matriz.
    Devuelve una matriz de z con NaN donde no hay suficientes series.
    """
    mat = np.asarray(mat, dtype=float)
    if mat.ndim != 2 or mat.shape[1] == 0:
        raise ValueError("Se esperaba una matriz con series")
    finito = np.isfinite(mat)
    referencia = mat[np.arange(mat.shape[0]), np.argmax(finito, axis=1)][:, None]
    referencia = np.where(np.isfinite(referencia), referencia, 0.0)
    mat = mat - referencia
    x0 = np.where(finito, mat, 0.0)
    n = finito.sum(axis=1)[:, None]
    s = x0.sum(axis=1)[:, None]
    ss = (x0 * x0).sum(axis=1)[:, None]

    n_otros = n - finito
    s_otros = s - x0
    ss_otros = ss - x0 * x0

    with np.errstate(invalid="ignore", divide="ignore"):
        media = s_otros / n_otros
        var = ss_otros / n_otros - media * media
        var = np.where(var > 0, var, np.nan)
        z = (mat - media) / np.sqrt(var)
    return np.where(finito & (n_otros >= minimo), z, np.nan)


def matriz_cambios(mat: np.ndarray) -> np.ndarray:
    """Cambio relativo año a año, fila i = paso del año i al i+1.

    Usa la misma expresión que la sensibilidad media, 2·(x₁−x₀)/(x₁+x₀), de
    modo que el cambio es comparable entre series de distinto crecimiento.
    """
    a = mat[:-1]
    b = mat[1:]
    den = a + b
    with np.errstate(invalid="ignore", divide="ignore"):
        c = 2.0 * (b - a) / den
    return np.where(np.isfinite(c) & (den > 0), c, np.nan)


def r_de_sumas(*bloques):
    """Correlación conjunta de varios tramos, a partir de sus sumas.

    Cada bloque es (n, Sx, Sy, Sxx, Syy, Sxy). Sumarlos y aplicar Pearson
    equivale a correlacionar la concatenación de los tramos ya alineados,
    aunque cada uno se haya alineado con un desfase distinto.
    """
    n = sx = sy = sxx = syy = sxy = 0.0
    for b in bloques:
        n += b[0]; sx += b[1]; sy += b[2]
        sxx += b[3]; syy += b[4]; sxy += b[5]
    if n < 5:
        return float("nan"), int(n)
    return pearson_desde_sumas(n, sx, sy, sxx, syy, sxy), int(n)
