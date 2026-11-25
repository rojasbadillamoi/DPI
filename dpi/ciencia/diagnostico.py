"""Diagnóstico de datación mediante estadísticas de series."""
import numpy as np
import pandas as pd
import dpi.ciencia.estadistica as _est


def diagnosticar_datacion(serie_std: pd.Series, crono_std: pd.Series,
                           ventana: int = 40, paso: int = 5,
                           max_shift: int = 3, min_overlap: int = 20) -> dict:
    """Determina QUÉ TRAMO de la serie está bien fechado y dónde está el error.

    Es como trabaja un dendrocronólogo: en vez de probar correcciones a ciegas
    en toda la serie, primero se busca el tramo que ya calza con la cronología
    (el ancla) y se localiza el punto donde deja de calzar.

    Para cada ventana móvil se prueba la serie desplazada en varios años y se
    ve QUÉ DESFASE gana localmente. Con eso se distinguen tres situaciones:

    • Todas las ventanas prefieren desfase 0 → la serie está bien fechada.
    • Todas prefieren el mismo desfase k ≠ 0 → la serie entera está corrida:
      no falta un anillo en medio, sino que el año base está mal (o faltan
      anillos fuera del tramo medido).
    • Unas prefieren 0 y otras k → hay un error DENTRO de la serie, justo en
      la frontera. El tramo que prefiere 0 es el que está bien fechado, y por
      tanto el que debe quedar fijo: si es el tramo reciente se ancla la
      corteza, si es el antiguo se ancla la médula.

    Devuelve un diccionario con las ventanas, los tramos detectados, el
    diagnóstico, el anclaje recomendado y el año y signo del error.
    """
    a = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    b = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()
    vacio = {"ventanas": [], "tramos": [], "diagnostico": "sin_datos",
             "anclaje_sugerido": "corteza", "anio_error": None,
             "delta_sugerido": 0, "shift_global": 0, "mensaje": ""}
    if a.empty or b.empty:
        return vacio

    ya = a.index.to_numpy(np.int64)
    va = a.to_numpy(dtype=float)
    yb = b.index.to_numpy(np.int64)
    vb = b.to_numpy(dtype=float)

    def _r(y_desde, y_hasta, shift):
        m = (ya >= y_desde) & (ya <= y_hasta)
        if m.sum() < min_overlap:
            return np.nan, 0
        comun, ia, ib = np.intersect1d(ya[m] + shift, yb,
                                       assume_unique=True, return_indices=True)
        if len(comun) < min_overlap:
            return np.nan, len(comun)
        x = va[m][ia]
        y = vb[ib]
        return _est.pearson(x, y), len(comun)

    ini, fin = int(ya.min()), int(ya.max())
    # VENTANAS ADAPTATIVAS: una ventana fija de 40 años deja fuera cualquier
    # serie corta (una de 18 años no se podría analizar). La ventana se ajusta
    # al largo disponible: alrededor de un tercio de la serie, entre 12 y 50
    # años, con paso proporcional.
    largo = fin - ini + 1
    ventana = int(min(max(largo // 3, 12), max(ventana, 12)))
    paso = int(min(max(ventana // 8, 1), 10))
    min_overlap = int(min(max(ventana // 2, 8), min_overlap))
    mitad = ventana // 2
    ventanas = []
    # Los centros recorren TODA la serie, incluidos los extremos: la ventana se
    # recorta contra los bordes cuando hace falta. Antes iban de ini+mitad a
    # fin−mitad, así que los primeros y últimos 25 años nunca eran centro de
    # ventana. Con un error de datación cerca del final, el tramo reciente
    # —que es justamente el que está bien fechado— casi no se medía, el
    # desfase 0 apenas aparecía y el diagnóstico lo confundía con un desfase
    # de toda la serie.
    for centro in range(ini, fin + 1, max(1, paso)):
        desde = max(ini, centro - mitad)
        hasta = min(fin, centro + mitad)
        if hasta - desde + 1 < min_overlap:
            continue
        mejores = []
        for sh in range(-max_shift, max_shift + 1):
            r, n = _r(desde, hasta, sh)
            if np.isfinite(r):
                mejores.append((r, sh, n))
        if not mejores:
            continue
        r_best, sh_best, n_best = max(mejores, key=lambda t: t[0])
        r0 = next((r for r, sh, _ in mejores if sh == 0), np.nan)
        # Solo se considera "ganador" un desfase si mejora de forma clara:
        # diferencias mínimas son ruido, no evidencia de un error de datación.
        if np.isfinite(r0) and (r_best - r0) < 0.10:
            sh_best, r_best = 0, r0
        ventanas.append({"centro": int(centro), "shift": int(sh_best),
                         "r": float(r_best), "r0": float(r0) if np.isfinite(r0) else np.nan,
                         "n": int(n_best)})

    if not ventanas:
        return vacio

    # Agrupar ventanas consecutivas con el mismo desfase ganador
    tramos = []
    for v in ventanas:
        if tramos and tramos[-1]["shift"] == v["shift"]:
            tramos[-1]["fin"] = v["centro"]
            tramos[-1]["rs"].append(v["r"])
        else:
            tramos.append({"inicio": v["centro"], "fin": v["centro"],
                           "shift": v["shift"], "rs": [v["r"]]})
    for t in tramos:
        t["r_medio"] = float(np.nanmean(t["rs"]))
        del t["rs"]

    # Descartar tramos de una sola ventana: con ventanas de pocas décadas la
    # correlación es ruidosa y aparecen desfases "ganadores" espurios. Un
    # error de datación real se manifiesta de forma sostenida en varias
    # ventanas consecutivas, no en una suelta.
    # Al menos 3 ventanas consecutivas (2 pasos de extensión): con una o dos
    # el desfase ganador es inestable, sobre todo cerca de los extremos del
    # solape, y produce diagnósticos seguros pero equivocados.
    min_extension = max(2 * paso, 1)
    solidos = [t for t in tramos if (t["fin"] - t["inicio"]) >= min_extension]
    if not solidos:
        solidos = tramos

    # Cobertura de cada desfase (en años cubiertos por sus tramos sólidos)
    cobertura = {}
    for t in solidos:
        cobertura[t["shift"]] = cobertura.get(t["shift"], 0) + \
            (t["fin"] - t["inicio"] + paso)
    total = sum(cobertura.values()) or 1

    shifts = set(cobertura)
    res = dict(vacio)
    res["ventanas"] = ventanas
    res["tramos"] = solidos

    if shifts == {0}:
        res.update(diagnostico="bien_fechada", anio_error=None, delta_sugerido=0,
                   mensaje="La serie calza con la cronología en toda su extensión.")
        return res

    # Desfase dominante distinto de cero
    no_cero = {k: v for k, v in cobertura.items() if k != 0}
    k_dom = max(no_cero, key=no_cero.get) if no_cero else 0
    frac_dom = no_cero.get(k_dom, 0) / total
    frac_cero = cobertura.get(0, 0) / total

    # Si un desfase no nulo domina de forma abrumadora y prácticamente no hay
    # tramos bien fechados, la serie ENTERA está corrida. El umbral es
    # exigente a propósito: basta con que exista un tramo sólido a desfase 0
    # para que se trate como error interno, porque ese tramo es una fecha
    # firme y lo que hay que hacer es corregir el resto respecto de él.
    hay_tramo_bueno = any(t["shift"] == 0 for t in solidos)
    if frac_dom >= 0.80 and not hay_tramo_bueno:
        res.update(diagnostico="desfase_global", shift_global=k_dom,
                   delta_sugerido=(1 if k_dom < 0 else -1),
                   anio_error=None,
                   mensaje=(f"TODA la serie calza mejor desplazada {k_dom:+d} "
                            f"año(s) ({frac_dom*100:.0f}% de las ventanas). No es "
                            "un anillo faltante en medio: el año base está mal, o "
                            "falta(n) anillo(s) fuera del tramo medido (cerca de "
                            "la corteza o de la médula)."))
        return res

    buenos = [t for t in solidos if t["shift"] == 0]
    malos = [t for t in solidos if t["shift"] == k_dom]
    if not buenos or not malos:
        res.update(diagnostico="ambiguo",
                   mensaje=("El patrón de desfases no es concluyente: la señal "
                            "común es débil o hay más de un error."))
        return res

    # Tramos más EXTENSOS de cada clase (no el de mayor desfase, que suele ser ruido)
    ancla = max(buenos, key=lambda t: (t["fin"] - t["inicio"], t["r_medio"]))
    peor = max(malos, key=lambda t: (t["fin"] - t["inicio"], t["r_medio"]))

    # CONFIANZA: la dirección del error (si falta o sobra un anillo) se deduce
    # del desfase que prefiere el tramo desajustado. Si ese tramo correlaciona
    # mal, su desfase "ganador" es poco más que ruido y la dirección puede
    # salir invertida — algo mucho peor que no opinar, porque manda a buscar
    # justo lo contrario de lo que hay en la madera. En ese caso se señala la
    # zona sospechosa sin afirmar la dirección.
    r_peor = peor.get("r_medio", 0.0)
    r_ancla = ancla.get("r_medio", 0.0)
    evidencia_debil = (not np.isfinite(r_peor) or r_peor < 0.25 or
                       (np.isfinite(r_ancla) and r_ancla > 0 and
                        r_peor < 0.55 * r_ancla))
    if evidencia_debil:
        zona = f"{peor['inicio']}–{peor['fin']}"
        res.update(diagnostico="ambiguo", anio_error=None, delta_sugerido=0,
                   mensaje=(f"El tramo {ancla['inicio']}–{ancla['fin']} calza bien "
                            f"(r≈{r_ancla:.2f}), pero el tramo {zona} tiene una "
                            f"correlación demasiado baja (r≈{r_peor:.2f}) para "
                            "determinar con seguridad si falta o sobra un anillo. "
                            "Revisa la madera en ese tramo: puede haber un anillo "
                            "ausente, un falso anillo, o simplemente poca señal "
                            "común en esos años."))
        return res

    if peor["inicio"] > ancla["fin"]:
        anio_error = int((ancla["fin"] + peor["inicio"]) // 2)
        lado = "reciente"
    else:
        anio_error = int((peor["fin"] + ancla["inicio"]) // 2)
        lado = "antiguo"

    # AFINADO POR PUNTO DE QUIEBRE: la frontera entre tramos solo da una
    # resolución del ancho de la ventana. Acá se busca el año T que mejor
    # separa "antes de T calza con desfase k" de "desde T calza con desfase 0",
    # usando TODOS los datos de cada lado (no una ventana fija). Además se
    # devuelve el INTERVALO de años compatibles: con señal común débil el dato
    # no alcanza para un año único, y dar uno solo mandaría al usuario a
    # buscar donde no es.
    k_ancla = peor["shift"]
    perfil = {}
    z = lambda r: np.arctanh(np.clip(r, -0.999, 0.999))
    min_seg = int(min(max((fin - ini + 1) // 6, 6), 15))

    def _r_seg(mask, sh):
        if mask.sum() < min_seg:
            return np.nan, 0
        com, ia, ib = np.intersect1d(ya[mask] + sh, yb,
                                     assume_unique=True, return_indices=True)
        if len(com) < min_seg:
            return np.nan, 0
        x = va[mask][ia]
        y = vb[ib]
        if np.std(x) == 0 or np.std(y) == 0:
            return np.nan, 0
        return _est.pearson(x, y), len(com)

    lo = max(int(ya.min()), int(yb.min()))
    hi = min(int(ya.max()), int(yb.max()))
    antes_es_malo = (peor["fin"] <= ancla["inicio"])
    for T in range(lo + min_seg, hi - min_seg + 1):
        if antes_es_malo:
            r1, n1 = _r_seg(ya < T, k_ancla)
            r2, n2 = _r_seg(ya >= T, 0)
        else:
            r1, n1 = _r_seg(ya < T, 0)
            r2, n2 = _r_seg(ya >= T, k_ancla)
        if not (np.isfinite(r1) and np.isfinite(r2)) or (n1 + n2) == 0:
            continue
        perfil[T] = (n1 * z(r1) + n2 * z(r2)) / (n1 + n2)

    rango = None
    candidatos = []
    if perfil:
        t_best = max(perfil, key=perfil.get)
        mx = perfil[t_best]
        # Umbral del intervalo: se calibró con series reales (ACI044B contra
        # una cronología de 169 series, r≈0.61) para que el intervalo sea
        # informativo y siga conteniendo el año verdadero.
        compatibles = [t for t, v in perfil.items() if v >= mx - 0.03]
        anio_error = int(t_best)
        if compatibles:
            # El estimador tiende a situar el quiebre uno o dos años DESPUÉS
            # del anillo que falta (el primer año mal fechado ya "arrastra" al
            # anterior), así que se garantiza un margen mínimo alrededor del
            # punto estimado para que el año verdadero quede dentro.
            rango = (min(min(compatibles), anio_error - 4),
                     max(max(compatibles), anio_error + 4))

        # LISTA CORTA DE AÑOS CONCRETOS. El intervalo por sí solo puede ser
        # ancho, y mandar al usuario a revisar 25 años de madera no sirve de
        # mucho. Pero dentro de ese intervalo no todos los años son igual de
        # probables: un anillo que se omite al fechar es casi siempre uno
        # ESTRECHO. Se combinan las dos fuentes de información —el perfil del
        # punto de quiebre y lo estrecho que es cada año en la cronología— y
        # se devuelven los pocos años que hay que mirar en la madera.
        if compatibles and vb.size > 5:
            media_c = float(np.nanmean(vb))
            sd_c = float(np.nanstd(vb)) or 1.0
            rango_perf = (max(perfil.values()) - min(perfil.values())) or 1.0
            puntuados = []
            for t in compatibles:
                pos = np.searchsorted(yb, t)
                if pos >= yb.size or int(yb[pos]) != int(t):
                    continue
                # estrechez: cuántas desviaciones bajo la media está ese año
                estrechez = (media_c - float(vb[pos])) / sd_c
                verosim = (perfil[t] - min(perfil.values())) / rango_perf
                puntuados.append((t, verosim + 0.6 * max(estrechez, 0.0),
                                  float(vb[pos])))
            puntuados.sort(key=lambda x: -x[1])
            candidatos = [{"anio": int(t), "indice_crono": round(v, 3)}
                          for t, _, v in puntuados[:5]]
    res["rango_error"] = rango
    res["candidatos"] = candidatos

    # Si el tramo bien fechado es el RECIENTE, hay que dejar fija la corteza;
    # si es el ANTIGUO, dejar fija la médula.
    centro_ancla = (ancla["inicio"] + ancla["fin"]) / 2.0
    centro_serie = (ini + fin) / 2.0
    anclaje = "corteza" if centro_ancla >= centro_serie else "medula"

    delta = 1 if k_dom < 0 else -1
    res.update(diagnostico="error_interno", anio_error=anio_error,
               delta_sugerido=delta, anclaje_sugerido=anclaje,
               shift_global=k_dom,
               mensaje=(f"El tramo {ancla['inicio']}–{ancla['fin']} calza bien "
                        f"(r≈{ancla['r_medio']:.2f}) y el tramo "
                        f"{peor['inicio']}–{peor['fin']} calza mejor desplazado "
                        f"{k_dom:+d}.<br><b>Busca el anillo "
                        + (f"entre {rango[0]} y {rango[1]}" if rango
                           else f"hacia {anio_error}")
                        + "</b>"
                        + (("<br><b>Años más probables</b> (estrechos en la "
                            "cronología, revísalos primero): "
                            + ", ".join(str(c["anio"]) for c in candidatos))
                           if candidatos else f" (lo más probable, {anio_error})")
                        + ". "
                        + ("El intervalo es amplio porque la señal común con la "
                           "cronología es débil; con una cronología de más series "
                           "se estrecha. "
                           if (rango and (rango[1] - rango[0]) > 25) else "")
                        + f"Se ancla en "
                        f"{'corteza' if anclaje == 'corteza' else 'médula'} "
                        f"para no mover el tramo ya fechado."))
    return res
