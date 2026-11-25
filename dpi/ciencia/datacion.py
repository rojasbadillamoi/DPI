"""Núcleo de datación dendrocronológica, independiente de la interfaz Qt."""
import logging
import numpy as np
import pandas as pd
import dpi.ciencia.estadistica as _est
import dpi.ciencia.quiebres as _qb
from dpi.ciencia.prioridad import clave_prioridad_correccion
from dpi.ciencia.estadistica import _r_movil
from dpi.ciencia.cronologia import normalizar_serie_para_tipo
from dpi.ciencia.constantes import OVERLAP_MINIMO_ANALISIS, OVERLAP_MINIMO_GRAFICO

logger = logging.getLogger(__name__)
from dpi.ciencia.correcciones import MAX_CORRECCION
MIN_OVERLAP_DEFAULT = 10


def score_compuesto(r: float, glk: float, t_bp: float) -> float:
    """Media geométrica con signo de r, GLK y t-BP normalizados a [-1, 1].

    Resultado en [-1, +1]:
      • cerca de +1  →  las tres métricas indican correlación fuerte
      • cerca de  0  →  ambiguo / al menos una métrica plana
      • cerca de -1  →  las tres indican ANTI-correlación
                        (señal de que el cofechado está completamente desfasado:
                         el patrón coincide pero invertido)

    Normalización: r ∈ [-1,1] directo, GLK mapeado desde [0,1] a [-1,1] con
    pivote en 0.5, t-BP saturado en ±10. Se usa raíz cúbica (np.cbrt) que
    preserva signo, a diferencia de la potencia 1/3 que en Python devuelve
    complejos para negativos.
    """
    if not (np.isfinite(r) and np.isfinite(glk) and np.isfinite(t_bp)):
        return float("nan")
    r_norm = max(-1.0, min(1.0, r))
    glk_norm = max(-1.0, min(1.0, 2.0 * (glk - 0.5)))
    tbp_norm = max(-1.0, min(1.0, t_bp / 10.0))
    producto = r_norm * glk_norm * tbp_norm
    return float(np.cbrt(producto))


def _serie_transformada_para_comparar(df: pd.DataFrame, meta: dict) -> pd.Series:
    tipo = (meta.get("tipo_cronologia") or "raw").lower()
    metodo = meta.get("metodo_estandarizacion", "spline")
    return normalizar_serie_para_tipo(df["Ancho_mm"], tipo, metodo)


_glk_np = _est.glk_alineado


_tbp_np = _est.tbp_alineado


from dpi.ciencia.alineamiento import alineamiento_optimo_anillos


# =============================================================================
# MOTOR DE BÚSQUEDA EXHAUSTIVA DE CORRECCIONES
# =============================================================================

def _diff_log(serie: pd.Series) -> pd.Series:
    """Diferencias de logaritmos — transforma anchos en tasas de crecimiento."""
    return _est.diferencias_log_anuales(serie)


_r_pearson = _est.pearson


from dpi.ciencia.correcciones import aplicar_correccion, _plausibilidad_anillo_estrecho, buscar_correcciones




