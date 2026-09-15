"""
main_anillos.py — Dendro Pixel Interface (DPI)
Herramienta de medición de ancho de anillos y co-datación visual.

Pestañas:
  📷 Imágenes y Medición  — visor de imágenes con herramientas de medición
  🧭 Cronología           — generación de cronologías a partir de series .rwl
  📊 Co-Datación          — cofechado estadístico de series contra cronología
"""

import sys
import os
import logging

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QLineEdit,
    QSpinBox, QComboBox, QCheckBox,
)
from PyQt6.QtGui import QIcon

from constantes import (
    APP_NOMBRE, APP_SIGLA, VERSION, icono_app, ruta_icono)
from estilos import ESTILO_OSCURO, ESTILO_CLARO
from modulo_medicion import PestanaImagen, ExportadorDendro
from modulo_codatacion import (
    PanelCodatacion, VentanaCronologia, VentanaSkeletonPlot)
from modulo_unir import DialogoUnirRwl


# =============================================================================
# Ventana principal
# =============================================================================

class VentanaAnillos(QMainWindow):
    """Herramienta de medición de anillos y co-datación."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            f"{APP_NOMBRE} ({APP_SIGLA}) {VERSION} — Medición y Co-datación")
        if ruta_icono():
            self.setWindowIcon(icono_app())
        self.setGeometry(100, 100, 1400, 800)
        # Restaurar tema guardado (o detectar tema del sistema)
        _cfg = QSettings("MoiCedrus", "DendroAnillos")
        _saved = _cfg.value("tema_oscuro", None)
        if _saved is None:
            # Detectar tema del sistema operativo
            from PyQt6.QtGui import QPalette
            _pal = QApplication.instance().palette()
            _bg = _pal.color(_pal.ColorRole.Window).lightness()
            self._modo_oscuro = _bg < 128  # fondo oscuro = tema oscuro
        else:
            self._modo_oscuro = _saved == "true" or _saved is True
        self.exportador = ExportadorDendro(self)
        self._aplicar_estilo()
        self._construir_ui()
        self._restaurar_geometria()

        # Atajo para maximizar/restaurar desde dentro del programa. El doble
        # clic en la barra de título lo maneja el gestor de ventanas del
        # sistema (GNOME), no la aplicación; este atajo funciona siempre,
        # independiente de la configuración del escritorio.
        from PyQt6.QtGui import QShortcut, QKeySequence
        _sc_max = QShortcut(QKeySequence("F11"), self)
        _sc_max.activated.connect(self._alternar_maximizada)

    def _alternar_maximizada(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── UI ────────────────────────────────────────────────────────────────

    def _construir_ui(self):
        self._tabs = QTabWidget()
        # Pestañas reordenables: el usuario puede arrastrarlas para cambiar su
        # orden (p. ej. mover Cronología al final si lo prefiere).
        self._tabs.setMovable(True)
        self.setCentralWidget(self._tabs)

        # ── Pestaña Imágenes y Medición ───────────────────────────────────
        panel_imagenes = QWidget()
        layout_img = QVBoxLayout(panel_imagenes)

        barra_top = QHBoxLayout()
        barra_top.setSpacing(6)

        btn_abrir = QPushButton("📁 Abrir Imagen(es)")
        btn_abrir.setStyleSheet(
            "background-color: #5cb85c; color: white; "
            "font-weight: bold; font-size: 14px; padding: 8px;"
        )
        btn_abrir.clicked.connect(self._abrir_imagenes)
        barra_top.addWidget(btn_abrir)
        barra_top.addSpacing(12)

        barra_top.addWidget(QLabel("Cód:"))
        self.input_codigo_global = QLineEdit()
        self.input_codigo_global.setMaxLength(8)
        self.input_codigo_global.setFixedWidth(110)
        self.input_codigo_global.setToolTip("Código de la serie activa")
        barra_top.addWidget(self.input_codigo_global)

        barra_top.addWidget(QLabel("Dir:"))
        self.combo_dir_global = QComboBox()
        self.combo_dir_global.addItems(["Med→Cor (+1)", "Cor→Med (−1)"])
        self.combo_dir_global.setFixedWidth(110)
        barra_top.addWidget(self.combo_dir_global)

        barra_top.addWidget(QLabel("Médula:"))
        self.spin_medula_global = QSpinBox()
        self.spin_medula_global.setRange(-10000, 5000)
        # 70px era demasiado angosto: las flechas de QSpinBox necesitan
        # ~16px adicionales y con padding/borde apenas quedaban visibles.
        self.spin_medula_global.setFixedWidth(95)
        barra_top.addWidget(self.spin_medula_global)

        barra_top.addWidget(QLabel("Corteza:"))
        self.spin_corteza_global = QSpinBox()
        self.spin_corteza_global.setRange(-10000, 5000)
        self.spin_corteza_global.setFixedWidth(95)
        barra_top.addWidget(self.spin_corteza_global)

        self.check_medula_global = QCheckBox("🌱 Médula")
        # Color blanco explícito en vez de `palette(buttonText)` que en
        # Linux devuelve el color del tema NATIVO del sistema (negro por
        # defecto), no el de nuestro stylesheet. Eso hacía que el texto
        # "Médula"/"Corteza" se viera negro sobre fondo oscuro.
        self.check_medula_global.setStyleSheet(
            "QCheckBox{color:white}"
            " QCheckBox::indicator{width:13px;height:13px;border:2px solid #888;"
            "border-radius:2px;background:transparent}"
            " QCheckBox::indicator:checked{border:2px solid #FF8C00;background:#FF8C00}")
        self.check_medula_global.setToolTip(
            "¿La serie llega físicamente a la médula? (pith present)")
        barra_top.addWidget(self.check_medula_global)

        self.check_corteza_global = QCheckBox("🪵 Corteza")
        self.check_corteza_global.setStyleSheet(
            "QCheckBox{color:white}"
            " QCheckBox::indicator{width:13px;height:13px;border:2px solid #888;"
            "border-radius:2px;background:transparent}"
            " QCheckBox::indicator:checked{border:2px solid #FF8C00;background:#FF8C00}")
        self.check_corteza_global.setToolTip(
            "¿La serie llega físicamente a la corteza? (bark present)")
        barra_top.addWidget(self.check_corteza_global)

        self.input_codigo_global.textChanged.connect(self._sync_codigo)
        self.combo_dir_global.currentIndexChanged.connect(self._sync_dir)
        self.spin_medula_global.valueChanged.connect(self._sync_medula)
        self.spin_corteza_global.valueChanged.connect(self._sync_corteza)
        self.check_medula_global.stateChanged.connect(self._sync_check_medula)
        self.check_corteza_global.stateChanged.connect(self._sync_check_corteza)

        # ── Auto-detección: especie + botones (movidos desde barra de herramientas) ──
        barra_top.addSpacing(12)
        barra_top.addWidget(QLabel("🌿"))
        # Los widgets viven en PestanaImagen pero se muestran aquí
        # Se adjuntan en _abrir_imagenes después de crear la pestaña
        self._placeholder_autodetect = QHBoxLayout()
        barra_top.addLayout(self._placeholder_autodetect)

        barra_top.addStretch()

        # Botón "Unir .rwl": acceso instantáneo a la utilidad de unión de
        # archivos. Ubicado a la izquierda del botón de tema porque NO es
        # parte del flujo de medición (se puede usar sin abrir imagen) y
        # debe estar visible al instante. Color morado para diferenciarse
        # del verde de "Abrir imagen" (que es la acción principal de
        # entrada). Reemplaza la antigua utilidad DendroUnir.
        self._btn_unir = QPushButton("🔗 Unir .rwl")
        self._btn_unir.setToolTip(
            "Unir múltiples archivos .rwl en uno solo (Tucson o Excel).\n"
            "No requiere tener imágenes abiertas.")
        self._btn_unir.setStyleSheet(
            "QPushButton { background-color: #8e44ad; color: white; "
            "font-weight: bold; padding: 6px 12px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #9b59b6; }"
        )
        self._btn_unir.clicked.connect(self._abrir_dialogo_unir)
        barra_top.addWidget(self._btn_unir)

        self._btn_tema = QPushButton("🌓")
        self._btn_tema.setFixedSize(36, 36)
        self._btn_tema.setToolTip("Alternar tema claro/oscuro")
        self._btn_tema.clicked.connect(self._alternar_tema)
        barra_top.addWidget(self._btn_tema)

        layout_img.addLayout(barra_top)

        self._sincronizando = False
        self._tabs_imagenes = QTabWidget()
        self._tabs_imagenes.setTabsClosable(True)
        self._tabs_imagenes.tabCloseRequested.connect(self._cerrar_pestana)
        self._tabs_imagenes.currentChanged.connect(self._al_cambiar_pestana)
        layout_img.addWidget(self._tabs_imagenes)

        self._tabs.addTab(panel_imagenes, "📷 Imágenes y Medición")

        # ── Pestaña Co-datación ───────────────────────────────────────────
        # Se crea ANTES que la de Cronología porque la pestaña Cronología le
        # pasa la cronología generada (set_cronologia_activa).
        self._tab_codatacion = PanelCodatacion(self)

        # ── Pestaña Cronología ────────────────────────────────────────────
        # La generación de cronologías es una tarea distinta de la
        # co-datación, así que vive en su propia pestaña. Le pasamos el panel
        # de co-datación como destino de la cronología activa.
        self._tab_cronologia = VentanaCronologia(self._tab_codatacion, parent=self)
        self._tabs.addTab(self._tab_cronologia, "🧭 Cronología")

        self._tabs.addTab(self._tab_codatacion, "📊 Co-Datación")

        # ── Pestaña Skeleton (cofechado visual) ───────────────────────────
        # Banco de trabajo de cofechado con su propio selector de series.
        # Puede importar/enviar series desde/hacia Co-Datación.
        self._tab_skeleton = VentanaSkeletonPlot(self._tab_codatacion, parent=self)
        self._tabs.addTab(self._tab_skeleton, "🦴 Skeleton")

        # ── Pestaña COFECHA (control de calidad de la colección) ──────────
        # Trabaja con la colección COMPLETA: es lo que permite construir el
        # maestro excluyendo cada serie (leave-one-out) y obtener
        # correlaciones comparables con las de COFECHA.
        try:
            from modulo_cofecha_ui import PestanaCofecha
            self._tab_cofecha = PestanaCofecha(parent=self)
            self._tabs.addTab(self._tab_cofecha, "📋 COFECHA")
        except Exception as _e:
            print("No se pudo cargar la pestaña COFECHA:", _e)
        # El botón "Skeleton" de Co-Datación cambia a esta pestaña e importa
        # (opcionalmente preseleccionando el par marcado).
        self._tab_codatacion.ir_a_skeleton = self.ir_a_pestana_skeleton

        # Restaurar el orden de pestañas guardado y persistir cambios futuros.
        self._restaurar_orden_pestanas()
        self._tabs.tabBar().tabMoved.connect(self._guardar_orden_pestanas)

    def _guardar_orden_pestanas(self, *args):
        """Guarda el orden actual de las pestañas (por su texto) para
        restaurarlo la próxima vez que se abra el programa."""
        orden = [self._tabs.tabText(i) for i in range(self._tabs.count())]
        QSettings("MoiCedrus", "DendroAnillos").setValue(
            "orden_pestanas", orden)

    def _restaurar_orden_pestanas(self):
        """Reordena las pestañas según el último orden guardado.

        Importante: se usa removeTab + insertTab (que mueven la etiqueta, el
        icono Y el contenido juntos), NO tabBar().moveTab con blockSignals.
        Bloquear las señales del tabBar impide que QTabWidget sincronice el
        contenido con la etiqueta, dejando el nombre de la pestaña en un lugar
        pero su contenido en otro (muy confuso). Aquí se bloquea solo
        currentChanged del propio QTabWidget para evitar parpadeos durante el
        reordenamiento, sin afectar la sincronización etiqueta↔contenido.
        """
        guardado = QSettings("MoiCedrus", "DendroAnillos").value(
            "orden_pestanas")
        if not guardado:
            return
        self._tabs.blockSignals(True)
        try:
            for destino, texto in enumerate(guardado):
                actual = next(
                    (i for i in range(self._tabs.count())
                     if self._tabs.tabText(i) == texto), None)
                if actual is not None and actual != destino:
                    w = self._tabs.widget(actual)
                    icono = self._tabs.tabIcon(actual)
                    txt = self._tabs.tabText(actual)
                    self._tabs.removeTab(actual)
                    self._tabs.insertTab(destino, w, icono, txt)
        finally:
            self._tabs.blockSignals(False)

    def ir_a_pestana_skeleton(self, ref_nombre=None, flo_nombre=None):
        """Cambia a la pestaña Skeleton, importa las series de Co-Datación y
        preselecciona el par indicado (si lo hay)."""
        if hasattr(self, "_tab_skeleton"):
            self._tabs.setCurrentWidget(self._tab_skeleton)
            self._tab_skeleton.preseleccionar_par(ref_nombre, flo_nombre)

    def ir_a_pestana_cronologia(self):
        """Cambia el foco a la pestaña de Cronología."""
        if hasattr(self, "_tab_cronologia"):
            self._tabs.setCurrentWidget(self._tab_cronologia)

    # ── Utilidad: Unir archivos .rwl ──────────────────────────────────────

    def _abrir_dialogo_unir(self):
        """Abre el diálogo de unión de archivos .rwl como modal.

        No requiere tener imágenes abiertas — el usuario puede entrar al
        programa SOLO para unir archivos y este botón le da acceso
        instantáneo. Es la integración nativa de la antigua utilidad
        DendroUnir como parte del cajón de herramientas de DPI.
        """
        dlg = DialogoUnirRwl(self)
        dlg.exec()

    # ── Tema ──────────────────────────────────────────────────────────────

    def _alternar_tema(self):
        self._modo_oscuro = not self._modo_oscuro
        self._aplicar_estilo()
        QSettings("MoiCedrus", "DendroAnillos").setValue(
            "tema_oscuro", str(self._modo_oscuro).lower())

    def closeEvent(self, event):
        cfg = QSettings("MoiCedrus", "DendroAnillos")
        cfg.setValue("tema_oscuro", str(self._modo_oscuro).lower())
        # Recordar tamaño/posición y si quedó maximizada, para reabrir la
        # ventana como el usuario la dejó (antes siempre volvía a 1400x800).
        cfg.setValue("ventana_maximizada", self.isMaximized())
        if not self.isMaximized():
            cfg.setValue("ventana_geometria", self.saveGeometry())
        super().closeEvent(event)

    def _restaurar_geometria(self):
        """Restaura tamaño/posición y estado maximizado de la sesión previa."""
        cfg = QSettings("MoiCedrus", "DendroAnillos")
        geo = cfg.value("ventana_geometria")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass
        maximizada = cfg.value("ventana_maximizada", False)
        if maximizada is True or str(maximizada).lower() == "true":
            self.showMaximized()

    def _aplicar_estilo(self):
        # Estilo extra que se concatena al global. Cubre dos bugs:
        #
        # 1) Flechas dobles de QSpinBox no se ven. Cuando estilos.py aplica
        #    background-color y border a QSpinBox, Qt entra en modo "fully
        #    styled" y oculta las flechas nativas. Hay que estilar los
        #    sub-controls explícitamente con una IMAGEN para las flechas.
        #    Los intentos previos con CSS triangles y SVG data URI no
        #    funcionaron de forma confiable en todas las versiones de Qt.
        #    Acá usamos PNGs base64 embebidos (10x7 px, triángulos) que
        #    Qt sí renderiza siempre correctamente.
        #
        # 2) QCheckBox con `color:palette(buttonText)` se ve en negro en
        #    Linux: el palette del sistema NO se actualiza cuando aplicamos
        #    nuestro stylesheet, así que devuelve buttonText=black del tema
        #    nativo. Forzar color blanco en modo oscuro, negro en claro.
        color_texto = "white" if self._modo_oscuro else "black"
        bg_btn = "#5a5a5a" if self._modo_oscuro else "#d0d0d0"
        bg_btn_hover = "#FF8C00"
        # PNGs 10×7 con triángulos blancos (modo oscuro) o negros (claro)
        if self._modo_oscuro:
            png_up = ("iVBORw0KGgoAAAANSUhEUgAAAAoAAAAHCAYAAAAxrNxjAAAAMUlEQVR4nI2NsQ0AMA"
                      "zCHP7/mUxdUqLWIzIAAduemTZpykpS4lrcikphkvW6PNSPBNAN0SPoUBunjAAAAABJRU5ErkJggg==")
            png_down = ("iVBORw0KGgoAAAANSUhEUgAAAAoAAAAHCAYAAAAxrNxjAAAAMklEQVR4nGP8////fwYiABM"
                        "jIyMjIUWMjIyMTDAGQRORdeEyDUUhPkUYColxAgrAFhIA0TgIIPOFyJgAAAAASUVORK5CYII=")
        else:
            png_up = ("iVBORw0KGgoAAAANSUhEUgAAAAoAAAAHCAYAAAAxrNxjAAAALklEQVR4nGNgwA7+owsw4VH"
                      "0H59CDJPwmYhVIxM2QWyKmQgoggNGYhQxMDAwAAA7wgkD7c1W1gAAAABJRU5ErkJggg==")
            png_down = ("iVBORw0KGgoAAAANSUhEUgAAAAoAAAAHCAYAAAAxrNxjAAAAL0lEQVR4nGNkYGD4z0AEYG"
                        "JgYGAkQh0jE4xBjIlwXbhMQ1eIUxE2hcS4FwVghAQAN8MCEXDdZS8AAAAASUVORK5CYII=")
        estilo_extra = f"""
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 18px;
            border-left: 1px solid #666;
            background-color: {bg_btn};
        }}
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
            background-color: {bg_btn_hover};
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 18px;
            border-left: 1px solid #666;
            background-color: {bg_btn};
        }}
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
            background-color: {bg_btn_hover};
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url(data:image/png;base64,{png_up});
            width: 10px;
            height: 7px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url(data:image/png;base64,{png_down});
            width: 10px;
            height: 7px;
        }}
        /* Forzar color de texto blanco/negro en checkboxes — el palette
           nativo del sistema (palette(buttonText)) devuelve mal el color
           cuando el tema dark/light viene del stylesheet, no del sistema. */
        QCheckBox {{ color: {color_texto}; }}
        QLabel {{ color: {color_texto}; }}
        """
        base = ESTILO_OSCURO if self._modo_oscuro else ESTILO_CLARO
        QApplication.instance().setStyleSheet(base + estilo_extra)

    # ── Imágenes ──────────────────────────────────────────────────────────

    def _abrir_imagenes(self):
        cfg = QSettings("MoiCedrus", "DendroAnillos")
        ultima_carpeta = cfg.value("ultima_carpeta", "")
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar imagen(es)", ultima_carpeta,
            "Imágenes (*.png *.PNG *.jpg *.JPG *.tif *.TIF);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not rutas:
            return
        import os
        cfg.setValue("ultima_carpeta", os.path.dirname(rutas[0]))
        # Encolar y abrir de a una para que la UI responda entre imágenes
        self._cola_rutas = list(rutas)
        self._abrir_siguiente_imagen()

    def _abrir_siguiente_imagen(self):
        """Abre la primera imagen de la cola y programa la siguiente."""
        if not getattr(self, "_cola_rutas", []):
            return
        ruta = self._cola_rutas.pop(0)
        pestana = PestanaImagen(ruta, self)
        pestana.metadatos_cambiados.connect(
            lambda p=pestana:
                self._pestana_activa() is p and self._sync_desde_pestana(p))
        pestana.input_codigo.textChanged.connect(
            lambda t, p=pestana:
                self._pestana_activa() is p and self._sync_desde_pestana(p))
        pestana.combo_dir.currentIndexChanged.connect(
            lambda i, p=pestana:
                self._pestana_activa() is p and self._sync_desde_pestana(p))
        pestana.check_tiene_medula.stateChanged.connect(
            lambda s, p=pestana:
                self._pestana_activa() is p and self._sync_desde_pestana(p))
        pestana.check_tiene_corteza.stateChanged.connect(
            lambda s, p=pestana:
                self._pestana_activa() is p and self._sync_desde_pestana(p))
        nombre = os.path.basename(ruta)
        idx = self._tabs_imagenes.addTab(pestana, nombre)
        self._tabs_imagenes.setCurrentIndex(idx)
        self._sync_desde_pestana(pestana)
        # Renovar widgets de auto-detección del top bar para esta pestaña.
        # Antes era condicional (solo si count==0), por eso al abrir una
        # segunda imagen los widgets quedaban apuntando a la primera.
        self._actualizar_widgets_top_bar(pestana)
        # Si quedan imágenes, esperar un ciclo de eventos antes de abrir la siguiente
        if self._cola_rutas:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(20, self._abrir_siguiente_imagen)

    def _cerrar_pestana(self, index: int):
        widget = self._tabs_imagenes.widget(index)
        # Si esta era la pestaña ACTIVA cuyos widgets estaban en el top bar,
        # sacarlos antes de borrar la pestaña para evitar que el layout
        # quede con referencias a widgets que se van a destruir.
        if widget is not None and widget is self._pestana_activa():
            self._actualizar_widgets_top_bar(None)
        if widget:
            widget.deleteLater()
        self._tabs_imagenes.removeTab(index)
        # Si después de cerrar quedan otras pestañas, mostrar los widgets
        # de la nueva pestaña activa
        nueva_activa = self._pestana_activa()
        if nueva_activa is not None:
            self._actualizar_widgets_top_bar(nueva_activa)

    # ── Sincronización barra ↔ pestaña ────────────────────────────────────

    def _pestana_activa(self):
        return self._tabs_imagenes.currentWidget()

    def _sync_desde_pestana(self, pestana):
        if pestana is None or self._sincronizando: return
        self._sincronizando = True
        self.input_codigo_global.setText(pestana.input_codigo.text())
        self.combo_dir_global.setCurrentIndex(pestana.combo_dir.currentIndex())
        self.spin_medula_global.setValue(pestana.spin_medula.value())
        self.spin_corteza_global.setValue(pestana.spin_corteza.value())
        self.check_medula_global.setChecked(pestana.check_tiene_medula.isChecked())
        self.check_corteza_global.setChecked(pestana.check_tiene_corteza.isChecked())
        self._sincronizando = False

    def _sync_codigo(self, texto):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p: p.input_codigo.setText(texto)

    def _sync_dir(self, idx):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p: p.combo_dir.setCurrentIndex(idx)

    def _sync_medula(self, val):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p: p.spin_medula.setValue(val)

    def _sync_corteza(self, val):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p: p.spin_corteza.setValue(val)

    def _sync_check_medula(self, state):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p:
            p.check_tiene_medula.setChecked(bool(state))
            p._guardar_sidecar_anom()

    def _sync_check_corteza(self, state):
        if self._sincronizando: return
        p = self._pestana_activa()
        if p:
            p.check_tiene_corteza.setChecked(bool(state))
            p._guardar_sidecar_anom()

    def _al_cambiar_pestana(self, _idx):
        p = self._pestana_activa()
        # Renovar los widgets de auto-detección del top bar para reflejar
        # los de la pestaña ACTIVA. Este era el bug que rompía #4 (auto-
        # detección) y #5 (botones ⚙ y +): el código original solo
        # agregaba los widgets cuando placeholder.count()==0 (al abrir
        # la primera pestaña), pero nunca los rotaba al cambiar de tab.
        # Resultado: los botones quedaban conectados a una pestaña
        # distinta de la visible — o peor, a una pestaña ya cerrada.
        self._actualizar_widgets_top_bar(p)
        self._sync_desde_pestana(p)

    def _actualizar_widgets_top_bar(self, pestana):
        """Refresca los widgets de auto-detección en `_placeholder_autodetect`
        para que pertenezcan a la pestaña activa.

        Estrategia: vaciar el placeholder (`takeAt(0)`) y volver a llenarlo
        con los widgets de la pestaña dada. Como cada pestaña tiene su
        propia instancia de combo_especie/btn_cfg/btn_nueva/btn_autodetect,
        esto asegura que las señales clicked/currentTextChanged disparen
        los métodos de la pestaña correcta.

        Si pestana es None (todas cerradas), solo limpia.
        """
        # Vaciar el placeholder. takeAt(0) repetidamente extrae items en
        # orden hasta vaciar. Los widgets siguen existiendo (no se borran),
        # solo se sacan del layout y se ocultan.
        while self._placeholder_autodetect.count() > 0:
            item = self._placeholder_autodetect.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.hide()
                # Reparentar a None para que no se confunda con el layout viejo
                w.setParent(None)

        if pestana is None:
            return

        # Agregar los widgets de la pestaña activa
        for w in (pestana.combo_especie, pestana.btn_cfg_especie,
                  pestana.btn_nueva_especie, pestana.btn_autodetect):
            if w is None:
                continue
            self._placeholder_autodetect.addWidget(w)
            w.show()


# =============================================================================
# Punto de entrada
# =============================================================================

def _instalar_traduccion_espanol(app: QApplication) -> None:
    """Instala las traducciones estándar de Qt al español.

    Sin esto, los diálogos internos de Qt (QFileDialog, QMessageBox,
    confirmaciones de sobreescritura, etc.) aparecen en INGLÉS aun
    cuando la app está completamente en español. Esto es porque Qt
    no carga traducciones automáticamente — hay que instalarlas
    explícitamente con QTranslator.

    Las traducciones se buscan en orden:
      1. Carpeta estándar del sistema (QLibraryInfo.TranslationsPath)
      2. Si no se encuentran, se ignora silenciosamente (la app
         sigue funcionando, solo los diálogos internos quedan en
         inglés)

    Los archivos .qm relevantes son:
      - qtbase_es.qm  → QFileDialog, QMessageBox, botones estándar
      - qt_es.qm      → catálogo legacy (Qt 5)
    """
    from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo

    ruta_traducciones = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    locale = QLocale(QLocale.Language.Spanish)

    # Mantener referencias en el app para que no se recolecten
    app._traducciones_qt = []
    for prefijo in ("qtbase", "qt"):
        tr = QTranslator(app)
        if tr.load(locale, prefijo, "_", ruta_traducciones):
            app.installTranslator(tr)
            app._traducciones_qt.append(tr)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_SIGLA)
    app.setApplicationDisplayName(APP_NOMBRE)
    app.setApplicationVersion(VERSION)
    if ruta_icono():
        app.setWindowIcon(icono_app())
    # Identificador de escritorio. En Wayland el compositor no puede leer el
    # ícono desde la ventana como hacía X11: busca un archivo .desktop cuyo
    # nombre coincida con este identificador y saca el ícono de ahí. Sin esta
    # línea el ícono sale en la ventana pero no en el dock.
    app.setDesktopFileName("moicedrus-dpi")
    _instalar_traduccion_espanol(app)
    ventana = VentanaAnillos()
    ventana.show()
    sys.exit(app.exec())
