"""Widgets y utilidades gráficas compartidas por los módulos de DPI."""
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSpinBox
import estilos_graficos as _gr
from dpi.ui.configuracion import ultima_carpeta


def crear_boton(texto, accion, *, tooltip=None, checkable=False):
    boton = QPushButton(texto)
    boton.setCheckable(checkable)
    if tooltip is not None:
        boton.setToolTip(tooltip)
    boton.clicked.connect(accion)
    return boton


def _ultima_carpeta():
    return ultima_carpeta("ultima_carpeta_codatacion")


def _ensanchar_dialogo(caja, minimo: int = 520):
    """Evita que los botones de un QMessageBox salgan cortados.

    QMessageBox calcula su ancho a partir del TEXTO, no de los botones, así
    que con etiquetas largas ("Conservando ancho (editor)") los botones se
    recortan y no se puede leer qué hace cada uno. Se mide el ancho que
    necesitan todos los botones juntos y se fuerza ese mínimo.
    """
    try:
        botones = caja.buttons()
        necesario = sum(max(b.sizeHint().width(), b.width()) + 16
                        for b in botones) + 60
        ancho = max(int(minimo), int(necesario))
        for b in botones:
            b.setMinimumWidth(b.sizeHint().width() + 12)
        grid = caja.layout()
        if grid is not None:
            # Espaciador invisible que obliga al diálogo a ese ancho mínimo
            from PyQt6.QtWidgets import QSpacerItem, QSizePolicy
            esp = QSpacerItem(ancho, 0, QSizePolicy.Policy.Minimum,
                              QSizePolicy.Policy.Expanding)
            grid.addItem(esp, grid.rowCount(), 0, 1, grid.columnCount())
        caja.setMinimumWidth(ancho)
    except Exception:
        pass

def _agregar_hover_anio(plot_widget, formato="Año {anio}", extra=None):
    """Muestra el AÑO bajo el cursor mientras se mueve por el gráfico.

    Los ejes suelen marcar cada 5 o 10 años, así que ubicarse en el tiempo
    obliga a contar. Con esto el año aparece directamente junto al cursor.
    `extra(anio)` puede devolver texto adicional (p. ej. el valor de la serie).
    """
    try:
        etiqueta = pg.TextItem(color="#f1c40f", anchor=(0, 1))
        etiqueta.setZValue(1000)
        plot_widget.addItem(etiqueta, ignoreBounds=True)
        etiqueta.hide()

        linea = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#f1c40f", width=1, style=Qt.PenStyle.DotLine))
        linea.setZValue(999)
        plot_widget.addItem(linea, ignoreBounds=True)
        linea.hide()

        vb = plot_widget.getPlotItem().vb

        def _asegurar_items():
            # Cada redibujo llama a plot_widget.clear(), que ELIMINA todos los
            # items de la escena, incluidos la etiqueta y la línea del hover.
            # Por eso el año no aparecía nunca: los items existían en Python
            # pero ya no estaban en el gráfico. Se vuelven a agregar si faltan.
            if etiqueta.scene() is None:
                plot_widget.addItem(etiqueta, ignoreBounds=True)
            if linea.scene() is None:
                plot_widget.addItem(linea, ignoreBounds=True)

        def _mover(evt):
            pos = evt[0] if isinstance(evt, (tuple, list)) else evt
            if not plot_widget.sceneBoundingRect().contains(pos):
                etiqueta.hide()
                linea.hide()
                return
            _asegurar_items()
            punto = vb.mapSceneToView(pos)
            anio = int(round(punto.x()))
            texto = formato.format(anio=anio)
            if extra is not None:
                try:
                    ad = extra(anio)
                    if ad:
                        texto += "\n" + ad
                except Exception:
                    pass
            etiqueta.setText(texto)
            etiqueta.setPos(punto.x(), punto.y())
            linea.setPos(anio)
            etiqueta.show()
            linea.show()

        plot_widget._proxy_hover_anio = pg.SignalProxy(
            plot_widget.scene().sigMouseMoved, rateLimit=60, slot=_mover)
        plot_widget._hover_anio_items = (etiqueta, linea)
        plot_widget._hover_anio_mover = _mover  # para pruebas/reuso
    except Exception:
        pass

