"""
json_seguro.py — Guardado de JSON a prueba de tipos de numpy/pandas.

DPI guarda varias cosas en JSON al lado de los archivos del usuario: los
metadatos de una cronología, el estado de la medición en curso, el sidecar de
anomalías y los perfiles de especie. Todos esos datos vienen de cálculos con
numpy y pandas, y ahí hay dos trampas.

La primera es que `json` no sabe escribir la mayoría de esos tipos. Conviene
tener presente cuáles pasan y cuáles no, porque no es evidente:

    np.float64     SÍ  — es subclase de `float`, json la trata como tal
    np.float32     NO
    np.int64/32    NO  — NO son subclase de `int`
    np.bool_       NO
    np.ndarray     NO
    pd.Series      NO
    pd.Timestamp   NO

Que `np.float64` pase de casualidad es justamente lo peligroso: un archivo
puede venir funcionando durante años y romperse el día que alguien guarda un
conteo (`np.int64`) en vez de una medida.

La segunda trampa es peor. `json.dump` escribe DIRECTO sobre el archivo, así
que cuando se topa con un tipo que no sabe escribir ya volcó media estructura:
lo que queda en disco es un JSON cortado, ilegible, que además pisó al bueno.
Fue exactamente lo que pasó con los metadatos de cronologías.

`guardar_json` resuelve las dos: convierte los tipos antes de escribir, y
escribe en un archivo temporal que recién al final reemplaza al definitivo.
Si algo falla, el archivo anterior queda intacto.
"""

from __future__ import annotations

import os
import json
import math
import datetime
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def a_json_clave(k):
    """Clave de diccionario admisible para JSON (siempre texto).

    JSON solo admite claves de texto. Un dict indexado por año trae `np.int64`
    de clave y `json` lo rechaza aunque el valor sea inofensivo.
    """
    if isinstance(k, np.generic):
        k = k.item()
    return str(k)


def a_json(obj):
    """Convierte recursivamente a tipos que `json` sepa escribir."""
    if isinstance(obj, dict):
        return {a_json_clave(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [a_json(v) for v in obj]
    if isinstance(obj, pd.Series):
        return {a_json_clave(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, pd.Index):
        return [a_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return {str(c): a_json(obj[c]) for c in obj.columns}
    if isinstance(obj, np.ndarray):
        return [a_json(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):        # np.float32, np.int64, np.bool_…
        obj = obj.item()
    # Ojo con el orden: `bool` es subclase de `int`, y `pd.Timestamp` lo es de
    # `datetime.datetime`, así que las fechas se resuelven antes que el bloque
    # de escalares para no caer en el `str()` final.
    if isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, float):
        # NaN e infinito no son JSON válido. `json` los escribiría igual como
        # NaN/Infinity, que otros lectores rechazan; van como null.
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (str, bool, int)) or obj is None:
        return obj
    return str(obj)                        # último recurso: no perder el dato


def guardar_json(ruta: str, datos, *, indent: int | None = 2,
                 ensure_ascii: bool = False) -> None:
    """Escribe `datos` como JSON de forma atómica y sin tipos problemáticos.

    Lanza la excepción si no se pudo escribir; quien llama decide si eso
    merece avisar al usuario o solo quedar en el registro. Pase lo que pase,
    el archivo que ya estaba en disco no queda a medio escribir.
    """
    tmp = ruta + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(a_json(datos), f, indent=indent, ensure_ascii=ensure_ascii)
        os.replace(tmp, ruta)
    except BaseException:
        # Sin esto queda un .tmp huérfano al lado del archivo del usuario cada
        # vez que falla un guardado.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def restaurar_claves_int(d: dict) -> dict:
    """Devuelve el dict con las claves que sean números vueltas a `int`.

    JSON obliga a que las claves sean texto, así que un diccionario indexado
    por año vuelve de disco con claves `"1990"`. Quien lo consume arma un
    `pd.Series` y después ordena y compara el índice como número, así que hay
    que deshacer la conversión al leer.
    """
    if not isinstance(d, dict):
        return d
    nuevo = {}
    for k, v in d.items():
        try:
            nuevo[int(k)] = v
        except (TypeError, ValueError):
            nuevo[k] = v
    return nuevo
