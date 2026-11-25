"""Núcleo científico de cronologías y estandarización, sin interfaz gráfica."""

import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import (
    serie_anual, agrupar_por_arbol, rbar_entre_arboles, correlaciones_pares, calcular_eps, pearson,
    BIWEIGHT_C, media_biweight,
)


from dpi.ciencia.tendencias import _bloques_anuales, _spline_cook, _fit_trend, _detrend_serie_indice, RIGIDEZ_SPLINE_DEFECTO


# Adaptador histórico: el cálculo reside únicamente en dpi.ciencia.estadistica.
def _biweight_mean(values, c: float = BIWEIGHT_C, minimo: int = 6) -> float:
    return media_biweight(values, c=c, minimo=minimo)


from scipy.linalg import solveh_banded










from dpi.ciencia.autorregresion import _ajustar_ar_yule_walker, _seleccionar_orden_ar, _ajustar_ar_burg, _residualizar_indice, orden_ar_agrupado, ORDEN_AR_MAXIMO










from dpi.ciencia.estabilizacion import rigidez_efectiva, estabilizar_varianza




def detrendar_para_cronologia(serie_mm: pd.Series,
                               metodo1: str = "spline",
                               rigidez1=32,
                               metodo2: str | None = None,
                               rigidez2=-128,
                               ventana_mm: int | None = None,
                               rigidez_minima: int = 0,
                               por_resta: bool = False,
                               log_previo: bool = False,
                               estabilizar: bool = False,
                               rigidez_estab=64,
                               normalizar: bool = False) -> pd.Series:
    """Detrending completo al modo de ARSTAN, incluido el DOBLE detrending.

    El doble detrending es el VALOR POR OMISIÓN de ARSTAN —su configuración
    inicial es «1 & 128»: exponencial negativa y después spline de 128 años— y
    DPI solo hacía uno. El manual explica por qué importa: la exponencial
    ajusta bien el tercio inicial de una serie, pero «hacia la mitad y el final
    puede ir muchas décadas casi enteramente por encima o por debajo del
    crecimiento real», dejando tramos largos de índices altos o bajos. El
    segundo ajuste, más rígido, corrige ese desvío sin tocar las frecuencias
    de interés.

    Orden de las operaciones, el mismo del manual:

      1. Logaritmo, sumando un sexto de la media (opcional, antes de ajustar)
      2. Primer ajuste e índices
      3. Segundo ajuste sobre esos índices e índices otra vez (opcional)
      4. Estabilización de varianza (opcional)
      5. Normalización a varianza 1 (opcional)

    `por_resta` cambia el índice de división a sustracción: ARSTAN permite las
    dos, y con series log-transformadas la resta es lo natural.
    """
    s = pd.to_numeric(serie_mm, errors="coerce").dropna().astype(float)
    if len(s) < 8:
        return s

    if log_previo:
        m = float(s.mean())
        c = m / 6.0 if m > 0 else 1e-3
        s = pd.Series(np.log(np.maximum(s.to_numpy() + c, 1e-10)), index=s.index)

    # Con la serie en logaritmos los valores pueden ser negativos con todo
    # derecho, así que la guarda de positividad de `_fit_trend` —pensada para
    # anchos en milímetros— no corresponde: descartaría curvas correctas.
    espacio_log = bool(log_previo)

    def _un_paso(x: pd.Series, metodo: str, rigidez) -> pd.Series:
        rig = rigidez_efectiva(rigidez, len(x), rigidez_minima)
        xv = x.to_numpy(dtype=float)
        if espacio_log and metodo == "spline":
            tend = np.asarray(_spline_cook(xv, nyrs=rig, f=0.5), dtype=float)
        elif espacio_log and metodo in ("media", "media_movil"):
            tend = (np.full_like(xv, float(np.nanmean(xv)))
                    if metodo == "media"
                    else np.asarray(_fit_trend(xv, metodo,
                                               ventana_mm=ventana_mm,
                                               rigidez=rig), dtype=float))
        else:
            tend = np.asarray(_fit_trend(xv, metodo, ventana_mm=ventana_mm,
                                         rigidez=rig), dtype=float)
        if por_resta:
            return pd.Series(xv - tend, index=x.index)
        piso = 0.10 * float(np.nanmean(x[x > 0])) if np.any(x > 0) else 1e-9
        return pd.Series(x.to_numpy(dtype=float) / np.maximum(tend, piso),
                         index=x.index)

    idx = _un_paso(s, metodo1, rigidez1)
    if metodo2:
        idx = _un_paso(idx, metodo2, rigidez2)

    if estabilizar:
        idx = estabilizar_varianza(idx, rigidez_estab, rigidez_minima)

    if normalizar:
        sd = float(idx.std())
        if sd > 0:
            m = float(idx.mean())
            idx = pd.Series((idx.to_numpy() - m) / sd + m, index=idx.index)
    return idx




