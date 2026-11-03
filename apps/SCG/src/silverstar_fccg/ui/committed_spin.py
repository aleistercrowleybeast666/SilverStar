from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QToolTip


class _EnterCommitMixin:
    """Keep typed values in their owning property transaction until Apply."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False)
        self._committed_value = self.value()
        self._pending_text = None
        self.lineEdit().textEdited.connect(self._Edited)

    def _Edited(self, text):
        if self.window().property('collectNumericDrafts'):
            self._pending_text = text

    def CommittedValue_Set(self, value: float) -> None:
        pending = self._pending_text if value == self._committed_value else None
        with QSignalBlocker(self):
            self.setValue(value)
        self._committed_value = self.value()
        self._pending_text = pending
        if pending is not None:
            self.lineEdit().setText(pending)

    def CommittedValue_Get(self) -> int | float:
        return self._committed_value

    def _Draft_Restore(self) -> None:
        with QSignalBlocker(self):
            self.setValue(self._committed_value)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.lineEdit().hasAcceptableInput():
                self.rejected.emit(self.lineEdit().text())
                if not self.window().property('collectNumericDrafts'):
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
            self._pending_text = None
            value = self.value()
            if value != self._committed_value:
                self._committed_value = value
                self.committed.emit(value)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        if self.window().property('collectNumericDrafts'):
            if self._pending_text is not None:
                text = self.lineEdit().text()
                with QSignalBlocker(self):
                    super().focusOutEvent(event)
                self.lineEdit().setText(text)
                self._pending_text = text
            else:
                super().focusOutEvent(event)
            return
        self._Draft_Restore()
        super().focusOutEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class EnterCommittedSpinBox(_EnterCommitMixin, QSpinBox):
    committed = Signal(int)
    rejected = Signal(str)


class EnterCommittedDoubleSpinBox(_EnterCommitMixin, QDoubleSpinBox):
    committed = Signal(float)
    rejected = Signal(str)


def NumericDrafts_Collect(dialog, error_label, message):
    """Validate all pending fields before notifying any private draft owner."""
    editors = [*dialog.findChildren(EnterCommittedSpinBox), *dialog.findChildren(EnterCommittedDoubleSpinBox)]
    values = []
    for editor in editors:
        if editor._pending_text is None and editor.value() == editor.CommittedValue_Get():
            continue
        if not editor.lineEdit().hasAcceptableInput():
            error_label.setText(message)
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
            editor.selectAll()
            return False
        values.append((editor, editor.valueFromText(editor.lineEdit().text())))
    for editor, value in values:
        previous = editor.CommittedValue_Get()
        editor._pending_text = None
        editor.CommittedValue_Set(value)
        if value != previous:
            editor.committed.emit(value)
    return True
