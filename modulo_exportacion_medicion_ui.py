"""Diálogo de exportación de mediciones."""
import os
import logging
from PyQt6.QtWidgets import QWidget, QFileDialog, QMessageBox
from dpi.ui.configuracion import ultima_carpeta
from dpi.formatos.exportacion import asegurar_extension
from dpi.formatos.tabular import exportar_tabular
from dpi.formatos.tucson import exportar_tucson_ewlw, _escribir_tucson

logger = logging.getLogger(__name__)


from dpi.ui.configuracion import carpeta_medicion as _ultima_carpeta


class ExportadorDendro:
    """Gestiona la exportación de mediciones a Tucson, CSV y Excel."""

    def __init__(self, ventana_padre: QWidget):
        self._parent = ventana_padre

    def exportar_datos(self, id_serie: str, lista_mediciones: list[dict],
                        anchos_ewlw: list | None = None):
        """Exporta mediciones a Tucson, CSV o Excel.

        Parameters
        ----------
        id_serie : str
            Identificador de la serie (código).
        lista_mediciones : list[dict]
            Lista de dicts {anio, ancho_mm} con las mediciones totales por anillo.
        anchos_ewlw : list[tuple], opcional
            Lista paralela de (total_mm, ew_mm, lw_mm) para anillos con
            límite EW/LW detectado. None en ew_mm/lw_mm si el anillo no
            tiene split. Si se provee y al menos un anillo tiene split,
            la exportación a CSV/Excel agregará columnas EW_mm y LW_mm.
            Para formato Tucson, ofrece exportar archivos separados
            (codigo.rwl + codigo_EW.rwl + codigo_LW.rwl).
        """
        if not lista_mediciones:
            return QMessageBox.warning(self._parent, "Error", "No hay mediciones para exportar.")

        orden = sorted(range(len(lista_mediciones)), key=lambda i: lista_mediciones[i]["anio"])
        datos = [lista_mediciones[i] for i in orden]
        if anchos_ewlw is not None and len(anchos_ewlw) == len(datos):
            anchos_ewlw = [anchos_ewlw[i] for i in orden]
        anios = [d["anio"] for d in datos]
        anchos = [d["ancho_mm"] for d in datos]

        # Detectar si hay info EW/LW útil para incluir
        tiene_ewlw = False
        if anchos_ewlw and len(anchos_ewlw) == len(datos):
            tiene_ewlw = any(ew is not None and lw is not None
                             for (_, ew, lw) in anchos_ewlw)

        # Obtener última carpeta y armar la ruta sugerida
        carpeta = _ultima_carpeta()
        ruta_sugerida = os.path.join(carpeta, id_serie) if carpeta else id_serie

        ruta, fmt = QFileDialog.getSaveFileName(
            self._parent, "Guardar", ruta_sugerida,
            "Formato Tucson (*.txt *.rwl);;Excel (*.xlsx);;CSV (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return

        ruta = asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)

        try:
            if "*.csv" in fmt:
                exportar_tabular(
                    id_serie, anios, anchos, ruta, "csv",
                    anchos_ewlw=anchos_ewlw if tiene_ewlw else None
                )
            elif "*.xlsx" in fmt:
                exportar_tabular(
                    id_serie, anios, anchos, ruta, "xlsx",
                    anchos_ewlw=anchos_ewlw if tiene_ewlw else None
                )
            else:
                mediciones_int = [int(round(m * 1000)) for m in anchos]
                _escribir_tucson(id_serie, anios[0], mediciones_int, ruta, anios=anios)

                # Si hay EW/LW, ofrecer exportar archivos separados
                # (convención CooRecorder/Velmex: _EW.rwl y _LW.rwl).
                if tiene_ewlw:
                    resp = QMessageBox.question(
                        self._parent, "EW/LW detectado",
                        f"Se detectaron límites EW/LW en algunos anillos.\n\n"
                        f"¿Desea exportar también archivos Tucson separados\n"
                        f"para earlywood y latewood?\n\n"
                        f"Se crearán:\n"
                        f"  • {id_serie}_EW.rwl (earlywood)\n"
                        f"  • {id_serie}_LW.rwl (latewood)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if resp == QMessageBox.StandardButton.Yes:
                        exportar_tucson_ewlw(
                            id_serie, anios, anchos_ewlw, ruta
                        )

            QMessageBox.information(self._parent, "Éxito", f"Exportado a:\n{ruta}")
        except Exception as exc:
            logger.exception("Error al exportar")
            QMessageBox.critical(self._parent, "Error", f"Fallo al exportar:\n{exc}")