def puntaje_consistencia(serie_std: pd.Series, crono_std: pd.Series,
                          **kwargs) -> dict:
    """Mide si una serie YA CORREGIDA quedó limpia, no cuánto correlaciona.

    El problema que resuelve: cuando el buscador propone corregir en 1850 o en
    1858, las dos candidatas dan correlaciones globales casi iguales —
    diferencias de milésimas— porque ambas arreglan casi toda la serie. La r
    global no distingue entre ellas, y así terminan aceptándose años que están
    a cinco o diez años del verdadero.

    La pregunta cambia: en vez de «¿cuál sube más la r?», «¿cuál deja la serie
    limpia?». Se aplica cada candidata y se vuelve a correr el diagnóstico de
    tramos. Si el año es el correcto, la serie queda con un solo tramo a
    desfase 0 de punta a punta. Si el año está equivocado por ocho años, queda
    un tramo residual de ocho años desajustado, que el diagnóstico ve como un
    segundo tramo.

    La ventaja es que el criterio pasa de continuo y casi empatado a
    esencialmente binario —quedó limpia o no—, y además el tramo residual
    crece con el error, así que la señal es proporcional a la distancia.

    Devuelve:
      limpia   1 si el diagnóstico dice bien_fechada, 0 si no
      residuo  años cubiertos por tramos con desfase distinto de cero
      n_tramos cuántos tramos sólidos quedaron
      diag     el diagnóstico textual, para mostrarlo en la interfaz
    """
    try:
        d = diagnosticar_datacion(serie_std, crono_std, **kwargs)
    except Exception:
        logger.debug("Falló evaluación de datación", exc_info=True)
        return {"limpia": 0, "residuo": 10 ** 6, "n_tramos": 99,
                "diag": "error", "r_medio": float("nan")}

    tramos = d.get("tramos") or []
    residuo = sum(max(t["fin"] - t["inicio"], 1)
                  for t in tramos if t.get("shift", 0) != 0)
    rs = [t.get("r_medio") for t in tramos if t.get("shift", 0) == 0]
    return {
        "limpia": 1 if d.get("diagnostico") == "bien_fechada" else 0,
        "residuo": int(residuo),
        "n_tramos": len(tramos),
        "diag": d.get("diagnostico") or "",
        "r_medio": float(np.nanmean(rs)) if rs else float("nan"),
    }


def _texto_correccion(delta: int) -> str:
    """Describe la corrección con la acción, no solo con el signo.

    COFECHA escribe "+1" o "-1" y deja que el usuario deduzca si hay que
    agregar o quitar. En la práctica esa deducción se equivoca seguido, así
    que acá se nombra la acción.

    Convención, verificada con series a las que se les quitó o duplicó un
    anillo en un año conocido: delta positivo = faltan anillos, hay que
    insertar; delta negativo = sobran, hay que eliminar. Es la misma que
    COFECHA, donde un desplazamiento de +1 señala un anillo ausente.
    """
    n = abs(int(delta))
    if delta > 0:
        return f"Insertar {n}" + (" anillo" if n == 1 else " anillos")
    if delta < 0:
        return f"Eliminar {n}" + (" anillo" if n == 1 else " anillos")
    return "Sin cambio"


