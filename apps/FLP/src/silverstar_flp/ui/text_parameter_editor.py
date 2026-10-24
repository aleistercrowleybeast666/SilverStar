"""Text parameter adapter for explicit, versioned host-reference configuration."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPlainTextEdit


class TextParameterEditor(QPlainTextEdit):
    valueChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(180)
        self.setPlaceholderText("Explicit configuration JSON is required; no defaults are inferred.")
        self.textChanged.connect(self._ValueChanged_Emit)

    def _ValueChanged_Emit(self):
        self.valueChanged.emit(self.value())

    def value(self):
        return self.toPlainText()

    def setValue(self, value):
        self.setPlainText(str(value))
