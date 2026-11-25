"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtCore import Qt
from estilos import color_secundario

def _anotar_anios_en_lista(self):
    """Recorre todas las series de la lista y anota en cada item su
    rango de años como tooltip. Si el último año de una serie supera
    el año actual (presente), marca el item con color de advertencia
    y un símbolo ⚠️ en el tooltip.

    Esto es importante sobre todo para series flotantes: cuando se les
    asigna un año de inicio, el último año puede quedar más allá del
    presente, lo que es físicamente imposible (un árbol no tiene
    anillos en el futuro) y delata un año de inicio mal asignado.
    """
    import datetime
    anio_actual = datetime.datetime.now().year

    # Colores de advertencia según el tema (claro/oscuro). Usamos un
    # naranja/rojo que contraste en ambos.
    COLOR_ADVERTENCIA = QColor("#e67e22")  # naranja
    # Color de texto normal heredado del tema actual de la lista
    COLOR_NORMAL = self.lista_series.palette().color(
        QPalette.ColorRole.Text)

    for i in range(self.lista_series.count()):
        item = self.lista_series.item(i)
        nombre = item.text()
        df = self.series_datos.get(nombre)
        if df is None or df.empty:
            item.setToolTip("Serie sin datos")
            continue

        try:
            anio_min = int(df.index.min())
            anio_max = int(df.index.max())
        except (ValueError, TypeError):
            item.setToolTip("Rango de años no disponible")
            continue

        n_anios = anio_max - anio_min + 1
        tooltip = (f"Años: {anio_min} – {anio_max}  ({n_anios} años)")

        # Para la cronología activa (📚), anteponer su tipo (RES/STD/RAW)
        # para que el usuario sepa en qué espacio está.
        if (nombre.startswith("📚") and
                nombre.replace("📚 ", "").strip() == self._nombre_cronologia_activa):
            tag = getattr(self, "_tag_tipo_cronologia", "") or {
                "residual": "RES", "standard": "STD", "raw": "RAW"}.get(
                ((self.meta_cronologia or {}).get("tipo_cronologia") or "").lower(), "")
            if tag:
                nombre_tipo = {"RES": "residual", "STD": "standard",
                               "RAW": "cruda"}.get(tag, "")
                tooltip = (f"Cronología · tipo {tag} ({nombre_tipo})\n"
                           + tooltip)

        if anio_max > anio_actual:
            # El último año supera el presente → advertencia
            exceso = anio_max - anio_actual
            tooltip += (
                f"\n\n⚠️ El último año ({anio_max}) supera el año actual "
                f"({anio_actual}) por {exceso} año(s).\n"
                f"Si es una serie flotante, revisa el año de inicio "
                f"asignado: probablemente está corrido hacia el futuro."
            )
            item.setForeground(COLOR_ADVERTENCIA)
        else:
            # Restaurar color normal del tema
            item.setForeground(COLOR_NORMAL)

        item.setToolTip(tooltip)


def _dibujar_barras_desviacion(self, series: list):
    """Dibuja las series como barras que salen de su MEDIA.

    La media de cada serie es el eje central: la barra sube cuando el
    año está sobre la media y baja cuando está bajo la media. Con varias
    series marcadas, las barras del mismo año se reparten lado a lado
    para que no se tapen.
    """
    n = len(series)
    # Ancho total ocupado por año (0.8 deja aire entre años).
    ancho_total = 0.8
    ancho_barra = ancho_total / n
    # Desplazamiento para centrar el grupo de barras en el año.
    offset_base = -ancho_total / 2 + ancho_barra / 2

    for k, (nombre, valores, color) in enumerate(series):
        anios = valores.index.to_numpy(dtype=float)
        vals = valores.to_numpy(dtype=float)
        media = float(np.nanmean(vals))
        desv = vals - media

        # Verde sobre la media, rojo bajo la media. Con una sola serie se
        # usa ese código de color (más legible); con varias se usa el
        # color de la serie para poder distinguirlas entre sí.
        if n == 1:
            brushes = ["#c0392b" if d < 0 else "#27ae60" for d in desv]
        else:
            brushes = [color] * len(desv)

        x = anios + (offset_base + k * ancho_barra)
        barras = pg.BarGraphItem(
            x=x, height=desv, width=ancho_barra * 0.9, y0=media,
            brushes=brushes, pen=pg.mkPen(None),
        )
        self.grafico.addItem(barras)

        # Línea de la media (el "eje" de la serie), punteada en su color.
        linea = pg.InfiniteLine(
            pos=media, angle=0,
            pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine),
        )
        self.grafico.addItem(linea)

        # Entrada de leyenda (BarGraphItem no la agrega solo).
        try:
            muestra = pg.PlotDataItem(pen=pg.mkPen(color, width=6))
            self.grafico.plotItem.legend.addItem(muestra, nombre)
        except Exception:
            pass


