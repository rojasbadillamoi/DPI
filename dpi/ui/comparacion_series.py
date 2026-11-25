"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
from dpi.ciencia.comparacion_nucleo import comparar_serie
from PyQt6.QtWidgets import QMessageBox, QApplication
from PyQt6.QtCore import Qt
from modulo_comparacion_ui import VentanaTablaOffset, DialogoComparacionMultiple

def comparar_series_marcadas_vs_crono(self):
    """Compara las series marcadas (1 o varias) contra la cronología
    activa. Lanzada desde el botón "Series múltiples vs Crono" del
    panel principal — el usuario no tiene que abrir la ventana de
    cronología para usar esta funcionalidad.

    Flujo:
      1. Si NO hay cronología cargada: avisa al usuario que primero
         cargue/genere una.
      2. Si hay 0 series marcadas: aviso.
      3. Si hay 1+ series marcadas: ejecuta el cálculo en lote y
         abre `DialogoComparacionMultiple` con los resultados.

    RANGO DE DESFASE DINÁMICO POR SERIE:
    En vez de usar un max_shift fijo, el rango se calcula por serie
    según los años que cubre. Esto permite que el mismo botón funcione
    con dos tipos de series:

      - Series FECHADAS (años calendar 1500-2020 por ejemplo): el
        rango natural es estrecho, solo hay overlap cerca de shift=0.
        El cálculo es rápido y detecta errores de datación pequeños
        (anillos faltantes/extra).

      - Series FLOTANTES (años arbitrarios 0-200 por ejemplo): el
        rango natural cubre TODA la cronología. Encuentra la posición
        donde encaja la serie. Más lento pero necesario — antes el
        límite fijo de 10 hacía que estas series mostraran todo en 0
        porque jamás se solapaban con la cronología.

    Fórmula:
      shift_min = c_min - s_max + min_overlap - 1
      shift_max = c_max - s_min - min_overlap + 1
    donde c_* son años de la cronología y s_* son años de la serie.
    Cualquier shift en ese rango garantiza al menos `min_overlap`
    años de solape.
    """
    # Validación 1: cronología activa
    if self.cronologia_activa is None or self.cronologia_activa.empty:
        QMessageBox.warning(
            self, "Sin cronología activa",
            "Primero carga una cronología desde el botón <b>📚 Crono</b>\n"
            "o genérala desde <b>🧭 Generar Cronología</b>.\n\n"
            "Una vez disponible podrás comparar series contra ella desde acá."
        )
        return

    # Validación 2: series marcadas
    nombres = self._series_marcadas()
    if len(nombres) < 1:
        QMessageBox.warning(
            self, "Sin series marcadas",
            "Marca al menos una serie con check en la lista\n"
            "para compararla contra la cronología."
        )
        return

    # ── Caché de resultados ───────────────────────────────────────
    # Construir una clave que represente el estado actual de la
    # comparación: series marcadas + cronología + un resumen de los
    # datos de cada una (largo, primer y último año, suma redondeada).
    # Si nada cambió desde el último cálculo, reusamos los resultados
    # guardados en vez de recalcular (que puede ser lento con series
    # flotantes y rangos de desfase amplios).
    nombres_iniciales = tuple(nombres)
    clave_actual = self._clave_cache_comparacion(nombres_iniciales)
    cache = getattr(self, "_cache_comparacion", None)
    if (cache is not None and cache.get("clave") == clave_actual
            and cache.get("resultados")):
        dlg = DialogoComparacionMultiple(
            cache["resultados"], cache["nombre_crono"], parent=self,
            obtener_serie=self.series_datos.get, aplicar_desfase=self.aplicar_desfase_a_serie,
            reemplazar=self.reemplazar_serie)
        dlg.exec()
        return

    # Excluir la propia cronología de la comparación si está marcada.
    # No tiene sentido comparar la cronología consigo misma — daría
    # siempre un puntaje perfecto en shift=0 y confunde el resumen.
    nombre_crono_completo = None
    for nombre in nombres:
        n_limpio = nombre.replace("📚 ", "").strip()
        if n_limpio == self._nombre_cronologia_activa:
            nombre_crono_completo = nombre
            break
    if nombre_crono_completo:
        nombres = [n for n in nombres if n != nombre_crono_completo]
        if not nombres:
            QMessageBox.warning(
                self, "Sin series comparables",
                "Solo marcaste la propia cronología activa. Marca otras\n"
                "series para compararlas contra ella."
            )
            return

    MIN_OVERLAP = 20
    # Desfase máximo a explorar para series que YA están fechadas (se
    # solapan con la cronología). Suficiente para detectar errores de
    # datación reales sin barrer cientos de años innecesariamente.
    VENTANA_DESFASE_FECHADA = 50

    # Preparar la serie de la cronología (lado derecho de la comparación)
    meta = self.meta_cronologia or {}
    col_val = meta.get("columna_valor")
    if not col_val or col_val not in self.cronologia_activa.columns:
        col_val = self.cronologia_activa.columns[0]
    referencia = self._preparar_serie_comparacion(self.cronologia_activa[col_val], True)
    if referencia.cruda.empty:
        QMessageBox.warning(
            self, "Cronología sin datos válidos",
            "La cronología activa no contiene valores numéricos válidos."
        )
        return

    # Cursor de espera durante el cálculo
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    resultados = []
    nombre_crono = self._nombre_cronologia_activa or "cronología"

    try:
        for nombre in nombres:
            df_serie = self.series_datos.get(nombre)
            if df_serie is None or df_serie.empty:
                continue

            serie = self._preparar_serie_comparacion(df_serie["Ancho_mm"], nombre.startswith("📚"))
            if serie.cruda.empty or serie.correlacion.empty:
                continue
            resultado = comparar_serie(nombre, serie, referencia,
                MIN_OVERLAP, VENTANA_DESFASE_FECHADA)
            resultados.append(resultado)
            if resultado["shifts"]:
                QApplication.processEvents()
                if (tuple(sorted(self._series_marcadas())) != tuple(sorted(nombres_iniciales))
                        or self._clave_cache_comparacion(nombres_iniciales) != clave_actual):
                    QMessageBox.warning(self, "Comparación desactualizada",
                        "Los datos o parámetros cambiaron durante el cálculo. Vuelve a comparar.")
                    return
    finally:
        QApplication.restoreOverrideCursor()

    if not resultados:
        QMessageBox.warning(
            self, "Sin resultados",
            "No se pudo comparar ninguna de las series marcadas.\n"
            "Verifica que las series tengan datos válidos."
        )
        return

    # Guardar en caché para no recalcular si se reabre con las mismas
    # series sin cambios.
    self._cache_comparacion = {
        "clave": clave_actual,
        "resultados": resultados,
        "nombre_crono": nombre_crono,
    }

    dlg = DialogoComparacionMultiple(resultados, nombre_crono, parent=self,
        obtener_serie=self.series_datos.get, aplicar_desfase=self.aplicar_desfase_a_serie,
        reemplazar=self.reemplazar_serie)
    dlg.exec()


