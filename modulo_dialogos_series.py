"""Componentes de la interfaz de co-datación de DPI."""

import os
import csv
import numpy as np
import pandas as pd
import pyqtgraph as pg
from modulo_widgets import _agregar_hover_anio, SpinBoxFlechas
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QFormLayout, QComboBox, QCheckBox, QGroupBox, QDialogButtonBox, QApplication, QRadioButton
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from estilos import SECUNDARIO_QSS, color_secundario
import estilos_graficos as _gr
from dpi.ciencia.datacion import alineamiento_optimo_anillos
from dpi.formatos.exportacion import asegurar_extension
from dpi.ciencia.cronologia import _fit_trend, diagnosticar_curva, elegir_metodo_para_grupo, METODOS_DETREND
from dpi.ui.series_util import ESTILO_CHK_COFECHA, _color_glk, _color_r, _ultima_carpeta


class DialogoSeleccionCronologias(QDialog):
    """Permite elegir CUÁLES cronologías cargar de un archivo con varias.

    Un archivo (sobre todo .ods/.xlsx) puede traer varias cronologías, ya sea
    en columnas distintas o en hojas distintas. Antes se obligaba a elegir una
    sola; acá se pueden marcar todas las que se quieran (todas marcadas por
    defecto).
    """

    def __init__(self, candidatos: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿Qué cronologías quieres cargar?")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        titulo = QLabel(
            "<b>El archivo contiene varias cronologías</b><br>"
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "Marca las que quieras cargar. Cada una se agregará como una "
            "cronología (📚) independiente.</span>"
        )
        titulo.setWordWrap(True)
        layout.addWidget(titulo)

        self.lista = QListWidget()
        for etiqueta in candidatos:
            it = QListWidgetItem(etiqueta)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)  # todas por defecto
            self.lista.addItem(it)
        layout.addWidget(self.lista)

        fila = QHBoxLayout()
        btn_todas = QPushButton("Marcar todas")
        btn_todas.clicked.connect(lambda: self._marcar(True))
        btn_ninguna = QPushButton("Desmarcar todas")
        btn_ninguna.clicked.connect(lambda: self._marcar(False))
        fila.addWidget(btn_todas)
        fila.addWidget(btn_ninguna)
        fila.addStretch()
        layout.addLayout(fila)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _marcar(self, marcar: bool):
        estado = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        for i in range(self.lista.count()):
            self.lista.item(i).setCheckState(estado)

    def seleccionadas(self) -> list[str]:
        return [self.lista.item(i).text()
                for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.CheckState.Checked]



