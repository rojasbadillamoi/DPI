"""Construcción de componentes de medición mediante acciones explícitas."""
from dataclasses import dataclass
from collections.abc import Callable
from modulo_widgets import crear_boton
from modulo_grafico_medicion_ui import GraficoMedicion
from modulo_widgets import crear_selector
import dpi.ciencia.transformacion as _tr
import pyqtgraph as pg
from PyQt6.QtWidgets import QGraphicsScene, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QSpinBox, QComboBox, QButtonGroup, QLineEdit, QListWidget, QSplitter
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QTimer
from estilos import SECUNDARIO_QSS
import estilos_graficos as _gr
from dpi.formatos.constantes import TUCSON_MAX_CHARS_ID
from dpi.ui.colores import TIPOS_ANOMALIA
from dpi.medicion.marcas import ModoMedicion
from modulo_vista_medicion import PanelSplit, VistaInteractiva


@dataclass(frozen=True)
class AccionesBarraMedicion:
    _activar_calibracion: Callable
    _al_cambiar_direccion: Callable
    _al_cambiar_especie: Callable
    _aplicar_anio_corteza: Callable
    _aplicar_anio_medula: Callable
    _aplicar_banda_actual: Callable
    _calibrar_por_dpi: Callable
    _cambiar_banda: Callable
    _configurar_especie: Callable
    _crear_popup: Callable
    _crear_separador: Callable
    _deshacer: Callable
    _deshacer_pith_offset: Callable
    _detectar_ewlw_automatico: Callable
    _ejecutar_exportacion: Callable
    _eliminar_ewlw: Callable
    _exportar_anomalias: Callable
    _guardar_ajustes_banda: Callable
    _importar_pos: Callable
    _iniciar_estimacion_pith: Callable
    _nueva_especie: Callable
    _rehacer: Callable
    _toggle_autodetect: Callable
    _toggle_popup: Callable
    _toggle_split_view: Callable
    set_modo: Callable


@dataclass(frozen=True)
class ControlesBarraMedicion:
    _banda_actual: object
    _botones_modo: object
    _btn_ewlw_dd: object
    _btn_herram: object
    _btn_imagen: object
    _btn_split: object
    _grupo_banda: object
    _popup_ewlw: object
    _popup_herram: object
    _popup_imagen: object
    _slider_brillo: object
    _slider_contraste: object
    _timer_banda: object
    btn_anomalia: object
    btn_autodetect: object
    btn_calibrar: object
    btn_calibrar_dpi: object
    btn_cfg_especie: object
    btn_deshacer: object
    btn_deshacer_pith: object
    btn_ewlw_auto: object
    btn_ewlw_eliminar: object
    btn_exportar: object
    btn_exportar_anom: object
    btn_importar_pos: object
    btn_nueva_especie: object
    btn_pith: object
    btn_rehacer: object
    check_tiene_corteza: object
    check_tiene_medula: object
    combo_dir: object
    combo_especie: object
    combo_tipo_anomalia: object
    grupo_modos: object
    input_codigo: object
    spin_corteza: object
    spin_medula: object


