"""Fit initial native frames once; never resize an editor during refresh."""
from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QDialog, QWidget


def Window_ConstrainInitialGeometry(window: QWidget, available: QRect | None = None) -> None:
    if window.isMaximized() or window.isFullScreen():
        return
    if available is None:
        screen = window.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
    frame = window.frameGeometry()
    if not available.isValid() or available.contains(frame):
        return
    border_width = max(0, frame.width() - window.width())
    border_height = max(0, frame.height() - window.height())
    width = max(1, available.width() - border_width)
    height = max(1, available.height() - border_height)
    window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
    window.resize(min(window.width(), width), min(window.height(), height))
    frame = window.frameGeometry()
    window.move(
        max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
        max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)),
    )


class PropertyDialog(QDialog):
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_initial_geometry_constrained', False):
            self._initial_geometry_constrained = True
            QTimer.singleShot(0, lambda: Window_ConstrainInitialGeometry(self))
