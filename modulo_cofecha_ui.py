"""
MoiCedrus — DPI · Pestaña COFECHA
=================================

Interfaz para correr el control de calidad de cofechado sobre una colección
completa de series y obtener el informe en formato .OUT.

A diferencia de la pestaña de Co-Datación —que trabaja de a una serie contra
una cronología— acá se carga la colección entera. Eso permite construir el
maestro excluyendo cada serie (leave-one-out), que es lo que hace COFECHA y
lo que da correlaciones comparables con las suyas.
"""

from __future__ import annotations

import os

import pandas as pd
import os

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QSpinBox, QCheckBox, QComboBox, QPlainTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout, QSplitter,
    QApplication, QAbstractItemView, QProgressBar,
)

import modulo_cofecha as _cof
import modulo_cofecha_salida as _sal
from modulo_codatacion import (
    leer_tucson_multi, leer_tabular, leer_columna_multi_hojas,
    RIGIDEZ_SPLINE_DEFECTO, _es_planilla,
)


class _HiloAnalisis(QThread):
    """Corre el análisis fuera del hilo de la interfaz.

    Con colecciones grandes el cálculo dura varios segundos y, si se ejecuta
    en el hilo principal, el sistema operativo marca la ventana como «no
    responde» aunque el trabajo avance. Acá se ejecuta aparte y se informa el
    progreso, de modo que la ventana sigue viva y se puede cancelar.
    """

    avance = pyqtSignal(float, str)
    terminado = pyqtSignal(object)
    fallado = pyqtSignal(str)

    def __init__(self, series, opciones, parent=None):
        super().__init__(parent)
        self._series = series
        self._opciones = opciones
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        try:
            res = _cof.analizar_coleccion(
                self._series,
                progreso=lambda f, t: self.avance.emit(f, t),
                cancelado=lambda: self._cancelar,
                **self._opciones)
            self.terminado.emit(res)
        except InterruptedError:
            self.fallado.emit("Análisis cancelado.")
        except Exception as e:
            import traceback
            self.fallado.emit(f"{e}\n\n{traceback.format_exc()}")