def _buscar_y_priorizar(ref, problema, mitad_ventana, max_corr,
                         diagnostico=None, coleccion_std=None,
                         nombre_serie=None, **kwargs):
    """Busca correcciones y las reordena según el diagnóstico previo.

    La búsqueda por correlación sola puede encabezar con una corrección del
    signo equivocado (por ejemplo, quitar un anillo cuando lo que falta es
    agregarlo): a corta distancia ambas cosas mejoran la r de forma parecida.
    El diagnóstico sí sabe qué pasa —qué tramo está bien fechado y hacia dónde
    está corrido el otro—, así que se usa para priorizar las correcciones
    COHERENTES con él: el signo correcto y cerca del año localizado.
    """
    sugerencias, es_marginal = buscar_correcciones(
        ref, problema, mitad_ventana, max_corr, **kwargs)
    if not sugerencias:
        return sugerencias, es_marginal

    # VERIFICACIÓN REAL de las mejores candidatas: en vez de confiar en la
    # métrica interna de la búsqueda (que trabaja sobre arreglos ya
    # transformados y con un relleno aproximado para el anillo nuevo), se
    # aplica cada candidata a la serie CRUDA, se vuelve a estandarizar y se
    # mide la correlación resultante. Sin esto la lista podía encabezar con
    # una corrección del signo equivocado: en una serie a la que le faltaba
    # un anillo, quitar otro daba r=0.256 mientras que insertarlo daba 0.349,
    # y aun así aparecía primero el "quitar".
    tr_ref = kwargs.get("transformar_ref")
    tr_prob = kwargs.get("transformar_prob")
    anclaje = kwargs.get("anclaje", "corteza")
    _eval_r = None
    ref_years_g = ref_vals_g = None
    _r_base_g = float("nan")
    _hay_quiebre_confiable = False
    _informe_zona = None
    if tr_ref is not None and tr_prob is not None:
        try:
            d_ref = tr_ref(ref["Ancho_mm"]).dropna()
            ref_years_g = d_ref.index.to_numpy(np.int64)
            ref_vals_g = d_ref.to_numpy(dtype=float)

            def _eval_r(df2):
                """Correlación real de una serie ya corregida contra la referencia."""
                d2 = tr_prob(df2["Ancho_mm"]).dropna()
                com = d_ref.index.intersection(d2.index)
                if len(com) < 10:
                    return -np.inf
                a = d_ref.loc[com].to_numpy(dtype=float)
                b = d2.loc[com].to_numpy(dtype=float)
                r = _est.pearson(a, b)
                return r if np.isfinite(r) else -np.inf

            def _r_real(sug):
                df2 = aplicar_correccion(problema, int(sug["anio"]),
                                         int(sug["delta"]), anclaje=anclaje)
                return _eval_r(df2)

            # Correlación SIN corregir: cualquier candidata que no la supere
            # se descarta. Una sugerencia que baja la correlación no es una
            # corrección, y ofrecerla solo confunde.
            r_base = _eval_r(problema)
            _r_base_g = r_base

            for sug in sugerencias[:12]:
                sug["r_verificada"] = _r_real(sug)
            verificadas = [s for s in sugerencias[:12]
                           if np.isfinite(s.get("r_verificada", -np.inf))
                           and (not np.isfinite(r_base)
                                or s["r_verificada"] > r_base)]
            resto = [s for s in sugerencias[12:]
                     if s.get("delta_r", 0) > 0]

            # CONSISTENCIA: se calcula para las candidatas de cabeza y se
            # guarda para mostrarla, pero NO se usa para ordenar.
            #
            # La idea era prometedora: en vez de preguntar cuál sube más la
            # correlación —criterio que empata cuando dos candidatas separadas
            # por ocho años difieren en milésimas— preguntar cuál deja la
            # serie sin tramos desajustados. Se probó de verdad, aplicando
            # cada candidata y volviendo a diagnosticar, contra el año real
            # conocido en 120 series simuladas.
            #
            # No funciona. El diagnóstico de tramos solo ve residuos de ocho
            # años o más; a cuatro años no distingue nada, y justo ahí es
            # donde la correlación tampoco decide. Peor: de vez en cuando
            # marca como sucia la candidata CORRECTA por ruido, y eso la
            # manda abajo en la lista. Medido:
            #
            #   señal fuerte (r~0.73)   exacto   error medio
            #     solo correlación        62%       0.97 años
            #     por consistencia        58%       1.33 años
            #   señal débil (r~0.35)
            #     solo correlación        32%       3.17 años
            #     por consistencia        22%       3.67 años
            #
            # Filtrar por residuo grande manteniendo el orden por r tampoco
            # aporta (62% / 1.00 años). Así que el orden sigue siendo por
            # correlación verificada, y la consistencia se muestra como
            # información de apoyo para que el usuario la juzgue.
            for sug in verificadas[:5]:
                try:
                    df2 = aplicar_correccion(problema, int(sug["anio"]),
                                             int(sug["delta"]), anclaje=anclaje)
                    sug["consistencia"] = puntaje_consistencia(
                        tr_prob(df2["Ancho_mm"]).dropna(), d_ref,
                        ventana=12, paso=2, min_overlap=6)
                except Exception:
                    logger.debug("Falló evaluación de datación", exc_info=True)
                    pass

            def _clave(s):
                return (s.get("r_verificada", -np.inf)
                        * s.get("plausibilidad", 1.0))

            verificadas.sort(key=_clave, reverse=True)
            sugerencias = verificadas + resto

            # ── LOCALIZACIÓN POR PARTICIÓN ÓPTIMA ────────────────────
            # Reproduce el procedimiento manual: fijar el tramo que ya calza
            # con la cronología y mover solo el que falla, hasta encontrar el
            # año exacto donde se rompe la correlación.
            #
            # No es un refinamiento del buscador por correlación: es una
            # pregunta distinta. El buscador prueba correcciones y se queda
            # con la que más sube la r global, criterio que se aplana cuando
            # dos candidatas separadas por varios años difieren en milésimas.
            # Acá el AÑO DEL QUIEBRE es el parámetro que se estima, con cada
            # tramo usando todos sus datos.
            #
            # Medido en 120 series simuladas con el año conocido y el anillo
            # ausente en un año estrecho (que es donde ocurren de verdad):
            #
            #                        exacto    ±1     ±2
            #   buscador por r        20%     53%    73%
            #   partición óptima      80%     92%    97%
            #   partición, confiables 94%    100%   100%
            #
            # y el número de anillos faltantes sale correcto en el 100%.
            # Por eso estas candidatas van a la cabeza de la lista.
            # Se pide el INFORME completo, no un año único. Exigir un año
            # solo dejaba fuera cuatro de cada cinco series con error real,
            # porque el año exacto solo es afirmable en un tercio a la mitad
            # de los casos. En cambio la zona contiene el año verdadero en
            # 97-100% de las series reales probadas, y los cinco años mejor
            # ordenados de esa zona lo contienen en 67-100%.
            informe = None
            try:
                s_std = tr_prob(problema["Ancho_mm"]).dropna()
                # n_nulo=0: el nulo por rotación está mal especificado para
                # este uso (rechaza series que sí cofechan), así que no se
                # corre. El informe lo advierte en su propio texto.
                # Nulo de colección: el umbral sale de las OTRAS series
                # cargadas, que están fechadas. Es el único de los tres nulos
                # probados que controla los falsos positivos sin perder
                # detección.
                informe = _qb.informe_quiebre(
                    s_std, d_ref, max_desfase=10, n_nulo=0,
                    coleccion=coleccion_std,
                    excluir=nombre_serie)
                quiebres = _qb.mapa_de_quiebres(
                    s_std, d_ref, max_desfase=10,
                    max_quiebres=3)
            except Exception:
                logger.debug("Falló evaluación de datación", exc_info=True)
                quiebres = []

            por_quiebre = []
            vistos = set()
            # ── UNA SOLA FUENTE DE VERDAD ──────────────────────────
            # El recuadro «Error localizado» venía de `_diagnosticar_datacion`,
            # un análisis por ventanas anterior e independiente, cuyo
            # `delta_sugerido` además era SIEMPRE ±1 sin importar cuántos
            # anillos. El resultado eran tres cifras distintas en la misma
            # pantalla para el mismo problema: la tabla decía +1, el recuadro
            # -2 y el informe -4.
            #
            # Ahora, cuando hay informe, el recuadro se reescribe con SUS
            # números. El diagnóstico por ventanas sigue sirviendo para decidir
            # el anclaje y para ordenar, que es donde aporta.
            if informe and informe.get("delta") and isinstance(diagnostico, dict):
                _d = int(informe["delta"])
                _n = abs(_d)
                _acc = ("INSERTAR" if _d > 0 else "ELIMINAR")
                _rg = informe.get("rango_error") or informe.get("zona")
                _cands = [str(int(a)) for a, _ in
                          (informe.get("candidatos") or [])[:5]]
                _tr = informe.get("tramos") or []
                _txt = ""
                if len(_tr) >= 2:
                    _b, _m = _tr[-1], _tr[0]
                    _txt = (f"El tramo {_b['inicio']}–{_b['fin']} calza bien "
                            f"(r≈{_b['r']:.2f}) y el tramo "
                            f"{_m['inicio']}–{_m['fin']} calza mejor desplazado "
                            f"{_m['desfase']:+d}.<br>")
                _txt += (f"<b>Hay que {_acc} {_n} anillo"
                         + ("s" if _n != 1 else "") + "</b>")
                if _rg:
                    _txt += f" <b>entre {_rg[0]} y {_rg[1]}</b>"
                if _cands:
                    _txt += ("<br><b>Años más probables</b> (estrechos en la "
                             "cronología, revísalos primero): "
                             + ", ".join(_cands))
                _txt += (". Se ancla en "
                         + ("corteza" if diagnostico.get("anclaje_sugerido",
                                                         "corteza") == "corteza"
                            else "médula")
                         + " para no mover el tramo ya fechado.")
                diagnostico["mensaje"] = _txt
                diagnostico["delta_sugerido"] = _d
                diagnostico["rango"] = _rg

            # Cada año candidato de la zona entra como una fila propia, con
            # la corrección ya aplicada, para que el usuario pueda probarlos
            # sin adivinar. Van ordenados por lo estrecho que es ese año en
            # la cronología, que es donde de verdad aparecen los ausentes.
            if informe and informe.get("candidatos") and informe.get("delta"):
                for a_cand, estrechez in informe["candidatos"]:
                    clave = (int(a_cand), int(informe["delta"]))
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    try:
                        df2 = aplicar_correccion(problema, int(a_cand),
                                                 int(informe["delta"]),
                                                 anclaje=anclaje)
                    except Exception:
                        logger.debug("Falló evaluación de datación", exc_info=True)
                        continue
                    r_v = _eval_r(df2)
                    if not np.isfinite(r_v):
                        continue
                    por_quiebre.append({
                        "anio": int(a_cand), "delta": int(informe["delta"]),
                        "tipo": _texto_correccion(int(informe["delta"])),
                        "r_antes": float(_r_base_g), "r_tras": float(r_v),
                        "delta_r": (float(r_v - _r_base_g)
                                    if np.isfinite(_r_base_g)
                                    else float("nan")),
                        "r_zona_antes": float("nan"),
                        "r_zona_tras": float("nan"),
                        "df_corregido": df2, "r_verificada": float(r_v),
                        "plausibilidad": 1.0 + max(estrechez, 0.0),
                        "origen": "zona",
                        "confiable": False,
                        "estrechez": float(estrechez),
                        "zona": informe.get("zona"),
                        "texto": informe.get("texto"),
                        "tramos": informe.get("tramos"),
                        "perfil": informe.get("perfil"),
                    })

            # lo que venía del buscador por correlación (sin duplicar años).
            # Orden: primero lo confiable; después los años de la ZONA, que
            # heredan el delta del informe (correcto en 70-100% de los casos
            # reales); al final las candidatas crudas de la cascada, que
            # pueden proponer deltas grandes y poco creíbles.
            for q in quiebres:
                if q.get("anio") is None or not q.get("delta"):
                    continue
                clave = (int(q["anio"]), int(q["delta"]))
                if clave in vistos:
                    continue
                vistos.add(clave)
                try:
                    df2 = aplicar_correccion(problema, int(q["anio"]),
                                             int(q["delta"]), anclaje=anclaje)
                except Exception:
                    logger.debug("Falló evaluación de datación", exc_info=True)
                    continue
                r_v = _eval_r(df2)
                if not np.isfinite(r_v):
                    continue
                por_quiebre.append({
                    "anio": int(q["anio"]), "delta": int(q["delta"]),
                    "tipo": _texto_correccion(int(q["delta"])),
                    "r_antes": float(_r_base_g),
                    "r_tras": float(r_v),
                    "delta_r": (float(r_v - _r_base_g)
                                if np.isfinite(_r_base_g) else float("nan")),
                    "r_zona_antes": float("nan"),
                    "r_zona_tras": float("nan"),
                    "df_corregido": df2,
                    "r_verificada": float(r_v),
                    "plausibilidad": (
                        _plausibilidad_anillo_estrecho(
                            ref_years_g, ref_vals_g, int(q["anio"]),
                            int(q["delta"]))
                        if ref_vals_g is not None else 1.0),
                    "origen": "quiebre",
                    "confiable": bool(q.get("confiable")),
                    "nitidez": int(q.get("nitidez", 0)),
                    "rango": q.get("rango"),
                    "perfil": q.get("perfil"),
                    "ganancia_quiebre": float(q.get("ganancia", float("nan"))),
                })

            # Primero las confiables, después el resto del quiebre, y al final
            # Dentro de la zona el orden es POR ESTRECHEZ, no por r. Es el
            # ranking que se validó: mezclarle la correlación verificada lo
            # desordena, porque entre años vecinos de la zona la r difiere en
            # milésimas y esas milésimas son ruido, mientras que lo estrecho
            # del anillo en la cronología sí informa dónde pudo faltar uno.
            por_quiebre.sort(
                key=lambda x: (
                    x["confiable"],
                    x.get("origen") == "zona",
                    (x.get("estrechez", 0.0) if x.get("origen") == "zona"
                     else x["r_verificada"])),
                reverse=True)
            claves_q = {(x["anio"], x["delta"]) for x in por_quiebre}
            sugerencias = por_quiebre + [
                x for x in sugerencias
                if (x.get("anio"), x.get("delta")) not in claves_q]

            # Fuera las candidatas que EMPEORAN la correlación. Nadie las va a
            # elegir, y llenan la tabla de ruido que estorba para encontrar
            # las que sirven.
            def _mejora(x):
                d = x.get("delta_r")
                if d is None or not np.isfinite(d):
                    a, b = x.get("r_antes"), x.get("r_tras")
                    if a is None or b is None:
                        return True          # sin dato: no se descarta
                    d = b - a
                return d > 0
            utiles = [x for x in sugerencias if _mejora(x)]
            if utiles:
                sugerencias = utiles
            _hay_quiebre_confiable = any(x["confiable"] for x in por_quiebre)
            if informe is not None:
                _informe_zona = informe
        except Exception:
            logger.debug("Falló evaluación de datación", exc_info=True)
            pass

    # Un quiebre CONFIABLE manda sobre el diagnóstico por ventanas. El
    # diagnóstico agrupa ventanas de largo fijo y acierta el signo con menos
    # frecuencia; dejar que filtre por su `delta_sugerido` descartaría justo
    # la candidata que las pruebas muestran correcta en el 100% de los casos.
    if _hay_quiebre_confiable:
        return sugerencias, False

    if not diagnostico:
        return sugerencias, es_marginal

    tipo = diagnostico.get("diagnostico")

    # Con un desfase de TODA la serie, proponer insertar o quitar un anillo
    # suelto es engañoso: lo que corresponde es corregir el año base. Se
    # devuelven cero sugerencias para no mandar al usuario a buscar un anillo
    # que no falta.
    if tipo == "desfase_global":
        return [], True

    if tipo == "ambiguo":
        # Sin dirección segura NO se muestra una sola opción: eso induciría a
        # buscar en la madera justo lo contrario de lo que puede haber. Se
        # ofrecen las mejores candidatas de AMBOS sentidos, alternadas, para
        # que sea la madera la que decida.
        pos = [s for s in sugerencias if s.get("delta", 0) > 0]
        neg = [s for s in sugerencias if s.get("delta", 0) < 0]
        mezcla = []
        for i in range(max(len(pos), len(neg))):
            if i < len(pos):
                mezcla.append(pos[i])
            if i < len(neg):
                mezcla.append(neg[i])
        return (mezcla or sugerencias), True

    if tipo != "error_interno":
        return sugerencias, es_marginal

    delta_ok = diagnostico.get("delta_sugerido")
    anio_ref = diagnostico.get("anio_error")
    if not delta_ok or anio_ref is None:
        return sugerencias, es_marginal

    # COHERENCIA: nunca mostrar correcciones del signo CONTRARIO al que dice
    # el diagnóstico. Si el análisis concluyó que falta un anillo, ofrecer
    # "quitar un anillo" manda al usuario a buscar justo lo opuesto de lo que
    # hay en la madera, y eso destruye la confianza en la herramienta. Es
    # preferible mostrar menos opciones —o ninguna— que opciones contrarias.
    coherentes = [s for s in sugerencias if s.get("delta") == delta_ok]

    # Si la búsqueda global no encontró ninguna del signo correcto (pasa
    # cuando la mejora no supera el umbral general), se generan candidatas
    # explícitas alrededor del año localizado y se evalúan de verdad.
    if not coherentes and _eval_r is not None:
        generadas = []
        for anio in range(int(anio_ref) - 25, int(anio_ref) + 26):
            try:
                df2 = aplicar_correccion(problema, int(anio), int(delta_ok),
                                         anclaje=anclaje)
            except Exception:
                logger.debug("Falló evaluación de datación", exc_info=True)
                continue
            r_v = _eval_r(df2)
            if not np.isfinite(r_v):
                continue
            if np.isfinite(_r_base_g) and r_v <= _r_base_g:
                continue  # no mejora: no se ofrece
            generadas.append({
                "anio": int(anio), "delta": int(delta_ok),
                "tipo": (f"+{delta_ok} anillo(s)" if delta_ok > 0
                         else f"{delta_ok} anillo(s)"),
                "r_antes": float("nan"), "r_tras": r_v,
                "delta_r": float("nan"), "r_zona_antes": float("nan"),
                "r_zona_tras": float("nan"), "df_corregido": df2,
                "r_verificada": r_v,
                "plausibilidad": _plausibilidad_anillo_estrecho(
                    ref_years_g, ref_vals_g, anio, delta_ok)
                if ref_vals_g is not None else 1.0,
            })
        if generadas:
            generadas.sort(key=lambda s: s["r_verificada"] * s.get("plausibilidad", 1.0),
                           reverse=True)
            coherentes = generadas[:10]
            es_marginal = True  # ninguna superó el umbral global


    coherentes = sorted(coherentes, key=lambda sug: clave_prioridad_correccion(sug, anio_ref), reverse=True)
    return coherentes, es_marginal


