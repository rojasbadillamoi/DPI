"""
modulo_medicion.py — Módulo de medición interactiva de anillos de árboles.

Contiene:
  - ExportadorDendro: escritura de archivos Tucson, CSV y Excel.
  - VistaInteractiva: lienzo con herramientas de marcado, calibración y edición.
  - PestanaImagen: pestaña completa por imagen con panel de co-datación en vivo.
"""
from dpi.ui.configuracion import ajustes_ui

from modulo_medicion_especial_ui import (ContextoRadio, ContextoImagen,
    ControlPith, ControlEWLW, ControlIntensidad)
from dpi.ui.medicion.tareas import GestorTareasMedicion
from modulo_exportacion_medicion_ui import ExportadorDendro


import modulo_medicion_ui

import os
from dpi.medicion.calculo import anchos_puntos, escala_desde_dpi
import logging
from dpi.medicion.datos import mediciones_desde_anchos, mediciones_radio
from dpi.medicion.sesion import guardar_sesion, leer_sesion

import cv2
import numpy as np
from dpi.ui.configuracion import ultima_carpeta
import dpi.ciencia.transformacion as _tr
from dpi.medicion.modelo import ModeloSesionMedicion, RadioMedicion, TipoMarca
import pandas as pd
from dpi.infraestructura.imagen import leer_imagen_bgr, detectar_dpi, preparar_banda_rgb
from dpi.formatos.wid import leer_wid
from dpi.formatos.deteccion import leer_dendro_auto
from dpi.formatos.pos import leer_pos, escribir_pos
from dpi.formatos.planillas import escribir_excel
from dpi.formatos.exportacion import asegurar_extension
from dpi.formatos.tabular import exportar_tabular
from dpi.formatos.tucson import exportar_tucson_ewlw, _escribir_tucson

from PyQt6.QtWidgets import QApplication, QGraphicsPixmapItem, QFileDialog, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QInputDialog, QMessageBox, QSpinBox, QListWidgetItem, QDialog
from PyQt6.QtGui import QImage, QPixmap, QPen, QColor, QBrush, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSettings, QSignalBlocker

from estilos import SECUNDARIO_QSS
import dpi.infraestructura.json_seguro as _js
from dpi.medicion.autodeteccion import (
    cargar_perfiles, guardar_perfiles,
    extraer_perfil, detectar_limites, posiciones_a_coordenadas,
 )
from modulo_autodeteccion_ui import DialogoEspecie, DialogoPreviewDeteccion
from dpi.medicion.constantes import DPI_DEFECTO, MM_POR_PULGADA, PIXELES_POR_MM_DEFECTO
from dpi.formatos.constantes import TUCSON_MAX_CHARS_ID
from dpi.ui.colores import TIPOS_ANOMALIA

logger = logging.getLogger(__name__)

# Modos de interacción del lienzo


# =============================================================================
# UTILIDADES DE es_salto
# =============================================================================
# es_salto[i] puede ser:
#   False        → límite de anillo normal (tick rojo, cuenta y cierra anillo)
#   True         → salto (tick amarillo, rompe la cuenta de anillos)
#   "espacio"    → tramo del quiebre intra-anillo (amarillo, NO suma, NO cierra)
#   "quiebre_ini"→ inicio de quiebre (azul, SUMA distancia, NO cierra anillo)
#   "ew_lw"      → límite earlywood/latewood (suma, NO cierra)


# =============================================================================
# EXPORTADOR
# =============================================================================

from dpi.medicion.marcas import ModoMedicion, _es_ewlw

from dpi.medicion.ewlw import anchos_ewlw_puntos




from dpi.ui.configuracion import carpeta_medicion as _ultima_carpeta


# =============================================================================
# PESTAÑA INDIVIDUAL POR IMAGEN
# =============================================================================

import dpi.ui.medicion.control_sesion as control_sesion


import dpi.ui.medicion.control_exportacion as control_exportacion


import dpi.ui.medicion.control_radios as control_radios


