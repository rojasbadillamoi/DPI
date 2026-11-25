"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import os
from dpi.medicion.sesion import guardar_sesion, leer_sesion
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtCore import Qt, QSignalBlocker
import dpi.infraestructura.json_seguro as _js
import logging
logger = logging.getLogger(__name__)

def _guardar_estado(self):
    timer = getattr(self, "_timer_autoguardado", None)
    if timer is not None:
        timer.stop()
    if getattr(self, "_sesion_protegida", None) == self.ruta_imagen_actual:
        return False
    self._guardado_pendiente = True
    try:
        guardar_sesion(
            self.ruta_imagen_actual,
            self.modelo_sesion.activo.pixeles_por_mm,
            self.caminos_guardados,
            self._capturar_radio(),
        )
    except Exception:
        logger.exception("No se pudo guardar el estado")
        if hasattr(self, "label_estado"):
            self.label_estado.setText("Error de guardado: hay cambios pendientes.")
        return False
    self._guardado_pendiente = False
    return True


def _cargar_estado(self) -> bool:
    self._sesion_protegida = None
    try:
        datos = leer_sesion(self.ruta_imagen_actual)
        if datos is None:
            return False
        activo = datos["camino_activo"]
        if activo:
            for campo, control in (("anio_medula", self.spin_medula),
                                   ("anio_corteza", self.spin_corteza)):
                if not control.minimum() <= getattr(activo, campo) <= control.maximum():
                    raise ValueError(f"{campo} fuera del rango permitido")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        self._sesion_protegida = self.ruta_imagen_actual
        logger.warning("No se pudo cargar el estado guardado: %s", exc)
        self._mostrar_aviso_dpi("Sesión protegida",
            "No se pudo restaurar la sesión. El autoguardado queda desactivado "
            "para esta imagen hasta resolver el archivo de sesión.")
        return False

    # La lectura, migración y validación han terminado antes de tocar Qt.
    if "pixeles_por_mm" in datos:
        self.vista.pixeles_por_mm = datos["pixeles_por_mm"]
        self._dpi_modo = "guardado"

    self.modelo_sesion.cargar_radios(datos["caminos_guardados"])
    with QSignalBlocker(self.lista_caminos):
        self.lista_caminos.clear()
        for nombre in self.caminos_guardados:
            item = QListWidgetItem(nombre)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.lista_caminos.addItem(item)
    self.vista.cargar_caminos_inactivos(self.caminos_guardados)

    if activo:
        with (QSignalBlocker(self.spin_medula),
              QSignalBlocker(self.spin_corteza),
              QSignalBlocker(self.combo_dir),
              QSignalBlocker(self.input_codigo)):
            if activo.codigo is not None:
                self.input_codigo.setText(activo.codigo)
            self.combo_dir.setCurrentIndex(activo.dir_idx)
            self.spin_medula.setValue(activo.anio_medula)
            self.spin_corteza.setValue(activo.anio_corteza)
            self.vista.limpiar_historial()
            self.vista.modelo_medicion.restaurar(activo.puntos)
        self._restaurar_metadatos_radio(activo)
        self.vista.recalcular_todas_las_distancias()
    else:
        self._actualizar_grafico()
    return True


def _guardar_sidecar_anom(self, ruta_rwl: str | None = None):
    """Escribe el .anom.json con anomalías + metadata del radio activo."""
    ruta_s = self._ruta_sidecar(ruta_rwl)
    if not ruta_s:
        return  # No hay ruta — silencioso (serie aún no exportada)
    try:
        datos = {
            "code":    self.input_codigo.text().strip(),
            "medula":  self.check_tiene_medula.isChecked(),
            "corteza": self.check_tiene_corteza.isChecked(),
            "anomalias": {
                str(anio): tipo
                for anio, tipo in self.vista.anomalias.items()
            },
        }
        # Agregar datos de estimación de médula si existen
        pith_est = self._pith.estimacion
        if pith_est:
            datos.update(pith_est)
        _js.guardar_json(ruta_s, datos)
    except Exception as e:
        logger.warning("No se pudo guardar sidecar: %s", e)


def _cargar_sidecar_anom(self, ruta_rwl: str):
    """Lee el .anom.json (oculto) y carga anomalías + checkboxes si existe."""
    directorio = os.path.dirname(ruta_rwl)
    nombre = os.path.basename(ruta_rwl)
    ruta_s = os.path.join(directorio, f".{nombre}.anom.json")
    # Retrocompatibilidad: buscar formato anterior (no oculto)
    if not os.path.exists(ruta_s):
        ruta_legacy = ruta_rwl + ".anom.json"
        if os.path.exists(ruta_legacy):
            ruta_s = ruta_legacy
        else:
            return
    try:
        with open(ruta_s, "r", encoding="utf-8") as fh:
            datos = _js.cargar_json(fh)
        self.check_tiene_medula.setChecked(bool(datos.get("medula", False)))
        self.check_tiene_corteza.setChecked(bool(datos.get("corteza", False)))
        self.vista.anomalias = {
            int(k): v for k, v in datos.get("anomalias", {}).items()
        }
        self.vista._dibujar_anomalias()
        self._pith.restaurar_estimacion(datos)
    except Exception as e:
        logger.warning("No se pudo cargar sidecar: %s", e)
