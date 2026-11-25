"""Comparación de una serie preparada contra una cronología, sin Qt."""
import hashlib
from dataclasses import dataclass
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import estadisticos_por_desfase
from dpi.ciencia.datacion import score_compuesto


@dataclass(frozen=True, slots=True)
class SeriePreparada:
    cruda: pd.Series
    correlacion: pd.Series
    glk: pd.Series


def comparar_serie(nombre, serie: SeriePreparada, referencia: SeriePreparada,
                   MIN_OVERLAP=20, VENTANA_DESFASE_FECHADA=50):
    s_a_raw, s_b_raw = serie.cruda, referencia.cruda
    s_a_corr, s_b_corr = serie.correlacion, referencia.correlacion
    s_a_glk, s_b_glk = serie.glk, referencia.glk
    if any(s.empty for s in (s_a_raw, s_b_raw, s_a_corr, s_b_corr)):
        return resultado_sin_overlap(nombre)
    c_min_year = int(s_b_raw.index.min())
    c_max_year = int(s_b_raw.index.max())
    s_min_year = int(s_a_raw.index.min())
    s_max_year = int(s_a_raw.index.max())

    # Rango de desfase que garantiza al menos MIN_OVERLAP años
    # de solape con la cronología.
    shift_min = c_min_year - s_max_year + MIN_OVERLAP - 1
    shift_max = c_max_year - s_min_year - MIN_OVERLAP + 1

    if shift_min > shift_max:
        return resultado_sin_overlap(nombre)
    max_shift_dinamico = max(abs(shift_min), abs(shift_max))

    # ACELERACIÓN: si la serie YA se solapa con la cronología en su
    # posición actual (serie fechada en años calendario), basta con
    # explorar desfases PEQUEÑOS para detectar errores de datación.
    # El barrido completo (±cientos de años) solo hace falta para
    # series FLOTANTES sin fecha. Con muchas series fechadas, esto
    # reduce el tiempo de más de un minuto a unos pocos segundos.
    overlap_en_0 = len(s_a_raw.index.intersection(s_b_raw.index))
    if overlap_en_0 >= MIN_OVERLAP:
        max_shift_dinamico = min(max_shift_dinamico, VENTANA_DESFASE_FECHADA)
    else:
        max_shift_dinamico = min(max_shift_dinamico, 5000)

    # r sobre alta frecuencia (s_*_corr); GLK/t-BP sobre
    # s_*_glk (transformada COFECHA si activo, cruda si no).
    shifts, rs, glks, tbps, ns = estadisticos_por_desfase(
        s_a_corr, s_b_corr, max_shift_dinamico, MIN_OVERLAP,
        serie_a_raw=s_a_glk, serie_b_raw=s_b_glk,
    )

    return resumir_desfases(nombre, shifts, rs, glks, tbps, ns, s_a_raw, s_b_raw)


def resumir_desfases(nombre, shifts, rs, glks, tbps, ns, s_a_raw, s_b_raw):
    """Resultado común para vistas de comparación, sin alterar el barrido."""
    if not shifts:
        return resultado_sin_overlap(nombre)

    # Puntaje compuesto por desfase y elección del mejor
    scores = [score_compuesto(r, g, t)
              for r, g, t in zip(rs, glks, tbps)]
    scores_validos = [
        (i, s) for i, s in enumerate(scores) if np.isfinite(s)]
    if scores_validos:
        idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
    else:
        idx_mejor = int(np.argmax(rs))

    # Puntaje en desfase=0 para calcular Δ
    if 0 in shifts:
        score_shift0 = scores[shifts.index(0)]
    else:
        score_shift0 = float("nan")

    return {
        "nombre_serie": nombre,
        "shifts": shifts, "rs": rs, "glks": glks,
        "tbps": tbps, "ns": ns,
        "mejor_shift": shifts[idx_mejor],
        "mejor_score": scores[idx_mejor],
        "mejor_r": rs[idx_mejor],
        "mejor_glk": glks[idx_mejor],
        "mejor_tbp": tbps[idx_mejor],
        "mejor_n": ns[idx_mejor],
        "score_shift0": score_shift0,
        # Series CRUDAS para los gráficos de detalle y el
        # alineamiento (que diferencia internamente).
        "serie_a": s_a_raw,
        "serie_b": s_b_raw,
    }


