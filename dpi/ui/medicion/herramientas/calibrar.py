"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import math
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from dpi.medicion.constantes import MM_POR_PULGADA
from dpi.ui.colores import COLOR_CALIBRACION
from dpi.medicion.marcas import ModoMedicion
from dpi.ui.medicion.calibracion import DialogoCalibracionRegla

def _limpiar_items_calibracion(self):
    """Elimina puntos / línea / texto de una calibración previa."""
    for item in self._calibracion.items:
        try:
            self.scene().removeItem(item)
        except Exception:
            pass
    self._calibracion.items.clear()
    self._calibracion.puntos = []


def iniciar_calibracion(self, objetivo_mm: float | None = None):
    """Inicia el modo de calibración por regla.

    Flujo:
      1. Si había marcas de calibración anteriores, se borran (nueva
         calibración reemplaza la anterior).
      2. Click 1 → marca punto inicial
      3. Click 2 → marca punto final + dibuja línea con distancia en px,
         luego pregunta los mm (QInputDialog)
      4. Si OK: aplica calibración. Las marcas SE MANTIENEN como
         recordatorio visual de que la imagen está calibrada (etiqueta
         cambia a "✓ Calibrada: X px = Y mm").
      5. Si Cancel: se borran las marcas (no hubo calibración).
    """
    # Limpiar marcas de calibración anteriores (puntos, línea, texto)
    # para evitar que se acumulen en la imagen tras múltiples usos.
    # Las marcas de la calibración previa se reemplazan por las nuevas.
    self._limpiar_items_calibracion()

    self.cambiar_modo(ModoMedicion.CALIBRAR)
    self._calibracion.objetivo_mm = objetivo_mm
    # Forzar foco en la vista para que el primer click se registre
    # directamente como mousePressEvent en la vista.
    self.setFocus()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()


