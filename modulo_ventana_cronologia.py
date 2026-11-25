"""Componentes de la interfaz de co-datación de DPI."""

import os
import logging
import numpy as np
import pandas as pd
import pyqtgraph as pg
from modulo_widgets import _agregar_hover_anio, _crear_barra_zoom, SpinBoxFlechas, SeccionColapsable
from dpi.ciencia.estadistica import (sensibilidad_media, autocorrelacion_lag1,
                                calcular_eps_rbar_movil, calcular_sss,
                                estadisticos_por_desfase)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QSplitter, QFileDialog, QMessageBox, QFormLayout, QComboBox, QCheckBox, QLineEdit, QTextEdit, QGroupBox, QApplication, QProgressDialog
from PyQt6.QtCore import Qt, QEvent
from estilos import color_secundario
import estilos_graficos as _gr
from dpi.ciencia.comparacion_nucleo import resumir_desfases
from dpi.ciencia.datacion import score_compuesto, _serie_transformada_para_comparar
from dpi.formatos.planillas import es_planilla
from dpi.formatos.exportacion import asegurar_extension
from dpi.formatos.tucson import leer_tucson_multi
from dpi.formatos.compacto import leer_formato_compacto
from dpi.formatos.wid import leer_wid
from dpi.formatos.tabular import leer_tabular
from dpi.ciencia.cronologia import _detrend_serie_indice, detectar_series_problematicas
from dpi.ciencia.cronologia import _construir_cronologia_desde_series
from dpi.formatos.cronologias import _guardar_metadatos_cronologia, _exportar_cronologia_df, _leer_cronologia_guardada
from dpi.ui.series_util import _html_curvas_negativas, _mostrar_dialogo_eps_rbar, _ultima_carpeta
from modulo_dialogos_series import DialogoCurvasNegativas
from modulo_comparacion_ui import DialogoComparacionMultiple, VentanaTablaOffset


logger = logging.getLogger(__name__)


import dpi.ui.control_cronologia as control_cronologia


import dpi.ui.presentacion_cronologia as presentacion_cronologia