from dpi.ciencia.diagnostico import diagnosticar_datacion




# =============================================================================
# MODO COFECHA
# =============================================================================

def aplicar_modo_cofecha(serie_mm, rigidez_spline=32, aplicar_log=True,
                          aplicar_ar=True, aplicar_first_diff=False):
    """Spline detrending + log + AR(1). Holmes (1983)."""
    s = pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
    if len(s) < 10:
        return s.copy()

    valores = s.to_numpy(dtype=float)

    try:
        from scipy.interpolate import UnivariateSpline
        x = np.arange(len(valores), dtype=float)
        s_factor = max(
            np.var(valores) * len(valores) * (rigidez_spline / max(len(valores), 1)) ** 1.5,
            1e-3,
        )
        spl = UnivariateSpline(x, valores, s=s_factor)
        tendencia = spl(x)
        tendencia = np.where(tendencia <= 0, np.nanmean(valores), tendencia)
        valores = valores / tendencia
    except Exception as exc:
        logger.warning("Spline COFECHA falló: %s", exc)
        valores = valores / np.mean(valores)

    if aplicar_log:
        media = np.mean(valores)
        c_const = media / 6.0 if media > 0 else 0.001
        valores = np.log(np.maximum(valores + c_const, 1e-10))

    if aplicar_ar and len(valores) > 4:
        c = valores - np.mean(valores)
        if np.std(c) > 0:
            phi = _est.pearson(c[1:], c[:-1])
            if np.isnan(phi):
                phi = 0.0
            phi = float(np.clip(phi, -0.99, 0.99))
            residuales = c.copy()
            residuales[1:] = c[1:] - phi * c[:-1]
            valores = residuales

    if aplicar_first_diff and len(valores) > 1:
        return _est.diferencias_anuales(pd.Series(valores, index=s.index))

    return pd.Series(valores, index=s.index)
