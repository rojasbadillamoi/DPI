"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import os
import pandas as pd
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from dpi.ciencia.datacion import aplicar_modo_cofecha
from dpi.formatos.exportacion import asegurar_extension
from dpi.ui.series_util import _ultima_carpeta

def _exportar_una_serie(self, nombre: str):
    """Exporta UNA serie por nombre (usado al exportar varias a la vez)."""
    prev = self.lista_series.currentItem()
    for i in range(self.lista_series.count()):
        it = self.lista_series.item(i)
        if it.text() == nombre:
            self.lista_series.setCurrentItem(it)
            break
    try:
        self._exportar_serie_por_nombre(nombre)
    finally:
        if prev is not None:
            self.lista_series.setCurrentItem(prev)


def exportar_serie_codatada(self):
    """Exporta la serie marcada con formato según extensión.

    Si el modo COFECHA está activo y aplica a este tipo (serie o
    cronología), ofrece guardar la serie ESTANDARIZADA (la misma
    transformación que se usa para las correlaciones) en vez de los
    datos crudos. Así el usuario puede subir una serie, activar el modo
    COFECHA y guardar la versión estandarizada directamente.
    """
    # Exporta la(s) serie(s) SELECCIONADA(S) (filas resaltadas), no las
    # marcadas con casilla: la casilla es solo para elegir qué se grafica.
    seleccionadas = [it.text() for it in self.lista_series.selectedItems()
                     if it.text() in self.series_datos]
    if not seleccionadas:
        nombre_unico = self._serie_para_accion("exportar")
        if nombre_unico is None:
            return
        seleccionadas = [nombre_unico]

    if len(seleccionadas) > 1:
        resp = QMessageBox.question(
            self, "Varias series seleccionadas",
            f"Hay {len(seleccionadas)} series seleccionadas.\n\n"
            "¿Exportarlas todas? Se pedirá una ubicación por cada una.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if resp != QMessageBox.StandardButton.Yes:
            return
        for nom in seleccionadas:
            self._exportar_una_serie(nom)
        return

    self._exportar_serie_por_nombre(seleccionadas[0])


def _exportar_serie_por_nombre(self, nombre: str):
    """Cuerpo real de la exportación, para una serie ya elegida."""
    df = self.series_datos.get(nombre)
    if df is None or df.empty:
        QMessageBox.warning(self, "Sin datos",
                            f"'{nombre}' no tiene datos para exportar.")
        return
    es_crono = nombre.startswith("📚 ")

    # ¿El modo COFECHA aplica a este tipo (serie/cronología)?
    cofecha_aplica = (
        self.btn_modo_cofecha.isChecked() and (
            (es_crono and self.chk_cof_crono.isChecked()) or
            (not es_crono and self.chk_cof_serie.isChecked())
        )
    )

    exportar_std = False
    if cofecha_aplica:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Modo COFECHA activo")
        box.setText(
            f"El modo COFECHA está activo para esta {'cronología' if es_crono else 'serie'}.\n\n"
            f"¿Qué quieres guardar de '{nombre}'?")
        b_std = box.addButton("Estandarizada (COFECHA)",
                              QMessageBox.ButtonRole.YesRole)
        box.addButton("Datos originales", QMessageBox.ButtonRole.NoRole)
        b_cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is b_cancel:
            return
        exportar_std = box.clickedButton() is b_std

    # ── Exportar ESTANDARIZADA (índice residual COFECHA, 2 columnas) ──
    if exportar_std:
        serie_std = aplicar_modo_cofecha(
            df["Ancho_mm"], **self._modo_cofecha_params)
        nombre_limpio = nombre.replace("📚 ", "").strip()
        self._guardar_serie_2col(
            serie_std, f"{nombre_limpio}_cofecha",
            "Exportar serie estandarizada (COFECHA)",
            estandarizada=True)
        return

    # ── Cronologías → formato 2-columnas con coma decimal ──
    if es_crono:
        nombre_limpio = nombre.replace("📚 ", "").strip()
        # Añadir el tipo de cronología al nombre de archivo por defecto
        # (RES/STD/RAW) para que quede claro qué se guardó. Se usa el tipo
        # de la cronología ACTIVA si el nombre coincide; si no, el de la
        # metadata disponible.
        tipo_c = ""
        if nombre_limpio == self._nombre_cronologia_activa:
            tipo_c = (self.meta_cronologia or {}).get("tipo_cronologia", "")
        tag = {"residual": "RES", "standard": "STD",
               "raw": "RAW"}.get((tipo_c or "").lower(), "")
        nombre_archivo = f"{nombre_limpio}_{tag}" if tag else nombre_limpio
        self._guardar_serie_2col(
            pd.to_numeric(df["Ancho_mm"], errors="coerce"),
            nombre_archivo, "Exportar cronología", estandarizada=False)
        return

    # ── Series normales → exportador Tucson (anchos crudos en mm) ──
    mediciones = [{"anio": int(idx), "ancho_mm": float(val)}
                  for idx, val in df["Ancho_mm"].items()]
    exp = getattr(self._ventana_padre, "exportador", None)
    if exp:
        exp.exportar_datos(nombre, mediciones)
    else:
        QMessageBox.information(self, "Sin exportador",
                                "No hay un exportador disponible.")


def _guardar_serie_2col(self, serie, nombre_archivo, titulo,
                         estandarizada=False):
    """Guarda una serie en formato 2 columnas (Año, Valor) con coma
    decimal. Usado para cronologías y para series estandarizadas
    COFECHA (que son índices residuales adimensionales, no anchos en
    mm, por lo que NO van por el exportador Tucson)."""
    ruta_default = os.path.join(_ultima_carpeta(), f"{nombre_archivo}.txt")
    ruta, fmt = QFileDialog.getSaveFileName(
        self, titulo, ruta_default,
        "Texto separado por tabulaciones (*.txt);;"
        "Tucson (*.rwl);;"
        "CSV separado por punto y coma (*.csv);;"
        "Excel (*.xlsx);;LibreOffice (*.ods)",
        options=QFileDialog.Option.DontUseNativeDialog,
    )
    if not ruta:
        return
    ruta = asegurar_extension(ruta, fmt)
    _ultima_carpeta(ruta)
    from dpi.formatos.exportacion import exportar_serie_2col
    try:
        n_anios = exportar_serie_2col(serie, ruta, nombre_archivo)
        if estandarizada:
            nota = ("Valores ESTANDARIZADOS por modo COFECHA "
                    "(índice residual adimensional, no anchos en mm).")
        else:
            nota = "Formato 2 columnas (Año, Valor) con coma decimal."
        QMessageBox.information(
            self, "✅ Serie exportada",
            f"Archivo guardado:\n{ruta}\n\n{nota}\n"
            f"Años: {n_anios}")
    except Exception as exc:
        QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")