class PestanaCofecha(QWidget):
    """Pestaña de análisis de cofechado de una colección completa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series: dict[str, pd.Series] = {}
        self._resultado = None
        self._informe = ""
        self._hilo = None
        # Firma de las opciones con las que se calculó `_resultado`. Sirve
        # para no recalcular cuando lo único que cambia es qué partes
        # imprimir: eso es formato, no análisis.
        self._firma_resultado = None
        # Nombre del archivo cargado: COFECHA lo imprime en la portada como
        # "File of DATED series", y era lo que DPI no mostraba.
        self._nombre_archivo = ""
        self._construir_ui()

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def _construir_ui(self):
        layout = QVBoxLayout(self)

        cabecera = QLabel(
            "<b>Análisis de cofechado de la colección</b> — "
            "<span style='color:#888;'>carga todas las series juntas; el maestro "
            "se recalcula excluyendo cada serie (leave-one-out), como en COFECHA."
            "</span>")
        cabecera.setWordWrap(True)
        layout.addWidget(cabecera)

        split = QSplitter(Qt.Orientation.Horizontal)

        # ── Panel izquierdo: series y opciones ──────────────────────
        izq = QWidget()
        lay_izq = QVBoxLayout(izq)
        lay_izq.setContentsMargins(0, 0, 0, 0)

        fila_carga = QHBoxLayout()
        btn_cargar = QPushButton("📂 Cargar series…")
        btn_cargar.setToolTip(
            "Acepta .rwl y .txt en formato Tucson (con varias series en un\n"
            "mismo archivo), .csv, .tsv, .xlsx y .ods (LibreOffice).")
        btn_cargar.clicked.connect(self.cargar_series)
        fila_carga.addWidget(btn_cargar)
        btn_quitar = QPushButton("🗑 Quitar")
        btn_quitar.clicked.connect(self.quitar_seleccionadas)
        fila_carga.addWidget(btn_quitar)
        lay_izq.addLayout(fila_carga)

        self.lista = QListWidget()
        self.lista.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        lay_izq.addWidget(self.lista, 1)

        self.lbl_resumen = QLabel("Sin series cargadas.")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setStyleSheet("color:#888; font-size:11px;")
        lay_izq.addWidget(self.lbl_resumen)

        # Opciones equivalentes a las de COFECHA
        caja = QGroupBox("Opciones de la corrida")
        form = QFormLayout(caja)

        self.spin_spline = QSpinBox()
        self.spin_spline.setRange(5, 500)
        self.spin_spline.setValue(RIGIDEZ_SPLINE_DEFECTO)
        self.spin_spline.setToolTip(
            "Spline cúbico de suavizado: longitud de onda con 50% de\n"
            "respuesta. Quita la tendencia de crecimiento por edad.")
        form.addRow("Spline (años):", self.spin_spline)

        self.spin_segmento = QSpinBox()
        self.spin_segmento.setRange(10, 200)
        self.spin_segmento.setValue(50)
        self.spin_segmento.setSingleStep(10)
        form.addRow("Largo del segmento:", self.spin_segmento)

        self.spin_avance = QSpinBox()
        self.spin_avance.setRange(5, 100)
        self.spin_avance.setValue(25)
        self.spin_avance.setSingleStep(5)
        self.spin_avance.setToolTip(
            "Cuántos años avanza cada segmento respecto al anterior.\n"
            "Lo habitual es la mitad del largo del segmento.")
        form.addRow("Avance:", self.spin_avance)
        self.spin_segmento.valueChanged.connect(
            lambda v: self.spin_avance.setValue(max(5, v // 2)))

        self.chk_log = QCheckBox("Transformar a logaritmos")
        self.chk_log.setChecked(True)
        form.addRow("", self.chk_log)

        self.chk_ar = QCheckBox("Aplicar modelo autorregresivo")
        self.chk_ar.setChecked(True)
        self.chk_ar.setToolTip(
            "Quita la autocorrelación de cada serie. El orden se elige\n"
            "automáticamente por AICc, como hace COFECHA.")
        form.addRow("", self.chk_ar)

        self.combo_conf = QComboBox()
        self.combo_conf.addItem("99%", 0.01)
        self.combo_conf.addItem("95%", 0.05)
        form.addRow("Nivel de confianza:", self.combo_conf)

        self.input_partes = QComboBox()
        self.input_partes.addItem("Todas las partes (1234567)", "1234567")
        self.input_partes.addItem("Solo problemas (Parte 6)", "6")
        self.input_partes.addItem("Problemas + estadísticos (6,7)", "67")
        self.input_partes.addItem("Segmentos + problemas (5,6)", "56")
        self.input_partes.currentIndexChanged.connect(self._reformatear)
        form.addRow("Partes a imprimir:", self.input_partes)

        self.chk_robusto = QCheckBox("Maestra biweight robusta")
        self.chk_robusto.setChecked(False)
        self.chk_robusto.setToolTip(
            "Por defecto la maestra es la MEDIA ARITMÉTICA de las series\n"
            "estandarizadas, que es lo que hace COFECHA.\n\n"
            "La media biweight resiste mejor una serie aberrante, pero no es\n"
            "el comportamiento de COFECHA y obliga a recalcular la maestra\n"
            "para cada serie, así que es bastante más lenta en colecciones\n"
            "grandes.")
        form.addRow("", self.chk_robusto)

        lay_izq.addWidget(caja)

        self.btn_correr = QPushButton("▶  Analizar colección")
        self.btn_correr.setStyleSheet(
            "background-color:#5cb85c; color:white; font-weight:bold; padding:6px;")
        self.btn_correr.clicked.connect(self.analizar)
        lay_izq.addWidget(self.btn_correr)

        # Cambiar el largo del segmento, el avance, el spline o cualquier otra
        # opción invalida el resultado guardado: antes había que acordarse de
        # volver a pulsar «Correr» y el informe seguía mostrando las cifras
        # del análisis anterior, sin ninguna señal de que estaba desactualizado.
        for w in (self.spin_segmento, self.spin_avance, self.spin_spline):
            w.valueChanged.connect(self._parametros_cambiaron)
        for w in (self.chk_log, self.chk_ar, self.chk_robusto):
            w.toggled.connect(self._parametros_cambiaron)
        self.combo_conf.currentIndexChanged.connect(self._parametros_cambiaron)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setVisible(False)
        lay_izq.addWidget(self.barra)

        self.btn_nuevo = QPushButton("🗑  Nuevo análisis")
        self.btn_nuevo.setToolTip(
            "Descarta las series cargadas, el resultado y el informe,\n"
            "y deja la pestaña en blanco para empezar con otro conjunto.")
        self.btn_nuevo.clicked.connect(self.nuevo_analisis)
        lay_izq.addWidget(self.btn_nuevo)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setVisible(False)
        self.btn_cancelar.clicked.connect(self._cancelar)
        lay_izq.addWidget(self.btn_cancelar)

        split.addWidget(izq)

        # ── Panel derecho: informe ──────────────────────────────────
        der = QWidget()
        lay_der = QVBoxLayout(der)
        lay_der.setContentsMargins(0, 0, 0, 0)

        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Tipografía monoespaciada: el informe es de ancho fijo y con
        # cualquier otra fuente las columnas se desalinean.
        fuente = QFont("Monospace")
        fuente.setStyleHint(QFont.StyleHint.TypeWriter)
        fuente.setPointSize(9)
        self.texto.setFont(fuente)
        self.texto.setPlaceholderText(
            "Carga las series y pulsa «Analizar colección».\n\n"
            "El informe aparecerá acá con el formato de COFECHA.")
        lay_der.addWidget(self.texto, 1)

        fila_exp = QHBoxLayout()
        fila_exp.addStretch()
        self.btn_exportar = QPushButton("💾 Exportar informe (.OUT)")
        self.btn_exportar.clicked.connect(self.exportar)
        self.btn_exportar.setEnabled(False)
        fila_exp.addWidget(self.btn_exportar)
        self.btn_copiar = QPushButton("📋 Copiar")
        self.btn_copiar.clicked.connect(self.copiar)
        self.btn_copiar.setEnabled(False)
        fila_exp.addWidget(self.btn_copiar)
        lay_der.addLayout(fila_exp)

        split.addWidget(der)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([330, 900])
        layout.addWidget(split, 1)

    # ------------------------------------------------------------------
    # Carga de series
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Memoria de la última carpeta usada
    # ------------------------------------------------------------------
    def _ajustes(self) -> QSettings:
        return QSettings("MoiCedrus", "DPI")

    def _ultima_carpeta(self, clave: str = "cofecha/carpeta") -> str:
        ruta = self._ajustes().value(clave, "", type=str)
        return ruta if ruta and os.path.isdir(ruta) else ""

    def _recordar_carpeta(self, ruta: str, clave: str = "cofecha/carpeta"):
        """Guarda la carpeta del archivo para la próxima vez.

        Antes el diálogo abría siempre en el directorio por omisión y había
        que volver a navegar hasta la carpeta de trabajo en cada sesión.
        """
        if not ruta:
            return
        carpeta = ruta if os.path.isdir(ruta) else os.path.dirname(ruta)
        if carpeta and os.path.isdir(carpeta):
            self._ajustes().setValue(clave, carpeta)

    def cargar_series(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Cargar series de la colección", self._ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.csv *.tsv *.xlsx *.xls *.ods);;"
            "Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog)
        if not rutas:
            return
        self._recordar_carpeta(rutas[0])
        self._nombre_archivo = ", ".join(os.path.basename(r) for r in rutas[:3])
        if len(rutas) > 3:
            self._nombre_archivo += f" (+{len(rutas) - 3})"

        nuevas, errores = 0, []
        for ruta in rutas:
            try:
                nuevas += self._cargar_archivo(ruta)
            except Exception as e:
                errores.append(f"{os.path.basename(ruta)}: {e}")

        self._refrescar_lista()
        if errores:
            QMessageBox.warning(
                self, "Archivos con problemas",
                f"Se cargaron {nuevas} series.\n\nNo se pudieron leer:\n"
                + "\n".join(errores[:8]))

    def _cargar_archivo(self, ruta: str) -> int:
        """Carga un archivo (puede traer varias series) y devuelve cuántas."""
        ext = os.path.splitext(ruta)[1].lower()
        base = os.path.splitext(os.path.basename(ruta))[0]

        # Tucson multi-serie (.rwl y .txt)
        if ext in (".rwl", ".txt"):
            try:
                multi = leer_tucson_multi(ruta)
                if multi:
                    for nombre, df in multi.items():
                        self.series[nombre] = pd.to_numeric(
                            df["Ancho_mm"], errors="coerce").dropna()
                    return len(multi)
            except Exception:
                pass

        # Planillas y tabulares con varias columnas
        if _es_planilla(ext) or ext in (".csv", ".tsv"):
            try:
                hojas = leer_columna_multi_hojas(ruta)
                n = 0
                for hoja, df in hojas.items():
                    for col in df.columns:
                        s = pd.to_numeric(df[col], errors="coerce").dropna()
                        if len(s) < 10:
                            continue
                        nombre = str(col) if len(df.columns) > 1 else base
                        if hoja and len(hojas) > 1:
                            nombre = f"{hoja}_{nombre}"
                        self.series[nombre] = s
                        n += 1
                if n:
                    return n
            except Exception:
                pass

        # Una sola serie
        df, nombre = leer_tabular(ruta)
        self.series[nombre or base] = pd.to_numeric(
            df["Ancho_mm"], errors="coerce").dropna()
        return 1

    def _refrescar_lista(self):
        self.lista.clear()
        for nombre in sorted(self.series):
            s = self.series[nombre]
            it = QListWidgetItem(
                f"{nombre}   ({int(s.index.min())}–{int(s.index.max())}, "
                f"{len(s)} años)")
            it.setData(Qt.ItemDataRole.UserRole, nombre)
            self.lista.addItem(it)
        if self.series:
            p = min(int(s.index.min()) for s in self.series.values())
            u = max(int(s.index.max()) for s in self.series.values())
            total = sum(len(s) for s in self.series.values())
            self.lbl_resumen.setText(
                f"{len(self.series)} series · {p}–{u} · {total} anillos")
        else:
            self.lbl_resumen.setText("Sin series cargadas.")

    def quitar_seleccionadas(self):
        for it in self.lista.selectedItems():
            self.series.pop(it.data(Qt.ItemDataRole.UserRole), None)
        self._refrescar_lista()

    # ------------------------------------------------------------------
    # Análisis
    # ------------------------------------------------------------------
    def _opciones_actuales(self) -> dict:
        return {
            "largo_segmento": self.spin_segmento.value(),
            "avance": self.spin_avance.value(),
            "rigidez_spline": self.spin_spline.value(),
            "aplicar_log": self.chk_log.isChecked(),
            "aplicar_ar": self.chk_ar.isChecked(),
            "alfa": self.combo_conf.currentData(),
            "maestro_robusto": self.chk_robusto.isChecked(),
        }

    def _firma(self) -> tuple:
        """Identifica la corrida: series cargadas + opciones de cálculo.

        Deliberadamente NO incluye las partes a imprimir.
        """
        return (tuple(sorted(self.series)),
                tuple(sorted(self._opciones_actuales().items())))

    def analizar(self):
        if len(self.series) < 3:
            QMessageBox.warning(
                self, "Faltan series",
                "Carga al menos 3 series: el maestro se construye excluyendo "
                "la serie que se evalúa, así que con menos no queda nada con "
                "qué compararla.")
            return
        if self._hilo is not None and self._hilo.isRunning():
            return

        # Si nada cambió salvo qué partes mostrar, basta con reformatear.
        if self._resultado is not None and self._firma() == self._firma_resultado:
            self._reformatear()
            return

        self.btn_correr.setEnabled(False)
        self.btn_cancelar.setVisible(True)
        self.barra.setVisible(True)
        self.barra.setValue(0)
        self.texto.setPlainText("Analizando…")

        self._hilo = _HiloAnalisis(dict(self.series), self._opciones_actuales(),
                                   self)
        self._hilo.avance.connect(self._on_avance)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.fallado.connect(self._on_fallado)
        self._hilo.start()

    def _parametros_cambiaron(self, *_):
        """Reacciona a un cambio de opción: vuelve a analizar si ya había
        un resultado; si no, solo deja el botón listo."""
        if self._resultado is None:
            return
        if self._hilo is not None and self._hilo.isRunning():
            return
        if self._firma() == self._firma_resultado:
            return
        self._firma_resultado = None
        self.analizar()

    def nuevo_analisis(self):
        """Deja la pestaña en blanco para empezar con otro conjunto."""
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.cancelar()
            self._hilo.wait(3000)
        if self.series:
            r = QMessageBox.question(
                self, "Nuevo análisis",
                f"Se van a descartar {len(self.series)} serie(s) cargada(s) "
                "y el informe actual.\n\n¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        self.series = {}
        self._resultado = None
        self._informe = ""
        self._firma_resultado = None
        self._nombre_archivo = ""
        self.texto.setPlainText("")
        self.btn_exportar.setEnabled(False)
        self.btn_copiar.setEnabled(False)
        self.barra.setVisible(False)
        self.btn_cancelar.setVisible(False)
        self.btn_correr.setEnabled(True)
        self._refrescar_lista()

    def _cancelar(self):
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.cancelar()

    def _on_avance(self, fraccion: float, texto: str):
        self.barra.setValue(int(max(0.0, min(1.0, fraccion)) * 100))
        self.barra.setFormat(f"{texto}  %p%")

    def _on_terminado(self, resultado):
        self._resultado = resultado
        self._firma_resultado = self._firma()
        self._fin_de_corrida()
        self._reformatear()

    def _on_fallado(self, mensaje: str):
        self._fin_de_corrida()
        self.texto.setPlainText(f"No se pudo completar el análisis:\n\n{mensaje}")

    def _fin_de_corrida(self):
        self.btn_correr.setEnabled(True)
        self.btn_cancelar.setVisible(False)
        self.barra.setVisible(False)
        self._hilo = None

    def _reformatear(self):
        """Regenera el texto del informe SIN volver a calcular nada."""
        if self._resultado is None:
            return
        self._informe = _sal.generar_informe(
            self._resultado,
            titulo=(self._nombre_archivo
                    or f"Colección de {self._resultado['n_series']} series"),
            partes=self.input_partes.currentData())
        self.texto.setPlainText(self._informe)
        self.texto.moveCursor(self.texto.textCursor().MoveOperation.Start)
        self.btn_exportar.setEnabled(True)
        self.btn_copiar.setEnabled(True)

    # ------------------------------------------------------------------
    # Salida
    # ------------------------------------------------------------------
    def exportar(self):
        if not self._informe:
            return
        carpeta = self._ultima_carpeta("cofecha/carpeta_salida") \
            or self._ultima_carpeta()
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe",
            os.path.join(carpeta, "cofecha.OUT") if carpeta else "cofecha.OUT",
            "Informe COFECHA (*.OUT);;Texto (*.txt)",
            options=QFileDialog.Option.DontUseNativeDialog)
        if not ruta:
            return
        self._recordar_carpeta(ruta, "cofecha/carpeta_salida")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(self._informe)
            QMessageBox.information(self, "Guardado",
                                    f"Informe guardado en:\n{ruta}")
        except Exception as e:
            QMessageBox.warning(self, "Error al guardar", str(e))

    def copiar(self):
        if self._informe:
            QApplication.clipboard().setText(self._informe)
