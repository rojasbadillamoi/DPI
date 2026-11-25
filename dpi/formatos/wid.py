"""Operaciones extraídas sin modificar sus algoritmos."""
import os
import pandas as pd
import logging
logger = logging.getLogger(__name__)

def leer_wid(ruta: str) -> tuple[pd.DataFrame, str]:
    """Lee CooRecorder .wid. Devuelve (DataFrame, nombre)."""
    anchos: list[float] = []
    anio_corteza: int | None = None
    nombre = os.path.splitext(os.path.basename(ruta))[0]

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.strip()
            if not ln:
                continue
            if ln.startswith("#C DATED"):
                try:
                    anio_corteza = int(ln.split()[2])
                except (IndexError, ValueError):
                    logger.warning("leer_wid: no se pudo parsear #C DATED en '%s'", ruta)
                continue
            if ln.startswith("#"):
                continue
            token = ln.replace(",", ".")
            try:
                anchos.append(float(token))
            except ValueError:
                logger.debug("leer_wid: token ignorado '%s'", ln)

    if not anchos:
        raise ValueError(f"No se encontraron datos de ancho en: {os.path.basename(ruta)}")

    n = len(anchos)
    if anio_corteza is None:
        import datetime
        anio_corteza = datetime.date.today().year
        logger.warning("leer_wid: '%s' sin #C DATED, usando año actual.", ruta)

    anio_medula = anio_corteza - n + 1
    anios = list(range(anio_medula, anio_corteza + 1))

    df = pd.DataFrame({"Ancho_mm": anchos}, index=pd.Index(anios, name="Anio"))
    df.sort_index(inplace=True)
    return df, nombre
