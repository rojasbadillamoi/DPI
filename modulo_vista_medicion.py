"""Componentes de medición de DPI."""

from modulo_pith_ui import HerramientaPith

from dpi.ui.medicion.render import RenderMedicion

import math
from dpi.medicion.calculo import segmento_mas_cercano, indice_punto_mas_cercano, anchos_puntos, anios_por_punto, dist_punto_segmento
import numpy as np
from dpi.medicion.modelo import ModeloMedicion, PuntoMedicion, HistorialMedicion, TipoMarca
from PyQt6.QtWidgets import QWidget, QDialog, QGraphicsView, QGraphicsScene, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox, QDoubleSpinBox, QComboBox, QToolTip, QGraphicsEllipseItem, QDialogButtonBox
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from modulo_pith import ajustar_circulo_minimos_cuadrados, ajuste_degenerado
from dpi.medicion.constantes import MM_POR_PULGADA, PIXELES_POR_MM_DEFECTO, MAX_PASOS_HISTORIAL
from dpi.ui.medicion.constantes import TOLERANCIA_CLICK_PUNTO, TOLERANCIA_CLICK_SEGMENTO
from dpi.ui.colores import INTERVALO_MARCADOR_DECADA, INTERVALO_MARCADOR_CINCUENTENA, INTERVALO_MARCADOR_CENTENA, COLOR_PUNTO_ACTIVO, COLOR_LINEA_ACTIVA, COLOR_SALTO, COLOR_GUIA, COLOR_CALIBRACION, COLOR_PUNTO_INACTIVO, COLOR_EWLW, TIPOS_ANOMALIA
from dpi.ui.medicion.herramientas.estado import conserva_ancla
from dpi.medicion.marcas import _es_amarillo, _es_espacio, _es_ewlw, _es_quiebre_ini, _es_salto_real
from dpi.medicion.marcas import ModoMedicion


from dpi.ui.medicion.vista_dividida import VistaSplitView, PanelSplit






from dpi.ui.medicion.calibracion import DialogoCalibracionRegla



import dpi.ui.medicion.herramientas.calibrar as calibrar


import dpi.ui.medicion.herramientas.seleccion as seleccion


import dpi.ui.medicion.herramientas.espacios as espacios


import dpi.ui.medicion.herramientas.ewlw as ewlw


import dpi.ui.medicion.herramientas.marcado as marcado


import dpi.ui.medicion.herramientas.autodetectar as autodetectar


from dpi.ui.medicion.herramientas.despacho import acciones_click


from dpi.ui.medicion.herramientas.estado import (
    EstadoCalibracion, EstadoSeleccion, EstadoEspacio, EstadoAutodeteccion,
)


