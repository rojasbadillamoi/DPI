"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import math
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.marcas import ModoMedicion

def _construir_panel_seleccion(self):
    """Construye perezosamente el panel HUD para la herramienta de
    selección. Hijo del viewport (no de la escena), así NO se mueve
    cuando el usuario hace pan/zoom.

    El panel solo MUESTRA información (contador + hint). Las acciones
    se ejecutan con los botones que ya existen en la barra de
    herramientas (✕ Borrar, 🔀 Salto, ⊘ Quiebre): cuando se hace clic
    en cualquiera de esos botones estando en MODO_SELECCIONAR con
    selecciones activas, se aplica la acción en bulk a la selección
    en vez de cambiar de modo (ver `DPIInteractiva.set_modo`)."""
    from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

    self._panel_seleccion = QFrame(self.viewport())
    self._panel_seleccion.setStyleSheet(
        "QFrame { background-color: rgba(20,20,20,235); "
        "border: 1px solid rgba(255,235,59,180); border-radius: 6px; }"
    )

    lay = QHBoxLayout(self._panel_seleccion)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(10)

    # Contador + estado
    self._lbl_seleccion_count = QLabel("🎯 Clic / arrastrá un área para seleccionar")
    self._lbl_seleccion_count.setStyleSheet(
        "color: #FFEB3B; font-weight: bold; font-size: 12px;"
    )
    lay.addWidget(self._lbl_seleccion_count)

    # Separador visual
    sep = QLabel("│")
    sep.setStyleSheet("color: #555; font-size: 14px;")
    lay.addWidget(sep)

    # Hint: las acciones se ejecutan con los botones existentes
    self._lbl_seleccion_hint = QLabel(
        "Aplicar con la barra: <b style='color:#e74c3c;'>✕ Borrar</b>"
        "  ·  <b style='color:#f39c12;'>🔀 Salto</b>"
        "  ·  <b style='color:#9b59b6;'>⊘ Quiebre</b>"
    )
    self._lbl_seleccion_hint.setStyleSheet("color: #cccccc; font-size: 11px;")
    lay.addWidget(self._lbl_seleccion_hint)

    # Mantener referencias compatibles con el código existente, pero
    # ahora ninguna apunta a botones (que fueron eliminados del panel).
    self._btn_borrar_sel = None
    self._btn_salto_sel = None
    self._btn_quiebre_sel = None
    self._btn_limpiar_sel = None

    self._panel_seleccion.adjustSize()
    self._panel_seleccion.setVisible(False)


