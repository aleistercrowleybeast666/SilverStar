from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPlainTextEdit,
    QScrollArea,
    QScroller,
    QTextEdit,
    QWidget,
)


def TouchScroll_Enable(widget: QWidget) -> None:
    """Register only ordinary content viewports; leave mouse and graphics gestures alone."""
    if isinstance(widget, QHeaderView) or not isinstance(
        widget, (QScrollArea, QAbstractItemView, QPlainTextEdit, QTextEdit)
    ):
        return
    QScroller.grabGesture(widget.viewport(), QScroller.ScrollerGestureType.TouchGesture)


class _ContentSizedScrollArea(QScrollArea):
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        content = self.widget()
        if content is not None:
            height = content.heightForWidth(self.viewport().width())
            if height < 0:
                height = content.sizeHint().height()
            height = max(height, content.minimumSizeHint().height())
            hint.setHeight(height + 2 * self.frameWidth())
        return hint


def TouchScroll_Wrap(content: QWidget, *, fit_content: bool = False) -> QScrollArea:
    """Make a form scrollable without changing the widgets inside it."""
    scroll = _ContentSizedScrollArea() if fit_content else QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    TouchScroll_Enable(scroll)
    return scroll
