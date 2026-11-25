"""Ordenamiento de candidatos de corrección."""
import numpy as np


def clave_prioridad_correccion(sug, anio_ref):
    """Prioridad de una corrección según correlación, cercanía y plausibilidad."""
    dist = abs(int(sug.get("anio", 0)) - int(anio_ref))
    cercania = max(0.0, 1.0 - dist / 60.0)
    base = sug.get("r_verificada")
    if base is None or not np.isfinite(base):
        base = sug.get("puntaje", sug.get("delta_r", 0.0))
    return base * (0.5 + cercania) * sug.get("plausibilidad", 1.0)
