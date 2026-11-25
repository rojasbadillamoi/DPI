"""
MoiCedrus — DPI · Transformación común para el cálculo de correlaciones
=======================================================================

Antes cada pestaña transformaba las series por su cuenta antes de correlacionar:

* Medición y Skeleton usaban DIFERENCIAS-LOG: log(x) y luego diferencia
  año a año. Es un filtro de alta frecuencia, barato y sin parámetros.
* Co-Datación usa el método de COFECHA: spline de Cook, índice de razón,
  logaritmo y modelo autorregresivo.

Como son transformaciones distintas, el MISMO par de series daba una r
distinta según la pestaña en que se mirara, sin que nada en pantalla
explicara la diferencia. Este módulo concentra las dos y expone un selector,
de modo que cualquier pestaña puede pedir cualquiera de los dos métodos y los
números coincidan cuando se elige el mismo.

Ninguno de los dos es «el correcto»: responden preguntas distintas.

* Las diferencias-log conservan solo la variación de un año al siguiente. Es
  robusto, no supone nada sobre la curva de crecimiento y funciona con series
  cortas, pero descarta toda la señal de baja frecuencia.
* El método COFECHA quita la tendencia de edad con un spline, así que retiene
  parte de la variabilidad decadal, y el modelo AR remueve la persistencia
  para que la correlación de Pearson —que supone independencia— sea legítima.
  A cambio necesita series con largo suficiente para ajustar el spline.

Para cofechar contra una cronología y comparar con COFECHA, el método COFECHA
es el que corresponde. Para una inspección rápida en pantalla o series muy
cortas, las diferencias-log siguen siendo razonables.
"""

from __future__ import annotations

import pandas as pd
from dpi.ciencia.estadistica import pearson, diferencias_log_anuales
from dpi.ciencia.cronologia import estandarizar_serie

DIFFLOG = "difflog"
COFECHA = "cofecha"

METODOS = (DIFFLOG, COFECHA)

ETIQUETAS = {
    DIFFLOG: "Diferencias-log",
    COFECHA: "COFECHA (spline + log + AR)",
}

DESCRIPCIONES = {
    DIFFLOG: ("Solo variación año a año: log(x) y diferencia.\n"
              "Rápido, sin parámetros, sirve con series cortas.\n"
              "Descarta la señal de baja frecuencia."),
    COFECHA: ("El método de COFECHA: spline de Cook, índice de razón,\n"
              "logaritmo y modelo autorregresivo.\n"
              "Es el que hay que usar para comparar con COFECHA\n"
              "y para cofechar contra una cronología."),
}


def serie_numerica(serie):
    """Convierte valores numéricos y descarta ausentes sin cambiar el orden."""
    return pd.to_numeric(serie, errors="coerce").astype(float).dropna()


def transformar(serie: pd.Series, metodo: str = DIFFLOG,
                 rigidez_spline: int = 32, aplicar_log: bool = True,
                 aplicar_ar: bool = True, max_orden_ar: int = 3) -> pd.Series:
    """Deja una serie de anchos lista para correlacionar.

    Devuelve una Series indexada por año. Con `difflog` el primer año se
    pierde (la diferencia necesita un año previo).
    """
    s = serie_numerica(serie)
    if s.empty:
        return s
    s = s.sort_index()

    if metodo == COFECHA:
        idx, _orden = estandarizar_serie(
            s, rigidez_spline=rigidez_spline, aplicar_log=aplicar_log,
            aplicar_ar=aplicar_ar, max_orden_ar=max_orden_ar)
        return idx.dropna()

    # Diferencias-log
    return diferencias_log_anuales(s, piso=1e-6)


def par(serie_a: pd.Series, serie_b: pd.Series, metodo: str = DIFFLOG,
        **kwargs):
    """Transforma dos series y devuelve (a, b, años comunes)."""
    da = transformar(serie_a, metodo, **kwargs)
    db = transformar(serie_b, metodo, **kwargs)
    comun = da.index.intersection(db.index)
    return da, db, sorted(comun)


def r_pearson(serie_a: pd.Series, serie_b: pd.Series, metodo: str = DIFFLOG,
               min_overlap: int = 5, **kwargs):
    """Correlación de dos series de anchos con el método elegido.

    Devuelve (r, n) o (nan, n) si no hay solape suficiente o alguna serie es
    constante en el tramo común.
    """
    da, db, comun = par(serie_a, serie_b, metodo, **kwargs)
    n = len(comun)
    if n < min_overlap:
        return float("nan"), n
    x = da.loc[comun].to_numpy(dtype=float)
    y = db.loc[comun].to_numpy(dtype=float)
    return pearson(x, y, tolerancia=1e-12), n


