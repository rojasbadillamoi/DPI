"""Identificación y orden natural de códigos dendrocronológicos."""

import re


def _clave_orden_natural(texto: str) -> list:
    """Genera una clave de orden alfanumérico natural.

    Permite que ['a1', 'a2', 'a10'] se ordenen como [a1, a2, a10] en
    lugar del orden lexicográfico clásico [a1, a10, a2]. Esto es
    importante en dendrocronología donde los códigos suelen tener
    sufijos numéricos (AUST001, AUST002, ..., AUST010) y el orden
    lexicográfico no respeta la secuencia natural.

    Funciona partiendo el texto en runs alternados de dígitos y no
    dígitos, convirtiendo los runs numéricos a int para que la
    comparación los ordene como números, no como strings.
    """
    partes = re.split(r'(\d+)', texto)
    return [int(p) if p.isdigit() else p.lower() for p in partes]


def clave_codigo_dendro(codigo: str) -> tuple:
    """Ordena códigos dendrocronológicos por sitio, árbol y radio.

    Un código como QLH107A se lee como tres cosas distintas, no como una
    cadena: el SITIO (QLH), el número de ÁRBOL (107) y el RADIO o dígito
    verificador (A). Ordenar alfabéticamente mezcla los tres y produce
    secuencias como COS1, COS10, COS2; ordenar solo por número natural pone
    juntos radios de árboles distintos cuando los sufijos difieren en largo.

    Esta clave separa las tres partes y ordena por sitio, después por número
    de árbol como NÚMERO, y por último por radio. Así QLH107A, QLH107B,
    QLH108A quedan en el orden en que uno los mira en la mesa.

    Casos que cubre:
      QLH107A   -> ('QLH', 107, 'A')          radio simple
      COS300    -> ('COS', 300, '')           sin radio
      QLP006bA  -> ('QLP', 6, 'BA')           radio compuesto
      SAN001C_2 -> ('SAN', 1, 'C_2')          renombrado por duplicado
      raro-01   -> ('RARO-', 1, '')           cualquier prefijo con símbolos

    Si el código no trae número, cae al final del grupo de su sitio, con el
    resto ordenado de forma natural.
    """
    txt = str(codigo).strip()
    m = re.match(r"^(.*?)(\d+)(.*)$", txt)
    if not m:
        return (txt.upper(), 10 ** 9, "", _clave_orden_natural(txt))
    prefijo, numero, sufijo = m.group(1), int(m.group(2)), m.group(3)
    return (prefijo.upper(), numero, sufijo.upper(),
            _clave_orden_natural(txt))
