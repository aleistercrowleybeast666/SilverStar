from __future__ import annotations

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