def construir_barra_herramientas(parent, acciones, especies, especie_activa):
    barra = QHBoxLayout()
    barra.setSpacing(3)

    # ══════════════════════════════════════════════════════════════════
    # SIEMPRE VISIBLES: botones de medición + edición
    # ══════════════════════════════════════════════════════════════════
    _ui_grupo_modos = QButtonGroup(parent)
    _ui__botones_modo = {}

    _btn_colores = {
        ModoMedicion.MEDIR:    ("#2ecc71", "#27ae60"),  # verde
        ModoMedicion.SALTO:    ("#f39c12", "#d68910"),  # ámbar
        ModoMedicion.ESPACIO:  ("#9b59b6", "#8e44ad"),  # púrpura
        ModoMedicion.INSERTAR: ("#3498db", "#2980b9"),  # azul
        ModoMedicion.MOVER:    ("#1abc9c", "#16a085"),  # turquesa
        ModoMedicion.BORRAR:   ("#e74c3c", "#c0392b"),  # rojo
        ModoMedicion.SELECCIONAR: ("#FFEB3B", "#FBC02D"),  # amarillo
    }

    botones_visibles = [
        ("📍 Medir",       ModoMedicion.MEDIR,        "Ctrl+A", "Clic izq: añadir anillo · Clic der: salto · Scroll: zoom"),
        ("🎯 Seleccionar", ModoMedicion.SELECCIONAR,  "Ctrl+R", "Seleccionar múltiples anillos para borrar / convertir a salto / quiebre"),
        ("🔀 Salto",       ModoMedicion.SALTO,        "Ctrl+D", "Añadir salto (discontinuidad)"),
        ("⊘ Quiebre",      ModoMedicion.ESPACIO,      "Ctrl+E", "Marcar quiebre intra-anillo\nNo cuenta como anillo"),
        ("➕ Insertar",     ModoMedicion.INSERTAR,     "Ctrl+W", "Insertar punto en segmento existente"),
        ("🖐 Mover",        ModoMedicion.MOVER,        "Ctrl+S", "Mover punto"),
        ("✕ Borrar",       ModoMedicion.BORRAR,       "Ctrl+X", "Borrar punto con clic"),
    ]
    for texto, modo, atajo, tooltip in botones_visibles:
        bg, bg_hover = _btn_colores[modo]
        btn = crear_boton(texto, lambda checked, m=modo: acciones.set_modo(m),
                          tooltip=f"{tooltip} ({atajo})", checkable=True)
        # ModoMedicion.SELECCIONAR usa color amarillo claro: el texto blanco no
        # contrasta bien, así que aplicamos texto NEGRO en lugar de blanco.
        color_texto = "#222" if modo == ModoMedicion.SELECCIONAR else "white"
        btn.setStyleSheet(
            f"QPushButton{{background-color:{bg}; color:{color_texto}; font-weight:bold; "
            f"padding:4px 10px; border-radius:4px;}}"
            f"QPushButton:hover{{background-color:{bg_hover};}}"
            f"QPushButton:checked{{background-color:#fff; color:{bg}; "
            f"border:2px solid {bg};}}"
        )
        _ui_grupo_modos.addButton(btn)
        _ui__botones_modo[modo] = btn
        barra.addWidget(btn)
        QShortcut(QKeySequence(atajo), parent).activated.connect(lambda m=modo: acciones.set_modo(m))
    _ui__botones_modo[ModoMedicion.MEDIR].setChecked(True)

    barra.addSpacing(6)

    # ══════════════════════════════════════════════════════════════════
    # 🍂 EW/LW (dropdown)
    # ══════════════════════════════════════════════════════════════════
    _ui__btn_ewlw_dd = QPushButton("🍂 EW/LW ▾")
    _ui__btn_ewlw_dd.setStyleSheet(
        "QPushButton{background-color:#FF8C00; color:white; font-weight:bold; "
        "padding:4px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#e67e22;}"
    )
    _ui__btn_ewlw_dd.setToolTip("Herramientas Earlywood / Latewood")
    _ui__btn_ewlw_dd.clicked.connect(lambda: acciones._toggle_popup(_ui__popup_ewlw))
    barra.addWidget(_ui__btn_ewlw_dd)

    _ui__popup_ewlw = acciones._crear_popup()
    pe_layout = QVBoxLayout(_ui__popup_ewlw)
    pe_layout.setContentsMargins(8, 8, 8, 8)
    pe_layout.setSpacing(4)

    btn_ewlw_marcar = QPushButton("🍂 Marcar EW/LW")
    btn_ewlw_marcar.setCheckable(True)
    btn_ewlw_marcar.setToolTip("Marcar límite Earlywood/Latewood (Ctrl+L)")
    btn_ewlw_marcar.clicked.connect(
        lambda: (acciones.set_modo(ModoMedicion.EWLW), _ui__popup_ewlw.hide()))
    _ui_grupo_modos.addButton(btn_ewlw_marcar)
    _ui__botones_modo[ModoMedicion.EWLW] = btn_ewlw_marcar
    QShortcut(QKeySequence("Ctrl+L"), parent).activated.connect(
        lambda: acciones.set_modo(ModoMedicion.EWLW))
    pe_layout.addWidget(btn_ewlw_marcar)

    _ui_btn_ewlw_auto = QPushButton("🔍 Auto-detectar EW/LW")
    _ui_btn_ewlw_auto.setToolTip("Detectar automáticamente EW/LW en cada anillo")
    _ui_btn_ewlw_auto.setStyleSheet(
        "QPushButton{background-color:#FF8C00; color:white; font-weight:bold;}")
    _ui_btn_ewlw_auto.clicked.connect(
        lambda: (acciones._detectar_ewlw_automatico(), _ui__popup_ewlw.hide()))
    pe_layout.addWidget(_ui_btn_ewlw_auto)

    _ui_btn_ewlw_eliminar = QPushButton("🗑 Eliminar todos EW/LW")
    _ui_btn_ewlw_eliminar.setToolTip("Eliminar todos los límites EW/LW del radio activo")
    _ui_btn_ewlw_eliminar.setStyleSheet(
        "QPushButton{background-color:#8B0000; color:white;}")
    _ui_btn_ewlw_eliminar.clicked.connect(
        lambda: (acciones._eliminar_ewlw(), _ui__popup_ewlw.hide()))
    pe_layout.addWidget(_ui_btn_ewlw_eliminar)

    # ══════════════════════════════════════════════════════════════════
    # 🔧 HERRAMIENTAS (dropdown)
    # ══════════════════════════════════════════════════════════════════
    _ui__btn_herram = QPushButton("🔧 Herramientas ▾")
    _ui__btn_herram.setStyleSheet(
        "QPushButton{background-color:#555; color:white; font-weight:bold; "
        "padding:4px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#666;}"
    )
    _ui__btn_herram.setToolTip("Deshacer, anomalías, estimación, calibración")
    _ui__btn_herram.clicked.connect(lambda: acciones._toggle_popup(_ui__popup_herram))
    barra.addWidget(_ui__btn_herram)

    _ui__popup_herram = acciones._crear_popup()
    ph_layout = QVBoxLayout(_ui__popup_herram)
    ph_layout.setContentsMargins(8, 8, 8, 8)
    ph_layout.setSpacing(4)

    fila_undo = QHBoxLayout()
    _ui_btn_deshacer = QPushButton("⏪ Deshacer")
    _ui_btn_deshacer.setStyleSheet("background-color:#d9534f; color:white;")
    _ui_btn_deshacer.setToolTip("Deshacer (Ctrl+Z)")
    _ui_btn_deshacer.clicked.connect(acciones._deshacer)
    QShortcut(QKeySequence("Ctrl+Z"), parent).activated.connect(acciones._deshacer)
    fila_undo.addWidget(_ui_btn_deshacer)
    _ui_btn_rehacer = QPushButton("Rehacer ⏩")
    _ui_btn_rehacer.setStyleSheet("background-color:#5bc0de; color:white;")
    _ui_btn_rehacer.setToolTip("Rehacer (Ctrl+Y)")
    _ui_btn_rehacer.clicked.connect(acciones._rehacer)
    QShortcut(QKeySequence("Ctrl+Y"), parent).activated.connect(acciones._rehacer)
    fila_undo.addWidget(_ui_btn_rehacer)
    ph_layout.addLayout(fila_undo)
    ph_layout.addWidget(acciones._crear_separador())

    fila_anom = QHBoxLayout()
    _ui_btn_anomalia = QPushButton("🔴 Anomalías")
    _ui_btn_anomalia.setCheckable(True)
    _ui_btn_anomalia.setToolTip("Modo anomalías (Ctrl+Q)")
    _ui_btn_anomalia.clicked.connect(
        lambda: (acciones.set_modo(ModoMedicion.ANOMALIA), _ui__popup_herram.hide()))
    _ui_grupo_modos.addButton(_ui_btn_anomalia)
    _ui__botones_modo[ModoMedicion.ANOMALIA] = _ui_btn_anomalia
    QShortcut(QKeySequence("Ctrl+Q"), parent).activated.connect(
        lambda: acciones.set_modo(ModoMedicion.ANOMALIA))
    fila_anom.addWidget(_ui_btn_anomalia)
    _ui_combo_tipo_anomalia = QComboBox()
    _ui_combo_tipo_anomalia.setToolTip("Tipo de anomalía a marcar")
    _ui_combo_tipo_anomalia.setMinimumWidth(140)
    for tipo, (icono, etiqueta, color) in TIPOS_ANOMALIA.items():
        _ui_combo_tipo_anomalia.addItem(f"{icono} {etiqueta}", userData=tipo)
    fila_anom.addWidget(_ui_combo_tipo_anomalia)
    ph_layout.addLayout(fila_anom)
    ph_layout.addWidget(acciones._crear_separador())

    fila_pith = QHBoxLayout()
    _ui_btn_pith = QPushButton("🎯 Anillos al centro")
    _ui_btn_pith.setCheckable(True)
    _ui_btn_pith.setToolTip("Estimar anillos faltantes (Ctrl+P)")
    _ui_btn_pith.setStyleSheet(
        "QPushButton{background-color:#8B4513; color:white; font-weight:bold;}"
        "QPushButton:checked{background-color:#FF8C00; color:white;}")
    _ui_btn_pith.clicked.connect(
        lambda: (acciones._iniciar_estimacion_pith(), _ui__popup_herram.hide()))
    _ui_grupo_modos.addButton(_ui_btn_pith)
    _ui__botones_modo[ModoMedicion.PITH] = _ui_btn_pith
    QShortcut(QKeySequence("Ctrl+P"), parent).activated.connect(acciones._iniciar_estimacion_pith)
    fila_pith.addWidget(_ui_btn_pith)
    _ui_btn_deshacer_pith = QPushButton("↩ Deshacer estimación")
    _ui_btn_deshacer_pith.setStyleSheet(
        "QPushButton{background-color:#d9534f; color:white; font-weight:bold;}")
    _ui_btn_deshacer_pith.clicked.connect(acciones._deshacer_pith_offset)
    _ui_btn_deshacer_pith.hide()
    fila_pith.addWidget(_ui_btn_deshacer_pith)
    ph_layout.addLayout(fila_pith)
    ph_layout.addWidget(acciones._crear_separador())

    fila_cal = QHBoxLayout()
    _ui_btn_calibrar_dpi = QPushButton("📐 DPI")
    _ui_btn_calibrar_dpi.setToolTip("Información de imagen y configuración de DPI")
    _ui_btn_calibrar_dpi.clicked.connect(
        lambda: (acciones._calibrar_por_dpi(), _ui__popup_herram.hide()))
    fila_cal.addWidget(_ui_btn_calibrar_dpi)
    _ui_btn_calibrar = QPushButton("📏 Regla")
    _ui_btn_calibrar.setToolTip("Calibrar midiendo una distancia conocida")
    _ui_btn_calibrar.clicked.connect(
        lambda: (acciones._activar_calibracion(), _ui__popup_herram.hide()))
    fila_cal.addWidget(_ui_btn_calibrar)
    ph_layout.addLayout(fila_cal)

    # ══════════════════════════════════════════════════════════════════
    # 🎨 COLORES (dropdown)
    # ══════════════════════════════════════════════════════════════════
    from PyQt6.QtWidgets import QSlider

    _ui__btn_imagen = QPushButton("🎨 Colores ▾")
    _ui__btn_imagen.setStyleSheet(
        "QPushButton{background-color:#555; color:white; font-weight:bold; "
        "padding:4px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#666;}"
    )
    _ui__btn_imagen.setToolTip("Visualización por banda y brillo/contraste")
    _ui__btn_imagen.clicked.connect(lambda: acciones._toggle_popup(_ui__popup_imagen))
    barra.addWidget(_ui__btn_imagen)

    _ui__popup_imagen = acciones._crear_popup()
    pi_layout = QVBoxLayout(_ui__popup_imagen)
    pi_layout.setContentsMargins(8, 8, 8, 8)
    pi_layout.setSpacing(6)
    pi_layout.addWidget(QLabel("Canal de visualización:"))

    fila_banda = QHBoxLayout()
    _ui__grupo_banda = QButtonGroup(parent)
    _ui__grupo_banda.setExclusive(True)
    _ui__banda_actual = "RGB"
    btn_estilo = (
        "QPushButton{min-width:40px; padding:4px 8px; font-weight:bold; "
        "border:1px solid #555; border-radius:3px; font-size:13px;}"
        "QPushButton:checked{border:2px solid #FFD700;}")
    for nombre_b, color_b, atajo_b in [
        ("RGB", "#aaa", "1"), ("R", "#FF4444", "2"),
        ("G", "#44CC44", "3"), ("B", "#4488FF", "4"), ("Gris", "#999", "5"),
    ]:
        btn_b = QPushButton(nombre_b)
        btn_b.setCheckable(True)
        btn_b.setFixedHeight(30)
        btn_b.setStyleSheet(
            btn_estilo + f"QPushButton{{color:{color_b};}}"
            f"QPushButton:checked{{color:{color_b}; background:rgba(255,255,255,15);}}")
        btn_b.setToolTip(f"Canal {nombre_b} (tecla {atajo_b})")
        btn_b.clicked.connect(lambda _, b=nombre_b: acciones._cambiar_banda(b))
        _ui__grupo_banda.addButton(btn_b)
        fila_banda.addWidget(btn_b)
        QShortcut(QKeySequence(atajo_b), parent).activated.connect(
            lambda b=nombre_b: acciones._cambiar_banda(b))
        if nombre_b == "RGB":
            btn_b.setChecked(True)
    pi_layout.addLayout(fila_banda)
    pi_layout.addWidget(acciones._crear_separador())

    fila_brillo = QHBoxLayout()
    fila_brillo.addWidget(QLabel("☀ Brillo"))
    _ui__slider_brillo = QSlider(Qt.Orientation.Horizontal)
    _ui__slider_brillo.setRange(-100, 100)
    _ui__slider_brillo.setValue(0)
    _ui__slider_brillo.sliderReleased.connect(acciones._guardar_ajustes_banda)
    fila_brillo.addWidget(_ui__slider_brillo)
    pi_layout.addLayout(fila_brillo)

    fila_contraste = QHBoxLayout()
    fila_contraste.addWidget(QLabel("◐ Contraste"))
    _ui__slider_contraste = QSlider(Qt.Orientation.Horizontal)
    _ui__slider_contraste.setRange(50, 300)
    _ui__slider_contraste.setValue(100)
    _ui__slider_contraste.sliderReleased.connect(acciones._guardar_ajustes_banda)
    fila_contraste.addWidget(_ui__slider_contraste)
    pi_layout.addLayout(fila_contraste)

    _ui__timer_banda = QTimer()
    _ui__timer_banda.setSingleShot(True)
    _ui__timer_banda.setInterval(120)
    _ui__timer_banda.timeout.connect(acciones._aplicar_banda_actual)
    _ui__slider_brillo.valueChanged.connect(lambda: _ui__timer_banda.start())
    _ui__slider_contraste.valueChanged.connect(lambda: _ui__timer_banda.start())
    _ui__slider_brillo.mouseDoubleClickEvent = lambda e: _ui__slider_brillo.setValue(0)
    _ui__slider_contraste.mouseDoubleClickEvent = lambda e: _ui__slider_contraste.setValue(100)

    # ══════════════════════════════════════════════════════════════════
    # Vista dividida
    barra.addSpacing(6)
    _ui__btn_split = QPushButton("◫ Ventana")
    _ui__btn_split.setCheckable(True)
    _ui__btn_split.setStyleSheet(
        "QPushButton{background-color:#555; color:white; font-weight:bold; "
        "padding:4px 10px; border-radius:4px;}"
        "QPushButton:hover{background-color:#666;}"
        "QPushButton:checked{background-color:#FF8C00; color:white;}"
    )
    _ui__btn_split.setToolTip(
        "Ventana auxiliar: muestra la misma imagen (u otra de las pestañas\n"
        "abiertas) en un panel con zoom y posición independientes.\n"
        "Útil para comparar zonas distantes o dos muestras a la vez. (Ctrl+B)")
    _ui__btn_split.clicked.connect(acciones._toggle_split_view)
    barra.addWidget(_ui__btn_split)
    QShortcut(QKeySequence("Ctrl+B"), parent).activated.connect(acciones._toggle_split_view)

    # ══════════════════════════════════════════════════════════════════
    barra.addStretch()

    _ui_btn_importar_pos = QPushButton("📥 Cargar .pos")
    _ui_btn_importar_pos.setStyleSheet(
        "background-color:#5bc0de; color:white; font-weight:bold; padding:4px 8px;")
    _ui_btn_importar_pos.setToolTip("Importar archivo CooRecorder .pos")
    _ui_btn_importar_pos.clicked.connect(acciones._importar_pos)
    barra.addWidget(_ui_btn_importar_pos)

    # Metadatos ocultos (lógica interna, visualmente en main.py)
    _ui_input_codigo = QLineEdit()
    _ui_input_codigo.setMaxLength(TUCSON_MAX_CHARS_ID)
    _ui_input_codigo.hide()

    _ui_combo_dir = QComboBox()
    _ui_combo_dir.addItems(["Médula→Corteza (+1)", "Corteza→Médula (-1)"])
    _ui_combo_dir.currentIndexChanged.connect(acciones._al_cambiar_direccion)
    _ui_combo_dir.hide()

    _ui_spin_medula = QSpinBox()
    _ui_spin_medula.setRange(-10000, 5000)
    _ui_spin_medula.valueChanged.connect(acciones._aplicar_anio_medula)
    _ui_spin_medula.hide()

    _ui_spin_corteza = QSpinBox()
    _ui_spin_corteza.setRange(-10000, 5000)
    _ui_spin_corteza.valueChanged.connect(acciones._aplicar_anio_corteza)
    _ui_spin_corteza.hide()

    from PyQt6.QtWidgets import QCheckBox
    _ui_check_tiene_medula = QCheckBox()
    _ui_check_tiene_medula.setToolTip("¿La serie llega físicamente a la médula?")
    _ui_check_tiene_medula.hide()

    _ui_check_tiene_corteza = QCheckBox()
    _ui_check_tiene_corteza.setToolTip("¿La serie llega físicamente a la corteza?")
    _ui_check_tiene_corteza.hide()

    # ── Auto-detección: combo especie + botón (se construyen aquí,
    #    pero se EXPONEN mediante métodos para que main_anillos los mueva
    #    a la barra superior si lo desea) ──────────────────────────────
    _ui_combo_especie = QComboBox()
    _ui_combo_especie.setToolTip("Especie activa para la auto-detección")
    _ui_combo_especie.setMinimumWidth(130)
    _ui_combo_especie.addItems(list(especies))
    if especie_activa in especies:
        _ui_combo_especie.setCurrentText(especie_activa)
    _ui_combo_especie.currentTextChanged.connect(acciones._al_cambiar_especie)
    _ui_combo_especie.hide()   # Se agrega desde main_anillos a barra_top

    _ui_btn_cfg_especie = QPushButton("⚙")
    _ui_btn_cfg_especie.setToolTip("Configurar parámetros de detección para esta especie")
    _ui_btn_cfg_especie.setFixedWidth(28)
    _ui_btn_cfg_especie.clicked.connect(acciones._configurar_especie)
    _ui_btn_cfg_especie.hide()

    _ui_btn_nueva_especie = QPushButton("＋")
    _ui_btn_nueva_especie.setToolTip("Crear nuevo perfil de especie")
    _ui_btn_nueva_especie.setFixedWidth(28)
    _ui_btn_nueva_especie.clicked.connect(acciones._nueva_especie)
    _ui_btn_nueva_especie.hide()

    _ui_btn_autodetect = QPushButton("🔍 Auto-detectar")
    _ui_btn_autodetect.setCheckable(True)
    _ui_btn_autodetect.setStyleSheet(
        "QPushButton{background-color:#5cb85c; color:white; font-weight:bold;}"
        "QPushButton:checked{background-color:#f0ad4e; color:white;}"
    )
    _ui_btn_autodetect.setToolTip(
        "Activa el modo auto-detección.\n"
        "Clic 1: médula   Clic 2: corteza\n"
        "El programa detecta todos los anillos automáticamente."
    )
    _ui_btn_autodetect.clicked.connect(acciones._toggle_autodetect)
    _ui_grupo_modos.addButton(_ui_btn_autodetect)
    _ui__botones_modo[ModoMedicion.AUTODETECT] = _ui_btn_autodetect
    _ui_btn_autodetect.hide()  # Se agrega desde main_anillos a barra_top

    _ui_btn_exportar = QPushButton("💾 Exp")
    _ui_btn_exportar.setToolTip(
        "Exportar la medición (Tucson / Excel / CSV / .pos CooRecorder)")
    _ui_btn_exportar.clicked.connect(acciones._ejecutar_exportacion)
    barra.addWidget(_ui_btn_exportar)

    _ui_btn_exportar_anom = QPushButton("🔖 Anom")
    _ui_btn_exportar_anom.setToolTip(
        "Exportar las anomalías a un archivo separado (CSV/TSV) para "
        "manejarlas en R u otros programas")
    _ui_btn_exportar_anom.clicked.connect(acciones._exportar_anomalias)
    barra.addWidget(_ui_btn_exportar_anom)


    return barra, ControlesBarraMedicion(
        _banda_actual=_ui__banda_actual,
        _botones_modo=_ui__botones_modo,
        _btn_ewlw_dd=_ui__btn_ewlw_dd,
        _btn_herram=_ui__btn_herram,
        _btn_imagen=_ui__btn_imagen,
        _btn_split=_ui__btn_split,
        _grupo_banda=_ui__grupo_banda,
        _popup_ewlw=_ui__popup_ewlw,
        _popup_herram=_ui__popup_herram,
        _popup_imagen=_ui__popup_imagen,
        _slider_brillo=_ui__slider_brillo,
        _slider_contraste=_ui__slider_contraste,
        _timer_banda=_ui__timer_banda,
        btn_anomalia=_ui_btn_anomalia,
        btn_autodetect=_ui_btn_autodetect,
        btn_calibrar=_ui_btn_calibrar,
        btn_calibrar_dpi=_ui_btn_calibrar_dpi,
        btn_cfg_especie=_ui_btn_cfg_especie,
        btn_deshacer=_ui_btn_deshacer,
        btn_deshacer_pith=_ui_btn_deshacer_pith,
        btn_ewlw_auto=_ui_btn_ewlw_auto,
        btn_ewlw_eliminar=_ui_btn_ewlw_eliminar,
        btn_exportar=_ui_btn_exportar,
        btn_exportar_anom=_ui_btn_exportar_anom,
        btn_importar_pos=_ui_btn_importar_pos,
        btn_nueva_especie=_ui_btn_nueva_especie,
        btn_pith=_ui_btn_pith,
        btn_rehacer=_ui_btn_rehacer,
        check_tiene_corteza=_ui_check_tiene_corteza,
        check_tiene_medula=_ui_check_tiene_medula,
        combo_dir=_ui_combo_dir,
        combo_especie=_ui_combo_especie,
        combo_tipo_anomalia=_ui_combo_tipo_anomalia,
        grupo_modos=_ui_grupo_modos,
        input_codigo=_ui_input_codigo,
        spin_corteza=_ui_spin_corteza,
        spin_medula=_ui_spin_medula,
    )


