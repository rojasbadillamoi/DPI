"""
estilos_graficos.py — Paletas de color de los gráficos de DPI.

Las cuatro paletas vienen de Veta (`veta/plot.py`, diccionario `TEMAS`), de la
misma suite MoiCedrus, y se conservan con sus mismos nombres y valores para que
una figura exportada desde DPI y otra desde Veta se vean como parte del mismo
trabajo.

Hay dos usos, y conviene no confundirlos:

  · `aplicar_a_pyqtgraph` pinta el gráfico VIVO, el que se ve en pantalla.
    Se llama al construirlo y cada vez que la app cambia de tema claro/oscuro.

  · `exportar_figura` re-dibuja los mismos datos con matplotlib al momento de
    descargar. No es una captura de pantalla: se rehace el gráfico, así que la
    salida sirve para publicar (vectorial en SVG/PDF, o PNG a la resolución que
    se pida) y puede usar una paleta distinta de la que se está viendo —por
    ejemplo trabajar en oscuro y exportar en Claro o Sepia para una revista.

matplotlib se importa DENTRO de `exportar_figura`, no al cargar el módulo:
solo hace falta al exportar y es la dependencia más pesada del programa; así
abrir DPI no paga ese costo.
"""

from __future__ import annotations

# Nombre de paleta ↔ colores. `mapa` es el colormap para gráficos coloreados
# por valor; `series` es el ciclo de colores cuando se dibuja más de una curva.
PALETAS: dict[str, dict] = {
    "Claro": {
        "fondo": "#ffffff", "texto": "#222222", "rejilla": "#cccccc",
        "linea": "#2b6cb0", "acento": "#c05621", "mapa": "viridis",
        "series": ["#2b6cb0", "#c05621", "#2f855a", "#6b46c1", "#b7791f"],
    },
    "Oscuro": {
        "fondo": "#1e1e1e", "texto": "#e8e8e8", "rejilla": "#555555",
        "linea": "#6aa9ff", "acento": "#ffa657", "mapa": "viridis",
        "series": ["#6aa9ff", "#ffa657", "#5cb85c", "#c792ea", "#ffd54f"],
    },
    "Alto contraste": {
        "fondo": "#000000", "texto": "#ffffff", "rejilla": "#666666",
        "linea": "#4fc3f7", "acento": "#ffd54f", "mapa": "turbo",
        "series": ["#4fc3f7", "#ffd54f", "#69f0ae", "#ff8a80", "#b388ff"],
    },
    "Sepia": {
        "fondo": "#f4efe6", "texto": "#3b332a", "rejilla": "#cbbfa8",
        "linea": "#2b6cb0", "acento": "#a04000", "mapa": "cividis",
        "series": ["#2b6cb0", "#a04000", "#40724c", "#6b4d8a", "#8a6d1f"],
    },
}

PALETA_POR_DEFECTO = "Claro"


def paleta(nombre: str | None = None) -> dict:
    """Devuelve la paleta pedida, cayendo en la de por omisión si no existe."""
    return PALETAS.get(nombre or "", PALETAS[PALETA_POR_DEFECTO])


def nombre_para_tema_app(oscuro: bool) -> str:
    """Paleta que le corresponde al tema claro/oscuro de la aplicación."""
    return "Oscuro" if oscuro else "Claro"


def _app_en_oscuro() -> bool:
    """¿La app está en tema oscuro? Se deduce de la paleta Qt, que es la
    fuente única de verdad desde que `estilos.aplicar_tema` la fija."""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette
        app = QApplication.instance()
        if app is None:
            return False
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    except Exception:
        return False


def nombre_paleta_actual() -> str:
    """Paleta que corresponde al tema que la app tiene puesto ahora."""
    return nombre_para_tema_app(_app_en_oscuro())


# --------------------------------------------------------------------------
# Gráfico vivo (pyqtgraph)
# --------------------------------------------------------------------------

def aplicar_a_pyqtgraph(widget, nombre: str | None = None) -> None:
    """Pinta un `pg.PlotWidget` con la paleta indicada.

    Sin esto los gráficos se quedaban con los colores por omisión de
    pyqtgraph —fondo negro y ejes gris claro— aunque la app estuviera en tema
    claro, que es justamente lo que se veía mal.

    Los colores de las CURVAS no se tocan acá: los elige quien dibuja, y cada
    módulo tiene su código de colores con significado (naranja = Raw,
    azul = Standard, verde = Residual). Acá va solo el «papel»: fondo, ejes,
    rótulos, título y rejilla.
    """
    if widget is None:
        return
    p = paleta(nombre or nombre_paleta_actual())
    try:
        widget.setBackground(p["fondo"])
        item = widget.getPlotItem()
        for lado in ("left", "bottom", "right", "top"):
            eje = item.getAxis(lado)
            if eje is None:
                continue
            eje.setPen(p["rejilla"])
            eje.setTextPen(p["texto"])
        # El título es un HTML aparte: hay que reponerlo con el color nuevo,
        # porque setTitle sin color deja el que tenía.
        titulo = item.titleLabel.text if item.titleLabel is not None else ""
        if titulo:
            item.setTitle(titulo, color=p["texto"])
        leyenda = item.legend
        if leyenda is not None:
            leyenda.setLabelTextColor(p["texto"])
            try:
                leyenda.setBrush(p["fondo"])
                leyenda.setPen(p["rejilla"])
            except Exception:
                pass   # versiones viejas de pyqtgraph no traen setBrush/setPen
    except Exception:
        # Un gráfico mal pintado no puede tumbar la ventana que lo contiene.
        import logging
        logging.getLogger(__name__).exception("No se pudo aplicar la paleta")


