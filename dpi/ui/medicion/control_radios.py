"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QListWidgetItem
from PyQt6.QtCore import Qt, QSignalBlocker

def _finalizar_camino(self):
    if not self.datos_medidos:
        return
    sufijo = "A" if not self.caminos_guardados else "B"
    nombre_defecto = self.input_codigo.text().strip() + sufijo
    nombre, ok = QInputDialog.getText(self, "Guardar Radio", "Identificador:", text=nombre_defecto)
    if not ok:
        return
    nombre = nombre.strip()
    if not nombre or nombre in self.caminos_guardados:
        return QMessageBox.warning(self, "Identificador", "Nombre vacío o ya existente.")

    self.modelo_sesion.guardar_radio(nombre, self._capturar_radio(nombre))
    item = QListWidgetItem(nombre)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Checked)
    self.lista_caminos.addItem(item)

    self.vista.limpiar_historial()
    self.vista.modelo_medicion.limpiar()
    self.vista.anomalias.clear()
    self._ultima_ruta_exportada = None
    with QSignalBlocker(self.check_tiene_medula), QSignalBlocker(self.check_tiene_corteza):
        self.check_tiene_medula.setChecked(False)
        self.check_tiene_corteza.setChecked(False)
    self.vista.redibujar_todo()

    self.spin_medula.blockSignals(True)
    self.spin_corteza.blockSignals(True)
    self.spin_medula.setValue(0)
    self.spin_corteza.setValue(0)
    self.spin_medula.blockSignals(False)
    self.spin_corteza.blockSignals(False)

    self.vista.cargar_caminos_inactivos(self.caminos_guardados)
    self._guardar_estado()
    self._actualizar_grafico()
    self._intensidad.invalidar_si_cambio()
    self.label_estado.setText(f"Radio '{nombre}' guardado. Listo para medir nuevo radio.")


def _editar_camino(self):
    items = self.lista_caminos.selectedItems()
    if not items:
        return QMessageBox.information(self, "Aviso", "Seleccione un radio para editar.")
    if self.datos_medidos:
        if QMessageBox.question(
            self, "Atención",
            "Tiene un radio en progreso. ¿Desea descartarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

    nombre = items[0].text()
    datos = self.caminos_guardados[nombre]
    if not datos.puntos or datos.datos_historicos:
        return QMessageBox.warning(self, "Aviso", "El radio no tiene coordenadas editables.")
    self.modelo_sesion.eliminar_radio(nombre)

    self.vista.limpiar_historial()
    self.vista.modelo_medicion.limpiar()
    self.vista.redibujar_todo()

    self.vista.eliminar_camino_inactivo(nombre)

    self.lista_caminos.takeItem(self.lista_caminos.row(items[0]))

    self.spin_medula.blockSignals(True)
    self.spin_corteza.blockSignals(True)
    self.combo_dir.blockSignals(True)
    try:
        self.combo_dir.setCurrentIndex(datos.dir_idx)
        self.spin_medula.setValue(datos.anio_medula)
        self.spin_corteza.setValue(datos.anio_corteza)
        self.vista.modelo_medicion.restaurar(datos.puntos)
    finally:
        self.combo_dir.blockSignals(False)
        self.spin_medula.blockSignals(False)
        self.spin_corteza.blockSignals(False)

    self.input_codigo.setText(nombre)
    self._restaurar_metadatos_radio(datos)
    self._ultima_ruta_exportada = None
    self.vista.recalcular_todas_las_distancias()
    # IMPORTANTE: emitir metadatos_cambiados para que main_anillos.py
    # sincronice los spinboxes/combo GLOBALES del top bar con los locales
    # (ocultos) recién restaurados. Sin esto, el usuario sigue viendo
    # año=0 en la barra superior aunque el radio cargado tenga año 1500
    # — esa era la causa real del bug "se volvió al año cero".
    self.metadatos_cambiados.emit()
    self._guardar_estado()
    self.label_estado.setText(f"Editando radio '{nombre}'.")


def _eliminar_camino(self):
    items = self.lista_caminos.selectedItems()
    if not items:
        return
    if QMessageBox.question(
        self, "Eliminar",
        "¿Eliminar permanentemente el radio seleccionado?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    ) != QMessageBox.StandardButton.Yes:
        return

    for item in items:
        nombre = item.text()
        self.modelo_sesion.eliminar_radio(nombre)
        self.lista_caminos.takeItem(self.lista_caminos.row(item))

    # Redibujar TODOS los caminos inactivos restantes desde cero.
    # cargar_caminos_inactivos limpia primero TODOS los items (puntos,
    # líneas Y textos) y vuelve a dibujar solo los que quedan. Antes se
    # hacía una eliminación manual que quitaba puntos y líneas pero NO
    # las etiquetas de año (textos), por lo que el radio borrado seguía
    # dejando rastros verdes en la imagen.
    self.vista.cargar_caminos_inactivos(self.caminos_guardados)

    # cargar_caminos_inactivos dibuja todo visible; re-aplicar la
    # visibilidad según el check de cada radio para no "resucitar"
    # radios que el usuario había ocultado.
    for i in range(self.lista_caminos.count()):
        it = self.lista_caminos.item(i)
        visible = it.checkState() == Qt.CheckState.Checked
        self.vista.toggle_camino_inactivo(it.text(), visible)

    self._guardar_estado()
    self._actualizar_grafico()


def _toggle_visual_camino(self, item: QListWidgetItem):
    self.vista.toggle_camino_inactivo(item.text(), item.checkState() == Qt.CheckState.Checked)
    self._actualizar_grafico()
