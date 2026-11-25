"""Componentes de la interfaz de co-datación de DPI."""

import os
import csv
import numpy as np
import pandas as pd
import pyqtgraph as pg
from modulo_widgets import _agregar_hover_anio
from dpi.ciencia.estadistica import gleichlaufigkeit, t_baillie_pilcher, pearson
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QApplication
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from estilos import color_secundario
import estilos_graficos as _gr
from dpi.ciencia.datacion import score_compuesto
from dpi.formatos.exportacion import asegurar_extension
from dpi.ui.series_util import _color_compuesto, _color_glk, _color_r, _color_tbp, _ultima_carpeta
from modulo_dialogos_series import DialogoAlineamientoAnillos


class VentanaTablaOffset(QDialog):
    """Tabla detallada con r, GLK y t-BP por cada desfase.

    Si se pasan `serie_a` y `serie_b` (las series transformadas usadas
    en el cálculo), agrega ARRIBA de la tabla un gráfico apropiado al
    tipo de serie:
      - Serie FLOTANTE (año mínimo < 500): gráfico de barras del
        puntaje compuesto por cada desfase. Permite ver de un vistazo
        dónde está el pico que indica la posición candidata.
      - Serie FECHADA (año mínimo ≥ 500): gráfico de correlación
        móvil con ventanas deslizantes año a año, aplicando el mejor
        desfase. Permite identificar zonas problemáticas dentro de la
        serie (años donde el cofechado se debilita).
    """

    def __init__(self, shifts, rs, glks=None, tbps=None, ns=None,
                 serie_a=None, serie_b=None, parent=None,
                 nombre_serie=None, *, obtener_serie=None, aplicar_desfase=None, reemplazar=None):
        super().__init__(parent)
        self.setWindowTitle("Resultados de Análisis de Desfases")
        self._nombre_serie = nombre_serie
        self._obtener_serie = obtener_serie
        self._aplicar_desfase = aplicar_desfase
        self._reemplazar = reemplazar
        # Si vamos a mostrar gráfico, necesitamos más alto
        if serie_a is not None and serie_b is not None and len(shifts) > 0:
            self.resize(720, 720)
        else:
            self.resize(560, 540)
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "Resultados ordenados por <b>puntaje compuesto</b> descendente. "
            "El puntaje combina las tres métricas (r × GLK × t-BP)^(1/3) — "
            "es lo más confiable para identificar la fecha verdadera."
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        glks = glks if glks is not None else [float("nan")] * len(shifts)
        tbps = tbps if tbps is not None else [float("nan")] * len(shifts)
        ns   = ns   if ns   is not None else [0] * len(shifts)

        scores = [score_compuesto(r, g, t) for r, g, t in zip(rs, glks, tbps)]

        # Guardar para el botón de alineamiento óptimo. El mejor desfase es
        # el de mayor puntaje compuesto (centro de la banda de búsqueda).
        self._serie_a = serie_a
        self._serie_b = serie_b
        self._mejor_shift_detalle = 0
        if shifts:
            scores_validos = [(i, s) for i, s in enumerate(scores)
                              if np.isfinite(s)]
            if scores_validos:
                self._mejor_shift_detalle = shifts[
                    max(scores_validos, key=lambda x: x[1])[0]]
            else:
                self._mejor_shift_detalle = shifts[int(np.argmax(rs))]

        # ── Gráfico opcional ──────────────────────────────────────────
        if serie_a is not None and serie_b is not None and len(shifts) > 0:
            self._agregar_grafico_detalle(
                layout, shifts, rs, glks, tbps, scores,
                serie_a, serie_b,
            )

        # Año de término base (último año de la serie sin desfase). Si hay
        # serie_a disponible, por cada desfase mostramos el año en que
        # terminaría la serie: útil para validar contra la presencia de
        # corteza (el término debería ser cercano al año de colecta).
        anio_max_base = None
        if serie_a is not None and len(serie_a) > 0:
            try:
                anio_max_base = int(serie_a.index.max())
            except (ValueError, TypeError):
                anio_max_base = None

        n_cols = 7 if anio_max_base is not None else 6
        self.tabla = QTableWidget(len(shifts), n_cols)
        if anio_max_base is not None:
            self.tabla.setHorizontalHeaderLabels(
                ["Desfase", "Año término", "Puntaje", "r", "GLK", "t-BP", "n"])
        else:
            self.tabla.setHorizontalHeaderLabels(
                ["Desfase", "Puntaje", "r", "GLK", "t-BP", "n"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setSortingEnabled(False)
        # Selección por fila para poder elegir un desfase y correr el
        # alineamiento desde ahí (no solo desde el mejor).
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        import datetime as _dt
        _anio_actual = _dt.datetime.now().year

        for row, (sh, r, g, t, n, sc) in enumerate(zip(shifts, rs, glks, tbps, ns, scores)):
            c = 0
            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(sh))
            self.tabla.setItem(row, c, it); c += 1

            # Columna Año término (solo si tenemos la serie)
            if anio_max_base is not None:
                anio_fin = anio_max_base + int(sh)
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, int(anio_fin))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if anio_fin > _anio_actual:
                    # Posición imposible: término en el futuro
                    it.setForeground(QColor("#e67e22"))
                    f = it.font(); f.setBold(True); it.setFont(f)
                    it.setToolTip(
                        f"El término ({anio_fin}) supera el año actual "
                        f"({_anio_actual}): posición imposible.")
                self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(sc, 3)) if np.isfinite(sc) else 0.0)
            it.setBackground(QColor(_color_compuesto(sc)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(r, 3)) if np.isfinite(r) else 0.0)
            it.setBackground(QColor(_color_r(r)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(g, 3)) if np.isfinite(g) else 0.0)
            it.setBackground(QColor(_color_glk(g)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(t, 2)) if np.isfinite(t) else 0.0)
            it.setBackground(QColor(_color_tbp(t)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(n))
            self.tabla.setItem(row, c, it); c += 1

        self.tabla.setSortingEnabled(True)
        # Ordenar por Puntaje descendente (columna 2 si hay año término, 1 si no)
        col_puntaje = 2 if anio_max_base is not None else 1
        self.tabla.sortItems(col_puntaje, Qt.SortOrder.DescendingOrder)
        layout.addWidget(self.tabla)

        fila_btns = QHBoxLayout()
        btn_copiar = QPushButton("📋 Copiar Todo")
        btn_copiar.clicked.connect(self.copiar_portapapeles)
        fila_btns.addWidget(btn_copiar)
        btn_exportar = QPushButton("💾 Exportar a CSV")
        btn_exportar.clicked.connect(self.exportar_csv)
        fila_btns.addWidget(btn_exportar)
        # Botón de alineamiento óptimo (anillos faltantes/sobrantes).
        # Solo tiene sentido si tenemos las series para descomponer.
        if self._serie_a is not None and self._serie_b is not None:
            btn_alinear = QPushButton("🧬 Buscar anillos faltantes/sobrantes")
            btn_alinear.setStyleSheet(
                "QPushButton{background-color:#8e44ad; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#9b59b6;}")
            btn_alinear.setToolTip(
                "Descompone la serie por programación dinámica para detectar "
                "dónde podría faltar o sobrar un anillo, buscando el "
                "alineamiento óptimo con la cronología.\n\n"
                "Selecciona primero una fila (un desfase) para analizar desde "
                "esa posición. Sin selección, usa el mejor desfase.")
            btn_alinear.clicked.connect(self._abrir_alineamiento)
            fila_btns.addWidget(btn_alinear)

        # Botón para aplicar el desfase SELECCIONADO a la serie.
        if self._obtener_serie is not None and self._aplicar_desfase is not None and self._nombre_serie is not None:
            btn_aplicar = QPushButton("✅ Aplicar desfase seleccionado")
            btn_aplicar.setStyleSheet(
                "QPushButton{background-color:#27ae60; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#2ecc71;}")
            btn_aplicar.setToolTip(
                "Aplica a la serie el desfase de la fila seleccionada (cambia "
                "su año de inicio) y la grafica re-datada en el panel "
                "principal.\n\nSelecciona una fila primero. Sin selección, "
                "usa el mejor desfase.")
            btn_aplicar.clicked.connect(self._aplicar_desfase_seleccionado)
            fila_btns.addWidget(btn_aplicar)

        layout.addLayout(fila_btns)

    def _aplicar_desfase_seleccionado(self):
        """Aplica a la serie el desfase de la fila seleccionada, re-datándola
        en el panel principal."""
        import datetime as _dt
        shift = self._mejor_shift_detalle
        seleccion = self.tabla.selectionModel().selectedRows()
        if seleccion:
            cell = self.tabla.item(seleccion[0].row(), 0)
            if cell is not None:
                try:
                    shift = int(cell.data(Qt.ItemDataRole.DisplayRole))
                except (ValueError, TypeError):
                    pass

        df = self._obtener_serie(self._nombre_serie)
        if df is None or df.empty:
            QMessageBox.warning(self, "Error",
                                "No se encontró la serie en el panel.")
            return
        nuevo_ini = int(df.index.min()) + shift
        nuevo_fin = int(df.index.max()) + shift
        anio_actual = _dt.datetime.now().year
        aviso = ""
        if nuevo_fin > anio_actual:
            aviso = (f"\n\n⚠️ El año de término ({nuevo_fin}) supera el año "
                     f"actual ({anio_actual}): datación probablemente espuria.")

        signo = f"+{shift}" if shift >= 0 else str(shift)
        resp = QMessageBox.question(
            self, "Aplicar desfase",
            f"Aplicar desfase {signo} a la serie '{self._nombre_serie}':\n"
            f"quedaría en los años {nuevo_ini}–{nuevo_fin}.{aviso}\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        if self._aplicar_desfase(self._nombre_serie, shift):
            QMessageBox.information(
                self, "Listo",
                f"Serie '{self._nombre_serie}' re-datada a "
                f"{nuevo_ini}–{nuevo_fin}.")
            self.accept()
        else:
            QMessageBox.information(
                self, "Sin cambios",
                "El desfase es 0; la serie ya está en esa posición.")

    def _abrir_alineamiento(self):
        """Abre el diálogo de alineamiento óptimo (anillos faltantes/
        sobrantes). Usa el desfase de la fila SELECCIONADA en la tabla
        como punto de partida; si no hay fila seleccionada, usa el mejor
        desfase. Así el usuario puede explorar el alineamiento desde
        cualquier posición candidata, no solo la mejor."""
        shift_base = self._mejor_shift_detalle
        seleccion = self.tabla.selectionModel().selectedRows()
        if seleccion:
            row = seleccion[0].row()
            cell = self.tabla.item(row, 0)  # columna 0 = Desfase
            if cell is not None:
                val = cell.data(Qt.ItemDataRole.DisplayRole)
                try:
                    shift_base = int(val)
                except (ValueError, TypeError):
                    pass
        nombre = self.windowTitle().replace(
            "Resultados de Análisis de Desfases", "serie")
        dlg = DialogoAlineamientoAnillos(
            self._serie_a, self._serie_b, shift_base,
            nombre, parent=self,
            penalizacion=3.0, max_correcciones=10,  # exploratorio por defecto
            obtener_serie=self._obtener_serie, reemplazar=self._reemplazar,
            nombre_real=self._nombre_serie,
        )
        dlg.exec()

    def _agregar_grafico_detalle(self, layout, shifts, rs, glks, tbps,
                                  scores, serie_a, serie_b):
        """Agrega un gráfico apropiado al tipo de serie arriba de la tabla.

        Detecta automáticamente si la serie es flotante o fechada según
        el año mínimo de la serie y dibuja el gráfico correspondiente:

          - Año mínimo < 500 → FLOTANTE → gráfico de barras del puntaje
            compuesto vs desfase. La barra más alta muestra la posición
            candidata.
          - Año mínimo ≥ 500 → FECHADA → correlación móvil año a año
            aplicando el mejor desfase. Permite ver zonas internas
            problemáticas de la serie.
        """
        anio_min = int(serie_a.index.min()) if not serie_a.empty else 0
        es_flotante = anio_min < 500

        grafico = pg.PlotWidget()
        _agregar_hover_anio(grafico)
        _gr.aplicar_a_pyqtgraph(grafico)
        grafico.showGrid(x=True, y=True, alpha=0.3)
        grafico.setMinimumHeight(180)

        if es_flotante:
            self._dibujar_barras_desfase(grafico, shifts, scores)
        else:
            self._dibujar_correlacion_movil(grafico, serie_a, serie_b,
                                              shifts, scores)

        layout.addWidget(grafico)

    def _dibujar_barras_desfase(self, grafico, shifts, scores):
        """Gráfico de barras: puntaje compuesto vs desfase.

        Útil para series flotantes — la barra más alta indica la posición
        candidata. Las barras se colorean por el umbral del puntaje
        compuesto (verde=alto, amarillo=medio, rojo=bajo) usando los
        mismos colores que la tabla.
        """
        grafico.setTitle("Puntaje compuesto por desfase")
        grafico.setLabel("bottom", "Desfase (años)")
        grafico.setLabel("left", "Puntaje compuesto")

        # Reemplazar NaN por 0 para que las barras sean dibujables
        scores_plot = [s if np.isfinite(s) else 0.0 for s in scores]

        # Una barra por desfase, coloreada por el puntaje
        for x, s in zip(shifts, scores_plot):
            color = _color_compuesto(s) if np.isfinite(s) else "#666"
            bar = pg.BarGraphItem(
                x=[x], height=[s], width=0.8,
                brush=pg.mkBrush(QColor(color)),
                pen=pg.mkPen(QColor(color).darker(110)),
            )
            grafico.addItem(bar)

        # Línea horizontal en y=0 como referencia
        grafico.addItem(pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen("#888", width=1)))

        # Resaltar el mejor desfase con una línea vertical
        scores_validos = [(i, s) for i, s in enumerate(scores)
                          if np.isfinite(s)]
        if scores_validos:
            idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
            grafico.addItem(pg.InfiniteLine(
                pos=shifts[idx_mejor], angle=90,
                pen=pg.mkPen("#5cb85c", width=2, style=Qt.PenStyle.DashLine)))

    def _dibujar_correlacion_movil(self, grafico, serie_a, serie_b,
                                     shifts, scores):
        """Gráfico de correlación móvil: r/GLK/t-BP en ventanas
        deslizantes a lo largo del solape, aplicando el mejor desfase.

        Útil para series fechadas — permite detectar tramos internos
        donde el cofechado se debilita (años con potenciales errores
        de medición o anillos faltantes/extra).
        """
        # Aplicar el mejor desfase a la serie_a antes de calcular ventanas
        scores_validos = [(i, s) for i, s in enumerate(scores)
                          if np.isfinite(s)]
        mejor_shift = shifts[max(scores_validos, key=lambda x: x[1])[0]] \
            if scores_validos else 0

        s_a_shifted = serie_a.copy()
        s_a_shifted.index = s_a_shifted.index + mejor_shift
        overlap = s_a_shifted.index.intersection(serie_b.index)

        if len(overlap) < 30:
            grafico.setTitle("Solape insuficiente para correlación móvil")
            return

        # Transformación para el r móvil: respeta el modo COFECHA del panel
        # (si está activo, usa esa estandarización; si no, los datos tal
        # cual, sin corrección). Para GLK se usa la serie tal cual la ventana
        # (esa función diferencia internamente). Así el r móvil es coherente
        # con la tabla y con el botón modo COFECHA.
        a_raw_al = s_a_shifted.loc[overlap]
        b_raw_al = serie_b.loc[overlap]
        panel = getattr(self, "_panel_ref", None)
        if panel is not None and hasattr(panel, "_transformar_para_correlacion"):
            # serie_a es la serie (no cronología); serie_b la cronología
            a_corr_full = panel._transformar_para_correlacion(a_raw_al, es_crono=False)
            b_corr_full = panel._transformar_para_correlacion(b_raw_al, es_crono=True)
        else:
            a_corr_full = a_raw_al
            b_corr_full = b_raw_al
        a_dl = a_corr_full
        b_dl = b_corr_full
        a_arr = a_raw_al.to_numpy(dtype=float)
        b_arr = b_raw_al.to_numpy(dtype=float)
        anios_overlap = list(overlap)

        # Ventana móvil de 30 años (estándar dendrocronológico)
        VENTANA = 30
        if len(anios_overlap) < VENTANA:
            grafico.setTitle("Solape insuficiente para correlación móvil")
            return

        anios_centro = []
        rs_movil = []
        glks_movil = []
        tbps_movil = []

        for i in range(len(anios_overlap) - VENTANA + 1):
            anios_win = anios_overlap[i:i + VENTANA]
            a_win = a_arr[i:i + VENTANA]
            b_win = b_arr[i:i + VENTANA]
            if np.std(a_win) == 0 or np.std(b_win) == 0:
                continue
            # r sobre diferencias-log de la ventana (alta frecuencia)
            a_dl_win = a_dl.loc[a_dl.index.intersection(anios_win)]
            b_dl_win = b_dl.loc[b_dl.index.intersection(anios_win)]
            ov_dl = a_dl_win.index.intersection(b_dl_win.index)
            if len(ov_dl) < 3:
                continue
            r_win = pearson(a_dl_win.loc[ov_dl], b_dl_win.loc[ov_dl])
            if not np.isfinite(r_win):
                continue

            # GLK y t-BP sobre crudo de la ventana
            a_ser = pd.Series(a_win, index=anios_win)
            b_ser = pd.Series(b_win, index=anios_win)
            glk_win, _ = gleichlaufigkeit(a_ser, b_ser, min_overlap=10)
            t_win, _, _ = t_baillie_pilcher(a_ser, b_ser, min_overlap=20)

            anios_centro.append(anios_win[VENTANA // 2])
            rs_movil.append(r_win)
            glks_movil.append(glk_win if np.isfinite(glk_win) else 0.0)
            # Normalizamos t-BP a escala [-1, 1] dividiendo por 10 para
            # graficarlo en el mismo eje (t-BP > 5 ya es alto)
            tbps_movil.append(min(1.0, max(-1.0, t_win / 10.0))
                              if np.isfinite(t_win) else 0.0)

        if not anios_centro:
            grafico.setTitle("No se pudo calcular correlación móvil")
            return

        grafico.setTitle(
            f"Correlación móvil (ventana {VENTANA} años, "
            f"desfase aplicado: {mejor_shift:+d})"
        )
        grafico.setLabel("bottom", "Año (centro de la ventana)")
        grafico.setLabel("left", "Valor del estadístico")
        grafico.setYRange(-1.05, 1.05)
        grafico.addLegend(offset=(10, 10))

        grafico.plot(anios_centro, rs_movil,
                     pen=pg.mkPen("#3388FF", width=2), name="r (Pearson)")
        grafico.plot(anios_centro, glks_movil,
                     pen=pg.mkPen("#fd7e14", width=2), name="GLK")
        grafico.plot(anios_centro, tbps_movil,
                     pen=pg.mkPen("#9b59b6", width=2), name="t-BP / 10")

        # Línea de referencia en y=0
        grafico.addItem(pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen("#888", width=1)))

    def copiar_portapapeles(self):
        ncols = self.tabla.columnCount()
        headers = [self.tabla.horizontalHeaderItem(c).text()
                   for c in range(ncols)]
        text = "\t".join(headers) + "\n"
        for row in range(self.tabla.rowCount()):
            text += "\t".join(
                (self.tabla.item(row, c).text()
                 if self.tabla.item(row, c) is not None else "")
                for c in range(ncols)) + "\n"
        QApplication.clipboard().setText(text)

    def exportar_csv(self):
        ruta_default = os.path.join(_ultima_carpeta(), "resultados_desfases.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar Datos", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        ncols = self.tabla.columnCount()
        headers = [self.tabla.horizontalHeaderItem(c).text()
                   for c in range(ncols)]
        try:
            with open(ruta, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in range(self.tabla.rowCount()):
                    writer.writerow([
                        (self.tabla.item(row, c).text()
                         if self.tabla.item(row, c) is not None else "")
                        for c in range(ncols)])
            QMessageBox.information(self, "Éxito", "Datos exportados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{e}")



class DialogoComparacionMultiple(QDialog):
    """Tabla resumen de comparación de N series vs cronología activa.

    Cada fila = una serie con su mejor desfase + score compuesto + los 3
    estadísticos (r, GLK, t-BP) en ese desfase. La tabla es ordenable
    (default: por score descendente).

    Interpretación rápida por el usuario:
      - Para una serie FECHADA, el mejor desfase debería ser 0 con Δ≈0.
        Si el mejor desfase es ≠ 0 y Δ alto → posible error de datación
        (anillo faltante o extra).
      - Para una serie FLOTANTE, el mejor desfase indica su POSICIÓN
        candidata respecto al inicio de la cronología.

    Interacciones:
      - Doble clic en fila → abre `VentanaTablaOffset` con TODOS los
        desfases de esa serie individualmente.
      - Botón "Exportar CSV" guarda el resumen completo.

    Las celdas se colorean con los mismos umbrales que `VentanaTablaOffset`
    (verde / amarillo verdoso / amarillo / rojo según rangos publicados
    de r, GLK y t-BP), para ser consecuentes con el resto del cofechado.
    """

    # Umbral de score por debajo del cual NO resaltamos filas con shift≠0
    # (resaltar correlaciones débiles solo agrega ruido visual)
    UMBRAL_SCORE_PARA_RESALTAR = 0.30

    def __init__(self, resultados: list[dict], nombre_crono: str, parent=None, *,
                 obtener_serie=None, aplicar_desfase=None, reemplazar=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"Comparación múltiple vs cronología '{nombre_crono}'")
        self.resize(900, 600)
        self._resultados_originales = resultados
        self._obtener_serie = obtener_serie
        self._aplicar_desfase = aplicar_desfase
        self._reemplazar = reemplazar

        layout = QVBoxLayout(self)

        # ── Header informativo ────────────────────────────────────────
        info = QLabel(
            f"<b>{len(resultados)} series</b> comparadas vs cronología "
            f"<b>'{nombre_crono}'</b>. "
            f"Filas ordenadas por <b>puntaje compuesto</b> descendente.<br>"
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "🟡 Resaltado amarillo = mejor desfase ≠ 0 con puntaje "
            "significativo. Para series fechadas indica posible error de "
            "datación; para flotantes indica la posición candidata. "
            "⚠️ = la posición colocaría el último anillo en el futuro "
            "(datación imposible, probable correlación espuria). "
            "<b>Doble clic</b> en una fila para ver todos los desfases "
            "de esa serie. <i>Pasa el mouse sobre los encabezados para ver "
            "qué significa cada columna.</i>"
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Tabla ─────────────────────────────────────────────────────
        # 9 columnas: Serie, n, Mejor desfase, Años (inicio–fin), Puntaje,
        # r, GLK, t-BP, Δ vs 0
        self.tabla = QTableWidget(len(resultados), 9)
        self.tabla.setHorizontalHeaderLabels([
            "Serie", "n", "Mejor desfase", "Año término", "Puntaje",
            "r", "GLK", "t-BP", "Δ vs desfase 0",
        ])
        # Tooltips explicativos en cada encabezado
        _tooltips_encabezado = {
            0: "Nombre de la serie comparada.",
            1: ("n = cantidad de años en común (solape) entre la serie y la "
                "cronología en el mejor desfase.\n\nMás solape = estadísticos "
                "más confiables. Con poco solape (n bajo) una correlación alta "
                "puede ser casualidad."),
            2: ("Desfase (en años) que produce la mejor correlación.\n\n"
                "• Serie fechada: debería ser 0. Si es ≠ 0, posible error de "
                "datación (anillo faltante o extra).\n"
                "• Serie flotante: indica los años que hay que sumar para "
                "posicionarla respecto a la cronología.\n\n"
                "⚠️ = la posición resultante supera el año actual (imposible)."),
            3: ("Año en que terminaría la serie SI se acepta el mejor desfase.\n\n"
                "Clave para validar: si la muestra tiene corteza, este año "
                "debería ser cercano al año de colecta. Un término muy antiguo "
                "es sospechoso si la madera no se preserva tanto tiempo en el "
                "sitio.\n\nSe marca en naranja si supera el año actual."),
            4: ("Puntaje compuesto: media geométrica de r, GLK y t-BP "
                "normalizados.\n\nEs el indicador más confiable de la fecha "
                "verdadera: solo es alto cuando los TRES estadísticos lo son "
                "simultáneamente. Si solo uno es alto, suele ser coincidencia."),
            5: "r de Pearson sobre las series transformadas.",
            6: "GLK (Gleichläufigkeit): % de años con cambios en la misma dirección.",
            7: "t-BP (t de Baillie-Pilcher): estadístico t de la correlación.",
            8: ("Δ vs desfase 0 = cuánto mejora el puntaje del mejor desfase "
                "respecto a quedarse en el desfase 0.\n\n"
                "• Serie fechada: cercano a 0 confirma que ya está bien datada.\n"
                "• Aparece '—' cuando el desfase 0 no se evaluó: típico en "
                "series flotantes, cuyo rango de búsqueda está lejos de 0 "
                "(la cronología y la serie no se solapan en su posición "
                "original, así que no existe un desfase 0 comparable)."),
        }
        for col, tip in _tooltips_encabezado.items():
            hdr_item = self.tabla.horizontalHeaderItem(col)
            if hdr_item is not None:
                hdr_item.setToolTip(tip)
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(False)
        self.tabla.setSortingEnabled(False)
        self.tabla.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        # Selección múltiple para poder aplicar el desfase a varias series
        # a la vez (Ctrl+clic / Shift+clic, o Ctrl+A para todas).
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection)
        self.tabla.itemDoubleClicked.connect(self._abrir_detalle_serie)

        # Ordenar resultados por score descendente para el llenado inicial.
        # (después setSortingEnabled(True) permitirá reordenar por cualquier
        # columna haciendo clic en el header)
        resultados_ord = sorted(
            resultados,
            key=lambda r: r.get("mejor_score") if np.isfinite(
                r.get("mejor_score", float("nan"))) else -1e9,
            reverse=True,
        )

        # Guardar referencia ordenada para resolver el doble clic
        self._resultados_ordenados = resultados_ord

        for row, res in enumerate(resultados_ord):
            self._llenar_fila(row, res)

        # Activar sorting DESPUÉS de llenar (orden inicial preservado)
        self.tabla.setSortingEnabled(True)
        layout.addWidget(self.tabla)

        # ── Botones ───────────────────────────────────────────────────
        botonera = QHBoxLayout()

        btn_copiar = QPushButton("📋 Copiar todo")
        btn_copiar.clicked.connect(self._copiar_portapapeles)
        botonera.addWidget(btn_copiar)

        btn_exportar = QPushButton("💾 Exportar CSV")
        btn_exportar.clicked.connect(self._exportar_csv)
        botonera.addWidget(btn_exportar)

        # Botón "Ver detalle" como alternativa al doble clic (útil en
        # touchpads donde el doble clic a veces no se registra bien).
        btn_detalle = QPushButton("🔍 Ver detalle de fila")
        btn_detalle.setToolTip(
            "Abre los desfases detallados de la serie seleccionada "
            "(equivale al doble clic).")
        btn_detalle.clicked.connect(self._ver_detalle_seleccionada)
        botonera.addWidget(btn_detalle)

        # Botón para aplicar el desfase sugerido a las series y graficarlas
        # re-datadas en el panel principal. Solo se muestra si el padre es
        # el panel de cofechado (tiene las estructuras de series).
        _padre = self.parent()
        if (_padre is not None and hasattr(_padre, "series_datos")
                and hasattr(_padre, "graficar_series")):
            btn_aplicar = QPushButton("✅ Aplicar desfase y graficar")
            btn_aplicar.setStyleSheet(
                "QPushButton{background-color:#27ae60; color:white; "
                "font-weight:bold; padding:5px 12px; border-radius:4px;}"
                "QPushButton:hover{background-color:#2ecc71;}")
            btn_aplicar.setToolTip(
                "Aplica el mejor desfase a las series SELECCIONADAS: cambia "
                "su año de inicio a la posición sugerida y las grafica re-"
                "datadas en el panel principal.\n\n"
                "Selecciona las filas a aplicar (Ctrl+clic para varias, "
                "Ctrl+A para todas). Sin selección, pregunta si aplicar a "
                "todas.")
            btn_aplicar.clicked.connect(self._aplicar_desfases)
            botonera.addWidget(btn_aplicar)

        botonera.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        botonera.addWidget(btn_cerrar)
        layout.addLayout(botonera)

    # ── Construcción de filas ─────────────────────────────────────────

    def _llenar_fila(self, row: int, res: dict):
        """Llena una fila de la tabla con los datos de UNA serie.

        Aplica colores por umbral en cada estadístico y, si corresponde,
        resalta toda la fila en amarillo (mejor_shift ≠ 0 con score
        significativo).
        """
        nombre = res.get("nombre_serie", "?")
        mejor_shift = res.get("mejor_shift", 0)
        mejor_score = res.get("mejor_score", float("nan"))
        mejor_r = res.get("mejor_r", float("nan"))
        mejor_glk = res.get("mejor_glk", float("nan"))
        mejor_tbp = res.get("mejor_tbp", float("nan"))
        mejor_n = res.get("mejor_n", 0)
        score_shift0 = res.get("score_shift0", float("nan"))

        # Δ vs shift=0: cuánto mejor es el mejor shift comparado con quedarse
        # en 0. Para fechadas correctas debería ser ~0 (porque shift=0 ya es
        # el mejor). Para incorrectas o flotantes, será > 0.
        if np.isfinite(mejor_score) and np.isfinite(score_shift0):
            delta = mejor_score - score_shift0
        else:
            delta = float("nan")

        # ── Columna 0: Serie ──
        it = QTableWidgetItem(str(nombre))
        # Guardar referencia al resultado completo para resolver doble clic
        # incluso después de reordenar por otra columna.
        it.setData(Qt.ItemDataRole.UserRole, id(res))
        self.tabla.setItem(row, 0, it)

        # ── Columna 1: n ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole, int(mejor_n))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 1, it)

        # ── Columna 2: Mejor shift ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole, int(mejor_shift))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Resaltar visualmente si el shift es ≠ 0 con score significativo
        resaltar_fila = (
            mejor_shift != 0
            and np.isfinite(mejor_score)
            and mejor_score >= self.UMBRAL_SCORE_PARA_RESALTAR
        )
        if resaltar_fila:
            # Texto en negrita para llamar la atención sobre el shift
            f = it.font(); f.setBold(True); it.setFont(f)

        # Calcular la posición resultante (años de inicio y término) que
        # tendría la serie si se acepta el mejor desfase. Se usa tanto para
        # el aviso de año futuro como para la nueva columna "Años".
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        serie_a = res.get("serie_a")
        placed_min = placed_max = None
        if serie_a is not None and len(serie_a) > 0:
            try:
                placed_min = int(serie_a.index.min()) + int(mejor_shift)
                placed_max = int(serie_a.index.max()) + int(mejor_shift)
            except (ValueError, TypeError):
                placed_min = placed_max = None

        supera_presente = placed_max is not None and placed_max > anio_actual
        if supera_presente:
            it.setText(f"{int(mejor_shift)} ⚠️")
            it.setForeground(QColor("#e67e22"))
            f = it.font(); f.setBold(True); it.setFont(f)
            it.setToolTip(
                f"⚠️ Posición imposible: con este desfase la serie quedaría "
                f"en los años {placed_min}–{placed_max}, y el último año "
                f"({placed_max}) supera el año actual ({anio_actual}).\n\n"
                f"Esto suele indicar que la mejor correlación encontrada es "
                f"espuria (la serie no cofecha bien con esta cronología), o "
                f"que el rango de búsqueda permitió posiciones futuras.\n"
                f"Revisa el puntaje: si es bajo, probablemente no hay un "
                f"cofechado real con esta cronología."
            )
        self.tabla.setItem(row, 2, it)

        # ── Columna 3: Año término ──
        it = QTableWidgetItem()
        if placed_max is not None:
            # DisplayRole numérico para que ordene por año correctamente
            it.setData(Qt.ItemDataRole.DisplayRole, int(placed_max))
            it.setToolTip(
                f"Si se acepta el desfase {int(mejor_shift)}, la serie "
                f"abarcaría {placed_min}–{placed_max}.\n\n"
                f"Validación con corteza: si la muestra conserva corteza, este "
                f"año de término ({placed_max}) debería ser cercano al año de "
                f"colecta. Un término muy antiguo es sospechoso si la madera "
                f"no se preserva tanto tiempo en el sitio."
            )
            if supera_presente:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
        else:
            it.setText("—")
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 3, it)

        # ── Columna 4: Score compuesto ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_score, 3))
                    if np.isfinite(mejor_score) else 0.0)
        it.setBackground(QColor(_color_compuesto(mejor_score)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 4, it)

        # ── Columna 5: r ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_r, 3))
                    if np.isfinite(mejor_r) else 0.0)
        it.setBackground(QColor(_color_r(mejor_r)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 5, it)

        # ── Columna 6: GLK ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_glk, 3))
                    if np.isfinite(mejor_glk) else 0.0)
        it.setBackground(QColor(_color_glk(mejor_glk)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 6, it)

        # ── Columna 7: t-BP ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_tbp, 2))
                    if np.isfinite(mejor_tbp) else 0.0)
        it.setBackground(QColor(_color_tbp(mejor_tbp)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 7, it)

        # ── Columna 8: Δ vs shift=0 ──
        it = QTableWidgetItem()
        if np.isfinite(delta):
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(delta, 3)))
        else:
            it.setData(Qt.ItemDataRole.DisplayRole, 0.0)
            it.setText("—")
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 8, it)

        # Resaltado de fila completa (solo color de fondo "sutil" en las
        # columnas que no tienen ya color por umbral: 0, 1, 2, 3, 8).
        # Usamos mostaza con texto casi negro (buen contraste en ambos temas).
        if resaltar_fila:
            color_fondo = QColor(218, 165, 32)        # mostaza (goldenrod)
            color_texto = QColor(20, 20, 20)          # casi negro
            for col in (0, 1, 2, 3, 8):
                cell = self.tabla.item(row, col)
                if cell is not None:
                    cell.setBackground(color_fondo)
                    cell.setForeground(color_texto)

    # ── Doble clic: drill-down ────────────────────────────────────────

    def _abrir_detalle_serie(self, item: QTableWidgetItem):
        """Doble clic en una fila → abre VentanaTablaOffset con todos los
        desfases de esa serie.

        Como las filas se pueden reordenar por cualquier columna usando
        el header, NO se puede usar `item.row()` para mapear al resultado
        original. En su lugar, guardamos el `id(res)` en UserRole de la
        columna 0 y buscamos el dict por identidad de objeto en
        `_resultados_originales`. Es a prueba de cualquier sort.
        """
        row = item.row()
        cell_nombre = self.tabla.item(row, 0)
        if cell_nombre is None:
            return
        id_buscado = cell_nombre.data(Qt.ItemDataRole.UserRole)
        if id_buscado is None:
            return
        res = next(
            (r for r in self._resultados_originales if id(r) == id_buscado),
            None,
        )
        if res is None:
            return

        dlg = VentanaTablaOffset(
            res["shifts"], res["rs"],
            glks=res["glks"], tbps=res["tbps"], ns=res["ns"],
            serie_a=res.get("serie_a"),
            serie_b=res.get("serie_b"),
            parent=self,
            # Para poder aplicar el desfase seleccionado desde el detalle:
            nombre_serie=res.get("nombre_serie"),
            obtener_serie=self._obtener_serie, aplicar_desfase=self._aplicar_desfase,
            reemplazar=self._reemplazar,
        )
        dlg.setWindowTitle(
            f"Desfases detallados — '{res.get('nombre_serie', '?')}' "
            f"vs cronología"
        )
        dlg.exec()

    def _ver_detalle_seleccionada(self):
        """Abre el detalle de la fila seleccionada (alternativa al doble
        clic, útil en touchpad)."""
        seleccion = self.tabla.selectionModel().selectedRows()
        if not seleccion:
            QMessageBox.information(
                self, "Sin selección",
                "Selecciona una fila primero para ver su detalle.")
            return
        row = seleccion[0].row()
        cell = self.tabla.item(row, 0)
        if cell is not None:
            self._abrir_detalle_serie(cell)

    def _resolver_res_de_fila(self, row: int) -> dict | None:
        """Devuelve el dict de resultado correspondiente a una fila de la
        tabla, resolviendo por id guardado en UserRole (a prueba de sort)."""
        cell = self.tabla.item(row, 0)
        if cell is None:
            return None
        id_buscado = cell.data(Qt.ItemDataRole.UserRole)
        return next(
            (r for r in self._resultados_originales if id(r) == id_buscado),
            None,
        )

    def _aplicar_desfases(self):
        """Aplica el mejor desfase a las series seleccionadas: re-data cada
        serie sumando su desfase al índice de años, actualiza las
        estructuras del panel principal y vuelve a graficar.

        Flujo:
          1. Determina las filas objetivo (seleccionadas; si no hay, ofrece
             aplicar a todas).
          2. Arma un resumen con el rango de años resultante por serie y
             marca las que quedarían en el futuro (datación imposible).
          3. Pide confirmación mostrando los cambios.
          4. Aplica: index += desfase en series_datos y series_originales.
          5. Invalida la caché de comparación y regrafica.
        """
        panel = self.parent()
        if panel is None or not hasattr(panel, "series_datos"):
            return

        # 1. Filas objetivo
        filas_sel = sorted({idx.row()
                            for idx in self.tabla.selectionModel().selectedRows()})
        if not filas_sel:
            resp = QMessageBox.question(
                self, "Sin selección",
                "No seleccionaste ninguna fila.\n\n"
                "¿Aplicar el desfase a TODAS las series de la tabla?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            filas_sel = list(range(self.tabla.rowCount()))

        # 2. Recolectar cambios
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        cambios = []          # (nombre, shift, nuevo_ini, nuevo_fin, futuro)
        for row in filas_sel:
            res = self._resolver_res_de_fila(row)
            if res is None:
                continue
            nombre = res.get("nombre_serie")
            shift = int(res.get("mejor_shift", 0))
            df = panel.series_datos.get(nombre)
            if df is None or df.empty:
                continue
            nuevo_ini = int(df.index.min()) + shift
            nuevo_fin = int(df.index.max()) + shift
            cambios.append((nombre, shift, nuevo_ini, nuevo_fin,
                            nuevo_fin > anio_actual))

        if not cambios:
            QMessageBox.information(
                self, "Sin cambios",
                "No se pudo resolver ninguna serie de las filas elegidas.")
            return

        # 3. Confirmación con resumen
        lineas = []
        hay_futuro = False
        for nombre, shift, ini, fin, futuro in cambios:
            marca = "  ⚠️ término en el futuro" if futuro else ""
            if futuro:
                hay_futuro = True
            signo = f"+{shift}" if shift >= 0 else str(shift)
            lineas.append(f"• {nombre}: desfase {signo} → años {ini}–{fin}{marca}")
        texto = (
            f"Se cambiará el año de inicio de {len(cambios)} serie(s) a la "
            f"posición sugerida:\n\n" + "\n".join(lineas)
        )
        if hay_futuro:
            texto += (
                "\n\n⚠️ Algunas series quedarían con año de término en el "
                "futuro (datación probablemente espuria). Revisa si de verdad "
                "quieres aplicarlas.")
        texto += "\n\n¿Continuar?"

        resp = QMessageBox.question(
            self, "Aplicar desfases", texto,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # 4. Aplicar usando el método reutilizable del panel
        for nombre, shift, _ini, _fin, _fut in cambios:
            panel.aplicar_desfase_a_serie(nombre, shift, regraficar=False)

        # 5. Regraficar una sola vez al final
        if hasattr(panel, "graficar_series"):
            panel.graficar_series()

        QMessageBox.information(
            self, "Listo",
            f"Se aplicó el desfase a {len(cambios)} serie(s) y se "
            f"regraficaron en el panel principal.")
        self.accept()

    # ── Exportación ───────────────────────────────────────────────────

    def _copiar_portapapeles(self):
        encabezado = ("Serie\tn\tMejor desfase\tAnio_termino\tPuntaje\t"
                      "r\tGLK\tt-BP\tDelta_vs_desfase_0\n")
        filas = []
        for row in range(self.tabla.rowCount()):
            cells = [self.tabla.item(row, c) for c in range(9)]
            filas.append("\t".join(
                c.text() if c is not None else "" for c in cells))
        QApplication.clipboard().setText(encabezado + "\n".join(filas))

    def _exportar_csv(self):
        ruta_default = os.path.join(
            _ultima_carpeta(), "comparacion_multiple.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar resumen", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Serie", "n", "Mejor desfase", "Anio_termino",
                    "Puntaje", "r", "GLK", "t-BP", "Delta_vs_desfase_0",
                ])
                for row in range(self.tabla.rowCount()):
                    cells = [self.tabla.item(row, c) for c in range(9)]
                    writer.writerow([
                        c.text() if c is not None else "" for c in cells])
            QMessageBox.information(self, "Éxito", "Resumen exportado.")
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                  f"No se pudo guardar:\n{e}")


from dpi.ciencia.comparacion_nucleo import resultado_sin_overlap
