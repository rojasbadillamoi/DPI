"""Importación de series sin dependencia de widgets."""
from dpi.formatos.deteccion import leer_series_auto


def importar_archivo(modelo, ruta):
    """Registra un archivo completo o no modifica el modelo."""
    series = leer_series_auto(ruta)
    from dpi.series.modelo import validar_anchos_fisicos
    for nombre, datos in series.items():
        if nombre not in modelo.datos:
            if 'Ancho_mm' not in datos.columns:
                raise ValueError('La serie debe contener Ancho_mm')
            validar_anchos_fisicos(datos['Ancho_mm'])
    return modelo.registrar_lote(series)
