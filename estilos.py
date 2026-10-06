"""
estilos.py — Estilos Qt compartidos entre ambas aplicaciones dendrocronológicas.

Un tema en Qt tiene DOS mitades y hacen falta las dos:

  1. La hoja de estilos (`ESTILO_OSCURO` / `ESTILO_CLARO`), que solo afecta a
     los widgets que nombra explícitamente.
  2. La paleta (`paleta`), que es de dónde saca el color TODO lo demás:
     los editores de texto, los diálogos nativos, los tooltips, los ítems de
     lista dibujados a mano, etc.

Durante mucho tiempo acá solo estaba la primera mitad, y eso producía un bug
que en Linux no se veía pero en Windows sí. La regla `QWidget { color: white; }`
pinta la LETRA de un QPlainTextEdit de blanco, pero su FONDO lo sigue decidiendo
la paleta del sistema. Con el tema oscuro de GNOME esa paleta ya era oscura y
todo se veía bien por casualidad; en Windows la paleta es clara (fondo blanco),
así que el informe de la pestaña Cofecha quedaba en blanco sobre blanco.

Por eso `aplicar_tema` fija paleta y hoja de estilos juntas, y además fuerza el
estilo «Fusion»: los estilos nativos de Windows dibujan varios controles
ignorando la paleta, mientras que Fusion la respeta en todas las plataformas.
Como efecto secundario útil, Linux pasa a verse igual que Windows, así que se
puede revisar el tema sin arrancar el otro sistema operativo.
"""

