"""
MoiCedrus — DPI · Informe de texto tipo COFECHA
===============================================

Convierte el resultado de `modulo_cofecha.analizar_coleccion` en un informe
de texto de ancho fijo con las 7 partes del formato clásico, para poder
leerlo, imprimirlo o compararlo con un .OUT de COFECHA.

Las cifras se calculan en `modulo_cofecha`; acá solo se les da formato.
"""

from __future__ import annotations

import datetime as _dt

import numpy as np

ANCHO = 132  # ancho de línea del formato clásico (medido en CLLCOF.OUT
             # y QLHcof.out: ninguna línea de ninguna parte pasa de 132)


def _f3(x, dec=3):
    """Formatea como COFECHA: .309 en vez de 0.309, y — si no hay dato."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return " " * (dec + 2)
    if not np.isfinite(v):
        return " " * (dec + 2)
    s = f"{v:.{dec}f}"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s.rjust(dec + 2)


def _titulo(texto: str, pagina: int, fecha: str) -> list[str]:
    izq = f" {texto}"
    der = f"{fecha}  Página {pagina:3d}"
    hueco = max(1, ANCHO - len(izq) - len(der))
    return [izq + " " * hueco + der, " " + "-" * (ANCHO - 2), ""]


def _caja_resumen(res: dict) -> list[str]:
    """El recuadro de asteriscos de la portada.

    Ancho y alineación calcados de COS4COF.OUT: el recuadro mide 40
    caracteres, arranca en la columna 40, y cada línea es
    `*L* <texto de 32> *L*` con el número pegado a la derecha del texto.
    """
    p, u = int(res["primer_anio"]), int(res["ultimo_anio"])
    filas = [
        ("C", "Series fechadas", f"{res['n_series']:d}"),
        ("O", "Maestra", f"{p} {u}  {u - p + 1} años"),
        ("F", "Anillos totales", f"{res['total_anillos']:d}"),
        ("E", "Anillos comprobados",
         f"{res.get('total_comprobados', res['total_anillos']):d}"),
        ("C", "Intercorrelación de series",
         _f3(res.get("intercorrelacion")).strip()),
        ("H", "Sensibilidad media", _f3(res.get("sensibilidad_media")).strip()),
        ("A", "Segmentos con problemas", f"{res['total_banderas']:d}"),
    ]
    CUERPO = 34
    sangria = " " * 40
    L = [sangria + "*" * (CUERPO + 8)]
    for letra, etq, val in filas:
        hueco = CUERPO - len(etq) - len(val)
        txt = etq + " " * max(hueco, 1) + val
        L.append(f"{sangria}*{letra}* {txt:<{CUERPO}} *{letra}*")
    L.append(sangria + "*" * (CUERPO + 8))
    return L


def _parte1(res: dict, titulo: str, fecha: str) -> list[str]:
    o = res["opciones"]
    L = []
    # Encabezado de la Dendrochronology Program Library, como en el original
    cab = " []  BIBLIOTECA DE PROGRAMAS DE DENDROCRONOLOGÍA"
    cola = f"Corrida DPI  Programa COF  {fecha}  Página   1"
    L.append(cab.ljust(max(1, ANCHO - len(cola))) + cola)
    L.append(" []")
    L.append(" []  P R O G R A M A      C O F E C H A".ljust(105)
             + f"MoiCedrus DPI {_VERSION_DPI()}")
    L.append(" " + "-" * (ANCHO - 1))
    L.append("")
    L.append(" CONTROL DE CALIDAD Y COMPROBACIÓN DE FECHADO DE MEDICIONES DE ANILLOS")
    L.append("")
    L.append(f" Archivo de series FECHADAS:   {titulo}")
    L.append("")
    L.append(" CONTENIDO:")
    L.append("")
    L.append("    Parte 1:  Portada, opciones, resumen, anillos ausentes por serie")
    L.append("    Parte 2:  Diagrama de extensión temporal de las series")
    L.append("    Parte 3:  Serie maestra con profundidad de muestreo y ausentes por año")
    L.append("    Parte 4:  Gráfico de barras de la serie maestra")
    L.append("    Parte 5:  Correlación por segmento de cada serie con la maestra")
    L.append("    Parte 6:  Problemas potenciales: correlación baja, cambios divergentes,"
             " anillos ausentes, atípicos")
    L.append("    Parte 7:  Estadísticos descriptivos")
    L.append("")
    L.append(" OPCIONES DE LA CORRIDA SELECCIONADAS                     VALOR")
    L.append("")
    L.append("         1  Spline cúbico de suavizado, corte al 50% de la longitud de onda")
    L.append(f"                                                         {o['rigidez_spline']:4d} años")
    L.append(f"         2  Segmentos examinados son                     {o['largo_segmento']:4d} años"
             f" avanzando de a {o['avance']:3d} años")
    ar = ("A  Se usan los residuos en la maestra y en las pruebas"
          if o["aplicar_ar"] else "N  No aplicado")
    L.append(f"         3  Modelo autorregresivo aplicado                {ar}")
    lg = ("S  Cada serie transformada para la maestra y las pruebas"
          if o["aplicar_log"] else "N  Sin transformar")
    L.append(f"         4  Series transformadas a logaritmos             {lg}")
    L.append(f"         5  Correlación crítica, {int((1 - o['alfa']) * 100)}% de confianza"
             f"    {_f3(res.get('critico_nominal'), 4)}")
    L.append("         6  Serie maestra guardada                           N")
    L.append("         7  Mediciones de anillos listadas                   N")
    L.append(f"         8  Partes impresas                            {o.get('partes', '1234567')}")
    L.append("         9  Anillos ausentes incluidos en la maestra         N")
    mst = ("Biweight robusta" if o.get("maestro_robusto") else
           "Media aritmética (como COFECHA)")
    L.append(f"        10  Construcción de la serie maestra              {mst}")
    L.append(f"        11  Desfase máximo explorado                      ±{o.get('max_desfase', 10):d} años")
    L.append("")

    p, u = int(res["primer_anio"]), int(res["ultimo_anio"])
    L.append(f" Extensión de la serie maestra es      {p:5d} a {u:5d}   {u - p + 1:5d} años")
    L.append(f" Tramo continuo es                     {p:5d} a {u:5d}   {u - p + 1:5d} años")
    pd_, ud_ = res.get("primer_anio_dos"), res.get("ultimo_anio_dos")
    if pd_ is not None:
        L.append(f" Tramo con dos o más series es         {int(pd_):5d} a {int(ud_):5d}"
                 f"   {int(ud_) - int(pd_) + 1:5d} años")
    L.append("")
    L.append("")
    L += _caja_resumen(res)
    L.append(" ")

    con_aus = [x for x in res["series"] if x.get("ausentes")]
    L.append(" ANILLOS AUSENTES listados por SERIE:"
             "            (ver la serie maestra para los ausentes por año)")
    L.append(" ")
    if not con_aus:
        L.append("               Ninguna medición de anillos con valor cero")
    else:
        for x in con_aus:
            aus = x["ausentes"]
            cab = f" {x['nombre']:<10}{len(aus):4d} anillos ausentes:  "
            sangria = " " * len(cab)
            for k, trozo in enumerate([aus[t:t + 12] for t in range(0, len(aus), 12)]):
                L.append((cab if k == 0 else sangria)
                         + "".join(f"{a:6d}" for a in trozo))
        tot = res.get("total_ausentes", sum(len(x["ausentes"]) for x in con_aus))
        pct = 100.0 * tot / res["total_anillos"] if res["total_anillos"] else 0.0
        L.append("")
        L.append(f"          {tot:5d} anillos ausentes   {pct:.3f}%")
    L.append(" " + "=" * (ANCHO - 2))
    return L


def _VERSION_DPI() -> str:
    try:
        from constantes import VERSION
        return VERSION
    except Exception:
        return ""


def _escala_parte2(p: int, u: int):
    """Elige años por carácter para que la extensión quepa en el diagrama.

    COFECHA usa 10 años por carácter. Con colecciones muy largas eso no cabe
    en la línea, así que se sube al siguiente paso redondo.
    """
    ancho = 102
    for paso in (1, 2, 5, 10, 20, 25, 50, 100, 200):
        base = (p // (paso * 10)) * paso * 10
        if (u - base) / paso <= ancho:
            return paso, base
    paso = 500
    return paso, (p // (paso * 10)) * paso * 10


def _parte2(res: dict, fecha: str) -> list[str]:
    L = _titulo("PARTE 2:  DIAGRAMA DE EXTENSIÓN TEMPORAL DE LAS SERIES", 2, fecha)
    p, u = int(res["primer_anio"]), int(res["ultimo_anio"])
    paso, base = _escala_parte2(p, u)

    def col(anio):
        return 3 + int(round((anio - base) / paso))

    fin_plot = col(u)
    # Fila de etiquetas: una cada 10 caracteres
    etiquetas = [" "] * (fin_plot + 2)
    marcas = [" "] * (fin_plot + 2)
    k = 0
    while True:
        anio = base + k * paso * 10
        c = col(anio)
        if c > fin_plot:
            break
        txt = str(anio)
        for m, ch in enumerate(txt):
            if 0 <= c - 1 + m < len(etiquetas):
                etiquetas[c - 1 + m] = ch
        k += 1
    c = 3
    while c <= fin_plot:
        marcas[c] = ":"
        c += 5

    cab = "".join(etiquetas).rstrip()
    marcas_txt = "".join(marcas).rstrip()
    # El bloque de la derecha va pegado al final del gráfico, no en una
    # columna fija. COFECHA usa un eje fijo de 1000 a 2000 que siempre llena
    # la línea; acá la escala se adapta al período de la colección, así que
    # fijar la columna dejaba un hueco enorme entre las barras y los códigos.
    col_der = max(fin_plot + 2, len(cab) + 2, len(marcas_txt) + 2)
    # El original pone "Beg End" en una línea propia sobre el bloque derecho y
    # mete "Ident Seq year year Yrs" en la MISMA línea de las etiquetas de año.
    L.append(" " * (col_der + 22) + "Ini  Fin")
    L.append(cab.ljust(col_der) + "Serie    Nº   año  año  Años")
    L.append(marcas_txt.ljust(col_der) + "-------- --- ---- ---- ----")
    for i, x in enumerate(res["series"], start=1):
        a, b = col(x["primer_anio"]), col(x["ultimo_anio"])
        fila = [" "] * (fin_plot + 2)
        c = 3
        while c <= fin_plot:
            fila[c] = "."
            c += 5
        b = max(b, a + 1)
        fila[a] = "<"
        for m in range(a + 1, min(b, len(fila) - 1)):
            fila[m] = "="
        fila[min(b, len(fila) - 1)] = ">"
        # El bloque derecho arranca en la columna 105, pegado al gráfico.
        # Antes había un hueco de varias columnas que no está en el original.
        L.append("".join(fila).ljust(col_der)
                 + f"{x['nombre']:<8} {i:3d} {x['primer_anio']:4d} "
                   f"{x['ultimo_anio']:4d} {x['n_anios']:4d}")
    # Pie: se repiten las marcas y las etiquetas, como en el original
    L.append(marcas_txt)
    L.append(cab)
    L.append(" " + "=" * (ANCHO - 2))
    return L


def _parte3(res: dict, fecha: str) -> list[str]:
    """Serie maestra con profundidad de muestreo y anillos ausentes por año.

    Disposición del original (verificada contra CLLCOF.OUT): seis columnas de
    22 caracteres, cada una cubriendo un bloque de 50 años, y 50 filas por
    página — o sea 300 años por página, leyendo hacia abajo dentro de cada
    columna. Cada celda lleva el año, el valor de la maestra, el número de
    series de ese año y, si corresponde, cuántas lo tienen ausente.

    El marcador << señala un año con anillos ausentes cuyo valor en la
    maestra NO es estrecho: si el resto de las series no muestran un anillo
    angosto ahí, el ausente es sospechoso y hay que revisarlo.
    """
    L = _titulo("PARTE 3:  SERIE MAESTRA CON PROFUNDIDAD Y ANILLOS AUSENTES",
                 3, fecha)
    maestro = res["maestro"]
    if maestro is None or maestro.empty:
        L.append(" (sin datos)")
        return L
    prof = res.get("profundidad")
    valores = {int(a): float(v) for a, v in maestro.items()}
    profundidad = ({int(a): int(v) for a, v in prof.items()}
                   if prof is not None else {})
    ausentes_por_anio = {}
    for x in res["series"]:
        for a in (x.get("ausentes") or []):
            ausentes_por_anio[a] = ausentes_por_anio.get(a, 0) + 1

    N_COL, ANCHO_COL, BLOQUE = 6, 22, 50
    # Campos de 18 caracteres (año 4, valor 7, series 4, ausentes 3) y 4 de
    # separación, como en el original: así el marcador << cabe en el hueco
    # sin invadir la columna siguiente.
    cab = (" " + (" Año  Valor Ser Au").ljust(ANCHO_COL) * N_COL).rstrip()
    sep = " " + ("-" * 18 + "    ") * N_COL

    def celda(anio):
        val = valores.get(anio)
        if val is None:
            return ""
        n = profundidad.get(anio, 0)
        aus = ausentes_por_anio.get(anio, 0)
        txt = f"{anio:4d}{_f3(val):>7}{n:4d}"
        if aus:
            txt += f"{aus:3d}"
            if np.isfinite(val) and val >= 0:
                txt += "<<"
        return txt

    inicio = (int(maestro.index.min()) // BLOQUE) * BLOQUE
    fin = int(maestro.index.max())
    primera = True
    pagina = inicio
    while pagina <= fin:
        if not primera:
            L.append("")
            L += _titulo("PARTE 3:  SERIE MAESTRA (continuación)", 3, fecha)
        primera = False
        L.append(cab)
        L.append(sep.rstrip())
        bases = [pagina + BLOQUE * k for k in range(N_COL)]
        for fila in range(BLOQUE):
            linea = " " + "".join(
                celda(b + fila).ljust(ANCHO_COL) for b in bases)
            if linea.strip():
                L.append(linea.rstrip())
        pagina += BLOQUE * N_COL
    L.append(" " + "=" * (ANCHO - 2))
    return L


def _codigo_valor(val: float, media: float, sd: float) -> tuple[int, str]:
    """Codifica un valor del maestro como (largo de barra, letra), tipo COFECHA.

    Verificado contra una salida real: cada letra vale 0,25 desviaciones
    típicas (A = +0,25, B = +0,50…; a, b, c hacia abajo; @ el valor medio) y
    la barra mide esa misma cantidad desplazada 5 caracteres, de modo que el
    valor medio queda en el centro de la columna. El redondeo de los empates
    exactos es hacia cero, como en el original.
    """
    if not np.isfinite(val):
        return 0, " "
    if sd <= 0:
        sd = 1.0
    z = (val - media) / sd
    paso = z * 4.0
    # redondeo al entero más próximo, con los .5 hacia cero
    cuartos = int(np.sign(paso) * np.floor(abs(paso) + 0.5 - 1e-9))
    if cuartos == 0:
        letra = "@"
    elif cuartos > 0:
        letra = chr(ord("A") + min(cuartos - 1, 25))
    else:
        letra = chr(ord("a") + min(-cuartos - 1, 25))
    largo = int(np.clip(cuartos + 5, 0, 10))
    return largo, letra


def _parte4(res: dict, fecha: str) -> list[str]:
    """Gráfico de barras del maestro.

    Disposición del original: ocho columnas de 50 años cada una, o sea 400
    años por página. Dentro de cada columna se leen cinco décadas de arriba
    abajo, separadas por una línea de guiones. La versión anterior usaba una
    década por columna y por eso las filas salían descolocadas.
    """
    L = _titulo("PARTE 4:  GRÁFICO DE BARRAS DE LA SERIE MAESTRA", 4, fecha)
    maestro = res["maestro"]
    if maestro.empty:
        L.append(" (sin datos)")
        return L
    v = maestro.to_numpy(dtype=float)
    media = float(np.mean(v))
    sd = float(np.std(v)) or 1.0
    valores = {int(a): float(x) for a, x in maestro.items()}

    N_COL, ANCHO_COL, BLOQUE = 8, 16, 50
    inicio = (int(maestro.index.min()) // BLOQUE) * BLOQUE
    fin = int(maestro.index.max())
    encabezado = "   " + "".join("Año  Valor rel. ".ljust(ANCHO_COL)
                                 for _ in range(N_COL)).rstrip()

    pagina = inicio
    primera = True
    while pagina <= fin:
        if not primera:
            L.append("")
            L += _titulo("PARTE 4:  GRÁFICO DE BARRAS DE LA SERIE MAESTRA "
                          "(continuación)", 4, fecha)
        primera = False
        L.append(encabezado.rstrip())
        bases = [pagina + N_COL * 0 + BLOQUE * k for k in range(N_COL)]
        for decada in range(0, BLOQUE, 10):
            hay_algo = False
            filas = []
            for fila in range(10):
                linea = ""
                for b in bases:
                    anio = b + decada + fila
                    val = valores.get(anio)
                    if val is None:
                        celda = ""
                    else:
                        largo, letra = _codigo_valor(val, media, sd)
                        celda = f"{anio:4d}" + "-" * largo + letra
                        hay_algo = True
                    linea += celda.ljust(ANCHO_COL)
                filas.append("   " + linea.rstrip())
            if hay_algo:
                L += filas
                L.append("   " + "----".ljust(ANCHO_COL) * N_COL)
        pagina += BLOQUE * N_COL
    L.append(" " + "=" * (ANCHO - 2))
    return L


def _parte5(res: dict, fecha: str) -> list[str]:
    """Correlación por segmento de cada serie con la maestra.

    Formato del original: prefijo de 25 caracteres (Nº, serie, extensión) y
    después celdas de 5 — cuatro para la correlación y una para la bandera —
    con veinte columnas por página. La versión anterior usaba celdas de 6 y
    volcaba todas las columnas en una sola línea, que con colecciones largas
    se iba muy por encima del ancho de página.

    Las columnas donde ninguna serie alcanza el solape mínimo se omiten, y
    una serie que no aparece en ninguna columna de la página no se imprime,
    igual que hace COFECHA.
    """
    o = res["opciones"]
    crit = res.get("critico_nominal")
    grilla = list(res.get("grilla") or [])

    # Valor por serie y por tramo
    por_serie = []
    for i, x in enumerate(res["series"], start=1):
        d = {(y["inicio"], y["fin"]): y for y in x["segmentos"]}
        por_serie.append((i, x, d))
    # Columnas sin ningún dato: fuera
    grilla = [g for g in grilla if any(g in d for _, _, d in por_serie)]

    L = _titulo("PARTE 5:  CORRELACIÓN DE LAS SERIES POR SEGMENTOS", 5, fecha)
    L.append(f" Correlaciones de segmentos fechados de {o['largo_segmento']} años,"
             f" desplazados de a {o['avance']} años")
    L.append(f" Banderas:  A = correlación bajo {_f3(crit, 4).strip()} pero la más alta"
             " en la posición fechada;"
             "  B = correlación más alta en otra posición")
    L.append("")
    if not grilla:
        L.append(" (ningún segmento alcanza el solape mínimo)")
        L.append(" " + "=" * (ANCHO - 2))
        return L

    PREFIJO, N_COL = 25, 20
    primera = True
    for k in range(0, len(grilla), N_COL):
        bloque = grilla[k:k + N_COL]
        if not primera:
            L.append("")
            L += _titulo("PARTE 5:  CORRELACIÓN POR SEGMENTOS (continuación)",
                          5, fecha)
        primera = False
        L.append(" Nº  Serie    Extensión".ljust(PREFIJO)
                 + "".join(f"{g[0]:5d}" for g in bloque))
        L.append(" " * PREFIJO + "".join(f"{g[1]:5d}" for g in bloque))
        L.append(" --- -------- ---------  " + "---- " * len(bloque))
        for i, x, d in por_serie:
            celdas = []
            hay = False
            for g in bloque:
                y = d.get(g)
                if y is None:
                    celdas.append(" " * 5)
                else:
                    hay = True
                    celdas.append(f"{_f3(y['r'], 2)}{y.get('bandera') or ' '}")
            if not hay:
                continue
            L.append(f" {i:3d} {x['nombre']:<8} {x['primer_anio']:4d} "
                     f"{x['ultimo_anio']:4d}  " + "".join(celdas).rstrip())
        # Correlación media de cada columna
        medias = []
        for g in bloque:
            vs = [d[g]["r"] for _, _, d in por_serie
                  if g in d and np.isfinite(d[g]["r"])]
            medias.append(_f3(np.mean(vs), 2) + " " if vs else " " * 5)
        L.append(" Correlación media".ljust(PREFIJO) + "".join(medias).rstrip())
    L.append(" " + "=" * (ANCHO - 2))
    return L


def _envolver(items, por_linea: int, sangria: str) -> list[str]:
    """Reparte una lista de textos en varias líneas, como hace COFECHA."""
    L = []
    for k in range(0, len(items), por_linea):
        L.append(sangria + "".join(items[k:k + por_linea]).rstrip())
    return L


def _parte6(res: dict, fecha: str) -> list[str]:
    """Problemas potenciales, con las cinco subsecciones de COFECHA."""
    L = _titulo("PARTE 6:  PROBLEMAS POTENCIALES", 6, fecha)
    o = res["opciones"]
    L.append("")
    L.append(" Para cada serie con problemas potenciales pueden aparecer estos diagnósticos:")
    L.append("")
    L.append(f" [A] Correlaciones con la serie maestra de los segmentos MARCADOS de"
             f" {o['largo_segmento']} años, filtrados con spline de"
             f" {o['rigidez_spline']} años,")
    L.append("     en cada posición desde diez años antes (-10) hasta diez años después (+10) de la fechada")
    L.append("")
    L.append(" [B] Efecto de los años que más bajan o suben la correlación con la maestra")
    L.append("")
    L.append(" [C] Cambios año a año muy distintos del cambio medio en las otras series")
    L.append("")
    L.append(" [D] Anillos ausentes (valores cero)")
    L.append("")
    L.append(" [E] Valores que son atípicos respecto de la media del año")
    L.append(" " + "=" * (ANCHO - 2))
    L.append("")

    desfases = list(range(-10, 11))
    prof = res.get("profundidad")
    maestro = res.get("maestro")
    n_con_problemas = 0

    for i, s_ in enumerate(res["series"], start=1):
        marcados = [x for x in s_["segmentos"] if x.get("bandera")]
        # COFECHA imprime TODAS las series acá, numeradas de forma correlativa
        # según su posición en el archivo: verificado en ACOF.OUT, 40 series
        # impresas y numeración de 1 a 40 sin saltos. DPI se saltaba las
        # series sin problemas, y la numeración quedaba con huecos — justo lo
        # que hace difícil encontrar una serie en el informe.
        tiene_algo = bool(marcados or s_.get("ausentes") or s_.get("atipicos")
                          or s_.get("divergentes"))
        n_con_problemas += int(tiene_algo)
        cabecera = (f" {s_['nombre']:<9}{s_['primer_anio']:5d} a "
                    f"{s_['ultimo_anio']:5d}  {s_['n_anios']:5d} años")
        cola = f"Serie {i:5d}"
        L.append(cabecera.ljust(max(1, ANCHO - 2 - len(cola))) + cola)
        L.append("")
        if not tiene_algo:
            L.append("     Sin problemas detectados.")
            L.append(" " + "=" * (ANCHO - 2))
            L.append("")
            continue

        # ── [A] correlaciones por desfase, SOLO de los segmentos marcados ──
        if marcados:
            L.append(" [A] Segmento   Alta   "
                     + "".join(f"{d:+4d} " for d in desfases).replace("+0", "  0"))
            L.append("    ---------   ----   " + "---- " * len(desfases))
            for x in marcados:
                rsd = x.get("rs_por_desfase") or {}
                if not rsd:
                    continue
                mejor = int(x.get("mejor_desfase", 0))
                celdas = []
                for d in desfases:
                    if d not in rsd:
                        celdas.append("  -  ")
                        continue
                    marca = "*" if (d == mejor and d != 0) else (
                        "|" if d == 0 else " ")
                    celdas.append(f"{_f3(rsd[d], 2)}{marca}")
                # La columna "Alta" lleva el desfase sin signo cuando es cero:
                # un "+0" no significa nada y confunde con un desfase real.
                L.append(f"    {x['inicio']:4d} {x['fin']:4d}   {mejor:4d}   "
                         + "".join(celdas))
            L.append("")

        # ── [B] años que más afectan la correlación ─────────────────
        ag = s_.get("aporte_global") or {}
        if ag.get("bajan") or ag.get("suben"):
            baja = "".join(f"{a:6d} {_f3(v)}" for a, v in ag.get("bajan", []))
            sube = "".join(f"{a:6d} {_f3(v)}" for a, v in ag.get("suben", []))
            L.append(f" [B] Serie completa, efecto sobre la correlación"
                     f" ({_f3(ag.get('r'))}):")
            L.append(f"       Bajan{baja}  Suben{sube}")
            for seg in s_.get("aporte_segmentos", []):
                b = "".join(f"{a:6d} {_f3(v)}" for a, v in seg["bajan"])
                u = "".join(f"{a:6d} {_f3(v)}" for a, v in seg["suben"])
                L.append(f"     segmento {seg['inicio']} a {seg['fin']}:")
                L.append(f"       Bajan{b}  Suben{u}")
            L.append("")

        # ── [C] cambios año a año divergentes ───────────────────────
        div = s_.get("divergentes") or []
        if div:
            L.append(" [C] Cambios año a año que divergen más de 4.0"
                     " desviaciones típicas:")
            L += _envolver([f"{a:6d} {b:5d} {z:+5.1f} DE;   " for a, b, z in div],
                           4, "     ")
            L.append("")

        # ── [D] anillos ausentes, con el contexto de la maestra ─────
        aus = s_.get("ausentes") or []
        if aus:
            L.append(f" [D] {len(aus):4d} anillos ausentes:  Año   Maestra"
                     "  N series  Ausentes")
            for a in aus:
                val = float(maestro.get(a, np.nan)) if maestro is not None else np.nan
                n_ser = int(prof.get(a, 0)) if prof is not None else 0
                n_aus = sum(1 for x in res["series"] if a in (x.get("ausentes") or []))
                L.append(f"                         {a:5d}  {_f3(val)}"
                         f"     {n_ser:5d}     {n_aus:5d}")
            L.append("")

        # ── [E] valores atípicos ────────────────────────────────────
        at = s_.get("atipicos") or []
        if at:
            L.append(f" [E] Valores atípicos {len(at):5d}"
                     "   3.0 DE sobre o -4.5 DE bajo la media del año")
            L += _envolver([f"{a:6d} {z:+5.1f} DE;  " for a, z in at],
                           7, "     ")
            L.append("")
        L.append(" " + "=" * (ANCHO - 2))
        L.append("")

    if n_con_problemas == 0:
        L.append(" No se detectaron series con problemas.")
    return L


def _n3(x) -> str:
    """Número en 3 decimales SIN el cero inicial, como COFECHA: .751, -.049."""
    if x is None or not np.isfinite(x):
        return "     "
    t = f"{x:.3f}"
    return t.replace("0.", ".", 1) if t.startswith(("0.", "-0.")) is False \
        else t.replace("0.", ".", 1)


def _n2(x) -> str:
    if x is None or not np.isfinite(x):
        return "     "
    return f"{x:.2f}"


def _parte7(res: dict, fecha: str) -> list[str]:
    """Estadísticos descriptivos, con las columnas del original.

    Anchos calcados de COS4COF.OUT. Dos detalles que estaban distintos: los
    valores menores que uno se escriben sin el cero inicial (.751, no 0.751)
    y al final va la fila de totales, que faltaba.
    """
    L = _titulo("PARTE 7:  ESTADÍSTICOS DESCRIPTIVOS", 7, fecha)
    L.append(" ")
    L.append(" NOTA sobre las columnas FILTRADAS: se calculan sobre el índice"
             " tras el spline y el modelo autorregresivo,")
    L.append("      antes del logaritmo. COFECHA informa en esas dos columnas"
             " valores cerca del doble de estos;")
    L.append("      la diferencia es de reporte y no afecta a ninguna"
             " correlación ni al marcado de segmentos.")
    L.append(" ")
    L.append(" " * 48 + "Corr   //------- Sin filtrar --------\\\\"
             "  //---- Filtrada -----\\\\")
    L.append(" " * 27 + "Nº     Nº     Nº     con    Media  Máx     Desv"
             "   Auto   Sens   Máx     Desv   Auto  AR")
    L.append(" Nº  Serie    Extensión   Años  Segmt  Marcas  Maestra medic"
             "  medic    est   corr  media  valor    est   corr  ()")
    L.append(" --- -------- ---------  -----  -----  -----   ------ -----"
             "  -----  -----  -----  -----  -----  -----  -----  --")
    for i, x in enumerate(res["series"], start=1):
        L.append(
            f"{i:4d} {x['nombre']:<8} {x['primer_anio']:4d} {x['ultimo_anio']:4d}"
            f"{x['n_anios']:7d}{x['n_segmentos']:7d}{x['n_banderas']:7d}"
            f"{_n3(x['r_maestro']):>8}"
            f"{_n2(x['media_cruda']):>7}{_n2(x['max_cruda']):>7}"
            f"{_n3(x['sd_cruda']):>7}{_n3(x['autocorr_cruda']):>7}"
            f"{_n3(x['sensibilidad']):>7}"
            f"{_n2(x['max_filt']):>7}{_n3(x['sd_filt']):>7}"
            f"{_n3(x['autocorr_filt']):>7}{x['orden_ar']:4d}")
    L.append(" --- -------- ---------  -----  -----  -----   ------ -----"
             "  -----  -----  -----  -----  -----  -----  -----  --")
    ser = res["series"]
    if ser:
        def _m(k):
            v = [x[k] for x in ser if np.isfinite(x.get(k, np.nan))]
            return float(np.mean(v)) if v else float("nan")
        L.append(
            " Total o media:          "
            f"{sum(x['n_anios'] for x in ser):8d}"
            f"{sum(x['n_segmentos'] for x in ser):7d}"
            f"{sum(x['n_banderas'] for x in ser):7d}"
            f"{_n3(res.get('intercorrelacion')):>8}"
            f"{_n2(_m('media_cruda')):>7}"
            f"{_n2(max((x['max_cruda'] for x in ser), default=float('nan'))):>7}"
            f"{_n3(_m('sd_cruda')):>7}{_n3(_m('autocorr_cruda')):>7}"
            f"{_n3(res.get('sensibilidad_media')):>7}"
            f"{_n2(_m('max_filt')):>7}{_n3(_m('sd_filt')):>7}"
            f"{_n3(_m('autocorr_filt')):>7}")
    L.append(" " + "=" * (ANCHO - 2))
    return L


def generar_informe(res: dict, titulo: str = "Colección sin nombre",
                     partes: str = "1234567") -> str:
    """Arma el informe completo de texto a partir del análisis."""
    fecha = _dt.datetime.now().strftime("%H:%M  %a %d %b %Y")
    generadores = {
        "1": _parte1, "2": _parte2, "3": _parte3, "4": _parte4,
        "5": _parte5, "6": _parte6, "7": _parte7,
    }
    res.setdefault("opciones", {})["partes"] = partes
    lineas = []
    for p in partes:
        gen = generadores.get(p)
        if gen is None:
            continue
        lineas += (gen(res, titulo, fecha) if p == "1"
                   else gen(res, fecha))
        lineas.append("")
    return "\n".join(lineas)