def normalizar_serie_para_tipo(serie_mm: pd.Series, tipo_cronologia: str,
                                  metodo_estandarizacion: str,
                                  ventana_mm: int | None = None,
                                  aplicar_log: bool = False,
                                  arstan: dict | None = None,
                                  orden_ar: int | None = None) -> pd.Series:
    tipo = (tipo_cronologia or "raw").lower()
    if tipo == "raw":
        return pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()

    # Camino ARSTAN: doble detrending, rigidez porcentual, estabilización de
    # varianza, normalización e índices por resta. Solo se toma si la pestaña
    # activó alguna de esas opciones; si no, sigue el camino simple de siempre.
    if arstan:
        idx = detrendar_para_cronologia(
            serie_mm,
            metodo1=arstan.get("metodo1", metodo_estandarizacion),
            rigidez1=arstan.get("rigidez1", 32),
            metodo2=arstan.get("metodo2"),
            rigidez2=arstan.get("rigidez2", -128),
            ventana_mm=ventana_mm,
            rigidez_minima=arstan.get("rigidez_minima", 0),
            por_resta=arstan.get("por_resta", False),
            log_previo=arstan.get("log_previo", False),
            estabilizar=arstan.get("estabilizar", False),
            rigidez_estab=arstan.get("rigidez_estab", 64),
            normalizar=arstan.get("normalizar", False))
        if tipo == "residual":
            return _residualizar_indice(idx)
        return idx
    idx = _detrend_serie_indice(serie_mm, metodo_estandarizacion, ventana_mm=ventana_mm)
    # Log estilo COFECHA (Holmes 1983): se aplica al índice de razón (media ~1)
    # antes del modelo autorregresivo. Comprime los anillos anchos y suele
    # subir la correlación de cofechado. Debe aplicarse por igual a la
    # cronología y a las series para que queden en el mismo espacio.
    if aplicar_log and not idx.empty:
        media = float(idx.mean())
        c_const = media / 6.0 if media > 0 else 0.001
        idx = pd.Series(
            np.log(np.maximum(idx.to_numpy(dtype=float) + c_const, 1e-10)),
            index=idx.index)
    if tipo == "residual":
        if orden_ar:
            return _residualizar_indice(idx, orden_fijo=orden_ar)
        return _residualizar_indice(idx)
    return idx


METODOS_DETREND = ("spline", "negexp", "linear", "media_movil", "media")