def transformar_para_correlacion(serie_mm: pd.Series, es_crono: bool, *, activo, aplicar_serie, aplicar_crono, meta, cronologia, parametros) -> pd.Series:
    """Transformación para calcular la r de correlación, gobernada por el
    botón modo COFECHA.

    Punto CLAVE (corrige un bug grave): para que la r coincida con COFECHA,
    la serie y la cronología deben quedar en el MISMO espacio. Una
    cronología residual se construyó con spline+AR (sin log); si a la
    serie se le aplicaba `aplicar_modo_cofecha` (spline+LOG+AR), quedaban
    en espacios distintos y la r se desplomaba (p. ej. 0.90 → 0.51, o peor
    con datos reales). La solución es estandarizar la SERIE cruda con el
    MISMO método que usó la cronología activa, y NO re-procesar la
    cronología (ya está estandarizada).

    - Modo COFECHA apagado: sin transformación (la serie tal como se subió).
    - Modo COFECHA encendido:
        • Cronología (es_crono=True): se usa tal cual (ya estandarizada;
          re-procesarla la dañaría). El checkbox 'Cronología' fuerza a
          estandarizarla igual, para el caso de una cronología cargada
          SIN estandarizar (anchos crudos en mm).
        • Serie cruda (es_crono=False): se estandariza con el método de la
          cronología activa (residual/standard + spline), quedando en su
          mismo espacio. Si no hay cronología activa comparable, se usa la
          estandarización COFECHA clásica (simétrica entre dos series).
      El checkbox 'Serie' permite desactivar la estandarización de la
      serie (usarla cruda) si el usuario ya la subió estandarizada.
    """
    from dpi.ciencia.datacion import aplicar_modo_cofecha
    from dpi.ciencia.cronologia import normalizar_serie_para_tipo
    s_raw = pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
    if not activo:
        return s_raw

    if es_crono:
        # Por defecto la cronología ya vive en su espacio estandarizado
        # (índice residual/standard), así que NO se re-procesa: aplicarle
        # spline+log+AR encima la dañaría y desplomaría la r.
        #
        # El checkbox 'Cronología' es la salida de escape para el caso en
        # que la cronología cargada NO esté estandarizada (p. ej. una
        # cronología de anchos crudos en mm): ahí sí hay que estandarizarla
        # para poder compararla. Por eso el valor por defecto es apagado.
        if not aplicar_crono:
            return s_raw
        try:
            res = aplicar_modo_cofecha(serie_mm, **parametros)
            if res is not None and not res.empty:
                return res
        except Exception:
            pass
        return s_raw

    # Serie cruda: solo estandarizar si el checkbox 'Serie' está activo.
    if not aplicar_serie:
        return s_raw

    meta = meta or {}
    tipo = (meta.get("tipo_cronologia") or "").lower()
    metodo = meta.get("metodo_estandarizacion") or "spline"

    # Si el tipo no está en la metadata (p. ej. una cronología cargada
    # desde un archivo plano sin encabezado de tipo), inferirlo del espacio
    # de la cronología activa. Una cronología residual/standard vive en
    # torno a media 1 (índice adimensional); una serie COFECHA clásica vive
    # en torno a 0 (log-residual). Sin esta inferencia, la serie se
    # transformaba con log-COFECHA (media 0) contra una cronología en media
    # 1 —espacios distintos— y la r se desplomaba a casi 0.
    if tipo not in ("residual", "standard") and cronologia is not None:
        try:
            mcol = meta.get("columna_valor")
            dfc = cronologia
            if not mcol or mcol not in dfc.columns:
                mcol = dfc.columns[0]
            media_crono = float(
                pd.to_numeric(dfc[mcol], errors="coerce").dropna().mean())
            if 0.5 < media_crono < 1.5:
                tipo = "residual"
        except Exception:
            pass

    if tipo in ("residual", "standard"):
        try:
            aplicar_log = bool(meta.get("aplicar_log", False))
            res = normalizar_serie_para_tipo(
                serie_mm, tipo, metodo, aplicar_log=aplicar_log)
            if res is not None and not res.empty:
                return res
        except Exception:
            pass
    # Sin cronología activa comparable: COFECHA clásico (simétrico).
    return aplicar_modo_cofecha(serie_mm, **parametros)
