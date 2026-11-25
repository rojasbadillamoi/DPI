"""Estado temporal por herramienta, independiente de Qt."""
from dataclasses import dataclass, field
from typing import Any

# Recursos de escena propiedad de la interfaz, no del modelo de medición.
RecursosEscena = list[Any]


@dataclass
class EstadoCalibracion:
    puntos: list = field(default_factory=list)
    items: RecursosEscena = field(default_factory=list)
    objetivo_mm: float | None = None


@dataclass
class EstadoSeleccion:
    puntos: set[int] = field(default_factory=set)
    items: RecursosEscena = field(default_factory=list)
    arrastre: bool = False
    inicio: tuple[float, float] = (0.0, 0.0)
    rectangulo: Any = None
    candidato: int | None = None
    posicion: tuple[float, float] = (0.0, 0.0)

    def alternar(self, indice):
        self.puntos.symmetric_difference_update({indice})


@dataclass
class EstadoEspacio:
    puntos: list = field(default_factory=list)
    items: RecursosEscena = field(default_factory=list)
    indice_inicio: int | None = None
    punto_inicio: tuple[float, float] = (0.0, 0.0)
    segmento_inicio: int = 0


@dataclass
class EstadoAutodeteccion:
    puntos: list = field(default_factory=list)
    items: RecursosEscena = field(default_factory=list)
    imagen: Any = None
    indice_ancla: int | None = None


def conserva_ancla(modo):
    from dpi.medicion.marcas import ModoMedicion
    return modo in (ModoMedicion.MEDIR, ModoMedicion.SALTO)