def _crear_barra_zoom(plot_widget, *, nombre_exportar: str = "",
                      lineas_h_exportar=()) -> QWidget:
    """Devuelve una barra compacta de controles de zoom para un PlotWidget.

    Da controles descubribles para lo que pyqtgraph ya permite con mouse,
    pero que no es evidente: zoom por área (arrastrar un rectángulo),
    ensanchar/comprimir el eje X (útil en series largas), y ver todo. La
    rueda del mouse siempre hace zoom y, fuera del modo área, arrastrar
    mueve (pan).

    Con `nombre_exportar` se agrega además el botón de descargar el gráfico.
    Es opcional y no automático a propósito: esta barra la usan también los
    gráficos auxiliares (correlación móvil, perfil de datación), donde la
    descarga para publicar no tiene sentido y solo sería ruido.
    """
    vb = plot_widget.getViewBox()
    cont = QWidget()
    fila = QHBoxLayout(cont)
    fila.setContentsMargins(0, 2, 0, 2)
    fila.setSpacing(4)
    fila.addWidget(QLabel("Zoom:"))

    btn_area = QPushButton("🔍 Área")
    btn_area.setCheckable(True)
    btn_area.setToolTip(
        "Activado: arrastra un rectángulo para hacer zoom en esa zona.\n"
        "Desactivado: arrastra para mover (pan). La rueda siempre hace zoom.")
    btn_area.toggled.connect(
        lambda a: vb.setMouseMode(
            pg.ViewBox.RectMode if a else pg.ViewBox.PanMode))
    fila.addWidget(btn_area)

    btn_mas = QPushButton("◄ ►")
    btn_mas.setMaximumWidth(48)
    btn_mas.setToolTip("Ensanchar: estira el eje X (ver menos años, más detalle).")
    btn_mas.clicked.connect(lambda: vb.scaleBy((0.7, 1.0)))
    fila.addWidget(btn_mas)

    btn_menos = QPushButton("► ◄")
    btn_menos.setMaximumWidth(48)
    btn_menos.setToolTip("Comprimir: comprime el eje X (ver más años).")
    btn_menos.clicked.connect(lambda: vb.scaleBy((1.4, 1.0)))
    fila.addWidget(btn_menos)

    btn_reset = QPushButton("⟲ Ver todo")
    btn_reset.clicked.connect(lambda: plot_widget.autoRange())
    fila.addWidget(btn_reset)

    if nombre_exportar:
        btn_export = QPushButton("💾 Descargar")
        btn_export.setToolTip(
            "Guardar el gráfico como imagen para publicar.\n\n"
            "Se vuelve a dibujar con matplotlib, así que podés elegir la\n"
            "paleta (Claro, Oscuro, Alto contraste, Sepia), el formato\n"
            "(PNG, SVG o PDF) y la resolución, sin depender del tamaño\n"
            "que tenga la ventana.")
        btn_export.clicked.connect(
            lambda: _gr.exportar_grafico_con_dialogo(
                cont, plot_widget,
                nombre_sugerido=nombre_exportar,
                carpeta_inicial=_ultima_carpeta(),
                lineas_h=lineas_h_exportar))
        fila.addWidget(btn_export)

    fila.addStretch()
    return cont

class SpinBoxFlechas(QSpinBox):
    """QSpinBox usando las flechas nativas del sistema.

    Históricamente esta clase reemplazaba las flechas del sistema con
    QToolButton custom dibujando caracteres Unicode (▲/▼), porque con
    un stylesheet global pesado las flechas nativas quedaban invisibles.
    Eso ya no aplica: con el stylesheet limpio actual (estilos.py), las
    flechas nativas se renderizan correctamente en ambos temas.

    Se mantiene la clase (en vez de usar QSpinBox directamente) para que
    sea drop-in replacement sin tocar 8 sitios, y por si en el futuro
    queremos volver a personalizar.
    """
    pass

class SeccionColapsable(QWidget):
    """Sección colapsable estilo accordion.

    Click en el header para expandir/contraer. Permite que múltiples secciones
    estén abiertas a la vez. Cuando todas están abiertas y exceden el alto
    disponible, el QScrollArea padre activa el scroll vertical.

    Estilo: usa overlays translúcidos rgba(0,0,0,XX) para que funcione tanto
    en tema oscuro como claro, igual que el patrón del módulo de medición.
    """

    def __init__(self, titulo: str, expandida: bool = True, parent=None):
        super().__init__(parent)
        self._titulo = titulo
        self._expandida = expandida

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 7px 10px;
                background-color: rgba(0, 0, 0, 50);
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgba(255, 140, 0, 60);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 80);
            }
        """)
        self.btn_toggle.clicked.connect(self.toggle)
        layout.addWidget(self.btn_toggle)

        # Contenedor sin background propio. La indentación visual viene de
        # los márgenes internos, no de un color de fondo (que rompería el
        # tema claro).
        self._contenido = QWidget()
        self._contenido_layout = QVBoxLayout(self._contenido)
        self._contenido_layout.setContentsMargins(10, 6, 4, 6)
        self._contenido_layout.setSpacing(4)
        layout.addWidget(self._contenido)

        self._actualizar()

    def _actualizar(self):
        flecha = "▼" if self._expandida else "▶"
        self.btn_toggle.setText(f"  {flecha}  {self._titulo}")
        self._contenido.setVisible(self._expandida)

    def toggle(self):
        self._expandida = not self._expandida
        self._actualizar()

    def expandir(self):
        if not self._expandida:
            self.toggle()

    def contraer(self):
        if self._expandida:
            self.toggle()

    def agregar_widget(self, widget):
        self._contenido_layout.addWidget(widget)

    def agregar_layout(self, layout):
        self._contenido_layout.addLayout(layout)


import dpi.ciencia.transformacion as _tr


def crear_selector(parent=None, metodo_inicial: str = _tr.DIFFLOG):
    """QComboBox con los métodos disponibles, para reutilizar en las pestañas."""
    from PyQt6.QtWidgets import QComboBox
    combo = QComboBox(parent)
    for m in _tr.METODOS:
        combo.addItem(_tr.ETIQUETAS[m], m)
    combo.setCurrentIndex(_tr.METODOS.index(metodo_inicial)
                          if metodo_inicial in _tr.METODOS else 0)
    combo.setToolTip(
        "Transformación aplicada antes de calcular la correlación.\n\n"
        + "\n\n".join(f"• {_tr.ETIQUETAS[m]}\n{_tr.DESCRIPCIONES[m]}" for m in _tr.METODOS)
        + "\n\nCon el mismo método, la r coincide entre pestañas.")
    return combo