ESTILO_OSCURO = """
    QMainWindow, QDialog, QMessageBox { background-color: #2b2b2b; color: white; }
    QWidget { color: white; }
    QPushButton {
        background-color: #4a4a4a; color: white;
        padding: 6px; border-radius: 4px; min-width: 80px;
    }
    QPushButton:checked  { background-color: #5cb85c; color: white; font-weight: bold; }
    QPushButton:hover    { background-color: #5a5a5a; }
    QPushButton:disabled { background-color: #3a3a3a; color: #808080; }
    QGraphicsView        { background-color: #1e1e1e; border: 1px solid #555; }
    QLabel               { color: white; background: transparent; }
    QCheckBox, QRadioButton { color: white; background: transparent; }
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
        background-color: #4a4a4a; color: white;
        padding: 4px; border: 1px solid #666;
    }
    QLineEdit:disabled, QComboBox:disabled,
    QSpinBox:disabled, QDoubleSpinBox:disabled {
        background-color: #3a3a3a; color: #808080;
    }
    QComboBox QAbstractItemView {
        background-color: #4a4a4a; color: white;
        selection-background-color: #5cb85c;
    }
    /* Editores de texto. Sin esta regla el fondo lo pone la paleta del
       sistema y en Windows salía blanco con la letra blanca.
       Ojo con el tono de la letra: modulo_codatacion deduce el tema buscando
       el color de fondo del tema claro como subcadena de esta hoja, así que
       ese valor no puede aparecer acá (ni siquiera en un comentario). */
    QPlainTextEdit, QTextEdit, QTextBrowser {
        background-color: #1e1e1e; color: #eaeaea;
        border: 1px solid #555;
        selection-background-color: #5cb85c; selection-color: white;
    }
    QListView, QTreeView, QTableView {
        background-color: #3b3b3b; color: white; border: 1px solid #555;
        selection-background-color: #5cb85c; selection-color: white;
        alternate-background-color: #333333;
    }
    QHeaderView::section {
        background-color: #4a4a4a; color: white;
        border: 1px solid #555; padding: 4px;
    }
    QTableCornerButton::section { background-color: #4a4a4a; border: 1px solid #555; }
    QTabWidget::pane { border: 1px solid #555; }
    QTabBar::tab {
        background: #3b3b3b; color: white;
        border: 1px solid #555; padding: 8px; min-width: 150px;
    }
    QTabBar::tab:selected { background: #5a5a5a; font-weight: bold; }
    QGroupBox {
        background-color: #2b2b2b; color: white;
        border: 1px solid #555; border-radius: 4px;
        margin-top: 8px; padding-top: 4px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        padding: 0 4px; color: white; background-color: #2b2b2b;
    }
    QMenuBar { background-color: #2b2b2b; color: white; }
    QMenuBar::item:selected { background-color: #5a5a5a; }
    QMenu { background-color: #3b3b3b; color: white; border: 1px solid #555; }
    QMenu::item:selected { background-color: #5cb85c; color: white; }
    QMenu::separator { background: #555; height: 1px; margin: 4px 0; }
    QToolTip {
        background-color: #3b3b3b; color: white;
        border: 1px solid #777; padding: 3px;
    }
    QProgressBar {
        background-color: #3b3b3b; color: white;
        border: 1px solid #555; border-radius: 4px; text-align: center;
    }
    QProgressBar::chunk { background-color: #5cb85c; border-radius: 3px; }
    QSplitter::handle { background-color: #4a4a4a; }
    QStatusBar { color: white; }
    QToolButton { color: white; background: transparent; }
    QScrollBar:vertical {
        background: #3b3b3b; width: 10px;
    }
    QScrollBar::handle:vertical {
        background: #5a5a5a; border-radius: 4px; min-height: 20px;
    }
    /* El informe de Cofecha no hace wrap, así que la barra horizontal se usa
       de verdad: sin estilarla quedaba con el color nativo del sistema. */
    QScrollBar:horizontal {
        background: #3b3b3b; height: 10px;
    }
    QScrollBar::handle:horizontal {
        background: #5a5a5a; border-radius: 4px; min-width: 20px;
    }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""

ESTILO_CLARO = """
    QMainWindow, QDialog, QMessageBox { background-color: #f0f0f0; color: black; }
    QWidget { color: black; }
    QPushButton {
        background-color: #e0e0e0; color: black;
        padding: 6px; border-radius: 4px; min-width: 80px;
    }
    QPushButton:checked  { background-color: #5cb85c; color: white; font-weight: bold; }
    QPushButton:hover    { background-color: #d0d0d0; }
    QPushButton:disabled { background-color: #ebebeb; color: #a0a0a0; }
    QGraphicsView        { background-color: #ffffff; border: 1px solid #ccc; }
    QLabel               { color: black; background: transparent; }
    QCheckBox, QRadioButton { color: black; background: transparent; }
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
        background-color: white; color: black;
        padding: 4px; border: 1px solid #ccc;
    }
    QLineEdit:disabled, QComboBox:disabled,
    QSpinBox:disabled, QDoubleSpinBox:disabled {
        background-color: #ebebeb; color: #a0a0a0;
    }
    QComboBox QAbstractItemView {
        background-color: white; color: black;
        selection-background-color: #e0e0e0;
    }
    QPlainTextEdit, QTextEdit, QTextBrowser {
        background-color: #ffffff; color: #111111;
        border: 1px solid #ccc;
        selection-background-color: #5cb85c; selection-color: white;
    }
    QListView, QTreeView, QTableView {
        background-color: #ffffff; color: black; border: 1px solid #ccc;
        selection-background-color: #5cb85c; selection-color: white;
        alternate-background-color: #f6f6f6;
    }
    QHeaderView::section {
        background-color: #e0e0e0; color: black;
        border: 1px solid #ccc; padding: 4px;
    }
    QTableCornerButton::section { background-color: #e0e0e0; border: 1px solid #ccc; }
    QTabWidget::pane { border: 1px solid #ccc; }
    QTabBar::tab {
        background: #e0e0e0; color: black;
        border: 1px solid #ccc; padding: 8px; min-width: 150px;
    }
    QTabBar::tab:selected { background: #ffffff; font-weight: bold; }
    QGroupBox {
        background-color: #f0f0f0; color: black;
        border: 1px solid #ccc; border-radius: 4px;
        margin-top: 8px; padding-top: 4px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        padding: 0 4px; color: black; background-color: #f0f0f0;
    }
    QMenuBar { background-color: #f0f0f0; color: black; }
    QMenuBar::item:selected { background-color: #d0d0d0; }
    QMenu { background-color: #ffffff; color: black; border: 1px solid #ccc; }
    QMenu::item:selected { background-color: #5cb85c; color: white; }
    QMenu::separator { background: #ccc; height: 1px; margin: 4px 0; }
    QToolTip {
        background-color: #ffffdc; color: black;
        border: 1px solid #999; padding: 3px;
    }
    QProgressBar {
        background-color: #e0e0e0; color: black;
        border: 1px solid #ccc; border-radius: 4px; text-align: center;
    }
    QProgressBar::chunk { background-color: #5cb85c; border-radius: 3px; }
    QSplitter::handle { background-color: #d0d0d0; }
    QStatusBar { color: black; }
    QToolButton { color: black; background: transparent; }
    QScrollBar:vertical {
        background: #e0e0e0; width: 10px;
    }
    QScrollBar::handle:vertical {
        background: #b0b0b0; border-radius: 4px; min-height: 20px;
    }
    QScrollBar:horizontal {
        background: #e0e0e0; height: 10px;
    }
    QScrollBar::handle:horizontal {
        background: #b0b0b0; border-radius: 4px; min-width: 20px;
    }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


# =============================================================================
# Texto secundario
# =============================================================================

# Color del texto de apoyo —notas al pie, rangos, contadores, ayudas en
# cursiva— que debe leerse menos que el texto principal pero seguir siendo
# legible. Sale del rol PlaceholderText de la paleta, así que hay UN solo
# lugar donde cambiarlo.
#
# Hay dos formas de usarlo y NO son intercambiables:
#
#   · SECUNDARIO_QSS, dentro de la hoja de estilos de un widget. Qt vuelve a
#     resolver `palette(...)` cada vez que la app cambia de tema, así que el
#     color se corrige solo. Es la forma preferida.
#
#   · color_secundario(), que devuelve el hex ya resuelto. Hace falta para el
#     HTML embebido (`<span style='color:...'>`), porque ahí Qt resuelve
#     `palette(...)` UNA vez al interpretar el texto y lo deja fijo: si el
#     usuario alterna el tema, el color queda con el valor viejo hasta que se
#     vuelva a armar el texto. Usarlo solo cuando no queda otra, y llamarlo al
#     momento de construir el HTML, nunca guardarlo en una constante de módulo.
SECUNDARIO_QSS = "palette(placeholder-text)"


def color_secundario() -> str:
    """Hex del texto secundario del tema activo, p. ej. ``'#6b6b6b'``."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPalette

    app = QApplication.instance()
    if app is None:          # sin app (tests, importación suelta)
        return "#6b6b6b"
    return app.palette().color(QPalette.ColorRole.PlaceholderText).name()


# =============================================================================
# Paleta
# =============================================================================

def paleta(oscuro: bool):
    """QPalette que acompaña a la hoja de estilos del mismo tema.

    Es la mitad del tema que la hoja de estilos no cubre: el fondo de los
    editores de texto (rol `Base`), los tooltips, los diálogos nativos y
    cualquier widget que consulte `palette()` para pintarse a mano —como hace
    la lista de series de la pestaña de Co-Datación, que lee `ColorRole.Text`
    para el color normal de sus ítems.
    """
    from PyQt6.QtGui import QPalette, QColor

    p = QPalette()
    g = QPalette.ColorGroup
    r = QPalette.ColorRole

    if oscuro:
        colores = {
            r.Window: "#2b2b2b",        r.WindowText: "#ffffff",
            r.Base: "#1e1e1e",          r.AlternateBase: "#3b3b3b",
            r.ToolTipBase: "#3b3b3b",   r.ToolTipText: "#ffffff",
            # PlaceholderText es además el color del TEXTO SECUNDARIO de toda
            # la app (ver `color_secundario`). #9a9a9a da 5.0:1 sobre el fondo
            # de ventana #2b2b2b; no bajarlo de #929292, que es el límite de
            # 4.5:1 que pide la WCAG para texto normal.
            r.Text: "#ffffff",          r.PlaceholderText: "#9a9a9a",
            r.Button: "#4a4a4a",        r.ButtonText: "#ffffff",
            r.BrightText: "#ff5555",
            r.Link: "#4aa3ff",          r.LinkVisited: "#b088ff",
            r.Highlight: "#5cb85c",     r.HighlightedText: "#ffffff",
            r.Light: "#5a5a5a",         r.Midlight: "#4f4f4f",
            r.Dark: "#1e1e1e",          r.Mid: "#3b3b3b",
            r.Shadow: "#141414",
        }
        deshabilitado = "#808080"
        resalte_off = "#3b3b3b"
    else:
        colores = {
            r.Window: "#f0f0f0",        r.WindowText: "#000000",
            r.Base: "#ffffff",          r.AlternateBase: "#f6f6f6",
            r.ToolTipBase: "#ffffdc",   r.ToolTipText: "#000000",
            # El #707070 anterior daba 4.35:1 sobre el fondo de ventana
            # #f0f0f0, por debajo del 4.5:1 de la WCAG. #6b6b6b da 4.68:1;
            # no subirlo de #6d6d6d, que es el límite.
            r.Text: "#000000",          r.PlaceholderText: "#6b6b6b",
            r.Button: "#e0e0e0",        r.ButtonText: "#000000",
            r.BrightText: "#d40000",
            r.Link: "#0066cc",          r.LinkVisited: "#7a4fbf",
            r.Highlight: "#5cb85c",     r.HighlightedText: "#ffffff",
            r.Light: "#ffffff",         r.Midlight: "#f0f0f0",
            r.Dark: "#a0a0a0",          r.Mid: "#c8c8c8",
            r.Shadow: "#6e6e6e",
        }
        deshabilitado = "#a0a0a0"
        resalte_off = "#d0d0d0"

    for rol, hexa in colores.items():
        p.setColor(rol, QColor(hexa))

    # Los controles deshabilitados necesitan su propio color: si se deja el
    # del grupo activo, un botón apagado se ve idéntico a uno usable.
    for rol in (r.WindowText, r.Text, r.ButtonText, r.PlaceholderText):
        p.setColor(g.Disabled, rol, QColor(deshabilitado))
    p.setColor(g.Disabled, r.Highlight, QColor(resalte_off))
    p.setColor(g.Disabled, r.HighlightedText, QColor(deshabilitado))

    return p


_estilo_fijado = False


def aplicar_tema(app, oscuro: bool, estilo_extra: str = ""):
    """Aplica el tema completo —estilo, paleta y hoja de estilos— a la app.

    `estilo_extra` se concatena al final de la hoja de estilos para los
    ajustes que dependen del tema y viven en el módulo que llama.
    """
    # Fusion respeta la paleta en las tres plataformas. Los estilos nativos de
    # Windows dibujan casillas, combos y barras con los colores del sistema
    # pase lo que pase, que es el origen de los contrastes rotos allá.
    #
    # Se fija una sola vez, controlado por una bandera y no preguntándole a
    # `app.style()`: en cuanto hay una hoja de estilos aplicada, Qt envuelve el
    # estilo en un proxy cuyo `name()` y `objectName()` vienen vacíos, así que
    # cualquier comparación por nombre daría siempre «no es Fusion» y
    # reinstalaría el estilo en cada cambio de tema.
    global _estilo_fijado
    if not _estilo_fijado:
        app.setStyle("Fusion")
        _estilo_fijado = True

    app.setPalette(paleta(oscuro))
    base = ESTILO_OSCURO if oscuro else ESTILO_CLARO
    app.setStyleSheet(base + estilo_extra)


def tema_del_sistema(app) -> bool:
    """¿El sistema operativo está en modo oscuro?

    Usa `styleHints().colorScheme()`, que pregunta al sistema directamente.
    Mirar la paleta no sirve una vez que forzamos Fusion, porque entonces
    devuelve la paleta que nosotros pusimos, no la del escritorio.
    """
    from PyQt6.QtCore import Qt

    try:
        esquema = app.styleHints().colorScheme()
        if esquema == Qt.ColorScheme.Dark:
            return True
        if esquema == Qt.ColorScheme.Light:
            return False
    except (AttributeError, TypeError):
        pass  # Qt < 6.5 no tiene colorScheme

    # Sin respuesta del sistema, deducirlo del brillo de la paleta nativa.
    from PyQt6.QtGui import QPalette
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
