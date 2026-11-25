"""
MoiCedrus — DPI · Localización del año exacto del error de datación
====================================================================

Reproduce el procedimiento manual del dendrocronólogo: tomar la serie, irla
moviendo año por año contra la cronología, quedarse con el tramo que ya
correlaciona bien y seguir moviendo solo el tramo que falla. El resultado es
el año preciso donde se rompe la correlación y cuántos anillos faltan o
sobran a cada lado.

Diferencia con `diagnosticar_datacion`
--------------------------------------
Aquel evalúa ventanas de largo fijo y cada una vota por su cuenta cuál es su
mejor desfase; después agrupa las ventanas vecinas que coinciden. Su
resolución no puede ser mejor que el largo de la ventana, y con ventanas
cortas la correlación se vuelve ruidosa: en las pruebas detectaba residuos de
ocho años pero no de cuatro.

Acá el año del quiebre es el PARÁMETRO que se estima, no un subproducto. Para
cada año candidato `b` y cada desfase `k` se evalúa la partición completa:
el tramo desde `b` en adelante alineado a desfase 0, y el tramo anterior a
`b` alineado a desfase `k`. Se elige la combinación que maximiza la
correlación conjunta. Como cada lado usa TODOS sus datos, la estimación del
año no depende del largo de ninguna ventana.

Costo
-----
Ingenuamente sería O(años × desfases × largo). Con las sumas acumuladas de
`dpi.ciencia.cofecha_nucleo` cada partición se evalúa en tiempo constante, así que
el total queda en O(años × desfases): unos milisegundos para una serie de
varios siglos y ±10 años de desfase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import pearson, centrar_escalar_correlacion

import dpi.ciencia.cofecha_nucleo as _nuc


def _alinear(serie_std: pd.Series, crono_std: pd.Series):
    """Deja serie y cronología sobre una grilla común de años, sin huecos."""
    a = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    b = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()
    if a.empty or b.empty:
        return None
    y0 = int(min(a.index.min(), b.index.min())) - 12
    y1 = int(max(a.index.max(), b.index.max())) + 12
    anios = np.arange(y0, y1 + 1, dtype=np.int64)
    x = np.full(anios.size, np.nan)
    y = np.full(anios.size, np.nan)
    x[np.asarray(a.index, dtype=np.int64) - y0] = a.to_numpy(dtype=float)
    y[np.asarray(b.index, dtype=np.int64) - y0] = b.to_numpy(dtype=float)
    return anios, x, y


def _acumulados_por_desfase(x, y, max_desfase):
    """Sumas acumuladas del par para cada desfase, listas para combinar."""
    # Centrar antes de desplazar: todos los bloques comparten referencia.
    x = centrar_escalar_correlacion(x)[0]
    y = centrar_escalar_correlacion(y)[0]
    n = x.size
    acum = {}
    for k in range(-max_desfase, max_desfase + 1):
        yy = np.full(n, np.nan)
        if k >= 0:
            if n - k > 0:
                yy[:n - k] = y[k:]
        else:
            yy[-k:] = y[:n + k]
        acum[k] = _nuc.AcumuladosPar(x, yy)
    return acum


def tramo_minimo(n_anios: int) -> int:
    """Años mínimos que debe tener cada tramo de la partición.

    Un valor fijo no sirve para todos los largos, y era la causa de que el
    roble rindiera mal: sus series tienen 84-150 anillos y exigirles 15 años a
    cada lado dejaba poco material para estimar la partición.

    La regla es una décima parte de la serie, entre 10 y 30 años. Medido sobre
    las cuatro especies, borrando un anillo en un año conocido:

                        roble          ciprés         lenga
                     zona  top5      zona  top5     zona  top5
        fijo 15       91%   82%      100%   64%      95%   50%
        fijo 12      100%   91%      100%   55%     100%   55%
        n/10         100%   91%      100%   68%     100%   55%

    La regla adaptativa iguala o supera al mejor valor fijo en las cuatro:
    las series cortas necesitan tramos chicos para tener dos tramos, y las
    largas se benefician de tramos grandes porque estabilizan la correlación.
    """
    return int(np.clip(n_anios // 10, 10, 30))


def localizar_quiebre(serie_std: pd.Series, crono_std: pd.Series,
                       max_desfase: int = 10, min_tramo: int | None = None,
                       margen_r: float = 0.0):
    """Busca el año exacto donde se rompe la correlación.

    Devuelve un diccionario con:

      anio          año donde aplicar la corrección (último del tramo mal
                    fechado); es el argumento que espera `aplicar_correccion`
      anio_quiebre  primer año del tramo bien fechado (= anio + 1)
      delta         cuántos anillos insertar (+) o quitar (−) en `anio`
      confiable     siempre False aquí; solo `evaluar_con_nulo` puede
                    ponerlo en True, porque hace falta el nulo para decidirlo
      r             correlación conjunta con la partición aplicada
      r_sin_quiebre correlación sin partir (todo a desfase 0)
      ganancia      r − r_sin_quiebre
      n_izq, n_der  años efectivos a cada lado
      perfil        lista (año, mejor r) para graficar la nitidez del quiebre
      nitidez       cuántos años alrededor del óptimo quedan dentro de
                    margen_r; 1 significa que el año está determinado

    Convención de signos: el tramo RECIENTE (desde `anio` en adelante) se
    toma como bien fechado y queda a desfase 0; el tramo ANTIGUO es el que se
    mueve. Es lo correcto para una serie fechada desde la corteza. Un desfase
    k > 0 del tramo antiguo significa que a la serie le FALTAN k anillos
    antes de `anio` (delta = +k).
    """
    vacio = {"anio": None, "delta": 0, "r": float("nan"),
             "r_sin_quiebre": float("nan"), "ganancia": float("nan"),
             "n_izq": 0, "n_der": 0, "perfil": [], "nitidez": 0}
    al = _alinear(serie_std, crono_std)
    if al is None:
        return vacio
    anios, x, y = al
    if min_tramo is None:
        min_tramo = tramo_minimo(int(np.isfinite(x).sum()))
    acum = _acumulados_por_desfase(x, y, max_desfase)

    hay = np.isfinite(x)
    if hay.sum() < 2 * min_tramo + 5:
        return vacio
    pos = np.flatnonzero(hay)
    i0, i1 = int(pos[0]), int(pos[-1]) + 1

    r_base, _n = acum[0].r(i0, i1)

    # Índices candidatos de quiebre: hay que dejar min_tramo años con dato
    # a cada lado. Se recorre sobre el acumulado de datos presentes para no
    # proponer cortes en huecos.
    presentes = np.cumsum(hay.astype(int))
    total = presentes[i1 - 1] - (presentes[i0 - 1] if i0 > 0 else 0)
    if total < 2 * min_tramo:
        return vacio

    mejor = None
    perfil = []
    for b in range(i0 + 1, i1):
        izq = presentes[b - 1] - (presentes[i0 - 1] if i0 > 0 else 0)
        der = total - izq
        if izq < min_tramo or der < min_tramo:
            continue
        s_der = acum[0].sumas(b, i1)
        mejor_b = None
        for k in range(-max_desfase, max_desfase + 1):
            if k == 0:
                continue
            s_izq = acum[k].sumas(i0, b)
            if s_izq[0] < min_tramo or s_der[0] < min_tramo:
                continue
            r, n = _nuc.r_de_sumas(s_izq, s_der)
            if not np.isfinite(r):
                continue
            if mejor_b is None or r > mejor_b[0]:
                mejor_b = (r, k, int(s_izq[0]), int(s_der[0]))
        if mejor_b is None:
            continue
        perfil.append((int(anios[b]), float(mejor_b[0]), int(mejor_b[1])))
        if mejor is None or mejor_b[0] > mejor[0]:
            mejor = (mejor_b[0], mejor_b[1], mejor_b[2], mejor_b[3], b)

    if mejor is None:
        return vacio

    r, k, n_izq, n_der, b = mejor
    # Nitidez: cuántos años candidatos quedan a menos de `margen_r` del
    # óptimo. Si son muchos, el año no está determinado y hay que informarlo
    # como rango en vez de como año único.
    if margen_r <= 0:
        margen_r = 0.01
    cerca = [a for a, rr, _kk in perfil if rr >= r - margen_r]

    # Ganancia bruta. Por sí sola NO dice nada: esta búsqueda explora unos
    # 21 desfases por cientos de años candidatos y por puro azar consigue
    # ganancias de 0,12 a 0,22 en series bien fechadas. Quien decide si el
    # año es creíble es `evaluar_con_nulo`, comparando contra esa misma
    # búsqueda hecha sobre una cronología rotada.
    #
    # Por eso `confiable` sale SIEMPRE en False desde aquí: antes había un
    # umbral fijo de 0,01 que marcaba como creíble casi cualquier cosa, y
    # dejarlo puesto era una trampa para quien llamara a esta función suelta.
    ganancia = (r - r_base) if np.isfinite(r_base) else float("nan")
    confiable = False

    # CONVENCIÓN, verificada contra 120 series con el año conocido:
    #   b  = primer año del tramo BIEN fechado (el reciente, a desfase 0)
    #   b-1 = último año del tramo mal fechado, que es DONDE va la corrección
    # El anillo que falta está justo antes del quiebre, no en él: sin este
    # ajuste la estimación salía sesgada exactamente +1 año en 48 de 60 casos.
    #
    # Signo: k es cuánto hay que MOVER el tramo antiguo. Si el tramo antiguo
    # calza corrido -1 año, es porque a la serie le falta un anillo ahí, así
    # que la corrección es INSERTAR: delta = -k.
    return {
        "anio_quiebre": int(anios[b]),
        "anio": int(anios[b]) - 1,
        "delta": int(-k),
        "r": float(r),
        "r_sin_quiebre": float(r_base),
        "ganancia": float(r - r_base) if np.isfinite(r_base) else float("nan"),
        "n_izq": n_izq, "n_der": n_der,
        "perfil": perfil,
        "nitidez": len(cerca),
        "confiable": confiable,
        "rango": (min(cerca), max(cerca)) if cerca else None,
    }


def mapa_de_quiebres(serie_std: pd.Series, crono_std: pd.Series,
                      max_desfase: int = 10, min_tramo: int | None = None,
                      max_quiebres: int = 3, ganancia_minima: float = 0.02,
                      n_nulo: int = 40):
    """Aplica `localizar_quiebre` en cascada sobre el tramo que sigue fallando.

    Es el procedimiento manual completo: se fija el tramo que ya calza, se
    corrige el que no, y se vuelve a mirar por si queda otro error más atrás.
    Se detiene cuando un quiebre nuevo no mejora la correlación al menos
    `ganancia_minima`, o cuando ya no quedan años suficientes.

    Cada quiebre se evalúa con `evaluar_con_nulo`, así que el campo
    `confiable` ya viene calibrado contra lo que la misma búsqueda consigue
    por azar. Con `n_nulo=0` se salta esa calibración (más rápido, pero el
    `confiable` queda siempre en False, que es lo honesto: sin el nulo no hay
    forma de saber si la ganancia supera al azar).

    Devuelve la lista de quiebres, del más reciente al más antiguo, con el
    desfase ACUMULADO que hay que aplicar antes de cada uno.
    """
    s = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    quiebres = []
    acumulado = 0
    for _ in range(max_quiebres):
        if n_nulo and n_nulo > 0:
            q = evaluar_con_nulo(s, crono_std, n_nulo=n_nulo,
                                 max_desfase=max_desfase, min_tramo=min_tramo)
        else:
            q = localizar_quiebre(s, crono_std, max_desfase=max_desfase,
                                  min_tramo=min_tramo)
        if q["anio"] is None or not np.isfinite(q["ganancia"]):
            break
        if q["ganancia"] < ganancia_minima:
            break
        acumulado += q["delta"]
        q["delta_acumulado"] = acumulado
        quiebres.append(q)
        # Corregir el tramo antiguo y volver a buscar más atrás
        idx = s.index.to_numpy(np.int64)
        nuevo = np.where(idx <= q["anio"], idx - q["delta"], idx)
        s = pd.Series(s.to_numpy(dtype=float), index=nuevo).sort_index()
        s = s[~s.index.duplicated(keep="first")]
    return quiebres


def evaluar_con_nulo(serie_std: pd.Series, crono_std: pd.Series,
                      n_nulo: int = 40, percentil: float = 95.0,
                      semilla: int = 0, **kwargs) -> dict:
    """Localiza el quiebre y decide si es creíble comparándolo con el azar.

    POR QUÉ HACE FALTA
    ------------------
    `localizar_quiebre` explora unos 21 desfases × varios cientos de años
    candidatos, o sea del orden de miles de configuraciones. Con esa libertad
    SIEMPRE encuentra una partición que sube la correlación, aunque la serie
    esté perfectamente fechada. Medido en las colecciones reales de ciprés y
    de lenga, la ganancia máxima obtenida por puro azar promedia 0,12–0,22 y
    su percentil 95 llega a 0,41. Un umbral fijo de 0,01 —el que tenía— daba
    por buena cualquier cosa: marcaba error en una de cada tres series
    correctamente fechadas.

    CÓMO SE CONSTRUYE EL NULO
    -------------------------
    Se corre exactamente la misma búsqueda, con la misma libertad, contra la
    cronología rotada circularmente un número grande de años al azar. Eso
    conserva la autocorrelación y la varianza de la cronología, pero destruye
    la correspondencia temporal, así que cualquier quiebre que aparezca es por
    azar. La ganancia real se compara con esa distribución.

    Es la misma lógica de nulo con la misma libertad de ajuste que usamos para
    las series de Juan Fernández: sin ella, la búsqueda se evalúa contra un
    umbral que no tiene nada que ver con lo que consigue el azar.

    Devuelve el diccionario de `localizar_quiebre` más:
      umbral_nulo   ganancia en el percentil pedido de la distribución nula
      ganancia_nula ganancia media del azar
      p_valor       fracción del nulo que iguala o supera la ganancia real
      confiable     True solo si la ganancia real supera el umbral del nulo
    """
    q = localizar_quiebre(serie_std, crono_std, **kwargs)
    q["umbral_nulo"] = float("nan")
    q["ganancia_nula"] = float("nan")
    q["p_valor"] = float("nan")
    if q.get("anio") is None or not np.isfinite(q.get("ganancia", np.nan)):
        q["confiable"] = False
        return q

    c = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()
    v = c.to_numpy(dtype=float)
    idx = c.index.to_numpy()
    if v.size < 100:
        q["confiable"] = False
        return q

    rng = np.random.default_rng(semilla)
    minimo = max(40, v.size // 10)
    ganancias = []
    for _ in range(int(n_nulo)):
        k = int(rng.integers(minimo, max(minimo + 1, v.size - minimo)))
        falsa = pd.Series(np.roll(v, k), index=idx)
        qn = localizar_quiebre(serie_std, falsa, **kwargs)
        g = qn.get("ganancia", np.nan)
        if np.isfinite(g):
            ganancias.append(float(g))

    if len(ganancias) < 10:
        q["confiable"] = False
        return q

    g = np.asarray(ganancias)
    umbral = float(np.percentile(g, percentil))
    q["umbral_nulo"] = umbral
    q["ganancia_nula"] = float(g.mean())
    q["p_valor"] = float((g >= q["ganancia"]).mean())
    # Se exige superar al azar Y que el óptimo no sea una meseta.
    q["confiable"] = bool(q["ganancia"] > umbral and q.get("nitidez", 99) <= 6)
    return q


def informe_quiebre(serie_std: pd.Series, crono_std: pd.Series,
                     n_candidatos: int = 8, n_nulo: int = 40,
                     coleccion: dict | None = None,
                     excluir: str | None = None, **kwargs) -> dict:
    """Entrega TODO lo que la serie permite afirmar, en vez de un año o nada.

    POR QUÉ ESTA FUNCIÓN REEMPLAZA AL CRITERIO BINARIO
    ---------------------------------------------------
    Exigir un año único obligaba al programa a callarse cuando no podía
    jugarse por uno solo, y eso dejaba fuera cuatro de cada cinco series con
    error real. Pero las tres preguntas que uno le hace a la serie no tienen
    la misma respuesta ni la misma confianza. Medido sobre series reales de
    ciprés, araucaria, roble y lenga, borrándoles un anillo en un año
    conocido:

        cuántos anillos faltan      70–100 % correcto
        el año exacto (±1)          33–53 %   — no es afirmable
        el rango contiene el año    97–100 %  con 28–54 años de ancho
        top 5 años del rango        70–93 %   contiene el año real

    Así que el informe afirma el número de anillos, entrega el rango como
    intervalo y ordena los años de ese rango por probabilidad, en vez de
    apostar a uno o quedarse mudo.

    EL INTERVALO
    ------------
    Un año candidato entra al rango si su correlación no se distingue de la
    del óptimo: se comparan en escala z de Fisher y se admite todo lo que
    quede a menos de un error estándar, 1/√(n−3). No es un umbral inventado;
    es la precisión con la que se puede medir una correlación con esos datos.

    EL ORDEN DENTRO DEL RANGO
    -------------------------
    Un anillo ausente no aparece en cualquier año: aparece donde el año fue
    extremo y el árbol casi no formó leño. Por eso los años del rango se
    ordenan por lo estrecho que es ese año en la cronología. Es el mismo
    razonamiento que usa el dendrocronólogo al buscar años puntero, y es lo
    que lleva el trabajo de revisar 30–50 anillos a revisar cinco.

    Devuelve, además de todo lo de `localizar_quiebre`:
      tramos       los dos tramos con su extensión, n, r y desfase
      zona         (primer año, último año) del intervalo compatible
      candidatos   [(año, puntaje)] ordenados por probabilidad
      texto        frase lista para mostrar en la interfaz
    """
    # El veredicto NO puede apoyarse en la significancia nominal de los
    # tramos. Esa significancia supone una correlación calculada una sola vez,
    # y acá se eligió la mejor de miles de particiones: el nivel nominal queda
    # inflado. Comprobado con una serie de ruido puro, que salía «significativa
    # al 90 %» en los dos tramos. Quien decide es el nulo con la misma
    # libertad de búsqueda; los niveles de confianza quedan para DESCRIBIR
    # cada tramo, que es para lo que sirven.
    # Prioridad de nulos, de mejor a peor:
    #   1. La colección: mide el umbral sobre las otras series fechadas.
    #      6-11 % de falsos positivos y 78-100 % de detección.
    #   2. Sustitutas sintéticas, si hay pocas series: detecta todo pero deja
    #      pasar más falsos positivos.
    #   3. Ninguno: `confiable` queda en False y el informe lo advierte.
    if coleccion and len(coleccion) >= 9:
        q = evaluar_con_coleccion(serie_std, crono_std, coleccion,
                                  excluir=excluir, **kwargs)
    elif n_nulo and n_nulo > 0:
        q = evaluar_con_sustitutas(serie_std, crono_std, n_nulo=n_nulo,
                                   **kwargs)
    else:
        q = localizar_quiebre(serie_std, crono_std, **kwargs)
    q["tramos"] = []
    q["zona"] = None
    q["candidatos"] = []
    q["texto"] = "No hay información suficiente para evaluar el fechado."
    if q.get("anio") is None or not q.get("perfil"):
        return q

    perfil = q["perfil"]
    r_max = max(r for _a, r, _k in perfil)
    n_tot = max(q.get("n_izq", 0) + q.get("n_der", 0), 8)
    se = 1.0 / np.sqrt(max(n_tot - 3, 4))

    def _z(r):
        return float(np.arctanh(np.clip(r, -0.999999, 0.999999)))

    z_max = _z(r_max)
    # OJO: `perfil` está indexado por el AÑO DEL QUIEBRE (primer año del tramo
    # bien fechado). El año donde va la corrección —y donde está el anillo que
    # falta— es el anterior. Sin este −1 la zona y los candidatos salían
    # corridos un año respecto de `anio`.
    compatibles = [(a - 1, r) for a, r, _k in perfil if _z(r) >= z_max - se]
    if not compatibles:
        compatibles = [(q["anio"], r_max)]
    a0 = min(a for a, _ in compatibles)
    a1 = max(a for a, _ in compatibles)
    q["zona"] = (int(a0), int(a1))

    # Los dos tramos, descritos en años reales
    s = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    corte = q["anio_quiebre"]
    izq = s[s.index < corte]
    der = s[s.index >= corte]
    c = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()

    def _r_tramo(tramo, desfase):
        if tramo.empty:
            return float("nan"), 0
        movida = pd.Series(tramo.to_numpy(dtype=float),
                           index=tramo.index.to_numpy(np.int64) + desfase)
        com = movida.index.intersection(c.index)
        if len(com) < 5:
            return float("nan"), len(com)
        x = movida.loc[com].to_numpy(dtype=float)
        y = c.loc[com].to_numpy(dtype=float)
        return pearson(x, y, tolerancia=1e-12), len(com)

    # El tramo antiguo se mueve -delta (delta = anillos a insertar)
    r_izq, n_izq = _r_tramo(izq, -int(q["delta"]))
    r_izq0, _ = _r_tramo(izq, 0)
    r_der, n_der = _r_tramo(der, 0)
    if not izq.empty:
        q["tramos"].append({
            "inicio": int(izq.index.min()), "fin": int(izq.index.max()),
            "n": n_izq, "r": r_izq, "r_sin_corregir": r_izq0,
            "desfase": -int(q["delta"]), "estado": "requiere corrección"})
    if not der.empty:
        q["tramos"].append({
            "inicio": int(der.index.min()), "fin": int(der.index.max()),
            "n": n_der, "r": r_der, "r_sin_corregir": r_der,
            "desfase": 0, "estado": "bien fechado"})

    # Orden de los años candidatos por lo estrecho del anillo en la cronología
    if len(c) > 5 and float(c.std()) > 0:
        z_crono = (c - c.mean()) / c.std()
    else:
        z_crono = c * 0.0
    puntuados = []
    for a, r in compatibles:
        estrechez = -float(z_crono.get(a, 0.0))
        puntuados.append((int(a), float(estrechez), float(r)))
    puntuados.sort(key=lambda t: -t[1])
    q["candidatos"] = [(a, e) for a, e, _r in puntuados[:n_candidatos]]

    # ── Calificar la correlación antes de afirmar nada ────────────────
    # El informe decía "la correlación es buena" pasara lo que pasara. Con una
    # serie que no cofecha eso producía frases como «de 2010 a 2024 la
    # correlación es buena (r = 0.08)», que es justo lo contrario de lo que
    # los datos dicen y manda al usuario a buscar un anillo inexistente.
    #
    # Pero exigir el 99 % que usa COFECHA para MARCAR segmentos es demasiado
    # duro acá: COFECHA lo usa para levantar sospechas sobre series ya
    # fechadas, mientras que este informe está orientando una revisión que
    # todavía no ha ocurrido. Así que se informan tres niveles —90, 95 y 99 %—
    # y se nombra el más alto que el tramo alcanza. Un tramo al 90 % no es
    # prueba, pero sí es una pista que vale la pena seguir.
    NIVELES = (99, 95, 90)

    def _critico(n, conf):
        if n is None or n < 5:
            return float("nan")
        alfa = (100 - conf) / 100.0
        try:
            from scipy import stats as _st
            t = _st.t.ppf(1 - alfa, n - 2)
        except Exception:
            t = {99: 2.33, 95: 1.645, 90: 1.282}[conf]
        return float(t / np.sqrt(t * t + n - 2))

    def _calificar(r, n):
        """Devuelve (texto, nivel de confianza alcanzado o 0)."""
        if r is None or not np.isfinite(r):
            return "sin datos suficientes", 0
        for conf in NIVELES:
            c = _critico(n, conf)
            if np.isfinite(c) and r >= c:
                return f"r = {r:.2f}, significativa al {conf} % (n = {n})", conf
        c90 = _critico(n, 90)
        if not np.isfinite(c90):
            return f"r = {r:.2f}, tramo muy corto para evaluarla (n = {n})", 0
        return (f"r = {r:.2f}, no alcanza el 90 % (haría falta {c90:.2f} "
                f"con n = {n})"), 0

    # Texto EXPLÍCITO sobre la acción, no solo el signo.
    #
    # COFECHA informa "+1" o "-1" y el usuario tiene que deducir si eso
    # significa agregar o quitar un anillo. Acá se dice con todas las letras.
    #
    # La convención de DPI, verificada con series a las que se les quitó o
    # duplicó un anillo conocido: delta POSITIVO significa que a la serie le
    # FALTAN anillos y hay que INSERTARLOS; delta negativo, que le SOBRAN y
    # hay que ELIMINARLOS. Coincide con COFECHA, donde un desplazamiento de
    # +1 indica un anillo ausente.
    cuantos = abs(int(q["delta"]))
    if q["delta"] > 0:
        signo = "faltan"
        accion = (f"hay que INSERTAR {cuantos} anillo(s)" if cuantos != 1
                  else "hay que INSERTAR 1 anillo")
    else:
        signo = "sobran"
        accion = (f"hay que ELIMINAR {cuantos} anillo(s)" if cuantos != 1
                  else "hay que ELIMINAR 1 anillo")
    q["accion"] = accion
    anios_txt = ", ".join(str(a) for a, _ in q["candidatos"][:5])
    partes = []
    niv_der = niv_izq = 0
    if q["tramos"]:
        t = q["tramos"][-1]
        txt, niv_der = _calificar(t["r"], t["n"])
        partes.append(f"De {t['inicio']} a {t['fin']}: {txt}.")
    if len(q["tramos"]) > 1:
        t = q["tramos"][0]
        txt_c, niv_izq = _calificar(t["r"], t["n"])
        partes.append(
            f"De {t['inicio']} a {t['fin']}: r = {t['r_sin_corregir']:.2f} "
            f"sin corregir, sube a {txt_c} al correr el tramo "
            f"{abs(t['desfase'])} año(s).")

    q["nivel_der"] = niv_der
    q["nivel_izq"] = niv_izq
    q["nivel"] = min(niv_der, niv_izq) if (niv_der and niv_izq) else 0
    q["tramos_significativos"] = int(niv_der > 0) + int(niv_izq > 0)
    if not (niv_der or niv_izq):
        # Ningún tramo alcanza significancia: la serie no cofecha con esta
        # referencia y proponer un año sería inventar precisión.
        q["cofecha"] = False
        partes.append(
            "NINGÚN tramo llega siquiera al 90 %, así que esta serie no "
            "cofecha con la referencia. La corrección de abajo es lo mejor "
            "que encuentra la búsqueda, pero no tiene respaldo: no vale la "
            "pena ir a buscar el anillo. Antes conviene revisar si la "
            "referencia corresponde al sitio, si la serie está bien medida "
            "y si tiene largo suficiente.")
    elif not (niv_der and niv_izq):
        q["cofecha"] = None
        lado = "el tramo reciente" if niv_der else "el tramo antiguo"
        partes.append(
            f"Solo {lado} alcanza significancia, así que el resultado es "
            "indicativo: sirve para orientar la revisión, no para dar por "
            "fechada la serie.")
    else:
        q["cofecha"] = True
        if q["nivel"] < 99:
            partes.append(
                f"Los dos tramos son significativos, el más débil al "
                f"{q['nivel']} %.")

    # Advertencia permanente sobre el nivel nominal.
    #
    # Los porcentajes de arriba son los de una correlación calculada UNA vez.
    # Acá se eligió la mejor de miles de particiones, así que están inflados y
    # hay que leerlos como descripción del tramo, no como prueba.
    #
    # Se probó calibrarlos con un nulo —la misma búsqueda contra la cronología
    # rotada— y NO sirve como veredicto: rotar destruye la señal, la base cae
    # a cero y cualquier partición gana mucho, de modo que el umbral queda tan
    # alto que rechaza series que sí cofechan. Verificado con COS300A a la que
    # se le borró el anillo de 1950: los dos tramos al 99 %, la corrección
    # correcta, y el nulo igual la rechazaba. Un nulo bien puesto tendría que
    # conservar la correlación de base y variar solo el quiebre; queda
    # pendiente construirlo.
    if q.get("cofecha") is not False:
        if q.get("nulo") == "coleccion" and np.isfinite(q.get("umbral_nulo", np.nan)):
            if q.get("confiable"):
                partes.append(
                    f"La mejora ({q['ganancia']:.2f}) SUPERA lo que esta misma "
                    f"búsqueda consigue en las otras {q.get('n_nulo_series', 0)} "
                    f"series de la colección, que están fechadas "
                    f"(umbral {q['umbral_nulo']:.2f}): el quiebre no se "
                    f"explica por la libertad del método.")
            else:
                partes.append(
                    f"ATENCIÓN: la mejora ({q['ganancia']:.2f}) NO supera lo que "
                    f"esta búsqueda consigue en las otras "
                    f"{q.get('n_nulo_series', 0)} series ya fechadas de la "
                    f"colección (umbral {q['umbral_nulo']:.2f}). El año de "
                    f"abajo es el mejor candidato, pero podría no haber ningún "
                    f"error que corregir.")
        else:
            partes.append(
                "Los niveles de confianza describen cada tramo, no prueban el "
                "quiebre: la búsqueda probó miles de posiciones y se quedó con "
                "la mejor, así que están algo inflados.")
    q["rango_error"] = (int(a0), int(a1))
    partes.append(f"Probablemente {signo} {cuantos} anillo(s) entre {a0} y "
                  f"{a1}: {accion} en uno de esos años.")
    if anios_txt:
        partes.append(f"Años más probables para revisar: {anios_txt}.")
    q["texto"] = " ".join(partes)
    return q


from dpi.ciencia import modelos_nulos as _nulos
from dpi.ciencia.modelos_nulos import _fase_aleatoria, _ruido_ar1


def evaluar_con_sustitutas(serie_std: pd.Series, crono_std: pd.Series, n_nulo: int=60, percentil: float=95.0, semilla: int=0, **kwargs) -> dict:
    """Decide si el quiebre es real, comparándolo con series SIN error."""
    return _nulos.evaluar_con_sustitutas(localizar_quiebre, serie_std, crono_std, n_nulo, percentil, semilla, **kwargs)


def nulo_de_coleccion(series_std: dict, crono_std, excluir: str | None=None, percentil: float=95.0, **kwargs) -> dict:
    """Umbral de ganancia a partir de las OTRAS series de la colección."""
    return _nulos.nulo_de_coleccion(localizar_quiebre, series_std, crono_std, excluir, percentil, **kwargs)


def evaluar_con_coleccion(serie_std: pd.Series, crono_std: pd.Series, series_std: dict, excluir: str | None=None, percentil: float=95.0, **kwargs) -> dict:
    """Localiza el quiebre y lo contrasta con el nulo de la colección."""
    return _nulos.evaluar_con_coleccion(localizar_quiebre, serie_std, crono_std, series_std, excluir, percentil, **kwargs)