def _paso_calibracion(self, x, y):
    """Procesa los clicks de calibración.

    Flujo:
      - Click 1: marca el punto inicial
      - Click 2: marca el punto final + dibuja línea + pregunta los mm
                 → aplica calibración y limpia las marcas
    """
    self._calibracion.puntos.append((x, y))

    # Dibujar el círculo del punto y agregar a la lista limpiable
    marker = self.scene().addEllipse(
        x - 5, y - 5, 10, 10,
        self._pen_calibracion, QBrush(QColor(COLOR_CALIBRACION)))
    marker.setZValue(500)
    self._calibracion.items.append(marker)

    # Solo hay un punto: pedir el segundo
    if len(self._calibracion.puntos) == 1:
        try:
            self.estado_cambiado.emit(
                "📏 Calibración: Haz clic en el segundo punto (final de la distancia conocida).")
        except Exception:
            pass
        return

    # Ya tenemos los 2 puntos
    p1, p2 = self._calibracion.puntos
    dist_px = math.dist(p1, p2)

    # Dibujar la línea entre los 2 puntos
    pen_linea = QPen(QColor(COLOR_CALIBRACION))
    pen_linea.setCosmetic(True)
    pen_linea.setWidthF(2.5)
    pen_linea.setStyle(Qt.PenStyle.SolidLine)
    linea = self.scene().addLine(p1[0], p1[1], p2[0], p2[1], pen_linea)
    linea.setZValue(499)
    self._calibracion.items.append(linea)

    # Etiqueta con la distancia, posicionada PEGADA AL BORDE INTERNO
    # de la imagen (el borde más cercano a la línea de calibración).
    # Quedaba afuera de la imagen porque calculábamos offsets estimados
    # (22 px de alto, etc.) — ahora usamos el boundingRect REAL del
    # texto después de setear el HTML para posicionarlo con precisión.
    from PyQt6.QtWidgets import QGraphicsItem

    # Crear el texto primero (necesario para conocer su tamaño)
    texto = self.scene().addText("")
    texto.setHtml(
        f"<div style='background:rgba(0,0,0,200); color:{COLOR_CALIBRACION}; "
        f"padding:2px 5px; border-radius:3px; font-size:12px; "
        f"font-weight:bold; font-family:Arial; white-space:nowrap;'>"
        f"📏 {dist_px:.1f} px"
        f"</div>"
    )
    texto.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    rect = texto.boundingRect()  # en píxeles de pantalla (por el flag)
    # Tamaño real del badge, no estimado
    rect_w_px = rect.width()
    rect_h_px = rect.height()

    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2

    # Bordes de la imagen (sceneRect coincide con la imagen — ver
    # _cargar_imagen donde se hace setSceneRect(0, 0, w, h)).
    scene_rect = self.scene().sceneRect()
    left, top = scene_rect.left(), scene_rect.top()
    right, bottom = scene_rect.right(), scene_rect.bottom()

    # Distancias del punto medio a cada borde
    d_top = my - top
    d_bottom = bottom - my
    d_left = mx - left
    d_right = right - mx
    min_d = min(d_top, d_bottom, d_left, d_right)

    # Margen INTERNO (en píxeles de pantalla) desde el borde de la
    # imagen. Garantiza que el badge entero queda DENTRO del rectángulo
    # de la imagen, independiente del zoom.
    MARGEN_INTERNO_PX = 6.0
    escala = self._escala_vista()

    # Convertir píxeles de pantalla a unidades de escena para colocar
    # el setPos en el lugar correcto. El badge ocupa rect_w_px x
    # rect_h_px en PANTALLA. La posición es la esquina top-left del
    # badge en coords de escena.
    rect_w_escena = rect_w_px * escala
    rect_h_escena = rect_h_px * escala
    margen_escena = MARGEN_INTERNO_PX * escala

    if min_d == d_top:
        # Borde superior: badge contra el borde superior, centrado en mx
        label_x = mx - rect_w_escena / 2.0
        label_y = top + margen_escena
    elif min_d == d_bottom:
        # Borde inferior: badge JUSTO ENCIMA del borde, alineado a su
        # base con (bottom - margen). Es decir, top-left.y = bottom -
        # rect_h - margen.
        label_x = mx - rect_w_escena / 2.0
        label_y = bottom - rect_h_escena - margen_escena
    elif min_d == d_left:
        # Borde izquierdo: badge contra el borde izquierdo, centrado
        # verticalmente en my
        label_x = left + margen_escena
        label_y = my - rect_h_escena / 2.0
    else:
        # Borde derecho: badge contra el borde derecho, top-left.x =
        # right - rect_w - margen
        label_x = right - rect_w_escena - margen_escena
        label_y = my - rect_h_escena / 2.0

    # Clamping defensivo: si por alguna razón el cálculo se desbordó,
    # forzar la posición a quedar dentro del sceneRect.
    label_x = max(left + margen_escena,
                  min(label_x, right - rect_w_escena - margen_escena))
    label_y = max(top + margen_escena,
                  min(label_y, bottom - rect_h_escena - margen_escena))

    texto.setPos(label_x, label_y)
    texto.setZValue(501)
    self._calibracion.items.append(texto)

    # Forzar repintado para que el usuario VEA la línea y la distancia
    # antes de que aparezca el diálogo
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()

    # Si ya teníamos un objetivo_mm pre-cargado (flujo viejo) lo usamos.
    # En el flujo nuevo es None, así que preguntamos al usuario.
    objetivo = self._calibracion.objetivo_mm
    if objetivo and objetivo > 0:
        dist_mm = objetivo
        ok = True
    else:
        dlg = DialogoCalibracionRegla(self.window())
        dlg.setWindowTitle(f"Calibración (línea = {dist_px:.1f} px)")
        if dlg.exec():
            dist_mm = dlg.obtener_mm()
            ok = (dist_mm > 0)
        else:
            dist_mm = 0
            ok = False

    if ok and dist_mm > 0:
        self.pixeles_por_mm = dist_px / dist_mm
        # Marcar el origen del DPI como "calibrado por regla"
        # para que el diálogo de info lo refleje correctamente.
        try:
            self.origen_calibracion_cambiado.emit("regla")
        except Exception:
            pass
        QMessageBox.information(
            self.window(), "Calibración aplicada",
            f"  {dist_px:.2f} px = {dist_mm:.3f} mm\n"
            f"  1 mm = {self.pixeles_por_mm:.2f} px\n"
            f"  ≈ {self.pixeles_por_mm * MM_POR_PULGADA:.0f} DPI"
        )
        # La señal sincroniza años, gráfico y escena antes del guardado.
        self.recalcular_todas_las_distancias()
        self.guardado_solicitado.emit()
        # Actualizar la etiqueta de la línea con los mm calibrados así
        # el usuario tiene un recordatorio visual de que la imagen
        # ya está calibrada y a qué escala.
        self._actualizar_etiqueta_calibracion(dist_px, dist_mm)
    else:
        # Si canceló el diálogo, limpiar las marcas (no hubo calibración)
        self._limpiar_items_calibracion()

    self._calibracion.objetivo_mm = None
    self._cambiar_modo_usuario(ModoMedicion.MEDIR)
    self.progreso_modificado.emit()


def _actualizar_etiqueta_calibracion(self, dist_px: float, dist_mm: float):
    """Reemplaza el texto de "📏 X px" por "✓ Calibrada: X mm = Y px"
    para que el usuario sepa que la calibración ya está aplicada.
    Las marcas (puntos y línea) se mantienen como recordatorio visual.

    El texto usa ItemIgnoresTransformations para tamaño constante en
    pantalla independiente del zoom.
    """
    from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsItem
    for i, item in enumerate(self._calibracion.items):
        if isinstance(item, QGraphicsTextItem):
            item.setHtml(
                f"<div style='background:rgba(0,0,0,200); "
                f"color:{COLOR_CALIBRACION}; "
                f"padding:2px 5px; border-radius:3px; font-size:12px; "
                f"font-weight:bold; font-family:Arial; white-space:nowrap;'>"
                f"✓ Calibrada: {dist_px:.1f} px = {dist_mm:.2f} mm"
                f"</div>"
            )
            # Asegurar el flag (por si vino de una versión vieja sin él)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True)
            break