def _posicionar_panel_seleccion(self):
    """Coloca el panel en la parte superior central del viewport.
    Llamar después de mostrar el panel o cuando cambia el tamaño del view."""
    if self._panel_seleccion is None:
        return
    self._panel_seleccion.adjustSize()
    vp_w = self.viewport().width()
    panel_w = self._panel_seleccion.width()
    x = max(8, (vp_w - panel_w) // 2)
    y = 8  # 8 px desde el borde superior del viewport
    self._panel_seleccion.move(x, y)


def _mostrar_panel_seleccion(self, visible: bool):
    if self._panel_seleccion is None:
        self._construir_panel_seleccion()
    if visible:
        self._actualizar_panel_seleccion()
        self._posicionar_panel_seleccion()
        self._panel_seleccion.setVisible(True)
        self._panel_seleccion.raise_()
    else:
        self._panel_seleccion.setVisible(False)


def _actualizar_panel_seleccion(self):
    """Actualiza solo el contador del panel. Los botones de acción ya
    no están en el panel: están en la barra principal."""
    if self._panel_seleccion is None:
        return
    n = len(self._seleccion.puntos)
    if n == 0:
        self._lbl_seleccion_count.setText(
            "🎯 Clic / arrastrá un área para seleccionar")
    elif n == 1:
        self._lbl_seleccion_count.setText("🎯 1 seleccionado")
    else:
        self._lbl_seleccion_count.setText(f"🎯 {n} seleccionados")
    self._posicionar_panel_seleccion()


def _dibujar_marcadores_seleccion(self):
    """Dibuja un círculo amarillo brillante alrededor de cada anillo
    seleccionado. Se redibuja completo cada vez para simplificar."""
    # Limpiar marcadores previos
    for item in self._seleccion.items:
        try:
            self.scene().removeItem(item)
        except Exception:
            pass
    self._seleccion.items.clear()

    if not self._seleccion.puntos:
        return

    # Radio del círculo de selección en píxeles de PANTALLA constantes
    r_px = 11.0
    r = r_px * self._escala_vista()

    pen = QPen(QColor("#FFEB3B"))  # amarillo brillante
    pen.setCosmetic(True)
    pen.setWidthF(3.0)
    brush = QBrush(Qt.BrushStyle.NoBrush)

    for idx in self._seleccion.puntos:
        if 0 <= idx < len(self.coordenadas_anillos):
            x, y = self.coordenadas_anillos[idx]
            e = self.scene().addEllipse(
                x - r, y - r, 2 * r, 2 * r, pen, brush)
            e.setZValue(950)  # arriba de casi todo
            self._seleccion.items.append(e)


def _toggle_seleccion_punto(self, idx: int):
    """Alterna la selección de un punto: si estaba seleccionado lo
    deselecciona, si no lo agrega a la selección."""
    self._seleccion.alternar(idx)
    self._dibujar_marcadores_seleccion()
    self._actualizar_panel_seleccion()


def _limpiar_seleccion_completa(self):
    """Vacía la selección y oculta sus marcadores."""
    self._seleccion.puntos.clear()
    self._dibujar_marcadores_seleccion()
    self._actualizar_panel_seleccion()


def _editar_seleccion(self, tipo=None):
    if not self._seleccion.puntos:
        return
    self.guardar_en_historial()
    self.modelo_medicion.editar_puntos(self._seleccion.puntos, tipo)
    self._seleccion.puntos.clear()
    self._dibujar_marcadores_seleccion()
    self.recalcular_todas_las_distancias()
    self._actualizar_panel_seleccion()
    self.progreso_modificado.emit()


def _iniciar_seleccion_mouse(self, x, y):
    # En ModoMedicion.SELECCIONAR hay dos comportamientos según dónde se
    # haga clic:
    #   - Sobre un anillo (a tolerancia): se guarda como candidato
    #     a toggle, que se ejecutará al soltar (mouseRelease) si
    #     no hubo arrastre.
    #   - Sobre área vacía: se inicia un rectángulo de selección
    #     que se completará al soltar. Todos los anillos dentro
    #     del rectángulo se agregan a la selección.
    # Esto permite seleccionar varios anillos rápidamente
    # arrastrando un área (request del usuario).
    idx = self._indice_punto_mas_cercano(x, y)
    self._seleccion.posicion = (x, y)
    if idx is not None:
        # Posible toggle de un punto — lo decidiremos en release
        self._seleccion.candidato = idx
        self._seleccion.arrastre = False
        self._seleccion.inicio = (x, y)
    else:
        # Click en área vacía → iniciar drag rectangle
        self._seleccion.candidato = None
        self._seleccion.arrastre = True
        self._seleccion.inicio = (x, y)
        # Si había un rectángulo previo (caso raro), removerlo
        if self._seleccion.rectangulo is not None:
            try:
                self.scene().removeItem(self._seleccion.rectangulo)
            except Exception:
                pass
            self._seleccion.rectangulo = None


def _actualizar_seleccion_mouse(self, x, y):
    # ── Selección por arrastre (ModoMedicion.SELECCIONAR) ──
    # Si comenzamos un drag desde un área vacía, dibujamos el
    # rectángulo de selección que sigue al mouse.
    # Si comenzamos sobre un punto pero el mouse se aleja del punto
    # de partida (umbral 4 px de pantalla), convertimos el "posible
    # toggle" en un drag-rectangle (cancela el candidato).
    if self.modo_actual == ModoMedicion.SELECCIONAR:
        mouse_se_movio = (
            math.hypot(x - self._seleccion.posicion[0],
                       y - self._seleccion.posicion[1])
            > 4.0 * self._escala_vista()
        )
        if (self._seleccion.candidato is not None
                and not self._seleccion.arrastre
                and mouse_se_movio):
            # El usuario empezó sobre un punto pero ahora está
            # arrastrando — convertir a drag-rectangle desde la pos
            # original.
            self._seleccion.candidato = None
            self._seleccion.arrastre = True
            # _sel_drag_start ya está seteado en mousePress

        if self._seleccion.arrastre:
            x0, y0 = self._seleccion.inicio
            xa, ya = min(x0, x), min(y0, y)
            xb, yb = max(x0, x), max(y0, y)
            # Crear/actualizar el rectángulo de preview
            if self._seleccion.rectangulo is None:
                pen = QPen(QColor("#FFEB3B"))
                pen.setCosmetic(True)
                pen.setWidthF(1.5)
                pen.setStyle(Qt.PenStyle.DashLine)
                brush = QBrush(QColor(255, 235, 59, 40))  # amarillo translúcido
                self._seleccion.rectangulo = self.scene().addRect(
                    xa, ya, xb - xa, yb - ya, pen, brush)
                self._seleccion.rectangulo.setZValue(951)
            else:
                self._seleccion.rectangulo.setRect(xa, ya, xb - xa, yb - ya)
            return True

    return False
