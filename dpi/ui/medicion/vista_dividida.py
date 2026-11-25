"""Operaciones extraídas sin modificar sus algoritmos."""
from PyQt6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
from PyQt6.QtGui import QPainter
from PyQt6.QtCore import Qt

class VistaSplitView(QGraphicsView):
    """Vista de solo lectura con zoom/pan independiente."""

    def __init__(self, escena: QGraphicsScene, parent=None):
        super().__init__(escena, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        # Permitir mover la imagen arrastrando con el mouse (mano).
        # Sin esto la ventana auxiliar solo soportaba zoom (wheel) pero no
        # paneo, lo que hacía la herramienta poco útil.
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # Estilo de scrollbars (igual que la vista principal)
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
            "QGraphicsView{border:2px solid #FF8C00; border-radius:2px;}"
        )
        # Cache de viewport: evita repintar la imagen completa en cada
        # movimiento o cambio menor — mejora notablemente la fluidez de pan
        # y zoom con imágenes grandes.
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
        event.accept()


class PanelSplit(QWidget):
    """Panel de vista dividida con selector de imagen y vista de solo lectura.

    Permite ver la misma imagen en otra posición/zoom, o bien una imagen
    diferente de otra pestaña abierta.
    """

    def __init__(self, escena_propia: QGraphicsScene, vista_principal, fuentes=lambda: ()):
        super().__init__()
        self._vista_principal = vista_principal
        self._fuentes = fuentes
        self._escena_propia = escena_propia

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Barra de selección ──
        barra = QHBoxLayout()
        barra.setContentsMargins(4, 2, 4, 2)

        lbl = QLabel("◫")
        lbl.setStyleSheet("color:#FF8C00; font-size:14px; font-weight:bold; background:transparent;")
        barra.addWidget(lbl)

        self.combo_fuente = QComboBox()
        self.combo_fuente.setToolTip("Selecciona qué imagen mostrar en este panel")
        self.combo_fuente.setMinimumWidth(140)
        self.combo_fuente.setStyleSheet(
            "QComboBox{background:#3b3b3b; color:white; border:1px solid #FF8C00; "
            "border-radius:3px; padding:2px 6px;}"
            "QComboBox QAbstractItemView{background:#3b3b3b; color:white; "
            "selection-background-color:#FF8C00;}"
        )
        self.combo_fuente.currentIndexChanged.connect(self._cambiar_fuente)
        barra.addWidget(self.combo_fuente, 1)

        # Botón sincronizar zoom/posición con la vista principal
        btn_sync = QPushButton("⟲")
        btn_sync.setFixedSize(26, 26)
        btn_sync.setToolTip("Sincronizar zoom y posición con la vista principal")
        btn_sync.setStyleSheet(
            "QPushButton{background:#555; color:white; border-radius:3px; font-size:14px;}"
            "QPushButton:hover{background:#FF8C00;}")
        btn_sync.clicked.connect(self._sincronizar_con_principal)
        barra.addWidget(btn_sync)

        layout.addLayout(barra)

        # ── Vista ──
        # El estilo (borde naranja + scrollbars) ya está aplicado por
        # VistaSplitView en su __init__, no hace falta aplicarlo aquí.
        self.vista = VistaSplitView(escena_propia, self)
        layout.addWidget(self.vista)

    def refrescar_combo(self):
        """Actualiza la lista de imágenes disponibles."""
        self.combo_fuente.blockSignals(True)
        seleccion_actual = self.combo_fuente.currentData()
        self.combo_fuente.clear()

        # Opción 1: misma imagen
        self.combo_fuente.addItem("📷 Misma imagen", userData="__self__")

        # El origen de las otras escenas lo aporta el contenedor.
        for clave, nombre, _ in self._fuentes():
            self.combo_fuente.addItem(f"📷 {nombre}", userData=clave)

        # Restaurar selección
        if seleccion_actual is not None:
            for i in range(self.combo_fuente.count()):
                if self.combo_fuente.itemData(i) == seleccion_actual:
                    self.combo_fuente.setCurrentIndex(i)
                    break

        self.combo_fuente.blockSignals(False)
        if seleccion_actual is not None and self.combo_fuente.currentData() != seleccion_actual:
            self._cambiar_fuente(self.combo_fuente.currentIndex())

    def _cambiar_fuente(self, idx):
        """Cambia la escena de la vista según la selección del combo."""
        data = self.combo_fuente.itemData(idx)
        if data == "__self__" or data is None:
            self.vista.setScene(self._escena_propia)
            return

        for clave, _, escena in self._fuentes():
            if clave == data:
                self.vista.setScene(escena)
                self.vista.fitInView(escena.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                return
        self.vista.setScene(self._escena_propia)

    def _sincronizar_con_principal(self):
        """Copia zoom y posición de la vista principal."""
        self.vista.setTransform(self._vista_principal.transform())
        center = self._vista_principal.mapToScene(
            self._vista_principal.viewport().rect().center())
        self.vista.centerOn(center)