class VentanaCronologia(QWidget):
    """Panel de cronologías con una salida explícita hacia el coordinador."""

    def __init__(self, enviar_cronologia=None, parent=None):
        super().__init__(parent)
        self._series_cronologia: dict[str, pd.DataFrame] = {}
        self._enviar_cronologia = enviar_cronologia
        self.setWindowTitle("Cronología")
        self.setMinimumSize(900, 600)

        self.cronologia_df: pd.DataFrame | None = None
        self.cronologia_meta: dict = {}
        self.eps_movil: pd.DataFrame | None = None

        self._construir_ui()
        self.refresh_series()
        self._sincronizar_widgets_con_tema_app()

    def _sincronizar_widgets_con_tema_app(self):
        """Aplica colores apropiados al QTextEdit según el tema activo de la app.
        QTextEdit no está cubierto por el stylesheet global (estilos.py solo
        cubre QListView/QSpinBox/etc), así que sin esto el QTextEdit queda con
        fondo blanco default y el texto blanco heredado de `QWidget { color: white; }`
        del estilo global oscuro → metadata invisible.
        """
        ss_app = QApplication.instance().styleSheet() or ""
        if "#2b2b2b" in ss_app:
            # Tema oscuro — replicar el estilo de QListView del global
            self.txt_info.setStyleSheet(
                "QTextEdit { background-color: #3b3b3b; color: white; "
                "border: 1px solid #555; border-radius: 3px; padding: 4px; }"
            )
        elif "#f0f0f0" in ss_app:
            # Tema claro
            self.txt_info.setStyleSheet(
                "QTextEdit { background-color: white; color: black; "
                "border: 1px solid #ccc; border-radius: 3px; padding: 4px; }"
            )
        # Si no hay marcador reconocible, dejar sin estilizar.

        # Los gráficos no se enteran solos del cambio de tema: pyqtgraph pinta
        # con sus propios colores (fondo negro por omisión) y no mira el
        # stylesheet ni la paleta de Qt.
        _gr.aplicar_a_todos(self)

    def changeEvent(self, event):
        """Re-sincroniza el QTextEdit cuando cambia el tema de la app en caliente."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange and hasattr(self, "txt_info"):
            self._sincronizar_widgets_con_tema_app()

    def _construir_ui(self):
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_cargar_series = QPushButton("📂 Cargar series")
        self.btn_cargar_series.clicked.connect(self._cargar_series_desde_panel)
        barra.addWidget(self.btn_cargar_series)

        self.btn_nueva = QPushButton("🗑 Nueva")
        self.btn_nueva.setToolTip(
            "Limpia todo (series cargadas y cronología generada) para "
            "empezar una cronología nueva desde cero.")
        self.btn_nueva.setStyleSheet(
            "QPushButton{background-color:#6c757d; color:white;}"
            "QPushButton:hover{background-color:#7d868e;}")
        self.btn_nueva.clicked.connect(self.nueva_cronologia)
        barra.addWidget(self.btn_nueva)

        self.btn_generar = QPushButton("⚙ Generar cronología")
        self.btn_generar.clicked.connect(self.generar_cronologia)
        self.btn_generar.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold;")
        barra.addWidget(self.btn_generar)

        self.btn_exportar = QPushButton("💾 Exportar cronología")
        self.btn_exportar.clicked.connect(self.exportar_cronologia)
        self.btn_exportar.setEnabled(False)
        barra.addWidget(self.btn_exportar)

        self.btn_eps_rbar = QPushButton("📈 EPS / Rbar")
        self.btn_eps_rbar.setToolTip(
            "Ver el gráfico de EPS móvil y Rbar móvil de la cronología actual.\n"
            "Permite identificar tramos de años con baja confianza estadística."
        )
        self.btn_eps_rbar.setStyleSheet(
            "QPushButton{background-color:#3a6e3a; color:white; font-weight:bold;}"
            "QPushButton:hover{background-color:#4a8e4a;}"
            "QPushButton:disabled{background-color:#444; color:#888;}"
        )
        self.btn_eps_rbar.setEnabled(False)
        self.btn_eps_rbar.clicked.connect(self._mostrar_eps_rbar)
        barra.addWidget(self.btn_eps_rbar)

        self.btn_usar = QPushButton("📚 Usar en cofechado")
        self.btn_usar.clicked.connect(self.usar_cronologia_en_panel)
        self.btn_usar.setEnabled(False)
        barra.addWidget(self.btn_usar)

        self.btn_comparar = QPushButton("🔎 Comparar con cronología")
        self.btn_comparar.setToolTip(
            "Comparar serie(s) marcada(s) contra la cronología activa.\n"
            "• 1 serie marcada  → gráfico + análisis detallado\n"
            "• 2+ marcadas      → tabla resumen batch (una fila por serie)")
        self.btn_comparar.clicked.connect(self.comparar_con_cronologia)
        self.btn_comparar.setEnabled(False)
        barra.addWidget(self.btn_comparar)

        # Botón "Tabla detallada": muestra los resultados de la última
        # comparación con TODOS los desfases ordenados por score compuesto.
        # Aparece oculto al inicio (no hay resultados todavía) y se muestra
        # automáticamente después de la primera comparación.
        self._btn_tabla_comparacion = QPushButton("📊 Tabla detallada")
        self._btn_tabla_comparacion.setToolTip(
            "Ver todos los desfases con r, GLK, t-BP y puntaje compuesto\n"
            "(disponible después de comparar con la cronología)")
        self._btn_tabla_comparacion.clicked.connect(self._abrir_tabla_comparacion)
        self._btn_tabla_comparacion.setVisible(False)
        barra.addWidget(self._btn_tabla_comparacion)

        layout.addLayout(barra)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        left_layout.addWidget(QLabel("<b>Series disponibles:</b>"))

        self.btn_sel_todo = QPushButton("☑ Seleccionar / Deseleccionar todo")
        self.btn_sel_todo.setStyleSheet("QPushButton{padding:4px; font-size:11px;}")
        self.btn_sel_todo.clicked.connect(self.toggle_seleccion)
        left_layout.addWidget(self.btn_sel_todo)

        self.lista_series = QListWidget()
        self.lista_series.itemChanged.connect(self._sincronizar_estado_botones)
        left_layout.addWidget(self.lista_series, 1)

        self.lbl_estado = QLabel("Sin cronología cargada.")
        self.lbl_estado.setWordWrap(True)
        left_layout.addWidget(self.lbl_estado)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        box_cfg = QGroupBox("Configuración")
        form = QFormLayout(box_cfg)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["raw", "standard", "residual", "Todas"])
        # Default = "residual": es el tipo típico para cofechado/clima (estilo
        # COFECHA/ARSTAN) y, además, deja el selector de estandarización
        # habilitado desde el inicio. Con "raw" (sin detrending) el método de
        # estandarización no aplica y queda deshabilitado, lo que confundía
        # ("no deja escoger").
        self.combo_tipo.setCurrentText("residual")
        self.combo_tipo.currentTextChanged.connect(self._on_tipo_cronologia_cambiado)
        form.addRow("Tipo de cronología:", self.combo_tipo)

        self.combo_metodo = QComboBox()
        # "raw" se quitó porque no aplica estandarización: tipo="standard" con
        # metodo="raw" devuelve exactamente lo mismo que tipo="raw". Para
        # cronología sin detrending, usar tipo="raw" directamente.
        # "media" se muestra en español; _ajustar_curva acepta tanto "media"
        # como "mean", así que el texto visible puede ir en español.
        self.combo_metodo.addItems(["spline", "negexp", "linear", "media_movil", "media"])
        self.combo_metodo.setCurrentText("spline")
        self.combo_metodo.currentTextChanged.connect(self._on_metodo_estandar_cambiado)

        # Spinbox de ventana para media_movil — aparece solo cuando se elige
        # ese método. Default 10% del largo (estilo ARSTAN), pero el usuario
        # puede sobreescribir con un valor fijo.
        self.spin_ventana_mm = SpinBoxFlechas()
        self.spin_ventana_mm.setRange(3, 999)
        self.spin_ventana_mm.setValue(11)
        self.spin_ventana_mm.setSuffix(" años")
        self.spin_ventana_mm.setMinimumWidth(140)
        self.spin_ventana_mm.setToolTip(
            "Ventana de la media móvil (en años). Por convención impar.\n"
            "Valores chicos (5–15) → tendencia local más sensible.\n"
            "Valores grandes (30+) → tendencia más suave (similar a spline rígido)."
        )
        self.spin_ventana_mm.setVisible(False)

        fila_metodo = QHBoxLayout()
        fila_metodo.setContentsMargins(0, 0, 0, 0)
        fila_metodo.setSpacing(6)
        fila_metodo.addWidget(self.combo_metodo, 1)
        fila_metodo.addWidget(self.spin_ventana_mm)
        contenedor_metodo = QWidget()
        contenedor_metodo.setLayout(fila_metodo)
        form.addRow("Estandarización:", contenedor_metodo)

        self.combo_agreg = QComboBox()
        # Texto en español visible para el usuario, pero el VALOR interno
        # (userData) se mantiene en inglés para no romper la lógica de
        # construcción de la cronología. Se lee con currentData().
        self.combo_agreg.addItem("Biponderada (biweight)", "biweight")
        self.combo_agreg.addItem("Media", "mean")
        self.combo_agreg.addItem("Mediana", "median")
        self.combo_agreg.setCurrentIndex(0)  # biponderada por defecto
        self.combo_agreg.setToolTip(
            "Cómo se combinan las series individuales en UNA cronología media:\n\n"
            "• Biponderada (biweight): media robusta de Tukey. Baja el peso\n"
            "  de valores atípicos progresivamente. Es el estándar en\n"
            "  dendrocronología (lo que usa ARSTAN por defecto).\n"
            "• Media: media aritmética simple. Sensible a valores atípicos.\n"
            "• Mediana: el valor central. Robusta pero descarta magnitud."
        )
        form.addRow("Agregación:", self.combo_agreg)

        # ── Opciones al modo de ARSTAN ────────────────────────────────────
        # Van en una sección plegada porque la mayoría de las corridas no las
        # necesita, pero sin ellas una cronología de DPI no es comparable con
        # una de ARSTAN: su configuración por omisión usa DOBLE detrending.
        self.grupo_arstan = SeccionColapsable("Opciones ARSTAN (avanzado)",
                                              expandida=False)
        _fa = QFormLayout()
        _fa.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_rigidez1 = SpinBoxFlechas()
        self.spin_rigidez1.setRange(-100, 999)
        self.spin_rigidez1.setValue(32)
        self.spin_rigidez1.setSuffix(" años / -%")
        self.spin_rigidez1.setToolTip(
            "Rigidez del PRIMER ajuste, solo si es spline.\n\n"
            "Positivo = años (32 es el corte del 50 % a 32 años).\n"
            "NEGATIVO = porcentaje del largo de CADA serie: -67 da un spline\n"
            "de 67 años en una serie de 100 y de 268 en una de 400.\n\n"
            "La forma negativa es la que permite tratar series de distinto\n"
            "largo de manera comparable.")
        _fa.addRow("Rigidez 1ª curva:", self.spin_rigidez1)

        self.combo_metodo2 = QComboBox()
        self.combo_metodo2.addItem("ninguno (un solo detrending)", "")
        for m in ("spline", "negexp", "linear", "media_movil", "media"):
            self.combo_metodo2.addItem(m, m)
        self.combo_metodo2.setToolTip(
            "SEGUNDO ajuste, aplicado sobre los índices del primero.\n\n"
            "Es el valor POR OMISIÓN de ARSTAN: su configuración inicial es\n"
            "exponencial negativa y después spline de 128 años.\n\n"
            "El manual explica por qué: la exponencial ajusta bien el tercio\n"
            "inicial, pero después puede ir muchas décadas por encima o por\n"
            "debajo del crecimiento real. El segundo ajuste corrige ese desvío.")
        _fa.addRow("2ª curva:", self.combo_metodo2)

        self.spin_rigidez2 = SpinBoxFlechas()
        self.spin_rigidez2.setRange(-100, 999)
        self.spin_rigidez2.setValue(128)
        self.spin_rigidez2.setSuffix(" años / -%")
        self.spin_rigidez2.setToolTip(
            "Rigidez de la segunda curva. 128 años es el valor de ARSTAN.")
        _fa.addRow("Rigidez 2ª curva:", self.spin_rigidez2)

        self.spin_rig_min = SpinBoxFlechas()
        self.spin_rig_min.setRange(0, 500)
        self.spin_rig_min.setValue(0)
        self.spin_rig_min.setSuffix(" años")
        self.spin_rig_min.setToolTip(
            "Rigidez MÍNIMA: el spline nunca baja de este valor.\n\n"
            "Sirve con la rigidez porcentual, para no ajustar curvas muy\n"
            "flexibles a series cortas, que las dejaría con una estructura de\n"
            "persistencia distinta a la de las largas. 0 = sin mínimo.")
        _fa.addRow("Rigidez mínima:", self.spin_rig_min)

        self.chk_estabilizar = QCheckBox("Estabilizar varianza")
        self.chk_estabilizar.setToolTip(
            "Compensa los cambios de varianza a lo largo de la serie.\n\n"
            "Ajusta un spline a los valores ABSOLUTOS de las desviaciones\n"
            "respecto de la media, divide por esa curva y restituye los signos.\n"
            "Sirve cuando la varianza cambia mucho en el tiempo, porque si no\n"
            "los tramos de varianza alta dominan la cronología.")
        _fa.addRow("", self.chk_estabilizar)

        self.spin_rig_estab = SpinBoxFlechas()
        self.spin_rig_estab.setRange(-100, 999)
        self.spin_rig_estab.setValue(64)
        self.spin_rig_estab.setSuffix(" años / -%")
        self.spin_rig_estab.setToolTip(
            "Rigidez del spline de estabilización.\n\n"
            "Es un compromiso, medido sobre seis series largas de ciprés como\n"
            "razón entre la desviación máxima y la mínima en ventanas de 60\n"
            "años (1,00 sería varianza perfectamente estable):\n\n"
            "   sin estabilizar   2,15\n"
            "   spline 128 años   1,56\n"
            "   spline  64 años   1,39   <- valor por omisión\n"
            "   spline  32 años   1,29\n\n"
            "Más flexible estabiliza mejor, pero también aplana amplitudes que\n"
            "pueden ser reales.")
        _fa.addRow("Rigidez estab.:", self.spin_rig_estab)

        self.chk_normalizar = QCheckBox("Normalizar a varianza 1")
        self.chk_normalizar.setToolTip(
            "Lleva cada serie a varianza 1 antes de promediar, para que todas\n"
            "pesen igual en la cronología.\n\n"
            "Sin esto, las series más variables dominan el promedio.")
        _fa.addRow("", self.chk_normalizar)

        self.chk_por_resta = QCheckBox("Índices por resta (no división)")
        self.chk_por_resta.setToolTip(
            "Calcula el índice como serie MENOS curva, en vez de dividida.\n\n"
            "ARSTAN permite las dos. Con series transformadas a logaritmos,\n"
            "la resta es lo natural.")
        _fa.addRow("", self.chk_por_resta)

        self.chk_log_arstan = QCheckBox("Logaritmo antes de ajustar")
        self.chk_log_arstan.setToolTip(
            "Toma el logaritmo del ancho (sumando un sexto de la media) ANTES\n"
            "de ajustar la curva. Es la transformación de datos de ARSTAN.")
        _fa.addRow("", self.chk_log_arstan)

        _cont_ar = QWidget()
        _cont_ar.setLayout(_fa)
        self.grupo_arstan.agregar_widget(_cont_ar)
        form.addRow(self.grupo_arstan)

        # ── Transformación logarítmica (estilo COFECHA) ──────────────
        # Aplica log(índice + media/6) antes del modelo AR, igual que
        # COFECHA (Holmes 1983). Comprime los anillos anchos y suele subir
        # la correlación de cofechado. Debe usarse por igual en la
        # cronología y en las series (DPI lo hace automático al cofechar).
        self.chk_log_crono = QCheckBox("Transformación logarítmica (estilo COFECHA)")
        self.chk_log_crono.setChecked(False)
        self.chk_log_crono.setToolTip(
            "Aplica log(índice + media/6) antes del modelo autorregresivo,\n"
            "igual que COFECHA (opción 'Series transformed to logarithms').\n\n"
            "Comprime los anillos anchos y normalmente sube la correlación\n"
            "de cofechado, acercándola a los valores de COFECHA. Al cofechar,\n"
            "DPI estandariza las series con log automáticamente si la\n"
            "cronología activa se construyó con esta opción.\n\n"
            "Solo aplica a cronologías 'standard' y 'residual' (no 'raw')."
        )
        form.addRow("", self.chk_log_crono)

        # Etiqueta de solape con descripción al pasar el mouse
        lbl_overlap = QLabel("Solape mínimo:")
        lbl_overlap.setToolTip(
            "Cantidad mínima de años en común que dos series deben tener\n"
            "para calcular la correlación entre ellas.\n\n"
            "Valores chicos (5–10) → incluye más pares pero correlaciones\n"
            "menos confiables. Valores grandes (30+) → solo pares con\n"
            "buen solape, más confiable pero descarta series cortas."
        )
        self.spin_min_overlap = SpinBoxFlechas()
        self.spin_min_overlap.setRange(2, 500)
        self.spin_min_overlap.setValue(10)
        self.spin_min_overlap.setToolTip(lbl_overlap.toolTip())
        form.addRow(lbl_overlap, self.spin_min_overlap)

        self.spin_shift = SpinBoxFlechas()
        self.spin_shift.setRange(0, 10)
        self.spin_shift.setValue(5)
        form.addRow("Desfase auto máx.:", self.spin_shift)

        # ── Ventana móvil para Rbar / EPS ─────────────────────────────
        # Permite reproducir el formato de ARSTAN (ventana de 50 años con
        # paso de 25) para comparar y reportar en publicaciones. Con
        # ventana chica (15) y paso 1 se obtiene la curva año a año suave.
        lbl_ventana_eps = QLabel("Ventana Rbar/EPS:")
        lbl_ventana_eps.setToolTip(
            "Tamaño de la ventana móvil (en años) para calcular Rbar y EPS.\n\n"
            "• 50 años → formato estándar de ARSTAN (recomendado para\n"
            "  comparar y para publicaciones).\n"
            "• 15 años o menos → curva más detallada año a año, útil para\n"
            "  ver la evolución fina de la señal común.\n\n"
            "Ventanas grandes promedian más datos y dan valores más estables."
        )
        self.spin_ventana_eps = SpinBoxFlechas()
        self.spin_ventana_eps.setRange(10, 200)
        self.spin_ventana_eps.setValue(50)
        self.spin_ventana_eps.setSingleStep(5)
        self.spin_ventana_eps.setSuffix(" años")
        self.spin_ventana_eps.setToolTip(lbl_ventana_eps.toolTip())
        form.addRow(lbl_ventana_eps, self.spin_ventana_eps)

        lbl_paso_eps = QLabel("Paso Rbar/EPS:")
        lbl_paso_eps.setToolTip(
            "Cada cuántos años se desliza la ventana móvil.\n\n"
            "• 25 años → formato estándar de ARSTAN (la ventana se mueve\n"
            "  en saltos de 25 años, generando pocos valores espaciados).\n"
            "• 1 año → un valor por cada año (curva continua y suave).\n\n"
            "Para reproducir ARSTAN usa ventana 50 y paso 25."
        )
        self.spin_paso_eps = SpinBoxFlechas()
        self.spin_paso_eps.setRange(1, 100)
        self.spin_paso_eps.setValue(25)
        self.spin_paso_eps.setSuffix(" años")
        self.spin_paso_eps.setToolTip(lbl_paso_eps.toolTip())
        form.addRow(lbl_paso_eps, self.spin_paso_eps)

        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Nombre de cronología")
        form.addRow("Nombre:", self.input_nombre)

        # Fila superior: Configuración (≈1/3 del ancho) e Información /
        # metadatos (≈2/3) lado a lado. Antes estaban apiladas y la
        # Configuración ocupaba todo el ancho; ponerlas en fila libera alto
        # para que el gráfico de abajo sea más grande.
        box_info = QGroupBox("Información / metadatos")
        info_layout = QVBoxLayout(box_info)
        self.txt_info = QTextEdit()
        self.txt_info.setReadOnly(True)
        self.txt_info.setMinimumHeight(140)
        info_layout.addWidget(self.txt_info)

        fila_cfg_info = QHBoxLayout()
        fila_cfg_info.addWidget(box_cfg, 1)    # ≈ un tercio
        fila_cfg_info.addWidget(box_info, 2)   # ≈ dos tercios
        right_layout.addLayout(fila_cfg_info, 0)

        self.grafico = pg.PlotWidget(title="Cronología")
        _agregar_hover_anio(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        _gr.aplicar_a_pyqtgraph(self.grafico)
        right_layout.addWidget(self.grafico, 1)
        # El umbral 0.85 del EPS es una línea de referencia del gráfico, no una
        # curva de datos, así que se pasa aparte para que la figura exportada
        # la dibuje como tal.
        right_layout.addWidget(_crear_barra_zoom(
            self.grafico, nombre_exportar="cronologia",
            lineas_h_exportar=[(0.85, "EPS 0.85")]))

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # Estado inicial: aplicar enable/disable según el tipo seleccionado
        self._on_tipo_cronologia_cambiado(self.combo_tipo.currentText())

    def _on_tipo_cronologia_cambiado(self, tipo: str):
        """Habilita/deshabilita el combo de estandarización según el tipo.

        Cuando tipo='raw' la estandarización no aplica (la serie se devuelve
        tal cual sin detrending), así que el combo se deshabilita visualmente
        para que el usuario sepa que no tiene efecto.
        """
        if not hasattr(self, "combo_metodo"):
            return
        es_raw = (tipo or "").lower() == "raw"
        self.combo_metodo.setEnabled(not es_raw)
        if hasattr(self, "spin_ventana_mm"):
            # También deshabilitar el spinbox de ventana si tipo=raw
            self.spin_ventana_mm.setEnabled(not es_raw)
        if hasattr(self, "chk_log_crono"):
            # El log no aplica a 'raw' (no hay índice que transformar)
            self.chk_log_crono.setEnabled(not es_raw)
        if es_raw:
            self.combo_metodo.setToolTip(
                "No aplica con tipo='raw' — la serie se usa sin estandarización."
            )
        else:
            self.combo_metodo.setToolTip("")

    def _on_metodo_estandar_cambiado(self, metodo: str):
        """Muestra el spinbox de ventana solo cuando se elige media_movil."""
        if hasattr(self, "spin_ventana_mm"):
            self.spin_ventana_mm.setVisible(
                (metodo or "").lower() in {"media_movil", "moving_average", "ma"}
            )

    def nueva_cronologia(self):
        """Limpia todo para empezar una cronología nueva: series cargadas,
        cronología generada, gráfico e información."""
        if self._series_cronologia or self.cronologia_df is not None:
            resp = QMessageBox.question(
                self, "Nueva cronología",
                "¿Limpiar todo (series cargadas y cronología generada) para "
                "empezar una nueva?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes:
                return
        self._series_cronologia.clear()
        self.cronologia_df = None
        self.cronologia_meta = {}
        self.eps_movil = None
        self.lista_series.clear()
        self.grafico.clear()
        self.txt_info.setPlainText("Sin cronología cargada.")
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setEnabled(False)

    def series_para_nulo(self):
        """Instantánea independiente para las comparaciones externas."""
        return {nombre: df.copy(deep=True) for nombre, df in self._series_cronologia.items()}

    def refresh_series(self, marcar_todas: bool = False):
        """Refresca la lista de series disponibles.

        Si `marcar_todas` es True (al cargar series nuevas), todas las series
        quedan SELECCIONADAS automáticamente — el propósito de cargarlas es
        construir la cronología con ellas, así que conviene que aparezcan
        marcadas. En refrescos normales se conserva el estado de selección.
        """
        self.lista_series.blockSignals(True)
        checked = {
            self.lista_series.item(i).text()
            for i in range(self.lista_series.count())
            if self.lista_series.item(i).checkState() == Qt.CheckState.Checked
        }
        self.lista_series.clear()
        for nombre in sorted(self._series_cronologia.keys()):
            if nombre.startswith("📚 "):
                continue
            item = QListWidgetItem(nombre)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            marcar = marcar_todas or (nombre in checked)
            item.setCheckState(
                Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
            self.lista_series.addItem(item)
        self.lista_series.blockSignals(False)
        self._sincronizar_estado_botones()

    def _series_marcadas(self) -> list[str]:
        return [
            self.lista_series.item(i).text()
            for i in range(self.lista_series.count())
            if self.lista_series.item(i).checkState() == Qt.CheckState.Checked
        ]

    def toggle_seleccion(self):
        todas = all(
            self.lista_series.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.lista_series.count())
        )
        estado = Qt.CheckState.Unchecked if todas else Qt.CheckState.Checked
        self.lista_series.blockSignals(True)
        for i in range(self.lista_series.count()):
            self.lista_series.item(i).setCheckState(estado)
        self.lista_series.blockSignals(False)
        self._sincronizar_estado_botones()

    def _sincronizar_estado_botones(self):
        hay_crono = self.cronologia_df is not None and not self.cronologia_df.empty
        self.btn_exportar.setEnabled(hay_crono)
        self.btn_usar.setEnabled(hay_crono)
        self.btn_comparar.setEnabled(hay_crono)
        # EPS/Rbar solo si hay datos móviles calculados
        tiene_eps_movil = bool((self.cronologia_meta or {}).get("EPS_movil"))
        self.btn_eps_rbar.setEnabled(hay_crono and tiene_eps_movil)
        if hay_crono:
            meta = self.cronologia_meta
            self.lbl_estado.setText(
                f"Cronología cargada: {meta.get('nombre', 'Cronología')} | "
                f"tipo={meta.get('tipo_cronologia', 'raw')} | "
                f"método={meta.get('metodo_estandarizacion', 'raw')} | "
                f"agregación={meta.get('agregacion', 'mean')}"
            )
        else:
            self.lbl_estado.setText("Sin cronología cargada.")

    def _mostrar_eps_rbar(self):
        """Muestra el diálogo EPS/Rbar de la cronología actual del diálogo.
        Reutiliza la misma función que el botón EPS/Rbar del panel."""
        nombre = (self.cronologia_meta or {}).get("nombre", "Cronología")
        _mostrar_dialogo_eps_rbar(self, self.cronologia_meta or {}, nombre)

    def _cargar_series_desde_panel(self):
        """Carga series SOLO en la ventana de cronología."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Series", _ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.wid *.csv *.tsv *.xlsx *.xls *.ods *.cat *.cmp);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if rutas:
            _ultima_carpeta(rutas[0])
        for ruta in rutas:
            try:
                with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                    primeras = f.read(500)
                if "=N" in primeras and "=I" in primeras:
                    series_ext = leer_formato_compacto(ruta)
                    for sid, df in series_ext.items():
                        if sid not in self._series_cronologia:
                            self._series_cronologia[sid] = df.copy()
                    continue
                ext = os.path.splitext(ruta)[1].lower()
                if ext == ".wid":
                    df, sid = leer_wid(ruta)
                    if sid not in self._series_cronologia:
                        self._series_cronologia[sid] = df.copy()
                elif ext in (".csv", ".tsv") or es_planilla(ext):
                    df, sid = leer_tabular(ruta)
                    if sid not in self._series_cronologia:
                        self._series_cronologia[sid] = df.copy()
                else:
                    try:
                        series_ext = leer_tucson_multi(ruta)
                        for sid, df in series_ext.items():
                            if sid not in self._series_cronologia:
                                self._series_cronologia[sid] = df.copy()
                    except (ValueError, OSError) as exc:
                        logger.debug("Tucson no reconocido, probando formato tabular: %s", exc)
                        df, sid = leer_tabular(ruta)
                        if sid not in self._series_cronologia:
                            self._series_cronologia[sid] = df.copy()
            except Exception as exc:
                logger.exception("No se pudo cargar serie de cronología")
                QMessageBox.warning(self, "Error", f"No se pudo cargar:\n{exc}")
        # Marcar automáticamente todas las series tras cargarlas.
        self.refresh_series(marcar_todas=True)

    def generar_cronologia(self):
        return control_cronologia.generar_cronologia(self)

    def cargar_cronologia(self):
        return control_cronologia.cargar_cronologia(self)

    def exportar_cronologia(self):
        return control_cronologia.exportar_cronologia(self)

    def usar_cronologia_en_panel(self):
        if self.cronologia_df is None or self.cronologia_df.empty:
            return
        nombre = self.cronologia_meta.get("nombre", "Cronología")
        if self._enviar_cronologia is None:
            QMessageBox.warning(self, "Sin destino", "No hay un panel de cofechado conectado.")
            return
        self._enviar_cronologia(self.cronologia_df, self.cronologia_meta, nombre)
        QMessageBox.information(
            self, "OK",
            f"Cronología '{nombre}' activada en el panel de cofechado.\n\n"
            "Aparece en la lista del panel con el prefijo 📚.\n"
            "Marcala junto a una serie y dale Verificar / Buscar / Analizar."
        )

    def comparar_con_cronologia(self):
        """Compara series marcadas contra la cronología activa.

        Bifurca según la cantidad de series marcadas:
          - 1 sola → modo individual: gráfico de r vs desfase, texto con
            top 3 candidatos por score, botón "Tabla detallada"
          - 2 o más → modo batch: diálogo nuevo con tabla resumen
            (una fila por serie) ordenable, con doble clic para drill-down
            al modo individual de cada serie.

        El usuario controla el modo con la cantidad de check marcados
        en el panel, sin botones extra.
        """
        if self.cronologia_df is None or self.cronologia_df.empty:
            QMessageBox.warning(self, "Atención", "Primero cargue o genere una cronología.")
            return
        nombres = self._series_marcadas()
        if len(nombres) < 1:
            QMessageBox.warning(
                self, "Atención",
                "Marque al menos una serie para comparar.\n"
                "(Marque varias para hacer comparación múltiple.)")
            return

        # Si hay más de una serie marcada → modo batch
        if len(nombres) > 1:
            self._comparar_multiple_con_cronologia(nombres)
            return

        # Modo individual (1 sola serie) — comportamiento histórico
        nombre = nombres[0]
        self._comparar_individual_con_cronologia(nombre)

    def _serie_referencia_comparacion(self):
        columna = self.cronologia_meta.get("columna_valor")
        if columna not in self.cronologia_df.columns:
            columna = self.cronologia_df.columns[0]
        return pd.to_numeric(self.cronologia_df[columna], errors="coerce").dropna()

    def _comparar_individual_con_cronologia(self, nombre: str):
        """Modo individual: 1 serie → gráfico + texto + tabla detallada.

        Es el comportamiento histórico, conservado tal cual estaba antes
        del modo batch. Útil para inspección a fondo de una sola serie.
        """
        serie = self._series_cronologia[nombre]
        meta = self.cronologia_meta
        s_a = _serie_transformada_para_comparar(serie, meta)
        s_b = self._serie_referencia_comparacion()

        # Cálculo de los TRES estadísticos por cada desfase
        shifts, rs, glks, tbps, ns = estadisticos_por_desfase(
            s_a, s_b,
            self.spin_shift.value(),
            self.spin_min_overlap.value(),
        )

        self.grafico.clear()
        if not shifts:
            self.grafico.setTitle("No se encontraron solapamientos suficientes.")
            return

        # Guardar para que el botón "Ver tabla" pueda abrirla después
        self._ultimo_resultado_comparacion = {
            "nombre_serie": nombre,
            "shifts": shifts, "rs": rs, "glks": glks,
            "tbps": tbps, "ns": ns,
        }

        # Línea de referencia en y=0
        self.grafico.addItem(
            pg.InfiniteLine(pos=0, angle=0,
                             pen=pg.mkPen("#888888", width=1)))

        # Plot principal: r (lo más interpretable visualmente, escala [-1, 1])
        self.grafico.plot(shifts, rs,
                          pen=pg.mkPen("#3388FF", width=2), symbol="o")

        # Score compuesto en cada shift y elección del mejor por score
        scores = [score_compuesto(r, g, t)
                  for r, g, t in zip(rs, glks, tbps)]
        scores_validos = [(i, s) for i, s in enumerate(scores) if np.isfinite(s)]
        if scores_validos:
            idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
        else:
            idx_mejor = int(np.argmax(rs))

        best_shift = shifts[idx_mejor]
        best_r = rs[idx_mejor]
        best_glk = glks[idx_mejor]
        best_tbp = tbps[idx_mejor]
        best_score = scores[idx_mejor]
        best_n = ns[idx_mejor]

        # Punto verde grande en el mejor según score compuesto
        self.grafico.addItem(pg.ScatterPlotItem(
            x=[best_shift], y=[best_r], size=14,
            brush=pg.mkBrush("#5cb85c"), pen=pg.mkPen("w", width=2),
        ))

        self.grafico.setYRange(-1.05, 1.05)
        self.grafico.setTitle(
            f"'{nombre}' vs cronología — mejor desfase: {best_shift}"
            f"  (puntaje={best_score:.3f})"
        )

        # Construir resumen multi-stat para txt_info
        def fmt(x, dec=3):
            return f"{x:.{dec}f}" if np.isfinite(x) else "—"

        # Top 3 desfases por score compuesto, para mostrar candidatos
        top3 = sorted(
            range(len(shifts)),
            key=lambda i: scores[i] if np.isfinite(scores[i]) else -1e9,
            reverse=True,
        )[:3]
        lineas_top = []
        for rank, i in enumerate(top3, start=1):
            lineas_top.append(
                f"    #{rank}  desfase={shifts[i]:+d}  "
                f"r={fmt(rs[i])}  GLK={fmt(glks[i])}  "
                f"t-BP={fmt(tbps[i], 2)}  puntaje={fmt(scores[i])}  "
                f"n={ns[i]}"
            )

        self.txt_info.append(
            f"\nComparación '{nombre}' vs cronología:\n"
            f"  Mejor desfase: {best_shift:+d}\n"
            f"    r       = {fmt(best_r)}\n"
            f"    GLK     = {fmt(best_glk)}\n"
            f"    t-BP    = {fmt(best_tbp, 2)}\n"
            f"    puntaje = {fmt(best_score)}  "
            f"(media geom. de las 3 métricas normalizadas)\n"
            f"    n       = {best_n} años de solape\n"
            f"  Top 3 desfases por puntaje compuesto:\n"
            + "\n".join(lineas_top)
            + "\n"
        )

        # Mostrar el botón "Ver tabla detallada" si está oculto
        if hasattr(self, "_btn_tabla_comparacion"):
            self._btn_tabla_comparacion.setVisible(True)

    def _comparar_multiple_con_cronologia(self, nombres: list[str]):
        """Modo batch: N>1 series → tabla resumen con una fila por serie.

        Para cada serie ejecuta `estadisticos_por_desfase` (mismo cálculo
        que el modo individual) y guarda el resultado completo + el "mejor"
        según score compuesto + el score en shift=0 para calcular el Δ.

        Al terminar abre `DialogoComparacionMultiple` que permite ordenar
        por cualquier columna y hacer drill-down con doble clic.
        """
        meta = self.cronologia_meta
        s_b = self._serie_referencia_comparacion()
        max_shift_val = self.spin_shift.value()
        min_overlap_val = self.spin_min_overlap.value()

        # Cursor de espera durante el cálculo (puede tomar segundos con
        # decenas de series y rangos de shift amplios)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        resultados = []
        nombre_crono = meta.get("nombre", "cronología")

        try:
            for nombre in nombres:
                serie = self._series_cronologia[nombre]
                s_a = _serie_transformada_para_comparar(serie, meta)

                shifts, rs, glks, tbps, ns = estadisticos_por_desfase(
                    s_a, s_b, max_shift_val, min_overlap_val,
                )

                resultados.append(resumir_desfases(nombre, shifts, rs, glks, tbps, ns, s_a, s_b))
                if not shifts:
                    continue

                # Refrescar UI para evitar congelamiento percibido en
                # series largas o muchas series. processEvents() es
                # suficiente acá; no necesitamos hilos para N modesto.
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        # Resumen de una línea en txt_info
        n_validas = sum(1 for r in resultados if np.isfinite(r["mejor_score"]))
        self.txt_info.append(
            f"\nComparación múltiple ({len(resultados)} series) vs "
            f"cronología '{nombre_crono}':\n"
            f"  {n_validas} con resultado válido  ·  "
            f"{len(resultados) - n_validas} sin solape suficiente\n"
            f"  → ver tabla resumen para análisis detallado.\n"
        )

        # Abrir el diálogo modal
        dlg = DialogoComparacionMultiple(resultados, nombre_crono, parent=self)
        dlg.exec()

    def _abrir_tabla_comparacion(self):
        """Abre VentanaTablaOffset con los resultados de la última
        `comparar_con_cronologia`. Reutilizamos exactamente la misma tabla
        que ya existe para series flotantes (con colores por umbral,
        ordenable, score compuesto destacado)."""
        datos = getattr(self, "_ultimo_resultado_comparacion", None)
        if not datos:
            QMessageBox.information(
                self, "Sin datos",
                "Ejecuta primero una comparación con la cronología.")
            return
        dlg = VentanaTablaOffset(
            datos["shifts"], datos["rs"],
            glks=datos["glks"], tbps=datos["tbps"], ns=datos["ns"],
            parent=self,
        )
        dlg.setWindowTitle(
            f"Resultados detallados — '{datos['nombre_serie']}' vs cronología"
        )
        dlg.exec()

    def _hacer_leyenda_clicable(self, grafico, curvas: dict):
        'Hace clicables los ítems de la leyenda para mostrar/ocultar cada\n        curva, como en los otros gráficos del programa. Al hacer clic en el\n        nombre, la curva se oculta/muestra y la etiqueta se atenúa.'
        return presentacion_cronologia._hacer_leyenda_clicable(self, grafico, curvas)

    def _pintar_cronologia(self):
        return presentacion_cronologia._pintar_cronologia(self)

    def _actualizar_info(self):
        return presentacion_cronologia._actualizar_info(self)
