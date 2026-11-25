"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
from dpi.medicion.modelo import TipoMarca
from dpi.medicion.edicion_ewlw import planificar_ewlw

def _paso_ewlw(self, x: float, y: float):
    """
    Modo EW/LW: clic sobre la línea azul del camino.
    Inserta un punto "ew_lw" (tick naranja) que divide el anillo
    en earlywood (izquierda) y latewood (derecha).
    Un anillo puede tener como máximo un límite EW/LW.
    La distancia total del anillo no cambia (EW+LW = total).
    Esc cancela. Ctrl+Z deshace.
    """
    coords = self.coordenadas_anillos
    hit = self._segmento_mas_cercano(x, y) if len(coords) >= 2 else None
    if hit is None:
        try:
            self.estado_cambiado.emit(
                "🍂 Haz clic sobre la línea azul del anillo a dividir.")
        except Exception:
            pass
        return

    indice, punto, error = planificar_ewlw(coords, self.es_salto, hit[0], hit[1])
    if error:
        try:
            self.estado_cambiado.emit(error)
        except Exception:
            pass
        return

    self.guardar_en_historial()
    self.modelo_medicion.insertar(indice, punto, TipoMarca.EW_LW)

    self.recalcular_todas_las_distancias()
    self.progreso_modificado.emit()
    try:
        self.estado_cambiado.emit(
            "🍂 Límite EW/LW insertado. Usa 🖐 Mover para ajustarlo. "
            "Ctrl+Z para deshacer.")
    except Exception:
        pass
