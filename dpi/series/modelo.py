"""Estado de series de co-datación, independiente de Qt."""
from dataclasses import dataclass
from collections.abc import Mapping

import pandas as pd
import numpy as np
from dpi.ciencia.indice_anual import validar_anios


@dataclass(frozen=True)
class _PruebaCorreccion:
    nombre: str
    respaldo: pd.DataFrame


@dataclass(slots=True)
class _Serie:
    original: pd.DataFrame
    actual: pd.DataFrame


class _LecturaSeries(Mapping):
    def __init__(self, series, campo):
        self._series = series
        self._campo = campo

    def __getitem__(self, nombre):
        return getattr(self._series[nombre], self._campo).copy(deep=True)

    def __iter__(self):
        return iter(self._series)

    def __len__(self):
        return len(self._series)

    def __contains__(self, nombre):
        return nombre in self._series


class ModeloSeries:
    """Conserva datos editables y originales independientes.

    Las vistas públicas entregan copias independientes de los datos.
    """
    def __init__(self):
        self._series: dict[str, _Serie] = {}
        self._prueba: _PruebaCorreccion | None = None
        self._revision = 0
        self.originales = _LecturaSeries(self._series, "original")
        self.datos = _LecturaSeries(self._series, "actual")

    def nombres(self):
        return tuple(self._series)

    @property
    def revision(self):
        return self._revision

    @property
    def nombre_en_prueba(self):
        return self._prueba.nombre if self._prueba else None

    def _exigir_sin_prueba(self, nombre):
        if self.nombre_en_prueba == nombre:
            raise ValueError('Confirme o descarte la corrección temporal primero')

    def probar_correccion(self, nombre, df):
        """Instala una vista temporal sin alterar la serie original."""
        if self._prueba is not None:
            raise ValueError('Ya existe una corrección temporal')
        respaldo = self._series[nombre].actual.copy()
        corregido = self._validar(df)
        self._series[nombre].actual = corregido
        self._prueba = _PruebaCorreccion(nombre, respaldo)
        self._revision += 1

    def confirmar_correccion(self):
        """Conserva los datos de la prueba, no sustituye el original."""
        if self._prueba is None:
            return False
        self._prueba = None
        return True

    def descartar_correccion(self):
        """Recupera el estado anterior a la prueba, incluidas ediciones previas."""
        if self._prueba is None:
            return False
        prueba = self._prueba
        self._series[prueba.nombre].actual = prueba.respaldo
        self._revision += 1
        self._prueba = None
        return True

    @staticmethod
    def _validar(df):
        if not isinstance(df, pd.DataFrame) or 'Ancho_mm' not in df.columns:
            raise ValueError('La serie debe contener Ancho_mm')
        if not df.columns.is_unique:
            raise ValueError('Columnas duplicadas en la serie')
        datos = df.copy()
        datos.index = pd.Index(validar_anios(datos.index), name=df.index.name)
        if not datos.index.is_unique or datos.empty:
            raise ValueError('Serie vacía o años duplicados')
        valores = pd.to_numeric(datos['Ancho_mm'], errors='raise')
        if np.isinf(valores).any():
            raise ValueError('Valores infinitos')
        if not valores.notna().any():
            raise ValueError('Serie sin valores válidos')
        datos['Ancho_mm'] = valores
        return datos.sort_index()

    def registrar(self, nombre, df):
        if nombre in self._series:
            raise ValueError(f"Serie ya registrada: {nombre}")
        self.reemplazar(nombre, df)

    def registrar_lote(self, series):
        """Valida todo el lote antes de cambiar el modelo."""
        nuevos = {}
        for nombre, df in series.items():
            if nombre not in self._series:
                datos = self._validar(df)
                nuevos[nombre] = _Serie(datos.copy(), datos)
        self._series.update(nuevos)
        self._revision += len(nuevos)
        return [(nombre, nombre in nuevos) for nombre in series]

    def reemplazar(self, nombre, df):
        """Sustitución explícita, incluido el original."""
        self._exigir_sin_prueba(nombre)
        datos = self._validar(df)
        original = datos.copy()
        self._series[nombre] = _Serie(original, datos)
        self._revision += 1

    def eliminar(self, nombre):
        self._exigir_sin_prueba(nombre)
        if nombre in self._series:
            del self._series[nombre]
            self._revision += 1

    def restablecer(self, nombre):
        self._exigir_sin_prueba(nombre)
        self._series[nombre].actual = self._series[nombre].original.copy()
        self._revision += 1

    def actualizar(self, nombre, df):
        """Valida una edición sin sustituir el respaldo original."""
        self._exigir_sin_prueba(nombre)
        if nombre not in self._series:
            raise KeyError(nombre)
        datos = self._validar(df)
        self._series[nombre].actual = datos
        self._revision += 1

    def desplazar(self, nombre, shift):
        self._exigir_sin_prueba(nombre)
        serie = self._series.get(nombre)
        df = serie.actual if serie is not None else None
        if not isinstance(shift, (int, np.integer)) or isinstance(shift, bool):
            raise ValueError('El desfase debe ser entero')
        if shift == 0 or df is None or df.empty:
            return False
        nuevo = df.copy()
        nuevo.index = pd.Index([int(a) + int(shift) for a in nuevo.index], name=nuevo.index.name)
        self.actualizar(nombre, nuevo)
        return True


def validar_anchos_fisicos(anchos):
    """Los anchos físicos admiten cero y faltantes, no negativos ni booleanos."""
    if any(isinstance(v, (bool, np.bool_)) for v in anchos):
        raise ValueError('Anchos booleanos')
    valores = pd.to_numeric(anchos, errors='raise')
    if (valores < 0).any():
        raise ValueError('Anchos negativos')