def diagnosticar_curva(serie_mm: pd.Series, metodo: str,
                        ventana_mm: int | None = None,
                        rigidez: int | None = None) -> dict:
    """Comprueba si la curva de ajuste cruza cero — el «dirty dog» de ARSTAN.

    Con series de caída muy fuerte, la exponencial negativa o la recta pueden
    bajar de cero. Ahí el índice queda indefinido o negativo, y dividir por un
    número cercano a cero lo dispara: medido sobre una serie real de ciprés,
    el ajuste lineal cruzaba cero en 24 de 422 años y producía un índice
    máximo de 96, cuando un índice normal ronda 1.

    DPI nunca devuelve índices negativos porque reemplaza la tendencia por la
    media de la serie donde sale <= 0. El problema no es que explote: es que
    parchaba en SILENCIO, y esos años quedan divididos por la media global en
    vez de por su tendencia local, así que su índice no significa lo mismo que
    el del resto de la serie.

    Devuelve:
      n_parches   años cuya tendencia hubo que reemplazar
      total       largo de la serie
      tramos      lista de (año inicial, año final) de los tramos parchados
      indice      la serie de índice resultante
      indice_max  máximo del índice; sobre 3 o 4 es señal de alarma
      valido      True si la curva no cruzó cero en ningún año
    """
    s = pd.to_numeric(serie_mm, errors="coerce").dropna().astype(float)
    vacio = {"n_parches": 0, "total": 0, "tramos": [], "indice": s.iloc[0:0],
             "indice_max": float("nan"), "valido": False}
    if len(s) < 8:
        return vacio
    try:
        tend = _fit_trend(s.to_numpy(dtype=float), metodo,
                          ventana_mm=ventana_mm, rigidez=rigidez)
    except Exception:
        return vacio
    tend = np.asarray(tend, dtype=float)
    # Mismo criterio que la guarda de `_detrend_serie_indice`: el 5 % de la
    # media, no el cero. Si no, el diálogo no avisaría de los casos donde la
    # curva no cruza cero pero igual dispara el índice.
    vals = s.to_numpy(dtype=float)
    med = float(np.nanmean(vals)) if len(vals) else 0.0
    piso = 0.05 * med if np.isfinite(med) and med > 0 else 0.0
    malo = ~np.isfinite(tend) | (tend <= piso)
    anios = s.index.to_numpy(np.int64)

    tramos = []
    if malo.any():
        ini = None
        for k, m in enumerate(malo):
            if m and ini is None:
                ini = k
            elif not m and ini is not None:
                tramos.append((int(anios[ini]), int(anios[k - 1])))
                ini = None
        if ini is not None:
            tramos.append((int(anios[ini]), int(anios[-1])))

    idx = _detrend_serie_indice(s, metodo, ventana_mm=ventana_mm,
                                rigidez=rigidez)
    return {
        "n_parches": int(malo.sum()), "total": int(len(s)),
        "tramos": tramos, "indice": idx,
        "indice_max": float(idx.max()) if len(idx) else float("nan"),
        "valido": not bool(malo.any()),
    }


def detectar_series_problematicas(series: dict, nombres: list,
                                   metodo: str, ventana_mm=None,
                                   rigidez=None) -> dict:
    """Series cuya curva cruza cero con el método elegido."""
    fuera = {}
    for n in nombres:
        if n not in series:
            continue
        col = series[n]["Ancho_mm"] if isinstance(series[n], pd.DataFrame) \
            else series[n]
        d = diagnosticar_curva(col, metodo, ventana_mm, rigidez)
        if d["n_parches"] > 0:
            fuera[n] = d
    return fuera


