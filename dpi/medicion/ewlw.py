"""Componentes de medición de DPI."""

import math
import numpy as np
from dpi.medicion.calculo import calcular_anillos, puntos_desde_geometria
from dpi.medicion.modelo import TipoMarca


def _calcular_ewlw_posiciones(sig_prog, gray, coords, saltos, banda,
                              cancel_flag=None, med_a_cor=True):
    """
    Detecta EW/LW procesando el perfil de intensidad gris PIXEL A PIXEL
    a lo largo de cada anillo completo. Inserta un límite en TODOS los anillos.

    Para cada anillo:
      1. Extrae el perfil continuo de intensidad gris px a px a lo largo
         del camino (promediando en banda perpendicular en cada punto).
      2. Suaviza con Savitzky-Golay.
      3. Encuentra la primera derivada más negativa.
      4. El punto de mayor oscurecimiento es el límite EW/LW.

    Corre en hilo secundario. Devuelve lista de (insert_at, px, py).
    Si cancel_flag no es None, cancela entre anillos y devuelve resultados
    parciales; al completar emite el progreso final de la ruta cancelable.
    """
    from scipy.signal import savgol_filter

    h, w = gray.shape
    n = len(coords)
    inserciones = []

    puntos = puntos_desde_geometria(coords, saltos)
    anillos = [list(range(a.indice_inicio, a.indice_fin + 1))
               for a in calcular_anillos(puntos, 1) if a.completo]

    n_anillos = len(anillos)

    def cancelado():
        return cancel_flag() if callable(cancel_flag) else bool(cancel_flag and cancel_flag.get("stop"))

    for a_num, anillo_idxs in enumerate(anillos):
        if cancelado():
            return inserciones

        if sig_prog is not None:
            pct = int(a_num * 100 / max(1, n_anillos))
            sig_prog.emit(pct, f"Anillo {a_num + 1}/{n_anillos}")

        if len(anillo_idxs) < 2:
            continue

        # Si ya tiene ew_lw, saltar
        if any(puntos[j].tipo is TipoMarca.EW_LW
               for j in anillo_idxs[1:]):
            continue

        # ── Construir perfil pixel a pixel ──────────────────────────────
        # Para cada punto a lo largo del camino del anillo,
        # promediamos los valores de gris en la banda perpendicular.
        perfil_vals = []   # valor gris en cada muestra
        perfil_pos  = []   # (px, py, seg_idx) en cada muestra

        for k in range(1, len(anillo_idxs)):
            if cancelado():
                return []
            ip = anillo_idxs[k - 1]
            ic = anillo_idxs[k]
            if ic >= n:
                break
            # Saltar quiebres y espacios (pero no ew_lw que ya filtramos)
            if puntos[ic].tipo.excluye_intensidad:
                continue

            x0, y0 = coords[ip]
            x1, y1 = coords[ic]
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len < 1:
                continue

            ux  = (x1 - x0) / seg_len
            uy  = (y1 - y0) / seg_len
            perp_x, perp_y = -uy, ux

            # Una muestra cada pixel a lo largo del segmento
            n_s  = max(2, int(round(seg_len)))
            ts   = np.linspace(0.0, 1.0, n_s)
            xs_c = x0 + ts * (x1 - x0)   # (n_s,)
            ys_c = y0 + ts * (y1 - y0)

            # Banda perpendicular vectorizada: shape (2b+1, n_s)
            offs  = np.arange(-banda, banda + 1, dtype=np.float32)
            xs_b  = xs_c[np.newaxis, :] + offs[:, np.newaxis] * perp_x  # (2b+1, n_s)
            ys_b  = ys_c[np.newaxis, :] + offs[:, np.newaxis] * perp_y

            # Clip a los bordes de la imagen
            xs_b  = np.clip(xs_b, 0, w - 1).astype(np.int32)
            ys_b  = np.clip(ys_b, 0, h - 1).astype(np.int32)

            # Media por columna (cada columna = una posición a lo largo del camino)
            # shape (n_s,)
            vals_col = gray[ys_b, xs_b].mean(axis=0)

            for j in range(n_s):
                perfil_vals.append(float(vals_col[j]))
                perfil_pos.append((float(xs_c[j]), float(ys_c[j]), ic))

        if len(perfil_vals) < 10:
            continue

        if not med_a_cor:
            perfil_vals.reverse()
            perfil_pos.reverse()
        arr = np.array(perfil_vals, dtype=np.float32)

        # Suavizado con ventana ~10% del anillo, mínimo 5 puntos
        # Ventana más grande → señal más limpia para detectar la transición
        win_ideal = max(5, int(len(arr) * 0.10))
        win = win_ideal if win_ideal % 2 == 1 else win_ideal + 1
        win = min(win, len(arr) if len(arr) % 2 == 1 else len(arr) - 1)
        arr_smooth = savgol_filter(arr, win, 2) if win >= 5 else arr.copy()

        # Algoritmo de detección EW→LW:
        # La transición es EW (claro, valor alto) → LW (oscuro, valor bajo).
        # El punto de límite es donde la pendiente negativa es máxima
        # (primera derivada más negativa = mayor tasa de oscurecimiento).
        # Usamos la primera derivada suavizada en lugar de la segunda.
        d1 = np.gradient(arr_smooth)

        # Rango de búsqueda: 15% al 95% del anillo
        m_ini = max(1, int(len(arr) * 0.15))
        m_fin = max(1, int(len(arr) * 0.05))
        if m_ini + m_fin >= len(arr):
            m_ini, m_fin = 1, 1

        d1_sub = d1[m_ini: len(arr) - m_fin]
        if len(d1_sub) == 0:
            continue

        # Mínimo de la primera derivada = punto de mayor oscurecimiento (EW→LW)
        # Si la derivada es siempre positiva (anillo monotónicamente creciente),
        # usar el umbral del 50% del rango como respaldo
        idx_min_d1 = int(np.argmin(d1_sub)) + m_ini

        # Respaldo: si la derivada en ese punto es positiva (no hay oscurecimiento),
        # usar el punto donde el perfil cruza la media del anillo
        if d1[idx_min_d1] >= 0:
            media = float(arr_smooth.mean())
            # Buscar primer cruce por debajo de la media en el rango
            sub = arr_smooth[m_ini: len(arr) - m_fin]
            cruces = np.where(np.diff(np.sign(sub - media)) < 0)[0]
            if len(cruces) > 0:
                idx_min_d1 = cruces[0] + m_ini
            else:
                idx_min_d1 = m_ini + len(sub) // 2

        px_ins, py_ins, insert_at = perfil_pos[idx_min_d1]
        inserciones.append((insert_at, px_ins, py_ins))

    # Emitir 100% al completar para que el usuario vea que el worker
    # terminó. Sin esto la barra queda pegada al 99% mientras el main
    # thread aplica los resultados, dando sensación de "crash".
    if cancel_flag is not None and sig_prog is not None:
        try:
            sig_prog.emit(100, "Procesando resultados...")
        except Exception:
            pass

    return inserciones



