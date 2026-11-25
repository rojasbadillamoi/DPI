"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import math
import numpy as np
from dpi.medicion.modelo import TipoMarca
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.marcas import ModoMedicion

def iniciar_autodetect(self, imagen_bgr: np.ndarray):
    """
    Activa el modo auto-detección y cachea la imagen BGR.
    Comportamiento:
      - Si hay puntos existentes: 1er clic ancla un punto, 2do clic define el extremo.
      - Si la serie está vacía: 1er clic = un extremo, 2do clic = el otro.

    Fix de foco: después de cambiar el modo, forzar foco en la vista
    y procesar eventos pendientes. Sin esto, el primer click sobre la
    imagen se "pierde" — el foco se queda en el botón/popup que invocó
    este método, y el mousePressEvent del primer click no llega
    limpio a la vista. El usuario tenía que hacer dos clicks para
    cada punto, que era exactamente lo que reportó como bug.
    """
    self._autodeteccion.imagen = imagen_bgr
    self._autodeteccion.puntos = []
    self._autodeteccion.indice_ancla = None   # índice del punto anclado (si existe)
    for item in self._autodeteccion.items:
        self.scene().removeItem(item)
    self._autodeteccion.items.clear()
    self.cambiar_modo(ModoMedicion.AUTODETECT)
    # Forzar foco en la vista y procesar eventos pendientes — sin esto
    # el primer click se pierde porque el botón "🔍 Auto-detectar" del
    # top bar retiene el foco hasta el siguiente evento.
    self.setFocus()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()


def _paso_autodetect(self, x: float, y: float):
    """
    Máquina de estados del modo auto-detección.

    Con puntos existentes:
      Clic 1: si cae sobre un punto existente → ancla ese punto (amarillo).
              Si no hay ninguno cerca → trata como extremo libre.
      Clic 2: define el otro extremo → lanza detección entre ancla y este punto.

    Sin puntos:
      Clic 1: primer extremo (verde).
      Clic 2: segundo extremo → lanza detección entre los dos.
    """
    pen_verde = QPen(QColor("#00FF88")); pen_verde.setCosmetic(True); pen_verde.setWidthF(3.0)
    brush_verde = QBrush(QColor("#00FF88"))
    pen_amarillo = QPen(QColor("#FFD700")); pen_amarillo.setCosmetic(True); pen_amarillo.setWidthF(3.0)
    brush_nulo = QBrush(Qt.BrushStyle.NoBrush)

    coords = self.coordenadas_anillos

    # ── Primer clic ───────────────────────────────────────────────────────
    if len(self._autodeteccion.puntos) == 0:
        idx_cercano = self._indice_punto_mas_cercano(x, y)

        if idx_cercano is not None and coords:
            # Anclar punto existente
            self._autodeteccion.indice_ancla = idx_cercano
            ax, ay = coords[idx_cercano]
            marker = self.scene().addEllipse(ax - 10, ay - 10, 20, 20,
                                              pen_amarillo, brush_nulo)
            self._autodeteccion.items.append(marker)
            self._autodeteccion.puntos.append(coords[idx_cercano])
        else:
            # Extremo libre
            self._autodeteccion.indice_ancla = None
            marker = self.scene().addEllipse(x - 8, y - 8, 16, 16,
                                              pen_verde, brush_verde)
            self._autodeteccion.items.append(marker)
            self._autodeteccion.puntos.append((x, y))
        return

    # ── Segundo clic: definir extremo y lanzar detección ─────────────────
    marker2 = self.scene().addEllipse(x - 8, y - 8, 16, 16, pen_verde, brush_verde)
    self._autodeteccion.items.append(marker2)
    self._autodeteccion.puntos.append((x, y))

    p1 = self._autodeteccion.puntos[0]
    p2 = self._autodeteccion.puntos[1]

    # Línea visual del segmento a detectar
    pen_linea = QPen(QColor("#00FF88")); pen_linea.setCosmetic(True); pen_linea.setWidthF(2.0)
    pen_linea.setStyle(Qt.PenStyle.DashLine)
    linea = self.scene().addLine(p1[0], p1[1], p2[0], p2[1], pen_linea)
    self._autodeteccion.items.append(linea)

    # Delegar a la pestaña con información del ancla
    self.autodeteccion_solicitada.emit(p1, p2, self._autodeteccion.imagen, self._autodeteccion.indice_ancla)

    # Limpiar y volver a Medir
    for item in self._autodeteccion.items:
        self.scene().removeItem(item)
    self._autodeteccion.items.clear()
    self._autodeteccion.puntos.clear()
    self._autodeteccion.indice_ancla = None
    self.cambiar_modo(ModoMedicion.MEDIR)


