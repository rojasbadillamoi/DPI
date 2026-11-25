"""Estadística dendrocronológica común, sin dependencias de Qt."""
import numpy as np
import pandas as pd
from dpi.ciencia.constantes import OVERLAP_MINIMO_GRAFICO
from dpi.ciencia.codigos import clave_codigo_dendro


BIWEIGHT_C = 9.0


def media_biweight(valores, c: float = BIWEIGHT_C, minimo: int = 6, *, axis=None):
    """Media biponderada de Tukey, escalar o vectorizada por un eje.

    Excluye NaN e infinitos. Sin observaciones devuelve NaN; con menos de
    seis (por defecto), MAD nula o sin pesos válidos devuelve la mediana.
    Usa C=9, escala C*MAD + 1e-6 y corte inclusivo, como en tbrm de dplR.
    El umbral de seis conserva la regla de cronología validada con ARSTAN.
    Con axis=None devuelve float; con un eje, un ndarray de resultados.
    """
    x = np.asarray(valores, dtype=float)
    if not np.isfinite(c) or c <= 0:
        raise ValueError("La constante biweight debe ser positiva y finita")
    minimo = max(int(minimo), 1)
    if axis is None:
        filas = x.reshape(1, x.size)
        forma = ()
    else:
        x = np.moveaxis(x, axis, -1)
        forma = x.shape[:-1]
        filas = x.reshape(int(np.prod(forma, dtype=np.intp)), x.shape[-1])

    finito = np.isfinite(filas)
    conteo = finito.sum(axis=1)
    seguro = np.where(finito, filas, np.nan)
    resultado = np.full(len(filas), np.nan)
    hay = conteo > 0
    if hay.any():
        resultado[hay] = np.nanmedian(seguro[hay], axis=1)

    candidatos = np.flatnonzero(conteo >= minimo)
    if candidatos.size:
        datos = seguro[candidatos]
        mediana = resultado[candidatos]
        with np.errstate(over="ignore", invalid="ignore"):
            mad = np.nanmedian(np.abs(datos - mediana[:, None]), axis=1)
            escala = c * mad + 1e-6
        usable = (mad > 0) & np.isfinite(escala) & (escala > 0)
        indices = candidatos[usable]
        if indices.size:
            datos = datos[usable]
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                u = (datos - mediana[usable, None]) / escala[usable, None]
                u = np.where(np.abs(u) <= 1, u, np.nan)
                pesos = np.where(np.isfinite(u), (1 - u * u) ** 2, 0.0)
                suma = pesos.sum(axis=1)
                numerador = (pesos * np.where(np.isfinite(datos), datos, 0.0)).sum(axis=1)
                media = numerador / suma
            validos = (suma > 0) & np.isfinite(media)
            resultado[indices[validos]] = media[validos]

    if axis is None:
        return float(resultado[0])
    return resultado.reshape(forma)


def centrar_escalar_correlacion(x):
    """Traslación y escala positivas comunes; conserva los no finitos como NaN."""
    x = np.asarray(x, dtype=float)
    valido = np.isfinite(x)
    z = np.full(x.shape, np.nan)
    if not valido.any():
        return z, 1.0, 1.0
    v = x[valido]
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        d = v - v[0]
        escala_previa = 1.0
        if not np.isfinite(d).all():
            escala_previa = float(np.max(np.abs(v)))
            v = v / escala_previa
            d = v - v[0]
        escala = float(np.max(np.abs(d))) or 1.0
        z[valido] = d / escala
    return z, escala_previa, escala