def _clave_cache_comparacion(self, nombres: list[str]) -> tuple:
    """Identifica datos, años, columnas y metadatos de la comparación."""
    # Incluir el estado del modo COFECHA: afecta directamente las
    # correlaciones (transformación de las series). Sin esto, al
    # activar/desactivar COFECHA la clave no cambiaba y se devolvía el
    # resultado cacheado anterior — parecía que COFECHA "no hacía nada".
    try:
        cof = (
            bool(self.btn_modo_cofecha.isChecked()),
            bool(self.chk_cof_serie.isChecked()),
            bool(self.chk_cof_crono.isChecked()),
            tuple(sorted((self._modo_cofecha_params or {}).items())),
        )
    except Exception:
        cof = ()
    from dpi.ciencia.comparacion_nucleo import clave_cache_comparacion
    modelo = getattr(self, "modelo_series", None)
    return clave_cache_comparacion(nombres,
        revision=modelo.revision if modelo is not None else None,
        series=self.series_datos, nombre_crono=self._nombre_cronologia_activa,
        cronologia=self.cronologia_activa, meta=self.meta_cronologia, cofecha=cof)


def mostrar_tabla_offset(self):
    """Abre el diálogo con la tabla completa de offsets."""
    if not self._shifts_actuales:
        return
    dialogo = VentanaTablaOffset(
        self._shifts_actuales, self._r_actuales,
        self._glk_actuales, self._tbp_actuales, self._n_actuales,
        serie_a=getattr(self, "_offset_serie_a_raw", None),
        serie_b=getattr(self, "_offset_serie_b_raw", None),
        parent=self,
        nombre_serie=getattr(self, "_offset_nombre_a", None),
        obtener_serie=self.series_datos.get, aplicar_desfase=self.aplicar_desfase_a_serie,
        reemplazar=self.reemplazar_serie,
    )
    dialogo.exec()
