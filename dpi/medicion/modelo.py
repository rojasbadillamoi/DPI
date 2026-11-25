"""Modelo de puntos de medición, independiente de la interfaz gráfica."""
from collections.abc import Sequence
from dataclasses import dataclass, replace, field
from types import MappingProxyType
from enum import Enum
from math import isfinite
from numbers import Real
from dpi.medicion.constantes import PIXELES_POR_MM_DEFECTO


class TipoMarca(Enum):
    NORMAL = False
    SALTO = True
    ESPACIO = 'espacio'
    EW_LW = 'ew_lw'
    QUIEBRE_INI = 'quiebre_ini'


    @classmethod
    def desde_valor(cls, valor):
        """Acepta marcas tipadas y los valores históricos del proyecto."""
        if isinstance(valor, cls):
            return valor
        if type(valor) not in (bool, str):
            raise ValueError(f"Marca inválida: {valor!r}")
        return cls(valor)

    @property
    def es_amarillo(self):
        return self in (TipoMarca.SALTO, TipoMarca.ESPACIO)

    @property
    def es_quiebre(self) -> bool:
        """Marcas de inicio y tramo de un quiebre intra-anillo."""
        return self in (TipoMarca.ESPACIO, TipoMarca.QUIEBRE_INI)

    @property
    def excluye_intensidad(self) -> bool:
        """Tramos excluidos de los perfiles de intensidad existentes."""
        return self is TipoMarca.SALTO or self.es_quiebre


@dataclass(frozen=True, slots=True)
class PuntoMedicion:
    coordenada: tuple[float, float]
    tipo: TipoMarca = TipoMarca.NORMAL

    def __post_init__(self):
        x, y = self.coordenada
        if not all(isinstance(v, Real) and not isinstance(v, bool)
                   and isfinite(v) for v in (x, y)):
            raise ValueError("Las coordenadas deben ser números finitos")
        object.__setattr__(self, "coordenada", (float(x), float(y)))
        object.__setattr__(self, "tipo", TipoMarca.desde_valor(self.tipo))


class _VistaCampo(Sequence):
    """Proyección viva de solo lectura, con los valores del formato histórico."""
    def __init__(self, modelo, marcas=False):
        self._modelo = modelo
        self._marcas = marcas

    def __len__(self):
        return len(self._modelo._puntos)

    def _valor(self, punto):
        return punto.tipo.value if self._marcas else punto.coordenada

    def __getitem__(self, indice):
        puntos = self._modelo._puntos[indice]
        if isinstance(indice, slice):
            return [self._valor(p) for p in puntos]
        return self._valor(puntos)

    def __iter__(self):
        return (self._valor(p) for p in self._modelo._puntos)

    def copy(self):
        return list(self)


class ModeloMedicion:
    def __init__(self):
        self._puntos = []
        self._pixeles_por_mm = PIXELES_POR_MM_DEFECTO
        self.anomalias: dict[int, str] = {}
        self.coordenadas = _VistaCampo(self)
        self.marcas = _VistaCampo(self, marcas=True)

    @property
    def pixeles_por_mm(self):
        return self._pixeles_por_mm

    @pixeles_por_mm.setter
    def pixeles_por_mm(self, valor):
        if not isinstance(valor, Real) or isinstance(valor, bool) or not isfinite(valor) or valor <= 0:
            raise ValueError("Escala de medición inválida")
        self._pixeles_por_mm = float(valor)

    def cargar(self, coordenadas, marcas):
        # Validar antes de sustituir el estado activo.
        puntos = [PuntoMedicion(c, m) for c, m in zip(coordenadas, marcas, strict=True)]
        self._puntos = puntos

    def insertar(self, indice, coordenada, marca=TipoMarca.NORMAL):
        self._puntos.insert(indice, PuntoMedicion(coordenada, marca))

    def agregar(self, coordenada, marca=TipoMarca.NORMAL):
        self._puntos.append(PuntoMedicion(coordenada, marca))

    def borrar(self, indice):
        del self._puntos[indice]

    def limpiar(self):
        self._puntos.clear()

    def mover(self, indice, coordenada):
        self._puntos[indice] = replace(self._puntos[indice], coordenada=coordenada)

    def marcar(self, indice, marca):
        self._puntos[indice] = replace(self._puntos[indice], tipo=marca)

    def editar_puntos(self, indices, tipo=None):
        """Borra o cambia marcas en bloque, validando antes de modificar."""
        indices = sorted(set(indices), reverse=True)
        if tipo is not None:
            tipo = TipoMarca.desde_valor(tipo)
        puntos = list(self._puntos)
        for i in indices:
            if 0 <= i < len(puntos):
                if tipo is None:
                    del puntos[i]
                else:
                    puntos[i] = replace(puntos[i], tipo=tipo)
        self._puntos = puntos

    def captura(self):
        return tuple(self._puntos)

    def restaurar(self, captura):
        puntos = list(captura)
        if not all(isinstance(p, PuntoMedicion) for p in puntos):
            raise ValueError("Captura de medición inválida")
        self._puntos = puntos