def elegir_metodo_para_grupo(series: dict, problematicas: list,
                              maestra: pd.Series,
                              metodos=METODOS_DETREND,
                              ventana_mm=None, rigidez=None) -> dict:
    """Elige UN método para todas las series con curva negativa.

    Dos etapas, y el orden importa:

    1. **Filtro duro:** se descarta cualquier método que cruce cero en alguna
       de las series del grupo. Ahí el índice no significa nada.
    2. **Entre los que sobreviven, la mediana de la correlación con la
       maestra.** No se usa el índice máximo como criterio, aunque delate bien
       los casos rotos, porque un máximo cercano a 1 se consigue de dos
       maneras opuestas: porque la curva ajusta bien, o porque ajusta DEMASIADO
       y se come toda la variabilidad. La correlación distingue esos dos casos;
       el máximo no. Tampoco sirve la sensibilidad media: medida sobre cinco
       métodos en la misma serie da 0,260 a 0,269, o sea que el método de
       estandarización no toca la alta frecuencia.

    Se elige sobre el GRUPO y no serie por serie, porque el informe tiene que
    poder decir «las N series con curva negativa se estandarizaron con X».
    Optimizar la primera serie puede castigar a las otras cinco.

    Devuelve {"metodo": str|None, "tabla": [...]} con el detalle por método.
    """
    tabla = []
    for m in metodos:
        rs, maxs, cruces = [], [], 0
        for n in problematicas:
            col = series[n]["Ancho_mm"] if isinstance(series[n], pd.DataFrame) \
                else series[n]
            d = diagnosticar_curva(col, m, ventana_mm, rigidez)
            cruces += d["n_parches"]
            idx = d["indice"]
            if idx is None or len(idx) < 10:
                continue
            maxs.append(d["indice_max"])
            com = idx.index.intersection(maestra.index)
            if len(com) >= 20:
                a = idx.loc[com].to_numpy(dtype=float)
                b = maestra.loc[com].to_numpy(dtype=float)
                if np.std(a) > 1e-12 and np.std(b) > 1e-12:
                    r = pearson(a, b)
                    if np.isfinite(r):
                        rs.append(r)
        tabla.append({
            "metodo": m, "cruces": cruces,
            "valido": cruces == 0,
            "r_mediana": float(np.median(rs)) if rs else float("nan"),
            "indice_max": float(np.max(maxs)) if maxs else float("nan"),
            "n_series": len(rs),
        })
    validos = [t for t in tabla
               if t["valido"] and np.isfinite(t["r_mediana"])]
    mejor = max(validos, key=lambda t: t["r_mediana"])["metodo"] \
        if validos else None
    tabla.sort(key=lambda t: (t["valido"],
                              t["r_mediana"] if np.isfinite(t["r_mediana"])
                              else -9), reverse=True)
    return {"metodo": mejor, "tabla": tabla}


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


