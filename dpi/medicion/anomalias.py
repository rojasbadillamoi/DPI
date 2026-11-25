"""Proyección tabular de eventos de anillos, independiente de Qt."""
import pandas as pd


def tabla_eventos(anios, anomalias, tipos):
    """Construye las columnas binarias en el orden de los tipos solicitados."""
    filas = []
    for anio in anios:
        tipo_anio = anomalias.get(anio)
        fila = {"Año": anio}
        for codigo, nombre in tipos:
            fila[nombre] = int(tipo_anio == codigo)
        filas.append(fila)
    return pd.DataFrame(filas)
