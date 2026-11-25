"""Operaciones extraídas sin modificar sus algoritmos."""
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import serie_anual
from scipy.linalg import solveh_banded
RIGIDEZ_SPLINE_DEFECTO = 32

def _bloques_anuales(serie):
    s = serie_anual(serie)
    cortes = np.flatnonzero(np.diff(s.index.to_numpy()) != 1) + 1
    return [s.iloc[a:b] for a, b in zip([0, *cortes], [*cortes, len(s)]) if a < b]


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
        # Opción 1 de ARSTAN: «neg expon curve (k>0), no = opt 4».
        #
        # Verificado contra una corrida real, leyendo su tabla de ajustes por
        # serie. Dos cosas que había que entender bien:
        #
        # 1. La ASÍNTOTA debe ser POSITIVA (d > 0 en y = a·exp(−b·t) + d). Un
        #    árbol no tiende a un ancho negativo.
        # 2. Cuando el ajuste no cumple, el respaldo de ARSTAN es su OPCIÓN 4,
        #    que es «linear regression (any slope)» — NO la media horizontal,
        #    que es su opción 6. Es un detalle que se presta a confusión y
        #    cambia por completo el resultado.
        #
        # Y lo que más importa: el ajuste exponencial **falla mucho más
        # seguido de lo que uno supondría**. En la corrida de referencia falló
        # en prácticamente todas las series de la colección, así que ARSTAN
        # terminó usando regresión lineal en casi todas. Nuestro ajuste, en
        # cambio, «tenía éxito» siempre porque el optimizador empuja los
        # parámetros contra el borde y devuelve una exponencial degenerada,
        # casi plana. Por eso se rechaza explícitamente el caso b ≈ 0: una
        # exponencial que no decae es una recta disfrazada.
        a0 = max(float(np.nanmax(y_fit) - np.nanmin(y_fit)), 1e-3)
        b0 = 0.01
        c0 = max(float(np.nanmin(y_fit)), 1e-6)

        def _recta():
            p = np.polyfit(x_fit, y_fit, 1)
            return np.polyval(p, x)

        try:
            popt, _ = curve_fit(
                f, x_fit, y_fit, p0=(a0, b0, c0), maxfev=20000,
                bounds=([0.0, 0.0, 0.0], [np.inf, 10.0, np.inf]),
            )
            a_f, b_f, d_f = popt
            tend = f(x, *popt)
            # La asíntota debe ser ESTRICTAMENTE positiva: la opción de
            # ARSTAN dice «neg expon curve (k>0)», y el estricto es literal.
            #
            # El optimizador, con el límite inferior en cero, empuja la
            # asíntota contra ese borde y devuelve un ajuste que técnicamente
            # converge pero que ARSTAN rechaza. Verificado con una corrida
            # suya sobre 19 series: aceptó UNA, COS140B, con asíntota 0,693;
            # las seis que nosotros aceptábamos de más tenían todas asíntota
            # 0,000 exacto, o sea pegadas al borde.
            #
            # El umbral es relativo a la media de la serie, no absoluto,
            # porque una asíntota de 0,001 mm significa cosas distintas en
            # una serie de 0,3 mm y en una de 3 mm.
            _piso_d = 1e-4 * float(np.nanmean(y_fit)) if np.isfinite(
                np.nanmean(y_fit)) else 0.0
            if (not np.all(np.isfinite(tend)) or b_f <= 1e-4
                    or a_f <= 1e-6 or d_f <= _piso_d):
                return _recta()
            return tend
        except Exception:
            return _recta()

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
    bloques = _bloques_anuales(serie_mm)
    if len(bloques) > 1:
        return pd.concat([_detrend_serie_indice(b, metodo, ventana_mm=ventana_mm, rigidez=rigidez) for b in bloques])
    s = serie_anual(serie_mm)
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
