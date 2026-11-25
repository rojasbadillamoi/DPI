"""Componente gráfico de medición. No depende de PestanaImagen ni del modelo."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QSignalBlocker
from estilos import color_secundario
from dpi.medicion.grafico import (
    normalizar_grafico, transformar_medicion, correlacion_global, correlacion_deslizante,
)


class GraficoMedicion:
    """Propietario de los items, leyenda, zoom y correlaciones del gráfico.

    Recibe los controles y dos callbacks explícitos: método estadístico y navegación.
    Los datos de los radios se entregan a actualizar(), no se leen desde la vista.
    """
    COLORES = ("#5cb85c", "#5bc0de", "#f0ad4e", "#d9534f",
               "#9b59b6", "#1abc9c", "#e67e22", "#3498db")

    def __init__(self, plot, combo_maestra, spin_ventana, lbl_total, lbl_ventanas,
                 metodo, navegar):
        self.grafico_unif = plot
        self.combo_maestra = combo_maestra
        self.spin_ventana_r = spin_ventana
        self.lbl_r_total = lbl_total
        self.lbl_ventanas_r = lbl_ventanas
        self._metodo = metodo
        self._navegar = navegar
        self._textos_corr_pendientes = []
        self._firma_series_grafico = None
        self._encuadre_pendiente = True
        self._legend = self.grafico_unif.addLegend(offset=(10, 10))
        self._plot_items: dict[str, object] = {}
        self._series_ocultas: set[str] = set()
        self._legend.scene().sigMouseClicked.connect(self._clic_leyenda)

        # ── Crosshair interactivo: línea vertical + etiqueta de año ────────
        from pyqtgraph import InfiniteLine, TextItem, SignalProxy
        self._graf_vline = InfiniteLine(angle=90, movable=False,
                                         pen=pg.mkPen("#888", width=1,
                                                      style=Qt.PenStyle.DotLine))
        self._graf_vline.setZValue(60)
        self._graf_vline.setVisible(False)
        self.grafico_unif.addItem(self._graf_vline, ignoreBounds=True)

        self._graf_label = TextItem(anchor=(0.0, 1.0),
                                     fill=pg.mkBrush(0, 0, 0, 180),
                                     border=pg.mkPen("#888", width=1))
        self._graf_label.setZValue(61)
        self._graf_label.setVisible(False)
        self.grafico_unif.addItem(self._graf_label, ignoreBounds=True)

        # Marcador del punto más cercano
        self._graf_dot = self.grafico_unif.plot(
            [], [], pen=None, symbol='o', symbolSize=10,
            symbolBrush='#FFD700', symbolPen=pg.mkPen('#FFF', width=1.5))
        self._graf_dot.setZValue(62)

        # Proxy para throttle del mouse-move (cada 30ms)
        self._graf_proxy = SignalProxy(
            self.grafico_unif.scene().sigMouseMoved,
            rateLimit=33, slot=self._graf_mouse_moved)

        # Click en el gráfico → navegar a ese año en la imagen
        self.grafico_unif.scene().sigMouseClicked.connect(self._graf_mouse_clicked)


    _normalizar = staticmethod(normalizar_grafico)

    def _transformar_corr(self, anios, anchos):
        return transformar_medicion(anios, anchos, self._metodo())

    def _r_global(self, anios_a, anchos_a, anios_b, anchos_b):
        return correlacion_global(anios_a, anchos_a, anios_b, anchos_b, self._metodo())

    def _r_deslizante(self, anios_a, anchos_a, anios_b, anchos_b, ventana):
        return correlacion_deslizante(anios_a, anchos_a, anios_b, anchos_b,
                                      ventana, self._metodo())

    def encuadrar(self, pw=None, solo_mas_larga=True):
        return self._encuadrar_grafico(pw, solo_mas_larga)

    def _actualizar_combo_maestra(self, entradas, nombre_maestra_ext):
        """Actualiza el combo selector de maestra con las series disponibles."""
        previo = self.combo_maestra.currentText()
        with QSignalBlocker(self.combo_maestra):
            self.combo_maestra.clear()
            if nombre_maestra_ext:
                self.combo_maestra.addItem(f"↑ Ext: {nombre_maestra_ext}")
            for nombre, *_ in entradas:
                self.combo_maestra.addItem(nombre)
            idx = self.combo_maestra.findText(previo)
            if idx >= 0:
                self.combo_maestra.setCurrentIndex(idx)


    def _graf_mouse_moved(self, evt):
        """Muestra crosshair vertical con año y valores al mover el mouse."""
        pos = evt[0]
        vb = self.grafico_unif.getViewBox()
        if not self.grafico_unif.sceneBoundingRect().contains(pos):
            self._graf_vline.setVisible(False)
            self._graf_label.setVisible(False)
            self._graf_dot.setData([], [])
            return

        mouse_point = vb.mapSceneToView(pos)
        anio = round(mouse_point.x())

        # Buscar valores de cada serie visible en ese año
        lineas = []
        dot_x, dot_y = [], []
        for nombre, item in self._plot_items.items():
            if not item.isVisible():
                continue
            xdata, ydata = item.getData()
            if xdata is None or len(xdata) == 0:
                continue
            # Buscar índice más cercano al año
            idx = int(np.argmin(np.abs(np.array(xdata) - anio)))
            if abs(xdata[idx] - anio) < 1.0:
                val = ydata[idx]
                # Quitar ★ y (maestra) del nombre para mostrar más limpio
                nombre_corto = nombre.replace("★ ", "").replace(" (maestra)", "")
                lineas.append(f"{nombre_corto}: {val:.3f}")
                dot_x.append(xdata[idx])
                dot_y.append(val)

        if not lineas:
            self._graf_vline.setVisible(False)
            self._graf_label.setVisible(False)
            self._graf_dot.setData([], [])
            return

        # Posicionar crosshair
        self._graf_vline.setPos(anio)
        self._graf_vline.setVisible(True)

        # Texto
        texto_html = (
            f"<span style='color:white; font-size:9pt; font-family:Arial;'>"
            f"<b>{anio}</b><br/>"
            + "<br/>".join(lineas)
            + "</span>"
        )
        self._graf_label.setHtml(texto_html)
        # Posicionar arriba a la derecha de la línea
        [[_xmin, _xmax], [_ymin, y_max]] = vb.viewRange()
        self._graf_label.setPos(anio + (_xmax - _xmin) * 0.01, y_max)
        self._graf_label.setVisible(True)

        # Puntos amarillos
        self._graf_dot.setData(dot_x, dot_y)


    def _graf_mouse_clicked(self, ev):
        """Al hacer clic en el gráfico, centra la imagen en el año clickeado."""
        # Ignorar si ya fue aceptado (e.g. por clic en leyenda)
        if ev.isAccepted():
            return
        # Solo clic izquierdo, y solo si el clic es sobre el área del plot
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        # No navegar si el clic fue sobre la leyenda
        pos = ev.scenePos()
        if not self.grafico_unif.getViewBox().sceneBoundingRect().contains(pos):
            return

        vb = self.grafico_unif.getViewBox()
        mouse_point = vb.mapSceneToView(pos)
        anio = round(mouse_point.x())

        if self._navegar(anio):
            ev.accept()


    def _clic_leyenda(self, ev):
        """Toggle visibilidad al hacer clic en un item de la leyenda."""
        pos = ev.scenePos()
        for nombre, item in self._plot_items.items():
            sample, label = None, None
            for s, l in self._legend.items:
                # Comparar por referencia al item de datos, no por nombre
                if s.item is item:
                    sample, label = s, l
                    break
            if sample is None:
                # Fallback: buscar por texto (nombres sin ★)
                for s, l in self._legend.items:
                    if l.text == nombre:
                        sample, label = s, l
                        break
            if sample is None:
                continue
            sr = sample.mapRectToScene(sample.boundingRect())
            lr = label.mapRectToScene(label.boundingRect())
            if sr.contains(pos) or lr.contains(pos):
                if nombre in self._series_ocultas:
                    self._series_ocultas.discard(nombre)
                    item.setVisible(True)
                    label.setAttr("color", "FFFFFF")
                else:
                    self._series_ocultas.add(nombre)
                    item.setVisible(False)
                    label.setAttr("color", "666666")
                ev.accept()
                return


    def _dibujar_segmentos_correlacion(self, pw, entradas, maestra):
        """
        Dibuja anotaciones de correlación por segmento directamente
        sobre el gráfico de series.

        Lógica de segmentación (igual a la descrita por el usuario):
          - Ventana W años → segmentos de W/2 años cada uno, sin solapamiento.
          - Ejemplo W=10: segmentos [0-5), [5-10), [10-15)...
          - Ejemplo W=20: segmentos [0-10), [10-20), [20-30)...
          - Cada segmento muestra su r como texto coloreado en el centro,
            sobre una barra de fondo semitransparente.
          - El primer segmento puede ser más pequeño si la serie tiene
            menos de W/2 años disponibles (ventana creciente al inicio).
        """
        from pyqtgraph import InfiniteLine, LinearRegionItem, TextItem

        if maestra is None or not entradas:
            return

        self._textos_corr_pendientes = []

        ventana = self.spin_ventana_r.value()
        paso    = max(5, ventana // 2)   # cada segmento = mitad de la ventana
        nombre_m, anios_m, anchos_m = maestra

        def _col_rgba(r):
            if r >= 0.50:  return (46,  204, 113, 55)   # verde fuerte
            if r >= 0.35:  return (92,  184,  92, 55)   # verde
            if r >= 0.15:  return (240, 173,  78, 55)   # naranja
            return (217,  83,  79, 55)                   # rojo

        def _col_hex(r):
            if r >= 0.50:  return "#2ecc71"
            if r >= 0.35:  return "#5cb85c"
            if r >= 0.15:  return "#f0ad4e"
            return "#d9534f"

        # Maestra transformada con el método seleccionado
        db_m = self._transformar_corr(anios_m, anchos_m)

        for nombre, anios, anchos, color, *_ in entradas:
            da = self._transformar_corr(anios, anchos)
            overlap = sorted(da.index.intersection(db_m.index))
            if len(overlap) < 5:
                continue

            yr_min = overlap[0]
            yr_max = overlap[-1]

            # Generar segmentos de paso años comenzando desde yr_min
            seg_inicio = yr_min
            while seg_inicio < yr_max:
                seg_fin = seg_inicio + paso
                seg = [y for y in overlap if seg_inicio <= y < seg_fin]
                if len(seg) < 3:
                    seg_inicio += paso
                    continue

                a_seg = da.loc[seg].values
                b_seg = db_m.loc[seg].values
                if np.std(a_seg) < 1e-9 or np.std(b_seg) < 1e-9:
                    seg_inicio += paso
                    continue

                r = float(np.corrcoef(a_seg, b_seg)[0, 1])
                if np.isnan(r):
                    seg_inicio += paso
                    continue

                # Fondo semitransparente para el segmento
                rgba = _col_rgba(r)
                region = LinearRegionItem(
                    values=[seg_inicio, seg_fin],
                    orientation='vertical',
                    brush=pg.mkBrush(*rgba),
                    pen=pg.mkPen(None),
                    movable=False,
                )
                region.setZValue(-10)
                pw.addItem(region)

                # Texto de correlación centrado en el segmento
                centro_x = (seg_inicio + seg_fin) / 2.0
                txt = TextItem(
                    anchor=(0.5, 0.0),
                    fill=pg.mkBrush(0, 0, 0, 160),
                    border=pg.mkPen(_col_hex(r), width=1),
                )
                txt.setHtml(
                    f"<span style='color:{_col_hex(r)}; font-size:10pt; "
                    f"font-weight:bold; font-family:Arial;'>"
                    f" r={r:+.2f} </span>"
                )
                txt.setZValue(50)
                pw.addItem(txt)
                # Posicionar en la parte alta del rango visible
                self._textos_corr_pendientes.append((txt, centro_x))

                seg_inicio += paso


    def _actualizar_correlaciones_texto(self, entradas, maestra):
        """
        Actualiza la barra de texto de correlaciones debajo del gráfico.

        Muestra para cada serie vs maestra:
          - Símbolo de calidad  ●●● / ●●○ / ●○○ / ○○○
          - r total coloreado
          - r por ventanas crecientes (10, 20, 30... hasta la ventana elegida)
          - N años de solapamiento
        """
        if maestra is None or not entradas:
            self.lbl_r_total.setText("")
            self.lbl_ventanas_r.setText("")
            return

        ventana_max = self.spin_ventana_r.value()
        nombre_m, anios_m, anchos_m = maestra

        def _col(r):
            if r is None:    return "#666666"
            if r >= 0.50:    return "#2ecc71"
            if r >= 0.35:    return "#5cb85c"
            if r >= 0.15:    return "#f0ad4e"
            return "#d9534f"

        def _simbolo(r):
            if r is None:    return "○○○"
            if r >= 0.50:    return "●●●"
            if r >= 0.35:    return "●●○"
            if r >= 0.15:    return "●○○"
            return "○○○"

        # Calcular ventanas a mostrar: 10, 20, 30... hasta ventana_max
        ventanas = list(range(10, ventana_max + 1, 10))
        if not ventanas or ventanas[-1] != ventana_max:
            ventanas.append(ventana_max)
        # Máximo 6 ventanas para no saturar el texto
        if len(ventanas) > 6:
            paso = len(ventanas) // 6
            ventanas = ventanas[::paso]
            if ventanas[-1] != ventana_max:
                ventanas.append(ventana_max)

        # Línea superior: r total por serie (label fila de referencia)
        partes_total = []
        for nombre, anios, anchos, color, *_ in entradas:
            r_tot = self._r_global(anios, anchos, anios_m, anchos_m)
            c = _col(r_tot)
            sym = _simbolo(r_tot)
            val = f"{r_tot:+.2f}" if r_tot is not None else "—"
            # Overlap
            sa = pd.Series(anchos, index=anios)
            sb = pd.Series(anchos_m, index=anios_m)
            n_ov = len(sa.index.intersection(sb.index))
            partes_total.append(
                f"<span style='color:{color}'><b>{nombre}</b></span>"
                f"&nbsp;<span style='color:{c}'>{sym}&nbsp;r={val}</span>"
                f"&nbsp;<span style='color:{color_secundario()}'>({n_ov} años)</span>"
            )

        self.lbl_r_total.setText("&nbsp;&nbsp;&nbsp;".join(partes_total))

        # Línea inferior: desglose por ventana
        if not partes_total:
            self.lbl_ventanas_r.setText("")
            return

        lineas_ventana = []
        for nombre, anios, anchos, color, *_ in entradas:
            celdas = [f"<span style='color:{color}'><b>{nombre}</b></span>&nbsp;"]
            for v in ventanas:
                res = self._r_deslizante(anios, anchos, anios_m, anchos_m, v)
                if res[0]:
                    # Media de todos los r de esa ventana
                    r_v = float(np.mean(res[1]))
                    c = _col(r_v)
                    celdas.append(
                        f"<span style='color:{color_secundario()}'>{v}a:</span>"
                        f"<span style='color:{c}'>&nbsp;{r_v:+.2f}</span>"
                    )
                else:
                    celdas.append(
                        f"<span style='color:{color_secundario()}'>{v}a:&nbsp;—</span>"
                    )
            lineas_ventana.append("&nbsp;&nbsp;".join(celdas))

        self.lbl_ventanas_r.setText("&nbsp;&nbsp;|&nbsp;&nbsp;".join(lineas_ventana))


    def actualizar(self, entradas, serie_maestra, nombre_maestra):
        """
        Gráfico de series (arriba) + correlación deslizante estilo COFECHA (abajo).
        La maestra puede ser externa (.rwl/.wid) o una serie propia elegida en el combo.
        """
        pw = self.grafico_unif
        pw.clear()
        self._legend.clear()
        pw.addItem(self._graf_vline, ignoreBounds=True)
        pw.addItem(self._graf_label, ignoreBounds=True)
        pw.addItem(self._graf_dot, ignoreBounds=True)
        self._graf_vline.hide()
        self._graf_label.hide()
        self._graf_dot.setData([], [])
        self._plot_items.clear()
        self._textos_corr_pendientes = []

        # ── Determinar maestra ────────────────────────────────────────────
        # Lógica: si hay maestra externa cargada (.rwl/.wid) Y el combo está
        # mostrando "↑ Ext: ..." (la opción de la externa), usar la externa.
        # Si el usuario eligió otra entrada del combo, respetarlo y usar esa
        # serie interna como maestra. Así el combo nunca queda "muerto"
        # cuando hay externa cargada.
        #
        # IMPORTANTE: aunque el usuario haya elegido una interna en el combo,
        # la externa SIGUE existiendo y debe aparecer en el combo (como opción
        # "↑ Ext: ...") y dibujarse en el gráfico (como referencia adicional).
        # Bug previo: si user cargaba externa pero elegía interna en combo,
        # nombre_maestra_ext quedaba en None → la externa desaparecía del
        # combo y del gráfico. Por eso "no aparecen series en el gráfico".
        maestra = None
        nombre_maestra_ext = None
        serie_maestra_data = None  # tupla (nombre, anios, anchos) de la externa
        seleccion_combo = self.combo_maestra.currentText()
        es_seleccion_externa = seleccion_combo.startswith("↑ Ext:")

        # 1) Si hay externa cargada, siempre preparar sus datos para que
        #    aparezca en el combo y se dibuje en el plot (independientemente
        #    de qué tenga seleccionado el usuario).
        if serie_maestra is not None and not serie_maestra.empty:
            col = ("Ancho_mm" if "Ancho_mm" in serie_maestra.columns
                   else serie_maestra.columns[0])
            ref = serie_maestra[col].dropna()
            if not ref.empty:
                nombre_maestra_ext = nombre_maestra
                serie_maestra_data = (
                    nombre_maestra,
                    list(ref.index.astype(int)),
                    list(ref.values.astype(float)),
                )

        # 2) Decidir cuál se usa como maestra para la correlación (=lo que
        #    se compara contra las demás).
        if serie_maestra_data is not None and (
                es_seleccion_externa or not seleccion_combo):
            # Combo apunta a la externa (o está vacío al principio) → usar externa
            maestra = serie_maestra_data
        else:
            # Combo apunta a una interna → usar esa
            sel = seleccion_combo
            for e in entradas:
                if e[0] == sel:
                    maestra = (e[0], e[1], e[2])
                    break
            # Fallback: si el seleccionado no está en entradas pero hay
            # externa, usar externa para no quedar sin maestra.
            if maestra is None and serie_maestra_data is not None:
                maestra = serie_maestra_data

        # Actualizar combo
        self._actualizar_combo_maestra(entradas, nombre_maestra_ext)

        # ── Normalizar ────────────────────────────────────────────────────
        n_curvas = len(entradas) + (1 if nombre_maestra_ext else 0)
        normalizar = n_curvas > 1
        pw.setLabel("left", "Ancho norm. (z)" if normalizar else "Ancho (mm)")

        # ── Dibujar series ────────────────────────────────────────────────
        # NUEVA LÓGICA (acorde a lo solicitado):
        # - La serie SELECCIONADA como maestra (la que se compara contra las
        #   demás, sin importar si es externa o interna) lleva ★ en su nombre
        #   en la leyenda Y se dibuja con línea SÓLIDA gruesa.
        # - Todas las otras series se dibujan con línea PUNTEADA fina.
        # - La externa, si está cargada pero no es la seleccionada, se dibuja
        #   con su propio etiquetado de referencia.
        nombre_maestra_actual = maestra[0] if maestra else None
        es_maestra_externa = (
            maestra is not None and maestra is serie_maestra_data
        )

        for nombre, anios, anchos, color, estilo in entradas:
            y = self._normalizar(anchos) if normalizar else anchos
            es_seleccionada = (nombre == nombre_maestra_actual
                                and not es_maestra_externa)
            if es_seleccionada:
                # Línea sólida gruesa + ★ en la leyenda
                nombre_legend = f"★ {nombre} (maestra)"
                pen = pg.mkPen(color, width=3, style=Qt.PenStyle.SolidLine)
            else:
                # Línea punteada fina
                nombre_legend = nombre
                pen = pg.mkPen(color, width=1.8, style=Qt.PenStyle.DashLine)
            item = pw.plot(anios, y,
                           pen=pen,
                           symbol="o", symbolSize=3,
                           symbolBrush=color, symbolPen=None,
                           name=nombre_legend)
            self._plot_items[nombre] = item
            if nombre in self._series_ocultas:
                item.setVisible(False)

        # Dibujar maestra externa si está cargada
        if serie_maestra_data is not None:
            nombre_m, anios_m, anchos_m = serie_maestra_data
            y_m = self._normalizar(anchos_m) if normalizar else anchos_m
            if es_maestra_externa:
                # Externa SELECCIONADA → ★ + sólida gruesa
                nombre_m_legend = f"★ {nombre_m} (maestra)"
                pen_m = pg.mkPen("#f0ad4e", width=3, style=Qt.PenStyle.SolidLine)
            else:
                # Externa NO seleccionada (hay una interna como maestra) →
                # se muestra como referencia adicional, dashed delgada
                nombre_m_legend = f"📂 {nombre_m} (ref. ext.)"
                pen_m = pg.mkPen("#f0ad4e", width=1.5, style=Qt.PenStyle.DashLine)
            item_m = pw.plot(anios_m, y_m,
                             pen=pen_m,
                             name=nombre_m_legend)
            self._plot_items[nombre_m] = item_m
            if nombre_m in self._series_ocultas:
                item_m.setVisible(False)

        # ── Correlaciones por segmento sobre el gráfico ─────────────────
        # Excluir de correlación la serie que ES la maestra (no tiene
        # sentido correlacionarla consigo misma). Funciona tanto si la
        # maestra es interna como si es externa.
        entradas_corr = [e for e in entradas
                         if not (maestra and e[0] == maestra[0]
                                 and not es_maestra_externa)]
        self._dibujar_segmentos_correlacion(pw, entradas_corr, maestra)
        self._actualizar_correlaciones_texto(entradas_corr, maestra)

        # ── Encuadre del gráfico ────────────────────────────────────────
        # Antes se forzaba autoRange() en CADA llamada. Como esta función se
        # dispara con cada anillo medido, el zoom se reiniciaba de continuo y
        # el eje X terminaba abarcando la unión de todas las series (p. ej.
        # 0-2024 con una serie flotante y una cronología reciente), dejando
        # todo apelotonado en un extremo.
        #
        # Ahora el encuadre se recalcula SOLO cuando cambia el conjunto de
        # series dibujadas (se carga o se quita una) o cuando el usuario lo
        # pide con el botón. Medir anillos ya no mueve la vista.
        firma = tuple(sorted(self._plot_items.keys()))
        if getattr(self, "_firma_series_grafico", None) != firma:
            self._firma_series_grafico = firma
            self._encuadre_pendiente = True
        if getattr(self, "_encuadre_pendiente", True):
            self._encuadre_pendiente = False
            self._encuadrar_grafico(pw, solo_mas_larga=True)

        # Posicionar textos de correlación en la parte alta del gráfico
        self._posicionar_textos_correlacion(pw)
        # Reconectar: reposicionar textos al hacer zoom/pan
        try:
            pw.getViewBox().sigRangeChanged.disconnect(self._reposicionar_textos_corr)
        except (TypeError, RuntimeError):
            pass
        pw.getViewBox().sigRangeChanged.connect(self._reposicionar_textos_corr)


    def _encuadrar_grafico(self, pw=None, solo_mas_larga: bool = True):
        """Fija el rango visible del gráfico a partir de los datos dibujados.

        `solo_mas_larga=True` usa la extensión de la serie con más años, que
        es lo que se quiere al mezclar una serie flotante (años 0-200) con una
        cronología fechada: la unión de ambas dejaría un hueco enorme y las
        curvas quedarían aplastadas contra los bordes.

        `solo_mas_larga=False` encuadra la unión de todo lo dibujado, para el
        botón «Encuadrar todo».
        """
        if pw is None:
            pw = getattr(self, "grafico_unif", None)
        if pw is None:
            return
        tramos = []
        for item in self._plot_items.values():
            try:
                if not item.isVisible():
                    continue
                x, y = item.getData()
            except Exception:
                continue
            if x is None or len(x) == 0:
                continue
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float) if y is not None else None
            finitos = np.isfinite(x)
            if not finitos.any():
                continue
            tramos.append((float(np.min(x[finitos])), float(np.max(x[finitos])),
                           y[finitos] if y is not None else None))
        if not tramos:
            return

        vb = pw.getViewBox()
        if solo_mas_larga:
            x0, x1, _ = max(tramos, key=lambda t: t[1] - t[0])
        else:
            x0 = min(t[0] for t in tramos)
            x1 = max(t[1] for t in tramos)
        if x1 <= x0:
            x1 = x0 + 1.0
        margen = (x1 - x0) * 0.02
        vb.enableAutoRange(axis=vb.XAxis, enable=False)
        vb.setXRange(x0 - margen, x1 + margen, padding=0)

        # El eje Y se ajusta a lo que cae dentro de la ventana X elegida
        ys = []
        for a, b, y in tramos:
            if y is None or b < x0 or a > x1:
                continue
            ys.append(y)
        if ys:
            todos = np.concatenate(ys)
            todos = todos[np.isfinite(todos)]
            if todos.size:
                y0, y1 = float(todos.min()), float(todos.max())
                if y1 <= y0:
                    y1 = y0 + 1.0
                m = (y1 - y0) * 0.05
                vb.enableAutoRange(axis=vb.YAxis, enable=False)
                vb.setYRange(y0 - m, y1 + m, padding=0)
        self._posicionar_textos_correlacion(pw)


    def _posicionar_textos_correlacion(self, pw):
        """Coloca los textos de correlación en la parte alta del rango Y visible."""
        pendientes = getattr(self, "_textos_corr_pendientes", [])
        if not pendientes:
            return
        vb = pw.getViewBox()
        [[_xmin, _xmax], [_ymin, y_max]] = vb.viewRange()
        # Posicionar justo en el tope del rango visible (anchor 0.0 = cuelga hacia abajo)
        y_top = y_max - (y_max - _ymin) * 0.01
        for txt, cx in pendientes:
            txt.setPos(cx, y_top)


    def _reposicionar_textos_corr(self, vb=None):
        """Slot: reposiciona textos de correlación cuando cambia el rango visible."""
        pw = self.grafico_unif
        self._posicionar_textos_correlacion(pw)