@dataclass(frozen=True)
class RadioMedicion:
    codigo: str | None
    puntos: tuple[PuntoMedicion, ...]
    anio_medula: int
    anio_corteza: int
    dir_idx: int
    anomalias: dict = field(default_factory=dict)
    medula: bool = False
    corteza: bool = False
    # Solo para radios históricos sin geometría suficiente.
    datos_historicos: tuple[tuple[int, float], ...] = ()

    def __post_init__(self):
        if type(self.dir_idx) is not int or self.dir_idx not in (0, 1):
            raise ValueError("Dirección de medición inválida")
        if any(type(a) is not int for a in (self.anio_medula, self.anio_corteza)):
            raise ValueError("Los años del radio deben ser enteros")
        if self.codigo is not None and not isinstance(self.codigo, str):
            raise ValueError("Código inválido")
        if type(self.medula) is not bool or type(self.corteza) is not bool:
            raise ValueError("Extremos deben ser booleanos")
        if any(type(k) is not int or not isinstance(v, str) for k,v in self.anomalias.items()):
            raise ValueError("Anomalías inválidas")
        puntos = tuple(self.puntos)
        if not all(isinstance(p, PuntoMedicion) for p in puntos):
            raise ValueError("Puntos de radio inválidos")
        historicos = tuple(tuple(d) for d in self.datos_historicos)
        if any(len(d) != 2 or type(d[0]) is not int or not isinstance(d[1], Real)
               or isinstance(d[1], bool) or not isfinite(d[1]) for d in historicos):
            raise ValueError("Medición histórica inválida")
        if len({d[0] for d in historicos}) != len(historicos):
            raise ValueError("Años históricos duplicados")
        if len(puntos) >= 2 and historicos:
            raise ValueError("Un radio geométrico no admite mediciones históricas")
        object.__setattr__(self, "puntos", puntos)
        object.__setattr__(self, "datos_historicos", historicos)
        object.__setattr__(self, "anomalias", MappingProxyType(dict(self.anomalias)))

    @property
    def coordenadas(self):
        return tuple(p.coordenada for p in self.puntos)

    @property
    def marcas(self):
        return tuple(p.tipo.value for p in self.puntos)

    def a_dict(self, *, activo=False):
        clave = "coordenadas" if activo else "coords"
        datos = {clave: list(self.coordenadas), "es_salto": list(self.marcas),
                 "anio_medula": self.anio_medula,
                 "anio_corteza": self.anio_corteza, "dir_idx": self.dir_idx,
                 "anomalias": dict(self.anomalias), "medula": self.medula,
                 "corteza": self.corteza}
        if self.codigo is not None:
            datos["codigo"] = self.codigo
        if self.datos_historicos:
            datos["datos_medidos"] = [
                {"anio": a, "ancho_mm": w} for a, w in self.datos_historicos]
        return datos


@dataclass(frozen=True, slots=True)
class EstadoEdicion:
    puntos: tuple[PuntoMedicion, ...]
    anomalias: tuple[tuple[int, str], ...]

    @classmethod
    def capturar(cls, modelo):
        return cls(modelo.captura(), tuple(modelo.anomalias.items()))

    def restaurar(self, modelo):
        modelo.restaurar(self.puntos)
        modelo.anomalias = dict(self.anomalias)


class HistorialMedicion:
    """Historial de geometría y anomalías; la calibración es independiente."""
    def __init__(self, modelo, limite):
        self.modelo = modelo
        self.limite = limite
        self._undo = []
        self._redo = []

    def guardar(self):
        self._undo.append(EstadoEdicion.capturar(self.modelo))
        if len(self._undo) > self.limite:
            self._undo.pop(0)
        self._redo.clear()

    def limpiar(self):
        self._undo.clear()
        self._redo.clear()

    def _cambiar(self, origen, destino):
        if not origen:
            return False
        destino.append(EstadoEdicion.capturar(self.modelo))
        origen.pop().restaurar(self.modelo)
        return True

    def deshacer(self):
        return self._cambiar(self._undo, self._redo)

    def rehacer(self):
        return self._cambiar(self._redo, self._undo)


class ModeloSesionMedicion:
    """Propietario de la geometría activa y los radios guardados tipados."""
    def __init__(self):
        self.activo = ModeloMedicion()
        self._radios = {}
        self.radios = MappingProxyType(self._radios)

    def cargar_radios(self, radios):
        nuevos = dict(radios)
        if not all(isinstance(r, RadioMedicion) for r in nuevos.values()):
            raise ValueError("Radio guardado inválido")
        self._radios.clear()
        self._radios.update(nuevos)

    def guardar_radio(self, nombre, radio):
        if not nombre or nombre in self._radios or not isinstance(radio, RadioMedicion):
            raise ValueError("Radio inválido o duplicado")
        self._radios[nombre] = radio

    def eliminar_radio(self, nombre):
        return self._radios.pop(nombre, None)
