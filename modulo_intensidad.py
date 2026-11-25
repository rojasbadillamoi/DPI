"""Diálogos de intensidad y API histórica de extracción/exportación."""
import math
import logging
import numpy as np
from dpi.medicion.intensidad import (
    CANALES, extraer_intensidad_por_anillo,
)
from dpi.formatos.tucson import escribir_rwl_intensidad

logger = logging.getLogger(__name__)


# =============================================================================
# DIÁLOGO DE CONFIGURACIÓN
# =============================================================================

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QSpinBox,
    QDialogButtonBox, QLabel, QGroupBox, QCheckBox,
)

class DialogoConfigBI(QDialog):
    """Configuración de la extracción de intensidad de color."""

    def __init__(self, banda_actual: int = 30,
                 canales_activos: list | None = None,
                 porcentaje: int = 100,
                 alineacion: str = "centro",
                 canal_vis: str = "B",
                 parent=None):
        super().__init__(parent)
        if canales_activos is None:
            canales_activos = ["B", "G", "R", "Gray"]
        self.setWindowTitle("Configurar extracción de intensidad (BI/GI/RI)")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Extrae la intensidad de los canales R, G, B y Gray\n"
            "a lo largo del radio medido, anillo por anillo.\n"
            "Compatible con el método de Maxwell et al. (2017)."
        ))

        grp = QGroupBox("Parámetros de muestreo")
        form = QFormLayout(grp)

        self.spin_banda = QSpinBox()
        self.spin_banda.setRange(0, 200)
        self.spin_banda.setValue(banda_actual)
        self.spin_banda.setSuffix(" px")
        self.spin_banda.setToolTip(
            "Píxeles a cada lado del camino para promediar.\n"
            "0 = solo el camino central.\n"
            "10 = banda de 21px de ancho total.\n"
            "CooRecorder usa típicamente 5-15px."
        )
        form.addRow("Banda (px a cada lado):", self.spin_banda)

        # Fila compacta: [___] % [EW] [Centro] [LW]  (como el selector Med/Cor)
        from PyQt6.QtWidgets import QHBoxLayout as _QHL, QRadioButton, QButtonGroup
        fila_pct = _QHL()

        self.spin_pct = QSpinBox()
        self.spin_pct.setRange(10, 100)
        self.spin_pct.setValue(porcentaje)
        self.spin_pct.setSuffix(" %")
        self.spin_pct.setFixedWidth(70)
        self.spin_pct.setToolTip(
            "Porcentaje del anillo a medir.\n"
            "100 = todo el anillo.  80 = descarta el 20% según alineación."
        )
        fila_pct.addWidget(self.spin_pct)
        fila_pct.addSpacing(8)

        self._btn_grp_alin = QButtonGroup(self)
        for etiq, val, tip in [
            ("EW",     "ew",     "Pegado a madera temprana.\nEl recorte se aplica al extremo de madera tardía."),
            ("Centro", "centro", "Centrado en el anillo.\nSe descarta el mismo margen en ambos extremos."),
            ("LW",     "lw",     "Pegado a madera tardía.\nEl recorte se aplica al extremo de madera temprana."),
        ]:
            rb = QRadioButton(etiq)

            rb.setToolTip(tip)
            rb.setProperty("alin_val", val)
            rb.setChecked(val == alineacion)
            self._btn_grp_alin.addButton(rb)
            fila_pct.addWidget(rb)

        fila_pct.addStretch()
        form.addRow("% anillo / alineación:", fila_pct)

        layout.addWidget(grp)

        grp2 = QGroupBox("Canales a calcular")
        form2 = QFormLayout(grp2)

        self.check_b    = QCheckBox("Blue Intensity (BI)")
        self.check_g    = QCheckBox("Green Intensity (GI)")
        self.check_r    = QCheckBox("Red Intensity (RI)")
        self.check_gray = QCheckBox("Gray Intensity — densidad de madera")
        self.check_b.setChecked("B" in canales_activos)
        self.check_g.setChecked("G" in canales_activos)
        self.check_r.setChecked("R" in canales_activos)
        self.check_gray.setChecked("Gray" in canales_activos)
        self.check_gray.setToolTip(
            "Canal de luminancia (escala de grises).\nSensible a la densidad de la madera.\nÚtil para detectar anillos falsos y bandas intra-anuales."
        )
        form2.addRow("", self.check_b)
        form2.addRow("", self.check_g)
        form2.addRow("", self.check_r)
        form2.addRow("", self.check_gray)
        layout.addWidget(grp2)

        grp3 = QGroupBox("Canal a visualizar en imagen")
        form3 = QFormLayout(grp3)
        from PyQt6.QtWidgets import QComboBox
        self.combo_canal_vis = QComboBox()
        for clave, etiq in [("B","Azul (BI)"),("G","Verde (GI)"),
                             ("R","Rojo (RI)"),("Gray","Gris (densidad)")]:
            self.combo_canal_vis.addItem(etiq, clave)
        idx = {"B":0,"G":1,"R":2,"Gray":3}.get(canal_vis, 0)
        self.combo_canal_vis.setCurrentIndex(idx)
        self.combo_canal_vis.setToolTip(
            "Canal cuya intensidad real se muestra sobre la imagen\n"
            "al activar el botón 👁 Ver área BI."
        )
        form3.addRow("Canal:", self.combo_canal_vis)
        layout.addWidget(grp3)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def showEvent(self, event):
        """Colores de controles adaptados al tema, con indicador siempre visible."""
        super().showEvent(event)
        from PyQt6.QtGui import QPalette
        pal    = self.palette()
        oscuro = pal.color(QPalette.ColorRole.Window).lightness() < 128
        txt    = "#ffffff" if oscuro else "#111111"
        borde  = "#aaaaaa" if oscuro else "#666666"
        # Marcado: fondo oscuro + check blanco (siempre contrasta)
        marca = "#FF8C00"  # naranja — siempre visible en tema claro y oscuro
        self.setStyleSheet(
            f"QCheckBox{{color:{txt}}}"
            f" QCheckBox::indicator{{width:13px;height:13px;"
            f"border:2px solid {borde};border-radius:2px;background:transparent}}"
            f" QCheckBox::indicator:checked{{border:2px solid {marca};"
            f"background:{marca}}}"
            f" QRadioButton{{color:{txt}}}"
            f" QRadioButton::indicator{{width:13px;height:13px;"
            f"border:2px solid {borde};border-radius:7px;background:transparent}}"
            f" QRadioButton::indicator:checked{{border:2px solid {marca};"
            f"background:{marca}}}"
            f" QLabel{{color:{txt}}} QGroupBox{{color:{txt}}}"
        )

    @property
    def banda(self) -> int:
        return self.spin_banda.value()

    @property
    def porcentaje(self) -> int:
        return self.spin_pct.value()

    @property
    def alineacion(self) -> str:
        for btn in self._btn_grp_alin.buttons():
            if btn.isChecked():
                return btn.property("alin_val")
        return "centro"

    @property
    def canal_vis(self) -> str:
        return self.combo_canal_vis.currentData()

    @property
    def canales(self) -> list[str]:
        c = []
        if self.check_b.isChecked():    c.append("B")
        if self.check_g.isChecked():    c.append("G")
        if self.check_r.isChecked():    c.append("R")
        if self.check_gray.isChecked(): c.append("Gray")
        return c