def _poblar_tabla(self, sugerencias: list[dict], es_marginal: bool = False):
    """Rellena la tabla de sugerencias.

    es_marginal=True indica que las correcciones están por debajo del umbral
    de significancia (probable ruido). Se muestran como sanity-check con
    una advertencia visible.
    """
    self.tabla_sugerencias.setRowCount(0)
    self.btn_aplicar.setEnabled(False)

    # Mensaje de estado de la sección
    # Cabecera con el DIAGNÓSTICO: qué tramo está bien fechado y de qué
    # tipo es el problema. Va antes que la lista de correcciones porque
    # cambia cómo hay que leerla.
    diag = getattr(self, "_diagnostico_datacion", None)
    cabecera = ""
    if diag:
        tipo = diag.get("diagnostico")
        msg = diag.get("mensaje", "")
        if tipo == "bien_fechada":
            cabecera = ("<span style='color:#5cb85c;'>✓ <b>Serie bien fechada</b>"
                        "</span><br><span style='font-size:9px;'>" + msg + "</span><br><br>")
        elif tipo == "desfase_global":
            cabecera = ("<span style='color:#d9534f;'>⚠️ <b>Desfase de toda la "
                        "serie</b></span><br><span style='font-size:9px;'>" + msg +
                        "<br><b>Revisa el año base antes de insertar o quitar "
                        "anillos.</b></span><br><br>")
        elif tipo == "error_interno":
            cabecera = ("<span style='color:#f0ad4e;'>🎯 <b>Error localizado</b>"
                        "</span><br><span style='font-size:9px;'>" + msg +
                        "</span><br><br>")
        elif tipo == "ambiguo":
            cabecera = (f"<span style='color:{color_secundario()};'><b>Diagnóstico no concluyente</b>"
                        "</span><br><span style='font-size:9px;'>" + msg +
                        "</span><br><br>")

    if hasattr(self, "lbl_estado_sug"):
        if not sugerencias:
            self.lbl_estado_sug.setText(
                cabecera +
                "<span style='color:#5cb85c;'>✓ <b>Sin correcciones sugeridas.</b></span><br>"
                "<span style='font-size:9px;'>La serie parece estar correctamente cofechada "
                "contra la referencia en esta ventana de análisis.</span>"
            )
            self.lbl_estado_sug.setVisible(True)
        elif es_marginal:
            self.lbl_estado_sug.setText(
                cabecera +
                "<span style='color:#f0ad4e;'>⚠️ <b>Sugerencias marginales</b></span> "
                "<span style='font-size:9px;'>(Δr &lt; 0.05)</span><br>"
                "<span style='font-size:9px;'>No hay correcciones significativas. "
                "Estos cambios podrían ser ruido estadístico. Si la serie ya está "
                "cofechada, probablemente no necesitas aplicar ninguno.</span>"
            )
            self.lbl_estado_sug.setVisible(True)
        else:
            n = len(sugerencias)
            self.lbl_estado_sug.setText(
                cabecera +
                f"<span style='color:#5cb85c;'>"
                f"<b>{n} corrección(es) significativa(s)</b> encontrada(s).</span><br>"
                "<span style='font-size:9px;'>Click en una fila para previsualizar "
                "el cambio antes de aplicarlo.</span>"
            )
            self.lbl_estado_sug.setVisible(True)

    # Auto-expandir la sección si hay algo que mostrar
    if (sugerencias or es_marginal) and hasattr(self, "sec_sug"):
        self.sec_sug.expandir()

    font_bold = QFont()
    font_bold.setBold(True)

    for sug in sugerencias:
        row = self.tabla_sugerencias.rowCount()
        self.tabla_sugerencias.insertRow(row)

        delta_r = sug["delta_r"]
        if es_marginal:
            # Filas marginales: fondo gris-naranja muy tenue
            bg = QColor(240, 173, 78, 50)
        elif delta_r >= 0.10:
            bg = QColor(80, 180, 80, 120)
        elif delta_r >= 0.05:
            bg = QColor(180, 220, 80, 80)
        else:
            bg = QColor(220, 200, 80, 60)

        if sug.get("origen") in ("quiebre", "zona"):
            # Estas vienen de localizar el quiebre, no de probar
            # correcciones a ciegas: se distinguen para que el usuario
            # sepa de dónde sale el año.
            bg = (QColor(60, 160, 220, 130) if sug.get("confiable")
                  else QColor(60, 160, 220, 60))

        signo = "+" if sug["delta"] > 0 else ""
        marca = ""
        if sug.get("origen") == "quiebre":
            marca = " ◆" if sug.get("confiable") else " ◇"
        elif sug.get("origen") == "zona":
            marca = " ◇"
        valores = [
            str(int(sug["anio"])) + marca,
            f"{signo}{sug['delta']} anillo(s)",
            self._fmt_r(sug["r_antes"]),
            self._fmt_r(sug["r_tras"]),
            f"+{delta_r:.3f}",
        ]
        for col, val in enumerate(valores):
            celda = QTableWidgetItem(val)
            celda.setBackground(bg)
            celda.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 4:
                celda.setFont(font_bold)
            self.tabla_sugerencias.setItem(row, col, celda)