def colocar_puntos_autodetectados(
    self,
    coordenadas: list[tuple[float, float]],
    idx_ancla: int | None = None,
    reemplazar_tramo: bool = False,
):
    """
    Inserta los puntos detectados respetando el ancla.

    idx_ancla=None      → append al final (comportamiento original).
    idx_ancla=i         → inserta a continuación del punto i, en la
                          dirección correcta detectada automáticamente.
    reemplazar_tramo    → si True, borra los puntos existentes entre
                          el ancla y el extremo antes de insertar.
    """
    if not coordenadas:
        return
    from dpi.medicion.modelo import PuntoMedicion
    coordenadas = [PuntoMedicion(c, TipoMarca.NORMAL).coordenada for c in coordenadas]
    if idx_ancla is not None and not 0 <= idx_ancla < len(self.coordenadas_anillos):
        raise ValueError('Ancla de autodetección inválida')
    self.guardar_en_historial()

    if idx_ancla is None:
        # Sin ancla: añadir al final
        for coord in coordenadas:
            self.modelo_medicion.agregar(coord, TipoMarca.NORMAL)
    else:
        n = len(self.coordenadas_anillos)
        # Detectar dirección: ¿los nuevos puntos van después o antes del ancla?
        # Comparar distancia del primer punto detectado al vecino derecho vs izquierdo
        ax, ay = self.coordenadas_anillos[idx_ancla]
        fx, fy = coordenadas[0]   # primer punto detectado (el más cercano al ancla)
        d_der = math.hypot(fx - self.coordenadas_anillos[min(idx_ancla+1, n-1)][0],
                           fy - self.coordenadas_anillos[min(idx_ancla+1, n-1)][1]) if idx_ancla < n-1 else float('inf')
        d_izq = math.hypot(fx - self.coordenadas_anillos[max(idx_ancla-1, 0)][0],
                           fy - self.coordenadas_anillos[max(idx_ancla-1, 0)][1]) if idx_ancla > 0 else float('inf')
        insertar_despues = d_der <= d_izq or idx_ancla == 0

        if insertar_despues:
            insert_at = idx_ancla + 1
            if reemplazar_tramo:
                # Determinar cuántos puntos hay hasta el extremo detectado
                ultimo_x, ultimo_y = coordenadas[-1]
                fin_tramo = insert_at
                for k in range(insert_at, n):
                    kx, ky = self.coordenadas_anillos[k]
                    if math.hypot(kx - ultimo_x, ky - ultimo_y) < self._tolerancia_punto() * 3:
                        fin_tramo = k + 1
                        break
                self.modelo_medicion.borrar(slice(insert_at, fin_tramo))
        else:
            insert_at = idx_ancla
            coordenadas = list(reversed(coordenadas))
            if reemplazar_tramo:
                ultimo_x, ultimo_y = coordenadas[-1]
                ini_tramo = 0
                for k in range(insert_at - 1, -1, -1):
                    kx, ky = self.coordenadas_anillos[k]
                    if math.hypot(kx - ultimo_x, ky - ultimo_y) < self._tolerancia_punto() * 3:
                        ini_tramo = k
                        break
                self.modelo_medicion.borrar(slice(ini_tramo, insert_at))
                insert_at = ini_tramo

        for i, coord in enumerate(coordenadas):
            self.modelo_medicion.insertar(insert_at + i, coord, TipoMarca.NORMAL)

    self.recalcular_todas_las_distancias()
    self.progreso_modificado.emit()