@dataclass(frozen=True)
class AccionesGraficoMedicion:
    _actualizar_grafico: Callable
    _calcular_bi: Callable
    _cargar_serie_maestra: Callable
    _cargar_serie_wid: Callable
    _configurar_bi: Callable
    _eliminar_serie_maestra: Callable
    _graficar_bi_ventana: Callable
    _guardar_bi: Callable
    _navegar_anio_grafico: Callable
    _toggle_banda_bi: Callable
    metodo_correlacion: Callable


@dataclass(frozen=True)
class ControlesGraficoMedicion:
    _btn_cfg_bi: object
    _item_highlight_anio: object
    btn_calcular_bi: object
    btn_cargar_maestra: object
    btn_cargar_wid: object
    btn_eliminar_maestra: object
    btn_graficar_bi: object
    btn_guardar_bi: object
    btn_mostrar_banda: object
    combo_maestra: object
    combo_metodo_corr: object
    grafico_medicion: object
    grafico_unif: object
    lbl_nombre_maestra: object
    lbl_r_total: object
    lbl_ventanas_r: object
    spin_ventana_r: object


def construir_panel_codatacion(parent, acciones):
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 5, 0, 0)

    # ── Fila de referencia + controles ───────────────────────────────
    fila_maestra = QHBoxLayout()
    fila_maestra.addWidget(QLabel("<b>Referencia:</b>"))
    _ui_btn_cargar_maestra = QPushButton("📂 Cargar referencia")
    _ui_btn_cargar_maestra.setToolTip(
        "Cargar serie o cronología de referencia.\n\n"
        "Acepta Tucson (.rwl, .txt), compacto, CooRecorder (.wid) y\n"
        "formatos de dos columnas (año + valor) en .txt, .csv, .xlsx\n"
        "y .ods — el mismo formato en que DPI exporta las cronologías.")
    _ui_btn_cargar_maestra.clicked.connect(acciones._cargar_serie_maestra)
    _ui_btn_cargar_wid = QPushButton("📂 .wid")
    _ui_btn_cargar_wid.setToolTip("Cargar cronología CooRecorder (.wid)")
    _ui_btn_cargar_wid.setStyleSheet(
        "background-color:#5bc0de; color:white; font-weight:bold;")
    _ui_btn_cargar_wid.clicked.connect(acciones._cargar_serie_wid)
    _ui_lbl_nombre_maestra = QLabel("Ninguna")
    _ui_lbl_nombre_maestra.setStyleSheet(f"color:{SECUNDARIO_QSS};")
    fila_maestra.addWidget(_ui_btn_cargar_maestra)
    fila_maestra.addWidget(_ui_btn_cargar_wid)
    fila_maestra.addWidget(_ui_lbl_nombre_maestra)

    # Botón para eliminar la maestra externa cargada
    _ui_btn_eliminar_maestra = QPushButton("🗑")
    _ui_btn_eliminar_maestra.setToolTip(
        "Eliminar la serie de referencia externa cargada")
    _ui_btn_eliminar_maestra.setFixedWidth(32)
    _ui_btn_eliminar_maestra.setStyleSheet(
        "QPushButton{background-color:#a94442; color:white; "
        "padding:2px; border-radius:3px; min-width:0px;}"
        "QPushButton:hover{background-color:#c9302c;}"
        "QPushButton:disabled{background-color:#555; color:#888;}"
    )
    _ui_btn_eliminar_maestra.clicked.connect(acciones._eliminar_serie_maestra)
    _ui_btn_eliminar_maestra.setEnabled(False)   # se habilita al cargar una
    fila_maestra.addWidget(_ui_btn_eliminar_maestra)

    # Combo selector de maestra propia
    fila_maestra.addSpacing(12)
    fila_maestra.addWidget(QLabel("Maestra:"))
    _ui_combo_maestra = QComboBox()
    _ui_combo_maestra.setToolTip(
        "Serie propia usada como referencia cuando no hay archivo externo cargado."
    )
    _ui_combo_maestra.setMinimumWidth(110)
    _ui_combo_maestra.currentIndexChanged.connect(acciones._actualizar_grafico)
    fila_maestra.addWidget(_ui_combo_maestra)

    # Selector de ventana de correlación
    fila_maestra.addSpacing(12)
    fila_maestra.addWidget(QLabel("Ventana:"))
    _ui_spin_ventana_r = QSpinBox()
    _ui_spin_ventana_r.setRange(10, 100)
    _ui_spin_ventana_r.setSingleStep(5)
    _ui_spin_ventana_r.setValue(50)
    _ui_spin_ventana_r.setSuffix(" años")
    # Antes era 80px — muy angosto: el padding (4px) + borde (1px) + las
    # flechas de incremento (~16px) consumían casi todo el espacio y las
    # flechas quedaban recortadas/invisibles. 110px deja espacio cómodo.
    _ui_spin_ventana_r.setFixedWidth(110)
    _ui_spin_ventana_r.setToolTip(
        "Ventana máxima de correlación deslizante.\n"
        "Mientras la serie tenga menos años, la ventana crece desde 10.\n"
        "El solapamiento entre ventanas es siempre la mitad (estilo COFECHA)."
    )
    _ui_spin_ventana_r.valueChanged.connect(acciones._actualizar_grafico)
    fila_maestra.addWidget(_ui_spin_ventana_r)

    fila_maestra.addSpacing(12)
    fila_maestra.addWidget(QLabel("Correlación:"))
    # Selector de método. Antes esta pestaña usaba siempre diferencias-log
    # mientras que Co-Datación usaba el método de COFECHA, así que el mismo
    # par de series daba r distintas en cada pestaña sin aviso alguno.
    _ui_combo_metodo_corr = crear_selector(parent, _tr.DIFFLOG)
    _ui_combo_metodo_corr.currentIndexChanged.connect(
        acciones._actualizar_grafico)
    fila_maestra.addWidget(_ui_combo_metodo_corr)

    fila_maestra.addStretch()

    # Label de r total
    _ui_lbl_r_total = QLabel("")
    _ui_lbl_r_total.setStyleSheet("font-size:12px; font-weight:bold;")
    fila_maestra.addWidget(_ui_lbl_r_total)

    _ui_btn_calcular_bi = QPushButton("🎨 Calcular BI")
    _ui_btn_calcular_bi.setToolTip(
        "Calcular Blue, Green, Red y Gray Intensity por anillo.\n"
        "El resultado queda en memoria — usa 💾 Guardar BI para exportar."
    )
    _ui_btn_calcular_bi.setStyleSheet(
        "background-color:#5bc0de; color:white; font-weight:bold;"
    )
    _ui_btn_calcular_bi.clicked.connect(acciones._calcular_bi)
    fila_maestra.addWidget(_ui_btn_calcular_bi)

    _ui_btn_graficar_bi = QPushButton("📊 Graficar BI")
    _ui_btn_graficar_bi.setToolTip(
        "Abrir ventana con el gráfico de BI/GI/RI/GrayI por anillo.\n"
        "Tiene zoom y paneo independientes del gráfico de series."
    )
    _ui_btn_graficar_bi.setEnabled(False)
    _ui_btn_graficar_bi.clicked.connect(acciones._graficar_bi_ventana)
    fila_maestra.addWidget(_ui_btn_graficar_bi)

    _ui_btn_guardar_bi = QPushButton("💾 Guardar BI")
    _ui_btn_guardar_bi.setToolTip(
        "Guardar los valores de intensidad calculados como archivos .rwl.\n"
        "Elige qué canales y métricas exportar."
    )
    _ui_btn_guardar_bi.setEnabled(False)
    _ui_btn_guardar_bi.clicked.connect(acciones._guardar_bi)
    fila_maestra.addWidget(_ui_btn_guardar_bi)

    _ui__btn_cfg_bi = QPushButton("⚙")
    _ui__btn_cfg_bi.setFixedWidth(28)
    _ui__btn_cfg_bi.setToolTip("Configurar banda de muestreo y canales")
    _ui__btn_cfg_bi.clicked.connect(acciones._configurar_bi)
    fila_maestra.addWidget(_ui__btn_cfg_bi)

    _ui_btn_mostrar_banda = QPushButton("👁 Ver área BI")
    _ui_btn_mostrar_banda.setCheckable(True)
    _ui_btn_mostrar_banda.setToolTip(
        "Mostrar/ocultar el área de muestreo BI sobre la imagen.\n"
        "Dibuja el rectángulo azul que cubre cada anillo (igual que CooRecorder)."
    )
    _ui_btn_mostrar_banda.toggled.connect(acciones._toggle_banda_bi)
    fila_maestra.addWidget(_ui_btn_mostrar_banda)

    layout.addLayout(fila_maestra)

    # ── Gráfico de series ─────────────────────────────────────────────
    _ui_grafico_unif = pg.PlotWidget()
    _gr.aplicar_a_pyqtgraph(_ui_grafico_unif)
    _ui_grafico_unif.showGrid(x=True, y=True, alpha=0.3)
    _ui_grafico_unif.setLabel("bottom", "Año")
    _ui_grafico_unif.setLabel("left",   "Ancho (mm)")
    layout.addWidget(_ui_grafico_unif)

    # Controles de zoom, los mismos de Co-Datación: zoom por área,
    # ensanchar/comprimir el eje X y ver todo. En series largas son
    # imprescindibles para poder mirar el detalle año a año.
    try:
        from modulo_widgets import _crear_barra_zoom
        layout.addWidget(_crear_barra_zoom(_ui_grafico_unif))
    except Exception as _e:
        print("No se pudo agregar la barra de zoom:", _e)

    # Item de resaltado en la imagen al hacer clic en el gráfico
    _ui__item_highlight_anio = None

    # ── Barra de correlaciones por ventana (texto enriquecido) ────────
    _ui_lbl_ventanas_r = QLabel("")
    _ui_lbl_ventanas_r.setWordWrap(True)
    _ui_lbl_ventanas_r.setStyleSheet(
        "font-size:11px; padding:3px 6px; "
        "background-color: rgba(0,0,0,30); border-radius:4px;"
    )
    _ui_lbl_ventanas_r.setAlignment(Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(_ui_lbl_ventanas_r)

    _ui_grafico_medicion = GraficoMedicion(
        _ui_grafico_unif, _ui_combo_maestra, _ui_spin_ventana_r,
        _ui_lbl_r_total, _ui_lbl_ventanas_r,
        acciones.metodo_correlacion, acciones._navegar_anio_grafico)


    return panel, ControlesGraficoMedicion(
        _btn_cfg_bi=_ui__btn_cfg_bi,
        _item_highlight_anio=_ui__item_highlight_anio,
        btn_calcular_bi=_ui_btn_calcular_bi,
        btn_cargar_maestra=_ui_btn_cargar_maestra,
        btn_cargar_wid=_ui_btn_cargar_wid,
        btn_eliminar_maestra=_ui_btn_eliminar_maestra,
        btn_graficar_bi=_ui_btn_graficar_bi,
        btn_guardar_bi=_ui_btn_guardar_bi,
        btn_mostrar_banda=_ui_btn_mostrar_banda,
        combo_maestra=_ui_combo_maestra,
        combo_metodo_corr=_ui_combo_metodo_corr,
        grafico_medicion=_ui_grafico_medicion,
        grafico_unif=_ui_grafico_unif,
        lbl_nombre_maestra=_ui_lbl_nombre_maestra,
        lbl_r_total=_ui_lbl_r_total,
        lbl_ventanas_r=_ui_lbl_ventanas_r,
        spin_ventana_r=_ui_spin_ventana_r,
    )


@dataclass(frozen=True)
class AccionesRadiosMedicion:
    _editar_camino: Callable
    _eliminar_camino: Callable
    _finalizar_camino: Callable
    _toggle_visual_camino: Callable


@dataclass(frozen=True)
class ControlesRadiosMedicion:
    btn_editar_camino: object
    btn_finalizar_camino: object
    lista_caminos: object


def construir_panel_radios(parent, acciones):
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel("Radios Guardados:"))

    _ui_lista_caminos = QListWidget()
    _ui_lista_caminos.itemChanged.connect(acciones._toggle_visual_camino)
    QShortcut(QKeySequence(Qt.Key.Key_Delete), _ui_lista_caminos).activated.connect(acciones._eliminar_camino)
    QShortcut(QKeySequence(Qt.Key.Key_Backspace), _ui_lista_caminos).activated.connect(acciones._eliminar_camino)
    layout.addWidget(_ui_lista_caminos)

    btn_eliminar = QPushButton("🗑️ Eliminar")
    btn_eliminar.setStyleSheet("background-color:#d9534f; color:white;")
    btn_eliminar.clicked.connect(acciones._eliminar_camino)
    layout.addWidget(btn_eliminar)

    _ui_btn_editar_camino = QPushButton("✏️ Editar Radio")
    _ui_btn_editar_camino.setStyleSheet("background-color:#f0ad4e; color:white; font-weight:bold;")
    _ui_btn_editar_camino.clicked.connect(acciones._editar_camino)
    layout.addWidget(_ui_btn_editar_camino)

    _ui_btn_finalizar_camino = QPushButton("✅ Terminar Radio")
    _ui_btn_finalizar_camino.setStyleSheet("background-color:#5cb85c; color:white; font-weight:bold;")
    _ui_btn_finalizar_camino.clicked.connect(acciones._finalizar_camino)
    layout.addWidget(_ui_btn_finalizar_camino)


    return panel, ControlesRadiosMedicion(
        btn_editar_camino=_ui_btn_editar_camino,
        btn_finalizar_camino=_ui_btn_finalizar_camino,
        lista_caminos=_ui_lista_caminos,
    )


