"""Componentes de la interfaz de co-datación de DPI."""

import os
import numpy as np
import pandas as pd
import pyqtgraph as pg
from dpi.ui.configuracion import ultima_carpeta
from modulo_widgets import _agregar_hover_anio
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QDialog
from PyQt6.QtCore import Qt
from estilos import color_secundario
import estilos_graficos as _gr
from dpi.formatos.planillas import es_planilla, escribir_excel
from dpi.formatos.exportacion import asegurar_extension
from dpi.infraestructura.escritura import ruta_atomica


from dpi.ui.configuracion import carpeta_codatacion as _ultima_carpeta



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



def _color_compuesto(s: float) -> str:
    if not np.isfinite(s): return "#666666"
    if s >= 0.60: return "#28a745"   # verde fuerte
    if s >= 0.40: return "#5cb85c"   # verde
    if s >= 0.20: return "#ffc107"   # amarillo
    if s >= -0.20: return "#fd7e14"  # naranja (zona ambigua cercana a 0)
    return "#dc3545"                  # rojo (anti-correlación)



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
        f"<span style='color:{color_secundario()};'>Año <b>{int(year)}</b> (±{mitad} años) ·</span>&nbsp;&nbsp;"
        f"<b>r</b>=<span style='color:{_color_r(r)}; font-weight:bold;'>{_f(r, 2)}</span>&nbsp;&nbsp;"
        f"<b>GLK</b>=<span style='color:{_color_glk(glk)}; font-weight:bold;'>{_f(glk, 2)}</span>"
        f"<span style='color:{color_secundario()};'>{sig}</span>&nbsp;&nbsp;"
        f"<b>t-BP</b>=<span style='color:{_color_tbp(t_bp)}; font-weight:bold;'>{_f(t_bp, 1)}</span>"
        f"&nbsp;&nbsp;<span style='color:{color_secundario()};'>n={int(n)}</span>"
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
        f"<span style='color:{color_secundario()};'>Global (n={n}) ·</span>&nbsp;&nbsp;"
        f"<b>r</b>=<span style='color:{_color_r(r)}; font-weight:bold;'>{_f(r, 2)}</span>&nbsp;&nbsp;"
        f"<b>GLK</b>=<span style='color:{_color_glk(glk)}; font-weight:bold;'>{_f(glk, 2)}</span>"
        f"<span style='color:{color_secundario()};'>{glk_sig}</span>&nbsp;&nbsp;"
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
        f"<span style='color:{color_secundario()}; font-size:11px;'>"
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
    _gr.aplicar_a_pyqtgraph(plot_eps)
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
        _gr.aplicar_a_pyqtgraph(plot_rbar)
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
        ruta = asegurar_extension(ruta, fmt)
        _ultima_carpeta(ruta)
        try:
            todos_anios = sorted(set(eps_dict.keys()) | set(rbar_dict.keys()))
            df_export = pd.DataFrame({
                "Anio": [int(a) for a in todos_anios],
                "EPS": [eps_dict.get(a, float("nan")) for a in todos_anios],
                "Rbar": [rbar_dict.get(a, float("nan")) for a in todos_anios],
            })
            ext = os.path.splitext(ruta)[1].lower()
            if es_planilla(ext):
                escribir_excel(df_export, ruta)
            else:
                with ruta_atomica(ruta) as temporal:
                    df_export.to_csv(temporal, index=False,
                                     sep=";" if ext == ".csv" else "\t",
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


ESTILO_CHK_COFECHA = (
    "QCheckBox::indicator{width:14px; height:14px; border:2px solid #888; "
    "border-radius:2px; background:transparent;}"
    "QCheckBox::indicator:hover{border:2px solid #FF8C00;}"
    "QCheckBox::indicator:checked{border:2px solid #FF8C00; background:#FF8C00;}"
)
