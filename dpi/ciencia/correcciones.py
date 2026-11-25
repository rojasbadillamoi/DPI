"""Aplicación y búsqueda de correcciones de anillos."""
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import _r_movil, pearson as _r_pearson
from dpi.ciencia.constantes import OVERLAP_MINIMO_ANALISIS, OVERLAP_MINIMO_GRAFICO

MAX_CORRECCION = 3


def aplicar_correccion(df: pd.DataFrame, anio: int, delta: int,
                        anclaje: str = "corteza") -> pd.DataFrame:
    """Inserta o elimina delta anillos en una posición.

    El ANCLAJE decide qué extremo de la serie se queda quieto:

    • "corteza" (por defecto): el ÚLTIMO año no se mueve y se desplazan los
      años ANTERIORES. Es lo correcto para árboles vivos fechados desde la
      corteza (se sabe con certeza el año del anillo externo). Si falta un
      anillo en 2023, al insertarlo la serie sigue terminando en 2024 y todo
      lo anterior a 2023 retrocede un año — que es justo lo que pasó en la
      madera.
        - delta > 0 (anillo faltante): los años ≤ anio se mueven −1 y se
          inserta un anillo en `anio`.
        - delta < 0 (anillo extra): se elimina `anio` y los años < anio
          se mueven +1.

    • "medula": el PRIMER año no se mueve y se desplazan los años
      posteriores. Útil para series flotantes o fechadas desde la médula.

    Antes solo existía el anclaje en médula, así que insertar un anillo
    empujaba la serie hacia el presente (una serie que terminaba en 2024
    pasaba a terminar en 2025) y obligaba a corregir el año base a mano.
    Además hacía que el buscador de correcciones propusiera años equivocados:
    para arreglar un desfase global proponía una corrección al INICIO de la
    serie en vez del anillo que realmente falta cerca de la corteza.

    Implementado con numpy (no pandas append/.loc) porque se llama cientos
    de veces por cada búsqueda de correcciones.
    """
    years = df.index.to_numpy(dtype=np.int64).copy()
    vals = pd.to_numeric(df["Ancho_mm"], errors="coerce").to_numpy(dtype=float).copy()
    placeholder = float(np.nanmean(vals)) if vals.size else 0.0
    a = int(anio)
    anclar_corteza = str(anclaje).lower().startswith("cort")

    for _ in range(abs(delta)):
        if delta > 0:
            if anclar_corteza:
                # Los años ≤ a retroceden; queda libre el año `a`
                years = np.where(years <= a, years - 1, years)
            else:
                years = np.where(years >= a, years + 1, years)
            years = np.append(years, a)
            vals = np.append(vals, placeholder)
        else:
            m = years != a
            years = years[m]
            vals = vals[m]
            if anclar_corteza:
                years = np.where(years < a, years + 1, years)
            else:
                years = np.where(years > a, years - 1, years)
    orden = np.argsort(years, kind="stable")
    return pd.DataFrame({"Ancho_mm": vals[orden]},
                        index=pd.Index(years[orden], name="Anio"))


def _plausibilidad_anillo_estrecho(ref_years: np.ndarray, ref_vals: np.ndarray,
                                    anio: int, delta: int,
                                    peso: float = 0.6) -> float:
    """Cuán creíble es que falte (o sobre) un anillo en `anio`.

    Los anillos que se omiten al fechar una muestra son los ESTRECHOS: en un
    año malo el anillo puede ser casi invisible o localmente ausente. Los
    anillos anchos prácticamente nunca se pasan por alto.

    Se mide cuán bajo está ese año en la REFERENCIA (la cronología, ya
    estandarizada, media ~1) usando su posición en desviaciones típicas, y se
    devuelve un factor:
        > 1  año estrecho  → candidato más creíble
        < 1  año ancho     → candidato menos creíble
    `peso` gradúa cuánto influye (0 = solo estadística, como antes).

    Para anillos SOBRANTES (delta<0) el razonamiento se invierte solo en
    parte: un falso anillo suele aparecer dentro de un año ancho (banda de
    madera tardía intermedia), así que ahí se premia lo ancho.
    """
    if ref_vals.size < 5:
        return 1.0
    idx = np.searchsorted(ref_years, int(anio))
    if idx < 0 or idx >= ref_years.size or int(ref_years[idx]) != int(anio):
        return 1.0  # el año no está en la referencia: sin información
    media = float(np.nanmean(ref_vals))
    sd = float(np.nanstd(ref_vals))
    if not np.isfinite(sd) or sd <= 0:
        return 1.0
    z = (float(ref_vals[idx]) - media) / sd
    # z<0 = año estrecho. Para anillo faltante premiamos z negativo.
    señal = -z if delta > 0 else z
    señal = float(np.clip(señal, -2.5, 2.5))
    return float(max(0.15, 1.0 + peso * señal / 2.5))


