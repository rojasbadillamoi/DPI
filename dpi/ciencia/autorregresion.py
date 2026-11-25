"""Operaciones extraídas sin modificar sus algoritmos."""
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import serie_anual
from dpi.ciencia.tendencias import _bloques_anuales
ORDEN_AR_MAXIMO = 3

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


def _ajustar_ar_burg(x: np.ndarray, p: int):
    """Coeficientes autorregresivos por el método de Burg.

    Es el que usa ARSTAN. Verificado despejando sus coeficientes desde los
    residuos por serie de una corrida real, sobre tres series:

        serie      ARSTAN   Yule-Walker   mín. cuad.     Burg
        COS088A    0.7893      0.7798       0.7888      0.7894
        COS088B    0.7382      0.7365       0.7455      0.7412
        COS305A    0.5083      0.5058       0.5086      0.5082

        error medio            0.00456      0.00273     0.00106

    Burg minimiza la suma de los errores de predicción hacia adelante y hacia
    atrás, en vez de resolver las ecuaciones de Yule-Walker sobre las
    autocorrelaciones muestrales. Con series cortas la diferencia se nota,
    porque Yule-Walker subestima la persistencia.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n <= p or p < 1:
        return np.zeros(max(p, 0)), float(np.var(x)) if n else 0.0
    f = x.copy()
    b = x.copy()
    a = []
    v = float(np.dot(x, x) / n)
    for m in range(p):
        num = 2.0 * float(np.dot(f[m + 1:], b[m:-1]))
        den = float(np.dot(f[m + 1:], f[m + 1:]) + np.dot(b[m:-1], b[m:-1]))
        k = num / den if den > 0 else 0.0
        a = [ai - k * aj for ai, aj in zip(a, a[::-1])] + [k] if a else [k]
        ff = f[m + 1:] - k * b[m:-1]
        bb = b[m:-1] - k * f[m + 1:]
        f = np.concatenate([f[:m + 1], ff])
        b = np.concatenate([b[:m + 1], bb])
        v *= (1.0 - k * k)
    return np.asarray(a, dtype=float), max(v, 1e-12)


def _residualizar_indice(indice: pd.Series, max_orden: int | None = None,
                          devolver_orden: bool = False, orden_fijo: int | None = None):
    """Quita la autocorrelación del índice con un modelo AR.

    El orden se elige automáticamente por AIC (como COFECHA). Antes se usaba
    siempre AR(1), lo que dejaba autocorrelación residual en las series que
    requieren orden 2 o 3.
    """
    bloques = _bloques_anuales(indice)
    if len(bloques) > 1:
        resultados = [_residualizar_indice(b, max_orden, True, orden_fijo) for b in bloques]
        resid = pd.concat([r for r, _ in resultados])
        orden = max(p for _, p in resultados)
        return (resid, orden) if devolver_orden else resid
    s = serie_anual(indice)
    if len(s) < 4:
        return (s.copy(), 0) if devolver_orden else s.copy()
    c = s - s.mean()
    x = c.to_numpy(dtype=float)
    if np.std(x) == 0:
        return (s.copy(), 0) if devolver_orden else s.copy()

    if max_orden is None:
        max_orden = ORDEN_AR_MAXIMO
    # `orden_fijo` viene del modelo AGRUPADO al modo de ARSTAN: un solo orden
    # para todas las series de la colección. Si no viene, se elige por serie.
    p = (int(orden_fijo) if orden_fijo
         else _seleccionar_orden_ar(x, max_orden))
    if p <= 0:
        resid_v = x.copy()
    else:
        # Burg, no Yule-Walker: es el estimador de ARSTAN. Ver _ajustar_ar_burg.
        phi, _ = _ajustar_ar_burg(x, p)
        # RETROPRONÓSTICO de los p valores anteriores al inicio.
        #
        # ARSTAN no deja los primeros p años sin modelar: estima los valores
        # previos con el mismo modelo AR, reflejando la serie, y así calcula
        # un residuo para TODOS los años. Verificado contra los residuos por
        # serie de una corrida real: sin retropronóstico, nuestro primer año
        # quedaba con el índice crudo (1,855 frente a su 1,327) y, peor, ese
        # valor entraba en la media de recentrado y desplazaba la serie
        # ENTERA unas tres milésimas. Con retropronóstico, los tres primeros
        # años quedan a menos de 0,007 y el resto coincide dentro del redondeo.
        prev = np.empty(p, dtype=float)
        for i in range(p):
            j = min(i, len(x) - 1)
            prev[p - 1 - i] = float(np.dot(phi[:1], [x[j]])) if p == 1 else x[j]
        ext = np.concatenate([prev, x])
        resid_v = x.copy()
        for t in range(len(x)):
            hist = ext[t:t + p][::-1]
            resid_v[t] = x[t] - float(np.dot(phi, hist))

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


def orden_ar_agrupado(indices: dict, pmax: int | None = None) -> tuple:
    """Orden autorregresivo AGRUPADO: uno solo para toda la colección.

    Es lo que hace ARSTAN —«series ar order 0, pooled ar order fit to all
    series»—: en vez de elegir un orden por serie, promedia las
    autocorrelaciones de la colección y ajusta sobre ellas. Agrupar mejora el
    ESTIMADOR de la autocorrelación, que es lo que aporta.

    Lo que NO cambia al agrupar es el criterio ni el tamaño de muestra, y por
    ahí se rompía. Esta función elegía el orden por el primer mínimo local del
    AIC con `n` igual a la SUMA de los largos de todas las series, y eso falla
    de dos maneras:

    **El criterio ya estaba medido y descartado.** El primer mínimo local del
    AIC es el de `chron.ars` de dplR, y contra los órdenes que informa COFECHA
    —un entero, así que no admite interpretación— acierta 81 % frente al 92 %
    del BIC, que es el que usa `_seleccionar_orden_ar`. Está en el registro de
    cambios 1.3. La función agrupada se quedó sin ese arreglo.

    **La suma de los largos no es el tamaño de muestra.** El modelo se aplica
    a series individuales, así que el orden tiene que ser el que se justifica
    para una serie del largo típico. Con `ntot` la penalización queda en torno
    a 1e-4 de `log(var)` —nula—, la traza del AIC sale monótona decreciente, el
    primer mínimo no se dispara nunca y el respaldo `argmin` devuelve el techo.
    Resultado: el orden lo decidía el TAMAÑO DE LA COLECCIÓN y no la
    persistencia de los datos. Medido sobre seis colecciones con ρ₁ entre 0,31
    y 0,36, salía 1 con 19 a 43 series y 10 con 70 a 82.

    Y lo que se modelaba pasado el retardo 1 era un artefacto: las
    autocorrelaciones parciales agrupadas son negativas y sin decaer del
    retardo 3 al 10 en las seis colecciones, que es la firma del spline, no de
    un proceso autorregresivo. Contra el piso de ruido de una serie individual
    quedan por debajo del ruido; agrupar las hacía parecer significativas.

    Con BIC sobre el largo mediano y el techo de `ORDEN_AR_MAXIMO`, el orden
    sale AR(1) en las seis, que es la moda de los órdenes por serie en todas.
    La cronología residual correlaciona 0,96 con la anterior, pero recupera
    señal: la desviación estándar sube un 8 % y el Rbar entre series también
    —0,407 a 0,448 en la colección de 82—, o sea que el AR(10) estaba quitando
    señal COMÚN, que es lo contrario de lo que busca una cronología residual.

    Nota sobre cómo se detectó: con series AR sintéticas la regla anterior
    acierta, porque ahí las parciales pasado el orden verdadero son ruido
    blanco y la traza del AIC sí da la vuelta. Degenera solo con la cola de
    parciales negativas que deja el detrending, así que hacen falta
    colecciones reales para verlo.

    Devuelve (orden, autocorrelaciones_agrupadas).
    """
    if pmax is None:
        pmax = ORDEN_AR_MAXIMO
    pmax = max(int(pmax), 1)
    num = np.zeros(pmax)
    den = np.zeros(pmax)
    largos = []
    for v in (b for serie in indices.values() for b in _bloques_anuales(serie)):
        x = v.to_numpy(dtype=float)
        if len(x) < 20:
            continue
        x = x - x.mean()
        n = len(x)
        largos.append(n)
        c0 = float(np.sum(x * x))
        if c0 <= 0:
            continue
        for k in range(1, pmax + 1):
            if n - k < 5:
                continue
            num[k - 1] += n * (float(np.sum(x[:-k] * x[k:])) / c0)
            den[k - 1] += n
    if not largos:
        return 1, np.zeros(pmax)
    rho = num / np.maximum(den, 1e-12)

    # Largo MEDIANO, no la suma: es el tamaño de la serie a la que se le va a
    # aplicar el modelo. La mediana y no la media, por las series cortas.
    n = int(np.median(largos))
    mejor_orden, mejor_pun = 1, np.inf
    for p in range(1, pmax + 1):
        R = np.array([[1.0 if i == j else rho[abs(i - j) - 1]
                       for j in range(p)] for i in range(p)])
        r = rho[:p]
        try:
            phi = np.linalg.solve(R, r)
        except Exception:
            continue
        var = 1.0 - float(np.dot(phi, r))
        if not np.isfinite(var) or var <= 0:
            continue
        pun = n * np.log(var) + p * np.log(n)      # BIC, igual que por serie
        if pun < mejor_pun - 1e-9:
            mejor_pun, mejor_orden = pun, p
    return mejor_orden, rho
