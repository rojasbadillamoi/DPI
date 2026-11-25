"""
modulo_codatacion.py — Panel de Co-datación Visual

Permite comparar series dendrocronológicas, detectar anillos faltantes o
sobrantes mediante búsqueda exhaustiva, y aplicar correcciones en memoria.
"""
from dpi.ui.configuracion import ajustes_ui

import modulo_codatacion_ui

import os
import sys
import datetime
import logging
import numpy as np
import pandas as pd
import pyqtgraph as pg
from dpi.ui.configuracion import ultima_carpeta
from modulo_widgets import (
    _ensanchar_dialogo, _agregar_hover_anio, _crear_barra_zoom,
    SpinBoxFlechas, SeccionColapsable,
)
from dpi.series.modelo import ModeloSeries
from dpi.ciencia.comparacion_nucleo import SeriePreparada, comparar_serie
import dpi.ciencia.transformacion as _tr
import dpi.ciencia.estadistica as _est
from dpi.ciencia.estadistica import (
    gleichlaufigkeit,
    glk_significance,
    _filtro_hollstein,
    t_baillie_pilcher,
    estadisticos_cofechado,
    calcular_eps_rbar_movil,
    calcular_rbar,
    calcular_eps,
    calcular_sss,
    correlacion_por_desfase,
    estadisticos_por_desfase,
    _r_movil,
    _stats_movil,
)
import dpi.ciencia.quiebres as _qb
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QFileDialog, QMessageBox, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog,
    QFormLayout, QComboBox, QCheckBox, QGroupBox,
    QDialogButtonBox, QApplication, QProgressDialog, QScrollArea,
    QFrame, QTabWidget, QPlainTextEdit, QTextBrowser,
)
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut, QPalette
from PyQt6.QtCore import Qt, QSettings, QEvent

from estilos import SECUNDARIO_QSS, color_secundario
import estilos_graficos as _gr
import dpi.infraestructura.json_seguro as _js
from dpi.formatos.constantes import TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE, TUCSON_MAX_CHARS_ID, TUCSON_DIVISOR
from dpi.ciencia.constantes import OVERLAP_MINIMO_ANALISIS, OVERLAP_MINIMO_GRAFICO, OVERLAP_MINIMO_FLOTANTE, UMBRAL_ANCLA_DEFECTO, VENTANA_COFECHADO_DEFECTO
from dpi.ui.colores import COLORES_SERIES

logger = logging.getLogger(__name__)

from dpi.ciencia.datacion import (
    score_compuesto,
    _serie_transformada_para_comparar,
    alineamiento_optimo_anillos,
    _diff_log,
    aplicar_correccion,
    _plausibilidad_anillo_estrecho,
    puntaje_consistencia,
    _texto_correccion,
    _buscar_y_priorizar,
    diagnosticar_datacion,
    buscar_correcciones,
    aplicar_modo_cofecha,
    _glk_np,
    _tbp_np,
    _r_pearson,
    MAX_CORRECCION,
    MIN_OVERLAP_DEFAULT,
)

# Extensiones de planilla que se leen/escriben con el motor de Excel de
# pandas. Incluye .ods (LibreOffice / OpenDocument), que necesita el módulo
# 'odfpy'. Se usa en todo el módulo para no repetir la lista y para que un
# .ods nunca caiga por error al parser de texto (CSV), que devolvería basura.
from dpi.formatos.planillas import EXTS_PLANILLA, es_planilla, leer_planilla, escribir_excel
from dpi.formatos.exportacion import asegurar_extension


from dpi.ciencia.cronologia import (
    agrupar_por_arbol,
    rbar_entre_arboles,
)


TOOLTIP_STATS = (
    "<b>Estadísticos de cofechado:</b><br><br>"
    "<b>r (Pearson):</b> correlación lineal.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥0.50</span>: excelente<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥0.35</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥0.20</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;0.20</span>: pobre<br><br>"
    "<b>GLK:</b> % años con misma dirección. Asteriscos = significancia.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥0.70</span>: muy bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥0.65</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥0.60</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;0.60</span>: subóptimo<br><br>"
    "<b>t-BP (Baillie-Pilcher):</b> t-statistic sobre series filtradas.<br>"
    "&nbsp;&nbsp;• <span style='color:#28a745'>≥6.0</span>: excelente<br>"
    "&nbsp;&nbsp;• <span style='color:#a3c44e'>≥4.0</span>: bueno<br>"
    "&nbsp;&nbsp;• <span style='color:#f0ad4e'>≥3.0</span>: aceptable<br>"
    "&nbsp;&nbsp;• <span style='color:#d9534f'>&lt;3.0</span>: no significativo<br><br>"
    "<b>n:</b> años de overlap.<br><br>"
    "<i>Los tres altos = cofechado sólido.</i>"
)


ESTILO_BTN_COFECHA = (
    "QPushButton{background:transparent; padding:4px 10px; "
    "border:2px solid #888; border-radius:4px; font-weight:bold;}"
    "QPushButton:hover{border:2px solid #FF8C00;}"
    "QPushButton:checked{border:2px solid #FF8C00; background:#FF8C00; color:white;}"
)

from dpi.ui.series_util import ESTILO_CHK_COFECHA


# =============================================================================
# LECTORES DE FORMATO DE ARCHIVO
# =============================================================================

from dpi.formatos.tucson import detectar_precision_tucson, leer_archivo_tucson, leer_tucson_multi
from dpi.formatos.compacto import leer_formato_compacto
from dpi.formatos.deteccion import leer_dendro_auto
from dpi.formatos.wid import leer_wid
from dpi.formatos.tabular import leer_tabular, _indexar_columna_multi, _leer_crudo_tabular, leer_columna_multi, leer_columna_multi_hojas


# =============================================================================
# CRONOLOGÍA: NORMALIZACIÓN Y CONSTRUCCIÓN
# =============================================================================

from dpi.ciencia.cronologia import (
    _biweight_mean,
    _spline_cook,
    _fit_trend,
    _detrend_serie_indice,
    _ajustar_ar_yule_walker,
    _seleccionar_orden_ar,
    _ajustar_ar_burg,
    _residualizar_indice,
    rigidez_efectiva,
    estabilizar_varianza,
    detrendar_para_cronologia,
    orden_ar_agrupado,
    normalizar_serie_para_tipo,
    diagnosticar_curva,
    detectar_series_problematicas,
    elegir_metodo_para_grupo,
    RIGIDEZ_SPLINE_DEFECTO,
    ORDEN_AR_MAXIMO,
    METODOS_DETREND,
    solveh_banded,
)


from dpi.ciencia.cronologia import (
    _construir_cronologia_desde_series,
)


from dpi.formatos.cronologias import _ruta_metadatos_cronologia, _restaurar_claves_anio, _guardar_metadatos_cronologia, _cargar_metadatos_cronologia, _exportar_cronologia_df, _leer_cronologia_guardada, _CAMPOS_POR_ANIO
from dpi.formatos.tucson import escribir_tucson


# =============================================================================
# PANEL DE CO-DATACIÓN
# =============================================================================


from dpi.ui.series_util import (
    _ultima_carpeta,
    _color_r,
    _color_glk,
    _color_tbp,
    _color_compuesto,
    formato_stats_hover_html,
    formato_stats_global_html,
    formato_estadisticos,
    _html_curvas_negativas,
    _mostrar_dialogo_eps_rbar,
)

from modulo_dialogos_series import (
    DialogoSeleccionCronologias,
    DialogoCofecha,
    DialogoEditarAnillos,
    DialogoAlineamientoAnillos,
    DialogoCurvasNegativas,
)

from modulo_comparacion_ui import (
    VentanaTablaOffset,
    DialogoComparacionMultiple,
)

from modulo_skeleton_plot import (
    VentanaSkeletonPlot,
)

from modulo_ventana_cronologia import (
    VentanaCronologia,
)


import dpi.ui.exportacion_series as exportacion_series


import dpi.ui.correcciones_series as correcciones_series


import dpi.ui.presentacion_series as presentacion_series


import dpi.ui.comparacion_series as comparacion_series