def resultado_sin_overlap(nombre: str) -> dict:
    """Devuelve un dict de resultado en blanco para series que no
    pueden compararse (sin solape suficiente con la cronología incluso
    con el desfase máximo). Aparecen en la tabla con valores en 0/—
    para que el usuario sepa cuáles quedaron fuera."""
    return {
        "nombre_serie": nombre,
        "shifts": [], "rs": [], "glks": [],
        "tbps": [], "ns": [],
        "mejor_shift": 0,
        "mejor_score": float("nan"),
        "mejor_r": float("nan"),
        "mejor_glk": float("nan"),
        "mejor_tbp": float("nan"),
        "mejor_n": 0,
        "score_shift0": float("nan"),
    }


def analizar_desfases(m_diff, t_diff, serie_a_glk, serie_b_glk):
    """Barrido de desfase de dos series; conserva el criterio de solape flotante."""
    from dpi.ciencia.constantes import OVERLAP_MINIMO_ANALISIS, OVERLAP_MINIMO_FLOTANTE
    from dpi.ciencia.estadistica import pearson as _r_pearson, gleichlaufigkeit, t_baillie_pilcher
    s_min = int(t_diff.index.min() - m_diff.index.max() + OVERLAP_MINIMO_ANALISIS - 1)
    s_max = int(t_diff.index.max() - m_diff.index.min() - OVERLAP_MINIMO_ANALISIS + 1)

    shifts = []
    rs = []
    glks = []
    tbps = []
    ns = []

    for shift in range(s_min, s_max + 1):
        # m_diff desplazada (+shift) se alinea con t_diff
        overlap = (m_diff.index + shift).intersection(t_diff.index)
        # Solape mínimo alto: ver OVERLAP_MINIMO_FLOTANTE. Sin esto las
        # posiciones de los extremos, con diez o veinte años de solape,
        # ganan por azar y tapan el desfase verdadero.
        if len(overlap) < min(OVERLAP_MINIMO_FLOTANTE,
                              max(len(m_diff), len(t_diff))):
            continue
        r = _r_pearson(m_diff.loc[overlap - shift].values,
                       t_diff.loc[overlap].values)
        if np.isnan(r):
            continue

        # GLK y t-BP sobre la serie para GLK (transformada COFECHA si
        # está activo, cruda si no): se desplaza la PRIMERA serie (a)
        a_glk_shift = serie_a_glk.copy()
        a_glk_shift.index = a_glk_shift.index + shift
        overlap_glk = a_glk_shift.index.intersection(serie_b_glk.index)
        n_ov = len(overlap_glk)
        if n_ov >= OVERLAP_MINIMO_ANALISIS:
            a_o = a_glk_shift.loc[overlap_glk]
            b_o = serie_b_glk.loc[overlap_glk]
            glk, _ = gleichlaufigkeit(a_o, b_o, min_overlap=OVERLAP_MINIMO_ANALISIS)
            t_bp, _, _ = t_baillie_pilcher(a_o, b_o, min_overlap=OVERLAP_MINIMO_ANALISIS)
        else:
            glk = float("nan")
            t_bp = float("nan")

        shifts.append(shift)
        rs.append(r)
        glks.append(glk)
        tbps.append(t_bp)
        ns.append(n_ov)

    return shifts, rs, glks, tbps, ns


def firma_dataframe(df):
    """Huella de contenido, índice, nombres y tipos de columnas."""
    if df is None:
        return None
    h = hashlib.blake2b(digest_size=32)
    h.update(repr((tuple(df.columns), tuple(map(str, df.dtypes)),
                   str(df.index.dtype))).encode("utf-8"))
    h.update(pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes())
    return h.digest()


def clave_cache_comparacion(nombres, *, revision, series, nombre_crono,
                             cronologia, meta, cofecha=()):
    """Identidad del cálculo independiente de los controles de Qt."""
    if revision is None:
        partes = [(n, firma_dataframe(series.get(n))) for n in sorted(nombres)]
    else:
        partes = [("__series__", revision, tuple(sorted(nombres)))]
    partes.append((nombre_crono, firma_dataframe(cronologia), repr(meta or {})))
    partes.append(("__cofecha__",) + tuple(cofecha))
    return tuple(partes)


def verificar_cofecha(a, b, overlap, mitad, cruda_a, cruda_b):
    """Estadísticos móviles y globales del mismo par de series."""
    from dpi.ciencia.estadistica import _stats_movil, pearson, estadisticos_cofechado
    movil = _stats_movil(a, b, overlap, mitad, cruda_a, cruda_b)
    r = pearson(a.loc[overlap].values, b.loc[overlap].values)
    return movil, r, estadisticos_cofechado(cruda_a, cruda_b)
