"""Construcción de la interfaz de co-datación mediante acciones explícitas."""
from dataclasses import dataclass
from collections.abc import Callable
import sys
import pyqtgraph as pg
from modulo_widgets import _agregar_hover_anio, _crear_barra_zoom, SpinBoxFlechas, SeccionColapsable
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QSplitter, QSpinBox, QTableWidget, QHeaderView, QAbstractItemView, QComboBox, QCheckBox, QGroupBox, QApplication, QScrollArea, QFrame, QTabWidget, QPlainTextEdit, QTextBrowser
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt
import estilos_graficos as _gr
from dpi.ciencia.constantes import VENTANA_COFECHADO_DEFECTO
from dpi.ciencia.datacion import MAX_CORRECCION
TOOLTIP_STATS = (
    "<b>Estadísticos de cofechado:</b><br><br>"
    "<b>r (Pearson):</b> correlación lineal.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥0.50</span>: excelente<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥0.35</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥0.20</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;0.20</span>: pobre<br><br>"
    "<b>GLK:</b> % años con misma dirección. Asteriscos = significancia.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥0.70</span>: muy bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥0.65</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥0.60</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;0.60</span>: subóptimo<br><br>"
    "<b>t-BP (Baillie-Pilcher):</b> t-statistic sobre series filtradas.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥6.0</span>: excelente<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥4.0</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥3.0</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;3.0</span>: no significativo<br><br>"
    "<b>n:</b> años de overlap.<br><br>"
    "<i>Los tres altos = cofechado sólido.</i>"
)
ESTILO_BTN_COFECHA = (
    "QPushButton{background:transparent; padding:4px 10px; "
    "border:2px solid #888; border-radius:4px; font-weight:bold;}"
    "QPushButton:hover{border:2px solid #FF8C00;}"
    "QPushButton:checked{border:2px solid #FF8C00; background:#FF8C00; color:white;}"
)
from dpi.ui.series_util import ESTILO_CHK_COFECHA


@dataclass(frozen=True)
class AccionesCodatacion:
    _abrir_editor_anillos_marcada: Callable
    _aplicar_fuente_informe: Callable
    _configurar_modo_cofecha: Callable
    _descartar_prueba: Callable
    _guardar_pref_fuente: Callable
    _mostrar_eps_cronologia_activa: Callable
    _on_cofecha_aplicar_cambiado: Callable
    _on_modo_cofecha_toggled: Callable
    _on_mouse_movido: Callable
    _on_seleccion_sugerencia: Callable
    _redibujar_offset: Callable
    abrir_skeleton_plot: Callable
    analizar_offset: Callable
    aplicar_correccion_seleccionada: Callable
    buscar_errores: Callable
    cargar_archivos_rwl: Callable
    cargar_cronologias_externas: Callable
    cargar_series_referencia: Callable
    comparar_series_marcadas_vs_crono: Callable
    editar_anio_serie: Callable
    eliminar_series: Callable
    exportar_serie_codatada: Callable
    graficar_series: Callable
    mostrar_tabla_offset: Callable
    probar_correccion_seleccionada: Callable
    restaurar_original_sugerencias: Callable
    restaurar_serie: Callable
    simular_borrar: Callable
    simular_insertar: Callable
    toggle_seleccion: Callable
    verificar_datacion: Callable


@dataclass(frozen=True)
class ControlesCodatacion:
    _texto_hover: object
    _widget_izq_panel: object
    btn_aplicar: object
    btn_buscar: object
    btn_cargar_crono: object
    btn_cargar_rwl: object
    btn_cof_config: object
    btn_descartar_prueba: object
    btn_editar_anillos: object
    btn_eps_crono: object
    btn_grafico_barras: object
    btn_modo_cofecha: object
    btn_multi_vs_crono: object
    btn_probar: object
    btn_restablecer_sug: object
    btn_series_nulo: object
    btn_skeleton: object
    btn_toggle_sel: object
    btn_ver_cofechado: object
    btn_ver_tabla_off: object
    chk_cof_crono: object
    chk_cof_serie: object
    combo_anclaje: object
    combo_fuente_informe: object
    combo_metrica_offset: object
    grafico: object
    grafico_offset: object
    grafico_perfil: object
    lbl_estado_sug: object
    lbl_info_crono: object
    lbl_prueba: object
    lbl_stats: object
    lista_series: object
    sec_sug: object
    spin_edit_year: object
    spin_fuente_informe: object
    spin_max_corr: object
    spin_ventana: object
    tabla_sugerencias: object
    tabs_inferior: object
    txt_ayuda_perfil: object
    txt_informe: object


