"""Capa gráfica de intensidad, independiente de PestanaImagen y VistaInteractiva."""
import math
import numpy as np
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.intensidad import segmentos_banda_intensidad


class BandaIntensidad:
    """Posee sus elementos gráficos; recibe imagen, escena y parámetros de muestreo."""

    def __init__(self):
        self._items = []

    def limpiar(self):
        for item in self._items:
            try:
                escena = item.scene()
                if escena is not None:
                    escena.removeItem(item)
            except RuntimeError:
                # Qt puede haber destruido la escena previamente.
                pass
        self._items.clear()

    def dibujar(self, escena, img_bgr, coords, saltos, canal, banda, pct, alin, med_a_cor=True):
        """
        Dibuja el área de muestreo BI sobre la imagen.

        Para cada anillo (entre dos límites False consecutivos):
          - Dibuja un polígono por columna de píxeles, coloreado con
            la intensidad real del canal elegido.
          - Sigue la curvatura exacta del camino.
          - Respeta el porcentaje y alineación configurados.
        """
        self.limpiar()
        if not med_a_cor:
            alin = {"ew": "lw", "lw": "ew", "centro": "centro"}[alin]
        if img_bgr is None:
            return

        import cv2 as _cv2
        from PyQt6.QtGui import QPolygonF, QColor as QC
        from PyQt6.QtCore import QPointF

        if canal == "B":
            ch_img = img_bgr[:, :, 0].astype(np.float32)
            def _rgba(v): return QC(int(v*0.25), int(v*0.55), int(v), 210)
        elif canal == "G":
            ch_img = img_bgr[:, :, 1].astype(np.float32)
            def _rgba(v): return QC(0, int(v), 0, 210)
        elif canal == "R":
            ch_img = img_bgr[:, :, 2].astype(np.float32)
            def _rgba(v): return QC(int(v), 0, 0, 210)
        else:
            ch_img = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2GRAY).astype(np.float32)
            def _rgba(v): return QC(int(v), int(v), int(v), 210)

        h_img, w_img = ch_img.shape

        color_borde = {"B": "#4488FF", "G": "#44BB44",
                       "R": "#FF4444", "Gray": "#AAAAAA"}[canal]
        pen_borde = QPen(QColor(color_borde))
        pen_borde.setCosmetic(True)
        pen_borde.setWidthF(1.0)
        pen_sin = QPen(Qt.PenStyle.NoPen)

        if len(coords) < 2:
            return
        items = self._items

        # ── Recopilar anillos ────────────────────────────────────────────
        # Un anillo es la lista de segmentos entre dos límites False
        anillos = segmentos_banda_intensidad(coords, saltos)

        for segs in anillos:
            if not segs:
                continue

            # Calcular longitud total
            long_total = sum(
                math.hypot(coords[ic][0]-coords[ip][0],
                           coords[ic][1]-coords[ip][1])
                for ip, ic in segs
            )
            if long_total < 2:
                continue

            # Rango de longitud a visualizar según alineación
            recorte = 1.0 - pct
            if alin == "ew":
                l_ini, l_fin = 0.0, long_total * pct
            elif alin == "lw":
                l_ini, l_fin = long_total * recorte, long_total
            else:
                m = recorte / 2.0
                l_ini, l_fin = long_total * m, long_total * (1.0 - m)

            # ── Construir columnas pixel a pixel ─────────────────────────
            # Paso 1: recopilar todos los valores y posiciones del anillo
            cols_vals = []   # valor medio del canal en cada columna
            cols_pts  = []   # (sup, inf) QPointF para cada columna
            cols_activa = [] # bool: está dentro del rango l_ini..l_fin

            acum = 0.0
            for ip, ic in segs:
                x0, y0 = coords[ip]
                x1, y1 = coords[ic]
                seg_len = math.hypot(x1-x0, y1-y0)
                if seg_len < 1:
                    continue
                ux = (x1-x0)/seg_len; uy = (y1-y0)/seg_len
                perp_x, perp_y = -uy, ux

                n_s = max(2, int(round(seg_len)))
                for j in range(n_s):
                    t_j   = j / max(1, n_s-1)
                    pos_j = acum + j * (seg_len / max(1, n_s-1))
                    cx = x0 + t_j*(x1-x0)
                    cy = y0 + t_j*(y1-y0)
                    sup = QPointF(cx + banda*perp_x, cy + banda*perp_y)
                    inf = QPointF(cx - banda*perp_x, cy - banda*perp_y)

                    activa = l_ini <= pos_j <= l_fin
                    if activa:
                        offs = np.arange(-banda, banda+1)
                        xs = np.clip(cx + offs*perp_x, 0, w_img-1).astype(np.int32)
                        ys = np.clip(cy + offs*perp_y, 0, h_img-1).astype(np.int32)
                        cols_vals.append(float(ch_img[ys, xs].mean()))
                    else:
                        cols_vals.append(None)
                    cols_pts.append((sup, inf))
                    cols_activa.append(activa)
                acum += seg_len

            if not any(cols_activa):
                continue

            # Paso 2: normalizar al rango del anillo para maximizar contraste
            vals_activos = [v for v in cols_vals if v is not None]
            v_min = min(vals_activos)
            v_max = max(vals_activos)
            v_rng = v_max - v_min if v_max > v_min else 1.0

            # Paso 3: dibujar polígono por columna con color normalizado
            prev_pts = None
            for k, (sup, inf) in enumerate(cols_pts):
                if not cols_activa[k]:
                    prev_pts = None
                    continue
                # Normalizar al rango 40-255 para que siempre se vea algo
                v_norm = 40 + int(215 * (cols_vals[k] - v_min) / v_rng)
                color = _rgba(v_norm)
                brush = QBrush(color)

                if prev_pts is not None:
                    p_sup_ant, p_inf_ant = prev_pts
                    poly = QPolygonF([p_sup_ant, sup, inf, p_inf_ant])
                    item = escena.addPolygon(poly, pen_sin, brush)
                    item.setZValue(5)
                    items.append(item)
                prev_pts = (sup, inf)

            # Borde exterior del área (polígono de contorno)
            # Reconstruir los puntos del borde para el contorno
            acum = 0.0
            pts_sup, pts_inf = [], []
            for ip, ic in segs:
                x0, y0 = coords[ip]
                x1, y1 = coords[ic]
                seg_len = math.hypot(x1-x0, y1-y0)
                if seg_len < 1:
                    continue
                ux = (x1-x0)/seg_len; uy = (y1-y0)/seg_len
                perp_x, perp_y = -uy, ux
                n_s = max(2, int(round(seg_len)))
                for j in range(n_s):
                    t_j   = j / max(1, n_s-1)
                    pos_j = acum + j*(seg_len/max(1, n_s-1))
                    if pos_j < l_ini or pos_j > l_fin:
                        continue
                    cx = x0 + t_j*(x1-x0)
                    cy = y0 + t_j*(y1-y0)
                    pts_sup.append(QPointF(cx + banda*perp_x, cy + banda*perp_y))
                    pts_inf.append(QPointF(cx - banda*perp_x, cy - banda*perp_y))
                acum += seg_len

            if len(pts_sup) >= 2:
                poly_borde = QPolygonF(pts_sup + list(reversed(pts_inf)))
                borde = escena.addPolygon(
                    poly_borde, pen_borde, QBrush(Qt.BrushStyle.NoBrush))
                borde.setZValue(6)
                items.append(borde)
