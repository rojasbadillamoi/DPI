"""
modulo_codatacion.py — Panel de Co-datación Visual

Permite comparar series dendrocronológicas, detectar anillos faltantes o
sobrantes mediante búsqueda exhaustiva, y aplicar correcciones en memoria.
"""

import os
import sys
import csv
import json
import logging
import numpy as np
import pandas as pd
import pyqtgraph as pg
import modulo_transformacion as _tr
import modulo_quiebres as _qb
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QSplitter, QFileDialog, QMessageBox, QInputDialog,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QFormLayout,
    QComboBox, QCheckBox, QLineEdit, QTextEdit, QGroupBox,
    QDialogButtonBox, QApplication, QProgressDialog,
    QScrollArea, QRadioButton, QButtonGroup, QFrame,
    QSlider,
    QTabWidget, QPlainTextEdit,
    QTextBrowser,
)
from PyQt6.QtGui import (
    QColor, QFont, QKeySequence, QShortcut, QPainter, QPalette,
)
from PyQt6.QtCore import Qt, QSettings, QEvent

from constantes import (
    TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE, TUCSON_VALOR_999,
    TUCSON_MAX_CHARS_ID, TUCSON_DIVISOR,
    OVERLAP_MINIMO_ANALISIS, OVERLAP_MINIMO_GRAFICO,
    OVERLAP_MINIMO_FLOTANTE,
    UMBRAL_ANCLA_DEFECTO,
    VENTANA_COFECHADO_DEFECTO, COLORES_SERIES,
)

logger = logging.getLogger(__name__)

# Correcciones máximas a explorar por año (±N anillos)
MAX_CORRECCION = 3
MIN_OVERLAP_DEFAULT = 10


# Extensiones de planilla que se leen/escriben con el motor de Excel de
# pandas. Incluye .ods (LibreOffice / OpenDocument), que necesita el módulo
# 'odfpy'. Se usa en todo el módulo para no repetir la lista y para que un
# .ods nunca caiga por error al parser de texto (CSV), que devolvería basura.
EXTS_PLANILLA = (".xlsx", ".xls", ".ods")


def _es_planilla(ruta_o_ext: str) -> bool:
    """True si la ruta (o extensión) corresponde a una planilla Excel/ODS."""
    valor = (ruta_o_ext or "").lower()
    ext = valor if valor.startswith(".") else os.path.splitext(valor)[1].lower()
    return ext in EXTS_PLANILLA


def _leer_planilla(ruta: str, **kwargs):
    """Lee una planilla .xlsx/.xls/.ods con el motor adecuado.

    pandas elige el motor por extensión, pero solo si el módulo está
    instalado; si falta, el error ("Missing optional dependency 'odfpy'") no
    es accionable para el usuario. Acá damos un mensaje claro con la solución.
    """
    import importlib.util
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".ods" and importlib.util.find_spec("odf") is None:
        raise RuntimeError(
            "Para leer planillas de LibreOffice (.ods) falta el módulo "
            "'odfpy'.\n\nInstálalo con:  pip install odfpy\n\n"
            "Como alternativa, en LibreOffice usa «Archivo → Guardar como» y "
            "elige .xlsx o .csv.")
    if ext in (".xlsx", ".xls") and importlib.util.find_spec("openpyxl") is None:
        raise RuntimeError(
            "Para leer planillas de Excel (.xlsx) falta el módulo "
            "'openpyxl'.\n\nInstálalo con:  pip install openpyxl")
    return pd.read_excel(ruta, **kwargs)


def _escribir_excel(df, ruta: str, index: bool = False):
    """Escribe un DataFrame a .xlsx/.ods eligiendo un motor disponible.

    pandas necesita openpyxl o xlsxwriter para .xlsx, y odfpy para .ods. Si no
    especifica engine y ninguno está instalado, lanza "No engine for filetype".
    Aquí elegimos el primero disponible y, si falta, damos un mensaje accionable.
    """
    import importlib.util
    ext = os.path.splitext(ruta)[1].lower()

    if ext == ".ods":
        if importlib.util.find_spec("odf") is not None:
            df.to_excel(ruta, index=index, engine="odf")
            return
        raise RuntimeError(
            "Para exportar a LibreOffice (.ods) falta el módulo 'odfpy'.\n\n"
            "Instálalo con:  pip install odfpy\n\n"
            "Como alternativa, exporta en CSV o TXT, que no requieren módulos "
            "adicionales.")

    for engine in ("openpyxl", "xlsxwriter"):
        if importlib.util.find_spec(engine) is not None:
            df.to_excel(ruta, index=index, engine=engine)
            return
    raise RuntimeError(
        "Para exportar a Excel (.xlsx) falta el módulo 'openpyxl'.\n\n"
        "Instálalo con:  pip install openpyxl\n\n"
        "Como alternativa, exporta en CSV o TXT, que no requieren módulos "
        "adicionales.")


def _asegurar_extension(ruta: str, filtro: str) -> str:
    """Garantiza que la ruta tenga una extensión coherente con el filtro
    elegido en el diálogo de guardado.

    El diálogo NO nativo de Qt no siempre agrega la extensión: si el usuario
    escribe solo el nombre, el archivo queda SIN extensión y los programas no
    lo reconocen (un .xlsx sin extensión se ve como un .zip). Esta función
    extrae las extensiones del filtro y agrega la primera si falta.
    """
    import re
    exts = re.findall(r"\*(\.[A-Za-z0-9]+)", filtro or "")
    if not exts:
        return ruta
    ruta_lower = ruta.lower()
    if any(ruta_lower.endswith(e.lower()) for e in exts):
        return ruta
    return ruta + exts[0]


def _ultima_carpeta(nueva_ruta: str | None = None) -> str:
    """
    Lee o guarda la última carpeta usada en el módulo de codatación.

    Usa una clave QSettings INDEPENDIENTE de modulo_medicion.py porque
    los usuarios típicamente organizan imágenes y mediciones en carpetas
    distintas.
    """
    cfg = QSettings("MoiCedrus", "DPI")
    if nueva_ruta is not None:
        cfg.setValue("ultima_carpeta_codatacion", os.path.dirname(nueva_ruta))
        return os.path.dirname(nueva_ruta)
    return cfg.value("ultima_carpeta_codatacion", "")


def _sensibilidad_media(x) -> float:
    """Sensibilidad media (mean sensitivity, MS) de una serie.

    MS = promedio de |2·(x_{t+1} − x_t) / (x_{t+1} + x_t)|. Mide la
    variabilidad relativa año a año. Clásica en dendrocronología:
    valores ~0.1–0.2 = serie complaciente; >0.3 = serie sensible.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan")
    num = np.abs(2.0 * (x[1:] - x[:-1]))
    den = np.abs(x[1:] + x[:-1])
    with np.errstate(divide="ignore", invalid="ignore"):
        vals = num / den
    vals = vals[np.isfinite(vals)]
    return float(np.mean(vals)) if len(vals) else float("nan")


def _autocorrelacion_ar1(x) -> float:
    """Autocorrelación de primer orden (lag-1) de una serie.

    Mide la persistencia interanual (cuánto depende un año del anterior).
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float("nan")
    x0, x1 = x[:-1], x[1:]
    if np.std(x0) == 0 or np.std(x1) == 0:
        return float("nan")
    r = float(np.corrcoef(x0, x1)[0, 1])
    return r if np.isfinite(r) else float("nan")


def _ensanchar_dialogo(caja, minimo: int = 520):
    """Evita que los botones de un QMessageBox salgan cortados.

    QMessageBox calcula su ancho a partir del TEXTO, no de los botones, así
    que con etiquetas largas ("Conservando ancho (editor)") los botones se
    recortan y no se puede leer qué hace cada uno. Se mide el ancho que
    necesitan todos los botones juntos y se fuerza ese mínimo.
    """
    try:
        botones = caja.buttons()
        necesario = sum(max(b.sizeHint().width(), b.width()) + 16
                        for b in botones) + 60
        ancho = max(int(minimo), int(necesario))
        for b in botones:
            b.setMinimumWidth(b.sizeHint().width() + 12)
        grid = caja.layout()
        if grid is not None:
            # Espaciador invisible que obliga al diálogo a ese ancho mínimo
            from PyQt6.QtWidgets import QSpacerItem, QSizePolicy
            esp = QSpacerItem(ancho, 0, QSizePolicy.Policy.Minimum,
                              QSizePolicy.Policy.Expanding)
            grid.addItem(esp, grid.rowCount(), 0, 1, grid.columnCount())
        caja.setMinimumWidth(ancho)
    except Exception:
        pass


def _agregar_hover_anio(plot_widget, formato="Año {anio}", extra=None):
    """Muestra el AÑO bajo el cursor mientras se mueve por el gráfico.

    Los ejes suelen marcar cada 5 o 10 años, así que ubicarse en el tiempo
    obliga a contar. Con esto el año aparece directamente junto al cursor.
    `extra(anio)` puede devolver texto adicional (p. ej. el valor de la serie).
    """
    try:
        etiqueta = pg.TextItem(color="#f1c40f", anchor=(0, 1))
        etiqueta.setZValue(1000)
        plot_widget.addItem(etiqueta, ignoreBounds=True)
        etiqueta.hide()

        linea = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#f1c40f", width=1, style=Qt.PenStyle.DotLine))
        linea.setZValue(999)
        plot_widget.addItem(linea, ignoreBounds=True)
        linea.hide()

        vb = plot_widget.getPlotItem().vb

        def _asegurar_items():
            # Cada redibujo llama a plot_widget.clear(), que ELIMINA todos los
            # items de la escena, incluidos la etiqueta y la línea del hover.
            # Por eso el año no aparecía nunca: los items existían en Python
            # pero ya no estaban en el gráfico. Se vuelven a agregar si faltan.
            if etiqueta.scene() is None:
                plot_widget.addItem(etiqueta, ignoreBounds=True)
            if linea.scene() is None:
                plot_widget.addItem(linea, ignoreBounds=True)

        def _mover(evt):
            pos = evt[0] if isinstance(evt, (tuple, list)) else evt
            if not plot_widget.sceneBoundingRect().contains(pos):
                etiqueta.hide()
                linea.hide()
                return
            _asegurar_items()
            punto = vb.mapSceneToView(pos)
            anio = int(round(punto.x()))
            texto = formato.format(anio=anio)
            if extra is not None:
                try:
                    ad = extra(anio)
                    if ad:
                        texto += "\n" + ad
                except Exception:
                    pass
            etiqueta.setText(texto)
            etiqueta.setPos(punto.x(), punto.y())
            linea.setPos(anio)
            etiqueta.show()
            linea.show()

        plot_widget._proxy_hover_anio = pg.SignalProxy(
            plot_widget.scene().sigMouseMoved, rateLimit=60, slot=_mover)
        plot_widget._hover_anio_items = (etiqueta, linea)
        plot_widget._hover_anio_mover = _mover  # para pruebas/reuso
    except Exception:
        pass


def _crear_barra_zoom(plot_widget) -> QWidget:
    """Devuelve una barra compacta de controles de zoom para un PlotWidget.

    Da controles descubribles para lo que pyqtgraph ya permite con mouse,
    pero que no es evidente: zoom por área (arrastrar un rectángulo),
    ensanchar/comprimir el eje X (útil en series largas), y ver todo. La
    rueda del mouse siempre hace zoom y, fuera del modo área, arrastrar
    mueve (pan).
    """
    vb = plot_widget.getViewBox()
    cont = QWidget()
    fila = QHBoxLayout(cont)
    fila.setContentsMargins(0, 2, 0, 2)
    fila.setSpacing(4)
    fila.addWidget(QLabel("Zoom:"))

    btn_area = QPushButton("🔍 Área")
    btn_area.setCheckable(True)
    btn_area.setToolTip(
        "Activado: arrastra un rectángulo para hacer zoom en esa zona.\n"
        "Desactivado: arrastra para mover (pan). La rueda siempre hace zoom.")
    btn_area.toggled.connect(
        lambda a: vb.setMouseMode(
            pg.ViewBox.RectMode if a else pg.ViewBox.PanMode))
    fila.addWidget(btn_area)

    btn_mas = QPushButton("◄ ►")
    btn_mas.setMaximumWidth(48)
    btn_mas.setToolTip("Ensanchar: estira el eje X (ver menos años, más detalle).")
    btn_mas.clicked.connect(lambda: vb.scaleBy((0.7, 1.0)))
    fila.addWidget(btn_mas)

    btn_menos = QPushButton("► ◄")
    btn_menos.setMaximumWidth(48)
    btn_menos.setToolTip("Comprimir: comprime el eje X (ver más años).")
    btn_menos.clicked.connect(lambda: vb.scaleBy((1.4, 1.0)))
    fila.addWidget(btn_menos)

    btn_reset = QPushButton("⟲ Ver todo")
    btn_reset.clicked.connect(lambda: plot_widget.autoRange())
    fila.addWidget(btn_reset)

    fila.addStretch()
    return cont



# =============================================================================
# ESTADÍSTICOS DE COFECHADO
# =============================================================================

def gleichlaufigkeit(serie_a, serie_b, min_overlap: int = 10):
    """GLK (Eckstein & Bauch 1969): proporción de años con cambio en la misma dirección."""
    a = pd.to_numeric(serie_a, errors="coerce").dropna()
    b = pd.to_numeric(serie_b, errors="coerce").dropna()
    overlap = a.index.intersection(b.index)
    if len(overlap) < min_overlap:
        return float("nan"), 0

    a = a.loc[overlap].sort_index().to_numpy(dtype=float)
    b = b.loc[overlap].sort_index().to_numpy(dtype=float)

    da = np.sign(np.diff(a))
    db = np.sign(np.diff(b))
    n = len(da)
    if n == 0:
        return float("nan"), len(overlap)

    coinciden = (da == db) & (da != 0)
    # Misma fórmula que dplR (glk.R): 1 − Σ|signo_a − signo_b| / (2n).
    # Da crédito completo cuando ambas series están planas en el mismo par de
    # años; DPI le daba 0,5. Ver el comentario extendido en `_glk_np`.
    glk = 1.0 - np.sum(np.abs(da - db)) / (2.0 * n)
    return float(glk), int(len(overlap))


def glk_significance(glk: float, n: int) -> str:
    """Significancia GLK (Jansma 1995): aproximación binomial."""
    if not np.isfinite(glk) or n < 30:
        return "ns"
    z = (glk - 0.5) * 2 * np.sqrt(n)
    if z >= 3.29: return "***"
    if z >= 2.58: return "**"
    if z >= 1.96: return "*"
    return "ns"


def _filtro_hollstein(serie):
    """Filtro de Hollstein: 100 × primera diferencia logarítmica."""
    s = pd.to_numeric(serie, errors="coerce").dropna()
    s = s[s > 0]
    if len(s) < 2:
        return pd.Series(dtype=float)
    return np.log(s).diff().dropna() * 100.0


def t_baillie_pilcher(serie_a, serie_b, min_overlap: int = 20):
    """t de Baillie-Pilcher: Hollstein → Pearson r → t-statistic."""
    a_filt = _filtro_hollstein(serie_a)
    b_filt = _filtro_hollstein(serie_b)
    overlap = a_filt.index.intersection(b_filt.index)
    n = len(overlap)
    if n < min_overlap:
        return float("nan"), float("nan"), n

    a = a_filt.loc[overlap].to_numpy(dtype=float)
    b = b_filt.loc[overlap].to_numpy(dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return float("nan"), float("nan"), n

    r = float(np.corrcoef(a, b)[0, 1])
    if np.isnan(r) or abs(r) >= 1.0:
        return float("nan"), r, n
    t_bp = r * np.sqrt(n - 2) / np.sqrt(1.0 - r * r)
    return float(t_bp), r, n


def estadisticos_cofechado(serie_a, serie_b, min_overlap: int = 20) -> dict:
    """r + GLK + t-BP simultáneos."""
    a = pd.to_numeric(serie_a, errors="coerce").dropna()
    b = pd.to_numeric(serie_b, errors="coerce").dropna()
    overlap = a.index.intersection(b.index)
    n = len(overlap)

    resultado = {
        "r": float("nan"), "n": n,
        "glk": float("nan"), "glk_sig": "ns",
        "t_bp": float("nan"), "r_filt": float("nan"),
    }

    if n < min_overlap:
        return resultado

    a_ov = a.loc[overlap].to_numpy(dtype=float)
    b_ov = b.loc[overlap].to_numpy(dtype=float)
    if np.std(a_ov) > 0 and np.std(b_ov) > 0:
        r = float(np.corrcoef(a_ov, b_ov)[0, 1])
        if np.isfinite(r):
            resultado["r"] = r

    glk, _ = gleichlaufigkeit(serie_a, serie_b, min_overlap)
    resultado["glk"] = glk
    resultado["glk_sig"] = glk_significance(glk, n)

    t_bp, r_filt, _ = t_baillie_pilcher(serie_a, serie_b, min_overlap)
    resultado["t_bp"] = t_bp
    resultado["r_filt"] = r_filt

    return resultado


# =============================================================================
# COLORES Y SCORE COMPUESTO
# =============================================================================

def _color_r(r: float) -> str:
    if not np.isfinite(r): return "#888"
    if r >= 0.50: return "#28a745"
    if r >= 0.35: return "#a3c44e"
    if r >= 0.20: return "#f0ad4e"
    return "#d9534f"


def _color_glk(g: float) -> str:
    if not np.isfinite(g): return "#888"
    if g >= 0.70: return "#28a745"
    if g >= 0.65: return "#a3c44e"
    if g >= 0.60: return "#f0ad4e"
    return "#d9534f"


def _color_tbp(t: float) -> str:
    if not np.isfinite(t): return "#888"
    if t >= 6.0: return "#28a745"
    if t >= 4.0: return "#a3c44e"
    if t >= 3.0: return "#f0ad4e"
    return "#d9534f"


def score_compuesto(r: float, glk: float, t_bp: float) -> float:
    """Media geométrica con signo de r, GLK y t-BP normalizados a [-1, 1].

    Resultado en [-1, +1]:
      • cerca de +1  →  las tres métricas indican correlación fuerte
      • cerca de  0  →  ambiguo / al menos una métrica plana
      • cerca de -1  →  las tres indican ANTI-correlación
                        (señal de que el cofechado está completamente desfasado:
                         el patrón coincide pero invertido)

    Normalización: r ∈ [-1,1] directo, GLK mapeado desde [0,1] a [-1,1] con
    pivote en 0.5, t-BP saturado en ±10. Se usa raíz cúbica (np.cbrt) que
    preserva signo, a diferencia de la potencia 1/3 que en Python devuelve
    complejos para negativos.
    """
    if not (np.isfinite(r) and np.isfinite(glk) and np.isfinite(t_bp)):
        return float("nan")
    r_norm = max(-1.0, min(1.0, r))
    glk_norm = max(-1.0, min(1.0, 2.0 * (glk - 0.5)))
    tbp_norm = max(-1.0, min(1.0, t_bp / 10.0))
    producto = r_norm * glk_norm * tbp_norm
    return float(np.cbrt(producto))


def _color_compuesto(s: float) -> str:
    if not np.isfinite(s): return "#666666"
    if s >= 0.60: return "#28a745"   # verde fuerte
    if s >= 0.40: return "#5cb85c"   # verde
    if s >= 0.20: return "#ffc107"   # amarillo
    if s >= -0.20: return "#fd7e14"  # naranja (zona ambigua cercana a 0)
    return "#dc3545"                  # rojo (anti-correlación)


# =============================================================================
# EPS / RBAR
# =============================================================================

def calcular_eps_rbar_movil(series_dict, nombres, window=15, paso=1, progreso=None):
    """EPS y Rbar móvil — versión numpy directa."""
    cols = []
    for n in nombres:
        if n in series_dict:
            s = series_dict[n]["Ancho_mm"].dropna()
            s.name = n
            cols.append(s)
    if len(cols) < 2:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    df = pd.concat(cols, axis=1).sort_index()
    n_series = df.shape[1]
    years = df.index.to_numpy()
    half = window // 2
    data = df.to_numpy(dtype=float)
    n_years = len(data)

    if n_years < window:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    indices = list(range(half, n_years - half, paso))
    total = len(indices)
    resultados = []
    min_per = 10

    for k, i in enumerate(indices):
        win = data[i - half: i + half + 1]

        # Rbar vectorizado. Antes se recorrían TODOS los pares de series en
        # bucles de Python (con 169 series son 14.196 pares por ventana, cada
        # uno con su np.corrcoef): era el cuello de botella al generar
        # cronologías grandes. Ahora se calcula la matriz de correlaciones de
        # una sola vez con álgebra matricial, respetando los NaN (cada par usa
        # solo los años en que ambas series tienen dato) y el mínimo de
        # solape `min_per`.
        valido = ~np.isnan(win)
        Z = np.where(valido, win, 0.0)
        V = valido.astype(float)

        n_ab = V.T @ V                      # años en común por par
        s_a = Z.T @ V                       # Σ a   (sobre años comunes)
        s_b = V.T @ Z                       # Σ b
        s_ab = Z.T @ Z                      # Σ a·b
        s_aa = (Z * Z).T @ V                # Σ a²
        s_bb = V.T @ (Z * Z)                # Σ b²

        with np.errstate(divide="ignore", invalid="ignore"):
            cov = s_ab - (s_a * s_b) / n_ab
            var_a = s_aa - (s_a * s_a) / n_ab
            var_b = s_bb - (s_b * s_b) / n_ab
            den = np.sqrt(var_a * var_b)
            R = cov / den

        # Solo pares por encima del solape mínimo, mitad superior (a<b)
        iu = np.triu_indices(n_series, k=1)
        r_pares = R[iu]
        ok = (n_ab[iu] >= min_per) & np.isfinite(r_pares)
        rs = r_pares[ok]

        if rs.size:
            rbar = float(np.mean(rs))
            # Profundidad de muestreo PROMEDIO en la ventana: número medio
            # de series con dato válido por año. ARSTAN usa esto (su columna
            # "cores") en la fórmula de EPS, NO el total de series. Usar el
            # total sobreestimaría el EPS en ventanas donde no todas las
            # series están presentes. Esto es clave para que el EPS coincida
            # con ARSTAN.
            sample_depth = (~np.isnan(win)).sum(axis=1)
            n_eff = float(sample_depth[sample_depth > 0].mean()) \
                if (sample_depth > 0).any() else float(n_series)
            # Fórmula de Wigley et al. (1984): EPS = N·r̄ / (1 + (N−1)·r̄)
            eps = (n_eff * rbar) / (1 + (n_eff - 1) * rbar)
            resultados.append((years[i], rbar, float(eps)))

        if progreso is not None and total > 0 and (k % 10 == 0 or k == total - 1):
            progreso(int(100 * (k + 1) / total))

    if not resultados:
        return pd.DataFrame(columns=["Rbar", "EPS"])

    return pd.DataFrame(resultados, columns=["Anio", "Rbar", "EPS"]).set_index("Anio")


def calcular_rbar(series_dict, nombres):
    series = [series_dict[n]["Ancho_mm"].dropna() for n in nombres if n in series_dict]
    rs = []
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            common = series[i].index.intersection(series[j].index)
            if len(common) < 10:
                continue
            a = series[i].loc[common]
            b = series[j].loc[common]
            if np.std(a) == 0 or np.std(b) == 0:
                continue
            r = np.corrcoef(a, b)[0, 1]
            if np.isfinite(r):
                rs.append(r)
    return float(np.mean(rs)) if rs else np.nan


def calcular_eps(rbar, n):
    if n <= 1 or not np.isfinite(rbar):
        return np.nan
    return (n * rbar) / (1 + (n - 1) * rbar)


def agrupar_por_arbol(nombres) -> dict:
    """Agrupa códigos de serie por ÁRBOL, reutilizando el lector de códigos.

    QLH107A y QLH107B son dos radios del mismo árbol; QLH108A es otro árbol.
    Se usa la misma clave que ordena los archivos al unir: sitio + número,
    ignorando el radio.

    Devuelve {nombre_de_serie: identificador_de_arbol}.
    """
    from modulo_unir import clave_codigo_dendro
    out = {}
    for n in nombres:
        k = clave_codigo_dendro(n)
        out[n] = f"{k[0]}{k[1]}"      # sitio + número de árbol, sin el radio
    return out


def rbar_entre_arboles(series_dict, nombres, min_overlap: int = 10) -> dict:
    """Rbar separando radios del mismo árbol de árboles distintos.

    POR QUÉ IMPORTA
    ---------------
    Dos radios del mismo árbol comparten mucho más que la señal del sitio:
    comparten el individuo, con su microambiente, sus competidores y sus
    daños. Meterlos en la misma bolsa que los pares entre árboles infla el
    Rbar y, con él, la EPS y la SSS. Una colección de 30 radios de 10 árboles
    NO tiene la réplica de 30 árboles.

    Se calculan tres cantidades, como en `rwi.stats` de dplR:

      rbar_wt   correlación media ENTRE radios del mismo árbol
      rbar_bt   correlación media ENTRE árboles distintos
      rbar_eff  el que hay que usar:
                    rbar_bt / (rbar_wt + (1 − rbar_wt)/c_eff)
                donde c_eff es el número efectivo de radios por árbol.

    Cuando cada árbol tiene un solo radio, rbar_eff es igual a rbar_bt y todo
    se reduce al caso simple.
    """
    arbol = agrupar_por_arbol(nombres)
    cols = {}
    for n in nombres:
        v = series_dict.get(n)
        if v is None:
            continue
        col = v["Ancho_mm"] if isinstance(v, pd.DataFrame) else v
        col = pd.to_numeric(col, errors="coerce").dropna()
        if len(col) > 5:
            cols[n] = col
    claves = list(cols)
    if len(claves) < 2:
        return {"rbar_wt": float("nan"), "rbar_bt": float("nan"),
                "rbar_eff": float("nan"), "n_arboles": 0, "c_eff": float("nan")}
    M = pd.concat(cols, axis=1)
    R = M.corr(min_periods=min_overlap)
    wt, bt = [], []
    for i in range(len(claves)):
        for j in range(i + 1, len(claves)):
            r = R.iloc[i, j]
            if not np.isfinite(r):
                continue
            (wt if arbol[claves[i]] == arbol[claves[j]] else bt).append(float(r))
    arboles = {}
    for n in claves:
        arboles.setdefault(arbol[n], []).append(n)
    n_por_arbol = np.array([len(v) for v in arboles.values()], dtype=float)
    rbar_wt = float(np.mean(wt)) if wt else float("nan")
    rbar_bt = float(np.mean(bt)) if bt else float("nan")
    if not wt:
        c_eff = 1.0
        rbar_eff = rbar_bt
    else:
        # Número efectivo de radios por árbol: media armónica, como dplR
        c_eff_rec = float(np.mean(1.0 / n_por_arbol))
        c_eff = 1.0 / c_eff_rec if c_eff_rec > 0 else 1.0
        den = rbar_wt + (1.0 - rbar_wt) * c_eff_rec
        rbar_eff = rbar_bt / den if den > 0 else float("nan")
    return {"rbar_wt": rbar_wt, "rbar_bt": rbar_bt, "rbar_eff": rbar_eff,
            "n_arboles": len(arboles), "c_eff": c_eff,
            "n_pares_wt": len(wt), "n_pares_bt": len(bt)}


def calcular_sss(n_por_anio, n_total, rbar):
    """Subsample Signal Strength: cuánta señal conserva cada año.

        SSS = n·(1 + (N−1)·rbar) / (N·(1 + (n−1)·rbar))

    donde `n` son las series de ese año y `N` el total de la colección.
    Fórmula de dplR (sss.R).

    POR QUÉ ADEMÁS DE LA EPS
    -----------------------
    Las dos responden preguntas distintas y se confunden seguido.

    La EPS compara la cronología contra una POBLACIÓN INFINITA de árboles:
    dice qué fracción de la varianza sería señal si se hubiera muestreado
    todo el rodal. Es una pregunta teórica.

    La SSS compara cada año contra la COLECCIÓN QUE REALMENTE TIENES: dice
    qué fracción de la señal de tu propia cronología conserva el tramo con
    menos series. Es la pregunta práctica cuando hay que decidir desde qué
    año usar la cronología, porque no depende de suponer nada sobre árboles
    que no se muestrearon.

    En el tramo con todas las series la SSS vale 1 por construcción, y va
    bajando hacia el pasado a medida que la profundidad cae. El umbral de uso
    habitual es el mismo 0,85 de la EPS.
    """
    n = np.asarray(n_por_anio, dtype=float)
    N = float(n_total)
    if not np.isfinite(rbar) or N <= 1:
        return np.full(n.shape, np.nan)
    num = n * (1.0 + (N - 1.0) * rbar)
    den = N * (1.0 + (n - 1.0) * rbar)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where((n >= 1) & (den > 0), num / den, np.nan)
    return out


# =============================================================================
# FORMATEADORES HTML PARA STATS
# =============================================================================

def formato_stats_hover_html(year: int, mitad: int, r, glk, t_bp, n) -> str:
    def _f(v, dec=2):
        return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

    if np.isfinite(glk) and n >= 30:
        z = (glk - 0.5) * 2 * np.sqrt(n)
        if z >= 3.29: sig = "***"
        elif z >= 2.58: sig = "**"
        elif z >= 1.96: sig = "*"
        else: sig = ""
    else:
        sig = ""

    return (
        f"<span style='font-size:13px;'>"
        f"<span style='color:#888;'>Año <b>{int(year)}</b> (±{mitad} años) ·</span>&nbsp;&nbsp;"
        f"<b>r</b>=<span style='color:{_color_r(r)}; font-weight:bold;'>{_f(r, 2)}</span>&nbsp;&nbsp;"
        f"<b>GLK</b>=<span style='color:{_color_glk(glk)}; font-weight:bold;'>{_f(glk, 2)}</span>"
        f"<span style='color:#bbb;'>{sig}</span>&nbsp;&nbsp;"
        f"<b>t-BP</b>=<span style='color:{_color_tbp(t_bp)}; font-weight:bold;'>{_f(t_bp, 1)}</span>"
        f"&nbsp;&nbsp;<span style='color:#888;'>n={int(n)}</span>"
        f"</span>"
    )


def formato_stats_global_html(stats: dict) -> str:
    r = stats.get("r", float("nan"))
    glk = stats.get("glk", float("nan"))
    glk_sig = stats.get("glk_sig", "")
    t_bp = stats.get("t_bp", float("nan"))
    n = stats.get("n", 0)

    def _f(v, dec=2):
        return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

    return (
        f"<span style='font-size:13px;'>"
        f"<span style='color:#888;'>Global (n={n}) ·</span>&nbsp;&nbsp;"
        f"<b>r</b>=<span style='color:{_color_r(r)}; font-weight:bold;'>{_f(r, 2)}</span>&nbsp;&nbsp;"
        f"<b>GLK</b>=<span style='color:{_color_glk(glk)}; font-weight:bold;'>{_f(glk, 2)}</span>"
        f"<span style='color:#bbb;'>{glk_sig}</span>&nbsp;&nbsp;"
        f"<b>t-BP</b>=<span style='color:{_color_tbp(t_bp)}; font-weight:bold;'>{_f(t_bp, 1)}</span>"
        f"</span>"
    )


def formato_estadisticos(stats: dict) -> str:
    r = stats.get("r", float("nan"))
    glk = stats.get("glk", float("nan"))
    glk_sig = stats.get("glk_sig", "")
    t_bp = stats.get("t_bp", float("nan"))
    n = stats.get("n", 0)

    def _fmt(v, dec=2):
        return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

    return (f"r={_fmt(r, 2)}  GLK={_fmt(glk, 2)}{glk_sig}  t-BP={_fmt(t_bp, 1)}  n={n}")


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

ESTILO_CHK_COFECHA = (
    "QCheckBox::indicator{width:14px; height:14px; border:2px solid #888; "
    "border-radius:2px; background:transparent;}"
    "QCheckBox::indicator:hover{border:2px solid #FF8C00;}"
    "QCheckBox::indicator:checked{border:2px solid #FF8C00; background:#FF8C00;}"
)



# =============================================================================
# LECTORES DE FORMATO DE ARCHIVO
# =============================================================================

def detectar_precision_tucson(ruta: str) -> dict:
    """Precisión de cada serie de un archivo Tucson, según SU terminador.

    El formato Tucson no declara la precisión: se deduce del marcador de fin
    de cada serie, que es el ÚLTIMO valor escrito. Es la regla que usa dplR en
    `src/readloop.c`:

        terminador  999  ->  las mediciones están en 0,01 mm  (dividir por 100)
        terminador -9999 ->  en 0,001 mm                      (dividir por 1000)
        sin terminador   ->  sin escalar

    Y es POR SERIE, no por archivo: un mismo archivo puede mezclar precisiones
    si se armó juntando mediciones de distintas épocas o equipos.

    DPI dividía siempre por 1000. Con un archivo en centésimas —lo habitual en
    material antiguo y en buena parte de la ITRDB— eso deja todos los anchos
    diez veces más chicos. No se nota en la correlación, porque es un factor
    constante, pero arruina cualquier cifra en milímetros: crecimiento medio,
    incremento en área basal, comparaciones entre sitios.
    """
    ultimo: dict[str, int] = {}
    try:
        with open(ruta, "r", encoding="latin-1") as f:
            for ln in f:
                ln = ln.rstrip("\r\n")
                if len(ln) < 13:
                    continue
                id_serie = ln[:8].strip()
                if not id_serie:
                    continue
                for i in range(10):
                    ini = 12 + i * 6
                    if ini >= len(ln):
                        break
                    tok = ln[ini:ini + 6].strip()
                    if not tok:
                        continue
                    try:
                        ultimo[id_serie] = int(tok)
                    except ValueError:
                        continue
    except Exception:
        return {}
    prec = {}
    for k, v in ultimo.items():
        prec[k] = 100.0 if v == 999 else (1000.0 if v == -9999 else 1.0)
    return prec


def leer_archivo_tucson(ruta: str) -> tuple[pd.DataFrame, str]:
    """Lee un .rwl Tucson UNA serie. Devuelve (DataFrame, id_serie)."""
    anios, mediciones, id_serie = [], [], "Desconocido"
    # Precisión por serie según su marcador de fin (ver
    # detectar_precision_tucson). Antes se dividía siempre por 1000.
    _prec = detectar_precision_tucson(ruta)

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.rstrip("\r\n")
            if not ln or ln.startswith("#"):
                continue
            if ln[:8].strip():
                id_serie = ln[:8].strip()
            try:
                anio_base = int(ln[8:12])
            except ValueError:
                continue
            for i in range(10):
                inicio = 12 + i * 6
                if inicio >= len(ln):
                    break
                token = ln[inicio: inicio + 6].strip()
                if not token:
                    continue
                try:
                    valor = int(token)
                except ValueError:
                    continue
                div = _prec.get(id_serie, TUCSON_DIVISOR)
                # 999 solo es fin de serie cuando el archivo está en
                # centésimas; con precisión de milésimas es un ancho válido
                # de 0,999 mm y NO debe cortar la lectura.
                if valor in (TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE):
                    break
                if valor == 999 and div == 100.0:
                    break
                if valor == TUCSON_VALOR_999:
                    valor = 999
                anios.append(anio_base + i)
                mediciones.append(valor / div)

    df = pd.DataFrame({"Anio": anios, "Ancho_mm": mediciones})
    if df.empty:
        raise ValueError(f"No se encontraron datos válidos en: {os.path.basename(ruta)}")
    df = df.groupby("Anio").mean()
    df.sort_index(inplace=True)
    return df, id_serie


def leer_tucson_multi(ruta: str) -> dict[str, pd.DataFrame]:
    """Lee un .rwl Tucson con UNA o VARIAS series. Devuelve dict {id: DataFrame}."""
    series_dict: dict[str, dict[int, float]] = {}
    # Precisión por serie, deducida de su marcador de fin (ver
    # detectar_precision_tucson). Antes se dividía siempre por 1000.
    _prec = detectar_precision_tucson(ruta)

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.rstrip("\r\n")
            if not ln or ln.startswith("#"):
                continue
            id_serie = ln[:8].strip()
            if not id_serie:
                continue

            try:
                anio_base = int(ln[8:12])
            except ValueError:
                continue

            if id_serie not in series_dict:
                series_dict[id_serie] = {}

            for i in range(10):
                inicio = 12 + i * 6
                if inicio >= len(ln):
                    break
                token = ln[inicio: inicio + 6].strip()
                if not token:
                    continue
                try:
                    valor = int(token)
                except ValueError:
                    continue
                div = _prec.get(id_serie, TUCSON_DIVISOR)
                if valor in (TUCSON_VALOR_FIN, TUCSON_VALOR_FALTANTE):
                    break
                if valor == 999 and div == 100.0:
                    break
                if valor == TUCSON_VALOR_999:
                    valor = 999
                series_dict[id_serie][anio_base + i] = valor / div

    resultado: dict[str, pd.DataFrame] = {}
    for sid, anios_vals in series_dict.items():
        if not anios_vals:
            continue
        df = pd.DataFrame({
            "Anio": list(anios_vals.keys()),
            "Ancho_mm": list(anios_vals.values()),
        })
        df = df.groupby("Anio").mean()
        df.sort_index(inplace=True)
        resultado[sid] = df

    if not resultado:
        raise ValueError(f"No se encontraron series válidas en: {os.path.basename(ruta)}")
    return resultado


def leer_formato_compacto(ruta: str, divisor: float = 100.0) -> dict:
    """Lee formato compacto FORTRAN (20F4.0) de CATRAS/Heidelberg."""
    import re
    series_dict = {}
    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        lineas = f.readlines()

    i = 0
    while i < len(lineas):
        linea = lineas[i].rstrip('\n\r')
        if not linea:
            i += 1
            continue

        if "=N" in linea and "=I" in linea:
            match_i = re.search(r'(\d+)=I', linea)
            anio_inicio = int(match_i.group(1)) if match_i else 0

            partes = linea.split('=I')
            if len(partes) > 1:
                subpartes = partes[1].strip().split()
                serie_id = subpartes[0] if subpartes else f"Serie_{len(series_dict)+1}"
            else:
                serie_id = f"Serie_{len(series_dict)+1}"

            i += 1
            valores = []
            while i < len(lineas) and "=N" not in lineas[i] and "=I" not in lineas[i]:
                linea_datos = lineas[i].rstrip('\n\r')
                for j in range(0, len(linea_datos), 4):
                    chunk = linea_datos[j:j+4]
                    if chunk.strip():
                        try:
                            valores.append(float(chunk.strip()) / divisor)
                        except ValueError:
                            pass
                i += 1

            if valores:
                anios = list(range(anio_inicio, anio_inicio + len(valores)))
                df = pd.DataFrame({"Anio": anios, "Ancho_mm": valores})
                df.set_index("Anio", inplace=True)
                series_dict[serie_id] = df
        else:
            i += 1

    return series_dict


def leer_dendro_auto(ruta: str):
    """Detecta formato y deriva al parser correcto.

    Acepta Tucson (.rwl/.txt), compacto, CooRecorder (.wid) y también
    formatos de COLUMNA (año + valor) en texto, CSV, Excel y ODS. Esto
    último es necesario porque las cronologías que genera DPI se exportan en
    dos columnas: sin esto no se podían volver a cargar como referencia.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext == '.wid':
        return leer_wid(ruta)

    # Planillas: no son texto, van directo al lector tabular
    if _es_planilla(ext):
        return leer_tabular(ruta)

    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        primeras_lineas = f.read(500)

    if "=N" in primeras_lineas and "=I" in primeras_lineas:
        return leer_formato_compacto(ruta)

    if ext in ('.csv', '.tsv'):
        return leer_tabular(ruta)

    # .txt y .rwl pueden ser Tucson o dos columnas. Se decide mirando la
    # primera línea con datos: en Tucson el segundo campo es un año de cuatro
    # dígitos y vienen varios enteros después. Un archivo de dos columnas
    # (año + valor decimal) leído como Tucson devuelve valores absurdos, así
    # que conviene descartarlo antes de intentarlo.
    def _parece_tucson(texto: str) -> bool:
        for linea in texto.splitlines():
            campos = linea.split()
            if len(campos) < 3:
                continue
            try:
                anio = int(campos[1])
            except ValueError:
                return False  # encabezado tipo "Anio  Valor"
            if not (-12000 <= anio <= 3000):
                return False
            # En Tucson todos los valores son ENTEROS
            try:
                for v in campos[2:]:
                    int(v)
            except ValueError:
                return False
            return True
        return False

    if _parece_tucson(primeras_lineas):
        try:
            df, nombre = leer_archivo_tucson(ruta)
            if df is not None and not df.empty:
                return df, nombre
        except Exception:
            pass
    return leer_tabular(ruta)


def leer_wid(ruta: str) -> tuple[pd.DataFrame, str]:
    """Lee CooRecorder .wid. Devuelve (DataFrame, nombre)."""
    anchos: list[float] = []
    anio_corteza: int | None = None
    nombre = os.path.splitext(os.path.basename(ruta))[0]

    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            ln = linea.strip()
            if not ln:
                continue
            if ln.startswith("#C DATED"):
                try:
                    anio_corteza = int(ln.split()[2])
                except (IndexError, ValueError):
                    logger.warning("leer_wid: no se pudo parsear #C DATED en '%s'", ruta)
                continue
            if ln.startswith("#"):
                continue
            token = ln.replace(",", ".")
            try:
                anchos.append(float(token))
            except ValueError:
                logger.debug("leer_wid: token ignorado '%s'", ln)

    if not anchos:
        raise ValueError(f"No se encontraron datos de ancho en: {os.path.basename(ruta)}")

    n = len(anchos)
    if anio_corteza is None:
        import datetime
        anio_corteza = datetime.date.today().year
        logger.warning("leer_wid: '%s' sin #C DATED, usando año actual.", ruta)

    anio_medula = anio_corteza - n + 1
    anios = list(range(anio_medula, anio_corteza + 1))

    df = pd.DataFrame({"Ancho_mm": anchos}, index=pd.Index(anios, name="Anio"))
    df.sort_index(inplace=True)
    return df, nombre


def leer_tabular(ruta: str) -> tuple[pd.DataFrame, str]:
    """Lee CSV/TSV/TXT/Excel con detección automática de header, decimal, separador."""
    ext = os.path.splitext(ruta)[1].lower()

    def _leer_excel(con_header):
        return _leer_planilla(ruta, header=0 if con_header else None)

    def _leer_csv(con_header, decimal="."):
        try:
            return pd.read_csv(
                ruta, header=0 if con_header else None,
                sep=None, engine="python", decimal=decimal,
                encoding="utf-8", encoding_errors="replace",
            )
        except Exception:
            return pd.read_csv(
                ruta, header=0 if con_header else None,
                sep=r"[\s,;\t]+", engine="python", decimal=decimal,
                encoding="utf-8", encoding_errors="replace",
            )

    if _es_planilla(ext):
        df_sondeo = _leer_excel(con_header=False)
    else:
        df_sondeo = _leer_csv(con_header=False)

    if df_sondeo.empty or df_sondeo.shape[1] < 2:
        raise ValueError(f"El archivo debe tener al menos dos columnas: {os.path.basename(ruta)}")

    primera = df_sondeo.iloc[0]
    tiene_header = False
    for val in primera:
        s = str(val).strip().replace(",", ".")
        try:
            float(s)
        except (ValueError, TypeError):
            tiene_header = True
            break

    if _es_planilla(ext):
        df = _leer_excel(con_header=tiene_header)
    else:
        df = _leer_csv(con_header=tiene_header)

    if not tiene_header:
        df.columns = [f"col{i}" for i in range(df.shape[1])]

    if not _es_planilla(ext) and df.shape[1] >= 2:
        test_col = df.iloc[:, 1]
        if pd.to_numeric(test_col, errors="coerce").isna().all() and len(test_col):
            try:
                df = _leer_csv(con_header=tiene_header, decimal=",")
                if not tiene_header:
                    df.columns = [f"col{i}" for i in range(df.shape[1])]
            except Exception:
                pass

    cols = list(df.columns)

    nombres_anio = {"anio", "año", "year", "anios", "años", "yr"}
    year_col = None
    for c in cols:
        if str(c).strip().lower() in nombres_anio:
            year_col = c
            break

    if year_col is None:
        for c in cols:
            test = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(test) > 0 and test.between(-10000, 10000).all():
                if test.std() > 1 and (test % 1 == 0).all():
                    year_col = c
                    break

    if year_col is None:
        raise ValueError(f"No se encontró columna de año en: {os.path.basename(ruta)}")

    nombres_excluidos = {
        str(year_col).strip().lower(),
        "id_serie", "id", "serie", "muestra", "sample", "code",
        "n", "sd", "se", "samp", "samp.depth", "sample.depth",
    }
    value_col = None
    for c in cols:
        if str(c).strip().lower() in nombres_excluidos:
            continue
        test = pd.to_numeric(df[c], errors="coerce")
        if test.notna().sum() > 0:
            value_col = c
            break

    if value_col is None:
        raise ValueError(f"No se encontró columna de valores en: {os.path.basename(ruta)}")

    df_out = pd.DataFrame({
        "Anio": pd.to_numeric(df[year_col], errors="coerce"),
        "Ancho_mm": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()

    if df_out.empty:
        raise ValueError(f"No se encontraron datos válidos en: {os.path.basename(ruta)}")

    df_out["Anio"] = df_out["Anio"].astype(int)
    df_out = df_out.groupby("Anio", as_index=True).mean(numeric_only=True)
    df_out.index.name = "Anio"
    df_out.sort_index(inplace=True)

    nombre = os.path.splitext(os.path.basename(ruta))[0]
    return df_out, nombre


def _indexar_columna_multi(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Toma una tabla cruda (año + N columnas de valor) y la devuelve indexada
    por año, con las columnas convertidas a numérico y sin las auxiliares."""
    if df_raw.shape[1] < 2:
        raise ValueError("El archivo debe tener al menos dos columnas (año + valor[es]).")

    df_raw = df_raw.copy()
    cols = list(df_raw.columns)
    year_col = None
    for c in cols:
        if str(c).lower() in ("anio", "año", "year", "anios", "años"):
            year_col = c
            break
    if year_col is None:
        year_col = cols[0]

    df_raw[year_col] = pd.to_numeric(df_raw[year_col], errors="coerce")
    df_raw = df_raw.dropna(subset=[year_col])
    df_raw[year_col] = df_raw[year_col].astype(int)
    df_raw.set_index(year_col, inplace=True)
    df_raw.index.name = "Anio"
    df_raw.sort_index(inplace=True)

    for c in df_raw.columns:
        df_raw[c] = pd.to_numeric(df_raw[c], errors="coerce")

    cols_valor = [c for c in df_raw.columns
                  if str(c).strip().lower() not in (
                      "n", "sd", "se", "samp", "samp.depth", "sample.depth",
                      "id_serie", "id", "serie", "muestra", "sample", "code"
                  )]
    if not cols_valor:
        raise ValueError("No se encontraron columnas de valores (todo es N/SD).")

    return df_raw[cols_valor]


def _leer_crudo_tabular(ruta: str) -> pd.DataFrame:
    """Lee la tabla cruda de un archivo (primera hoja si es planilla)."""
    ext = os.path.splitext(ruta)[1].lower()

    if _es_planilla(ext):
        return _leer_planilla(ruta)

    try:
        df_raw = pd.read_csv(ruta, sep=None, engine="python",
                             encoding="utf-8", encoding_errors="replace")
    except Exception:
        df_raw = pd.read_csv(ruta, sep=r"[\s,;\t]+", engine="python",
                             encoding="utf-8", encoding_errors="replace")

    if df_raw.shape[1] >= 2:
        test = pd.to_numeric(df_raw.iloc[1:, 1], errors="coerce")
        if test.isna().all() and len(test) > 0:
            try:
                df_raw = pd.read_csv(ruta, sep=None, engine="python", decimal=",",
                                     encoding="utf-8", encoding_errors="replace")
            except Exception:
                pass
    return df_raw


def leer_columna_multi(ruta: str) -> pd.DataFrame:
    """Lee archivo con N columnas de valor, devuelve DataFrame con índice año."""
    return _indexar_columna_multi(_leer_crudo_tabular(ruta))


def leer_columna_multi_hojas(ruta: str) -> dict[str, pd.DataFrame]:
    """Igual que `leer_columna_multi` pero devuelve TODAS las hojas.

    pandas lee solo la primera hoja por defecto, así que un .ods/.xlsx con
    varias cronologías en hojas distintas mostraba solo una. Devuelve un dict
    {nombre_hoja: df_indexado}; para archivos de texto devuelve una sola
    entrada con clave "".
    """
    if not _es_planilla(ruta):
        return {"": leer_columna_multi(ruta)}

    hojas = _leer_planilla(ruta, sheet_name=None)  # dict {hoja: df}
    if not isinstance(hojas, dict):
        hojas = {"": hojas}

    salida = {}
    for nombre_hoja, df_hoja in hojas.items():
        try:
            df_idx = _indexar_columna_multi(df_hoja)
        except Exception:
            continue  # hoja sin formato de cronología (notas, etc.)
        if not df_idx.empty:
            salida[str(nombre_hoja)] = df_idx
    if not salida:
        raise ValueError("Ninguna hoja tiene formato de cronología (año + valores).")
    return salida


# =============================================================================
# CRONOLOGÍA: NORMALIZACIÓN Y CONSTRUCCIÓN
# =============================================================================

def _biweight_mean(values, c: float = 6.0) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan
    if len(x) < 3:
        return float(np.mean(x))
    m = np.median(x)
    mad = np.median(np.abs(x - m))
    if mad == 0:
        return float(np.mean(x))
    u = (x - m) / (c * mad)
    mask = np.abs(u) < 1
    if not np.any(mask):
        return float(np.mean(x))
    w = (1 - u[mask] ** 2) ** 2
    return float(np.sum((x[mask] - m) * w) / np.sum(w) + m)


from scipy.linalg import solveh_banded


def _spline_cook(y: np.ndarray, nyrs: float = 32.0, f: float = 0.5) -> np.ndarray:
    """Spline cúbico de suavizado de Cook & Peters (1981).

    Es el spline estándar de la dendrocronología (ARSTAN, COFECHA, dplR): se
    define por su RESPUESTA DE FRECUENCIA, no por un parámetro arbitrario de
    suavizado. Con los valores por defecto, una oscilación de `nyrs` años
    conserva el 50% de su amplitud; las más rápidas se atenúan y las más
    lentas pasan casi intactas. Eso es justo lo que se quiere para quitar la
    tendencia de crecimiento por edad conservando la señal climática.

    Minimiza  Σ(yᵢ−gᵢ)² + λ·∫g″², resuelto por el algoritmo de Reinsch:
      (R + λ·QᵀQ)·c = Qᵀy   →   g = y − λ·Q·c
    con Q las segundas diferencias y R tridiagonal (2/3 en la diagonal,
    1/6 fuera). Para datos equiespaciados la respuesta es
      H(ω) = 1 / (1 + λ·48·sin⁴(ω/2)/(2+cos ω))
    y de ahí se despeja λ para que H(2π/nyrs) = f.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 4:
        return np.full(n, float(np.mean(y)) if n else 0.0)

    nyrs = max(float(nyrs), 2.5)  # por debajo de ~2 años no hay señal muestreable
    f = min(max(float(f), 1e-6), 1.0 - 1e-6)
    w = 2.0 * np.pi / nyrs
    cw = np.cos(w)
    lam = (1.0 / f - 1.0) * (2.0 + cw) / (12.0 * (1.0 - cw) ** 2)

    m = n - 2
    # A = R + λ·QᵀQ: simétrica pentadiagonal (Toeplitz para paso constante)
    ab = np.zeros((3, m))
    if m > 2:
        ab[0, 2:] = lam
    if m > 1:
        ab[1, 1:] = 1.0 / 6.0 - 4.0 * lam
    ab[2, :] = 2.0 / 3.0 + 6.0 * lam

    qty = y[:-2] - 2.0 * y[1:-1] + y[2:]
    try:
        c = solveh_banded(ab, qty, lower=False)
    except Exception:
        return np.full(n, float(np.mean(y)))

    # (Q·c)ᵢ = cᵢ − 2cᵢ₋₁ + cᵢ₋₂  (c extendido con ceros en los bordes)
    cp = np.zeros(n + 2)
    cp[2:2 + m] = c
    qc = cp[2:n + 2] - 2.0 * cp[1:n + 1] + cp[0:n]
    return y - lam * qc


RIGIDEZ_SPLINE_DEFECTO = 32  # rigidez del spline de detrend (años, estilo COFECHA)


def _fit_trend(values: np.ndarray, metodo: str, ventana_mm: int | None = None,
               rigidez: int | None = None) -> np.ndarray:
    """Ajusta tendencia a la serie según el método indicado.

    Parameters
    ----------
    values : array
        Valores de la serie.
    metodo : str
        Método de ajuste: 'spline', 'negexp', 'linear', 'media_movil', 'mean'.
    ventana_mm : int, opcional
        Ventana (en años) para 'media_movil'. Si None, usa el 10% del largo
        de la serie (estilo ARSTAN). Solo aplica si metodo='media_movil'.
    """
    from scipy.interpolate import UnivariateSpline
    from scipy.optimize import curve_fit

    y = np.asarray(values, dtype=float)
    x = np.arange(len(y), dtype=float)
    m = np.isfinite(y)
    if m.sum() < 3:
        return np.full_like(y, np.nanmean(y[m]) if m.any() else np.nan, dtype=float)

    x_fit = x[m]
    y_fit = y[m]
    metodo = (metodo or "spline").lower()

    if metodo in {"raw", "none", "ninguno"}:
        return np.full_like(y, np.nanmean(y_fit), dtype=float)
    if metodo in {"mean", "media"}:
        return np.full_like(y, np.nanmean(y_fit), dtype=float)
    if metodo in {"linear", "lineal"}:
        p = np.polyfit(x_fit, y_fit, 1)
        return np.polyval(p, x)
    if metodo in {"negexp", "negative_exponential", "exponencial", "exp"}:
        def f(t, a, b, c):
            return a * np.exp(-b * t) + c
        a0 = max(float(np.nanmax(y_fit) - np.nanmin(y_fit)), 1e-3)
        b0 = 0.01
        c0 = float(np.nanmin(y_fit))
        try:
            popt, _ = curve_fit(
                f, x_fit, y_fit, p0=(a0, b0, c0), maxfev=20000,
                bounds=([0.0, 0.0, -np.inf], [np.inf, 10.0, np.inf]),
            )
            return f(x, *popt)
        except Exception:
            p = np.polyfit(x_fit, y_fit, 1)
            return np.polyval(p, x)
    if metodo in {"spline", "spl", "cubic_spline"}:
        try:
            # Spline cúbico de suavizado de Cook & Peters (1981), el estándar
            # de la dendrocronología (ARSTAN/COFECHA/dplR): definido por su
            # respuesta de frecuencia (50% a RIGIDEZ_SPLINE_DEFECTO años).
            #
            # Antes se usaba UnivariateSpline de scipy con un parámetro `s`
            # heurístico, que no equivale al spline dendrocronológico: dejaba
            # estructura distinta en los residuos y (con s = len·var·0.8)
            # podía degenerar en una cúbica que CRUZABA CERO en los extremos,
            # haciendo explotar el índice serie/tendencia.
            # La rigidez llega desde arriba: la opción 1 de la corrida.
            # Antes se usaba siempre la constante del módulo, así que cambiar
            # el spline en la interfaz no alteraba el resultado en absoluto.
            #
            # El spline se ajusta sobre el LOGARITMO del ancho y después se
            # exponencia. Así la curva es positiva por construcción y no hace
            # falta ninguna guarda.
            #
            # Ajustado en escala lineal, el spline sobrepasa hacia abajo en los
            # extremos de la serie y puede cruzar cero. La guarda que había
            # solo atrapaba los valores <= 0, así que un valor diminuto pero
            # POSITIVO pasaba y el índice explotaba: en DBC200B la tendencia
            # bajaba a 0.00094 en 2023 y el índice de ese año llegaba a 268,
            # cuando un índice normal ronda 1. Eso hundía la correlación de la
            # serie con la maestra a -0.132 donde COFECHA da +0.434.
            #
            # Medido sobre las 36 series de cos8.rwl contra la corrida real de
            # COFECHA, el cambio mejora todo a la vez:
            #
            #                        err medio  err máx  intercorrelación
            #   escala lineal          0.0646    0.566        0.425
            #   sobre el logaritmo     0.0519    0.131        0.455
            #                                            (COFECHA .463)
            #
            # y el índice máximo de toda la colección baja de 265 a 4.4.
            # Spline en ESCALA LINEAL, con piso en el 10 % de la media.
            #
            # El spline de Cook se ajusta a la serie cruda: así lo hace su
            # Fortran original (capsf.f95, que verificamos idéntico al
            # nuestro) y así lo usa COFECHA. Antes lo ajustábamos sobre el
            # logaritmo para garantizar positividad, y eso mejoraba mientras
            # el AR estaba mal puesto; corregido el AR, la escala lineal pasa
            # a ganar en todo.
            #
            # El piso resuelve el problema de la escala lineal: el spline
            # sobrepasa hacia abajo en los extremos y puede acercarse a cero,
            # disparando el índice (en DBC200B llegaba a 268 con un valor de
            # tendencia de 0,00094). Ninguna curva de crecimiento real baja al
            # 10 % de la media de su serie.
            #
            # El 10 % no es arbitrario: se barrió contra la corrida real de
            # COFECHA sobre cos8.rwl.
            #
            #   piso   maestra   error   DBC200B
            #   0.05    0.9549   0.0518    0.360   <- choca con la guarda del 5 %
            #   0.10    0.9709   0.0359    0.425
            #   0.15    0.9690   0.0381    0.421
            #   0.25    0.9647   0.0416    0.440
            #
            # Con 0.05 o menos el valor recortado queda por debajo del umbral
            # de la guarda de `_detrend_serie_indice`, que entonces descarta la
            # curva entera y usa la media: por eso esas filas coinciden con el
            # respaldo total. El 10 % deja las dos protecciones sin pisarse.
            _y = np.asarray(y_fit, dtype=float)
            _sp = np.asarray(_spline_cook(
                _y, nyrs=float(rigidez or RIGIDEZ_SPLINE_DEFECTO), f=0.5))
            _pos = _y[_y > 0]
            _piso = 0.10 * float(np.nanmean(_pos)) if _pos.size else 1e-6
            tend = np.maximum(_sp, _piso)
            if len(tend) != len(x):
                tend = np.interp(x, x_fit, tend)
            # Guarda de positividad: el crecimiento no puede ser negativo, así
            # que cualquier tramo de tendencia ≤0 (o no finito) se reemplaza por
            # la media para no hacer explotar el índice al dividir.
            media = float(np.nanmean(y_fit))
            tend = np.where(np.isfinite(tend) & (tend > 0), tend, media)
            return tend
        except Exception:
            p = np.polyfit(x_fit, y_fit, 1)
            return np.polyval(p, x)
    if metodo in {"media_movil", "moving_average", "ma"}:
        # Si el usuario especifica ventana, usar esa. Si no, default ARSTAN-like.
        if ventana_mm is not None and ventana_mm >= 3:
            w = int(ventana_mm)
        else:
            w = max(3, int(round(len(y_fit) * 0.10)))
        if w % 2 == 0:
            w += 1
        return pd.Series(y).rolling(window=w, center=True, min_periods=1).mean().to_numpy(dtype=float)
    p = np.polyfit(x_fit, y_fit, 1)
    return np.polyval(p, x)


def _detrend_serie_indice(serie_mm: pd.Series, metodo: str,
                           ventana_mm: int | None = None,
                           rigidez: int | None = None) -> pd.Series:
    s = pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
    if s.empty:
        return s.copy()
    if (metodo or "").lower() in {"raw", "none", "ninguno"}:
        return s.copy()
    tendencia = _fit_trend(s.to_numpy(dtype=float), metodo,
                           ventana_mm=ventana_mm, rigidez=rigidez)
    tendencia = pd.Series(tendencia, index=s.index, dtype=float)
    # Guarda de positividad, al estilo de ARSTAN y dplR: si ALGÚN valor de la
    # curva sale ≤ 0 o no finito, se descarta la curva ENTERA y se usa la
    # media de la serie. Es el «dirty dog» que ARSTAN pide graficar.
    #
    # Antes se parchaban solo los años malos, y eso dejaba una serie cuyo
    # índice significa una cosa en un tramo y otra en el resto: unos años
    # divididos por su tendencia local y otros por la media global. Peor aún,
    # el parche solo atrapaba los valores ≤ 0, así que una tendencia diminuta
    # pero positiva pasaba y disparaba el índice (en DBC200B llegó a 268).
    #
    # Reemplazar la curva completa es más honesto: la serie queda
    # consistentemente sin detrending, y el diálogo de curvas negativas de la
    # pestaña de cronología avisa y deja elegir otro método.
    # El umbral no es cero sino el 5 % de la media de la serie. dplR solo
    # comprueba <= 0, pero una tendencia POSITIVA y diminuta hace el mismo
    # daño: en QLH026a el ajuste lineal nunca cruza cero y aun así produce un
    # índice de 43,5, cuando la razón entre el anillo más ancho y la media es
    # apenas 4,6. Ninguna curva de crecimiento real baja al 5 % de la media
    # de la serie, así que llegar ahí es señal de que el ajuste se rompió.
    tv = tendencia.to_numpy(dtype=float)
    media_s = float(np.nanmean(s.to_numpy(dtype=float)))
    piso = 0.05 * media_s if np.isfinite(media_s) and media_s > 0 else 0.0
    if not np.all(np.isfinite(tv)) or np.any(tv <= piso):
        tendencia = pd.Series(np.full(len(tendencia), media_s),
                              index=tendencia.index)
    idx = (s / tendencia).replace([np.inf, -np.inf], np.nan).dropna()
    return idx


ORDEN_AR_MAXIMO = 3  # orden máximo del modelo AR (COFECHA usa hasta 3)


def _ajustar_ar_yule_walker(x: np.ndarray, p: int):
    """Ajusta un AR(p) por Yule-Walker (recursión de Levinson-Durbin).

    Devuelve (coeficientes phi, varianza residual). `x` debe venir centrado.
    """
    n = len(x)
    if p <= 0:
        return np.array([]), float(np.var(x))
    # Autocovarianzas r[0..p]
    r = np.array([np.dot(x[k:], x[:n - k]) / n if k else np.dot(x, x) / n
                  for k in range(p + 1)])
    if r[0] <= 0:
        return np.zeros(p), 0.0
    phi = np.zeros(p)
    v = r[0]
    for k in range(1, p + 1):
        # Coeficiente de reflexión
        acum = r[k] - np.dot(phi[:k - 1], r[1:k][::-1]) if k > 1 else r[1]
        if v <= 0:
            break
        kappa = acum / v
        nuevo = phi[:k - 1] - kappa * phi[:k - 1][::-1] if k > 1 else np.array([])
        phi[:k - 1] = nuevo
        phi[k - 1] = kappa
        v *= (1.0 - kappa * kappa)
        if v <= 0:
            v = 1e-12
            break
    return phi[:p], float(v)


def _seleccionar_orden_ar(x: np.ndarray, max_orden: int = ORDEN_AR_MAXIMO) -> int:
    """Elige el orden del AR minimizando el AIC, como hace COFECHA.

    COFECHA ajusta modelos autorregresivos de distinto orden y se queda con
    el mejor según el criterio de Akaike (la columna 'AR()' de su salida).
    DPI usaba AR(1) fijo para todas las series, lo que dejaba autocorrelación
    sin remover en las series que necesitan orden mayor.
    """
    n = len(x)
    max_orden = int(max(0, min(max_orden, n // 10, 10)))
    if n < 20 or max_orden < 1:
        return min(1, max_orden)
    # El orden mínimo es 1, no 0: cuando el modelo autorregresivo está
    # activado, COFECHA nunca informa orden 0 — sus corridas con AR dan 1, 2
    # o 3, y solo la corrida SIN AR muestra 0. Permitir el 0 dejaba series sin
    # blanquear que en COFECHA sí lo están.
    # CRITERIO: BIC, no AIC.
    #
    # Comparado contra los órdenes AR que informa COFECHA en su Parte 7 —un
    # entero, así que la coincidencia no admite interpretación— sobre las 36
    # series de cos8.rwl:
    #
    #     BIC   33/36  (92 %)
    #     PACF  32/36  (89 %)
    #     AICc  25/36  (69 %)
    #     AIC   24/36  (67 %)
    #     FPE   24/36  (67 %)
    #
    # El BIC penaliza los parámetros con log(n) en vez de 2, así que prefiere
    # modelos más simples. Coincide con lo que se ve en COFECHA: de sus 36
    # series, 30 salen con orden 1 y solo 2 llegan a 3.
    mejor_orden, mejor_pun = 1, np.inf
    for p in range(1, max_orden + 1):
        _, v = _ajustar_ar_yule_walker(x, p)
        if not np.isfinite(v) or v <= 0:
            continue
        pun = n * np.log(v) + p * np.log(n)
        if pun < mejor_pun - 1e-9:
            mejor_pun, mejor_orden = pun, p
    return mejor_orden


def _residualizar_indice(indice: pd.Series, max_orden: int | None = None,
                          devolver_orden: bool = False):
    """Quita la autocorrelación del índice con un modelo AR.

    El orden se elige automáticamente por AIC (como COFECHA). Antes se usaba
    siempre AR(1), lo que dejaba autocorrelación residual en las series que
    requieren orden 2 o 3.
    """
    s = pd.to_numeric(indice, errors="coerce").astype(float).dropna()
    if len(s) < 4:
        return (s.copy(), 0) if devolver_orden else s.copy()
    c = s - s.mean()
    x = c.to_numpy(dtype=float)
    if np.std(x) == 0:
        return (s.copy(), 0) if devolver_orden else s.copy()

    if max_orden is None:
        max_orden = ORDEN_AR_MAXIMO
    p = _seleccionar_orden_ar(x, max_orden)
    if p <= 0:
        resid_v = x.copy()
    else:
        phi, _ = _ajustar_ar_yule_walker(x, p)
        resid_v = x.copy()
        # e_t = x_t - Σ phi_i · x_{t-i}   (los primeros p quedan sin modelo)
        for t in range(p, len(x)):
            resid_v[t] = x[t] - float(np.dot(phi, x[t - p:t][::-1]))

    resid = pd.Series(resid_v, index=s.index)
    # Se devuelve el nivel de la serie ORIGINAL, no 1.0.
    #
    # Es lo que hace dplR en `ar.func`: `y <- ar1$resid + ar1$x.mean`, o sea
    # que a los residuos les suma la media de la serie de entrada. DPI sumaba
    # 1.0 fijo. Para la correlación da lo mismo —es un desplazamiento— pero
    # NO da lo mismo para el logaritmo que viene después, porque log(x + m/6)
    # no es lineal: desplazar la serie antes de aplicarlo cambia los valores
    # de forma no afín.
    #
    # Medido contra las 136 correlaciones por segmento de la Parte 5 de
    # COFECHA: el sesgo baja de -0.0206 a -0.0176 y la desviación media de
    # 0.0750 a 0.0734.
    resid = resid - resid.mean() + float(s.mean())
    return (resid, p) if devolver_orden else resid


def _normalizar_serie_para_tipo(serie_mm: pd.Series, tipo_cronologia: str,
                                  metodo_estandarizacion: str,
                                  ventana_mm: int | None = None,
                                  aplicar_log: bool = False) -> pd.Series:
    tipo = (tipo_cronologia or "raw").lower()
    if tipo == "raw":
        return pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
    idx = _detrend_serie_indice(serie_mm, metodo_estandarizacion, ventana_mm=ventana_mm)
    # Log estilo COFECHA (Holmes 1983): se aplica al índice de razón (media ~1)
    # antes del modelo autorregresivo. Comprime los anillos anchos y suele
    # subir la correlación de cofechado. Debe aplicarse por igual a la
    # cronología y a las series para que queden en el mismo espacio.
    if aplicar_log and not idx.empty:
        media = float(idx.mean())
        c_const = media / 6.0 if media > 0 else 0.001
        idx = pd.Series(
            np.log(np.maximum(idx.to_numpy(dtype=float) + c_const, 1e-10)),
            index=idx.index)
    if tipo == "residual":
        return _residualizar_indice(idx)
    return idx


METODOS_DETREND = ("spline", "negexp", "linear", "media_movil", "media")


def diagnosticar_curva(serie_mm: pd.Series, metodo: str,
                        ventana_mm: int | None = None,
                        rigidez: int | None = None) -> dict:
    """Comprueba si la curva de ajuste cruza cero — el «dirty dog» de ARSTAN.

    Con series de caída muy fuerte, la exponencial negativa o la recta pueden
    bajar de cero. Ahí el índice queda indefinido o negativo, y dividir por un
    número cercano a cero lo dispara: medido sobre una serie real de ciprés,
    el ajuste lineal cruzaba cero en 24 de 422 años y producía un índice
    máximo de 96, cuando un índice normal ronda 1.

    DPI nunca devuelve índices negativos porque reemplaza la tendencia por la
    media de la serie donde sale <= 0. El problema no es que explote: es que
    parchaba en SILENCIO, y esos años quedan divididos por la media global en
    vez de por su tendencia local, así que su índice no significa lo mismo que
    el del resto de la serie.

    Devuelve:
      n_parches   años cuya tendencia hubo que reemplazar
      total       largo de la serie
      tramos      lista de (año inicial, año final) de los tramos parchados
      indice      la serie de índice resultante
      indice_max  máximo del índice; sobre 3 o 4 es señal de alarma
      valido      True si la curva no cruzó cero en ningún año
    """
    s = pd.to_numeric(serie_mm, errors="coerce").dropna().astype(float)
    vacio = {"n_parches": 0, "total": 0, "tramos": [], "indice": s.iloc[0:0],
             "indice_max": float("nan"), "valido": False}
    if len(s) < 8:
        return vacio
    try:
        tend = _fit_trend(s.to_numpy(dtype=float), metodo,
                          ventana_mm=ventana_mm, rigidez=rigidez)
    except Exception:
        return vacio
    tend = np.asarray(tend, dtype=float)
    # Mismo criterio que la guarda de `_detrend_serie_indice`: el 5 % de la
    # media, no el cero. Si no, el diálogo no avisaría de los casos donde la
    # curva no cruza cero pero igual dispara el índice.
    vals = s.to_numpy(dtype=float)
    med = float(np.nanmean(vals)) if len(vals) else 0.0
    piso = 0.05 * med if np.isfinite(med) and med > 0 else 0.0
    malo = ~np.isfinite(tend) | (tend <= piso)
    anios = s.index.to_numpy(np.int64)

    tramos = []
    if malo.any():
        ini = None
        for k, m in enumerate(malo):
            if m and ini is None:
                ini = k
            elif not m and ini is not None:
                tramos.append((int(anios[ini]), int(anios[k - 1])))
                ini = None
        if ini is not None:
            tramos.append((int(anios[ini]), int(anios[-1])))

    idx = _detrend_serie_indice(s, metodo, ventana_mm=ventana_mm,
                                rigidez=rigidez)
    return {
        "n_parches": int(malo.sum()), "total": int(len(s)),
        "tramos": tramos, "indice": idx,
        "indice_max": float(idx.max()) if len(idx) else float("nan"),
        "valido": not bool(malo.any()),
    }


def detectar_series_problematicas(series: dict, nombres: list,
                                   metodo: str, ventana_mm=None,
                                   rigidez=None) -> dict:
    """Series cuya curva cruza cero con el método elegido."""
    fuera = {}
    for n in nombres:
        if n not in series:
            continue
        col = series[n]["Ancho_mm"] if isinstance(series[n], pd.DataFrame) \
            else series[n]
        d = diagnosticar_curva(col, metodo, ventana_mm, rigidez)
        if d["n_parches"] > 0:
            fuera[n] = d
    return fuera


def elegir_metodo_para_grupo(series: dict, problematicas: list,
                              maestra: pd.Series,
                              metodos=METODOS_DETREND,
                              ventana_mm=None, rigidez=None) -> dict:
    """Elige UN método para todas las series con curva negativa.

    Dos etapas, y el orden importa:

    1. **Filtro duro:** se descarta cualquier método que cruce cero en alguna
       de las series del grupo. Ahí el índice no significa nada.
    2. **Entre los que sobreviven, la mediana de la correlación con la
       maestra.** No se usa el índice máximo como criterio, aunque delate bien
       los casos rotos, porque un máximo cercano a 1 se consigue de dos
       maneras opuestas: porque la curva ajusta bien, o porque ajusta DEMASIADO
       y se come toda la variabilidad. La correlación distingue esos dos casos;
       el máximo no. Tampoco sirve la sensibilidad media: medida sobre cinco
       métodos en la misma serie da 0,260 a 0,269, o sea que el método de
       estandarización no toca la alta frecuencia.

    Se elige sobre el GRUPO y no serie por serie, porque el informe tiene que
    poder decir «las N series con curva negativa se estandarizaron con X».
    Optimizar la primera serie puede castigar a las otras cinco.

    Devuelve {"metodo": str|None, "tabla": [...]} con el detalle por método.
    """
    tabla = []
    for m in metodos:
        rs, maxs, cruces = [], [], 0
        for n in problematicas:
            col = series[n]["Ancho_mm"] if isinstance(series[n], pd.DataFrame) \
                else series[n]
            d = diagnosticar_curva(col, m, ventana_mm, rigidez)
            cruces += d["n_parches"]
            idx = d["indice"]
            if idx is None or len(idx) < 10:
                continue
            maxs.append(d["indice_max"])
            com = idx.index.intersection(maestra.index)
            if len(com) >= 20:
                a = idx.loc[com].to_numpy(dtype=float)
                b = maestra.loc[com].to_numpy(dtype=float)
                if np.std(a) > 1e-12 and np.std(b) > 1e-12:
                    rs.append(float(np.corrcoef(a, b)[0, 1]))
        tabla.append({
            "metodo": m, "cruces": cruces,
            "valido": cruces == 0,
            "r_mediana": float(np.median(rs)) if rs else float("nan"),
            "indice_max": float(np.max(maxs)) if maxs else float("nan"),
            "n_series": len(rs),
        })
    validos = [t for t in tabla
               if t["valido"] and np.isfinite(t["r_mediana"])]
    mejor = max(validos, key=lambda t: t["r_mediana"])["metodo"] \
        if validos else None
    tabla.sort(key=lambda t: (t["valido"],
                              t["r_mediana"] if np.isfinite(t["r_mediana"])
                              else -9), reverse=True)
    return {"metodo": mejor, "tabla": tabla}


def _html_curvas_negativas(meta: dict) -> str:
    """Bloque del informe con las series cuya curva de ajuste cruzó cero.

    Es lo que hace reproducible el resultado: si N series se estandarizaron
    con otro método, el informe tiene que decir cuáles, cuántos años estaban
    afectados y con qué método se resolvieron. Sin esto el usuario no puede
    escribir la sección de métodos de su tesis.
    """
    neg = meta.get("curvas_negativas") or {}
    if not neg:
        return ""
    alterno = meta.get("metodo_alterno")
    alternas = set(meta.get("series_alternas") or [])
    filas = []
    for n, d in sorted(neg.items()):
        tr = ", ".join(f"{a}–{b}" for a, b in (d.get("tramos") or [])[:3])
        porserie = meta.get("metodos_por_serie") or {}
        met = porserie.get(n) or (alterno if (alterno and n in alternas)
                                  else meta.get("metodo_estandarizacion", ""))
        filas.append(
            f"<tr><td>{n}</td><td align='right'>{d['n_parches']}/{d['total']}</td>"
            f"<td>{tr}</td><td align='right'>{d['indice_max']:.2f}</td>"
            f"<td>{met}</td></tr>")
    porserie = meta.get("metodos_por_serie") or {}
    if alterno:
        resumen = (f"Se estandarizaron con <b>{alterno}</b> en vez del método "
                   f"general.")
    elif porserie:
        resumen = ("Cada una se estandarizó con el método indicado en la "
                   "última columna.")
    else:
        resumen = ("Se mantuvieron con el método general: en esos años la "
                   "tendencia se reemplazó por la media de la serie, así que "
                   "su índice no es comparable con el del resto.")
    return f"""<br>
        <b style='color:#d9534f;'>Curvas de ajuste que cruzan cero:
        {len(neg)} serie(s)</b><br>
        {resumen}<br>
        <table style='font-size:10px;' cellpadding='2'>
        <tr><th align='left'>Serie</th><th>Años afectados</th>
        <th align='left'>Tramos</th><th>Índice máx</th>
        <th align='left'>Método usado</th></tr>
        {''.join(filas)}
        </table>"""


def _construir_cronologia_desde_series(
    series: dict[str, pd.DataFrame],
    nombres: list[str],
    tipo_cronologia: str,
    metodo_estandarizacion: str,
    agregacion: str,
    ventana_mm: int | None = None,
    aplicar_log: bool = False,
    metodo_alterno: str | None = None,
    series_alternas: list | None = None,
    metodos_por_serie: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    if not nombres:
        raise ValueError("No hay series seleccionadas.")

    alternas = set(series_alternas or [])
    columnas = []
    for nombre in nombres:
        if nombre not in series:
            continue
        # Las series cuya curva cruzaba cero pueden llevar otro método, el
        # mismo para todas, elegido por el usuario o por correlación.
        # Prioridad: elección individual > método del grupo > método general.
        met = metodo_estandarizacion
        if metodo_alterno and nombre in alternas:
            met = metodo_alterno
        if metodos_por_serie and nombre in metodos_por_serie:
            met = metodos_por_serie[nombre]
        s_norm = _normalizar_serie_para_tipo(
            series[nombre]["Ancho_mm"], tipo_cronologia,
            met, ventana_mm=ventana_mm,
            aplicar_log=aplicar_log
        )
        s_norm.name = nombre
        columnas.append(s_norm)
    if not columnas:
        raise ValueError("No hay datos válidos para construir la cronología.")

    df = pd.concat(columnas, axis=1).sort_index()
    if df.empty:
        raise ValueError("La cronología quedó vacía.")

    agg = (agregacion or "biweight").lower()
    tipo = (tipo_cronologia or "raw").lower()

    if agg in {"biweight", "robusta", "robust"}:
        valores = df.apply(lambda row: _biweight_mean(row.dropna().values), axis=1)
    elif agg in {"median", "mediana"}:
        valores = df.median(axis=1, skipna=True)
    else:
        valores = df.mean(axis=1, skipna=True)

    ns = df.notna().sum(axis=1)
    sds = df.std(axis=1, skipna=True, ddof=1).fillna(0.0)

    col_name = {"raw": "Raw", "residual": "Residual"}.get(tipo, "Standard")
    cron = pd.DataFrame(
        {col_name: valores, "N": ns.astype(int), "SD": sds},
        index=pd.Index(df.index.astype(int), name="Anio"),
    )
    cron = cron.dropna(subset=[col_name]).sort_index()

    # ── Rbar y EPS de PERÍODO COMPLETO sobre SERIES DETRENDADAS ──────
    # Antes calcular_rbar usaba las series RAW (Ancho_mm), lo que daba
    # valores inflados porque las tendencias decadales hacen que las
    # series brutas covaríen fuertemente a largo plazo. ARSTAN computa
    # su "all possible series rbar" sobre las series DETRENDADAS, que
    # es lo correcto: queremos la señal común año-a-año, no las
    # tendencias compartidas. Acá usamos el `df` de series detrendadas
    # que ya construimos arriba.
    # Rbar global vectorizado. Antes se recorrían todos los pares en bucles
    # de Python con pandas (.dropna/.intersection/.loc por par): con 169
    # series son 14.196 pares y era el mayor costo al generar la cronología.
    # Ahora la matriz de correlaciones se calcula de una sola vez con
    # álgebra matricial, respetando NaN y el mínimo de 10 años en común.
    M = df.to_numpy(dtype=float)
    valido = ~np.isnan(M)
    Z = np.where(valido, M, 0.0)
    V = valido.astype(float)
    n_ab = V.T @ V
    s_a = Z.T @ V
    s_b = V.T @ Z
    s_ab = Z.T @ Z
    s_aa = (Z * Z).T @ V
    s_bb = V.T @ (Z * Z)
    with np.errstate(divide="ignore", invalid="ignore"):
        cov_m = s_ab - (s_a * s_b) / n_ab
        var_a = s_aa - (s_a * s_a) / n_ab
        var_b = s_bb - (s_b * s_b) / n_ab
        R_m = cov_m / np.sqrt(var_a * var_b)
    iu = np.triu_indices(M.shape[1], k=1)
    r_pares = R_m[iu]
    ok = (n_ab[iu] >= 10) & np.isfinite(r_pares)
    rs_pairs = r_pares[ok]
    rbar_completo = float(np.mean(rs_pairs)) if rs_pairs.size else float("nan")
    # Profundidad de muestreo promedio (mean number of series per year
    # with valid data) — igual que la columna "cores" de ARSTAN.
    sample_depth_mean = float(ns[ns > 0].mean()) if (ns > 0).any() else 0.0
    if np.isfinite(rbar_completo) and sample_depth_mean > 1:
        eps_completo = float(
            (sample_depth_mean * rbar_completo) /
            (1 + (sample_depth_mean - 1) * rbar_completo)
        )
    else:
        eps_completo = float("nan")

    meta = {
        "nombre": "",
        "tipo_cronologia": tipo,
        "metodo_estandarizacion": metodo_estandarizacion,
        "aplicar_log": bool(aplicar_log),
        "agregacion": agg,
        "series_usadas": list(nombres),
        "n_series": len(nombres),
        "n_anios": int(len(cron)),
        "creado_en": pd.Timestamp.utcnow().isoformat(),
        "columna_valor": col_name,
        # Rbar/EPS sobre series detrendadas (comparable con ARSTAN
        # "all possible series rbar")
        "Rbar": rbar_completo,
        "EPS": eps_completo,
        "sample_depth_mean": sample_depth_mean,
        # Profundidad AÑO POR AÑO, necesaria para la SSS (la media no sirve:
        # la SSS pregunta desde qué año la cronología es utilizable).
        "sample_depth": pd.Series(ns, index=df.index),
        "rbar_arboles": rbar_entre_arboles(series, nombres),
    }
    return cron, meta


def _ruta_metadatos_cronologia(ruta: str) -> str:
    base = os.path.basename(ruta)
    carpeta = os.path.dirname(ruta)
    return os.path.join(carpeta, f".{os.path.splitext(base)[0]}.json")


def _guardar_metadatos_cronologia(ruta: str, meta: dict):
    with open(_ruta_metadatos_cronologia(ruta), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def _cargar_metadatos_cronologia(ruta: str) -> dict | None:
    meta_path = _ruta_metadatos_cronologia(ruta)
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def escribir_tucson(serie: pd.Series, ruta: str, codigo: str = "CRONO",
                     factor: float = 1000.0, decimales_mm: bool = True):
    """Escribe una serie en formato Tucson (decadal, 10 valores por línea).

    `factor` convierte a enteros: 1000 para anchos en mm (0.452 → 452) y
    también para cronologías, cuyos índices adimensionales rondan 1.0 y se
    guardan como 1000 = índice 1.000. Esa es la convención de ARSTAN para
    los archivos .crn, así que un índice de 0.873 queda como 873.

    Cada línea lleva el código, el año de la década y hasta 10 valores; el
    archivo cierra con el marcador de fin de serie (-9999).
    """
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        raise ValueError("La serie está vacía.")
    s = s.sort_index()
    cod = str(codigo)[:TUCSON_MAX_CHARS_ID].ljust(TUCSON_MAX_CHARS_ID)

    anios = s.index.to_numpy(dtype=np.int64)
    vals = s.to_numpy(dtype=float)
    a_ini, a_fin = int(anios.min()), int(anios.max())
    por_anio = {int(a): float(v) for a, v in zip(anios, vals)}

    lineas = []
    decada = (a_ini // 10) * 10
    while decada <= a_fin:
        # En Tucson, la primera línea lleva el año REAL de inicio (no el de la
        # década) y solo los valores hasta el fin de esa década. Si se
        # etiquetara con la década, al releer el archivo los valores quedarían
        # corridos hacia atrás.
        etiqueta = max(decada, a_ini)
        fila = f"{cod}{etiqueta:4d}"
        hay = False
        for k in range(10):
            anio = decada + k
            if anio < a_ini or anio > a_fin:
                continue
            v = por_anio.get(anio)
            entero = (TUCSON_VALOR_FALTANTE if v is None
                      else int(round(v * factor)))
            fila += f"{entero:6d}"
            hay = True
        if hay:
            lineas.append(fila)
        decada += 10

    # Marcador de fin de serie
    ultima_decada = (a_fin // 10) * 10
    if a_fin % 10 == 9:
        lineas.append(f"{cod}{ultima_decada + 10:4d}{TUCSON_VALOR_FIN:6d}")
    else:
        lineas[-1] += f"{TUCSON_VALOR_FIN:6d}"

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def _exportar_cronologia_df(df: pd.DataFrame, ruta: str, codigo: str = "CRONO"):
    ext = os.path.splitext(ruta)[1].lower()
    df_out = df.copy()
    df_out.index.name = "Anio"
    if ext == ".rwl":
        # Tucson: se guarda la columna de valores de la cronología
        col = df_out.columns[0]
        for c in df_out.columns:
            if str(c).strip().lower() not in ("n", "sd", "se", "eps", "rbar"):
                col = c
                break
        escribir_tucson(pd.to_numeric(df_out[col], errors="coerce"),
                        ruta, codigo=codigo)
        return
    if _es_planilla(ext):
        _escribir_excel(df_out, ruta, index=True)
    elif ext == ".csv":
        df_out.to_csv(ruta, index=True)
    else:
        df_out.to_csv(ruta, index=True, sep="\t")


def _leer_cronologia_guardada(ruta: str) -> tuple[pd.DataFrame, dict]:
    ext = os.path.splitext(ruta)[1].lower()
    if _es_planilla(ext):
        df = _leer_planilla(ruta)
    elif ext == ".csv":
        df = pd.read_csv(ruta)
        if df.shape[1] < 2:
            df = pd.read_csv(ruta, sep=";", decimal=",")
    else:
        try:
            df = pd.read_csv(ruta, sep="\t")
            test_col = df.iloc[:, 1] if df.shape[1] > 1 else pd.Series()
            if pd.to_numeric(test_col, errors="coerce").isna().all() and len(test_col) > 0:
                df = pd.read_csv(ruta, sep="\t", decimal=",")
        except Exception:
            try:
                df = pd.read_csv(ruta, sep=None, engine="python", decimal=",")
            except Exception:
                df = pd.read_csv(ruta, sep=None, engine="python")

    if df.shape[1] < 2:
        raise ValueError("La cronología debe tener al menos dos columnas.")

    cols = list(df.columns)
    year_col = None
    for c in cols:
        if c.lower() in ("anio", "año", "year"):
            year_col = c
            break
    if year_col is None:
        year_col = cols[0]

    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df.dropna(subset=[year_col])
    df[year_col] = df[year_col].astype(int)
    df.set_index(year_col, inplace=True)
    df.index.name = "Anio"
    df.sort_index(inplace=True)

    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    value_cols = [c for c in df.columns if c.lower() not in ("n", "sd", "se")]

    meta = _cargar_metadatos_cronologia(ruta) or {}
    nombre = meta.get("nombre") or os.path.splitext(os.path.basename(ruta))[0]

    if not meta:
        cols_lower = {c.lower(): c for c in value_cols}
        columnas_disponibles = []
        for t in ["Raw", "Standard", "Residual"]:
            if t.lower() in cols_lower or t in df.columns:
                columnas_disponibles.append(t)

        if len(columnas_disponibles) > 1:
            tipo = "todas"
            col_valor = columnas_disponibles[0]
        elif len(columnas_disponibles) == 1:
            tipo = columnas_disponibles[0].lower()
            col_valor = columnas_disponibles[0]
        else:
            tipo = "raw"
            col_valor = value_cols[0] if value_cols else df.columns[0]

        meta = {
            "nombre": nombre, "tipo_cronologia": tipo,
            "metodo_estandarizacion": "desconocido", "agregacion": "desconocido",
            "series_usadas": [], "n_series": 0,
            "n_anios": int(len(df)),
            "columna_valor": col_valor,
            "columnas_disponibles": columnas_disponibles if len(columnas_disponibles) > 1 else [],
        }

    meta.setdefault("nombre", nombre)
    meta.setdefault("n_anios", int(len(df)))

    col_val = meta.get("columna_valor", "")
    if col_val not in df.columns:
        for c in df.columns:
            if c.lower() == col_val.lower():
                meta["columna_valor"] = c
                break
        else:
            meta["columna_valor"] = value_cols[0] if value_cols else df.columns[0]

    return df, meta


def _serie_transformada_para_comparar(df: pd.DataFrame, meta: dict) -> pd.Series:
    tipo = (meta.get("tipo_cronologia") or "raw").lower()
    metodo = meta.get("metodo_estandarizacion", "spline")
    return _normalizar_serie_para_tipo(df["Ancho_mm"], tipo, metodo)


def _correlacion_por_desfase(serie_a: pd.Series, serie_b: pd.Series,
                              max_shift: int, min_overlap: int = MIN_OVERLAP_DEFAULT
                              ) -> tuple[list[int], list[float]]:
    shifts, rs = [], []
    for shift in range(-max_shift, max_shift + 1):
        shifted = serie_a.copy()
        shifted.index = shifted.index + shift
        overlap = shifted.index.intersection(serie_b.index)
        if len(overlap) < min_overlap:
            continue
        a = shifted.loc[overlap].to_numpy(dtype=float)
        b = serie_b.loc[overlap].to_numpy(dtype=float)
        if len(a) < 2 or len(b) < 2 or np.std(a) == 0 or np.std(b) == 0:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if np.isfinite(r):
            shifts.append(shift)
            rs.append(r)
    return shifts, rs


def _glk_np(a: np.ndarray, b: np.ndarray, min_overlap: int) -> float:
    """GLK sobre arreglos numpy ya alineados (réplica de gleichlaufigkeit)."""
    if len(a) < min_overlap:
        return float("nan")
    da = np.sign(np.diff(a))
    db = np.sign(np.diff(b))
    n = len(da)
    if n == 0:
        return float("nan")
    # Fórmula de dplR (glk.R): GLK = 1 − Σ|signo_a − signo_b| / (2n).
    # Desglosada, eso da crédito COMPLETO cuando los dos signos coinciden,
    # incluido el caso en que AMBAS series están planas: si las dos repiten
    # valor entre dos años, eso es coincidencia, no medio acierto.
    # DPI le daba 0,5 a ese caso. Con mediciones a 0,01 mm los valores
    # repetidos no son raros, así que la diferencia aparece de verdad.
    #   ambos signos iguales (incl. ambos cero) -> 1
    #   uno plano y el otro no                  -> 0,5
    #   signos opuestos                         -> 0
    return float(1.0 - np.sum(np.abs(da - db)) / (2.0 * n))


def _tbp_np(a: np.ndarray, b: np.ndarray, min_overlap: int) -> float:
    """t-BP sobre arreglos numpy ya alineados (réplica de t_baillie_pilcher:
    filtro de Hollstein 100·log-diff → Pearson → t)."""
    m = (a > 0) & (b > 0)
    if int(m.sum()) < 2:
        return float("nan")
    la = np.log(a[m])
    lb = np.log(b[m])
    ha = 100.0 * np.diff(la)
    hb = 100.0 * np.diff(lb)
    n = len(ha)
    if n < min_overlap:
        return float("nan")
    if np.std(ha) == 0 or np.std(hb) == 0:
        return float("nan")
    r = float(np.corrcoef(ha, hb)[0, 1])
    if not np.isfinite(r) or abs(r) >= 1.0:
        return float("nan")
    return float(r * np.sqrt(n - 2) / np.sqrt(1.0 - r * r))


def _estadisticos_por_desfase(
    serie_a: pd.Series, serie_b: pd.Series,
    max_shift: int, min_overlap: int = MIN_OVERLAP_DEFAULT,
    serie_a_raw: pd.Series | None = None,
    serie_b_raw: pd.Series | None = None,
) -> tuple[list[int], list[float], list[float], list[float], list[int]]:
    """Calcula r, GLK y t-BP en cada desplazamiento (shift).

    IMPORTANTE — consistencia de transformaciones:
      - `serie_a`/`serie_b` deben venir en la transformación de ALTA
        FRECUENCIA usada para correlacionar (típicamente diferencias
        logarítmicas). El r de Pearson se calcula sobre estas.
      - `serie_a_raw`/`serie_b_raw` (opcionales) son las series CRUDAS.
        Si se pasan, GLK y t-BP se calculan sobre ellas, porque esas
        funciones diferencian internamente y esperan datos crudos (GLK
        estándar de Eckstein & Bauch). Esto reproduce exactamente lo que
        hace 'Analizar Serie Flotante': r sobre diferencias-log y GLK/t-BP
        sobre crudo. Sin estos parámetros (modo retrocompatible), los tres
        se calculan sobre serie_a/serie_b.

    Antes la comparación múltiple pasaba anchos CRUDOS como serie_a/serie_b,
    lo que daba correlaciones espurias altas por las tendencias de edad
    compartidas entre árboles — inconsistente con el cofechado real. Por eso
    el mismo alineamiento mostraba r=+0.44 en una tabla y r=-0.30 en otra.

    Devuelve listas paralelas: (shifts, rs, glks, t_bps, ns).
    """
    usar_raw = serie_a_raw is not None and serie_b_raw is not None

    # Vectorización: se pasa todo a arreglos numpy ordenados por año una sola
    # vez, y cada desfase se alinea con np.intersect1d (rápido). Antes se
    # copiaban Series de pandas y se recalculaba el filtro de Hollstein por
    # cada desfase (decenas de miles de construcciones de Series) — eso hacía
    # que comparar muchas series tardara más de un minuto.
    a_s = pd.to_numeric(serie_a, errors="coerce").dropna().sort_index()
    b_s = pd.to_numeric(serie_b, errors="coerce").dropna().sort_index()
    ya = a_s.index.to_numpy(np.int64)
    va = a_s.to_numpy(dtype=float)
    yb = b_s.index.to_numpy(np.int64)
    vb = b_s.to_numpy(dtype=float)
    if usar_raw:
        ar_s = pd.to_numeric(serie_a_raw, errors="coerce").dropna().sort_index()
        br_s = pd.to_numeric(serie_b_raw, errors="coerce").dropna().sort_index()
        yar = ar_s.index.to_numpy(np.int64)
        var_ = ar_s.to_numpy(dtype=float)
        ybr = br_s.index.to_numpy(np.int64)
        vbr = br_s.to_numpy(dtype=float)

    min_glk = min(10, min_overlap)
    min_tbp = min(20, min_overlap)
    shifts, rs, glks, tbps, ns = [], [], [], [], []
    for shift in range(-max_shift, max_shift + 1):
        common, ia, ib = np.intersect1d(
            ya + shift, yb, assume_unique=True, return_indices=True)
        n = len(common)
        if n < min_overlap:
            continue
        a_arr = va[ia]
        b_arr = vb[ib]
        if a_arr.size < 2:
            continue
        if np.std(a_arr) == 0 or np.std(b_arr) == 0:
            continue
        r = float(np.corrcoef(a_arr, b_arr)[0, 1])
        if not np.isfinite(r):
            continue

        # GLK y t-BP sobre las series CRUDAS (alineadas) si se proporcionaron;
        # si el solape crudo es corto, sobre las mismas series de r.
        if usar_raw:
            cr, iga, igb = np.intersect1d(
                yar + shift, ybr, assume_unique=True, return_indices=True)
            if len(cr) >= min_glk:
                ag = var_[iga]
                bg = vbr[igb]
                n = len(cr)
            else:
                ag = a_arr
                bg = b_arr
        else:
            ag = a_arr
            bg = b_arr

        glk = _glk_np(ag, bg, min_glk)
        t_bp = _tbp_np(ag, bg, min_tbp)

        shifts.append(shift)
        rs.append(r)
        glks.append(glk if np.isfinite(glk) else float("nan"))
        tbps.append(t_bp if np.isfinite(t_bp) else float("nan"))
        ns.append(n)

    return shifts, rs, glks, tbps, ns


def alineamiento_optimo_anillos(serie_a, serie_b, shift_base,
                                 max_correcciones=10, penalizacion=3.0):
    """Alineamiento óptimo serie↔cronología por programación dinámica.

    A diferencia del cofechado por ventanas fijas (COFECHA), este método
    descompone la serie completa buscando el alineamiento globalmente
    óptimo que permite insertar anillos faltantes y eliminar anillos
    sobrantes en CUALQUIER posición, con una penalización por cada
    corrección.

    Modelo:
      - Se recorre la serie año a año (sobre primeras diferencias, que es
        la señal de cofechado).
      - En cada año la serie tiene un "desfase acumulado" respecto a la
        cronología.
      - De un año al siguiente, el desfase puede mantenerse (año normal),
        +1 (anillo faltante → hay que insertar uno) o −1 (anillo sobrante
        → hay que eliminar uno).
      - Cada cambio de desfase cuesta `penalizacion`.
      - Se maximiza la concordancia total (acuerdo de signo de las
        primeras diferencias, equivalente a GLK punto a punto) menos las
        penalizaciones.

    Implementación: programación dinámica O(n·S·3) donde S = 2·max_corr+1.
    Garantiza el óptimo global (no es heurístico como las ventanas).

    Parámetros:
      shift_base: desfase global de partida (centro de la banda de búsqueda)
      max_correcciones: máximo de anillos a corregir acumulados (banda ±)
      penalizacion: costo por corrección. Bajo = exploratorio (propone más
                    correcciones); alto = conservador (solo las muy claras).

    Devuelve dict con:
      "segmentos": lista de tramos de desfase constante, cada uno con
                   rango de años de la serie, rango calendario, corrección
                   neta vs base, n años, r y GLK del tramo.
      "correcciones": lista de puntos donde cambia el desfase (año
                      calendario aproximado y tipo: faltante/sobrante).
      "shift_base": el desfase base usado.
    Devuelve None si no hay datos suficientes.
    """
    a = pd.to_numeric(serie_a, errors="coerce").dropna().sort_index()
    b = pd.to_numeric(serie_b, errors="coerce").dropna().sort_index()
    if len(a) < 10 or len(b) < 10:
        return None

    da = a.diff().dropna()
    db = b.diff().dropna()
    sa = np.sign(da.to_numpy())
    years_a = da.index.to_numpy().astype(int)
    sb_by_year = {int(y): np.sign(v)
                  for y, v in zip(db.index.to_numpy(), db.to_numpy())}
    da_by_year = {int(y): float(v)
                  for y, v in zip(da.index.to_numpy(), da.to_numpy())}
    db_by_year = {int(y): float(v)
                  for y, v in zip(db.index.to_numpy(), db.to_numpy())}

    n = len(years_a)
    shifts = list(range(int(shift_base) - int(max_correcciones),
                        int(shift_base) + int(max_correcciones) + 1))
    S = len(shifts)
    NEG = -1e9
    dp = np.full((n, S), NEG)
    back = np.full((n, S), -1, dtype=int)

    def score(t, s):
        ya = years_a[t]
        cb = sb_by_year.get(ya + s)
        if cb is None or sa[t] == 0 or cb == 0:
            return 0.0
        return 1.0 if sa[t] == cb else -1.0

    # Inicialización: el primer año puede empezar en cualquier desfase de
    # la banda sin costo (la posición del extremo de médula es la hipótesis
    # de datación; las correcciones internas son las que cuestan).
    for si, s in enumerate(shifts):
        dp[0][si] = score(0, s)

    for t in range(1, n):
        prev = dp[t - 1]
        for si in range(S):
            sc = score(t, shifts[si])
            best = prev[si]       # mismo desfase (año normal)
            bptr = si
            if si - 1 >= 0 and prev[si - 1] - penalizacion > best:
                best = prev[si - 1] - penalizacion  # anillo faltante
                bptr = si - 1
            if si + 1 < S and prev[si + 1] - penalizacion > best:
                best = prev[si + 1] - penalizacion  # anillo sobrante
                bptr = si + 1
            dp[t][si] = best + sc
            back[t][si] = bptr

    end_si = int(np.argmax(dp[n - 1]))
    path = [0] * n
    si = end_si
    for t in range(n - 1, 0, -1):
        path[t] = si
        si = back[t][si]
        if si < 0:
            si = path[t]
    path[0] = si
    shift_path = [shifts[i] for i in path]

    # Construir segmentos de desfase constante
    segmentos = []
    correcciones = []
    i0 = 0
    for t in range(1, n + 1):
        if t == n or shift_path[t] != shift_path[i0]:
            s = shift_path[i0]
            ys = years_a[i0:t]
            avals, bvals, agree, tot = [], [], 0, 0
            for y in ys:
                if y in da_by_year and (y + s) in db_by_year:
                    avals.append(da_by_year[y])
                    bvals.append(db_by_year[y + s])
                    if (np.sign(da_by_year[y]) == np.sign(db_by_year[y + s])
                            and da_by_year[y] != 0):
                        agree += 1
                    tot += 1
            if len(avals) > 2 and np.std(avals) > 0 and np.std(bvals) > 0:
                r = float(np.corrcoef(avals, bvals)[0, 1])
            else:
                r = float("nan")
            glk = agree / tot if tot else float("nan")
            segmentos.append({
                "serie_ini": int(ys[0]), "serie_fin": int(ys[-1]),
                "cal_ini": int(ys[0] + s), "cal_fin": int(ys[-1] + s),
                "shift": int(s), "correccion": int(s - shift_base),
                "n": int(len(ys)), "r": r, "glk": glk,
            })
            # Registrar el punto de corrección (transición entre segmentos)
            if t < n:
                s_next = shift_path[t]
                year_corr = int(years_a[t] + s_next)
                if s_next > s:
                    # El desfase aumenta → faltaba un anillo (insertar)
                    correcciones.append({
                        "anio_calendario": year_corr,
                        "tipo": "faltante", "delta": s_next - s,
                    })
                else:
                    correcciones.append({
                        "anio_calendario": year_corr,
                        "tipo": "sobrante", "delta": s - s_next,
                    })
            i0 = t

    return {
        "segmentos": segmentos,
        "correcciones": correcciones,
        "shift_base": int(shift_base),
    }


# =============================================================================
# MOTOR DE BÚSQUEDA EXHAUSTIVA DE CORRECCIONES
# =============================================================================

def _diff_log(serie: pd.Series) -> pd.Series:
    """Diferencias de logaritmos — transforma anchos en tasas de crecimiento."""
    return np.log(serie.replace(0, np.nan).dropna()).diff().dropna()


def _r_pearson(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    r = np.corrcoef(a, b)[0, 1]
    return float(r) if not np.isnan(r) else np.nan


def _r_movil(m: pd.Series, t: pd.Series, overlap: list, mitad: int) -> tuple[list, list]:
    """Correlación de Pearson en ventana deslizante centrada."""
    years, r_vals = [], []
    for anio in overlap:
        ventana = [y for y in overlap if 0 < abs(y - anio) <= mitad]
        if len(ventana) < OVERLAP_MINIMO_GRAFICO:
            continue
        r = _r_pearson(m.loc[ventana].values, t.loc[ventana].values)
        if not np.isnan(r):
            years.append(float(anio))
            r_vals.append(r)
    return years, r_vals


def _stats_movil(m, t, overlap, mitad, m_raw=None, t_raw=None):
    """Versión extendida de _r_movil que calcula r, GLK y t-BP por ventana."""
    if m_raw is None:
        m_raw = m
    if t_raw is None:
        t_raw = t

    years, r_vals, glk_vals, tbp_vals, n_vals = [], [], [], [], []

    for anio in overlap:
        ventana = [y for y in overlap if 0 < abs(y - anio) <= mitad]
        n_v = len(ventana)
        if n_v < OVERLAP_MINIMO_GRAFICO:
            continue

        r = _r_pearson(m.loc[ventana].values, t.loc[ventana].values)
        if np.isnan(r):
            continue

        m_raw_w = m_raw.loc[m_raw.index.intersection(ventana)]
        t_raw_w = t_raw.loc[t_raw.index.intersection(ventana)]
        glk, _ = gleichlaufigkeit(m_raw_w, t_raw_w, min_overlap=5)
        t_bp, _, _ = t_baillie_pilcher(m_raw_w, t_raw_w, min_overlap=5)

        years.append(float(anio))
        r_vals.append(r)
        glk_vals.append(glk)
        tbp_vals.append(t_bp)
        n_vals.append(n_v)

    return years, r_vals, glk_vals, tbp_vals, n_vals


def aplicar_correccion(df: pd.DataFrame, anio: int, delta: int,
                        anclaje: str = "corteza") -> pd.DataFrame:
    """Inserta o elimina delta anillos en una posición.

    El ANCLAJE decide qué extremo de la serie se queda quieto:

    • "corteza" (por defecto): el ÚLTIMO año no se mueve y se desplazan los
      años ANTERIORES. Es lo correcto para árboles vivos fechados desde la
      corteza (se sabe con certeza el año del anillo externo). Si falta un
      anillo en 2023, al insertarlo la serie sigue terminando en 2024 y todo
      lo anterior a 2023 retrocede un año — que es justo lo que pasó en la
      madera.
        - delta > 0 (anillo faltante): los años ≤ anio se mueven −1 y se
          inserta un anillo en `anio`.
        - delta < 0 (anillo extra): se elimina `anio` y los años < anio
          se mueven +1.

    • "medula": el PRIMER año no se mueve y se desplazan los años
      posteriores. Útil para series flotantes o fechadas desde la médula.

    Antes solo existía el anclaje en médula, así que insertar un anillo
    empujaba la serie hacia el presente (una serie que terminaba en 2024
    pasaba a terminar en 2025) y obligaba a corregir el año base a mano.
    Además hacía que el buscador de correcciones propusiera años equivocados:
    para arreglar un desfase global proponía una corrección al INICIO de la
    serie en vez del anillo que realmente falta cerca de la corteza.

    Implementado con numpy (no pandas append/.loc) porque se llama cientos
    de veces por cada búsqueda de correcciones.
    """
    years = df.index.to_numpy(dtype=np.int64).copy()
    vals = pd.to_numeric(df["Ancho_mm"], errors="coerce").to_numpy(dtype=float).copy()
    placeholder = float(np.nanmean(vals)) if vals.size else 0.0
    a = int(anio)
    anclar_corteza = str(anclaje).lower().startswith("cort")

    for _ in range(abs(delta)):
        if delta > 0:
            if anclar_corteza:
                # Los años ≤ a retroceden; queda libre el año `a`
                years = np.where(years <= a, years - 1, years)
            else:
                years = np.where(years >= a, years + 1, years)
            years = np.append(years, a)
            vals = np.append(vals, placeholder)
        else:
            m = years != a
            years = years[m]
            vals = vals[m]
            if anclar_corteza:
                years = np.where(years < a, years + 1, years)
            else:
                years = np.where(years > a, years - 1, years)
    orden = np.argsort(years, kind="stable")
    return pd.DataFrame({"Ancho_mm": vals[orden]},
                        index=pd.Index(years[orden], name="Anio"))


def _plausibilidad_anillo_estrecho(ref_years: np.ndarray, ref_vals: np.ndarray,
                                    anio: int, delta: int,
                                    peso: float = 0.6) -> float:
    """Cuán creíble es que falte (o sobre) un anillo en `anio`.

    Los anillos que se omiten al fechar una muestra son los ESTRECHOS: en un
    año malo el anillo puede ser casi invisible o localmente ausente. Los
    anillos anchos prácticamente nunca se pasan por alto.

    Se mide cuán bajo está ese año en la REFERENCIA (la cronología, ya
    estandarizada, media ~1) usando su posición en desviaciones típicas, y se
    devuelve un factor:
        > 1  año estrecho  → candidato más creíble
        < 1  año ancho     → candidato menos creíble
    `peso` gradúa cuánto influye (0 = solo estadística, como antes).

    Para anillos SOBRANTES (delta<0) el razonamiento se invierte solo en
    parte: un falso anillo suele aparecer dentro de un año ancho (banda de
    madera tardía intermedia), así que ahí se premia lo ancho.
    """
    if ref_vals.size < 5:
        return 1.0
    idx = np.searchsorted(ref_years, int(anio))
    if idx < 0 or idx >= ref_years.size or int(ref_years[idx]) != int(anio):
        return 1.0  # el año no está en la referencia: sin información
    media = float(np.nanmean(ref_vals))
    sd = float(np.nanstd(ref_vals))
    if not np.isfinite(sd) or sd <= 0:
        return 1.0
    z = (float(ref_vals[idx]) - media) / sd
    # z<0 = año estrecho. Para anillo faltante premiamos z negativo.
    señal = -z if delta > 0 else z
    señal = float(np.clip(señal, -2.5, 2.5))
    return float(max(0.15, 1.0 + peso * señal / 2.5))


def puntaje_consistencia(serie_std: pd.Series, crono_std: pd.Series,
                          **kwargs) -> dict:
    """Mide si una serie YA CORREGIDA quedó limpia, no cuánto correlaciona.

    El problema que resuelve: cuando el buscador propone corregir en 1850 o en
    1858, las dos candidatas dan correlaciones globales casi iguales —
    diferencias de milésimas— porque ambas arreglan casi toda la serie. La r
    global no distingue entre ellas, y así terminan aceptándose años que están
    a cinco o diez años del verdadero.

    La pregunta cambia: en vez de «¿cuál sube más la r?», «¿cuál deja la serie
    limpia?». Se aplica cada candidata y se vuelve a correr el diagnóstico de
    tramos. Si el año es el correcto, la serie queda con un solo tramo a
    desfase 0 de punta a punta. Si el año está equivocado por ocho años, queda
    un tramo residual de ocho años desajustado, que el diagnóstico ve como un
    segundo tramo.

    La ventaja es que el criterio pasa de continuo y casi empatado a
    esencialmente binario —quedó limpia o no—, y además el tramo residual
    crece con el error, así que la señal es proporcional a la distancia.

    Devuelve:
      limpia   1 si el diagnóstico dice bien_fechada, 0 si no
      residuo  años cubiertos por tramos con desfase distinto de cero
      n_tramos cuántos tramos sólidos quedaron
      diag     el diagnóstico textual, para mostrarlo en la interfaz
    """
    try:
        d = diagnosticar_datacion(serie_std, crono_std, **kwargs)
    except Exception:
        return {"limpia": 0, "residuo": 10 ** 6, "n_tramos": 99,
                "diag": "error", "r_medio": float("nan")}

    tramos = d.get("tramos") or []
    residuo = sum(max(t["fin"] - t["inicio"], 1)
                  for t in tramos if t.get("shift", 0) != 0)
    rs = [t.get("r_medio") for t in tramos if t.get("shift", 0) == 0]
    return {
        "limpia": 1 if d.get("diagnostico") == "bien_fechada" else 0,
        "residuo": int(residuo),
        "n_tramos": len(tramos),
        "diag": d.get("diagnostico") or "",
        "r_medio": float(np.nanmean(rs)) if rs else float("nan"),
    }


def _texto_correccion(delta: int) -> str:
    """Describe la corrección con la acción, no solo con el signo.

    COFECHA escribe "+1" o "-1" y deja que el usuario deduzca si hay que
    agregar o quitar. En la práctica esa deducción se equivoca seguido, así
    que acá se nombra la acción.

    Convención, verificada con series a las que se les quitó o duplicó un
    anillo en un año conocido: delta positivo = faltan anillos, hay que
    insertar; delta negativo = sobran, hay que eliminar. Es la misma que
    COFECHA, donde un desplazamiento de +1 señala un anillo ausente.
    """
    n = abs(int(delta))
    if delta > 0:
        return f"Insertar {n}" + (" anillo" if n == 1 else " anillos")
    if delta < 0:
        return f"Eliminar {n}" + (" anillo" if n == 1 else " anillos")
    return "Sin cambio"


def _buscar_y_priorizar(ref, problema, mitad_ventana, max_corr,
                         diagnostico=None, coleccion_std=None,
                         nombre_serie=None, **kwargs):
    """Busca correcciones y las reordena según el diagnóstico previo.

    La búsqueda por correlación sola puede encabezar con una corrección del
    signo equivocado (por ejemplo, quitar un anillo cuando lo que falta es
    agregarlo): a corta distancia ambas cosas mejoran la r de forma parecida.
    El diagnóstico sí sabe qué pasa —qué tramo está bien fechado y hacia dónde
    está corrido el otro—, así que se usa para priorizar las correcciones
    COHERENTES con él: el signo correcto y cerca del año localizado.
    """
    sugerencias, es_marginal = buscar_correcciones(
        ref, problema, mitad_ventana, max_corr, **kwargs)
    if not sugerencias:
        return sugerencias, es_marginal

    # VERIFICACIÓN REAL de las mejores candidatas: en vez de confiar en la
    # métrica interna de la búsqueda (que trabaja sobre arreglos ya
    # transformados y con un relleno aproximado para el anillo nuevo), se
    # aplica cada candidata a la serie CRUDA, se vuelve a estandarizar y se
    # mide la correlación resultante. Sin esto la lista podía encabezar con
    # una corrección del signo equivocado: en una serie a la que le faltaba
    # un anillo, quitar otro daba r=0.256 mientras que insertarlo daba 0.349,
    # y aun así aparecía primero el "quitar".
    tr_ref = kwargs.get("transformar_ref")
    tr_prob = kwargs.get("transformar_prob")
    anclaje = kwargs.get("anclaje", "corteza")
    _eval_r = None
    ref_years_g = ref_vals_g = None
    _r_base_g = float("nan")
    _hay_quiebre_confiable = False
    _informe_zona = None
    if tr_ref is not None and tr_prob is not None:
        try:
            d_ref = tr_ref(ref["Ancho_mm"]).dropna()
            ref_years_g = d_ref.index.to_numpy(np.int64)
            ref_vals_g = d_ref.to_numpy(dtype=float)

            def _eval_r(df2):
                """Correlación real de una serie ya corregida contra la referencia."""
                d2 = tr_prob(df2["Ancho_mm"]).dropna()
                com = d_ref.index.intersection(d2.index)
                if len(com) < 10:
                    return -np.inf
                a = d_ref.loc[com].to_numpy(dtype=float)
                b = d2.loc[com].to_numpy(dtype=float)
                if np.std(a) == 0 or np.std(b) == 0:
                    return -np.inf
                r = float(np.corrcoef(a, b)[0, 1])
                return r if np.isfinite(r) else -np.inf

            def _r_real(sug):
                df2 = aplicar_correccion(problema, int(sug["anio"]),
                                         int(sug["delta"]), anclaje=anclaje)
                return _eval_r(df2)

            # Correlación SIN corregir: cualquier candidata que no la supere
            # se descarta. Una sugerencia que baja la correlación no es una
            # corrección, y ofrecerla solo confunde.
            r_base = _eval_r(problema)
            _r_base_g = r_base

            for sug in sugerencias[:12]:
                sug["r_verificada"] = _r_real(sug)
            verificadas = [s for s in sugerencias[:12]
                           if np.isfinite(s.get("r_verificada", -np.inf))
                           and (not np.isfinite(r_base)
                                or s["r_verificada"] > r_base)]
            resto = [s for s in sugerencias[12:]
                     if s.get("delta_r", 0) > 0]

            # CONSISTENCIA: se calcula para las candidatas de cabeza y se
            # guarda para mostrarla, pero NO se usa para ordenar.
            #
            # La idea era prometedora: en vez de preguntar cuál sube más la
            # correlación —criterio que empata cuando dos candidatas separadas
            # por ocho años difieren en milésimas— preguntar cuál deja la
            # serie sin tramos desajustados. Se probó de verdad, aplicando
            # cada candidata y volviendo a diagnosticar, contra el año real
            # conocido en 120 series simuladas.
            #
            # No funciona. El diagnóstico de tramos solo ve residuos de ocho
            # años o más; a cuatro años no distingue nada, y justo ahí es
            # donde la correlación tampoco decide. Peor: de vez en cuando
            # marca como sucia la candidata CORRECTA por ruido, y eso la
            # manda abajo en la lista. Medido:
            #
            #   señal fuerte (r~0.73)   exacto   error medio
            #     solo correlación        62%       0.97 años
            #     por consistencia        58%       1.33 años
            #   señal débil (r~0.35)
            #     solo correlación        32%       3.17 años
            #     por consistencia        22%       3.67 años
            #
            # Filtrar por residuo grande manteniendo el orden por r tampoco
            # aporta (62% / 1.00 años). Así que el orden sigue siendo por
            # correlación verificada, y la consistencia se muestra como
            # información de apoyo para que el usuario la juzgue.
            for sug in verificadas[:5]:
                try:
                    df2 = aplicar_correccion(problema, int(sug["anio"]),
                                             int(sug["delta"]), anclaje=anclaje)
                    sug["consistencia"] = puntaje_consistencia(
                        tr_prob(df2["Ancho_mm"]).dropna(), d_ref,
                        ventana=12, paso=2, min_overlap=6)
                except Exception:
                    pass

            def _clave(s):
                return (s.get("r_verificada", -np.inf)
                        * s.get("plausibilidad", 1.0))

            verificadas.sort(key=_clave, reverse=True)
            sugerencias = verificadas + resto

            # ── LOCALIZACIÓN POR PARTICIÓN ÓPTIMA ────────────────────
            # Reproduce el procedimiento manual: fijar el tramo que ya calza
            # con la cronología y mover solo el que falla, hasta encontrar el
            # año exacto donde se rompe la correlación.
            #
            # No es un refinamiento del buscador por correlación: es una
            # pregunta distinta. El buscador prueba correcciones y se queda
            # con la que más sube la r global, criterio que se aplana cuando
            # dos candidatas separadas por varios años difieren en milésimas.
            # Acá el AÑO DEL QUIEBRE es el parámetro que se estima, con cada
            # tramo usando todos sus datos.
            #
            # Medido en 120 series simuladas con el año conocido y el anillo
            # ausente en un año estrecho (que es donde ocurren de verdad):
            #
            #                        exacto    ±1     ±2
            #   buscador por r        20%     53%    73%
            #   partición óptima      80%     92%    97%
            #   partición, confiables 94%    100%   100%
            #
            # y el número de anillos faltantes sale correcto en el 100%.
            # Por eso estas candidatas van a la cabeza de la lista.
            # Se pide el INFORME completo, no un año único. Exigir un año
            # solo dejaba fuera cuatro de cada cinco series con error real,
            # porque el año exacto solo es afirmable en un tercio a la mitad
            # de los casos. En cambio la zona contiene el año verdadero en
            # 97-100% de las series reales probadas, y los cinco años mejor
            # ordenados de esa zona lo contienen en 67-100%.
            informe = None
            try:
                s_std = tr_prob(problema["Ancho_mm"]).dropna()
                # n_nulo=0: el nulo por rotación está mal especificado para
                # este uso (rechaza series que sí cofechan), así que no se
                # corre. El informe lo advierte en su propio texto.
                # Nulo de colección: el umbral sale de las OTRAS series
                # cargadas, que están fechadas. Es el único de los tres nulos
                # probados que controla los falsos positivos sin perder
                # detección.
                informe = _qb.informe_quiebre(
                    s_std, d_ref, max_desfase=10, n_nulo=0,
                    coleccion=coleccion_std,
                    excluir=nombre_serie)
                quiebres = _qb.mapa_de_quiebres(
                    s_std, d_ref, max_desfase=10, 
                    max_quiebres=3)
            except Exception:
                quiebres = []

            por_quiebre = []
            vistos = set()
            # ── UNA SOLA FUENTE DE VERDAD ──────────────────────────
            # El recuadro «Error localizado» venía de `_diagnosticar_datacion`,
            # un análisis por ventanas anterior e independiente, cuyo
            # `delta_sugerido` además era SIEMPRE ±1 sin importar cuántos
            # anillos. El resultado eran tres cifras distintas en la misma
            # pantalla para el mismo problema: la tabla decía +1, el recuadro
            # -2 y el informe -4.
            #
            # Ahora, cuando hay informe, el recuadro se reescribe con SUS
            # números. El diagnóstico por ventanas sigue sirviendo para decidir
            # el anclaje y para ordenar, que es donde aporta.
            if informe and informe.get("delta") and isinstance(diagnostico, dict):
                _d = int(informe["delta"])
                _n = abs(_d)
                _acc = ("INSERTAR" if _d > 0 else "ELIMINAR")
                _rg = informe.get("rango_error") or informe.get("zona")
                _cands = [str(int(a)) for a, _ in
                          (informe.get("candidatos") or [])[:5]]
                _tr = informe.get("tramos") or []
                _txt = ""
                if len(_tr) >= 2:
                    _b, _m = _tr[-1], _tr[0]
                    _txt = (f"El tramo {_b['inicio']}–{_b['fin']} calza bien "
                            f"(r≈{_b['r']:.2f}) y el tramo "
                            f"{_m['inicio']}–{_m['fin']} calza mejor desplazado "
                            f"{_m['desfase']:+d}.<br>")
                _txt += (f"<b>Hay que {_acc} {_n} anillo"
                         + ("s" if _n != 1 else "") + "</b>")
                if _rg:
                    _txt += f" <b>entre {_rg[0]} y {_rg[1]}</b>"
                if _cands:
                    _txt += ("<br><b>Años más probables</b> (estrechos en la "
                             "cronología, revísalos primero): "
                             + ", ".join(_cands))
                _txt += (". Se ancla en "
                         + ("corteza" if diagnostico.get("anclaje_sugerido",
                                                         "corteza") == "corteza"
                            else "médula")
                         + " para no mover el tramo ya fechado.")
                diagnostico["mensaje"] = _txt
                diagnostico["delta_sugerido"] = _d
                diagnostico["rango"] = _rg

            # Cada año candidato de la zona entra como una fila propia, con
            # la corrección ya aplicada, para que el usuario pueda probarlos
            # sin adivinar. Van ordenados por lo estrecho que es ese año en
            # la cronología, que es donde de verdad aparecen los ausentes.
            if informe and informe.get("candidatos") and informe.get("delta"):
                for a_cand, estrechez in informe["candidatos"]:
                    clave = (int(a_cand), int(informe["delta"]))
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    try:
                        df2 = aplicar_correccion(problema, int(a_cand),
                                                 int(informe["delta"]),
                                                 anclaje=anclaje)
                    except Exception:
                        continue
                    r_v = _eval_r(df2)
                    if not np.isfinite(r_v):
                        continue
                    por_quiebre.append({
                        "anio": int(a_cand), "delta": int(informe["delta"]),
                        "tipo": _texto_correccion(int(informe["delta"])),
                        "r_antes": float(_r_base_g), "r_tras": float(r_v),
                        "delta_r": (float(r_v - _r_base_g)
                                    if np.isfinite(_r_base_g)
                                    else float("nan")),
                        "r_zona_antes": float("nan"),
                        "r_zona_tras": float("nan"),
                        "df_corregido": df2, "r_verificada": float(r_v),
                        "plausibilidad": 1.0 + max(estrechez, 0.0),
                        "origen": "zona",
                        "confiable": False,
                        "estrechez": float(estrechez),
                        "zona": informe.get("zona"),
                        "texto": informe.get("texto"),
                        "tramos": informe.get("tramos"),
                        "perfil": informe.get("perfil"),
                    })

            # lo que venía del buscador por correlación (sin duplicar años).
            # Orden: primero lo confiable; después los años de la ZONA, que
            # heredan el delta del informe (correcto en 70-100% de los casos
            # reales); al final las candidatas crudas de la cascada, que
            # pueden proponer deltas grandes y poco creíbles.
            for q in quiebres:
                if q.get("anio") is None or not q.get("delta"):
                    continue
                clave = (int(q["anio"]), int(q["delta"]))
                if clave in vistos:
                    continue
                vistos.add(clave)
                try:
                    df2 = aplicar_correccion(problema, int(q["anio"]),
                                             int(q["delta"]), anclaje=anclaje)
                except Exception:
                    continue
                r_v = _eval_r(df2)
                if not np.isfinite(r_v):
                    continue
                por_quiebre.append({
                    "anio": int(q["anio"]), "delta": int(q["delta"]),
                    "tipo": _texto_correccion(int(q["delta"])),
                    "r_antes": float(_r_base_g),
                    "r_tras": float(r_v),
                    "delta_r": (float(r_v - _r_base_g)
                                if np.isfinite(_r_base_g) else float("nan")),
                    "r_zona_antes": float("nan"),
                    "r_zona_tras": float("nan"),
                    "df_corregido": df2,
                    "r_verificada": float(r_v),
                    "plausibilidad": (
                        _plausibilidad_anillo_estrecho(
                            ref_years_g, ref_vals_g, int(q["anio"]),
                            int(q["delta"]))
                        if ref_vals_g is not None else 1.0),
                    "origen": "quiebre",
                    "confiable": bool(q.get("confiable")),
                    "nitidez": int(q.get("nitidez", 0)),
                    "rango": q.get("rango"),
                    "perfil": q.get("perfil"),
                    "ganancia_quiebre": float(q.get("ganancia", float("nan"))),
                })

            # Primero las confiables, después el resto del quiebre, y al final
            # Dentro de la zona el orden es POR ESTRECHEZ, no por r. Es el
            # ranking que se validó: mezclarle la correlación verificada lo
            # desordena, porque entre años vecinos de la zona la r difiere en
            # milésimas y esas milésimas son ruido, mientras que lo estrecho
            # del anillo en la cronología sí informa dónde pudo faltar uno.
            por_quiebre.sort(
                key=lambda x: (
                    x["confiable"],
                    x.get("origen") == "zona",
                    (x.get("estrechez", 0.0) if x.get("origen") == "zona"
                     else x["r_verificada"])),
                reverse=True)
            claves_q = {(x["anio"], x["delta"]) for x in por_quiebre}
            sugerencias = por_quiebre + [
                x for x in sugerencias
                if (x.get("anio"), x.get("delta")) not in claves_q]

            # Fuera las candidatas que EMPEORAN la correlación. Nadie las va a
            # elegir, y llenan la tabla de ruido que estorba para encontrar
            # las que sirven.
            def _mejora(x):
                d = x.get("delta_r")
                if d is None or not np.isfinite(d):
                    a, b = x.get("r_antes"), x.get("r_tras")
                    if a is None or b is None:
                        return True          # sin dato: no se descarta
                    d = b - a
                return d > 0
            utiles = [x for x in sugerencias if _mejora(x)]
            if utiles:
                sugerencias = utiles
            _hay_quiebre_confiable = any(x["confiable"] for x in por_quiebre)
            if informe is not None:
                _informe_zona = informe
        except Exception:
            pass

    # Un quiebre CONFIABLE manda sobre el diagnóstico por ventanas. El
    # diagnóstico agrupa ventanas de largo fijo y acierta el signo con menos
    # frecuencia; dejar que filtre por su `delta_sugerido` descartaría justo
    # la candidata que las pruebas muestran correcta en el 100% de los casos.
    if _hay_quiebre_confiable:
        return sugerencias, False

    if not diagnostico:
        return sugerencias, es_marginal

    tipo = diagnostico.get("diagnostico")

    # Con un desfase de TODA la serie, proponer insertar o quitar un anillo
    # suelto es engañoso: lo que corresponde es corregir el año base. Se
    # devuelven cero sugerencias para no mandar al usuario a buscar un anillo
    # que no falta.
    if tipo == "desfase_global":
        return [], True

    if tipo == "ambiguo":
        # Sin dirección segura NO se muestra una sola opción: eso induciría a
        # buscar en la madera justo lo contrario de lo que puede haber. Se
        # ofrecen las mejores candidatas de AMBOS sentidos, alternadas, para
        # que sea la madera la que decida.
        pos = [s for s in sugerencias if s.get("delta", 0) > 0]
        neg = [s for s in sugerencias if s.get("delta", 0) < 0]
        mezcla = []
        for i in range(max(len(pos), len(neg))):
            if i < len(pos):
                mezcla.append(pos[i])
            if i < len(neg):
                mezcla.append(neg[i])
        return (mezcla or sugerencias), True

    if tipo != "error_interno":
        return sugerencias, es_marginal

    delta_ok = diagnostico.get("delta_sugerido")
    anio_ref = diagnostico.get("anio_error")
    if not delta_ok or anio_ref is None:
        return sugerencias, es_marginal

    # COHERENCIA: nunca mostrar correcciones del signo CONTRARIO al que dice
    # el diagnóstico. Si el análisis concluyó que falta un anillo, ofrecer
    # "quitar un anillo" manda al usuario a buscar justo lo opuesto de lo que
    # hay en la madera, y eso destruye la confianza en la herramienta. Es
    # preferible mostrar menos opciones —o ninguna— que opciones contrarias.
    coherentes = [s for s in sugerencias if s.get("delta") == delta_ok]

    # Si la búsqueda global no encontró ninguna del signo correcto (pasa
    # cuando la mejora no supera el umbral general), se generan candidatas
    # explícitas alrededor del año localizado y se evalúan de verdad.
    if not coherentes and _eval_r is not None:
        generadas = []
        for anio in range(int(anio_ref) - 25, int(anio_ref) + 26):
            try:
                df2 = aplicar_correccion(problema, int(anio), int(delta_ok),
                                         anclaje=anclaje)
            except Exception:
                continue
            r_v = _eval_r(df2)
            if not np.isfinite(r_v):
                continue
            if np.isfinite(_r_base_g) and r_v <= _r_base_g:
                continue  # no mejora: no se ofrece
            generadas.append({
                "anio": int(anio), "delta": int(delta_ok),
                "tipo": (f"+{delta_ok} anillo(s)" if delta_ok > 0
                         else f"{delta_ok} anillo(s)"),
                "r_antes": float("nan"), "r_tras": r_v,
                "delta_r": float("nan"), "r_zona_antes": float("nan"),
                "r_zona_tras": float("nan"), "df_corregido": df2,
                "r_verificada": r_v,
                "plausibilidad": _plausibilidad_anillo_estrecho(
                    ref_years_g, ref_vals_g, anio, delta_ok)
                if ref_vals_g is not None else 1.0,
            })
        if generadas:
            generadas.sort(key=lambda s: s["r_verificada"] * s.get("plausibilidad", 1.0),
                           reverse=True)
            coherentes = generadas[:10]
            es_marginal = True  # ninguna superó el umbral global

    def _clave(sug):
        dist = abs(int(sug.get("anio", 0)) - int(anio_ref))
        cercania = max(0.0, 1.0 - dist / 60.0)
        base = sug.get("r_verificada")
        if base is None or not np.isfinite(base):
            base = sug.get("puntaje", sug.get("delta_r", 0.0))
        return base * (0.5 + cercania) * sug.get("plausibilidad", 1.0)

    coherentes = sorted(coherentes, key=_clave, reverse=True)
    return coherentes, es_marginal


def diagnosticar_datacion(serie_std: pd.Series, crono_std: pd.Series,
                           ventana: int = 40, paso: int = 5,
                           max_shift: int = 3, min_overlap: int = 20) -> dict:
    """Determina QUÉ TRAMO de la serie está bien fechado y dónde está el error.

    Es como trabaja un dendrocronólogo: en vez de probar correcciones a ciegas
    en toda la serie, primero se busca el tramo que ya calza con la cronología
    (el ancla) y se localiza el punto donde deja de calzar.

    Para cada ventana móvil se prueba la serie desplazada en varios años y se
    ve QUÉ DESFASE gana localmente. Con eso se distinguen tres situaciones:

    • Todas las ventanas prefieren desfase 0 → la serie está bien fechada.
    • Todas prefieren el mismo desfase k ≠ 0 → la serie entera está corrida:
      no falta un anillo en medio, sino que el año base está mal (o faltan
      anillos fuera del tramo medido).
    • Unas prefieren 0 y otras k → hay un error DENTRO de la serie, justo en
      la frontera. El tramo que prefiere 0 es el que está bien fechado, y por
      tanto el que debe quedar fijo: si es el tramo reciente se ancla la
      corteza, si es el antiguo se ancla la médula.

    Devuelve un diccionario con las ventanas, los tramos detectados, el
    diagnóstico, el anclaje recomendado y el año y signo del error.
    """
    a = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    b = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()
    vacio = {"ventanas": [], "tramos": [], "diagnostico": "sin_datos",
             "anclaje_sugerido": "corteza", "anio_error": None,
             "delta_sugerido": 0, "shift_global": 0, "mensaje": ""}
    if a.empty or b.empty:
        return vacio

    ya = a.index.to_numpy(np.int64)
    va = a.to_numpy(dtype=float)
    yb = b.index.to_numpy(np.int64)
    vb = b.to_numpy(dtype=float)

    def _r(y_desde, y_hasta, shift):
        m = (ya >= y_desde) & (ya <= y_hasta)
        if m.sum() < min_overlap:
            return np.nan, 0
        comun, ia, ib = np.intersect1d(ya[m] + shift, yb,
                                       assume_unique=True, return_indices=True)
        if len(comun) < min_overlap:
            return np.nan, len(comun)
        x = va[m][ia]
        y = vb[ib]
        if np.std(x) == 0 or np.std(y) == 0:
            return np.nan, len(comun)
        return float(np.corrcoef(x, y)[0, 1]), len(comun)

    ini, fin = int(ya.min()), int(ya.max())
    # VENTANAS ADAPTATIVAS: una ventana fija de 40 años deja fuera cualquier
    # serie corta (una de 18 años no se podría analizar). La ventana se ajusta
    # al largo disponible: alrededor de un tercio de la serie, entre 12 y 50
    # años, con paso proporcional.
    largo = fin - ini + 1
    ventana = int(min(max(largo // 3, 12), max(ventana, 12)))
    paso = int(min(max(ventana // 8, 1), 10))
    min_overlap = int(min(max(ventana // 2, 8), min_overlap))
    mitad = ventana // 2
    ventanas = []
    # Los centros recorren TODA la serie, incluidos los extremos: la ventana se
    # recorta contra los bordes cuando hace falta. Antes iban de ini+mitad a
    # fin−mitad, así que los primeros y últimos 25 años nunca eran centro de
    # ventana. Con un error de datación cerca del final, el tramo reciente
    # —que es justamente el que está bien fechado— casi no se medía, el
    # desfase 0 apenas aparecía y el diagnóstico lo confundía con un desfase
    # de toda la serie.
    for centro in range(ini, fin + 1, max(1, paso)):
        desde = max(ini, centro - mitad)
        hasta = min(fin, centro + mitad)
        if hasta - desde + 1 < min_overlap:
            continue
        mejores = []
        for sh in range(-max_shift, max_shift + 1):
            r, n = _r(desde, hasta, sh)
            if np.isfinite(r):
                mejores.append((r, sh, n))
        if not mejores:
            continue
        r_best, sh_best, n_best = max(mejores, key=lambda t: t[0])
        r0 = next((r for r, sh, _ in mejores if sh == 0), np.nan)
        # Solo se considera "ganador" un desfase si mejora de forma clara:
        # diferencias mínimas son ruido, no evidencia de un error de datación.
        if np.isfinite(r0) and (r_best - r0) < 0.10:
            sh_best, r_best = 0, r0
        ventanas.append({"centro": int(centro), "shift": int(sh_best),
                         "r": float(r_best), "r0": float(r0) if np.isfinite(r0) else np.nan,
                         "n": int(n_best)})

    if not ventanas:
        return vacio

    # Agrupar ventanas consecutivas con el mismo desfase ganador
    tramos = []
    for v in ventanas:
        if tramos and tramos[-1]["shift"] == v["shift"]:
            tramos[-1]["fin"] = v["centro"]
            tramos[-1]["rs"].append(v["r"])
        else:
            tramos.append({"inicio": v["centro"], "fin": v["centro"],
                           "shift": v["shift"], "rs": [v["r"]]})
    for t in tramos:
        t["r_medio"] = float(np.nanmean(t["rs"]))
        del t["rs"]

    # Descartar tramos de una sola ventana: con ventanas de pocas décadas la
    # correlación es ruidosa y aparecen desfases "ganadores" espurios. Un
    # error de datación real se manifiesta de forma sostenida en varias
    # ventanas consecutivas, no en una suelta.
    # Al menos 3 ventanas consecutivas (2 pasos de extensión): con una o dos
    # el desfase ganador es inestable, sobre todo cerca de los extremos del
    # solape, y produce diagnósticos seguros pero equivocados.
    min_extension = max(2 * paso, 1)
    solidos = [t for t in tramos if (t["fin"] - t["inicio"]) >= min_extension]
    if not solidos:
        solidos = tramos

    # Cobertura de cada desfase (en años cubiertos por sus tramos sólidos)
    cobertura = {}
    for t in solidos:
        cobertura[t["shift"]] = cobertura.get(t["shift"], 0) + \
            (t["fin"] - t["inicio"] + paso)
    total = sum(cobertura.values()) or 1

    shifts = set(cobertura)
    res = dict(vacio)
    res["ventanas"] = ventanas
    res["tramos"] = solidos

    if shifts == {0}:
        res.update(diagnostico="bien_fechada", anio_error=None, delta_sugerido=0,
                   mensaje="La serie calza con la cronología en toda su extensión.")
        return res

    # Desfase dominante distinto de cero
    no_cero = {k: v for k, v in cobertura.items() if k != 0}
    k_dom = max(no_cero, key=no_cero.get) if no_cero else 0
    frac_dom = no_cero.get(k_dom, 0) / total
    frac_cero = cobertura.get(0, 0) / total

    # Si un desfase no nulo domina de forma abrumadora y prácticamente no hay
    # tramos bien fechados, la serie ENTERA está corrida. El umbral es
    # exigente a propósito: basta con que exista un tramo sólido a desfase 0
    # para que se trate como error interno, porque ese tramo es una fecha
    # firme y lo que hay que hacer es corregir el resto respecto de él.
    hay_tramo_bueno = any(t["shift"] == 0 for t in solidos)
    if frac_dom >= 0.80 and not hay_tramo_bueno:
        res.update(diagnostico="desfase_global", shift_global=k_dom,
                   delta_sugerido=(1 if k_dom < 0 else -1),
                   anio_error=None,
                   mensaje=(f"TODA la serie calza mejor desplazada {k_dom:+d} "
                            f"año(s) ({frac_dom*100:.0f}% de las ventanas). No es "
                            "un anillo faltante en medio: el año base está mal, o "
                            "falta(n) anillo(s) fuera del tramo medido (cerca de "
                            "la corteza o de la médula)."))
        return res

    buenos = [t for t in solidos if t["shift"] == 0]
    malos = [t for t in solidos if t["shift"] == k_dom]
    if not buenos or not malos:
        res.update(diagnostico="ambiguo",
                   mensaje=("El patrón de desfases no es concluyente: la señal "
                            "común es débil o hay más de un error."))
        return res

    # Tramos más EXTENSOS de cada clase (no el de mayor desfase, que suele ser ruido)
    ancla = max(buenos, key=lambda t: (t["fin"] - t["inicio"], t["r_medio"]))
    peor = max(malos, key=lambda t: (t["fin"] - t["inicio"], t["r_medio"]))

    # CONFIANZA: la dirección del error (si falta o sobra un anillo) se deduce
    # del desfase que prefiere el tramo desajustado. Si ese tramo correlaciona
    # mal, su desfase "ganador" es poco más que ruido y la dirección puede
    # salir invertida — algo mucho peor que no opinar, porque manda a buscar
    # justo lo contrario de lo que hay en la madera. En ese caso se señala la
    # zona sospechosa sin afirmar la dirección.
    r_peor = peor.get("r_medio", 0.0)
    r_ancla = ancla.get("r_medio", 0.0)
    evidencia_debil = (not np.isfinite(r_peor) or r_peor < 0.25 or
                       (np.isfinite(r_ancla) and r_ancla > 0 and
                        r_peor < 0.55 * r_ancla))
    if evidencia_debil:
        zona = f"{peor['inicio']}–{peor['fin']}"
        res.update(diagnostico="ambiguo", anio_error=None, delta_sugerido=0,
                   mensaje=(f"El tramo {ancla['inicio']}–{ancla['fin']} calza bien "
                            f"(r≈{r_ancla:.2f}), pero el tramo {zona} tiene una "
                            f"correlación demasiado baja (r≈{r_peor:.2f}) para "
                            "determinar con seguridad si falta o sobra un anillo. "
                            "Revisa la madera en ese tramo: puede haber un anillo "
                            "ausente, un falso anillo, o simplemente poca señal "
                            "común en esos años."))
        return res

    if peor["inicio"] > ancla["fin"]:
        anio_error = int((ancla["fin"] + peor["inicio"]) // 2)
        lado = "reciente"
    else:
        anio_error = int((peor["fin"] + ancla["inicio"]) // 2)
        lado = "antiguo"

    # AFINADO POR PUNTO DE QUIEBRE: la frontera entre tramos solo da una
    # resolución del ancho de la ventana. Acá se busca el año T que mejor
    # separa "antes de T calza con desfase k" de "desde T calza con desfase 0",
    # usando TODOS los datos de cada lado (no una ventana fija). Además se
    # devuelve el INTERVALO de años compatibles: con señal común débil el dato
    # no alcanza para un año único, y dar uno solo mandaría al usuario a
    # buscar donde no es.
    k_ancla = peor["shift"]
    perfil = {}
    z = lambda r: np.arctanh(np.clip(r, -0.999, 0.999))
    min_seg = int(min(max((fin - ini + 1) // 6, 6), 15))

    def _r_seg(mask, sh):
        if mask.sum() < min_seg:
            return np.nan, 0
        com, ia, ib = np.intersect1d(ya[mask] + sh, yb,
                                     assume_unique=True, return_indices=True)
        if len(com) < min_seg:
            return np.nan, 0
        x = va[mask][ia]
        y = vb[ib]
        if np.std(x) == 0 or np.std(y) == 0:
            return np.nan, 0
        return float(np.corrcoef(x, y)[0, 1]), len(com)

    lo = max(int(ya.min()), int(yb.min()))
    hi = min(int(ya.max()), int(yb.max()))
    antes_es_malo = (peor["fin"] <= ancla["inicio"])
    for T in range(lo + min_seg, hi - min_seg + 1):
        if antes_es_malo:
            r1, n1 = _r_seg(ya < T, k_ancla)
            r2, n2 = _r_seg(ya >= T, 0)
        else:
            r1, n1 = _r_seg(ya < T, 0)
            r2, n2 = _r_seg(ya >= T, k_ancla)
        if not (np.isfinite(r1) and np.isfinite(r2)) or (n1 + n2) == 0:
            continue
        perfil[T] = (n1 * z(r1) + n2 * z(r2)) / (n1 + n2)

    rango = None
    candidatos = []
    if perfil:
        t_best = max(perfil, key=perfil.get)
        mx = perfil[t_best]
        # Umbral del intervalo: se calibró con series reales (ACI044B contra
        # una cronología de 169 series, r≈0.61) para que el intervalo sea
        # informativo y siga conteniendo el año verdadero.
        compatibles = [t for t, v in perfil.items() if v >= mx - 0.03]
        anio_error = int(t_best)
        if compatibles:
            # El estimador tiende a situar el quiebre uno o dos años DESPUÉS
            # del anillo que falta (el primer año mal fechado ya "arrastra" al
            # anterior), así que se garantiza un margen mínimo alrededor del
            # punto estimado para que el año verdadero quede dentro.
            rango = (min(min(compatibles), anio_error - 4),
                     max(max(compatibles), anio_error + 4))

        # LISTA CORTA DE AÑOS CONCRETOS. El intervalo por sí solo puede ser
        # ancho, y mandar al usuario a revisar 25 años de madera no sirve de
        # mucho. Pero dentro de ese intervalo no todos los años son igual de
        # probables: un anillo que se omite al fechar es casi siempre uno
        # ESTRECHO. Se combinan las dos fuentes de información —el perfil del
        # punto de quiebre y lo estrecho que es cada año en la cronología— y
        # se devuelven los pocos años que hay que mirar en la madera.
        if compatibles and vb.size > 5:
            media_c = float(np.nanmean(vb))
            sd_c = float(np.nanstd(vb)) or 1.0
            rango_perf = (max(perfil.values()) - min(perfil.values())) or 1.0
            puntuados = []
            for t in compatibles:
                pos = np.searchsorted(yb, t)
                if pos >= yb.size or int(yb[pos]) != int(t):
                    continue
                # estrechez: cuántas desviaciones bajo la media está ese año
                estrechez = (media_c - float(vb[pos])) / sd_c
                verosim = (perfil[t] - min(perfil.values())) / rango_perf
                puntuados.append((t, verosim + 0.6 * max(estrechez, 0.0),
                                  float(vb[pos])))
            puntuados.sort(key=lambda x: -x[1])
            candidatos = [{"anio": int(t), "indice_crono": round(v, 3)}
                          for t, _, v in puntuados[:5]]
    res["rango_error"] = rango
    res["candidatos"] = candidatos

    # Si el tramo bien fechado es el RECIENTE, hay que dejar fija la corteza;
    # si es el ANTIGUO, dejar fija la médula.
    centro_ancla = (ancla["inicio"] + ancla["fin"]) / 2.0
    centro_serie = (ini + fin) / 2.0
    anclaje = "corteza" if centro_ancla >= centro_serie else "medula"

    delta = 1 if k_dom < 0 else -1
    res.update(diagnostico="error_interno", anio_error=anio_error,
               delta_sugerido=delta, anclaje_sugerido=anclaje,
               shift_global=k_dom,
               mensaje=(f"El tramo {ancla['inicio']}–{ancla['fin']} calza bien "
                        f"(r≈{ancla['r_medio']:.2f}) y el tramo "
                        f"{peor['inicio']}–{peor['fin']} calza mejor desplazado "
                        f"{k_dom:+d}.<br><b>Busca el anillo "
                        + (f"entre {rango[0]} y {rango[1]}" if rango
                           else f"hacia {anio_error}")
                        + "</b>"
                        + (("<br><b>Años más probables</b> (estrechos en la "
                            "cronología, revísalos primero): "
                            + ", ".join(str(c["anio"]) for c in candidatos))
                           if candidatos else f" (lo más probable, {anio_error})")
                        + ". "
                        + ("El intervalo es amplio porque la señal común con la "
                           "cronología es débil; con una cronología de más series "
                           "se estrecha. "
                           if (rango and (rango[1] - rango[0]) > 25) else "")
                        + f"Se ancla en "
                        f"{'corteza' if anclaje == 'corteza' else 'médula'} "
                        f"para no mover el tramo ya fechado."))
    return res


def buscar_correcciones(ref, problema, mitad_ventana, max_corr=MAX_CORRECCION,
                        anclaje="corteza",
                        transformar_ref=None, transformar_prob=None,
                        delta_r_minimo: float = 0.05,
                        max_fallback: int = 3):
    """Busca correcciones que mejoran la correlación global.

    Devuelve tupla **(sugerencias, es_marginal)**:
      • Si hay correcciones con Δr ≥ delta_r_minimo: devuelve esas (hasta 15) y
        es_marginal = False.
      • Si no hay correcciones significativas pero sí hay alguna mejora positiva:
        devuelve las mejores hasta `max_fallback` y es_marginal = True. Esto
        permite mostrar un "sanity check" al usuario en lugar de una lista vacía,
        con la advertencia de que son cambios dentro del ruido estadístico.
      • Si no hay ninguna mejora positiva: devuelve ([], False).

    delta_r_minimo: filtro de ruido. 0.05 es razonable; con series ya
    correctamente cofechadas las "mejoras" suelen ser 0.01-0.04 (ruido) y
    las correcciones reales suelen estar en 0.10+.
    """
    if transformar_ref is None:
        transformar_ref = lambda s: pd.to_numeric(s, errors="coerce").astype(float).dropna()
    if transformar_prob is None:
        transformar_prob = lambda s: pd.to_numeric(s, errors="coerce").astype(float).dropna()

    d_ref = transformar_ref(ref["Ancho_mm"])
    d_prob = transformar_prob(problema["Ancho_mm"])
    overlap_base = list(d_ref.index.intersection(d_prob.index))
    if len(overlap_base) < OVERLAP_MINIMO_ANALISIS:
        return [], False

    r_global_base = _r_pearson(d_ref.loc[overlap_base].values, d_prob.loc[overlap_base].values)
    if np.isnan(r_global_base):
        return [], False

    _, r_movil_base = _r_movil(d_ref, d_prob, overlap_base, mitad_ventana)

    # OPTIMIZACIÓN CLAVE (antes el programa se colgaba): todo el bucle de
    # candidatos se hace en numpy puro. Se transforma la serie UNA sola vez
    # (fuera del bucle) y cada corrección candidata se aplica sobre los
    # arreglos ya transformados, alineando con la referencia por año con
    # np.intersect1d. Nada de spline ni construcción de DataFrames por
    # candidato (eso era lo lento).
    ref_years = d_ref.index.to_numpy(np.int64)
    ref_vals = d_ref.to_numpy(dtype=float)
    prob_years = d_prob.index.to_numpy(np.int64)
    prob_vals = d_prob.to_numpy(dtype=float)
    prob_mean = float(np.nanmean(prob_vals)) if prob_vals.size else 0.0
    ref_min, ref_max = int(ref_years.min()), int(ref_years.max())

    ob_arr = np.asarray(overlap_base, dtype=np.int64)
    base_ref_ov = d_ref.loc[overlap_base].to_numpy(dtype=float)
    base_prob_ov = d_prob.loc[overlap_base].to_numpy(dtype=float)

    _anclar_corteza = str(anclaje).lower().startswith("cort")

    def _corr_np(anio, delta):
        """Aplica la corrección sobre (prob_years, prob_vals) en numpy,
        respetando el anclaje elegido, y devuelve (años, valores) ordenados."""
        yrs = prob_years.copy()
        vals = prob_vals.copy()
        a = int(anio)
        for _ in range(abs(delta)):
            if delta > 0:
                if _anclar_corteza:
                    yrs = np.where(yrs <= a, yrs - 1, yrs)
                else:
                    yrs = np.where(yrs >= a, yrs + 1, yrs)
                yrs = np.append(yrs, a)
                vals = np.append(vals, prob_mean)
            else:
                m = yrs != a
                yrs = yrs[m]
                vals = vals[m]
                if _anclar_corteza:
                    yrs = np.where(yrs < a, yrs + 1, yrs)
                else:
                    yrs = np.where(yrs > a, yrs - 1, yrs)
        o = np.argsort(yrs, kind="stable")
        return yrs[o], vals[o]

    resultados = []
    # Limitar los años a probar a la zona que puede afectar el solape con la
    # referencia (un año posterior a ref_max no cambia la correlación).
    anios_candidatos = [int(a) for a in problema.index
                        if ref_min - max_corr <= int(a) <= ref_max]
    for anio in anios_candidatos:
        for delta in range(-max_corr, max_corr + 1):
            if delta == 0:
                continue
            cyrs, cvals = _corr_np(anio, delta)
            common, iref, icorr = np.intersect1d(
                ref_years, cyrs, assume_unique=True, return_indices=True)
            if common.size < OVERLAP_MINIMO_ANALISIS:
                continue
            a_vals = ref_vals[iref]
            b_vals = cvals[icorr]
            r_global_tras = _r_pearson(a_vals, b_vals)
            if np.isnan(r_global_tras):
                continue
            delta_r = r_global_tras - r_global_base
            if delta_r <= 0:
                continue

            zmask = np.abs(common - anio) <= mitad_ventana
            r_zona_tras = np.nan
            if int(zmask.sum()) >= OVERLAP_MINIMO_GRAFICO:
                r_zona_tras = _r_pearson(a_vals[zmask], b_vals[zmask])
            zbmask = np.abs(ob_arr - anio) <= mitad_ventana
            r_zona_antes = np.nan
            if int(zbmask.sum()) >= OVERLAP_MINIMO_GRAFICO:
                r_zona_antes = _r_pearson(base_ref_ov[zbmask], base_prob_ov[zbmask])

            # Solo para las candidatas que mejoran: la serie CRUDA corregida
            # (barata, sin spline) que se guardará para aplicarla luego.
            df_corr = aplicar_correccion(problema, anio, delta, anclaje=anclaje)

            # PLAUSIBILIDAD BIOLÓGICA: los anillos que se omiten al fechar son
            # casi siempre los ESTRECHOS (años malos), no los anchos. Cuando
            # varios años dan una mejora de correlación parecida —cosa muy
            # habitual, porque desplazar la serie un año produce mejoras
            # similares en un tramo— la estadística sola no distingue cuál es.
            # Aquí se pondera cada candidato según lo estrecho que sea ese año
            # en la REFERENCIA (la cronología): un año marcadamente bajo la
            # media es un candidato mucho más creíble para un anillo faltante.
            plaus = _plausibilidad_anillo_estrecho(
                ref_years, ref_vals, anio, delta)

            resultados.append({
                "anio": int(anio), "delta": delta,
                "tipo": f"+{delta} anillo(s)" if delta > 0 else f"{delta} anillo(s)",
                "r_antes": r_global_base, "r_tras": r_global_tras,
                "delta_r": delta_r, "r_zona_antes": r_zona_antes,
                "r_zona_tras": r_zona_tras, "df_corregido": df_corr,
                "plausibilidad": plaus,
                "puntaje": delta_r * plaus,
            })

    # Ordenar por PUNTAJE (mejora de correlación × plausibilidad del año),
    # no solo por la mejora bruta.
    resultados.sort(key=lambda x: x.get("puntaje", x["delta_r"]), reverse=True)

    # Deduplicar correcciones solapadas (cerca del mismo año con mismo signo)
    filtrados, ocupados = [], []
    for r in resultados:
        solapado = any(
            abs(r["anio"] - oc["anio"]) <= 5 and np.sign(r["delta"]) == np.sign(oc["delta"])
            for oc in ocupados)
        if not solapado:
            filtrados.append(r)
            ocupados.append(r)

    # Separar en significativas y fallback marginal
    significativas = [r for r in filtrados if r["delta_r"] >= delta_r_minimo]
    if significativas:
        return significativas[:15], False
    return filtrados[:max_fallback], True


# =============================================================================
# MODO COFECHA
# =============================================================================

def aplicar_modo_cofecha(serie_mm, rigidez_spline=32, aplicar_log=True,
                          aplicar_ar=True, aplicar_first_diff=False):
    """Spline detrending + log + AR(1). Holmes (1983)."""
    s = pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
    if len(s) < 10:
        return s.copy()

    valores = s.to_numpy(dtype=float)

    try:
        from scipy.interpolate import UnivariateSpline
        x = np.arange(len(valores), dtype=float)
        s_factor = max(
            np.var(valores) * len(valores) * (rigidez_spline / max(len(valores), 1)) ** 1.5,
            1e-3,
        )
        spl = UnivariateSpline(x, valores, s=s_factor)
        tendencia = spl(x)
        tendencia = np.where(tendencia <= 0, np.nanmean(valores), tendencia)
        valores = valores / tendencia
    except Exception as exc:
        logger.warning("Spline COFECHA falló: %s", exc)
        valores = valores / np.mean(valores)

    if aplicar_log:
        media = np.mean(valores)
        c_const = media / 6.0 if media > 0 else 0.001
        valores = np.log(np.maximum(valores + c_const, 1e-10))

    if aplicar_ar and len(valores) > 4:
        c = valores - np.mean(valores)
        if np.std(c) > 0:
            phi = np.corrcoef(c[1:], c[:-1])[0, 1]
            if np.isnan(phi):
                phi = 0.0
            phi = float(np.clip(phi, -0.99, 0.99))
            residuales = c.copy()
            residuales[1:] = c[1:] - phi * c[:-1]
            valores = residuales

    if aplicar_first_diff and len(valores) > 1:
        valores = np.diff(valores)
        return pd.Series(valores, index=s.index[1:])

    return pd.Series(valores, index=s.index)


class DialogoSeleccionCronologias(QDialog):
    """Permite elegir CUÁLES cronologías cargar de un archivo con varias.

    Un archivo (sobre todo .ods/.xlsx) puede traer varias cronologías, ya sea
    en columnas distintas o en hojas distintas. Antes se obligaba a elegir una
    sola; acá se pueden marcar todas las que se quieran (todas marcadas por
    defecto).
    """

    def __init__(self, candidatos: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿Qué cronologías quieres cargar?")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        titulo = QLabel(
            "<b>El archivo contiene varias cronologías</b><br>"
            "<span style='color:#888; font-size:11px;'>"
            "Marca las que quieras cargar. Cada una se agregará como una "
            "cronología (📚) independiente.</span>"
        )
        titulo.setWordWrap(True)
        layout.addWidget(titulo)

        self.lista = QListWidget()
        for etiqueta in candidatos:
            it = QListWidgetItem(etiqueta)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)  # todas por defecto
            self.lista.addItem(it)
        layout.addWidget(self.lista)

        fila = QHBoxLayout()
        btn_todas = QPushButton("Marcar todas")
        btn_todas.clicked.connect(lambda: self._marcar(True))
        btn_ninguna = QPushButton("Desmarcar todas")
        btn_ninguna.clicked.connect(lambda: self._marcar(False))
        fila.addWidget(btn_todas)
        fila.addWidget(btn_ninguna)
        fila.addStretch()
        layout.addLayout(fila)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _marcar(self, marcar: bool):
        estado = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        for i in range(self.lista.count()):
            self.lista.item(i).setCheckState(estado)

    def seleccionadas(self) -> list[str]:
        return [self.lista.item(i).text()
                for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.CheckState.Checked]


class DialogoCofecha(QDialog):
    """Configuración del Modo COFECHA."""

    def __init__(self, parent=None, params: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Modo COFECHA — Configuración")
        self.setMinimumWidth(520)
        params = params or {}
        layout = QVBoxLayout(self)

        titulo = QLabel(
            "<b>Transformaciones tipo COFECHA</b><br>"
            "<span style='color:#888; font-size:11px;'>"
            "Holmes (1983). Aplicado a las series antes de calcular correlaciones."
            "</span>"
        )
        titulo.setWordWrap(True)
        layout.addWidget(titulo)

        grp_sp = QGroupBox("1. Spline detrending")
        f_sp = QFormLayout(grp_sp)
        self.spin_rigidez = SpinBoxFlechas()
        self.spin_rigidez.setRange(10, 200)
        self.spin_rigidez.setValue(int(params.get("rigidez_spline", 32)))
        self.spin_rigidez.setSuffix(" años")
        f_sp.addRow("Rigidez:", self.spin_rigidez)
        layout.addWidget(grp_sp)

        grp_t = QGroupBox("2. Transformaciones")
        v_t = QVBoxLayout(grp_t)
        self.chk_log = QCheckBox("Transformación logarítmica  log(x + media/6)")
        self.chk_log.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_log.setChecked(params.get("aplicar_log", True))
        self.chk_log.setToolTip(
            "Pondera de forma más equitativa las diferencias proporcionales.\n"
            "La constante 1/6 de la media evita log(0)."
        )
        v_t.addWidget(self.chk_log)
        self.chk_ar = QCheckBox("Modelado AR(1)")
        self.chk_ar.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_ar.setChecked(params.get("aplicar_ar", True))
        self.chk_ar.setToolTip(
            "Elimina la autocorrelación (inercia biológica).\n"
            "Resta phi × x[t-1] de cada valor."
        )
        v_t.addWidget(self.chk_ar)
        layout.addWidget(grp_t)

        grp_fd = QGroupBox("3. Opcional")
        v_fd = QVBoxLayout(grp_fd)
        self.chk_fd = QCheckBox("Primeras diferencias  x[t] − x[t−1]")
        self.chk_fd.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_fd.setChecked(params.get("aplicar_first_diff", False))
        self.chk_fd.setToolTip(
            "Estabiliza series con períodos prolongados de varianza alta y baja.\n"
            "Activar solo si las transformaciones anteriores no son suficientes."
        )
        v_fd.addWidget(self.chk_fd)
        layout.addWidget(grp_fd)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_params(self) -> dict:
        return {
            "rigidez_spline": self.spin_rigidez.value(),
            "aplicar_log": self.chk_log.isChecked(),
            "aplicar_ar": self.chk_ar.isChecked(),
            "aplicar_first_diff": self.chk_fd.isChecked(),
        }


# =============================================================================
# VENTANA TABLA DE OFFSET
# =============================================================================

class DialogoEditarAnillos(QDialog):
    """Editor de anillos que CONSERVA el ancho total de la madera.

    Principio dendrocronológico: cuando se elimina un anillo, su ancho no
    desaparece — pasa a un anillo vecino (la madera sigue ahí). Cuando se
    inserta un anillo, su ancho debe salir de un anillo vecino (que lo
    pierde). Así el ancho radial total se mantiene constante.

    Operaciones:
      • Eliminar anillo: se suma su ancho al vecino elegido (anterior o
        posterior). Útil para anillos falsos (dos contados como uno).
      • Insertar anillo: se crea con un ancho que se resta de un vecino.
        Útil para anillos faltantes / fusionados (un ancho que en realidad
        eran dos años).

    Tras editar, los años se renumeran consecutivamente desde el año de
    inicio.
    """

    # Estilo de radio buttons con indicador NARANJA al seleccionar, igual
    # que el resto del programa (el círculo por defecto no se distingue
    # bien en tema oscuro).
    ESTILO_RADIO = (
        "QRadioButton{spacing:6px; padding:2px;}"
        "QRadioButton::indicator{width:14px; height:14px; border-radius:8px;"
        " border:2px solid #888;}"
        "QRadioButton::indicator:checked{background-color:#e67e22;"
        " border:2px solid #e67e22;}"
        "QRadioButton::indicator:unchecked{background-color:transparent;}"
        "QRadioButton:disabled{color:#666;}"
    )

    def __init__(self, df_serie, nombre, panel_ref, parent=None,
                 sugerencia=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar anillos — {nombre}")
        self.resize(440, 600)
        self._nombre = nombre
        self._panel = panel_ref

        df = df_serie.sort_index()
        self._anchos = [float(x) for x in
                        pd.to_numeric(df["Ancho_mm"], errors="coerce").fillna(0).values]
        self._start_year = int(df.index.min())
        # Copia original para deshacer
        self._anchos_orig = list(self._anchos)
        self._start_orig = self._start_year

        layout = QVBoxLayout(self)

        info = QLabel(
            "<span style='color:#aaa; font-size:11px;'>"
            "El ancho total de la madera se <b>conserva</b>: al eliminar un "
            "anillo su ancho pasa a un vecino; al insertar uno, su ancho se "
            "resta de un vecino. Selecciona un anillo y usa los botones."
            "</span>")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Banner de sugerencia (cuando se abre desde "Aplicar corrección").
        # Indica al usuario qué operación sugiere el cofechado y en qué año,
        # pero la decisión final (qué ancho mover y hacia qué vecino) la toma
        # él en el diálogo de insertar/eliminar, conservando el ancho.
        if sugerencia:
            anio_s = sugerencia.get("anio")
            delta_s = sugerencia.get("delta", 0)
            if delta_s > 0:
                accion = (f"Posible anillo <b>FALTANTE</b> cerca del año "
                          f"<b>{anio_s}</b>. Selecciona ese anillo y pulsa "
                          f"<b>➕ Insertar anillo</b> para agregarlo, eligiendo "
                          f"de qué vecino tomar el ancho.")
                color = "#5bc0de"
            else:
                accion = (f"Posible anillo <b>FALSO/EXTRA</b> en el año "
                          f"<b>{anio_s}</b>. Selecciónalo y pulsa "
                          f"<b>➖ Eliminar anillo</b>, eligiendo a qué vecino "
                          f"sumarle el ancho.")
                color = "#d9534f"
            banner = QLabel(f"<span style='font-size:11px;'>💡 {accion}</span>")
            banner.setWordWrap(True)
            banner.setStyleSheet(
                f"QLabel{{background-color:rgba(0,0,0,40); border-left:3px "
                f"solid {color}; padding:6px 8px; border-radius:3px;}}")
            layout.addWidget(banner)

        # ── Anclaje y años de la serie ───────────────────────────────
        # No siempre conviene fijar la corteza: en series o cronologías
        # FLOTANTES el usuario puede querer extenderlas hacia el presente,
        # dejando fijo el primer año. Por eso se ofrece la opción.
        fila_ancla = QHBoxLayout()
        fila_ancla.addWidget(QLabel("Al insertar/eliminar, mantener fijo:"))
        self.combo_ancla_editor = QComboBox()
        self.combo_ancla_editor.addItem("Último año (corteza)", "corteza")
        self.combo_ancla_editor.addItem("Primer año (médula)", "medula")
        self.combo_ancla_editor.setToolTip(
            "Qué extremo de la serie NO se mueve al agregar o quitar anillos.\n\n"
            "• Último año (corteza): para árboles vivos, donde el año del\n"
            "  anillo externo se conoce con certeza. Al insertar un anillo la\n"
            "  serie empieza un año antes y sigue terminando igual.\n\n"
            "• Primer año (médula): para series o cronologías FLOTANTES que se\n"
            "  quieran extender hacia el presente. Al insertar un anillo la\n"
            "  serie termina un año después.")
        fila_ancla.addWidget(self.combo_ancla_editor, 1)
        layout.addLayout(fila_ancla)

        fila_anios = QHBoxLayout()
        fila_anios.addWidget(QLabel("Año inicio:"))
        self.spin_anio_inicio = QSpinBox()
        self.spin_anio_inicio.setRange(-20000, 20000)
        self.spin_anio_inicio.setValue(self._start_year)
        self.spin_anio_inicio.setToolTip(
            "Desplaza TODA la serie para que comience en este año.")
        self.spin_anio_inicio.valueChanged.connect(self._on_anio_inicio_cambiado)
        fila_anios.addWidget(self.spin_anio_inicio)
        fila_anios.addWidget(QLabel("Año fin:"))
        self.spin_anio_fin = QSpinBox()
        self.spin_anio_fin.setRange(-20000, 20000)
        self.spin_anio_fin.setValue(self._start_year + len(self._anchos) - 1)
        self.spin_anio_fin.setToolTip(
            "Desplaza TODA la serie para que termine en este año.")
        self.spin_anio_fin.valueChanged.connect(self._on_anio_fin_cambiado)
        fila_anios.addWidget(self.spin_anio_fin)
        fila_anios.addStretch()
        layout.addLayout(fila_anios)

        # ── Tabla + botones al costado ───────────────────────────────
        # Los botones van JUNTO a la lista (no debajo) para poder seleccionar
        # un año y operar sobre él viendo el resultado al instante.
        fila_centro = QHBoxLayout()

        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Año", "Ancho (mm)"])
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fila_centro.addWidget(self.tabla, 1)

        col_ops = QVBoxLayout()
        col_ops.setSpacing(4)

        lbl_ins = QLabel("<b>Insertar anillo</b>")
        lbl_ins.setStyleSheet("font-size:11px;")
        col_ops.addWidget(lbl_ins)

        # Dos flechas: insertar ANTES (hacia arriba en la lista, años más
        # antiguos) o DESPUÉS (hacia abajo) del año seleccionado.
        btn_ins_arriba = QPushButton("⬆  Antes")
        btn_ins_arriba.setToolTip(
            "Inserta un anillo EN el año seleccionado.\n"
            "El año seleccionado y los anteriores retroceden un año;\n"
            "el último año de la serie (corteza) no se mueve.")
        btn_ins_arriba.clicked.connect(lambda: self._insertar_en(desplazar_antes=True))
        col_ops.addWidget(btn_ins_arriba)

        btn_ins_abajo = QPushButton("⬇  Después")
        btn_ins_abajo.setToolTip(
            "Inserta un anillo DESPUÉS del año seleccionado\n"
            "(entre el seleccionado y el siguiente).")
        btn_ins_abajo.clicked.connect(lambda: self._insertar_en(desplazar_antes=False))
        col_ops.addWidget(btn_ins_abajo)

        col_ops.addSpacing(10)
        lbl_del = QLabel("<b>Eliminar anillo</b>")
        lbl_del.setStyleSheet("font-size:11px;")
        col_ops.addWidget(lbl_del)

        btn_eliminar = QPushButton("✖  Eliminar")
        btn_eliminar.setToolTip(
            "Elimina el anillo seleccionado. Su ancho se suma a un vecino\n"
            "para conservar el ancho total de la madera.")
        btn_eliminar.clicked.connect(self._eliminar)
        col_ops.addWidget(btn_eliminar)

        col_ops.addSpacing(10)
        btn_deshacer = QPushButton("↺  Deshacer todo")
        btn_deshacer.clicked.connect(self._deshacer)
        col_ops.addWidget(btn_deshacer)

        col_ops.addStretch()
        self.lbl_resumen_edicion = QLabel("")
        self.lbl_resumen_edicion.setWordWrap(True)
        self.lbl_resumen_edicion.setStyleSheet("font-size:10px; color:#aaa;")
        col_ops.addWidget(self.lbl_resumen_edicion)

        cont_ops = QWidget()
        cont_ops.setLayout(col_ops)
        cont_ops.setMaximumWidth(210)
        fila_centro.addWidget(cont_ops)
        layout.addLayout(fila_centro, 1)

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("font-weight:bold; padding:4px;")
        layout.addWidget(self.lbl_total)

        # Botones de cierre
        fila_cierre = QHBoxLayout()
        fila_cierre.addStretch()
        btn_aplicar = QPushButton("✅ Aplicar cambios")
        btn_aplicar.setStyleSheet(
            "QPushButton{background-color:#27ae60; color:white; "
            "font-weight:bold; padding:5px 12px; border-radius:4px;}"
            "QPushButton:hover{background-color:#2ecc71;}")
        btn_aplicar.clicked.connect(self._aplicar)
        fila_cierre.addWidget(btn_aplicar)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_cierre.addWidget(btn_cancelar)
        layout.addLayout(fila_cierre)

        self._refrescar_tabla()
        self._actualizar_resumen_edicion()

        # Pre-seleccionar el anillo del año sugerido, si se indicó.
        if sugerencia and sugerencia.get("anio") is not None:
            fila = int(sugerencia["anio"]) - self._start_year
            if 0 <= fila < len(self._anchos):
                self.tabla.selectRow(fila)
                self.tabla.scrollToItem(
                    self.tabla.item(fila, 0),
                    QAbstractItemView.ScrollHint.PositionAtCenter)

    def _years(self):
        return list(range(self._start_year,
                          self._start_year + len(self._anchos)))

    def _refrescar_tabla(self, seleccionar=None):
        years = self._years()
        self.tabla.setRowCount(len(self._anchos))
        for i, (y, w) in enumerate(zip(years, self._anchos)):
            it = QTableWidgetItem(); it.setData(Qt.ItemDataRole.DisplayRole, int(y))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(i, 0, it)
            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole, round(w, 4))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(i, 1, it)
        total = sum(self._anchos)
        total_orig = sum(self._anchos_orig)
        self.lbl_total.setText(
            f"Total: {total:.4f} mm  |  {len(self._anchos)} anillos  |  "
            f"Original: {total_orig:.4f} mm "
            f"({'✅ conservado' if abs(total-total_orig) < 1e-6 else '⚠️ DIFIERE'})")
        if seleccionar is not None and 0 <= seleccionar < len(self._anchos):
            self.tabla.selectRow(seleccionar)

    def _fila_sel(self):
        sel = self.tabla.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(
                self, "Selecciona un anillo",
                "Primero selecciona un anillo en la tabla.")
            return None
        return sel[0].row()

    def _eliminar(self):
        idx = self._fila_sel()
        if idx is None:
            return
        years = self._years()
        w = self._anchos[idx]
        # Diálogo para elegir destino del ancho
        dlg = QDialog(self)
        dlg.setWindowTitle("Eliminar anillo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"Vas a eliminar el anillo del año <b>{years[idx]}</b> "
            f"(ancho {w:.4f} mm).<br>¿A qué anillo vecino se le suma ese "
            f"ancho?", dlg))
        rb_ant = QRadioButton(
            f"Anterior ({years[idx-1]})" if idx > 0 else "Anterior (no existe)")
        rb_post = QRadioButton(
            f"Posterior ({years[idx+1]})" if idx < len(years)-1
            else "Posterior (no existe)")
        rb_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setStyleSheet(self.ESTILO_RADIO)
        rb_ant.setEnabled(idx > 0)
        rb_post.setEnabled(idx < len(years)-1)
        if idx > 0:
            rb_ant.setChecked(True)
        else:
            rb_post.setChecked(True)
        lay.addWidget(rb_ant); lay.addWidget(rb_post)
        botones = QHBoxLayout(); botones.addStretch()
        ok = QPushButton("Eliminar"); ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar"); ca.clicked.connect(dlg.reject)
        botones.addWidget(ok); botones.addWidget(ca)
        lay.addLayout(botones)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if rb_ant.isChecked() and idx > 0:
            self._anchos[idx-1] += w
            nueva_sel = idx - 1
        elif rb_post.isChecked() and idx < len(self._anchos)-1:
            self._anchos[idx+1] += w
            nueva_sel = idx
        else:
            return
        del self._anchos[idx]
        # Con corteza anclada la serie pierde un anillo, así que el inicio
        # avanza un año; con médula anclada el inicio se mantiene.
        if self._anclar_corteza():
            self._start_year += 1
        self._refrescar_tabla(seleccionar=min(nueva_sel, len(self._anchos)-1))
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _anclar_corteza(self) -> bool:
        """True si el ÚLTIMO año debe quedar fijo al insertar/eliminar."""
        combo = getattr(self, "combo_ancla_editor", None)
        if combo is None:
            return True
        return (combo.currentData() or "corteza") == "corteza"

    def _sincronizar_spins_anio(self):
        """Refleja los años actuales en los campos, sin disparar sus señales."""
        if not hasattr(self, "spin_anio_inicio") or not self._anchos:
            return
        fin = self._start_year + len(self._anchos) - 1
        for spin, val in ((self.spin_anio_inicio, self._start_year),
                          (self.spin_anio_fin, fin)):
            spin.blockSignals(True)
            spin.setValue(int(val))
            spin.blockSignals(False)

    def _on_anio_inicio_cambiado(self, valor: int):
        """Desplaza toda la serie para que comience en `valor`."""
        if not self._anchos:
            return
        self._start_year = int(valor)
        self._sincronizar_spins_anio()
        self._refrescar_tabla(seleccionar=self._fila_sel())
        self._actualizar_resumen_edicion()

    def _on_anio_fin_cambiado(self, valor: int):
        """Desplaza toda la serie para que termine en `valor`."""
        if not self._anchos:
            return
        self._start_year = int(valor) - len(self._anchos) + 1
        self._sincronizar_spins_anio()
        self._refrescar_tabla(seleccionar=self._fila_sel())
        self._actualizar_resumen_edicion()

    def _insertar_en(self, desplazar_antes: bool = True):
        """Inserta un anillo manteniendo FIJO el último año (corteza).

        `desplazar_antes=True` coloca el anillo EN el año seleccionado (ese año
        y los anteriores retroceden uno); False lo coloca justo después.

        El último año de la serie no se mueve: si la muestra termina en 2024 y
        se inserta el anillo que faltaba en 2023, la serie sigue terminando en
        2024 y el inicio retrocede un año. Antes el editor dejaba fijo el
        primer año y la serie se estiraba hacia el presente (terminaba en
        2025), obligando a corregir el año base a mano después.
        """
        idx = self._fila_sel()
        if idx is None:
            QMessageBox.information(
                self, "Selecciona un año",
                "Elige en la lista el año donde quieres insertar el anillo.")
            return
        years = self._years()
        anio_sel = years[idx]
        insert_idx = idx if desplazar_antes else idx + 1

        dlg = QDialog(self)
        dlg.setWindowTitle("Insertar anillo")
        dlg.setMinimumWidth(430)
        lay = QVBoxLayout(dlg)
        destino = anio_sel if desplazar_antes else anio_sel + 1
        if self._anclar_corteza():
            efecto = (f"El último año (<b>{years[-1]}</b>) no se mueve; "
                      f"la serie comenzará un año antes.")
        else:
            efecto = (f"El primer año (<b>{years[0]}</b>) no se mueve; "
                      f"la serie terminará un año después.")
        lay.addWidget(QLabel(
            f"Se insertará un anillo en el año <b>{destino}</b>.<br>"
            f"{efecto}<br><br>"
            f"El ancho del nuevo anillo se <b>resta</b> de un vecino, para que "
            f"el ancho total de la madera no cambie.", dlg))

        lay.addWidget(QLabel("Tomar el ancho del anillo:", dlg))
        rb_ant = QRadioButton("Anterior (el de más adentro)", dlg)
        rb_post = QRadioButton("Posterior (el de más afuera)", dlg)
        rb_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setStyleSheet(self.ESTILO_RADIO)
        rb_post.setChecked(True)
        lay.addWidget(rb_ant)
        lay.addWidget(rb_post)

        fila_w = QHBoxLayout()
        fila_w.addWidget(QLabel("Ancho del nuevo anillo (mm):", dlg))
        spin_w = QDoubleSpinBox(dlg)
        spin_w.setDecimals(4)
        spin_w.setRange(0.0, 100.0)
        spin_w.setSingleStep(0.01)
        fila_w.addWidget(spin_w)
        lay.addLayout(fila_w)
        lbl_ayuda = QLabel("", dlg)
        lbl_ayuda.setStyleSheet("color:#888; font-size:10px;")
        lbl_ayuda.setWordWrap(True)
        lay.addWidget(lbl_ayuda)

        def _vecino_actual():
            return insert_idx - 1 if rb_ant.isChecked() else insert_idx

        def _actualizar_max():
            v = _vecino_actual()
            if 0 <= v < len(self._anchos):
                disp = self._anchos[v]
                spin_w.setMaximum(disp)
                if spin_w.value() > disp:
                    spin_w.setValue(disp)
                lbl_ayuda.setText(
                    f"El vecino ({self._years()[v]}) mide {disp:.4f} mm; "
                    f"quedará con {max(disp - spin_w.value(), 0):.4f} mm.")
            else:
                spin_w.setMaximum(0.0)
                lbl_ayuda.setText("⚠️ No hay vecino en esa dirección.")

        rb_ant.toggled.connect(_actualizar_max)
        rb_post.toggled.connect(_actualizar_max)
        spin_w.valueChanged.connect(lambda _v: _actualizar_max())
        _actualizar_max()

        botones = QHBoxLayout()
        botones.addStretch()
        ok = QPushButton("Insertar", dlg)
        ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar", dlg)
        ca.clicked.connect(dlg.reject)
        botones.addWidget(ok)
        botones.addWidget(ca)
        lay.addLayout(botones)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        ancho_nuevo = spin_w.value()
        vecino = _vecino_actual()
        if vecino < 0 or vecino >= len(self._anchos):
            QMessageBox.warning(self, "Sin vecino",
                                "No hay un anillo vecino en esa dirección.")
            return
        if self._anchos[vecino] < ancho_nuevo - 1e-9:
            QMessageBox.warning(
                self, "Ancho insuficiente",
                f"El anillo vecino solo tiene {self._anchos[vecino]:.4f} mm.")
            return

        self._anchos[vecino] -= ancho_nuevo
        self._anchos.insert(insert_idx, ancho_nuevo)
        # Si se ancla la corteza, al crecer la serie el inicio retrocede (el
        # último año no se mueve). Si se ancla la médula, el inicio se queda y
        # la serie se extiende hacia el presente.
        if self._anclar_corteza():
            self._start_year -= 1
        self._refrescar_tabla(seleccionar=insert_idx)
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _actualizar_resumen_edicion(self):
        """Muestra en vivo cómo quedó la serie tras las ediciones."""
        lbl = getattr(self, "lbl_resumen_edicion", None)
        if lbl is None:
            return
        years = self._years()
        if not years:
            lbl.setText("")
            return
        n_orig = len(self._anchos_orig)
        dif = len(self._anchos) - n_orig
        txt = f"Ahora: {years[0]}–{years[-1]} ({len(self._anchos)} anillos)"
        if dif:
            txt += f"<br><b>{dif:+d}</b> respecto al original " \
                   f"({self._start_orig}–{self._start_orig + n_orig - 1})"
        lbl.setText(txt)

    def _insertar(self):
        idx = self._fila_sel()
        if idx is None:
            return
        years = self._years()
        dlg = QDialog(self)
        dlg.setWindowTitle("Insertar anillo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            f"Insertar un nuevo anillo junto al año <b>{years[idx]}</b>.<br>"
            f"El ancho del nuevo anillo se RESTA de un vecino (la madera se "
            f"reparte).", dlg))

        # Posición
        lay.addWidget(QLabel("Posición del nuevo anillo:", dlg))
        rb_antes = QRadioButton(f"Antes de {years[idx]}")
        rb_despues = QRadioButton(f"Después de {years[idx]}")
        rb_antes.setStyleSheet(self.ESTILO_RADIO)
        rb_despues.setStyleSheet(self.ESTILO_RADIO)
        rb_antes.setChecked(True)
        lay.addWidget(rb_antes); lay.addWidget(rb_despues)

        # Origen del ancho
        lay.addWidget(QLabel("Tomar el ancho del anillo:", dlg))
        rb_org_ant = QRadioButton("Anterior")
        rb_org_post = QRadioButton("Posterior")
        rb_org_ant.setStyleSheet(self.ESTILO_RADIO)
        rb_org_post.setStyleSheet(self.ESTILO_RADIO)
        rb_org_ant.setChecked(True)
        lay.addWidget(rb_org_ant); lay.addWidget(rb_org_post)

        # Ancho
        fila_w = QHBoxLayout()
        fila_w.addWidget(QLabel("Ancho del nuevo anillo (mm):", dlg))
        spin_w = QDoubleSpinBox(dlg)
        spin_w.setDecimals(4); spin_w.setRange(0.0, 100.0)
        spin_w.setSingleStep(0.01)
        spin_w.setValue(0.0)
        fila_w.addWidget(spin_w)
        lay.addLayout(fila_w)
        lbl_ayuda = QLabel("", dlg)
        lbl_ayuda.setStyleSheet("color:#888; font-size:10px;")
        lay.addWidget(lbl_ayuda)

        def _actualizar_max():
            # Calcular índice de inserción y vecino origen para mostrar el máx
            insert_idx = idx if rb_antes.isChecked() else idx + 1
            if rb_org_ant.isChecked():
                vecino = insert_idx - 1
            else:
                vecino = insert_idx
            if 0 <= vecino < len(self._anchos):
                disponible = self._anchos[vecino]
                spin_w.setMaximum(disponible)
                lbl_ayuda.setText(
                    f"Máximo disponible del vecino: {disponible:.4f} mm")
            else:
                spin_w.setMaximum(0.0)
                lbl_ayuda.setText("⚠️ No hay vecino en esa dirección.")
        for rb in (rb_antes, rb_despues, rb_org_ant, rb_org_post):
            rb.toggled.connect(_actualizar_max)
        _actualizar_max()

        botones = QHBoxLayout(); botones.addStretch()
        ok = QPushButton("Insertar"); ok.clicked.connect(dlg.accept)
        ca = QPushButton("Cancelar"); ca.clicked.connect(dlg.reject)
        botones.addWidget(ok); botones.addWidget(ca)
        lay.addLayout(botones)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        ancho_nuevo = spin_w.value()
        insert_idx = idx if rb_antes.isChecked() else idx + 1
        vecino = insert_idx - 1 if rb_org_ant.isChecked() else insert_idx
        if vecino < 0 or vecino >= len(self._anchos):
            QMessageBox.warning(self, "Sin vecino",
                                "No hay un anillo vecino en esa dirección.")
            return
        if self._anchos[vecino] < ancho_nuevo - 1e-9:
            QMessageBox.warning(
                self, "Ancho insuficiente",
                f"El anillo vecino solo tiene {self._anchos[vecino]:.4f} mm.")
            return
        self._anchos[vecino] -= ancho_nuevo
        self._anchos.insert(insert_idx, ancho_nuevo)
        if self._anclar_corteza():
            self._start_year -= 1
        self._refrescar_tabla(seleccionar=insert_idx)
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _deshacer(self):
        self._anchos = list(self._anchos_orig)
        self._start_year = self._start_orig
        self._refrescar_tabla()
        self._sincronizar_spins_anio()
        self._actualizar_resumen_edicion()

    def _aplicar(self):
        if not self._anchos:
            QMessageBox.warning(self, "Serie vacía",
                                "La serie no puede quedar sin anillos.")
            return
        years = self._years()
        df_new = pd.DataFrame(
            {"Ancho_mm": self._anchos},
            index=pd.Index(years, name="Anio"),
        )
        if self._panel is not None and hasattr(self._panel, "reemplazar_serie"):
            self._panel.reemplazar_serie(self._nombre, df_new)
        QMessageBox.information(
            self, "Listo",
            f"Serie '{self._nombre}' actualizada: {len(self._anchos)} anillos, "
            f"años {years[0]}–{years[-1]}.")
        self.accept()


class DialogoAlineamientoAnillos(QDialog):
    """Muestra el resultado del alineamiento óptimo por programación
    dinámica: tabla de segmentos de desfase constante + lista de
    correcciones (anillos faltantes/sobrantes) detectadas.

    Permite reajustar la penalización y el máximo de correcciones en vivo
    y recalcular, para explorar entre un análisis conservador y uno
    exploratorio.
    """

    def __init__(self, serie_a, serie_b, shift_base, nombre_serie,
                 parent=None, penalizacion=3.0, max_correcciones=10,
                 panel_ref=None, nombre_real=None):
        super().__init__(parent)
        self.setWindowTitle(f"Alineamiento óptimo — {nombre_serie}")
        self.resize(760, 600)
        self._serie_a = serie_a
        self._serie_b = serie_b
        self._shift_base = shift_base
        self._nombre = nombre_serie
        # Para abrir el editor de anillos: necesitamos el panel y el nombre
        # REAL de la serie (clave en series_datos), no el del título.
        self._panel_ref = panel_ref
        self._nombre_real = nombre_real or nombre_serie

        layout = QVBoxLayout(self)

        info = QLabel(
            "<b>Alineamiento óptimo por programación dinámica.</b><br>"
            f"<span style='color:#aaa; font-size:11px;'>"
            f"Analizando desde el desfase base <b>{shift_base}</b>. "
            "Descompone la serie completa buscando dónde conviene insertar "
            "anillos faltantes o eliminar anillos sobrantes para maximizar "
            "la concordancia con la cronología. Cada fila es un tramo de "
            "desfase constante. Una <b>corrección ≠ 0</b> indica que en ese "
            "tramo la serie debería correrse respecto al anterior — revisa "
            "la madera en el año señalado. <i>La madera manda: esto es solo "
            "una guía de dónde mirar.</i>"
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Controles de recálculo ────────────────────────────────────
        fila_cfg = QHBoxLayout()
        lbl_pen = QLabel("Penalización:")
        lbl_pen.setToolTip(
            "Costo por cada corrección de anillo.\n"
            "• Bajo (1–3): exploratorio, propone más correcciones.\n"
            "• Alto (6–12): conservador, solo las muy evidentes.")
        fila_cfg.addWidget(lbl_pen)
        self.spin_pen = QDoubleSpinBox()
        self.spin_pen.setRange(0.5, 30.0)
        self.spin_pen.setSingleStep(0.5)
        self.spin_pen.setValue(penalizacion)
        self.spin_pen.setToolTip(lbl_pen.toolTip())
        fila_cfg.addWidget(self.spin_pen)

        lbl_max = QLabel("Máx. correcciones:")
        lbl_max.setToolTip(
            "Cantidad máxima de anillos (acumulada) que el algoritmo puede "
            "insertar o eliminar.")
        fila_cfg.addWidget(lbl_max)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 30)
        self.spin_max.setValue(max_correcciones)
        self.spin_max.setToolTip(lbl_max.toolTip())
        fila_cfg.addWidget(self.spin_max)

        btn_recalc = QPushButton("🔄 Recalcular")
        btn_recalc.clicked.connect(self._recalcular)
        fila_cfg.addWidget(btn_recalc)
        fila_cfg.addStretch()
        layout.addLayout(fila_cfg)

        # ── Resumen de correcciones ───────────────────────────────────
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setStyleSheet(
            "QLabel{background:rgba(230,126,34,0.12); border:1px solid "
            "rgba(230,126,34,0.4); border-radius:4px; padding:6px 8px; "
            "font-size:11px;}")
        layout.addWidget(self.lbl_resumen)

        # ── Tabla de segmentos ────────────────────────────────────────
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels([
            "Tramo (serie)", "Años calendario", "Corrección",
            "n", "r", "GLK", "Anillo término",
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tabla)

        # ── Botones ───────────────────────────────────────────────────
        fila_btn = QHBoxLayout()
        btn_copiar = QPushButton("📋 Copiar")
        btn_copiar.clicked.connect(self._copiar)
        fila_btn.addWidget(btn_copiar)
        btn_exportar = QPushButton("💾 Exportar CSV")
        btn_exportar.clicked.connect(self._exportar)
        fila_btn.addWidget(btn_exportar)
        # Botón para abrir el editor de anillos y aplicar las correcciones
        # que el análisis sugiere (insertar/eliminar conservando el ancho).
        if (self._panel_ref is not None
                and hasattr(self._panel_ref, "series_datos")):
            btn_editar = QPushButton("✏️ Editar anillos de esta serie")
            btn_editar.setStyleSheet(
                "QPushButton{background-color:#8e44ad; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#9b59b6;}")
            btn_editar.setToolTip(
                "Abre el editor para insertar o eliminar anillos en los años "
                "señalados, conservando el ancho total de la madera.")
            btn_editar.clicked.connect(self._abrir_editor_anillos)
            fila_btn.addWidget(btn_editar)
        fila_btn.addStretch()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        fila_btn.addWidget(btn_cerrar)
        layout.addLayout(fila_btn)

        self._recalcular()

    def _abrir_editor_anillos(self):
        """Abre el editor de anillos con la serie REAL (anchos en mm) del
        panel principal, para aplicar correcciones de anillos faltantes/
        sobrantes conservando el ancho."""
        df = self._panel_ref.series_datos.get(self._nombre_real)
        if df is None or df.empty:
            QMessageBox.warning(
                self, "Serie no encontrada",
                "No se encontró la serie en el panel principal.")
            return
        # Recordatorio de las correcciones detectadas
        corrs = self._resultado.get("correcciones", []) if self._resultado else []
        if corrs:
            resumen = "; ".join(
                f"{c['tipo']} ~{c['anio_calendario']}" for c in corrs)
            QMessageBox.information(
                self, "Correcciones sugeridas",
                f"El análisis sugiere: {resumen}.\n\n"
                "En el editor, inserta o elimina los anillos en esos años. "
                "Recuerda: la madera manda — verifica antes de aplicar.")
        dlg = DialogoEditarAnillos(df, self._nombre_real, self._panel_ref,
                                    parent=self)
        dlg.exec()

    def _recalcular(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._resultado = alineamiento_optimo_anillos(
                self._serie_a, self._serie_b, self._shift_base,
                max_correcciones=self.spin_max.value(),
                penalizacion=self.spin_pen.value(),
            )
        finally:
            QApplication.restoreOverrideCursor()

        if self._resultado is None:
            self.lbl_resumen.setText("No hay datos suficientes para alinear.")
            self.tabla.setRowCount(0)
            return

        self._llenar_tabla()
        self._llenar_resumen()

    def _llenar_resumen(self):
        corrs = self._resultado["correcciones"]
        if not corrs:
            self.lbl_resumen.setText(
                "✅ No se detectaron anillos faltantes ni sobrantes: la serie "
                "alinea con la cronología sin correcciones internas en su "
                "posición actual.")
            return
        faltantes = [c for c in corrs if c["tipo"] == "faltante"]
        sobrantes = [c for c in corrs if c["tipo"] == "sobrante"]
        partes = []
        if faltantes:
            anios = ", ".join(str(c["anio_calendario"]) for c in faltantes)
            partes.append(
                f"<b>{len(faltantes)} posible(s) anillo(s) FALTANTE(s)</b> "
                f"(insertar) cerca de: {anios}")
        if sobrantes:
            anios = ", ".join(str(c["anio_calendario"]) for c in sobrantes)
            partes.append(
                f"<b>{len(sobrantes)} posible(s) anillo(s) SOBRANTE(s)</b> "
                f"(eliminar) cerca de: {anios}")
        self.lbl_resumen.setText(
            "⚠️ " + " &nbsp;•&nbsp; ".join(partes) +
            "<br><span style='color:#aaa;'>Revisa la madera en esos años "
            "antes de aceptar cualquier corrección.</span>")

    def _llenar_tabla(self):
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        segs = self._resultado["segmentos"]
        self.tabla.setRowCount(len(segs))
        for row, seg in enumerate(segs):
            it = QTableWidgetItem(f"{seg['serie_ini']}–{seg['serie_fin']}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 0, it)

            it = QTableWidgetItem(f"{seg['cal_ini']}–{seg['cal_fin']}")
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 1, it)

            corr = seg["correccion"]
            txt_corr = "0" if corr == 0 else f"{corr:+d}"
            it = QTableWidgetItem(txt_corr)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if corr != 0:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
                it.setToolTip(
                    "Corrección neta de anillos respecto al inicio de la "
                    "serie. Distinto de 0 = en este tramo la serie va corrida "
                    "respecto a su posición original.")
            self.tabla.setItem(row, 2, it)

            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole, int(seg["n"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 3, it)

            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole,
                float(round(seg["r"], 3)) if np.isfinite(seg["r"]) else 0.0)
            it.setBackground(QColor(_color_r(seg["r"])))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 4, it)

            glk_pct = seg["glk"] * 100 if np.isfinite(seg["glk"]) else float("nan")
            it = QTableWidgetItem(); it.setData(
                Qt.ItemDataRole.DisplayRole,
                float(round(glk_pct, 1)) if np.isfinite(glk_pct) else 0.0)
            it.setBackground(QColor(_color_glk(seg["glk"])))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 5, it)

            # Año de término calendario del tramo (con aviso si futuro)
            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(seg["cal_fin"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if seg["cal_fin"] > anio_actual:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
            self.tabla.setItem(row, 6, it)

    def _filas_texto(self):
        filas = [["Tramo_serie", "Anios_calendario", "Correccion",
                  "n", "r", "GLK_pct", "Anio_termino"]]
        for row in range(self.tabla.rowCount()):
            filas.append([
                self.tabla.item(row, c).text() if self.tabla.item(row, c)
                else "" for c in range(7)])
        return filas

    def _copiar(self):
        filas = self._filas_texto()
        QApplication.clipboard().setText(
            "\n".join("\t".join(f) for f in filas))

    def _exportar(self):
        ruta_default = os.path.join(_ultima_carpeta(), "alineamiento_anillos.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar alineamiento", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(self._filas_texto())
            QMessageBox.information(self, "Éxito", "Alineamiento exportado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{e}")


class VentanaTablaOffset(QDialog):
    """Tabla detallada con r, GLK y t-BP por cada desfase.

    Si se pasan `serie_a` y `serie_b` (las series transformadas usadas
    en el cálculo), agrega ARRIBA de la tabla un gráfico apropiado al
    tipo de serie:
      - Serie FLOTANTE (año mínimo < 500): gráfico de barras del
        puntaje compuesto por cada desfase. Permite ver de un vistazo
        dónde está el pico que indica la posición candidata.
      - Serie FECHADA (año mínimo ≥ 500): gráfico de correlación
        móvil con ventanas deslizantes año a año, aplicando el mejor
        desfase. Permite identificar zonas problemáticas dentro de la
        serie (años donde el cofechado se debilita).
    """

    def __init__(self, shifts, rs, glks=None, tbps=None, ns=None,
                 serie_a=None, serie_b=None, parent=None,
                 nombre_serie=None, panel_ref=None):
        super().__init__(parent)
        self.setWindowTitle("Resultados de Análisis de Desfases")
        self._nombre_serie = nombre_serie
        self._panel_ref = panel_ref
        # Si vamos a mostrar gráfico, necesitamos más alto
        if serie_a is not None and serie_b is not None and len(shifts) > 0:
            self.resize(720, 720)
        else:
            self.resize(560, 540)
        layout = QVBoxLayout(self)

        info = QLabel(
            "<span style='color:#aaa; font-size:11px;'>"
            "Resultados ordenados por <b>puntaje compuesto</b> descendente. "
            "El puntaje combina las tres métricas (r × GLK × t-BP)^(1/3) — "
            "es lo más confiable para identificar la fecha verdadera."
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        glks = glks if glks is not None else [float("nan")] * len(shifts)
        tbps = tbps if tbps is not None else [float("nan")] * len(shifts)
        ns   = ns   if ns   is not None else [0] * len(shifts)

        scores = [score_compuesto(r, g, t) for r, g, t in zip(rs, glks, tbps)]

        # Guardar para el botón de alineamiento óptimo. El mejor desfase es
        # el de mayor puntaje compuesto (centro de la banda de búsqueda).
        self._serie_a = serie_a
        self._serie_b = serie_b
        self._mejor_shift_detalle = 0
        if shifts:
            scores_validos = [(i, s) for i, s in enumerate(scores)
                              if np.isfinite(s)]
            if scores_validos:
                self._mejor_shift_detalle = shifts[
                    max(scores_validos, key=lambda x: x[1])[0]]
            else:
                self._mejor_shift_detalle = shifts[int(np.argmax(rs))]

        # ── Gráfico opcional ──────────────────────────────────────────
        if serie_a is not None and serie_b is not None and len(shifts) > 0:
            self._agregar_grafico_detalle(
                layout, shifts, rs, glks, tbps, scores,
                serie_a, serie_b,
            )

        # Año de término base (último año de la serie sin desfase). Si hay
        # serie_a disponible, por cada desfase mostramos el año en que
        # terminaría la serie: útil para validar contra la presencia de
        # corteza (el término debería ser cercano al año de colecta).
        anio_max_base = None
        if serie_a is not None and len(serie_a) > 0:
            try:
                anio_max_base = int(serie_a.index.max())
            except (ValueError, TypeError):
                anio_max_base = None

        n_cols = 7 if anio_max_base is not None else 6
        self.tabla = QTableWidget(len(shifts), n_cols)
        if anio_max_base is not None:
            self.tabla.setHorizontalHeaderLabels(
                ["Desfase", "Año término", "Puntaje", "r", "GLK", "t-BP", "n"])
        else:
            self.tabla.setHorizontalHeaderLabels(
                ["Desfase", "Puntaje", "r", "GLK", "t-BP", "n"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setSortingEnabled(False)
        # Selección por fila para poder elegir un desfase y correr el
        # alineamiento desde ahí (no solo desde el mejor).
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        import datetime as _dt
        _anio_actual = _dt.datetime.now().year

        for row, (sh, r, g, t, n, sc) in enumerate(zip(shifts, rs, glks, tbps, ns, scores)):
            c = 0
            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(sh))
            self.tabla.setItem(row, c, it); c += 1

            # Columna Año término (solo si tenemos la serie)
            if anio_max_base is not None:
                anio_fin = anio_max_base + int(sh)
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, int(anio_fin))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if anio_fin > _anio_actual:
                    # Posición imposible: término en el futuro
                    it.setForeground(QColor("#e67e22"))
                    f = it.font(); f.setBold(True); it.setFont(f)
                    it.setToolTip(
                        f"El término ({anio_fin}) supera el año actual "
                        f"({_anio_actual}): posición imposible.")
                self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(sc, 3)) if np.isfinite(sc) else 0.0)
            it.setBackground(QColor(_color_compuesto(sc)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(r, 3)) if np.isfinite(r) else 0.0)
            it.setBackground(QColor(_color_r(r)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(g, 3)) if np.isfinite(g) else 0.0)
            it.setBackground(QColor(_color_glk(g)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(t, 2)) if np.isfinite(t) else 0.0)
            it.setBackground(QColor(_color_tbp(t)))
            self.tabla.setItem(row, c, it); c += 1

            it = QTableWidgetItem()
            it.setData(Qt.ItemDataRole.DisplayRole, int(n))
            self.tabla.setItem(row, c, it); c += 1

        self.tabla.setSortingEnabled(True)
        # Ordenar por Puntaje descendente (columna 2 si hay año término, 1 si no)
        col_puntaje = 2 if anio_max_base is not None else 1
        self.tabla.sortItems(col_puntaje, Qt.SortOrder.DescendingOrder)
        layout.addWidget(self.tabla)

        fila_btns = QHBoxLayout()
        btn_copiar = QPushButton("📋 Copiar Todo")
        btn_copiar.clicked.connect(self.copiar_portapapeles)
        fila_btns.addWidget(btn_copiar)
        btn_exportar = QPushButton("💾 Exportar a CSV")
        btn_exportar.clicked.connect(self.exportar_csv)
        fila_btns.addWidget(btn_exportar)
        # Botón de alineamiento óptimo (anillos faltantes/sobrantes).
        # Solo tiene sentido si tenemos las series para descomponer.
        if self._serie_a is not None and self._serie_b is not None:
            btn_alinear = QPushButton("🧬 Buscar anillos faltantes/sobrantes")
            btn_alinear.setStyleSheet(
                "QPushButton{background-color:#8e44ad; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#9b59b6;}")
            btn_alinear.setToolTip(
                "Descompone la serie por programación dinámica para detectar "
                "dónde podría faltar o sobrar un anillo, buscando el "
                "alineamiento óptimo con la cronología.\n\n"
                "Selecciona primero una fila (un desfase) para analizar desde "
                "esa posición. Sin selección, usa el mejor desfase.")
            btn_alinear.clicked.connect(self._abrir_alineamiento)
            fila_btns.addWidget(btn_alinear)

        # Botón para aplicar el desfase SELECCIONADO a la serie.
        if self._panel_ref is not None and self._nombre_serie is not None:
            btn_aplicar = QPushButton("✅ Aplicar desfase seleccionado")
            btn_aplicar.setStyleSheet(
                "QPushButton{background-color:#27ae60; color:white; "
                "font-weight:bold; padding:5px 10px; border-radius:4px;}"
                "QPushButton:hover{background-color:#2ecc71;}")
            btn_aplicar.setToolTip(
                "Aplica a la serie el desfase de la fila seleccionada (cambia "
                "su año de inicio) y la grafica re-datada en el panel "
                "principal.\n\nSelecciona una fila primero. Sin selección, "
                "usa el mejor desfase.")
            btn_aplicar.clicked.connect(self._aplicar_desfase_seleccionado)
            fila_btns.addWidget(btn_aplicar)

        layout.addLayout(fila_btns)

    def _aplicar_desfase_seleccionado(self):
        """Aplica a la serie el desfase de la fila seleccionada, re-datándola
        en el panel principal."""
        import datetime as _dt
        shift = self._mejor_shift_detalle
        seleccion = self.tabla.selectionModel().selectedRows()
        if seleccion:
            cell = self.tabla.item(seleccion[0].row(), 0)
            if cell is not None:
                try:
                    shift = int(cell.data(Qt.ItemDataRole.DisplayRole))
                except (ValueError, TypeError):
                    pass

        df = self._panel_ref.series_datos.get(self._nombre_serie)
        if df is None or df.empty:
            QMessageBox.warning(self, "Error",
                                "No se encontró la serie en el panel.")
            return
        nuevo_ini = int(df.index.min()) + shift
        nuevo_fin = int(df.index.max()) + shift
        anio_actual = _dt.datetime.now().year
        aviso = ""
        if nuevo_fin > anio_actual:
            aviso = (f"\n\n⚠️ El año de término ({nuevo_fin}) supera el año "
                     f"actual ({anio_actual}): datación probablemente espuria.")

        signo = f"+{shift}" if shift >= 0 else str(shift)
        resp = QMessageBox.question(
            self, "Aplicar desfase",
            f"Aplicar desfase {signo} a la serie '{self._nombre_serie}':\n"
            f"quedaría en los años {nuevo_ini}–{nuevo_fin}.{aviso}\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        if self._panel_ref.aplicar_desfase_a_serie(self._nombre_serie, shift):
            QMessageBox.information(
                self, "Listo",
                f"Serie '{self._nombre_serie}' re-datada a "
                f"{nuevo_ini}–{nuevo_fin}.")
            self.accept()
        else:
            QMessageBox.information(
                self, "Sin cambios",
                "El desfase es 0; la serie ya está en esa posición.")

    def _abrir_alineamiento(self):
        """Abre el diálogo de alineamiento óptimo (anillos faltantes/
        sobrantes). Usa el desfase de la fila SELECCIONADA en la tabla
        como punto de partida; si no hay fila seleccionada, usa el mejor
        desfase. Así el usuario puede explorar el alineamiento desde
        cualquier posición candidata, no solo la mejor."""
        shift_base = self._mejor_shift_detalle
        seleccion = self.tabla.selectionModel().selectedRows()
        if seleccion:
            row = seleccion[0].row()
            cell = self.tabla.item(row, 0)  # columna 0 = Desfase
            if cell is not None:
                val = cell.data(Qt.ItemDataRole.DisplayRole)
                try:
                    shift_base = int(val)
                except (ValueError, TypeError):
                    pass
        nombre = self.windowTitle().replace(
            "Resultados de Análisis de Desfases", "serie")
        dlg = DialogoAlineamientoAnillos(
            self._serie_a, self._serie_b, shift_base,
            nombre, parent=self,
            penalizacion=3.0, max_correcciones=10,  # exploratorio por defecto
            panel_ref=self._panel_ref,
            nombre_real=self._nombre_serie,
        )
        dlg.exec()

    def _agregar_grafico_detalle(self, layout, shifts, rs, glks, tbps,
                                  scores, serie_a, serie_b):
        """Agrega un gráfico apropiado al tipo de serie arriba de la tabla.

        Detecta automáticamente si la serie es flotante o fechada según
        el año mínimo de la serie y dibuja el gráfico correspondiente:

          - Año mínimo < 500 → FLOTANTE → gráfico de barras del puntaje
            compuesto vs desfase. La barra más alta muestra la posición
            candidata.
          - Año mínimo ≥ 500 → FECHADA → correlación móvil año a año
            aplicando el mejor desfase. Permite ver zonas internas
            problemáticas de la serie.
        """
        anio_min = int(serie_a.index.min()) if not serie_a.empty else 0
        es_flotante = anio_min < 500

        grafico = pg.PlotWidget()
        _agregar_hover_anio(grafico)
        grafico.setBackground(None)
        grafico.showGrid(x=True, y=True, alpha=0.3)
        grafico.setMinimumHeight(180)

        if es_flotante:
            self._dibujar_barras_desfase(grafico, shifts, scores)
        else:
            self._dibujar_correlacion_movil(grafico, serie_a, serie_b,
                                              shifts, scores)

        layout.addWidget(grafico)

    def _dibujar_barras_desfase(self, grafico, shifts, scores):
        """Gráfico de barras: puntaje compuesto vs desfase.

        Útil para series flotantes — la barra más alta indica la posición
        candidata. Las barras se colorean por el umbral del puntaje
        compuesto (verde=alto, amarillo=medio, rojo=bajo) usando los
        mismos colores que la tabla.
        """
        grafico.setTitle("Puntaje compuesto por desfase")
        grafico.setLabel("bottom", "Desfase (años)")
        grafico.setLabel("left", "Puntaje compuesto")

        # Reemplazar NaN por 0 para que las barras sean dibujables
        scores_plot = [s if np.isfinite(s) else 0.0 for s in scores]

        # Una barra por desfase, coloreada por el puntaje
        for x, s in zip(shifts, scores_plot):
            color = _color_compuesto(s) if np.isfinite(s) else "#666"
            bar = pg.BarGraphItem(
                x=[x], height=[s], width=0.8,
                brush=pg.mkBrush(QColor(color)),
                pen=pg.mkPen(QColor(color).darker(110)),
            )
            grafico.addItem(bar)

        # Línea horizontal en y=0 como referencia
        grafico.addItem(pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen("#888", width=1)))

        # Resaltar el mejor desfase con una línea vertical
        scores_validos = [(i, s) for i, s in enumerate(scores)
                          if np.isfinite(s)]
        if scores_validos:
            idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
            grafico.addItem(pg.InfiniteLine(
                pos=shifts[idx_mejor], angle=90,
                pen=pg.mkPen("#5cb85c", width=2, style=Qt.PenStyle.DashLine)))

    def _dibujar_correlacion_movil(self, grafico, serie_a, serie_b,
                                     shifts, scores):
        """Gráfico de correlación móvil: r/GLK/t-BP en ventanas
        deslizantes a lo largo del solape, aplicando el mejor desfase.

        Útil para series fechadas — permite detectar tramos internos
        donde el cofechado se debilita (años con potenciales errores
        de medición o anillos faltantes/extra).
        """
        # Aplicar el mejor desfase a la serie_a antes de calcular ventanas
        scores_validos = [(i, s) for i, s in enumerate(scores)
                          if np.isfinite(s)]
        mejor_shift = shifts[max(scores_validos, key=lambda x: x[1])[0]] \
            if scores_validos else 0

        s_a_shifted = serie_a.copy()
        s_a_shifted.index = s_a_shifted.index + mejor_shift
        overlap = s_a_shifted.index.intersection(serie_b.index)

        if len(overlap) < 30:
            grafico.setTitle("Solape insuficiente para correlación móvil")
            return

        # Transformación para el r móvil: respeta el modo COFECHA del panel
        # (si está activo, usa esa estandarización; si no, los datos tal
        # cual, sin corrección). Para GLK se usa la serie tal cual la ventana
        # (esa función diferencia internamente). Así el r móvil es coherente
        # con la tabla y con el botón modo COFECHA.
        a_raw_al = s_a_shifted.loc[overlap]
        b_raw_al = serie_b.loc[overlap]
        panel = getattr(self, "_panel_ref", None)
        if panel is not None and hasattr(panel, "_transformar_para_correlacion"):
            # serie_a es la serie (no cronología); serie_b la cronología
            a_corr_full = panel._transformar_para_correlacion(a_raw_al, es_crono=False)
            b_corr_full = panel._transformar_para_correlacion(b_raw_al, es_crono=True)
        else:
            a_corr_full = a_raw_al
            b_corr_full = b_raw_al
        a_dl = a_corr_full
        b_dl = b_corr_full
        a_arr = a_raw_al.to_numpy(dtype=float)
        b_arr = b_raw_al.to_numpy(dtype=float)
        anios_overlap = list(overlap)

        # Ventana móvil de 30 años (estándar dendrocronológico)
        VENTANA = 30
        if len(anios_overlap) < VENTANA:
            grafico.setTitle("Solape insuficiente para correlación móvil")
            return

        anios_centro = []
        rs_movil = []
        glks_movil = []
        tbps_movil = []

        for i in range(len(anios_overlap) - VENTANA + 1):
            anios_win = anios_overlap[i:i + VENTANA]
            a_win = a_arr[i:i + VENTANA]
            b_win = b_arr[i:i + VENTANA]
            if np.std(a_win) == 0 or np.std(b_win) == 0:
                continue
            # r sobre diferencias-log de la ventana (alta frecuencia)
            a_dl_win = a_dl.loc[a_dl.index.intersection(anios_win)]
            b_dl_win = b_dl.loc[b_dl.index.intersection(anios_win)]
            ov_dl = a_dl_win.index.intersection(b_dl_win.index)
            if len(ov_dl) < 3 or np.std(a_dl_win.loc[ov_dl]) == 0 \
                    or np.std(b_dl_win.loc[ov_dl]) == 0:
                continue
            r_win = float(np.corrcoef(
                a_dl_win.loc[ov_dl].to_numpy(),
                b_dl_win.loc[ov_dl].to_numpy())[0, 1])
            if not np.isfinite(r_win):
                continue

            # GLK y t-BP sobre crudo de la ventana
            a_ser = pd.Series(a_win, index=anios_win)
            b_ser = pd.Series(b_win, index=anios_win)
            glk_win, _ = gleichlaufigkeit(a_ser, b_ser, min_overlap=10)
            t_win, _, _ = t_baillie_pilcher(a_ser, b_ser, min_overlap=20)

            anios_centro.append(anios_win[VENTANA // 2])
            rs_movil.append(r_win)
            glks_movil.append(glk_win if np.isfinite(glk_win) else 0.0)
            # Normalizamos t-BP a escala [-1, 1] dividiendo por 10 para
            # graficarlo en el mismo eje (t-BP > 5 ya es alto)
            tbps_movil.append(min(1.0, max(-1.0, t_win / 10.0))
                              if np.isfinite(t_win) else 0.0)

        if not anios_centro:
            grafico.setTitle("No se pudo calcular correlación móvil")
            return

        grafico.setTitle(
            f"Correlación móvil (ventana {VENTANA} años, "
            f"desfase aplicado: {mejor_shift:+d})"
        )
        grafico.setLabel("bottom", "Año (centro de la ventana)")
        grafico.setLabel("left", "Valor del estadístico")
        grafico.setYRange(-1.05, 1.05)
        grafico.addLegend(offset=(10, 10))

        grafico.plot(anios_centro, rs_movil,
                     pen=pg.mkPen("#3388FF", width=2), name="r (Pearson)")
        grafico.plot(anios_centro, glks_movil,
                     pen=pg.mkPen("#fd7e14", width=2), name="GLK")
        grafico.plot(anios_centro, tbps_movil,
                     pen=pg.mkPen("#9b59b6", width=2), name="t-BP / 10")

        # Línea de referencia en y=0
        grafico.addItem(pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen("#888", width=1)))

    def copiar_portapapeles(self):
        ncols = self.tabla.columnCount()
        headers = [self.tabla.horizontalHeaderItem(c).text()
                   for c in range(ncols)]
        text = "\t".join(headers) + "\n"
        for row in range(self.tabla.rowCount()):
            text += "\t".join(
                (self.tabla.item(row, c).text()
                 if self.tabla.item(row, c) is not None else "")
                for c in range(ncols)) + "\n"
        QApplication.clipboard().setText(text)

    def exportar_csv(self):
        ruta_default = os.path.join(_ultima_carpeta(), "resultados_desfases.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar Datos", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        ncols = self.tabla.columnCount()
        headers = [self.tabla.horizontalHeaderItem(c).text()
                   for c in range(ncols)]
        try:
            with open(ruta, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in range(self.tabla.rowCount()):
                    writer.writerow([
                        (self.tabla.item(row, c).text()
                         if self.tabla.item(row, c) is not None else "")
                        for c in range(ncols)])
            QMessageBox.information(self, "Éxito", "Datos exportados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{e}")


# =============================================================================
# DIÁLOGO DE COMPARACIÓN MÚLTIPLE VS CRONOLOGÍA
# =============================================================================

class DialogoComparacionMultiple(QDialog):
    """Tabla resumen de comparación de N series vs cronología activa.

    Cada fila = una serie con su mejor desfase + score compuesto + los 3
    estadísticos (r, GLK, t-BP) en ese desfase. La tabla es ordenable
    (default: por score descendente).

    Interpretación rápida por el usuario:
      - Para una serie FECHADA, el mejor desfase debería ser 0 con Δ≈0.
        Si el mejor desfase es ≠ 0 y Δ alto → posible error de datación
        (anillo faltante o extra).
      - Para una serie FLOTANTE, el mejor desfase indica su POSICIÓN
        candidata respecto al inicio de la cronología.

    Interacciones:
      - Doble clic en fila → abre `VentanaTablaOffset` con TODOS los
        desfases de esa serie individualmente.
      - Botón "Exportar CSV" guarda el resumen completo.

    Las celdas se colorean con los mismos umbrales que `VentanaTablaOffset`
    (verde / amarillo verdoso / amarillo / rojo según rangos publicados
    de r, GLK y t-BP), para ser consecuentes con el resto del cofechado.
    """

    # Umbral de score por debajo del cual NO resaltamos filas con shift≠0
    # (resaltar correlaciones débiles solo agrega ruido visual)
    UMBRAL_SCORE_PARA_RESALTAR = 0.30

    def __init__(self, resultados: list[dict], nombre_crono: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"Comparación múltiple vs cronología '{nombre_crono}'")
        self.resize(900, 600)
        self._resultados_originales = resultados

        layout = QVBoxLayout(self)

        # ── Header informativo ────────────────────────────────────────
        info = QLabel(
            f"<b>{len(resultados)} series</b> comparadas vs cronología "
            f"<b>'{nombre_crono}'</b>. "
            f"Filas ordenadas por <b>puntaje compuesto</b> descendente.<br>"
            "<span style='color:#aaa; font-size:11px;'>"
            "🟡 Resaltado amarillo = mejor desfase ≠ 0 con puntaje "
            "significativo. Para series fechadas indica posible error de "
            "datación; para flotantes indica la posición candidata. "
            "⚠️ = la posición colocaría el último anillo en el futuro "
            "(datación imposible, probable correlación espuria). "
            "<b>Doble clic</b> en una fila para ver todos los desfases "
            "de esa serie. <i>Pasa el mouse sobre los encabezados para ver "
            "qué significa cada columna.</i>"
            "</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Tabla ─────────────────────────────────────────────────────
        # 9 columnas: Serie, n, Mejor desfase, Años (inicio–fin), Puntaje,
        # r, GLK, t-BP, Δ vs 0
        self.tabla = QTableWidget(len(resultados), 9)
        self.tabla.setHorizontalHeaderLabels([
            "Serie", "n", "Mejor desfase", "Año término", "Puntaje",
            "r", "GLK", "t-BP", "Δ vs desfase 0",
        ])
        # Tooltips explicativos en cada encabezado
        _tooltips_encabezado = {
            0: "Nombre de la serie comparada.",
            1: ("n = cantidad de años en común (solape) entre la serie y la "
                "cronología en el mejor desfase.\n\nMás solape = estadísticos "
                "más confiables. Con poco solape (n bajo) una correlación alta "
                "puede ser casualidad."),
            2: ("Desfase (en años) que produce la mejor correlación.\n\n"
                "• Serie fechada: debería ser 0. Si es ≠ 0, posible error de "
                "datación (anillo faltante o extra).\n"
                "• Serie flotante: indica los años que hay que sumar para "
                "posicionarla respecto a la cronología.\n\n"
                "⚠️ = la posición resultante supera el año actual (imposible)."),
            3: ("Año en que terminaría la serie SI se acepta el mejor desfase.\n\n"
                "Clave para validar: si la muestra tiene corteza, este año "
                "debería ser cercano al año de colecta. Un término muy antiguo "
                "es sospechoso si la madera no se preserva tanto tiempo en el "
                "sitio.\n\nSe marca en naranja si supera el año actual."),
            4: ("Puntaje compuesto: media geométrica de r, GLK y t-BP "
                "normalizados.\n\nEs el indicador más confiable de la fecha "
                "verdadera: solo es alto cuando los TRES estadísticos lo son "
                "simultáneamente. Si solo uno es alto, suele ser coincidencia."),
            5: "r de Pearson sobre las series transformadas.",
            6: "GLK (Gleichläufigkeit): % de años con cambios en la misma dirección.",
            7: "t-BP (t de Baillie-Pilcher): estadístico t de la correlación.",
            8: ("Δ vs desfase 0 = cuánto mejora el puntaje del mejor desfase "
                "respecto a quedarse en el desfase 0.\n\n"
                "• Serie fechada: cercano a 0 confirma que ya está bien datada.\n"
                "• Aparece '—' cuando el desfase 0 no se evaluó: típico en "
                "series flotantes, cuyo rango de búsqueda está lejos de 0 "
                "(la cronología y la serie no se solapan en su posición "
                "original, así que no existe un desfase 0 comparable)."),
        }
        for col, tip in _tooltips_encabezado.items():
            hdr_item = self.tabla.horizontalHeaderItem(col)
            if hdr_item is not None:
                hdr_item.setToolTip(tip)
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(False)
        self.tabla.setSortingEnabled(False)
        self.tabla.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        # Selección múltiple para poder aplicar el desfase a varias series
        # a la vez (Ctrl+clic / Shift+clic, o Ctrl+A para todas).
        self.tabla.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection)
        self.tabla.itemDoubleClicked.connect(self._abrir_detalle_serie)

        # Ordenar resultados por score descendente para el llenado inicial.
        # (después setSortingEnabled(True) permitirá reordenar por cualquier
        # columna haciendo clic en el header)
        resultados_ord = sorted(
            resultados,
            key=lambda r: r.get("mejor_score") if np.isfinite(
                r.get("mejor_score", float("nan"))) else -1e9,
            reverse=True,
        )

        # Guardar referencia ordenada para resolver el doble clic
        self._resultados_ordenados = resultados_ord

        for row, res in enumerate(resultados_ord):
            self._llenar_fila(row, res)

        # Activar sorting DESPUÉS de llenar (orden inicial preservado)
        self.tabla.setSortingEnabled(True)
        layout.addWidget(self.tabla)

        # ── Botones ───────────────────────────────────────────────────
        botonera = QHBoxLayout()

        btn_copiar = QPushButton("📋 Copiar todo")
        btn_copiar.clicked.connect(self._copiar_portapapeles)
        botonera.addWidget(btn_copiar)

        btn_exportar = QPushButton("💾 Exportar CSV")
        btn_exportar.clicked.connect(self._exportar_csv)
        botonera.addWidget(btn_exportar)

        # Botón "Ver detalle" como alternativa al doble clic (útil en
        # touchpads donde el doble clic a veces no se registra bien).
        btn_detalle = QPushButton("🔍 Ver detalle de fila")
        btn_detalle.setToolTip(
            "Abre los desfases detallados de la serie seleccionada "
            "(equivale al doble clic).")
        btn_detalle.clicked.connect(self._ver_detalle_seleccionada)
        botonera.addWidget(btn_detalle)

        # Botón para aplicar el desfase sugerido a las series y graficarlas
        # re-datadas en el panel principal. Solo se muestra si el padre es
        # el panel de cofechado (tiene las estructuras de series).
        _padre = self.parent()
        if (_padre is not None and hasattr(_padre, "series_datos")
                and hasattr(_padre, "graficar_series")):
            btn_aplicar = QPushButton("✅ Aplicar desfase y graficar")
            btn_aplicar.setStyleSheet(
                "QPushButton{background-color:#27ae60; color:white; "
                "font-weight:bold; padding:5px 12px; border-radius:4px;}"
                "QPushButton:hover{background-color:#2ecc71;}")
            btn_aplicar.setToolTip(
                "Aplica el mejor desfase a las series SELECCIONADAS: cambia "
                "su año de inicio a la posición sugerida y las grafica re-"
                "datadas en el panel principal.\n\n"
                "Selecciona las filas a aplicar (Ctrl+clic para varias, "
                "Ctrl+A para todas). Sin selección, pregunta si aplicar a "
                "todas.")
            btn_aplicar.clicked.connect(self._aplicar_desfases)
            botonera.addWidget(btn_aplicar)

        botonera.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        botonera.addWidget(btn_cerrar)
        layout.addLayout(botonera)

    # ── Construcción de filas ─────────────────────────────────────────

    def _llenar_fila(self, row: int, res: dict):
        """Llena una fila de la tabla con los datos de UNA serie.

        Aplica colores por umbral en cada estadístico y, si corresponde,
        resalta toda la fila en amarillo (mejor_shift ≠ 0 con score
        significativo).
        """
        nombre = res.get("nombre_serie", "?")
        mejor_shift = res.get("mejor_shift", 0)
        mejor_score = res.get("mejor_score", float("nan"))
        mejor_r = res.get("mejor_r", float("nan"))
        mejor_glk = res.get("mejor_glk", float("nan"))
        mejor_tbp = res.get("mejor_tbp", float("nan"))
        mejor_n = res.get("mejor_n", 0)
        score_shift0 = res.get("score_shift0", float("nan"))

        # Δ vs shift=0: cuánto mejor es el mejor shift comparado con quedarse
        # en 0. Para fechadas correctas debería ser ~0 (porque shift=0 ya es
        # el mejor). Para incorrectas o flotantes, será > 0.
        if np.isfinite(mejor_score) and np.isfinite(score_shift0):
            delta = mejor_score - score_shift0
        else:
            delta = float("nan")

        # ── Columna 0: Serie ──
        it = QTableWidgetItem(str(nombre))
        # Guardar referencia al resultado completo para resolver doble clic
        # incluso después de reordenar por otra columna.
        it.setData(Qt.ItemDataRole.UserRole, id(res))
        self.tabla.setItem(row, 0, it)

        # ── Columna 1: n ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole, int(mejor_n))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 1, it)

        # ── Columna 2: Mejor shift ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole, int(mejor_shift))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Resaltar visualmente si el shift es ≠ 0 con score significativo
        resaltar_fila = (
            mejor_shift != 0
            and np.isfinite(mejor_score)
            and mejor_score >= self.UMBRAL_SCORE_PARA_RESALTAR
        )
        if resaltar_fila:
            # Texto en negrita para llamar la atención sobre el shift
            f = it.font(); f.setBold(True); it.setFont(f)

        # Calcular la posición resultante (años de inicio y término) que
        # tendría la serie si se acepta el mejor desfase. Se usa tanto para
        # el aviso de año futuro como para la nueva columna "Años".
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        serie_a = res.get("serie_a")
        placed_min = placed_max = None
        if serie_a is not None and len(serie_a) > 0:
            try:
                placed_min = int(serie_a.index.min()) + int(mejor_shift)
                placed_max = int(serie_a.index.max()) + int(mejor_shift)
            except (ValueError, TypeError):
                placed_min = placed_max = None

        supera_presente = placed_max is not None and placed_max > anio_actual
        if supera_presente:
            it.setText(f"{int(mejor_shift)} ⚠️")
            it.setForeground(QColor("#e67e22"))
            f = it.font(); f.setBold(True); it.setFont(f)
            it.setToolTip(
                f"⚠️ Posición imposible: con este desfase la serie quedaría "
                f"en los años {placed_min}–{placed_max}, y el último año "
                f"({placed_max}) supera el año actual ({anio_actual}).\n\n"
                f"Esto suele indicar que la mejor correlación encontrada es "
                f"espuria (la serie no cofecha bien con esta cronología), o "
                f"que el rango de búsqueda permitió posiciones futuras.\n"
                f"Revisa el puntaje: si es bajo, probablemente no hay un "
                f"cofechado real con esta cronología."
            )
        self.tabla.setItem(row, 2, it)

        # ── Columna 3: Año término ──
        it = QTableWidgetItem()
        if placed_max is not None:
            # DisplayRole numérico para que ordene por año correctamente
            it.setData(Qt.ItemDataRole.DisplayRole, int(placed_max))
            it.setToolTip(
                f"Si se acepta el desfase {int(mejor_shift)}, la serie "
                f"abarcaría {placed_min}–{placed_max}.\n\n"
                f"Validación con corteza: si la muestra conserva corteza, este "
                f"año de término ({placed_max}) debería ser cercano al año de "
                f"colecta. Un término muy antiguo es sospechoso si la madera "
                f"no se preserva tanto tiempo en el sitio."
            )
            if supera_presente:
                it.setForeground(QColor("#e67e22"))
                f = it.font(); f.setBold(True); it.setFont(f)
        else:
            it.setText("—")
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 3, it)

        # ── Columna 4: Score compuesto ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_score, 3))
                    if np.isfinite(mejor_score) else 0.0)
        it.setBackground(QColor(_color_compuesto(mejor_score)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 4, it)

        # ── Columna 5: r ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_r, 3))
                    if np.isfinite(mejor_r) else 0.0)
        it.setBackground(QColor(_color_r(mejor_r)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 5, it)

        # ── Columna 6: GLK ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_glk, 3))
                    if np.isfinite(mejor_glk) else 0.0)
        it.setBackground(QColor(_color_glk(mejor_glk)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 6, it)

        # ── Columna 7: t-BP ──
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole,
                    float(round(mejor_tbp, 2))
                    if np.isfinite(mejor_tbp) else 0.0)
        it.setBackground(QColor(_color_tbp(mejor_tbp)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 7, it)

        # ── Columna 8: Δ vs shift=0 ──
        it = QTableWidgetItem()
        if np.isfinite(delta):
            it.setData(Qt.ItemDataRole.DisplayRole, float(round(delta, 3)))
        else:
            it.setData(Qt.ItemDataRole.DisplayRole, 0.0)
            it.setText("—")
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 8, it)

        # Resaltado de fila completa (solo color de fondo "sutil" en las
        # columnas que no tienen ya color por umbral: 0, 1, 2, 3, 8).
        # Usamos mostaza con texto casi negro (buen contraste en ambos temas).
        if resaltar_fila:
            color_fondo = QColor(218, 165, 32)        # mostaza (goldenrod)
            color_texto = QColor(20, 20, 20)          # casi negro
            for col in (0, 1, 2, 3, 8):
                cell = self.tabla.item(row, col)
                if cell is not None:
                    cell.setBackground(color_fondo)
                    cell.setForeground(color_texto)

    # ── Doble clic: drill-down ────────────────────────────────────────

    def _abrir_detalle_serie(self, item: QTableWidgetItem):
        """Doble clic en una fila → abre VentanaTablaOffset con todos los
        desfases de esa serie.

        Como las filas se pueden reordenar por cualquier columna usando
        el header, NO se puede usar `item.row()` para mapear al resultado
        original. En su lugar, guardamos el `id(res)` en UserRole de la
        columna 0 y buscamos el dict por identidad de objeto en
        `_resultados_originales`. Es a prueba de cualquier sort.
        """
        row = item.row()
        cell_nombre = self.tabla.item(row, 0)
        if cell_nombre is None:
            return
        id_buscado = cell_nombre.data(Qt.ItemDataRole.UserRole)
        if id_buscado is None:
            return
        res = next(
            (r for r in self._resultados_originales if id(r) == id_buscado),
            None,
        )
        if res is None:
            return

        dlg = VentanaTablaOffset(
            res["shifts"], res["rs"],
            glks=res["glks"], tbps=res["tbps"], ns=res["ns"],
            serie_a=res.get("serie_a"),
            serie_b=res.get("serie_b"),
            parent=self,
            # Para poder aplicar el desfase seleccionado desde el detalle:
            nombre_serie=res.get("nombre_serie"),
            panel_ref=self.parent() if hasattr(self.parent(), "series_datos") else None,
        )
        dlg.setWindowTitle(
            f"Desfases detallados — '{res.get('nombre_serie', '?')}' "
            f"vs cronología"
        )
        dlg.exec()

    def _ver_detalle_seleccionada(self):
        """Abre el detalle de la fila seleccionada (alternativa al doble
        clic, útil en touchpad)."""
        seleccion = self.tabla.selectionModel().selectedRows()
        if not seleccion:
            QMessageBox.information(
                self, "Sin selección",
                "Selecciona una fila primero para ver su detalle.")
            return
        row = seleccion[0].row()
        cell = self.tabla.item(row, 0)
        if cell is not None:
            self._abrir_detalle_serie(cell)

    def _resolver_res_de_fila(self, row: int) -> dict | None:
        """Devuelve el dict de resultado correspondiente a una fila de la
        tabla, resolviendo por id guardado en UserRole (a prueba de sort)."""
        cell = self.tabla.item(row, 0)
        if cell is None:
            return None
        id_buscado = cell.data(Qt.ItemDataRole.UserRole)
        return next(
            (r for r in self._resultados_originales if id(r) == id_buscado),
            None,
        )

    def _aplicar_desfases(self):
        """Aplica el mejor desfase a las series seleccionadas: re-data cada
        serie sumando su desfase al índice de años, actualiza las
        estructuras del panel principal y vuelve a graficar.

        Flujo:
          1. Determina las filas objetivo (seleccionadas; si no hay, ofrece
             aplicar a todas).
          2. Arma un resumen con el rango de años resultante por serie y
             marca las que quedarían en el futuro (datación imposible).
          3. Pide confirmación mostrando los cambios.
          4. Aplica: index += desfase en series_datos y series_originales.
          5. Invalida la caché de comparación y regrafica.
        """
        panel = self.parent()
        if panel is None or not hasattr(panel, "series_datos"):
            return

        # 1. Filas objetivo
        filas_sel = sorted({idx.row()
                            for idx in self.tabla.selectionModel().selectedRows()})
        if not filas_sel:
            resp = QMessageBox.question(
                self, "Sin selección",
                "No seleccionaste ninguna fila.\n\n"
                "¿Aplicar el desfase a TODAS las series de la tabla?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            filas_sel = list(range(self.tabla.rowCount()))

        # 2. Recolectar cambios
        import datetime as _dt
        anio_actual = _dt.datetime.now().year
        cambios = []          # (nombre, shift, nuevo_ini, nuevo_fin, futuro)
        for row in filas_sel:
            res = self._resolver_res_de_fila(row)
            if res is None:
                continue
            nombre = res.get("nombre_serie")
            shift = int(res.get("mejor_shift", 0))
            df = panel.series_datos.get(nombre)
            if df is None or df.empty:
                continue
            nuevo_ini = int(df.index.min()) + shift
            nuevo_fin = int(df.index.max()) + shift
            cambios.append((nombre, shift, nuevo_ini, nuevo_fin,
                            nuevo_fin > anio_actual))

        if not cambios:
            QMessageBox.information(
                self, "Sin cambios",
                "No se pudo resolver ninguna serie de las filas elegidas.")
            return

        # 3. Confirmación con resumen
        lineas = []
        hay_futuro = False
        for nombre, shift, ini, fin, futuro in cambios:
            marca = "  ⚠️ término en el futuro" if futuro else ""
            if futuro:
                hay_futuro = True
            signo = f"+{shift}" if shift >= 0 else str(shift)
            lineas.append(f"• {nombre}: desfase {signo} → años {ini}–{fin}{marca}")
        texto = (
            f"Se cambiará el año de inicio de {len(cambios)} serie(s) a la "
            f"posición sugerida:\n\n" + "\n".join(lineas)
        )
        if hay_futuro:
            texto += (
                "\n\n⚠️ Algunas series quedarían con año de término en el "
                "futuro (datación probablemente espuria). Revisa si de verdad "
                "quieres aplicarlas.")
        texto += "\n\n¿Continuar?"

        resp = QMessageBox.question(
            self, "Aplicar desfases", texto,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # 4. Aplicar usando el método reutilizable del panel
        for nombre, shift, _ini, _fin, _fut in cambios:
            panel.aplicar_desfase_a_serie(nombre, shift, regraficar=False)

        # 5. Regraficar una sola vez al final
        if hasattr(panel, "graficar_series"):
            panel.graficar_series()

        QMessageBox.information(
            self, "Listo",
            f"Se aplicó el desfase a {len(cambios)} serie(s) y se "
            f"regraficaron en el panel principal.")
        self.accept()

    # ── Exportación ───────────────────────────────────────────────────

    def _copiar_portapapeles(self):
        encabezado = ("Serie\tn\tMejor desfase\tAnio_termino\tPuntaje\t"
                      "r\tGLK\tt-BP\tDelta_vs_desfase_0\n")
        filas = []
        for row in range(self.tabla.rowCount()):
            cells = [self.tabla.item(row, c) for c in range(9)]
            filas.append("\t".join(
                c.text() if c is not None else "" for c in cells))
        QApplication.clipboard().setText(encabezado + "\n".join(filas))

    def _exportar_csv(self):
        ruta_default = os.path.join(
            _ultima_carpeta(), "comparacion_multiple.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar resumen", ruta_default, "CSV (*.csv)")
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Serie", "n", "Mejor desfase", "Anio_termino",
                    "Puntaje", "r", "GLK", "t-BP", "Delta_vs_desfase_0",
                ])
                for row in range(self.tabla.rowCount()):
                    cells = [self.tabla.item(row, c) for c in range(9)]
                    writer.writerow([
                        c.text() if c is not None else "" for c in cells])
            QMessageBox.information(self, "Éxito", "Resumen exportado.")
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                  f"No se pudo guardar:\n{e}")


# =============================================================================
# QSPINBOX CON FLECHAS UNICODE SIEMPRE VISIBLES
# =============================================================================

class SpinBoxFlechas(QSpinBox):
    """QSpinBox usando las flechas nativas del sistema.

    Históricamente esta clase reemplazaba las flechas del sistema con
    QToolButton custom dibujando caracteres Unicode (▲/▼), porque con
    un stylesheet global pesado las flechas nativas quedaban invisibles.
    Eso ya no aplica: con el stylesheet limpio actual (estilos.py), las
    flechas nativas se renderizan correctamente en ambos temas.

    Se mantiene la clase (en vez de usar QSpinBox directamente) para que
    sea drop-in replacement sin tocar 8 sitios, y por si en el futuro
    queremos volver a personalizar.
    """
    pass


# =============================================================================
# WIDGET DE SECCIÓN COLAPSABLE (ACCORDION)
# =============================================================================

class SeccionColapsable(QWidget):
    """Sección colapsable estilo accordion.

    Click en el header para expandir/contraer. Permite que múltiples secciones
    estén abiertas a la vez. Cuando todas están abiertas y exceden el alto
    disponible, el QScrollArea padre activa el scroll vertical.

    Estilo: usa overlays translúcidos rgba(0,0,0,XX) para que funcione tanto
    en tema oscuro como claro, igual que el patrón del módulo de medición.
    """

    def __init__(self, titulo: str, expandida: bool = True, parent=None):
        super().__init__(parent)
        self._titulo = titulo
        self._expandida = expandida

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 7px 10px;
                background-color: rgba(0, 0, 0, 50);
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgba(255, 140, 0, 60);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 80);
            }
        """)
        self.btn_toggle.clicked.connect(self.toggle)
        layout.addWidget(self.btn_toggle)

        # Contenedor sin background propio. La indentación visual viene de
        # los márgenes internos, no de un color de fondo (que rompería el
        # tema claro).
        self._contenido = QWidget()
        self._contenido_layout = QVBoxLayout(self._contenido)
        self._contenido_layout.setContentsMargins(10, 6, 4, 6)
        self._contenido_layout.setSpacing(4)
        layout.addWidget(self._contenido)

        self._actualizar()

    def _actualizar(self):
        flecha = "▼" if self._expandida else "▶"
        self.btn_toggle.setText(f"  {flecha}  {self._titulo}")
        self._contenido.setVisible(self._expandida)

    def toggle(self):
        self._expandida = not self._expandida
        self._actualizar()

    def expandir(self):
        if not self._expandida:
            self.toggle()

    def contraer(self):
        if self._expandida:
            self.toggle()

    def agregar_widget(self, widget):
        self._contenido_layout.addWidget(widget)

    def agregar_layout(self, layout):
        self._contenido_layout.addLayout(layout)


# =============================================================================
# PANEL DE CO-DATACIÓN
# =============================================================================

class VentanaSkeletonPlot(QWidget):
    """Pestaña de cofechado visual tipo skeleton plot.

    Muestra la serie de REFERENCIA arriba y la serie a cofechar abajo
    (espejada), como en el método clásico de Stokes & Smiley. La serie
    flotante se desliza año a año para encontrar dónde calzan los anillos
    angostos (años marcadores). Tres vistas:

      • Skeleton: marca solo los anillos angostos respecto a sus vecinos.
      • Barras de ancho: altura ∝ ancho de cada anillo (normalizado 0–1).
      • Líneas: cada serie como una curva (a veces es más fácil de mirar).

    Tiene su PROPIO almacenamiento de series y un selector de referencia y
    flotante. Puede importar las series del panel de Co-Datación (y enviarle
    las suyas) para mantener el flujo entre ambas pestañas. Al deslizar se
    actualizan en vivo r, GLK, t-BP, n y el puntaje; permite editar los
    anillos de la flotante (probando) y aplicarlos a la serie real.
    """

    def __init__(self, panel_cod, parent=None):
        super().__init__(parent)
        self._panel_cod = panel_cod
        self._series = {}  # nombre -> pd.Series (Ancho_mm), almacenamiento propio

        # Estado del par activo (referencia vs flotante)
        self._ref = pd.Series(dtype=float)
        self._flo = pd.Series(dtype=float)
        self._ref_nombre = ""
        self._flo_nombre = ""
        self._ref_nombre_full = ""
        self._flo_nombre_full = ""
        self._flo_original = pd.Series(dtype=float)
        self._modificado = False
        self._offset = 0
        self._off_min, self._off_max = -100, 100
        self._modo = "skeleton"  # "skeleton" | "barras" | "lineas"
        self._ventana_tabla = None
        self._mostrar_segmentos = True
        self._mostrar_marcas = True
        self._labels_overlay = []

        self._construir_ui()
        self._refrescar_selectores()

    def _serie_de_panel(self, nombre):
        df = self._panel_cod.series_datos.get(nombre) if self._panel_cod else None
        if df is None:
            return pd.Series(dtype=float)
        return pd.to_numeric(df["Ancho_mm"], errors="coerce").dropna()

    # ── gestión de series propias y flujo con Co-Datación ─────────────────
    def _cargar_archivos(self):
        """Carga series desde archivos directamente en el skeleton,
        detectando el formato (reutiliza los mismos lectores que
        Co-Datación)."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Series", _ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.wid *.csv *.tsv *.xlsx *.xls *.ods "
            "*.cat *.cmp);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not rutas:
            return
        _ultima_carpeta(rutas[0])

        n_agregadas = 0
        n_duplicadas = 0
        errores = []
        for ruta in rutas:
            ext = os.path.splitext(ruta)[1].lower()
            base_nombre = os.path.splitext(os.path.basename(ruta))[0]
            try:
                with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                    primeras = f.read(500)

                if "=N" in primeras and "=I" in primeras:
                    series_extraidas = leer_formato_compacto(ruta)
                elif ext == ".wid":
                    df, sid = leer_wid(ruta)
                    series_extraidas = {f"🌲{sid}": df}
                elif ext in (".rwl", ".txt"):
                    primera_real = ""
                    try:
                        with open(ruta, "r", encoding="utf-8",
                                  errors="replace") as f:
                            for linea in f:
                                ln = linea.rstrip("\r\n")
                                if not ln or ln.startswith("#"):
                                    continue
                                primera_real = ln
                                break
                    except Exception:
                        primera_real = ""
                    if "\t" in primera_real:
                        series_extraidas = self._leer_tabular_via_panel(
                            ruta, base_nombre)
                    else:
                        try:
                            series_extraidas = leer_tucson_multi(ruta)
                        except Exception:
                            series_extraidas = self._leer_tabular_via_panel(
                                ruta, base_nombre)
                elif ext in (".csv", ".tsv") or _es_planilla(ext):
                    series_extraidas = self._leer_tabular_via_panel(
                        ruta, base_nombre)
                else:
                    df, sid = leer_tabular(ruta)
                    series_extraidas = {sid: df}

                for id_serie, df_serie in series_extraidas.items():
                    if id_serie in self._series:
                        n_duplicadas += 1
                        continue
                    s = pd.to_numeric(
                        df_serie["Ancho_mm"], errors="coerce").dropna()
                    if s.empty:
                        continue
                    self._series[id_serie] = s
                    n_agregadas += 1
            except (ValueError, OSError) as exc:
                errores.append(f"{os.path.basename(ruta)}: {exc}")
                continue

        self._refrescar_selectores()
        if n_agregadas == 0 and not errores:
            QMessageBox.information(
                self, "Sin novedades",
                "No se agregaron series nuevas (ya estaban cargadas).")
        elif errores:
            msg = f"Se agregaron {n_agregadas} serie(s)."
            if n_duplicadas:
                msg += f"\n{n_duplicadas} duplicada(s) omitida(s)."
            msg += "\n\nErrores:\n" + "\n".join(errores)
            QMessageBox.warning(self, "Carga con errores", msg)

    def _leer_tabular_via_panel(self, ruta, base_nombre):
        """Reutiliza el lector tabular/columnas del panel de Co-Datación; si
        no está disponible, cae a leer_tabular."""
        if (self._panel_cod is not None
                and hasattr(self._panel_cod, "_leer_como_columnas_o_tabular")):
            return self._panel_cod._leer_como_columnas_o_tabular(
                ruta, base_nombre)
        df, sid = leer_tabular(ruta)
        return {sid: df}

    def importar_de_codatacion(self):
        """Copia todas las series del panel de Co-Datación al almacenamiento
        propio del skeleton."""
        if self._panel_cod is None:
            return
        n = 0
        for nombre, df in self._panel_cod.series_datos.items():
            try:
                s = pd.to_numeric(df["Ancho_mm"], errors="coerce").dropna()
            except Exception:
                continue
            if not s.empty:
                self._series[nombre] = s
                n += 1
        self._refrescar_selectores()
        if n == 0:
            QMessageBox.information(
                self, "Importar",
                "No hay series en Co-Datación para importar. Carga series "
                "en esa pestaña primero.")

    def preseleccionar_par(self, ref_nombre=None, flo_nombre=None):
        """Importa las series de Co-Datación y, si se indican, fija el par
        referencia/flotante. Lo usa el botón 'Skeleton' de Co-Datación."""
        self.importar_de_codatacion()
        if ref_nombre and ref_nombre in self._series:
            i = self.combo_ref.findData(ref_nombre)
            if i >= 0:
                self.combo_ref.blockSignals(True)
                self.combo_ref.setCurrentIndex(i)
                self.combo_ref.blockSignals(False)
        if flo_nombre and flo_nombre in self._series:
            i = self.combo_flo.findData(flo_nombre)
            if i >= 0:
                self.combo_flo.blockSignals(True)
                self.combo_flo.setCurrentIndex(i)
                self.combo_flo.blockSignals(False)
        self._aplicar_par_desde_combos(auto_rango=True)

    def _enviar_a_codatacion(self):
        """Envía las series propias del skeleton al panel de Co-Datación."""
        if self._panel_cod is None or not self._series:
            return
        enviadas = 0
        for nombre, s in self._series.items():
            df = pd.DataFrame({"Ancho_mm": s.values},
                              index=pd.Index(s.index, name="Anio"))
            try:
                if (hasattr(self._panel_cod, "agregar_serie_externa")):
                    self._panel_cod.agregar_serie_externa(nombre, df)
                else:
                    self._panel_cod.series_datos[nombre] = df
                    if hasattr(self._panel_cod, "series_originales"):
                        self._panel_cod.series_originales[nombre] = df.copy()
                enviadas += 1
            except Exception:
                pass
        if hasattr(self._panel_cod, "actualizar_lista_series"):
            try:
                self._panel_cod.actualizar_lista_series()
            except Exception:
                pass
        QMessageBox.information(
            self, "Enviar a Co-Datación",
            f"Se enviaron {enviadas} series a Co-Datación.")

    def _refrescar_selectores(self):
        """Rellena los combos de referencia y flotante con las series propias,
        conservando la selección actual si es posible."""
        nombres = sorted(self._series.keys(),
                         key=lambda s: (not s.startswith("📚"), s))
        ref_prev = self.combo_ref.currentData()
        flo_prev = self.combo_flo.currentData()
        for combo in (self.combo_ref, self.combo_flo):
            combo.blockSignals(True)
            combo.clear()
            for nombre in nombres:
                etiqueta = nombre.replace("📚 ", "📚 ")
                combo.addItem(etiqueta, nombre)
            combo.blockSignals(False)
        self.lbl_num_series.setText(f"{len(nombres)} series")
        if not nombres:
            self._ref = pd.Series(dtype=float)
            self._flo = pd.Series(dtype=float)
            self._redibujar(auto_rango=True)
            self._actualizar_stats()
            return
        # Restaurar o elegir por defecto: 📚 (o primera) = ref; otra = flo
        if ref_prev in self._series:
            self.combo_ref.setCurrentIndex(self.combo_ref.findData(ref_prev))
        else:
            self.combo_ref.setCurrentIndex(0)
        idx_flo = 1 if len(nombres) > 1 else 0
        if flo_prev in self._series and flo_prev != self.combo_ref.currentData():
            self.combo_flo.setCurrentIndex(self.combo_flo.findData(flo_prev))
        else:
            self.combo_flo.setCurrentIndex(idx_flo)
        self._aplicar_par_desde_combos(auto_rango=True)

    def _aplicar_par_desde_combos(self, auto_rango=True):
        ref_nombre = self.combo_ref.currentData()
        flo_nombre = self.combo_flo.currentData()
        if not ref_nombre or not flo_nombre:
            return
        if ref_nombre == flo_nombre:
            # Evitar comparar una serie consigo misma si hay alternativa
            for i in range(self.combo_flo.count()):
                if self.combo_flo.itemData(i) != ref_nombre:
                    self.combo_flo.blockSignals(True)
                    self.combo_flo.setCurrentIndex(i)
                    self.combo_flo.blockSignals(False)
                    flo_nombre = self.combo_flo.currentData()
                    break
        self._set_par(ref_nombre, flo_nombre, auto_rango=auto_rango)

    def _set_par(self, ref_nombre, flo_nombre, auto_rango=True):
        """Fija el par activo (referencia, flotante), recalcula el rango de
        desfase y redibuja."""
        self._ref_nombre_full = ref_nombre
        self._flo_nombre_full = flo_nombre
        self._ref_nombre = ref_nombre.replace("📚 ", "")
        self._flo_nombre = flo_nombre.replace("📚 ", "")
        self._ref = self._series.get(ref_nombre, pd.Series(dtype=float))
        self._flo = self._series.get(flo_nombre, pd.Series(dtype=float)).copy()
        self._flo_original = self._flo.copy()
        self._marcar_modificado(False)
        # Rango de desfase basado en los años
        if not self._ref.empty and not self._flo.empty:
            ref_min, ref_max = int(self._ref.index.min()), int(self._ref.index.max())
            flo_min, flo_max = int(self._flo.index.min()), int(self._flo.index.max())
            self._off_min = ref_min - flo_max - 20
            self._off_max = ref_max - flo_min + 20
        else:
            self._off_min, self._off_max = -100, 100
        self._offset = 0
        for w in (self.spin_offset, self.slider):
            w.blockSignals(True)
            w.setRange(self._off_min, self._off_max)
            w.setValue(0)
            w.blockSignals(False)
        self._redibujar(auto_rango=auto_rango)
        self._actualizar_stats()

    def _on_ref_changed(self, _idx):
        self._aplicar_par_desde_combos(auto_rango=True)

    def _on_flo_changed(self, _idx):
        self._aplicar_par_desde_combos(auto_rango=True)

    # ── construcción de UI ────────────────────────────────────────────────
    def _construir_ui(self):
        layout = QVBoxLayout(self)

        # ── Fila de gestión de series (flujo con Co-Datación) ──
        fila_series = QHBoxLayout()
        btn_importar = QPushButton("📥 Importar de Co-Datación")
        btn_importar.setToolTip(
            "Trae al skeleton todas las series cargadas en la pestaña "
            "Co-Datación.")
        btn_importar.clicked.connect(self.importar_de_codatacion)
        fila_series.addWidget(btn_importar)

        btn_cargar = QPushButton("📂 Cargar archivo")
        btn_cargar.setToolTip(
            "Carga series desde archivos (.rwl, .txt, .csv, .xlsx, .ods, .wid…)\n"
            "directamente en el skeleton, detectando el formato.")
        btn_cargar.clicked.connect(self._cargar_archivos)
        fila_series.addWidget(btn_cargar)

        btn_enviar = QPushButton("📤 Enviar a Co-Datación")
        btn_enviar.setToolTip(
            "Envía las series del skeleton a la pestaña Co-Datación.")
        btn_enviar.clicked.connect(self._enviar_a_codatacion)
        fila_series.addWidget(btn_enviar)

        self.lbl_num_series = QLabel("0 series")
        self.lbl_num_series.setStyleSheet("color:#888;")
        fila_series.addWidget(self.lbl_num_series)
        fila_series.addStretch()
        layout.addLayout(fila_series)

        # ── Fila de selección de par y vista ──
        controles = QHBoxLayout()
        controles.addWidget(QLabel("<b>Referencia:</b>"))
        self.combo_ref = QComboBox()
        self.combo_ref.setMinimumWidth(140)
        self.combo_ref.currentIndexChanged.connect(self._on_ref_changed)
        controles.addWidget(self.combo_ref)

        controles.addWidget(QLabel("<b>Flotante:</b>"))
        self.combo_flo = QComboBox()
        self.combo_flo.setMinimumWidth(140)
        self.combo_flo.currentIndexChanged.connect(self._on_flo_changed)
        controles.addWidget(self.combo_flo)

        controles.addWidget(QLabel("Vista:"))
        self.combo_modo = QComboBox()
        self.combo_modo.addItem("Skeleton (anillos angostos)", "skeleton")
        self.combo_modo.addItem("Barras de ancho", "barras")
        self.combo_modo.addItem("Líneas", "lineas")
        self.combo_modo.currentIndexChanged.connect(self._on_modo)
        controles.addWidget(self.combo_modo)

        controles.addWidget(QLabel("Desfase:"))
        self.spin_offset = QSpinBox()
        self.spin_offset.setRange(self._off_min, self._off_max)
        self.spin_offset.setValue(0)
        self.spin_offset.valueChanged.connect(self._on_offset_spin)
        controles.addWidget(self.spin_offset)

        self.btn_mejor = QPushButton("🔍 Mejor desfase")
        self.btn_mejor.setToolTip(
            "Busca el desfase con mayor puntaje compuesto (r·GLK·t-BP).")
        self.btn_mejor.clicked.connect(self._buscar_mejor_desfase)
        controles.addWidget(self.btn_mejor)

        self.btn_tabla_desf = QPushButton("📋 Tabla de desfases")
        self.btn_tabla_desf.setToolTip(
            "Abre una tabla ordenable con r, GLK, t-BP y puntaje de cada\n"
            "desfase. Doble clic en una fila salta a ese desfase.")
        self.btn_tabla_desf.clicked.connect(self._abrir_tabla_desfases)
        controles.addWidget(self.btn_tabla_desf)

        self.btn_editar_flo = QPushButton("✏️ Editar anillos (flotante)")
        self.btn_editar_flo.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold;")
        self.btn_editar_flo.setToolTip(
            "Agregar/quitar anillos de la serie flotante conservando el\n"
            "ancho total (para corregir anillos faltantes o falsos). Se\n"
            "prueba primero y luego se aplica a la serie real.")
        self.btn_editar_flo.clicked.connect(self._editar_flotante)
        controles.addWidget(self.btn_editar_flo)
        controles.addStretch()
        layout.addLayout(controles)

        # Slider de desplazamiento (deslizar la serie flotante)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(self._off_min, self._off_max)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_offset_slider)
        layout.addWidget(self.slider)

        # Etiqueta de estadísticos
        self.lbl_stats = QLabel("")
        self.lbl_stats.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stats.setStyleSheet(
            "QLabel{padding:6px 8px; background-color:rgba(0,0,0,40); "
            "border-radius:4px; font-family:monospace;}")
        layout.addWidget(self.lbl_stats)

        # Fila de controles de zoom/desplazamiento del gráfico
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Gráfico:"))

        self.btn_zoom_area = QPushButton("🔍 Zoom por área")
        self.btn_zoom_area.setCheckable(True)
        self.btn_zoom_area.setToolTip(
            "Activado: arrastra un rectángulo para hacer zoom en esa zona.\n"
            "Desactivado: arrastra para desplazar (pan). La rueda siempre "
            "hace zoom.")
        self.btn_zoom_area.toggled.connect(self._toggle_zoom_area)
        zoom_row.addWidget(self.btn_zoom_area)

        btn_ancho_mas = QPushButton("◄ ►")
        btn_ancho_mas.setMaximumWidth(48)
        btn_ancho_mas.setToolTip("Ensanchar: estira el eje de años (ver menos años, más detalle).")
        btn_ancho_mas.clicked.connect(lambda: self._zoom_x(0.7))
        zoom_row.addWidget(btn_ancho_mas)

        btn_ancho_menos = QPushButton("► ◄")
        btn_ancho_menos.setMaximumWidth(48)
        btn_ancho_menos.setToolTip("Comprimir: comprime el eje de años (ver más años).")
        btn_ancho_menos.clicked.connect(lambda: self._zoom_x(1.4))
        zoom_row.addWidget(btn_ancho_menos)

        btn_reset = QPushButton("⟲ Ver todo")
        btn_reset.setToolTip("Restablece la vista para ver ambas series completas.")
        btn_reset.clicked.connect(self._reset_zoom)
        zoom_row.addWidget(btn_reset)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        # Fila de simulación: toggles de superposiciones + aplicar/descartar
        sim_row = QHBoxLayout()
        self.chk_segmentos = QCheckBox("Correlación por segmentos de")
        self.chk_segmentos.setChecked(True)
        self.chk_segmentos.setToolTip(
            "Muestra el color de correlación por tramos sobre el gráfico\n"
            "(verde = correlaciona; rojo = falla), como en medición.")
        self.chk_segmentos.toggled.connect(self._on_toggle_segmentos)
        sim_row.addWidget(self.chk_segmentos)

        self.spin_segmento = QSpinBox()
        self.spin_segmento.setRange(5, 50)
        self.spin_segmento.setValue(10)
        self.spin_segmento.setSuffix(" años")
        self.spin_segmento.setToolTip("Largo de cada segmento de correlación.")
        self.spin_segmento.valueChanged.connect(
            lambda _: self._redibujar(auto_rango=False))
        sim_row.addWidget(self.spin_segmento)

        sim_row.addSpacing(10)
        sim_row.addWidget(QLabel("Correlación:"))
        # Mismo selector que en Medición: sin él, esta ventana calculaba
        # siempre con diferencias-log mientras el panel de Co-Datación usaba
        # el método de COFECHA, y las dos r del mismo par no coincidían.
        self.combo_metodo_corr = _tr.crear_selector(self, _tr.DIFFLOG)
        self.combo_metodo_corr.currentIndexChanged.connect(
            lambda *_: (self._actualizar_stats(), self._redibujar()))
        sim_row.addWidget(self.combo_metodo_corr)

        sim_row.addSpacing(12)
        self.chk_marcas = QCheckBox("Marcar faltante/sobrante")
        self.chk_marcas.setChecked(True)
        self.chk_marcas.setToolTip(
            "Marca dónde el alineamiento sugiere corregir anillos.")
        self.chk_marcas.toggled.connect(self._on_toggle_marcas)
        sim_row.addWidget(self.chk_marcas)

        lbl_leyenda = QLabel(
            "<span style='color:#e74c3c;'>▮ falta (agregar)</span> "
            "<span style='color:#17a2b8;'>▮ sobra (quitar)</span>")
        lbl_leyenda.setTextFormat(Qt.TextFormat.RichText)
        lbl_leyenda.setStyleSheet("font-size:11px;")
        sim_row.addWidget(lbl_leyenda)

        sim_row.addStretch()

        self.lbl_modif = QLabel("")
        self.lbl_modif.setStyleSheet("color:#e67e22; font-weight:bold;")
        sim_row.addWidget(self.lbl_modif)

        self.btn_aplicar_real = QPushButton("✅ Aplicar a serie real")
        self.btn_aplicar_real.setStyleSheet(
            "background-color:#5cb85c; color:white; font-weight:bold;")
        self.btn_aplicar_real.setToolTip(
            "Guarda los cambios probados (anillos agregados/quitados) en la\n"
            "serie real del panel de co-datación.")
        self.btn_aplicar_real.setEnabled(False)
        self.btn_aplicar_real.clicked.connect(self._aplicar_a_serie_real)
        sim_row.addWidget(self.btn_aplicar_real)

        self.btn_descartar = QPushButton("↺ Descartar cambios")
        self.btn_descartar.setToolTip(
            "Revierte la serie flotante a como estaba, descartando las "
            "pruebas.")
        self.btn_descartar.setEnabled(False)
        self.btn_descartar.clicked.connect(self._descartar_cambios)
        sim_row.addWidget(self.btn_descartar)
        layout.addLayout(sim_row)

        # Gráfico: referencia arriba, flotante abajo (espejada)
        self.grafico = pg.PlotWidget()
        _agregar_hover_anio(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.setLabel("bottom", "Año")
        self.grafico.setLabel("left", "Índice (0–1, espejado)")
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))
        # Interacción: rueda hace zoom, arrastrar hace pan por defecto.
        self._viewbox = self.grafico.getViewBox()
        self._viewbox.setMouseEnabled(x=True, y=True)
        # Etiquetas de superposición (r por segmento, marcas): se guardan
        # para reubicarlas en el borde visible cuando cambia el zoom, de modo
        # que sigan viéndose. Cada entrada: (item, x, "top"|"bottom").
        self._labels_overlay = []
        self._viewbox.sigRangeChanged.connect(self._reposicionar_overlays)
        layout.addWidget(self.grafico, 1)

    # ── transformaciones ──────────────────────────────────────────────────
    def _normalizada(self, serie):
        """Ancho estandarizado al rango 0–1 (min–máx), para que ambas series
        —de distinta escala en mm— sean comparables y queden acotadas."""
        s = serie.astype(float)
        lo, hi = s.min(), s.max()
        if hi > lo:
            return (s - lo) / (hi - lo)
        return s * 0.0 + 0.5

    def metodo_correlacion(self) -> str:
        combo = getattr(self, "combo_metodo_corr", None)
        if combo is None:
            return _tr.DIFFLOG
        return combo.currentData() or _tr.DIFFLOG

    def _skeleton(self, serie):
        """Marca de anillos angostos: altura ∝ cuánto más angosto es el
        anillo respecto al promedio de sus vecinos (ventana 3). Solo valores
        positivos (angostos); los anchos quedan en ~0. Rango 0–1 (los
        anillos más angostos se acercan a 1)."""
        s = serie.astype(float)
        if len(s) < 3:
            return s * 0.0
        local = s.rolling(3, center=True, min_periods=1).mean()
        rel = (local - s) / local.replace(0, np.nan)
        rel = rel.clip(lower=0, upper=1).fillna(0.0)
        return rel

    # ── dibujo ────────────────────────────────────────────────────────────
    def _redibujar(self, auto_rango=False):
        self.grafico.clear()
        self._labels_overlay = []
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))

    # ── dibujo ────────────────────────────────────────────────────────────
    def _redibujar(self, auto_rango=False):
        self.grafico.clear()
        self._labels_overlay = []
        self.grafico.addLine(y=0, pen=pg.mkPen("#888888", width=1))

        # Sin par seleccionado: no hay nada que dibujar.
        if self._ref.empty or self._flo.empty:
            aviso = pg.TextItem(
                "Importa o selecciona una referencia y una flotante.",
                color="#888888", anchor=(0.5, 0.5))
            aviso.setPos(0, 0)
            self.grafico.addItem(aviso)
            if auto_rango:
                self.grafico.autoRange()
            return

        if self._modo == "skeleton":
            ref_h = self._skeleton(self._ref)
            flo_h = self._skeleton(self._flo)
        else:
            ref_h = self._normalizada(self._ref)
            flo_h = self._normalizada(self._flo)

        xr = ref_h.index.to_numpy(dtype=float)
        yr = ref_h.to_numpy(dtype=float)
        xf = flo_h.index.to_numpy(dtype=float) + self._offset

        if self._modo == "lineas":
            # Vista de líneas: referencia arriba, flotante abajo (espejada),
            # como curvas en vez de barras (a veces más fácil de mirar).
            yf = -flo_h.to_numpy(dtype=float)
            self.grafico.plot(xr, yr, pen=pg.mkPen("#3388FF", width=2))
            self.grafico.plot(xf, yf, pen=pg.mkPen("#FF8C00", width=2))
        else:
            # Referencia: barras hacia ARRIBA en sus años
            self.grafico.addItem(pg.BarGraphItem(
                x=xr, height=yr, width=0.8, brush="#3388FF", pen=None))
            # Flotante: barras hacia ABAJO, desplazadas por el offset
            yf = -flo_h.to_numpy(dtype=float)
            self.grafico.addItem(pg.BarGraphItem(
                x=xf, height=yf, width=0.8, brush="#FF8C00", pen=None))

        # Etiquetas arriba/abajo
        ti = pg.TextItem(self._ref_nombre, color="#3388FF", anchor=(0, 1))
        ti.setPos(xr.min() if len(xr) else 0, max(yr.max() if len(yr) else 1, 1))
        self.grafico.addItem(ti)
        tf = pg.TextItem(self._flo_nombre, color="#FF8C00", anchor=(0, 0))
        tf.setPos(xf.min() if len(xf) else 0, min(yf.min() if len(yf) else -1, -1))
        self.grafico.addItem(tf)

        # Superposiciones en vivo: correlación por segmentos y marcas de
        # anillos faltantes/sobrantes en el desfase actual.
        if self._mostrar_segmentos:
            self._dibujar_correlacion_segmentos()
        if self._mostrar_marcas:
            self._dibujar_marcas_correcciones()

        # Solo auto-ajustar la vista al inicio o al cambiar de modo/reset.
        # Al DESLIZAR el desfase NO se auto-ajusta, para que la serie
        # flotante se mueva dentro de la ventana con zoom que fijó el usuario
        # (que es justo lo que se necesita para cofechar deslizando).
        if auto_rango:
            self.grafico.autoRange()

    def _dibujar_correlacion_segmentos(self):
        """Dibuja el color de correlación por tramos sobre el gráfico (verde
        = correlaciona, rojo = falla), como en el módulo de medición. El
        largo del segmento lo fija el usuario (spin_segmento). Se recalcula
        en vivo. Las etiquetas r se guardan para reubicarlas al hacer zoom."""
        ref = self._ref
        flo = self._flo.copy()
        flo.index = flo.index + self._offset
        metodo = self.metodo_correlacion()
        la = _tr.transformar(ref, metodo)
        lb = _tr.transformar(flo, metodo)
        overlap = sorted(la.index.intersection(lb.index))
        if len(overlap) < 6:
            return
        paso = self.spin_segmento.value()

        def _rgba(r):
            if r >= 0.50: return (46, 204, 113, 45)
            if r >= 0.35: return (92, 184, 92, 45)
            if r >= 0.15: return (240, 173, 78, 45)
            return (217, 83, 79, 55)

        def _hex(r):
            if r >= 0.50: return "#2ecc71"
            if r >= 0.35: return "#5cb85c"
            if r >= 0.15: return "#f0ad4e"
            return "#d9534f"

        seg_ini = overlap[0]
        while seg_ini < overlap[-1]:
            seg_fin = seg_ini + paso
            seg = [y for y in overlap if seg_ini <= y < seg_fin]
            if len(seg) >= 4:
                a = la.loc[seg].to_numpy()
                b = lb.loc[seg].to_numpy()
                if np.std(a) > 1e-9 and np.std(b) > 1e-9:
                    r = float(np.corrcoef(a, b)[0, 1])
                    if np.isfinite(r):
                        reg = pg.LinearRegionItem(
                            values=[seg_ini, seg_fin], movable=False,
                            brush=pg.mkBrush(*_rgba(r)), pen=pg.mkPen(None))
                        reg.setZValue(-20)
                        self.grafico.addItem(reg)
                        # Etiqueta: r y el tramo de años (para saber el largo)
                        txt = pg.TextItem(
                            html=f"<span style='color:{_hex(r)}; font-size:8pt; "
                                 f"font-weight:bold; background:#000;'>&nbsp;"
                                 f"r={r:+.2f}<br>{int(seg[0])}–{int(seg[-1])}"
                                 f"&nbsp;</span>",
                            anchor=(0.5, 0.0))
                        cx = (seg_ini + seg_fin) / 2.0
                        txt.setZValue(50)
                        self.grafico.addItem(txt)
                        self._labels_overlay.append((txt, cx, "top"))
            seg_ini += paso
        self._reposicionar_overlays()

    def _dibujar_marcas_correcciones(self):
        """Dibuja líneas verticales donde el alineamiento óptimo sugiere que
        FALTA un anillo (rojo) o SOBRA uno (celeste), en el desfase actual.
        La etiqueta indica el año y cuántos anillos (delta)."""
        try:
            res = alineamiento_optimo_anillos(
                self._flo, self._ref, shift_base=self._offset,
                max_correcciones=10, penalizacion=3.0)
        except Exception:
            return
        if not res:
            return
        for c in res.get("correcciones", []):
            x = c.get("anio_calendario")
            if x is None:
                continue
            delta = int(c.get("delta", 1) or 1)
            if c.get("tipo") == "faltante":
                color = "#e74c3c"
                etiqueta = (f"falta {delta} anillo{'s' if delta > 1 else ''}"
                            f"<br>~{int(x)} (agregar)")
            else:
                color = "#17a2b8"
                etiqueta = (f"sobra {delta} anillo{'s' if delta > 1 else ''}"
                            f"<br>~{int(x)} (quitar)")
            linea = pg.InfiniteLine(
                pos=x, angle=90,
                pen=pg.mkPen(color, width=2, style=Qt.PenStyle.DashLine))
            linea.setZValue(40)
            self.grafico.addItem(linea)
            et = pg.TextItem(
                html=f"<span style='color:{color}; font-size:8pt; "
                     f"background:#000;'>&nbsp;{etiqueta}&nbsp;</span>",
                anchor=(0.5, 1.0))
            et.setZValue(51)
            self.grafico.addItem(et)
            self._labels_overlay.append((et, x, "bottom"))
        self._reposicionar_overlays()

    def _reposicionar_overlays(self):
        """Reubica las etiquetas de correlación (arriba) y de marcas (abajo)
        en el borde visible actual, para que sigan viéndose al hacer zoom o
        pan (las etiquetas están en coordenadas de datos y si no se reubican,
        salen de la vista)."""
        if not getattr(self, "_labels_overlay", None):
            return
        try:
            (y0, y1) = self._viewbox.viewRange()[1]
        except Exception:
            return
        margen = (y1 - y0) * 0.02
        for item, x, pos in self._labels_overlay:
            try:
                if pos == "top":
                    item.setPos(x, y1 - margen)
                else:
                    item.setPos(x, y0 + margen)
            except Exception:
                pass

    # ── estadísticos en el desfase actual ─────────────────────────────────
    def _stats_offset(self, offset):
        ref = self._ref
        flo = self._flo.copy()
        flo.index = flo.index + offset
        ov = ref.index.intersection(flo.index)
        n = len(ov)
        if n < 5:
            return None
        a = ref.loc[ov]
        b = flo.loc[ov]
        # r con el método elegido en el selector de la barra
        metodo = self.metodo_correlacion()
        la = _tr.transformar(a, metodo)
        lb = _tr.transformar(b, metodo)
        cidx = la.index.intersection(lb.index)
        if len(cidx) >= 5 and la.loc[cidx].std() > 0 and lb.loc[cidx].std() > 0:
            r = float(np.corrcoef(la.loc[cidx], lb.loc[cidx])[0, 1])
        else:
            r = float("nan")
        glk, _ = gleichlaufigkeit(a, b, min_overlap=5)
        t_bp, _, _ = t_baillie_pilcher(a, b, min_overlap=5)
        return r, glk, t_bp, n

    def _actualizar_stats(self):
        if self._ref.empty or self._flo.empty:
            self.lbl_stats.setText(
                "<span style='color:#888;'>Selecciona una referencia y una "
                "flotante para ver la correlación.</span>")
            return
        res = self._stats_offset(self._offset)
        if res is None:
            self.lbl_stats.setText(
                "<span style='color:#d9534f;'>Solape insuficiente en este "
                "desfase (mín. 5 años).</span>")
            return
        r, glk, t_bp, n = res
        sc = score_compuesto(r, glk, t_bp)
        sig = glk_significance(glk, n)

        def f(v, dec=2):
            return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

        self.lbl_stats.setText(
            f"<b>Desfase {self._offset:+d}</b> &nbsp;|&nbsp; "
            f"n={n} &nbsp;|&nbsp; "
            f"r=<b style='color:{_color_r(r)}'>{f(r)}</b> &nbsp;|&nbsp; "
            f"GLK={f(glk*100,0)}% ({sig}) &nbsp;|&nbsp; "
            f"t-BP=<b style='color:{_color_tbp(t_bp)}'>{f(t_bp,1)}</b> "
            f"&nbsp;|&nbsp; puntaje={f(sc)}")

    # ── eventos ───────────────────────────────────────────────────────────
    def _on_modo(self, _idx):
        self._modo = self.combo_modo.currentData()
        self._redibujar(auto_rango=True)

    def _on_offset_spin(self, val):
        self._offset = int(val)
        self.slider.blockSignals(True)
        self.slider.setValue(self._offset)
        self.slider.blockSignals(False)
        self._redibujar()
        self._actualizar_stats()

    def _on_offset_slider(self, val):
        self._offset = int(val)
        self.spin_offset.blockSignals(True)
        self.spin_offset.setValue(self._offset)
        self.spin_offset.blockSignals(False)
        self._redibujar()
        self._actualizar_stats()

    def _toggle_zoom_area(self, activo):
        """Activa el modo 'zoom por área' (arrastrar un rectángulo hace zoom)
        o vuelve al modo desplazamiento (arrastrar mueve el gráfico)."""
        modo = (pg.ViewBox.RectMode if activo else pg.ViewBox.PanMode)
        self._viewbox.setMouseMode(modo)

    def _zoom_x(self, factor):
        """Estira (factor<1) o comprime (factor>1) el eje de años alrededor
        del centro visible, sin tocar el eje vertical."""
        self._viewbox.scaleBy((factor, 1.0))

    def _reset_zoom(self):
        """Restablece la vista para ver ambas series completas."""
        self._redibujar(auto_rango=True)

    # ── edición de anillos (de prueba; se aplica a la real aparte) ────────
    def reemplazar_serie(self, nombre, df_nuevo, regraficar=True):
        """Recibe la serie editada desde DialogoEditarAnillos. La edición es
        DE PRUEBA: modifica solo la copia de trabajo del skeleton (para ver
        cómo queda la correlación) SIN tocar la serie real del panel. Los
        cambios se comprometen con 'Aplicar a serie real'."""
        serie = pd.to_numeric(df_nuevo["Ancho_mm"], errors="coerce").dropna()
        if nombre == self._flo_nombre_full:
            self._flo = serie
            self._marcar_modificado(True)
        elif nombre == self._ref_nombre_full:
            self._ref = serie
            self._marcar_modificado(True)
        self._redibujar(auto_rango=False)
        self._actualizar_stats()
        if self._ventana_tabla is not None and self._ventana_tabla.isVisible():
            self._poblar_tabla_desfases()

    def _marcar_modificado(self, v: bool):
        self._modificado = v
        self.btn_aplicar_real.setEnabled(v)
        self.btn_descartar.setEnabled(v)
        self.lbl_modif.setText("● Cambios sin aplicar" if v else "")

    def _aplicar_a_serie_real(self):
        """Compromete la copia de trabajo a la serie real: actualiza el
        almacenamiento propio del skeleton y, si la serie también existe en
        Co-Datación, la propaga allí."""
        df = pd.DataFrame({"Ancho_mm": self._flo.values},
                          index=pd.Index(self._flo.index, name="Anio"))
        # Almacenamiento propio del skeleton
        self._series[self._flo_nombre_full] = self._flo.copy()
        # Propagar a Co-Datación si esa serie existe allí
        propagado = ""
        if (self._panel_cod is not None
                and hasattr(self._panel_cod, "series_datos")
                and self._flo_nombre_full in self._panel_cod.series_datos
                and hasattr(self._panel_cod, "reemplazar_serie")):
            self._panel_cod.reemplazar_serie(
                self._flo_nombre_full, df, regraficar=True)
            propagado = " y en Co-Datación"
        self._flo_original = self._flo.copy()
        self._marcar_modificado(False)
        QMessageBox.information(
            self, "Aplicado",
            f"Los cambios se guardaron en la serie '{self._flo_nombre}'"
            f"{propagado}.")

    def _editar_flotante(self):
        """Abre el editor de anillos (con conservación de ancho) para la
        serie flotante."""
        if self._flo.empty:
            QMessageBox.information(
                self, "Editar anillos",
                "Primero selecciona una serie flotante.")
            return
        df = pd.DataFrame({"Ancho_mm": self._flo.values},
                          index=pd.Index(self._flo.index, name="Anio"))
        dlg = DialogoEditarAnillos(df, self._flo_nombre_full, self, parent=self)
        dlg.exec()

    def _descartar_cambios(self):
        """Revierte la copia de trabajo a la serie comprometida."""
        self._flo = self._flo_original.copy()
        self._marcar_modificado(False)
        self._redibujar(auto_rango=False)
        self._actualizar_stats()
        if self._ventana_tabla is not None and self._ventana_tabla.isVisible():
            self._poblar_tabla_desfases()

    def _on_toggle_segmentos(self, v):
        self._mostrar_segmentos = bool(v)
        self._redibujar(auto_rango=False)

    def _on_toggle_marcas(self, v):
        self._mostrar_marcas = bool(v)
        self._redibujar(auto_rango=False)

    # ── tabla de desfases (ventana modificable) ───────────────────────────
    def _abrir_tabla_desfases(self):
        if self._ventana_tabla is None:
            self._ventana_tabla = QDialog(self)
            self._ventana_tabla.setWindowTitle("Desfases — r, GLK, t-BP, puntaje")
            self._ventana_tabla.resize(560, 460)
            lay = QVBoxLayout(self._ventana_tabla)
            lay.addWidget(QLabel(
                "Doble clic en una fila para saltar a ese desfase. "
                "Clic en un encabezado para ordenar."))
            self._tabla_desf = QTableWidget(0, 6)
            self._tabla_desf.setHorizontalHeaderLabels(
                ["Desfase", "n", "r", "GLK", "t-BP", "Puntaje"])
            self._tabla_desf.setSortingEnabled(True)
            self._tabla_desf.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            self._tabla_desf.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            self._tabla_desf.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            self._tabla_desf.itemDoubleClicked.connect(
                self._on_doble_clic_tabla)
            lay.addWidget(self._tabla_desf)
        self._poblar_tabla_desfases()
        self._ventana_tabla.show()
        self._ventana_tabla.raise_()

    def _poblar_tabla_desfases(self):
        filas = []
        for off in range(self._off_min, self._off_max + 1):
            res = self._stats_offset(off)
            if res is None:
                continue
            r, glk, t_bp, n = res
            sc = score_compuesto(r, glk, t_bp)
            filas.append((off, n, r, glk, t_bp, sc))
        if not filas:
            return
        filas.sort(key=lambda f: (f[5] if np.isfinite(f[5]) else -np.inf),
                   reverse=True)

        t = self._tabla_desf
        t.setSortingEnabled(False)
        t.setRowCount(len(filas))
        for i, (off, n, r, glk, t_bp, sc) in enumerate(filas):
            vals = [off, n, round(r, 3), round(glk * 100, 1),
                    round(t_bp, 2), round(sc, 3)]
            for j, v in enumerate(vals):
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, v)
                if j == 0:
                    it.setData(Qt.ItemDataRole.UserRole, int(off))
                if j == 2:
                    it.setForeground(QColor(_color_r(r)))
                elif j == 4:
                    it.setForeground(QColor(_color_tbp(t_bp)))
                t.setItem(i, j, it)
        t.setSortingEnabled(True)

    def _on_doble_clic_tabla(self, item):
        fila = item.row()
        celda_off = self._tabla_desf.item(fila, 0)
        if celda_off is None:
            return
        off = celda_off.data(Qt.ItemDataRole.UserRole)
        if off is None:
            off = int(celda_off.text())
        self.spin_offset.setValue(int(off))  # dispara redibujo + stats

    def _buscar_mejor_desfase(self):
        lo, hi = self._off_min, self._off_max
        mejor_sc, mejor_off = -np.inf, 0
        for off in range(lo, hi + 1):
            res = self._stats_offset(off)
            if res is None:
                continue
            r, glk, t_bp, n = res
            sc = score_compuesto(r, glk, t_bp)
            if np.isfinite(sc) and sc > mejor_sc:
                mejor_sc, mejor_off = sc, off
        if np.isfinite(mejor_sc):
            self.spin_offset.setValue(mejor_off)  # dispara redibujo y stats
        else:
            QMessageBox.information(
                self, "Sin solape",
                "No se encontró ningún desfase con solape suficiente.")


class DialogoCurvasNegativas(QDialog):
    """Elección del método para las series cuya curva de ajuste cruza cero.

    Muestra, para cada serie problemática, la serie cruda con las curvas de
    TODOS los métodos superpuestas y su correlación con la maestra al lado.
    Así se elige viendo la consecuencia, que es de lo que se trata.

    Se elige UN método para todo el grupo, no uno por serie: el informe de la
    cronología tiene que poder decir «las N series con curva negativa se
    estandarizaron con X», y eso es lo que hace el resultado reproducible.
    """

    def __init__(self, series, problematicas, maestra, metodo_original,
                 parent=None, ventana_mm=None, rigidez=None):
        super().__init__(parent)
        self.setWindowTitle("Series con curva de ajuste negativa")
        self.resize(1000, 700)
        self._series = series
        self._problem = list(problematicas)
        self._maestra = maestra
        self._vent = ventana_mm
        self._rig = rigidez

        self._auto = elegir_metodo_para_grupo(
            series, self._problem, maestra,
            ventana_mm=ventana_mm, rigidez=rigidez)

        lay = QVBoxLayout(self)
        cab = QLabel(
            f"<b>{len(self._problem)} serie(s)</b> tienen una curva de ajuste "
            f"que cruza cero con el método <b>{metodo_original}</b>.<br>"
            "En esos años el índice no significa lo mismo que en el resto de "
            "la serie: DPI reemplaza la tendencia por la media, y el índice "
            "puede dispararse.<br>"
            "Elige con qué método estandarizar <i>solo estas series</i>. Las "
            "demás mantienen el método original.")
        cab.setWordWrap(True)
        lay.addWidget(cab)

        # Tabla comparativa de métodos sobre el grupo
        self.tabla = QTableWidget(len(self._auto["tabla"]), 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Método", "Cruza cero", "r mediana con la maestra",
             "Índice máximo", "Series"])
        for i, t in enumerate(self._auto["tabla"]):
            vals = [t["metodo"],
                    "sí" if t["cruces"] else "no",
                    "—" if not np.isfinite(t["r_mediana"]) else f"{t['r_mediana']:.3f}",
                    "—" if not np.isfinite(t["indice_max"]) else f"{t['indice_max']:.2f}",
                    str(t["n_series"])]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if not t["valido"]:
                    it.setForeground(QColor("#d9534f"))
                elif t["metodo"] == self._auto["metodo"]:
                    it.setForeground(QColor("#5cb85c"))
                self.tabla.setItem(i, j, it)
        self.tabla.resizeColumnsToContents()
        self.tabla.setMaximumHeight(190)
        lay.addWidget(self.tabla)

        nota = QLabel(
            "El criterio es la correlación con la maestra, no el índice "
            "máximo: un máximo cercano a 1 también se consigue cuando la "
            "curva se come toda la variabilidad, y la correlación distingue "
            "esos dos casos.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#999; font-size:11px;")
        lay.addWidget(nota)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Serie:"))
        self.combo_serie = QComboBox()
        self.combo_serie.addItems(self._problem)
        self.combo_serie.currentIndexChanged.connect(self._dibujar)
        fila.addWidget(self.combo_serie, 1)
        self.chk_por_serie = QCheckBox("Elegir por serie")
        self.chk_por_serie.setToolTip(
            "Sin marcar, se aplica UN método a todas las series con curva\n"
            "negativa, que es lo reproducible: el informe puede decir «las N\n"
            "series afectadas se estandarizaron con X».\n\n"
            "Marcado, cada serie lleva el suyo. Úsalo cuando las series\n"
            "problemáticas tengan historias de crecimiento muy distintas\n"
            "entre sí; el informe detallará el método de cada una.")
        self.chk_por_serie.toggled.connect(self._cambiar_modo)
        fila.addWidget(self.chk_por_serie)

        self.lbl_aplicar = QLabel("Aplicar a todas:")
        fila.addWidget(self.lbl_aplicar)
        self.combo_metodo = QComboBox()
        for t in self._auto["tabla"]:
            etq = t["metodo"] + ("" if t["valido"] else "  (cruza cero)")
            self.combo_metodo.addItem(etq, t["metodo"])
        if self._auto["metodo"]:
            i = self.combo_metodo.findData(self._auto["metodo"])
            if i >= 0:
                self.combo_metodo.setCurrentIndex(i)
        self.combo_metodo.currentIndexChanged.connect(self._on_metodo_grupo)
        fila.addWidget(self.combo_metodo, 1)
        lay.addLayout(fila)

        # Elección individual: parte con el método del grupo para todas, así
        # marcar la casilla no borra lo que ya se había decidido.
        inicial = self._auto["metodo"] or metodo_original
        self._por_serie = {n: inicial for n in self._problem}

        self.grafico = pg.PlotWidget(title="Serie cruda y curvas de ajuste")
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.setLabel("left", "Ancho (mm)")
        self.grafico.setLabel("bottom", "Año")
        _agregar_hover_anio(self.grafico)
        lay.addWidget(self.grafico, 1)

        self.lbl_detalle = QLabel("")
        self.lbl_detalle.setWordWrap(True)
        lay.addWidget(self.lbl_detalle)

        botones = QHBoxLayout()
        botones.addStretch()
        b_auto = QPushButton("Usar el que el programa recomienda")
        b_auto.clicked.connect(self._usar_auto)
        botones.addWidget(b_auto)
        b_ok = QPushButton("Aplicar")
        b_ok.setStyleSheet("background-color:#5cb85c; color:white; "
                           "font-weight:bold; padding:6px 14px;")
        b_ok.clicked.connect(self.accept)
        botones.addWidget(b_ok)
        b_no = QPushButton("Dejar el método original")
        b_no.clicked.connect(self.reject)
        botones.addWidget(b_no)
        lay.addLayout(botones)
        self._dibujar()

    def _cambiar_modo(self, marcado):
        self.lbl_aplicar.setText("Método de esta serie:" if marcado
                                 else "Aplicar a todas:")
        if not marcado:
            m = self.combo_metodo.currentData()
            self._por_serie = {n: m for n in self._problem}
        self._dibujar()

    def _on_metodo_grupo(self, *_):
        m = self.combo_metodo.currentData()
        if self.chk_por_serie.isChecked():
            self._por_serie[self.combo_serie.currentText()] = m
        else:
            self._por_serie = {n: m for n in self._problem}
        self._dibujar()

    def metodos_por_serie(self) -> dict:
        """Método elegido para cada serie problemática."""
        if self.chk_por_serie.isChecked():
            return dict(self._por_serie)
        m = self.combo_metodo.currentData()
        return {n: m for n in self._problem}

    def _usar_auto(self):
        if self._auto["metodo"]:
            i = self.combo_metodo.findData(self._auto["metodo"])
            if i >= 0:
                self.combo_metodo.setCurrentIndex(i)

    def metodo_elegido(self):
        return self.combo_metodo.currentData()

    def _dibujar(self):
        self.grafico.clear()
        nom = self.combo_serie.currentText()
        # En modo individual, el combo refleja lo elegido para ESTA serie
        if self.chk_por_serie.isChecked() and nom in self._por_serie:
            i = self.combo_metodo.findData(self._por_serie[nom])
            if i >= 0 and self.combo_metodo.currentIndex() != i:
                self.combo_metodo.blockSignals(True)
                self.combo_metodo.setCurrentIndex(i)
                self.combo_metodo.blockSignals(False)
        if not nom or nom not in self._series:
            return
        obj = self._series[nom]
        col = obj["Ancho_mm"] if isinstance(obj, pd.DataFrame) else obj
        col = pd.to_numeric(col, errors="coerce").dropna()
        x = col.index.to_numpy(np.int64)
        self.grafico.plot(x, col.to_numpy(dtype=float),
                          pen=pg.mkPen("#888888", width=1), name=nom)
        colores = {"spline": "#4aa3dc", "negexp": "#e0a030",
                   "linear": "#e04040", "media_movil": "#5cb85c",
                   "media": "#a06ad0"}
        elegido = (self._por_serie.get(nom) if self.chk_por_serie.isChecked()
                   else self.metodo_elegido())
        filas = []
        for m in METODOS_DETREND:
            try:
                t = _fit_trend(col.to_numpy(dtype=float), m,
                               ventana_mm=self._vent, rigidez=self._rig)
            except Exception:
                continue
            t = np.asarray(t, dtype=float)
            ancho = 3 if m == elegido else 1
            self.grafico.plot(
                x, t, pen=pg.mkPen(colores.get(m, "#ccc"), width=ancho),
                name=m + (" ←" if m == elegido else ""))
            d = diagnosticar_curva(col, m, self._vent, self._rig)
            idx = d["indice"]
            r = float("nan")
            com = idx.index.intersection(self._maestra.index)
            if len(com) >= 20:
                a = idx.loc[com].to_numpy(dtype=float)
                b = self._maestra.loc[com].to_numpy(dtype=float)
                if np.std(a) > 1e-12 and np.std(b) > 1e-12:
                    r = float(np.corrcoef(a, b)[0, 1])
            filas.append(
                f"<b>{m}</b>: cruza cero en {d['n_parches']} de {d['total']} "
                f"años · índice máx {d['indice_max']:.2f} · "
                f"r con la maestra {'—' if r != r else f'{r:.3f}'}")
        self.grafico.addLine(y=0, pen=pg.mkPen("#d9534f", width=1,
                                               style=Qt.PenStyle.DashLine))
        self.lbl_detalle.setText("<br>".join(filas))


class PanelCodatacion(QWidget):
    """Panel principal de co-datación visual."""

    def __init__(self, ventana_padre: QWidget):
        super().__init__()
        self._ventana_padre = ventana_padre

        self.series_originales: dict[str, pd.DataFrame] = {}
        self.series_datos: dict[str, pd.DataFrame] = {}

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

        # Estado de PRUEBA de corrección (patrón probar → confirmar → aplicar):
        # al probar una sugerencia, se aplica a series_datos de forma temporal
        # (con respaldo) sin tocar series_originales; se confirma para hacerlo
        # permanente o se descarta para revertir.
        self._prueba_activa: bool = False
        self._prueba_nombre: str = ""
        self._prueba_backup: pd.DataFrame | None = None
        self._prueba_sug: dict | None = None

        # Cronología activa
        self.cronologia_activa: pd.DataFrame | None = None
        self.meta_cronologia: dict | None = None
        self._ventana_cronologia = None
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
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)

        splitter_principal = QSplitter(Qt.Orientation.Horizontal)

        # ═══════════════════════════════════════════════════════════════
        # PANEL IZQUIERDO: Scroll area con secciones colapsables
        # ═══════════════════════════════════════════════════════════════
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(220)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        widget_izq = QWidget()
        # Guardamos referencia para poder ajustar su fondo según el tema
        # activo (el global de la app no estila QWidget genérico).
        self._widget_izq_panel = widget_izq
        panel_izq = QVBoxLayout(widget_izq)
        panel_izq.setContentsMargins(4, 4, 4, 4)
        panel_izq.setSpacing(6)

        # ── BLOQUE FIJO ARRIBA: Carga y gestión de series ──
        fila_carga = QHBoxLayout()
        self.btn_cargar_rwl = QPushButton("📂 Series")
        self.btn_cargar_rwl.setToolTip("Cargar series de medición")
        self.btn_cargar_rwl.clicked.connect(self.cargar_archivos_rwl)
        fila_carga.addWidget(self.btn_cargar_rwl)
        self.btn_cargar_crono = QPushButton("📚 Crono")
        self.btn_cargar_crono.setToolTip(
            "Cargar una cronología externa.\n"
            "Si el archivo trae varias series, se auto-genera la cronología.")
        self.btn_cargar_crono.setStyleSheet(
            "QPushButton{background-color:#6f42c1; color:white; font-weight:bold;}"
            "QPushButton:hover{background-color:#5a32a3;}")
        self.btn_cargar_crono.clicked.connect(self.cargar_cronologias_externas)
        fila_carga.addWidget(self.btn_cargar_crono)

        # Series solo para el contraste: no entran a la lista ni se cofechan.
        # Sirven cuando se tiene la cronología ya hecha y una sola serie por
        # cofechar, que es el caso donde el localizador se quedaba sin nulo.
        self.btn_series_nulo = QPushButton("📊 Referencia")
        self.btn_series_nulo.setToolTip(
            "Cargar series YA FECHADAS que sirvan solo de contraste.\n\n"
            "El localizador de quiebres decide si una corrección es real\n"
            "midiendo cuánto gana la misma búsqueda en series sin error.\n"
            "Con nueve o más, ese contraste pasa a ser el bueno.\n\n"
            "No aparecen en la lista ni se cofechan.\n"
            "Si ya cargaste series acá o construiste la cronología en su\n"
            "pestaña, esas se usan solas y este botón no hace falta.")
        self.btn_series_nulo.clicked.connect(self.cargar_series_referencia)
        fila_carga.addWidget(self.btn_series_nulo)
        panel_izq.addLayout(fila_carga)

        self.btn_toggle_sel = QPushButton("☑ Des / Seleccionar Todo")
        self.btn_toggle_sel.clicked.connect(self.toggle_seleccion)
        panel_izq.addWidget(self.btn_toggle_sel)

        panel_izq.addWidget(QLabel("Series en Memoria:"))
        self.lista_series = QListWidget()
        self.lista_series.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lista_series.setMinimumHeight(120)
        self.lista_series.itemChanged.connect(self.graficar_series)
        panel_izq.addWidget(self.lista_series)

        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.lista_series).activated.connect(self.eliminar_series)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.lista_series).activated.connect(self.eliminar_series)

        fila_btns = QHBoxLayout()
        btn_elim = QPushButton("🗑️ Eliminar")
        btn_elim.setStyleSheet("background-color: #d9534f; color: white;")
        btn_elim.clicked.connect(self.eliminar_series)
        fila_btns.addWidget(btn_elim)
        btn_anio = QPushButton("📅 Editar Año Base")
        btn_anio.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold;")
        btn_anio.clicked.connect(self.editar_anio_serie)
        fila_btns.addWidget(btn_anio)
        panel_izq.addLayout(fila_btns)

        btn_exp = QPushButton("💾 Exportar Seleccionada")
        btn_exp.clicked.connect(self.exportar_serie_codatada)
        panel_izq.addWidget(btn_exp)

        # Botón directo de comparación múltiple vs cronología activa.
        # Permite al usuario marcar varias series en la lista y compararlas
        # contra la cronología ya cargada sin tener que abrir la ventana
        # de cronología por separado. La cronología activa se mantiene
        # entre llamadas (en `_cronologia_para_comparacion`), así que
        # típicamente: cargo cronología una vez → comparo decenas de
        # series con dos clics.
        self.btn_multi_vs_crono = QPushButton("📊 Series múltiples vs Crono")
        self.btn_multi_vs_crono.setStyleSheet(
            "QPushButton{background-color:#8e44ad; color:white; "
            "font-weight:bold; padding:5px 10px; border-radius:4px;}"
            "QPushButton:hover{background-color:#9b59b6;}"
            "QPushButton:disabled{background-color:#555; color:#aaa;}"
        )
        self.btn_multi_vs_crono.setToolTip(
            "Comparar las series marcadas contra una cronología.\n"
            "• Si todavía no hay cronología cargada, se pedirá elegir un archivo .rwl\n"
            "• Si ya hay una cargada, se reutiliza automáticamente\n"
            "• Funciona con 1 o más series marcadas\n"
            "• Resultados en tabla resumen con r, GLK, t-BP y puntaje compuesto")
        self.btn_multi_vs_crono.clicked.connect(self.comparar_series_marcadas_vs_crono)
        panel_izq.addWidget(self.btn_multi_vs_crono)

        self.btn_skeleton = QPushButton("📊 Skeleton plot — cofechado visual")
        self.btn_skeleton.setStyleSheet(
            "QPushButton{background-color:#6f42c1; color:white; "
            "font-weight:bold; padding:8px; font-size:13px; border-radius:4px;}"
            "QPushButton:hover{background-color:#8250d6;}")
        self.btn_skeleton.setToolTip(
            "Cofechado visual: referencia arriba, serie flotante abajo,\n"
            "deslizable año a año para ver dónde calzan los anillos.\n\n"
            "Marca DOS series: la cronología (📚) o la primera será la\n"
            "referencia; la otra será la flotante.")
        self.btn_skeleton.clicked.connect(self.abrir_skeleton_plot)
        panel_izq.addWidget(self.btn_skeleton)

        # Botón para editar anillos (insertar/eliminar conservando el ancho)
        # de la serie marcada, accesible directamente desde el panel.
        self.btn_editar_anillos = QPushButton("✏️ Editar anillos de serie marcada")
        self.btn_editar_anillos.setStyleSheet(
            "QPushButton{background-color:#8e44ad; color:white; "
            "font-weight:bold; padding:5px 10px; border-radius:4px;}"
            "QPushButton:hover{background-color:#9b59b6;}"
            "QPushButton:disabled{background-color:#555; color:#aaa;}")
        self.btn_editar_anillos.setToolTip(
            "Abre el editor de anillos (insertar/eliminar conservando el "
            "ancho total) para la serie marcada con check.\n"
            "Marca exactamente UNA serie.")
        self.btn_editar_anillos.clicked.connect(self._abrir_editor_anillos_marcada)
        panel_izq.addWidget(self.btn_editar_anillos)

        # ── Modo COFECHA (control global del cofechado) ──
        # Va aquí, a nivel del panel (no dentro de una sección colapsable),
        # porque gobierna TODAS las correlaciones del módulo: con él el
        # usuario decide si las series/cronologías se estandarizan o se usan
        # tal cual. Por eso debe estar siempre visible, justo bajo el botón
        # de comparación múltiple.
        grp_cof = QGroupBox("Modo COFECHA")
        grp_cof.setStyleSheet(
            "QGroupBox{border:1px solid #555; border-radius:4px; "
            "margin-top:6px; padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin; left:8px; padding:0 3px;}"
        )
        layout_cof = QVBoxLayout(grp_cof)
        layout_cof.setSpacing(4)
        layout_cof.setContentsMargins(6, 4, 6, 6)

        self.btn_modo_cofecha = QPushButton("🎯 Activar Modo COFECHA")
        self.btn_modo_cofecha.setCheckable(True)
        self.btn_modo_cofecha.setStyleSheet(ESTILO_BTN_COFECHA)
        self.btn_modo_cofecha.setToolTip(
            "Activa transformaciones tipo COFECHA (spline + log + AR(1))\n"
            "con los parámetros configurados (botón ⚙ al lado para ajustar).\n"
            "Al activarlo, el gráfico muestra las series transformadas y\n"
            "todas las correlaciones usan esa estandarización."
        )
        self.btn_modo_cofecha.toggled.connect(self._on_modo_cofecha_toggled)

        self.btn_cof_config = QPushButton("⚙")
        self.btn_cof_config.setMaximumWidth(34)
        self.btn_cof_config.setToolTip(
            "Configurar parámetros del Modo COFECHA\n"
            "(rigidez del spline, log, AR(1), primeras diferencias)"
        )
        self.btn_cof_config.setStyleSheet(
            "QPushButton{padding:4px 8px; font-size:14px; font-weight:bold; "
            "border:2px solid #888; border-radius:4px; "
            "background:transparent;}"
            "QPushButton:hover{border-color:#FF8C00; color:#FF8C00;}"
        )
        self.btn_cof_config.clicked.connect(self._configurar_modo_cofecha)

        fila_cof_btn = QHBoxLayout()
        fila_cof_btn.addWidget(self.btn_modo_cofecha, 1)
        fila_cof_btn.addWidget(self.btn_cof_config)
        layout_cof.addLayout(fila_cof_btn)

        fila_aplicar = QHBoxLayout()
        lbl_aplicar = QLabel("Aplicar a:")
        lbl_aplicar.setStyleSheet("font-size:11px;")
        fila_aplicar.addWidget(lbl_aplicar)
        self.chk_cof_serie = QCheckBox("Serie")
        self.chk_cof_serie.setChecked(True)
        self.chk_cof_serie.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_cof_serie.setToolTip(
            "Estandariza la SERIE a datar con el mismo método de la\n"
            "cronología activa, para que ambas queden en el mismo espacio\n"
            "y la correlación sea válida.\n\n"
            "Desactívalo solo si subiste la serie YA estandarizada."
        )
        self.chk_cof_serie.toggled.connect(self._on_cofecha_aplicar_cambiado)
        fila_aplicar.addWidget(self.chk_cof_serie)
        self.chk_cof_crono = QCheckBox("Cronología")
        self.chk_cof_crono.setChecked(False)
        self.chk_cof_crono.setStyleSheet(ESTILO_CHK_COFECHA)
        self.chk_cof_crono.setToolTip(
            "Normalmente NO se activa: una cronología generada con el botón\n"
            "Crono (o exportada por DPI/ARSTAN) ya viene estandarizada, y\n"
            "volver a aplicarle spline + log + AR la daña y hace caer la\n"
            "correlación.\n\n"
            "Actívalo solo si la cronología cargada NO está estandarizada\n"
            "(por ejemplo, una cronología de anchos crudos en mm)."
        )
        self.chk_cof_crono.toggled.connect(self._on_cofecha_aplicar_cambiado)
        fila_aplicar.addWidget(self.chk_cof_crono)
        fila_aplicar.addStretch()
        # Esta fila DEBE agregarse al layout del grupo. Al retirar la casilla
        # de leave-one-out se perdió esta línea y las casillas quedaron
        # creadas pero fuera de todo layout, o sea invisibles.
        layout_cof.addLayout(fila_aplicar)
        panel_izq.addWidget(grp_cof)

        # ── SECCIÓN COLAPSABLE: Cronología ──
        # Todas las secciones inician COLAPSADAS para no abrumar al usuario
        # con un panel sobrecargado de botones al abrir el programa. El
        # usuario expande la sección que necesita en cada momento.
        # ── Sección "Cronología" ELIMINADA de esta pestaña ──
        # La generación y gestión de cronologías vive en su propia pestaña,
        # así que aquí no aporta. Se conservan estos dos widgets OCULTOS (no
        # se agregan a ningún layout) solo para que set_cronologia_activa
        # pueda seguir actualizando el indicador y el estado de EPS sin
        # romperse.
        self.lbl_info_crono = QLabel("", self)
        self.lbl_info_crono.setVisible(False)
        self.btn_eps_crono = QPushButton(self)
        self.btn_eps_crono.setVisible(False)
        self.btn_eps_crono.setEnabled(False)
        self.btn_eps_crono.clicked.connect(self._mostrar_eps_cronologia_activa)

        # ── SECCIÓN COLAPSABLE: Cofechado con año conocido ──
        sec_conocido = SeccionColapsable(
            "📊 Cofechado con Año Conocido", expandida=False)

        # Parámetros del motor (compactos lado a lado)
        fila_params = QHBoxLayout()
        fila_params.addWidget(QLabel("Ventana:"))
        self.spin_ventana = SpinBoxFlechas()
        self.spin_ventana.setRange(10, 200)
        self.spin_ventana.setValue(VENTANA_COFECHADO_DEFECTO)
        self.spin_ventana.setSingleStep(10)
        self.spin_ventana.setSuffix(" años")
        fila_params.addWidget(self.spin_ventana)
        fila_params.addWidget(QLabel("Máx corr:"))
        self.spin_max_corr = SpinBoxFlechas()
        self.spin_max_corr.setRange(1, 10)
        self.spin_max_corr.setValue(MAX_CORRECCION)
        fila_params.addWidget(self.spin_max_corr)
        sec_conocido.agregar_layout(fila_params)

        # Anclaje: qué extremo de la serie queda fijo al insertar/eliminar
        # un anillo. Para árboles vivos fechados desde la corteza (el caso
        # normal) debe quedar fija la CORTEZA: así, al insertar el anillo que
        # falta, la serie sigue terminando en el mismo año y se corrige todo
        # lo anterior. Con médula fija la serie se corría hacia el presente y
        # el buscador proponía años equivocados.
        fila_ancla = QHBoxLayout()
        fila_ancla.addWidget(QLabel("Anclar en:"))
        self.combo_anclaje = QComboBox()
        self.combo_anclaje.addItem("Corteza (último año fijo)", "corteza")
        self.combo_anclaje.addItem("Médula (primer año fijo)", "medula")
        self.combo_anclaje.setToolTip(
            "Qué extremo de la serie NO se mueve al insertar o eliminar un anillo.\n\n"
            "• Corteza: el último año queda fijo y se desplazan los años anteriores.\n"
            "  Es lo correcto en árboles vivos, donde el año del anillo externo se\n"
            "  conoce con certeza. Si falta un anillo en 2023, al insertarlo la serie\n"
            "  sigue terminando en 2024 y todo lo anterior retrocede un año.\n\n"
            "• Médula: el primer año queda fijo y se desplazan los posteriores.\n"
            "  Para series flotantes o fechadas desde la médula."
        )
        fila_ancla.addWidget(self.combo_anclaje, 1)
        sec_conocido.agregar_layout(fila_ancla)

        self.btn_ver_cofechado = QPushButton("📊 Ver Cofechado Actual")
        self.btn_ver_cofechado.setStyleSheet("background-color: #5bc0de; color: white;")
        self.btn_ver_cofechado.clicked.connect(self.verificar_datacion)
        sec_conocido.agregar_widget(self.btn_ver_cofechado)

        self.btn_buscar = QPushButton("🔎 Buscar Anillos Faltantes/Sobrantes")
        self.btn_buscar.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold;")
        self.btn_buscar.clicked.connect(self.buscar_errores)
        sec_conocido.agregar_widget(self.btn_buscar)

        panel_izq.addWidget(sec_conocido)

        # ── SECCIÓN COLAPSABLE: Cofechado serie flotante ──
        sec_flotante = SeccionColapsable(
            "🔍 Cofechado Serie Flotante", expandida=False)

        btn_off = QPushButton("🔍 Analizar Serie Flotante")
        btn_off.setStyleSheet("background-color: #5bc0de; color: white;")
        btn_off.clicked.connect(self.analizar_offset)
        sec_flotante.agregar_widget(btn_off)

        self.btn_ver_tabla_off = QPushButton("📊 Ver tabla de desfases")
        self.btn_ver_tabla_off.setEnabled(False)
        self.btn_ver_tabla_off.clicked.connect(self.mostrar_tabla_offset)
        sec_flotante.agregar_widget(self.btn_ver_tabla_off)

        # Métrica al final, label arriba y combo a todo el ancho
        lbl_met = QLabel("📐 Métrica del gráfico:")
        lbl_met.setStyleSheet("font-size: 11px; padding-top: 4px;")
        sec_flotante.agregar_widget(lbl_met)
        self.combo_metrica_offset = QComboBox()
        self.combo_metrica_offset.addItems([
            "🎯 Compuesto (las tres juntas)",
            "t-BP (Baillie-Pilcher)",
            "r (Pearson)",
            "GLK (Eckstein)",
        ])
        self.combo_metrica_offset.setToolTip(
            "Métrica del gráfico de barras de desfase.\n\n"
            "🎯 Compuesto: media geométrica de las tres métricas.\n"
            "    La fecha verdadera tiene puntaje alto SOLO cuando\n"
            "    las tres son altas simultáneamente.\n\n"
            "t-BP: pondera r por tamaño de muestra.\n"
            "r: engañoso solo — puede dar máximos azarosos.\n"
            "GLK: robusto pero menos sensible que t-BP."
        )
        self.combo_metrica_offset.currentTextChanged.connect(self._redibujar_offset)
        sec_flotante.agregar_widget(self.combo_metrica_offset)

        panel_izq.addWidget(sec_flotante)

        # ── SECCIÓN COLAPSABLE: Sugerencias ──
        self.sec_sug = SeccionColapsable("💡 Sugerencias", expandida=False)

        self.lbl_estado_sug = QLabel("")
        self.lbl_estado_sug.setWordWrap(True)
        self.lbl_estado_sug.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_estado_sug.setStyleSheet(
            "QLabel{font-size:10px; padding:4px 6px; "
            "background-color: rgba(0,0,0,30); border-radius:3px;}")
        self.lbl_estado_sug.setVisible(False)
        self.sec_sug.agregar_widget(self.lbl_estado_sug)

        self.tabla_sugerencias = QTableWidget(0, 5)
        # Selección de FILA COMPLETA, con un color que se ve por encima del
        # fondo con que se marcan las filas según su origen. Sin esto, al
        # moverse con las flechas no se distinguía dónde estaba el cursor.
        self.tabla_sugerencias.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_sugerencias.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_sugerencias.setStyleSheet(
            "QTableWidget::item:selected{background-color:#2d6ea8;"
            " color:#ffffff;}")
        self.tabla_sugerencias.setHorizontalHeaderLabels(
            ["Año", "Tipo", "r antes", "r tras", "Δr"])
        self.tabla_sugerencias.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla_sugerencias.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_sugerencias.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_sugerencias.itemSelectionChanged.connect(
            self._on_seleccion_sugerencia)
        self.tabla_sugerencias.setMaximumHeight(200)
        self.tabla_sugerencias.setMinimumHeight(120)
        self.sec_sug.agregar_widget(self.tabla_sugerencias)

        # Indicador de prueba en curso
        self.lbl_prueba = QLabel("")
        self.lbl_prueba.setWordWrap(True)
        self.lbl_prueba.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_prueba.setStyleSheet(
            "QLabel{font-size:11px; padding:4px 6px; color:#e67e22; "
            "font-weight:bold;}")
        self.lbl_prueba.setVisible(False)
        self.sec_sug.agregar_widget(self.lbl_prueba)

        # Paso 1: probar la corrección (sin tocar la serie real)
        self.btn_probar = QPushButton("🧪 Probar corrección seleccionada")
        self.btn_probar.setStyleSheet(
            "background-color:#5bc0de; color:white; font-weight:bold;")
        self.btn_probar.setToolTip(
            "Aplica la corrección de forma temporal para ver cómo queda la\n"
            "correlación, SIN modificar todavía la serie real.")
        self.btn_probar.setEnabled(False)
        self.btn_probar.clicked.connect(self.probar_correccion_seleccionada)
        self.sec_sug.agregar_widget(self.btn_probar)

        # Paso 2: aplicar a la serie real (con confirmación de qué cambia)
        self.btn_aplicar = QPushButton("✅ Aplicar a serie real")
        self.btn_aplicar.setStyleSheet(
            "background-color: #5cb85c; color: white; font-weight: bold;")
        self.btn_aplicar.setEnabled(False)
        self.btn_aplicar.setToolTip(
            "Confirma qué datos se modifican y guarda el cambio en la serie "
            "real.")
        self.btn_aplicar.clicked.connect(self.aplicar_correccion_seleccionada)
        self.sec_sug.agregar_widget(self.btn_aplicar)

        # Descartar la prueba (revierte a como estaba)
        self.btn_descartar_prueba = QPushButton("↺ Descartar prueba")
        self.btn_descartar_prueba.setStyleSheet(
            "QPushButton{background-color:#6c757d; color:white; padding:4px;}"
            "QPushButton:hover{background-color:#7d868e;}")
        self.btn_descartar_prueba.setEnabled(False)
        self.btn_descartar_prueba.clicked.connect(self._descartar_prueba)
        self.sec_sug.agregar_widget(self.btn_descartar_prueba)

        # Botón para restablecer la serie corregida a sus valores originales,
        # disponible aquí (no solo en el simulador manual).
        self.btn_restablecer_sug = QPushButton("🔄 Restablecer valores originales")
        self.btn_restablecer_sug.setStyleSheet(
            "QPushButton{background-color:#6c757d; color:white; "
            "padding:4px;}"
            "QPushButton:hover{background-color:#7d868e;}")
        self.btn_restablecer_sug.clicked.connect(self.restaurar_original_sugerencias)
        self.sec_sug.agregar_widget(self.btn_restablecer_sug)
        panel_izq.addWidget(self.sec_sug)

        # ── SECCIÓN COLAPSABLE: Simulador manual ──
        # Va al final porque se usa poco; las correcciones normales se hacen
        # desde Sugerencias (que abre el editor con conservación de ancho).
        sec_sim = SeccionColapsable("📝 Simulador Manual", expandida=False)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Año:"))
        self.spin_edit_year = SpinBoxFlechas()
        self.spin_edit_year.setRange(-10000, 5000)
        self.spin_edit_year.setValue(1900)
        fila.addWidget(self.spin_edit_year)
        sec_sim.agregar_layout(fila)

        fila2 = QHBoxLayout()
        btn_ins = QPushButton("➕ Insertar")
        btn_ins.setStyleSheet("background-color: #5bc0de; color: white;")
        btn_ins.clicked.connect(self.simular_insertar)
        fila2.addWidget(btn_ins)
        btn_del = QPushButton("➖ Borrar")
        btn_del.setStyleSheet("background-color: #d9534f; color: white;")
        btn_del.clicked.connect(self.simular_borrar)
        fila2.addWidget(btn_del)
        sec_sim.agregar_layout(fila2)
        btn_rst = QPushButton("🔄 Restaurar Original")
        btn_rst.clicked.connect(self.restaurar_serie)
        sec_sim.agregar_widget(btn_rst)
        panel_izq.addWidget(sec_sim)

        panel_izq.addStretch()
        scroll.setWidget(widget_izq)

        # ═══════════════════════════════════════════════════════════════
        # PANEL DERECHO: Gráficos
        # ═══════════════════════════════════════════════════════════════
        splitter_der = QSplitter(Qt.Orientation.Vertical)

        self.grafico = pg.PlotWidget(title="Series de Ancho de Anillo")
        _agregar_hover_anio(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.addLegend()
        _cont_grafico = QWidget()
        _lay_grafico = QVBoxLayout(_cont_grafico)
        _lay_grafico.setContentsMargins(0, 0, 0, 0)
        _lay_grafico.setSpacing(2)
        _lay_grafico.addWidget(self.grafico, 1)

        # Fila de controles del gráfico: zoom + selector de tipo de gráfico.
        _fila_ctrl_graf = QHBoxLayout()
        _fila_ctrl_graf.setContentsMargins(0, 0, 0, 0)
        _fila_ctrl_graf.setSpacing(6)
        _barra_sup = _crear_barra_zoom(self.grafico)
        _fila_ctrl_graf.addWidget(_barra_sup)

        # Modo barras: dibuja cada serie como barras que salen de su MEDIA
        # (hacia arriba si el año fue de crecimiento sobre la media, hacia
        # abajo si fue bajo la media). Es la vista clásica de desviaciones,
        # muy útil para ver años característicos y comparar con COFECHA.
        self.btn_grafico_barras = QPushButton("📊 Barras")
        self.btn_grafico_barras.setCheckable(True)
        self.btn_grafico_barras.setToolTip(
            "Alterna entre gráfico de LÍNEAS y gráfico de BARRAS.\n\n"
            "En modo barras, la MEDIA de cada serie es el eje central:\n"
            "las barras suben sobre la media (años buenos, verde) y bajan\n"
            "bajo la media (años malos, rojo). Con varias series marcadas,\n"
            "las barras se dibujan lado a lado por año."
        )
        self.btn_grafico_barras.toggled.connect(self.graficar_series)

        # El botón de barras va junto a «Ver todo», que es donde se
        # esperan los controles de ESTE gráfico. La fila que ocupaba antes
        # queda libre para los controles de los gráficos de abajo.
        _barra_sup.layout().insertWidget(
            _barra_sup.layout().count() - 1, self.btn_grafico_barras)
        _fila_ctrl_graf.addStretch()

        _cont_ctrl_graf = QWidget()
        _cont_ctrl_graf.setLayout(_fila_ctrl_graf)
        _lay_grafico.addWidget(_cont_ctrl_graf)
        splitter_der.addWidget(_cont_grafico)

        contenedor_offset = QWidget()
        layout_offset = QVBoxLayout(contenedor_offset)
        layout_offset.setContentsMargins(0, 0, 0, 0)
        layout_offset.setSpacing(2)

        self.grafico_offset = pg.PlotWidget(
            title="Correlación móvil (r) entre la serie y la referencia, por ventana")
        self.grafico_offset.showGrid(x=True, y=True, alpha=0.3)
        self.grafico_offset.setYRange(-1.05, 1.05)
        self.grafico_offset.setLabel("left", "r (correlación por ventana)")
        self.grafico_offset.setLabel("bottom", "Año (centro de la ventana)")
        self.grafico_offset.addLegend(offset=(10, 10))
        self._texto_hover = pg.TextItem(fill=(40, 40, 40, 220), color=(255, 255, 255))
        self._texto_hover.hide()
        self.grafico_offset.addItem(self._texto_hover)
        self.grafico_offset.scene().sigMouseMoved.connect(self._on_mouse_movido)
        _agregar_hover_anio(self.grafico_offset)
        layout_offset.addWidget(self.grafico_offset, 1)
        # Controles de zoom propios de ESTA pestaña: cada gráfico de abajo se
        # maneja por su cuenta, así se puede dejar uno encuadrado en un tramo
        # mientras se explora el otro.
        layout_offset.addWidget(_crear_barra_zoom(self.grafico_offset))

        self.lbl_stats = QLabel("")
        self.lbl_stats.setWordWrap(False)
        self.lbl_stats.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stats.setMinimumHeight(38)
        # Fondo oscuro fijo: este label es un overlay sobre el gráfico
        # de pyqtgraph (que es negro siempre), y el HTML interno usa
        # colores #888/#aaa/etc que requieren fondo oscuro para verse.
        self.lbl_stats.setStyleSheet(
            "QLabel{background-color:#1a1a1a; color:#e0e0e0; "
            "border:1px solid #444; border-radius:4px; padding:8px 12px;}"
        )
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignVCenter |
                                    Qt.AlignmentFlag.AlignLeft)
        self.lbl_stats.setToolTip(TOOLTIP_STATS)
        self.lbl_stats.setVisible(False)
        layout_offset.addWidget(self.lbl_stats)

        # ── Panel inferior con pestañas ────────────────────────────────
        # Antes este panel mostraba solo la correlación móvil. El informe de
        # co-datación y el perfil del quiebre se calculaban pero no se veían
        # en ninguna parte: la explicación en prosa y el gráfico que muestra
        # si el año está determinado o es una meseta quedaban dentro de la
        # estructura de datos, invisibles. Van acá, junto al gráfico que ya
        # había, para que el usuario alterne entre los tres sin perder nada.
        self.tabs_inferior = QTabWidget()
        self.tabs_inferior.addTab(contenedor_offset, "Correlación móvil")

        self.txt_informe = QPlainTextEdit()
        self.txt_informe.setReadOnly(True)
        self.txt_informe.setPlaceholderText(
            "Acá aparece el informe de co-datación cuando se busca una "
            "corrección:\n\n"
            "  · qué tramo de la serie correlaciona bien y con qué r\n"
            "  · dónde baja la correlación\n"
            "  · cuántos anillos faltan o sobran, y entre qué años\n"
            "  · los años concretos que conviene revisar bajo la lupa")
        self.txt_informe.setStyleSheet(
            "QPlainTextEdit{background-color:#1a1a1a; color:#e0e0e0;"
            " border:1px solid #444; padding:8px;}")
        f_inf = QFont("Consolas" if sys.platform.startswith("win")
                      else "Monospace")
        f_inf.setStyleHint(QFont.StyleHint.TypeWriter)
        f_inf.setPointSize(10)
        self.txt_informe.setFont(f_inf)

        # Controles de letra: no todo el mundo lee cómodo el mismo cuerpo, y
        # la monoespaciada alinea las tablas pero cansa en prosa larga.
        _cont_inf = QWidget()
        _lay_inf = QVBoxLayout(_cont_inf)
        _lay_inf.setContentsMargins(0, 0, 0, 0)
        _lay_inf.setSpacing(2)
        _lay_inf.addWidget(self.txt_informe, 1)

        _fila_letra = QHBoxLayout()
        _fila_letra.setContentsMargins(4, 0, 4, 0)
        _fila_letra.addWidget(QLabel("Letra:"))
        self.combo_fuente_informe = QComboBox()
        for etq, fam in (("Monoespaciada", "__mono__"),
                         ("Garamond", "Garamond"),
                         ("Arial", "Arial"),
                         ("Verdana", "Verdana"),
                         ("Georgia", "Georgia"),
                         ("Times New Roman", "Times New Roman")):
            self.combo_fuente_informe.addItem(etq, fam)
        self.combo_fuente_informe.setToolTip(
            "La monoespaciada mantiene alineadas las tablas del informe.\n"
            "Las demás se leen mejor en la prosa, pero descuadran columnas.")
        self.combo_fuente_informe.currentIndexChanged.connect(
            self._aplicar_fuente_informe)
        self.combo_fuente_informe.currentIndexChanged.connect(
            self._guardar_pref_fuente)
        _fila_letra.addWidget(self.combo_fuente_informe)

        _fila_letra.addWidget(QLabel("Tamaño:"))
        self.spin_fuente_informe = QSpinBox()
        self.spin_fuente_informe.setRange(7, 24)
        self.spin_fuente_informe.setValue(10)
        self.spin_fuente_informe.setSuffix(" pt")
        self.spin_fuente_informe.valueChanged.connect(
            self._aplicar_fuente_informe)
        self.spin_fuente_informe.valueChanged.connect(
            self._guardar_pref_fuente)
        _fila_letra.addWidget(self.spin_fuente_informe)

        btn_copiar_inf = QPushButton("Copiar")
        btn_copiar_inf.setToolTip("Copia el informe completo al portapapeles.")
        btn_copiar_inf.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.txt_informe.toPlainText()))
        _fila_letra.addWidget(btn_copiar_inf)
        _fila_letra.addStretch()

        _cw = QWidget()
        _cw.setLayout(_fila_letra)
        _lay_inf.addWidget(_cw)
        self.tabs_inferior.addTab(_cont_inf, "Informe")
        self._restaurar_pref_fuente()

        self.grafico_perfil = pg.PlotWidget(
            title="¿En qué año se rompe el fechado? "
                  "Correlación de la serie completa si el error estuviera "
                  "en cada año")
        self.grafico_perfil.showGrid(x=True, y=True, alpha=0.3)
        self.grafico_perfil.setLabel(
            "left", "r de TODA la serie si el error estuviera en ese año")
        self.grafico_perfil.setLabel(
            "bottom", "Año donde se probó poner el error")
        self.grafico_perfil.addLegend(offset=(10, 10))
        _agregar_hover_anio(self.grafico_perfil)
        _cont_perfil = QWidget()
        _lay_perfil = QVBoxLayout(_cont_perfil)
        _lay_perfil.setContentsMargins(0, 0, 0, 0)
        _lay_perfil.setSpacing(2)

        # Gráfico y explicación lado a lado, con divisor movible: el perfil no
        # se entiende solo mirándolo, y una leyenda no alcanza para explicar
        # que cada punto es un experimento distinto de datación.
        _div_perfil = QSplitter(Qt.Orientation.Horizontal)
        _div_perfil.addWidget(self.grafico_perfil)

        self.txt_ayuda_perfil = QTextBrowser()
        self.txt_ayuda_perfil.setOpenExternalLinks(False)
        self.txt_ayuda_perfil.setHtml(
            "<div style='font-size:12px; line-height:1.35;'>"
            "<b>Qué estás viendo</b><br>"
            "Cada punto del gráfico es un <i>experimento</i>: el programa "
            "supone que el error de fechado está en ese año, aplica la "
            "corrección, y mide cómo queda <b>la serie completa</b>.<br><br>"
            "No es la correlación de un tramo. Es la de toda la serie, "
            "partida en ese año.<br><br>"
            "<b>Cómo se lee la forma</b><br>"
            "<span style='color:#5cb85c;'>▲ Pico angosto</span> — un solo año "
            "funciona. El fechado está determinado.<br>"
            "<span style='color:#e0a030;'>▬ Meseta ancha</span> — muchos años "
            "funcionan igual de bien. Elegir uno sería falsa precisión: hay "
            "que revisar todos los candidatos.<br>"
            "<span style='color:#d9534f;'>▼ Todo bajo</span> — si el mejor "
            "pico no llega a 0,3, ninguna corrección arregla esta serie. El "
            "problema es otro.<br><br>"
            "<b>Los colores</b><br>"
            "<span style='color:#4aa3dc;'>━ Curva azul</span>: la correlación "
            "de cada hipótesis.<br>"
            "<span style='color:#4aa3dc;'>▨ Franja azul</span>: la zona "
            "compatible, los años que no se distinguen del mejor.<br>"
            "<span style='color:#e04040;'>┃ Línea roja</span>: el año más "
            "probable.<br>"
            "<span style='color:#e0a030;'>┆ Punteadas</span>: los otros años "
            "a revisar, ordenados por lo estrecho que es ese anillo en la "
            "cronología.<br><br>"
            "<b>Ojo</b><br>"
            "La altura del pico dice si vale la pena; el ancho dice cuánta "
            "confianza tienes en el año. Son dos cosas distintas."
            "</div>")
        self.txt_ayuda_perfil.setStyleSheet(
            "QTextBrowser{background-color:#1a1a1a; color:#d8d8d8;"
            " border:1px solid #444; padding:8px;}")
        _div_perfil.addWidget(self.txt_ayuda_perfil)
        _div_perfil.setStretchFactor(0, 3)
        _div_perfil.setStretchFactor(1, 1)
        _div_perfil.setSizes([700, 260])
        _lay_perfil.addWidget(_div_perfil, 1)
        _lay_perfil.addWidget(_crear_barra_zoom(self.grafico_perfil))
        self.tabs_inferior.addTab(_cont_perfil, "Perfil del quiebre")

        splitter_der.addWidget(self.tabs_inferior)

        splitter_principal.addWidget(scroll)
        splitter_principal.addWidget(splitter_der)
        splitter_principal.setStretchFactor(0, 1)
        splitter_principal.setStretchFactor(1, 4)
        splitter_principal.setSizes([280, 1120])
        layout_principal.addWidget(splitter_principal)

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

        for ruta in rutas:
            ext = os.path.splitext(ruta)[1].lower()
            base_nombre = os.path.splitext(os.path.basename(ruta))[0]

            try:
                with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                    primeras = f.read(500)

                if "=N" in primeras and "=I" in primeras:
                    series_extraidas = leer_formato_compacto(ruta)
                elif ext == ".wid":
                    df, sid = leer_wid(ruta)
                    series_extraidas = {f"🌲{sid}": df}
                elif ext in (".rwl", ".txt"):
                    primera_real = ""
                    try:
                        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                            for linea in f:
                                ln = linea.rstrip("\r\n")
                                if not ln or ln.startswith("#"):
                                    continue
                                primera_real = ln
                                break
                    except Exception:
                        primera_real = ""

                    if "\t" in primera_real:
                        series_extraidas = self._leer_como_columnas_o_tabular(ruta, base_nombre)
                    else:
                        try:
                            series_extraidas = leer_tucson_multi(ruta)
                        except Exception:
                            series_extraidas = self._leer_como_columnas_o_tabular(ruta, base_nombre)
                elif ext in (".csv", ".tsv") or _es_planilla(ext):
                    series_extraidas = self._leer_como_columnas_o_tabular(ruta, base_nombre)
                else:
                    df, sid = leer_tabular(ruta)
                    series_extraidas = {sid: df}

                for id_serie, df_serie in series_extraidas.items():
                    if id_serie in self.series_datos:
                        n_duplicadas += 1
                        continue
                    self.series_datos[id_serie] = df_serie.copy()
                    self.series_originales[id_serie] = df_serie.copy()
                    item = QListWidgetItem(id_serie)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.lista_series.addItem(item)
                    n_agregadas += 1

            except (ValueError, OSError) as exc:
                logger.warning("Error al cargar %s: %s", ruta, exc)
                errores.append(f"{os.path.basename(ruta)}: {exc}")
                continue

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

    def _leer_como_columnas_o_tabular(self, ruta: str, base_nombre: str) -> dict:
        """Si el archivo tiene múltiples columnas de valor, cada una como serie separada."""
        try:
            df_multi = leer_columna_multi(ruta)
        except Exception:
            df, sid = leer_tabular(ruta)
            return {sid: df}

        cols = list(df_multi.columns)
        if len(cols) == 0:
            df, sid = leer_tabular(ruta)
            return {sid: df}

        if len(cols) == 1:
            col = cols[0]
            df_serie = pd.DataFrame(
                {"Ancho_mm": pd.to_numeric(df_multi[col], errors="coerce")},
                index=df_multi.index,
            ).dropna()
            return {base_nombre: df_serie}

        resultado = {}
        for col in cols:
            df_serie = pd.DataFrame(
                {"Ancho_mm": pd.to_numeric(df_multi[col], errors="coerce")},
                index=df_multi.index,
            ).dropna()
            if df_serie.empty:
                continue
            nombre = f"{base_nombre}_{col}"
            resultado[nombre] = df_serie
        return resultado

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
            if not _es_planilla(ext):
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
                except Exception:
                    primera_real = ""
                if "\t" not in primera_real:
                    try:
                        series = leer_tucson_multi(ruta)
                        if series:
                            self._procesar_tucson_como_crono(series, ruta)
                            return
                    except Exception:
                        pass

            # Multi-columna o tabular
            try:
                # Leer TODAS las hojas (un .ods/.xlsx puede traer una
                # cronología por hoja; pandas solo lee la primera por defecto).
                hojas = leer_columna_multi_hojas(ruta)
                base_nombre = os.path.splitext(os.path.basename(ruta))[0]

                # Detectar columnas auxiliares y descartarlas.
                # Una cronología exportada típicamente trae el VALOR del
                # índice + columnas auxiliares (tamaño de muestra, EPS,
                # Rbar, desviación estándar, etc). Antes cada columna se
                # cargaba como una cronología separada, por eso el usuario
                # veía aparecer 2 o más cronologías al abrir UN archivo.
                # Acá filtramos por nombre los auxiliares conocidos para
                # quedarnos solo con las columnas que son valores de
                # cronología real.
                AUX_COLUMNAS = {
                    # Tamaño de muestra
                    "n", "n_series", "n_samples", "sample_size", "samples",
                    "depth", "count", "cantidad",
                    # Dispersión
                    "sd", "std", "stdev", "stderr", "se", "desv_std",
                    "desviacion", "desviación",
                    # Estadísticos de calidad
                    "rbar", "r_bar", "eps", "snr",
                    # Año (debería estar como índice pero por si acaso)
                    "anio", "año", "year",
                }

                # Armar la lista de candidatos: cada par (hoja, columna) que
                # tenga datos es una cronología potencial.
                candidatos = []  # [(etiqueta, nombre_crono, df_serie)]
                for nombre_hoja, df_multi in hojas.items():
                    cols_validas = [
                        c for c in df_multi.columns
                        if str(c).strip().lower() not in AUX_COLUMNAS
                    ]
                    # Si el filtro quitó todo (raro), no aplicamos el filtro
                    if not cols_validas:
                        cols_validas = list(df_multi.columns)

                    for col in cols_validas:
                        df_serie = pd.DataFrame(
                            {"Ancho_mm": pd.to_numeric(df_multi[col],
                                                       errors="coerce")},
                            index=df_multi.index,
                        ).dropna()
                        if df_serie.empty:
                            continue

                        # Nombre único por cronología. Antes todas las
                        # columnas se agregaban con el MISMO nombre
                        # (el del archivo), así que chocaban entre sí.
                        # Solo se agrega la hoja si hay más de una, y la
                        # columna si hay más de una, para no ensuciar el
                        # nombre con partes redundantes.
                        partes = [base_nombre]
                        if nombre_hoja and len(hojas) > 1:
                            partes.append(str(nombre_hoja))
                        if len(cols_validas) > 1:
                            partes.append(str(col))
                        nombre_crono = "_".join(partes)

                        etiqueta = nombre_crono
                        if len(df_serie):
                            etiqueta += (f"   ({df_serie.index.min()}–"
                                         f"{df_serie.index.max()}, "
                                         f"{len(df_serie)} años)")
                        candidatos.append((etiqueta, nombre_crono, df_serie))

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
                pass

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
        self.series_datos[nombre] = df.copy()
        self.series_originales[nombre] = df.copy()
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

        nombres_a_eliminar = [item.text() for item in items]
        nombres_set = set(nombres_a_eliminar)

        for nombre in nombres_a_eliminar:
            self.series_datos.pop(nombre, None)
            self.series_originales.pop(nombre, None)

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
            f"<span style='color:#888;'>({n_anios} años)</span>"
        )
        v.addWidget(info)

        hint = QLabel(
            "<span style='color:#aaa; font-size:11px;'>"
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

        nuevo_idx = df.index + delta
        df_nuevo = df.copy()
        df_nuevo.index = nuevo_idx
        df_nuevo.sort_index(inplace=True)

        self.series_datos[nombre] = df_nuevo
        self.series_originales[nombre] = df_nuevo.copy()

        self.graficar_series()
        QMessageBox.information(
            self, "Año actualizado",
            f"Serie '{nombre}' desplazada {delta:+d} años.\n"
            f"Ahora va de {int(df_nuevo.index.min())} a {int(df_nuevo.index.max())}."
        )

    def _exportar_una_serie(self, nombre: str):
        """Exporta UNA serie por nombre (usado al exportar varias a la vez)."""
        prev = self.lista_series.currentItem()
        for i in range(self.lista_series.count()):
            it = self.lista_series.item(i)
            if it.text() == nombre:
                self.lista_series.setCurrentItem(it)
                break
        try:
            self._exportar_serie_por_nombre(nombre)
        finally:
            if prev is not None:
                self.lista_series.setCurrentItem(prev)

    def exportar_serie_codatada(self):
        """Exporta la serie marcada con formato según extensión.

        Si el modo COFECHA está activo y aplica a este tipo (serie o
        cronología), ofrece guardar la serie ESTANDARIZADA (la misma
        transformación que se usa para las correlaciones) en vez de los
        datos crudos. Así el usuario puede subir una serie, activar el modo
        COFECHA y guardar la versión estandarizada directamente.
        """
        # Exporta la(s) serie(s) SELECCIONADA(S) (filas resaltadas), no las
        # marcadas con casilla: la casilla es solo para elegir qué se grafica.
        seleccionadas = [it.text() for it in self.lista_series.selectedItems()
                         if it.text() in self.series_datos]
        if not seleccionadas:
            nombre_unico = self._serie_para_accion("exportar")
            if nombre_unico is None:
                return
            seleccionadas = [nombre_unico]

        if len(seleccionadas) > 1:
            resp = QMessageBox.question(
                self, "Varias series seleccionadas",
                f"Hay {len(seleccionadas)} series seleccionadas.\n\n"
                "¿Exportarlas todas? Se pedirá una ubicación por cada una.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            if resp != QMessageBox.StandardButton.Yes:
                return
            for nom in seleccionadas:
                self._exportar_una_serie(nom)
            return

        self._exportar_serie_por_nombre(seleccionadas[0])

    def _exportar_serie_por_nombre(self, nombre: str):
        """Cuerpo real de la exportación, para una serie ya elegida."""
        df = self.series_datos.get(nombre)
        if df is None or df.empty:
            QMessageBox.warning(self, "Sin datos",
                                f"'{nombre}' no tiene datos para exportar.")
            return
        es_crono = nombre.startswith("📚 ")

        # ¿El modo COFECHA aplica a este tipo (serie/cronología)?
        cofecha_aplica = (
            self.btn_modo_cofecha.isChecked() and (
                (es_crono and self.chk_cof_crono.isChecked()) or
                (not es_crono and self.chk_cof_serie.isChecked())
            )
        )

        exportar_std = False
        if cofecha_aplica:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Modo COFECHA activo")
            box.setText(
                f"El modo COFECHA está activo para esta {'cronología' if es_crono else 'serie'}.\n\n"
                f"¿Qué quieres guardar de '{nombre}'?")
            b_std = box.addButton("Estandarizada (COFECHA)",
                                  QMessageBox.ButtonRole.YesRole)
            box.addButton("Datos originales", QMessageBox.ButtonRole.NoRole)
            b_cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is b_cancel:
                return
            exportar_std = box.clickedButton() is b_std

        # ── Exportar ESTANDARIZADA (índice residual COFECHA, 2 columnas) ──
        if exportar_std:
            serie_std = aplicar_modo_cofecha(
                df["Ancho_mm"], **self._modo_cofecha_params)
            nombre_limpio = nombre.replace("📚 ", "").strip()
            self._guardar_serie_2col(
                serie_std, f"{nombre_limpio}_cofecha",
                "Exportar serie estandarizada (COFECHA)",
                estandarizada=True)
            return

        # ── Cronologías → formato 2-columnas con coma decimal ──
        if es_crono:
            nombre_limpio = nombre.replace("📚 ", "").strip()
            # Añadir el tipo de cronología al nombre de archivo por defecto
            # (RES/STD/RAW) para que quede claro qué se guardó. Se usa el tipo
            # de la cronología ACTIVA si el nombre coincide; si no, el de la
            # metadata disponible.
            tipo_c = ""
            if nombre_limpio == self._nombre_cronologia_activa:
                tipo_c = (self.meta_cronologia or {}).get("tipo_cronologia", "")
            tag = {"residual": "RES", "standard": "STD",
                   "raw": "RAW"}.get((tipo_c or "").lower(), "")
            nombre_archivo = f"{nombre_limpio}_{tag}" if tag else nombre_limpio
            self._guardar_serie_2col(
                pd.to_numeric(df["Ancho_mm"], errors="coerce"),
                nombre_archivo, "Exportar cronología", estandarizada=False)
            return

        # ── Series normales → exportador Tucson (anchos crudos en mm) ──
        mediciones = [{"anio": int(idx), "ancho_mm": float(val)}
                      for idx, val in df["Ancho_mm"].items()]
        exp = getattr(self._ventana_padre, "exportador", None)
        if exp:
            exp.exportar_datos(nombre, mediciones)
        else:
            QMessageBox.information(self, "Sin exportador",
                                    "No hay un exportador disponible.")

    def _guardar_serie_2col(self, serie, nombre_archivo, titulo,
                             estandarizada=False):
        """Guarda una serie en formato 2 columnas (Año, Valor) con coma
        decimal. Usado para cronologías y para series estandarizadas
        COFECHA (que son índices residuales adimensionales, no anchos en
        mm, por lo que NO van por el exportador Tucson)."""
        ruta_default = os.path.join(_ultima_carpeta(), f"{nombre_archivo}.txt")
        ruta, fmt = QFileDialog.getSaveFileName(
            self, titulo, ruta_default,
            "Texto separado por tabulaciones (*.txt);;"
            "Tucson (*.rwl);;"
            "CSV separado por punto y coma (*.csv);;"
            "Excel (*.xlsx);;LibreOffice (*.ods)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        ext = os.path.splitext(ruta)[1].lower()
        s = pd.to_numeric(serie, errors="coerce").dropna()
        df_export = pd.DataFrame({
            "Anio": s.index.astype(int),
            "Valor": s.values,
        })
        try:
            if ext == ".rwl":
                # Tucson: los índices adimensionales se guardan ×1000, la
                # convención de ARSTAN (índice 0.873 → 873).
                escribir_tucson(s, ruta, codigo=str(nombre_archivo))
            elif _es_planilla(ext):
                _escribir_excel(df_export, ruta)
            elif ext == ".csv":
                df_export.to_csv(ruta, index=False, sep=";", decimal=",",
                                 float_format="%.6f")
            else:
                df_export.to_csv(ruta, index=False, sep="\t", decimal=",",
                                 float_format="%.6f")
            if estandarizada:
                nota = ("Valores ESTANDARIZADOS por modo COFECHA "
                        "(índice residual adimensional, no anchos en mm).")
            else:
                nota = "Formato 2 columnas (Año, Valor) con coma decimal."
            QMessageBox.information(
                self, "✅ Serie exportada",
                f"Archivo guardado:\n{ruta}\n\n{nota}\n"
                f"Años: {len(df_export)}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")

    # -------------------------------------------------------------------------
    # SIMULADOR MANUAL
    # -------------------------------------------------------------------------

    def simular_insertar(self):
        nombre = self._serie_para_accion("editar")
        if nombre is None:
            return
        anio = self.spin_edit_year.value()
        self.series_datos[nombre] = aplicar_correccion(
            self.series_datos[nombre], anio, 1, anclaje=self._anclaje_actual())
        self.graficar_series()

    def simular_borrar(self):
        nombre = self._serie_para_accion("editar")
        if nombre is None:
            return
        anio = self.spin_edit_year.value()
        self.series_datos[nombre] = aplicar_correccion(
            self.series_datos[nombre], anio, -1, anclaje=self._anclaje_actual())
        self.graficar_series()

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
        self.series_datos[nombre] = self.series_originales[nombre].copy()
        self.graficar_series()
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
        self.series_datos[nombre] = self.series_originales[nombre].copy()
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

    # -------------------------------------------------------------------------
    # CRONOLOGÍA ACTIVA
    # -------------------------------------------------------------------------

    def abrir_ventana_cronologia(self):
        """Cambia a la pestaña de Cronología (antes abría una ventana
        flotante; ahora la cronología es una pestaña propia)."""
        vp = getattr(self, "_ventana_padre", None)
        if vp is not None and hasattr(vp, "ir_a_pestana_cronologia"):
            vp.ir_a_pestana_cronologia()
        elif self._ventana_cronologia is not None:
            # Respaldo: si no hay ventana principal con pestañas, mostrar
            # como ventana flotante (compatibilidad).
            self._ventana_cronologia.show()
            self._ventana_cronologia.raise_()

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
        self.cronologia_activa = df.copy()
        self.meta_cronologia = dict(meta) if meta else {}
        self._nombre_cronologia_activa = nombre or "Cronología"

        if agregar_a_lista:
            # Agregar a la lista como 📚
            nombre_lista = f"📚 {self._nombre_cronologia_activa}"
            col_val = self.meta_cronologia.get("columna_valor", df.columns[0])
            if col_val not in df.columns:
                col_val = df.columns[0]
            df_serie = pd.DataFrame({"Ancho_mm": df[col_val]}, index=df.index)
            df_serie = df_serie.dropna()

            if nombre_lista in self.series_datos:
                self.series_datos[nombre_lista] = df_serie
                self.series_originales[nombre_lista] = df_serie.copy()
            else:
                self.series_datos[nombre_lista] = df_serie
                self.series_originales[nombre_lista] = df_serie.copy()
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
        """Transformación para calcular la r de correlación, gobernada por el
        botón modo COFECHA.

        Punto CLAVE (corrige un bug grave): para que la r coincida con COFECHA,
        la serie y la cronología deben quedar en el MISMO espacio. Una
        cronología residual se construyó con spline+AR (sin log); si a la
        serie se le aplicaba `aplicar_modo_cofecha` (spline+LOG+AR), quedaban
        en espacios distintos y la r se desplomaba (p. ej. 0.90 → 0.51, o peor
        con datos reales). La solución es estandarizar la SERIE cruda con el
        MISMO método que usó la cronología activa, y NO re-procesar la
        cronología (ya está estandarizada).

        - Modo COFECHA apagado: sin transformación (la serie tal como se subió).
        - Modo COFECHA encendido:
            • Cronología (es_crono=True): se usa tal cual (ya estandarizada;
              re-procesarla la dañaría). El checkbox 'Cronología' fuerza a
              estandarizarla igual, para el caso de una cronología cargada
              SIN estandarizar (anchos crudos en mm).
            • Serie cruda (es_crono=False): se estandariza con el método de la
              cronología activa (residual/standard + spline), quedando en su
              mismo espacio. Si no hay cronología activa comparable, se usa la
              estandarización COFECHA clásica (simétrica entre dos series).
          El checkbox 'Serie' permite desactivar la estandarización de la
          serie (usarla cruda) si el usuario ya la subió estandarizada.
        """
        s_raw = pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()
        if not self.btn_modo_cofecha.isChecked():
            return s_raw

        if es_crono:
            # Por defecto la cronología ya vive en su espacio estandarizado
            # (índice residual/standard), así que NO se re-procesa: aplicarle
            # spline+log+AR encima la dañaría y desplomaría la r.
            #
            # El checkbox 'Cronología' es la salida de escape para el caso en
            # que la cronología cargada NO esté estandarizada (p. ej. una
            # cronología de anchos crudos en mm): ahí sí hay que estandarizarla
            # para poder compararla. Por eso el valor por defecto es apagado.
            if not self.chk_cof_crono.isChecked():
                return s_raw
            try:
                res = aplicar_modo_cofecha(serie_mm, **self._modo_cofecha_params)
                if res is not None and not res.empty:
                    return res
            except Exception:
                pass
            return s_raw

        # Serie cruda: solo estandarizar si el checkbox 'Serie' está activo.
        if not self.chk_cof_serie.isChecked():
            return s_raw

        meta = self.meta_cronologia or {}
        tipo = (meta.get("tipo_cronologia") or "").lower()
        metodo = meta.get("metodo_estandarizacion") or "spline"

        # Si el tipo no está en la metadata (p. ej. una cronología cargada
        # desde un archivo plano sin encabezado de tipo), inferirlo del espacio
        # de la cronología activa. Una cronología residual/standard vive en
        # torno a media 1 (índice adimensional); una serie COFECHA clásica vive
        # en torno a 0 (log-residual). Sin esta inferencia, la serie se
        # transformaba con log-COFECHA (media 0) contra una cronología en media
        # 1 —espacios distintos— y la r se desplomaba a casi 0.
        if tipo not in ("residual", "standard") and self.cronologia_activa is not None:
            try:
                mcol = meta.get("columna_valor")
                dfc = self.cronologia_activa
                if not mcol or mcol not in dfc.columns:
                    mcol = dfc.columns[0]
                media_crono = float(
                    pd.to_numeric(dfc[mcol], errors="coerce").dropna().mean())
                if 0.5 < media_crono < 1.5:
                    tipo = "residual"
            except Exception:
                pass

        if tipo in ("residual", "standard"):
            try:
                aplicar_log = bool(meta.get("aplicar_log", False))
                res = _normalizar_serie_para_tipo(
                    serie_mm, tipo, metodo, aplicar_log=aplicar_log)
                if res is not None and not res.empty:
                    return res
            except Exception:
                pass
        # Sin cronología activa comparable: COFECHA clásico (simétrico).
        return aplicar_modo_cofecha(serie_mm, **self._modo_cofecha_params)

    def _serie_para_glk(self, serie_mm: pd.Series, es_crono: bool) -> pd.Series:
        """Serie para calcular GLK y t-BP.

        GLK y t-BP diferencian internamente (GLK usa el signo de la primera
        diferencia; t-BP aplica el filtro de Hollstein = diff-log), así que se
        calculan sobre los datos CRUDOS y no necesitan la estandarización
        COFECHA. Esto los mantiene estables y comparables con el uso clásico.
        """
        return pd.to_numeric(serie_mm, errors="coerce").astype(float).dropna()

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
        m_diff, t_diff, n_m, n_t = self._preparar_diferencias_log(mover, referencia)

        if (len(m_diff) < OVERLAP_MINIMO_ANALISIS or
                len(t_diff) < OVERLAP_MINIMO_ANALISIS):
            return self.grafico_offset.setTitle(
                f"Error: Se requieren >{OVERLAP_MINIMO_ANALISIS} años.")

        serie_a_raw = pd.to_numeric(
            self.series_datos[n_m]["Ancho_mm"], errors="coerce").dropna()
        serie_b_raw = pd.to_numeric(
            self.series_datos[n_t]["Ancho_mm"], errors="coerce").dropna()

        # Series para GLK/t-BP respetando el modo COFECHA (transformadas si
        # está activo; crudas si no). Así estos estadísticos también miran
        # el botón modo COFECHA, igual que r.
        serie_a_glk = self._serie_para_glk(
            self.series_datos[n_m]["Ancho_mm"], es_crono=n_m.startswith("📚"))
        serie_b_glk = self._serie_para_glk(
            self.series_datos[n_t]["Ancho_mm"], es_crono=n_t.startswith("📚"))

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
        s_min = int(t_diff.index.min() - m_diff.index.max() + OVERLAP_MINIMO_ANALISIS - 1)
        s_max = int(t_diff.index.max() - m_diff.index.min() - OVERLAP_MINIMO_ANALISIS + 1)

        self._shifts_actuales = []
        self._r_actuales = []
        self._glk_actuales = []
        self._tbp_actuales = []
        self._n_actuales = []

        for shift in range(s_min, s_max + 1):
            # m_diff desplazada (+shift) se alinea con t_diff
            overlap = (m_diff.index + shift).intersection(t_diff.index)
            # Solape mínimo alto: ver OVERLAP_MINIMO_FLOTANTE. Sin esto las
            # posiciones de los extremos, con diez o veinte años de solape,
            # ganan por azar y tapan el desfase verdadero.
            if len(overlap) < min(OVERLAP_MINIMO_FLOTANTE,
                                  max(len(m_diff), len(t_diff))):
                continue
            r = _r_pearson(m_diff.loc[overlap - shift].values,
                           t_diff.loc[overlap].values)
            if np.isnan(r):
                continue

            # GLK y t-BP sobre la serie para GLK (transformada COFECHA si
            # está activo, cruda si no): se desplaza la PRIMERA serie (a)
            a_glk_shift = serie_a_glk.copy()
            a_glk_shift.index = a_glk_shift.index + shift
            overlap_glk = a_glk_shift.index.intersection(serie_b_glk.index)
            n_ov = len(overlap_glk)
            if n_ov >= OVERLAP_MINIMO_ANALISIS:
                a_o = a_glk_shift.loc[overlap_glk]
                b_o = serie_b_glk.loc[overlap_glk]
                glk, _ = gleichlaufigkeit(a_o, b_o, min_overlap=OVERLAP_MINIMO_ANALISIS)
                t_bp, _, _ = t_baillie_pilcher(a_o, b_o, min_overlap=OVERLAP_MINIMO_ANALISIS)
            else:
                glk = float("nan")
                t_bp = float("nan")

            self._shifts_actuales.append(shift)
            self._r_actuales.append(r)
            self._glk_actuales.append(glk)
            self._tbp_actuales.append(t_bp)
            self._n_actuales.append(n_ov)

        if not self._shifts_actuales:
            return self.grafico_offset.setTitle("Sin coincidencias suficientes.")

        self._redibujar_offset()
        self.btn_ver_tabla_off.setEnabled(True)

    def _redibujar_offset(self):
        """Redibuja las barras de offset con la métrica seleccionada en el combo."""
        if not self._shifts_actuales:
            return

        metrica_txt = self.combo_metrica_offset.currentText()

        if metrica_txt.startswith("🎯"):
            vals = [score_compuesto(r, g, t)
                    for r, g, t in zip(self._r_actuales, self._glk_actuales, self._tbp_actuales)]
            metric_name = "Puntaje compuesto"
            color_func = _color_compuesto
            umbrales_html = (
                "<b>Puntaje compuesto</b> = ∛(r × GLK_norm × t-BP_norm) preserva signo: "
                "<span style='color:#dc3545;'>&lt;-0.20 anti-correlación</span> · "
                "<span style='color:#fd7e14;'>-0.20–+0.20 ambiguo</span> · "
                "<span style='color:#ffc107;'>+0.20–+0.40 débil</span> · "
                "<span style='color:#5cb85c;'>+0.40–+0.60 bueno</span> · "
                "<span style='color:#28a745;'>&gt;+0.60 confiable</span>"
            )
            y_range = (-1.05, 1.05)
        elif metrica_txt.startswith("t-BP"):
            vals = list(self._tbp_actuales)
            metric_name = "t-BP"
            color_func = _color_tbp
            umbrales_html = (
                "<b>Umbrales t-BP</b> (Baillie & Pilcher 1973): "
                "<span style='color:#dc3545;'>&lt;3 dudoso</span> · "
                "<span style='color:#fd7e14;'>3–4 débil</span> · "
                "<span style='color:#ffc107;'>4–6 aceptable</span> · "
                "<span style='color:#5cb85c;'>&gt;6 confiable</span>"
            )
            vals_validos = [v for v in vals if np.isfinite(v)]
            y_max = (max(vals_validos) * 1.15) if vals_validos else 10.0
            y_range = (-1.0, max(8.0, y_max))
        elif metrica_txt.startswith("GLK"):
            vals = list(self._glk_actuales)
            metric_name = "GLK"
            color_func = _color_glk
            umbrales_html = (
                "<b>Umbrales GLK</b> (Eckstein 1969): "
                "<span style='color:#dc3545;'>&lt;0.60 azar</span> · "
                "<span style='color:#fd7e14;'>0.60–0.65 débil</span> · "
                "<span style='color:#ffc107;'>0.65–0.70 aceptable</span> · "
                "<span style='color:#5cb85c;'>&gt;0.70 confiable</span>"
            )
            y_range = (0.30, 1.0)
        else:
            vals = list(self._r_actuales)
            metric_name = "r"
            color_func = _color_r
            umbrales_html = (
                "<b>Umbrales r</b> (Pearson, post-AR): "
                "<span style='color:#dc3545;'>&lt;0.20 azar</span> · "
                "<span style='color:#fd7e14;'>0.20–0.35 débil</span> · "
                "<span style='color:#ffc107;'>0.35–0.50 aceptable</span> · "
                "<span style='color:#5cb85c;'>&gt;0.50 confiable</span>"
            )
            y_range = (-1.05, 1.05)

        self.grafico_offset.clear()
        self.grafico_offset.addItem(self._texto_hover)
        self._texto_hover.hide()

        self.grafico_offset.addItem(pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen("#aaaaaa", width=1)))

        for shift, val in zip(self._shifts_actuales, vals):
            if not np.isfinite(val):
                continue
            self.grafico_offset.addItem(pg.BarGraphItem(
                x=[shift], height=[val], width=1.0,
                brush=color_func(val), pen=pg.mkPen(None)
            ))

        vals_para_max = [v if np.isfinite(v) else -np.inf for v in vals]
        if max(vals_para_max) > -np.inf:
            idx_max = int(np.argmax(vals_para_max))
            best_shift = self._shifts_actuales[idx_max]
            best_val = vals[idx_max]
            self.grafico_offset.addItem(pg.BarGraphItem(
                x=[best_shift], height=[best_val], width=1.0,
                brush=color_func(best_val),
                pen=pg.mkPen("white", width=2)
            ))

            def _f(v, dec=2):
                return "—" if not np.isfinite(v) else f"{v:.{dec}f}"

            self.grafico_offset.setTitle(
                f"Análisis de desfase — métrica: <b>{metric_name}</b>  "
                f"|  mejor: shift {best_shift:+d}, {metric_name}={_f(best_val)}"
            )
        else:
            self.grafico_offset.setTitle(f"Análisis de desfase — métrica: <b>{metric_name}</b>")

        self.grafico_offset.setYRange(*y_range)
        self.grafico_offset.setXRange(
            min(self._shifts_actuales) - 2, max(self._shifts_actuales) + 2)

        self.lbl_stats.setText(
            f"<div style='font-size:11px; line-height:1.5;'>"
            f"{umbrales_html}<br>"
            f"<span style='color:#888;'>"
            f"💡 Pasá el mouse sobre las barras para ver r/GLK/t-BP/n de cada shift. "
            f"La fecha verdadera es donde las TRES métricas son altas simultáneamente — "
            f"si solo una es alta, suele ser coincidencia.</span>"
            f"</div>"
        )
        self.lbl_stats.setVisible(True)

    # ── Comparación múltiple directa contra cronología ────────────────────

    def aplicar_desfase_a_serie(self, nombre: str, shift: int,
                                 regraficar: bool = True) -> bool:
        """Re-data UNA serie sumando `shift` a su índice de años.

        Reutilizable desde la tabla de comparación múltiple y desde la
        ventana de detalle. Actualiza series_datos y series_originales,
        invalida la caché de comparación y (opcionalmente) regrafica.

        Devuelve True si aplicó algún cambio.
        """
        if shift == 0:
            return False
        df = self.series_datos.get(nombre)
        if df is None or df.empty:
            return False
        df_new = df.copy()
        df_new.index = df_new.index + int(shift)
        self.series_datos[nombre] = df_new
        if hasattr(self, "series_originales"):
            self.series_originales[nombre] = df_new.copy()
        self._cache_comparacion = None
        if regraficar:
            self.graficar_series()
        return True

    def reemplazar_serie(self, nombre: str, df_nuevo: pd.DataFrame,
                          regraficar: bool = True):
        """Reemplaza por completo los datos de una serie (usado por el
        editor de anillos, que cambia anchos y/o cantidad de anillos).
        Invalida la caché de comparación y regrafica."""
        self.series_datos[nombre] = df_nuevo.copy()
        if hasattr(self, "series_originales"):
            self.series_originales[nombre] = df_nuevo.copy()
        self._cache_comparacion = None
        if regraficar:
            self.graficar_series()

    def _abrir_editor_anillos_marcada(self):
        """Abre el editor de anillos para la serie marcada (exactamente
        una). Accesible directamente desde el panel principal."""
        nombre = self._serie_para_accion("editar")
        if nombre is None:
            return
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
        dlg = DialogoEditarAnillos(df, nombre, self, parent=self)
        dlg.exec()

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
        clave_actual = self._clave_cache_comparacion(nombres)
        cache = getattr(self, "_cache_comparacion", None)
        if (cache is not None and cache.get("clave") == clave_actual
                and cache.get("resultados")):
            dlg = DialogoComparacionMultiple(
                cache["resultados"], cache["nombre_crono"], parent=self)
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
        # CRUDA (para rangos de años, GLK/t-BP, y series guardadas)
        s_b_raw = pd.to_numeric(
            self.cronologia_activa[col_val], errors="coerce"
        ).dropna()
        if s_b_raw.empty:
            QMessageBox.warning(
                self, "Cronología sin datos válidos",
                "La cronología activa no contiene valores numéricos válidos."
            )
            return
        # ALTA FRECUENCIA para r (misma transformación que el cofechado real,
        # respetando el modo COFECHA si está activo). Evita las correlaciones
        # espurias de los anchos crudos (tendencias de edad compartidas).
        s_b_corr = self._transformar_para_correlacion(
            self.cronologia_activa[col_val], es_crono=True)
        # Serie para GLK/t-BP respetando COFECHA (transformada si COFECHA
        # activo; cruda si no).
        s_b_glk = self._serie_para_glk(
            self.cronologia_activa[col_val], es_crono=True)
        c_min_year = int(s_b_raw.index.min())
        c_max_year = int(s_b_raw.index.max())

        # Cursor de espera durante el cálculo
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        resultados = []
        nombre_crono = self._nombre_cronologia_activa or "cronología"

        try:
            for nombre in nombres:
                df_serie = self.series_datos.get(nombre)
                if df_serie is None or df_serie.empty:
                    continue

                # CRUDA (rangos de años, GLK/t-BP, gráficos, alineamiento)
                s_a_raw = pd.to_numeric(
                    df_serie["Ancho_mm"], errors="coerce").dropna()
                if s_a_raw.empty:
                    continue
                # ALTA FRECUENCIA para r
                es_crono_serie = nombre.startswith("📚")
                s_a_corr = self._transformar_para_correlacion(
                    df_serie["Ancho_mm"], es_crono_serie)
                if s_a_corr.empty:
                    continue
                # Serie para GLK/t-BP respetando COFECHA
                s_a_glk = self._serie_para_glk(
                    df_serie["Ancho_mm"], es_crono_serie)

                s_min_year = int(s_a_raw.index.min())
                s_max_year = int(s_a_raw.index.max())

                # Rango de desfase que garantiza al menos MIN_OVERLAP años
                # de solape con la cronología.
                shift_min = c_min_year - s_max_year + MIN_OVERLAP - 1
                shift_max = c_max_year - s_min_year - MIN_OVERLAP + 1

                if shift_min > shift_max:
                    resultados.append(self._resultado_sin_overlap(nombre))
                    continue
                max_shift_dinamico = max(abs(shift_min), abs(shift_max))

                # ACELERACIÓN: si la serie YA se solapa con la cronología en su
                # posición actual (serie fechada en años calendario), basta con
                # explorar desfases PEQUEÑOS para detectar errores de datación.
                # El barrido completo (±cientos de años) solo hace falta para
                # series FLOTANTES sin fecha. Con muchas series fechadas, esto
                # reduce el tiempo de más de un minuto a unos pocos segundos.
                overlap_en_0 = len(s_a_raw.index.intersection(s_b_raw.index))
                if overlap_en_0 >= MIN_OVERLAP:
                    max_shift_dinamico = min(max_shift_dinamico, VENTANA_DESFASE_FECHADA)
                else:
                    max_shift_dinamico = min(max_shift_dinamico, 5000)

                # r sobre alta frecuencia (s_*_corr); GLK/t-BP sobre
                # s_*_glk (transformada COFECHA si activo, cruda si no).
                shifts, rs, glks, tbps, ns = _estadisticos_por_desfase(
                    s_a_corr, s_b_corr, max_shift_dinamico, MIN_OVERLAP,
                    serie_a_raw=s_a_glk, serie_b_raw=s_b_glk,
                )

                if not shifts:
                    resultados.append(self._resultado_sin_overlap(nombre))
                    continue

                # Puntaje compuesto por desfase y elección del mejor
                scores = [score_compuesto(r, g, t)
                          for r, g, t in zip(rs, glks, tbps)]
                scores_validos = [
                    (i, s) for i, s in enumerate(scores) if np.isfinite(s)]
                if scores_validos:
                    idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
                else:
                    idx_mejor = int(np.argmax(rs))

                # Puntaje en desfase=0 para calcular Δ
                if 0 in shifts:
                    score_shift0 = scores[shifts.index(0)]
                else:
                    score_shift0 = float("nan")

                resultados.append({
                    "nombre_serie": nombre,
                    "shifts": shifts, "rs": rs, "glks": glks,
                    "tbps": tbps, "ns": ns,
                    "mejor_shift": shifts[idx_mejor],
                    "mejor_score": scores[idx_mejor],
                    "mejor_r": rs[idx_mejor],
                    "mejor_glk": glks[idx_mejor],
                    "mejor_tbp": tbps[idx_mejor],
                    "mejor_n": ns[idx_mejor],
                    "score_shift0": score_shift0,
                    # Series CRUDAS para los gráficos de detalle y el
                    # alineamiento (que diferencia internamente).
                    "serie_a": s_a_raw,
                    "serie_b": s_b_raw,
                })

                QApplication.processEvents()
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

        dlg = DialogoComparacionMultiple(resultados, nombre_crono, parent=self)
        dlg.exec()

    def _clave_cache_comparacion(self, nombres: list[str]) -> tuple:
        """Construye una clave que identifica el estado de una comparación.

        Incluye, por cada serie marcada y por la cronología activa: nombre,
        número de puntos, primer y último año, y suma redondeada de los
        valores. Si el usuario edita una medición, agrega o quita series, o
        cambia de cronología, la clave cambia y se fuerza el recálculo. Si
        todo sigue igual, la clave coincide y se reusan los resultados.
        """
        def _firma(df: pd.DataFrame) -> tuple:
            if df is None or df.empty:
                return (0, 0, 0, 0.0)
            try:
                vals = pd.to_numeric(df["Ancho_mm"], errors="coerce").dropna()
                return (
                    len(vals),
                    int(df.index.min()),
                    int(df.index.max()),
                    round(float(vals.sum()), 4),
                )
            except (ValueError, TypeError, KeyError):
                return (len(df), 0, 0, 0.0)

        partes = []
        for n in sorted(nombres):
            partes.append((n,) + _firma(self.series_datos.get(n)))
        # Incluir la cronología activa
        crono_firma = (self._nombre_cronologia_activa,)
        if self.cronologia_activa is not None:
            meta = self.meta_cronologia or {}
            col_val = meta.get("columna_valor")
            df_c = self.cronologia_activa
            if col_val and col_val in df_c.columns:
                vals_c = pd.to_numeric(df_c[col_val], errors="coerce").dropna()
                crono_firma += (len(vals_c), round(float(vals_c.sum()), 4))
        partes.append(crono_firma)

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
        partes.append(("__cofecha__",) + cof)
        return tuple(partes)

    def _resultado_sin_overlap(self, nombre: str) -> dict:
        """Devuelve un dict de resultado en blanco para series que no
        pueden compararse (sin solape suficiente con la cronología incluso
        con el desfase máximo). Aparecen en la tabla con valores en 0/—
        para que el usuario sepa cuáles quedaron fuera."""
        return {
            "nombre_serie": nombre,
            "shifts": [], "rs": [], "glks": [],
            "tbps": [], "ns": [],
            "mejor_shift": 0,
            "mejor_score": float("nan"),
            "mejor_r": float("nan"),
            "mejor_glk": float("nan"),
            "mejor_tbp": float("nan"),
            "mejor_n": 0,
            "score_shift0": float("nan"),
        }

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
            panel_ref=self,
        )
        dialogo.exec()

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

        years, rs, glks, tbps, ns = _stats_movil(
            m_diff, t_diff, overlap, mitad, serie_a_raw, serie_b_raw)

        self._stats_movil_years = years
        self._stats_movil_r = rs
        self._stats_movil_glk = glks
        self._stats_movil_tbp = tbps
        self._stats_movil_n = ns
        self._mitad_ventana_actual = mitad

        r_global = _r_pearson(m_diff.loc[overlap].values, t_diff.loc[overlap].values)
        self._stats_actuales = estadisticos_cofechado(serie_a_raw, serie_b_raw)
        self._nombre_referencia = n_m
        self._nombre_problema = n_t

        self._dibujar_curva_cofechado(years, rs, overlap, r_global, n_t, [], False)

    def buscar_errores(self):
        """Busca anillos faltantes/sobrantes + calcula stats móviles."""
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
            a = QSettings("MoiCedrus", "DPI")
            a.setValue("informe/fuente",
                       self.combo_fuente_informe.currentData())
            a.setValue("informe/tamano", self.spin_fuente_informe.value())
        except Exception:
            pass

    def _restaurar_pref_fuente(self):
        try:
            from PyQt6.QtCore import QSettings
            a = QSettings("MoiCedrus", "DPI")
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
        vc = getattr(self, "_ventana_cronologia", None)
        if vc is not None:
            _sumar(getattr(vc, "_series_cronologia", None))
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
            QSettings("MoiCedrus", "DPI").setValue(
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
            r = QSettings("MoiCedrus", "DPI").value(
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
                cabecera = ("<span style='color:#888;'><b>Diagnóstico no concluyente</b>"
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

    def _on_seleccion_sugerencia(self):
        fila = self.tabla_sugerencias.currentRow()
        # Cambiar de sugerencia descarta una prueba en curso (para no mezclar).
        if self._prueba_activa:
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
            f"<span style='color:#888;'>Los años ≤ {anio} no cambian "
            f"(médula fija).</span><br>"
            f"Correlación r: {self._fmt_r(sug['r_antes'])} → "
            f"{self._fmt_r(sug['r_tras'])} "
            f"(Δr +{sug['delta_r']:.3f})")

    def probar_correccion_seleccionada(self):
        """Aplica la corrección seleccionada de forma TEMPORAL (con respaldo)
        para ver cómo queda la serie corregida, sin tocar la serie real ni
        re-buscar (para no reiniciar la tabla)."""
        fila = self.tabla_sugerencias.currentRow()
        if fila < 0 or fila >= len(self._sugerencias):
            return
        sug = self._sugerencias[fila]
        nombre = self._nombre_problema
        df_corr = sug.get("df_corregido")
        if nombre not in self.series_datos or df_corr is None:
            QMessageBox.warning(self, "Sin serie",
                                "No se encontró la serie a corregir.")
            return
        # Respaldar y aplicar temporalmente
        self._prueba_backup = self.series_datos[nombre].copy()
        self._prueba_nombre = nombre
        self._prueba_sug = dict(sug)
        self._prueba_activa = True
        self.series_datos[nombre] = df_corr.copy()

        self._marcar_prueba_ui(True)
        self.btn_aplicar.setEnabled(True)
        # Redibujar la serie corregida y su preview de correlación
        self.graficar_series()
        self._dibujar_preview(self._prueba_sug)
        self.lbl_prueba.setText(
            "● Probando corrección (sin aplicar)<br>"
            + self._texto_cambio_sugerencia(self._prueba_sug, nombre))
        self.lbl_prueba.setVisible(True)

    def _marcar_prueba_ui(self, activa: bool):
        self.btn_descartar_prueba.setEnabled(activa)
        self.btn_probar.setEnabled(not activa)
        if not activa:
            self.lbl_prueba.setVisible(False)
            self.lbl_prueba.setText("")

    def _descartar_prueba(self, silencioso: bool = False):
        """Revierte una prueba en curso a la serie original."""
        if not self._prueba_activa:
            return
        if (self._prueba_backup is not None
                and self._prueba_nombre in self.series_datos):
            self.series_datos[self._prueba_nombre] = self._prueba_backup.copy()
        self._prueba_activa = False
        self._prueba_backup = None
        self._prueba_nombre = ""
        self._prueba_sug = None
        self._marcar_prueba_ui(False)
        self.graficar_series()
        if not silencioso:
            try:
                self.buscar_errores()
            except Exception:
                pass

    def aplicar_correccion_seleccionada(self):
        """Aplica la corrección a la serie REAL, tras confirmar exactamente
        qué datos se modifican. Ofrece hacerlo conservando el ancho (editor)
        o de forma automática (ancho promedio)."""
        # Determinar la sugerencia a aplicar: la que se está probando, o la
        # seleccionada en la tabla.
        if self._prueba_activa and self._prueba_sug is not None:
            sug = self._prueba_sug
            nombre = self._prueba_nombre
        else:
            fila = self.tabla_sugerencias.currentRow()
            if fila < 0 or fila >= len(self._sugerencias):
                return
            sug = self._sugerencias[fila]
            nombre = self._nombre_problema
        if nombre not in self.series_datos:
            QMessageBox.warning(self, "Sin serie",
                                "No se encontró la serie a corregir.")
            return

        # Confirmación: mostrar QUÉ datos se modifican y CÓMO aplicarlos.
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Question)
        caja.setWindowTitle("Confirmar corrección")
        caja.setTextFormat(Qt.TextFormat.RichText)
        caja.setText(
            "¿Aplicar esta corrección a la serie real?<br><br>"
            + self._texto_cambio_sugerencia(sug, nombre))
        btn_ancho = caja.addButton("Conservando ancho (editor)",
                                   QMessageBox.ButtonRole.AcceptRole)
        btn_auto = caja.addButton("Automático (ancho promedio)",
                                  QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        # QMessageBox reparte el ancho según el TEXTO, no según los botones, así
        # que con botones de etiqueta larga estos salían cortados y no se podía
        # leer qué hacía cada uno. Se fuerza un ancho mínimo suficiente.
        _ensanchar_dialogo(caja, minimo=560)
        caja.exec()
        elegido = caja.clickedButton()
        if elegido not in (btn_ancho, btn_auto):
            return  # cancelado

        if elegido is btn_ancho:
            # Conservar ancho: revertir la prueba (si la hay) y abrir el editor
            # posicionado en el año sugerido, que hace el commit definitivo.
            if self._prueba_activa:
                self.series_datos[self._prueba_nombre] = self._prueba_backup.copy()
                self._prueba_activa = False
                self._prueba_backup = None
                self._marcar_prueba_ui(False)
            df = self.series_datos[nombre]
            dlg = DialogoEditarAnillos(df, nombre, self, parent=self,
                                       sugerencia=sug)
            dlg.exec()
        else:
            # Automático: comprometer la serie corregida (ancho promedio).
            df_corr = sug.get("df_corregido")
            if df_corr is not None:
                self.series_datos[nombre] = df_corr.copy()
            self.series_originales[nombre] = self.series_datos[nombre].copy()
            # Limpiar estado de prueba (ya comprometido)
            self._prueba_activa = False
            self._prueba_backup = None
            self._marcar_prueba_ui(False)

        # Refrescar tras aplicar
        self.spin_edit_year.setValue(int(sug["anio"]))
        for i in range(self.lista_series.count()):
            item = self.lista_series.item(i)
            if item.text() == nombre:
                self.lista_series.setCurrentItem(item)
                break
        self._limpiar_preview()
        self._sugerencias.clear()
        self.tabla_sugerencias.setRowCount(0)
        self.btn_aplicar.setEnabled(False)
        self.btn_probar.setEnabled(False)
        self.graficar_series()
        self.buscar_errores()

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


# =============================================================================
# VENTANA DE CRONOLOGÍA
# =============================================================================

# =============================================================================
# DIÁLOGO REUSABLE EPS / RBAR (compartido entre panel y VentanaCronologia)
# =============================================================================

def _mostrar_dialogo_eps_rbar(parent, meta: dict, nombre_cronologia: str):
    """Diálogo modal que grafica EPS móvil y Rbar móvil de una cronología,
    con botón para exportar los datos a CSV/TXT/Excel.

    Función a nivel módulo (en vez de método) para que ambos puntos de
    entrada (botón del panel y botón de la ventana de cronología) usen
    exactamente el mismo flujo y diálogo.

    Parameters
    ----------
    parent : QWidget
        Widget padre para el QDialog (típicamente el panel o la ventana).
    meta : dict
        Diccionario de metadatos. Debe tener llaves 'EPS_movil' y 'Rbar_movil'
        (cada una es un dict {año: valor}).
    nombre_cronologia : str
        Nombre que aparece en el título del diálogo.
    """
    eps_dict = (meta or {}).get("EPS_movil", {})
    rbar_dict = (meta or {}).get("Rbar_movil", {})

    if not eps_dict:
        QMessageBox.information(parent, "Sin datos",
            "Esta cronología no tiene EPS móvil calculado.\n\n"
            "Para verlo, regenerala con varias series desde la "
            "ventana de Cronología.")
        return

    dlg = QDialog(parent)
    nombre_safe = nombre_cronologia or "Cronología"
    dlg.setWindowTitle(f"EPS / Rbar — {nombre_safe}")
    dlg.resize(900, 600)
    lay = QVBoxLayout(dlg)

    lbl = QLabel(
        "<b>EPS (Expressed Population Signal)</b> — Wigley et al. (1984)<br>"
        "<span style='color:#888; font-size:11px;'>"
        "EPS = (N·Rbar) / (1 + (N-1)·Rbar). Umbral 0.85 (línea gris).<br>"
        "Rbar = correlación promedio entre pares de series en cada ventana móvil.<br>"
        "Una EPS &lt; 0.85 indica que el promedio (cronología) no captura "
        "adecuadamente la señal común de las series — esa porción de años "
        "es poco confiable.</span>"
    )
    lbl.setWordWrap(True)
    lay.addWidget(lbl)

    plot_eps = pg.PlotWidget(title="EPS móvil")
    _agregar_hover_anio(plot_eps)
    plot_eps.showGrid(x=True, y=True, alpha=0.3)
    plot_eps.setYRange(0, 1.05)
    anios_eps = sorted(eps_dict.keys())
    vals_eps = [eps_dict[a] for a in anios_eps]
    plot_eps.plot(anios_eps, vals_eps, pen=pg.mkPen("#5cb85c", width=2))
    plot_eps.addItem(pg.InfiniteLine(
        pos=0.85, angle=0,
        pen=pg.mkPen("#888", style=Qt.PenStyle.DashLine)
    ))
    lay.addWidget(plot_eps)

    if rbar_dict:
        plot_rbar = pg.PlotWidget(title="Rbar móvil")
        _agregar_hover_anio(plot_rbar)
        plot_rbar.showGrid(x=True, y=True, alpha=0.3)
        anios_r = sorted(rbar_dict.keys())
        vals_r = [rbar_dict[a] for a in anios_r]
        plot_rbar.plot(anios_r, vals_r, pen=pg.mkPen("#3388FF", width=2))
        lay.addWidget(plot_rbar)

    fila_btn = QHBoxLayout()

    btn_export = QPushButton("💾 Exportar EPS / Rbar a CSV")
    btn_export.setStyleSheet(
        "background-color:#5cb85c; color:white; font-weight:bold; "
        "padding:6px 12px;"
    )

    def _exportar_eps_rbar():
        ruta_default = os.path.join(
            _ultima_carpeta(), f"{nombre_safe}_eps_rbar.csv")
        ruta, fmt = QFileDialog.getSaveFileName(
            dlg, "Exportar EPS / Rbar",
            ruta_default,
            "CSV separado por punto y coma (*.csv);;"
            "Texto separado por tabulaciones (*.txt);;"
            "Excel (*.xlsx);;LibreOffice (*.ods)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            todos_anios = sorted(set(eps_dict.keys()) | set(rbar_dict.keys()))
            df_export = pd.DataFrame({
                "Anio": [int(a) for a in todos_anios],
                "EPS": [eps_dict.get(a, float("nan")) for a in todos_anios],
                "Rbar": [rbar_dict.get(a, float("nan")) for a in todos_anios],
            })
            ext = os.path.splitext(ruta)[1].lower()
            if _es_planilla(ext):
                _escribir_excel(df_export, ruta)
            elif ext == ".csv":
                df_export.to_csv(ruta, index=False, sep=";",
                                 decimal=",", float_format="%.6f")
            else:
                df_export.to_csv(ruta, index=False, sep="\t",
                                 decimal=",", float_format="%.6f")
            QMessageBox.information(
                dlg, "✅ Exportado",
                f"EPS / Rbar exportados a:\n{ruta}\n\n"
                f"Filas: {len(df_export)} años"
            )
        except Exception as exc:
            QMessageBox.critical(dlg, "Error",
                                 f"No se pudo guardar:\n{exc}")

    btn_export.clicked.connect(_exportar_eps_rbar)
    fila_btn.addWidget(btn_export)

    btn_close = QPushButton("Cerrar")
    btn_close.clicked.connect(dlg.accept)
    fila_btn.addWidget(btn_close)

    lay.addLayout(fila_btn)
    dlg.exec()


class VentanaCronologia(QWidget):
    """Panel para construir, cargar, exportar y comparar cronologías.

    Antes era un QDialog flotante abierto desde Co-Datación. Ahora es un
    panel embebible que vive en su propia pestaña (la generación de
    cronologías no pertenece a la co-datación). Sigue pasando la cronología
    generada a Co-Datación mediante `self._panel.set_cronologia_activa(...)`.

    `panel_codatacion`: el PanelCodatacion al que se le pasa la cronología
    activa. `parent`: el widget contenedor (la ventana principal / pestaña).
    """

    def __init__(self, panel_codatacion, parent=None):
        super().__init__(parent)
        self._series_cronologia: dict[str, pd.DataFrame] = {}
        self._panel = panel_codatacion
        # Registro inverso: el panel necesita alcanzar las series con que se
        # construyó la cronología, porque sirven de nulo para el localizador
        # de quiebres. Sin esto, cargar solo la cronología terminada dejaba al
        # panel sin colección con qué comparar.
        try:
            panel_codatacion._ventana_cronologia = self
        except Exception:
            pass
        self.setWindowTitle("Cronología")
        self.setMinimumSize(900, 600)

        self.cronologia_df: pd.DataFrame | None = None
        self.cronologia_meta: dict = {}
        self.eps_movil: pd.DataFrame | None = None

        self._construir_ui()
        self.refresh_series()
        self._sincronizar_widgets_con_tema_app()

    def _sincronizar_widgets_con_tema_app(self):
        """Aplica colores apropiados al QTextEdit según el tema activo de la app.
        QTextEdit no está cubierto por el stylesheet global (estilos.py solo
        cubre QListView/QSpinBox/etc), así que sin esto el QTextEdit queda con
        fondo blanco default y el texto blanco heredado de `QWidget { color: white; }`
        del estilo global oscuro → metadata invisible.
        """
        ss_app = QApplication.instance().styleSheet() or ""
        if "#2b2b2b" in ss_app:
            # Tema oscuro — replicar el estilo de QListView del global
            self.txt_info.setStyleSheet(
                "QTextEdit { background-color: #3b3b3b; color: white; "
                "border: 1px solid #555; border-radius: 3px; padding: 4px; }"
            )
        elif "#f0f0f0" in ss_app:
            # Tema claro
            self.txt_info.setStyleSheet(
                "QTextEdit { background-color: white; color: black; "
                "border: 1px solid #ccc; border-radius: 3px; padding: 4px; }"
            )
        # Si no hay marcador reconocible, dejar sin estilizar.

    def changeEvent(self, event):
        """Re-sincroniza el QTextEdit cuando cambia el tema de la app en caliente."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange and hasattr(self, "txt_info"):
            self._sincronizar_widgets_con_tema_app()

    def _construir_ui(self):
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_cargar_series = QPushButton("📂 Cargar series")
        self.btn_cargar_series.clicked.connect(self._cargar_series_desde_panel)
        barra.addWidget(self.btn_cargar_series)

        self.btn_nueva = QPushButton("🗑 Nueva")
        self.btn_nueva.setToolTip(
            "Limpia todo (series cargadas y cronología generada) para "
            "empezar una cronología nueva desde cero.")
        self.btn_nueva.setStyleSheet(
            "QPushButton{background-color:#6c757d; color:white;}"
            "QPushButton:hover{background-color:#7d868e;}")
        self.btn_nueva.clicked.connect(self.nueva_cronologia)
        barra.addWidget(self.btn_nueva)

        self.btn_generar = QPushButton("⚙ Generar cronología")
        self.btn_generar.clicked.connect(self.generar_cronologia)
        self.btn_generar.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold;")
        barra.addWidget(self.btn_generar)

        self.btn_exportar = QPushButton("💾 Exportar cronología")
        self.btn_exportar.clicked.connect(self.exportar_cronologia)
        self.btn_exportar.setEnabled(False)
        barra.addWidget(self.btn_exportar)

        self.btn_eps_rbar = QPushButton("📈 EPS / Rbar")
        self.btn_eps_rbar.setToolTip(
            "Ver el gráfico de EPS móvil y Rbar móvil de la cronología actual.\n"
            "Permite identificar tramos de años con baja confianza estadística."
        )
        self.btn_eps_rbar.setStyleSheet(
            "QPushButton{background-color:#3a6e3a; color:white; font-weight:bold;}"
            "QPushButton:hover{background-color:#4a8e4a;}"
            "QPushButton:disabled{background-color:#444; color:#888;}"
        )
        self.btn_eps_rbar.setEnabled(False)
        self.btn_eps_rbar.clicked.connect(self._mostrar_eps_rbar)
        barra.addWidget(self.btn_eps_rbar)

        self.btn_usar = QPushButton("📚 Usar en cofechado")
        self.btn_usar.clicked.connect(self.usar_cronologia_en_panel)
        self.btn_usar.setEnabled(False)
        barra.addWidget(self.btn_usar)

        self.btn_comparar = QPushButton("🔎 Comparar con cronología")
        self.btn_comparar.setToolTip(
            "Comparar serie(s) marcada(s) contra la cronología activa.\n"
            "• 1 serie marcada  → gráfico + análisis detallado\n"
            "• 2+ marcadas      → tabla resumen batch (una fila por serie)")
        self.btn_comparar.clicked.connect(self.comparar_con_cronologia)
        self.btn_comparar.setEnabled(False)
        barra.addWidget(self.btn_comparar)

        # Botón "Tabla detallada": muestra los resultados de la última
        # comparación con TODOS los desfases ordenados por score compuesto.
        # Aparece oculto al inicio (no hay resultados todavía) y se muestra
        # automáticamente después de la primera comparación.
        self._btn_tabla_comparacion = QPushButton("📊 Tabla detallada")
        self._btn_tabla_comparacion.setToolTip(
            "Ver todos los desfases con r, GLK, t-BP y puntaje compuesto\n"
            "(disponible después de comparar con la cronología)")
        self._btn_tabla_comparacion.clicked.connect(self._abrir_tabla_comparacion)
        self._btn_tabla_comparacion.setVisible(False)
        barra.addWidget(self._btn_tabla_comparacion)

        layout.addLayout(barra)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        left_layout.addWidget(QLabel("<b>Series disponibles:</b>"))

        self.btn_sel_todo = QPushButton("☑ Seleccionar / Deseleccionar todo")
        self.btn_sel_todo.setStyleSheet("QPushButton{padding:4px; font-size:11px;}")
        self.btn_sel_todo.clicked.connect(self.toggle_seleccion)
        left_layout.addWidget(self.btn_sel_todo)

        self.lista_series = QListWidget()
        self.lista_series.itemChanged.connect(self._sincronizar_estado_botones)
        left_layout.addWidget(self.lista_series, 1)

        self.lbl_estado = QLabel("Sin cronología cargada.")
        self.lbl_estado.setWordWrap(True)
        left_layout.addWidget(self.lbl_estado)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        box_cfg = QGroupBox("Configuración")
        form = QFormLayout(box_cfg)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["raw", "standard", "residual", "Todas"])
        # Default = "residual": es el tipo típico para cofechado/clima (estilo
        # COFECHA/ARSTAN) y, además, deja el selector de estandarización
        # habilitado desde el inicio. Con "raw" (sin detrending) el método de
        # estandarización no aplica y queda deshabilitado, lo que confundía
        # ("no deja escoger").
        self.combo_tipo.setCurrentText("residual")
        self.combo_tipo.currentTextChanged.connect(self._on_tipo_cronologia_cambiado)
        form.addRow("Tipo de cronología:", self.combo_tipo)

        self.combo_metodo = QComboBox()
        # "raw" se quitó porque no aplica estandarización: tipo="standard" con
        # metodo="raw" devuelve exactamente lo mismo que tipo="raw". Para
        # cronología sin detrending, usar tipo="raw" directamente.
        # "media" se muestra en español; _ajustar_curva acepta tanto "media"
        # como "mean", así que el texto visible puede ir en español.
        self.combo_metodo.addItems(["spline", "negexp", "linear", "media_movil", "media"])
        self.combo_metodo.setCurrentText("spline")
        self.combo_metodo.currentTextChanged.connect(self._on_metodo_estandar_cambiado)

        # Spinbox de ventana para media_movil — aparece solo cuando se elige
        # ese método. Default 10% del largo (estilo ARSTAN), pero el usuario
        # puede sobreescribir con un valor fijo.
        self.spin_ventana_mm = SpinBoxFlechas()
        self.spin_ventana_mm.setRange(3, 999)
        self.spin_ventana_mm.setValue(11)
        self.spin_ventana_mm.setSuffix(" años")
        self.spin_ventana_mm.setMinimumWidth(140)
        self.spin_ventana_mm.setToolTip(
            "Ventana de la media móvil (en años). Por convención impar.\n"
            "Valores chicos (5–15) → tendencia local más sensible.\n"
            "Valores grandes (30+) → tendencia más suave (similar a spline rígido)."
        )
        self.spin_ventana_mm.setVisible(False)

        fila_metodo = QHBoxLayout()
        fila_metodo.setContentsMargins(0, 0, 0, 0)
        fila_metodo.setSpacing(6)
        fila_metodo.addWidget(self.combo_metodo, 1)
        fila_metodo.addWidget(self.spin_ventana_mm)
        contenedor_metodo = QWidget()
        contenedor_metodo.setLayout(fila_metodo)
        form.addRow("Estandarización:", contenedor_metodo)

        self.combo_agreg = QComboBox()
        # Texto en español visible para el usuario, pero el VALOR interno
        # (userData) se mantiene en inglés para no romper la lógica de
        # construcción de la cronología. Se lee con currentData().
        self.combo_agreg.addItem("Biponderada (biweight)", "biweight")
        self.combo_agreg.addItem("Media", "mean")
        self.combo_agreg.addItem("Mediana", "median")
        self.combo_agreg.setCurrentIndex(0)  # biponderada por defecto
        self.combo_agreg.setToolTip(
            "Cómo se combinan las series individuales en UNA cronología media:\n\n"
            "• Biponderada (biweight): media robusta de Tukey. Baja el peso\n"
            "  de valores atípicos progresivamente. Es el estándar en\n"
            "  dendrocronología (lo que usa ARSTAN por defecto).\n"
            "• Media: media aritmética simple. Sensible a valores atípicos.\n"
            "• Mediana: el valor central. Robusta pero descarta magnitud."
        )
        form.addRow("Agregación:", self.combo_agreg)

        # ── Transformación logarítmica (estilo COFECHA) ──────────────
        # Aplica log(índice + media/6) antes del modelo AR, igual que
        # COFECHA (Holmes 1983). Comprime los anillos anchos y suele subir
        # la correlación de cofechado. Debe usarse por igual en la
        # cronología y en las series (DPI lo hace automático al cofechar).
        self.chk_log_crono = QCheckBox("Transformación logarítmica (estilo COFECHA)")
        self.chk_log_crono.setChecked(False)
        self.chk_log_crono.setToolTip(
            "Aplica log(índice + media/6) antes del modelo autorregresivo,\n"
            "igual que COFECHA (opción 'Series transformed to logarithms').\n\n"
            "Comprime los anillos anchos y normalmente sube la correlación\n"
            "de cofechado, acercándola a los valores de COFECHA. Al cofechar,\n"
            "DPI estandariza las series con log automáticamente si la\n"
            "cronología activa se construyó con esta opción.\n\n"
            "Solo aplica a cronologías 'standard' y 'residual' (no 'raw')."
        )
        form.addRow("", self.chk_log_crono)

        # Etiqueta de solape con descripción al pasar el mouse
        lbl_overlap = QLabel("Solape mínimo:")
        lbl_overlap.setToolTip(
            "Cantidad mínima de años en común que dos series deben tener\n"
            "para calcular la correlación entre ellas.\n\n"
            "Valores chicos (5–10) → incluye más pares pero correlaciones\n"
            "menos confiables. Valores grandes (30+) → solo pares con\n"
            "buen solape, más confiable pero descarta series cortas."
        )
        self.spin_min_overlap = SpinBoxFlechas()
        self.spin_min_overlap.setRange(2, 500)
        self.spin_min_overlap.setValue(10)
        self.spin_min_overlap.setToolTip(lbl_overlap.toolTip())
        form.addRow(lbl_overlap, self.spin_min_overlap)

        self.spin_shift = SpinBoxFlechas()
        self.spin_shift.setRange(0, 10)
        self.spin_shift.setValue(5)
        form.addRow("Desfase auto máx.:", self.spin_shift)

        # ── Ventana móvil para Rbar / EPS ─────────────────────────────
        # Permite reproducir el formato de ARSTAN (ventana de 50 años con
        # paso de 25) para comparar y reportar en publicaciones. Con
        # ventana chica (15) y paso 1 se obtiene la curva año a año suave.
        lbl_ventana_eps = QLabel("Ventana Rbar/EPS:")
        lbl_ventana_eps.setToolTip(
            "Tamaño de la ventana móvil (en años) para calcular Rbar y EPS.\n\n"
            "• 50 años → formato estándar de ARSTAN (recomendado para\n"
            "  comparar y para publicaciones).\n"
            "• 15 años o menos → curva más detallada año a año, útil para\n"
            "  ver la evolución fina de la señal común.\n\n"
            "Ventanas grandes promedian más datos y dan valores más estables."
        )
        self.spin_ventana_eps = SpinBoxFlechas()
        self.spin_ventana_eps.setRange(10, 200)
        self.spin_ventana_eps.setValue(50)
        self.spin_ventana_eps.setSingleStep(5)
        self.spin_ventana_eps.setSuffix(" años")
        self.spin_ventana_eps.setToolTip(lbl_ventana_eps.toolTip())
        form.addRow(lbl_ventana_eps, self.spin_ventana_eps)

        lbl_paso_eps = QLabel("Paso Rbar/EPS:")
        lbl_paso_eps.setToolTip(
            "Cada cuántos años se desliza la ventana móvil.\n\n"
            "• 25 años → formato estándar de ARSTAN (la ventana se mueve\n"
            "  en saltos de 25 años, generando pocos valores espaciados).\n"
            "• 1 año → un valor por cada año (curva continua y suave).\n\n"
            "Para reproducir ARSTAN usa ventana 50 y paso 25."
        )
        self.spin_paso_eps = SpinBoxFlechas()
        self.spin_paso_eps.setRange(1, 100)
        self.spin_paso_eps.setValue(25)
        self.spin_paso_eps.setSuffix(" años")
        self.spin_paso_eps.setToolTip(lbl_paso_eps.toolTip())
        form.addRow(lbl_paso_eps, self.spin_paso_eps)

        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Nombre de cronología")
        form.addRow("Nombre:", self.input_nombre)

        # Fila superior: Configuración (≈1/3 del ancho) e Información /
        # metadatos (≈2/3) lado a lado. Antes estaban apiladas y la
        # Configuración ocupaba todo el ancho; ponerlas en fila libera alto
        # para que el gráfico de abajo sea más grande.
        box_info = QGroupBox("Información / metadatos")
        info_layout = QVBoxLayout(box_info)
        self.txt_info = QTextEdit()
        self.txt_info.setReadOnly(True)
        self.txt_info.setMinimumHeight(140)
        info_layout.addWidget(self.txt_info)

        fila_cfg_info = QHBoxLayout()
        fila_cfg_info.addWidget(box_cfg, 1)    # ≈ un tercio
        fila_cfg_info.addWidget(box_info, 2)   # ≈ dos tercios
        right_layout.addLayout(fila_cfg_info, 0)

        self.grafico = pg.PlotWidget(title="Cronología")
        _agregar_hover_anio(self.grafico)
        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        right_layout.addWidget(self.grafico, 1)
        right_layout.addWidget(_crear_barra_zoom(self.grafico))

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # Estado inicial: aplicar enable/disable según el tipo seleccionado
        self._on_tipo_cronologia_cambiado(self.combo_tipo.currentText())

    def _on_tipo_cronologia_cambiado(self, tipo: str):
        """Habilita/deshabilita el combo de estandarización según el tipo.

        Cuando tipo='raw' la estandarización no aplica (la serie se devuelve
        tal cual sin detrending), así que el combo se deshabilita visualmente
        para que el usuario sepa que no tiene efecto.
        """
        if not hasattr(self, "combo_metodo"):
            return
        es_raw = (tipo or "").lower() == "raw"
        self.combo_metodo.setEnabled(not es_raw)
        if hasattr(self, "spin_ventana_mm"):
            # También deshabilitar el spinbox de ventana si tipo=raw
            self.spin_ventana_mm.setEnabled(not es_raw)
        if hasattr(self, "chk_log_crono"):
            # El log no aplica a 'raw' (no hay índice que transformar)
            self.chk_log_crono.setEnabled(not es_raw)
        if es_raw:
            self.combo_metodo.setToolTip(
                "No aplica con tipo='raw' — la serie se usa sin estandarización."
            )
        else:
            self.combo_metodo.setToolTip("")

    def _on_metodo_estandar_cambiado(self, metodo: str):
        """Muestra el spinbox de ventana solo cuando se elige media_movil."""
        if hasattr(self, "spin_ventana_mm"):
            self.spin_ventana_mm.setVisible(
                (metodo or "").lower() in {"media_movil", "moving_average", "ma"}
            )

    def nueva_cronologia(self):
        """Limpia todo para empezar una cronología nueva: series cargadas,
        cronología generada, gráfico e información."""
        if self._series_cronologia or self.cronologia_df is not None:
            resp = QMessageBox.question(
                self, "Nueva cronología",
                "¿Limpiar todo (series cargadas y cronología generada) para "
                "empezar una nueva?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes:
                return
        self._series_cronologia.clear()
        self.cronologia_df = None
        self.cronologia_meta = {}
        self.eps_movil = None
        self.lista_series.clear()
        self.grafico.clear()
        self.txt_info.setPlainText("Sin cronología cargada.")
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setEnabled(False)

    def refresh_series(self, marcar_todas: bool = False):
        """Refresca la lista de series disponibles.

        Si `marcar_todas` es True (al cargar series nuevas), todas las series
        quedan SELECCIONADAS automáticamente — el propósito de cargarlas es
        construir la cronología con ellas, así que conviene que aparezcan
        marcadas. En refrescos normales se conserva el estado de selección.
        """
        self.lista_series.blockSignals(True)
        checked = {
            self.lista_series.item(i).text()
            for i in range(self.lista_series.count())
            if self.lista_series.item(i).checkState() == Qt.CheckState.Checked
        }
        self.lista_series.clear()
        for nombre in sorted(self._series_cronologia.keys()):
            if nombre.startswith("📚 "):
                continue
            item = QListWidgetItem(nombre)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            marcar = marcar_todas or (nombre in checked)
            item.setCheckState(
                Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
            self.lista_series.addItem(item)
        self.lista_series.blockSignals(False)
        self._sincronizar_estado_botones()

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
        self._sincronizar_estado_botones()

    def _sincronizar_estado_botones(self):
        hay_crono = self.cronologia_df is not None and not self.cronologia_df.empty
        self.btn_exportar.setEnabled(hay_crono)
        self.btn_usar.setEnabled(hay_crono)
        self.btn_comparar.setEnabled(hay_crono)
        # EPS/Rbar solo si hay datos móviles calculados
        tiene_eps_movil = bool((self.cronologia_meta or {}).get("EPS_movil"))
        self.btn_eps_rbar.setEnabled(hay_crono and tiene_eps_movil)
        if hay_crono:
            meta = self.cronologia_meta
            self.lbl_estado.setText(
                f"Cronología cargada: {meta.get('nombre', 'Cronología')} | "
                f"tipo={meta.get('tipo_cronologia', 'raw')} | "
                f"método={meta.get('metodo_estandarizacion', 'raw')} | "
                f"agregación={meta.get('agregacion', 'mean')}"
            )
        else:
            self.lbl_estado.setText("Sin cronología cargada.")

    def _mostrar_eps_rbar(self):
        """Muestra el diálogo EPS/Rbar de la cronología actual del diálogo.
        Reutiliza la misma función que el botón EPS/Rbar del panel."""
        nombre = (self.cronologia_meta or {}).get("nombre", "Cronología")
        _mostrar_dialogo_eps_rbar(self, self.cronologia_meta or {}, nombre)

    def _cargar_series_desde_panel(self):
        """Carga series SOLO en la ventana de cronología."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Series", _ultima_carpeta(),
            "Series compatibles (*.rwl *.txt *.wid *.csv *.tsv *.xlsx *.xls *.ods *.cat *.cmp);;Todos (*.*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if rutas:
            _ultima_carpeta(rutas[0])
        for ruta in rutas:
            try:
                with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                    primeras = f.read(500)
                if "=N" in primeras and "=I" in primeras:
                    series_ext = leer_formato_compacto(ruta)
                    for sid, df in series_ext.items():
                        if sid not in self._series_cronologia:
                            self._series_cronologia[sid] = df.copy()
                    continue
                ext = os.path.splitext(ruta)[1].lower()
                if ext == ".wid":
                    df, sid = leer_wid(ruta)
                    if sid not in self._series_cronologia:
                        self._series_cronologia[sid] = df.copy()
                elif ext in (".csv", ".tsv") or _es_planilla(ext):
                    df, sid = leer_tabular(ruta)
                    if sid not in self._series_cronologia:
                        self._series_cronologia[sid] = df.copy()
                else:
                    try:
                        series_ext = leer_tucson_multi(ruta)
                        for sid, df in series_ext.items():
                            if sid not in self._series_cronologia:
                                self._series_cronologia[sid] = df.copy()
                    except Exception:
                        df, sid = leer_tabular(ruta)
                        if sid not in self._series_cronologia:
                            self._series_cronologia[sid] = df.copy()
            except Exception as exc:
                QMessageBox.warning(self, "Error", f"No se pudo cargar:\n{exc}")
        # Marcar automáticamente todas las series tras cargarlas.
        self.refresh_series(marcar_todas=True)

    def generar_cronologia(self):
        nombres = self._series_marcadas()
        if not nombres:
            QMessageBox.warning(self, "Atención", "Seleccione al menos una serie.")
            return

        tipo_sel = self.combo_tipo.currentText()
        metodo = self.combo_metodo.currentText()
        # currentData() devuelve el valor interno en inglés (biweight/mean/
        # median) aunque el texto visible esté en español.
        agreg = self.combo_agreg.currentData() or "biweight"
        aplicar_log = bool(self.chk_log_crono.isChecked())
        nombre_base = self.input_nombre.text().strip() or "Cronologia"

        tipos = ["raw", "standard", "residual"] if tipo_sel == "Todas" else [tipo_sel]

        # ── Series cuya curva de ajuste cruza cero ──────────────────────
        # Es el «dirty dog» de ARSTAN. DPI nunca produce índices negativos
        # porque reemplaza la tendencia por la media donde sale <= 0, pero
        # hacerlo en silencio deja años cuyo índice no significa lo mismo que
        # el del resto de la serie. Acá se detectan, se cuentan, y se le da al
        # usuario la opción de estandarizarlas con otro método.
        self._metodo_alterno = None
        self._metodos_por_serie = {}
        self._series_alternas = []
        self._diag_negativas = {}
        if tipo_sel != "raw" and metodo != "media":
            vmm0 = (self.spin_ventana_mm.value()
                    if metodo == "media_movil" else None)
            try:
                probl = detectar_series_problematicas(
                    self._series_cronologia, nombres, metodo, ventana_mm=vmm0)
            except Exception:
                probl = {}
            if probl:
                # Maestra de referencia con las series SANAS, para poder
                # comparar métodos sin que las problemáticas se autoevalúen.
                sanas = [n for n in nombres if n not in probl]
                maestra = None
                try:
                    cols = []
                    for n in sanas:
                        idx = _detrend_serie_indice(
                            self._series_cronologia[n]["Ancho_mm"], metodo,
                            ventana_mm=vmm0)
                        if len(idx) > 10:
                            idx.name = n
                            cols.append(idx)
                    if cols:
                        maestra = pd.concat(cols, axis=1).mean(axis=1).dropna()
                except Exception:
                    maestra = None
                if maestra is not None and len(maestra) > 30:
                    dlg = DialogoCurvasNegativas(
                        self._series_cronologia, list(probl), maestra, metodo,
                        parent=self, ventana_mm=vmm0)
                    self._diag_negativas = probl
                    if dlg.exec():
                        porserie = dlg.metodos_por_serie()
                        distintos = {n: m for n, m in porserie.items()
                                     if m and m != metodo}
                        if distintos:
                            self._metodos_por_serie = distintos
                            self._series_alternas = list(distintos)
                            unicos = set(distintos.values())
                            self._metodo_alterno = (unicos.pop()
                                                    if len(unicos) == 1
                                                    else None)

        progreso = QProgressDialog("Generando cronología...", None, 0, 100, self)
        progreso.setWindowTitle("Procesando")
        progreso.setWindowModality(Qt.WindowModality.WindowModal)
        progreso.setMinimumDuration(0)
        progreso.setMaximum(100)
        progreso.setValue(0)
        progreso.setCancelButton(None)
        QApplication.processEvents()

        resultados = {}
        for i, tipo in enumerate(tipos):
            pct_inicio = int(i * 50 / len(tipos))
            progreso.setLabelText(f"Generando cronología {tipo}... ({i+1}/{len(tipos)})")
            progreso.setValue(pct_inicio)
            QApplication.processEvents()

            try:
                # Solo pasar ventana_mm si el método es media_movil
                vmm = (self.spin_ventana_mm.value()
                       if metodo == "media_movil" else None)
                df, meta = _construir_cronologia_desde_series(
                    self._series_cronologia, nombres, tipo, metodo, agreg,
                    ventana_mm=vmm, aplicar_log=aplicar_log,
                    metodo_alterno=self._metodo_alterno,
                    series_alternas=self._series_alternas,
                    metodos_por_serie=self._metodos_por_serie,
                )
                meta["curvas_negativas"] = {
                    n: {"n_parches": d["n_parches"], "total": d["total"],
                        "tramos": d["tramos"],
                        "indice_max": d["indice_max"]}
                    for n, d in (self._diag_negativas or {}).items()}
                meta["metodo_alterno"] = self._metodo_alterno
                meta["series_alternas"] = list(self._series_alternas)
                meta["metodos_por_serie"] = dict(self._metodos_por_serie)
                nombre = f"{nombre_base}_{tipo}" if len(tipos) > 1 else nombre_base
                meta["nombre"] = nombre

                # Rbar y EPS ahora vienen calculados desde dentro de
                # _construir_cronologia_desde_series sobre las series
                # DETRENDADAS (comparable con ARSTAN). Antes acá se
                # sobrescribían usando series raw, lo que inflaba el Rbar
                # porque las tendencias decadales hacen covariar las
                # series brutas a largo plazo.

                resultados[tipo] = (df, meta)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Error en cronología {tipo}:\n{exc}")

        if not resultados:
            progreso.close()
            return

        progreso.setLabelText("Calculando EPS / Rbar móvil...")
        progreso.setValue(50)
        QApplication.processEvents()

        # Callback de progreso para mantener la UI responsiva durante el
        # cálculo de EPS / Rbar móvil (que itera sobre muchos años con
        # ventana móvil — es la parte más lenta).
        def _cb_progreso(pct):
            progreso.setValue(50 + int(pct * 0.45))
            QApplication.processEvents()

        # Determinar paso para muestreo. El usuario configura ventana y paso
        # en la UI (default 50/25 estilo ARSTAN para comparación directa).
        ventana_eps = self.spin_ventana_eps.value()
        paso_eps = self.spin_paso_eps.value()

        eps_df = calcular_eps_rbar_movil(
            self._series_cronologia, nombres, window=ventana_eps,
            paso=paso_eps, progreso=_cb_progreso,
        )
        self.eps_movil = eps_df

        if len(resultados) > 1:
            frames = []
            for tipo, (df, meta) in resultados.items():
                col = meta.get("columna_valor", tipo.capitalize())
                frames.append(df[[col]].rename(columns={col: tipo.capitalize()}))
                if "N" in df.columns:
                    frames.append(df[["N"]])
            combined = pd.concat(frames, axis=1)
            combined = combined.loc[:, ~combined.columns.duplicated()]
            last_tipo = list(resultados.keys())[-1]
            _, last_meta = resultados[last_tipo]
            last_meta["nombre"] = nombre_base
            last_meta["tipo_cronologia"] = "todas"
            last_meta["columna_valor"] = "Standard"
            last_meta["columnas_disponibles"] = [t.capitalize() for t in resultados.keys()]
            if not eps_df.empty:
                last_meta["EPS_movil"] = eps_df["EPS"].dropna().to_dict()
                last_meta["Rbar_movil"] = eps_df["Rbar"].dropna().to_dict()
            self.cronologia_df = combined
            self.cronologia_meta = last_meta
        else:
            tipo_unico = list(resultados.keys())[0]
            self.cronologia_df, self.cronologia_meta = resultados[tipo_unico]
            if not eps_df.empty:
                self.cronologia_meta["EPS_movil"] = eps_df["EPS"].dropna().to_dict()
                self.cronologia_meta["Rbar_movil"] = eps_df["Rbar"].dropna().to_dict()

        progreso.setValue(100)
        progreso.close()

        self._pintar_cronologia()
        self._actualizar_info()
        self._sincronizar_estado_botones()

    def cargar_cronologia(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Cargar cronología", _ultima_carpeta(),
            "Cronologías (*.csv *.txt *.xlsx *.ods);;Todos (*.*)"
        )
        if not ruta:
            return
        _ultima_carpeta(ruta)

        try:
            df, meta = _leer_cronologia_guardada(ruta)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo abrir la cronología:\n{exc}")
            return

        meta.setdefault("nombre", os.path.splitext(os.path.basename(ruta))[0])
        meta.setdefault("columna_valor", df.columns[0])
        self.cronologia_df = df
        self.cronologia_meta = meta
        self.input_nombre.setText(meta.get("nombre", "Cronología"))
        self._pintar_cronologia()
        self._actualizar_info()
        self._sincronizar_estado_botones()

    def exportar_cronologia(self):
        if self.cronologia_df is None or self.cronologia_df.empty:
            QMessageBox.warning(self, "Atención", "No hay cronología para exportar.")
            return
        nombre = self.cronologia_meta.get("nombre", "cronologia")
        ruta_default = os.path.join(_ultima_carpeta(), nombre)
        ruta, fmt = QFileDialog.getSaveFileName(
            self, "Exportar cronología", ruta_default,
            "Texto 2 columnas (*.txt);;Tucson (*.rwl);;Excel (*.xlsx);;"
            "LibreOffice (*.ods);;CSV (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not ruta:
            return
        ruta = _asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            _exportar_cronologia_df(self.cronologia_df, ruta)
            meta = dict(self.cronologia_meta)
            meta["archivo"] = os.path.basename(ruta)
            _guardar_metadatos_cronologia(ruta, meta)
            QMessageBox.information(self, "OK", f"Cronología exportada:\n{ruta}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo exportar:\n{exc}")

    def usar_cronologia_en_panel(self):
        if self.cronologia_df is None or self.cronologia_df.empty:
            return
        nombre = self.cronologia_meta.get("nombre", "Cronología")
        self._panel.set_cronologia_activa(self.cronologia_df, self.cronologia_meta, nombre)
        QMessageBox.information(
            self, "OK",
            f"Cronología '{nombre}' activada en el panel de cofechado.\n\n"
            "Aparece en la lista del panel con el prefijo 📚.\n"
            "Marcala junto a una serie y dale Verificar / Buscar / Analizar."
        )

    def comparar_con_cronologia(self):
        """Compara series marcadas contra la cronología activa.

        Bifurca según la cantidad de series marcadas:
          - 1 sola → modo individual: gráfico de r vs desfase, texto con
            top 3 candidatos por score, botón "Tabla detallada"
          - 2 o más → modo batch: diálogo nuevo con tabla resumen
            (una fila por serie) ordenable, con doble clic para drill-down
            al modo individual de cada serie.

        El usuario controla el modo con la cantidad de check marcados
        en el panel, sin botones extra.
        """
        if self.cronologia_df is None or self.cronologia_df.empty:
            QMessageBox.warning(self, "Atención", "Primero cargue o genere una cronología.")
            return
        nombres = self._series_marcadas()
        if len(nombres) < 1:
            QMessageBox.warning(
                self, "Atención",
                "Marque al menos una serie para comparar.\n"
                "(Marque varias para hacer comparación múltiple.)")
            return

        # Si hay más de una serie marcada → modo batch
        if len(nombres) > 1:
            self._comparar_multiple_con_cronologia(nombres)
            return

        # Modo individual (1 sola serie) — comportamiento histórico
        nombre = nombres[0]
        self._comparar_individual_con_cronologia(nombre)

    def _comparar_individual_con_cronologia(self, nombre: str):
        """Modo individual: 1 serie → gráfico + texto + tabla detallada.

        Es el comportamiento histórico, conservado tal cual estaba antes
        del modo batch. Útil para inspección a fondo de una sola serie.
        """
        serie = self._series_cronologia[nombre]
        meta = self.cronologia_meta
        s_a = _serie_transformada_para_comparar(serie, meta)
        col_val = meta.get("columna_valor") or self.cronologia_df.columns[0]
        if col_val not in self.cronologia_df.columns:
            col_val = self.cronologia_df.columns[0]
        s_b = pd.to_numeric(self.cronologia_df[col_val], errors="coerce").dropna()

        # Cálculo de los TRES estadísticos por cada desfase
        shifts, rs, glks, tbps, ns = _estadisticos_por_desfase(
            s_a, s_b,
            self.spin_shift.value(),
            self.spin_min_overlap.value(),
        )

        self.grafico.clear()
        if not shifts:
            self.grafico.setTitle("No se encontraron solapamientos suficientes.")
            return

        # Guardar para que el botón "Ver tabla" pueda abrirla después
        self._ultimo_resultado_comparacion = {
            "nombre_serie": nombre,
            "shifts": shifts, "rs": rs, "glks": glks,
            "tbps": tbps, "ns": ns,
        }

        # Línea de referencia en y=0
        self.grafico.addItem(
            pg.InfiniteLine(pos=0, angle=0,
                             pen=pg.mkPen("#888888", width=1)))

        # Plot principal: r (lo más interpretable visualmente, escala [-1, 1])
        self.grafico.plot(shifts, rs,
                          pen=pg.mkPen("#3388FF", width=2), symbol="o")

        # Score compuesto en cada shift y elección del mejor por score
        scores = [score_compuesto(r, g, t)
                  for r, g, t in zip(rs, glks, tbps)]
        scores_validos = [(i, s) for i, s in enumerate(scores) if np.isfinite(s)]
        if scores_validos:
            idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
        else:
            idx_mejor = int(np.argmax(rs))

        best_shift = shifts[idx_mejor]
        best_r = rs[idx_mejor]
        best_glk = glks[idx_mejor]
        best_tbp = tbps[idx_mejor]
        best_score = scores[idx_mejor]
        best_n = ns[idx_mejor]

        # Punto verde grande en el mejor según score compuesto
        self.grafico.addItem(pg.ScatterPlotItem(
            x=[best_shift], y=[best_r], size=14,
            brush=pg.mkBrush("#5cb85c"), pen=pg.mkPen("w", width=2),
        ))

        self.grafico.setYRange(-1.05, 1.05)
        self.grafico.setTitle(
            f"'{nombre}' vs cronología — mejor desfase: {best_shift}"
            f"  (puntaje={best_score:.3f})"
        )

        # Construir resumen multi-stat para txt_info
        def fmt(x, dec=3):
            return f"{x:.{dec}f}" if np.isfinite(x) else "—"

        # Top 3 desfases por score compuesto, para mostrar candidatos
        top3 = sorted(
            range(len(shifts)),
            key=lambda i: scores[i] if np.isfinite(scores[i]) else -1e9,
            reverse=True,
        )[:3]
        lineas_top = []
        for rank, i in enumerate(top3, start=1):
            lineas_top.append(
                f"    #{rank}  desfase={shifts[i]:+d}  "
                f"r={fmt(rs[i])}  GLK={fmt(glks[i])}  "
                f"t-BP={fmt(tbps[i], 2)}  puntaje={fmt(scores[i])}  "
                f"n={ns[i]}"
            )

        self.txt_info.append(
            f"\nComparación '{nombre}' vs cronología:\n"
            f"  Mejor desfase: {best_shift:+d}\n"
            f"    r       = {fmt(best_r)}\n"
            f"    GLK     = {fmt(best_glk)}\n"
            f"    t-BP    = {fmt(best_tbp, 2)}\n"
            f"    puntaje = {fmt(best_score)}  "
            f"(media geom. de las 3 métricas normalizadas)\n"
            f"    n       = {best_n} años de solape\n"
            f"  Top 3 desfases por puntaje compuesto:\n"
            + "\n".join(lineas_top)
            + "\n"
        )

        # Mostrar el botón "Ver tabla detallada" si está oculto
        if hasattr(self, "_btn_tabla_comparacion"):
            self._btn_tabla_comparacion.setVisible(True)

    def _comparar_multiple_con_cronologia(self, nombres: list[str]):
        """Modo batch: N>1 series → tabla resumen con una fila por serie.

        Para cada serie ejecuta `_estadisticos_por_desfase` (mismo cálculo
        que el modo individual) y guarda el resultado completo + el "mejor"
        según score compuesto + el score en shift=0 para calcular el Δ.

        Al terminar abre `DialogoComparacionMultiple` que permite ordenar
        por cualquier columna y hacer drill-down con doble clic.
        """
        meta = self.cronologia_meta
        col_val = meta.get("columna_valor") or self.cronologia_df.columns[0]
        if col_val not in self.cronologia_df.columns:
            col_val = self.cronologia_df.columns[0]
        s_b = pd.to_numeric(self.cronologia_df[col_val],
                             errors="coerce").dropna()
        max_shift_val = self.spin_shift.value()
        min_overlap_val = self.spin_min_overlap.value()

        # Cursor de espera durante el cálculo (puede tomar segundos con
        # decenas de series y rangos de shift amplios)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        resultados = []
        nombre_crono = meta.get("nombre", "cronología")

        try:
            for nombre in nombres:
                serie = self._series_cronologia[nombre]
                s_a = _serie_transformada_para_comparar(serie, meta)

                shifts, rs, glks, tbps, ns = _estadisticos_por_desfase(
                    s_a, s_b, max_shift_val, min_overlap_val,
                )

                if not shifts:
                    # Serie sin solape suficiente → registrar igualmente
                    # para que el usuario sepa cuáles quedaron fuera
                    resultados.append({
                        "nombre_serie": nombre,
                        "shifts": [], "rs": [], "glks": [],
                        "tbps": [], "ns": [],
                        "mejor_shift": 0,
                        "mejor_score": float("nan"),
                        "mejor_r": float("nan"),
                        "mejor_glk": float("nan"),
                        "mejor_tbp": float("nan"),
                        "mejor_n": 0,
                        "score_shift0": float("nan"),
                    })
                    continue

                # Score compuesto por shift + selección del mejor
                scores = [score_compuesto(r, g, t)
                          for r, g, t in zip(rs, glks, tbps)]
                scores_validos = [
                    (i, s) for i, s in enumerate(scores) if np.isfinite(s)]
                if scores_validos:
                    idx_mejor = max(scores_validos, key=lambda x: x[1])[0]
                else:
                    idx_mejor = int(np.argmax(rs))

                # Score en shift=0 (para calcular Δ vs el mejor).
                # Si shift=0 no está en la lista (no hubo overlap
                # suficiente sin shift), Δ queda NaN.
                if 0 in shifts:
                    idx0 = shifts.index(0)
                    score_shift0 = scores[idx0]
                else:
                    score_shift0 = float("nan")

                resultados.append({
                    "nombre_serie": nombre,
                    "shifts": shifts, "rs": rs, "glks": glks,
                    "tbps": tbps, "ns": ns,
                    "mejor_shift": shifts[idx_mejor],
                    "mejor_score": scores[idx_mejor],
                    "mejor_r": rs[idx_mejor],
                    "mejor_glk": glks[idx_mejor],
                    "mejor_tbp": tbps[idx_mejor],
                    "mejor_n": ns[idx_mejor],
                    "score_shift0": score_shift0,
                    # Series transformadas para el gráfico de detalle
                    "serie_a": s_a,
                    "serie_b": s_b,
                })

                # Refrescar UI para evitar congelamiento percibido en
                # series largas o muchas series. processEvents() es
                # suficiente acá; no necesitamos hilos para N modesto.
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        # Resumen de una línea en txt_info
        n_validas = sum(1 for r in resultados if np.isfinite(r["mejor_score"]))
        self.txt_info.append(
            f"\nComparación múltiple ({len(resultados)} series) vs "
            f"cronología '{nombre_crono}':\n"
            f"  {n_validas} con resultado válido  ·  "
            f"{len(resultados) - n_validas} sin solape suficiente\n"
            f"  → ver tabla resumen para análisis detallado.\n"
        )

        # Abrir el diálogo modal
        dlg = DialogoComparacionMultiple(resultados, nombre_crono, parent=self)
        dlg.exec()

    def _abrir_tabla_comparacion(self):
        """Abre VentanaTablaOffset con los resultados de la última
        `comparar_con_cronologia`. Reutilizamos exactamente la misma tabla
        que ya existe para series flotantes (con colores por umbral,
        ordenable, score compuesto destacado)."""
        datos = getattr(self, "_ultimo_resultado_comparacion", None)
        if not datos:
            QMessageBox.information(
                self, "Sin datos",
                "Ejecuta primero una comparación con la cronología.")
            return
        dlg = VentanaTablaOffset(
            datos["shifts"], datos["rs"],
            glks=datos["glks"], tbps=datos["tbps"], ns=datos["ns"],
            parent=self,
        )
        dlg.setWindowTitle(
            f"Resultados detallados — '{datos['nombre_serie']}' vs cronología"
        )
        dlg.exec()

    def _hacer_leyenda_clicable(self, grafico, curvas: dict):
        """Hace clicables los ítems de la leyenda para mostrar/ocultar cada
        curva, como en los otros gráficos del programa. Al hacer clic en el
        nombre, la curva se oculta/muestra y la etiqueta se atenúa."""
        leyenda = grafico.plotItem.legend
        if leyenda is None:
            return
        for sample, label in list(leyenda.items):
            nombre = label.text
            curva = curvas.get(nombre)
            if curva is None:
                continue

            def _toggle(evt, c=curva, lbl=label, nm=nombre):
                visible = not c.isVisible()
                c.setVisible(visible)
                lbl.setText(nm, color="#ffffff" if visible else "#777777")
                try:
                    evt.accept()
                except Exception:
                    pass

            sample.mouseClickEvent = _toggle
            label.mouseClickEvent = _toggle

    def _pintar_cronologia(self):
        if self.cronologia_df is None or self.cronologia_df.empty:
            self.grafico.clear()
            return
        self.grafico.clear()

        # Recrear la leyenda en cada repintado (clear() deja entradas viejas).
        if self.grafico.plotItem.legend is not None:
            try:
                self.grafico.plotItem.legend.scene().removeItem(
                    self.grafico.plotItem.legend)
            except Exception:
                pass
            self.grafico.plotItem.legend = None
        self.grafico.addLegend(offset=(10, 10))

        curvas = {}  # nombre -> curva, para la leyenda clicable

        colores_tipo = {"Raw": "#FF8C00", "Standard": "#3388FF", "Residual": "#5cb85c"}

        cols_disponibles = self.cronologia_meta.get("columnas_disponibles", [])
        if not cols_disponibles:
            col_val = self.cronologia_meta.get("columna_valor", "")
            if col_val and col_val in self.cronologia_df.columns:
                cols_disponibles = [col_val]
            else:
                cols_disponibles = [c for c in self.cronologia_df.columns
                                    if c.lower() not in ("n", "sd", "se")][:1]

        x = self.cronologia_df.index.to_numpy(dtype=float)
        for col in cols_disponibles:
            if col in self.cronologia_df.columns:
                y = pd.to_numeric(self.cronologia_df[col], errors="coerce").to_numpy(dtype=float)
                color = colores_tipo.get(col, "#FF8C00")
                curvas[col] = self.grafico.plot(
                    x, y, pen=pg.mkPen(color, width=2), name=col)

        self.grafico.showGrid(x=True, y=True, alpha=0.3)
        self.grafico.autoRange()

        if self.eps_movil is not None and not self.eps_movil.empty:
            try:
                eps = self.eps_movil["EPS"].dropna()
                if not eps.empty:
                    curvas["EPS"] = self.grafico.plot(
                        eps.index.to_numpy(), eps.to_numpy(),
                        pen=pg.mkPen("#5cb85c", width=1, style=Qt.PenStyle.DashLine),
                        name="EPS"
                    )
                    self.grafico.addItem(pg.InfiniteLine(
                        pos=0.85, angle=0,
                        pen=pg.mkPen("#888888", style=Qt.PenStyle.DashLine)))
            except Exception:
                pass

        # Hacer la leyenda clicable (mostrar/ocultar series)
        self._hacer_leyenda_clicable(self.grafico, curvas)

    def _actualizar_info(self):
        if self.cronologia_df is None or self.cronologia_df.empty:
            self.txt_info.setPlainText("Sin cronología cargada.")
            return
        df = self.cronologia_df
        meta = self.cronologia_meta or {}

        # Columna de índice (Raw/Standard/Residual)
        col_val = meta.get("columna_valor", "")
        if col_val not in df.columns:
            cands = [c for c in df.columns if c not in ("N", "SD", "SE")]
            col_val = cands[0] if cands else df.columns[0]
        serie = pd.to_numeric(df[col_val], errors="coerce").dropna()
        x = serie.to_numpy(dtype=float)

        # ── Cobertura ──
        anio_ini = int(serie.index.min())
        anio_fin = int(serie.index.max())
        n_anios = len(serie)
        n_series = meta.get("n_series", 0)

        # Profundidad de muestreo (series por año)
        if "N" in df.columns:
            ns = pd.to_numeric(df["N"], errors="coerce").dropna()
            depth_min = int(ns.min()) if not ns.empty else 0
            depth_max = int(ns.max()) if not ns.empty else 0
            depth_mean = float(ns.mean()) if not ns.empty else 0.0
        else:
            depth_min = depth_max = 0
            depth_mean = float(meta.get("sample_depth_mean", 0.0))

        # Año desde el cual EPS ≥ 0.85
        primer_conf = None
        if (self.eps_movil is not None and not self.eps_movil.empty
                and "EPS" in self.eps_movil.columns):
            eps_s = pd.to_numeric(self.eps_movil["EPS"], errors="coerce").dropna()
            ok = eps_s[eps_s >= 0.85]
            if not ok.empty:
                primer_conf = int(ok.index.min())

        # ── SSS: desde qué año la cronología conserva el 85 % de su señal ──
        # La EPS compara contra una población infinita; la SSS, contra la
        # colección que realmente se tiene. Para decidir el período usable la
        # segunda es la pregunta correcta, porque no supone nada sobre
        # árboles que no se muestrearon.
        # La SSS y la EPS se calculan con el Rbar EFECTIVO y con el número de
        # ÁRBOLES, no de series. Dos radios del mismo árbol comparten el
        # individuo, no solo el sitio: contarlos como réplica independiente
        # infla los dos estadísticos.
        primer_sss = None
        sss_txt = "—"
        arboles_txt = ""
        try:
            prof = meta.get("sample_depth")
            info = meta.get("rbar_arboles") or {}
            rb_eff = float(info.get("rbar_eff", float("nan")))
            n_arb = int(info.get("n_arboles", 0))
            rb = rb_eff if np.isfinite(rb_eff) else float(
                meta.get("Rbar", float("nan")))
            n_ref = float(n_arb) if n_arb > 1 else float(n_series or 0)
            if prof is not None and len(prof) and np.isfinite(rb) and n_ref > 1:
                prof_s = pd.Series(prof).dropna()
                # La profundidad se escala de radios a árboles con c_eff
                c_eff = float(info.get("c_eff", 1.0)) or 1.0
                prof_arb = np.maximum(prof_s.to_numpy(dtype=float) / c_eff, 1.0)
                vals = calcular_sss(prof_arb, n_ref, rb)
                sss_s = pd.Series(vals, index=prof_s.index).dropna()
                ok_s = sss_s[sss_s >= 0.85]
                if not ok_s.empty:
                    primer_sss = int(ok_s.index.min())
                    sss_txt = str(primer_sss)
                else:
                    sss_txt = "nunca alcanza 0.85"
            if n_arb:
                arboles_txt = (
                    f"{n_series} series de <b>{n_arb} árboles</b> "
                    f"({info.get('c_eff', 1):.2f} radios por árbol)<br>"
                    f"Rbar entre radios del mismo árbol: "
                    f"<b>{info.get('rbar_wt', float('nan')):.3f}</b> &nbsp;|&nbsp; "
                    f"entre árboles: <b>{info.get('rbar_bt', float('nan')):.3f}</b>"
                    f" &nbsp;|&nbsp; efectivo: <b>{rb_eff:.3f}</b><br>")
        except Exception:
            pass

        # ── Señal común ──
        rbar = float(meta.get("Rbar", float("nan")))
        eps = float(meta.get("EPS", float("nan")))
        n_eff = meta.get("sample_depth_mean") or n_series or 0
        if np.isfinite(rbar) and rbar < 1.0 and n_eff:
            snr = float(n_eff * rbar / (1.0 - rbar))
        else:
            snr = float("nan")

        # ── Estadística de la serie ──
        media = float(np.mean(x)) if len(x) else float("nan")
        de = float(np.std(x, ddof=1)) if len(x) > 1 else float("nan")
        ms = _sensibilidad_media(x)
        ar1 = _autocorrelacion_ar1(x)

        def f(v, dec=3):
            return "—" if v is None or not np.isfinite(v) else f"{v:.{dec}f}"

        conf_txt = (f"{primer_conf}" if primer_conf is not None
                    else "— (sin EPS móvil)")
        depth_txt = (f"{depth_min}–{depth_max} (media {depth_mean:.1f})"
                     if depth_max else f"media {depth_mean:.1f}")

        html = f"""
        <div style='font-size:11px;'>
        <b>Identificación</b><br>
        Nombre: <b>{meta.get('nombre', 'Cronología')}</b><br>
        Tipo: {meta.get('tipo_cronologia', 'raw')} &nbsp;|&nbsp;
        Método: {meta.get('metodo_estandarizacion', 'raw')} &nbsp;|&nbsp;
        Agregación: {meta.get('agregacion', 'mean')}<br>
        {_html_curvas_negativas(meta)}
        <br>
        <b>Cobertura</b><br>
        Período: <b>{anio_ini}–{anio_fin}</b> ({n_anios} años)<br>
        Series usadas: {n_series}<br>
        Profundidad de muestreo: {depth_txt}<br>
        EPS ≥ 0.85 desde: <b>{conf_txt}</b><br>
        {arboles_txt}
        SSS ≥ 0.85 desde: <b>{sss_txt}</b>
        &nbsp;<span style='color:#999;'>(señal conservada respecto de la
        colección completa)</span><br>
        <br>
        <b>Señal común</b><br>
        Rbar (inter-series): <b>{f(rbar)}</b><br>
        EPS: <b>{f(eps)}</b><br>
        SNR (señal/ruido): {f(snr, 2)}<br>
        <br>
        <b>Estadística de la serie</b><br>
        Media: {f(media)} &nbsp;|&nbsp; DE: {f(de)}<br>
        Sensibilidad media (MS): <b>{f(ms)}</b><br>
        Autocorrelación AR1: {f(ar1)}<br>
        <br>
        <span style='color:#888;'>Archivo: {meta.get('archivo', '—')}</span>
        </div>
        """
        self.txt_info.setHtml(html)
