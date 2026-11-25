"""Parámetros científicos compartidos."""

# --- Ventana deslizante de co-datación ---
VENTANA_COFECHADO_DEFECTO = 40
OVERLAP_MINIMO_ANALISIS = 10   # Años mínimos de solapamiento para calcular r
OVERLAP_MINIMO_GRAFICO = 5    # Años mínimos para subventanas del motor split-window

# Solape mínimo para DATAR UNA SERIE FLOTANTE. Es mucho más alto que
# OVERLAP_MINIMO_ANALISIS a propósito: al deslizar una serie por cientos de
# posiciones, las de los extremos tienen poquísimo solape y ahí la correlación
# alcanza valores altos por puro azar. Medido con una serie de 310 anillos
# desplazada 300 años, usando diferencias-log: con solape mínimo de 10 años el
# desfase VERDADERO caía al cuarto puesto, detrás de tres posiciones de 10 a 20
# años de solape. Es el valor por omisión de `xdate.floater` en dplR.
OVERLAP_MINIMO_FLOTANTE = 50
RANGO_SHIFT_SIMULADOR = 5      # ±años que prueba el simulador de anillos

# --- Umbrales estadísticos por defecto (panel co-datación) ---
UMBRAL_ANCLA_DEFECTO = 0.40    # r mínimo para considerar un segmento "cofechado"
UMBRAL_DESFASE_DEFECTO = 0.25  # r máximo para considerar un segmento "con error"
UMBRAL_MEJORA_DEFECTO = 0.35   # Mejora de r mínima para sugerir cambio

# --- Supresión de no-máximos en detección de anomalías ---
VENTANA_SUPRESION_ANOMALIAS = 7  # Años de radio para suprimir duplicados
