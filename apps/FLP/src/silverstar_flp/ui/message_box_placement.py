"""Place message boxes without intercepting normal application traffic."""
from weakref import ref

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget


def FramePosition_Get(frame: QRect, parent: QRect, available: QRect) -> QPoint:
    """Use logical screen coordinates, including monitors with negative origins."""
    x = parent.center().x() - frame.width() // 2
    y = parent.center().y() - frame.height() // 2
    return QPoint(
        max(available.left(), min(x, available.right() - frame.width() + 1)),
        max(available.top(), min(y, available.bottom() - frame.height() + 1)),
    )


def MessageBox_Center(dialog: QMessageBox) -> None:
    parent = dialog.parentWidget()
    if parent is None or not dialog.isVisible():
        return
    parent = parent.window()
    screen = parent.screen()
    if screen is None or not screen.availableGeometry().isValid():
        return
    dialog.move(FramePosition_Get(
        dialog.frameGeometry(), parent.frameGeometry(), screen.availableGeometry(),
    ))


class MessageBoxPlacement(QObject):
    """Dialog-local observer, or temporary observer during a Qt modal call."""

    def __init__(self, owner: QWidget, parent: QObject) -> None:
        super().__init__(parent)
        self._owner = ref(owner)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            owner = self._owner()
            if owner is None:
                return False
            current = watched
            while current is not None and current is not owner:
                current = current.parentWidget()
            if current is owner:
                MessageBox_Center(watched)
                # Show-time layout/native frame margins can settle on the next
                # event turn. The receiver context cancels this if it is deleted.
                QTimer.singleShot(0, watched, lambda: MessageBox_Center(watched))
        return False


def MessageBox_Watch(dialog: QMessageBox) -> MessageBoxPlacement:
    """Watch a nonblocking/reused notice without an application event filter."""
    placement = getattr(dialog, "_silverstar_message_box_placement", None)
    if placement is None:
        placement = MessageBoxPlacement(dialog, dialog)
        dialog._silverstar_message_box_placement = placement
        dialog.installEventFilter(placement)
    return placement


def MessageBox_Show(operation, parent: QWidget, *args, **kwargs):
    """Preserve the actual Qt operation, defaults, return value and errors."""
    application = QApplication.instance()
    if application is None or parent is None:
        return operation(parent, *args, **kwargs)
    placement = MessageBoxPlacement(parent, application)
    application.installEventFilter(placement)
    try:
        return operation(parent, *args, **kwargs)
    finally:
        application.removeEventFilter(placement)
        placement.deleteLater()

