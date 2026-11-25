"""Control de herramientas de medición con dependencias explícitas."""
from dataclasses import dataclass
from collections.abc import Callable
import os
import logging
from dpi.ui.configuracion import ultima_carpeta
import math
import cv2
from dpi.medicion.modelo import PuntoMedicion, TipoMarca
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtWidgets import QFileDialog, QVBoxLayout, QMessageBox, QDialog
from PyQt6.QtCore import Qt
import estilos_graficos as _gr
from modulo_intensidad import DialogoConfigBI, DialogoGuardarBI
from dpi.medicion.intensidad import extraer_intensidad_por_anillo
from dpi.medicion.intensidad import valores_intensidad
from modulo_pith import estimar_anillos_faltantes, DialogoMetodoPith, DialogoEstimacionPith
from dpi.medicion.pith import distancia_faltante_dap
logger = logging.getLogger(__name__)
from dpi.medicion.marcas import ModoMedicion, _es_ewlw
from dpi.medicion.ewlw import detectar_ewlw_imagen
from dpi.ui.medicion.tareas import GestorTareasMedicion
def _ultima_carpeta(nueva_ruta: str | None = None) -> str:
    return ultima_carpeta("ultima_carpeta", nueva_ruta)


from modulo_banda_intensidad_ui import BandaIntensidad


@dataclass(frozen=True)
class ContextoRadio:
    parent: object
    vista: object
    obtener_mediciones: Callable
    label_estado: object
    combo_dir: object

    @property
    def datos_medidos(self):
        return self.obtener_mediciones()


@dataclass(frozen=True)
class ContextoImagen:
    imagen: Callable
    ruta: Callable
    tareas: GestorTareasMedicion


