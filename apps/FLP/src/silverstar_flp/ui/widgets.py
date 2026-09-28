from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QStyle

from silverstar_flp.ui.touch_scroll import TouchScroll_Enable


class StandardComboBox(QComboBox):
    """Conventional drop-down: open below and scroll only for long lists."""

    MAX_VISIBLE_ITEMS = 10

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        TouchScroll_Enable(self.view())
        self.setMaxVisibleItems(self.MAX_VISIBLE_ITEMS)
        self.setMinimumContentsLength(12)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view().setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)

    def showPopup(self) -> None:
        view = self.view()
        vertical_policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if self.count() > self.MAX_VISIBLE_ITEMS
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        view.setVerticalScrollBarPolicy(vertical_policy)
        super().showPopup()
        if self.count() == 0:
            return

        popup = view.window()
        if not popup.isVisible():
            return
        available = self.screen().availableGeometry()
        combo_top = self.mapToGlobal(QPoint(0, 0))
        combo_bottom = self.mapToGlobal(QPoint(0, self.height()))
        popup_height = popup.height()
        if self.count() > self.MAX_VISIBLE_ITEMS:
            row_height = sum(
                max(view.sizeHintForRow(index), 1) for index in range(self.MAX_VISIBLE_ITEMS)
            )
            scroller_height = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            popup_height = min(popup_height, row_height + scroller_height)
        popup.resize(max(popup.width(), self.width()), popup_height)
        maximum_x = max(available.left(), available.right() - popup.width() + 1)
        popup_x = min(max(combo_bottom.x(), available.left()), maximum_x)
        if combo_bottom.y() + popup.height() - 1 <= available.bottom():
            popup_y = combo_bottom.y()
        else:
            popup_y = max(available.top(), combo_top.y() - popup.height())
        popup.move(popup_x, popup_y)