def buscar_correcciones(ref, problema, mitad_ventana, max_corr=MAX_CORRECCION,
                        anclaje="corteza",
                        transformar_ref=None, transformar_prob=None,
                        delta_r_minimo: float = 0.05,
                        max_fallback: int = 3):
    """Busca correcciones que mejoran la correlación global.

    Devuelve tupla **(sugerencias, es_marginal)**:
      • Si hay correcciones con Δr ≥ delta_r_minimo: devuelve esas (hasta 15) y
        es_marginal = False.
      • Si no hay correcciones significativas pero sí hay alguna mejora positiva:
        devuelve las mejores hasta `max_fallback` y es_marginal = True. Esto
        permite mostrar un "sanity check" al usuario en lugar de una lista vacía,
        con la advertencia de que son cambios dentro del ruido estadístico.
      • Si no hay ninguna mejora positiva: devuelve ([], False).

    delta_r_minimo: filtro de ruido. 0.05 es razonable; con series ya
    correctamente cofechadas las "mejoras" suelen ser 0.01-0.04 (ruido) y
    las correcciones reales suelen estar en 0.10+.
    """
    if transformar_ref is None:
        transformar_ref = lambda s: pd.to_numeric(s, errors="coerce").astype(float).dropna()
    if transformar_prob is None:
        transformar_prob = lambda s: pd.to_numeric(s, errors="coerce").astype(float).dropna()

    d_ref = transformar_ref(ref["Ancho_mm"])
    d_prob = transformar_prob(problema["Ancho_mm"])
    overlap_base = list(d_ref.index.intersection(d_prob.index))
    if len(overlap_base) < OVERLAP_MINIMO_ANALISIS:
        return [], False

    r_global_base = _r_pearson(d_ref.loc[overlap_base].values, d_prob.loc[overlap_base].values)
    if np.isnan(r_global_base):
        return [], False

    _, r_movil_base = _r_movil(d_ref, d_prob, overlap_base, mitad_ventana)

    # OPTIMIZACIÓN CLAVE (antes el programa se colgaba): todo el bucle de
    # candidatos se hace en numpy puro. Se transforma la serie UNA sola vez
    # (fuera del bucle) y cada corrección candidata se aplica sobre los
    # arreglos ya transformados, alineando con la referencia por año con
    # np.intersect1d. Nada de spline ni construcción de DataFrames por
    # candidato (eso era lo lento).
    ref_years = d_ref.index.to_numpy(np.int64)
    ref_vals = d_ref.to_numpy(dtype=float)
    prob_years = d_prob.index.to_numpy(np.int64)
    prob_vals = d_prob.to_numpy(dtype=float)
    prob_mean = float(np.nanmean(prob_vals)) if prob_vals.size else 0.0
    ref_min, ref_max = int(ref_years.min()), int(ref_years.max())

    ob_arr = np.asarray(overlap_base, dtype=np.int64)
    base_ref_ov = d_ref.loc[overlap_base].to_numpy(dtype=float)
    base_prob_ov = d_prob.loc[overlap_base].to_numpy(dtype=float)

    _anclar_corteza = str(anclaje).lower().startswith("cort")

    def _corr_np(anio, delta):
        """Aplica la corrección sobre (prob_years, prob_vals) en numpy,
        respetando el anclaje elegido, y devuelve (años, valores) ordenados."""
        yrs = prob_years.copy()
        vals = prob_vals.copy()
        a = int(anio)
        for _ in range(abs(delta)):
            if delta > 0:
                if _anclar_corteza:
                    yrs = np.where(yrs <= a, yrs - 1, yrs)
                else:
                    yrs = np.where(yrs >= a, yrs + 1, yrs)
                yrs = np.append(yrs, a)
                vals = np.append(vals, prob_mean)
            else:
                m = yrs != a
                yrs = yrs[m]
                vals = vals[m]
                if _anclar_corteza:
                    yrs = np.where(yrs < a, yrs + 1, yrs)
                else:
                    yrs = np.where(yrs > a, yrs - 1, yrs)
        o = np.argsort(yrs, kind="stable")
        return yrs[o], vals[o]

    resultados = []
    # Limitar los años a probar a la zona que puede afectar el solape con la
    # referencia (un año posterior a ref_max no cambia la correlación).
    anios_candidatos = [int(a) for a in problema.index
                        if ref_min - max_corr <= int(a) <= ref_max]
    for anio in anios_candidatos:
        for delta in range(-max_corr, max_corr + 1):
            if delta == 0:
                continue
            cyrs, cvals = _corr_np(anio, delta)
            common, iref, icorr = np.intersect1d(
                ref_years, cyrs, assume_unique=True, return_indices=True)
            if common.size < OVERLAP_MINIMO_ANALISIS:
                continue
            a_vals = ref_vals[iref]
            b_vals = cvals[icorr]
            r_global_tras = _r_pearson(a_vals, b_vals)
            if np.isnan(r_global_tras):
                continue
            delta_r = r_global_tras - r_global_base
            if delta_r <= 0:
                continue

            zmask = np.abs(common - anio) <= mitad_ventana
            r_zona_tras = np.nan
            if int(zmask.sum()) >= OVERLAP_MINIMO_GRAFICO:
                r_zona_tras = _r_pearson(a_vals[zmask], b_vals[zmask])
            zbmask = np.abs(ob_arr - anio) <= mitad_ventana
            r_zona_antes = np.nan
            if int(zbmask.sum()) >= OVERLAP_MINIMO_GRAFICO:
                r_zona_antes = _r_pearson(base_ref_ov[zbmask], base_prob_ov[zbmask])

            # Solo para las candidatas que mejoran: la serie CRUDA corregida
            # (barata, sin spline) que se guardará para aplicarla luego.
            df_corr = aplicar_correccion(problema, anio, delta, anclaje=anclaje)

            # PLAUSIBILIDAD BIOLÓGICA: los anillos que se omiten al fechar son
            # casi siempre los ESTRECHOS (años malos), no los anchos. Cuando
            # varios años dan una mejora de correlación parecida —cosa muy
            # habitual, porque desplazar la serie un año produce mejoras
            # similares en un tramo— la estadística sola no distingue cuál es.
            # Aquí se pondera cada candidato según lo estrecho que sea ese año
            # en la REFERENCIA (la cronología): un año marcadamente bajo la
            # media es un candidato mucho más creíble para un anillo faltante.
            plaus = _plausibilidad_anillo_estrecho(
                ref_years, ref_vals, anio, delta)

            resultados.append({
                "anio": int(anio), "delta": delta,
                "tipo": f"+{delta} anillo(s)" if delta > 0 else f"{delta} anillo(s)",
                "r_antes": r_global_base, "r_tras": r_global_tras,
                "delta_r": delta_r, "r_zona_antes": r_zona_antes,
                "r_zona_tras": r_zona_tras, "df_corregido": df_corr,
                "plausibilidad": plaus,
                "puntaje": delta_r * plaus,
            })

    # Ordenar por PUNTAJE (mejora de correlación × plausibilidad del año),
    # no solo por la mejora bruta.
    resultados.sort(key=lambda x: x.get("puntaje", x["delta_r"]), reverse=True)

    # Deduplicar correcciones solapadas (cerca del mismo año con mismo signo)
    filtrados, ocupados = [], []
    for r in resultados:
        solapado = any(
            abs(r["anio"] - oc["anio"]) <= 5 and np.sign(r["delta"]) == np.sign(oc["delta"])
            for oc in ocupados)
        if not solapado:
            filtrados.append(r)
            ocupados.append(r)

    # Separar en significativas y fallback marginal
    significativas = [r for r in filtrados if r["delta_r"] >= delta_r_minimo]
    if significativas:
        return significativas[:15], False
    return filtrados[:max_fallback], True