class ControlPith:
    """Estimación y persistencia de la médula."""
    def __init__(self, radio, *, serie_maestra, set_modo, guardar_estado, guardar_sidecar,
                 spin_medula, spin_corteza, check_tiene_medula, btn_pith, btn_deshacer_pith):
        self.radio = radio
        self._obtener_maestra = serie_maestra
        self.set_modo = set_modo
        self._guardar_estado = guardar_estado
        self._guardar_sidecar_anom = guardar_sidecar
        self.spin_medula = spin_medula
        self.spin_corteza = spin_corteza
        self.check_tiene_medula = check_tiene_medula
        self.btn_pith = btn_pith
        self.btn_deshacer_pith = btn_deshacer_pith
        self._pith_estimacion = None
        self._pith_undo = None
        self._pith_metodo = "arco"
        self._pith_n_int = 5
        self._pith_usar_ref = False
        self._pith_dap_mm = 200.0
        self._pith_metodo_calculo = "rg"

    @property
    def configuracion_pith(self):
        return self._pith_n_int, self._pith_metodo_calculo


    @property
    def estimacion(self):
        return dict(self._pith_estimacion) if self._pith_estimacion else None


    def restaurar_estimacion(self, datos):
        if not datos.get("pith_estimated"):
            return
        self._pith_estimacion = {k: v for k, v in datos.items() if k.startswith("pith_")}
        offset = datos.get("pith_offset", 0)
        if offset > 0:
            med_a_cor = self.radio.combo_dir.currentIndex() == 0
            self._pith_undo = {
                "med_a_cor": med_a_cor,
                "anio_medula_old": self.spin_medula.value() + (offset if med_a_cor else 0),
                "anio_corteza_old": self.spin_corteza.value() - (offset if not med_a_cor else 0),
                "medula_checked": False,
                "n_anillos": offset,
            }
            self.btn_deshacer_pith.show()


    def iniciar_estimacion_pith(self):
        """Abre el diálogo de configuración y activa el modo PITH."""
        # Limpieza defensiva: si por algún motivo quedaron items del modo
        # pith de una sesión anterior (incompleta, mal cancelada, etc.),
        # los borramos antes de empezar. Sin esto, los círculos/líneas/
        # texto naranjas anteriores se solapaban con los nuevos.
        if hasattr(self.radio.vista, "limpiar_pith"):
            self.radio.vista.limpiar_pith()

        n_disponibles = len(self.radio.datos_medidos)
        if n_disponibles < 3:
            QMessageBox.warning(self.radio.parent, "Pocos anillos",
                "Necesitas al menos 3 anillos medidos para usar esta función.")
            self.btn_pith.setChecked(False)
            return

        tiene_ref = (self._obtener_maestra() is not None
                     and not self._obtener_maestra().empty)

        dlg = DialogoMetodoPith(
            tiene_referencia=tiene_ref,
            n_anillos_disponibles=n_disponibles,
            parent=self.radio.parent,
        )
        if dlg.exec() != DialogoMetodoPith.DialogCode.Accepted:
            self.btn_pith.setChecked(False)
            return

        self._pith_metodo    = dlg.metodo
        self._pith_n_int     = dlg.n_internos
        self._pith_usar_ref  = dlg.usar_referencia
        self._pith_dap_mm    = dlg.dap_mm
        self._pith_metodo_calculo = dlg.metodo_calculo  # 'rg', 'bai', 'promedio'

        if self._pith_metodo == "arco":
            self.set_modo(ModoMedicion.PITH)
            self.radio.label_estado.setText(
                "🎯 Paso 1/3: Haz clic en un EXTREMO del arco del anillo más interno."
            )
        else:
            # DAP: no necesita marcado en imagen, calcular directamente
            self.btn_pith.setChecked(False)
            self._calcular_pith_por_dap()


    def _calcular_pith_por_dap(self):
        """Calcula la distancia faltante usando el DAP ingresado."""
        radio_mm    = self._pith_dap_mm / 2.0
        radio_px    = radio_mm * self.radio.vista.pixeles_por_mm

        # Longitud del radio medido: distancia desde el primer punto hasta el último
        if len(self.radio.vista.coordenadas_anillos) < 2:
            QMessageBox.warning(self.radio.parent, "Sin camino",
                "Necesitas tener puntos medidos en el camino activo.")
            return

        coords = self.radio.vista.coordenadas_anillos
        distancia_faltante_px = distancia_faltante_dap(coords, self.radio.vista.es_salto, radio_px)

        if distancia_faltante_px <= 0:
            QMessageBox.information(self.radio.parent, "Sin anillos faltantes",
                "La longitud medida ya cubre o supera el radio estimado por DAP.")
            return

        # Centro estimado: extrapolando desde el primer punto
        cx = coords[0][0]
        cy = coords[0][1]

        self._mostrar_dialogo_resultados_pith(
            cx, cy, radio_px, distancia_faltante_px, metodo="dap"
        )


    def confirmar_estimacion_pith(self):
        """Confirma la estimación de pith por método arco.

        Llamado desde VistaInteractiva al presionar Enter en MODO_PITH.

        Algoritmo:
          1. La médula está en el centro del círculo ajustado (Duncan GM,
             1989): r = L²/(8h) + h/2 = radio del círculo por mínimos
             cuadrados a través de los puntos marcados.
          2. La distancia faltante es `dist(p_inner, centro)`: desde el
             primer anillo medido más cercano a la médula hasta el centro
             estimado. Esta es la métrica relevante INDEPENDIENTEMENTE
             de qué anillo marque el usuario — el arco marcado es solo
             la herramienta para localizar la médula.
          3. Los anillos faltantes se calculan en el diálogo de resultados
             usando RG (Altman 2016): anillos = distancia / promedio_ancho,
             donde el promedio viene de N anillos junto al arco marcado
             contando hacia la corteza.
        """
        resultado = self.radio.vista.confirmar_pith()
        self.set_modo(ModoMedicion.MEDIR)
        self.btn_pith.setChecked(False)

        if resultado is None:
            return

        cx, cy, radio_px = resultado
        coords = self.radio.vista.coordenadas_anillos

        if radio_px <= 0 or not coords:
            QMessageBox.warning(self.radio.parent, "Estimación inválida",
                "El círculo ajustado tiene radio 0. Verifica los puntos marcados.")
            return

        # p_inner según dirección de medición
        try:
            med_a_cor = self.radio.combo_dir.currentIndex() == 0
        except Exception:
            med_a_cor = True

        if med_a_cor:
            p_inner = coords[0]
        else:
            p_inner = coords[-1] if len(coords) >= 2 else coords[0]

        # Distancia faltante = dist(p_inner, centro). NO usar radio.
        distancia_faltante_px = math.hypot(cx - p_inner[0], cy - p_inner[1])

        if distancia_faltante_px <= 0:
            QMessageBox.warning(self.radio.parent, "Estimación inválida",
                "El primer anillo medido coincide con la médula estimada.\n"
                "No hay anillos faltantes para estimar.")
            return

        self._mostrar_dialogo_resultados_pith(
            cx, cy, radio_px, distancia_faltante_px, metodo="arco"
        )


    def _mostrar_dialogo_resultados_pith(
        self,
        cx: float, cy: float,
        radio_px: float,
        distancia_faltante_px: float,
        metodo: str,
    ):
        """Calcula los resultados y muestra el diálogo de confirmación."""
        import math as _math

        n_int = getattr(self, '_pith_n_int', 5)
        usar_ref = getattr(self, '_pith_usar_ref', False)

        # Obtener los N anillos más internos (los primeros en la lista)
        # datos_medidos está ordenado médula→corteza
        med_a_cor = self.radio.combo_dir.currentIndex() == 0
        dm = self.radio.datos_medidos
        if med_a_cor:
            # Los más internos son los del inicio
            anchos_internos = [d["ancho_mm"] for d in dm[:n_int]]
            anio_inicio = dm[0]["anio"] if dm else None
        else:
            # Los más internos son los del final
            anchos_internos = [d["ancho_mm"] for d in dm[-n_int:]]
            anio_inicio = dm[-1]["anio"] if dm else None

        anchos_internos = [a for a in anchos_internos if a > 0]

        # Serie de referencia si está disponible y seleccionada
        serie_ref = None
        if usar_ref and self._obtener_maestra() is not None and not self._obtener_maestra().empty:
            col = ("Ancho_mm" if "Ancho_mm" in self._obtener_maestra().columns
                   else self._obtener_maestra().columns[0])
            serie_ref = self._obtener_maestra()[col].dropna()

        resultados = estimar_anillos_faltantes(
            distancia_faltante_mm=distancia_faltante_px / self.radio.vista.pixeles_por_mm,
            anchos_internos_mm=anchos_internos,
            serie_ref=serie_ref,
            anio_inicio_serie=anio_inicio,
        )

        if not resultados:
            QMessageBox.warning(self.radio.parent, "Sin resultados",
                "No se pudo calcular la estimación. Verifica los datos.")
            return

        tiene_ref = (serie_ref is not None)
        dlg = DialogoEstimacionPith(
            resultados=resultados,
            radio_px=radio_px,
            distancia_faltante_px=distancia_faltante_px,
            pixeles_por_mm=self.radio.vista.pixeles_por_mm,
            n_anillos_internos=len(anchos_internos),
            tiene_referencia=tiene_ref,
            parent=self.radio.parent,
        )
        dlg.poblar_grafico(anchos_internos)
        dlg.aplicar_offset.connect(
            lambda n: self._aplicar_pith_offset(n, dlg.marcar_estimada, resultados, metodo,
                                                 radio_px / self.radio.vista.pixeles_por_mm,
                                                 distancia_faltante_px / self.radio.vista.pixeles_por_mm)
        )
        dlg.exec()


    def _aplicar_pith_offset(
        self,
        n_anillos: int,
        marcar_estimada: bool,
        resultados: dict,
        metodo: str,
        radio_mm: float,
        distancia_faltante_mm: float,
    ):
        """
        Aplica el offset: retrocede el año de médula en n_anillos.
        Actualiza el sidecar con la información de la estimación.
        """
        if n_anillos <= 0:
            return

        # Guardar estado previo para poder deshacer
        med_a_cor = self.radio.combo_dir.currentIndex() == 0
        self._pith_undo = {
            "med_a_cor":        med_a_cor,
            "anio_medula_old":  self.spin_medula.value(),
            "anio_corteza_old": self.spin_corteza.value(),
            "medula_checked":   self.check_tiene_medula.isChecked(),
            "n_anillos":        n_anillos,
        }

        if med_a_cor:
            nuevo_anio_medula = self.spin_medula.value() - n_anillos
            self.spin_medula.setValue(nuevo_anio_medula)
        else:
            nuevo_anio_corteza = self.spin_corteza.value() + n_anillos
            self.spin_corteza.setValue(nuevo_anio_corteza)

        if marcar_estimada:
            self.check_tiene_medula.setChecked(True)

        # Guardar en el sidecar
        self._pith_estimacion = {
            "pith_estimated":       True,
            "pith_offset":          n_anillos,
            "pith_method":          metodo,
            "pith_radio_mm":        round(radio_mm, 2),
            "pith_distancia_mm":    round(distancia_faltante_mm, 2),
            "pith_n_media":         resultados.get("n_media"),
            "pith_n_tendencia":     resultados.get("n_tendencia"),
            "pith_n_referencia":    resultados.get("n_referencia"),
            "pith_ancho_medio":     resultados.get("ancho_medio"),
            "pith_rango_min":       resultados.get("incertidumbre_min"),
            "pith_rango_max":       resultados.get("incertidumbre_max"),
        }
        self._guardar_sidecar_anom()
        self._guardar_estado()

        dist = distancia_faltante_mm
        self.radio.label_estado.setText(
            f"✅ Estimación aplicada: {n_anillos} anillos faltantes al centro · "
            f"distancia {dist:.1f} mm · año médula → {self.spin_medula.value()}"
        )
        self.btn_deshacer_pith.show()


    def deshacer_pith_offset(self):
        """Revierte la última estimación de médula aplicada."""
        undo = getattr(self, "_pith_undo", None)
        if not undo:
            QMessageBox.information(self.radio.parent, "Nada que deshacer",
                "No hay estimación para revertir.")
            return

        resp = QMessageBox.question(
            self.radio.parent, "Deshacer estimación",
            f"¿Revertir la estimación de {undo['n_anillos']} anillos faltantes?\n"
            f"El año de médula volverá a su valor anterior.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # Restaurar años
        self.spin_medula.setValue(undo["anio_medula_old"])
        self.spin_corteza.setValue(undo["anio_corteza_old"])
        self.check_tiene_medula.setChecked(undo["medula_checked"])

        # Limpiar estimación
        self._pith_estimacion = None
        self._pith_undo = None
        self.btn_deshacer_pith.hide()

        self._guardar_sidecar_anom()
        self._guardar_estado()
        self.radio.vista.recalcular_todas_las_distancias()

        self.radio.label_estado.setText(
            f"↩ Estimación revertida · "
            f"año médula → {self.spin_medula.value()}"
        )


class ControlEWLW:
    """Detección, edición y exportación EW/LW."""
    def __init__(self, radio, imagen, obtener_banda):
        self.radio = radio
        self.imagen = imagen
        self._obtener_banda = obtener_banda

    def eliminar_ewlw(self):
        """Elimina todos los límites EW/LW del radio activo tras confirmación."""
        n_ewlw = sum(1 for v in self.radio.vista.es_salto if _es_ewlw(v))
        if n_ewlw == 0:
            QMessageBox.information(self.radio.parent, "Sin límites EW/LW",
                "No hay límites EW/LW en el radio activo.")
            return
        resp = QMessageBox.question(
            self.radio.parent, "Eliminar límites EW/LW",
            f"¿Eliminar los {n_ewlw} límite(s) EW/LW del radio activo?\n"
            "Esta acción se puede deshacer con Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        self.radio.vista.guardar_en_historial()
        # Eliminar de atrás hacia adelante para no invalidar índices
        indices = [i for i, v in enumerate(self.radio.vista.es_salto) if _es_ewlw(v)]
        for i in reversed(indices):
            self.radio.vista.modelo_medicion.borrar(i)
        self.radio.vista.recalcular_todas_las_distancias()
        self.radio.vista.progreso_modificado.emit()
        self.radio.label_estado.setText(
            f"🗑 {n_ewlw} límite(s) EW/LW eliminados. Ctrl+Z para deshacer.")


    def detectar_ewlw_automatico(self):
        """Detecta límites en segundo plano y aplica una sola edición validada."""
        if self.imagen.tareas.en_curso:
            QMessageBox.information(self.radio.parent, "Tarea en curso", "Hay una tarea de medición activa.")
            return
        coords = list(self.radio.vista.coordenadas_anillos)
        saltos = list(self.radio.vista.es_salto)
        if len(coords) < 2:
            QMessageBox.information(self.radio.parent, "Sin anillos", "Marca al menos un anillo.")
            return
        banda, ruta = self._obtener_banda(), self.imagen.ruta()
        imagen = self.imagen.imagen()
        direccion = self.radio.combo_dir.currentIndex()

        def tarea(progreso, cancelado):
            return detectar_ewlw_imagen(progreso, imagen, coords, saltos, banda,
                                         ruta, cancelado, direccion == 0)

        def aplicar(inserciones):
            if (self.imagen.ruta() != ruta or self.radio.combo_dir.currentIndex() != direccion
                    or list(self.radio.vista.coordenadas_anillos) != coords
                    or list(self.radio.vista.es_salto) != saltos):
                self.radio.label_estado.setText("Resultados EW/LW descartados: cambió el radio.")
                return
            if not inserciones:
                self.radio.label_estado.setText("🍂 No se encontraron límites EW/LW.")
                return
            puntos = list(self.radio.vista.modelo_medicion.captura())
            for indice, x, y in sorted(inserciones, reverse=True):
                if not 1 <= indice < len(coords):
                    raise ValueError("Índice de inserción EW/LW inválido")
                puntos.insert(indice, PuntoMedicion((x, y), TipoMarca.EW_LW))
            self.radio.vista.guardar_en_historial()
            self.radio.vista.modelo_medicion.restaurar(puntos)
            self.radio.vista.recalcular_todas_las_distancias()
            self.radio.vista.progreso_modificado.emit()
            self.radio.label_estado.setText(f"🍂 EW/LW automático: {len(inserciones)} límites insertados.")

        self.imagen.tareas.iniciar("Detectando límites EW/LW", tarea, aplicar,
            lambda error: QMessageBox.critical(self.radio.parent, "Error EW/LW", error),
            lambda: self.radio.label_estado.setText("Detección EW/LW cancelada — sin cambios."))


class ControlIntensidad:
    """Configuración, muestreo y resultados de intensidad."""
    def __init__(self, radio, imagen, *, btn_mostrar_banda, btn_graficar_bi,
                 btn_guardar_bi, input_codigo):
        self.radio = radio
        self.imagen = imagen
        self.btn_mostrar_banda = btn_mostrar_banda
        self.btn_graficar_bi = btn_graficar_bi
        self.btn_guardar_bi = btn_guardar_bi
        self.input_codigo = input_codigo
        self._bi_datos = []
        self._bi_firma = None
        self._bi_banda = 30
        self._bi_porcentaje = 100
        self._bi_alineacion = "centro"
        self._bi_canal_vis = "B"
        self._bi_canales = ["B", "G", "R", "Gray"]
        self._banda_intensidad = BandaIntensidad()

    def _firma_radio(self):
        return (self.imagen.ruta(), self.radio.vista.modelo_medicion.captura(),
                self.radio.vista.pixeles_por_mm, self.radio.combo_dir.currentIndex(),
                tuple(d["anio"] for d in self.radio.datos_medidos),
                self._bi_banda, tuple(self._bi_canales), self._bi_porcentaje, self._bi_alineacion)

    def invalidar_si_cambio(self):
        if self._bi_firma is not None and self._bi_firma != self._firma_radio():
            self._bi_datos = []
            self._bi_firma = None
            self.btn_guardar_bi.setEnabled(False)
            self.btn_graficar_bi.setEnabled(False)

    @property
    def banda(self):
        return self._bi_banda

    def configurar_bi(self):
        """Abre el diálogo de configuración de la extracción de intensidad."""
        dlg = DialogoConfigBI(
            banda_actual=self._bi_banda,
            canales_activos=self._bi_canales,
            porcentaje=self._bi_porcentaje,
            alineacion=self._bi_alineacion,
            canal_vis=self._bi_canal_vis,
            parent=self.radio.parent,
        )
        if dlg.exec():
            self._bi_banda       = dlg.banda
            self._bi_canales     = dlg.canales
            self._bi_porcentaje  = dlg.porcentaje
            self._bi_alineacion  = dlg.alineacion
            self._bi_canal_vis   = dlg.canal_vis
            self.invalidar_si_cambio()
            # Redibujar banda si está activa
            if self.btn_mostrar_banda.isChecked():
                self._dibujar_banda_bi()


    def calcular_bi(self):
        """Calcula BI/GI/RI en hilo separado con barra de progreso."""
        if not self.radio.datos_medidos:
            QMessageBox.information(self.radio.parent, "Sin mediciones",
                "Mide al menos un anillo antes de calcular la intensidad.")
            return

        # Protección contra doble lanzamiento (mismo problema que en EW/LW:
        # múltiples workers concurrentes con copias de la imagen llevan a OOM
        # y posible crash del sistema).
        if self.imagen.tareas.en_curso:
            QMessageBox.information(
                self.radio.parent, "Cálculo en curso",
                "Ya se está ejecutando un cálculo de intensidad.\n"
                "Espera a que termine.")
            return

        # Asegurar que haya canales activos (si el usuario no configuró, usar todos)
        if not self._bi_canales:
            self._bi_canales = ["B", "G", "R", "Gray"]

        ruta = self.imagen.ruta()
        if not ruta:
            QMessageBox.warning(self.radio.parent, "Sin imagen",
                "No hay imagen cargada para extraer la intensidad.")
            return

        # Usar imagen cacheada si está disponible — evita re-leer del disco
        img_bgr = self.imagen.imagen()
        if img_bgr is None:
            img_bgr = cv2.imread(ruta, cv2.IMREAD_COLOR)
            if img_bgr is None:
                QMessageBox.critical(self.radio.parent, "Error",
                    "No se pudo leer la imagen para extraer la intensidad.")
                return

        # Capturar estado en este momento (el worker corre en otro hilo)
        coords   = list(self.radio.vista.coordenadas_anillos)
        saltos   = list(self.radio.vista.es_salto)
        ppm      = self.radio.vista.pixeles_por_mm
        banda    = self._bi_banda
        canales  = list(self._bi_canales)
        anios_capturados = [d["anio"] for d in self.radio.datos_medidos]

        pct_calculo  = self._bi_porcentaje / 100.0
        alin_calculo = self._bi_alineacion
        med_a_cor = self.radio.combo_dir.currentIndex() == 0
        firma = self._firma_radio()

        def _tarea(progreso, cancelado):
            return extraer_intensidad_por_anillo(
                signal_progreso=progreso, imagen_bgr=img_bgr,
                coordenadas=coords, es_salto=saltos, pixeles_por_mm=ppm,
                banda_px=banda, canales=canales, porcentaje=pct_calculo,
                alineacion=alin_calculo, med_a_cor=med_a_cor, cancelado=cancelado)

        def _on_resultado(resultados):
            if (self._firma_radio() != firma or self.imagen.ruta() != ruta
                    or list(self.radio.vista.coordenadas_anillos) != coords
                    or list(self.radio.vista.es_salto) != saltos
                    or self.radio.vista.pixeles_por_mm != ppm
                    or (self.radio.combo_dir.currentIndex() == 0) != med_a_cor
                    or [d["anio"] for d in self.radio.datos_medidos] != anios_capturados):
                self.radio.label_estado.setText("Resultados BI descartados: cambió el radio.")
                return
            for resultado in resultados:
                resultado["anio"] = anios_capturados[resultado["indice_anillo"]]
            self._bi_datos = resultados
            self._bi_firma = firma
            self.btn_guardar_bi.setEnabled(bool(resultados))
            self.btn_graficar_bi.setEnabled(bool(resultados))
            self.radio.label_estado.setText(
                f"🎨 {len(resultados)} anillos · banda {banda}px · "
                f"canales: {', '.join(canales)}")

        self.imagen.tareas.iniciar("Calculando intensidad de color", _tarea, _on_resultado,
            lambda error: QMessageBox.critical(self.radio.parent, "Error al calcular BI", error),
            lambda: self.radio.label_estado.setText("Cálculo BI cancelado — sin cambios."))


    def toggle_banda_bi(self, activo: bool):
        """Muestra u oculta la banda de muestreo BI sobre la imagen."""
        if activo:
            self._dibujar_banda_bi()
        else:
            self._limpiar_banda_bi()


    def _dibujar_banda_bi(self):
        self._banda_intensidad.limpiar()
        ruta = self.imagen.ruta()
        if not ruta:
            return
        img = cv2.imread(ruta, cv2.IMREAD_COLOR)
        self._banda_intensidad.dibujar(self.radio.vista.scene(), img,
            self.radio.vista.coordenadas_anillos, self.radio.vista.es_salto,
            self._bi_canal_vis, self._bi_banda, self._bi_porcentaje / 100.0,
            self._bi_alineacion, med_a_cor=self.radio.combo_dir.currentIndex() == 0)


    def _limpiar_banda_bi(self):
        self._banda_intensidad.limpiar()


    def graficar_bi_ventana(self):
        """Abre una ventana independiente con el gráfico de BI/GI/RI con zoom."""
        self.invalidar_si_cambio()
        if not self._bi_datos:
            return

        anios = [d.get("anio", i) for i, d in enumerate(self._bi_datos)]
        colores = {"B": "#4488FF", "G": "#44BB44", "R": "#FF4444", "Gray": "#AAAAAA"}
        estilos = {
            "mean": (Qt.PenStyle.SolidLine,  "Promedio"),
            "min":  (Qt.PenStyle.DashLine,   "Mínimo"),
            "max":  (Qt.PenStyle.DotLine,    "Máximo"),
        }

        win = QDialog(self.radio.parent)
        win.setWindowTitle("Intensidad de color — BI/GI/RI/GrayI")
        win.resize(900, 450)
        lay = QVBoxLayout(win)

        pw = pg.PlotWidget()
        _gr.aplicar_a_pyqtgraph(pw)
        pw.showGrid(x=True, y=True, alpha=0.3)
        pw.setLabel("bottom", "Año")
        pw.setLabel("left",   "Intensidad (0-255)")
        pw.setYRange(0, 255, padding=0.05)
        pw.addLegend(offset=(10, 10))
        pw.setMouseEnabled(x=True, y=True)
        lay.addWidget(pw)

        from PyQt6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout as QHL
        chks_canal: dict[str, QCheckBox] = {}
        chks_met:   dict[str, QCheckBox] = {}

        def _reconstruir():
            pw.clear()
            pw.addLegend(offset=(10, 10))
            for canal, chk_c in chks_canal.items():
                if not chk_c.isChecked():
                    continue
                color = colores.get(canal, "#888888")
                for met, (estilo, etiq) in estilos.items():
                    if not chks_met[met].isChecked():
                        continue
                    key = f"{canal}_{met}"
                    vals = [d.get(key) for d in self._bi_datos if key in d]
                    if not vals or len(vals) != len(anios):
                        continue
                    pw.plot(anios, vals,
                            pen=pg.mkPen(color,
                                         width=2.0 if met == "mean" else 1.0,
                                         style=estilo),
                            name=f"{canal} {etiq}")

        fila = QHL()
        grp_c = QGroupBox("Canales")
        lay_c = QHL(grp_c)
        for canal in ["B", "G", "R", "Gray"]:
            chk = QCheckBox(canal)
            chk.setChecked(canal in self._bi_canales)
            chk.toggled.connect(_reconstruir)
            lay_c.addWidget(chk)
            chks_canal[canal] = chk
        fila.addWidget(grp_c)

        grp_m = QGroupBox("Métricas")
        lay_m = QHL(grp_m)
        for met, etiq in [("mean","Promedio"), ("min","Mínimo"), ("max","Máximo")]:
            chk = QCheckBox(etiq)
            chk.setChecked(True)
            chk.toggled.connect(_reconstruir)
            lay_m.addWidget(chk)
            chks_met[met] = chk
        fila.addWidget(grp_m)
        fila.addStretch()
        lay.addLayout(fila)

        _reconstruir()
        win.show()
        self._bi_ventana = win   # evitar GC


    def guardar_bi(self):
        """
        Abre el diálogo de selección de métricas y guarda en el formato
        elegido por la extensión del archivo:
          • .rwl       → un archivo Tucson por canal×métrica
          • .xlsx      → un Excel multi-columna con todas las series
          • .csv/.txt  → un texto multi-columna con coma decimal
        """
        self.invalidar_si_cambio()
        if not self._bi_datos:
            QMessageBox.information(self.radio.parent, "Sin datos",
                "Primero calcula la intensidad con el botón 🎨 Calcular BI.")
            return

        # 1. Diálogo de selección de canales y métricas
        dlg = DialogoGuardarBI(
            canales_calculados=self._bi_canales,
            parent=self.radio.parent,
        )
        if dlg.exec() != DialogoGuardarBI.DialogCode.Accepted:
            return

        seleccion = dlg.seleccion
        if not seleccion:
            QMessageBox.information(self.radio.parent, "Sin selección",
                "No se seleccionó ningún canal/métrica para exportar.")
            return

        # 2. Selector de archivo con formato
        codigo = self.input_codigo.text().strip() or "serie"
        ruta_default = os.path.join(_ultima_carpeta(), f"{codigo}_bi.txt")

        ruta, filtro = QFileDialog.getSaveFileName(
            self.radio.parent, "Guardar intensidad de color",
            ruta_default,
            "Texto multi-columna (*.txt);;"
            "CSV multi-columna (*.csv);;"
            "Excel multi-columna (*.xlsx);;"
            "Tucson — un archivo por canal (*.rwl)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return

        _ultima_carpeta(ruta)
        ext = os.path.splitext(ruta)[1].lower()
        if not ext:
            # Si no escribieron extensión, deducir del filtro
            if "rwl" in filtro:
                ruta += ".rwl"
                ext = ".rwl"
            elif "csv" in filtro:
                ruta += ".csv"
                ext = ".csv"
            elif "xlsx" in filtro:
                ruta += ".xlsx"
                ext = ".xlsx"
            else:
                ruta += ".txt"
                ext = ".txt"

        anios = [d.get("anio", i) for i, d in enumerate(self._bi_datos)]
        if not anios:
            return

        try:
            if ext == ".rwl":
                self._exportar_bi_tucson(ruta, anios, seleccion)
            else:
                self._exportar_bi_multicolumna(ruta, ext, anios, seleccion, codigo)
        except Exception as exc:
            logger.error("Error al exportar BI: %s", exc)
            QMessageBox.critical(self.radio.parent, "Error",
                                 f"Fallo al exportar:\n{exc}")


    def _exportar_bi_tucson(self, ruta: str, anios: list, seleccion: list):
        """Genera un .rwl Tucson por cada (canal, métrica)."""
        codigo = self.input_codigo.text().strip() or "serie"
        directorio = os.path.dirname(ruta)
        base = os.path.splitext(os.path.basename(ruta))[0]
        # Si terminaba en "_bi", quitarlo para evitar duplicación
        if base.lower().endswith("_bi"):
            base = base[:-3]

        escritos = []
        errores = []

        for canal, met in seleccion:
            vals = valores_intensidad(self._bi_datos, canal, met)
            if canal in ("B_R", "B_G"):
                r_max = max(vals, default=0.0)
                vals_norm = [v / r_max if r_max > 0 else 0.0 for v in vals]
                suf = canal.lower().replace("_", "div")
            else:
                vals_norm = [v / 255.0 for v in vals]
                suf = f"{canal.lower()}_{met}"

            nombre_archivo = f"{base}_{suf}.rwl"
            ruta_rwl = os.path.join(directorio, nombre_archivo)
            try:
                from dpi.formatos.tucson import escribir_tucson
                escribir_tucson(pd.Series(vals_norm, index=anios), ruta_rwl,
                    codigo=f"{codigo[:6]}{canal[:1].lower()}{met[:1] if met else ''}")
                escritos.append(nombre_archivo)
            except Exception as exc:
                errores.append(f"{nombre_archivo}: {exc}")

        msg = f"✅ Guardados {len(escritos)} archivos Tucson en:\n{directorio}"
        if escritos:
            msg += "\n\n" + "\n".join(f"  • {f}" for f in escritos)
        if errores:
            msg += "\n\n⚠ Errores:\n" + "\n".join(errores)
        QMessageBox.information(self.radio.parent, "Guardado completado", msg)


    def _exportar_bi_multicolumna(self, ruta: str, ext: str, anios: list,
                                    seleccion: list, codigo: str):
        """Genera un solo archivo Excel/CSV/TXT con todas las series como columnas."""
        # Construir DataFrame con una columna por cada (canal, métrica)
        data = {"Anio": anios}
        for canal, met in seleccion:
            col_label = f"{canal}_ratio" if canal in ("B_R", "B_G") else f"{canal}_{met}"
            data[col_label] = valores_intensidad(self._bi_datos, canal, met)

        df = pd.DataFrame(data).sort_values("Anio")
        from dpi.formatos.tabular import escribir_tabla
        escribir_tabla(df, ruta)

        n_cols = len(df.columns) - 1  # restar la columna Anio
        QMessageBox.information(
            self.radio.parent, "✅ Exportación completada",
            f"Archivo guardado:\n{ruta}\n\n"
            f"Formato: multi-columna ({n_cols} series)\n"
            f"Filas: {len(df)} años\n"
            f"Columnas: Anio + {n_cols} canales/métricas"
        )
