"""Operaciones extraídas sin modificar sus algoritmos."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox, QDialogButtonBox

class DialogoCalibracionRegla(QDialog):
    """Diálogo para preguntar la distancia antes de trazar la regla."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar Escala (Regla)")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Ingresa la distancia física que vas a trazar en la imagen:"))

        fila = QHBoxLayout()
        self.spin_val = QDoubleSpinBox()
        self.spin_val.setRange(0.01, 10000.0)
        self.spin_val.setValue(1.0)
        self.spin_val.setDecimals(2)
        self.spin_val.setSingleStep(0.1)
        fila.addWidget(self.spin_val)

        self.combo_unidad = QComboBox()
        self.combo_unidad.addItems(["cm", "mm"])
        fila.addWidget(self.combo_unidad)

        layout.addLayout(fila)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def obtener_mm(self) -> float:
        val = self.spin_val.value()
        if self.combo_unidad.currentText() == "cm":
            return val * 10.0  # Convertir a mm
        return val
