from __future__ import annotations

import math
import struct
from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from silverstar_fccg.core.nis_probability import ChiSquareCdf_Get, NisInput_Resolve
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox

class NisProbabilityEditor(QWidget):
    """Percent draft plus immutable numeric baseline; no load-time round trip."""
    committed = Signal(object)
    valueChanged = Signal(object)

    def __init__(self, df: int, minimum: float, maximum: float, language: str, parent=None):
        super().__init__(parent)
        self.df, self.minimum, self.maximum = df, minimum, maximum
        self._zh = language == "zh_CN"
        self._input = None
        self._numeric_display = False
        self._error = ""
        self.percent = EnterCommittedDoubleSpinBox(self)
        self.percent.setDecimals(12)
        self.percent.setRange(0.0, 100.0)
        self.percent.setSingleStep(0.01)
        self.percent.setSuffix(" %")
        self.percent.setKeyboardTracking(False)
        self.readout = QLabel(self)
        self.readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.percent)
        row.addWidget(self.readout)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        self.notice = QLabel(self)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.percent.committed.connect(self._Probability_Change)
        self.setToolTip("CDF 覆盖概率越高，门限越宽松；不是量测正确率。" if self._zh else
                        "Higher CDF coverage makes the gate more permissive; not measurement correctness.")

    def _Probability_Change(self, percent: float) -> None:
        self._input = {"schema_id": "silverstar.nis-cdf-input/1.0", "unit": "fraction",
                       "degrees_of_freedom": self.df, "probability": percent / 100.0}
        try:
            actual = self.value()
            self._error = ""
            actual = struct.unpack("<f", struct.pack("<f", actual))[0]
            self.readout.setText(f"NIS = {actual:.9g} · df = {self.df}")
        except ValueError:
            self.readout.setText(f"NIS = ? · df = {self.df}")
            self._error = "输入须满足 0 < p < 100%，且数值在原门限范围内" if self._zh else "Require 0 < p < 100% and the existing numeric threshold range"
        self._Notice_Refresh()
        self.valueChanged.emit(self._input)
        self.committed.emit(deepcopy(self._input))

    def _Notice_Refresh(self) -> None:
        if self._error:
            text = self._error
        elif self._numeric_display:
            text = "历史记录未声明自由度；仅显示实际数值" if self._zh else "Recorded df unavailable; numeric threshold only"
        elif self.df == 3:
            text = "3D 保留配置；当前 GNSS 更新采用 2+1 分组" if self._zh else "Reserved 3D configuration; current GNSS uses 2+1 groups"
        else:
            text = "CDF 概率越高，门限越宽松；不是量测正确率" if self._zh else "Higher CDF coverage is more permissive; not measurement correctness"
        self.notice.setText(text)

    def setValue(self, value: object) -> None:
        actual = NisInput_Resolve(value, self.df)
        self._input, self._error = deepcopy(value), ""
        self.percent.blockSignals(True)
        p = value["probability"] if isinstance(value, dict) else ChiSquareCdf_Get(
            struct.unpack("<f", struct.pack("<f", actual))[0], self.df)
        self.percent.CommittedValue_Set(p * 100.0)
        self.percent.blockSignals(False)
        actual = struct.unpack("<f", struct.pack("<f", self.value()))[0]
        self.readout.setText(f"NIS = {actual:.9g} · df = {self.df}")
        self._Notice_Refresh()

    CommittedValue_Set = setValue

    def value(self) -> float:
        actual = NisInput_Resolve(self._input, self.df)
        if isinstance(self._input, dict):
            actual = struct.unpack("<f", struct.pack("<f", actual))[0]
        if not math.isfinite(actual) or not self.minimum <= actual <= self.maximum:
            raise ValueError("nis_numeric_threshold_out_of_range")
        return actual

    def Input_Get(self) -> object:
        self.value()
        return deepcopy(self._input)

    def InputValid_Is(self) -> bool:
        try:
            self.value()
            return True
        except ValueError:
            return False

    def Language_Set(self, language: str) -> None:
        self._zh = language == "zh_CN"
        self._Notice_Refresh()

    def NumericDisplay_Set(self, numeric_only: bool) -> None:
        self._numeric_display = numeric_only
        self.percent.setVisible(not numeric_only)
        if self.InputValid_Is():
            actual = struct.unpack("<f", struct.pack("<f", self.value()))[0]
            self.readout.setText(f"NIS = {actual:.9g}" + (" · df = ?" if numeric_only else f" · df = {self.df}"))
        else:
            self.readout.setText("NIS = ?" + (" · df = ?" if numeric_only else f" · df = {self.df}"))
        self._Notice_Refresh()

    def setReadOnly(self, readonly: bool) -> None:
        self.percent.setReadOnly(readonly)

    def isReadOnly(self) -> bool:
        return self.percent.isReadOnly()

    def lineEdit(self):
        return self.percent.lineEdit()


class GateEnableEditor(QCheckBox):
    committed = Signal(int)
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toggled.connect(self._Change)

    def _Change(self, checked: bool) -> None:
        self.valueChanged.emit(int(checked))
        self.committed.emit(int(checked))

    def setValue(self, value) -> None:
        if value not in (0, 1):
            raise ValueError("nis_enable_invalid")
        self.setChecked(bool(value))

    def CommittedValue_Set(self, value) -> None:
        self.blockSignals(True)
        self.setValue(value)
        self.blockSignals(False)

    def value(self) -> int:
        return int(self.isChecked())

    def setReadOnly(self, readonly: bool) -> None:
        self.setEnabled(not readonly)

    def isReadOnly(self) -> bool:
        return not self.isEnabled()

    def decimals(self) -> int:
        return 0
