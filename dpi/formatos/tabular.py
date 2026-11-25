"""Operaciones extraídas sin modificar sus algoritmos."""
import os
from dpi.infraestructura.escritura import ruta_atomica
import pandas as pd
from dpi.formatos.planillas import es_planilla, leer_planilla, escribir_excel

def leer_tabular(ruta: str) -> tuple[pd.DataFrame, str]:
    """Lee CSV/TSV/TXT/Excel con detección automática de header, decimal, separador."""
    ext = os.path.splitext(ruta)[1].lower()

    def _leer_excel(con_header):
        return leer_planilla(ruta, header=0 if con_header else None)

    def _leer_csv(con_header, decimal="."):
        try:
            return pd.read_csv(
                ruta, header=0 if con_header else None,
                sep=None, engine="python", decimal=decimal,
                encoding="utf-8", encoding_errors="replace",
            )
        except Exception:
            return pd.read_csv(
                ruta, header=0 if con_header else None,
                sep=r"[\s,;\t]+", engine="python", decimal=decimal,
                encoding="utf-8", encoding_errors="replace",
            )

    if es_planilla(ext):
        df_sondeo = _leer_excel(con_header=False)
    else:
        df_sondeo = _leer_csv(con_header=False)

    if df_sondeo.empty or df_sondeo.shape[1] < 2:
        raise ValueError(f"El archivo debe tener al menos dos columnas: {os.path.basename(ruta)}")

    primera = df_sondeo.iloc[0]
    tiene_header = False
    for val in primera:
        s = str(val).strip().replace(",", ".")
        try:
            float(s)
        except (ValueError, TypeError):
            tiene_header = True
            break

    if es_planilla(ext):
        df = _leer_excel(con_header=tiene_header)
    else:
        df = _leer_csv(con_header=tiene_header)

    if not tiene_header:
        df.columns = [f"col{i}" for i in range(df.shape[1])]

    if not es_planilla(ext) and df.shape[1] >= 2:
        test_col = df.iloc[:, 1]
        if pd.to_numeric(test_col, errors="coerce").isna().all() and len(test_col):
            try:
                df = _leer_csv(con_header=tiene_header, decimal=",")
                if not tiene_header:
                    df.columns = [f"col{i}" for i in range(df.shape[1])]
            except Exception:
                pass

    cols = list(df.columns)

    nombres_anio = {"anio", "año", "year", "anios", "años", "yr"}
    year_col = None
    for c in cols:
        if str(c).strip().lower() in nombres_anio:
            year_col = c
            break

    if year_col is None:
        for c in cols:
            test = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(test) > 0 and test.between(-10000, 10000).all():
                if test.std() > 1 and (test % 1 == 0).all():
                    year_col = c
                    break

    if year_col is None:
        raise ValueError(f"No se encontró columna de año en: {os.path.basename(ruta)}")

    nombres_excluidos = {
        str(year_col).strip().lower(),
        "id_serie", "id", "serie", "muestra", "sample", "code",
        "n", "sd", "se", "samp", "samp.depth", "sample.depth",
    }
    value_col = None
    for c in cols:
        if str(c).strip().lower() in nombres_excluidos:
            continue
        test = pd.to_numeric(df[c], errors="coerce")
        if test.notna().sum() > 0:
            value_col = c
            break

    if value_col is None:
        raise ValueError(f"No se encontró columna de valores en: {os.path.basename(ruta)}")

    df_out = pd.DataFrame({
        "Anio": pd.to_numeric(df[year_col], errors="coerce"),
        "Ancho_mm": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()

    if df_out.empty:
        raise ValueError(f"No se encontraron datos válidos en: {os.path.basename(ruta)}")

    df_out["Anio"] = df_out["Anio"].astype(int)
    df_out = df_out.groupby("Anio", as_index=True).mean(numeric_only=True)
    df_out.index.name = "Anio"
    df_out.sort_index(inplace=True)

    nombre = os.path.splitext(os.path.basename(ruta))[0]
    return df_out, nombre


def _indexar_columna_multi(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Toma una tabla cruda (año + N columnas de valor) y la devuelve indexada
    por año, con las columnas convertidas a numérico y sin las auxiliares."""
    if df_raw.shape[1] < 2:
        raise ValueError("El archivo debe tener al menos dos columnas (año + valor[es]).")

    df_raw = df_raw.copy()
    cols = list(df_raw.columns)
    year_col = None
    for c in cols:
        if str(c).lower() in ("anio", "año", "year", "anios", "años"):
            year_col = c
            break
    if year_col is None:
        year_col = cols[0]

    df_raw[year_col] = pd.to_numeric(df_raw[year_col], errors="coerce")
    df_raw = df_raw.dropna(subset=[year_col])
    df_raw[year_col] = df_raw[year_col].astype(int)
    df_raw.set_index(year_col, inplace=True)
    df_raw.index.name = "Anio"
    df_raw.sort_index(inplace=True)

    for c in df_raw.columns:
        df_raw[c] = pd.to_numeric(df_raw[c], errors="coerce")

    cols_valor = [c for c in df_raw.columns
                  if str(c).strip().lower() not in (
                      "n", "sd", "se", "samp", "samp.depth", "sample.depth",
                      "id_serie", "id", "serie", "muestra", "sample", "code"
                  )]
    if not cols_valor:
        raise ValueError("No se encontraron columnas de valores (todo es N/SD).")

    return df_raw[cols_valor]


def _leer_crudo_tabular(ruta: str) -> pd.DataFrame:
    """Lee la tabla cruda de un archivo (primera hoja si es planilla)."""
    ext = os.path.splitext(ruta)[1].lower()

    if es_planilla(ext):
        return leer_planilla(ruta)

    try:
        df_raw = pd.read_csv(ruta, sep=None, engine="python",
                             encoding="utf-8", encoding_errors="replace")
    except Exception:
        df_raw = pd.read_csv(ruta, sep=r"[\s,;\t]+", engine="python",
                             encoding="utf-8", encoding_errors="replace")

    if df_raw.shape[1] >= 2:
        test = pd.to_numeric(df_raw.iloc[1:, 1], errors="coerce")
        if test.isna().all() and len(test) > 0:
            try:
                df_raw = pd.read_csv(ruta, sep=None, engine="python", decimal=",",
                                     encoding="utf-8", encoding_errors="replace")
            except Exception:
                pass
    return df_raw


def leer_columna_multi(ruta: str) -> pd.DataFrame:
    """Lee archivo con N columnas de valor, devuelve DataFrame con índice año."""
    return _indexar_columna_multi(_leer_crudo_tabular(ruta))


def leer_columna_multi_hojas(ruta: str) -> dict[str, pd.DataFrame]:
    """Igual que `leer_columna_multi` pero devuelve TODAS las hojas.

    pandas lee solo la primera hoja por defecto, así que un .ods/.xlsx con
    varias cronologías en hojas distintas mostraba solo una. Devuelve un dict
    {nombre_hoja: df_indexado}; para archivos de texto devuelve una sola
    entrada con clave "".
    """
    if not es_planilla(ruta):
        return {"": leer_columna_multi(ruta)}

    hojas = leer_planilla(ruta, sheet_name=None)  # dict {hoja: df}
    if not isinstance(hojas, dict):
        hojas = {"": hojas}

    salida = {}
    for nombre_hoja, df_hoja in hojas.items():
        try:
            df_idx = _indexar_columna_multi(df_hoja)
        except Exception:
            continue  # hoja sin formato de cronología (notas, etc.)
        if not df_idx.empty:
            salida[str(nombre_hoja)] = df_idx
    if not salida:
        raise ValueError("Ninguna hoja tiene formato de cronología (año + valores).")
    return salida


def exportar_tabular(id_serie: str, anios: list, anchos: list, ruta: str,
                       formato: str, anchos_ewlw: list | None = None):
    """Exporta a CSV o Excel. Si anchos_ewlw está presente, agrega columnas EW_mm y LW_mm."""
    data = {"ID_Serie": id_serie, "Anio": anios, "Ancho_mm": anchos}
    if anchos_ewlw and len(anchos_ewlw) == len(anios):
        # Columnas separadas: NaN para anillos sin EW/LW detectado
        ew_col = [(t[1] if t[1] is not None else float("nan"))
                  for t in anchos_ewlw]
        lw_col = [(t[2] if t[2] is not None else float("nan"))
                  for t in anchos_ewlw]
        data["EW_mm"] = ew_col
        data["LW_mm"] = lw_col
    df = pd.DataFrame(data)
    if formato == "csv":
        with ruta_atomica(ruta) as temporal:
            df.to_csv(temporal, index=False)
    else:
        escribir_excel(df, ruta)


def leer_como_columnas_o_tabular(ruta: str, base_nombre: str) -> dict:
    """Si el archivo tiene múltiples columnas de valor, cada una como serie separada."""
    try:
        df_multi = leer_columna_multi(ruta)
    except Exception:
        df, sid = leer_tabular(ruta)
        return {sid: df}

    cols = list(df_multi.columns)
    if len(cols) == 0:
        df, sid = leer_tabular(ruta)
        return {sid: df}

    if len(cols) == 1:
        col = cols[0]
        df_serie = pd.DataFrame(
            {"Ancho_mm": pd.to_numeric(df_multi[col], errors="coerce")},
            index=df_multi.index,
        ).dropna()
        return {base_nombre: df_serie}

    resultado = {}
    for col in cols:
        df_serie = pd.DataFrame(
            {"Ancho_mm": pd.to_numeric(df_multi[col], errors="coerce")},
            index=df_multi.index,
        ).dropna()
        if df_serie.empty:
            continue
        nombre = f"{base_nombre}_{col}"
        resultado[nombre] = df_serie
    return resultado


def escribir_tabla(df, ruta, *, separador_csv=";", decimal=",", precision="%.6f"):
    """Escritura tabular común, con formato decimal explícito por consumidor."""
    ext = os.path.splitext(ruta)[1].lower()
    if es_planilla(ext):
        escribir_excel(df, ruta)
    elif ext in (".csv", ".txt", ".tsv"):
        with ruta_atomica(ruta) as temporal:
            df.to_csv(temporal, index=False, sep=separador_csv if ext == ".csv" else "\t",
                      decimal=decimal, float_format=precision)
    else:
        raise ValueError(f"Formato tabular no compatible: {ext}")
