"""Representación gráfica de desfases."""
import numpy as np
import pyqtgraph as pg
from estilos import color_secundario
from dpi.ui.series_util import _color_compuesto, _color_glk, _color_r, _color_tbp
from dpi.ciencia.datacion import score_compuesto


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
        f"<span style='color:{color_secundario()};'>"
        f"💡 Pasá el mouse sobre las barras para ver r/GLK/t-BP/n de cada shift. "
        f"La fecha verdadera es donde las TRES métricas son altas simultáneamente — "
        f"si solo una es alta, suele ser coincidencia.</span>"
        f"</div>"
    )
    self.lbl_stats.setVisible(True)
