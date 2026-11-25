"""Operaciones extraídas sin modificar sus algoritmos."""
import os
import re
import pandas as pd
from dpi.formatos.tucson import escribir_tucson
from dpi.formatos.tabular import escribir_tabla

def asegurar_extension(ruta: str, filtro: str) -> str:
    """Garantiza que la ruta tenga una extensión coherente con el filtro
    elegido en el diálogo de guardado.

    El diálogo NO nativo de Qt no siempre agrega la extensión: si el usuario
    escribe solo el nombre, el archivo queda SIN extensión y los programas no
    lo reconocen (un .xlsx sin extensión se ve como un .zip). Esta función
    extrae las extensiones del filtro y agrega la primera si falta.
    """
    import re
    exts = re.findall(r"\*(\.[A-Za-z0-9]+)", filtro or "")
    if not exts:
        return ruta
    ruta_lower = ruta.lower()
    if any(ruta_lower.endswith(e.lower()) for e in exts):
        return ruta
    return ruta + exts[0]


def exportar_serie_2col(serie, ruta, codigo):
    """Exporta una serie de índices y devuelve el número de años escritos."""
    ext = os.path.splitext(ruta)[1].lower()
    s = pd.to_numeric(serie, errors="coerce").dropna()
    df = pd.DataFrame({"Anio": s.index.astype(int), "Valor": s.values})
    if ext == ".rwl":
        escribir_tucson(s, ruta, codigo=str(codigo))
    else:
        escribir_tabla(df, ruta)
    return len(df)