def aplicar_a_todos(raiz, nombre: str | None = None) -> int:
    """Pinta TODOS los gráficos que cuelgan de `raiz`. Devuelve cuántos.

    Se recorre el árbol de widgets en vez de nombrar cada gráfico uno por uno
    porque una pestaña puede tener varios —el principal, el de correlación
    móvil, el del perfil— y los que se agreguen después quedarían sin pintar
    si hubiera que acordarse de añadirlos a una lista.
    """
    if raiz is None:
        return 0
    try:
        import pyqtgraph as pg
        graficos = raiz.findChildren(pg.PlotWidget)
    except Exception:
        return 0
    for w in graficos:
        aplicar_a_pyqtgraph(w, nombre)
    return len(graficos)


def curvas_desde_pyqtgraph(widget) -> list[dict]:
    """Lee las curvas que ya están dibujadas en un `pg.PlotWidget`.

    Se leen del gráfico en vez de rearmarlas desde los datos de origen para
    que lo exportado sea exactamente lo que el usuario está viendo —incluidas
    las series que haya ocultado con la leyenda— y para no tener que duplicar,
    en cada ventana, la lógica de qué se dibuja y con qué color.
    """
    import pyqtgraph as pg

    curvas: list[dict] = []
    if widget is None:
        return curvas
    item = widget.getPlotItem()
    for d in item.listDataItems():
        try:
            if not d.isVisible():
                continue           # respetar lo ocultado desde la leyenda
            x, y = d.getData()
            if x is None or y is None or len(x) == 0:
                continue
            color, estilo, ancho = None, "-", 1.6
            lapiz = (getattr(d, "opts", {}) or {}).get("pen")
            if lapiz is not None:
                qpen = pg.mkPen(lapiz)
                color = qpen.color().name()
                if qpen.width():
                    ancho = max(0.8, qpen.width() * 0.8)
                from PyQt6.QtCore import Qt as _Qt
                if qpen.style() in (_Qt.PenStyle.DashLine, _Qt.PenStyle.DashDotLine):
                    estilo = "--"
                elif qpen.style() == _Qt.PenStyle.DotLine:
                    estilo = ":"
            curvas.append({
                "nombre": _nombre_de_item(d),
                "x": list(x), "y": list(y),
                "color": color, "estilo": estilo, "ancho": ancho,
            })
        except Exception:
            continue               # una curva rara no debe impedir exportar
    return curvas


def _nombre_de_item(d) -> str:
    try:
        n = d.name()
    except Exception:
        n = None
    return str(n) if n else ""


def textos_desde_pyqtgraph(widget) -> dict:
    """Título y rótulos de ejes del gráfico, para reusarlos en la figura."""
    datos = {"titulo": "", "etiqueta_x": "", "etiqueta_y": ""}
    try:
        item = widget.getPlotItem()
        if item.titleLabel is not None:
            datos["titulo"] = item.titleLabel.text or ""
        datos["etiqueta_x"] = item.getAxis("bottom").labelText or ""
        datos["etiqueta_y"] = item.getAxis("left").labelText or ""
    except Exception:
        pass
    return datos


# --------------------------------------------------------------------------
# Exportación (matplotlib)
# --------------------------------------------------------------------------

FORMATOS = ("png", "svg", "pdf")


