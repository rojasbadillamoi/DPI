"""Operaciones extraídas sin modificar sus algoritmos."""
import re
import pandas as pd

def leer_formato_compacto(ruta: str, divisor: float = 100.0) -> dict:
    """Lee formato compacto FORTRAN (20F4.0) de CATRAS/Heidelberg."""
    import re
    series_dict = {}
    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        lineas = f.readlines()

    i = 0
    while i < len(lineas):
        linea = lineas[i].rstrip('\n\r')
        if not linea:
            i += 1
            continue

        if "=N" in linea and "=I" in linea:
            match_i = re.search(r'(\d+)=I', linea)
            anio_inicio = int(match_i.group(1)) if match_i else 0

            partes = linea.split('=I')
            if len(partes) > 1:
                subpartes = partes[1].strip().split()
                serie_id = subpartes[0] if subpartes else f"Serie_{len(series_dict)+1}"
            else:
                serie_id = f"Serie_{len(series_dict)+1}"

            i += 1
            valores = []
            while i < len(lineas) and "=N" not in lineas[i] and "=I" not in lineas[i]:
                linea_datos = lineas[i].rstrip('\n\r')
                for j in range(0, len(linea_datos), 4):
                    chunk = linea_datos[j:j+4]
                    if chunk.strip():
                        try:
                            valores.append(float(chunk.strip()) / divisor)
                        except ValueError:
                            pass
                i += 1

            if valores:
                anios = list(range(anio_inicio, anio_inicio + len(valores)))
                df = pd.DataFrame({"Anio": anios, "Ancho_mm": valores})
                df.set_index("Anio", inplace=True)
                series_dict[serie_id] = df
        else:
            i += 1

    return series_dict
