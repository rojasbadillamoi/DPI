"""Persistencia y validación de sesiones de medición, sin Qt."""
import math
import os
from numbers import Real

from dpi.ciencia.indice_anual import validar_anios
from dpi.infraestructura.json_seguro import guardar_json, cargar_json
from dpi.medicion.datos import normalizar_radio, radio_desde_dict
from dpi.medicion.modelo import RadioMedicion

VERSION_FORMATO = 1


def ruta_sesion(ruta_imagen):
    directorio, nombre = os.path.split(ruta_imagen)
    return os.path.join(directorio, f".{nombre}_dpi.json")


def _validar_radio(radio, *, activo=False):
    if not isinstance(radio, dict):
        raise ValueError("Radio inválido: se esperaba un objeto")
    # Validar también la información histórica antes de migrarla.
    legacy = radio.get("datos_medidos", [])
    if not isinstance(legacy, list):
        raise ValueError("datos_medidos inválidos")
    for dato in legacy:
        if (not isinstance(dato, dict) or type(dato.get("anio")) is not int
                or not _numero_finito(dato.get("ancho_mm"))):
            raise ValueError("Medición histórica inválida")
    datos = normalizar_radio(radio)
    if "anomalias" in datos:
        if not isinstance(datos["anomalias"], dict):
            raise ValueError("Anomalías inválidas")
        anomalias = {}
        for k, v in datos["anomalias"].items():
            if isinstance(k, bool) or not isinstance(k, (str, int)) or not isinstance(v, str):
                raise ValueError("Anomalía inválida")
            anio = int(validar_anios([int(k)])[0])
            if anio in anomalias:
                raise ValueError("Año de anomalía duplicado")
            anomalias[anio] = v
        datos["anomalias"] = anomalias
    clave = "coordenadas" if activo else "coords"
    alternativa = "coords" if activo else "coordenadas"
    coords = datos.get(clave, datos.get(alternativa, []))
    marcas = datos.get("es_salto", [])
    if not isinstance(coords, (list, tuple)) or not isinstance(marcas, (list, tuple)):
        raise ValueError("Geometría de radio inválida")
    if clave in datos and alternativa in datos and datos[clave] != datos[alternativa]:
        raise ValueError("Representaciones de geometría incompatibles")
    if activo and legacy and len(coords) < 2:
        raise ValueError("Radio activo histórico sin geometría editable")
    if "codigo" in datos and not isinstance(datos["codigo"], str):
        raise ValueError("Código de radio inválido")
    radio_tipado = radio_desde_dict(datos)
    datos[clave] = list(radio_tipado.coordenadas)
    datos["es_salto"] = list(radio_tipado.marcas)
    datos.pop(alternativa, None)
    return datos


def _numero_finito(valor):
    return isinstance(valor, Real) and not isinstance(valor, bool) and math.isfinite(valor)


def normalizar_sesion(datos):
    """Valida y migra una sesión completa antes de entregarla al consumidor."""
    if not isinstance(datos, dict):
        raise ValueError("La sesión debe ser un objeto JSON")
    version = datos.get("version_formato", 0)
    if type(version) is not int or version not in (0, VERSION_FORMATO):
        raise ValueError(f"Versión de sesión no compatible: {version!r}")
    resultado = dict(datos)
    resultado["version_formato"] = VERSION_FORMATO
    if "pixeles_por_mm" in datos:
        ppm = datos["pixeles_por_mm"]
        if not _numero_finito(ppm) or ppm <= 0:
            raise ValueError("Escala de sesión inválida")
        resultado["pixeles_por_mm"] = float(ppm)
    radios = datos.get("caminos_guardados", {})
    if not isinstance(radios, dict):
        raise ValueError("Colección de radios inválida")
    resultado["caminos_guardados"] = {}
    for nombre, radio in radios.items():
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("Nombre de radio inválido")
        try:
            resultado["caminos_guardados"][nombre] = _validar_radio(radio)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise ValueError(f"Radio {nombre!r}: {exc}") from exc
    activo = datos.get("camino_activo", {})
    if not isinstance(activo, dict):
        raise ValueError("Radio activo inválido")
    resultado["camino_activo"] = _validar_radio(activo, activo=True) if activo else {}
    return resultado


def leer_sesion(ruta_imagen):
    """Devuelve None solo cuando no existe el archivo de sesión."""
    try:
        with open(ruta_sesion(ruta_imagen), encoding="utf-8-sig") as archivo:
            datos = cargar_json(archivo)
    except FileNotFoundError:
        return None
    datos = normalizar_sesion(datos)
    datos["caminos_guardados"] = {
        nombre: radio_desde_dict(radio)
        for nombre, radio in datos["caminos_guardados"].items()}
    activo = datos["camino_activo"]
    datos["camino_activo"] = radio_desde_dict(activo) if activo else None
    return datos


def guardar_sesion(ruta_imagen, ppm, radios, activo):
    """Valida antes de reemplazar atómicamente la sesión anterior."""
    datos = normalizar_sesion({
        "pixeles_por_mm": ppm,
        "caminos_guardados": {
            nombre: radio.a_dict() if isinstance(radio, RadioMedicion) else radio
            for nombre, radio in radios.items()},
        "camino_activo": activo.a_dict(activo=True)
        if isinstance(activo, RadioMedicion) else activo,
    })
    guardar_json(ruta_sesion(ruta_imagen), datos, indent=None)
