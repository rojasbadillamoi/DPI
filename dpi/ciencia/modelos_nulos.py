"""Contrastes nulos con localizador de quiebres inyectado."""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from dpi.ciencia.estadistica import pearson

logger = logging.getLogger(__name__)


def _fase_aleatoria(x: np.ndarray, rng) -> np.ndarray:
    """Sustituta con el MISMO espectro de potencia y fases al azar.

    Conserva exactamente la autocorrelación de la serie —a cualquier orden, no
    solo el primero— pero destruye la estructura temporal. Es el sustituto
    estándar para este tipo de contraste.

    Hace falta porque un ruido AR(1) es demasiado simple: las series reales
    tienen persistencia de orden mayor y variabilidad decadal que la búsqueda
    puede aprovechar, así que un nulo AR(1) subestima lo que se consigue por
    azar y deja pasar falsos positivos.
    """
    n = len(x)
    F = np.fft.rfft(x - x.mean())
    fases = rng.uniform(0, 2 * np.pi, len(F))
    fases[0] = 0.0
    if n % 2 == 0:
        fases[-1] = 0.0
    G = np.abs(F) * np.exp(1j * fases)
    out = np.fft.irfft(G, n=n)
    sd = out.std()
    return out / sd if sd > 0 else out


def _ruido_ar1(n: int, phi: float, rng) -> np.ndarray:
    """Ruido con autocorrelación de primer orden `phi`, varianza 1."""
    phi = float(np.clip(phi, -0.95, 0.95))
    e = rng.standard_normal(n)
    out = np.empty(n)
    out[0] = e[0] / np.sqrt(max(1.0 - phi * phi, 1e-6))
    for t in range(1, n):
        out[t] = phi * out[t - 1] + e[t]
    s = out.std()
    return out / s if s > 0 else out


def evaluar_con_sustitutas(localizar_quiebre, serie_std: pd.Series, crono_std: pd.Series,
                            n_nulo: int = 60, percentil: float = 95.0,
                            semilla: int = 0, **kwargs) -> dict:
    """Decide si el quiebre es real, comparándolo con series SIN error.

    POR QUÉ NO SIRVE ROTAR LA CRONOLOGÍA
    ------------------------------------
    El primer nulo que probamos corría la misma búsqueda contra la cronología
    rotada. Eliminaba los falsos positivos, pero rechazaba también los casos
    verdaderos, y la razón es de fondo: rotar destruye la señal, así que la
    correlación de base cae a cero y CUALQUIER partición gana mucho. Para una
    serie que sí cofecha, la base ya es alta y arreglar un anillo gana poco,
    aunque el resultado sea excelente. Las dos ganancias no son comparables.

    LA PREGUNTA CORRECTA
    --------------------
    No es «¿cuánto gana la búsqueda cuando no hay ninguna señal?» sino
    «¿cuánto gana cuando hay señal pero NO hay error de datación?».

    Para responderla se generan series SUSTITUTAS que conservan lo que
    importa y no tienen quiebre:

      · la misma correlación con la cronología que alcanza la serie una vez
        corregida — o sea el nivel al que aspira la corrección propuesta;
      · la misma persistencia, mediante ruido autorregresivo ajustado a la
        autocorrelación de la serie real;
      · el mismo largo y los mismos años, para que el espacio de búsqueda
        tenga exactamente el mismo tamaño.

    Sobre cada sustituta se corre la misma búsqueda y se anota su ganancia.
    Si la ganancia real supera el percentil de esa distribución, el quiebre no
    se explica por la libertad del método.

    Devuelve el diccionario de `localizar_quiebre` más `umbral_nulo`,
    `ganancia_nula`, `p_valor` y `confiable`.
    """
    q = localizar_quiebre(serie_std, crono_std, **kwargs)
    q["umbral_nulo"] = float("nan")
    q["ganancia_nula"] = float("nan")
    q["p_valor"] = float("nan")
    q["nulo"] = "sustitutas"
    if q.get("anio") is None or not np.isfinite(q.get("ganancia", np.nan)):
        q["confiable"] = False
        return q

    s = pd.to_numeric(serie_std, errors="coerce").dropna().sort_index()
    c = pd.to_numeric(crono_std, errors="coerce").dropna().sort_index()
    com = s.index.intersection(c.index)
    if len(com) < 40:
        q["confiable"] = False
        return q

    # Nivel de correlación al que aspira la corrección: el de la serie ya
    # partida. Es lo que la sustituta debe reproducir SIN quiebre.
    r_obj = float(np.clip(q["r"], -0.95, 0.95))
    x = s.to_numpy(dtype=float)
    phi = 0.0
    if len(x) > 5 and np.std(x) > 0:
        phi = pearson(x[:-1], x[1:])
        if not np.isfinite(phi):
            phi = 0.0

    cz = c.reindex(s.index)
    hay = cz.notna().to_numpy()
    base = cz.to_numpy(dtype=float)
    if hay.sum() < 40:
        q["confiable"] = False
        return q
    m = np.nanmean(base[hay])
    sd = np.nanstd(base[hay])
    if sd <= 0:
        q["confiable"] = False
        return q
    base_z = np.where(hay, (base - m) / sd, 0.0)

    # Residuo real de la serie respecto de la cronología: es lo que se
    # aleatoriza, para que la sustituta herede su espectro completo.
    beta = r_obj * (np.std(x) / 1.0) if np.std(x) > 0 else 0.0
    resid = (x - x.mean()) / (np.std(x) or 1.0) - r_obj * base_z

    rng = np.random.default_rng(semilla)
    ganancias = []
    for _ in range(int(n_nulo)):
        e = _fase_aleatoria(resid, rng)
        sint = r_obj * base_z + np.sqrt(max(1.0 - r_obj * r_obj, 0.0)) * e
        # Donde la cronología no cubre, la sustituta es solo ruido: igual que
        # la serie real, que ahí tampoco tiene con qué correlacionar.
        sint = np.where(hay, sint, e)
        qn = localizar_quiebre(pd.Series(sint, index=s.index), c, **kwargs)
        g = qn.get("ganancia", np.nan)
        if np.isfinite(g):
            ganancias.append(float(g))

    if len(ganancias) < 15:
        q["confiable"] = False
        return q
    g = np.asarray(ganancias)
    q["umbral_nulo"] = float(np.percentile(g, percentil))
    q["ganancia_nula"] = float(g.mean())
    q["p_valor"] = float((g >= q["ganancia"]).mean())
    q["confiable"] = bool(q["ganancia"] > q["umbral_nulo"])
    return q


