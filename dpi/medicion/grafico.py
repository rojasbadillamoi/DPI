"""Preparación estadística de gráficos de medición sin Qt."""
import numpy as np
import pandas as pd
import dpi.ciencia.transformacion as _tr
from dpi.ciencia.estadistica import pearson


def normalizar_grafico(valores):
    """Z-score gráfico, con ceros cuando la desviación es casi nula."""
    arr = np.array(valores, dtype=float)
    std = arr.std()
    if std < 1e-9:
        return [0.0] * len(valores)
    return ((arr - arr.mean()) / std).tolist()


def serie_medicion(anios, anchos):
    return pd.Series(anchos, index=anios).clip(lower=0.01)


def transformar_medicion(anios, anchos, metodo):
    return _tr.transformar(serie_medicion(anios, anchos), metodo)


def correlacion_global(anios_a, anchos_a, anios_b, anchos_b, metodo):
    if len(anios_a) < 5 or len(anios_b) < 5:
        return None
    r, _ = _tr.r_pearson(serie_medicion(anios_a, anchos_a),
                         serie_medicion(anios_b, anchos_b),
                         metodo=metodo, min_overlap=5)
    return float(r) if np.isfinite(r) else None


def correlacion_deslizante(anios_a, anchos_a, anios_b, anchos_b, ventana: int, metodo):
    """
    Correlación deslizante estilo COFECHA.

    Calcula r de Pearson (sobre diff-log) en cada ventana de `ventana` años,
    avanzando de la mitad de la ventana en la mitad (solapamiento 50%).
    Cuando la serie tiene menos de `ventana` años, usa todos los años
    disponibles como única ventana (ventana creciente al inicio).

    Devuelve dos listas paralelas: (años_centro, r_vals).
    Los años_centro son el año central de cada ventana.
    """
    if ventana < 2:
        raise ValueError("Ventana demasiado corta")
    MIN_VENTANA = 10
    if len(anios_a) < MIN_VENTANA or len(anios_b) < MIN_VENTANA:
        return [], []

    da = transformar_medicion(anios_a, anchos_a, metodo)
    db = transformar_medicion(anios_b, anchos_b, metodo)
    overlap = sorted(da.index.intersection(db.index))
    n_ov = len(overlap)
    if n_ov < MIN_VENTANA:
        return [], []

    años_centro, r_vals = [], []
    paso = max(1, ventana // 2)
    largo = min(ventana, n_ov)
    a = da.loc[overlap].to_numpy(dtype=float)
    b = db.loc[overlap].to_numpy(dtype=float)
    tolerancia = np.nextafter(1e-9, np.inf)  # conserva la condición estricta >
    for k in range(0, n_ov - largo + 1, paso):
        r = pearson(a[k:k + largo], b[k:k + largo], tolerancia=tolerancia)
        if np.isfinite(r):
            años_centro.append(overlap[k + largo // 2])
            r_vals.append(r)
    return años_centro, r_vals
