from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal

from silverstar_fccg.ui.widgets import StandardComboBox


class FusionTimingEditor(StandardComboBox):
    """Named values for the two implemented timing modes; no implicit coercion."""

    committed = Signal(int)
    valueChanged = Signal(int)

    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self.addItem("", 0)
        self.addItem("", 1)
        self.setCurrentIndex(1)
        self.Language_Set(language)
        self.currentIndexChanged.connect(self._Value_Change)
        self.activated.connect(self._Value_Commit)

    def _Value_Change(self, _index: int) -> None:
        self.valueChanged.emit(self.value())

    def _Value_Commit(self, _index: int) -> None:
        self.committed.emit(self.value())

    def Language_Set(self, language: str) -> None:
        labels = (("当前状态融合（不回放）", "延迟融合（历史回放）")
                  if language == "zh_CN" else
                  ("Current state (no replay)", "Delayed fusion (history replay)"))
        with QSignalBlocker(self):
            for index, label in enumerate(labels):
                self.setItemText(index, label)

    def setValue(self, value: object) -> None:
        if isinstance(value, bool) or value not in (0, 1):
            raise ValueError("fusion_timing_mode_invalid")
        self.setCurrentIndex(self.findData(int(value)))

    def CommittedValue_Set(self, value: object) -> None:
        with QSignalBlocker(self):
            self.setValue(value)

    def value(self) -> int:
        value = self.currentData()
        if type(value) is not int or value not in (0, 1):
            raise ValueError("fusion_timing_mode_invalid")
        return value

    def setReadOnly(self, readonly: bool) -> None:
        self.setEnabled(not readonly)

    def isReadOnly(self) -> bool:
        return not self.isEnabled()

    def decimals(self) -> int:
        return 0
