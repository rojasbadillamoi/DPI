"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import math
from dpi.medicion.calculo import posicion_insercion
from dpi.medicion.modelo import TipoMarca
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.marcas import ModoMedicion

def _salto_rapido(self, x, y):
    if self.modo_actual in (ModoMedicion.MEDIR, ModoMedicion.SALTO, ModoMedicion.INSERTAR,
                            ModoMedicion.BORRAR, ModoMedicion.ANOMALIA):
        modo_previo = self.modo_actual
        self.modo_actual = ModoMedicion.SALTO
        try:
            self._paso_medir(x, y)
        except BaseException:
            self.modo_actual = modo_previo
            raise
        # _paso_medir ya restaura ModoMedicion.MEDIR tras un salto;
        # si el modo previo era especial (anomalía, etc.) lo respetamos
        if modo_previo not in (ModoMedicion.MEDIR, ModoMedicion.SALTO):
            self.modo_actual = modo_previo
            try:
                self.modo_cambiado.emit(modo_previo)
            except Exception:
                pass


def _insertar_en_segmento(self, x, y):
    if len(self.coordenadas_anillos) < 2:
        return
    hit = self._segmento_mas_cercano(x, y)
    if hit is not None and hit[2] < self._tolerancia_segmento():
        mejor_idx = hit[0]
        self.guardar_en_historial()
        self.modelo_medicion.insertar(mejor_idx + 1, (x, y), TipoMarca.NORMAL)
        self.notificar_edicion()


def _borrar_punto_cercano(self, x, y):
    idx = self._indice_punto_mas_cercano(x, y)
    if idx is not None:
        self.guardar_en_historial()
        self.modelo_medicion.borrar(idx)
        self._limpiar_anclado()
        self.notificar_edicion()


def _limpiar_anclado(self):
    """Elimina el resaltado visual del punto ancla."""
    if self._item_anclado is not None:
        try:
            self.scene().removeItem(self._item_anclado)
        except Exception:
            pass
        self._item_anclado = None
    self._idx_anclado = None


def _resaltar_anclado(self, idx: int):
    """Dibuja un círculo amarillo sobre el punto anclado."""
    self._limpiar_anclado()
    if idx < 0 or idx >= len(self.coordenadas_anillos):
        return   # índice inválido tras deshacer/borrar
    self._idx_anclado = idx
    x, y = self.coordenadas_anillos[idx]
    pen  = QPen(QColor("#FFD700")); pen.setCosmetic(True); pen.setWidthF(3.0)
    brush = QBrush(Qt.BrushStyle.NoBrush)
    r = 10 * self._escala_vista()
    self._item_anclado = self.scene().addEllipse(x - r, y - r, 2*r, 2*r, pen, brush)


def _paso_medir(self, x: float, y: float):
    """
    Lógica unificada para los modos Medir y Salto.

    Estado de la máquina:
      • Sin ancla + puntos existentes → busca punto cercano para anclar.
        Si no hay ninguno cerca → ancla al extremo más cercano y añade.
      • Sin ancla + serie vacía       → primer punto de la serie.
      • Con ancla                     → inserta punto adyacente al ancla,
        detectando dirección automáticamente.
    """
    coords = self.coordenadas_anillos
    es_salto_modo = self.modo_actual == ModoMedicion.SALTO

    # ── Serie vacía: primer punto ────────────────────────────────────
    if not coords:
        self.guardar_en_historial()
        self.modelo_medicion.agregar((x, y), TipoMarca.NORMAL)
        self._resaltar_anclado(0)
        self.recalcular_todas_las_distancias()
        if es_salto_modo:
            self._cambiar_modo_usuario(ModoMedicion.MEDIR)
        self.progreso_modificado.emit()
        return

    # ── Sin ancla: intentar seleccionar punto existente ──────────────
    if self._idx_anclado is None:
        idx = self._indice_punto_mas_cercano(x, y)
        if idx is not None:
            # El clic fue sobre un punto → anclar sin añadir nada
            self._resaltar_anclado(idx)
            return
        else:
            # Clic lejos de cualquier punto → anclar al extremo más cercano
            d0 = math.hypot(x - coords[0][0],  y - coords[0][1])
            d1 = math.hypot(x - coords[-1][0], y - coords[-1][1])
            self._resaltar_anclado(0 if d0 < d1 else len(coords) - 1)
            # Caemos al bloque "con ancla" para insertar de inmediato
            # (este clic también es el de inserción)

    # ── Con ancla: insertar punto adyacente ──────────────────────────
    idx_a = self._idx_anclado
    n = len(coords)
    # Guard: ancla puede haber quedado fuera de rango tras deshacer
    if idx_a is None or idx_a >= n:
        self._limpiar_anclado()
        idx_a = n - 1
        self._resaltar_anclado(idx_a)

    insert_pos = posicion_insercion(coords, idx_a, (x, y))

    self.guardar_en_historial()
    self.modelo_medicion.insertar(insert_pos, (x, y), TipoMarca.SALTO if es_salto_modo else TipoMarca.NORMAL)

    # El nuevo ancla pasa a ser el punto recién insertado
    self._resaltar_anclado(insert_pos)

    self.recalcular_todas_las_distancias()

    if es_salto_modo:
        self._limpiar_anclado()
        self._cambiar_modo_usuario(ModoMedicion.MEDIR)

    self.progreso_modificado.emit()