class DialogoCofecha(QDialog):
    """Configuración del Modo COFECHA."""

    def __init__(self, parent=None, params: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Modo COFECHA — Configuración")
        self.setMinimumWidth(520)
        params = params or {}
        layout = QVBoxLayout(self)

        titulo = QLabel(
            "<b>Transformaciones tipo COFECHA</b><br>"
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "Holmes (1983). Aplicado a las series antes de calcular correlaciones."
            "</span>"
        )
        titulo.setWordWrap(True)
        layout.addWidget(titulo)

        grp_sp = QGroupBox("1. Spline detrending")
        f_sp = QFormLayout(grp_sp)
        self.spin_rigidez = SpinBoxFlechas()
        self.spin_rigidez.setRange(10, 200)
        self.spin_rigidez.setValue(int(params.get("rigidez_spline", 32)))
        self.spin_rigidez.setSuffix(" años")
        f_sp.addRow("Rigidez:", self.spin_rigidez)
        layout.addWidget(grp_sp)

        grp_t = QGroupBox("2. Transformaciones")
        v_t = QVBoxLayout(grp_t)
        self.chk_log = QCheckBox("Transformación logarítmica  log(x + media/6)")
        self.chk_log.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_log.setChecked(params.get("aplicar_log", True))
        self.chk_log.setToolTip(
            "Pondera de forma más equitativa las diferencias proporcionales.\n"
            "La constante 1/6 de la media evita log(0)."
        )
        v_t.addWidget(self.chk_log)
        self.chk_ar = QCheckBox("Modelado AR(1)")
        self.chk_ar.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_ar.setChecked(params.get("aplicar_ar", True))
        self.chk_ar.setToolTip(
            "Elimina la autocorrelación (inercia biológica).\n"
            "Resta phi × x[t-1] de cada valor."
        )
        v_t.addWidget(self.chk_ar)
        layout.addWidget(grp_t)

        grp_fd = QGroupBox("3. Opcional")
        v_fd = QVBoxLayout(grp_fd)
        self.chk_fd = QCheckBox("Primeras diferencias  x[t] − x[t−1]")
        self.chk_fd.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_fd.setChecked(params.get("aplicar_first_diff", False))
        self.chk_fd.setToolTip(
            "Estabiliza series con períodos prolongados de varianza alta y baja.\n"
            "Activar solo si las transformaciones anteriores no son suficientes."
        )
        v_fd.addWidget(self.chk_fd)
        layout.addWidget(grp_fd)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_params(self) -> dict:
        return {
            "rigidez_spline": self.spin_rigidez.value(),
            "aplicar_log": self.chk_log.isChecked(),
            "aplicar_ar": self.chk_ar.isChecked(),
            "aplicar_first_diff": self.chk_fd.isChecked(),
        }



class DialogoEditarAnillos(QDialog):
    """Editor de anillos que CONSERVA el ancho total de la madera.

    Principio dendrocronológico: cuando se elimina un anillo, su ancho no
    desaparece — pasa a un anillo vecino (la madera sigue ahí). Cuando se
    inserta un anillo, su ancho debe salir de un anillo vecino (que lo
    pierde). Así el ancho radial total se mantiene constante.

    Operaciones:
      • Eliminar anillo: se suma su ancho al vecino elegido (anterior o
        posterior). Útil para anillos falsos (dos contados como uno).
      • Insertar anillo: se crea con un ancho que se resta de un vecino.
        Útil para anillos faltantes / fusionados (un ancho que en realidad
        eran dos años).

    Tras editar, los años se renumeran consecutivamente desde el año de
    inicio.
    """

    # Estilo de radio buttons con indicador NARANJA al seleccionar, igual
    # que el resto del programa (el círculo por defecto no se distingue
    # bien en tema oscuro).
    ESTILO_RADIO = (
        "QRadioButton{spacing:6px; padding:2px;}"
        "QRadioButton::indicator{width:14px; height:14px; border-radius:8px;"
        " border:2px solid #888;}"
        "QRadioButton::indicator:checked{background-color:#e67e22;"
        " border:2px solid #e67e22;}"
        "QRadioButton::indicator:unchecked{background-color:transparent;}"
        "QRadioButton:disabled{color:#666;}"
    )

    def __init__(self, df_serie, nombre, reemplazar=None, parent=None,
                 sugerencia=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar anillos — {nombre}")
        self.resize(440, 600)
        self._nombre = nombre
        self._reemplazar = reemplazar

        df = df_serie.sort_index()
        self._anchos = [float(x) for x in
                        pd.to_numeric(df["Ancho_mm"], errors="coerce").fillna(0).values]
        self._start_year = int(df.index.min())
        # Copia original para deshacer
        self._anchos_orig = list(self._anchos)
        self._start_orig = self._start_year

        layout = QVBoxLayout(self)

        info = QLabel(
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "El ancho total de la madera se <b>conserva</b>: al eliminar un "
            "anillo su ancho pasa a un vecino; al insertar uno, su ancho se "
            "resta de un vecino. Selecciona un anillo y usa los botones."
            "</span>")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Banner de sugerencia (cuando se abre desde "Aplicar corrección").
        # Indica al usuario qué operación sugiere el cofechado y en qué año,
        # pero la decisión final (qué ancho mover y hacia qué vecino) la toma
        # él en el diálogo de insertar/eliminar, conservando el ancho.
        if sugerencia:
            anio_s = sugerencia.get("anio")
            delta_s = sugerencia.get("delta", 0)
            if delta_s > 0:
                accion = (f"Posible anillo <b>FALTANTE</b> cerca del año "
                          f"<b>{anio_s}</b>. Selecciona ese anillo y pulsa "
                          f"<b>➕ Insertar anillo</b> para agregarlo, eligiendo "
                          f"de qué vecino tomar el ancho.")
                color = "#5bc0de"
            else:
                accion = (f"Posible anillo <b>FALSO/EXTRA</b> en el año "
                          f"<b>{anio_s}</b>. Selecciónalo y pulsa "
                          f"<b>➖ Eliminar anillo</b>, eligiendo a qué vecino "
                          f"sumarle el ancho.")
                color = "#d9534f"
            banner = QLabel(f"<span style='font-size:11px;'>💡 {accion}</span>")
            banner.setWordWrap(True)
            banner.setStyleSheet(
                f"QLabel{{background-color:rgba(0,0,0,40); border-left:3px "
                f"solid {color}; padding:6px 8px; border-radius:3px;}}")
            layout.addWidget(banner)

        # ── Anclaje y años de la serie ───────────────────────────────
        # No siempre conviene fijar la corteza: en series o cronologías
        # FLOTANTES el usuario puede querer extenderlas hacia el presente,
        # dejando fijo el primer año. Por eso se ofrece la opción.
        fila_ancla = QHBoxLayout()
        fila_ancla.addWidget(QLabel("Al insertar/eliminar, mantener fijo:"))
        self.combo_ancla_editor = QComboBox()
        self.combo_ancla_editor.addItem("Último año (corteza)", "corteza")
        self.combo_ancla_editor.addItem("Primer año (médula)", "medula")
        self.combo_ancla_editor.setToolTip(
            "Qué extremo de la serie NO se mueve al agregar o quitar anillos.\n\n"
            "• Último año (corteza): para árboles vivos, donde el año del\n"
            "  anillo externo se conoce con certeza. Al insertar un anillo la\n"
            "  serie empieza un año antes y sigue terminando igual.\n\n"
            "• Primer año (médula): para series o cronologías FLOTANTES que se\n"
            "  quieran extender hacia el presente. Al insertar un anillo la\n"
            "  serie termina un año después.")
        fila_ancla.addWidget(self.combo_ancla_editor, 1)
        layout.addLayout(fila_ancla)

        fila_anios = QHBoxLayout()
        fila_anios.addWidget(QLabel("Año inicio:"))
        self.spin_anio_inicio = QSpinBox()
        self.spin_anio_inicio.setRange(-20000, 20000)
        self.spin_anio_inicio.setValue(self._start_year)
        self.spin_anio_inicio.setToolTip(
            "Desplaza TODA la serie para que comience en este año.")
        self.spin_anio_inicio.valueChanged.connect(self._on_anio_inicio_cambiado)
        fila_anios.addWidget(self.spin_anio_inicio)
        fila_anios.addWidget(QLabel("Año fin:"))
        self.spin_anio_fin = QSpinBox()
        self.spin_anio_fin.setRange(-20000, 20000)
        self.spin_anio_fin.setValue(self._start_year + len(self._anchos) - 1)
        self.spin_anio_fin.setToolTip(
            "Desplaza TODA la serie para que termine en este año.")
        self.spin_anio_fin.valueChanged.connect(self._on_anio_fin_cambiado)
        fila_anios.addWidget(self.spin_anio_fin)
        fila_anios.addStretch()
        layout.addLayout(fila_anios)

        # ── Tabla + botones al costado ───────────────────────────────
        # Los botones van JUNTO a la lista (no debajo) para poder seleccionar
        # un año y operar sobre él viendo el resultado al instante.
        fila_centro = QHBoxLayout()

        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Año", "Ancho (mm)"])
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fila_centro.addWidget(self.tabla, 1)

        col_ops = QVBoxLayout()
        col_ops.setSpacing(4)

        lbl_ins = QLabel("<b>Insertar anillo</b>")
        lbl_ins.setStyleSheet("font-size:11px;")
        col_ops.addWidget(lbl_ins)

        # Dos flechas: insertar ANTES (hacia arriba en la lista, años más
        # antiguos) o DESPUÉS (hacia abajo) del año seleccionado.
        btn_ins_arriba = QPushButton("⬆  Antes")
        btn_ins_arriba.setToolTip(
            "Inserta un anillo EN el año seleccionado.\n"
            "El año seleccionado y los anteriores retroceden un año;\n"
            "el último año de la serie (corteza) no se mueve.")
        btn_ins_arriba.clicked.connect(lambda: self._insertar_en(desplazar_antes=True))
        col_ops.addWidget(btn_ins_arriba)

        btn_ins_abajo = QPushButton("⬇  Después")
        btn_ins_abajo.setToolTip(
            "Inserta un anillo DESPUÉS del año seleccionado\n"
            "(entre el seleccionado y el siguiente).")
        btn_ins_abajo.clicked.connect(lambda: self._insertar_en(desplazar_antes=False))
        col_ops.addWidget(btn_ins_abajo)

        col_ops.addSpacing(10)
        lbl_del = QLabel("<b>Eliminar anillo</b>")
        lbl_del.setStyleSheet("font-size:11px;")
        col_ops.addWidget(lbl_del)

        btn_eliminar = QPushButton("✖  Eliminar")
        btn_eliminar.setToolTip(
            "Elimina el anillo seleccionado. Su ancho se suma a un vecino\n"
            "para conservar el ancho total de la madera.")
        btn_eliminar.clicked.connect(self._eliminar)
        col_ops.addWidget(btn_eliminar)

        col_ops.addSpacing(10)
        btn_deshacer = QPushButton("↺  Deshacer todo")
        btn_deshacer.clicked.connect(self._deshacer)
        col_ops.addWidget(btn_deshacer)

        col_ops.addStretch()
        self.lbl_resumen_edicion = QLabel("")
        self.lbl_resumen_edicion.setWordWrap(True)
        self.lbl_resumen_edicion.setStyleSheet(
            f"font-size:10px; color:{SECUNDARIO_QSS};")
        col_ops.addWidget(self.lbl_resumen_edicion)

        cont_ops = QWidget()
        cont_ops.setLayout(col_ops)
        cont_ops.setMaximumWidth(210)
        fila_centro.addWidget(cont_ops)
        layout.addLayout(fila_centro, 1)

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("font-weight:bold; padding:4px;")
        layout.addWidget(self.lbl_total)

        # Botones de cierre
        fila_cierre = QHBoxLayout()
        fila_cierre.addStretch()
        btn_aplicar = QPushButton("✅ Aplicar cambios")
        btn_aplicar.setStyleSheet(
            "QPushButton{background-color:#27ae60; color:white; "
            "font-weight:bold; padding:5px 12px; border-radius:4px;}"
            "QPushButton:hover{background-color:#2ecc71;}")
        btn_aplicar.clicked.connect(self._aplicar)
        fila_cierre.addWidget(btn_aplicar)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_cierre.addWidget(btn_cancelar)
        layout.addLayout(fila_cierre)

        self._refrescar_tabla()
        self._actualizar_resumen_edicion()

        # Pre-seleccionar el anillo del año sugerido, si se indicó.
        if sugerencia and sugerencia.get("anio") is not None:
            fila = int(sugerencia["anio"]) - self._start_year
            if 0 <= fila < len(self._anchos):
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(
                    self.tabla.item(fila, 0),
                    QAbstractItemView.ScrollHint.PositionAtCenter)

    def _years(self):
        return list(range(self._start_year,
                          self._start_year + len(self._anchos)))

    def _refrescar_tabla(self, seleccionar=None):
        years = self._years()
        self.tabla.setRowCount(len(self._anchos))
        for i, (y, w) in enumerate(zip(years, self._anchos)):
            it = QTableWidgetItem(); it.setData(Qt.ItemDataRole.DisplayRole, int(y))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(i, 0, it)
            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole, round(w, 4))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(i, 1, it)
        total = sum(self._anchos)
        total_orig = sum(self._anchos_orig)
        self.lbl_total.setText(
            f"Total: {total:.4f} mm  |  {len(self._anchos)} anillos  |  "
            f"Original: {total_orig:.4f} mm "
            f"({'✅ conservado' if abs(total-total_orig) < 1e-6 else '⚠️ DIFIERE'})")
        if seleccionar is not None and 0 <= seleccionar < len(self._anchos):
            self.tabla.selectRow(seleccionar)

    def _fila_sel(self):
        sel = self.tabla.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(
                self, "Selecciona un anillo",
                "Primero selecciona un anillo en la tabla.")
            return None
        return sel[0].row()

    def _eliminar(self):
        idx = self._fila_sel()
        if idx is None:
            return
        years = self._years()
        w = self._anchos[idx]
        # Diálogo para elegir destino del ancho
        dlg = QDialog(self)
        dlg.setWindowTitle("Eliminar anillo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"Vas a eliminar el anillo del año <b>{years[idx]}</b> "
            f"(ancho {w:.4f} mm).<br>¿A qué anillo vecino se le suma ese "
            f"ancho?", dlg))
        rb_ant = QRadioButton(
            f"Anterior ({years[idx-1]})" if idx > 0 else "Anterior (no existe)")
        rb_post = QRadioButton(
            f"Posterior ({years[idx+1]})" if idx < len(years)-1
            else "Posterior (no existe)")
        rb_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setStyleSheet(self.ESTILO_RADIO)
        rb_ant.setEnabled(idx > 0)
        rb_post.setEnabled(idx < len(years)-1)
        if idx > 0:
            rb_ant.setChecked(True)
        else:
            rb_post.setChecked(True)
        lay.addWidget(rb_ant); lay.addWidget(rb_post)
        botones = QHBoxLayout(); botones.addStretch()
        ok = QPushButton("Eliminar"); ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar"); ca.clicked.connect(dlg.reject)
        botones.addWidget(ok); botones.addWidget(ca)
        lay.addLayout(botones)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if rb_ant.isChecked() and idx > 0:
            self._anchos[idx-1] += w
            nueva_sel = idx - 1
        elif rb_post.isChecked() and idx < len(self._anchos)-1:
            self._anchos[idx+1] += w
            nueva_sel = idx
        else:
            return
        del self._anchos[idx]
        # Con corteza anclada la serie pierde un anillo, así que el inicio
        # avanza un año; con médula anclada el inicio se mantiene.
        if self._anclar_corteza():
            self._start_year += 1
        self._refrescar_tabla(seleccionar=min(nueva_sel, len(self._anchos)-1))
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _anclar_corteza(self) -> bool:
        """True si el ÚLTIMO año debe quedar fijo al insertar/eliminar."""
        combo = getattr(self, "combo_ancla_editor", None)
        if combo is None:
            return True
        return (combo.currentData() or "corteza") == "corteza"

    def _sincronizar_spins_anio(self):
        """Refleja los años actuales en los campos, sin disparar sus señales."""
        if not hasattr(self, "spin_anio_inicio") or not self._anchos:
            return
        fin = self._start_year + len(self._anchos) - 1
        for spin, val in ((self.spin_anio_inicio, self._start_year),
                          (self.spin_anio_fin, fin)):
            spin.blockSignals(True)
            spin.setValue(int(val))
            spin.blockSignals(False)

    def _on_anio_inicio_cambiado(self, valor: int):
        """Desplaza toda la serie para que comience en `valor`."""
        if not self._anchos:
            return
        self._start_year = int(valor)
        self._sincronizar_spins_anio()
        self._refrescar_tabla(seleccionar=self._fila_sel())
        self._actualizar_resumen_edicion()

    def _on_anio_fin_cambiado(self, valor: int):
        """Desplaza toda la serie para que termine en `valor`."""
        if not self._anchos:
            return
        self._start_year = int(valor) - len(self._anchos) + 1
        self._sincronizar_spins_anio()
        self._refrescar_tabla(seleccionar=self._fila_sel())
        self._actualizar_resumen_edicion()

    def _insertar_en(self, desplazar_antes: bool = True):
        """Inserta un anillo manteniendo FIJO el último año (corteza).

        `desplazar_antes=True` coloca el anillo EN el año seleccionado (ese año
        y los anteriores retroceden uno); False lo coloca justo después.

        El último año de la serie no se mueve: si la muestra termina en 2024 y
        se inserta el anillo que faltaba en 2023, la serie sigue terminando en
        2024 y el inicio retrocede un año. Antes el editor dejaba fijo el
        primer año y la serie se estiraba hacia el presente (terminaba en
        2025), obligando a corregir el año base a mano después.
        """
        idx = self._fila_sel()
        if idx is None:
            QMessageBox.information(
                self, "Selecciona un año",
                "Elige en la lista el año donde quieres insertar el anillo.")
            return
        years = self._years()
        anio_sel = years[idx]
        insert_idx = idx if desplazar_antes else idx + 1

        dlg = QDialog(self)
        dlg.setWindowTitle("Insertar anillo")
        dlg.setMinimumWidth(430)
        lay = QVBoxLayout(dlg)
        destino = anio_sel if desplazar_antes else anio_sel + 1
        if self._anclar_corteza():
            efecto = (f"El último año (<b>{years[-1]}</b>) no se mueve; "
                      f"la serie comenzará un año antes.")
        else:
            efecto = (f"El primer año (<b>{years[0]}</b>) no se mueve; "
                      f"la serie terminará un año después.")
        lay.addWidget(QLabel(
            f"Se insertará un anillo en el año <b>{destino}</b>.<br>"
            f"{efecto}<br><br>"
            f"El ancho del nuevo anillo se <b>resta</b> de un vecino, para que "
            f"el ancho total de la madera no cambie.", dlg))

        lay.addWidget(QLabel("Tomar el ancho del anillo:", dlg))
        rb_ant = QRadioButton("Anterior (el de más adentro)", dlg)
        rb_post = QRadioButton("Posterior (el de más afuera)", dlg)
        rb_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setChecked(True)
        lay.addWidget(rb_ant)
        lay.addWidget(rb_post)

        fila_w = QHBoxLayout()
        fila_w.addWidget(QLabel("Ancho del nuevo anillo (mm):", dlg))
        spin_w = QDoubleSpinBox(dlg)
        spin_w.setDecimals(4)
        spin_w.setRange(0.0, 100.0)
        spin_w.setSingleStep(0.01)
        fila_w.addWidget(spin_w)
        lay.addLayout(fila_w)
        lbl_ayuda = QLabel("", dlg)
        lbl_ayuda.setStyleSheet(f"color:{SECUNDARIO_QSS}; font-size:10px;")
        lbl_ayuda.setWordWrap(True)
        lay.addWidget(lbl_ayuda)

        def _vecino_actual():
            return insert_idx - 1 if rb_ant.isChecked() else insert_idx

        def _actualizar_max():
            v = _vecino_actual()
            if 0 <= v < len(self._anchos):
                disp = self._anchos[v]
                spin_w.setMaximum(disp)
                if spin_w.value() > disp:
                    spin_w.setValue(disp)
                lbl_ayuda.setText(
                    f"El vecino ({self._years()[v]}) mide {disp:.4f} mm; "
                    f"quedará con {max(disp - spin_w.value(), 0):.4f} mm.")
            else:
                spin_w.setMaximum(0.0)
                lbl_ayuda.setText("⚠️ No hay vecino en esa dirección.")

        rb_ant.toggled.connect(_actualizar_max)
        rb_post.toggled.connect(_actualizar_max)
        spin_w.valueChanged.connect(lambda _v: _actualizar_max())
        _actualizar_max()

        botones = QHBoxLayout()
        botones.addStretch()
        ok = QPushButton("Insertar", dlg)
        ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar", dlg)
        ca.clicked.connect(dlg.reject)
        botones.addWidget(ok)
        botones.addWidget(ca)
        lay.addLayout(botones)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        ancho_nuevo = spin_w.value()
        vecino = _vecino_actual()
        if vecino < 0 or vecino >= len(self._anchos):
            QMessageBox.warning(self, "Sin vecino",
                                "No hay un anillo vecino en esa dirección.")
            return
        if self._anchos[vecino] < ancho_nuevo - 1e-9:
            QMessageBox.warning(
                self, "Ancho insuficiente",
                f"El anillo vecino solo tiene {self._anchos[vecino]:.4f} mm.")
            return

        self._anchos[vecino] -= ancho_nuevo
        self._anchos.insert(insert_idx, ancho_nuevo)
        # Si se ancla la corteza, al crecer la serie el inicio retrocede (el
        # último año no se mueve). Si se ancla la médula, el inicio se queda y
        # la serie se extiende hacia el presente.
        if self._anclar_corteza():
            self._start_year -= 1
        self._refrescar_tabla(seleccionar=insert_idx)
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _actualizar_resumen_edicion(self):
        """Muestra en vivo cómo quedó la serie tras las ediciones."""
        lbl = getattr(self, "lbl_resumen_edicion", None)
        if lbl is None:
            return
        years = self._years()
        if not years:
            lbl.setText("")
            return
        n_orig = len(self._anchos_orig)
        dif = len(self._anchos) - n_orig
        txt = f"Ahora: {years[0]}–{years[-1]} ({len(self._anchos)} anillos)"
        if dif:
            txt += f"<br><b>{dif:+d}</b> respecto al original " \
                   f"({self._start_orig}–{self._start_orig + n_orig - 1})"
        lbl.setText(txt)

    def _insertar(self):
        idx = self._fila_sel()
        if idx is None:
            return
        years = self._years()
        dlg = QDialog(self)
        dlg.setWindowTitle("Insertar anillo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"Insertar un nuevo anillo junto al año <b>{years[idx]}</b>.<br>"
            f"El ancho del nuevo anillo se RESTA de un vecino (la madera se "
            f"reparte).", dlg))

        # Posición
        lay.addWidget(QLabel("Posición del nuevo anillo:", dlg))
        rb_antes = QRadioButton(f"Antes de {years[idx]}")
        rb_despues = QRadioButton(f"Después de {years[idx]}")
        rb_antes.setStyleSheet(self.ESTILO_RADIO)
        rb_despues.setStyleSheet(self.ESTILO_RADIO)
        rb_antes.setChecked(True)
        lay.addWidget(rb_antes); lay.addWidget(rb_despues)

        # Origen del ancho
        lay.addWidget(QLabel("Tomar el ancho del anillo:", dlg))
        rb_org_ant = QRadioButton("Anterior")
        rb_org_post = QRadioButton("Posterior")
        rb_org_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_org_post.setStyleSheet(self.ESTILO_RADIO)
        rb_org_ant.setChecked(True)
        lay.addWidget(rb_org_ant); lay.addWidget(rb_org_post)

        # Ancho
        fila_w = QHBoxLayout()
        fila_w.addWidget(QLabel("Ancho del nuevo anillo (mm):", dlg))
        spin_w = QDoubleSpinBox(dlg)
        spin_w.setDecimals(4); spin_w.setRange(0.0, 100.0)
        spin_w.setSingleStep(0.01)
        spin_w.setValue(0.0)
        fila_w.addWidget(spin_w)
        lay.addLayout(fila_w)
        lbl_ayuda = QLabel("", dlg)
        lbl_ayuda.setStyleSheet(f"color:{SECUNDARIO_QSS}; font-size:10px;")
        lay.addWidget(lbl_ayuda)

        def _actualizar_max():
            # Calcular índice de inserción y vecino origen para mostrar el máx
            insert_idx = idx if rb_antes.isChecked() else idx + 1
            if rb_org_ant.isChecked():
                vecino = insert_idx - 1
            else:
                vecino = insert_idx
            if 0 <= vecino < len(self._anchos):
                disponible = self._anchos[vecino]
                spin_w.setMaximum(disponible)
                lbl_ayuda.setText(
                    f"Máximo disponible del vecino: {disponible:.4f} mm")
            else:
                spin_w.setMaximum(0.0)
                lbl_ayuda.setText("⚠️ No hay vecino en esa dirección.")
        for rb in (rb_antes, rb_despues, rb_org_ant, rb_org_post):
            rb.toggled.connect(_actualizar_max)
        _actualizar_max()

        botones = QHBoxLayout(); botones.addStretch()
        ok = QPushButton("Insertar"); ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar"); ca.clicked.connect(dlg.reject)
        botones.addWidget(ok); botones.addWidget(ca)
        lay.addLayout(botones)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        ancho_nuevo = spin_w.value()
        insert_idx = idx if rb_antes.isChecked() else idx + 1
        vecino = insert_idx - 1 if rb_org_ant.isChecked() else insert_idx
        if vecino < 0 or vecino >= len(self._anchos):
            QMessageBox.warning(self, "Sin vecino",
                                "No hay un anillo vecino en esa dirección.")
            return
        if self._anchos[vecino] < ancho_nuevo - 1e-9:
            QMessageBox.warning(
                self, "Ancho insuficiente",
                f"El anillo vecino solo tiene {self._anchos[vecino]:.4f} mm.")
            return
        self._anchos[vecino] -= ancho_nuevo
        self._anchos.insert(insert_idx, ancho_nuevo)
        if self._anclar_corteza():
            self._start_year -= 1
        self._refrescar_tabla(seleccionar=insert_idx)
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _deshacer(self):
        self._anchos = list(self._anchos_orig)
        self._start_year = self._start_orig
        self._refrescar_tabla()
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _aplicar(self):
        if not self._anchos:
            QMessageBox.warning(self, "Serie vacía",
                                "La serie no puede quedar sin anillos.")
            return
        years = self._years()
        df_new = pd.DataFrame(
            {"Ancho_mm": self._anchos},
            index=pd.Index(years, name="Anio"),
        )
        if self._reemplazar is not None:
            self._reemplazar(self._nombre, df_new)
        QMessageBox.information(
            self, "Listo",
            f"Serie '{self._nombre}' actualizada: {len(self._anchos)} anillos, "
            f"años {years[0]}–{years[-1]}.")
        self.accept()



