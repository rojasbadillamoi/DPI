"""Operaciones extraídas sin modificar sus algoritmos."""
import os
from dpi.infraestructura.escritura import ruta_atomica
import pandas as pd
import dpi.infraestructura.json_seguro as _js
import logging
logger = logging.getLogger(__name__)
from dpi.formatos.planillas import es_planilla, leer_planilla, escribir_excel
from dpi.formatos.tucson import leer_archivo_tucson, escribir_tucson
_CAMPOS_POR_ANIO = ("sample_depth", "EPS_movil", "Rbar_movil")

def _ruta_metadatos_cronologia(ruta: str) -> str:
    base = os.path.basename(ruta)
    carpeta = os.path.dirname(ruta)
    return os.path.join(carpeta, f".{os.path.splitext(base)[0]}.json")


def _restaurar_claves_anio(meta: dict) -> dict:
    for campo in _CAMPOS_POR_ANIO:
        if isinstance(meta.get(campo), dict):
            meta[campo] = _js.restaurar_claves_int(meta[campo])
    return meta


def _guardar_metadatos_cronologia(ruta: str, meta: dict):
    """Escribe el .json de metadatos, saneando tipos y de forma atómica."""
    _js.guardar_json(_ruta_metadatos_cronologia(ruta), meta)


def _cargar_metadatos_cronologia(ruta: str) -> dict | None:
    meta_path = _ruta_metadatos_cronologia(ruta)
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return _restaurar_claves_anio(_js.cargar_json(f))
    except Exception:
        logger.exception("No se pudo leer el metadato %s", meta_path)
        return None


def _exportar_cronologia_df(df: pd.DataFrame, ruta: str, codigo: str = "CRONO"):
    ext = os.path.splitext(ruta)[1].lower()
    df_out = df.copy()
    df_out.index.name = "Anio"
    if ext == ".rwl":
        # Tucson: se guarda la columna de valores de la cronología
        col = df_out.columns[0]
        for c in df_out.columns:
            if str(c).strip().lower() not in ("n", "sd", "se", "eps", "rbar"):
                col = c
                break
        escribir_tucson(pd.to_numeric(df_out[col], errors="coerce"),
                        ruta, codigo=codigo)
        return
    if es_planilla(ext):
        escribir_excel(df_out, ruta, index=True)
    elif ext == ".csv":
        with ruta_atomica(ruta) as temporal:
            df_out.to_csv(temporal, index=True)
    else:
        with ruta_atomica(ruta) as temporal:
            df_out.to_csv(temporal, index=True, sep="\t")


def _leer_cronologia_guardada(ruta: str) -> tuple[pd.DataFrame, dict]:
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".rwl":
        df, _ = leer_archivo_tucson(ruta)
        df = df.reset_index()
    elif es_planilla(ext):
        df = leer_planilla(ruta)
    elif ext == ".csv":
        df = pd.read_csv(ruta)
        if df.shape[1] < 2:
            df = pd.read_csv(ruta, sep=";", decimal=",")
    else:
        try:
            df = pd.read_csv(ruta, sep="\t")
            test_col = df.iloc[:, 1] if df.shape[1] > 1 else pd.Series()
            if pd.to_numeric(test_col, errors="coerce").isna().all() and len(test_col) > 0:
                df = pd.read_csv(ruta, sep="\t", decimal=",")
        except Exception:
            try:
                df = pd.read_csv(ruta, sep=None, engine="python", decimal=",")
            except Exception:
                df = pd.read_csv(ruta, sep=None, engine="python")

    if df.shape[1] < 2:
        raise ValueError("La cronología debe tener al menos dos columnas.")

    cols = list(df.columns)
    year_col = None
    for c in cols:
        if c.lower() in ("anio", "año", "year"):
            year_col = c
            break
    if year_col is None:
        year_col = cols[0]

    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df.dropna(subset=[year_col])
    df[year_col] = df[year_col].astype(int)
    df.set_index(year_col, inplace=True)
    df.index.name = "Anio"
    df.sort_index(inplace=True)

    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    value_cols = [c for c in df.columns if c.lower() not in ("n", "sd", "se")]

    meta = _cargar_metadatos_cronologia(ruta) or {}
    nombre = meta.get("nombre") or os.path.splitext(os.path.basename(ruta))[0]

    if not meta:
        cols_lower = {c.lower(): c for c in value_cols}
        columnas_disponibles = []
        for t in ["Raw", "Standard", "Residual"]:
            if t.lower() in cols_lower or t in df.columns:
                columnas_disponibles.append(t)

        if len(columnas_disponibles) > 1:
            tipo = "todas"
            col_valor = columnas_disponibles[0]
        elif len(columnas_disponibles) == 1:
            tipo = columnas_disponibles[0].lower()
            col_valor = columnas_disponibles[0]
        else:
            tipo = "raw"
            col_valor = value_cols[0] if value_cols else df.columns[0]

        meta = {
            "nombre": nombre, "tipo_cronologia": tipo,
            "metodo_estandarizacion": "desconocido", "agregacion": "desconocido",
            "series_usadas": [], "n_series": 0,
            "n_anios": int(len(df)),
            "columna_valor": col_valor,
            "columnas_disponibles": columnas_disponibles if len(columnas_disponibles) > 1 else [],
        }

    meta.setdefault("nombre", nombre)
    meta.setdefault("n_anios", int(len(df)))

    col_val = meta.get("columna_valor", "")
    if col_val not in df.columns:
        for c in df.columns:
            if c.lower() == col_val.lower():
                meta["columna_valor"] = c
                break
        else:
            meta["columna_valor"] = value_cols[0] if value_cols else df.columns[0]

    return df, meta