class PestanaImagen(QWidget):
    """
    Pestaña completa asociada a una imagen escaneada.
    Incluye el lienzo de marcado, la gestión de radios guardados,
    la co-datación en vivo y las funciones de importación/exportación.
    """
    # Emitida cada vez que médula, corteza o código cambian (incluso con blockSignals)
    metadatos_cambiados = pyqtSignal()

    def __init__(self, ruta_imagen: str, ventana_padre: QWidget):
        super().__init__()
        self._ventana_padre = ventana_padre
        self.ruta_imagen_actual = ruta_imagen
        # No escribir antes de comprobar si existe una sesión previa.
        self._sesion_protegida = ruta_imagen
        self._guardado_pendiente = False
        self.modelo_sesion = ModeloSesionMedicion()
        self.serie_maestra: pd.DataFrame | None = None
        self.nombre_maestra: str = "Ninguna"
        self._exportador = ExportadorDendro(self)
        self.item_imagen = None
        # Imagen original para cambio de banda
        self._img_bgr_original: np.ndarray | None = None
        # Perfiles de especie para auto-detección
        self._perfiles_especie = cargar_perfiles()
        self._especie_activa: str = next(iter(self._perfiles_especie))
        # Origen del DPI actual. Posibles valores:
        #   "auto"     → detectado automáticamente desde metadata JFIF/EXIF/TIFF
        #   "manual"   → cambiado a mano por el usuario en el diálogo DPI
        #   "regla"    → calibrado midiendo una distancia conocida
        #   "default"  → no se detectó, se usa DPI_DEFECTO
        #   "guardado" → restaurado desde un estado/sesión guardada
        # Sirve para mostrar al usuario qué origen tiene el DPI con el que
        # está trabajando, sobre todo cuando lo cambia y vuelve a abrir el
        # diálogo (antes seguía diciendo "Detectado automáticamente" aun
        # después de un override manual, lo cual era confuso).
        self._dpi_modo: str = "default"

        self._construir_ui()
        self._tareas = GestorTareasMedicion(self)
        radio = ContextoRadio(self, self.vista, lambda: self.datos_medidos,
                              self.label_estado, self.combo_dir)
        imagen = ContextoImagen(lambda: self._img_bgr_original,
                                lambda: self.ruta_imagen_actual, self._tareas)
        self._pith = ControlPith(radio, serie_maestra=lambda: self.serie_maestra,
            set_modo=self.set_modo, guardar_estado=self._guardar_estado,
            guardar_sidecar=self._guardar_sidecar_anom, spin_medula=self.spin_medula,
            spin_corteza=self.spin_corteza, check_tiene_medula=self.check_tiene_medula,
            btn_pith=self.btn_pith, btn_deshacer_pith=self.btn_deshacer_pith)
        self._intensidad = ControlIntensidad(radio, imagen,
            btn_mostrar_banda=self.btn_mostrar_banda, btn_graficar_bi=self.btn_graficar_bi,
            btn_guardar_bi=self.btn_guardar_bi, input_codigo=self.input_codigo)
        self._ewlw = ControlEWLW(radio, imagen, lambda: self._intensidad.banda)
        self._cargar_imagen(ruta_imagen)

    # -------------------------------------------------------------------------
    # Construcción de la interfaz
    # -------------------------------------------------------------------------

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # ── Barra de herramientas colapsable ──
        self._panel_herramientas = QWidget()
        lh = QVBoxLayout(self._panel_herramientas)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(2)
        lh.addLayout(self._construir_barra_herramientas())

        self.label_estado = QLabel("Preparando imagen...")
        self.label_estado.setStyleSheet("font-size:12px; font-weight:bold; color:#5cb85c;")
        lh.addWidget(self.label_estado)

        layout.addWidget(self._panel_herramientas)

        # Botón colapsar barra de herramientas
        self._btn_toggle_barra = QPushButton("🔼 Herramientas")
        self._btn_toggle_barra.setFixedHeight(18)
        self._btn_toggle_barra.setStyleSheet(
            "QPushButton{font-size:10px; padding:0px 6px; border:none; "
            f"color:{SECUNDARIO_QSS}; background:transparent;}}"
            "QPushButton:hover{color:white; background:#555;}"
        )
        self._btn_toggle_barra.setToolTip("Mostrar/ocultar barra de herramientas (Ctrl+H)")
        self._btn_toggle_barra.clicked.connect(self._toggle_barra)
        layout.addWidget(self._btn_toggle_barra)

        layout.addWidget(self._construir_splitter_principal())

        # Atajos de teclado para colapsar paneles
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._toggle_barra)
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self._toggle_grafico)

        # Código de serie por defecto
        nombre_base = os.path.splitext(os.path.basename(self.ruta_imagen_actual))[0]
        self.input_codigo.setText(nombre_base.replace(" ", "")[:TUCSON_MAX_CHARS_ID].upper())

    def _toggle_barra(self):
        """Muestra/oculta la barra de herramientas."""
        visible = self._panel_herramientas.isVisible()
        self._panel_herramientas.setVisible(not visible)
        # not visible = nuevo estado: True=ahora visible, False=ahora oculto
        self._btn_toggle_barra.setText(
            "🔼 Herramientas" if not visible else "🔽 Herramientas"
        )

    def _toggle_grafico(self):
        """Muestra/oculta el panel del gráfico."""
        visible = self._panel_codatacion.isVisible()
        self._panel_codatacion.setVisible(not visible)
        self._btn_toggle_grafico.setText(
            "🔼 Gráfico" if not visible else "🔽 Gráfico"
        )

    def _fuentes_split(self):
        tabs = getattr(self._ventana_padre, '_tabs_imagenes', None)
        if tabs is None:
            return ()
        fuentes = []
        for i in range(tabs.count()):
            widget = tabs.widget(i)
            if widget is not None and widget is not self and hasattr(widget, "escena"):
                fuentes.append((id(widget), tabs.tabText(i), widget.escena))
        return fuentes

    def _toggle_split_view(self):
        """Activa o desactiva la vista dividida."""
        es_visible = self.panel_split.isVisible()
        if es_visible:
            self.panel_split.hide()
            self._btn_split.setChecked(False)
        else:
            # Refrescar lista de imágenes y abrir
            self.panel_split.refrescar_combo()
            self.panel_split.show()
            self.panel_split._sincronizar_con_principal()
            # Ajustar splitter 50/50
            total = self._splitter_vistas.width()
            self._splitter_vistas.setSizes([total // 2, total // 2])
            self._btn_split.setChecked(True)

    # ── Popup helpers ─────────────────────────────────────────────────────

    def _crear_popup(self) -> QWidget:
        """Crea un QWidget flotante estilizado para usar como dropdown."""
        popup = QWidget(self, Qt.WindowType.Popup)
        popup.setStyleSheet(
            "QWidget{background-color:#333; border:1px solid #555; "
            "border-radius:6px; color:white;}"
            "QPushButton{background-color:#4a4a4a; color:white; "
            "padding:5px 10px; border-radius:3px; min-width:60px;}"
            "QPushButton:hover{background-color:#5a5a5a;}"
            "QPushButton:checked{background-color:#5cb85c; color:white; font-weight:bold;}"
            "QLabel{color:#ccc; font-size:11px; background:transparent;}"
            "QComboBox{background-color:#4a4a4a; color:white; padding:4px; border:1px solid #666;}"
            "QSlider::groove:horizontal{background:#555; height:6px; border-radius:3px;}"
            "QSlider::handle:horizontal{background:#FF8C00; width:14px; height:14px; "
            "border-radius:7px; margin:-4px 0;}"
        )
        return popup

    def _crear_separador(self) -> QWidget:
        """Crea una línea horizontal estilizada para separar secciones."""
        from PyQt6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame{color:#555; background:#555; max-height:1px;}")
        return sep

    def _toggle_popup(self, popup: QWidget):
        """Muestra u oculta un popup debajo de su botón padre."""
        if popup.isVisible():
            popup.hide()
            return
        # Cerrar el otro popup si está abierto
        for p in [self._popup_herram, self._popup_imagen, self._popup_ewlw]:
            if p is not popup and p.isVisible():
                p.hide()
        # Posicionar debajo del botón que lo activó
        btn = (self._btn_herram if popup is self._popup_herram
               else self._btn_imagen if popup is self._popup_imagen
               else self._btn_ewlw_dd)
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        popup.move(pos)
        popup.show()

    def _construir_barra_herramientas(self) -> QHBoxLayout:
        acciones = modulo_medicion_ui.AccionesBarraMedicion(
            _activar_calibracion=self._activar_calibracion,
            _al_cambiar_direccion=self._al_cambiar_direccion,
            _al_cambiar_especie=self._al_cambiar_especie,
            _aplicar_anio_corteza=self._aplicar_anio_corteza,
            _aplicar_anio_medula=self._aplicar_anio_medula,
            _aplicar_banda_actual=self._aplicar_banda_actual,
            _calibrar_por_dpi=self._calibrar_por_dpi,
            _cambiar_banda=self._cambiar_banda,
            _configurar_especie=self._configurar_especie,
            _crear_popup=self._crear_popup,
            _crear_separador=self._crear_separador,
            _deshacer=self._deshacer,
            _deshacer_pith_offset=self._deshacer_pith_offset,
            _detectar_ewlw_automatico=self._detectar_ewlw_automatico,
            _ejecutar_exportacion=self._ejecutar_exportacion,
            _eliminar_ewlw=self._eliminar_ewlw,
            _exportar_anomalias=self._exportar_anomalias,
            _guardar_ajustes_banda=self._guardar_ajustes_banda,
            _importar_pos=self._importar_pos,
            _iniciar_estimacion_pith=self._iniciar_estimacion_pith,
            _nueva_especie=self._nueva_especie,
            _rehacer=self._rehacer,
            _toggle_autodetect=self._toggle_autodetect,
            _toggle_popup=self._toggle_popup,
            _toggle_split_view=self._toggle_split_view,
            set_modo=self.set_modo,
        )
        widget, controles = modulo_medicion_ui.construir_barra_herramientas(self, acciones, self._perfiles_especie, self._especie_activa)
        self._banda_actual = controles._banda_actual
        self._botones_modo = controles._botones_modo
        self._btn_ewlw_dd = controles._btn_ewlw_dd
        self._btn_herram = controles._btn_herram
        self._btn_imagen = controles._btn_imagen
        self._btn_split = controles._btn_split
        self._grupo_banda = controles._grupo_banda
        self._popup_ewlw = controles._popup_ewlw
        self._popup_herram = controles._popup_herram
        self._popup_imagen = controles._popup_imagen
        self._slider_brillo = controles._slider_brillo
        self._slider_contraste = controles._slider_contraste
        self._timer_banda = controles._timer_banda
        self.btn_anomalia = controles.btn_anomalia
        self.btn_autodetect = controles.btn_autodetect
        self.btn_calibrar = controles.btn_calibrar
        self.btn_calibrar_dpi = controles.btn_calibrar_dpi
        self.btn_cfg_especie = controles.btn_cfg_especie
        self.btn_deshacer = controles.btn_deshacer
        self.btn_deshacer_pith = controles.btn_deshacer_pith
        self.btn_ewlw_auto = controles.btn_ewlw_auto
        self.btn_ewlw_eliminar = controles.btn_ewlw_eliminar
        self.btn_exportar = controles.btn_exportar
        self.btn_exportar_anom = controles.btn_exportar_anom
        self.btn_importar_pos = controles.btn_importar_pos
        self.btn_nueva_especie = controles.btn_nueva_especie
        self.btn_pith = controles.btn_pith
        self.btn_rehacer = controles.btn_rehacer
        self.check_tiene_corteza = controles.check_tiene_corteza
        self.check_tiene_medula = controles.check_tiene_medula
        self.combo_dir = controles.combo_dir
        self.combo_especie = controles.combo_especie
        self.combo_tipo_anomalia = controles.combo_tipo_anomalia
        self.grupo_modos = controles.grupo_modos
        self.input_codigo = controles.input_codigo
        self.spin_corteza = controles.spin_corteza
        self.spin_medula = controles.spin_medula
        return widget

    def _construir_splitter_principal(self) -> QWidget:
        acciones = modulo_medicion_ui.AccionesSplitterMedicion(
            _anomalias_modificadas=self._anomalias_modificadas,
            _configuracion_pith=self._configuracion_pith,
            _confirmar_estimacion_pith=self._confirmar_estimacion_pith,
            _datacion_activa=self._datacion_activa,
            _ejecutar_autodeteccion=self._ejecutar_autodeteccion,
            _fuentes_split=self._fuentes_split,
            _guardar_estado=self._guardar_estado,
            _origen_calibracion=self._origen_calibracion,
            _programar_guardado=self._programar_guardado,
            _reflejar_modo_vista=self._reflejar_modo_vista,
            _sincronizar_mediciones=self._sincronizar_mediciones,
            _tipo_anomalia_activo=self._tipo_anomalia_activo,
            _toggle_grafico=self._toggle_grafico,
        )
        widget, controles = modulo_medicion_ui.construir_splitter_principal(self, acciones, self.modelo_sesion.activo, self.label_estado.setText,
            lambda: self.datos_medidos, self._construir_panel_radios(),
            self._construir_panel_codatacion())
        self._btn_toggle_grafico = controles._btn_toggle_grafico
        self._panel_codatacion = controles._panel_codatacion
        self._splitter_principal = controles._splitter_principal
        self._splitter_vistas = controles._splitter_vistas
        self._timer_autoguardado = controles._timer_autoguardado
        self.escena = controles.escena
        self.panel_split = controles.panel_split
        self.vista = controles.vista
        return widget

    def _construir_panel_radios(self) -> QWidget:
        acciones = modulo_medicion_ui.AccionesRadiosMedicion(
            _editar_camino=self._editar_camino,
            _eliminar_camino=self._eliminar_camino,
            _finalizar_camino=self._finalizar_camino,
            _toggle_visual_camino=self._toggle_visual_camino,
        )
        widget, controles = modulo_medicion_ui.construir_panel_radios(self, acciones)
        self.btn_editar_camino = controles.btn_editar_camino
        self.btn_finalizar_camino = controles.btn_finalizar_camino
        self.lista_caminos = controles.lista_caminos
        return widget

    def _construir_panel_codatacion(self) -> QWidget:
        acciones = modulo_medicion_ui.AccionesGraficoMedicion(
            _actualizar_grafico=self._actualizar_grafico,
            _calcular_bi=self._calcular_bi,
            _cargar_serie_maestra=self._cargar_serie_maestra,
            _cargar_serie_wid=self._cargar_serie_wid,
            _configurar_bi=self._configurar_bi,
            _eliminar_serie_maestra=self._eliminar_serie_maestra,
            _graficar_bi_ventana=self._graficar_bi_ventana,
            _guardar_bi=self._guardar_bi,
            _navegar_anio_grafico=self._navegar_anio_grafico,
            _toggle_banda_bi=self._toggle_banda_bi,
            metodo_correlacion=self.metodo_correlacion,
        )
        widget, controles = modulo_medicion_ui.construir_panel_codatacion(self, acciones)
        self._btn_cfg_bi = controles._btn_cfg_bi
        self._item_highlight_anio = controles._item_highlight_anio
        self.btn_calcular_bi = controles.btn_calcular_bi
        self.btn_cargar_maestra = controles.btn_cargar_maestra
        self.btn_cargar_wid = controles.btn_cargar_wid
        self.btn_eliminar_maestra = controles.btn_eliminar_maestra
        self.btn_graficar_bi = controles.btn_graficar_bi
        self.btn_guardar_bi = controles.btn_guardar_bi
        self.btn_mostrar_banda = controles.btn_mostrar_banda
        self.combo_maestra = controles.combo_maestra
        self.combo_metodo_corr = controles.combo_metodo_corr
        self.grafico_medicion = controles.grafico_medicion
        self.grafico_unif = controles.grafico_unif
        self.lbl_nombre_maestra = controles.lbl_nombre_maestra
        self.lbl_r_total = controles.lbl_r_total
        self.lbl_ventanas_r = controles.lbl_ventanas_r
        self.spin_ventana_r = controles.spin_ventana_r
        return widget

    # -------------------------------------------------------------------------
    # Carga de imagen
    # -------------------------------------------------------------------------

    def _mostrar_aviso_dpi(self, titulo: str, texto: str):
        """Muestra un aviso de DPI NO modal y con autocierre.

        Crítico: NO usa QMessageBox.information() (que llama exec() y es
        modal). Un diálogo modal disparado por QTimer durante la carga de
        imágenes —que usa processEvents() y abre las siguientes en cola—
        anida un bucle de eventos que re-entra en la carga y CONGELA el
        programa al abrir varias imágenes a la vez.

        Este aviso:
          • Es no modal: se muestra con show() y no bloquea el bucle.
          • Se guarda en una lista para que el GC no lo elimine.
          • Se cierra solo a los 7 segundos (o cuando el usuario pulsa OK).
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(titulo)
        box.setText(texto)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setWindowModality(Qt.WindowModality.NonModal)

        if not hasattr(self, "_avisos_no_modales"):
            self._avisos_no_modales = []
        self._avisos_no_modales.append(box)
        box.finished.connect(
            lambda _=None, b=box: (
                self._avisos_no_modales.remove(b)
                if b in self._avisos_no_modales else None))

        box.show()
        # Autocierre no bloqueante. El timer se parenta al box para que
        # muera junto con él si el usuario lo cierra antes.
        timer = QTimer(box)
        timer.setSingleShot(True)
        timer.timeout.connect(box.close)
        timer.start(7000)

    def _cargar_imagen(self, ruta: str):
        import time
        t0 = time.perf_counter()
 
        dpi_detectado = self._detectar_dpi(ruta)
        if dpi_detectado and dpi_detectado > 0:
            self.vista.pixeles_por_mm = escala_desde_dpi(dpi_detectado)
            self._dpi_modo = "auto"
            msg_escala = f"Resolución detectada: {dpi_detectado:.0f} DPI."
            # Aviso NO modal (ver _mostrar_aviso_dpi). Se difiere 800 ms para
            # que aparezca tras cargar la imagen. NUNCA usar un QMessageBox
            # modal aquí: al abrir varias imágenes en cola, el exec() modal
            # anida un bucle de eventos que re-entra en la carga de la
            # siguiente imagen y congela el programa.
            QTimer.singleShot(800, lambda d=dpi_detectado: self._mostrar_aviso_dpi(
                "Resolución detectada",
                f"Se detectaron automáticamente <b>{d:.0f} DPI</b> "
                f"desde los metadatos de la imagen.<br><br>"
                f"Si necesitas cambiar este valor, puedes hacerlo desde "
                f"<b>Herramientas → 📐 DPI</b>.",
            ))
        else:
            self.vista.pixeles_por_mm = PIXELES_POR_MM_DEFECTO
            self._dpi_modo = "default"
            msg_escala = f"DPI no detectado. Asumiendo {DPI_DEFECTO} DPI por defecto."
            QTimer.singleShot(500, lambda: self._mostrar_aviso_dpi(
                "Aviso de Resolución",
                f"No se detectaron DPI en los metadatos.<br><br>"
                f"Se usará <b>{DPI_DEFECTO} DPI</b> por defecto.<br><br>"
                f"Si conoces el DPI real del escáner, puedes configurarlo "
                f"desde <b>Herramientas → 📐 DPI</b>.",
            ))
 
        print("[CARGA] DPI detectado en %.2fs", time.perf_counter() - t0)
        t1 = time.perf_counter()
 
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            QApplication.processEvents()
            try:
                img_cv = leer_imagen_bgr(ruta)
            except Exception as exc:
                self.label_estado.setText(f"⚠ Error al leer la imagen: {exc}")
                return
 
            h, w = img_cv.shape[:2]
            mp = (w * h) / 1e6
            print("[CARGA] cv2.imread %dx%d (%.1f MP) en %.2fs",
                        w, h, mp, time.perf_counter() - t1)
            t2 = time.perf_counter()
 
            img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
            QApplication.processEvents()
            print("[CARGA] cvtColor en %.2fs", time.perf_counter() - t2)
            t3 = time.perf_counter()
 
            q_img = QImage(img_rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            del img_rgb
            QApplication.processEvents()
            print("[CARGA] QImage en %.2fs", time.perf_counter() - t3)
            t4 = time.perf_counter()
 
            self.item_imagen = QGraphicsPixmapItem(QPixmap.fromImage(q_img))
            self.item_imagen.setTransformationMode(
                Qt.TransformationMode.FastTransformation
            )
            del q_img
            self.escena.addItem(self.item_imagen)
            self.escena.setSceneRect(0, 0, w, h)
            print("[CARGA] Pixmap + escena en %.2fs", time.perf_counter() - t4)
            t5 = time.perf_counter()
 
            self._img_bgr_original = img_cv
        finally:
            QApplication.restoreOverrideCursor()

        restaurado = self._cargar_estado()
        if restaurado:
            self.label_estado.setText(
                f"Progreso restaurado. Escala: {self.vista.pixeles_por_mm * MM_POR_PULGADA:.0f} DPI."
            )
        elif self._sesion_protegida == self.ruta_imagen_actual:
            self.label_estado.setText("Sesión no restaurada: autoguardado desactivado.")
        else:
            self.label_estado.setText(f"Imagen lista. {msg_escala}")
 
        print("[CARGA] _cargar_estado en %.2fs", time.perf_counter() - t5)
        print("[CARGA] TOTAL: %.2fs para %.1f MP", time.perf_counter() - t0, mp)
 
        QTimer.singleShot(100, self._ajustar_zoom_inicial)
 
    _detectar_dpi = staticmethod(detectar_dpi)

    def _ajustar_zoom_inicial(self):
        if self.item_imagen:
            self.vista.fitInView(self.escena.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    # -------------------------------------------------------------------------
    # Visualización por banda (R, G, B, Gray)
    # -------------------------------------------------------------------------

    def _cambiar_banda(self, banda: str):
        """Cambia la banda activa y actualiza la imagen."""
        self._banda_actual = banda
        # Marcar el botón correcto
        for btn in self._grupo_banda.buttons():
            btn.setChecked(btn.text() == banda)
        # Cargar ajustes guardados para esta especie+banda
        self._cargar_ajustes_banda()
        self._aplicar_banda_actual()

    def _aplicar_banda_actual(self):
        """Reenderiza la imagen con la banda y ajustes de brillo/contraste actuales.

        Usa cv2.LUT (lookup table de 256 bytes) para aplicar brillo/contraste
        sin crear copias float32 de la imagen completa — crítico para imágenes
        de alta resolución (2400+ DPI) que pueden superar los 500 MB.
        """
        if self._img_bgr_original is None or self.item_imagen is None:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            img = self._img_bgr_original
            banda = self._banda_actual
            brillo = self._slider_brillo.value()
            contraste = self._slider_contraste.value() / 100.0

            rgb = preparar_banda_rgb(img, banda, brillo, contraste)

            QApplication.processEvents()

            h, w = rgb.shape[:2]
            rgb = np.ascontiguousarray(rgb)
            q_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self.item_imagen.setPixmap(QPixmap.fromImage(q_img.copy()))
            del rgb
        finally:
            QApplication.restoreOverrideCursor()

    def _guardar_ajustes_banda(self):
        """Guarda brillo/contraste de la banda activa en el perfil de especie."""
        try:
            especie = self._especie_activa
            settings = ajustes_ui()
            key = f"banda/{especie}/{self._banda_actual}"
            settings.setValue(f"{key}/brillo", self._slider_brillo.value())
            settings.setValue(f"{key}/contraste", self._slider_contraste.value())
        except Exception:
            pass

    def _cargar_ajustes_banda(self):
        """Restaura brillo/contraste guardados para la especie+banda actual."""
        try:
            especie = self._especie_activa
            settings = ajustes_ui()
            key = f"banda/{especie}/{self._banda_actual}"
            brillo = settings.value(f"{key}/brillo", 0, type=int)
            contraste = settings.value(f"{key}/contraste", 100, type=int)
            with QSignalBlocker(self._slider_brillo), QSignalBlocker(self._slider_contraste):
                self._slider_brillo.setValue(brillo)
                self._slider_contraste.setValue(contraste)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Modos de interacción
    # -------------------------------------------------------------------------

    def set_modo(self, modo: ModoMedicion):
        modo = self.vista.aplicar_accion_seleccion(modo)
        self.vista.cambiar_modo(modo)
        self._reflejar_modo_vista(modo)

    def _reflejar_modo_vista(self, modo):
        btn = self._botones_modo.get(modo)
        if btn:
            btn.setChecked(True)
        self.vista.setFocus()

    def _datacion_activa(self):
        if not all(hasattr(self, n) for n in ("spin_medula", "spin_corteza", "combo_dir")):
            return None
        return self.spin_medula.value(), self.spin_corteza.value(), self.combo_dir.currentIndex() == 0

    def _tipo_anomalia_activo(self):
        combo = getattr(self, "combo_tipo_anomalia", None)
        return combo.currentData() if combo is not None else None

    def _configuracion_pith(self):
        especial = getattr(self, "_pith", None)
        return especial.configuracion_pith if especial is not None else (5, "rg")

    def _origen_calibracion(self, origen):
        self._dpi_modo = origen

    def _deshacer(self):
        self.vista.deshacer_ultimo()

    def _rehacer(self):
        self.vista.rehacer_ultimo()

    # -------------------------------------------------------------------------
    # Auto-detección de anillos por especie
    # -------------------------------------------------------------------------

    def _refrescar_combo_especie(self):
        self.combo_especie.blockSignals(True)
        self.combo_especie.clear()
        self.combo_especie.addItems(list(self._perfiles_especie.keys()))
        if self._especie_activa in self._perfiles_especie:
            self.combo_especie.setCurrentText(self._especie_activa)
        self.combo_especie.blockSignals(False)

    def _guardar_perfiles_especie(self):
        """Guarda los perfiles y AVISA si no se pudo.

        Antes el fallo se tragaba y solo quedaba en el registro: el usuario
        afinaba una especie, pulsaba guardar, no veía nada raro y al reiniciar
        el perfil no estaba. Si falla hay que decirlo, porque es trabajo suyo
        el que se pierde.
        """
        from dpi.medicion.autodeteccion import guardar_perfiles, RUTA_PERFILES
        try:
            guardar_perfiles(self._perfiles_especie)
        except Exception as exc:
            QMessageBox.warning(
                self, "No se pudo guardar el perfil de especie",
                f"El perfil quedó activo en esta sesión, pero no se pudo "
                f"escribir en disco, así que se perderá al cerrar DPI.\n\n"
                f"Archivo: {RUTA_PERFILES}\n{exc}")

    def _al_cambiar_especie(self, nombre: str):
        if nombre in self._perfiles_especie:
            self._especie_activa = nombre

    def _configurar_especie(self):
        """Abre el diálogo de configuración para la especie activa."""
        perfil = self._perfiles_especie.get(self._especie_activa, {})
        dlg = DialogoEspecie(self._especie_activa, perfil, self)
        if dlg.exec():
            self._perfiles_especie[self._especie_activa] = dlg.obtener_perfil()
            self._guardar_perfiles_especie()

    def _nueva_especie(self):
        """Crea un perfil de especie nuevo a partir del nombre que ingrese el usuario."""
        from dpi.medicion.autodeteccion import PERFIL_DEFECTO
        nombre, ok = QInputDialog.getText(self, "Nueva especie", "Nombre de la especie:")
        if not ok or not nombre.strip():
            return
        nombre = nombre.strip()
        if nombre in self._perfiles_especie:
            QMessageBox.warning(self, "Especie existente",
                                f'Ya existe un perfil para "{nombre}".')
            return
        self._perfiles_especie[nombre] = PERFIL_DEFECTO.copy()
        self._guardar_perfiles_especie()
        self._especie_activa = nombre
        self._refrescar_combo_especie()
        # Abrir configuración inmediatamente
        self._configurar_especie()

    def _toggle_autodetect(self):
        """Activa/desactiva el modo auto-detección desde el botón."""
        if self.btn_autodetect.isChecked():
            # Cargar imagen BGR si aún no está cacheada
            img_bgr = cv2.imread(self.ruta_imagen_actual, cv2.IMREAD_COLOR)
            if img_bgr is None:
                QMessageBox.critical(self, "Error",
                                     "No se pudo leer la imagen para la detección.")
                self.btn_autodetect.setChecked(False)
                return
            self.vista.iniciar_autodetect(img_bgr)
            self.label_estado.setText(
                "🔍 Auto-detección: clic en la MÉDULA, luego en la CORTEZA."
            )
        else:
            self.vista.cambiar_modo(ModoMedicion.MEDIR)
            self._botones_modo[ModoMedicion.MEDIR].setChecked(True)
            self.label_estado.setText("Modo añadir activado.")

    def _ejecutar_autodeteccion(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        imagen_bgr: np.ndarray,
        idx_ancla: int | None = None,
    ):
        """
        Llamado por VistaInteractiva tras los 2 clics de auto-detección.
        Extrae el perfil entre p1 y p2, muestra preview y coloca los puntos.

        idx_ancla: índice del punto existente desde el que se continúa,
                   o None si la detección es sobre una zona vacía.
        """
        perfil = self._perfiles_especie.get(self._especie_activa, {})
        ppm    = self.vista.pixeles_por_mm

        dist, intens = extraer_perfil(
            imagen_bgr, p1, p2,
            canal=perfil.get("canal", "gray"),
            banda_px=perfil.get("banda_px", 5),
        )

        if len(dist) == 0:
            QMessageBox.warning(self, "Sin datos",
                                "No se pudo extraer el perfil de intensidad.")
            return

        dlg = DialogoPreviewDeteccion(dist, intens, perfil, ppm, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        banda_nueva = dlg.obtener_banda_final()
        if banda_nueva != perfil.get("banda_px", 5):
            perfil["banda_px"] = banda_nueva
            self._perfiles_especie[self._especie_activa] = perfil
            self._guardar_perfiles_especie()
            dist, intens = extraer_perfil(
                imagen_bgr, p1, p2,
                canal=perfil.get("canal", "gray"),
                banda_px=banda_nueva,
            )

        perfil["prominencia"] = dlg.obtener_prominencia_final()

        posiciones_px = detectar_limites(dist, intens, perfil)
        if len(posiciones_px) == 0:
            QMessageBox.information(self, "Sin detecciones",
                                    "No se detectaron límites de anillo.\n"
                                    "Prueba a reducir la prominencia mínima o\n"
                                    "verificar el canal y la polaridad de la especie.")
            return

        coordenadas = posiciones_a_coordenadas(posiciones_px, p1, p2)

        # Si hay ancla, verificar si hay puntos en el tramo y preguntar qué hacer
        reemplazar_tramo = False
        if idx_ancla is not None and len(self.vista.coordenadas_anillos) > 1:
            n_total = len(self.vista.coordenadas_anillos)
            # Hay puntos más allá del ancla?
            tiene_vecinos = (idx_ancla > 0 or idx_ancla < n_total - 1)
            if tiene_vecinos:
                resp = QMessageBox.question(
                    self,
                    "Puntos existentes en el tramo",
                    "Ya hay puntos entre el ancla y el extremo detectado.\n\n"
                    "¿Qué desea hacer?\n\n"
                    "  • Sí  → Reemplazar los puntos existentes en ese tramo\n"
                    "  • No  → Insertar los nuevos sin borrar los existentes",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                reemplazar_tramo = resp == QMessageBox.StandardButton.Yes

        self.vista.colocar_puntos_autodetectados(
            coordenadas,
            idx_ancla=idx_ancla,
            reemplazar_tramo=reemplazar_tramo,
        )
        n = len(coordenadas)
        self.label_estado.setText(
            f"✅ Auto-detección: {n} anillos colocados"
            + (f" desde punto #{idx_ancla}" if idx_ancla is not None else "")
            + ". Usa las herramientas para corregir."
        )

    # -------------------------------------------------------------------------
    # Gestión de años (médula / corteza)
    # -------------------------------------------------------------------------

    @property
    def datos_medidos(self):
        """Proyección calculada; nunca se conserva ni se modifica como estado."""
        if not all(hasattr(self, n) for n in ("vista", "spin_medula",
                                                "spin_corteza", "combo_dir")):
            return []
        modelo = self.vista.modelo_medicion
        anchos = anchos_puntos(modelo.captura(), self.vista.pixeles_por_mm)
        return mediciones_desde_anchos(
            anchos, self.spin_medula.value(), self.spin_corteza.value(),
            self.combo_dir.currentIndex() == 0)

    def _ajustar_anios(self, n, ancla):
        if not n:
            return None
        with QSignalBlocker(self.spin_medula), QSignalBlocker(self.spin_corteza):
            if ancla == "medula":
                self.spin_corteza.setValue(self.spin_medula.value() + n - 1)
                return self.spin_corteza.value()
            self.spin_medula.setValue(self.spin_corteza.value() - n + 1)
            return self.spin_medula.value()

    def _refrescar_medicion(self):
        intensidad = getattr(self, "_intensidad", None)
        if intensidad is not None:
            intensidad.invalidar_si_cambio()
        self.metadatos_cambiados.emit()
        self._actualizar_grafico()
        self.vista.redibujar_todo()

    def _recalcular_anios(self, ancla: str):
        n = len(self.datos_medidos)
        if not n:
            return
        self._ajustar_anios(n, ancla)
        self._guardar_estado()
        self._refrescar_medicion()

    def _aplicar_anio_medula(self):
        self._recalcular_anios("medula")

    def _aplicar_anio_corteza(self):
        self._recalcular_anios("corteza")

    def _al_cambiar_direccion(self):
        self._recalcular_anios("medula")

    # -------------------------------------------------------------------------
    # Sincronización de mediciones desde el lienzo
    # -------------------------------------------------------------------------

    def _sincronizar_mediciones(self, lista_anchos: list[float]):
        n = len(lista_anchos)
        if not n:
            self.label_estado.setText("Listo para el primer anillo.")
        else:
            ancla = "medula" if self.combo_dir.currentIndex() == 0 else "corteza"
            extremo = self._ajustar_anios(n, ancla)
            self.label_estado.setText(
                f"Último: {lista_anchos[-1]:.3f} mm (año {extremo}) | Total: {n}")
        self._refrescar_medicion()

    # -------------------------------------------------------------------------
    # Co-datación en vivo
    # -------------------------------------------------------------------------

    def _cargar_serie_maestra(self):
        carpeta = _ultima_carpeta()
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Cargar Serie de Referencia", carpeta,
            "Series y cronologías (*.rwl *.txt *.cat *.cmp *.pos *.wid "
            "*.csv *.tsv *.xlsx *.xls *.ods);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        try:
            # AQUÍ ESTÁ EL CAMBIO PRINCIPAL
            self.serie_maestra, self.nombre_maestra = leer_dendro_auto(ruta)

            self.lbl_nombre_maestra.setText(self.nombre_maestra)
            self.lbl_nombre_maestra.setStyleSheet("color:#5cb85c;")
            self.btn_eliminar_maestra.setEnabled(True)
            self._actualizar_grafico()

            # Seleccionar la referencia recién cargada como maestra. Sin esto
            # el combo conservaba la selección anterior (normalmente una serie
            # interna), así que las correlaciones y sus fondos de color se
            # seguían calculando contra esa y no contra la referencia — daba la
            # impresión de que cargarla no hacía nada.
            self._seleccionar_maestra_externa()
            _ultima_carpeta(ruta)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", f"No se pudo leer la referencia:\n{exc}")
            
    def _cargar_serie_wid(self):
        """Carga una cronología CooRecorder (.wid) como serie de referencia."""
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Cargar Cronología CooRecorder", _ultima_carpeta(),
            "CooRecorder WID (*.wid);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        try:
            self.serie_maestra, self.nombre_maestra = leer_wid(ruta)
            self.lbl_nombre_maestra.setText(f"🌲 {self.nombre_maestra}")
            self.lbl_nombre_maestra.setStyleSheet("color:#5bc0de; font-weight:bold;")
            self.btn_eliminar_maestra.setEnabled(True)
            self._actualizar_grafico()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", f"No se pudo leer el archivo .wid:\n{exc}")

    def _eliminar_serie_maestra(self):
        """Elimina la serie maestra externa cargada.

        Útil cuando el usuario quiere volver a comparar solo entre radios
        internos sin la referencia externa, o cambiar a otra de cero.
        """
        if self.serie_maestra is None:
            return
        self.serie_maestra = None
        self.nombre_maestra = "Ninguna"
        self.lbl_nombre_maestra.setText("Ninguna")
        self.lbl_nombre_maestra.setStyleSheet(f"color:{SECUNDARIO_QSS};")
        self.btn_eliminar_maestra.setEnabled(False)
        self._actualizar_grafico()

    # -------------------------------------------------------------------------
    # Interacción con el gráfico: crosshair + navegación por clic
    # -------------------------------------------------------------------------


    def _navegar_anio_grafico(self, anio):
        mapa = self.vista.mapa_anio_coordenada()
        if anio not in mapa:
            if not mapa:
                return False
            anio = min(mapa, key=lambda a: abs(a - anio))
        coord = mapa[anio]
        self.vista.centerOn(coord[0], coord[1])
        self._resaltar_anio_en_imagen(coord, anio)
        return True

    def _resaltar_anio_en_imagen(self, coord: tuple, anio: int):
        """Dibuja un círculo brillante temporal sobre el punto del año en la imagen."""
        # Limpiar resaltado anterior
        if self._item_highlight_anio is not None:
            try:
                self.vista.scene().removeItem(self._item_highlight_anio)
            except Exception:
                pass
            self._item_highlight_anio = None

        x, y = coord
        r = 18 * self.vista._escala_vista()
        pen = QPen(QColor("#00BFFF"))
        pen.setCosmetic(True)
        pen.setWidthF(3.5)
        brush = QBrush(QColor(0, 191, 255, 50))
        self._item_highlight_anio = self.vista.scene().addEllipse(
            x - r, y - r, 2 * r, 2 * r, pen, brush)
        self._item_highlight_anio.setZValue(80)

        # Auto-eliminar después de 2 segundos
        QTimer.singleShot(2000, self._limpiar_highlight_anio)

    def _limpiar_highlight_anio(self):
        if self._item_highlight_anio is not None:
            try:
                self.vista.scene().removeItem(self._item_highlight_anio)
            except Exception:
                pass
            self._item_highlight_anio = None



    def metodo_correlacion(self) -> str:
        """Método de transformación elegido en el selector de la barra."""
        combo = getattr(self, "combo_metodo_corr", None)
        if combo is None:
            return _tr.DIFFLOG
        return combo.currentData() or _tr.DIFFLOG




    def _seleccionar_maestra_externa(self):
        """Apunta el combo de maestra a la referencia externa cargada."""
        if not getattr(self, "nombre_maestra", None):
            return
        idx = self.combo_maestra.findText(f"↑ Ext: {self.nombre_maestra}")
        if idx >= 0 and self.combo_maestra.currentIndex() != idx:
            # currentIndexChanged ya está conectado a _actualizar_grafico,
            # así que basta con cambiar el índice.
            self.combo_maestra.setCurrentIndex(idx)




    def _actualizar_grafico(self):
        grafico = getattr(self, "grafico_medicion", None)
        if grafico is None:
            return
        colores = grafico.COLORES
        entradas = []
        for i, (nombre, radio) in enumerate(self.caminos_guardados.items()):
            dm = mediciones_radio(radio, self.vista.pixeles_por_mm)
            if dm:
                entradas.append((nombre, [d["anio"] for d in dm],
                    [d["ancho_mm"] for d in dm], colores[i % len(colores)], Qt.PenStyle.SolidLine))
        dm = self.datos_medidos
        if dm:
            entradas.append((self.input_codigo.text().strip() or "En medición",
                [d["anio"] for d in dm], [d["ancho_mm"] for d in dm],
                colores[len(self.caminos_guardados) % len(colores)], Qt.PenStyle.SolidLine))
        grafico.actualizar(entradas, self.serie_maestra, self.nombre_maestra)

    # Aliases para compatibilidad con todas las llamadas existentes
    def _encuadrar_grafico(self, pw=None, solo_mas_larga: bool = True):
        return self.grafico_medicion.encuadrar(pw, solo_mas_larga)



    # -------------------------------------------------------------------------
    # Gestión de radios guardados
    # -------------------------------------------------------------------------

    @property
    def caminos_guardados(self):
        return self.modelo_sesion.radios

    def _finalizar_camino(self):
        return control_radios._finalizar_camino(self)

    def _editar_camino(self):
        return control_radios._editar_camino(self)

    def _eliminar_camino(self):
        return control_radios._eliminar_camino(self)

    def _toggle_visual_camino(self, item: QListWidgetItem):
        return control_radios._toggle_visual_camino(self, item)

    # -------------------------------------------------------------------------
    # Calibración
    # -------------------------------------------------------------------------

    def _calibrar_por_dpi(self):
        """Abre una ventana auxiliar con información completa de la imagen
        y permite cambiar el DPI manualmente.

        La ventana muestra:
          - Dimensiones en píxeles + megapíxeles totales
          - DPI actual y método con el que se detectó (JFIF / EXIF /
            TIFF / manual / default)
          - Tamaño físico calculado (mm y cm)
          - Resolución espacial (px / mm)
          - Spin box para override manual del DPI

        Útil para:
          - Verificar que el DPI detectado coincide con el real del
            escáner (cuando el usuario lo conoce)
          - Diagnosticar imágenes sin metadata (DPI default)
          - Confirmar tamaño físico calculado vs. tamaño real de la
            pieza escaneada

        Históricamente: reemplaza al QInputDialog simple que solo mostraba
        un número, sin contexto sobre cómo se obtuvo ni qué implicaba.
        """
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
            QPushButton, QFrame, QGridLayout,
        )
        from PyQt6.QtGui import QFont

        # ── Recopilar información actual ──────────────────────────────
        dpi_actual = int(round(self.vista.pixeles_por_mm * MM_POR_PULGADA))
        ruta_img = getattr(self, "ruta_imagen_actual", None)

        # Tamaño de la imagen cargada (pixmap)
        if self.item_imagen is not None:
            pm = self.item_imagen.pixmap()
            w_px, h_px = pm.width(), pm.height()
        else:
            w_px = h_px = 0

        # Re-detectar para mostrar el método empleado
        dpi_detectado = None
        if ruta_img:
            dpi_detectado = self._detectar_dpi(ruta_img)

        # Texto descriptivo del MODO actual (puede ser distinto al
        # resultado de la metadata si el usuario lo cambió manualmente).
        modo_label = {
            "auto":     "✓ Detectado automáticamente desde metadata",
            "manual":   "✏️ Cambiado manualmente por el usuario",
            "regla":    "📏 Calibrado midiendo una distancia conocida",
            "default":  "⚠ No se detectó — usando DPI por defecto",
            "guardado": "💾 Restaurado desde sesión guardada",
        }
        metodo_deteccion = modo_label.get(
            getattr(self, "_dpi_modo", "default"),
            "Desconocido")

        # Cálculos derivados
        if dpi_actual > 0:
            w_mm = w_px / dpi_actual * MM_POR_PULGADA
            h_mm = h_px / dpi_actual * MM_POR_PULGADA
        else:
            w_mm = h_mm = 0
        mp = (w_px * h_px) / 1e6

        # ── Construir el diálogo ──────────────────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("Información de imagen — Configuración DPI")
        dlg.setMinimumWidth(500)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        # Título
        titulo = QLabel("📐 Información de la imagen")
        f = QFont(); f.setBold(True); f.setPointSize(11)
        titulo.setFont(f)
        layout.addWidget(titulo)

        # Grid con datos
        grid_frame = QFrame()
        grid_frame.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(grid_frame)
        grid.setSpacing(8)

        def add_row(row: int, label: str, valor: str, destacar: bool = False):
            lab = QLabel(label)
            val = QLabel(valor)
            if destacar:
                fb = QFont(); fb.setBold(True)
                val.setFont(fb)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lab, row, 0)
            grid.addWidget(val, row, 1)

        add_row(0, "Dimensiones (px):", f"{w_px:,} × {h_px:,}".replace(",", "."))
        add_row(1, "Megapíxeles totales:", f"{mp:.1f} MP")
        add_row(2, "DPI actual:", f"{dpi_actual} DPI", destacar=True)
        add_row(3, "Método de detección:", metodo_deteccion)
        if dpi_detectado is not None and dpi_detectado != dpi_actual:
            add_row(4, "DPI desde metadata:", f"{int(round(dpi_detectado))} DPI")
            offset = 5
        else:
            offset = 4
        add_row(offset, "Tamaño físico calculado:",
                f"{w_mm:.1f} × {h_mm:.1f} mm  ({w_mm/10:.1f} × {h_mm/10:.1f} cm)")
        add_row(offset + 1, "Resolución espacial:",
                f"{self.vista.pixeles_por_mm:.2f} px/mm  "
                f"({1000/self.vista.pixeles_por_mm:.1f} μm/px)")
        layout.addWidget(grid_frame)

        # Ayuda
        ayuda = QLabel(
            "💡 Si el DPI detectado no coincide con el real del escáner, "
            "puedes sobreescribirlo manualmente aquí. El cambio recalcula "
            "todas las mediciones existentes."
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet(f"color: {SECUNDARIO_QSS}; font-style: italic;")
        layout.addWidget(ayuda)

        # Spin box para override
        fila_override = QHBoxLayout()
        fila_override.addWidget(QLabel("DPI manual:"))
        spin_dpi = QSpinBox()
        spin_dpi.setRange(72, 12800)
        spin_dpi.setValue(dpi_actual)
        spin_dpi.setSuffix(" DPI")
        spin_dpi.setSingleStep(100)
        spin_dpi.setMinimumWidth(120)
        fila_override.addWidget(spin_dpi)

        # Botones rápidos de DPI común
        for dpi_preset in (1200, 1600, 2400, 3200):
            btn_p = QPushButton(str(dpi_preset))
            btn_p.setMaximumWidth(60)
            btn_p.clicked.connect(lambda _, v=dpi_preset: spin_dpi.setValue(v))
            fila_override.addWidget(btn_p)
        fila_override.addStretch()
        layout.addLayout(fila_override)

        # Botones
        botonera = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(dlg.reject)
        btn_aplicar = QPushButton("✓ Aplicar DPI")
        btn_aplicar.setDefault(True)
        btn_aplicar.setStyleSheet(
            "QPushButton{background:#5cb85c; color:white; "
            "font-weight:bold; padding:6px 14px; border-radius:4px;}")
        btn_aplicar.clicked.connect(dlg.accept)
        botonera.addStretch()
        botonera.addWidget(btn_cancelar)
        botonera.addWidget(btn_aplicar)
        layout.addLayout(botonera)

        # ── Ejecutar ──────────────────────────────────────────────────
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        dpi_nuevo = spin_dpi.value()
        if dpi_nuevo <= 0 or dpi_nuevo == dpi_actual:
            return

        # Aplicar el cambio
        self.vista.pixeles_por_mm = dpi_nuevo / MM_POR_PULGADA
        # Marcar el origen como manual para que el diálogo lo refleje
        # correctamente la próxima vez que se abra.
        self._dpi_modo = "manual"
        # Recalcular y sincronizar una sola vez con la nueva escala.
        self.vista.recalcular_todas_las_distancias()
        self._guardar_estado()
        self.label_estado.setText(
            f"📐 DPI cambiado manualmente: {dpi_nuevo} "
            f"(1 mm = {self.vista.pixeles_por_mm:.2f} px). "
            f"Mediciones recalculadas."
        )

    def _activar_calibracion(self):
        """Activa el modo de calibración por regla.

        Flujo nuevo (acorde a la solicitud del usuario):
          1. Activar modo
          2. Usuario hace clic en 2 puntos sobre la imagen
          3. Después del 2° clic, se dibuja la línea con la distancia en px
             y aparece el diálogo pidiendo los mm
          4. Al aplicar, las marcas visuales se borran solas

        Antes el flujo era inverso: preguntaba primero los mm y después
        el usuario marcaba — era contra-intuitivo y dejaba las marcas
        permanentes en la imagen.
        """
        self.vista.iniciar_calibracion()
        self.label_estado.setText(
            "📏 Calibración: Haz clic en el primer punto de la distancia conocida.")
    # -------------------------------------------------------------------------
    # Importación de archivos .pos (CooRecorder)
    # -------------------------------------------------------------------------

    def _importar_pos(self):
        return control_exportacion._importar_pos(self)

    def _exportar_anomalias(self):
        'Exporta las anomalías de un radio en formato DendroEventos:\n        matriz binaria con los AÑOS en la primera columna y una columna por\n        cada TIPO de anomalía presente, con valores 0/1 (1 = ese año tiene\n        ese tipo de anomalía). El nombre de archivo sugerido es el de la\n        serie.\n\n        Las filas cubren TODO el rango de años de la medición (no solo los\n        años con anomalía), para que el archivo sea una serie temporal\n        completa lista para análisis de eventos en R u otros programas.\n        '
        return control_exportacion._exportar_anomalias(self)

    # -------------------------------------------------------------------------
    # Persistencia (guardado automático en JSON oculto)
    # -------------------------------------------------------------------------

    def _restaurar_metadatos_radio(self, datos):
        self.vista.anomalias = dict(datos.anomalias)
        with QSignalBlocker(self.check_tiene_medula), QSignalBlocker(self.check_tiene_corteza):
            self.check_tiene_medula.setChecked(datos.medula)
            self.check_tiene_corteza.setChecked(datos.corteza)

    def _capturar_radio(self, codigo=None):
        return RadioMedicion(
            codigo=self.input_codigo.text() if codigo is None else codigo,
            puntos=self.vista.modelo_medicion.captura(),
            anio_medula=self.spin_medula.value(),
            anio_corteza=self.spin_corteza.value(),
            dir_idx=self.combo_dir.currentIndex(),
            anomalias=self.vista.anomalias,
            medula=self.check_tiene_medula.isChecked(),
            corteza=self.check_tiene_corteza.isChecked(),
        )

    def _programar_guardado(self):
        self._guardado_pendiente = True
        self._timer_autoguardado.start()

    def guardar_pendiente(self):
        if self._guardado_pendiente or self._timer_autoguardado.isActive():
            return self._guardar_estado()
        return True

    def _guardar_estado(self):
        return control_sesion._guardar_estado(self)

    def _cargar_estado(self) -> bool:
        return control_sesion._cargar_estado(self)

    # -------------------------------------------------------------------------
    # Exportación
    # -------------------------------------------------------------------------

    def _ejecutar_exportacion(self):
        return control_exportacion._ejecutar_exportacion(self)

    # -------------------------------------------------------------------------
    # Sidecar de anomalías  (.rwl.anom.json)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Estimación de anillos faltantes hacia la médula
    # -------------------------------------------------------------------------

    def _iniciar_estimacion_pith(self):
        return self._pith.iniciar_estimacion_pith()


    def _confirmar_estimacion_pith(self):
        return self._pith.confirmar_estimacion_pith()



    def _deshacer_pith_offset(self):
        return self._pith.deshacer_pith_offset()

    # -------------------------------------------------------------------------
    # Earlywood / Latewood
    # -------------------------------------------------------------------------

    def _eliminar_ewlw(self):
        return self._ewlw.eliminar_ewlw()

    def _detectar_ewlw_automatico(self):
        return self._ewlw.detectar_ewlw_automatico()

    # -------------------------------------------------------------------------
    # Blue / Red / Green Intensity
    # -------------------------------------------------------------------------

    def _configurar_bi(self):
        return self._intensidad.configurar_bi()

    def _calcular_bi(self):
        return self._intensidad.calcular_bi()

    # ── Banda de muestreo BI sobre la imagen ─────────────────────────────
    def _toggle_banda_bi(self, activo: bool):
        return self._intensidad.toggle_banda_bi(activo)



    def _graficar_bi_ventana(self):
        return self._intensidad.graficar_bi_ventana()

    def _guardar_bi(self):
        return self._intensidad.guardar_bi()
 
 
 

    def tareas_medicion_en_curso(self):
        return self._tareas.en_curso

    def _ruta_sidecar(self, ruta_rwl: str | None = None) -> str | None:
        """Devuelve la ruta del archivo sidecar (oculto) para el radio exportado más reciente."""
        ruta = ruta_rwl or getattr(self, '_ultima_ruta_exportada', None)
        if not ruta:
            return None
        directorio = os.path.dirname(ruta)
        nombre = os.path.basename(ruta)
        return os.path.join(directorio, f".{nombre}.anom.json")

    def _guardar_sidecar_anom(self, ruta_rwl: str | None=None):
        'Escribe el .anom.json con anomalías + metadata del radio activo.'
        return control_sesion._guardar_sidecar_anom(self, ruta_rwl)

    def _cargar_sidecar_anom(self, ruta_rwl: str):
        'Lee el .anom.json (oculto) y carga anomalías + checkboxes si existe.'
        return control_sesion._cargar_sidecar_anom(self, ruta_rwl)

    def _anomalias_modificadas(self):
        """Llamado desde la vista cuando el usuario cambia una anomalía."""
        self._guardar_estado()
        self._guardar_sidecar_anom()