class DialogoAlineamientoAnillos(QDialog):
    """Muestra el resultado del alineamiento óptimo por programación
    dinámica: tabla de segmentos de desfase constante + lista de
    correcciones (anillos faltantes/sobrantes) detectadas.

    Permite reajustar la penalización y el máximo de correcciones en vivo
    y recalcular, para explorar entre un análisis conservador y uno
    exploratorio.
    """

    def __init__(self, serie_a, serie_b, shift_base, nombre_serie,
                 parent=None, penalizacion=3.0, max_correcciones=10,
                 obtener_serie=None, reemplazar=None, nombre_real=None):
        super().__init__(parent)
        self.setWindowTitle(f"Alineamiento óptimo — {nombre_serie}")
        self.resize(760, 600)
        self._serie_a = serie_a
        self._serie_b = serie_b
        self._shift_base = shift_base
        self._nombre = nombre_serie
        # Para abrir el editor de anillos: necesitamos el panel y el nombre
        # REAL de la serie (clave en series_datos), no el del título.
        self._obtener_serie = obtener_serie
        self._reemplazar = reemplazar
        self._nombre_real = nombre_real or nombre_serie

        layout = QVBoxLayout(self)

        info = QLabel(
            "<b>Alineamiento óptimo por programación dinámica.</b><br>"
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            f"Analizando desde el desfase base <b>{shift_base}</b>. "
            "Descompone la serie completa buscando dónde conviene insertar "
            "anillos faltantes o eliminar anillos sobrantes para maximizar "
            "la concordancia con la cronología. Cada fila es un tramo de "
            "desfase constante. Una <b>corrección ≠ 0</b> indica que en ese "
            "tramo la serie debería correrse respecto al anterior — revisa "
            "la madera en el año señalado. <i>La madera manda: esto es solo "
            "una guía de dónde mirar.</i>"
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Controles de recálculo ────────────────────────────────────
        fila_cfg = QHBoxLayout()
        lbl_pen = QLabel("Penalización:")
        lbl_pen.setToolTip(
            "Costo por cada corrección de anillo.\n"
            "• Bajo (1–3): exploratorio, propone más correcciones.\n"
            "• Alto (6–12): conservador, solo las muy evidentes.")
        fila_cfg.addWidget(lbl_pen)
        self.spin_pen = QDoubleSpinBox()
        self.spin_pen.setRange(0.5, 30.0)
        self.spin_pen.setSingleStep(0.5)
        self.spin_pen.setValue(penalizacion)
        self.spin_pen.setToolTip(lbl_pen.toolTip())
        fila_cfg.addWidget(self.spin_pen)

        lbl_max = QLabel("Máx. correcciones:")
        lbl_max.setToolTip(
            "Cantidad máxima de anillos (acumulada) que el algoritmo puede "
            "insertar o eliminar.")
        fila_cfg.addWidget(lbl_max)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 30)
        self.spin_max.setValue(max_correcciones)
        self.spin_max.setToolTip(lbl_max.toolTip())
        fila_cfg.addWidget(self.spin_max)

        btn_recalc = QPushButton("🔄 Recalcular")
        btn_recalc.clicked.connect(self._recalcular)
        fila_cfg.addWidget(btn_recalc)
        fila_cfg.addStretch()
        layout.addLayout(fila_cfg)

        # ── Resumen de correcciones ───────────────────────────────────
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setStyleSheet(
            "QLabel{background:rgba(230,126,34,0.12); border:1px solid "
            "rgba(230,126,34,0.4); border-radius:4px; padding:6px 8px; "
            "font-size:11px;}")
        layout.addWidget(self.lbl_resumen)

        # ── Tabla de segmentos ────────────────────────────────────────
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels([
            "Tramo (serie)", "Años calendario", "Corrección",
            "n", "r", "GLK", "Anillo término",
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tabla)

        # ── Botones ───────────────────────────────────────────────────
        fila_btn = QHBoxLayout()
        btn_copiar = QPushButton("📋 Copiar")
        btn_copiar.clicked.connect(self._copiar)
        fila_btn.addWidget(btn_copiar)
        btn_exportar = QPushButton("💾 Exportar CSV")
        btn_exportar.clicked.connect(self._exportar)
        fila_btn.addWidget(btn_exportar)
        # Botón para abrir el editor de anillos y aplicar las correcciones
        # que el análisis sugiere (insertar/eliminar conservando el ancho).
        if self._obtener_serie is not None and self._reemplazar is not None:
            btn_editar = QPushButton("✏️ Editar anillos de esta serie")
            btn_editar.setStyleSheet(
                "QPushButton{background-color:#8e44ad; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#9b59b6;}")
            btn_editar.setToolTip(
                "Abre el editor para insertar o eliminar anillos en los años "
                "señalados, conservando el ancho total de la madera.")
            btn_editar.clicked.connect(self._abrir_editor_anillos)
            fila_btn.addWidget(btn_editar)
        fila_btn.addStretch()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        fila_btn.addWidget(btn_cerrar)
        layout.addLayout(fila_btn)

        self._recalcular()

    def _abrir_editor_anillos(self):
        """Abre el editor de anillos con la serie REAL (anchos en mm) del
        panel principal, para aplicar correcciones de anillos faltantes/
        sobrantes conservando el ancho."""
        df = self._obtener_serie(self._nombre_real)
        if df is None or df.empty:
            QMessageBox.warning(
                self, "Serie no encontrada",
                "No se encontró la serie en el panel principal.")
            return
        # Recordatorio de las correcciones detectadas
        corrs = self._resultado.get("correcciones", []) if self._resultado else []
        if corrs:
            resumen = "; ".join(
                f"{c['tipo']} ~{c['anio_calendario']}" for c in corrs)
            QMessageBox.information(
                self, "Correcciones sugeridas",
                f"El análisis sugiere: {resumen}.\n\n"
                "En el editor, inserta o elimina los anillos en esos años. "
                "Recuerda: la madera manda — verifica antes de aplicar.")
        dlg = DialogoEditarAnillos(df, self._nombre_real, self._reemplazar,
                                    parent=self)
        dlg.exec()

    def _recalcular(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._resultado = alineamiento_optimo_anillos(
                self._serie_a, self._serie_b, self._shift_base,
                max_correcciones=self.spin_max.value(),
                penalizacion=self.spin_pen.value(),
            )
        finally:
            QApplication.restoreOverrideCursor()

        if self._resultado is None:
            self.lbl_resumen.setText("No hay datos suficientes para alinear.")
            self.tabla.setRowCount(0)
            return

        self._llenar_tabla()
        self._llenar_resumen()

    def _llenar_resumen(self):
        corrs = self._resultado["correcciones"]
        if not corrs:
            self.lbl_resumen.setText(
                "✅ No se detectaron anillos faltantes ni sobrantes: la serie "
                "alinea con la cronología sin correcciones internas en su "
                "posición actual.")
            return
        faltantes = [c for c in corrs if c["tipo"] == "faltante"]
        sobrantes = [c for c in corrs if c["tipo"] == "sobrante"]
        partes = []
        if faltantes:
            anios = ", ".join(str(c["anio_calendario"]) for c in faltantes)
            partes.append(
                f"<b>{len(faltantes)} posible(s) anillo(s) FALTANTE(s)</b> "
                f"(insertar) cerca de: {anios}")
        if sobrantes:
            anios = ", ".join(str(c["anio_calendario"]) for c in sobrantes)
            partes.append(
                f"<b>{len(sobrantes)} posible(s) anillo(s) SOBRANTE(s)</b> "
                f"(eliminar) cerca de: {anios}")
        self.lbl_resumen.setText(
            "⚠️ " + " &nbsp;•&nbsp; ".join(partes) +
            f"<br><span style='color:{color_secundario()};'>Revisa la madera en esos años "
            "antes de aceptar cualquier corrección.</span>")

    def _llenar_tabla(self):
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        segs = self._resultado["segmentos"]
        self.tabla.setRowCount(len(segs))
        for row, seg in enumerate(segs):
            it = QTableWidgetItem(f"{seg['serie_ini']}–{seg['serie_fin']}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 0, it)

            it = QTableWidgetItem(f"{seg['cal_ini']}–{seg['cal_fin']}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 1, it)

            corr = seg["correccion"]
            txt_corr = "0" if corr == 0 else f"{corr:+d}"
            it = QTableWidgetItem(txt_corr)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if corr != 0:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
                it.setToolTip(
                    "Corrección neta de anillos respecto al inicio de la "
                    "serie. Distinto de 0 = en este tramo la serie va corrida "
                    "respecto a su posición original.")
            self.tabla.setItem(row, 2, it)

            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole, int(seg["n"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 3, it)

            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole,
                float(round(seg["r"], 3)) if np.isfinite(seg["r"]) else 0.0)
            it.setBackground(QColor(_color_r(seg["r"])))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 4, it)

            glk_pct = seg["glk"] * 100 if np.isfinite(seg["glk"]) else float("nan")
            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole,
                float(round(glk_pct, 1)) if np.isfinite(glk_pct) else 0.0)
            it.setBackground(QColor(_color_glk(seg["glk"])))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 5, it)

            # Año de término calendario del tramo (con aviso si futuro)
            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(seg["cal_fin"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if seg["cal_fin"] > anio_actual:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
            self.tabla.setItem(row, 6, it)

    def _filas_texto(self):
        filas = [["Tramo_serie", "Anios_calendario", "Correccion",
                  "n", "r", "GLK_pct", "Anio_termino"]]
        for row in range(self.tabla.rowCount()):
            filas.append([
                self.tabla.item(row, c).text() if self.tabla.item(row, c)
                else "" for c in range(7)])
        return filas

    def _copiar(self):
        filas = self._filas_texto()
        QApplication.clipboard().setText(
            "\n".join("\t".join(f) for f in filas))

    def _exportar(self):
        ruta_default = os.path.join(_ultima_carpeta(), "alineamiento_anillos.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar alineamiento", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(self._filas_texto())
            QMessageBox.information(self, "Éxito", "Alineamiento exportado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{e}")



class DialogoCurvasNegativas(QDialog):
    """Elección del método para las series cuya curva de ajuste cruza cero.

    Muestra, para cada serie problemática, la serie cruda con las curvas de
    TODOS los métodos superpuestas y su correlación con la maestra al lado.
    Así se elige viendo la consecuencia, que es de lo que se trata.

    Se elige UN método para todo el grupo, no uno por serie: el informe de la
    cronología tiene que poder decir «las N series con curva negativa se
    estandarizaron con X», y eso es lo que hace el resultado reproducible.
    """

    def __init__(self, series, problematicas, maestra, metodo_original,
                 parent=None, ventana_mm=None, rigidez=None):
        super().__init__(parent)
        self.setWindowTitle("Series con curva de ajuste negativa")
        self.resize(1000, 700)
        self._series = series
        self._problem = list(problematicas)
        self._maestra = maestra
        self._vent = ventana_mm
        self._rig = rigidez

        self._auto = elegir_metodo_para_grupo(
            series, self._problem, maestra,
            ventana_mm=ventana_mm, rigidez=rigidez)

        lay = QVBoxLayout(self)
        cab = QLabel(
            f"<b>{len(self._problem)} serie(s)</b> tienen una curva de ajuste "
            f"que cruza cero con el método <b>{metodo_original}</b>.<br>"
            "En esos años el índice no significa lo mismo que en el resto de "
            "la serie: DPI reemplaza la tendencia por la media, y el índice "
            "puede dispararse.<br>"
            "Elige con qué método estandarizar <i>solo estas series</i>. Las "
            "demás mantienen el método original.")
        cab.setWordWrap(True)
        lay.addWidget(cab)

        # Tabla comparativa de métodos sobre el grupo
        self.tabla = QTableWidget(len(self._auto["tabla"]), 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Método", "Cruza cero", "r mediana con la maestra",
             "Índice máximo", "Series"])
        for i, t in enumerate(self._auto["tabla"]):
            vals = [t["metodo"],
                    "sí" if t["cruces"] else "no",
                    "—" if not np.isfinite(t["r_mediana"]) else f"{t['r_mediana']:.3f}",
                    "—" if not np.isfinite(t["indice_max"]) else f"{t['indice_max']:.2f}",
                    str(t["n_series"])]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if not t["valido"]:
                    it.setForeground(QColor("#d9534f"))
                elif t["metodo"] == self._auto["metodo"]:
                    it.setForeground(QColor("#5cb85c"))
                self.tabla.setItem(i, j, it)
        self.tabla.resizeColumnsToContents()
        self.tabla.setMaximumHeight(190)
        lay.addWidget(self.tabla)

        nota = QLabel(
            "El criterio es la correlación con la maestra, no el índice "
            "máximo: un máximo cercano a 1 también se consigue cuando la "
            "curva se come toda la variabilidad, y la correlación distingue "
            "esos dos casos.")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color:{SECUNDARIO_QSS}; font-size:11px;")
        lay.addWidget(nota)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Serie:"))
        self.combo_serie = QComboBox()
        self.combo_serie.addItems(self._problem)
        self.combo_serie.currentIndexChanged.connect(self._dibujar)
        fila.addWidget(self.combo_serie, 1)
        self.chk_por_serie = QCheckBox("Elegir por serie")
        self.chk_por_serie.setToolTip(
            "Sin marcar, se aplica UN método a todas las series con curva\n"
            "negativa, que es lo reproducible: el informe puede decir «las N\n"
            "series afectadas se estandarizaron con X».\n\n"
            "Marcado, cada serie lleva el suyo. Úsalo cuando las series\n"
            "problemáticas tengan historias de crecimiento muy distintas\n"
            "entre sí; el informe detallará el método de cada una.")
        self.chk_por_serie.toggled.connect(self._cambiar_modo)
        fila.addWidget(self.chk_por_serie)

        self.lbl_aplicar = QLabel("Aplicar a todas:")
        fila.addWidget(self.lbl_aplicar)
        self.combo_metodo = QComboBox()
        for t in self._auto["tabla"]:
            etq = t["metodo"] + ("" if t["valido"] else "  (cruza cero)")
            self.combo_metodo.addItem(etq, t["metodo"])
        if self._auto["metodo"]:
            i = self.combo_metodo.findData(self._auto["metodo"])
            if i >= 0:
                self.combo_metodo.setCurrentIndex(i)
        self.combo_metodo.currentIndexChanged.connect(self._on_metodo_grupo)
        fila.addWidget(self.combo_metodo, 1)
        lay.addLayout(fila)

        # Elección individual: parte con el método del grupo para todas, así
        # marcar la casilla no borra lo que ya se había decidido.
        inicial = self._auto["metodo"] or metodo_original
        self._por_serie = {n: inicial for n in self._problem}

        self.grafico = pg.PlotWidget(title="Serie cruda y curvas de ajuste")
        _gr.aplicar_a_pyqtgraph(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.setLabel("left", "Ancho (mm)")
        self.grafico.setLabel("bottom", "Año")
        _agregar_hover_anio(self.grafico)
        lay.addWidget(self.grafico, 1)

        self.lbl_detalle = QLabel("")
        self.lbl_detalle.setWordWrap(True)
        lay.addWidget(self.lbl_detalle)

        botones = QHBoxLayout()
        botones.addStretch()
        b_auto = QPushButton("Usar el que el programa recomienda")
        b_auto.clicked.connect(self._usar_auto)
        botones.addWidget(b_auto)
        b_ok = QPushButton("Aplicar")
        b_ok.setStyleSheet("background-color:#5cb85c; color:white; "
                           "font-weight:bold; padding:6px 14px;")
        b_ok.clicked.connect(self.accept)
        botones.addWidget(b_ok)
        b_no = QPushButton("Dejar el método original")
        b_no.clicked.connect(self.reject)
        botones.addWidget(b_no)
        lay.addLayout(botones)
        self._dibujar()

    def _cambiar_modo(self, marcado):
        self.lbl_aplicar.setText("Método de esta serie:" if marcado
                                 else "Aplicar a todas:")
        if not marcado:
            m = self.combo_metodo.currentData()
            self._por_serie = {n: m for n in self._problem}
        self._dibujar()

    def _on_metodo_grupo(self, *_):
        m = self.combo_metodo.currentData()
        if self.chk_por_serie.isChecked():
            self._por_serie[self.combo_serie.currentText()] = m
        else:
            self._por_serie = {n: m for n in self._problem}
        self._dibujar()

    def metodos_por_serie(self) -> dict:
        """Método elegido para cada serie problemática."""
        if self.chk_por_serie.isChecked():
            return dict(self._por_serie)
        m = self.combo_metodo.currentData()
        return {n: m for n in self._problem}

    def _usar_auto(self):
        if self._auto["metodo"]:
            i = self.combo_metodo.findData(self._auto["metodo"])
            if i >= 0:
                self.combo_metodo.setCurrentIndex(i)

    def metodo_elegido(self):
        return self.combo_metodo.currentData()

    def _dibujar(self):
        self.grafico.clear()
        nom = self.combo_serie.currentText()
        # En modo individual, el combo refleja lo elegido para ESTA serie
        if self.chk_por_serie.isChecked() and nom in self._por_serie:
            i = self.combo_metodo.findData(self._por_serie[nom])
            if i >= 0 and self.combo_metodo.currentIndex() != i:
                self.combo_metodo.blockSignals(True)
                self.combo_metodo.setCurrentIndex(i)
                self.combo_metodo.blockSignals(False)
        if not nom or nom not in self._series:
            return
        obj = self._series[nom]
        col = obj["Ancho_mm"] if isinstance(obj, pd.DataFrame) else obj
        col = pd.to_numeric(col, errors="coerce").dropna()
        x = col.index.to_numpy(np.int64)
        self.grafico.plot(x, col.to_numpy(dtype=float),
                          pen=pg.mkPen("#888888", width=1), name=nom)
        colores = {"spline": "#4aa3dc", "negexp": "#e0a030",
                   "linear": "#e04040", "media_movil": "#5cb85c",
                   "media": "#a06ad0"}
        elegido = (self._por_serie.get(nom) if self.chk_por_serie.isChecked()
                   else self.metodo_elegido())
        filas = []
        for m in METODOS_DETREND:
            try:
                t = _fit_trend(col.to_numpy(dtype=float), m,
                               ventana_mm=self._vent, rigidez=self._rig)
            except Exception:
                continue
            t = np.asarray(t, dtype=float)
            ancho = 3 if m == elegido else 1
            self.grafico.plot(
                x, t, pen=pg.mkPen(colores.get(m, "#ccc"), width=ancho),
                name=m + (" ←" if m == elegido else ""))
            d = diagnosticar_curva(col, m, self._vent, self._rig)
            idx = d["indice"]
            r = float("nan")
            com = idx.index.intersection(self._maestra.index)
            if len(com) >= 20:
                a = idx.loc[com].to_numpy(dtype=float)
                b = self._maestra.loc[com].to_numpy(dtype=float)
                if np.std(a) > 1e-12 and np.std(b) > 1e-12:
                    r = float(np.corrcoef(a, b)[0, 1])
            filas.append(
                f"<b>{m}</b>: cruza cero en {d['n_parches']} de {d['total']} "
                f"años · índice máx {d['indice_max']:.2f} · "
                f"r con la maestra {'—' if r != r else f'{r:.3f}'}")
        self.grafico.addLine(y=0, pen=pg.mkPen("#d9534f", width=1,
                                               style=Qt.PenStyle.DashLine))
        self.lbl_detalle.setText("<br>".join(filas))
