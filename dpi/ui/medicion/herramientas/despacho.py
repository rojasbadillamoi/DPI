"""Asociación única entre modos y acciones de clic."""
from dpi.medicion.marcas import ModoMedicion

def acciones_click(*, insertar_en_segmento, borrar_punto_cercano, iniciar_seleccion_mouse, paso_calibracion, paso_medir, paso_autodetect, paso_anomalia, paso_pith, paso_espacio, paso_ewlw):
    return {
        ModoMedicion.INSERTAR: insertar_en_segmento,
        ModoMedicion.BORRAR: borrar_punto_cercano,
        ModoMedicion.SELECCIONAR: iniciar_seleccion_mouse,
        ModoMedicion.CALIBRAR: paso_calibracion,
        ModoMedicion.MEDIR: paso_medir,
        ModoMedicion.SALTO: paso_medir,
        ModoMedicion.AUTODETECT: paso_autodetect,
        ModoMedicion.ANOMALIA: paso_anomalia,
        ModoMedicion.PITH: paso_pith,
        ModoMedicion.ESPACIO: paso_espacio,
        ModoMedicion.EWLW: paso_ewlw,
    }