def construir_ui(parent, acciones):
    layout_principal = QHBoxLayout(parent)
    layout_principal.setContentsMargins(0, 0, 0, 0)

    splitter_principal = QSplitter(Qt.Orientation.Horizontal)

    # ═══════════════════════════════════════════════════════════════
    # PANEL IZQUIERDO: Scroll area con secciones colapsables
    # ═══════════════════════════════════════════════════════════════
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMinimumWidth(220)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    widget_izq = QWidget()
    # Guardamos referencia para poder ajustar su fondo según el tema
    # activo (el global de la app no estila QWidget genérico).
    _ui__widget_izq_panel = widget_izq
    panel_izq = QVBoxLayout(widget_izq)
    panel_izq.setContentsMargins(4, 4, 4, 4)
    panel_izq.setSpacing(6)

    # ── BLOQUE FIJO ARRIBA: Carga y gestión de series ──
    fila_carga = QHBoxLayout()
    _ui_btn_cargar_rwl = QPushButton("📂 Series")
    _ui_btn_cargar_rwl.setToolTip("Cargar series de medición")
    _ui_btn_cargar_rwl.clicked.connect(acciones.cargar_archivos_rwl)
    fila_carga.addWidget(_ui_btn_cargar_rwl)
    _ui_btn_cargar_crono = QPushButton("📚 Crono")
    _ui_btn_cargar_crono.setToolTip(
        "Cargar una cronología externa.\n"
        "Si el archivo trae varias series, se auto-genera la cronología.")
    _ui_btn_cargar_crono.setStyleSheet(
        "QPushButton{background-color:#6f42c1; color:white; font-weight:bold;}"
        "QPushButton:hover{background-color:#5a32a3;}")
    _ui_btn_cargar_crono.clicked.connect(acciones.cargar_cronologias_externas)
    fila_carga.addWidget(_ui_btn_cargar_crono)

    # Series solo para el contraste: no entran a la lista ni se cofechan.
    # Sirven cuando se tiene la cronología ya hecha y una sola serie por
    # cofechar, que es el caso donde el localizador se quedaba sin nulo.
    _ui_btn_series_nulo = QPushButton("📊 Referencia")
    _ui_btn_series_nulo.setToolTip(
        "Cargar series YA FECHADAS que sirvan solo de contraste.\n\n"
        "El localizador de quiebres decide si una corrección es real\n"
        "midiendo cuánto gana la misma búsqueda en series sin error.\n"
        "Con nueve o más, ese contraste pasa a ser el bueno.\n\n"
        "No aparecen en la lista ni se cofechan.\n"
        "Si ya cargaste series acá o construiste la cronología en su\n"
        "pestaña, esas se usan solas y este botón no hace falta.")
    _ui_btn_series_nulo.clicked.connect(acciones.cargar_series_referencia)
    fila_carga.addWidget(_ui_btn_series_nulo)
    panel_izq.addLayout(fila_carga)

    _ui_btn_toggle_sel = QPushButton("☑ Des / Seleccionar Todo")
    _ui_btn_toggle_sel.clicked.connect(acciones.toggle_seleccion)
    panel_izq.addWidget(_ui_btn_toggle_sel)

    panel_izq.addWidget(QLabel("Series en Memoria:"))
    _ui_lista_series = QListWidget()
    _ui_lista_series.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection)
    _ui_lista_series.setMinimumHeight(120)
    _ui_lista_series.itemChanged.connect(acciones.graficar_series)
    panel_izq.addWidget(_ui_lista_series)

    QShortcut(QKeySequence(Qt.Key.Key_Delete), _ui_lista_series).activated.connect(acciones.eliminar_series)
    QShortcut(QKeySequence(Qt.Key.Key_Backspace), _ui_lista_series).activated.connect(acciones.eliminar_series)

    fila_btns = QHBoxLayout()
    btn_elim = QPushButton("🗑️ Eliminar")
    btn_elim.setStyleSheet("background-color: #d9534f; color: white;")
    btn_elim.clicked.connect(acciones.eliminar_series)
    fila_btns.addWidget(btn_elim)
    btn_anio = QPushButton("📅 Editar Año Base")
    btn_anio.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold;")
    btn_anio.clicked.connect(acciones.editar_anio_serie)
    fila_btns.addWidget(btn_anio)
    panel_izq.addLayout(fila_btns)

    btn_exp = QPushButton("💾 Exportar Seleccionada")
    btn_exp.clicked.connect(acciones.exportar_serie_codatada)
    panel_izq.addWidget(btn_exp)

    # Botón directo de comparación múltiple vs cronología activa.
    # Permite al usuario marcar varias series en la lista y compararlas
    # contra la cronología ya cargada sin tener que abrir la ventana
    # de cronología por separado. La cronología activa se mantiene
    # entre llamadas (en `_cronologia_para_comparacion`), así que
    # típicamente: cargo cronología una vez → comparo decenas de
    # series con dos clics.
    _ui_btn_multi_vs_crono = QPushButton("📊 Series múltiples vs Crono")
    _ui_btn_multi_vs_crono.setStyleSheet(
        "QPushButton{background-color:#8e44ad; color:white; "
        "font-weight:bold; padding:5px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#9b59b6;}"
        "QPushButton:disabled{background-color:#555; color:#aaa;}"
    )
    _ui_btn_multi_vs_crono.setToolTip(
        "Comparar las series marcadas contra una cronología.\n"
        "• Si todavía no hay cronología cargada, se pedirá elegir un archivo .rwl\n"
        "• Si ya hay una cargada, se reutiliza automáticamente\n"
        "• Funciona con 1 o más series marcadas\n"
        "• Resultados en tabla resumen con r, GLK, t-BP y puntaje compuesto")
    _ui_btn_multi_vs_crono.clicked.connect(acciones.comparar_series_marcadas_vs_crono)
    panel_izq.addWidget(_ui_btn_multi_vs_crono)

    _ui_btn_skeleton = QPushButton("📊 Skeleton plot — cofechado visual")
    _ui_btn_skeleton.setStyleSheet(
        "QPushButton{background-color:#6f42c1; color:white; "
        "font-weight:bold; padding:8px; font-size:13px; border-radius:4px;}"
        "QPushButton:hover{background-color:#8250d6;}")
    _ui_btn_skeleton.setToolTip(
        "Cofechado visual: referencia arriba, serie flotante abajo,\n"
        "deslizable año a año para ver dónde calzan los anillos.\n\n"
        "Marca DOS series: la cronología (📚) o la primera será la\n"
        "referencia; la otra será la flotante.")
    _ui_btn_skeleton.clicked.connect(acciones.abrir_skeleton_plot)
    panel_izq.addWidget(_ui_btn_skeleton)

    # Botón para editar anillos (insertar/eliminar conservando el ancho)
    # de la serie marcada, accesible directamente desde el panel.
    _ui_btn_editar_anillos = QPushButton("✏️ Editar anillos de serie marcada")
    _ui_btn_editar_anillos.setStyleSheet(
        "QPushButton{background-color:#8e44ad; color:white; "
        "font-weight:bold; padding:5px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#9b59b6;}"
        "QPushButton:disabled{background-color:#555; color:#aaa;}")
    _ui_btn_editar_anillos.setToolTip(
        "Abre el editor de anillos (insertar/eliminar conservando el "
        "ancho total) para la serie marcada con check.\n"
        "Marca exactamente UNA serie.")
    _ui_btn_editar_anillos.clicked.connect(acciones._abrir_editor_anillos_marcada)
    panel_izq.addWidget(_ui_btn_editar_anillos)

    # ── Modo COFECHA (control global del cofechado) ──
    # Va aquí, a nivel del panel (no dentro de una sección colapsable),
    # porque gobierna TODAS las correlaciones del módulo: con él el
    # usuario decide si las series/cronologías se estandarizan o se usan
    # tal cual. Por eso debe estar siempre visible, justo bajo el botón
    # de comparación múltiple.
    grp_cof = QGroupBox("Modo COFECHA")
    grp_cof.setStyleSheet(
        "QGroupBox{border:1px solid #555; border-radius:4px; "
        "margin-top:6px; padding-top:4px;}"
        "QGroupBox::title{subcontrol-origin:margin; left:8px; padding:0 3px;}"
    )
    layout_cof = QVBoxLayout(grp_cof)
    layout_cof.setSpacing(4)
    layout_cof.setContentsMargins(6, 4, 6, 6)

    _ui_btn_modo_cofecha = QPushButton("🎯 Activar Modo COFECHA")
    _ui_btn_modo_cofecha.setCheckable(True)
    _ui_btn_modo_cofecha.setStyleSheet(ESTILO_BTN_COFECHA)
    _ui_btn_modo_cofecha.setToolTip(
        "Activa transformaciones tipo COFECHA (spline + log + AR(1))\n"
        "con los parámetros configurados (botón ⚙ al lado para ajustar).\n"
        "Al activarlo, el gráfico muestra las series transformadas y\n"
        "todas las correlaciones usan esa estandarización."
    )
    _ui_btn_modo_cofecha.toggled.connect(acciones._on_modo_cofecha_toggled)

    _ui_btn_cof_config = QPushButton("⚙")
    _ui_btn_cof_config.setMaximumWidth(34)
    _ui_btn_cof_config.setToolTip(
        "Configurar parámetros del Modo COFECHA\n"
        "(rigidez del spline, log, AR(1), primeras diferencias)"
    )
    _ui_btn_cof_config.setStyleSheet(
        "QPushButton{padding:4px 8px; font-size:14px; font-weight:bold; "
        "border:2px solid #888; border-radius:4px; "
        "background:transparent;}"
        "QPushButton:hover{border-color:#FF8C00; color:#FF8C00;}"
    )
    _ui_btn_cof_config.clicked.connect(acciones._configurar_modo_cofecha)

    fila_cof_btn = QHBoxLayout()
    fila_cof_btn.addWidget(_ui_btn_modo_cofecha, 1)
    fila_cof_btn.addWidget(_ui_btn_cof_config)
    layout_cof.addLayout(fila_cof_btn)

    fila_aplicar = QHBoxLayout()
    lbl_aplicar = QLabel("Aplicar a:")
    lbl_aplicar.setStyleSheet("font-size:11px;")
    fila_aplicar.addWidget(lbl_aplicar)
    _ui_chk_cof_serie = QCheckBox("Serie")
    _ui_chk_cof_serie.setChecked(True)
    _ui_chk_cof_serie.setStyleSheet(ESTILO_CHK_COFECHA)
    _ui_chk_cof_serie.setToolTip(
        "Estandariza la SERIE a datar con el mismo método de la\n"
        "cronología activa, para que ambas queden en el mismo espacio\n"
        "y la correlación sea válida.\n\n"
        "Desactívalo solo si subiste la serie YA estandarizada."
    )
    _ui_chk_cof_serie.toggled.connect(acciones._on_cofecha_aplicar_cambiado)
    fila_aplicar.addWidget(_ui_chk_cof_serie)
    _ui_chk_cof_crono = QCheckBox("Cronología")
    _ui_chk_cof_crono.setChecked(False)
    _ui_chk_cof_crono.setStyleSheet(ESTILO_CHK_COFECHA)
    _ui_chk_cof_crono.setToolTip(
        "Normalmente NO se activa: una cronología generada con el botón\n"
        "Crono (o exportada por DPI/ARSTAN) ya viene estandarizada, y\n"
        "volver a aplicarle spline + log + AR la daña y hace caer la\n"
        "correlación.\n\n"
        "Actívalo solo si la cronología cargada NO está estandarizada\n"
        "(por ejemplo, una cronología de anchos crudos en mm)."
    )
    _ui_chk_cof_crono.toggled.connect(acciones._on_cofecha_aplicar_cambiado)
    fila_aplicar.addWidget(_ui_chk_cof_crono)
    fila_aplicar.addStretch()
    # Esta fila DEBE agregarse al layout del grupo. Al retirar la casilla
    # de leave-one-out se perdió esta línea y las casillas quedaron
    # creadas pero fuera de todo layout, o sea invisibles.
    layout_cof.addLayout(fila_aplicar)
    panel_izq.addWidget(grp_cof)

    # ── SECCIÓN COLAPSABLE: Cronología ──
    # Todas las secciones inician COLAPSADAS para no abrumar al usuario
    # con un panel sobrecargado de botones al abrir el programa. El
    # usuario expande la sección que necesita en cada momento.
    # ── Sección "Cronología" ELIMINADA de esta pestaña ──
    # La generación y gestión de cronologías vive en su propia pestaña,
    # así que aquí no aporta. Se conservan estos dos widgets OCULTOS (no
    # se agregan a ningún layout) solo para que set_cronologia_activa
    # pueda seguir actualizando el indicador y el estado de EPS sin
    # romperse.
    _ui_lbl_info_crono = QLabel("", parent)
    _ui_lbl_info_crono.setVisible(False)
    _ui_btn_eps_crono = QPushButton(parent)
    _ui_btn_eps_crono.setVisible(False)
    _ui_btn_eps_crono.setEnabled(False)
    _ui_btn_eps_crono.clicked.connect(acciones._mostrar_eps_cronologia_activa)

    # ── SECCIÓN COLAPSABLE: Cofechado con año conocido ──
    sec_conocido = SeccionColapsable(
        "📊 Cofechado con Año Conocido", expandida=False)

    # Parámetros del motor (compactos lado a lado)
    fila_params = QHBoxLayout()
    fila_params.addWidget(QLabel("Ventana:"))
    _ui_spin_ventana = SpinBoxFlechas()
    _ui_spin_ventana.setRange(10, 200)
    _ui_spin_ventana.setValue(VENTANA_COFECHADO_DEFECTO)
    _ui_spin_ventana.setSingleStep(10)
    _ui_spin_ventana.setSuffix(" años")
    fila_params.addWidget(_ui_spin_ventana)
    fila_params.addWidget(QLabel("Máx corr:"))
    _ui_spin_max_corr = SpinBoxFlechas()
    _ui_spin_max_corr.setRange(1, 10)
    _ui_spin_max_corr.setValue(MAX_CORRECCION)
    fila_params.addWidget(_ui_spin_max_corr)
    sec_conocido.agregar_layout(fila_params)

    # Anclaje: qué extremo de la serie queda fijo al insertar/eliminar
    # un anillo. Para árboles vivos fechados desde la corteza (el caso
    # normal) debe quedar fija la CORTEZA: así, al insertar el anillo que
    # falta, la serie sigue terminando en el mismo año y se corrige todo
    # lo anterior. Con médula fija la serie se corría hacia el presente y
    # el buscador proponía años equivocados.
    fila_ancla = QHBoxLayout()
    fila_ancla.addWidget(QLabel("Anclar en:"))
    _ui_combo_anclaje = QComboBox()
    _ui_combo_anclaje.addItem("Corteza (último año fijo)", "corteza")
    _ui_combo_anclaje.addItem("Médula (primer año fijo)", "medula")
    _ui_combo_anclaje.setToolTip(
        "Qué extremo de la serie NO se mueve al insertar o eliminar un anillo.\n\n"
        "• Corteza: el último año queda fijo y se desplazan los años anteriores.\n"
        "  Es lo correcto en árboles vivos, donde el año del anillo externo se\n"
        "  conoce con certeza. Si falta un anillo en 2023, al insertarlo la serie\n"
        "  sigue terminando en 2024 y todo lo anterior retrocede un año.\n\n"
        "• Médula: el primer año queda fijo y se desplazan los posteriores.\n"
        "  Para series flotantes o fechadas desde la médula."
    )
    fila_ancla.addWidget(_ui_combo_anclaje, 1)
    sec_conocido.agregar_layout(fila_ancla)

    _ui_btn_ver_cofechado = QPushButton("📊 Ver Cofechado Actual")
    _ui_btn_ver_cofechado.setStyleSheet("background-color: #5bc0de; color: white;")
    _ui_btn_ver_cofechado.clicked.connect(acciones.verificar_datacion)
    sec_conocido.agregar_widget(_ui_btn_ver_cofechado)

    _ui_btn_buscar = QPushButton("🔎 Buscar Anillos Faltantes/Sobrantes")
    _ui_btn_buscar.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold;")
    _ui_btn_buscar.clicked.connect(acciones.buscar_errores)
    sec_conocido.agregar_widget(_ui_btn_buscar)

    panel_izq.addWidget(sec_conocido)

    # ── SECCIÓN COLAPSABLE: Cofechado serie flotante ──
    sec_flotante = SeccionColapsable(
        "🔍 Cofechado Serie Flotante", expandida=False)

    btn_off = QPushButton("🔍 Analizar Serie Flotante")
    btn_off.setStyleSheet("background-color: #5bc0de; color: white;")
    btn_off.clicked.connect(acciones.analizar_offset)
    sec_flotante.agregar_widget(btn_off)

    _ui_btn_ver_tabla_off = QPushButton("📊 Ver tabla de desfases")
    _ui_btn_ver_tabla_off.setEnabled(False)
    _ui_btn_ver_tabla_off.clicked.connect(acciones.mostrar_tabla_offset)
    sec_flotante.agregar_widget(_ui_btn_ver_tabla_off)

    # Métrica al final, label arriba y combo a todo el ancho
    lbl_met = QLabel("📐 Métrica del gráfico:")
    lbl_met.setStyleSheet("font-size: 11px; padding-top: 4px;")
    sec_flotante.agregar_widget(lbl_met)
    _ui_combo_metrica_offset = QComboBox()
    _ui_combo_metrica_offset.addItems([
        "🎯 Compuesto (las tres juntas)",
        "t-BP (Baillie-Pilcher)",
        "r (Pearson)",
        "GLK (Eckstein)",
    ])
    _ui_combo_metrica_offset.setToolTip(
        "Métrica del gráfico de barras de desfase.\n\n"
        "🎯 Compuesto: media geométrica de las tres métricas.\n"
        "    La fecha verdadera tiene puntaje alto SOLO cuando\n"
        "    las tres son altas simultáneamente.\n\n"
        "t-BP: pondera r por tamaño de muestra.\n"
        "r: engañoso solo — puede dar máximos azarosos.\n"
        "GLK: robusto pero menos sensible que t-BP."
    )
    _ui_combo_metrica_offset.currentTextChanged.connect(acciones._redibujar_offset)
    sec_flotante.agregar_widget(_ui_combo_metrica_offset)

    panel_izq.addWidget(sec_flotante)

    # ── SECCIÓN COLAPSABLE: Sugerencias ──
    _ui_sec_sug = SeccionColapsable("💡 Sugerencias", expandida=False)

    _ui_lbl_estado_sug = QLabel("")
    _ui_lbl_estado_sug.setWordWrap(True)
    _ui_lbl_estado_sug.setTextFormat(Qt.TextFormat.RichText)
    _ui_lbl_estado_sug.setStyleSheet(
        "QLabel{font-size:10px; padding:4px 6px; "
        "background-color: rgba(0,0,0,30); border-radius:3px;}")
    _ui_lbl_estado_sug.setVisible(False)
    _ui_sec_sug.agregar_widget(_ui_lbl_estado_sug)

    _ui_tabla_sugerencias = QTableWidget(0, 5)
    # Selección de FILA COMPLETA, con un color que se ve por encima del
    # fondo con que se marcan las filas según su origen. Sin esto, al
    # moverse con las flechas no se distinguía dónde estaba el cursor.
    _ui_tabla_sugerencias.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows)
    _ui_tabla_sugerencias.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection)
    _ui_tabla_sugerencias.setStyleSheet(
        "QTableWidget::item:selected{background-color:#2d6ea8;"
        " color:#ffffff;}")
    _ui_tabla_sugerencias.setHorizontalHeaderLabels(
        ["Año", "Tipo", "r antes", "r tras", "Δr"])
    _ui_tabla_sugerencias.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch)
    _ui_tabla_sugerencias.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows)
    _ui_tabla_sugerencias.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection)
    _ui_tabla_sugerencias.itemSelectionChanged.connect(
        acciones._on_seleccion_sugerencia)
    _ui_tabla_sugerencias.setMaximumHeight(200)
    _ui_tabla_sugerencias.setMinimumHeight(120)
    _ui_sec_sug.agregar_widget(_ui_tabla_sugerencias)

    # Indicador de prueba en curso
    _ui_lbl_prueba = QLabel("")
    _ui_lbl_prueba.setWordWrap(True)
    _ui_lbl_prueba.setTextFormat(Qt.TextFormat.RichText)
    _ui_lbl_prueba.setStyleSheet(
        "QLabel{font-size:11px; padding:4px 6px; color:#e67e22; "
        "font-weight:bold;}")
    _ui_lbl_prueba.setVisible(False)
    _ui_sec_sug.agregar_widget(_ui_lbl_prueba)

    # Paso 1: probar la corrección (sin tocar la serie real)
    _ui_btn_probar = QPushButton("🧪 Probar corrección seleccionada")
    _ui_btn_probar.setStyleSheet(
        "background-color:#5bc0de; color:white; font-weight:bold;")
    _ui_btn_probar.setToolTip(
        "Aplica la corrección de forma temporal para ver cómo queda la\n"
        "correlación, SIN modificar todavía la serie real.")
    _ui_btn_probar.setEnabled(False)
    _ui_btn_probar.clicked.connect(acciones.probar_correccion_seleccionada)
    _ui_sec_sug.agregar_widget(_ui_btn_probar)

    # Paso 2: aplicar a la serie real (con confirmación de qué cambia)
    _ui_btn_aplicar = QPushButton("✅ Aplicar a serie real")
    _ui_btn_aplicar.setStyleSheet(
        "background-color: #5cb85c; color: white; font-weight: bold;")
    _ui_btn_aplicar.setEnabled(False)
    _ui_btn_aplicar.setToolTip(
        "Confirma qué datos se modifican y guarda el cambio en la serie "
        "real.")
    _ui_btn_aplicar.clicked.connect(acciones.aplicar_correccion_seleccionada)
    _ui_sec_sug.agregar_widget(_ui_btn_aplicar)

    # Descartar la prueba (revierte a como estaba)
    _ui_btn_descartar_prueba = QPushButton("↺ Descartar prueba")
    _ui_btn_descartar_prueba.setStyleSheet(
        "QPushButton{background-color:#6c757d; color:white; padding:4px;}"
        "QPushButton:hover{background-color:#7d868e;}")
    _ui_btn_descartar_prueba.setEnabled(False)
    _ui_btn_descartar_prueba.clicked.connect(acciones._descartar_prueba)
    _ui_sec_sug.agregar_widget(_ui_btn_descartar_prueba)

    # Botón para restablecer la serie corregida a sus valores originales,
    # disponible aquí (no solo en el simulador manual).
    _ui_btn_restablecer_sug = QPushButton("🔄 Restablecer valores originales")
    _ui_btn_restablecer_sug.setStyleSheet(
        "QPushButton{background-color:#6c757d; color:white; "
        "padding:4px;}"
        "QPushButton:hover{background-color:#7d868e;}")
    _ui_btn_restablecer_sug.clicked.connect(acciones.restaurar_original_sugerencias)
    _ui_sec_sug.agregar_widget(_ui_btn_restablecer_sug)
    panel_izq.addWidget(_ui_sec_sug)

    # ── SECCIÓN COLAPSABLE: Simulador manual ──
    # Va al final porque se usa poco; las correcciones normales se hacen
    # desde Sugerencias (que abre el editor con conservación de ancho).
    sec_sim = SeccionColapsable("📝 Simulador Manual", expandida=False)
    fila = QHBoxLayout()
    fila.addWidget(QLabel("Año:"))
    _ui_spin_edit_year = SpinBoxFlechas()
    _ui_spin_edit_year.setRange(-10000, 5000)
    _ui_spin_edit_year.setValue(1900)
    fila.addWidget(_ui_spin_edit_year)
    sec_sim.agregar_layout(fila)

    fila2 = QHBoxLayout()
    btn_ins = QPushButton("➕ Insertar")
    btn_ins.setStyleSheet("background-color: #5bc0de; color: white;")
    btn_ins.clicked.connect(acciones.simular_insertar)
    fila2.addWidget(btn_ins)
    btn_del = QPushButton("➖ Borrar")
    btn_del.setStyleSheet("background-color: #d9534f; color: white;")
    btn_del.clicked.connect(acciones.simular_borrar)
    fila2.addWidget(btn_del)
    sec_sim.agregar_layout(fila2)
    btn_rst = QPushButton("🔄 Restaurar Original")
    btn_rst.clicked.connect(acciones.restaurar_serie)
    sec_sim.agregar_widget(btn_rst)
    panel_izq.addWidget(sec_sim)

    panel_izq.addStretch()
    scroll.setWidget(widget_izq)

    # ═══════════════════════════════════════════════════════════════
    # PANEL DERECHO: Gráficos
    # ═══════════════════════════════════════════════════════════════
    splitter_der = QSplitter(Qt.Orientation.Vertical)

    _ui_grafico = pg.PlotWidget(title="Series de Ancho de Anillo")
    _agregar_hover_anio(_ui_grafico)
    _ui_grafico.showGrid(x=True, y=True, alpha=0.3)
    _ui_grafico.addLegend()
    _gr.aplicar_a_pyqtgraph(_ui_grafico)
    _cont_grafico = QWidget()
    _lay_grafico = QVBoxLayout(_cont_grafico)
    _lay_grafico.setContentsMargins(0, 0, 0, 0)
    _lay_grafico.setSpacing(2)
    _lay_grafico.addWidget(_ui_grafico, 1)

    # Fila de controles del gráfico: zoom + selector de tipo de gráfico.
    _fila_ctrl_graf = QHBoxLayout()
    _fila_ctrl_graf.setContentsMargins(0, 0, 0, 0)
    _fila_ctrl_graf.setSpacing(6)
    _barra_sup = _crear_barra_zoom(_ui_grafico, nombre_exportar="series")
    _fila_ctrl_graf.addWidget(_barra_sup)

    # Modo barras: dibuja cada serie como barras que salen de su MEDIA
    # (hacia arriba si el año fue de crecimiento sobre la media, hacia
    # abajo si fue bajo la media). Es la vista clásica de desviaciones,
    # muy útil para ver años característicos y comparar con COFECHA.
    _ui_btn_grafico_barras = QPushButton("📊 Barras")
    _ui_btn_grafico_barras.setCheckable(True)
    _ui_btn_grafico_barras.setToolTip(
        "Alterna entre gráfico de LÍNEAS y gráfico de BARRAS.\n\n"
        "En modo barras, la MEDIA de cada serie es el eje central:\n"
        "las barras suben sobre la media (años buenos, verde) y bajan\n"
        "bajo la media (años malos, rojo). Con varias series marcadas,\n"
        "las barras se dibujan lado a lado por año."
    )
    _ui_btn_grafico_barras.toggled.connect(acciones.graficar_series)

    # El botón de barras va junto a «Ver todo», que es donde se
    # esperan los controles de ESTE gráfico. La fila que ocupaba antes
    # queda libre para los controles de los gráficos de abajo.
    _barra_sup.layout().insertWidget(
        _barra_sup.layout().count() - 1, _ui_btn_grafico_barras)
    _fila_ctrl_graf.addStretch()

    _cont_ctrl_graf = QWidget()
    _cont_ctrl_graf.setLayout(_fila_ctrl_graf)
    _lay_grafico.addWidget(_cont_ctrl_graf)
    splitter_der.addWidget(_cont_grafico)

    contenedor_offset = QWidget()
    layout_offset = QVBoxLayout(contenedor_offset)
    layout_offset.setContentsMargins(0, 0, 0, 0)
    layout_offset.setSpacing(2)

    _ui_grafico_offset = pg.PlotWidget(
        title="Correlación móvil (r) entre la serie y la referencia, por ventana")
    _ui_grafico_offset.showGrid(x=True, y=True, alpha=0.3)
    _ui_grafico_offset.setYRange(-1.05, 1.05)
    _ui_grafico_offset.setLabel("left", "r (correlación por ventana)")
    _ui_grafico_offset.setLabel("bottom", "Año (centro de la ventana)")
    _ui_grafico_offset.addLegend(offset=(10, 10))
    _ui__texto_hover = pg.TextItem(fill=(40, 40, 40, 220), color=(255, 255, 255))
    _ui__texto_hover.hide()
    _ui_grafico_offset.addItem(_ui__texto_hover)
    _ui_grafico_offset.scene().sigMouseMoved.connect(acciones._on_mouse_movido)
    _agregar_hover_anio(_ui_grafico_offset)
    layout_offset.addWidget(_ui_grafico_offset, 1)
    # Controles de zoom propios de ESTA pestaña: cada gráfico de abajo se
    # maneja por su cuenta, así se puede dejar uno encuadrado en un tramo
    # mientras se explora el otro.
    layout_offset.addWidget(_crear_barra_zoom(_ui_grafico_offset))

    _ui_lbl_stats = QLabel("")
    _ui_lbl_stats.setWordWrap(False)
    _ui_lbl_stats.setTextFormat(Qt.TextFormat.RichText)
    _ui_lbl_stats.setMinimumHeight(38)
    # Fondo oscuro fijo: este label es un overlay sobre el gráfico
    # de pyqtgraph (que es negro siempre), y el HTML interno usa
    # colores #888/#aaa/etc que requieren fondo oscuro para verse.
    _ui_lbl_stats.setStyleSheet(
        "QLabel{background-color:#1a1a1a; color:#e0e0e0; "
        "border:1px solid #444; border-radius:4px; padding:8px 12px;}"
    )
    _ui_lbl_stats.setAlignment(Qt.AlignmentFlag.AlignVCenter |
                                Qt.AlignmentFlag.AlignLeft)
    _ui_lbl_stats.setToolTip(TOOLTIP_STATS)
    _ui_lbl_stats.setVisible(False)
    layout_offset.addWidget(_ui_lbl_stats)

    # ── Panel inferior con pestañas ────────────────────────────────
    # Antes este panel mostraba solo la correlación móvil. El informe de
    # co-datación y el perfil del quiebre se calculaban pero no se veían
    # en ninguna parte: la explicación en prosa y el gráfico que muestra
    # si el año está determinado o es una meseta quedaban dentro de la
    # estructura de datos, invisibles. Van acá, junto al gráfico que ya
    # había, para que el usuario alterne entre los tres sin perder nada.
    _ui_tabs_inferior = QTabWidget()
    _ui_tabs_inferior.addTab(contenedor_offset, "Correlación móvil")

    _ui_txt_informe = QPlainTextEdit()
    _ui_txt_informe.setReadOnly(True)
    _ui_txt_informe.setPlaceholderText(
        "Acá aparece el informe de co-datación cuando se busca una "
        "corrección:\n\n"
        "  · qué tramo de la serie correlaciona bien y con qué r\n"
        "  · dónde baja la correlación\n"
        "  · cuántos anillos faltan o sobran, y entre qué años\n"
        "  · los años concretos que conviene revisar bajo la lupa")
    _ui_txt_informe.setStyleSheet(
        "QPlainTextEdit{background-color:#1a1a1a; color:#e0e0e0;"
        " border:1px solid #444; padding:8px;}")
    f_inf = QFont("Consolas" if sys.platform.startswith("win")
                  else "Monospace")
    f_inf.setStyleHint(QFont.StyleHint.TypeWriter)
    f_inf.setPointSize(10)
    _ui_txt_informe.setFont(f_inf)

    # Controles de letra: no todo el mundo lee cómodo el mismo cuerpo, y
    # la monoespaciada alinea las tablas pero cansa en prosa larga.
    _cont_inf = QWidget()
    _lay_inf = QVBoxLayout(_cont_inf)
    _lay_inf.setContentsMargins(0, 0, 0, 0)
    _lay_inf.setSpacing(2)
    _lay_inf.addWidget(_ui_txt_informe, 1)

    _fila_letra = QHBoxLayout()
    _fila_letra.setContentsMargins(4, 0, 4, 0)
    _fila_letra.addWidget(QLabel("Letra:"))
    _ui_combo_fuente_informe = QComboBox()
    for etq, fam in (("Monoespaciada", "__mono__"),
                     ("Garamond", "Garamond"),
                     ("Arial", "Arial"),
                     ("Verdana", "Verdana"),
                     ("Georgia", "Georgia"),
                     ("Times New Roman", "Times New Roman")):
        _ui_combo_fuente_informe.addItem(etq, fam)
    _ui_combo_fuente_informe.setToolTip(
        "La monoespaciada mantiene alineadas las tablas del informe.\n"
        "Las demás se leen mejor en la prosa, pero descuadran columnas.")
    _ui_combo_fuente_informe.currentIndexChanged.connect(
        acciones._aplicar_fuente_informe)
    _ui_combo_fuente_informe.currentIndexChanged.connect(
        acciones._guardar_pref_fuente)
    _fila_letra.addWidget(_ui_combo_fuente_informe)

    _fila_letra.addWidget(QLabel("Tamaño:"))
    _ui_spin_fuente_informe = QSpinBox()
    _ui_spin_fuente_informe.setRange(7, 24)
    _ui_spin_fuente_informe.setValue(10)
    _ui_spin_fuente_informe.setSuffix(" pt")
    _ui_spin_fuente_informe.valueChanged.connect(
        acciones._aplicar_fuente_informe)
    _ui_spin_fuente_informe.valueChanged.connect(
        acciones._guardar_pref_fuente)
    _fila_letra.addWidget(_ui_spin_fuente_informe)

    btn_copiar_inf = QPushButton("Copiar")
    btn_copiar_inf.setToolTip("Copia el informe completo al portapapeles.")
    btn_copiar_inf.clicked.connect(
        lambda: QApplication.clipboard().setText(
            _ui_txt_informe.toPlainText()))
    _fila_letra.addWidget(btn_copiar_inf)
    _fila_letra.addStretch()

    _cw = QWidget()
    _cw.setLayout(_fila_letra)
    _lay_inf.addWidget(_cw)
    _ui_tabs_inferior.addTab(_cont_inf, "Informe")

    _ui_grafico_perfil = pg.PlotWidget(
        title="¿En qué año se rompe el fechado? "
              "Correlación de la serie completa si el error estuviera "
              "en cada año")
    _ui_grafico_perfil.showGrid(x=True, y=True, alpha=0.3)
    _ui_grafico_perfil.setLabel(
        "left", "r de TODA la serie si el error estuviera en ese año")
    _ui_grafico_perfil.setLabel(
        "bottom", "Año donde se probó poner el error")
    _ui_grafico_perfil.addLegend(offset=(10, 10))
    _agregar_hover_anio(_ui_grafico_perfil)
    _cont_perfil = QWidget()
    _lay_perfil = QVBoxLayout(_cont_perfil)
    _lay_perfil.setContentsMargins(0, 0, 0, 0)
    _lay_perfil.setSpacing(2)

    # Gráfico y explicación lado a lado, con divisor movible: el perfil no
    # se entiende solo mirándolo, y una leyenda no alcanza para explicar
    # que cada punto es un experimento distinto de datación.
    _div_perfil = QSplitter(Qt.Orientation.Horizontal)
    _div_perfil.addWidget(_ui_grafico_perfil)

    _ui_txt_ayuda_perfil = QTextBrowser()
    _ui_txt_ayuda_perfil.setOpenExternalLinks(False)
    _ui_txt_ayuda_perfil.setHtml(
        "<div style='font-size:12px; line-height:1.35;'>"
        "<b>Qué estás viendo</b><br>"
        "Cada punto del gráfico es un <i>experimento</i>: el programa "
        "supone que el error de fechado está en ese año, aplica la "
        "corrección, y mide cómo queda <b>la serie completa</b>.<br><br>"
        "No es la correlación de un tramo. Es la de toda la serie, "
        "partida en ese año.<br><br>"
        "<b>Cómo se lee la forma</b><br>"
        "<span style='color:#5cb85c;'>▲ Pico angosto</span> — un solo año "
        "funciona. El fechado está determinado.<br>"
        "<span style='color:#e0a030;'>▬ Meseta ancha</span> — muchos años "
        "funcionan igual de bien. Elegir uno sería falsa precisión: hay "
        "que revisar todos los candidatos.<br>"
        "<span style='color:#d9534f;'>▼ Todo bajo</span> — si el mejor "
        "pico no llega a 0,3, ninguna corrección arregla esta serie. El "
        "problema es otro.<br><br>"
        "<b>Los colores</b><br>"
        "<span style='color:#4aa3dc;'>━ Curva azul</span>: la correlación "
        "de cada hipótesis.<br>"
        "<span style='color:#4aa3dc;'>▨ Franja azul</span>: la zona "
        "compatible, los años que no se distinguen del mejor.<br>"
        "<span style='color:#e04040;'>┃ Línea roja</span>: el año más "
        "probable.<br>"
        "<span style='color:#e0a030;'>┆ Punteadas</span>: los otros años "
        "a revisar, ordenados por lo estrecho que es ese anillo en la "
        "cronología.<br><br>"
        "<b>Ojo</b><br>"
        "La altura del pico dice si vale la pena; el ancho dice cuánta "
        "confianza tienes en el año. Son dos cosas distintas."
        "</div>")
    _ui_txt_ayuda_perfil.setStyleSheet(
        "QTextBrowser{background-color:#1a1a1a; color:#d8d8d8;"
        " border:1px solid #444; padding:8px;}")
    _div_perfil.addWidget(_ui_txt_ayuda_perfil)
    _div_perfil.setStretchFactor(0, 3)
    _div_perfil.setStretchFactor(1, 1)
    _div_perfil.setSizes([700, 260])
    _lay_perfil.addWidget(_div_perfil, 1)
    _lay_perfil.addWidget(_crear_barra_zoom(_ui_grafico_perfil))
    _ui_tabs_inferior.addTab(_cont_perfil, "Perfil del quiebre")

    splitter_der.addWidget(_ui_tabs_inferior)

    splitter_principal.addWidget(scroll)
    splitter_principal.addWidget(splitter_der)
    splitter_principal.setStretchFactor(0, 1)
    splitter_principal.setStretchFactor(1, 4)
    splitter_principal.setSizes([280, 1120])
    layout_principal.addWidget(splitter_principal)
    return ControlesCodatacion(
        _texto_hover=_ui__texto_hover,
        _widget_izq_panel=_ui__widget_izq_panel,
        btn_aplicar=_ui_btn_aplicar,
        btn_buscar=_ui_btn_buscar,
        btn_cargar_crono=_ui_btn_cargar_crono,
        btn_cargar_rwl=_ui_btn_cargar_rwl,
        btn_cof_config=_ui_btn_cof_config,
        btn_descartar_prueba=_ui_btn_descartar_prueba,
        btn_editar_anillos=_ui_btn_editar_anillos,
        btn_eps_crono=_ui_btn_eps_crono,
        btn_grafico_barras=_ui_btn_grafico_barras,
        btn_modo_cofecha=_ui_btn_modo_cofecha,
        btn_multi_vs_crono=_ui_btn_multi_vs_crono,
        btn_probar=_ui_btn_probar,
        btn_restablecer_sug=_ui_btn_restablecer_sug,
        btn_series_nulo=_ui_btn_series_nulo,
        btn_skeleton=_ui_btn_skeleton,
        btn_toggle_sel=_ui_btn_toggle_sel,
        btn_ver_cofechado=_ui_btn_ver_cofechado,
        btn_ver_tabla_off=_ui_btn_ver_tabla_off,
        chk_cof_crono=_ui_chk_cof_crono,
        chk_cof_serie=_ui_chk_cof_serie,
        combo_anclaje=_ui_combo_anclaje,
        combo_fuente_informe=_ui_combo_fuente_informe,
        combo_metrica_offset=_ui_combo_metrica_offset,
        grafico=_ui_grafico,
        grafico_offset=_ui_grafico_offset,
        grafico_perfil=_ui_grafico_perfil,
        lbl_estado_sug=_ui_lbl_estado_sug,
        lbl_info_crono=_ui_lbl_info_crono,
        lbl_prueba=_ui_lbl_prueba,
        lbl_stats=_ui_lbl_stats,
        lista_series=_ui_lista_series,
        sec_sug=_ui_sec_sug,
        spin_edit_year=_ui_spin_edit_year,
        spin_fuente_informe=_ui_spin_fuente_informe,
        spin_max_corr=_ui_spin_max_corr,
        spin_ventana=_ui_spin_ventana,
        tabla_sugerencias=_ui_tabla_sugerencias,
        tabs_inferior=_ui_tabs_inferior,
        txt_ayuda_perfil=_ui_txt_ayuda_perfil,
        txt_informe=_ui_txt_informe,
    )
