"""
MoiCedrus — DPI · Motor de análisis tipo COFECHA
================================================

Reproduce el análisis de control de calidad de cofechado de COFECHA
(Holmes 1983) sobre una colección de series de ancho de anillo.

Este módulo calcula SOLO los números; el formato de la salida de texto vive
en `modulo_cofecha_salida.py`. Se separan a propósito para poder verificar
las cifras contra archivos .OUT reales sin depender del formato.

Procedimiento, igual que COFECHA:

1. Cada serie se estandariza: spline cúbico de suavizado de Cook & Peters
   (respuesta del 50% a `rigidez_spline` años), log opcional, y modelo
   autorregresivo de orden elegido por AICc.
2. Para cada serie se construye un MAESTRO que la EXCLUYE (leave-one-out),
   promediando las demás con media biweight robusta.
3. La serie se correlaciona con su maestro en segmentos solapados
   (por defecto 50 años avanzando 25) y también en toda su extensión.
4. Cada segmento se marca cuando su correlación cae bajo el nivel crítico
   (bandera A) o cuando correlaciona mejor en otra posición (bandera B).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import modulo_cofecha_nucleo as _nuc

from modulo_codatacion import (
    _spline_cook,
    _residualizar_indice,
    _detrend_serie_indice,
    RIGIDEZ_SPLINE_DEFECTO,
)


# ---------------------------------------------------------------------------
# Estadísticos descriptivos de una serie
# ---------------------------------------------------------------------------

def sensibilidad_media(valores: np.ndarray) -> float:
    """Sensibilidad media (mean sensitivity) de Douglass.

    Media de las diferencias relativas entre anillos consecutivos:
        MS = (1/(n-1)) · Σ | 2·(xₜ₊₁ − xₜ) / (xₜ₊₁ + xₜ) |
    Mide cuánta variación año a año tiene la serie; valores altos indican
    una serie sensible al clima, que es la que sirve para cofechar.
    """
    v = np.asarray(valores, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 2:
        return float("nan")
    suma = v[1:] + v[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.abs(2.0 * (v[1:] - v[:-1]) / suma)
    d = d[np.isfinite(d)]
    return float(np.mean(d)) if d.size else float("nan")


def autocorrelacion_lag1(valores: np.ndarray) -> float:
    """Autocorrelación de primer orden."""
    v = np.asarray(valores, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 3:
        return float("nan")
    c = v - v.mean()
    if np.std(c) == 0:
        return float("nan")
    return float(np.corrcoef(c[1:], c[:-1])[0, 1])


def nivel_critico(n: int, alfa: float = 0.01) -> float:
    """Correlación mínima significativa para n años.

    COFECHA marca los segmentos cuya correlación con el maestro no alcanza
    este nivel. Se obtiene invirtiendo el estadístico t de Student:
        r_crit = t / √(t² + n − 2)
    """
    if n is None or n < 4:
        return float("nan")
    try:
        from scipy import stats
        t = stats.t.ppf(1.0 - alfa, n - 2)
    except Exception:
        t = 2.326  # aproximación normal al 99%
    return float(t / np.sqrt(t * t + n - 2))


# ---------------------------------------------------------------------------
# Estandarización de la colección
# ---------------------------------------------------------------------------

def estandarizar_serie(serie_mm: pd.Series,
                        rigidez_spline: int = RIGIDEZ_SPLINE_DEFECTO,
                        aplicar_log: bool = True,
                        aplicar_ar: bool = True,
                        max_orden_ar: int = 3):
    """Estandariza una serie como COFECHA y devuelve (índice, orden AR).

    Pasos: spline de Cook (quita la tendencia de crecimiento) → índice de
    razón → log opcional → modelo autorregresivo.
    """
    s = pd.to_numeric(serie_mm, errors="coerce").dropna().astype(float)
    if s.empty:
        return s, 0

    idx = _detrend_serie_indice(s, "spline", rigidez=rigidez_spline)
    if idx.empty:
        return idx, 0

    # ORDEN: spline -> índice -> AR -> logaritmo.
    #
    # Es el que describe el manual de la Dendrochronology Program Library
    # (Holmes 1994): (1) spline y división, (2) "la persistencia de la serie
    # suavizada se elimina por modelado autorregresivo", (3) "se toma el
    # logaritmo de cada valor tras sumar una constante de un sexto de la
    # media". DPI aplicaba el logaritmo ANTES del AR.
    #
    # La prueba que lo zanja es el ORDEN DEL MODELO AR, que es un entero y no
    # admite interpretación. Comparado con las 36 series de cos8.rwl contra la
    # corrida real de COFECHA:
    #
    #   AR sobre el índice (manual):  25 de 36 órdenes coinciden  (69 %)
    #   AR sobre el logaritmo:        19 de 36                    (53 %)
    #
    # Y en el archivo de dos series 88B.rwl, el orden sobre el índice acierta
    # los dos (2 y 1) mientras que sobre el logaritmo falla los dos (1 y 3).
    orden = 0
    if aplicar_ar:
        idx, orden = _residualizar_indice(idx, max_orden=max_orden_ar,
                                          devolver_orden=True)

    if aplicar_log:
        media = float(idx.mean())
        c = media / 6.0 if media > 0 else 1e-3
        idx = pd.Series(
            np.log(np.maximum(idx.to_numpy(dtype=float) + c, 1e-10)),
            index=idx.index)

    return idx, orden


def _biweight(mat: np.ndarray, c: float = 9.0) -> np.ndarray:
    """Media biweight robusta por filas (ignora NaN)."""
    n_años = mat.shape[0]
    out = np.full(n_años, np.nan)
    for i in range(n_años):
        fila = mat[i]
        fila = fila[np.isfinite(fila)]
        if fila.size == 0:
            continue
        if fila.size < 3:
            out[i] = float(np.mean(fila))
            continue
        m = float(np.median(fila))
        mad = float(np.median(np.abs(fila - m)))
        if mad <= 0:
            out[i] = float(np.mean(fila))
            continue
        u = (fila - m) / (c * mad)
        w = np.where(np.abs(u) < 1, (1 - u * u) ** 2, 0.0)
        if w.sum() <= 0:
            out[i] = m
        else:
            out[i] = float((w * fila).sum() / w.sum())
    return out


def construir_maestro(indices: dict[str, pd.Series],
                       excluir: str | None = None) -> pd.Series:
    """Maestro (cronología media) a partir de las series estandarizadas.

    `excluir` deja fuera una serie: es el leave-one-out de COFECHA, que evita
    que una serie se correlacione en parte consigo misma.
    """
    usar = {k: v for k, v in indices.items() if k != excluir and not v.empty}
    if not usar:
        return pd.Series(dtype=float)
    df = pd.DataFrame(usar)
    valores = _biweight(df.to_numpy(dtype=float))
    return pd.Series(valores, index=df.index).dropna()


# ---------------------------------------------------------------------------
# Correlaciones por segmento
# ---------------------------------------------------------------------------

def _r(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    r = float(np.corrcoef(a, b)[0, 1])
    return r if np.isfinite(r) else float("nan")


def grilla_segmentos(primer_anio: int, ultimo_anio: int,
                      largo_segmento: int = 30, avance: int = 15):
    """Grilla GLOBAL de segmentos de la colección.

    COFECHA no define los segmentos serie por serie: usa una sola grilla para
    toda la colección y después cada serie rellena las columnas que alcanza a
    cubrir. Por eso la tabla de la Parte 5 tiene encabezados de años comunes.

    El anclaje se verificó contra CLLCOF.OUT y QLHcof.out: los segmentos
    empiezan en años DIVISIBLES POR EL AVANCE (850, 875, 900… con avance 25),
    tal como dice el manual («intermediate segments will always begin on years
    evenly divisible by the lag value»). La versión anterior los anclaba al
    último año de la colección, así que la tabla no calzaba con la de COFECHA.
    """
    if primer_anio is None or ultimo_anio is None:
        return []
    largo = int(largo_segmento)
    paso = max(int(avance), 1)
    inicio = (int(primer_anio) // paso) * paso
    tramos = []
    while inicio <= int(ultimo_anio):
        tramos.append((int(inicio), int(inicio + largo - 1)))
        inicio += paso
    return tramos


def solape_minimo(largo_segmento: int, avance: int) -> int:
    """Años de solape que exige COFECHA para evaluar un segmento.

    Deducido de las salidas reales: con segmentos de 50 años y avance de 25,
    la separación entre segmentos evaluados y omitidos cae exactamente en 26
    (todos los solapes >= 26 aparecen con valor, todos los <= 25 quedan en
    blanco), en los dos archivos y sin una sola excepción. O sea, más de la
    mitad del segmento. Antes se usaba 0,6 del largo, que descartaba de más.
    """
    return max(int(avance), 1) + 1


def correlaciones_segmento(serie: pd.Series, maestro: pd.Series,
                            largo_segmento: int = 50, avance: int = 25,
                            max_desfase: int = 10, alfa: float = 0.01,
                            grilla: list | None = None):
    """Correlación de cada segmento con el maestro y su mejor desfase.

    Devuelve una lista de diccionarios, uno por segmento, con la correlación
    en la posición actual, el mejor desfase encontrado y su correlación, y la
    bandera correspondiente:
       "A" la correlación no alcanza el nivel crítico,
       "B" correlaciona mejor en otra posición que en la fechada.
    """
    if serie.empty or maestro.empty:
        return []

    ys = serie.index.to_numpy(np.int64)
    vs = serie.to_numpy(dtype=float)
    ym = maestro.index.to_numpy(np.int64)
    vm = maestro.to_numpy(dtype=float)

    ini, fin = int(ys.min()), int(ys.max())
    # Cobertura mínima para que una serie participe de un segmento.
    # Calibrado con COS3COF.OUT: COFECHA acepta un solape de 18 años en un
    # segmento de 30 (COS085B) pero descarta uno de 14 (COS140B).
    minimo = solape_minimo(largo_segmento, avance)
    if grilla is None:
        grilla = grilla_segmentos(ini, fin, largo_segmento, avance)
    segmentos = []
    for inicio, f_seg in grilla:
        # La serie solo participa de los segmentos que alcanza a cubrir
        m = (ys >= inicio) & (ys <= f_seg)
        if m.sum() >= minimo:
            res = {"inicio": int(inicio), "fin": int(f_seg)}
            rs = {}
            for sh in range(-max_desfase, max_desfase + 1):
                com, ia, ib = np.intersect1d(ys[m] + sh, ym,
                                             assume_unique=True,
                                             return_indices=True)
                if len(com) < minimo:
                    continue
                val = _r(vs[m][ia], vm[ib])
                if np.isfinite(val):
                    rs[sh] = (val, len(com))
            res["rs_por_desfase"] = {k: v[0] for k, v in rs.items()}
            if 0 in rs:
                r0, n0 = rs[0]
                res["r"] = r0
                res["n"] = n0
                crit = nivel_critico(n0, alfa)
                res["critico"] = crit
                mejor_sh = max(rs, key=lambda k: rs[k][0])
                res["mejor_desfase"] = int(mejor_sh)
                res["mejor_r"] = rs[mejor_sh][0]
                bandera = ""
                if mejor_sh != 0 and rs[mejor_sh][0] > r0:
                    bandera = "B"
                elif np.isfinite(crit) and r0 < crit:
                    bandera = "A"
                res["bandera"] = bandera
                segmentos.append(res)
    return segmentos


def aporte_por_anio(serie: pd.Series, maestro: pd.Series,
                     desde: int | None = None, hasta: int | None = None,
                     n_extremos: int = 4):
    """Cuánto sube o baja cada año la correlación con la maestra.

    Es la subsección [B] de COFECHA: se recalcula la correlación quitando un
    año a la vez; los años cuya ausencia SUBE la correlación son los que la
    estaban bajando (candidatos a error de medición o de fechado).
    Devuelve (lista_bajan, lista_suben, r_del_tramo).
    """
    com = serie.index.intersection(maestro.index)
    if desde is not None:
        com = com[(com >= desde) & (com <= hasta)]
    if len(com) < 5:
        return [], [], float("nan")
    a = serie.loc[com].to_numpy(dtype=float)
    b = maestro.loc[com].to_numpy(dtype=float)
    r_todo = _r(a, b)
    if not np.isfinite(r_todo):
        return [], [], float("nan")
    efectos = []
    for i in range(len(com)):
        m = np.ones(len(com), dtype=bool)
        m[i] = False
        r_sin = _r(a[m], b[m])
        if np.isfinite(r_sin):
            # efecto de INCLUIR ese año
            efectos.append((int(com[i]), r_todo - r_sin))
    efectos.sort(key=lambda t: t[1])
    bajan = efectos[:n_extremos]
    suben = list(reversed(efectos[-n_extremos:]))
    return bajan, suben, r_todo


def anillos_ausentes(serie_mm: pd.Series) -> list[int]:
    """Años con anillo ausente (valor cero)."""
    s = pd.to_numeric(serie_mm, errors="coerce")
    return [int(a) for a, v in s.items() if np.isfinite(v) and v == 0]


def valores_atipicos(serie_mm: pd.Series, todas: dict[str, pd.Series],
                      sd_alto: float = 3.0, sd_bajo: float = -4.5):
    """Años cuyo valor se aparta mucho de la media de ese año en la colección."""
    fuera = []
    for anio, val in pd.to_numeric(serie_mm, errors="coerce").items():
        if not np.isfinite(val):
            continue
        otros = [float(o.get(anio, np.nan)) for o in todas.values()]
        otros = [x for x in otros if np.isfinite(x)]
        if len(otros) < 4:
            continue
        m, sd = float(np.mean(otros)), float(np.std(otros))
        if sd <= 0:
            continue
        z = (float(val) - m) / sd
        if z >= sd_alto or z <= sd_bajo:
            fuera.append((int(anio), float(z)))
    return fuera


def cambios_divergentes(serie_mm: pd.Series, todas: dict[str, pd.Series],
                         umbral_sd: float = 4.0):
    """Cambios año a año muy distintos del cambio medio de las otras series.

    Es la subsección [C] de COFECHA. Para cada par de años consecutivos se
    calcula el cambio relativo de la serie y se compara con la distribución
    de ese mismo cambio en las demás series. Un cambio que se aparta muchas
    desviaciones típicas suele delatar un anillo mal medido, un falso anillo
    o un límite de anillo mal ubicado — y a diferencia de la correlación,
    señala el par de años exacto.
    """
    s = pd.to_numeric(serie_mm, errors="coerce").dropna()
    if len(s) < 3:
        return []

    def _cambio(x: pd.Series, a: int):
        """Cambio relativo entre el año a y el siguiente."""
        if a not in x.index or (a + 1) not in x.index:
            return np.nan
        v0, v1 = float(x.loc[a]), float(x.loc[a + 1])
        den = v0 + v1
        if den <= 0:
            return np.nan
        return 2.0 * (v1 - v0) / den

    fuera = []
    for a in s.index[:-1]:
        propio = _cambio(s, int(a))
        if not np.isfinite(propio):
            continue
        otros = []
        for nom, o in todas.items():
            if o is serie_mm:
                continue
            c = _cambio(pd.to_numeric(o, errors="coerce").dropna(), int(a))
            if np.isfinite(c):
                otros.append(c)
        if len(otros) < 4:
            continue
        m, sd = float(np.mean(otros)), float(np.std(otros))
        if sd <= 0:
            continue
        z = (propio - m) / sd
        if abs(z) >= umbral_sd:
            fuera.append((int(a), int(a) + 1, float(z)))
    return fuera


def _indices_segmento(anios: np.ndarray, ini_anio: int, fin_anio: int):
    """Convierte un tramo de años en posiciones [a, b) del arreglo alineado."""
    a = int(np.searchsorted(anios, ini_anio, side="left"))
    b = int(np.searchsorted(anios, fin_anio, side="right"))
    return a, b


def _pares_por_desfase(col: np.ndarray, maestro: np.ndarray,
                        max_desfase: int) -> dict:
    """Sumas acumuladas del par serie–maestro para cada desfase.

    Desplazar la serie `sh` años equivale a leer el maestro `sh` posiciones
    más adelante, porque el arreglo está alineado año a año sin huecos. Con
    las acumuladas listas, la correlación de cualquier segmento en cualquier
    desfase sale en tiempo constante.
    """
    n = col.size
    fuera = np.full(n, np.nan)
    acum = {}
    for sh in range(-max_desfase, max_desfase + 1):
        y = fuera.copy()
        if sh >= 0:
            if n - sh > 0:
                y[:n - sh] = maestro[sh:]
        else:
            y[-sh:] = maestro[:n + sh]
        acum[sh] = _nuc.AcumuladosPar(col, y)
    return acum


def _maestro_desplazado(maestro: np.ndarray, sh: int) -> np.ndarray:
    n = maestro.size
    y = np.full(n, np.nan)
    if sh >= 0:
        if n - sh > 0:
            y[:n - sh] = maestro[sh:]
    else:
        y[-sh:] = maestro[:n + sh]
    return y


def analizar_coleccion(series_mm: dict,
                        largo_segmento: int = 50, avance: int = 25,
                        rigidez_spline: int = RIGIDEZ_SPLINE_DEFECTO,
                        aplicar_log: bool = True, aplicar_ar: bool = True,
                        max_orden_ar: int = 3, max_desfase: int = 10,
                        alfa: float = 0.01, maestro_robusto: bool = False,
                        progreso=None, cancelado=None) -> dict:
    """Analiza una colección completa al estilo COFECHA.

    `series_mm` es {nombre: Series de anchos en mm indexada por año}.

    `progreso(fraccion, texto)` se llama de tanto en tanto para que la
    interfaz pueda mostrar avance; `cancelado()` se consulta para abortar.
    Ambos son opcionales.

    Todo el trabajo pesado ocurre sobre matrices alineadas (ver
    `modulo_cofecha_nucleo`): la versión anterior recorría las series con
    bucles de Python anidados y escalaba de forma cuadrática, hasta el punto
    de colgarse con colecciones de tamaño normal.
    """
    if not series_mm:
        raise ValueError("No hay series para analizar.")

    def _avisar(f, txt):
        if progreso is not None:
            progreso(float(f), txt)

    def _abortado():
        return bool(cancelado()) if cancelado is not None else False

    # ── 1) Estandarizar cada serie ─────────────────────────────────────
    _avisar(0.0, "Estandarizando series…")
    # DOS estandarizaciones, no una.
    #
    # Verificado guardando la serie maestra de COFECHA (opción 6) en dos
    # corridas idénticas salvo la opción 3, una con modelo autorregresivo y
    # otra sin él: los dos archivos .MAS salen IDÉNTICOS byte a byte, mientras
    # que la columna "Corr with Master" y los estadísticos filtrados sí
    # cambian entre corridas.
    #
    # O sea que COFECHA aplica el AR a la serie que pone a prueba, pero NO a
    # la maestra contra la que la compara, aunque su propia opción 3 diga
    # "Residuals are used in master dating series and testing". DPI aplicaba
    # el AR a las dos, y por eso su maestra correlacionaba 0,88 con la de
    # COFECHA en vez de 0,94.
    indices, ordenes, crudas = {}, {}, {}
    indices_maestro = {}
    filtradas = {}
    total = len(series_mm)
    for k, (nombre, s) in enumerate(series_mm.items()):
        if _abortado():
            raise InterruptedError("Análisis cancelado.")
        cruda = pd.to_numeric(s, errors="coerce").dropna().astype(float)
        if cruda.empty:
            continue
        idx, p = estandarizar_serie(
            cruda, rigidez_spline=rigidez_spline, aplicar_log=aplicar_log,
            aplicar_ar=aplicar_ar, max_orden_ar=max_orden_ar)
        if idx.empty:
            continue
        crudas[nombre] = cruda
        indices[nombre] = idx
        ordenes[nombre] = int(p)
        # Serie "filtrada" PARA INFORMAR, en escala de índice (media 1).
        # COFECHA reporta en la Parte 7 un máximo cercano a 2 y una desviación
        # cercana a 0,4, cifras propias del índice de razón; DPI las sacaba de
        # la serie logarítmica, que vive en otra escala (máximo ~1,6), así que
        # las dos últimas columnas nunca podían coincidir.
        try:
            idx_r = _detrend_serie_indice(cruda, "spline",
                                          rigidez=rigidez_spline)
            if aplicar_ar and not idx_r.empty:
                idx_r, _o = _residualizar_indice(
                    idx_r, max_orden=max_orden_ar, devolver_orden=True)
            filtradas[nombre] = idx_r
        except Exception:
            filtradas[nombre] = idx
        if aplicar_ar:
            idx_m, _ = estandarizar_serie(
                cruda, rigidez_spline=rigidez_spline, aplicar_log=aplicar_log,
                aplicar_ar=False, max_orden_ar=max_orden_ar)
            if not idx_m.empty:
                indices_maestro[nombre] = idx_m
        else:
            indices_maestro[nombre] = idx
        if k % 25 == 0:
            _avisar(0.35 * k / max(total, 1), "Estandarizando series…")

    if not indices:
        raise ValueError("Ninguna serie pudo estandarizarse.")

    nombres = [n for n in series_mm if n in indices]

    # ── 2) Matrices alineadas ──────────────────────────────────────────
    _avisar(0.36, "Alineando la colección…")
    M_cruda = _nuc.Matriz.desde_series({n: crudas[n] for n in nombres})
    M_idx = _nuc.Matriz.desde_series({n: indices[n] for n in nombres})
    anios_idx = M_idx.anios

    # La maestra se construye sobre la MISMA grilla de años que las series de
    # prueba, para que un desfase de k años sea k posiciones en los dos
    # arreglos.
    mas_alineado = np.full(M_idx.valores.shape, np.nan)
    for j, n in enumerate(nombres):
        sm = indices_maestro.get(n)
        if sm is None or sm.empty:
            continue
        pos = np.asarray(sm.index, dtype=np.int64) - int(anios_idx[0])
        v = sm.to_numpy(dtype=float)
        ok = (pos >= 0) & (pos < anios_idx.size) & np.isfinite(v)
        mas_alineado[pos[ok], j] = v[ok]

    # DOS maestras, y la distinción es la clave de la compatibilidad.
    #
    # `maestro_obj` (con AR) es la que se usa para CORRELACIONAR.
    # `maestro_pub` (sin AR) es la que se muestra en las Partes 3 y 4 y la que
    # equivale al archivo que COFECHA guarda con su opción 6.
    #
    # Durante mucho tiempo dedujimos que la maestra no llevaba AR, porque dos
    # corridas de COFECHA que solo diferían en la opción 3 producían archivos
    # .MAS IDÉNTICOS byte a byte, y porque esa maestra tiene autocorrelación
    # +0,40. Las dos observaciones son ciertas — pero se refieren al archivo
    # GUARDADO, no a la maestra interna.
    #
    # La prueba está en las correlaciones de la Parte 7. Sobre 274 series de
    # tres colecciones, comparando contra las corridas reales:
    #
    #     serie con AR vs maestra SIN AR   sesgo -0.0353   error 0.0410
    #     serie con AR vs maestra CON AR   sesgo +0.0043   error 0.0182
    #
    # El error cae a menos de la mitad y el sesgo sistemático desaparece. Así
    # que COFECHA guarda la maestra antes de blanquear, pero correlaciona
    # contra la blanqueada.
    maestro_obj = _nuc.Maestro(M_idx.valores, robusto=maestro_robusto)
    maestro_pub = _nuc.Maestro(mas_alineado, robusto=maestro_robusto)

    # ── 3) Diagnósticos de colección, de una sola vez ──────────────────
    _avisar(0.42, "Buscando valores atípicos…")
    Z_atip = _nuc.z_leave_one_out(M_cruda.valores)
    _avisar(0.48, "Buscando cambios divergentes…")
    Z_camb = _nuc.z_leave_one_out(_nuc.matriz_cambios(M_cruda.valores))

    # Grilla global de segmentos, común a toda la colección
    grilla = grilla_segmentos(int(M_cruda.anios[0]), int(M_cruda.anios[-1]),
                              largo_segmento, avance)
    tramos_idx = [(_indices_segmento(anios_idx, a, b), (a, b))
                  for a, b in grilla]
    minimo = solape_minimo(largo_segmento, avance)
    desfases = list(range(-max_desfase, max_desfase + 1))

    resultados = []
    for j, nombre in enumerate(nombres):
        if _abortado():
            raise InterruptedError("Análisis cancelado.")
        if j % 10 == 0:
            _avisar(0.5 + 0.45 * j / max(len(nombres), 1),
                    f"Correlacionando ({j + 1}/{len(nombres)})…")

        col = M_idx.valores[:, j]
        maestro = maestro_obj.excluyendo(j)
        acum = _pares_por_desfase(col, maestro, max_desfase)

        # Correlación de la serie completa con su maestro
        hay = np.isfinite(col)
        pos = np.flatnonzero(hay)
        a_ser, b_ser = int(pos[0]), int(pos[-1]) + 1
        r_maestro, _n_tot = acum[0].r(a_ser, b_ser)

        # ── Segmentos ───────────────────────────────────────────────
        segs = []
        for (a, b), (anio_ini, anio_fin) in tramos_idx:
            if b - a <= 0 or hay[a:b].sum() < minimo:
                continue
            r0, n0 = acum[0].r(a, b)
            if not np.isfinite(r0):
                continue
            rs = {}
            for sh in desfases:
                rv, nv = acum[sh].r(a, b)
                if np.isfinite(rv) and nv >= minimo:
                    rs[sh] = rv
            if 0 not in rs:
                continue
            crit = nivel_critico(n0, alfa)
            mejor_sh = max(rs, key=lambda k: rs[k])
            bandera = ""
            if mejor_sh != 0 and rs[mejor_sh] > rs[0]:
                bandera = "B"
            elif np.isfinite(crit) and rs[0] < crit:
                bandera = "A"
            segs.append({
                "inicio": int(anio_ini), "fin": int(anio_fin),
                "r": float(rs[0]), "n": int(n0), "critico": float(crit),
                "mejor_desfase": int(mejor_sh),
                "mejor_r": float(rs[mejor_sh]),
                "rs_por_desfase": rs, "bandera": bandera,
            })

        # ── [B] efecto de cada año sobre la correlación ─────────────
        y0 = _maestro_desplazado(maestro, 0)
        p_g, ef_g, r_g = _nuc.r_quitando_cada_punto(col, y0)
        b_global = _extremos(anios_idx, p_g, ef_g)
        b_segmentos = []
        for sg in segs:
            if not sg.get("bandera"):
                continue
            a, b = _indices_segmento(anios_idx, sg["inicio"], sg["fin"])
            ps, es, rs_ = _nuc.r_quitando_cada_punto(col[a:b], y0[a:b])
            bj, sb = _extremos(anios_idx[a:b], ps, es)
            b_segmentos.append({"inicio": sg["inicio"], "fin": sg["fin"],
                                "bajan": bj, "suben": sb, "r": rs_})

        # ── Correlación con la maestra ──────────────────────────────
        # COFECHA informa en la Parte 7 la MEDIA DE LAS CORRELACIONES POR
        # SEGMENTO, no una correlación global sobre todo el solape. DPI
        # informaba la global, y la diferencia no es cosmética: llegaba a 0,13
        # en algunas series, magnitud que decide si una serie entra o no a la
        # cronología.
        #
        # Medido sobre las 36 series de cos8.rwl contra la corrida real:
        #
        #                              err medio   err máx   sesgo
        #   r global (lo anterior)       0.0519     0.131    +0.0136
        #   media de los segmentos       0.0386     0.115    +0.0009
        #   media z ponderada por n      0.0399     0.147    +0.0096
        #
        # La media simple de los segmentos no solo ajusta mejor: elimina el
        # sesgo, que era la señal de que se estaba calculando otra cosa.
        # También se probó añadir los segmentos anclados al primer y último
        # año de cada serie, como sugiere el manual, y empeora (0.0405).
        rs_seg = [x["r"] for x in segs if np.isfinite(x["r"])]
        r_segmentos = float(np.mean(rs_seg)) if rs_seg else r_maestro

        # ── Estadísticos descriptivos ───────────────────────────────
        cruda = crudas[nombre]
        v_cruda = cruda.to_numpy(dtype=float)
        f_rep = filtradas.get(nombre)
        v_filt = (f_rep.to_numpy(dtype=float) if f_rep is not None
                  and not f_rep.empty else col[hay])
        jc = M_cruda.indice_nombre[nombre]
        col_cruda = M_cruda.valores[:, jc]
        anios_c = M_cruda.anios

        ausentes = [int(a) for a in anios_c[col_cruda == 0]]
        za = Z_atip[:, jc]
        sel_a = np.isfinite(za) & ((za >= 3.0) | (za <= -4.5))
        atipicos = [(int(a), float(z))
                    for a, z in zip(anios_c[sel_a], za[sel_a])]
        zc = Z_camb[:, jc]
        sel_c = np.isfinite(zc) & (np.abs(zc) >= 4.0)
        divergentes = [(int(a), int(a) + 1, float(z))
                       for a, z in zip(anios_c[:-1][sel_c], zc[sel_c])]

        resultados.append({
            "nombre": nombre,
            "primer_anio": int(cruda.index.min()),
            "ultimo_anio": int(cruda.index.max()),
            "n_anios": int(len(cruda)),
            "n_segmentos": len(segs),
            "n_banderas": sum(1 for s in segs if s.get("bandera")),
            "r_maestro": r_segmentos,
            "r_global": r_maestro,
            "media_cruda": float(np.mean(v_cruda)),
            "max_cruda": float(np.max(v_cruda)),
            "min_cruda": float(np.min(v_cruda)),
            "sd_cruda": float(np.std(v_cruda, ddof=1)) if v_cruda.size > 1 else float("nan"),
            "autocorr_cruda": autocorrelacion_lag1(v_cruda),
            "sensibilidad": sensibilidad_media(v_cruda),
            "max_filt": float(np.max(v_filt)) if v_filt.size else float("nan"),
            "sd_filt": float(np.std(v_filt, ddof=1)) if v_filt.size > 1 else float("nan"),
            "autocorr_filt": autocorrelacion_lag1(v_filt),
            "orden_ar": ordenes.get(nombre, 0),
            "segmentos": segs,
            "aporte_global": {"bajan": b_global[0], "suben": b_global[1],
                              "r": r_g},
            "aporte_segmentos": b_segmentos,
            "ausentes": ausentes,
            "atipicos": atipicos,
            "divergentes": divergentes,
        })

    _avisar(0.97, "Armando el resumen…")
    # NO se reordenan las series. COFECHA respeta el orden del archivo, y el
    # usuario cuenta con eso: al depurar una serie se la pone al principio
    # del .rwl para encontrarla siempre en la misma posición del informe.
    # Ordenar alfabéticamente rompía ese flujo de trabajo.

    # La maestra que se publica es la SIN AR, que es la que guarda COFECHA
    maestro_total = pd.Series(maestro_pub.valores, index=anios_idx).dropna()
    prof = pd.Series(np.isfinite(mas_alineado).sum(axis=1), index=anios_idx)
    anios = [r["primer_anio"] for r in resultados] + \
            [r["ultimo_anio"] for r in resultados]
    rs_tot = [r["r_maestro"] for r in resultados if np.isfinite(r["r_maestro"])]
    sens = [r["sensibilidad"] for r in resultados
            if np.isfinite(r["sensibilidad"])]

    # Tramo con dos o más series: lo informa la portada de COFECHA
    con_dos = anios_idx[prof.to_numpy() >= 2]
    ausentes_totales = sum(len(r["ausentes"]) for r in resultados)
    total_anillos = int(sum(r["n_anios"] for r in resultados))
    # "Anillos comprobados" no es lo mismo que "anillos totales": un anillo
    # solo puede comprobarse si hay al menos otra serie que cubra ese año
    # (contra sí misma no se compara). COFECHA informa las dos cifras y antes
    # DPI repetía la misma en ambas.
    prof_arr = np.isfinite(mas_alineado).sum(axis=1)
    comprobables = int(np.isfinite(mas_alineado)[prof_arr >= 2].sum())

    _avisar(1.0, "Listo.")
    return {
        "series": resultados,
        "grilla": grilla,
        "critico_nominal": nivel_critico(largo_segmento, alfa),
        "indices": indices,
        "maestro": maestro_total,
        "profundidad": prof,
        "n_series": len(resultados),
        "primer_anio": min(anios) if anios else None,
        "ultimo_anio": max(anios) if anios else None,
        "primer_anio_dos": int(con_dos[0]) if con_dos.size else None,
        "ultimo_anio_dos": int(con_dos[-1]) if con_dos.size else None,
        "total_anillos": total_anillos,
        "total_comprobados": comprobables,
        "total_banderas": int(sum(r["n_banderas"] for r in resultados)),
        "total_ausentes": ausentes_totales,
        "intercorrelacion": float(np.mean(rs_tot)) if rs_tot else float("nan"),
        "sensibilidad_media": float(np.mean(sens)) if sens else float("nan"),
        "opciones": {
            "largo_segmento": largo_segmento,
            "avance": avance,
            "rigidez_spline": rigidez_spline,
            "aplicar_log": aplicar_log,
            "aplicar_ar": aplicar_ar,
            "max_orden_ar": max_orden_ar,
            "max_desfase": max_desfase,
            "maestro_robusto": maestro_robusto,
            "alfa": alfa,
        },
    }


def _extremos(anios: np.ndarray, posiciones: np.ndarray,
               efectos: np.ndarray, n_extremos: int = 4):
    """Los n años que más bajan y los que más suben la correlación."""
    if posiciones.size == 0:
        return [], []
    orden = np.argsort(efectos)
    bajan = [(int(anios[posiciones[i]]), float(efectos[i]))
             for i in orden[:n_extremos]]
    suben = [(int(anios[posiciones[i]]), float(efectos[i]))
             for i in orden[::-1][:n_extremos]]
    return bajan, suben