# =============================================================================
# DIÁLOGO DE GUARDADO DE BI/GI/RI
# =============================================================================

class DialogoGuardarBI(QDialog):
    """
    Diálogo para seleccionar qué métricas de intensidad guardar
    y en qué formato (.rwl por canal×métrica).
    """

    METRICAS = [
        ("mean", "Promedio (mean)"),
        ("min",  "Mínimo (min)"),
        ("max",  "Máximo (max)"),
    ]
    CANALES_DISPONIBLES = [
        ("B",    "Blue Intensity (BI)"),
        ("G",    "Green Intensity (GI)"),
        ("R",    "Red Intensity (RI)"),
        ("Gray", "Gray Intensity (densidad)"),
        ("B_R",  "B/R — ratio azul/rojo (proxy climático, Maxwell 2017)"),
        ("B_G",  "B/G — ratio azul/verde"),
    ]

    def __init__(self, canales_calculados: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guardar intensidad de color (BI/GI/RI)")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Selecciona qué métricas guardar.\nSe generará un archivo .rwl por cada combinación canal × métrica."
        ))

        # Canales
        grp_c = QGroupBox("Canales")
        fc = QVBoxLayout(grp_c)
        self._checks_canal: dict[str, QCheckBox] = {}
        for clave, etiq in self.CANALES_DISPONIBLES:
            chk = QCheckBox(etiq)

            # Ratios disponibles si los dos canales base están calculados
            if clave == "B_R":
                disponible = "B" in canales_calculados and "R" in canales_calculados
                chk.setToolTip("Calculado automáticamente como B_mean / R_mean por anillo.")
            elif clave == "B_G":
                disponible = "B" in canales_calculados and "G" in canales_calculados
                chk.setToolTip("Calculado automáticamente como B_mean / G_mean por anillo.")
            else:
                disponible = clave in canales_calculados
                if not disponible:
                    chk.setToolTip("No calculado — recalcula con este canal activo.")
            chk.setChecked(False)   # ratios desactivados por defecto
            chk.setEnabled(disponible)
            self._checks_canal[clave] = chk
            fc.addWidget(chk)
        layout.addWidget(grp_c)

        # Métricas
        grp_m = QGroupBox("Métricas (no aplica a ratios B/R, B/G)")
        fm = QVBoxLayout(grp_m)
        self._checks_met: dict[str, QCheckBox] = {}
        for clave, etiq in self.METRICAS:
            chk = QCheckBox(etiq)

            chk.setChecked(True)
            self._checks_met[clave] = chk
            fm.addWidget(chk)
        layout.addWidget(grp_m)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def showEvent(self, event):
        super().showEvent(event)
        from PyQt6.QtGui import QPalette
        pal    = self.palette()
        oscuro = pal.color(QPalette.ColorRole.Window).lightness() < 128
        txt    = "#ffffff" if oscuro else "#111111"
        borde  = "#aaaaaa" if oscuro else "#666666"
        marca = "#FF8C00"
        self.setStyleSheet(
            f"QCheckBox{{color:{txt}}}"
            f" QCheckBox::indicator{{width:13px;height:13px;"
            f"border:2px solid {borde};border-radius:2px;background:transparent}}"
            f" QCheckBox::indicator:checked{{border:2px solid {marca};"
            f"background:{marca}}}"
            f" QLabel{{color:{txt}}} QGroupBox{{color:{txt}}}"
        )

    @property
    def seleccion(self) -> list[tuple[str, str]]:
        """Devuelve lista de (canal, metrica) a exportar."""
        result = []
        for canal, chk_c in self._checks_canal.items():
            if not chk_c.isChecked():
                continue
            for met, chk_m in self._checks_met.items():
                if chk_m.isChecked():
                    result.append((canal, met))
        return result
