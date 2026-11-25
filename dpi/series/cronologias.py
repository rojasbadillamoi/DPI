"""Preparación de candidatos a cronologías externas sin Qt."""
import pandas as pd


def candidatos_cronologias(hojas, base_nombre):
    # Detectar columnas auxiliares y descartarlas.
    # Una cronología exportada típicamente trae el VALOR del
    # índice + columnas auxiliares (tamaño de muestra, EPS,
    # Rbar, desviación estándar, etc). Antes cada columna se
    # cargaba como una cronología separada, por eso el usuario
    # veía aparecer 2 o más cronologías al abrir UN archivo.
    # Acá filtramos por nombre los auxiliares conocidos para
    # quedarnos solo con las columnas que son valores de
    # cronología real.
    AUX_COLUMNAS = {
        # Tamaño de muestra
        "n", "n_series", "n_samples", "sample_size", "samples",
        "depth", "count", "cantidad",
        # Dispersión
        "sd", "std", "stdev", "stderr", "se", "desv_std",
        "desviacion", "desviación",
        # Estadísticos de calidad
        "rbar", "r_bar", "eps", "snr",
        # Año (debería estar como índice pero por si acaso)
        "anio", "año", "year",
    }

    # Armar la lista de candidatos: cada par (hoja, columna) que
    # tenga datos es una cronología potencial.
    candidatos = []  # [(etiqueta, nombre_crono, df_serie)]
    for nombre_hoja, df_multi in hojas.items():
        cols_validas = [
            c for c in df_multi.columns
            if str(c).strip().lower() not in AUX_COLUMNAS
        ]
        # Si el filtro quitó todo (raro), no aplicamos el filtro
        if not cols_validas:
            cols_validas = list(df_multi.columns)

        for col in cols_validas:
            df_serie = pd.DataFrame(
                {"Ancho_mm": pd.to_numeric(df_multi[col],
                                           errors="coerce")},
                index=df_multi.index,
            ).dropna()
            if df_serie.empty:
                continue

            # Nombre único por cronología. Antes todas las
            # columnas se agregaban con el MISMO nombre
            # (el del archivo), así que chocaban entre sí.
            # Solo se agrega la hoja si hay más de una, y la
            # columna si hay más de una, para no ensuciar el
            # nombre con partes redundantes.
            partes = [base_nombre]
            if nombre_hoja and len(hojas) > 1:
                partes.append(str(nombre_hoja))
            if len(cols_validas) > 1:
                partes.append(str(col))
            nombre_crono = "_".join(partes)

            etiqueta = nombre_crono
            if len(df_serie):
                etiqueta += (f"   ({df_serie.index.min()}–"
                             f"{df_serie.index.max()}, "
                             f"{len(df_serie)} años)")
            candidatos.append((etiqueta, nombre_crono, df_serie))
    return candidatos
