"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import os
import pandas as pd
from dpi.ciencia.estadistica import calcular_eps_rbar_movil
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication, QProgressDialog
from PyQt6.QtCore import Qt
from dpi.formatos.exportacion import asegurar_extension
from dpi.ciencia.cronologia import _detrend_serie_indice, detectar_series_problematicas
from dpi.ciencia.cronologia import _construir_cronologia_desde_series
from dpi.formatos.cronologias import _guardar_metadatos_cronologia, _exportar_cronologia_df, _leer_cronologia_guardada
from dpi.ui.series_util import _ultima_carpeta
from modulo_dialogos_series import DialogoCurvasNegativas

def generar_cronologia(self):
    nombres = self._series_marcadas()
    if not nombres:
        QMessageBox.warning(self, "Atención", "Seleccione al menos una serie.")
        return

    tipo_sel = self.combo_tipo.currentText()
    metodo = self.combo_metodo.currentText()
    # currentData() devuelve el valor interno en inglés (biweight/mean/
    # median) aunque el texto visible esté en español.
    agreg = self.combo_agreg.currentData() or "biweight"
    aplicar_log = bool(self.chk_log_crono.isChecked())
    nombre_base = self.input_nombre.text().strip() or "Cronologia"

    tipos = ["raw", "standard", "residual"] if tipo_sel == "Todas" else [tipo_sel]

    # ── Series cuya curva de ajuste cruza cero ──────────────────────
    # Es el «dirty dog» de ARSTAN. DPI nunca produce índices negativos
    # porque reemplaza la tendencia por la media donde sale <= 0, pero
    # hacerlo en silencio deja años cuyo índice no significa lo mismo que
    # el del resto de la serie. Acá se detectan, se cuentan, y se le da al
    # usuario la opción de estandarizarlas con otro método.
    # Opciones ARSTAN: solo se activan si el usuario tocó alguna, para
    # que una corrida corriente siga dando exactamente lo de siempre.
    try:
        m2 = self.combo_metodo2.currentData() or None
        ar_ops = {
            "metodo1": metodo,
            "rigidez1": int(self.spin_rigidez1.value()),
            "metodo2": m2,
            "rigidez2": int(self.spin_rigidez2.value()),
            "rigidez_minima": int(self.spin_rig_min.value()),
            "estabilizar": bool(self.chk_estabilizar.isChecked()),
            "rigidez_estab": int(self.spin_rig_estab.value()),
            "normalizar": bool(self.chk_normalizar.isChecked()),
            "por_resta": bool(self.chk_por_resta.isChecked()),
            "log_previo": bool(self.chk_log_arstan.isChecked()),
        }
        usa_arstan = bool(m2 or ar_ops["estabilizar"] or ar_ops["normalizar"]
                          or ar_ops["por_resta"] or ar_ops["log_previo"]
                          or ar_ops["rigidez_minima"]
                          or ar_ops["rigidez1"] < 0)
        self._arstan_ops = ar_ops if usa_arstan else None
    except Exception:
        self._arstan_ops = None

    self._metodo_alterno = None
    self._metodos_por_serie = {}
    self._series_alternas = []
    self._diag_negativas = {}
    if tipo_sel != "raw" and metodo != "media":
        vmm0 = (self.spin_ventana_mm.value()
                if metodo == "media_movil" else None)
        try:
            probl = detectar_series_problematicas(
                self._series_cronologia, nombres, metodo, ventana_mm=vmm0)
        except Exception:
            probl = {}
        if probl:
            # Maestra de referencia con las series SANAS, para poder
            # comparar métodos sin que las problemáticas se autoevalúen.
            sanas = [n for n in nombres if n not in probl]
            maestra = None
            try:
                cols = []
                for n in sanas:
                    idx = _detrend_serie_indice(
                        self._series_cronologia[n]["Ancho_mm"], metodo,
                        ventana_mm=vmm0)
                    if len(idx) > 10:
                        idx.name = n
                        cols.append(idx)
                if cols:
                    maestra = pd.concat(cols, axis=1).mean(axis=1).dropna()
            except Exception:
                maestra = None
            if maestra is not None and len(maestra) > 30:
                dlg = DialogoCurvasNegativas(
                    self._series_cronologia, list(probl), maestra, metodo,
                    parent=self, ventana_mm=vmm0)
                self._diag_negativas = probl
                if dlg.exec():
                    porserie = dlg.metodos_por_serie()
                    distintos = {n: m for n, m in porserie.items()
                                 if m and m != metodo}
                    if distintos:
                        self._metodos_por_serie = distintos
                        self._series_alternas = list(distintos)
                        unicos = set(distintos.values())
                        self._metodo_alterno = (unicos.pop()
                                                if len(unicos) == 1
                                                else None)

    progreso = QProgressDialog("Generando cronología...", None, 0, 100, self)
    progreso.setWindowTitle("Procesando")
    progreso.setWindowModality(Qt.WindowModality.WindowModal)
    progreso.setMinimumDuration(0)
    progreso.setMaximum(100)
    progreso.setValue(0)
    progreso.setCancelButton(None)
    QApplication.processEvents()

    resultados = {}
    for i, tipo in enumerate(tipos):
        pct_inicio = int(i * 50 / len(tipos))
        progreso.setLabelText(f"Generando cronología {tipo}... ({i+1}/{len(tipos)})")
        progreso.setValue(pct_inicio)
        QApplication.processEvents()

        try:
            # Solo pasar ventana_mm si el método es media_movil
            vmm = (self.spin_ventana_mm.value()
                   if metodo == "media_movil" else None)
            df, meta = _construir_cronologia_desde_series(
                self._series_cronologia, nombres, tipo, metodo, agreg,
                ventana_mm=vmm, aplicar_log=aplicar_log,
                metodo_alterno=self._metodo_alterno,
                series_alternas=self._series_alternas,
                metodos_por_serie=self._metodos_por_serie,
                arstan=self._arstan_ops,
            )
            meta["curvas_negativas"] = {
                n: {"n_parches": d["n_parches"], "total": d["total"],
                    "tramos": d["tramos"],
                    "indice_max": d["indice_max"]}
                for n, d in (self._diag_negativas or {}).items()}
            meta["metodo_alterno"] = self._metodo_alterno
            meta["series_alternas"] = list(self._series_alternas)
            meta["metodos_por_serie"] = dict(self._metodos_por_serie)
            meta["arstan_ops"] = dict(self._arstan_ops or {})
            nombre = f"{nombre_base}_{tipo}" if len(tipos) > 1 else nombre_base
            meta["nombre"] = nombre

            # Rbar y EPS ahora vienen calculados desde dentro de
            # _construir_cronologia_desde_series sobre las series
            # DETRENDADAS (comparable con ARSTAN). Antes acá se
            # sobrescribían usando series raw, lo que inflaba el Rbar
            # porque las tendencias decadales hacen covariar las
            # series brutas a largo plazo.

            resultados[tipo] = (df, meta)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Error en cronología {tipo}:\n{exc}")

    if not resultados:
        progreso.close()
        return

    progreso.setLabelText("Calculando EPS / Rbar móvil...")
    progreso.setValue(50)
    QApplication.processEvents()

    # Callback de progreso para mantener la UI responsiva durante el
    # cálculo de EPS / Rbar móvil (que itera sobre muchos años con
    # ventana móvil — es la parte más lenta).
    def _cb_progreso(pct):
        progreso.setValue(50 + int(pct * 0.45))
        QApplication.processEvents()

    # Determinar paso para muestreo. El usuario configura ventana y paso
    # en la UI (default 50/25 estilo ARSTAN para comparación directa).
    ventana_eps = self.spin_ventana_eps.value()
    paso_eps = self.spin_paso_eps.value()

    eps_df = calcular_eps_rbar_movil(
        self._series_cronologia, nombres, window=ventana_eps,
        paso=paso_eps, progreso=_cb_progreso,
    )
    self.eps_movil = eps_df

    if len(resultados) > 1:
        frames = []
        for tipo, (df, meta) in resultados.items():
            col = meta.get("columna_valor", tipo.capitalize())
            frames.append(df[[col]].rename(columns={col: tipo.capitalize()}))
            if "N" in df.columns:
                frames.append(df[["N"]])
        combined = pd.concat(frames, axis=1)
        combined = combined.loc[:, ~combined.columns.duplicated()]
        last_tipo = list(resultados.keys())[-1]
        _, last_meta = resultados[last_tipo]
        last_meta["nombre"] = nombre_base
        last_meta["tipo_cronologia"] = "todas"
        last_meta["columna_valor"] = "Standard"
        last_meta["columnas_disponibles"] = [t.capitalize() for t in resultados.keys()]
        if not eps_df.empty:
            last_meta["EPS_movil"] = eps_df["EPS"].dropna().to_dict()
            last_meta["Rbar_movil"] = eps_df["Rbar"].dropna().to_dict()
        self.cronologia_df = combined
        self.cronologia_meta = last_meta
    else:
        tipo_unico = list(resultados.keys())[0]
        self.cronologia_df, self.cronologia_meta = resultados[tipo_unico]
        if not eps_df.empty:
            self.cronologia_meta["EPS_movil"] = eps_df["EPS"].dropna().to_dict()
            self.cronologia_meta["Rbar_movil"] = eps_df["Rbar"].dropna().to_dict()

    progreso.setValue(100)
    progreso.close()

    self._pintar_cronologia()
    self._actualizar_info()
    self._sincronizar_estado_botones()


