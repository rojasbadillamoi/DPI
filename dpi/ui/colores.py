"""Colores y marcadores de la interfaz."""
# --- Tipos de anomalía: clave → (icono, etiqueta, color_hex) ---
# Fuente única de verdad — importar desde aquí en todos los módulos.
TIPOS_ANOMALIA: dict[str, tuple[str, str, str]] = {
    "frost_ring":  ("❄",  "Frost ring",    "#00BFFF"),
    "light_ring":  ("☀",  "Light ring",    "#FFD700"),
    "fire":        ("🔥", "Fuego",         "#FF4500"),
    "compression": ("▼",  "Comp. madera",  "#FF6600"),
    "tension":     ("▲",  "Tensión",       "#9933CC"),
    "false_ring":  ("⊘",  "Falso anillo",  "#3399FF"),
    "wedge":       ("◆",  "Cuña",          "#CCAA00"),
    "resin":       ("●",  "Resina",        "#8B4513"),
    "event":       ("★",  "Otro/Genérico", "#CC0000"),
}

# --- Colores (RGB tuples para pyqtgraph) ---
COLORES_SERIES = [
    (255, 51, 51),
    (51, 136, 255),
    (51, 204, 51),
    (255, 204, 51),
    (204, 51, 255),
]
COLORES_SERIES_INACTIVAS = [
    (51, 204, 51),
    (255, 204, 51),
    (204, 51, 255),
    (255, 102, 0),
]

COLOR_PUNTO_ACTIVO = "#FF3333"
COLOR_LINEA_ACTIVA = "#3388FF"
COLOR_SALTO = "#FFD700"
COLOR_GUIA = "#aaaaaa"
COLOR_CALIBRACION = "#33FF33"
COLOR_PUNTO_INACTIVO = "#5cb85c"
COLOR_EWLW           = "#FF8C00"   # naranja — límite earlywood/latewood

# --- Marcadores de décadas en la imagen ---
INTERVALO_MARCADOR_DECADA = 10
INTERVALO_MARCADOR_CINCUENTENA = 50
INTERVALO_MARCADOR_CENTENA = 100
