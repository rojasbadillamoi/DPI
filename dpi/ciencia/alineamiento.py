"""Alineamiento de anillos mediante programación dinámica."""
import numpy as np
import pandas as pd
import dpi.ciencia.estadistica as _est


def alineamiento_optimo_anillos(serie_a, serie_b, shift_base,
                                 max_correcciones=10, penalizacion=3.0):
    """Alineamiento óptimo serie↔cronología por programación dinámica.

    A diferencia del cofechado por ventanas fijas (COFECHA), este método
    descompone la serie completa buscando el alineamiento globalmente
    óptimo que permite insertar anillos faltantes y eliminar anillos
    sobrantes en CUALQUIER posición, con una penalización por cada
    corrección.

    Modelo:
      - Se recorre la serie año a año (sobre primeras diferencias, que es
        la señal de cofechado).
      - En cada año la serie tiene un "desfase acumulado" respecto a la
        cronología.
      - De un año al siguiente, el desfase puede mantenerse (año normal),
        +1 (anillo faltante → hay que insertar uno) o −1 (anillo sobrante
        → hay que eliminar uno).
      - Cada cambio de desfase cuesta `penalizacion`.
      - Se maximiza la concordancia total (acuerdo de signo de las
        primeras diferencias, equivalente a GLK punto a punto) menos las
        penalizaciones.

    Implementación: programación dinámica O(n·S·3) donde S = 2·max_corr+1.
    Garantiza el óptimo global (no es heurístico como las ventanas).

    Parámetros:
      shift_base: desfase global de partida (centro de la banda de búsqueda)
      max_correcciones: máximo de anillos a corregir acumulados (banda ±)
      penalizacion: costo por corrección. Bajo = exploratorio (propone más
                    correcciones); alto = conservador (solo las muy claras).

    Devuelve dict con:
      "segmentos": lista de tramos de desfase constante, cada uno con
                   rango de años de la serie, rango calendario, corrección
                   neta vs base, n años, r y GLK del tramo.
      "correcciones": lista de puntos donde cambia el desfase (año
                      calendario aproximado y tipo: faltante/sobrante).
      "shift_base": el desfase base usado.
    Devuelve None si no hay datos suficientes.
    """
    a = pd.to_numeric(serie_a, errors="coerce").dropna().sort_index()
    b = pd.to_numeric(serie_b, errors="coerce").dropna().sort_index()
    if len(a) < 10 or len(b) < 10:
        return None

    da = _est.diferencias_anuales(a)
    db = _est.diferencias_anuales(b)
    sa = np.sign(da.to_numpy())
    years_a = da.index.to_numpy().astype(int)
    sb_by_year = {int(y): np.sign(v)
                  for y, v in zip(db.index.to_numpy(), db.to_numpy())}
    da_by_year = {int(y): float(v)
                  for y, v in zip(da.index.to_numpy(), da.to_numpy())}
    db_by_year = {int(y): float(v)
                  for y, v in zip(db.index.to_numpy(), db.to_numpy())}

    n = len(years_a)
    if n == 0 or db.empty:
        return None
    shifts = list(range(int(shift_base) - int(max_correcciones),
                        int(shift_base) + int(max_correcciones) + 1))
    S = len(shifts)
    NEG = -1e9
    dp = np.full((n, S), NEG)
    back = np.full((n, S), -1, dtype=int)

    def score(t, s):
        ya = years_a[t]
        cb = sb_by_year.get(ya + s)
        if cb is None or sa[t] == 0 or cb == 0:
            return 0.0
        return 1.0 if sa[t] == cb else -1.0

    # Inicialización: el primer año puede empezar en cualquier desfase de
    # la banda sin costo (la posición del extremo de médula es la hipótesis
    # de datación; las correcciones internas son las que cuestan).
    for si, s in enumerate(shifts):
        dp[0][si] = score(0, s)

    for t in range(1, n):
        prev = dp[t - 1]
        for si in range(S):
            sc = score(t, shifts[si])
            best = prev[si]       # mismo desfase (año normal)
            bptr = si
            if si - 1 >= 0 and prev[si - 1] - penalizacion > best:
                best = prev[si - 1] - penalizacion  # anillo faltante
                bptr = si - 1
            if si + 1 < S and prev[si + 1] - penalizacion > best:
                best = prev[si + 1] - penalizacion  # anillo sobrante
                bptr = si + 1
            dp[t][si] = best + sc
            back[t][si] = bptr

    end_si = int(np.argmax(dp[n - 1]))
    path = [0] * n
    si = end_si
    for t in range(n - 1, 0, -1):
        path[t] = si
        si = back[t][si]
        if si < 0:
            si = path[t]
    path[0] = si
    shift_path = [shifts[i] for i in path]

    # Construir segmentos de desfase constante
    segmentos = []
    correcciones = []
    i0 = 0
    for t in range(1, n + 1):
        if t == n or shift_path[t] != shift_path[i0]:
            s = shift_path[i0]
            ys = years_a[i0:t]
            avals, bvals, agree, tot = [], [], 0, 0
            for y in ys:
                if y in da_by_year and (y + s) in db_by_year:
                    avals.append(da_by_year[y])
                    bvals.append(db_by_year[y + s])
                    if (np.sign(da_by_year[y]) == np.sign(db_by_year[y + s])
                            and da_by_year[y] != 0):
                        agree += 1
                    tot += 1
            r = _est.pearson(avals, bvals) if len(avals) > 2 else float("nan")
            glk = agree / tot if tot else float("nan")
            segmentos.append({
                "serie_ini": int(ys[0]), "serie_fin": int(ys[-1]),
                "cal_ini": int(ys[0] + s), "cal_fin": int(ys[-1] + s),
                "shift": int(s), "correccion": int(s - shift_base),
                "n": int(len(ys)), "r": r, "glk": glk,
            })
            # Registrar el punto de corrección (transición entre segmentos)
            if t < n:
                s_next = shift_path[t]
                year_corr = int(years_a[t] + s_next)
                if s_next > s:
                    # El desfase aumenta → faltaba un anillo (insertar)
                    correcciones.append({
                        "anio_calendario": year_corr,
                        "tipo": "faltante", "delta": s_next - s,
                    })
                else:
                    correcciones.append({
                        "anio_calendario": year_corr,
                        "tipo": "sobrante", "delta": s - s_next,
                    })
            i0 = t

    return {
        "segmentos": segmentos,
        "correcciones": correcciones,
        "shift_base": int(shift_base),
    }
