"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import os
from dpi.medicion.datos import mediciones_radio
from dpi.medicion.anomalias import tabla_eventos
from dpi.medicion.modelo import TipoMarca
from dpi.formatos.pos import leer_pos, escribir_pos
from dpi.formatos.planillas import escribir_excel
from dpi.formatos.exportacion import asegurar_extension
from dpi.formatos.tabular import exportar_tabular
from dpi.infraestructura.escritura import ruta_atomica
from dpi.formatos.tucson import exportar_tucson_ewlw, _escribir_tucson
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
import dpi.infraestructura.json_seguro as _js
from dpi.medicion.constantes import MM_POR_PULGADA
from dpi.formatos.constantes import TUCSON_MAX_CHARS_ID
from dpi.ui.colores import TIPOS_ANOMALIA
from dpi.medicion.ewlw import anchos_ewlw_puntos
import logging
logger = logging.getLogger(__name__)
from dpi.ui.configuracion import ultima_carpeta
from dpi.ui.configuracion import carpeta_medicion as _ultima_carpeta

def _importar_pos(self):
    if self.datos_medidos:
        if QMessageBox.question(
            self, "Atención",
            "Tiene un radio en progreso. ¿Sobrescribirlo con el archivo importado?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

    ruta, _ = QFileDialog.getOpenFileName(
        self, "Importar CooRecorder .pos", _ultima_carpeta(),
        "CooRecorder POS (*.pos);;Todos (*.*)",
        options=QFileDialog.Option.DontUseNativeDialog,
    )
    if not ruta:
        return

    try:
        dpi_pos, anio_datado, coords_px, saltos = leer_pos(ruta)
    except (OSError, ValueError) as exc:
        return QMessageBox.critical(self, "Error", f"No se pudo procesar el archivo:\n{exc}")

    if not coords_px:
        return QMessageBox.warning(self, "Error", "No se encontraron coordenadas válidas.")

    self.vista.limpiar_historial()
    self.vista.pixeles_por_mm = dpi_pos / MM_POR_PULGADA
    self.vista.modelo_medicion.cargar(coords_px, saltos)

    # Detectar automáticamente médula/corteza:
    # el año más reciente (#C DATED) = corteza; el más antiguo = médula.
    anillos_validos = sum(1 for s in saltos[1:] if not s)
    self.spin_medula.blockSignals(True)
    self.spin_corteza.blockSignals(True)
    if anio_datado is not None:
        # El archivo declara explícitamente el año de corteza
        anio_corteza = anio_datado
        anio_medula  = anio_datado - anillos_validos + 1
    else:
        # Sin fecha declarada: usar año actual como corteza estimada
        import datetime
        anio_corteza = datetime.date.today().year
        anio_medula  = anio_corteza - anillos_validos + 1
    self.spin_corteza.setValue(anio_corteza)
    self.spin_medula.setValue(anio_medula)
    # Asegurar que la dirección quede en Médula→Corteza (+1)
    self.combo_dir.setCurrentIndex(0)
    self.spin_medula.blockSignals(False)
    self.spin_corteza.blockSignals(False)

    self.input_codigo.setText(os.path.splitext(os.path.basename(ruta))[0][:TUCSON_MAX_CHARS_ID].upper())
    self.vista.recalcular_todas_las_distancias()
    self._guardar_estado()
    self.label_estado.setText(f"Archivo importado correctamente ({dpi_pos:.0f} DPI).")


def _exportar_anomalias(self):
    """Exporta las anomalías de un radio en formato DendroEventos:
    matriz binaria con los AÑOS en la primera columna y una columna por
    cada TIPO de anomalía presente, con valores 0/1 (1 = ese año tiene
    ese tipo de anomalía). El nombre de archivo sugerido es el de la
    serie.

    Las filas cubren TODO el rango de años de la medición (no solo los
    años con anomalía), para que el archivo sea una serie temporal
    completa lista para análisis de eventos en R u otros programas.
    """
    opciones = []
    if self.vista.anomalias:
        opciones.append("Radio Actual (En progreso)")
    for nombre, datos in self.caminos_guardados.items():
        if datos.anomalias:
            opciones.append(nombre)
    if not opciones:
        return QMessageBox.information(
            self, "Sin anomalías",
            "No hay anomalías registradas en ningún radio.")

    seleccion, ok = QInputDialog.getItem(
        self, "Exportar anomalías (DendroEventos)",
        "¿De qué radio exportar las anomalías?", opciones, 0, False)
    if not ok or not seleccion:
        return

    if seleccion == "Radio Actual (En progreso)":
        anomalias = dict(self.vista.anomalias)
        codigo = self.input_codigo.text().strip() or "radio"
        datos_med = self.datos_medidos
    else:
        anomalias = dict(self.caminos_guardados[seleccion].anomalias)
        codigo = seleccion
        datos_med = mediciones_radio(self.caminos_guardados[seleccion],
                                     self.vista.pixeles_por_mm)

    # Normalizar claves de año a int (al venir de JSON pueden ser str)
    anomalias = {int(k): v for k, v in anomalias.items()}
    if not anomalias:
        return QMessageBox.information(
            self, "Sin anomalías", "Ese radio no tiene anomalías.")

    # Rango de años: completo desde la medición; si no hay datos
    # medidos, usar solo el rango de las anomalías.
    anios_medidos = sorted({int(d["anio"]) for d in datos_med}) if datos_med else []
    if anios_medidos:
        todos_anios = list(range(anios_medidos[0], anios_medidos[-1] + 1))
    else:
        a = sorted(anomalias.keys())
        todos_anios = list(range(a[0], a[-1] + 1))

    # Tipos presentes, en el orden de definición de TIPOS_ANOMALIA.
    # Las columnas usan el NOMBRE legible del tipo (ej. "Fuego",
    # "Frost ring"). Si DendroEventos espera otros encabezados, se
    # ajusta fácil aquí.
    presentes = set(anomalias.values())
    tipos_cols = [(t, TIPOS_ANOMALIA[t][1]) for t in TIPOS_ANOMALIA
                  if t in presentes]

    ruta_sugerida = os.path.join(_ultima_carpeta(), f"{codigo}.csv")
    ruta, fmt = QFileDialog.getSaveFileName(
        self, "Exportar anomalías (DendroEventos)", ruta_sugerida,
        "CSV separado por punto y coma (*.csv);;"
        "Texto separado por tabulaciones (*.txt);;"
        "Excel (*.xlsx)",
        options=QFileDialog.Option.DontUseNativeDialog,
    )
    if not ruta:
        return
    ruta = asegurar_extension(ruta, fmt)
    _ultima_carpeta(ruta)

    try:
        df = tabla_eventos(todos_anios, anomalias, tipos_cols)

        ext = os.path.splitext(ruta)[1].lower()
        if ext == ".xlsx":
            escribir_excel(df, ruta)
        else:
            with ruta_atomica(ruta) as temporal:
                df.to_csv(temporal, index=False, sep="\t" if ext == ".txt" else ";")

        cols_txt = ", ".join(nom for _, nom in tipos_cols)
        QMessageBox.information(
            self, "Éxito",
            f"Anomalías exportadas (formato DendroEventos):\n{ruta}\n\n"
            f"Años: {todos_anios[0]}–{todos_anios[-1]} "
            f"({len(todos_anios)} filas)\n"
            f"Columnas de evento (0/1): {cols_txt}")
    except Exception as exc:
        QMessageBox.critical(
            self, "Error", f"No se pudo exportar:\n{exc}")


def _ejecutar_exportacion(self):
    opciones = []
    if self.datos_medidos:
        opciones.append("Radio Actual (En progreso)")
    opciones.extend(list(self.caminos_guardados.keys()))
    if not opciones:
        return QMessageBox.warning(self, "Aviso", "No hay radios para exportar.")

    seleccion, ok = QInputDialog.getItem(
        self, "Exportar", "Seleccione el radio a exportar:", opciones, 0, False
    )
    if not ok or not seleccion:
        return

    if seleccion == "Radio Actual (En progreso)":
        datos = self.datos_medidos
        codigo = self.input_codigo.text().strip()
        anomalias_export = self.vista.anomalias
        # Para EW/LW: usar el estado en vivo de la vista
        puntos_export = self.modelo_sesion.activo.captura()
        coords_export = tuple(p.coordenada for p in puntos_export)
        saltos_export = tuple(p.tipo.value for p in puntos_export)
        med_a_cor_export = self.combo_dir.currentIndex() == 0
    else:
        radio = self.caminos_guardados[seleccion]
        datos = mediciones_radio(radio, self.vista.pixeles_por_mm)
        codigo = seleccion
        anomalias_export = dict(radio.anomalias)
        # Proyecciones del radio elegido, no del radio activo.
        puntos_export = radio.puntos
        coords_export = radio.coordenadas
        saltos_export = radio.marcas
        med_a_cor_export = radio.dir_idx == 0

    if not codigo:
        return QMessageBox.warning(self, "Aviso", "El radio no tiene nombre/código.")

    # Diálogo de guardado para capturar ruta y guardar sidecar
    # Obtener última carpeta y armar la ruta sugerida
    carpeta = _ultima_carpeta()
    ruta_sugerida = os.path.join(carpeta, codigo) if carpeta else codigo

    # Diálogo de guardado para capturar ruta y guardar sidecar
    ruta, fmt = QFileDialog.getSaveFileName(
        self, "Guardar", ruta_sugerida,
        "Formato Tucson (*.txt *.rwl);;Excel (*.xlsx);;CSV (*.csv);;"
        "CooRecorder POS (*.pos)",
        options=QFileDialog.Option.DontUseNativeDialog,
    )
    if not ruta:
        return

    # Garantizar la extensión según el filtro elegido (el diálogo no
    # nativo no la agrega solo; sin ella, .xlsx/.pos no se reconocen).
    ruta = asegurar_extension(ruta, fmt)
    # Guardar la ruta elegida
    _ultima_carpeta(ruta)

    # ── Exportación a .pos (CooRecorder) ──
    # Solo coordenadas (en mm) + DPI + año de corteza, para compartir la
    # medición e interoperar con CooRecorder u otros programas. Las
    # anomalías y la info de EW/LW se exportan por separado.
    if "*.pos" in fmt or ruta.lower().endswith(".pos"):
        try:
            anio_corteza = max((d["anio"] for d in datos), default=None)
            dpi = self.vista.pixeles_por_mm * MM_POR_PULGADA
            escribir_pos(ruta, coords_export, saltos_export,
                               dpi, anio_corteza, codigo, self.ruta_imagen_actual)
            QMessageBox.information(
                self, "Éxito",
                f"Medición exportada en formato .pos:\n{ruta}\n\n"
                f"Contiene las coordenadas de los anillos (en mm), el DPI "
                f"y el año de corteza. Las anomalías se exportan aparte.")
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"No se pudo exportar .pos:\n{exc}")
        return

    try:
        import pandas as pd
        anios  = [d["anio"]     for d in sorted(datos, key=lambda d: d["anio"])]
        anchos = [d["ancho_mm"] for d in sorted(datos, key=lambda d: d["anio"])]

        # Calcular EW/LW por anillo si hay límites — para incluir como
        # columnas extras en CSV/Excel.
        ppm = self.vista.pixeles_por_mm
        anchos_ewlw = None
        tiene_ewlw_en_radio = any(p.tipo is TipoMarca.EW_LW for p in puntos_export)
        if tiene_ewlw_en_radio and coords_export:
            try:
                anchos_ewlw = anchos_ewlw_puntos(
                    puntos_export, ppm, med_a_cor_export
                )
                # Alinear largo con datos por seguridad
                if len(anchos_ewlw) != len(datos):
                    anchos_ewlw = None
                else:
                    anchos_ewlw = [t for _, t in sorted(zip([d["anio"] for d in datos], anchos_ewlw))]
            except Exception as exc:
                logger.warning("No se pudo calcular EW/LW para tabla: %s", exc)
                anchos_ewlw = None

        if "*.csv" in fmt:
            exportar_tabular(
                codigo, anios, anchos, ruta, "csv",
                anchos_ewlw=anchos_ewlw)
        elif "*.xlsx" in fmt:
            exportar_tabular(
                codigo, anios, anchos, ruta, "xlsx",
                anchos_ewlw=anchos_ewlw)
        else:
            mediciones_int = [int(round(m * 1000)) for m in anchos]
            _escribir_tucson(codigo, anios[0], mediciones_int, ruta, anios=anios)

        # Exportar EW/LW si hay límites marcados en el radio elegido
        # (no en la vista en vivo, que puede ser distinta).
        if anchos_ewlw and any(ew is not None and lw is not None
                               for _, ew, lw in anchos_ewlw):
            exportar_tucson_ewlw(codigo, anios, anchos_ewlw, ruta,
                                 sufijos=("_ew", "_lw"), extension=".rwl")

        QMessageBox.information(self, "Éxito", f"Exportado a:\n{ruta}")
        # No asociar las anomalías del radio activo a otro radio.
        if seleccion == "Radio Actual (En progreso)":
            self._ultima_ruta_exportada = ruta
            self._guardar_sidecar_anom(ruta)
        else:
            radio = self.caminos_guardados[seleccion]
            _js.guardar_json(self._ruta_sidecar(ruta), {
                "code": codigo, "medula": radio.medula,
                "corteza": radio.corteza,
                "anomalias": dict(radio.anomalias),
            })
    except Exception as exc:
        logger.error("Error al exportar: %s", exc)
        QMessageBox.critical(self, "Error", f"Fallo al exportar:\n{exc}")