def _calcular_anchos_ewlw_por_anillo(coords, saltos, ppm, med_a_cor=True):
    """Adaptador de coordenadas y marcas históricas."""
    return anchos_ewlw_puntos(puntos_desde_geometria(coords, saltos), ppm, med_a_cor)


def anchos_ewlw_puntos(puntos, ppm, med_a_cor=True):
    """Anchos en orden de captura; ausentes si no existe un límite único."""
    puntos = tuple(puntos)
    resultado = []
    for anillo in calcular_anillos(puntos, ppm):
        limites = [i for i in anillo.segmentos if puntos[i].tipo is TipoMarca.EW_LW]
        if len(limites) != 1 or not anillo.completo:
            resultado.append((anillo.ancho_mm, None, None))
            continue
        previo = sum(math.dist(puntos[i-1].coordenada, puntos[i].coordenada) / ppm
                     for i in anillo.segmentos if i <= limites[0])
        posterior = max(0., anillo.ancho_mm - previo)
        ew, lw = (previo, posterior) if med_a_cor else (posterior, previo)
        resultado.append((anillo.ancho_mm, ew, lw))
    return resultado


def detectar_ewlw_imagen(sig_prog, img_bgr, c, s, b, ruta_disco, cancel_flag=None, med_a_cor=True):
    """Ejecuta en thread secundario. NO toca widgets Qt directamente."""
    import cv2 as _cv2
    if img_bgr is None:
        # Fallback: leer del disco (solo si no está cacheada)
        img_bgr = _cv2.imread(ruta_disco, _cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise RuntimeError(
                "No se pudo leer la imagen desde el disco para detectar EW/LW.")
    gray = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2GRAY).astype(np.float32)
    return _calcular_ewlw_posiciones(
        sig_prog, gray, c, s, b, cancel_flag, med_a_cor)


def calcular_anchos_ewlw(coords, saltos, datos_medidos, ppm, med_a_cor=None):
    """Proyección de anillos completos con EW/LW, conservando años reales."""
    if med_a_cor is None:
        med_a_cor = len(datos_medidos) < 2 or datos_medidos[0]['anio'] <= datos_medidos[-1]['anio']
    anchos = _calcular_anchos_ewlw_por_anillo(coords, saltos, ppm, med_a_cor)
    if len(anchos) != len(datos_medidos):
        raise ValueError('EW/LW: geometría y datación incompatibles')
    filas = sorted((d['anio'], ew, lw) for d, (_, ew, lw) in zip(datos_medidos, anchos)
                   if ew is not None and lw is not None)
    anios = [a for a, _, _ in filas]
    return anios, [ew for _, ew, _ in filas], anios.copy(), [lw for _, _, lw in filas]
