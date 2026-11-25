"""Herramienta de médula con estado propio y entradas explícitas."""
import math
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.pith import ajustar_circulo_minimos_cuadrados, ajuste_degenerado


class HerramientaPith:
    """Gestiona arco, elementos temporales y HUD sin conocer la pestaña."""

    def __init__(self, escena, viewport, escala, coordenadas, ppm, direccion,
                 configuracion, mediciones, estado):
        self.scene = escena
        self.viewport = viewport
        self._escala_vista = escala
        self._coordenadas = coordenadas
        self._ppm = ppm
        self._direccion = direccion
        self._configuracion = configuracion
        self._mediciones = mediciones
        self._estado = estado
        self._puntos_pith = []
        self._items_pith = []
        self._item_circulo_pith = None
        self._items_pith_extras = []
        self._item_pith_mouse_preview = None
        from PyQt6.QtWidgets import QLabel
        self._hud_pith = QLabel(viewport())
        self._hud_pith.setVisible(False)
        self._hud_pith.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    @property
    def esperando_curvatura(self):
        return len(self._puntos_pith) == 2

    def reposicionar_hud(self):
        if self._hud_pith.isVisible():
            x = max(10, (self.viewport().width() - self._hud_pith.width()) // 2)
            self._hud_pith.move(x, 12)

    def _paso_pith(self, x: float, y: float):
        """
        Modo interactivo de estimación de anillos al centro.
        Flujo guiado en 3 pasos:
          Clic 1: Extremo izquierdo del arco interno visible.
          Clic 2: Extremo derecho del arco → se dibuja guía entre ambos.
          Clic 3: Punto central del arco (la curvatura) → ajuste de círculo.
          Clics 4+: Puntos adicionales para refinar el ajuste.
        Enter confirma; Esc cancela.
        """
        pen_punto = QPen(QColor("#FF8C00"))
        pen_punto.setCosmetic(True)
        pen_punto.setWidthF(3.0)
        brush_punto = QBrush(QColor("#FF8C00"))

        self._puntos_pith.append((x, y))
        n = len(self._puntos_pith)

        # Marcador visual del punto
        r = 8 * self._escala_vista()
        marker = self.scene().addEllipse(x - r, y - r, 2*r, 2*r,
                                          pen_punto, brush_punto)
        self._items_pith.append(marker)

        # ── Paso 1: primer extremo ──
        if n == 1:
            try:
                self._estado(
                    "🎯 Paso 2/3: Haz clic en el otro EXTREMO del arco.")
            except Exception:
                pass
            return

        # ── Paso 2: segundo extremo → dibujar guía ──
        if n == 2:
            p1, p2 = self._puntos_pith
            # Línea guía entre los dos extremos
            pen_guia = QPen(QColor("#FFD700"))
            pen_guia.setCosmetic(True)
            pen_guia.setWidthF(1.5)
            pen_guia.setStyle(Qt.PenStyle.DashDotLine)
            linea_guia = self.scene().addLine(p1[0], p1[1], p2[0], p2[1], pen_guia)
            self._items_pith_extras.append(linea_guia)

            # Punto medio (referencia visual)
            mx, my = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2
            r_mid = 5 * self._escala_vista()
            pen_mid = QPen(QColor("#FFD700"))
            pen_mid.setCosmetic(True)
            pen_mid.setWidthF(2.0)
            mid_marker = self.scene().addEllipse(
                mx-r_mid, my-r_mid, 2*r_mid, 2*r_mid,
                pen_mid, QBrush(Qt.BrushStyle.NoBrush))
            self._items_pith_extras.append(mid_marker)

            # NOTA: el círculo guía amarillo que mostraba un preview tras
            # el 2° clic fue removido a petición del usuario ("el círculo
            # no ayuda en nada"). Después del 2° clic solo se mantiene la
            # línea entre los dos puntos como referencia visual. El círculo
            # real (calculado por mínimos cuadrados a través de los 3 puntos)
            # se dibuja después del 3° clic en _actualizar_circulo_pith.

            try:
                self._estado(
                    "🎯 Paso 3/3: Haz clic en un 3er punto sobre el MISMO "
                    "anillo visible (formando un arco claro con los otros 2).")
            except Exception:
                pass
            return

        # ── Paso 3+: ajustar círculo ──
        self._limpiar_preview_pith_mouse()  # limpiar preview del mouse
        self._actualizar_circulo_pith()
        try:
            self._estado(
                f"🎯 Círculo ajustado con {n} puntos. "
                "Enter para confirmar · clic para agregar más puntos · Esc para cancelar.")
        except Exception:
            pass


    def _preview_pith_mouse(self, x: float, y: float):
        """Dibuja un arco preview cuando hay 2 puntos y el mouse se mueve.

        Estilo: línea más gruesa, color amarillo brillante, opacidad alta
        para que sea visible sobre la textura de la madera (la versión
        anterior usaba opacidad 0.5 + naranja, que se confundía con los
        anillos).
        """
        if len(self._puntos_pith) != 2:
            return
        # Limpiar preview anterior
        self._limpiar_preview_pith_mouse()

        puntos_temp = list(self._puntos_pith) + [(x, y)]
        resultado = ajustar_circulo_minimos_cuadrados(puntos_temp)
        if resultado is None:
            return

        cx, cy, radio = resultado
        # Evitar dibujar círculos absurdamente grandes (cuando el mouse
        # cae casi en línea con p1-p2, el radio tiende a infinito).
        # Tamaño máximo razonable: 10x la distancia entre p1 y p2.
        p1, p2 = self._puntos_pith
        d12 = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        if radio > d12 * 10:
            return

        pen_preview = QPen(QColor("#FFD700"))   # amarillo brillante
        pen_preview.setCosmetic(True)
        pen_preview.setWidthF(2.5)
        pen_preview.setStyle(Qt.PenStyle.DashLine)

        item = self.scene().addEllipse(
            cx - radio, cy - radio, 2*radio, 2*radio,
            pen_preview, QBrush(Qt.BrushStyle.NoBrush))
        item.setOpacity(0.85)
        # Z-value alto: garantiza visibilidad sobre la imagen
        item.setZValue(1000)
        self._item_pith_mouse_preview = item


    def _limpiar_preview_pith_mouse(self):
        """Elimina el arco preview del mouse."""
        item = getattr(self, '_item_pith_mouse_preview', None)
        if item is not None:
            try:
                self.scene().removeItem(item)
            except Exception:
                pass
            self._item_pith_mouse_preview = None


    def _actualizar_circulo_pith(self):
        """Redibuja el círculo ajustado con la estimación de anillos faltantes.

        Algoritmo (simple y correcto para arcos en CUALQUIER dirección):
          1. Ajustar círculo a los puntos marcados (Duncan GM clásico)
          2. El centro del círculo ajustado es la médula estimada
          3. Distancia faltante = `dist(p_inner, centro)` — distancia
             euclidiana desde el primer anillo medido (el más cercano a la
             médula) hasta el centro estimado
          4. Cantidad de anillos = distancia_mm / promedio_ancho_internos

        Importante (corrección del error anterior):
          - NO proyectar sobre eje radial — los anillos son perpendiculares
            al radio, así que un arco bien marcado sobre un anillo tiene
            puntos casi-perpendiculares al radio. Proyectar el centro
            (que está sobre el eje radial) sobre ese mismo eje desde p0
            funciona, PERO requiere que la dirección de medición esté
            "alineada" con la suposición del código. Como p_inner puede
            ser p0 o pK según combo_dir, y la dirección de medición puede
            ir en cualquier sentido, la proyección era inestable.
          - La distancia euclidiana funciona para arcos en cualquier
            dirección (horizontal, vertical, diagonal, etc).

        p_inner se determina por `combo_dir`:
          - med_a_cor=True (medición médula→corteza): p_inner = coords[0]
          - med_a_cor=False (medición corteza→médula): p_inner = coords[-1]
        """
        resultado = ajustar_circulo_minimos_cuadrados(self._puntos_pith)
        if resultado is None:
            try:
                self._estado(
                    "⚠ Puntos colineales. Mueve uno para que el ajuste pueda calcular.")
            except Exception:
                pass
            return
        cx, cy, radio = resultado

        # Detectar fit realmente degenerado: solo cuando los puntos son
        # casi exactamente colineales (radio MUCHÍSIMO más grande que el
        # span de los puntos). Umbral relajado: 50× en lugar de 15×.
        # Un anillo grande puede tener radio 20× el chord medido y NO ser
        # degenerado.
        fit_degenerado = ajuste_degenerado(self._puntos_pith, radio)

        # Limpiar items previos del círculo
        if self._item_circulo_pith is not None:
            try:
                self.scene().removeItem(self._item_circulo_pith)
            except Exception:
                pass
        for item in self._items_pith_extras:
            try:
                self.scene().removeItem(item)
            except Exception:
                pass
        self._items_pith_extras.clear()

        color_fit = "#FF6B6B" if fit_degenerado else "#FF8C00"

        # ── Círculo ajustado punteado ──
        pen_circ = QPen(QColor(color_fit))
        pen_circ.setCosmetic(True)
        pen_circ.setWidthF(2.0)
        pen_circ.setStyle(Qt.PenStyle.DashLine)
        self._item_circulo_pith = self.scene().addEllipse(
            cx - radio, cy - radio, 2*radio, 2*radio,
            pen_circ, QBrush(Qt.BrushStyle.NoBrush)
        )
        self._item_circulo_pith.setZValue(900)

        # ── Cruz en el centro del fit (puede caer fuera de la imagen) ──
        r_centro = 10 * self._escala_vista()
        pen_centro = QPen(QColor(color_fit))
        pen_centro.setCosmetic(True)
        pen_centro.setWidthF(2.5)
        linea_h = self.scene().addLine(cx - r_centro, cy, cx + r_centro, cy, pen_centro)
        linea_v = self.scene().addLine(cx, cy - r_centro, cx, cy + r_centro, pen_centro)
        linea_h.setZValue(901)
        linea_v.setZValue(901)
        self._items_pith_extras.extend([linea_h, linea_v])

        # ── Cálculo de distancia faltante (fórmula de Duncan GM) ──
        coords = self._coordenadas()
        if coords:
            # Determinar cuál extremo de la medición es el más cercano a la
            # médula (p_inner), según la dirección de medición elegida.
            try:
                med_a_cor = self._direccion()
            except Exception:
                med_a_cor = True

            if med_a_cor:
                p_inner = coords[0]
            else:
                p_inner = coords[-1] if len(coords) >= 2 else coords[0]

            # ── MÉTRICA PRIMARIA: distancia faltante = dist(p_inner, centro)
            # La médula está en el centro del círculo ajustado (fit center).
            # La distancia faltante SIEMPRE se cuenta desde p_inner (el
            # primer anillo medido más cercano a la médula) hasta el centro.
            #
            # Esto es independiente de DÓNDE marque el usuario el arco. El
            # arco marcado es solo la herramienta para encontrar la médula
            # (vía fit por mínimos cuadrados, Duncan GM 1989). Si el usuario
            # marca el anillo más interno visible: dist ≈ radio del fit.
            # Si marca un anillo más exterior (porque el interno no se ve
            # claro): radio > dist, pero los anillos faltantes se siguen
            # contando desde p_inner.
            dist_p_inner_centro_mm = (
                math.hypot(cx - p_inner[0], cy - p_inner[1])
                / self._ppm())
            missing_mm = dist_p_inner_centro_mm

            # Radio del fit como información secundaria (diagnóstico)
            radio_fit_mm = radio / self._ppm()

            # Línea desde p_inner hasta el centro del fit (visualización
            # de la DISTANCIA FALTANTE — la métrica primaria)
            pen_dist = QPen(QColor(color_fit))
            pen_dist.setCosmetic(True)
            pen_dist.setWidthF(2.5)
            pen_dist.setStyle(Qt.PenStyle.SolidLine)
            linea_dist = self.scene().addLine(
                p_inner[0], p_inner[1], cx, cy, pen_dist)
            linea_dist.setZValue(903)
            self._items_pith_extras.append(linea_dist)

            # Línea desde el centro hasta uno de los puntos marcados, punteada
            # (visualización del radio del fit como referencia secundaria)
            if self._puntos_pith:
                p_marca = self._puntos_pith[0]
                pen_radio = QPen(QColor(color_fit))
                pen_radio.setCosmetic(True)
                pen_radio.setWidthF(1.5)
                pen_radio.setStyle(Qt.PenStyle.DotLine)
                linea_radio = self.scene().addLine(
                    cx, cy, p_marca[0], p_marca[1], pen_radio)
                linea_radio.setZValue(902)
                self._items_pith_extras.append(linea_radio)

            # ── Estimación de anillos (RG / BAI / Promedio) ──
            # El usuario elige el método en el diálogo. RG es el default
            # (estándar usado por CooRecorder). BAI y Promedio están
            # disponibles para mayor precisión según Altman et al. (2016).
            #
            # Lógica común (anillos de referencia):
            #   1. Encontrar el anillo medido geométricamente más cercano
            #      al arco marcado (su distancia al centro del fit es la
            #      más parecida al radio del fit).
            #   2. Desde ese anillo "ancla", tomar exactamente N anillos
            #      contando HACIA LA CORTEZA (N = `_pith_n_int`).
            #   3. Los anchos de esos N anillos son la referencia.
            #
            # RG: n = distancia_faltante / promedio_ancho
            # BAI: n = (π × distancia²) / mean_BAI_referencia
            #      donde mean_BAI_ref se calcula con las distancias
            #      absolutas de los anillos al centro del fit (que ahora
            #      conocemos).
            # Promedio: (n_rg + n_bai) / 2
            n_est = None
            mean_w_mm = None
            n_used = 0
            n_rg = None
            n_bai = None
            try:
                n_int_user, metodo_calc = self._configuracion()
                dm = self._mediciones()

                if dm and len(coords) >= 2:
                    # Paso 1: anillo medido más cercano al arco marcado
                    distancias_coord = [
                        math.hypot(coords[i][0] - cx, coords[i][1] - cy)
                        for i in range(len(coords))
                    ]
                    diferencias = [abs(d - radio) for d in distancias_coord]
                    idx_anchor = diferencias.index(min(diferencias))

                    # Paso 2: tomar N anillos hacia corteza
                    max_idx_dm = len(dm) - 1
                    if med_a_cor:
                        start = min(idx_anchor, max_idx_dm)
                        end = min(start + n_int_user, max_idx_dm + 1)
                        indices = list(range(start, end))
                    else:
                        start = max(0, min(idx_anchor, max_idx_dm))
                        end_back = max(-1, start - n_int_user)
                        indices = list(range(start, end_back, -1))

                    # Paso 3: anchos de referencia
                    anchos_ref = [
                        dm[i]["ancho_mm"] for i in indices
                        if 0 <= i <= max_idx_dm and dm[i]["ancho_mm"] > 0
                    ]

                    if anchos_ref:
                        mean_w_mm = sum(anchos_ref) / len(anchos_ref)
                        n_used = len(anchos_ref)

                        # ── Cálculo RG ──
                        if mean_w_mm > 0:
                            n_rg = missing_mm / mean_w_mm

                        # ── Cálculo BAI ──
                        # Para BAI necesitamos la distancia del anillo ancla
                        # al centro del fit (posición absoluta desde la médula).
                        # Ahora SÍ podemos calcularlo porque tenemos cx, cy.
                        # No tenemos el problema de dependencia circular que
                        # mencionaba antes.
                        r_anchor_mm = distancias_coord[idx_anchor] / self._ppm()
                        sum_w_ref = sum(anchos_ref)
                        r_outer_ref_mm = r_anchor_mm + sum_w_ref
                        # Área basal total cubierta por los N anillos de
                        # referencia (en mm²)
                        ba_total_ref_mm2 = math.pi * (
                            r_outer_ref_mm**2 - r_anchor_mm**2)
                        mean_bai_mm2 = ba_total_ref_mm2 / len(anchos_ref)
                        # Área basal faltante = disco de radio missing_mm
                        # (desde el centro hasta p_inner)
                        ba_faltante_mm2 = math.pi * missing_mm**2
                        if mean_bai_mm2 > 0:
                            n_bai = ba_faltante_mm2 / mean_bai_mm2

                        # ── Selección final según método ──
                        if metodo_calc == "rg":
                            n_est = n_rg
                        elif metodo_calc == "bai":
                            n_est = n_bai
                        elif metodo_calc == "promedio":
                            if n_rg is not None and n_bai is not None:
                                n_est = (n_rg + n_bai) / 2.0
                            elif n_rg is not None:
                                n_est = n_rg
                            else:
                                n_est = n_bai
                        else:
                            n_est = n_rg  # fallback
            except Exception:
                pass

            # Etiqueta del método usado (para el HUD)
            etiqueta_metodo = {
                "rg": "RG",
                "bai": "BAI",
                "promedio": "Promedio RG+BAI"
            }.get(self._configuracion()[1], 'RG')

            # Construir texto del HUD según calidad del resultado
            if fit_degenerado:
                hud_text = (
                    "⚠ Estimación no confiable. "
                    "Los puntos parecen estar casi en línea recta. "
                    "Marca puntos formando un arco más curvado."
                )
                hud_color = "#FF6B6B"
            elif n_est is None:
                hud_text = (
                    f"📏 Distancia p_inner → médula: {missing_mm:.1f} mm "
                    f"(necesitas anillos medidos para estimar cantidad)"
                )
                hud_color = "#FF8C00"
            elif n_est > 500:
                hud_text = (
                    f"⚠ {missing_mm:.0f} mm → ≈{round(n_est)} anillos. "
                    f"Parece demasiado, ¿marcaste sobre el borde externo?"
                )
                hud_color = "#FF6B6B"
            else:
                # Texto principal con el método elegido + comparación si
                # se calcularon los otros dos
                comparacion = ""
                if n_rg is not None and n_bai is not None:
                    comparacion = (
                        f"  ·  RG: {round(n_rg)}  ·  BAI: {round(n_bai)}"
                    )
                hud_text = (
                    f"🪵 Faltan ≈{round(n_est)} anillos [{etiqueta_metodo}]  ·  "
                    f"Distancia: {missing_mm:.1f} mm  "
                    f"(promedio anillo: {mean_w_mm:.2f} mm  ·  "
                    f"radio arco: {radio_fit_mm:.1f} mm{comparacion})"
                )
                hud_color = "#FF8C00"

            # Mostrar en HUD del viewport
            self._actualizar_hud_pith(hud_text, hud_color)


    def _confirmar_pith(self):
        """Llamado desde PestanaImagen cuando el usuario confirma (Enter/botón)."""
        resultado = ajustar_circulo_minimos_cuadrados(self._puntos_pith)
        self._limpiar_items_pith()
        if resultado is None:
            try:
                self._estado(
                    "⚠ No se pudo ajustar el círculo. "
                    "Asegúrate de que los puntos no sean colineales.")
            except Exception:
                pass
            return resultado
        return resultado


    def _limpiar_items_pith(self):
        """Elimina todos los marcadores visuales del modo pith."""
        for item in self._items_pith:
            try:
                self.scene().removeItem(item)
            except Exception:
                pass
        self._items_pith.clear()
        self._puntos_pith.clear()
        if self._item_circulo_pith is not None:
            try:
                self.scene().removeItem(self._item_circulo_pith)
            except Exception:
                pass
            self._item_circulo_pith = None
        for item in self._items_pith_extras:
            try:
                self.scene().removeItem(item)
            except Exception:
                pass
        self._items_pith_extras.clear()
        self._limpiar_preview_pith_mouse()
        # Ocultar HUD del resultado
        if hasattr(self, "_hud_pith"):
            self._hud_pith.setVisible(False)


    def _actualizar_hud_pith(self, html_text: str, color: str = "#FF8C00"):
        """Actualiza el HUD del pith (texto fijo en la esquina del viewport,
        independiente del pan/zoom de la escena).

        El HUD se posiciona en la parte superior central del viewport para
        que siempre esté visible, sin importar dónde caiga la médula
        estimada (que muchas veces está FUERA de la muestra).
        """
        if not hasattr(self, "_hud_pith"):
            return
        # Reconstruir el stylesheet con el color de fit (naranja=bueno,
        # rojo=no confiable). Mantener el resto fijo.
        self._hud_pith.setStyleSheet(
            f"QLabel {{ background-color: rgba(0,0,0,220); color: {color}; "
            f"padding: 6px 12px; border-radius: 4px; font-size: 13px; "
            f"font-weight: bold; font-family: Arial; "
            f"border: 1px solid rgba(255,140,0,150); }}"
        )
        self._hud_pith.setText(html_text)
        self._hud_pith.adjustSize()
        # Posicionar arriba al centro del viewport
        vp = self.viewport()
        x = max(10, (vp.width() - self._hud_pith.width()) // 2)
        self._hud_pith.move(x, 12)
        self._hud_pith.setVisible(True)
        self._hud_pith.raise_()
