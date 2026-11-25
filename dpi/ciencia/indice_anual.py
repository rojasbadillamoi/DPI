"""Validación común de índices anuales."""
import numpy as np
import pandas as pd


def validar_anios(indice):
    valores = list(indice)
    if any(isinstance(v, (bool, np.bool_)) for v in valores):
        raise ValueError("Los años no pueden ser booleanos")
    numerico = pd.to_numeric(pd.Index(valores), errors='raise')
    idx = numerico.to_numpy(dtype=float)
    if (not np.isfinite(idx).all() or not np.equal(idx, np.floor(idx)).all()
            or (np.abs(idx) > 2**53 - 1).any() or np.unique(idx).size != idx.size):
        raise ValueError('Índice anual inválido')
    return idx.astype(np.int64)