def _construir_cronologia_desde_series(
    series: dict[str, pd.DataFrame],
    nombres: list[str],
    tipo_cronologia: str,
    metodo_estandarizacion: str,
    agregacion: str,
    ventana_mm: int | None = None,
    aplicar_log: bool = False,
    metodo_alterno: str | None = None,
    series_alternas: list | None = None,
    metodos_por_serie: dict | None = None,
    arstan: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    if not nombres:
        raise ValueError("No hay series seleccionadas.")

    alternas = set(series_alternas or [])
    # Orden AR agrupado para la cronología residual, al modo de ARSTAN: un
    # solo orden para todas las series, elegido sobre las autocorrelaciones
    # del conjunto. Se calcula una vez y se pasa a cada serie.
    orden_pool = None
    if (tipo_cronologia or "").lower() == "residual":
        try:
            prev = {}
            for n in nombres:
                if n in series:
                    m2 = (metodo_alterno if (metodo_alterno and n in alternas)
                          else metodo_estandarizacion)
                    prev[n] = _detrend_serie_indice(
                        series[n]["Ancho_mm"], m2, ventana_mm=ventana_mm)
            if len(prev) >= 3:
                orden_pool, _rho = orden_ar_agrupado(prev)
        except Exception:
            orden_pool = None
    columnas = []
    for nombre in nombres:
        if nombre not in series:
            continue
        # Las series cuya curva cruzaba cero pueden llevar otro método, el
        # mismo para todas, elegido por el usuario o por correlación.
        # Prioridad: elección individual > método del grupo > método general.
        met = metodo_estandarizacion
        if metodo_alterno and nombre in alternas:
            met = metodo_alterno
        if metodos_por_serie and nombre in metodos_por_serie:
            met = metodos_por_serie[nombre]
        s_norm = normalizar_serie_para_tipo(
            series[nombre]["Ancho_mm"], tipo_cronologia,
            met, ventana_mm=ventana_mm,
            aplicar_log=aplicar_log, arstan=arstan,
            orden_ar=orden_pool
        )
        s_norm.name = nombre
        columnas.append(s_norm)
    if not columnas:
        raise ValueError("No hay datos válidos para construir la cronología.")

    df = pd.concat(columnas, axis=1).sort_index()
    if df.empty:
        raise ValueError("La cronología quedó vacía.")

    agg = (agregacion or "biweight").lower()
    tipo = (tipo_cronologia or "raw").lower()

    if agg in {"biweight", "robusta", "robust"}:
        valores = pd.Series(media_biweight(df.to_numpy(dtype=float), axis=1),
                            index=df.index)
    elif agg in {"median", "mediana"}:
        valores = df.median(axis=1, skipna=True)
    else:
        valores = df.mean(axis=1, skipna=True)

    ns = df.notna().sum(axis=1)
    sds = df.std(axis=1, skipna=True, ddof=1).fillna(0.0)

    col_name = {"raw": "Raw", "residual": "Residual"}.get(tipo, "Standard")
    cron = pd.DataFrame(
        {col_name: valores, "N": ns.astype(int), "SD": sds},
        index=pd.Index(df.index.astype(int), name="Anio"),
    )
    cron = cron.dropna(subset=[col_name]).sort_index()

    # ── Rbar y EPS de PERÍODO COMPLETO sobre SERIES DETRENDADAS ──────
    # Antes calcular_rbar usaba las series RAW (Ancho_mm), lo que daba
    # valores inflados porque las tendencias decadales hacen que las
    # series brutas covaríen fuertemente a largo plazo. ARSTAN computa
    # su "all possible series rbar" sobre las series DETRENDADAS, que
    # es lo correcto: queremos la señal común año-a-año, no las
    # tendencias compartidas. Acá usamos el `df` de series detrendadas
    # que ya construimos arriba.
    # Rbar global vectorizado. Antes se recorrían todos los pares en bucles
    # de Python con pandas (.dropna/.intersection/.loc por par): con 169
    # series son 14.196 pares y era el mayor costo al generar la cronología.
    # Ahora la matriz de correlaciones se calcula de una sola vez con
    # álgebra matricial, respetando NaN y el mínimo de 10 años en común.
    rs_pairs = correlaciones_pares(df.to_numpy(dtype=float))
    rbar_completo = float(np.mean(rs_pairs)) if rs_pairs.size else float("nan")
    # Profundidad de muestreo promedio (mean number of series per year
    # with valid data) — igual que la columna "cores" de ARSTAN.
    sample_depth_mean = float(ns[ns > 0].mean()) if (ns > 0).any() else 0.0
    eps_completo = float(calcular_eps(rbar_completo, sample_depth_mean))

    meta = {
        "nombre": "",
        "tipo_cronologia": tipo,
        "metodo_estandarizacion": metodo_estandarizacion,
        "aplicar_log": bool(aplicar_log),
        "agregacion": agg,
        "series_usadas": list(nombres),
        "n_series": len(nombres),
        "n_anios": int(len(cron)),
        "creado_en": pd.Timestamp.utcnow().isoformat(),
        "columna_valor": col_name,
        # Rbar/EPS sobre series detrendadas (comparable con ARSTAN
        # "all possible series rbar")
        "Rbar": rbar_completo,
        "EPS": eps_completo,
        "sample_depth_mean": sample_depth_mean,
        # Profundidad AÑO POR AÑO, necesaria para la SSS (la media no sirve:
        # la SSS pregunta desde qué año la cronología es utilizable).
        "sample_depth": pd.Series(ns, index=df.index),
        # Sobre las series DETRENDADAS, no las crudas. Dos series brutas
        # covarían por sus tendencias de edad aunque no compartan señal
        # climática, y eso infla el Rbar dentro y entre árboles por igual.
        "rbar_arboles": rbar_entre_arboles(
            {c.name: c for c in columnas if getattr(c, "name", None)},
            [c.name for c in columnas if getattr(c, "name", None)]),
    }
    return cron, meta
