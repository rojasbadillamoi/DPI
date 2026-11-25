"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import math
from dpi.medicion.calculo import ordenar_extremos_espacio
from dpi.medicion.modelo import TipoMarca
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.marcas import ModoMedicion

def _paso_espacio(self, x: float, y: float):
    """
    Modo espacio intra-anillo. Dos submodos según dónde cae el clic:

    A) SOBRE LÍNEA EXISTENTE (hay segmento azul cercano):
       Clic 1 → inserta tick AMARILLO (inicio del espacio) en la línea.
       Clic 2 → inserta tick AMARILLO (fin del espacio) en la línea.
       Resultado: prev_tick ─(azul)─ /═══espacio═══/ ─(azul)─ next_tick
       Ambos / son ticks amarillos ("espacio"), el tramo entre ellos también.

    B) EN EL EXTREMO ACTIVO (clic lejos de cualquier segmento):
       Actúa como Medir pero los puntos se insertan como "espacio".
       Clic 1 → añade tick amarillo al final del camino (inicio espacio).
       Clic 2 → añade tick amarillo al final (fin espacio).
       Vuelve automáticamente a Medir.

    Los ticks amarillos NO cuentan como límites de anillo.
    El ancho del anillo = solo los tramos azules (False), no los espacios.
    Esc cancela. Ctrl+Z deshace.
    """
    coords = self.coordenadas_anillos

    # ── Detectar si el clic cae sobre un segmento existente ───────────
    hit = self._segmento_mas_cercano(x, y) if len(coords) >= 2 else None

    pen_v = QPen(QColor("#FFD700"))   # amarillo para marcadores visuales
    pen_v.setCosmetic(True); pen_v.setWidthF(3.0)
    brush_nulo = QBrush(Qt.BrushStyle.NoBrush)

    # ══════════════════════════════════════════════════════════════════
    # SUBMODO B: extremo activo — clic lejos de la línea existente
    #
    # Estructura correcta del quiebre al medir en el extremo activo:
    #
    #  tick_N(False) ──azul── A("quiebre_ini") ══"espacio"══ B("espacio") ──azul── tick_N+1(False)
    #
    # Clic 1 → punto A: es_salto="quiebre_ini" → línea AZUL desde tick anterior,
    #                    suma distancia al anillo pero NO cierra el anillo.
    #
    # Clic 2 → punto B: es_salto="espacio" → línea AMARILLA desde A,
    #                                          tick AMARILLO (no cuenta)
    #          Vuelve a Medir. El siguiente clic normal agrega el límite final
    #          del anillo con línea azul desde B.
    # ══════════════════════════════════════════════════════════════════
    if hit is None:
        if not coords:
            try:
                self.estado_cambiado.emit(
                    "↔ Mide al menos un punto antes de insertar un quiebre.")
            except Exception:
                pass
            return

        # Primer clic: punto A — suma distancia pero NO cierra anillo
        if self._espacio.indice_inicio is None:
            self.guardar_en_historial()
            self.modelo_medicion.agregar((x, y), TipoMarca.QUIEBRE_INI)   # línea azul, suma, no cierra
            self._espacio.indice_inicio = len(coords) - 1
            self._espacio.punto_inicio   = (x, y)
            self._espacio.segmento_inicio = -1
            # Marcador visual (círculo verde para distinguirlo)
            r = 9 * self._escala_vista()
            m = self.scene().addEllipse(x-r, y-r, 2*r, 2*r, pen_v, brush_nulo)
            self._espacio.items.append(m)
            self.recalcular_todas_las_distancias()
            self.progreso_modificado.emit()
            try:
                self.estado_cambiado.emit(
                    "↔ Inicio del quiebre marcado. Haz clic en el borde final.")
            except Exception:
                pass
            return

        # Segundo clic: punto B — línea AMARILLA desde A, tick amarillo
        self.guardar_en_historial()
        self.modelo_medicion.agregar((x, y), TipoMarca.ESPACIO)   # línea amarilla desde A, tick amarillo
        self._espacio.indice_inicio = None
        self._limpiar_espacio()
        self.recalcular_todas_las_distancias()
        self.progreso_modificado.emit()
        try:
            self._resaltar_anclado(len(self.coordenadas_anillos) - 1)
            self.estado_cambiado.emit(
                "↔ Quiebre marcado. Haz clic en el límite final del anillo.")
            self._cambiar_modo_usuario(ModoMedicion.MEDIR)
        except Exception:
            pass
        return

    # ══════════════════════════════════════════════════════════════════
    # SUBMODO A: sobre línea existente
    # ══════════════════════════════════════════════════════════════════
    seg_idx, t, _ = hit
    x1, y1 = coords[seg_idx]
    x2, y2 = coords[seg_idx + 1]
    px = x1 + t * (x2 - x1)
    py = y1 + t * (y2 - y1)

    # ── Primer clic A ─────────────────────────────────────────────────
    if self._espacio.indice_inicio is None:
        self._limpiar_espacio()
        r = 9 * self._escala_vista()
        m = self.scene().addEllipse(px-r, py-r, 2*r, 2*r, pen_v, brush_nulo)
        self._espacio.items.append(m)
        self._espacio.punto_inicio   = (px, py)
        self._espacio.segmento_inicio = seg_idx
        self._espacio.indice_inicio = seg_idx
        try:
            self.estado_cambiado.emit(
                "↔ Inicio del espacio marcado. Haz clic en el borde final.")
        except Exception:
            pass
        return

    # ── Segundo clic A ────────────────────────────────────────────────
    p1, s1 = self._espacio.punto_inicio, self._espacio.segmento_inicio
    p2, s2 = (px, py), seg_idx
    self._espacio.indice_inicio = None
    self._limpiar_espacio()

    p1, s1, p2, s2 = ordenar_extremos_espacio(coords, p1, s1, p2, s2)

    if math.hypot(p1[0]-p2[0], p1[1]-p2[1]) < 2:
        try:
            self.estado_cambiado.emit("↔ Puntos demasiado cercanos. Cancelado.")
        except Exception:
            pass
        return

    # Validar que no hay ticks normales (anillos completos) entre s1 y s2
    for j in range(s1 + 1, s2 + 1):
        if j < len(self.es_salto) and self.es_salto[j] is False:
            try:
                self.estado_cambiado.emit(
                    "↔ El espacio no puede cruzar un límite de anillo.")
            except Exception:
                pass
            return

    self.guardar_en_historial()

    # Estado final deseado:
    #   prev_tick ─("quiebre_ini")─ p1 ─("espacio")─ p2 ─(False)─ next_tick
    #                                ↑ tick amarillo   ↑ tick amarillo
    #
    # p1 tiene es_salto="quiebre_ini" (azul, SUMA distancia, no cierra)
    # el tramo p1→p2 tiene es_salto="espacio" (amarillo, no suma, no cierra)
    # p2→siguiente tiene es_salto=False (reanuda normal, suma y cierra)
    #
    # Insertar de atrás hacia adelante:
    #   1) p2 en s2+1 con es_salto=False (p2→siguiente normal)
    #   2) p1 en s1+1 con es_salto="quiebre_ini" (prev→p1 azul, suma)
    #   3) El segmento p1→p2 (índice s1+2) = "espacio"
    #   4) Segmentos intermedios si s1 < s2 → también "espacio"

    # 1) Insertar p2
    self.modelo_medicion.insertar(s2 + 1, p2, TipoMarca.NORMAL)   # p2→siguiente: reanuda normal

    # 2) Insertar p1 con es_salto="quiebre_ini" (suma distancia antes del quiebre)
    self.modelo_medicion.insertar(s1 + 1, p1, TipoMarca.QUIEBRE_INI)  # prev→p1: azul, suma

    # 3) Segmento p1→p2 = "espacio"
    idx_tramo = s1 + 2
    if idx_tramo < len(self.es_salto):
        self.modelo_medicion.marcar(idx_tramo, TipoMarca.ESPACIO)

    # 4) Segmentos intermedios (si s1 < s2)
    for j in range(idx_tramo + 1, s2 + 2):
        if j < len(self.es_salto) and self.es_salto[j] is False:
            self.modelo_medicion.marcar(j, TipoMarca.ESPACIO)

    self.recalcular_todas_las_distancias()
    self.progreso_modificado.emit()
    try:
        self.estado_cambiado.emit(
            "↔ Quiebre insertado. Tramo amarillo no cuenta. Ctrl+Z para deshacer.")
        self._cambiar_modo_usuario(ModoMedicion.MEDIR)
    except Exception:
        pass


def _limpiar_espacio(self):
    for item in self._espacio.items:
        try: self.scene().removeItem(item)
        except Exception: pass
    self._espacio.items.clear()
