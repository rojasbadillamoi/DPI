"""Operaciones extraídas sin modificar sus algoritmos."""
import os
from dpi.infraestructura.escritura import ruta_atomica
import pandas as pd
EXTS_PLANILLA = (".xlsx", ".xls", ".ods")

def es_planilla(ruta_o_ext: str) -> bool:
    """True si la ruta (o extensión) corresponde a una planilla Excel/ODS."""
    valor = os.fspath(ruta_o_ext).lower() if ruta_o_ext is not None else ""
    ext = valor if valor in EXTS_PLANILLA else os.path.splitext(valor)[1]
    return ext in EXTS_PLANILLA


def leer_planilla(ruta: str, **kwargs):
    """Lee una planilla .xlsx/.xls/.ods con el motor adecuado.

    pandas elige el motor por extensión, pero solo si el módulo está
    instalado; si falta, el error ("Missing optional dependency 'odfpy'") no
    es accionable para el usuario. Acá damos un mensaje claro con la solución.
    """
    import importlib.util
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".ods" and importlib.util.find_spec("odf") is None:
        raise RuntimeError(
            "Para leer planillas de LibreOffice (.ods) falta el módulo "
            "'odfpy'.\n\nInstálalo con:  pip install odfpy\n\n"
            "Como alternativa, en LibreOffice usa «Archivo → Guardar como» y "
            "elige .xlsx o .csv.")
    if ext == ".xls" and importlib.util.find_spec("xlrd") is None:
        raise RuntimeError("Para leer planillas .xls instala xlrd: pip install xlrd")
    if ext == ".xlsx" and importlib.util.find_spec("openpyxl") is None:
        raise RuntimeError(
            "Para leer planillas de Excel (.xlsx) falta el módulo "
            "'openpyxl'.\n\nInstálalo con:  pip install openpyxl")
    return pd.read_excel(ruta, **kwargs)


def escribir_excel(df, ruta: str, index: bool = False):
    """Escribe un DataFrame a .xlsx/.ods eligiendo un motor disponible.

    pandas necesita openpyxl o xlsxwriter para .xlsx, y odfpy para .ods. Si no
    especifica engine y ninguno está instalado, lanza "No engine for filetype".
    Aquí elegimos el primero disponible y, si falta, damos un mensaje accionable.
    """
    import importlib.util
    ext = os.path.splitext(ruta)[1].lower()

    if ext == ".ods":
        if importlib.util.find_spec("odf") is not None:
            with ruta_atomica(ruta) as temporal:
                df.to_excel(temporal, index=index, engine="odf")
            return
        raise RuntimeError(
            "Para exportar a LibreOffice (.ods) falta el módulo 'odfpy'.\n\n"
            "Instálalo con:  pip install odfpy\n\n"
            "Como alternativa, exporta en CSV o TXT, que no requieren módulos "
            "adicionales.")

    for engine in ("openpyxl", "xlsxwriter"):
        if importlib.util.find_spec(engine) is not None:
            with ruta_atomica(ruta) as temporal:
                df.to_excel(temporal, index=index, engine=engine)
            return
    raise RuntimeError(
        "Para exportar a Excel (.xlsx) falta el módulo 'openpyxl'.\n\n"
        "Instálalo con:  pip install openpyxl\n\n"
        "Como alternativa, exporta en CSV o TXT, que no requieren módulos "
        "adicionales.")


def escribir_excel_merge(series_dict: dict[str, pd.DataFrame], ruta: str) -> None:
    """Escribe TODAS las series en UNA hoja Excel.

    Estructura:
      - Columna A: Año
      - Columnas B, C, D, ...: una por serie (header = ID de la serie)
      - Celdas: ancho en mm; vacías donde la serie no tiene dato para
        ese año

    Este formato es el preferido del usuario porque facilita análisis
    posterior (importar a R, hacer cofechado, etc.) sin tener que
    deshacer la separación por hojas.
    """
    if not ruta.lower().endswith((".xlsx", ".xls")):
        ruta += ".xlsx"

    # Construir DataFrame combinado con Año como index, una columna por serie
    series_alineadas: dict[str, pd.Series] = {}
    for sid, df in series_dict.items():
        if "Anio" in df.columns:
            df_local = df.set_index("Anio")
        else:
            df_local = df
        s = df_local["Ancho_mm"].copy()
        s.name = sid
        series_alineadas[sid] = s

    combinado = pd.DataFrame(series_alineadas)
    combinado.sort_index(inplace=True)
    combinado.index.name = "Anio"

    # Exportar: incluir el index (Año) como primera columna
    with ruta_atomica(ruta) as temporal:
        combinado.to_excel(temporal, sheet_name="Series", index=True)