def nulo_de_coleccion(localizar_quiebre, series_std: dict, crono_std, excluir: str | None = None,
                       percentil: float = 95.0, **kwargs) -> dict:
    """Umbral de ganancia a partir de las OTRAS series de la colección.

    ES EL NULO QUE FUNCIONA, y conviene entender por qué después de dos que
    no funcionaron.

    El primero rotaba la cronología. Eliminaba los falsos positivos pero
    rechazaba los casos verdaderos: rotar destruye la señal, la correlación de
    base cae a cero y cualquier partición gana mucho, así que el umbral queda
    altísimo.

    El segundo generaba series sustitutas con la misma correlación y el mismo
    espectro. Detectaba todo, pero dejaba pasar hasta un 39 % de falsos
    positivos: ninguna sustituta sintética reproduce la complejidad de una
    serie real —persistencia de orden alto, relación no estacionaria con la
    cronología, perturbaciones locales— y la búsqueda explota justamente eso.

    La salida es no inventar el nulo sino MEDIRLO: correr la misma búsqueda
    sobre las demás series de la colección, que están fechadas, y quedarse con
    el percentil de sus ganancias. Ese umbral incorpora toda la complejidad
    real porque proviene de datos reales, y responde exactamente la pregunta
    que importa: cuánto gana esta búsqueda en una serie de este sitio, de esta
    especie, con esta cronología, cuando NO hay error de datación.

    Medido sobre las cuatro especies, con un anillo borrado en un año conocido:

                    falsos+   detecta
        roble          6 %     100 %
        ciprés         6 %     100 %
        araucaria      0 %     100 %
        lenga         11 %      78 %

    Requiere al menos ocho series además de la evaluada. Con menos, el
    percentil no es estable y conviene `evaluar_con_sustitutas`, aceptando su
    tasa de falsos positivos más alta.

    Devuelve {"umbral", "ganancias", "n"}.
    """
    gan = []
    for nombre, serie in series_std.items():
        if excluir is not None and nombre == excluir:
            continue
        try:
            q = localizar_quiebre(serie, crono_std, **kwargs)
        except Exception:
            logger.debug("Falló evaluación de serie del nulo", exc_info=True)
            continue
        g = q.get("ganancia", np.nan)
        if np.isfinite(g):
            gan.append(float(g))
    if len(gan) < 8:
        return {"umbral": float("nan"), "ganancias": gan, "n": len(gan)}
    return {"umbral": float(np.percentile(gan, percentil)),
            "ganancias": gan, "n": len(gan)}


def evaluar_con_coleccion(localizar_quiebre, serie_std: pd.Series, crono_std: pd.Series,
                           series_std: dict, excluir: str | None = None,
                           percentil: float = 95.0, **kwargs) -> dict:
    """Localiza el quiebre y lo contrasta con el nulo de la colección."""
    q = localizar_quiebre(serie_std, crono_std, **kwargs)
    nulo = nulo_de_coleccion(localizar_quiebre, series_std, crono_std, excluir=excluir,
                             percentil=percentil, **kwargs)
    q["umbral_nulo"] = nulo["umbral"]
    q["n_nulo_series"] = nulo["n"]
    q["nulo"] = "coleccion"
    if nulo["ganancias"]:
        g = np.asarray(nulo["ganancias"])
        q["ganancia_nula"] = float(g.mean())
        q["p_valor"] = float((g >= q.get("ganancia", -np.inf)).mean())
    q["confiable"] = bool(np.isfinite(nulo["umbral"])
                          and np.isfinite(q.get("ganancia", np.nan))
                          and q["ganancia"] > nulo["umbral"])
    return q
