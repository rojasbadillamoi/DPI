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

import numpy as np
import pandas as pd

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


def transformar(serie: pd.Series, metodo: str = DIFFLOG,
                 rigidez_spline: int = 32, aplicar_log: bool = True,
                 aplicar_ar: bool = True, max_orden_ar: int = 3) -> pd.Series:
    """Deja una serie de anchos lista para correlacionar.

    Devuelve una Series indexada por año. Con `difflog` el primer año se
    pierde (la diferencia necesita un año previo).
    """
    s = pd.to_numeric(serie, errors="coerce").dropna().astype(float)
    if s.empty:
        return s
    s = s.sort_index()

    if metodo == COFECHA:
        # Import diferido: modulo_cofecha importa modulo_codatacion, y este
        # módulo lo usan ambos. Hacerlo acá evita el ciclo de importación.
        from modulo_cofecha import estandarizar_serie
        idx, _orden = estandarizar_serie(
            s, rigidez_spline=rigidez_spline, aplicar_log=aplicar_log,
            aplicar_ar=aplicar_ar, max_orden_ar=max_orden_ar)
        return idx.dropna()

    # Diferencias-log
    s = s.clip(lower=1e-6)
    return np.log(s).diff().dropna()


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
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return float("nan"), n
    r = float(np.corrcoef(x, y)[0, 1])
    return (r if np.isfinite(r) else float("nan")), n


def crear_selector(parent=None, metodo_inicial: str = DIFFLOG):
    """QComboBox con los métodos disponibles, para reutilizar en las pestañas."""
    from PyQt6.QtWidgets import QComboBox
    combo = QComboBox(parent)
    for m in METODOS:
        combo.addItem(ETIQUETAS[m], m)
    combo.setCurrentIndex(METODOS.index(metodo_inicial)
                          if metodo_inicial in METODOS else 0)
    combo.setToolTip(
        "Transformación aplicada antes de calcular la correlación.\n\n"
        + "\n\n".join(f"• {ETIQUETAS[m]}\n{DESCRIPCIONES[m]}" for m in METODOS)
        + "\n\nCon el mismo método, la r coincide entre pestañas.")
    return combo