@dataclass(frozen=True)
class AccionesSplitterMedicion:
    _anomalias_modificadas: Callable
    _configuracion_pith: Callable
    _confirmar_estimacion_pith: Callable
    _datacion_activa: Callable
    _ejecutar_autodeteccion: Callable
    _fuentes_split: Callable
    _guardar_estado: Callable
    _origen_calibracion: Callable
    _programar_guardado: Callable
    _reflejar_modo_vista: Callable
    _sincronizar_mediciones: Callable
    _tipo_anomalia_activo: Callable
    _toggle_grafico: Callable


@dataclass(frozen=True)
class ControlesSplitterMedicion:
    _btn_toggle_grafico: object
    _panel_codatacion: object
    _splitter_principal: object
    _splitter_vistas: object
    _timer_autoguardado: object
    escena: object
    panel_split: object
    vista: object


def construir_splitter_principal(parent, acciones, modelo, estado_cambiado, mediciones, panel_radios, panel_codatacion):
    contenedor = QWidget()
    layout_v = QVBoxLayout(contenedor)
    layout_v.setContentsMargins(0, 0, 0, 0)
    layout_v.setSpacing(0)

    splitter = QSplitter(Qt.Orientation.Vertical)
    _ui__splitter_principal = splitter

    # -- Zona superior: imagen (+ vista dividida opcional) + lista de radios --
    splitter_sup = QSplitter(Qt.Orientation.Horizontal)

    # Splitter interno para vista principal + vista dividida
    _ui__splitter_vistas = QSplitter(Qt.Orientation.Horizontal)
    _ui_escena = QGraphicsScene()
    _ui_vista = VistaInteractiva(_ui_escena, parent, modelo=modelo,
        datacion=acciones._datacion_activa, tipo_anomalia=acciones._tipo_anomalia_activo,
        configuracion_pith=acciones._configuracion_pith, mediciones=mediciones)
    _ui_vista.estado_cambiado.connect(estado_cambiado)
    _ui_vista.modo_cambiado.connect(acciones._reflejar_modo_vista)
    _ui_vista.anomalias_modificadas.connect(acciones._anomalias_modificadas)
    _ui_vista.confirmar_pith_solicitado.connect(acciones._confirmar_estimacion_pith)
    _ui_vista.origen_calibracion_cambiado.connect(acciones._origen_calibracion)
    _ui_vista.guardado_solicitado.connect(acciones._guardar_estado)
    _ui_vista.autodeteccion_solicitada.connect(acciones._ejecutar_autodeteccion)
    _ui_vista.mediciones_actualizadas.connect(acciones._sincronizar_mediciones)
    _ui__timer_autoguardado = QTimer(parent)
    _ui__timer_autoguardado.setSingleShot(True)
    _ui__timer_autoguardado.setInterval(350)
    _ui__timer_autoguardado.timeout.connect(acciones._guardar_estado)
    _ui_vista.progreso_modificado.connect(acciones._programar_guardado)
    _ui__splitter_vistas.addWidget(_ui_vista)

    # Vista secundaria (panel dividido, oculto por defecto)
    _ui_panel_split = PanelSplit(_ui_escena, _ui_vista, acciones._fuentes_split)
    _ui_panel_split.hide()
    _ui__splitter_vistas.addWidget(_ui_panel_split)

    splitter_sup.addWidget(_ui__splitter_vistas)
    splitter_sup.addWidget(panel_radios)
    splitter_sup.setSizes([1000, 150])
    splitter.addWidget(splitter_sup)

    # -- Botón colapsar gráfico --
    _ui__btn_toggle_grafico = QPushButton("🔼 Gráfico")
    _ui__btn_toggle_grafico.setFixedHeight(18)
    _ui__btn_toggle_grafico.setStyleSheet(
        "QPushButton{font-size:10px; padding:0px 6px; border:none; "
        f"color:{SECUNDARIO_QSS}; background:transparent;}}"
        "QPushButton:hover{color:white; background:#555;}"
    )
    _ui__btn_toggle_grafico.setToolTip("Mostrar/ocultar panel de gráfico (Ctrl+G)")
    _ui__btn_toggle_grafico.clicked.connect(acciones._toggle_grafico)

    # -- Zona inferior: co-datación en vivo --
    _ui__panel_codatacion = panel_codatacion
    splitter.addWidget(_ui__panel_codatacion)
    splitter.setSizes([600, 200])
    splitter.setChildrenCollapsible(False)

    layout_v.addWidget(splitter)
    layout_v.addWidget(_ui__btn_toggle_grafico)

    return contenedor, ControlesSplitterMedicion(
        _btn_toggle_grafico=_ui__btn_toggle_grafico,
        _panel_codatacion=_ui__panel_codatacion,
        _splitter_principal=_ui__splitter_principal,
        _splitter_vistas=_ui__splitter_vistas,
        _timer_autoguardado=_ui__timer_autoguardado,
        escena=_ui_escena,
        panel_split=_ui_panel_split,
        vista=_ui_vista,
    )
