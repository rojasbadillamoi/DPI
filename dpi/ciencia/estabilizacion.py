"""Operaciones extraídas sin modificar sus algoritmos."""
import numpy as np
import pandas as pd
from dpi.ciencia.tendencias import _spline_cook

def rigidez_efectiva(valor, n_anios: int, minima: int = 0) -> float:
    """Traduce la especificación de rigidez de ARSTAN a años.

    ARSTAN admite dos formas de pedir un spline, y la segunda no existía en DPI:

      · **Positiva** — años. `32` es un corte del 50 % a 32 años.
      · **Negativa** — PORCENTAJE DEL LARGO DE LA SERIE. `-75` es un corte al
        50 % en el 75 % del largo de cada serie, así que una serie de 400
        anillos recibe un spline de 300 años y una de 100, uno de 75.

    La forma negativa es la que permite tratar series de distinto largo de
    manera comparable: el filtro se adapta a cada una en vez de imponer el
    mismo corte a todas.

    `minima` es la rigidez mínima de ARSTAN: el spline nunca baja de ese valor.
    Sirve para no ajustar curvas muy flexibles a series cortas, que las dejaría
    con una estructura de persistencia distinta a la de las largas.
    """
    # Los métodos que no son spline no usan rigidez; se acepta None.
    if valor is None:
        return float(max(minima, 5.0)) if minima else 32.0
    v = float(valor)
    rig = (abs(v) / 100.0) * float(n_anios) if v < 0 else v
    if minima and minima > 0:
        rig = max(rig, float(minima))
    return max(rig, 5.0)


def estabilizar_varianza(idx: pd.Series, rigidez=64,
                          rigidez_minima: int = 0) -> pd.Series:
    """Estabiliza la varianza al modo de ARSTAN.

    El manual describe el procedimiento con precisión, y no es obvio: se
    normaliza la serie a media cero, se voltean las desviaciones negativas a
    positivas *anotando cuáles eran*, se ajusta un spline a esa serie de
    valores absolutos, se divide cada desviación por su valor del spline, se
    devuelven los signos y por último se suma de vuelta la media.

    Sirve cuando la varianza de una serie cambia mucho en el tiempo —algo
    propio de ciertos sitios, especies o árboles individuales—, porque si no,
    los tramos de varianza alta dominan la cronología.

    LA RIGIDEZ ES UN COMPROMISO, y por eso queda configurable. Medido sobre
    seis series largas de ciprés, como razón entre la desviación máxima y la
    mínima en ventanas de 60 años (1,00 sería varianza perfectamente estable):

        sin estabilizar   2,15
        spline 128 años   1,56
        spline  64 años   1,39   <- valor por omisión
        spline  32 años   1,29
        spline  20 años   1,25

    Más flexible estabiliza mejor, pero también aplana amplitudes que pueden
    ser reales: una década genuinamente extrema queda rebajada junto con el
    artefacto. 64 años reduce el desequilibrio a la mitad sin llegar a eso.
    """
    v = pd.to_numeric(idx, errors="coerce").dropna().astype(float)
    if len(v) < 12:
        return idx
    media = float(v.mean())
    desv = v.to_numpy() - media
    signos = np.sign(desv)
    absol = np.abs(desv)
    rig = rigidez_efectiva(rigidez, len(v), rigidez_minima)
    try:
        curva = np.asarray(_spline_cook(absol, nyrs=rig, f=0.5), dtype=float)
    except Exception:
        return idx
    # Piso proporcional: donde la curva se acerca a cero la división explota,
    # igual que en el detrending.
    piso = 0.10 * float(np.mean(absol[absol > 0])) if np.any(absol > 0) else 1e-6
    curva = np.maximum(curva, max(piso, 1e-9))
    fuera = signos * (absol / curva)
    # El manual dice «se suma de vuelta la media», pero dividir por la curva de
    # desviaciones absolutas deja la serie en unidades de esa desviación local,
    # no en unidades de índice: la desviación típica salta de ~0,23 a ~1,28.
    # Para que la cronología siga siendo comparable, se reescala al mismo
    # desvío que tenía antes. Lo que se elimina es la VARIACIÓN de la varianza
    # en el tiempo, que es el objetivo; la escala global se conserva.
    sd0 = float(np.std(desv))
    sd1 = float(np.std(fuera))
    if sd1 > 0 and sd0 > 0:
        fuera = fuera * (sd0 / sd1)
    return pd.Series(fuera + media, index=v.index)
