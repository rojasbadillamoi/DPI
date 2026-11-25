"""Componentes de medición de DPI."""
from enum import IntEnum
from dpi.medicion.modelo import TipoMarca


def _tipo(val):
    try:
        return TipoMarca.desde_valor(val)
    except ValueError:
        return None

class ModoMedicion(IntEnum):
    MEDIR = 1
    CALIBRAR = 2
    MOVER = 3
    SALTO = 4
    INSERTAR = 5
    BORRAR = 6
    AUTODETECT = 7
    ANOMALIA = 8
    PITH = 9
    ESPACIO = 10
    EWLW = 11
    SELECCIONAR = 12


def _es_salto_real(val) -> bool:
    """True solo si el segmento es un salto que rompe la cuenta."""
    return _tipo(val) is TipoMarca.SALTO



def _es_espacio(val) -> bool:
    """True si el segmento es un espacio intra-anillo."""
    return _tipo(val) is TipoMarca.ESPACIO



def _es_quiebre_ini(val) -> bool:
    """True si el segmento es inicio de quiebre (suma distancia, no cierra)."""
    return _tipo(val) is TipoMarca.QUIEBRE_INI



def _es_ewlw(val) -> bool:
    """True si el segmento es un límite earlywood/latewood."""
    return _tipo(val) is TipoMarca.EW_LW



def _es_amarillo(val) -> bool:
    """True si el segmento debe dibujarse en amarillo (salto o espacio)."""
    tipo = _tipo(val)
    return tipo is not None and tipo.es_amarillo


def _es_normal(val) -> bool:
    return _tipo(val) is TipoMarca.NORMAL


def _es_quiebre(val) -> bool:
    tipo = _tipo(val)
    return tipo is not None and tipo.es_quiebre


def _excluye_intensidad(val) -> bool:
    tipo = _tipo(val)
    return tipo is not None and tipo.excluye_intensidad
