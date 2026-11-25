"""Operaciones extraídas sin modificar sus algoritmos."""
import os
from dpi.infraestructura.escritura import ruta_atomica
import numpy as np
import pandas as pd
from dpi.formatos.constantes import TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE, TUCSON_MAX_CHARS_ID
import logging
logger = logging.getLogger(__name__)

def _registros_tucson(ruta):
    """Lee campos fijos una sola vez, conservando año y código."""
    registros = {}
    codigo = None
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.rstrip("\r\n")
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            try:
                anio = int(ln[8:12])
            except ValueError:
                continue
            codigo = ln[:8].strip() or codigo
            if not codigo:
                continue
            for i in range(10):
                token = ln[12 + 6*i:18 + 6*i].strip()
                if not token:
                    continue
                try:
                    valor = int(token)
                except ValueError:
                    logger.warning("Tucson: campo inválido %s, año %s", codigo, anio+i)
                    continue
                registros.setdefault(codigo, []).append((anio+i, valor))
    return registros


def _precision_registros(registros):
    return {sid: (100.0 if pares[-1][1] == 999 else
                  1000.0 if pares[-1][1] == TUCSON_VALOR_FIN else 1.0)
            for sid, pares in registros.items() if pares}


def detectar_precision_tucson(ruta: str) -> dict:
    return _precision_registros(_registros_tucson(ruta))


def leer_tucson_multi(ruta: str) -> dict[str, pd.DataFrame]:
    registros = _registros_tucson(ruta)
    precision = _precision_registros(registros)
    resultado = {}
    for sid, pares in registros.items():
        div = precision[sid]
        datos = []
        for anio, valor in pares:
            if valor == TUCSON_VALOR_FIN or (valor == 999 and div == 100.0):
                break
            if valor == TUCSON_VALOR_FALTANTE:
                continue
            datos.append((anio, valor / div))
        if not datos:
            continue
        df = pd.DataFrame(datos, columns=["Anio", "Ancho_mm"])
        if df["Anio"].duplicated().any():
            logger.warning("Tucson: años duplicados en %s; se promedian", sid)
        resultado[sid] = df.groupby("Anio").mean().sort_index()
    if not resultado:
        raise ValueError(f"No se encontraron series válidas en: {os.path.basename(ruta)}")
    return resultado


def leer_archivo_tucson(ruta: str) -> tuple[pd.DataFrame, str]:
    series = leer_tucson_multi(ruta)
    if len(series) != 1:
        raise ValueError("El archivo contiene varias series; utilice la importación múltiple.")
    sid, df = next(iter(series.items()))
    return df, sid


def _lineas_tucson(serie, codigo, factor=1000.0):
    """Generador común: campos fijos, años reales y terminador inequívoco."""
    if factor not in (100.0, 1000.0):
        raise ValueError("Tucson: factor debe ser 100 o 1000.")
    codigo = str(codigo)[:TUCSON_MAX_CHARS_ID]
    if not codigo.strip() or not codigo.isascii() or any(c in codigo for c in "\r\n\t"):
        raise ValueError("Código Tucson inválido.")
    if serie.empty or serie.index.has_duplicates:
        raise ValueError("Tucson: serie vacía o años duplicados.")
    datos = {}
    fin = 999 if factor == 100 else TUCSON_VALOR_FIN
    for anio, valor in serie.items():
        y = int(anio)
        if float(anio) != y or not -999 <= y <= 9999:
            raise ValueError(f"Año Tucson inválido: {anio}")
        if pd.isna(valor):
            v = TUCSON_VALOR_FALTANTE
        else:
            v = int(round(float(valor) * factor))
            if v in (fin, TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE) or len(str(v)) > 6:
                raise ValueError(f"Valor Tucson reservado o fuera de rango: {valor} ({y})")
        datos[y] = v
    inicio, ultimo = min(datos), max(datos)
    lineas = []
    y = inicio
    while y <= ultimo:
        n = min(10-y%10, ultimo-y+1)
        valores = [datos.get(k, TUCSON_VALOR_FALTANTE) for k in range(y,y+n)]
        lineas.append(f"{codigo:8s}{y:4d}" + "".join(f"{v:6d}" for v in valores))
        y += n
    if (len(lineas[-1])-12)//6 < 10 and y%10:
        lineas[-1] += f"{fin:6d}"
    else:
        if y > 9999:
            raise ValueError("Tucson: año del terminador fuera de rango.")
        lineas.append(f"{codigo:8s}{y:4d}{fin:6d}")
    return lineas


def _guardar_lineas_tucson(ruta, lineas):
    with ruta_atomica(ruta) as temporal:
        with open(temporal, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lineas) + "\n")


def escribir_tucson(serie: pd.Series, ruta: str, codigo: str = "CRONO",
                     factor: float = 1000.0, decimales_mm: bool = True):
    _guardar_lineas_tucson(ruta, _lineas_tucson(serie, codigo, factor))


def exportar_tucson_ewlw(id_serie: str, anios: list,
                            anchos_ewlw: list, ruta_base: str, *,
                            sufijos=("_EW", "_LW"), extension=None):
    if not anios or len(anchos_ewlw) != len(anios):
        raise ValueError("EW/LW: cantidad de años y mediciones incompatible.")
    base, ext = os.path.splitext(ruta_base)
    ext = extension or ext or ".rwl"
    salidas = []
    for sufijo, columna in zip(sufijos, (1, 2), strict=True):
        valores = [t[columna] if t[1] is not None and t[2] is not None else np.nan
                   for t in anchos_ewlw]
        codigo = id_serie[:TUCSON_MAX_CHARS_ID-len(sufijo)] + sufijo
        salidas.append((base+sufijo+ext, _lineas_tucson(pd.Series(valores, index=anios), codigo)))
    for ruta, lineas in salidas:
        _guardar_lineas_tucson(ruta, lineas)


def _escribir_tucson(codigo: str, anio_inicio: int, mediciones: list[int], ruta: str,
                     *, anios=None):
    if not ruta.lower().endswith((".txt", ".rwl")):
        ruta += ".txt"
    if anios is None:
        anios = range(anio_inicio, anio_inicio+len(mediciones))
    serie = pd.Series(mediciones, index=anios, dtype=float) / 1000.0
    escribir_tucson(serie, ruta, codigo)


def _escribir_tucson_serie(codigo: str, anio_inicio: int,
                            mediciones_mm: list[float], buffer: list[str]) -> None:
    serie = pd.Series(mediciones_mm, index=range(anio_inicio, anio_inicio+len(mediciones_mm)))
    buffer.extend(_lineas_tucson(serie, codigo))


def escribir_tucson_merge(series_dict: dict[str, pd.DataFrame], ruta: str) -> None:
    if not ruta.lower().endswith((".rwl", ".txt")):
        ruta += ".rwl"
    buffer = []
    codigos = set()
    for sid, df in series_dict.items():
        codigo = str(sid)[:TUCSON_MAX_CHARS_ID].strip()
        if codigo in codigos:
            raise ValueError(f"Identificadores Tucson coincidentes: {codigo}")
        codigos.add(codigo)
        df = df.set_index("Anio") if "Anio" in df.columns else df
        buffer.extend(_lineas_tucson(df["Ancho_mm"], codigo))
    if not buffer:
        raise ValueError("No hay series para exportar.")
    _guardar_lineas_tucson(ruta, buffer)


def escribir_rwl_intensidad(codigo, anio_inicio, valores, ruta):
    """Adaptador histórico para series de intensidad consecutivas."""
    escribir_tucson(pd.Series(valores, index=range(anio_inicio, anio_inicio + len(valores))),
                     ruta, codigo=codigo)