def exportar_figura(curvas, ruta: str, *, nombre_paleta: str = "Claro",
                    titulo: str = "", etiqueta_x: str = "Año",
                    etiqueta_y: str = "", dpi: int = 300,
                    lineas_h=(), ancho_cm: float = 24.0,
                    alto_cm: float = 12.0) -> str:
    """Re-dibuja `curvas` con matplotlib y guarda el archivo. Devuelve la ruta.

    `curvas` es una lista de diccionarios:
        {"nombre": str, "x": secuencia, "y": secuencia,
         "color": str | None, "estilo": "-" | "--", "ancho": float}
    Si `color` viene vacío se toma del ciclo de la paleta.

    `lineas_h` son líneas horizontales de referencia, como el umbral 0.85 del
    EPS: una secuencia de `(y, etiqueta)`.
    """
    # Backend sin ventana: exportar no debe abrir nada ni pelear con Qt por
    # el hilo de interfaz.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    p = paleta(nombre_paleta)
    cm = 1 / 2.54
    fig = Figure(figsize=(ancho_cm * cm, alto_cm * cm), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    fig.patch.set_facecolor(p["fondo"])
    ax.set_facecolor(p["fondo"])

    ciclo = p["series"]
    for i, c in enumerate(curvas):
        ax.plot(
            c["x"], c["y"],
            color=c.get("color") or ciclo[i % len(ciclo)],
            linestyle=c.get("estilo", "-"),
            linewidth=c.get("ancho", 1.6),
            label=c.get("nombre") or None,
        )

    # Las líneas de referencia van en el color del TEXTO y atenuadas, no en el
    # de acento: el acento es el segundo color del ciclo de series, así que un
    # umbral quedaba idéntico a una curva de datos y se confundían.
    for y, etiqueta in lineas_h:
        ax.axhline(y, color=p["texto"], linestyle="--", linewidth=1.0, alpha=0.55)
        if etiqueta:
            ax.text(0.012, y, etiqueta, transform=ax.get_yaxis_transform(),
                    ha="left", va="bottom", fontsize=8,
                    color=p["texto"], alpha=0.75)

    if titulo:
        ax.set_title(titulo, color=p["texto"])
    ax.set_xlabel(etiqueta_x, color=p["texto"])
    ax.set_ylabel(etiqueta_y, color=p["texto"])
    ax.tick_params(colors=p["texto"], which="both")
    for lado in ax.spines.values():
        lado.set_color(p["rejilla"])
    # Sin rejilla: la cuadrícula de fondo compite con las curvas y ensucia la
    # figura cuando se lleva a un documento. Los ejes ya dan la referencia.
    ax.grid(False)

    if any(c.get("nombre") for c in curvas):
        leg = ax.legend(frameon=True, fontsize=9)
        leg.get_frame().set_facecolor(p["fondo"])
        leg.get_frame().set_edgecolor(p["rejilla"])
        for t in leg.get_texts():
            t.set_color(p["texto"])

    fig.tight_layout()
    # facecolor explícito: sin esto matplotlib guarda con fondo blanco aunque
    # la figura sea oscura, y las paletas oscuras salían con marco blanco.
    fig.savefig(ruta, dpi=dpi, facecolor=p["fondo"], edgecolor="none")
    return ruta


# --------------------------------------------------------------------------
# Diálogo de descarga
# --------------------------------------------------------------------------

# Lo elegido al guardar una figura se recuerda entre sesiones. Quien exporta
# una figura casi siempre exporta varias seguidas, con la misma paleta, el
# mismo formato y a la misma carpeta; volver a fijarlo cada vez era puro ruido.
_CLAVE = "graficos"


def _ajustes():
    from PyQt6.QtCore import QSettings
    return QSettings("MoiCedrus", "DPI")


def _carpeta_recordada() -> str:
    import os
    ruta = _ajustes().value(f"{_CLAVE}/carpeta", "", type=str)
    return ruta if ruta and os.path.isdir(ruta) else ""


def _recordar_carpeta(carpeta: str):
    import os
    if carpeta and os.path.isdir(carpeta):
        _ajustes().setValue(f"{_CLAVE}/carpeta", carpeta)


def _preferencias() -> dict:
    a = _ajustes()
    return {
        "paleta": a.value(f"{_CLAVE}/paleta", "", type=str),
        "formato": a.value(f"{_CLAVE}/formato", "png", type=str),
        "dpi": a.value(f"{_CLAVE}/dpi", 300, type=int),
        "ancho": a.value(f"{_CLAVE}/ancho", 24.0, type=float),
        "alto": a.value(f"{_CLAVE}/alto", 12.0, type=float),
    }


def _recordar_preferencias(paleta, formato, dpi, ancho, alto):
    a = _ajustes()
    a.setValue(f"{_CLAVE}/paleta", paleta)
    a.setValue(f"{_CLAVE}/formato", formato)
    a.setValue(f"{_CLAVE}/dpi", int(dpi))
    a.setValue(f"{_CLAVE}/ancho", float(ancho))
    a.setValue(f"{_CLAVE}/alto", float(alto))

def exportar_grafico_con_dialogo(parent, widget_grafico, *,
                                 nombre_sugerido: str = "grafico",
                                 carpeta_inicial: str = "",
                                 lineas_h=()) -> str | None:
    """Pide paleta, formato y resolución, y guarda el gráfico. Devuelve la ruta.

    Devuelve None si el usuario cancela o si el gráfico está vacío.
    """
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
        QDialogButtonBox, QFileDialog, QMessageBox, QLabel, QDoubleSpinBox,
    )
    import os

    curvas = curvas_desde_pyqtgraph(widget_grafico)
    if not curvas:
        QMessageBox.information(
            parent, "Nada que exportar",
            "El gráfico está vacío. Generá o cargá datos antes de descargarlo.")
        return None

    dlg = QDialog(parent)
    dlg.setWindowTitle("Descargar gráfico")
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(
        f"<b>{len(curvas)} curva(s)</b> en el gráfico. Se vuelve a dibujar "
        "para la descarga, así que<br>la calidad no depende del tamaño de la "
        "ventana."))
    form = QFormLayout()

    pref = _preferencias()

    cmb_paleta = QComboBox()
    cmb_paleta.addItems(list(PALETAS))
    # La paleta usada la última vez; si es la primera, la que corresponde al
    # tema que el usuario tiene puesto.
    cmb_paleta.setCurrentText(pref["paleta"] if pref["paleta"] in PALETAS
                              else nombre_paleta_actual())
    form.addRow("Paleta de colores:", cmb_paleta)

    cmb_fmt = QComboBox()
    cmb_fmt.addItem("PNG (imagen)", "png")
    cmb_fmt.addItem("SVG (vectorial, editable)", "svg")
    cmb_fmt.addItem("PDF (vectorial)", "pdf")
    _i = cmb_fmt.findData(pref["formato"])
    if _i >= 0:
        cmb_fmt.setCurrentIndex(_i)
    form.addRow("Formato:", cmb_fmt)

    spin_dpi = QSpinBox()
    spin_dpi.setRange(72, 1200)
    spin_dpi.setSingleStep(50)
    spin_dpi.setValue(pref["dpi"])   # 300 dpi es lo que piden casi todas las revistas
    spin_dpi.setToolTip("Solo afecta al PNG; SVG y PDF son vectoriales.")
    form.addRow("Resolución (dpi):", spin_dpi)

    spin_ancho = QDoubleSpinBox()
    spin_ancho.setRange(6.0, 60.0)
    spin_ancho.setValue(pref["ancho"])
    spin_ancho.setSuffix(" cm")
    form.addRow("Ancho:", spin_ancho)

    spin_alto = QDoubleSpinBox()
    spin_alto.setRange(4.0, 40.0)
    spin_alto.setValue(pref["alto"])
    spin_alto.setSuffix(" cm")
    form.addRow("Alto:", spin_alto)

    lay.addLayout(form)
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    lay.addWidget(botones)

    # El PNG es el único formato al que la resolución le cambia algo.
    def _sync_dpi():
        spin_dpi.setEnabled(cmb_fmt.currentData() == "png")
    cmb_fmt.currentIndexChanged.connect(_sync_dpi)
    _sync_dpi()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    fmt = cmb_fmt.currentData()
    # La carpeta de la última figura guardada manda sobre la que pase quien
    # llama: las figuras para publicar suelen ir a una carpeta distinta de la
    # de los datos, y volver a navegar hasta ella en cada guardado molesta.
    destino = os.path.join(_carpeta_recordada() or carpeta_inicial or "",
                           f"{nombre_sugerido}.{fmt}")
    ruta, _ = QFileDialog.getSaveFileName(
        parent, "Guardar gráfico", destino,
        f"{fmt.upper()} (*.{fmt});;Todos (*.*)",
        options=QFileDialog.Option.DontUseNativeDialog)
    if not ruta:
        return None
    if not ruta.lower().endswith("." + fmt):
        ruta += "." + fmt
    _recordar_carpeta(os.path.dirname(ruta))
    _recordar_preferencias(cmb_paleta.currentText(), fmt, spin_dpi.value(),
                           spin_ancho.value(), spin_alto.value())

    textos = textos_desde_pyqtgraph(widget_grafico)
    try:
        exportar_figura(
            curvas, ruta,
            nombre_paleta=cmb_paleta.currentText(),
            titulo=textos["titulo"],
            etiqueta_x=textos["etiqueta_x"] or "Año",
            etiqueta_y=textos["etiqueta_y"],
            dpi=spin_dpi.value(),
            lineas_h=lineas_h,
            ancho_cm=spin_ancho.value(),
            alto_cm=spin_alto.value(),
        )
    except ImportError:
        QMessageBox.critical(
            parent, "Falta matplotlib",
            "La descarga de gráficos necesita matplotlib.\n\n"
            "Instalalo con:\n    pip install matplotlib")
        return None
    except Exception as exc:
        QMessageBox.critical(parent, "Error al guardar",
                             f"No se pudo guardar el gráfico:\n{exc}")
        return None

    QMessageBox.information(parent, "Gráfico guardado", f"Guardado en:\n{ruta}")
    return ruta