class VistaInteractiva(QGraphicsView):
    """
    Vista de imagen con herramientas de marcado de anillos.

    Modos disponibles (constantes MODO_*):
      1 ANADIR    — clic para añadir punto de anillo
      2 CALIBRAR  — clic en dos puntos para calibrar escala
      3 MOVER     — arrastrar puntos o hacer pan de la imagen
      4 SALTO     — añade un salto (discontinuidad del camino)
      5 INSERTAR  — inserta un punto en un segmento existente
      6 BORRAR    — elimina un punto con clic
      7 AUTODETECT — marca médula y corteza para auto-detección
    """

    mediciones_actualizadas = pyqtSignal(list)
    progreso_modificado = pyqtSignal()
    estado_cambiado = pyqtSignal(str)
    modo_cambiado = pyqtSignal(object)
    anomalias_modificadas = pyqtSignal()
    confirmar_pith_solicitado = pyqtSignal()
    origen_calibracion_cambiado = pyqtSignal(str)
    guardado_solicitado = pyqtSignal()
    autodeteccion_solicitada = pyqtSignal(object, object, object, object)

    def __init__(self, escena: QGraphicsScene, parent=None, *, modelo=None,
                 datacion=lambda: None, tipo_anomalia=lambda: None,
                 configuracion_pith=lambda: (5, "rg"), mediciones=lambda: ()):
        super().__init__(escena, parent)
        self._obtener_datacion = datacion
        self._obtener_tipo_anomalia = tipo_anomalia

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)

        # Estilo de scrollbars — el global de estilos.py solo cubre la
        # vertical, dejando la horizontal con el default del sistema (blanco
        # en algunos temas de Linux). Acá la estilamos local para que se vea
        # consistente con el resto de la UI.
        self.setStyleSheet(
            "QScrollBar:horizontal{background:#3b3b3b; height:10px;}"
            "QScrollBar::handle:horizontal{background:#5a5a5a;"
            " border-radius:4px; min-width:20px;}"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal{"
            " width:0px; background:none;}"
            "QScrollBar:vertical{background:#3b3b3b; width:10px;}"
            "QScrollBar::handle:vertical{background:#5a5a5a;"
            " border-radius:4px; min-height:20px;}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{"
            " height:0px; background:none;}"
        )

        # Estado de medición
        self.modelo_medicion = modelo if modelo is not None else ModeloMedicion()
        self._calibracion = EstadoCalibracion()
        # Items visuales de calibración (puntos, línea, texto) — se limpian
        # al cancelar/aceptar/reiniciar la calibración.

        self._render = RenderMedicion(self.scene, self._escala_vista)

        # Estado de interacción
        self.modo_actual: ModoMedicion = ModoMedicion.MEDIR
        self._acciones_click = acciones_click(
            insertar_en_segmento=self._insertar_en_segmento,
            borrar_punto_cercano=self._borrar_punto_cercano,
            iniciar_seleccion_mouse=self._iniciar_seleccion_mouse,
            paso_calibracion=self._paso_calibracion,
            paso_medir=self._paso_medir,
            paso_autodetect=self._paso_autodetect,
            paso_anomalia=self._paso_anomalia,
            paso_pith=self._paso_pith,
            paso_espacio=self._paso_espacio,
            paso_ewlw=self._paso_ewlw,
        )
        # Anomalías: {anio: tipo_str}
        self._punto_arrastrado_idx: int | None = None
        self._is_panning: bool = False
        self._last_pan_pos = None
        self._linea_guia = None
        self._item_hover_prev = None
        # Estado del modo Medir/Salto: punto de anclaje seleccionado
        self._idx_anclado: int | None = None   # índice del punto de partida
        self._item_anclado = None               # resaltado visual del ancla

        # Historial de deshacer
        self._historial = HistorialMedicion(self.modelo_medicion, MAX_PASOS_HISTORIAL)

        # Auto-detección: almacena los dos puntos (médula, corteza)
        self._autodeteccion = EstadoAutodeteccion()
        # Imagen OpenCV cacheada para no releerla en cada detección

        # Espacio intra-anillo: selección de dos puntos existentes
        self._espacio = EstadoEspacio()

        # Pens y brushes — cosméticos (grosor en px pantalla, invariante al zoom)
        self._pen_punto       = QPen()
        self._brush_punto     = QBrush(QColor(COLOR_PUNTO_ACTIVO))
        self._pen_linea       = QPen()
        self._pen_salto       = QPen()
        self._pen_guia        = QPen(QColor(COLOR_GUIA))
        self._pen_guia.setStyle(Qt.PenStyle.DashLine)
        self._pen_guia.setCosmetic(True)
        self._pen_guia.setWidthF(1.0)
        self._pen_calibracion = QPen()
        self._pen_ewlw        = QPen()
        self._actualizar_pens()   # inicializa colores y grosores

        self._herramienta_pith = HerramientaPith(
            self.scene, self.viewport, self._escala_vista,
            lambda: self.coordenadas_anillos, lambda: self.pixeles_por_mm,
            lambda: (self._datacion_render() or (0, 0, True))[2],
            configuracion_pith, mediciones, self.estado_cambiado.emit)

        # ── Herramienta de selección múltiple ──
        # Permite al usuario seleccionar varios anillos a la vez (clic
        # alterna selección por punto) y aplicarles una acción común:
        # borrarlos todos, convertirlos a salto o convertirlos a quiebre.
        self._seleccion = EstadoSeleccion()

        # Estado para selección por arrastre (rectángulo).
        # Cuando el usuario hace clic+drag en ModoMedicion.SELECCIONAR sobre un
        # área vacía, dibujamos un rectángulo de selección. Al soltar,
        # todos los anillos dentro del rectángulo se agregan a la selección.

        # Panel flotante (HUD) con los botones de acción. Se muestra solo
        # en ModoMedicion.SELECCIONAR. Lo construimos perezosamente la primera vez
        # que se entra al modo (para no impactar la inicialización).
        self._panel_seleccion: 'QFrame | None' = None
        self._lbl_seleccion_count: 'QLabel | None' = None
        self._btn_borrar_sel = None
        self._btn_salto_sel = None
        self._btn_quiebre_sel = None
        self._btn_limpiar_sel = None

        self.cambiar_modo(ModoMedicion.MEDIR)

    # -------------------------------------------------------------------------
    # Historial
    # -------------------------------------------------------------------------

    @property
    def coordenadas_anillos(self):
        return self.modelo_medicion.coordenadas

    @property
    def es_salto(self):
        return self.modelo_medicion.marcas

    def guardar_en_historial(self):
        self._historial.guardar()

    def limpiar_historial(self):
        self._historial.limpiar()

    def deshacer_ultimo(self):
        self._aplicar_historial(self._historial.deshacer)

    def rehacer_ultimo(self):
        self._aplicar_historial(self._historial.rehacer)

    def _aplicar_historial(self, operacion):
        anomalias = dict(self.anomalias)
        if operacion():
            self._actualizar_tras_historial()
            if anomalias != self.anomalias:
                self.anomalias_modificadas.emit()

    def _actualizar_tras_historial(self):
        self._limpiar_anclado()
        if self._linea_guia:
            self.scene().removeItem(self._linea_guia)
            self._linea_guia = None
        self.recalcular_todas_las_distancias()
        self.progreso_modificado.emit()

    # -------------------------------------------------------------------------
    # Modos
    # -------------------------------------------------------------------------

    def _cambiar_modo_usuario(self, modo):
        self.cambiar_modo(modo)
        self.modo_cambiado.emit(modo)

    def aplicar_accion_seleccion(self, modo):
        """Aplica acciones masivas desde la barra sin exponer la selección."""
        if self.modo_actual != ModoMedicion.SELECCIONAR or not self._seleccion.puntos:
            return modo
        acciones = {ModoMedicion.BORRAR: self._ejecutar_borrar_seleccionados,
                    ModoMedicion.SALTO: self._ejecutar_convertir_a_salto,
                    ModoMedicion.ESPACIO: self._ejecutar_convertir_a_quiebre}
        if modo in acciones:
            acciones[modo]()
            return ModoMedicion.MEDIR
        return modo

    def cambiar_modo(self, nuevo_modo: ModoMedicion):
        modo_anterior = self.modo_actual  # capturar antes de asignar
        self.modo_actual = nuevo_modo
        # Limpiar ancla visual al salir del modo Medir/Salto
        if not conserva_ancla(nuevo_modo):
            self._limpiar_anclado()
        # Al entrar a ModoMedicion.ESPACIO limpiar la línea guía de Medir
        # pero NO borrar el ancla — así al volver a Medir se reanuda
        if nuevo_modo == ModoMedicion.ESPACIO:
            if self._linea_guia:
                self.scene().removeItem(self._linea_guia)
                self._linea_guia = None
        # Limpiar selección espacio al salir del modo
        if nuevo_modo != ModoMedicion.ESPACIO:
            self._espacio.indice_inicio = None
            self._limpiar_espacio()
        # Limpiar items visuales del modo PITH al salir de ese modo.
        # Bug previo: si el usuario activaba "Anillos al centro" y luego
        # cambiaba a otra herramienta (Mover, Borrar, etc.), los círculos
        # naranjas, líneas y texto del análisis quedaban dibujados en la
        # imagen indefinidamente. Solo se limpiaban con Enter (confirmar) o
        # Esc — pero cualquier otro modo de salida los dejaba huérfanos.
        # Usamos modo_anterior (capturado antes de asignar) porque
        # self.modo_actual ya fue actualizado a nuevo_modo arriba.
        if (modo_anterior == ModoMedicion.PITH and nuevo_modo != ModoMedicion.PITH
                and hasattr(self, "limpiar_pith")):
            self.limpiar_pith()
        # NOTA: NO limpiamos items de calibración al cambiar de modo.
        # Las marcas persisten como recordatorio visual de que la imagen
        # fue calibrada. Solo se borran cuando el usuario inicia una nueva
        # calibración (iniciar_calibracion las limpia al inicio) o cancela
        # el diálogo de mm.
        # ── Manejo del panel de la herramienta de selección ──
        # Al entrar: mostrar panel + resetear estado de drag.
        # Al salir: limpiar selección, drag activo y panel.
        if nuevo_modo == ModoMedicion.SELECCIONAR:
            self._seleccion.arrastre = False
            self._seleccion.candidato = None
            self._mostrar_panel_seleccion(True)
        elif modo_anterior == ModoMedicion.SELECCIONAR:
            # Si quedó un rectángulo de drag en la escena, removerlo
            if self._seleccion.rectangulo is not None:
                try:
                    self.scene().removeItem(self._seleccion.rectangulo)
                except Exception:
                    pass
                self._seleccion.rectangulo = None
            self._seleccion.arrastre = False
            self._seleccion.candidato = None
            self._limpiar_seleccion_completa()
            self._mostrar_panel_seleccion(False)

        if not conserva_ancla(nuevo_modo) and self._linea_guia:
            self.scene().removeItem(self._linea_guia)
            self._linea_guia = None
        cursores = {
            ModoMedicion.MEDIR:       Qt.CursorShape.CrossCursor,
            ModoMedicion.CALIBRAR:    Qt.CursorShape.CrossCursor,
            ModoMedicion.SALTO:       Qt.CursorShape.CrossCursor,
            ModoMedicion.MOVER:       Qt.CursorShape.OpenHandCursor,
            ModoMedicion.INSERTAR:    Qt.CursorShape.ArrowCursor,
            ModoMedicion.BORRAR:      Qt.CursorShape.ArrowCursor,
            ModoMedicion.AUTODETECT:  Qt.CursorShape.CrossCursor,
            ModoMedicion.ANOMALIA:    Qt.CursorShape.PointingHandCursor,
            ModoMedicion.PITH:        Qt.CursorShape.CrossCursor,
            ModoMedicion.ESPACIO:     Qt.CursorShape.CrossCursor,
            ModoMedicion.EWLW:        Qt.CursorShape.CrossCursor,
            ModoMedicion.SELECCIONAR: Qt.CursorShape.PointingHandCursor,
        }
        self.setCursor(cursores.get(nuevo_modo, Qt.CursorShape.ArrowCursor))

    def _limpiar_items_calibracion(self):
        'Elimina puntos / línea / texto de una calibración previa.'
        return calibrar._limpiar_items_calibracion(self)

    def iniciar_calibracion(self, objetivo_mm: float | None=None):
        'Inicia el modo de calibración por regla.\n\n        Flujo:\n          1. Si había marcas de calibración anteriores, se borran (nueva\n             calibración reemplaza la anterior).\n          2. Click 1 → marca punto inicial\n          3. Click 2 → marca punto final + dibuja línea con distancia en px,\n             luego pregunta los mm (QInputDialog)\n          4. Si OK: aplica calibración. Las marcas SE MANTIENEN como\n             recordatorio visual de que la imagen está calibrada (etiqueta\n             cambia a "✓ Calibrada: X px = Y mm").\n          5. Si Cancel: se borran las marcas (no hubo calibración).\n        '
        return calibrar.iniciar_calibracion(self, objetivo_mm)

    # -------------------------------------------------------------------------
    # ── Propiedad pixeles_por_mm ──────────────────────────────────────────

    @property
    def anomalias(self):
        return self.modelo_medicion.anomalias

    @anomalias.setter
    def anomalias(self, valor):
        self.modelo_medicion.anomalias = dict(valor)

    @property
    def pixeles_por_mm(self) -> float:
        return self.modelo_medicion.pixeles_por_mm

    @pixeles_por_mm.setter
    def pixeles_por_mm(self, valor: float):
        self.modelo_medicion.pixeles_por_mm = valor
        self._actualizar_pens()

    def _actualizar_pens(self):
        """
        Recalcula el grosor de los pens en función de los DPI actuales.
        Los pens son COSMÉTICOS: su grosor se expresa en píxeles de pantalla,
        invariante al zoom, pero proporcional a la resolución de la imagen.

        Lógica:
          - A 2400 DPI (defecto, ~94 px/mm) queremos líneas de 2 px → grosor base.
          - A menor DPI (imagen más gruesa por px) escalamos proporcionalmente.
          - Mínimo 1.5 px, máximo 5 px para evitar extremos.
        """
        dpi = self.pixeles_por_mm * MM_POR_PULGADA
        # Grosor base calibrado para 2400 DPI
        factor = dpi / 2400.0
        grosor_linea  = max(1.5, min(5.0, 2.0 * factor))
        grosor_tick   = max(1.5, min(5.0, 2.0 * factor))
        grosor_calib  = max(2.0, min(6.0, 3.0 * factor))

        def _make(color, grosor, estilo=Qt.PenStyle.SolidLine) -> QPen:
            p = QPen(QColor(color))
            p.setCosmetic(True)
            p.setWidthF(grosor)
            p.setStyle(estilo)
            return p

        self._pen_punto       = _make(COLOR_PUNTO_ACTIVO, grosor_tick)
        self._brush_punto     = QBrush(QColor(COLOR_PUNTO_ACTIVO))
        self._pen_linea       = _make(COLOR_LINEA_ACTIVA, grosor_linea)
        self._pen_salto       = _make(COLOR_SALTO, grosor_linea, Qt.PenStyle.DashLine)
        self._pen_ewlw        = _make(COLOR_EWLW, grosor_tick)
        self._pen_calibracion = _make(COLOR_CALIBRACION, grosor_calib)

    # ── Utilidades de dibujo proporcionales al zoom ───────────────────────


    def _escala_vista(self) -> float:
        """
        Devuelve cuántas unidades de escena equivalen a 1 píxel de pantalla.
        Usado para que las líneas perpendiculares mantengan largo visual constante.
        """
        t = self.transform()
        # El factor de escala horizontal de la transformación afín
        escala_px_por_escena = t.m11()   # >1 = zoom in, <1 = zoom out
        return 1.0 / escala_px_por_escena if escala_px_por_escena != 0 else 1.0

    def _datacion_render(self):
        return self._obtener_datacion()

    def redibujar_todo(self):
        self._render.redibujar_todo(self.modelo_medicion.captura(), self.pixeles_por_mm,
            self._datacion_render(), self.anomalias,
            (self._pen_punto, self._pen_linea, self._pen_salto, self._pen_ewlw))

    def _anio_en_indice(self, idx: int) -> int | None:
        """Devuelve el año calendario del punto en coordenadas_anillos[idx], o None."""
        datacion = self._datacion_render()
        if datacion is None:
            return None
        anio_medula, anio_corteza, medula_a_corteza = datacion
        anios, _ = anios_por_punto(self.modelo_medicion.captura(),
            self.pixeles_por_mm, anio_medula, anio_corteza, medula_a_corteza)
        return anios[idx] if 0 <= idx < len(anios) else None

    def _dibujar_anomalias(self):
        self._render.dibujar_anomalias(self.modelo_medicion.captura(), self.pixeles_por_mm,
                                      self._datacion_render(), self.anomalias)

    def recalcular_todas_las_distancias(self):
        """
        Calcula el ancho de cada anillo.

        Estructura de es_salto:
          False    → segmento normal (cuenta, cierra anillo)
          True     → salto (no cuenta, cierra anillo previo, inicia nuevo)
          "espacio"→ quiebre intra-anillo (no cuenta, no cierra)
          "ew_lw"  → límite EW/LW (cuenta, NO cierra — el anillo continúa)

        Un anillo se cierra cuando se encuentra un segmento con val=False
        (el límite del anillo) o al final del camino.
        Los segmentos ew_lw se acumulan junto con los False del mismo anillo.
        """
        distancias = anchos_puntos(self.modelo_medicion.captura(), self.pixeles_por_mm)
        self.mediciones_actualizadas.emit(distancias)

    def notificar_edicion(self):
        self.recalcular_todas_las_distancias()
        self.progreso_modificado.emit()

    _dist_punto_segmento = staticmethod(dist_punto_segmento)

    def _tolerancia_punto(self) -> float:
        return TOLERANCIA_CLICK_PUNTO / self.transform().m11()

    def _tolerancia_segmento(self) -> float:
        return TOLERANCIA_CLICK_SEGMENTO / self.transform().m11()

    def _indice_punto_mas_cercano(self, x: float, y: float) -> int | None:
        return indice_punto_mas_cercano(self.coordenadas_anillos, x, y, self._tolerancia_punto())

    # =========================================================================
    # Selección múltiple — métodos
    # =========================================================================

    def _construir_panel_seleccion(self):
        'Construye perezosamente el panel HUD para la herramienta de\n        selección. Hijo del viewport (no de la escena), así NO se mueve\n        cuando el usuario hace pan/zoom.\n\n        El panel solo MUESTRA información (contador + hint). Las acciones\n        se ejecutan con los botones que ya existen en la barra de\n        herramientas (✕ Borrar, 🔀 Salto, ⊘ Quiebre): cuando se hace clic\n        en cualquiera de esos botones estando en MODO_SELECCIONAR con\n        selecciones activas, se aplica la acción en bulk a la selección\n        en vez de cambiar de modo (ver `DPIInteractiva.set_modo`).'
        return seleccion._construir_panel_seleccion(self)

    def _posicionar_panel_seleccion(self):
        'Coloca el panel en la parte superior central del viewport.\n        Llamar después de mostrar el panel o cuando cambia el tamaño del view.'
        return seleccion._posicionar_panel_seleccion(self)

    def _mostrar_panel_seleccion(self, visible: bool):
        return seleccion._mostrar_panel_seleccion(self, visible)

    def _actualizar_panel_seleccion(self):
        'Actualiza solo el contador del panel. Los botones de acción ya\n        no están en el panel: están en la barra principal.'
        return seleccion._actualizar_panel_seleccion(self)

    def _dibujar_marcadores_seleccion(self):
        'Dibuja un círculo amarillo brillante alrededor de cada anillo\n        seleccionado. Se redibuja completo cada vez para simplificar.'
        return seleccion._dibujar_marcadores_seleccion(self)

    def _toggle_seleccion_punto(self, idx: int):
        'Alterna la selección de un punto: si estaba seleccionado lo\n        deselecciona, si no lo agrega a la selección.'
        return seleccion._toggle_seleccion_punto(self, idx)

    def _limpiar_seleccion_completa(self):
        'Vacía la selección y oculta sus marcadores.'
        return seleccion._limpiar_seleccion_completa(self)

    # ── Acciones sobre la selección ──

    def _editar_seleccion(self, tipo=None):
        return seleccion._editar_seleccion(self, tipo)

    def _ejecutar_borrar_seleccionados(self):
        self._editar_seleccion()

    def _ejecutar_convertir_a_salto(self):
        self._editar_seleccion(TipoMarca.SALTO)

    def _ejecutar_convertir_a_quiebre(self):
        self._editar_seleccion(TipoMarca.ESPACIO)

    # =========================================================================
    # Eventos de ratón
    # =========================================================================

    def wheelEvent(self, event):
        """
        Zoom con rueda del mouse o touchpad.

        - Mouse wheel: cada "click" envía angleDelta=±120, factor 1.25 / 0.8
          como antes.
        - Touchpad: envía MUCHOS eventos con deltas pequeños (típicamente
          pixelDelta es no-null). Aplicamos un factor proporcional MUY
          pequeño por evento para que el zoom acumulado sea suave en vez
          de exagerado.

        Además debouncing del `redibujar_todo`: en gestos de touchpad llegan
        decenas de eventos por segundo, no tiene sentido redibujar todo
        en cada uno. Esperamos 80 ms de quietud antes de redibujar.
        """
        # Botón central presionado durante el scroll → ignorar zoom (es paneo)
        if event.buttons() & Qt.MouseButton.MiddleButton:
            return

        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()

        if not pixel_delta.isNull():
            # Touchpad de alta resolución: delta en píxeles
            delta_y = pixel_delta.y()
            if delta_y == 0:
                return
            # 200 px ≈ doble zoom. Suave pero responsive.
            factor = 1.0 + (delta_y / 200.0)
        elif not angle_delta.isNull():
            # Rueda de mouse: angleDelta en 1/8 de grado; 120 = un "click"
            delta_y = angle_delta.y()
            if delta_y == 0:
                return
            # Mantener comportamiento clásico: 1.25 por click, escalado
            # proporcionalmente a la magnitud del delta
            factor = 1.25 ** (delta_y / 120.0)
        else:
            return

        # Limitar el factor por evento para evitar saltos enormes
        factor = max(0.5, min(2.0, factor))

        self.scale(factor, factor)

        # Debounce: en vez de redibujar_todo() en cada evento de touchpad,
        # esperamos a que el usuario "termine" de hacer zoom (80 ms de
        # quietud) y entonces redibujamos una vez. Esto evita la "recarga"
        # constante que mencionaba el usuario.
        #
        # IMPORTANTE: el timer se dispara si hay camino activo O si hay
        # caminos inactivos. Antes solo se chequeaba coordenadas_anillos,
        # entonces al terminar un radio (que vacía la lista activa) los
        # caminos guardados se quedaban "congelados" al último zoom desde
        # el cual fueron renderizados.
        if self.coordenadas_anillos or self._render.hay_inactivos:
            if not hasattr(self, '_zoom_debounce_timer'):
                from PyQt6.QtCore import QTimer
                self._zoom_debounce_timer = QTimer(self)
                self._zoom_debounce_timer.setSingleShot(True)
                self._zoom_debounce_timer.timeout.connect(self._redibujar_post_zoom)
            self._zoom_debounce_timer.start(80)

    def _redibujar_post_zoom(self):
        """Redibuja después del zoom (llamado por el debounce timer)."""
        if self.coordenadas_anillos:
            self.redibujar_todo()
        # Reescalar marcadores de selección si los hay (su radio se
        # calcula con _escala_vista() para mantener tamaño constante
        # en pantalla — al cambiar el zoom hay que regenerarlos).
        if self._seleccion.puntos:
            self._dibujar_marcadores_seleccion()
        # Re-renderizar caminos inactivos para que labels y ticks usen
        # la escala nueva. Sin esto, los labels viejos quedan con el
        # tamaño de un zoom anterior (lo cual hace aparecer un "100"
        # enorme tras alejar/acercar).
        if self._render.hay_inactivos:
            self._render.redibujar_inactivos(self.pixeles_por_mm, self._pen_salto)

    def event(self, ev):
        """Intercepta el evento `ShortcutOverride` para que las teclas
        Delete/Backspace en MODO_SELECCIONAR las maneje keyPressEvent (bulk
        borrar selección) en vez del QShortcut global (que cambiaría a
        MODO_BORRAR).

        Qt envía ShortcutOverride al widget con foco ANTES de disparar
        QShortcut. Si el widget acepta el evento, el shortcut se inhibe
        y la tecla llega a keyPressEvent. Si no lo acepta, el shortcut
        toma precedencia.
        """
        if ev.type() == QEvent.Type.ShortcutOverride:
            if self.modo_actual == ModoMedicion.SELECCIONAR:
                if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                    ev.accept()
                    return True
        return super().event(ev)

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        x, y = pos.x(), pos.y()
        boton = event.button()
        if boton == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if boton == Qt.MouseButton.RightButton:
            self._salto_rapido(x, y)
            return
        if boton != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if self.modo_actual == ModoMedicion.MOVER:
            self._iniciar_mover(x, y, event)
            return
        accion = self._acciones_click.get(self.modo_actual)
        if accion is None:
            return super().mousePressEvent(event)
        accion(x, y)

    def _salto_rapido(self, x, y):
        return marcado._salto_rapido(self, x, y)

    def _iniciar_seleccion_mouse(self, x, y):
        return seleccion._iniciar_seleccion_mouse(self, x, y)

    def _paso_anomalia(self, x: float, y: float):
        """
        Clic en MODO_ANOMALIA: asigna el tipo activo (seleccionado en la barra)
        al anillo más cercano. Si el anillo ya tiene ese mismo tipo, lo quita (toggle).
        """
        idx = self._indice_punto_mas_cercano(x, y)
        if idx is None or idx == 0:
            return
        anio = self._anio_en_indice(idx)
        if anio is None:
            return

        # Obtener tipo activo desde el combo de la pestaña
        try:
            tipo_activo = self._obtener_tipo_anomalia()
        except Exception:
            return
        if not tipo_activo:
            return

        self.guardar_en_historial()
        tipo_actual = self.anomalias.get(anio)
        if tipo_actual == tipo_activo:
            # Toggle: quitar si ya tiene el mismo tipo
            self.anomalias.pop(anio, None)
        else:
            # Asignar (sobreescribe si tenía otro tipo)
            self.anomalias[anio] = tipo_activo

        self._dibujar_anomalias()
        try:
            self.anomalias_modificadas.emit()
        except Exception:
            pass

    def _paso_pith(self, x: float, y: float):
        return self._herramienta_pith._paso_pith(x, y)

    def _preview_pith_mouse(self, x: float, y: float):
        return self._herramienta_pith._preview_pith_mouse(x, y)

    def _limpiar_preview_pith_mouse(self):
        return self._herramienta_pith._limpiar_preview_pith_mouse()

    def _actualizar_circulo_pith(self):
        return self._herramienta_pith._actualizar_circulo_pith()

    def confirmar_pith(self):
        return self._herramienta_pith._confirmar_pith()

    def limpiar_pith(self):
        return self._herramienta_pith._limpiar_items_pith()

    def _actualizar_hud_pith(self, html_text: str, color: str = "#FF8C00"):
        return self._herramienta_pith._actualizar_hud_pith(html_text, color)

    def resizeEvent(self, event):
        """Reposicionar el HUD del pith y el panel de selección cuando
        cambia el tamaño del widget."""
        super().resizeEvent(event)
        if hasattr(self, "_herramienta_pith"):
            self._herramienta_pith.reposicionar_hud()
        # Reposicionar también el panel de selección si está visible
        if (hasattr(self, "_panel_seleccion")
                and self._panel_seleccion is not None
                and self._panel_seleccion.isVisible()):
            self._posicionar_panel_seleccion()

    def mapa_anio_coordenada(self) -> dict[int, tuple[float, float]]:
        """Devuelve un dict {año: (x, y)} para cada límite de anillo válido."""
        mapa: dict[int, tuple[float, float]] = {}
        coords = self.coordenadas_anillos
        if not coords or len(coords) < 2:
            return mapa
        datacion = self._datacion_render()
        if datacion is None:
            return mapa
        anio_medula, anio_corteza, med_a_cor = datacion

        anios, cierres = anios_por_punto(self.modelo_medicion.captura(),
            self.pixeles_por_mm, anio_medula, anio_corteza, med_a_cor)
        return {anios[i]: coords[i] for i in sorted(cierres)}

    def _segmento_mas_cercano(self, x: float, y: float) -> tuple[int, float, float] | None:
        return segmento_mas_cercano(self.coordenadas_anillos, x, y, self._tolerancia_segmento())

    def _paso_espacio(self, x: float, y: float):
        '\n        Modo espacio intra-anillo. Dos submodos según dónde cae el clic:\n\n        A) SOBRE LÍNEA EXISTENTE (hay segmento azul cercano):\n           Clic 1 → inserta tick AMARILLO (inicio del espacio) en la línea.\n           Clic 2 → inserta tick AMARILLO (fin del espacio) en la línea.\n           Resultado: prev_tick ─(azul)─ /═══espacio═══/ ─(azul)─ next_tick\n           Ambos / son ticks amarillos ("espacio"), el tramo entre ellos también.\n\n        B) EN EL EXTREMO ACTIVO (clic lejos de cualquier segmento):\n           Actúa como Medir pero los puntos se insertan como "espacio".\n           Clic 1 → añade tick amarillo al final del camino (inicio espacio).\n           Clic 2 → añade tick amarillo al final (fin espacio).\n           Vuelve automáticamente a Medir.\n\n        Los ticks amarillos NO cuentan como límites de anillo.\n        El ancho del anillo = solo los tramos azules (False), no los espacios.\n        Esc cancela. Ctrl+Z deshace.\n        '
        return espacios._paso_espacio(self, x, y)


    def _paso_ewlw(self, x: float, y: float):
        '\n        Modo EW/LW: clic sobre la línea azul del camino.\n        Inserta un punto "ew_lw" (tick naranja) que divide el anillo\n        en earlywood (izquierda) y latewood (derecha).\n        Un anillo puede tener como máximo un límite EW/LW.\n        La distancia total del anillo no cambia (EW+LW = total).\n        Esc cancela. Ctrl+Z deshace.\n        '
        return ewlw._paso_ewlw(self, x, y)

    def _limpiar_espacio(self):
        return espacios._limpiar_espacio(self)
        # No limpiar _idx_espacio_inicio aquí — se maneja en _paso_espacio

    def keyPressEvent(self, event):
        """Enter confirma el modo pith; Esc lo cancela."""
        if self.modo_actual == ModoMedicion.PITH:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                try:
                    self.confirmar_pith_solicitado.emit()
                except Exception:
                    pass
                return
            if event.key() == Qt.Key.Key_Escape:
                self.limpiar_pith()
                try:
                    self._cambiar_modo_usuario(ModoMedicion.MEDIR)
                    self.estado_cambiado.emit("Estimación cancelada.")
                except Exception:
                    pass
                return
        if self.modo_actual == ModoMedicion.ESPACIO:
            if event.key() == Qt.Key.Key_Escape:
                self._espacio.indice_inicio = None
                self._limpiar_espacio()
                try:
                    self.estado_cambiado.emit("↔ Selección de espacio cancelada.")
                except Exception:
                    pass
                return
        # Modo selección múltiple: atajos de teclado
        if self.modo_actual == ModoMedicion.SELECCIONAR:
            # Delete o Backspace → borrar los seleccionados
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._ejecutar_borrar_seleccionados()
                return
            # Esc → limpiar selección y volver a Medir
            if event.key() == Qt.Key.Key_Escape:
                self._limpiar_seleccion_completa()
                try:
                    self._cambiar_modo_usuario(ModoMedicion.MEDIR)
                except Exception:
                    pass
                return
        super().keyPressEvent(event)

    def _iniciar_mover(self, x, y, event):
        idx = self._indice_punto_mas_cercano(x, y)
        if idx is not None:
            self.guardar_en_historial()
            self._punto_arrastrado_idx = idx
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self._is_panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _insertar_en_segmento(self, x, y):
        return marcado._insertar_en_segmento(self, x, y)

    def _borrar_punto_cercano(self, x, y):
        return marcado._borrar_punto_cercano(self, x, y)

    def _paso_calibracion(self, x, y):
        'Procesa los clicks de calibración.\n\n        Flujo:\n          - Click 1: marca el punto inicial\n          - Click 2: marca el punto final + dibuja línea + pregunta los mm\n                     → aplica calibración y limpia las marcas\n        '
        return calibrar._paso_calibracion(self, x, y)

    def _actualizar_etiqueta_calibracion(self, dist_px: float, dist_mm: float):
        'Reemplaza el texto de "📏 X px" por "✓ Calibrada: X mm = Y px"\n        para que el usuario sepa que la calibración ya está aplicada.\n        Las marcas (puntos y línea) se mantienen como recordatorio visual.\n\n        El texto usa ItemIgnoresTransformations para tamaño constante en\n        pantalla independiente del zoom.\n        '
        return calibrar._actualizar_etiqueta_calibracion(self, dist_px, dist_mm)

    # ------------------------------------------------------------------
    # Modo MEDIR / SALTO con ancla seleccionable
    # ------------------------------------------------------------------

    def _limpiar_anclado(self):
        'Elimina el resaltado visual del punto ancla.'
        return marcado._limpiar_anclado(self)

    def _resaltar_anclado(self, idx: int):
        'Dibuja un círculo amarillo sobre el punto anclado.'
        return marcado._resaltar_anclado(self, idx)

    def _paso_medir(self, x: float, y: float):
        '\n        Lógica unificada para los modos Medir y Salto.\n\n        Estado de la máquina:\n          • Sin ancla + puntos existentes → busca punto cercano para anclar.\n            Si no hay ninguno cerca → ancla al extremo más cercano y añade.\n          • Sin ancla + serie vacía       → primer punto de la serie.\n          • Con ancla                     → inserta punto adyacente al ancla,\n            detectando dirección automáticamente.\n        '
        return marcado._paso_medir(self, x, y)

    def _anadir_punto(self, x, y):
        """Alias de compatibilidad — delega a _paso_medir."""
        self._paso_medir(x, y)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.pos())
        x, y = pos.x(), pos.y()
        if self._actualizar_seleccion_mouse(x, y):
            return
        # ── Preview de arco en modo pith con 2 puntos ──
        if self.modo_actual == ModoMedicion.PITH and self._herramienta_pith.esperando_curvatura:
            self._preview_pith_mouse(x, y)

        self._actualizar_cursor_mouse(x, y)
        self._actualizar_tooltip_mouse(event)
        super().mouseMoveEvent(event)
        if self._actualizar_paneo_mouse(event):
            return
        if self._actualizar_arrastre_mouse(x, y):
            return
        self._actualizar_guia_mouse(event, x, y)

    def _actualizar_seleccion_mouse(self, x, y):
        return seleccion._actualizar_seleccion_mouse(self, x, y)

    def _actualizar_cursor_mouse(self, x, y):
        # Cursor dinámico según modo
        if self.modo_actual == ModoMedicion.ESPACIO:
            sobre_linea = self._segmento_mas_cercano(x, y) is not None
            self.setCursor(
                Qt.CursorShape.CrossCursor if sobre_linea
                else Qt.CursorShape.ArrowCursor
            )

        elif self.modo_actual == ModoMedicion.BORRAR:
            hovering = any(
                math.hypot(px - x, py - y) < self._tolerancia_punto()
                for px, py in self.coordenadas_anillos
            )
            self.setCursor(Qt.CursorShape.CrossCursor if hovering else Qt.CursorShape.ArrowCursor)

        elif self.modo_actual == ModoMedicion.INSERTAR:
            tol = self._tolerancia_segmento()
            hovering = any(
                self._dist_punto_segmento(
                    x, y,
                    self.coordenadas_anillos[i][0], self.coordenadas_anillos[i][1],
                    self.coordenadas_anillos[i + 1][0], self.coordenadas_anillos[i + 1][1],
                ) < tol
                for i in range(len(self.coordenadas_anillos) - 1)
            )
            self.setCursor(Qt.CursorShape.CrossCursor if hovering else Qt.CursorShape.ArrowCursor)

    def _actualizar_tooltip_mouse(self, event):
        # Tooltip en puntos
        item = self.itemAt(event.pos())
        if isinstance(item, QGraphicsEllipseItem) and hasattr(item, "anio_texto"):
            if item != self._item_hover_prev:
                QToolTip.showText(event.globalPosition().toPoint(), item.anio_texto, self.viewport())
                self._item_hover_prev = item
        elif self._item_hover_prev is not None:
            QToolTip.hideText()
            self._item_hover_prev = None

    def _actualizar_paneo_mouse(self, event):
        # Pan con botón central (independiente del modo)
        if self._is_panning and self._last_pan_pos and not (
            self.modo_actual == ModoMedicion.MOVER and self._punto_arrastrado_idx is not None
        ):
            if event.buttons() & Qt.MouseButton.MiddleButton or (
                self.modo_actual == ModoMedicion.MOVER and event.buttons() & Qt.MouseButton.LeftButton
            ):
                delta = event.pos() - self._last_pan_pos
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                self._last_pan_pos = event.pos()
                return True

        # Pan de la imagen (modo mover, sin punto seleccionado)
        if self.modo_actual == ModoMedicion.MOVER and self._is_panning and self._last_pan_pos:
            delta = event.pos() - self._last_pan_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_pan_pos = event.pos()
            return True

        return False

    def _actualizar_arrastre_mouse(self, x, y):
        # Arrastre de punto
        if self.modo_actual == ModoMedicion.MOVER and self._punto_arrastrado_idx is not None:
            self.modelo_medicion.mover(self._punto_arrastrado_idx, (x, y))
            self.recalcular_todas_las_distancias()
            return True

        return False

    def _actualizar_guia_mouse(self, event, x, y):
        # Línea guía hacia el cursor
        if self.modo_actual == ModoMedicion.ESPACIO and self.coordenadas_anillos:
            # Línea guía desde el punto A ya insertado en el camino
            if self._espacio.indice_inicio is not None:
                x_ant, y_ant = self._espacio.punto_inicio
                pen_esp = QPen(QColor("#00FF88"))
                pen_esp.setCosmetic(True)
                pen_esp.setWidthF(1.5)
                pen_esp.setStyle(Qt.PenStyle.DashLine)
                if self._linea_guia is None:
                    self._linea_guia = self.scene().addLine(x_ant, y_ant, x, y, pen_esp)
                else:
                    self._linea_guia.setLine(x_ant, y_ant, x, y)
                    self._linea_guia.setPen(pen_esp)
            elif self._linea_guia:
                self.scene().removeItem(self._linea_guia)
                self._linea_guia = None

        elif self.modo_actual in (ModoMedicion.MEDIR, ModoMedicion.SALTO, ModoMedicion.ANOMALIA,
                                   ModoMedicion.INSERTAR, ModoMedicion.BORRAR) and self.coordenadas_anillos:
            # Botón derecho presionado → previsualizar salto
            es_salto_preview = bool(event.buttons() & Qt.MouseButton.RightButton)
            modo_guia = ModoMedicion.SALTO if es_salto_preview else self.modo_actual
            if modo_guia not in (ModoMedicion.MEDIR, ModoMedicion.SALTO):
                # En otros modos solo mostrar guía si hay ancla activa
                if self._idx_anclado is None:
                    return
            # La guía sale desde el punto anclado (o el último si no hay ancla)
            if self._idx_anclado is not None and self._idx_anclado < len(self.coordenadas_anillos):
                x_ant, y_ant = self.coordenadas_anillos[self._idx_anclado]
            else:
                self._limpiar_anclado()   # ancla inválida tras deshacer → resetear
                x_ant, y_ant = self.coordenadas_anillos[-1]
            pen = self._pen_salto if modo_guia == ModoMedicion.SALTO else self._pen_guia
            if self._linea_guia is None:
                self._linea_guia = self.scene().addLine(x_ant, y_ant, x, y, pen)
            else:
                self._linea_guia.setLine(x_ant, y_ant, x, y)
                self._linea_guia.setPen(pen)

    def mouseReleaseEvent(self, event):
        # ── Selección por arrastre (ModoMedicion.SELECCIONAR) ──
        # Si terminamos un drag-rectangle: encontrar todos los anillos
        # dentro del área y agregarlos a la selección.
        # Si fue solo un click sobre un punto (sin arrastre): toggle.
        if (self.modo_actual == ModoMedicion.SELECCIONAR
                and event.button() == Qt.MouseButton.LeftButton):
            if self._seleccion.arrastre and self._seleccion.rectangulo is not None:
                # Calcular los bounds del rectángulo final
                rect = self._seleccion.rectangulo.rect()
                xa, ya = rect.left(), rect.top()
                xb, yb = rect.right(), rect.bottom()
                # Buscar anillos dentro
                indices_dentro = []
                for i, (px, py) in enumerate(self.coordenadas_anillos):
                    if xa <= px <= xb and ya <= py <= yb:
                        indices_dentro.append(i)
                # Agregar al set de seleccionados (no toggle, para que
                # arrastres sucesivos sumen sin deseleccionar lo previo).
                for i in indices_dentro:
                    self._seleccion.puntos.add(i)
                # Limpiar el preview del rectángulo
                try:
                    self.scene().removeItem(self._seleccion.rectangulo)
                except Exception:
                    pass
                self._seleccion.rectangulo = None
                self._seleccion.arrastre = False
                # Redibujar marcadores + actualizar panel
                self._dibujar_marcadores_seleccion()
                self._actualizar_panel_seleccion()
                return
            elif self._seleccion.candidato is not None:
                # No hubo arrastre: ejecutar el toggle del punto candidato
                self._toggle_seleccion_punto(self._seleccion.candidato)
                self._seleccion.candidato = None
                return
            # Si no hubo ni drag ni candidato, no hacemos nada
            self._seleccion.arrastre = False
            self._seleccion.candidato = None

        # Botón central: fin del paneo
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self._last_pan_pos = None
            # Restaurar cursor según el modo activo
            cursores = {
                ModoMedicion.MEDIR:    Qt.CursorShape.CrossCursor,
                ModoMedicion.SALTO:    Qt.CursorShape.CrossCursor,
                ModoMedicion.MOVER:    Qt.CursorShape.OpenHandCursor,
                ModoMedicion.INSERTAR: Qt.CursorShape.ArrowCursor,
                ModoMedicion.BORRAR:   Qt.CursorShape.ArrowCursor,
                ModoMedicion.ANOMALIA: Qt.CursorShape.PointingHandCursor,
            }
            self.setCursor(cursores.get(self.modo_actual, Qt.CursorShape.ArrowCursor))
            return

        if self.modo_actual == ModoMedicion.MOVER:
            if self._is_panning:
                self._is_panning = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self._punto_arrastrado_idx is not None:
                self._punto_arrastrado_idx = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.progreso_modificado.emit()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Auto-detección de anillos
    # -------------------------------------------------------------------------

    def iniciar_autodetect(self, imagen_bgr: np.ndarray):
        '\n        Activa el modo auto-detección y cachea la imagen BGR.\n        Comportamiento:\n          - Si hay puntos existentes: 1er clic ancla un punto, 2do clic define el extremo.\n          - Si la serie está vacía: 1er clic = un extremo, 2do clic = el otro.\n\n        Fix de foco: después de cambiar el modo, forzar foco en la vista\n        y procesar eventos pendientes. Sin esto, el primer click sobre la\n        imagen se "pierde" — el foco se queda en el botón/popup que invocó\n        este método, y el mousePressEvent del primer click no llega\n        limpio a la vista. El usuario tenía que hacer dos clicks para\n        cada punto, que era exactamente lo que reportó como bug.\n        '
        return autodetectar.iniciar_autodetect(self, imagen_bgr)

    def _paso_autodetect(self, x: float, y: float):
        '\n        Máquina de estados del modo auto-detección.\n\n        Con puntos existentes:\n          Clic 1: si cae sobre un punto existente → ancla ese punto (amarillo).\n                  Si no hay ninguno cerca → trata como extremo libre.\n          Clic 2: define el otro extremo → lanza detección entre ancla y este punto.\n\n        Sin puntos:\n          Clic 1: primer extremo (verde).\n          Clic 2: segundo extremo → lanza detección entre los dos.\n        '
        return autodetectar._paso_autodetect(self, x, y)

    def colocar_puntos_autodetectados(self, coordenadas: list[tuple[float, float]], idx_ancla: int | None=None, reemplazar_tramo: bool=False):
        '\n        Inserta los puntos detectados respetando el ancla.\n\n        idx_ancla=None      → append al final (comportamiento original).\n        idx_ancla=i         → inserta a continuación del punto i, en la\n                              dirección correcta detectada automáticamente.\n        reemplazar_tramo    → si True, borra los puntos existentes entre\n                              el ancla y el extremo antes de insertar.\n        '
        return autodetectar.colocar_puntos_autodetectados(self, coordenadas, idx_ancla, reemplazar_tramo)

    # -------------------------------------------------------------------------
    # Caminos inactivos (otros radios guardados)
    # -------------------------------------------------------------------------

    def cargar_caminos_inactivos(self, caminos: dict):
        self._render.cargar_caminos_inactivos(caminos, self.pixeles_por_mm, self._pen_salto)

    def eliminar_camino_inactivo(self, nombre):
        self._render.eliminar_inactivo(nombre)

    def toggle_camino_inactivo(self, nombre: str, visible: bool):
        self._render.toggle_inactivo(nombre, visible)

    def cargar_camino_activo(self, coordenadas: list, es_salto: list, *, redibujar=True):
        self.modelo_medicion.cargar(coordenadas, es_salto)
        if redibujar:
            self.redibujar_todo()