def pearson(a, b, *, tolerancia=0.0):
    """Pearson sobre pares alineados; NaN si no es calculable.

    La tolerancia se expresa en unidades originales (desviación poblacional).
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or a.size < 2:
        return float("nan")
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        return float("nan")
    a, pa, ea = centrar_escalar_correlacion(a)
    b, pb, eb = centrar_escalar_correlacion(b)
    a -= a.mean()
    b -= b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return float("nan")
    if tolerancia > 0:
        with np.errstate(over="ignore", under="ignore"):
            sa = (na / np.sqrt(a.size) * ea) * pa
            sb = (nb / np.sqrt(b.size) * eb) * pb
        if sa < tolerancia or sb < tolerancia:
            return float("nan")
    r = float(np.dot(a / na, b / nb))
    return float(np.clip(r, -1.0, 1.0)) if np.isfinite(r) else float("nan")


def pearson_desde_sumas(n, sx, sy, sxx, syy, sxy):
    """Pearson escalar o vectorizado a partir de momentos comunes.

    No recupera precisión perdida en los momentos de entrada. Devuelve NaN
    si no hay varianza positiva o el resultado es numéricamente inconsistente.
    """
    if all(np.isscalar(v) for v in (n, sx, sy, sxx, syy, sxy)):
        import math
        if n < 2:
            return float("nan")
        vx = sxx - sx * (sx / n)
        vy = syy - sy * (sy / n)
        if not (vx > 0 and vy > 0):
            return float("nan")
        r = ((sxy - sx * (sy / n)) / math.sqrt(vx)) / math.sqrt(vy)
        if not math.isfinite(r) or abs(r) > 1 + 1e-8:
            return float("nan")
        return max(-1.0, min(1.0, r))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        vx = sxx - sx * (sx / n)
        vy = syy - sy * (sy / n)
        r = ((sxy - sx * (sy / n)) / np.sqrt(vx)) / np.sqrt(vy)
    valido = (n >= 2) & (vx > 0) & (vy > 0) & np.isfinite(r) & (np.abs(r) <= 1 + 1e-8)
    return np.where(valido, np.clip(r, -1.0, 1.0), np.nan)


def serie_anual(serie):
    """Serie numérica ordenada, con años únicos y observaciones finitas."""
    s = pd.to_numeric(serie, errors="coerce").astype(float).sort_index()
    if not s.index.is_unique:
        raise ValueError("La serie contiene años duplicados.")
    return s[np.isfinite(s)]


def diferencias_anuales(serie):
    """Diferencias únicamente entre años consecutivos, indexadas por año final."""
    s = serie_anual(serie)
    return s.diff().iloc[1:][np.diff(s.index.to_numpy()) == 1].dropna()


def diferencias_log_anuales(serie, *, piso=None):
    s = serie_anual(serie)
    s = s[s > 0] if piso is None else s.clip(lower=piso)
    return diferencias_anuales(np.log(s))


def _pares_anuales(a, b, anios=None):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("Las observaciones deben estar alineadas.")
    valido = np.isfinite(a) & np.isfinite(b)
    pares = valido[:-1] & valido[1:]
    if anios is not None:
        anios = np.asarray(anios)
        if anios.shape != a.shape:
            raise ValueError("Los años deben estar alineados.")
        pares &= np.diff(anios) == 1
    return a, b, pares


def _glk_con_n(a, b, min_overlap=10, *, anios=None):
    a, b, pares = _pares_anuales(a, b, anios)
    n = int(pares.sum())
    # Mantener el umbral histórico para series continuas: N años, N-1 cambios.
    if n < max(1, min_overlap - 1):
        return float("nan"), n
    da, db = np.sign(np.diff(a)[pares]), np.sign(np.diff(b)[pares])
    return float(1.0 - np.mean(np.abs(da - db)) / 2.0), n


def glk_alineado(a, b, min_overlap=10, *, anios=None):
    """GLK; sin años explícitos se presupone una grilla anual continua."""
    return _glk_con_n(a, b, min_overlap, anios=anios)[0]


def t_desde_r(r, n):
    """Conserva la convención histórica de DPI para correlaciones perfectas."""
    if n < 3 or not np.isfinite(r) or abs(r) >= 1.0:
        return float("nan")
    return float(r * np.sqrt(n - 2) / np.sqrt(1.0 - r * r))


def tbp_filtrado(a, b, min_overlap=20):
    """t-BP y r a partir de diferencias logarítmicas ya alineadas."""
    n = len(a)
    if n < min_overlap:
        return float("nan"), float("nan"), n
    r = pearson(a, b)
    return t_desde_r(r, n), r, n


def tbp_alineado(a, b, min_overlap=20, *, anios=None):
    a, b, pares = _pares_anuales(a, b, anios)
    positivos = (a > 0) & (b > 0)
    pares &= positivos[:-1] & positivos[1:]
    ha = 100.0 * (np.log(a[1:][pares]) - np.log(a[:-1][pares]))
    hb = 100.0 * (np.log(b[1:][pares]) - np.log(b[:-1][pares]))
    return tbp_filtrado(ha, hb, min_overlap)[0]


def sensibilidad_media(valores: np.ndarray, anios=None) -> float:
    """Sensibilidad media (mean sensitivity) de Douglass.

    Media de las diferencias relativas entre anillos consecutivos:
        MS = (1/(n-1)) · Σ | 2·(xₜ₊₁ − xₜ) / (xₜ₊₁ + xₜ) |
    Mide cuánta variación año a año tiene la serie; valores altos indican
    una serie sensible al clima, que es la que sirve para cofechar.
    """
    v = np.asarray(valores, dtype=float)
    if anios is None:
        anios = np.arange(len(v))
    _, _, pares = _pares_anuales(v, v, anios)
    if v.size < 2:
        return float("nan")
    suma = v[1:] + v[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.abs(2.0 * (v[1:] - v[:-1]) / suma)
    d = d[pares & np.isfinite(d)]
    return float(np.mean(d)) if d.size else float("nan")


def _sensibilidad_media(x, anios=None):
    """Adaptador histórico; usar sensibilidad_media en código nuevo."""
    return sensibilidad_media(x, anios)


def autocorrelacion_lag1(valores: np.ndarray, anios=None) -> float:
    """Pearson entre pares de años consecutivos y finitos."""
    v = np.asarray(valores, dtype=float)
    _, _, pares = _pares_anuales(v, v, anios)
    return pearson(v[:-1][pares], v[1:][pares])


def _autocorrelacion_ar1(x, anios=None):
    """Adaptador histórico; usar autocorrelacion_lag1 en código nuevo."""
    return autocorrelacion_lag1(x, anios)


def gleichlaufigkeit(serie_a, serie_b, min_overlap: int = 10):
    """GLK (Eckstein & Bauch 1969): proporción de años con cambio en la misma dirección."""
    a, b = serie_anual(serie_a), serie_anual(serie_b)
    overlap = a.index.intersection(b.index).sort_values()
    return _glk_con_n(a.loc[overlap], b.loc[overlap], min_overlap,
                      anios=overlap.to_numpy())


def glk_significance(glk: float, n: int) -> str:
    """Significancia GLK (Jansma 1995): aproximación binomial."""
    if not np.isfinite(glk) or n < 30:
        return "ns"
    z = (glk - 0.5) * 2 * np.sqrt(n)
    if z >= 3.29: return "***"
    if z >= 2.58: return "**"
    if z >= 1.96: return "*"
    return "ns"


def _filtro_hollstein(serie):
    """Filtro de Hollstein: 100 × primera diferencia logarítmica."""
    return diferencias_log_anuales(serie) * 100.0


def t_baillie_pilcher(serie_a, serie_b, min_overlap: int = 20):
    """t de Baillie-Pilcher: Hollstein → Pearson r → t-statistic."""
    a_filt = _filtro_hollstein(serie_a)
    b_filt = _filtro_hollstein(serie_b)
    overlap = a_filt.index.intersection(b_filt.index)
    n = len(overlap)
    if n < min_overlap:
        return float("nan"), float("nan"), n

    a = a_filt.loc[overlap].to_numpy(dtype=float)
    b = b_filt.loc[overlap].to_numpy(dtype=float)
    return tbp_filtrado(a, b, min_overlap)


def estadisticos_cofechado(serie_a, serie_b, min_overlap: int = 20) -> dict:
    """r + GLK + t-BP simultáneos."""
    a = pd.to_numeric(serie_a, errors="coerce").dropna()
    b = pd.to_numeric(serie_b, errors="coerce").dropna()
    overlap = a.index.intersection(b.index)
    n = len(overlap)

    resultado = {
        "r": float("nan"), "n": n,
        "glk": float("nan"), "glk_sig": "ns",
        "t_bp": float("nan"), "r_filt": float("nan"),
    }

    if n < min_overlap:
        return resultado

    a_ov = a.loc[overlap].to_numpy(dtype=float)
    b_ov = b.loc[overlap].to_numpy(dtype=float)
    resultado["r"] = pearson(a_ov, b_ov)

    glk, n_glk = gleichlaufigkeit(serie_a, serie_b, min_overlap)
    resultado["glk"] = glk
    resultado["glk_sig"] = glk_significance(glk, n_glk)

    t_bp, r_filt, _ = t_baillie_pilcher(serie_a, serie_b, min_overlap)
    resultado["t_bp"] = t_bp
    resultado["r_filt"] = r_filt

    return resultado


def calcular_eps_rbar_movil(series_dict, nombres, window=15, paso=1, progreso=None):
    """EPS y Rbar móvil — versión numpy directa."""
    cols = []
    for n in nombres:
        if n in series_dict:
            s = series_dict[n]["Ancho_mm"].dropna()
            s.name = n
            cols.append(s)
    if len(cols) < 2:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    df = pd.concat(cols, axis=1).sort_index()
    n_series = df.shape[1]
    years = df.index.to_numpy()
    half = window // 2
    data = df.to_numpy(dtype=float)
    n_years = len(data)

    if n_years < window:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    indices = list(range(half, n_years - half, paso))
    total = len(indices)
    resultados = []
    min_per = 10

    for k, i in enumerate(indices):
        win = data[i - half: i + half + 1]

        # Rbar vectorizado. Antes se recorrían TODOS los pares de series en
        # bucles de Python (con 169 series son 14.196 pares por ventana, cada
        # uno con su np.corrcoef): era el cuello de botella al generar
        # cronologías grandes. Ahora se calcula la matriz de correlaciones de
        # una sola vez con álgebra matricial, respetando los NaN (cada par usa
        # solo los años en que ambas series tienen dato) y el mínimo de
        # solape `min_per`.
        rs = correlaciones_pares(win, min_per)

        if rs.size:
            rbar = float(np.mean(rs))
            # Profundidad de muestreo PROMEDIO en la ventana: número medio
            # de series con dato válido por año. ARSTAN usa esto (su columna
            # "cores") en la fórmula de EPS, NO el total de series. Usar el
            # total sobreestimaría el EPS en ventanas donde no todas las
            # series están presentes. Esto es clave para que el EPS coincida
            # con ARSTAN.
            sample_depth = np.isfinite(win).sum(axis=1)
            n_eff = float(sample_depth[sample_depth > 0].mean()) \
                if (sample_depth > 0).any() else float(n_series)
            # Fórmula de Wigley et al. (1984): EPS = N·r̄ / (1 + (N−1)·r̄)
            eps = calcular_eps(rbar, n_eff)
            resultados.append((years[i], rbar, float(eps)))

        if progreso is not None and total > 0 and (k % 10 == 0 or k == total - 1):
            progreso(int(100 * (k + 1) / total))

    if not resultados:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    return pd.DataFrame(resultados, columns=["Anio", "Rbar", "EPS"]).set_index("Anio")


def calcular_rbar(series_dict, nombres):
    series = [series_dict[n]["Ancho_mm"].dropna() for n in nombres if n in series_dict]
    if len(series) < 2:
        return np.nan
    mat = pd.concat(series, axis=1).to_numpy(dtype=float)
    rs = correlaciones_pares(mat, min_overlap=10)
    return float(np.mean(rs)) if rs.size else np.nan


def calcular_eps(rbar, n):
    """EPS con profundidad efectiva (puede ser fraccionaria)."""
    if not np.isfinite(n) or n <= 1 or not np.isfinite(rbar):
        return np.nan
    den = 1 + (n - 1) * rbar
    if den == 0:
        return np.nan
    return (n * rbar) / den


def calcular_sss(n_por_anio, n_total, rbar):
    """Subsample Signal Strength: cuánta señal conserva cada año.

        SSS = n·(1 + (N−1)·rbar) / (N·(1 + (n−1)·rbar))

    donde `n` son las series de ese año y `N` el total de la colección.
    Fórmula de dplR (sss.R).

    POR QUÉ ADEMÁS DE LA EPS
    -----------------------
    Las dos responden preguntas distintas y se confunden seguido.

    La EPS compara la cronología contra una POBLACIÓN INFINITA de árboles:
    dice qué fracción de la varianza sería señal si se hubiera muestreado
    todo el rodal. Es una pregunta teórica.

    La SSS compara cada año contra la COLECCIÓN QUE REALMENTE TIENES: dice
    qué fracción de la señal de tu propia cronología conserva el tramo con
    menos series. Es la pregunta práctica cuando hay que decidir desde qué
    año usar la cronología, porque no depende de suponer nada sobre árboles
    que no se muestrearon.

    En el tramo con todas las series la SSS vale 1 por construcción, y va
    bajando hacia el pasado a medida que la profundidad cae. El umbral de uso
    habitual es el mismo 0,85 de la EPS.
    """
    n = np.asarray(n_por_anio, dtype=float)
    N = float(n_total)
    if not np.isfinite(rbar) or N <= 1:
        return np.full(n.shape, np.nan)
    num = n * (1.0 + (N - 1.0) * rbar)
    den = N * (1.0 + (n - 1.0) * rbar)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where((n >= 1) & (den > 0), num / den, np.nan)
    return out


def correlacion_por_desfase(serie_a: pd.Series, serie_b: pd.Series,
                              max_shift: int, min_overlap: int = 10
                              ) -> tuple[list[int], list[float]]:
    shifts, rs = [], []
    for shift in range(-max_shift, max_shift + 1):
        shifted = serie_a.copy()
        shifted.index = shifted.index + shift
        overlap = shifted.index.intersection(serie_b.index)
        if len(overlap) < min_overlap:
            continue
        a = shifted.loc[overlap].to_numpy(dtype=float)
        b = serie_b.loc[overlap].to_numpy(dtype=float)
        r = pearson(a, b)
        if np.isfinite(r):
            shifts.append(shift)
            rs.append(r)
    return shifts, rs


def estadisticos_por_desfase(
    serie_a: pd.Series, serie_b: pd.Series,
    max_shift: int, min_overlap: int = 10,
    serie_a_raw: pd.Series | None = None,
    serie_b_raw: pd.Series | None = None,
) -> tuple[list[int], list[float], list[float], list[float], list[int]]:
    """Calcula r, GLK y t-BP en cada desplazamiento (shift).

    IMPORTANTE — consistencia de transformaciones:
      - `serie_a`/`serie_b` deben venir en la transformación de ALTA
        FRECUENCIA usada para correlacionar (típicamente diferencias
        logarítmicas). El r de Pearson se calcula sobre estas.
      - `serie_a_raw`/`serie_b_raw` (opcionales) son las series CRUDAS.
        Si se pasan, GLK y t-BP se calculan sobre ellas, porque esas
        funciones diferencian internamente y esperan datos crudos (GLK
        estándar de Eckstein & Bauch). Esto reproduce exactamente lo que
        hace 'Analizar Serie Flotante': r sobre diferencias-log y GLK/t-BP
        sobre crudo. Sin estos parámetros (modo retrocompatible), los tres
        se calculan sobre serie_a/serie_b.

    Antes la comparación múltiple pasaba anchos CRUDOS como serie_a/serie_b,
    lo que daba correlaciones espurias altas por las tendencias de edad
    compartidas entre árboles — inconsistente con el cofechado real. Por eso
    el mismo alineamiento mostraba r=+0.44 en una tabla y r=-0.30 en otra.

    Devuelve listas paralelas: (shifts, rs, glks, t_bps, ns).
    """
    usar_raw = serie_a_raw is not None and serie_b_raw is not None

    # Vectorización: se pasa todo a arreglos numpy ordenados por año una sola
    # vez, y cada desfase se alinea con np.intersect1d (rápido). Antes se
    # copiaban Series de pandas y se recalculaba el filtro de Hollstein por
    # cada desfase (decenas de miles de construcciones de Series) — eso hacía
    # que comparar muchas series tardara más de un minuto.
    a_s = serie_anual(serie_a)
    b_s = serie_anual(serie_b)
    ya = a_s.index.to_numpy(np.int64)
    va = a_s.to_numpy(dtype=float)
    yb = b_s.index.to_numpy(np.int64)
    vb = b_s.to_numpy(dtype=float)
    if usar_raw:
        ar_s = serie_anual(serie_a_raw)
        br_s = serie_anual(serie_b_raw)
        yar = ar_s.index.to_numpy(np.int64)
        var_ = ar_s.to_numpy(dtype=float)
        ybr = br_s.index.to_numpy(np.int64)
        vbr = br_s.to_numpy(dtype=float)

    min_glk = min(10, min_overlap)
    min_tbp = min(20, min_overlap)
    shifts, rs, glks, tbps, ns = [], [], [], [], []
    for shift in range(-max_shift, max_shift + 1):
        common, ia, ib = np.intersect1d(
            ya + shift, yb, assume_unique=True, return_indices=True)
        n = len(common)
        if n < min_overlap:
            continue
        a_arr = va[ia]
        b_arr = vb[ib]
        r = pearson(a_arr, b_arr)
        if not np.isfinite(r):
            continue

        # GLK y t-BP sobre las series CRUDAS (alineadas) si se proporcionaron;
        # si el solape crudo es corto, sobre las mismas series de r.
        anios_glk = common
        if usar_raw:
            cr, iga, igb = np.intersect1d(
                yar + shift, ybr, assume_unique=True, return_indices=True)
            if len(cr) >= min_glk:
                ag = var_[iga]
                bg = vbr[igb]
                n = len(cr)
                anios_glk = cr
            else:
                ag = a_arr
                bg = b_arr
        else:
            ag = a_arr
            bg = b_arr

        glk = glk_alineado(ag, bg, min_glk, anios=anios_glk)
        t_bp = tbp_alineado(ag, bg, min_tbp, anios=anios_glk)

        shifts.append(shift)
        rs.append(r)
        glks.append(glk if np.isfinite(glk) else float("nan"))
        tbps.append(t_bp if np.isfinite(t_bp) else float("nan"))
        ns.append(n)

    return shifts, rs, glks, tbps, ns


def _ventanas_correlacion(m, t, overlap, mitad):
    """Una sola selección de ventanas y Pearson para ambos consumidores."""
    for anio, ventana in _ventanas_sin_centro(overlap, mitad):
        if len(ventana) < OVERLAP_MINIMO_GRAFICO:
            continue
        r = pearson(m.loc[ventana].values, t.loc[ventana].values)
        if np.isfinite(r):
            yield anio, ventana, r


def _r_movil(m: pd.Series, t: pd.Series, overlap: list, mitad: int) -> tuple[list, list]:
    """Correlación de Pearson en ventana deslizante centrada."""
    years, r_vals = [], []
    for anio, _, r in _ventanas_correlacion(m, t, overlap, mitad):
        years.append(float(anio))
        r_vals.append(r)
    return years, r_vals


def _stats_movil(m, t, overlap, mitad, m_raw=None, t_raw=None):
    """Versión extendida de _r_movil que calcula r, GLK y t-BP por ventana."""
    if m_raw is None:
        m_raw = m
    if t_raw is None:
        t_raw = t

    years, r_vals, glk_vals, tbp_vals, n_vals = [], [], [], [], []

    for anio, ventana, r in _ventanas_correlacion(m, t, overlap, mitad):
        n_v = len(ventana)

        m_raw_w = m_raw.loc[m_raw.index.intersection(ventana)]
        t_raw_w = t_raw.loc[t_raw.index.intersection(ventana)]
        glk, _ = gleichlaufigkeit(m_raw_w, t_raw_w, min_overlap=5)
        t_bp, _, _ = t_baillie_pilcher(m_raw_w, t_raw_w, min_overlap=5)

        years.append(float(anio))
        r_vals.append(r)
        glk_vals.append(glk)
        tbp_vals.append(t_bp)
        n_vals.append(n_v)

    return years, r_vals, glk_vals, tbp_vals, n_vals


def agrupar_por_arbol(nombres) -> dict:
    """Agrupa códigos de serie por ÁRBOL, reutilizando el lector de códigos.

    QLH107A y QLH107B son dos radios del mismo árbol; QLH108A es otro árbol.
    Se usa la misma clave que ordena los archivos al unir: sitio + número,
    ignorando el radio.

    Devuelve {nombre_de_serie: identificador_de_arbol}.
    """
    out = {}
    for n in nombres:
        k = clave_codigo_dendro(n)
        out[n] = f"{k[0]}{k[1]}"      # sitio + número de árbol, sin el radio
    return out


def rbar_entre_arboles(series_dict, nombres, min_overlap: int = 10) -> dict:
    """Rbar separando radios del mismo árbol de árboles distintos.

    POR QUÉ IMPORTA
    ---------------
    Dos radios del mismo árbol comparten mucho más que la señal del sitio:
    comparten el individuo, con su microambiente, sus competidores y sus
    daños. Meterlos en la misma bolsa que los pares entre árboles infla el
    Rbar y, con él, la EPS y la SSS. Una colección de 30 radios de 10 árboles
    NO tiene la réplica de 30 árboles.

    Se calculan tres cantidades, como en `rwi.stats` de dplR:

      rbar_wt   correlación media ENTRE radios del mismo árbol
      rbar_bt   correlación media ENTRE árboles distintos
      rbar_eff  el que hay que usar:
                    rbar_bt / (rbar_wt + (1 − rbar_wt)/c_eff)
                donde c_eff es el número efectivo de radios por árbol.

    Cuando cada árbol tiene un solo radio, rbar_eff es igual a rbar_bt y todo
    se reduce al caso simple.
    """
    arbol = agrupar_por_arbol(nombres)
    cols = {}
    for n in nombres:
        v = series_dict.get(n)
        if v is None:
            continue
        col = v["Ancho_mm"] if isinstance(v, pd.DataFrame) else v
        col = pd.to_numeric(col, errors="coerce").dropna()
        if len(col) > 5:
            cols[n] = col
    claves = list(cols)
    if len(claves) < 2:
        return {"rbar_wt": float("nan"), "rbar_bt": float("nan"),
                "rbar_eff": float("nan"), "n_arboles": 0, "c_eff": float("nan")}
    M = pd.concat(cols, axis=1)
    ii, jj, rs = correlaciones_pares(M.to_numpy(dtype=float), min_overlap,
                                      devolver_indices=True)
    wt, bt = [], []
    for i, j, r in zip(ii, jj, rs):
        (wt if arbol[claves[i]] == arbol[claves[j]] else bt).append(float(r))
    arboles = {}
    for n in claves:
        arboles.setdefault(arbol[n], []).append(n)
    n_por_arbol = np.array([len(v) for v in arboles.values()], dtype=float)
    rbar_wt = float(np.mean(wt)) if wt else float("nan")
    rbar_bt = float(np.mean(bt)) if bt else float("nan")
    if not wt:
        c_eff = 1.0
        rbar_eff = rbar_bt
    else:
        # Número efectivo de radios por árbol: media armónica, como dplR
        c_eff_rec = float(np.mean(1.0 / n_por_arbol))
        c_eff = 1.0 / c_eff_rec if c_eff_rec > 0 else 1.0
        den = rbar_wt + (1.0 - rbar_wt) * c_eff_rec
        rbar_eff = rbar_bt / den if den > 0 else float("nan")
    return {"rbar_wt": rbar_wt, "rbar_bt": rbar_bt, "rbar_eff": rbar_eff,
            "n_arboles": len(arboles), "c_eff": c_eff,
            "n_pares_wt": len(wt), "n_pares_bt": len(bt)}


def correlaciones_pares(mat, min_overlap=10, *, devolver_indices=False):
    """Correlaciones válidas de la mitad superior, con solape por par.

    Con devolver_indices=True devuelve (filas, columnas, correlaciones).
    Los índices identifican las columnas originales de cada par válido.
    """
    mat = np.asarray(mat, dtype=float)
    if mat.ndim != 2:
        raise ValueError("Se esperaba una matriz de años por series.")
    if mat.shape[0] < 2 or mat.shape[1] < 2:
        rs = np.empty(0, dtype=float)
        if devolver_indices:
            return np.empty(0, dtype=int), np.empty(0, dtype=int), rs
        return rs
    valido = np.isfinite(mat)
    V = valido.astype(float)
    # Restar una referencia por columna antes de acumular productos.
    # La correlación por pares es invariante ante esta traslación.
    referencia = mat[np.argmax(valido, axis=0), np.arange(mat.shape[1])]
    referencia = np.where(np.isfinite(referencia), referencia, 0.0)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        Z = np.where(valido, mat - referencia, 0.0)
        escala = np.max(np.abs(Z), axis=0)
        Z = Z / np.where(escala > 0, escala, 1.0)
        n_ab = V.T @ V
        s_a = Z.T @ V
        s_b = s_a.T
        s_ab = Z.T @ Z
        s_aa = (Z * Z).T @ V
        s_bb = s_aa.T
        cov = s_ab - s_a * s_b / n_ab
        var_a = s_aa - s_a * s_a / n_ab
        var_b = s_bb - s_b * s_b / n_ab
        R = cov / (np.sqrt(var_a) * np.sqrt(var_b))

    iu = np.triu_indices(mat.shape[1], k=1)
    suficientes = n_ab[iu] >= max(2, min_overlap)
    rs = R[iu].copy()
    # Si el subconjunto común tiene varianza muy pequeña respecto de la
    # columna completa, recalcular solo ese par con centrado local.
    tol = 64 * np.finfo(float).eps
    dudosos = suficientes & (
        (var_a[iu] <= tol * s_aa[iu]) | (var_b[iu] <= tol * s_bb[iu])
        | ~np.isfinite(rs) | (np.abs(rs) > 1 + tol))
    for k in np.flatnonzero(dudosos):
        i, j = iu[0][k], iu[1][k]
        m = valido[:, i] & valido[:, j]
        rs[k] = pearson(mat[m, i], mat[m, j])
    validos = suficientes & np.isfinite(rs)
    rs = np.clip(rs[validos], -1.0, 1.0)
    if devolver_indices:
        return iu[0][validos], iu[1][validos], rs
    return rs


def _ventanas_sin_centro(overlap, mitad):
    for anio in overlap:
        yield anio, [y for y in overlap if 0 < abs(y - anio) <= mitad]
