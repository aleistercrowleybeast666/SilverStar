"""Editable serial baud selector with a measured visible edit field."""

import math

from PySide6.QtCore import QEvent, QRect, QSize
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QComboBox, QSizePolicy, QStyle, QStyleOptionComboBox
from transport.serial_options import SERIAL_BAUD_CANDIDATES, SERIAL_BAUD_MAX


class BaudComboBox(QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self._width_updating = False
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addItems(SERIAL_BAUD_CANDIDATES)
        self.lineEdit().setValidator(QIntValidator(1, SERIAL_BAUD_MAX, self))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.currentTextChanged.connect(self._Width_Update)
        self._Width_Update()

    def _Width_Update(self, *_args) -> None:
        if self._width_updating:
            return
        self._width_updating = True
        try:
            edit = self.lineEdit()
            metrics = edit.fontMetrics()
            texts = ("2000000", self.currentText())
            margins = edit.textMargins()
            # The editable line edit keeps its own text inset and caret gutter.
            padding = max(12, math.ceil(8 * self.devicePixelRatioF()))
            required = max(max(metrics.horizontalAdvance(value),
                               metrics.boundingRect(value).width()) for value in texts)
            required += margins.left() + margins.right() + padding + 4
            option = QStyleOptionComboBox()
            self.initStyleOption(option)
            width = self.style().sizeFromContents(
                QStyle.ContentsType.CT_ComboBox, option,
                QSize(required, metrics.height()), self).width()
            for _ in range(6):
                option.rect = QRect(0, 0, width, max(self.height(), metrics.height() + 8))
                field = self.style().subControlRect(
                    QStyle.ComplexControl.CC_ComboBox, option,
                    QStyle.SubControl.SC_ComboBoxEditField, self)
                deficit = required - field.width()
                if deficit <= 0:
                    break
                width += deficit
            self.setMinimumWidth(width)
            self.updateGeometry()
        finally:
            self._width_updating = False

    def event(self, event) -> bool:
        result = super().event(event)
        if hasattr(self, "_width_updating") and event.type() in (
            QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange, QEvent.Type.Polish, QEvent.Type.Show,
            QEvent.Type.DevicePixelRatioChange,
        ):
            self._Width_Update()
        return result
