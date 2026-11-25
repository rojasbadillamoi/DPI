"""Componentes de la interfaz de co-datación de DPI."""

import os
import numpy as np
import pandas as pd
import pyqtgraph as pg
from modulo_widgets import _agregar_hover_anio
from modulo_widgets import crear_selector
import dpi.ciencia.transformacion as _tr
from dpi.ciencia.estadistica import gleichlaufigkeit, glk_significance, t_baillie_pilcher, pearson
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QComboBox, QCheckBox, QSlider
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QEvent
from estilos import SECUNDARIO_QSS, color_secundario
import estilos_graficos as _gr
from dpi.ciencia.datacion import score_compuesto, alineamiento_optimo_anillos
from dpi.formatos.planillas import es_planilla
from dpi.formatos.tucson import leer_tucson_multi
from dpi.formatos.compacto import leer_formato_compacto
from dpi.formatos.wid import leer_wid
from dpi.formatos.tabular import leer_tabular, leer_como_columnas_o_tabular
from dpi.ui.series_util import _color_r, _color_tbp, _ultima_carpeta
from modulo_dialogos_series import DialogoEditarAnillos


class VentanaSkeletonPlot(QWidget):
    """Pestaña de cofechado visual tipo skeleton plot.

    Muestra la serie de REFERENCIA arriba y la serie a cofechar abajo
    (espejada), como en el método clásico de Stokes & Smiley. La serie
    flotante se desliza año a año para encontrar dónde calzan los anillos
    angostos (años marcadores). Tres vistas:

      • Skeleton: marca solo los anillos angostos respecto a sus vecinos.
      • Barras de ancho: altura ∝ ancho de cada anillo (normalizado 0–1).
      • Líneas: cada serie como una curva (a veces es más fácil de mirar).

    Tiene su PROPIO almacenamiento de series y un selector de referencia y
    flotante. Puede importar las series del panel de Co-Datación (y enviarle
    las suyas) para mantener el flujo entre ambas pestañas. Al deslizar se
    actualizan en vivo r, GLK, t-BP, n y el puntaje; permite editar los
    anillos de la flotante (probando) y aplicarlos a la serie real.
    """

    def __init__(self, parent=None, *, obtener_series=lambda: {},
                 agregar_serie=None, reemplazar_serie=None):
        super().__init__(parent)
        self._obtener_series = obtener_series
        self._agregar_serie = agregar_serie
        self._reemplazar_externa = reemplazar_serie
        self._series = {}  # nombre -> pd.Series (Ancho_mm), almacenamiento propio

        # Estado del par activo (referencia vs flotante)
        self._ref = pd.Series(dtype=float)
        self._flo = pd.Series(dtype=float)
        self._ref_nombre = ""
        self._flo_nombre = ""
        self._ref_nombre_full = ""
        self._flo_nombre_full = ""
        self._flo_original = pd.Series(dtype=float)
        self._modificado = False
        self._offset = 0
        self._off_min, self._off_max = -100, 100
        self._modo = "skeleton"  # "skeleton" | "barras" | "lineas"
        self._ventana_tabla = None
        self._mostrar_segmentos = True
        self._mostrar_marcas = True
        self._labels_overlay = []

        self._construir_ui()
        self._refrescar_selectores()
        _gr.aplicar_a_todos(self)

    def changeEvent(self, event):
        """Repinta los gráficos cuando la app cambia de tema claro/oscuro."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            _gr.aplicar_a_todos(self)

    def _serie_de_panel(self, nombre):
        df = self._obtener_series().get(nombre)
        if df is None:
            return pd.Series(dtype=float)
        return pd.to_numeric(df["Ancho_mm"], errors="coerce").dropna()

    # ── gestión de series propias y flujo con Co-Datación ─────────────────
    def _cargar_archivos(self):
        """Carga series desde archivos directamente en el skeleton,
        detectando el formato (reutiliza los mismos lectores que
        Co-Datación)."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Series", _ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.wid *.csv *.tsv *.xlsx *.xls *.ods "
            "*.cat *.cmp);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not rutas:
            return
        _ultima_carpeta(rutas[0])

        n_agregadas = 0
        n_duplicadas = 0
        errores = []
        for ruta in rutas:
            ext = os.path.splitext(ruta)[1].lower()
            base_nombre = os.path.splitext(os.path.basename(ruta))[0]
            try:
                with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                    primeras = f.read(500)

                if "=N" in primeras and "=I" in primeras:
                    series_extraidas = leer_formato_compacto(ruta)
                elif ext == ".wid":
                    df, sid = leer_wid(ruta)
                    series_extraidas = {f"🌲{sid}": df}
                elif ext in (".rwl", ".txt"):
                    primera_real = ""
                    try:
                        with open(ruta, "r", encoding="utf-8",
                                  errors="replace") as f:
                            for linea in f:
                                ln = linea.rstrip("\r\n")
                                if not ln or ln.startswith("#"):
                                    continue
                                primera_real = ln
                                break
                    except Exception:
                        primera_real = ""
                    if "\t" in primera_real:
                        series_extraidas = self._leer_tabular_via_panel(
                            ruta, base_nombre)
                    else:
                        try:
                            series_extraidas = leer_tucson_multi(ruta)
                        except Exception:
                            series_extraidas = self._leer_tabular_via_panel(
                                ruta, base_nombre)
                elif ext in (".csv", ".tsv") or es_planilla(ext):
                    series_extraidas = self._leer_tabular_via_panel(
                        ruta, base_nombre)
                else:
                    df, sid = leer_tabular(ruta)
                    series_extraidas = {sid: df}

                for id_serie, df_serie in series_extraidas.items():
                    if id_serie in self._series:
                        n_duplicadas += 1
                        continue
                    s = pd.to_numeric(
                        df_serie["Ancho_mm"], errors="coerce").dropna()
                    if s.empty:
                        continue
                    self._series[id_serie] = s
                    n_agregadas += 1
            except (ValueError, OSError) as exc:
                errores.append(f"{os.path.basename(ruta)}: {exc}")
                continue

        self._refrescar_selectores()
        if n_agregadas == 0 and not errores:
            QMessageBox.information(
                self, "Sin novedades",
                "No se agregaron series nuevas (ya estaban cargadas).")
        elif errores:
            msg = f"Se agregaron {n_agregadas} serie(s)."
            if n_duplicadas:
                msg += f"\n{n_duplicadas} duplicada(s) omitida(s)."
            msg += "\n\nErrores:\n" + "\n".join(errores)
            QMessageBox.warning(self, "Carga con errores", msg)

    def _leer_tabular_via_panel(self, ruta, base_nombre):
        return leer_como_columnas_o_tabular(ruta, base_nombre)

    def importar_de_codatacion(self):
        """Copia todas las series del panel de Co-Datación al almacenamiento
        propio del skeleton."""
        n = 0
        for nombre, df in self._obtener_series().items():
            try:
                s = pd.to_numeric(df["Ancho_mm"], errors="coerce").dropna()
            except Exception:
                continue
            if not s.empty:
                self._series[nombre] = s
                n += 1
        self._refrescar_selectores()
        if n == 0:
            QMessageBox.information(
                self, "Importar",
                "No hay series en Co-Datación para importar. Carga series "
                "en esa pestaña primero.")

    def preseleccionar_par(self, ref_nombre=None, flo_nombre=None):
        """Importa las series de Co-Datación y, si se indican, fija el par
        referencia/flotante. Lo usa el botón 'Skeleton' de Co-Datación."""
        self.importar_de_codatacion()
        if ref_nombre and ref_nombre in self._series:
            i = self.combo_ref.findData(ref_nombre)
            if i >= 0:
                self.combo_ref.blockSignals(True)
                self.combo_ref.setCurrentIndex(i)
                self.combo_ref.blockSignals(False)
        if flo_nombre and flo_nombre in self._series:
            i = self.combo_flo.findData(flo_nombre)
            if i >= 0:
                self.combo_flo.blockSignals(True)
                self.combo_flo.setCurrentIndex(i)
                self.combo_flo.blockSignals(False)
        self._aplicar_par_desde_combos(auto_rango=True)

    def _enviar_a_codatacion(self):
        """Envía las series propias del skeleton al panel de Co-Datación."""
        if self._agregar_serie is None or not self._series:
            return
        enviadas = 0
        for nombre, s in self._series.items():
            df = pd.DataFrame({"Ancho_mm": s.values},
                              index=pd.Index(s.index, name="Anio"))
            try:
                if self._agregar_serie(nombre, df):
                    enviadas += 1
            except Exception:
                pass
        QMessageBox.information(
            self, "Enviar a Co-Datación",
            f"Se enviaron {enviadas} series a Co-Datación.")

    def _refrescar_selectores(self):
        """Rellena los combos de referencia y flotante con las series propias,
        conservando la selección actual si es posible."""
        nombres = sorted(self._series.keys(),
                         key=lambda s: (not s.startswith("📚"), s))
        ref_prev = self.combo_ref.currentData()
        flo_prev = self.combo_flo.currentData()
        for combo in (self.combo_ref, self.combo_flo):
            combo.blockSignals(True)
            combo.clear()
            for nombre in nombres:
                etiqueta = nombre.replace("📚 ", "📚 ")
                combo.addItem(etiqueta, nombre)
            combo.blockSignals(False)
        self.lbl_num_series.setText(f"{len(nombres)} series")
        if not nombres:
            self._ref = pd.Series(dtype=float)
            self._flo = pd.Series(dtype=float)
            self._redibujar(auto_rango=True)
            self._actualizar_stats()
            return
        # Restaurar o elegir por defecto: 📚 (o primera) = ref; otra = flo
        if ref_prev in self._series:
            self.combo_ref.setCurrentIndex(self.combo_ref.findData(ref_prev))
        else:
            self.combo_ref.setCurrentIndex(0)
        idx_flo = 1 if len(nombres) > 1 else 0
        if flo_prev in self._series and flo_prev != self.combo_ref.currentData():
            self.combo_flo.setCurrentIndex(self.combo_flo.findData(flo_prev))
        else:
            self.combo_flo.setCurrentIndex(idx_flo)
        self._aplicar_par_desde_combos(auto_rango=True)

    def _aplicar_par_desde_combos(self, auto_rango=True):
        ref_nombre = self.combo_ref.currentData()
        flo_nombre = self.combo_flo.currentData()
        if not ref_nombre or not flo_nombre:
            return
        if ref_nombre == flo_nombre:
            # Evitar comparar una serie consigo misma si hay alternativa
            for i in range(self.combo_flo.count()):
                if self.combo_flo.itemData(i) != ref_nombre:
                    self.combo_flo.blockSignals(True)
                    self.combo_flo.setCurrentIndex(i)
                    self.combo_flo.blockSignals(False)
                    flo_nombre = self.combo_flo.currentData()
                    break
        self._set_par(ref_nombre, flo_nombre, auto_rango=auto_rango)

    def _set_par(self, ref_nombre, flo_nombre, auto_rango=True):
        """Fija el par activo (referencia, flotante), recalcula el rango de
        desfase y redibuja."""
        self._ref_nombre_full = ref_nombre
        self._flo_nombre_full = flo_nombre
        self._ref_nombre = ref_nombre.replace("📚 ", "")
        self._flo_nombre = flo_nombre.replace("📚 ", "")
        self._ref = self._series.get(ref_nombre, pd.Series(dtype=float))
        self._flo = self._series.get(flo_nombre, pd.Series(dtype=float)).copy()
        self._flo_original = self._flo.copy()
        self._marcar_modificado(False)
        # Rango de desfase basado en los años
        if not self._ref.empty and not self._flo.empty:
            ref_min, ref_max = int(self._ref.index.min()), int(self._ref.index.max())
            flo_min, flo_max = int(self._flo.index.min()), int(self._flo.index.max())
            self._off_min = ref_min - flo_max - 20
            self._off_max = ref_max - flo_min + 20
        else:
            self._off_min, self._off_max = -100, 100
        self._offset = 0
        for w in (self.spin_offset, self.slider):
            w.blockSignals(True)
            w.setRange(self._off_min, self._off_max)
            w.setValue(0)
            w.blockSignals(False)
        self._redibujar(auto_rango=auto_rango)
        self._actualizar_stats()

    def _on_ref_changed(self, _idx):
        self._aplicar_par_desde_combos(auto_rango=True)

    def _on_flo_changed(self, _idx):
        self._aplicar_par_desde_combos(auto_rango=True)

    # ── construcción de UI ────────────────────────────────────────────────
    def _construir_ui(self):
        layout = QVBoxLayout(self)

        # ── Fila de gestión de series (flujo con Co-Datación) ──
        fila_series = QHBoxLayout()
        btn_importar = QPushButton("📥 Importar de Co-Datación")
        btn_importar.setToolTip(
            "Trae al skeleton todas las series cargadas en la pestaña "
            "Co-Datación.")
        btn_importar.clicked.connect(self.importar_de_codatacion)
        fila_series.addWidget(btn_importar)

        btn_cargar = QPushButton("📂 Cargar archivo")
        btn_cargar.setToolTip(
            "Carga series desde archivos (.rwl, .txt, .csv, .xlsx, .ods, .wid…)\n"
            "directamente en el skeleton, detectando el formato.")
        btn_cargar.clicked.connect(self._cargar_archivos)
        fila_series.addWidget(btn_cargar)

        btn_enviar = QPushButton("📤 Enviar a Co-Datación")
        btn_enviar.setToolTip(
            "Envía las series del skeleton a la pestaña Co-Datación.")
        btn_enviar.clicked.connect(self._enviar_a_codatacion)
        fila_series.addWidget(btn_enviar)

        self.lbl_num_series = QLabel("0 series")
        self.lbl_num_series.setStyleSheet(f"color:{SECUNDARIO_QSS};")
        fila_series.addWidget(self.lbl_num_series)
        fila_series.addStretch()
        layout.addLayout(fila_series)

        # ── Fila de selección de par y vista ──
        controles = QHBoxLayout()
        controles.addWidget(QLabel("<b>Referencia:</b>"))
        self.combo_ref = QComboBox()
        self.combo_ref.setMinimumWidth(140)
        self.combo_ref.currentIndexChanged.connect(self._on_ref_changed)
        controles.addWidget(self.combo_ref)

        controles.addWidget(QLabel("<b>Flotante:</b>"))
        self.combo_flo = QComboBox()
        self.combo_flo.setMinimumWidth(140)
        self.combo_flo.currentIndexChanged.connect(self._on_flo_changed)
        controles.addWidget(self.combo_flo)

        controles.addWidget(QLabel("Vista:"))
        self.combo_modo = QComboBox()
        self.combo_modo.addItem("Skeleton (anillos angostos)", "skeleton")
        self.combo_modo.addItem("Barras de ancho", "barras")
        self.combo_modo.addItem("Líneas", "lineas")
        self.combo_modo.currentIndexChanged.connect(self._on_modo)
        controles.addWidget(self.combo_modo)

        controles.addWidget(QLabel("Desfase:"))
        self.spin_offset = QSpinBox()
        self.spin_offset.setRange(self._off_min, self._off_max)
        self.spin_offset.setValue(0)
        self.spin_offset.valueChanged.connect(self._on_offset_spin)
        controles.addWidget(self.spin_offset)

        self.btn_mejor = QPushButton("🔍 Mejor desfase")
        self.btn_mejor.setToolTip(
            "Busca el desfase con mayor puntaje compuesto (r·GLK·t-BP).")
        self.btn_mejor.clicked.connect(self._buscar_mejor_desfase)
        controles.addWidget(self.btn_mejor)

        self.btn_tabla_desf = QPushButton("📋 Tabla de desfases")
        self.btn_tabla_desf.setToolTip(
            "Abre una tabla ordenable con r, GLK, t-BP y puntaje de cada\n"
            "desfase. Doble clic en una fila salta a ese desfase.")
        self.btn_tabla_desf.clicked.connect(self._abrir_tabla_desfases)
        controles.addWidget(self.btn_tabla_desf)

        self.btn_editar_flo = QPushButton("✏️ Editar anillos (flotante)")
        self.btn_editar_flo.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold;")
        self.btn_editar_flo.setToolTip(
            "Agregar/quitar anillos de la serie flotante conservando el\n"
            "ancho total (para corregir anillos faltantes o falsos). Se\n"
            "prueba primero y luego se aplica a la serie real.")
        self.btn_editar_flo.clicked.connect(self._editar_flotante)
        controles.addWidget(self.btn_editar_flo)
        controles.addStretch()
        layout.addLayout(controles)

        # Slider de desplazamiento (deslizar la serie flotante)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(self._off_min, self._off_max)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_offset_slider)
        layout.addWidget(self.slider)

        # Etiqueta de estadísticos
        self.lbl_stats = QLabel("")
        self.lbl_stats.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stats.setStyleSheet(
            "QLabel{padding:6px 8px; background-color:rgba(0,0,0,40); "
            "border-radius:4px; font-family:monospace;}")
        layout.addWidget(self.lbl_stats)

        # Fila de controles de zoom/desplazamiento del gráfico
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Gráfico:"))

        self.btn_zoom_area = QPushButton("🔍 Zoom por área")
        self.btn_zoom_area.setCheckable(True)
        self.btn_zoom_area.setToolTip(
            "Activado: arrastra un rectángulo para hacer zoom en esa zona.\n"
            "Desactivado: arrastra para desplazar (pan). La rueda siempre "
            "hace zoom.")
        self.btn_zoom_area.toggled.connect(self._toggle_zoom_area)
        zoom_row.addWidget(self.btn_zoom_area)

        btn_ancho_mas = QPushButton("◄ ►")
        btn_ancho_mas.setMaximumWidth(48)
        btn_ancho_mas.setToolTip("Ensanchar: estira el eje de años (ver menos años, más detalle).")
        btn_ancho_mas.clicked.connect(lambda: self._zoom_x(0.7))
        zoom_row.addWidget(btn_ancho_mas)

        btn_ancho_menos = QPushButton("► ◄")
        btn_ancho_menos.setMaximumWidth(48)
        btn_ancho_menos.setToolTip("Comprimir: comprime el eje de años (ver más años).")
        btn_ancho_menos.clicked.connect(lambda: self._zoom_x(1.4))
        zoom_row.addWidget(btn_ancho_menos)

        btn_reset = QPushButton("⟲ Ver todo")
        btn_reset.setToolTip("Restablece la vista para ver ambas series completas.")
        btn_reset.clicked.connect(self._reset_zoom)
        zoom_row.addWidget(btn_reset)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        # Fila de simulación: toggles de superposiciones + aplicar/descartar
        sim_row = QHBoxLayout()
        self.chk_segmentos = QCheckBox("Correlación por segmentos de")
        self.chk_segmentos.setChecked(True)
        self.chk_segmentos.setToolTip(
            "Muestra el color de correlación por tramos sobre el gráfico\n"
            "(verde = correlaciona; rojo = falla), como en medición.")
        self.chk_segmentos.toggled.connect(self._on_toggle_segmentos)
        sim_row.addWidget(self.chk_segmentos)

        self.spin_segmento = QSpinBox()
        self.spin_segmento.setRange(5, 50)
        self.spin_segmento.setValue(10)
        self.spin_segmento.setSuffix(" años")
        self.spin_segmento.setToolTip("Largo de cada segmento de correlación.")
        self.spin_segmento.valueChanged.connect(
            lambda _: self._redibujar(auto_rango=False))
        sim_row.addWidget(self.spin_segmento)

        sim_row.addSpacing(10)
        sim_row.addWidget(QLabel("Correlación:"))
        # Mismo selector que en Medición: sin él, esta ventana calculaba
        # siempre con diferencias-log mientras el panel de Co-Datación usaba
        # el método de COFECHA, y las dos r del mismo par no coincidían.
        self.combo_metodo_corr = crear_selector(self, _tr.DIFFLOG)
        self.combo_metodo_corr.currentIndexChanged.connect(
            lambda *_: (self._actualizar_stats(), self._redibujar()))
        sim_row.addWidget(self.combo_metodo_corr)

        sim_row.addSpacing(12)
        self.chk_marcas = QCheckBox("Marcar faltante/sobrante")
        self.chk_marcas.setChecked(True)
        self.chk_marcas.setToolTip(
            "Marca dónde el alineamiento sugiere corregir anillos.")
        self.chk_marcas.toggled.connect(self._on_toggle_marcas)
        sim_row.addWidget(self.chk_marcas)

        lbl_leyenda = QLabel(
            "<span style='color:#e74c3c;'>▮ falta (agregar)</span> "
            "<span style='color:#17a2b8;'>▮ sobra (quitar)</span>")
        lbl_leyenda.setTextFormat(Qt.TextFormat.RichText)
        lbl_leyenda.setStyleSheet("font-size:11px;")
        sim_row.addWidget(lbl_leyenda)

        sim_row.addStretch()

        self.lbl_modif = QLabel("")
        self.lbl_modif.setStyleSheet("color:#e67e22; font-weight:bold;")
        sim_row.addWidget(self.lbl_modif)

        self.btn_aplicar_real = QPushButton("✅ Aplicar a serie real")
        self.btn_aplicar_real.setStyleSheet(
            "background-color:#5cb85c; color:white; font-weight:bold;")
        self.btn_aplicar_real.setToolTip(
            "Guarda los cambios probados (anillos agregados/quitados) en la\n"
            "serie real del panel de co-datación.")
        self.btn_aplicar_real.setEnabled(False)
        self.btn_aplicar_real.clicked.connect(self._aplicar_a_serie_real)
        sim_row.addWidget(self.btn_aplicar_real)

        self.btn_descartar = QPushButton("↺ Descartar cambios")
        self.btn_descartar.setToolTip(
            "Revierte la serie flotante a como estaba, descartando las "
            "pruebas.")
        self.btn_descartar.setEnabled(False)
        self.btn_descartar.clicked.connect(self._descartar_cambios)
        sim_row.addWidget(self.btn_descartar)
        layout.addLayout(sim_row)

        # Gráfico: referencia arriba, flotante abajo (espejada)
        self.grafico = pg.PlotWidget()
        _agregar_hover_anio(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.setLabel("bottom", "Año")
        self.grafico.setLabel("left", "Índice (0–1, espejado)")
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))
        # Interacción: rueda hace zoom, arrastrar hace pan por defecto.
        self._viewbox = self.grafico.getViewBox()
        self._viewbox.setMouseEnabled(x=True, y=True)
        # Etiquetas de superposición (r por segmento, marcas): se guardan
        # para reubicarlas en el borde visible cuando cambia el zoom, de modo
        # que sigan viéndose. Cada entrada: (item, x, "top"|"bottom").
        self._labels_overlay = []
        self._viewbox.sigRangeChanged.connect(self._reposicionar_overlays)
        layout.addWidget(self.grafico, 1)

    # ── transformaciones ──────────────────────────────────────────────────
    def _normalizada(self, serie):
        """Ancho estandarizado al rango 0–1 (min–máx), para que ambas series
        —de distinta escala en mm— sean comparables y queden acotadas."""
        s = serie.astype(float)
        lo, hi = s.min(), s.max()
        if hi > lo:
            return (s - lo) / (hi - lo)
        return s * 0.0 + 0.5

    def metodo_correlacion(self) -> str:
        combo = getattr(self, "combo_metodo_corr", None)
        if combo is None:
            return _tr.DIFFLOG
        return combo.currentData() or _tr.DIFFLOG

    def _skeleton(self, serie):
        """Marca de anillos angostos: altura ∝ cuánto más angosto es el
        anillo respecto al promedio de sus vecinos (ventana 3). Solo valores
        positivos (angostos); los anchos quedan en ~0. Rango 0–1 (los
        anillos más angostos se acercan a 1)."""
        s = serie.astype(float)
        if len(s) < 3:
            return s * 0.0
        local = s.rolling(3, center=True, min_periods=1).mean()
        rel = (local - s) / local.replace(0, np.nan)
        rel = rel.clip(lower=0, upper=1).fillna(0.0)
        return rel

    # ── dibujo ────────────────────────────────────────────────────────────
    def _redibujar(self, auto_rango=False):
        self.grafico.clear()
        self._labels_overlay = []
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))

    # ── dibujo ────────────────────────────────────────────────────────────
    def _redibujar(self, auto_rango=False):
        self.grafico.clear()
        self._labels_overlay = []
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))

        # Sin par seleccionado: no hay nada que dibujar.
        if self._ref.empty or self._flo.empty:
            aviso = pg.TextItem(
                "Importa o selecciona una referencia y una flotante.",
                color="#888888", anchor=(0.5, 0.5))
            aviso.setPos(0, 0)
            self.grafico.addItem(aviso)
            if auto_rango:
                self.grafico.autoRange()
            return

        if self._modo == "skeleton":
            ref_h = self._skeleton(self._ref)
            flo_h = self._skeleton(self._flo)
        else:
            ref_h = self._normalizada(self._ref)
            flo_h = self._normalizada(self._flo)

        xr = ref_h.index.to_numpy(dtype=float)
        yr = ref_h.to_numpy(dtype=float)
        xf = flo_h.index.to_numpy(dtype=float) + self._offset

        if self._modo == "lineas":
            # Vista de líneas: referencia arriba, flotante abajo (espejada),
            # como curvas en vez de barras (a veces más fácil de mirar).
            yf = -flo_h.to_numpy(dtype=float)
            self.grafico.plot(xr, yr, pen=pg.mkPen("#3388FF", width=2))
            self.grafico.plot(xf, yf, pen=pg.mkPen("#FF8C00", width=2))
        else:
            # Referencia: barras hacia ARRIBA en sus años
            self.grafico.addItem(pg.BarGraphItem(
                x=xr, height=yr, width=0.8, brush="#3388FF", pen=None))
            # Flotante: barras hacia ABAJO, desplazadas por el offset
            yf = -flo_h.to_numpy(dtype=float)
            self.grafico.addItem(pg.BarGraphItem(
                x=xf, height=yf, width=0.8, brush="#FF8C00", pen=None))

        # Etiquetas arriba/abajo
        ti = pg.TextItem(self._ref_nombre, color="#3388FF", anchor=(0, 1))
        ti.setPos(xr.min() if len(xr) else 0, max(yr.max() if len(yr) else 1, 1))
        self.grafico.addItem(ti)
        tf = pg.TextItem(self._flo_nombre, color="#FF8C00", anchor=(0, 0))
        tf.setPos(xf.min() if len(xf) else 0, min(yf.min() if len(yf) else -1, -1))
        self.grafico.addItem(tf)

        # Superposiciones en vivo: correlación por segmentos y marcas de
        # anillos faltantes/sobrantes en el desfase actual.
        if self._mostrar_segmentos:
            self._dibujar_correlacion_segmentos()
        if self._mostrar_marcas:
            self._dibujar_marcas_correcciones()

        # Solo auto-ajustar la vista al inicio o al cambiar de modo/reset.
        # Al DESLIZAR el desfase NO se auto-ajusta, para que la serie
        # flotante se mueva dentro de la ventana con zoom que fijó el usuario
        # (que es justo lo que se necesita para cofechar deslizando).
        if auto_rango:
            self.grafico.autoRange()

    def _dibujar_correlacion_segmentos(self):
        """Dibuja el color de correlación por tramos sobre el gráfico (verde
        = correlaciona, rojo = falla), como en el módulo de medición. El
        largo del segmento lo fija el usuario (spin_segmento). Se recalcula
        en vivo. Las etiquetas r se guardan para reubicarlas al hacer zoom."""
        ref = self._ref
        flo = self._flo.copy()
        flo.index = flo.index + self._offset
        metodo = self.metodo_correlacion()
        la = _tr.transformar(ref, metodo)
        lb = _tr.transformar(flo, metodo)
        overlap = sorted(la.index.intersection(lb.index))
        if len(overlap) < 6:
            return
        paso = self.spin_segmento.value()

        def _rgba(r):
            if r >= 0.50: return (46, 204, 113, 45)
            if r >= 0.35: return (92, 184, 92, 45)
            if r >= 0.15: return (240, 173, 78, 45)
            return (217, 83, 79, 55)

        def _hex(r):
            if r >= 0.50: return "#2ecc71"
            if r >= 0.35: return "#5cb85c"
            if r >= 0.15: return "#f0ad4e"
            return "#d9534f"

        seg_ini = overlap[0]
        while seg_ini < overlap[-1]:
            seg_fin = seg_ini + paso
            seg = [y for y in overlap if seg_ini <= y < seg_fin]
            if len(seg) >= 4:
                a = la.loc[seg].to_numpy()
                b = lb.loc[seg].to_numpy()
                if np.std(a) > 1e-9 and np.std(b) > 1e-9:
                    r = pearson(a, b)
                    if np.isfinite(r):
                        reg = pg.LinearRegionItem(
                            values=[seg_ini, seg_fin], movable=False,
                            brush=pg.mkBrush(*_rgba(r)), pen=pg.mkPen(None))
                        reg.setZValue(-20)
                        self.grafico.addItem(reg)
                        # Etiqueta: r y el tramo de años (para saber el largo)
                        txt = pg.TextItem(
                            html=f"<span style='color:{_hex(r)}; font-size:8pt; "
                                 f"font-weight:bold; background:#000;'>&nbsp;"
                                 f"r={r:+.2f}<br>{int(seg[0])}–{int(seg[-1])}"
                                 f"&nbsp;</span>",
                            anchor=(0.5, 0.0))
                        cx = (seg_ini + seg_fin) / 2.0
                        txt.setZValue(50)
                        self.grafico.addItem(txt)
                        self._labels_overlay.append((txt, cx, "top"))
            seg_ini += paso
        self._reposicionar_overlays()

    def _dibujar_marcas_correcciones(self):
        """Dibuja líneas verticales donde el alineamiento óptimo sugiere que
        FALTA un anillo (rojo) o SOBRA uno (celeste), en el desfase actual.
        La etiqueta indica el año y cuántos anillos (delta)."""
        try:
            res = alineamiento_optimo_anillos(
                self._flo, self._ref, shift_base=self._offset,
                max_correcciones=10, penalizacion=3.0)
        except Exception:
            return
        if not res:
            return
        for c in res.get("correcciones", []):
            x = c.get("anio_calendario")
            if x is None:
                continue
            delta = int(c.get("delta", 1) or 1)
            if c.get("tipo") == "faltante":
                color = "#e74c3c"
                etiqueta = (f"falta {delta} anillo{'s' if delta > 1 else ''}"
                            f"<br>~{int(x)} (agregar)")
            else:
                color = "#17a2b8"
                etiqueta = (f"sobra {delta} anillo{'s' if delta > 1 else ''}"
                            f"<br>~{int(x)} (quitar)")
            linea = pg.InfiniteLine(
                pos=x, angle=90,
                pen=pg.mkPen(color, width=2, style=Qt.PenStyle.DashLine))
            linea.setZValue(40)
            self.grafico.addItem(linea)
            et = pg.TextItem(
                html=f"<span style='color:{color}; font-size:8pt; "
                     f"background:#000;'>&nbsp;{etiqueta}&nbsp;</span>",
                anchor=(0.5, 1.0))
            et.setZValue(51)
            self.grafico.addItem(et)
            self._labels_overlay.append((et, x, "bottom"))
        self._reposicionar_overlays()

    def _reposicionar_overlays(self):
        """Reubica las etiquetas de correlación (arriba) y de marcas (abajo)
        en el borde visible actual, para que sigan viéndose al hacer zoom o
        pan (las etiquetas están en coordenadas de datos y si no se reubican,
        salen de la vista)."""
        if not getattr(self, "_labels_overlay", None):
            return
        try:
            (y0, y1) = self._viewbox.viewRange()[1]
        except Exception:
            return
        margen = (y1 - y0) * 0.02
        for item, x, pos in self._labels_overlay:
            try:
                if pos == "top":
                    item.setPos(x, y1 - margen)
                else:
                    item.setPos(x, y0 + margen)
            except Exception:
                pass

    # ── estadísticos en el desfase actual ─────────────────────────────────
    def _stats_offset(self, offset):
        ref = self._ref
        flo = self._flo.copy()
        flo.index = flo.index + offset
        ov = ref.index.intersection(flo.index)
        n = len(ov)
        if n < 5:
            return None
        a = ref.loc[ov]
        b = flo.loc[ov]
        # r con el método elegido en el selector de la barra
        metodo = self.metodo_correlacion()
        la = _tr.transformar(a, metodo)
        lb = _tr.transformar(b, metodo)
        cidx = la.index.intersection(lb.index)
        if len(cidx) >= 5 and la.loc[cidx].std() > 0 and lb.loc[cidx].std() > 0:
            r = pearson(la.loc[cidx], lb.loc[cidx])
        else:
            r = float("nan")
        glk, n_glk = gleichlaufigkeit(a, b, min_overlap=5)
        t_bp, _, _ = t_baillie_pilcher(a, b, min_overlap=5)
        return r, glk, t_bp, n, n_glk

    def _actualizar_stats(self):
        if self._ref.empty or self._flo.empty:
            self.lbl_stats.setText(
                f"<span style='color:{color_secundario()};'>Selecciona una referencia y una "
                "flotante para ver la correlación.</span>")
            return
        res = self._stats_offset(self._offset)
        if res is None:
            self.lbl_stats.setText(
                "<span style='color:#d9534f;'>Solape insuficiente en este "
                "desfase (mín. 5 años).</span>")
            return
        r, glk, t_bp, n, n_glk = res
        sc = score_compuesto(r, glk, t_bp)
        sig = glk_significance(glk, n_glk)

        def f(v, dec=2):
            return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

        self.lbl_stats.setText(
            f"<b>Desfase {self._offset:+d}</b> &nbsp;|&nbsp; "
            f"n={n} &nbsp;|&nbsp; "
            f"r=<b style='color:{_color_r(r)}'>{f(r)}</b> &nbsp;|&nbsp; "
            f"GLK={f(glk*100,0)}% ({sig}) &nbsp;|&nbsp; "
            f"t-BP=<b style='color:{_color_tbp(t_bp)}'>{f(t_bp,1)}</b> "
            f"&nbsp;|&nbsp; puntaje={f(sc)}")

    # ── eventos ───────────────────────────────────────────────────────────
    def _on_modo(self, _idx):
        self._modo = self.combo_modo.currentData()
        self._redibujar(auto_rango=True)

    def _on_offset_spin(self, val):
        self._offset = int(val)
        self.slider.blockSignals(True)
        self.slider.setValue(self._offset)
        self.slider.blockSignals(False)
        self._redibujar()
        self._actualizar_stats()

    def _on_offset_slider(self, val):
        self._offset = int(val)
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(self._offset)
        self.spin_offset.blockSignals(False)
        self._redibujar()
        self._actualizar_stats()

    def _toggle_zoom_area(self, activo):
        """Activa el modo 'zoom por área' (arrastrar un rectángulo hace zoom)
        o vuelve al modo desplazamiento (arrastrar mueve el gráfico)."""
        modo = (pg.ViewBox.RectMode if activo else pg.ViewBox.PanMode)
        self._viewbox.setMouseMode(modo)

    def _zoom_x(self, factor):
        """Estira (factor<1) o comprime (factor>1) el eje de años alrededor
        del centro visible, sin tocar el eje vertical."""
        self._viewbox.scaleBy((factor, 1.0))

    def _reset_zoom(self):
        """Restablece la vista para ver ambas series completas."""
        self._redibujar(auto_rango=True)

    # ── edición de anillos (de prueba; se aplica a la real aparte) ────────
    def reemplazar_serie(self, nombre, df_nuevo, regraficar=True):
        """Recibe la serie editada desde DialogoEditarAnillos. La edición es
        DE PRUEBA: modifica solo la copia de trabajo del skeleton (para ver
        cómo queda la correlación) SIN tocar la serie real del panel. Los
        cambios se comprometen con 'Aplicar a serie real'."""
        serie = pd.to_numeric(df_nuevo["Ancho_mm"], errors="coerce").dropna()
        if nombre == self._flo_nombre_full:
            self._flo = serie
            self._marcar_modificado(True)
        elif nombre == self._ref_nombre_full:
            self._ref = serie
            self._marcar_modificado(True)
        self._redibujar(auto_rango=False)
        self._actualizar_stats()
        if self._ventana_tabla is not None and self._ventana_tabla.isVisible():
            self._poblar_tabla_desfases()

    def _marcar_modificado(self, v: bool):
        self._modificado = v
        self.btn_aplicar_real.setEnabled(v)
        self.btn_descartar.setEnabled(v)
        self.lbl_modif.setText("● Cambios sin aplicar" if v else "")

    def _aplicar_a_serie_real(self):
        """Compromete la copia de trabajo a la serie real: actualiza el
        almacenamiento propio del skeleton y, si la serie también existe en
        Co-Datación, la propaga allí."""
        df = pd.DataFrame({"Ancho_mm": self._flo.values},
                          index=pd.Index(self._flo.index, name="Anio"))
        # Almacenamiento propio del skeleton
        self._series[self._flo_nombre_full] = self._flo.copy()
        # Propagar a Co-Datación si esa serie existe allí
        propagado = ""
        if self._reemplazar_externa is not None and self._flo_nombre_full in self._obtener_series():
            self._reemplazar_externa(self._flo_nombre_full, df, regraficar=True)
            propagado = " y en Co-Datación"
        self._flo_original = self._flo.copy()
        self._marcar_modificado(False)
        QMessageBox.information(
            self, "Aplicado",
            f"Los cambios se guardaron en la serie '{self._flo_nombre}'"
            f"{propagado}.")

    def _editar_flotante(self):
        """Abre el editor de anillos (con conservación de ancho) para la
        serie flotante."""
        if self._flo.empty:
            QMessageBox.information(
                self, "Editar anillos",
                "Primero selecciona una serie flotante.")
            return
        df = pd.DataFrame({"Ancho_mm": self._flo.values},
                          index=pd.Index(self._flo.index, name="Anio"))
        dlg = DialogoEditarAnillos(df, self._flo_nombre_full, self.reemplazar_serie, parent=self)
        dlg.exec()

    def _descartar_cambios(self):
        """Revierte la copia de trabajo a la serie comprometida."""
        self._flo = self._flo_original.copy()
        self._marcar_modificado(False)
        self._redibujar(auto_rango=False)
        self._actualizar_stats()
        if self._ventana_tabla is not None and self._ventana_tabla.isVisible():
            self._poblar_tabla_desfases()

    def _on_toggle_segmentos(self, v):
        self._mostrar_segmentos = bool(v)
        self._redibujar(auto_rango=False)

    def _on_toggle_marcas(self, v):
        self._mostrar_marcas = bool(v)
        self._redibujar(auto_rango=False)

    # ── tabla de desfases (ventana modificable) ───────────────────────────
    def _abrir_tabla_desfases(self):
        if self._ventana_tabla is None:
            self._ventana_tabla = QDialog(self)
            self._ventana_tabla.setWindowTitle("Desfases — r, GLK, t-BP, puntaje")
            self._ventana_tabla.resize(560, 460)
            lay = QVBoxLayout(self._ventana_tabla)
            lay.addWidget(QLabel(
                "Doble clic en una fila para saltar a ese desfase. "
                "Clic en un encabezado para ordenar."))
            self._tabla_desf = QTableWidget(0, 6)
            self._tabla_desf.setHorizontalHeaderLabels(
                ["Desfase", "n", "r", "GLK", "t-BP", "Puntaje"])
            self._tabla_desf.setSortingEnabled(True)
            self._tabla_desf.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            self._tabla_desf.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            self._tabla_desf.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            self._tabla_desf.itemDoubleClicked.connect(
                self._on_doble_clic_tabla)
            lay.addWidget(self._tabla_desf)
        self._poblar_tabla_desfases()
        self._ventana_tabla.show()
        self._ventana_tabla.raise_()

    def _poblar_tabla_desfases(self):
        filas = []
        for off in range(self._off_min, self._off_max + 1):
            res = self._stats_offset(off)
            if res is None:
                continue
            r, glk, t_bp, n, _ = res
            sc = score_compuesto(r, glk, t_bp)
            filas.append((off, n, r, glk, t_bp, sc))
        if not filas:
            return
        filas.sort(key=lambda f: (f[5] if np.isfinite(f[5]) else -np.inf),
                   reverse=True)

        t = self._tabla_desf
        t.setSortingEnabled(False)
        t.setRowCount(len(filas))
        for i, (off, n, r, glk, t_bp, sc) in enumerate(filas):
            vals = [off, n, round(r, 3), round(glk * 100, 1),
                    round(t_bp, 2), round(sc, 3)]
            for j, v in enumerate(vals):
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, v)
                if j == 0:
                    it.setData(Qt.ItemDataRole.UserRole, int(off))
                if j == 2:
                    it.setForeground(QColor(_color_r(r)))
                elif j == 4:
                    it.setForeground(QColor(_color_tbp(t_bp)))
                t.setItem(i, j, it)
        t.setSortingEnabled(True)

    def _on_doble_clic_tabla(self, item):
        fila = item.row()
        celda_off = self._tabla_desf.item(fila, 0)
        if celda_off is None:
            return
        off = celda_off.data(Qt.ItemDataRole.UserRole)
        if off is None:
            off = int(celda_off.text())
        self.spin_offset.setValue(int(off))  # dispara redibujo + stats

    def _buscar_mejor_desfase(self):
        lo, hi = self._off_min, self._off_max
        mejor_sc, mejor_off = -np.inf, 0
        for off in range(lo, hi + 1):
            res = self._stats_offset(off)
            if res is None:
                continue
            r, glk, t_bp, n, _ = res
            sc = score_compuesto(r, glk, t_bp)
            if np.isfinite(sc) and sc > mejor_sc:
                mejor_sc, mejor_off = sc, off
        if np.isfinite(mejor_sc):
            self.spin_offset.setValue(mejor_off)  # dispara redibujo y stats
        else:
            QMessageBox.information(
                self, "Sin solape",
                "No se encontró ningún desfase con solape suficiente.")
