from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QToolTip


class _EnterCommitMixin:
    """Keep spinbox edits local until Return; discard uncommitted drafts on blur."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False)
        self._committed_value = self.value()

    def CommittedValue_Set(self, value: float) -> None:
        with QSignalBlocker(self):
            self.setValue(value)
        self._committed_value = self.value()

    def CommittedValue_Get(self) -> int | float:
        return self._committed_value

    def _Draft_Restore(self) -> None:
        with QSignalBlocker(self):
            self.setValue(self._committed_value)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.lineEdit().hasAcceptableInput():
                self._Draft_Restore()
                if self.toolTip():
                    QToolTip.showText(
                        self.mapToGlobal(QPoint(0, self.height())),
                        self.toolTip(),
                        self,
                    )
                event.accept()
                return
            self.interpretText()
            value = self.value()
            if value != self._committed_value:
                self._committed_value = value
                self.committed.emit(value)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._Draft_Restore()
        super().focusOutEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class EnterCommittedSpinBox(_EnterCommitMixin, QSpinBox):
    committed = Signal(int)


class EnterCommittedDoubleSpinBox(_EnterCommitMixin, QDoubleSpinBox):
    committed = Signal(float)