def cargar_cronologia(self):
    ruta, _ = QFileDialog.getOpenFileName(
        self, "Cargar cronología", _ultima_carpeta(),
        "Cronologías (*.csv *.txt *.xlsx *.ods);;Todos (*.*)"
    )
    if not ruta:
        return
    _ultima_carpeta(ruta)

    try:
        df, meta = _leer_cronologia_guardada(ruta)
    except Exception as exc:
        QMessageBox.critical(self, "Error", f"No se pudo abrir la cronología:\n{exc}")
        return

    meta.setdefault("nombre", os.path.splitext(os.path.basename(ruta))[0])
    meta.setdefault("columna_valor", df.columns[0])
    self.cronologia_df = df
    self.cronologia_meta = meta
    self.input_nombre.setText(meta.get("nombre", "Cronología"))
    self._pintar_cronologia()
    self._actualizar_info()
    self._sincronizar_estado_botones()


def exportar_cronologia(self):
    if self.cronologia_df is None or self.cronologia_df.empty:
        QMessageBox.warning(self, "Atención", "No hay cronología para exportar.")
        return
    nombre = self.cronologia_meta.get("nombre", "cronologia")
    ruta_default = os.path.join(_ultima_carpeta(), nombre)
    ruta, fmt = QFileDialog.getSaveFileName(
        self, "Exportar cronología", ruta_default,
        "Texto 2 columnas (*.txt);;Tucson (*.rwl);;Excel (*.xlsx);;"
        "LibreOffice (*.ods);;CSV (*.csv)",
        options=QFileDialog.Option.DontUseNativeDialog,
    )
    if not ruta:
        return
    ruta = asegurar_extension(ruta, fmt)
    _ultima_carpeta(ruta)
    try:
        _exportar_cronologia_df(self.cronologia_df, ruta)
        meta = dict(self.cronologia_meta)
        meta["archivo"] = os.path.basename(ruta)
        _guardar_metadatos_cronologia(ruta, meta)
        QMessageBox.information(self, "OK", f"Cronología exportada:\n{ruta}")
    except Exception as exc:
        QMessageBox.critical(self, "Error", f"No se pudo exportar:\n{exc}")