class PanelCodatacion(QWidget):
    """Panel principal de co-datación visual."""

    def __init__(self, ventana_padre: QWidget):
        super().__init__()
        self._ventana_padre = ventana_padre

        self.modelo_series = ModeloSeries()
        self.series_originales = self.modelo_series.originales
        self.series_datos = self.modelo_series.datos

        # Datos del análisis de offset (analizar_offset)
        self._shifts_actuales: list[int] = []
        self._r_actuales: list[float] = []
        self._glk_actuales: list[float] = []
        self._tbp_actuales: list[float] = []
        self._n_actuales: list[int] = []

        # Datos de la correlación móvil (verificar_datacion / buscar_errores)
        self._stats_movil_years: list[float] = []
        self._stats_movil_r: list[float] = []
        self._stats_movil_glk: list[float] = []
        self._stats_movil_tbp: list[float] = []
        self._stats_movil_n: list[int] = []
        self._mitad_ventana_actual: int = 15

        # Estado del motor de sugerencias
        self._sugerencias: list[dict] = []
        self._sugerencias_es_marginal: bool = False
        self._nombre_referencia: str = ""
        self._nombre_problema: str = ""
        self._item_preview = None
        self._stats_actuales: dict | None = None

        # El modelo conserva el respaldo; aquí solo queda la sugerencia visual.
        self._prueba_sug: dict | None = None

        # Cronología activa
        self.cronologia_activa: pd.DataFrame | None = None
        self.meta_cronologia: dict | None = None
        self._obtener_series_cronologia = lambda: {}
        self._abrir_cronologia = getattr(ventana_padre, "ir_a_pestana_cronologia", None)
        self._nombre_cronologia_activa: str = ""

        # Parámetros del modo COFECHA
        self._modo_cofecha_params: dict = {
            "rigidez_spline": 32,
            "aplicar_log": True,
            "aplicar_ar": True,
            "aplicar_first_diff": False,
        }

        self._construir_ui()
        self._sincronizar_fondo_con_tema_app()

    # -------------------------------------------------------------------------
    # CONSTRUCCIÓN DE LA INTERFAZ
    # -------------------------------------------------------------------------

    def _construir_ui(self):
        acciones = modulo_codatacion_ui.AccionesCodatacion(
            _abrir_editor_anillos_marcada=self._abrir_editor_anillos_marcada,
            _aplicar_fuente_informe=self._aplicar_fuente_informe,
            _configurar_modo_cofecha=self._configurar_modo_cofecha,
            _descartar_prueba=self._descartar_prueba,
            _guardar_pref_fuente=self._guardar_pref_fuente,
            _mostrar_eps_cronologia_activa=self._mostrar_eps_cronologia_activa,
            _on_cofecha_aplicar_cambiado=self._on_cofecha_aplicar_cambiado,
            _on_modo_cofecha_toggled=self._on_modo_cofecha_toggled,
            _on_mouse_movido=self._on_mouse_movido,
            _on_seleccion_sugerencia=self._on_seleccion_sugerencia,
            _redibujar_offset=self._redibujar_offset,
            abrir_skeleton_plot=self.abrir_skeleton_plot,
            analizar_offset=self.analizar_offset,
            aplicar_correccion_seleccionada=self.aplicar_correccion_seleccionada,
            buscar_errores=self.buscar_errores,
            cargar_archivos_rwl=self.cargar_archivos_rwl,
            cargar_cronologias_externas=self.cargar_cronologias_externas,
            cargar_series_referencia=self.cargar_series_referencia,
            comparar_series_marcadas_vs_crono=self.comparar_series_marcadas_vs_crono,
            editar_anio_serie=self.editar_anio_serie,
            eliminar_series=self.eliminar_series,
            exportar_serie_codatada=self.exportar_serie_codatada,
            graficar_series=self.graficar_series,
            mostrar_tabla_offset=self.mostrar_tabla_offset,
            probar_correccion_seleccionada=self.probar_correccion_seleccionada,
            restaurar_original_sugerencias=self.restaurar_original_sugerencias,
            restaurar_serie=self.restaurar_serie,
            simular_borrar=self.simular_borrar,
            simular_insertar=self.simular_insertar,
            toggle_seleccion=self.toggle_seleccion,
            verificar_datacion=self.verificar_datacion,
        )
        controles = modulo_codatacion_ui.construir_ui(self, acciones)
        self._texto_hover = controles._texto_hover
        self._widget_izq_panel = controles._widget_izq_panel
        self.btn_aplicar = controles.btn_aplicar
        self.btn_buscar = controles.btn_buscar
        self.btn_cargar_crono = controles.btn_cargar_crono
        self.btn_cargar_rwl = controles.btn_cargar_rwl
        self.btn_cof_config = controles.btn_cof_config
        self.btn_descartar_prueba = controles.btn_descartar_prueba
        self.btn_editar_anillos = controles.btn_editar_anillos
        self.btn_eps_crono = controles.btn_eps_crono
        self.btn_grafico_barras = controles.btn_grafico_barras
        self.btn_modo_cofecha = controles.btn_modo_cofecha
        self.btn_multi_vs_crono = controles.btn_multi_vs_crono
        self.btn_probar = controles.btn_probar
        self.btn_restablecer_sug = controles.btn_restablecer_sug
        self.btn_series_nulo = controles.btn_series_nulo
        self.btn_skeleton = controles.btn_skeleton
        self.btn_toggle_sel = controles.btn_toggle_sel
        self.btn_ver_cofechado = controles.btn_ver_cofechado
        self.btn_ver_tabla_off = controles.btn_ver_tabla_off
        self.chk_cof_crono = controles.chk_cof_crono
        self.chk_cof_serie = controles.chk_cof_serie
        self.combo_anclaje = controles.combo_anclaje
        self.combo_fuente_informe = controles.combo_fuente_informe
        self.combo_metrica_offset = controles.combo_metrica_offset
        self.grafico = controles.grafico
        self.grafico_offset = controles.grafico_offset
        self.grafico_perfil = controles.grafico_perfil
        self.lbl_estado_sug = controles.lbl_estado_sug
        self.lbl_info_crono = controles.lbl_info_crono
        self.lbl_prueba = controles.lbl_prueba
        self.lbl_stats = controles.lbl_stats
        self.lista_series = controles.lista_series
        self.sec_sug = controles.sec_sug
        self.spin_edit_year = controles.spin_edit_year
        self.spin_fuente_informe = controles.spin_fuente_informe
        self.spin_max_corr = controles.spin_max_corr
        self.spin_ventana = controles.spin_ventana
        self.tabla_sugerencias = controles.tabla_sugerencias
        self.tabs_inferior = controles.tabs_inferior
        self.txt_ayuda_perfil = controles.txt_ayuda_perfil
        self.txt_informe = controles.txt_informe
        self._restaurar_pref_fuente()

    # -------------------------------------------------------------------------
    # SINCRONIZACIÓN DE FONDO CON EL TEMA DE LA APP
    # -------------------------------------------------------------------------

    def _sincronizar_fondo_con_tema_app(self):
        """Aplica el fondo correcto al QWidget contenedor del panel según el
        tema activo de la aplicación.

        El stylesheet global de la app (estilos.py) define backgrounds para
        QMainWindow / QDialog / QListView / QSpinBox / etc., pero NO para
        QWidget genérico. Como el contenedor del scroll del panel es un
        QWidget plano, sin esto Qt lo pinta con palette(window) del sistema
        — que en Linux/GTK puede ser gris claro incluso con el tema oscuro
        de la app activo. Resultado: labels con texto blanco quedan invisibles
        sobre fondo gris claro.

        Detectamos el tema inspeccionando el stylesheet global. ESTILO_OSCURO
        contiene "background-color: #2b2b2b" y ESTILO_CLARO contiene
        "background-color: #f0f0f0" — ambos definidos en estilos.py.
        """
        # Los gráficos van primero, antes del `return` de más abajo: pyqtgraph
        # pinta con sus propios colores y no se entera del cambio de tema por
        # su cuenta, así que tienen que repintarse pase lo que pase con el
        # stylesheet. Se recorren todos (principal, correlación móvil, perfil).
        _gr.aplicar_a_todos(self)

        ss_app = QApplication.instance().styleSheet() or ""

        # Marcador robusto: el QMainWindow en ESTILO_OSCURO tiene #2b2b2b,
        # en ESTILO_CLARO tiene #f0f0f0. Si ninguno está, dejamos sin
        # estilizar (Qt usa palette del sistema).
        if "#2b2b2b" in ss_app:
            fondo = "#2b2b2b"
        elif "#f0f0f0" in ss_app:
            fondo = "#f0f0f0"
        else:
            return  # sin stylesheet reconocible, no tocar nada

        if hasattr(self, "_widget_izq_panel"):
            # Solo el QWidget contenedor — los descendientes con estilo propio
            # (QSpinBox, QListWidget, QPushButton, etc.) mantienen sus colores
            # del stylesheet global porque su selector específico vence al
            # genérico QWidget. Los QLabel también: el global tiene
            # "QLabel { background: transparent; }" que vence a este.
            self._widget_izq_panel.setStyleSheet(
                f"QWidget {{ background-color: {fondo}; }}"
            )

    def changeEvent(self, event):
        """Re-sincroniza el fondo del panel en caliente cuando la app
        cambia su stylesheet global (toggle de tema oscuro/claro).

        Cuando el usuario activa el toggle de tema, la app llama a
        QApplication.setStyleSheet(NUEVO_ESTILO). Eso propaga un evento
        QEvent.StyleChange a todos los widgets visibles e invisibles.
        Aprovechamos ese evento para re-aplicar el fondo apropiado al
        contenedor del scroll sin requerir reinicio.
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._sincronizar_fondo_con_tema_app()

    # -------------------------------------------------------------------------
    # CARGA DE ARCHIVOS
    # -------------------------------------------------------------------------

    def cargar_archivos_rwl(self):
        """Carga uno o más archivos, detectando formato automáticamente."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Series", _ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.wid *.csv *.tsv *.xlsx *.xls *.ods *.cat *.cmp);;"
            "Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not rutas:
            return
        _ultima_carpeta(rutas[0])

        n_agregadas = 0
        n_duplicadas = 0
        errores: list[str] = []

        from dpi.series.importacion import importar_archivo
        for ruta in rutas:
            try:
                for id_serie, agregada in importar_archivo(self.modelo_series, ruta):
                    if not agregada:
                        n_duplicadas += 1
                        continue
                    item = QListWidgetItem(id_serie)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.lista_series.addItem(item)
                    n_agregadas += 1

            except (ValueError, OSError) as exc:
                logger.warning("Error al cargar %s: %s", ruta, exc)
                errores.append(f"{os.path.basename(ruta)}: {exc}")
                continue

        if n_agregadas:
            self._series_modificadas(regraficar=False)
        self.graficar_series()

        if n_agregadas == 0 and not errores:
            QMessageBox.information(
                self, "Sin novedades",
                f"Las {n_duplicadas} series del archivo ya estaban cargadas.")
        elif errores:
            msg = f"Se agregaron {n_agregadas} serie(s)."
            if n_duplicadas:
                msg += f"\n{n_duplicadas} duplicada(s) omitida(s)."
            msg += "\n\nErrores:\n" + "\n".join(errores)
            QMessageBox.warning(self, "Carga con errores", msg)

    def agregar_serie_externa(self, nombre, df):
        """Entrada pública: registra y representa la serie una sola vez."""
        if nombre in self.series_datos:
            return False
        self.modelo_series.registrar(nombre, df)
        item = QListWidgetItem(nombre)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.lista_series.addItem(item)
        self._series_modificadas()
        return True

    def cargar_cronologias_externas(self):
        """Carga cronologías externas con prefijo 📚."""
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Cargar cronología(s) externa(s)", _ultima_carpeta(),
            "Cronologías y series (*.rwl *.txt *.crn *.wid *.csv *.tsv "
            "*.xlsx *.xls *.ods *.cat *.cmp);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        _ultima_carpeta(ruta)

        ext = os.path.splitext(ruta)[1].lower()
        try:
            # Detectar formato compacto (solo en archivos de texto: una
            # planilla .ods/.xlsx es un ZIP binario y leerla como texto puede
            # dar falsos positivos).
            primeras = ""
            if not es_planilla(ext):
                with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                    primeras = f.read(500)
            if "=N" in primeras and "=I" in primeras:
                series = leer_formato_compacto(ruta)
                self._procesar_tucson_como_crono(series, ruta)
                return

            # WID directo
            if ext == ".wid":
                df, sid = leer_wid(ruta)
                self._agregar_crono(f"📚 {sid}", df, ruta)
                return

            # Tucson (.rwl/.txt SIN tabs)
            if ext in (".rwl", ".txt"):
                primera_real = ""
                try:
                    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                        for linea in f:
                            ln = linea.rstrip("\r\n")
                            if not ln or ln.startswith("#"):
                                continue
                            primera_real = ln
                            break
                except (OSError, UnicodeError):
                    logger.debug("No se pudo inspeccionar el formato de %s", ruta, exc_info=True)
                    primera_real = ""
                if "\t" not in primera_real:
                    try:
                        series = leer_tucson_multi(ruta)
                        if series:
                            self._procesar_tucson_como_crono(series, ruta)
                            return
                    except Exception:
                        logger.debug("Lectura Tucson descartada para %s", ruta, exc_info=True)

            # Multi-columna o tabular
            try:
                # Leer TODAS las hojas (un .ods/.xlsx puede traer una
                # cronología por hoja; pandas solo lee la primera por defecto).
                hojas = leer_columna_multi_hojas(ruta)
                base_nombre = os.path.splitext(os.path.basename(ruta))[0]

                from dpi.series.cronologias import candidatos_cronologias
                candidatos = candidatos_cronologias(hojas, base_nombre)

                if not candidatos:
                    raise ValueError("No se encontraron cronologías en el archivo.")

                # Con varias cronologías, preguntar cuáles cargar (todas
                # marcadas por defecto). Con una sola, cargarla directo.
                if len(candidatos) > 1:
                    dlg = DialogoSeleccionCronologias(
                        [c[0] for c in candidatos], parent=self)
                    if dlg.exec() != QDialog.DialogCode.Accepted:
                        return
                    elegidas = set(dlg.seleccionadas())
                    candidatos = [c for c in candidatos if c[0] in elegidas]
                    if not candidatos:
                        return
                elif len(candidatos) == 1:
                    # Una sola: usar el nombre del archivo tal cual
                    etiqueta, _nombre, df_serie = candidatos[0]
                    candidatos = [(etiqueta, base_nombre, df_serie)]

                for _etiqueta, nombre_crono, df_serie in candidatos:
                    self._agregar_crono(f"📚 {nombre_crono}", df_serie, ruta)
                return
            except Exception:
                logger.debug("Lectura multicolumna descartada para %s", ruta, exc_info=True)

            df, sid = leer_tabular(ruta)
            self._agregar_crono(f"📚 {sid}", df, ruta)

        except Exception as exc:
            QMessageBox.warning(self, "Error", f"No se pudo cargar la cronología:\n{exc}")

        self.graficar_series()

    def _procesar_tucson_como_crono(self, series: dict, ruta: str):
        """Procesa series Tucson de un archivo:
        • 1 serie → la carga directamente como 📚
        • N series → auto-genera cronología (residual+spline+biweight), la
          activa como 📚 y NO carga las series individuales
        """
        if not series:
            return

        if len(series) == 1:
            sid, df = next(iter(series.items()))
            self._agregar_crono(f"📚 {sid}", df, ruta)
            self.graficar_series()
            return

        # Múltiples series → auto-cronología con diálogo de progreso
        nombres = list(series.keys())

        progreso = QProgressDialog(
            f"Generando cronología desde {len(nombres)} series...",
            None, 0, 100, self
        )
        progreso.setWindowTitle("Auto-Cronología")
        progreso.setWindowModality(Qt.WindowModality.WindowModal)
        progreso.setMinimumDuration(0)
        progreso.setCancelButton(None)  # no cancelable, evita estados inconsistentes
        progreso.setValue(5)
        QApplication.processEvents()

        try:
            progreso.setLabelText("Estandarizando series (spline + AR removal)...")
            QApplication.processEvents()
            df_crono, meta = _construir_cronologia_desde_series(
                series, nombres,
                tipo_cronologia="residual",
                metodo_estandarizacion="spline",
                agregacion="biweight",
            )
            progreso.setValue(30)
            QApplication.processEvents()
        except Exception as exc:
            progreso.close()
            QMessageBox.warning(
                self, "Error al generar cronología",
                f"No se pudo generar cronología automática:\n{exc}\n\n"
                "Las series individuales no fueron cargadas."
            )
            return

        nombre_base = os.path.splitext(os.path.basename(ruta))[0]
        nombre = f"{nombre_base}_auto"
        meta["nombre"] = nombre

        # Rbar y EPS ya vienen calculados desde dentro de
        # _construir_cronologia_desde_series sobre las series DETRENDADAS
        # (comparable con ARSTAN "all possible series rbar"). Antes acá
        # se sobrescribían usando series raw, lo que inflaba el Rbar.
        progreso.setValue(50)
        QApplication.processEvents()

        # EPS / Rbar móvil con callback
        progreso.setLabelText("Calculando EPS y Rbar móvil...")
        QApplication.processEvents()

        def _cb_progreso(pct):
            # mapear 0..100 a 50..95
            progreso.setValue(50 + int(pct * 0.45))
            QApplication.processEvents()

        try:
            eps_df = calcular_eps_rbar_movil(
                series, nombres, window=15,
                paso=max(1, len(df_crono) // 200),
                progreso=_cb_progreso,
            )
            if not eps_df.empty:
                meta["EPS_movil"] = eps_df["EPS"].dropna().to_dict()
                meta["Rbar_movil"] = eps_df["Rbar"].dropna().to_dict()
        except Exception as exc:
            logger.warning("EPS/Rbar móvil falló: %s", exc)

        progreso.setLabelText("Activando cronología...")
        progreso.setValue(95)
        QApplication.processEvents()

        # Activar como cronología, garantizando el cierre del diálogo de
        # progreso pase lo que pase (así no queda una ventana "pegada" que
        # parece que nunca termina).
        try:
            self.set_cronologia_activa(df_crono, meta, nombre)
            progreso.setValue(100)
        finally:
            progreso.close()

        # Rbar y EPS para el mensaje: vienen calculados dentro de
        # _construir_cronologia_desde_series y quedan en meta.
        rbar = meta.get("Rbar", float("nan"))
        eps_val = meta.get("EPS", float("nan"))
        rbar_txt = f"{rbar:.3f}" if np.isfinite(rbar) else "—"
        eps_txt = f"{eps_val:.3f}" if np.isfinite(eps_val) else "—"

        QMessageBox.information(
            self, "✅ Cronología generada automáticamente",
            f"Se generó la cronología '{nombre}' a partir de "
            f"{len(nombres)} serie(s) del archivo.\n\n"
            f"  • Años: {len(df_crono)}\n"
            f"  • Tipo: residual (spline 32 años + AR removal)\n"
            f"  • Agregación: biweight\n"
            f"  • Rbar: {rbar_txt}    EPS: {eps_txt}\n\n"
            f"La cronología aparece en la lista con 📚 y está lista para "
            f"cofechado.\n\n"
            f"Si quieres ajustar parámetros (tipo, método, estandarización), "
            f"usa la pestaña 🧭 Cronología."
        )

    def _agregar_crono(self, nombre: str, df: pd.DataFrame, ruta: str):
        """Agrega una cronología 📚 a la lista y la marca como activa.

        La cronología recién cargada queda como `cronologia_activa` para que
        el botón "Series múltiples vs Crono" la encuentre disponible
        inmediatamente. Si ya había una activa anterior, la sobrescribe (el
        usuario puede tener varias en la lista pero solo una "activa" para
        comparaciones).

        Meta mínima: tipo "raw" porque las cronologías cargadas externamente
        ya vienen en su forma final (no se les aplica más transformación).
        """
        if nombre in self.series_datos:
            return
        self.modelo_series.registrar(nombre, df)
        self._series_modificadas(regraficar=False)
        item = QListWidgetItem(nombre)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.lista_series.addItem(item)

        # Marcar automáticamente como cronología activa SIN volver a
        # agregarla a la lista (ya la agregamos arriba). El flag
        # agregar_a_lista=False evita la duplicación: antes la cronología
        # aparecía dos veces (una por este método y otra porque
        # set_cronologia_activa también la agregaba).
        meta = {
            "tipo_cronologia": "raw",
            "columna_valor": "Ancho_mm",
            "metodo_estandarizacion": "spline",
        }
        nombre_limpio = nombre.replace("📚 ", "").strip()
        self.set_cronologia_activa(df, meta, nombre_limpio, agregar_a_lista=False)


    # -------------------------------------------------------------------------
    # GESTIÓN DE LA LISTA DE SERIES
    # -------------------------------------------------------------------------

    def _anclaje_actual(self) -> str:
        """Extremo fijo al corregir anillos ('corteza' o 'medula')."""
        combo = getattr(self, "combo_anclaje", None)
        if combo is None:
            return "corteza"
        return combo.currentData() or "corteza"

    def _ordenar_ref_problema(self, n1: str, n2: str) -> tuple[str, str]:
        """Devuelve (referencia, problema) para un par de series.

        La CRONOLOGÍA siempre es la referencia: es el patrón contra el que se
        data y nunca se le insertan ni quitan anillos. Si ninguna lo es (o lo
        son ambas), se usa la más larga como referencia.
        """
        c1 = n1.startswith("📚")
        c2 = n2.startswith("📚")
        if c1 and not c2:
            return n1, n2
        if c2 and not c1:
            return n2, n1
        try:
            if len(self.series_datos[n1]) >= len(self.series_datos[n2]):
                return n1, n2
        except Exception:
            pass
        return n2, n1

    def _serie_seleccionada(self) -> str | None:
        """Devuelve la serie SELECCIONADA (fila resaltada en azul), o None.

        Separación de responsabilidades en la lista de series:
          • La CASILLA (☑) controla qué series se DIBUJAN en el gráfico.
          • La SELECCIÓN (fila azul) es sobre qué serie ACTÚAN los botones
            (editar, restaurar, insertar/borrar anillo, año base, etc.).

        Antes las acciones usaban las casillas y exigían exactamente UNA
        marcada; al comparar una serie con su cronología (lo normal) hay dos
        marcadas, así que los botones no hacían nada y solo avisaban.
        """
        item = self.lista_series.currentItem()
        if item is None:
            return None
        nombre = item.text()
        return nombre if nombre in self.series_datos else None

    def _serie_para_accion(self, accion: str = "editar") -> str | None:
        """Serie sobre la que actuar, con aviso claro si no hay selección.

        Respaldo: si no hay fila seleccionada pero hay exactamente UNA casilla
        marcada, se usa esa (comportamiento antiguo) para no romper la
        costumbre de quien ya trabajaba así.
        """
        nombre = self._serie_seleccionada()
        if nombre is not None:
            return nombre
        marcadas = self._series_marcadas()
        if len(marcadas) == 1:
            return marcadas[0]
        QMessageBox.warning(
            self, "Atención",
            f"Selecciona (haz clic sobre) la serie que quieres {accion}.\n\n"
            "La casilla ☑ solo controla qué series se dibujan en el gráfico; "
            "la fila resaltada en azul es la que se edita.")
        return None
    def _series_marcadas(self) -> list[str]:
        return [
            self.lista_series.item(i).text()
            for i in range(self.lista_series.count())
            if self.lista_series.item(i).checkState() == Qt.CheckState.Checked
        ]

    def toggle_seleccion(self):
        todas = all(
            self.lista_series.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.lista_series.count())
        )
        estado = Qt.CheckState.Unchecked if todas else Qt.CheckState.Checked
        self.lista_series.blockSignals(True)
        for i in range(self.lista_series.count()):
            self.lista_series.item(i).setCheckState(estado)
        self.lista_series.blockSignals(False)
        self.graficar_series()

    def eliminar_series(self):
        """Elimina las series seleccionadas (múltiples permitidas)."""
        items = self.lista_series.selectedItems()
        if not items:
            return

        self._descartar_prueba(silencioso=True)
        nombres_a_eliminar = [item.text() for item in items]
        nombres_set = set(nombres_a_eliminar)

        for nombre in nombres_a_eliminar:
            self.modelo_series.eliminar(nombre)
        self._series_modificadas(regraficar=False)

        for i in range(self.lista_series.count() - 1, -1, -1):
            if self.lista_series.item(i).text() in nombres_set:
                self.lista_series.takeItem(i)

        if self._nombre_referencia in nombres_set:
            self._nombre_referencia = ""
        if self._nombre_problema in nombres_set:
            self._nombre_problema = ""

        if (self._nombre_cronologia_activa and
                f"📚 {self._nombre_cronologia_activa}" in nombres_set):
            self.cronologia_activa = None
            self.meta_cronologia = None
            self._nombre_cronologia_activa = ""
            self.lbl_info_crono.setVisible(False)
            self.btn_eps_crono.setEnabled(False)

        self.graficar_series()

        necesita_limpiar = (
            not self._nombre_referencia or not self._nombre_problema or
            self._nombre_referencia not in self.series_datos or
            self._nombre_problema not in self.series_datos
        )
        if necesita_limpiar:
            self.grafico_offset.clear()
            self._shifts_actuales.clear()
            self._r_actuales.clear()
            self._glk_actuales.clear()
            self._tbp_actuales.clear()
            self._n_actuales.clear()
            self._stats_movil_years.clear()
            self._stats_movil_r.clear()
            self._stats_movil_glk.clear()
            self._stats_movil_tbp.clear()
            self._stats_movil_n.clear()
            self._sugerencias = []
            self.tabla_sugerencias.setRowCount(0)
            self.btn_aplicar.setEnabled(False)
            self.lbl_stats.setVisible(False)
            self.btn_ver_tabla_off.setEnabled(False)

    def editar_anio_serie(self):
        """Cambia el año base de la serie seleccionada.

        Muestra un diálogo con DOS spinboxes:
          • Año del primer anillo (MÉDULA) ← campo principal, foco por defecto
          • Año del último anillo (CORTEZA)
        Al cambiar uno, el otro se ajusta automáticamente. El usuario edita
        el que tenga datos confiables (típicamente médula para series flotantes,
        corteza para muestras con corteza preservada).
        """
        items = self.lista_series.selectedItems()
        if not items:
            QMessageBox.warning(self, "Atención",
                                "Selecciona una serie (haz clic sobre su nombre).")
            return
        if len(items) > 1:
            QMessageBox.warning(self, "Atención", "Edita una sola serie a la vez.")
            return

        nombre = items[0].text()
        self._descartar_prueba(silencioso=True)
        df = self.series_datos.get(nombre)
        if df is None or df.empty:
            return

        n_anios = len(df)
        anio_medula_actual = int(df.index.min())
        anio_corteza_actual = int(df.index.max())

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Editar año base — {nombre}")
        dlg.setMinimumWidth(440)
        v = QVBoxLayout(dlg)

        info = QLabel(
            f"<b>Serie:</b> {nombre}<br>"
            f"<b>Rango actual:</b> {anio_medula_actual} → {anio_corteza_actual} "
            f"<span style='color:{color_secundario()};'>({n_anios} años)</span>"
        )
        v.addWidget(info)

        hint = QLabel(
            f"<span style='color:{color_secundario()}; font-size:11px;'>"
            "Edita el campo que conozcas con certeza. El otro se "
            "ajusta automáticamente. Para series flotantes lo habitual "
            "es anclar el primer año (médula); para muestras con corteza "
            "preservada se ancla el último año."
            "</span>"
        )
        hint.setWordWrap(True)
        v.addWidget(hint)

        form = QFormLayout()
        spin_medula = SpinBoxFlechas()
        spin_medula.setRange(-10000, 5000)
        spin_medula.setValue(anio_medula_actual)
        spin_medula.setStyleSheet("QSpinBox{font-weight:bold; color:#5cb85c;}")
        form.addRow("🌱 <b>Primer año (MÉDULA):</b>", spin_medula)

        spin_corteza = SpinBoxFlechas()
        spin_corteza.setRange(-10000, 5000)
        spin_corteza.setValue(anio_corteza_actual)
        spin_corteza.setStyleSheet("QSpinBox{color:#f0ad4e;}")
        form.addRow("🪵 Último año (CORTEZA):", spin_corteza)
        v.addLayout(form)

        # Vinculación: cuando cambia uno, el otro se ajusta
        _bloqueado = [False]

        def _sync_desde_medula():
            if _bloqueado[0]:
                return
            _bloqueado[0] = True
            spin_corteza.setValue(spin_medula.value() + n_anios - 1)
            _bloqueado[0] = False

        def _sync_desde_corteza():
            if _bloqueado[0]:
                return
            _bloqueado[0] = True
            spin_medula.setValue(spin_corteza.value() - n_anios + 1)
            _bloqueado[0] = False

        spin_medula.valueChanged.connect(_sync_desde_medula)
        spin_corteza.valueChanged.connect(_sync_desde_corteza)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)

        # Foco en MÉDULA por default
        spin_medula.setFocus()
        spin_medula.selectAll()

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        nuevo_medula = spin_medula.value()
        delta = nuevo_medula - anio_medula_actual
        if delta == 0:
            return

        self.modelo_series.desplazar(nombre, delta)
        df_nuevo = self.modelo_series.datos[nombre]
        self._series_modificadas()
        QMessageBox.information(
            self, "Año actualizado",
            f"Serie '{nombre}' desplazada {delta:+d} años.\n"
            f"Ahora va de {int(df_nuevo.index.min())} a {int(df_nuevo.index.max())}."
        )

    def _exportar_una_serie(self, nombre: str):
        'Exporta UNA serie por nombre (usado al exportar varias a la vez).'
        return exportacion_series._exportar_una_serie(self, nombre)

    def exportar_serie_codatada(self):
        'Exporta la serie marcada con formato según extensión.\n\n        Si el modo COFECHA está activo y aplica a este tipo (serie o\n        cronología), ofrece guardar la serie ESTANDARIZADA (la misma\n        transformación que se usa para las correlaciones) en vez de los\n        datos crudos. Así el usuario puede subir una serie, activar el modo\n        COFECHA y guardar la versión estandarizada directamente.\n        '
        return exportacion_series.exportar_serie_codatada(self)

    def _exportar_serie_por_nombre(self, nombre: str):
        'Cuerpo real de la exportación, para una serie ya elegida.'
        return exportacion_series._exportar_serie_por_nombre(self, nombre)

    def _guardar_serie_2col(self, serie, nombre_archivo, titulo, estandarizada=False):
        'Guarda una serie en formato 2 columnas (Año, Valor) con coma\n        decimal. Usado para cronologías y para series estandarizadas\n        COFECHA (que son índices residuales adimensionales, no anchos en\n        mm, por lo que NO van por el exportador Tucson).'
        return exportacion_series._guardar_serie_2col(self, serie, nombre_archivo, titulo, estandarizada)

    # -------------------------------------------------------------------------
    # SIMULADOR MANUAL
    # -------------------------------------------------------------------------

    def simular_insertar(self):
        self._simular_correccion(1)

    def simular_borrar(self):
        self._simular_correccion(-1)

    def _simular_correccion(self, delta):
        nombre = self._serie_para_accion("editar")
        if nombre is None:
            return
        self._descartar_prueba(silencioso=True)
        anio = self.spin_edit_year.value()
        corregido = aplicar_correccion(
            self.series_datos[nombre], anio, delta, anclaje=self._anclaje_actual())
        try:
            self.modelo_series.actualizar(nombre, corregido)
        except (ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "Corrección inválida", str(exc))
            return
        self._series_modificadas()

    def abrir_skeleton_plot(self):
        """Va a la pestaña Skeleton, importa las series de Co-Datación y, si
        hay exactamente dos marcadas, las fija como referencia y flotante.

        `ir_a_skeleton` lo conecta main_anillos: recibe (ref_nombre_o_None,
        flo_nombre_o_None) para preseleccionar el par (o None para solo ir e
        importar)."""
        marcadas = self._series_marcadas()
        ref_nombre = flo_nombre = None
        if len(marcadas) == 2:
            cronos = [n for n in marcadas if n.startswith("📚")]
            if cronos:
                ref_nombre = cronos[0]
                flo_nombre = [n for n in marcadas if n != ref_nombre][0]
            else:
                ref_nombre, flo_nombre = marcadas[0], marcadas[1]

        cb = getattr(self, "ir_a_skeleton", None)
        if callable(cb):
            cb(ref_nombre, flo_nombre)
        else:
            QMessageBox.information(
                self, "Skeleton",
                "Abre la pestaña Skeleton e importa las series desde allí.")

    def restaurar_serie(self):
        nombre = self._serie_para_accion("restaurar")
        if nombre is None:
            return
        if nombre not in self.series_originales:
            QMessageBox.information(
                self, "Sin original",
                f"'{nombre}' no tiene una copia original guardada "
                "(no se le han aplicado correcciones).")
            return
        self._descartar_prueba(silencioso=True)
        self.modelo_series.restablecer(nombre)
        self._series_modificadas()
        QMessageBox.information(
            self, "Restaurada",
            f"'{nombre}' volvió a sus valores originales.")

    def restaurar_original_sugerencias(self):
        """Restablece a sus valores originales la serie que se está
        corrigiendo (la del cofechado/sugerencias). Si no hay una serie
        problema definida, usa la serie marcada."""
        nombre = getattr(self, "_nombre_problema", None)
        if not nombre or nombre not in self.series_datos:
            marcadas = self._series_marcadas()
            nombre = marcadas[0] if len(marcadas) == 1 else None
        if not nombre or nombre not in self.series_originales:
            QMessageBox.warning(
                self, "Sin original",
                "No hay una serie con valores originales para restablecer.\n"
                "Cofecha o selecciona una serie primero.")
            return
        resp = QMessageBox.question(
            self, "Restablecer valores originales",
            f"¿Restablecer '{nombre}' a sus valores originales?\n\n"
            "Se descartarán todas las correcciones de anillos aplicadas a "
            "esta serie.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        self._descartar_prueba(silencioso=True)
        self.modelo_series.restablecer(nombre)
        self._series_modificadas(regraficar=False)
        self._limpiar_preview()
        self._sugerencias.clear()
        self.tabla_sugerencias.setRowCount(0)
        self.btn_aplicar.setEnabled(False)
        self.graficar_series()
        self.buscar_errores()

    # -------------------------------------------------------------------------
    # VISUALIZACIÓN DE SERIES
    # -------------------------------------------------------------------------

    def _anotar_anios_en_lista(self):
        'Recorre todas las series de la lista y anota en cada item su\n        rango de años como tooltip. Si el último año de una serie supera\n        el año actual (presente), marca el item con color de advertencia\n        y un símbolo ⚠️ en el tooltip.\n\n        Esto es importante sobre todo para series flotantes: cuando se les\n        asigna un año de inicio, el último año puede quedar más allá del\n        presente, lo que es físicamente imposible (un árbol no tiene\n        anillos en el futuro) y delata un año de inicio mal asignado.\n        '
        return presentacion_series._anotar_anios_en_lista(self)

    def _series_modificadas(self, *, regraficar=True):
        """Invalida resultados de comparación tras cambiar datos o cronología."""
        self._cache_comparacion = None
        if regraficar:
            self.graficar_series()

    def graficar_series(self):
        """Redibuja el gráfico principal con las series marcadas.

        Si el Modo COFECHA está activo, grafica las series TRANSFORMADAS
        (spline + log + AR(1) según configuración) en vez del ancho crudo,
        respetando los checkboxes 'Aplicar a: Serie / Cronología'. Esto
        permite ver las series detrendadas superpuestas, que es mucho más
        informativo para cofechar que el ancho crudo (donde la tendencia
        de crecimiento por edad domina y oculta la señal común).
        """
        # Anotar el rango de años de cada serie en la lista (tooltip +
        # aviso si el último año supera el presente).
        self._anotar_anios_en_lista()

        self.grafico.clear()

        # Recrear la leyenda en cada repintado. En algunas versiones de
        # pyqtgraph, clear() NO borra la leyenda, y ésta acumula los códigos
        # de todas las series dibujadas (una "ventana" de leyenda que persiste
        # y crece). Recrearla garantiza que solo muestre las series actuales.
        if self.grafico.plotItem.legend is not None:
            try:
                self.grafico.plotItem.legend.scene().removeItem(
                    self.grafico.plotItem.legend)
            except Exception:
                pass
            self.grafico.plotItem.legend = None
        self.grafico.addLegend()

        modo_cofecha = self.btn_modo_cofecha.isChecked()
        modo_barras = (hasattr(self, "btn_grafico_barras") and
                       self.btn_grafico_barras.isChecked())
        graficadas = 0
        series_a_dibujar = []  # [(nombre, valores, color)] usado en modo barras
        for i in range(self.lista_series.count()):
            item = self.lista_series.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            nombre = item.text()
            if nombre not in self.series_datos:
                continue
            df = self.series_datos[nombre]
            serie_mm = pd.to_numeric(df["Ancho_mm"], errors="coerce")

            # Decidir si transformar esta serie según el modo y los checkboxes
            es_crono = nombre.startswith("📚")
            transformar = modo_cofecha and (
                (es_crono and self.chk_cof_crono.isChecked()) or
                (not es_crono and self.chk_cof_serie.isChecked())
            )
            if transformar:
                try:
                    # Usar la MISMA transformación que la correlación para que
                    # la serie quede en el espacio de la cronología activa
                    # (índice residual, media ~1) y se pueda superponer
                    # visualmente con la cronología. Antes se usaba
                    # aplicar_modo_cofecha (log, media 0) y los gráficos
                    # quedaban en escalas distintas (crono en 1, serie en 0).
                    valores = self._transformar_para_correlacion(
                        serie_mm, es_crono)
                except Exception:
                    valores = serie_mm
            else:
                valores = serie_mm

            valores = valores.dropna()
            if valores.empty:
                continue

            color = COLORES_SERIES[graficadas % len(COLORES_SERIES)]
            if modo_barras:
                # Se acumulan para dibujarlas después: hay que saber cuántas
                # series hay para repartir el ancho de las barras por año.
                series_a_dibujar.append((nombre, valores, color))
            else:
                self.grafico.plot(
                    valores.index.to_numpy(dtype=float),
                    valores.to_numpy(dtype=float),
                    pen=pg.mkPen(color, width=2),
                    name=nombre,
                )
            graficadas += 1

        if modo_barras and series_a_dibujar:
            self._dibujar_barras_desviacion(series_a_dibujar)

        # Actualizar etiqueta del eje Y según el modo
        if modo_cofecha:
            self.grafico.setLabel("left", "Índice estandarizado (media ~1)")
        else:
            self.grafico.setLabel("left", "Ancho de anillo (mm)")

    def _dibujar_barras_desviacion(self, series: list):
        'Dibuja las series como barras que salen de su MEDIA.\n\n        La media de cada serie es el eje central: la barra sube cuando el\n        año está sobre la media y baja cuando está bajo la media. Con varias\n        series marcadas, las barras del mismo año se reparten lado a lado\n        para que no se tapen.\n        '
        return presentacion_series._dibujar_barras_desviacion(self, series)

    # -------------------------------------------------------------------------
    # CRONOLOGÍA ACTIVA
    # -------------------------------------------------------------------------

    def conectar_fuente_cronologia(self, obtener_series, abrir=None):
        self._obtener_series_cronologia = obtener_series
        if abrir is not None:
            self._abrir_cronologia = abrir

    def abrir_ventana_cronologia(self):
        if self._abrir_cronologia is not None:
            self._abrir_cronologia()

    def set_cronologia_activa(self, df: pd.DataFrame, meta: dict, nombre: str,
                               agregar_a_lista: bool = True):
        """Setea la cronología activa para cofechado.

        Parámetro `agregar_a_lista`:
          - True (default): agrega la cronología a la lista de series con
            prefijo 📚 (comportamiento usado cuando se genera una
            cronología desde la VentanaCronologia, que NO la tiene aún
            en la lista).
          - False: NO toca la lista — solo marca la cronología como activa
            y actualiza la etiqueta informativa. Se usa desde
            `_agregar_crono`, que YA agregó la cronología a la lista. Sin
            este flag, la cronología aparecía DUPLICADA: una vez por
            `_agregar_crono` y otra por esta función.
        """
        self._descartar_prueba(silencioso=True)
        self.cronologia_activa = df.copy()
        self.meta_cronologia = dict(meta) if meta else {}
        self._nombre_cronologia_activa = nombre or "Cronología"
        self._series_modificadas(regraficar=False)

        if agregar_a_lista:
            # Agregar a la lista como 📚
            nombre_lista = f"📚 {self._nombre_cronologia_activa}"
            col_val = self.meta_cronologia.get("columna_valor", df.columns[0])
            if col_val not in df.columns:
                col_val = df.columns[0]
            df_serie = pd.DataFrame({"Ancho_mm": df[col_val]}, index=df.index)
            df_serie = df_serie.dropna()

            existe = nombre_lista in self.series_datos
            if existe:
                self.modelo_series.reemplazar(nombre_lista, df_serie)
            else:
                self.modelo_series.registrar(nombre_lista, df_serie)
            if not existe:
                item = QListWidgetItem(nombre_lista)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.lista_series.addItem(item)

        # Mostrar info de cronología (siempre, sin importar agregar_a_lista)
        n_anios = len(df)
        n_series = self.meta_cronologia.get("n_series", 0)
        rbar = self.meta_cronologia.get("Rbar", float("nan"))
        eps = self.meta_cronologia.get("EPS", float("nan"))

        # Etiqueta corta del tipo de cronología: RES (residual), STD
        # (standard) o RAW (cruda). Se muestra al usuario para que sepa en qué
        # espacio está la cronología (una RES vive en torno a media 1).
        tipo_crono = (self.meta_cronologia.get("tipo_cronologia") or "raw").lower()
        tag_tipo = {"residual": "RES", "standard": "STD", "raw": "RAW"}.get(
            tipo_crono, tipo_crono.upper()[:3])
        nombre_tipo = {"RES": "residual", "STD": "standard",
                       "RAW": "cruda"}.get(tag_tipo, tipo_crono)
        self._tag_tipo_cronologia = tag_tipo

        info = f"📚 <b>{self._nombre_cronologia_activa}</b> [{tag_tipo}] — {n_anios} años"
        if n_series:
            info += f", {n_series} series"
        if np.isfinite(rbar):
            info += f", Rbar={rbar:.3f}"
        if np.isfinite(eps):
            info += f", EPS={eps:.3f}"
        self.lbl_info_crono.setText(info)
        # NO se hace visible: este QLabel quedó vestigial al mover la sección
        # de Cronología a su propia pestaña. Antes se hacía setVisible(True),
        # pero como el label no está en ningún layout (sin padre visible), Qt
        # lo mostraba como una ventana suelta transparente titulada
        # "run_dpi.py" detrás del programa. Se mantiene oculto.

        # Habilitar botón EPS si hay datos móviles
        tiene_eps_movil = bool(self.meta_cronologia.get("EPS_movil"))
        self.btn_eps_crono.setEnabled(tiene_eps_movil)

        self.graficar_series()

    def _mostrar_eps_cronologia_activa(self):
        """Muestra el diálogo de EPS/Rbar móvil de la cronología activa."""
        _mostrar_dialogo_eps_rbar(
            self, self.meta_cronologia or {}, self._nombre_cronologia_activa
        )

    # -------------------------------------------------------------------------
    # MODO COFECHA
    # -------------------------------------------------------------------------

    def _on_modo_cofecha_toggled(self, activo: bool):
        """Al activar/desactivar el Modo COFECHA, actualiza el texto del
        botón y redibuja el gráfico para mostrar las series transformadas
        (si activo) o el ancho crudo (si inactivo)."""
        self.btn_modo_cofecha.setText(
            "🎯 Modo COFECHA ACTIVO" if activo else "🎯 Activar Modo COFECHA")
        self.graficar_series()

    def _on_cofecha_aplicar_cambiado(self, _checked: bool):
        """Al cambiar los checkboxes 'Aplicar a: Serie/Cronología',
        redibuja solo si el modo COFECHA está activo (si no, no tiene
        efecto visible)."""
        if self.btn_modo_cofecha.isChecked():
            self.graficar_series()

    def _configurar_modo_cofecha(self):
        """Abre el diálogo de configuración del modo COFECHA."""
        dlg = DialogoCofecha(self, self._modo_cofecha_params)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._modo_cofecha_params = dlg.get_params()
            # Si el modo está activo, redibujar con los nuevos parámetros
            if self.btn_modo_cofecha.isChecked():
                self.graficar_series()

    # -------------------------------------------------------------------------
    # TRANSFORMACIÓN PARA CORRELACIÓN
    # -------------------------------------------------------------------------

    def _transformar_para_correlacion(self, serie_mm: pd.Series, es_crono: bool) -> pd.Series:
        return _tr.transformar_para_correlacion(
            serie_mm, es_crono, activo=self.btn_modo_cofecha.isChecked(),
            aplicar_serie=self.chk_cof_serie.isChecked(), aplicar_crono=self.chk_cof_crono.isChecked(),
            meta=self.meta_cronologia, cronologia=self.cronologia_activa,
            parametros=self._modo_cofecha_params)

    def _serie_para_glk(self, serie_mm: pd.Series, es_crono: bool) -> pd.Series:
        """Serie para calcular GLK y t-BP.

        GLK y t-BP diferencian internamente (GLK usa el signo de la primera
        diferencia; t-BP aplica el filtro de Hollstein = diff-log), así que se
        calculan sobre los datos CRUDOS y no necesitan la estandarización
        COFECHA. Esto los mantiene estables y comparables con el uso clásico.
        """
        return _tr.serie_numerica(serie_mm)

    def _preparar_serie_comparacion(self, datos, es_crono):
        from dpi.series.comparacion import preparar_serie
        return preparar_serie(datos,
            lambda serie: self._transformar_para_correlacion(serie, es_crono),
            lambda serie: self._serie_para_glk(serie, es_crono))

    def _preparar_diferencias_log(self, n1: str, n2: str):
        """Prepara las series transformadas de un par para cofechado."""
        df1 = self.series_datos[n1]
        df2 = self.series_datos[n2]
        es_crono_1 = n1.startswith("📚")
        es_crono_2 = n2.startswith("📚")

        # El leave-one-out vive ahora en la pestaña COFECHA, donde todas las
        # series miembro están cargadas y puede aplicarse siempre. Acá se
        # comparan las series tal cual.
        s1 = df1["Ancho_mm"]
        s2 = df2["Ancho_mm"]
        d1 = self._transformar_para_correlacion(s1, es_crono_1)
        d2 = self._transformar_para_correlacion(s2, es_crono_2)
        return d1, d2, n1, n2

    def _fmt_r(self, r: float) -> str:
        if not np.isfinite(r):
            return "—"
        return f"{r:.3f}"


    # -------------------------------------------------------------------------
    # ANÁLISIS DE OFFSET (BÚSQUEDA DE DESFASE)
    # -------------------------------------------------------------------------

    def analizar_offset(self):
        """Análisis de desfase: r/GLK/t-BP por cada shift posible."""
        marcadas = self._series_marcadas()
        if len(marcadas) != 2:
            return QMessageBox.warning(self, "Atención", "Marque EXACTAMENTE dos series.")

        # Determinar cuál es la SERIE (se mueve) y cuál la CRONOLOGÍA (fija,
        # referencia). Se distinguen por el prefijo 📚 de las cronologías.
        # El desfase se aplica siempre a la SERIE para alinearla con la
        # cronología. Si ninguna o ambas son cronología, se respeta el
        # orden de marcado (la primera se mueve).
        cronos = [m for m in marcadas if m.startswith("📚")]
        series = [m for m in marcadas if not m.startswith("📚")]
        if len(cronos) == 1 and len(series) == 1:
            mover, referencia = series[0], cronos[0]
        else:
            mover, referencia = marcadas[0], marcadas[1]

        # Limpiar modo de la curva de cofechado
        self._stats_movil_years = []
        self._stats_movil_r = []
        self._stats_movil_glk = []
        self._stats_movil_tbp = []
        self._stats_movil_n = []

        self.grafico_offset.clear()
        self.grafico_offset.setTitle("Procesando…")
        self.grafico_offset.addItem(self._texto_hover)
        self._texto_hover.hide()

        # m_diff = serie que se MUEVE; t_diff = cronología/referencia FIJA
        n_m, n_t = mover, referencia
        datos_a = self.series_datos[n_m]["Ancho_mm"]
        datos_b = self.series_datos[n_t]["Ancho_mm"]
        preparada_a = self._preparar_serie_comparacion(datos_a, n_m.startswith("📚"))
        preparada_b = self._preparar_serie_comparacion(datos_b, n_t.startswith("📚"))
        m_diff, t_diff = preparada_a.correlacion, preparada_b.correlacion

        if (len(m_diff) < OVERLAP_MINIMO_ANALISIS or
                len(t_diff) < OVERLAP_MINIMO_ANALISIS):
            return self.grafico_offset.setTitle(
                f"Error: Se requieren >{OVERLAP_MINIMO_ANALISIS} años.")

        serie_a_raw, serie_b_raw = preparada_a.cruda, preparada_b.cruda
        serie_a_glk, serie_b_glk = preparada_a.glk, preparada_b.glk

        # Guardar para la tabla de detalle (año de término, alineamiento,
        # aplicar desfase). n_m es la primera serie marcada (la que se data).
        self._offset_nombre_a = n_m
        self._offset_serie_a_raw = serie_a_raw
        self._offset_serie_b_raw = serie_b_raw

        # Convención de desfase: el shift se aplica a la PRIMERA serie
        # marcada (m_diff, la que se está datando) para alinearla con la
        # SEGUNDA (t_diff, la referencia). Así un desfase positivo significa
        # "sumar estos años a la primera serie para posicionarla", igual que
        # en 'Series múltiples vs Crono'. Antes se desplazaba la segunda
        # serie, lo que daba desfases negativos para series flotantes y
        # resultaba confuso e inconsistente entre los dos análisis.
        from dpi.ciencia.comparacion_nucleo import analizar_desfases
        (self._shifts_actuales, self._r_actuales, self._glk_actuales,
         self._tbp_actuales, self._n_actuales) = analizar_desfases(
            m_diff, t_diff, serie_a_glk, serie_b_glk)

        if not self._shifts_actuales:
            return self.grafico_offset.setTitle("Sin coincidencias suficientes.")

        self._redibujar_offset()
        self.btn_ver_tabla_off.setEnabled(True)

    def _redibujar_offset(self):
        from dpi.ui.presentacion_desfases import _redibujar_offset
        return _redibujar_offset(self)

    # ── Comparación múltiple directa contra cronología ────────────────────

    def aplicar_desfase_a_serie(self, nombre: str, shift: int,
                                 regraficar: bool = True) -> bool:
        """Re-data UNA serie sumando `shift` a su índice de años.

        Reutilizable desde la tabla de comparación múltiple y desde la
        ventana de detalle. Conserva los datos originales,
        invalida la caché de comparación y (opcionalmente) regrafica.

        Devuelve True si aplicó algún cambio.
        """
        self._descartar_prueba(silencioso=True)
        if not self.modelo_series.desplazar(nombre, shift):
            return False
        self._series_modificadas(regraficar=regraficar)
        return True

    def reemplazar_serie(self, nombre: str, df_nuevo: pd.DataFrame,
                          regraficar: bool = True):
        """Reemplaza por completo los datos de una serie (usado por el
        editor de anillos, que cambia anchos y/o cantidad de anillos).
        Invalida la caché de comparación y regrafica."""
        self._descartar_prueba(silencioso=True)
        self.modelo_series.actualizar(nombre, df_nuevo)
        self._series_modificadas(regraficar=regraficar)

    def _abrir_editor_anillos_marcada(self):
        """Abre el editor de anillos para la serie marcada (exactamente
        una). Accesible directamente desde el panel principal."""
        nombre = self._serie_para_accion("editar")
        if nombre is None:
            return
        self._descartar_prueba(silencioso=True)
        # No se editan anchos de una cronología
        if nombre.startswith("📚"):
            QMessageBox.information(
                self, "Selecciona una serie",
                "La selección es una cronología (📚) y no se editan sus "
                "anchos.\n\nSelecciona una serie de medición.")
            return
        df = self.series_datos.get(nombre)
        if df is None or df.empty:
            QMessageBox.warning(self, "Sin datos",
                                "La serie seleccionada no tiene datos.")
            return
        dlg = DialogoEditarAnillos(df, nombre, self.reemplazar_serie, parent=self)
        dlg.exec()

    def comparar_series_marcadas_vs_crono(self):
        'Compara las series marcadas (1 o varias) contra la cronología\n        activa. Lanzada desde el botón "Series múltiples vs Crono" del\n        panel principal — el usuario no tiene que abrir la ventana de\n        cronología para usar esta funcionalidad.\n\n        Flujo:\n          1. Si NO hay cronología cargada: avisa al usuario que primero\n             cargue/genere una.\n          2. Si hay 0 series marcadas: aviso.\n          3. Si hay 1+ series marcadas: ejecuta el cálculo en lote y\n             abre `DialogoComparacionMultiple` con los resultados.\n\n        RANGO DE DESFASE DINÁMICO POR SERIE:\n        En vez de usar un max_shift fijo, el rango se calcula por serie\n        según los años que cubre. Esto permite que el mismo botón funcione\n        con dos tipos de series:\n\n          - Series FECHADAS (años calendar 1500-2020 por ejemplo): el\n            rango natural es estrecho, solo hay overlap cerca de shift=0.\n            El cálculo es rápido y detecta errores de datación pequeños\n            (anillos faltantes/extra).\n\n          - Series FLOTANTES (años arbitrarios 0-200 por ejemplo): el\n            rango natural cubre TODA la cronología. Encuentra la posición\n            donde encaja la serie. Más lento pero necesario — antes el\n            límite fijo de 10 hacía que estas series mostraran todo en 0\n            porque jamás se solapaban con la cronología.\n\n        Fórmula:\n          shift_min = c_min - s_max + min_overlap - 1\n          shift_max = c_max - s_min - min_overlap + 1\n        donde c_* son años de la cronología y s_* son años de la serie.\n        Cualquier shift en ese rango garantiza al menos `min_overlap`\n        años de solape.\n        '
        return comparacion_series.comparar_series_marcadas_vs_crono(self)

    def _clave_cache_comparacion(self, nombres: list[str]) -> tuple:
        'Identifica datos, años, columnas y metadatos de la comparación.'
        return comparacion_series._clave_cache_comparacion(self, nombres)

    def mostrar_tabla_offset(self):
        'Abre el diálogo con la tabla completa de offsets.'
        return comparacion_series.mostrar_tabla_offset(self)

    # -------------------------------------------------------------------------
    # COFECHADO: CORRELACIÓN MÓVIL
    # -------------------------------------------------------------------------

    def verificar_datacion(self):
        """Dibuja curva de correlación móvil y stats por ventana."""
        marcadas = self._series_marcadas()
        if len(marcadas) != 2:
            return QMessageBox.warning(self, "Atención", "Marque EXACTAMENTE dos series.")

        # Limpiar modo offset
        self._shifts_actuales = []
        self._r_actuales = []
        self._glk_actuales = []
        self._tbp_actuales = []
        self._n_actuales = []

        _ref, _prob = self._ordenar_ref_problema(marcadas[0], marcadas[1])
        m_diff, t_diff, n_m, n_t = self._preparar_diferencias_log(_ref, _prob)
        overlap = list(m_diff.index.intersection(t_diff.index))
        if len(overlap) < OVERLAP_MINIMO_ANALISIS:
            return QMessageBox.warning(self, "Error", "Las series no se solapan lo suficiente.")

        mitad = self.spin_ventana.value() // 2

        # Series para GLK/t-BP respetando el modo COFECHA (transformadas si
        # está activo; crudas si no), igual que el resto de los análisis.
        serie_a_raw = self._serie_para_glk(
            self.series_datos[n_m]["Ancho_mm"], es_crono=n_m.startswith("📚"))
        serie_b_raw = self._serie_para_glk(
            self.series_datos[n_t]["Ancho_mm"], es_crono=n_t.startswith("📚"))

        from dpi.ciencia.comparacion_nucleo import verificar_cofecha
        (years, rs, glks, tbps, ns), r_global, stats = verificar_cofecha(
            m_diff, t_diff, overlap, mitad, serie_a_raw, serie_b_raw)

        self._stats_movil_years = years
        self._stats_movil_r = rs
        self._stats_movil_glk = glks
        self._stats_movil_tbp = tbps
        self._stats_movil_n = ns
        self._mitad_ventana_actual = mitad

        self._stats_actuales = stats
        self._nombre_referencia = n_m
        self._nombre_problema = n_t

        self._dibujar_curva_cofechado(years, rs, overlap, r_global, n_t, [], False)

    def buscar_errores(self):
        """Busca anillos faltantes/sobrantes + calcula stats móviles."""
        self._descartar_prueba(silencioso=True)
        marcadas = self._series_marcadas()
        if len(marcadas) != 2:
            return QMessageBox.warning(self, "Atención", "Marque EXACTAMENTE dos series.")

        # Limpiar modo offset
        self._shifts_actuales = []
        self._r_actuales = []
        self._glk_actuales = []
        self._tbp_actuales = []
        self._n_actuales = []

        n1, n2 = marcadas[0], marcadas[1]
        # La CRONOLOGÍA es siempre la referencia: es el patrón contra el que se
        # data, y nunca se le insertan ni quitan anillos. Antes se elegía como
        # referencia la serie más LARGA, así que si la serie a datar era más
        # larga que la cronología (caso habitual con una cronología corta),
        # los papeles se invertían y las correcciones se probaban sobre la
        # cronología. El resultado eran sugerencias con el signo cambiado.
        self._nombre_referencia, self._nombre_problema = \
            self._ordenar_ref_problema(n1, n2)

        df_ref = self.series_datos[self._nombre_referencia]
        df_prob = self.series_datos[self._nombre_problema]
        mitad = self.spin_ventana.value() // 2
        max_c = self.spin_max_corr.value()
        self._mitad_ventana_actual = mitad

        self.grafico_offset.setTitle("Buscando correcciones…")
        QApplication.processEvents()

        self._stats_actuales = estadisticos_cofechado(
            df_ref["Ancho_mm"], df_prob["Ancho_mm"])

        ref_es_crono = self._nombre_referencia.startswith("📚")
        prob_es_crono = self._nombre_problema.startswith("📚")

        def transformar_ref(serie_mm):
            return self._transformar_para_correlacion(serie_mm, ref_es_crono)

        def transformar_prob(serie_mm):
            return self._transformar_para_correlacion(serie_mm, prob_es_crono)

        # DIAGNÓSTICO PREVIO: antes de probar correcciones a ciegas, detectar
        # qué tramo de la serie ya calza con la referencia. Ese tramo es el
        # ancla y define qué extremo debe quedar fijo; además indica si el
        # problema es un error interno o un desfase de toda la serie.
        try:
            self._diagnostico_datacion = diagnosticar_datacion(
                transformar_prob(df_prob["Ancho_mm"]),
                transformar_ref(df_ref["Ancho_mm"]))
        except Exception:
            self._diagnostico_datacion = None

        anclaje_usar = self._anclaje_actual()
        diag = self._diagnostico_datacion
        if diag and diag.get("diagnostico") == "error_interno":
            # Para BUSCAR se ancla el tramo que ya está bien fechado (mover el
            # tramo correcto sería un error), pero NO se toca la selección del
            # usuario: el selector es suyo y cambiarlo solo resulta confuso.
            # Si el anclaje recomendado difiere del elegido, se avisa en el
            # texto del diagnóstico.
            anclaje_usar = diag.get("anclaje_sugerido", anclaje_usar)

        coleccion_std = self._coleccion_para_nulo(transformar_prob)

        self._sugerencias, es_marginal = _buscar_y_priorizar(
            df_ref, df_prob, mitad, max_c,
            diagnostico=self._diagnostico_datacion,
            anclaje=anclaje_usar,
            transformar_ref=transformar_ref,
            transformar_prob=transformar_prob,
            coleccion_std=coleccion_std,
            nombre_serie=self._nombre_problema,
        )
        self._sugerencias_es_marginal = es_marginal
        self._poblar_tabla(self._sugerencias, es_marginal=es_marginal)
        self._mostrar_informe_quiebre(
            self._sugerencias,
            serie=transformar_prob(df_prob["Ancho_mm"]).dropna(),
            referencia=transformar_ref(df_ref["Ancho_mm"]).dropna())

        d_ref = transformar_ref(df_ref["Ancho_mm"])
        d_prob = transformar_prob(df_prob["Ancho_mm"])
        overlap = list(d_ref.index.intersection(d_prob.index))

        serie_a_raw = pd.to_numeric(df_ref["Ancho_mm"], errors="coerce").dropna()
        serie_b_raw = pd.to_numeric(df_prob["Ancho_mm"], errors="coerce").dropna()

        years, rs, glks, tbps, ns = _stats_movil(
            d_ref, d_prob, overlap, mitad, serie_a_raw, serie_b_raw)

        self._stats_movil_years = years
        self._stats_movil_r = rs
        self._stats_movil_glk = glks
        self._stats_movil_tbp = tbps
        self._stats_movil_n = ns

        r_global = (_r_pearson(d_ref.loc[overlap].values, d_prob.loc[overlap].values)
                    if overlap else float("nan"))
        self._dibujar_curva_cofechado(
            years, rs, overlap, r_global, self._nombre_problema,
            self._sugerencias[:10], False)

    def _dibujar_curva_cofechado(self, years, r_vals, overlap, r_global,
                                  nombre_target, marcadores, es_preview):
        """Dibuja la curva base de cofechado."""
        if not es_preview:
            self.grafico_offset.clear()
            self._item_preview = None
            self.grafico_offset.setYRange(-1.05, 1.05)
            if overlap:
                self.grafico_offset.setXRange(min(overlap) - 5, max(overlap) + 5)

            self.grafico_offset.addItem(
                pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#555555", width=1))
            )
            self.grafico_offset.addItem(
                pg.InfiniteLine(pos=UMBRAL_ANCLA_DEFECTO, angle=0,
                                pen=pg.mkPen("#5cb85c", style=Qt.PenStyle.DashLine, width=1))
            )
            self.grafico_offset.addItem(self._texto_hover)
            self._texto_hover.hide()

            if years:
                self.grafico_offset.plot(
                    years, r_vals,
                    pen=pg.mkPen("#3388FF", width=2),
                    name="r móvil actual",
                )

            for m in marcadores:
                color_hex = "#FF4444" if m["delta"] > 0 else "#FFA500"
                y_pos = m.get("r_zona_antes", 0.0)
                if np.isnan(y_pos):
                    y_pos = 0.0
                self.grafico_offset.addItem(
                    pg.ScatterPlotItem(
                        x=[m["anio"]], y=[y_pos], size=14,
                        brush=pg.mkBrush(color_hex),
                        pen=pg.mkPen("#ffffff", width=1),
                    )
                )
                signo = "+" if m["delta"] > 0 else ""
                html = (
                    f"<div style='color:{color_hex}; font-weight:bold; "
                    f"background:rgba(0,0,0,0.8); padding:3px 6px; border-radius:4px;'>"
                    f"{int(m['anio'])}<br>"
                    f"{signo}{m['delta']} anillo(s)<br>"
                    f"Δr = +{m['delta_r']:.3f}</div>"
                )
                txt = pg.TextItem(html=html, anchor=(0.5, 1.2))
                txt.setPos(m["anio"], y_pos)
                self.grafico_offset.addItem(txt)

            n_sug = len(marcadores)
            estado = "Sin sugerencias" if n_sug == 0 else f"{n_sug} sugerencia(s)"
            modo_str = " [COFECHA]" if self.btn_modo_cofecha.isChecked() else ""
            self.grafico_offset.setTitle(
                f"Cofechado{modo_str} '{nombre_target}' | "
                f"r global: {self._fmt_r(r_global)} | {estado}"
            )

            stats = getattr(self, "_stats_actuales", None)
            if stats and np.isfinite(stats.get("r", float("nan"))):
                self.lbl_stats.setText(formato_stats_global_html(stats))
                self.lbl_stats.setVisible(True)
            else:
                self.lbl_stats.setVisible(False)
        else:
            if self._item_preview is not None:
                self.grafico_offset.removeItem(self._item_preview)
            if years:
                self._item_preview = self.grafico_offset.plot(
                    years, r_vals,
                    pen=pg.mkPen("#FFA500", width=2, style=Qt.PenStyle.DashLine),
                    name="r móvil tras corrección",
                )

    def _limpiar_preview(self):
        if self._item_preview is not None:
            try:
                self.grafico_offset.removeItem(self._item_preview)
            except Exception:
                pass
            self._item_preview = None

    def _dibujar_preview(self, sug: dict):
        if not self._nombre_referencia or not self._nombre_problema:
            return
        df_ref = self.series_datos.get(self._nombre_referencia)
        df_corr = sug.get("df_corregido")
        if df_ref is None or df_corr is None:
            return

        ref_es_crono = self._nombre_referencia.startswith("📚")
        prob_es_crono = self._nombre_problema.startswith("📚")

        d_ref = self._transformar_para_correlacion(df_ref["Ancho_mm"], ref_es_crono)
        d_corr = self._transformar_para_correlacion(df_corr["Ancho_mm"], prob_es_crono)

        overlap_corr = list(d_ref.index.intersection(d_corr.index))
        mitad = self.spin_ventana.value() // 2
        years_p, r_p = _r_movil(d_ref, d_corr, overlap_corr, mitad)
        self._dibujar_curva_cofechado(years_p, r_p, overlap_corr, 0, "", [], True)

    # -------------------------------------------------------------------------
    # TABLA DE SUGERENCIAS
    # -------------------------------------------------------------------------

    def _guardar_pref_fuente(self, *_):
        """Recuerda tipo y tamaño de letra entre sesiones."""
        try:
            from PyQt6.QtCore import QSettings
            a = ajustes_ui()
            a.setValue("informe/fuente",
                       self.combo_fuente_informe.currentData())
            a.setValue("informe/tamano", self.spin_fuente_informe.value())
        except Exception:
            pass

    def _restaurar_pref_fuente(self):
        try:
            from PyQt6.QtCore import QSettings
            a = ajustes_ui()
            fam = a.value("informe/fuente", "", type=str)
            tam = a.value("informe/tamano", 0, type=int)
            if fam:
                i = self.combo_fuente_informe.findData(fam)
                if i >= 0:
                    self.combo_fuente_informe.setCurrentIndex(i)
            if tam:
                self.spin_fuente_informe.setValue(tam)
        except Exception:
            pass
        self._aplicar_fuente_informe()

    def _aplicar_fuente_informe(self, *_):
        """Cambia tipo y tamaño de letra del informe."""
        if not hasattr(self, "txt_informe"):
            return
        fam = self.combo_fuente_informe.currentData()
        if fam == "__mono__":
            f = QFont("Consolas" if sys.platform.startswith("win")
                      else "Monospace")
            f.setStyleHint(QFont.StyleHint.TypeWriter)
        else:
            f = QFont(fam)
        f.setPointSize(self.spin_fuente_informe.value())
        self.txt_informe.setFont(f)

    def _coleccion_para_nulo(self, transformar) -> dict:
        """Series fechadas que sirven de nulo para el localizador de quiebres.

        El umbral de credibilidad se MIDE sobre series ya fechadas en vez de
        inventarlo, así que hace falta reunir todas las que haya a mano. Se
        buscan en tres lugares, y se acumulan:

        1. Las cargadas en este panel con «📂 Series».
        2. Las que se usaron para construir la cronología en su pestaña. Es el
           caso más común y el que antes se perdía: quien arma la cronología y
           después cofecha contra ella ya tiene decenas de series fechadas, y
           el panel no las veía.
        3. Las cargadas expresamente como referencia con «📊 Series de
           referencia», para cuando solo se dispone de una cronología ya hecha
           y una serie por cofechar.

        Se excluyen la serie que se evalúa y la referencia, y todo lo que
        parezca una cronología, porque una cronología promediada no es una
        serie individual y su ganancia no es comparable.
        """
        fuera = {self._nombre_problema, self._nombre_referencia}
        crudas: dict = {}

        def _sumar(origen):
            for n, df in (origen or {}).items():
                if n in fuera or n in crudas or str(n).startswith("📚"):
                    continue
                try:
                    col = df["Ancho_mm"] if isinstance(df, pd.DataFrame) else df
                    if len(col.dropna()) > 40:
                        crudas[n] = col
                except Exception:
                    continue

        _sumar(getattr(self, "series_datos", None))
        _sumar(self._obtener_series_cronologia())
        _sumar(getattr(self, "_series_nulo", None))

        out = {}
        for n, col in crudas.items():
            try:
                t = transformar(col).dropna()
                if len(t) > 30:
                    out[n] = t
            except Exception:
                continue
        return out

    def cargar_series_referencia(self):
        """Carga series solo para que sirvan de nulo, sin meterlas en la lista.

        Pensado para el caso de tener una cronología ya construida y una sola
        serie por cofechar: sin otras series fechadas, el localizador cae a un
        nulo sintético que deja pasar bastantes más falsos positivos.
        """
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Cargar series de referencia para el contraste",
            self._ultima_carpeta_nulo(),
            "Series (*.rwl *.txt *.RWL *.TXT);;Todos (*)")
        if not rutas:
            return
        if not hasattr(self, "_series_nulo"):
            self._series_nulo = {}
        n_antes = len(self._series_nulo)
        for r in rutas:
            try:
                d = leer_tucson_multi(r)
                for k, v in d.items():
                    self._series_nulo[k] = v
            except Exception:
                try:
                    df, ide = leer_archivo_tucson(r)
                    self._series_nulo[ide] = df
                except Exception:
                    continue
        try:
            from PyQt6.QtCore import QSettings
            ajustes_ui().setValue(
                "codatacion/carpeta_nulo", os.path.dirname(rutas[0]))
        except Exception:
            pass
        n = len(self._series_nulo)
        QMessageBox.information(
            self, "Series de referencia",
            f"Hay {n} serie(s) de referencia cargadas "
            f"({n - n_antes} nueva(s)).\n\n"
            "No aparecen en la lista ni se cofechan: solo se usan para medir "
            "cuánto gana la búsqueda en series que ya están fechadas, y así "
            "decidir si un quiebre propuesto es real.\n\n"
            "Con nueve o más, el contraste pasa a ser el bueno.")

    def _ultima_carpeta_nulo(self) -> str:
        try:
            from PyQt6.QtCore import QSettings
            r = ajustes_ui().value(
                "codatacion/carpeta_nulo", "", type=str)
            return r if r and os.path.isdir(r) else ""
        except Exception:
            return ""

    def _mostrar_informe_quiebre(self, sugerencias, serie=None,
                                  referencia=None):
        """Vuelca el informe en prosa y el perfil del quiebre a sus pestañas.

        El informe viaja dentro de las sugerencias de origen "zona", pero todo
        ese cálculo vive bajo un `try` amplio en el buscador: si algo falla ahí
        —una serie muy corta, un solape insuficiente— la excepción se traga y
        las pestañas quedaban en blanco sin explicar por qué. Por eso, si no
        llega informe en las sugerencias, se calcula acá directamente con la
        serie y la referencia ya transformadas.
        """
        if not hasattr(self, "txt_informe"):
            return
        base = next((x for x in (sugerencias or [])
                     if x.get("origen") == "zona" and x.get("texto")), None)

        if base is None and serie is not None and referencia is not None:
            try:
                inf = _qb.informe_quiebre(serie, referencia, max_desfase=10,
                                          n_nulo=0)
                if inf.get("texto") and inf.get("zona"):
                    base = {"texto": inf["texto"], "zona": inf["zona"],
                            "tramos": inf.get("tramos"),
                            "perfil": inf.get("perfil")}
            except Exception as e:
                self.txt_informe.setPlainText(
                    "No se pudo generar el informe de co-datación.\n\n"
                    f"Motivo: {e}\n\n"
                    "Suele ocurrir cuando la serie o el solape con la "
                    "referencia son demasiado cortos: hacen falta al menos 15 "
                    "años a cada lado del quiebre.")
                self.grafico_perfil.clear()
                return

        # ── Texto ────────────────────────────────────────────────────
        if base is None:
            self.txt_informe.setPlainText(
                "Todavía no hay informe.\n\n"
                "Se genera al buscar correcciones sobre una serie y una "
                "referencia con solape suficiente (al menos 15 años a cada "
                "lado del posible quiebre).")
            self.grafico_perfil.clear()
            return
        L = ["INFORME DE CO-DATACIÓN", "=" * 60, ""]
        L.append(base["texto"])
        L.append("")
        tramos = base.get("tramos") or []
        if tramos:
            L.append("TRAMOS")
            L.append(f"  {'años':<16}{'n':>5}{'r':>8}{'desfase':>9}   estado")
            for t in tramos:
                r = t.get("r")
                L.append(f"  {t['inicio']}-{t['fin']:<11}{t['n']:>5}"
                         f"{(f'{r:.3f}' if r == r else '   -'):>8}"
                         f"{t['desfase']:>9}   {t['estado']}")
            L.append("")
        z = base.get("zona")
        if z:
            L.append(f"ZONA COMPATIBLE:  {z[0]} a {z[1]}"
                     f"   ({z[1] - z[0] + 1} años)")
            L.append("  La zona reúne los años cuya correlación no se distingue")
            L.append("  de la del óptimo. Contiene el año verdadero casi siempre,")
            L.append("  pero es ancha: por eso abajo van ordenados por prioridad.")
            L.append("")
        cands = [x for x in (sugerencias or []) if x.get("origen") == "zona"]
        if cands:
            L.append("AÑOS A REVISAR, por orden de probabilidad")
            L.append("  El orden usa lo estrecho que es ese año en la cronología:")
            L.append("  un anillo ausente aparece donde el árbol casi no formó leño.")
            L.append("")
            L.append(f"  {'#':>2}  {'año':>6}  {'corrección':<14}{'r resultante':>13}")
            for k, x in enumerate(cands[:10], start=1):
                L.append(f"  {k:>2}  {int(x['anio']):>6}  {x['tipo']:<14}"
                         f"{x.get('r_verificada', float('nan')):>13.3f}")
        self.txt_informe.setPlainText("\n".join(L))

        # ── Perfil ───────────────────────────────────────────────────
        self.grafico_perfil.clear()
        perfil = base.get("perfil") or []
        if not perfil:
            return
        xs = [p[0] - 1 for p in perfil]   # año de la corrección, no del quiebre
        ys = [p[1] for p in perfil]
        self.grafico_perfil.plot(
            xs, ys, pen=pg.mkPen("#4aa3dc", width=2),
            name="r si el quiebre estuviera en ese año")
        leyenda = self.grafico_perfil.addLegend(offset=(10, 10))
        if z:
            reg = pg.LinearRegionItem(values=[z[0], z[1]], movable=False,
                                      brush=(74, 163, 220, 45))
            reg.setZValue(-10)
            self.grafico_perfil.addItem(reg)
            # pyqtgraph no pone las regiones ni las líneas verticales en la
            # leyenda, así que se agregan entradas falsas con el mismo trazo:
            # sin esto el usuario ve tres colores y ningún nombre.
            leyenda.addItem(
                pg.PlotDataItem(pen=None, symbol="s", symbolSize=10,
                                symbolBrush=(74, 163, 220, 120),
                                symbolPen=None),
                f"Zona compatible ({z[0]}–{z[1]})")
        pen_cand = pg.mkPen("#e0a030", width=1, style=Qt.PenStyle.DashLine)
        pen_mejor = pg.mkPen("#e04040", width=2)
        for x in cands[1:5]:
            self.grafico_perfil.addItem(
                pg.InfiniteLine(pos=int(x["anio"]), angle=90, pen=pen_cand))
        if len(cands) > 1:
            leyenda.addItem(pg.PlotDataItem(pen=pen_cand),
                            "Otros años a revisar")
        if cands:
            self.grafico_perfil.addItem(
                pg.InfiniteLine(pos=int(cands[0]["anio"]), angle=90,
                                pen=pen_mejor))
            leyenda.addItem(pg.PlotDataItem(pen=pen_mejor),
                            f"Año más probable ({int(cands[0]['anio'])})")

    def _poblar_tabla(self, sugerencias: list[dict], es_marginal: bool=False):
        'Rellena la tabla de sugerencias.\n\n        es_marginal=True indica que las correcciones están por debajo del umbral\n        de significancia (probable ruido). Se muestran como sanity-check con\n        una advertencia visible.\n        '
        return presentacion_series._poblar_tabla(self, sugerencias, es_marginal)

    def _on_seleccion_sugerencia(self):
        fila = self.tabla_sugerencias.currentRow()
        # Cambiar de sugerencia descarta una prueba en curso (para no mezclar).
        if self.modelo_series.nombre_en_prueba is not None:
            self._descartar_prueba(silencioso=True)
        if fila < 0 or fila >= len(self._sugerencias):
            self.btn_probar.setEnabled(False)
            self.btn_aplicar.setEnabled(False)
            self._limpiar_preview()
            return
        self.btn_probar.setEnabled(True)
        # Aplicar directo también es posible sin probar, pero pedirá confirmación.
        self.btn_aplicar.setEnabled(True)
        self._dibujar_preview(self._sugerencias[fila])

    def _texto_cambio_sugerencia(self, sug, nombre):
        """Arma la descripción de QUÉ datos se modifican con una sugerencia."""
        anio = int(sug["anio"])
        delta = int(sug["delta"])
        df_act = self.series_datos.get(nombre)
        df_corr = sug.get("df_corregido")
        n0 = len(df_act) if df_act is not None else 0
        n1 = len(df_corr) if df_corr is not None else n0
        if delta > 0:
            accion = f"insertar {delta} anillo(s)"
        else:
            accion = f"eliminar {abs(delta)} anillo(s)"
        rango = ""
        if df_corr is not None and not df_corr.empty:
            rango = (f"<br>Rango resultante: <b>{int(df_corr.index.min())}–"
                     f"{int(df_corr.index.max())}</b>")
        return (
            f"Serie: <b>{nombre.replace('📚 ', '')}</b><br>"
            f"Acción: <b>{accion}</b> en el año <b>{anio}</b><br>"
            f"Anillos: <b>{n0} → {n1}</b>{rango}<br>"
            f"<span style='color:{color_secundario()};'>Los años ≤ {anio} no cambian "
            f"(médula fija).</span><br>"
            f"Correlación r: {self._fmt_r(sug['r_antes'])} → "
            f"{self._fmt_r(sug['r_tras'])} "
            f"(Δr +{sug['delta_r']:.3f})")

    def probar_correccion_seleccionada(self):
        'Aplica la corrección seleccionada de forma TEMPORAL (con respaldo)\n        para ver cómo queda la serie corregida, sin tocar la serie real ni\n        re-buscar (para no reiniciar la tabla).'
        return correcciones_series.probar_correccion_seleccionada(self)

    def _marcar_prueba_ui(self, activa: bool):
        return correcciones_series._marcar_prueba_ui(self, activa)

    def _descartar_prueba(self, silencioso: bool=False):
        'Recupera la serie anterior a la prueba, no la original importada.'
        return correcciones_series._descartar_prueba(self, silencioso)

    def aplicar_correccion_seleccionada(self):
        'Aplica la corrección a la serie REAL, tras confirmar exactamente\n        qué datos se modifican. Ofrece hacerlo conservando el ancho (editor)\n        o de forma automática (ancho promedio).'
        return correcciones_series.aplicar_correccion_seleccionada(self)

    # -------------------------------------------------------------------------
    # HOVER EN GRÁFICO
    # -------------------------------------------------------------------------

    def _on_mouse_movido(self, evt):
        """Hover sobre el gráfico de cofechado/offset."""
        if not self.grafico_offset.sceneBoundingRect().contains(evt):
            self._texto_hover.hide()
            self._restaurar_stats_globales()
            return

        punto = self.grafico_offset.plotItem.vb.mapSceneToView(evt)
        x_val = punto.x()

        # Modo curva de cofechado
        if self._stats_movil_years:
            years_arr = np.array(self._stats_movil_years)
            idx = int(np.argmin(np.abs(years_arr - x_val)))
            if abs(years_arr[idx] - x_val) > 5:
                self._restaurar_stats_globales()
                self._texto_hover.hide()
                return

            mitad = self._mitad_ventana_actual
            self.lbl_stats.setText(formato_stats_hover_html(
                int(self._stats_movil_years[idx]), mitad,
                self._stats_movil_r[idx],
                self._stats_movil_glk[idx],
                self._stats_movil_tbp[idx],
                self._stats_movil_n[idx],
            ))
            self.lbl_stats.setVisible(True)
            self._texto_hover.hide()
            return

        # Modo barras de offset
        if self._shifts_actuales:
            xi = int(round(x_val))
            if xi in self._shifts_actuales:
                idx = self._shifts_actuales.index(xi)
                r = self._r_actuales[idx]
                glk = self._glk_actuales[idx] if idx < len(self._glk_actuales) else float("nan")
                t_bp = self._tbp_actuales[idx] if idx < len(self._tbp_actuales) else float("nan")
                n = self._n_actuales[idx] if idx < len(self._n_actuales) else 0
                sc = score_compuesto(r, glk, t_bp)

                def _f(v, dec=2):
                    return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

                html = (
                    f"<div style='background:rgba(40,40,40,230); padding:6px 10px; "
                    f"border-radius:4px; font-family:monospace; font-size:11px;'>"
                    f"<b style='color:#fff;'>Mover {xi:+d} años</b><br>"
                    f"<span style='color:#aaa;'>Puntaje:</span> "
                    f"<span style='color:{_color_compuesto(sc)}; font-weight:bold;'>{_f(sc, 2)}</span><br>"
                    f"<span style='color:#aaa;'>r:</span> "
                    f"<span style='color:{_color_r(r)}; font-weight:bold;'>{_f(r, 2)}</span><br>"
                    f"<span style='color:#aaa;'>GLK:</span> "
                    f"<span style='color:{_color_glk(glk)}; font-weight:bold;'>{_f(glk, 2)}</span><br>"
                    f"<span style='color:#aaa;'>t-BP:</span> "
                    f"<span style='color:{_color_tbp(t_bp)}; font-weight:bold;'>{_f(t_bp, 1)}</span><br>"
                    f"<span style='color:#aaa;'>n:</span> <span style='color:#ddd;'>{n}</span>"
                    f"</div>"
                )
                self._texto_hover.setHtml(html)
                self._texto_hover.setPos(punto.x(), punto.y())
                self._texto_hover.show()
            else:
                self._texto_hover.hide()
            return

        self._texto_hover.hide()

    def _restaurar_stats_globales(self):
        stats = getattr(self, "_stats_actuales", None)
        if stats and np.isfinite(stats.get("r", float("nan"))) and self._stats_movil_years:
            self.lbl_stats.setText(formato_stats_global_html(stats))
            self.lbl_stats.setVisible(True)
