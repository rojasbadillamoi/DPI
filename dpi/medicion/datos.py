"""Proyecciones de medición y migración de radios, independientes de Qt."""
from dpi.medicion.calculo import anchos_puntos, anios_medicion
from dpi.medicion.modelo import PuntoMedicion, RadioMedicion


def mediciones_desde_anchos(anchos, medula, corteza, med_a_cor):
    anios = anios_medicion(len(anchos), medula, corteza, med_a_cor)
    return [{"anio": a, "ancho_mm": w} for a, w in zip(anios, anchos)]


def normalizar_radio(radio):
    """Migra metadatos de sesiones antiguas sin modificar el diccionario original."""
    datos = dict(radio)
    legacy = datos.get("datos_medidos", [])
    if legacy:
        primero, ultimo = legacy[0]["anio"], legacy[-1]["anio"]
    else:
        primero = ultimo = 0
    datos.setdefault("dir_idx", int(primero > ultimo))
    inverso = datos["dir_idx"] != 0
    datos.setdefault("anio_medula", datos.get("anio_inicio", ultimo if inverso else primero))
    datos.setdefault("anio_corteza", datos.get("anio_actual", primero if inverso else ultimo))
    coords = datos.get("coords", datos.get("coordenadas", []))
    # No perder una serie antigua cuya geometría no está disponible.
    if len(coords) >= 2 and len(coords) == len(datos.get("es_salto", [])):
        datos.pop("datos_medidos", None)
    return datos


def radio_desde_dict(radio):
    """Adaptador histórico: el cálculo posterior solo recibe radios tipados."""
    datos = normalizar_radio(radio)
    coords = datos.get("coords", datos.get("coordenadas", []))
    marcas = datos.get("es_salto", [])
    puntos = tuple(PuntoMedicion(c, m) for c, m in zip(coords, marcas, strict=True))
    return RadioMedicion(datos.get("codigo"), puntos, datos["anio_medula"],
        datos["anio_corteza"], datos["dir_idx"], datos.get("anomalias", {}),
        datos.get("medula", False), datos.get("corteza", False),
        tuple((d["anio"], d["ancho_mm"]) for d in datos.get("datos_medidos", [])))


def mediciones_radio(radio, ppm):
    if not isinstance(radio, RadioMedicion):
        radio = radio_desde_dict(radio)
    if len(radio.puntos) < 2:
        return [{"anio": a, "ancho_mm": w} for a, w in radio.datos_historicos]
    return mediciones_desde_anchos(
        anchos_puntos(radio.puntos, ppm), radio.anio_medula,
        radio.anio_corteza, radio.dir_idx == 0)
