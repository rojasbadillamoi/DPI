"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
from modulo_widgets import _ensanchar_dialogo
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt
from modulo_dialogos_series import DialogoEditarAnillos

def probar_correccion_seleccionada(self):
    """Aplica la corrección seleccionada de forma TEMPORAL (con respaldo)
    para ver cómo queda la serie corregida, sin tocar la serie real ni
    re-buscar (para no reiniciar la tabla)."""
    fila = self.tabla_sugerencias.currentRow()
    if fila < 0 or fila >= len(self._sugerencias):
        return
    sug = self._sugerencias[fila]
    nombre = self._nombre_problema
    df_corr = sug.get("df_corregido")
    if nombre not in self.series_datos or df_corr is None:
        QMessageBox.warning(self, "Sin serie",
                            "No se encontró la serie a corregir.")
        return
    try:
        self.modelo_series.probar_correccion(nombre, df_corr)
    except (ValueError, TypeError, KeyError) as exc:
        QMessageBox.warning(self, "Corrección inválida", str(exc))
        return
    self._prueba_sug = dict(sug)
    self._series_modificadas(regraficar=False)

    self._marcar_prueba_ui(True)
    self.btn_aplicar.setEnabled(True)
    # Redibujar la serie corregida y su preview de correlación
    self.graficar_series()
    self._dibujar_preview(self._prueba_sug)
    self.lbl_prueba.setText(
        "● Probando corrección (sin aplicar)<br>"
        + self._texto_cambio_sugerencia(self._prueba_sug, nombre))
    self.lbl_prueba.setVisible(True)


def _marcar_prueba_ui(self, activa: bool):
    self.btn_descartar_prueba.setEnabled(activa)
    self.btn_probar.setEnabled(not activa)
    if not activa:
        self.lbl_prueba.setVisible(False)
        self.lbl_prueba.setText("")


def _descartar_prueba(self, silencioso: bool = False):
    """Recupera la serie anterior a la prueba, no la original importada."""
    if not self.modelo_series.descartar_correccion():
        return
    self._prueba_sug = None
    self._marcar_prueba_ui(False)
    self._series_modificadas()
    if not silencioso:
        try:
            self.buscar_errores()
        except Exception:
            pass


def aplicar_correccion_seleccionada(self):
    """Aplica la corrección a la serie REAL, tras confirmar exactamente
    qué datos se modifican. Ofrece hacerlo conservando el ancho (editor)
    o de forma automática (ancho promedio)."""
    # Determinar la sugerencia a aplicar: la que se está probando, o la
    # seleccionada en la tabla.
    if self.modelo_series.nombre_en_prueba is not None:
        sug = self._prueba_sug
        nombre = self.modelo_series.nombre_en_prueba
    else:
        fila = self.tabla_sugerencias.currentRow()
        if fila < 0 or fila >= len(self._sugerencias):
            return
        sug = self._sugerencias[fila]
        nombre = self._nombre_problema
    if nombre not in self.series_datos:
        QMessageBox.warning(self, "Sin serie",
                            "No se encontró la serie a corregir.")
        return

    # Confirmación: mostrar QUÉ datos se modifican y CÓMO aplicarlos.
    caja = QMessageBox(self)
    caja.setIcon(QMessageBox.Icon.Question)
    caja.setWindowTitle("Confirmar corrección")
    caja.setTextFormat(Qt.TextFormat.RichText)
    caja.setText(
        "¿Aplicar esta corrección a la serie real?<br><br>"
        + self._texto_cambio_sugerencia(sug, nombre))
    btn_ancho = caja.addButton("Conservando ancho (editor)",
                               QMessageBox.ButtonRole.AcceptRole)
    btn_auto = caja.addButton("Automático (ancho promedio)",
                              QMessageBox.ButtonRole.AcceptRole)
    caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    # QMessageBox reparte el ancho según el TEXTO, no según los botones, así
    # que con botones de etiqueta larga estos salían cortados y no se podía
    # leer qué hacía cada uno. Se fuerza un ancho mínimo suficiente.
    _ensanchar_dialogo(caja, minimo=560)
    caja.exec()
    elegido = caja.clickedButton()
    if elegido not in (btn_ancho, btn_auto):
        return  # cancelado

    if elegido is btn_ancho:
        # El editor debe recibir la serie anterior a la prueba.
        self._descartar_prueba(silencioso=True)
        df = self.series_datos[nombre]
        dlg = DialogoEditarAnillos(df, nombre, self.reemplazar_serie, parent=self,
                                   sugerencia=sug)
        dlg.exec()
    else:
        try:
            if self.modelo_series.nombre_en_prueba is not None:
                self.modelo_series.confirmar_correccion()
            else:
                df_corr = sug.get("df_corregido")
                if df_corr is None:
                    raise ValueError("La sugerencia no contiene datos corregidos")
                self.modelo_series.actualizar(nombre, df_corr)
        except (ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "Corrección inválida", str(exc))
            return
        self._prueba_sug = None
        self._series_modificadas(regraficar=False)
        self._marcar_prueba_ui(False)

    # Refrescar tras aplicar
    self.spin_edit_year.setValue(int(sug["anio"]))
    for i in range(self.lista_series.count()):
        item = self.lista_series.item(i)
        if item.text() == nombre:
            self.lista_series.setCurrentItem(item)
            break
    self._limpiar_preview()
    self._sugerencias.clear()
    self.tabla_sugerencias.setRowCount(0)
    self.btn_aplicar.setEnabled(False)
    self.btn_probar.setEnabled(False)
    self.graficar_series()
    self.buscar_errores()
