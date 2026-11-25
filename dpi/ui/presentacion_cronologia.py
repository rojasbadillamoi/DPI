"""Operaciones de interfaz extraídas; reciben explícitamente el contexto de la vista."""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from dpi.ciencia.estadistica import sensibilidad_media, autocorrelacion_lag1, calcular_sss
from PyQt6.QtCore import Qt
from estilos import color_secundario
from dpi.ui.series_util import _html_curvas_negativas

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
    ms = sensibilidad_media(x, serie.index)
    ar1 = autocorrelacion_lag1(x, serie.index)

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
    &nbsp;<span style='color:{color_secundario()};'>(señal conservada respecto de la
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
    <span style='color:{color_secundario()};'>Archivo: {meta.get('archivo', '—')}</span>
    </div>
    """
    self.txt_info.setHtml(html)
