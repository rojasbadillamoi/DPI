"""Preparación de una serie para las métricas de comparación."""
from dpi.ciencia.transformacion import serie_numerica
from dpi.ciencia.comparacion_nucleo import SeriePreparada

def preparar_serie(datos, transformar, para_glk):
    cruda = serie_numerica(datos)
    if cruda.empty:
        return SeriePreparada(cruda, cruda, cruda)
    return SeriePreparada(cruda, transformar(datos), para_glk(datos))
