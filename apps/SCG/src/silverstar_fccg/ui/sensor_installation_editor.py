"""Explicit measured position entry, independent of sensor orientation and calibration."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from silverstar_fccg.project.sensor_installation import SENSOR_POSITION_LIMIT_M
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox
from silverstar_fccg.ui.widgets import StandardCheckBox


class SensorPositionEditor(QWidget):
    positionChanged = Signal(object)

    def __init__(self, translator, instance_id: str, position: tuple | None, parent=None):
        super().__init__(parent)
        self.setObjectName("sensorPosition_" + instance_id)
        self.recorded = StandardCheckBox(translator.Text_Get("installation.position.recorded"))
        self.recorded.setObjectName("sensorPositionRecorded_" + instance_id)
        self.recorded.setChecked(position is not None)
        self._position = position if position is not None else (0.0, 0.0, 0.0)
        self.setToolTip(translator.Text_Get("installation.position.note"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.recorded)
        self.coordinates = {}
        for index, axis in enumerate(("x", "y", "z")):
            layout.addWidget(QLabel(axis.upper()))
            editor = EnterCommittedDoubleSpinBox()
            editor.setObjectName(f"sensorPosition_{instance_id}_{axis}")
            editor.setRange(-SENSOR_POSITION_LIMIT_M, SENSOR_POSITION_LIMIT_M)
            editor.setDecimals(6)
            editor.setSingleStep(0.001)
            editor.setSuffix(" m")
            editor.CommittedValue_Set(position[index] if position is not None else 0.0)
            editor.setEnabled(position is not None)
            editor.committed.connect(
                lambda value, axis_index=index: self._Coordinate_Commit(axis_index, value))
            layout.addWidget(editor)
            self.coordinates[axis] = editor
        self.recorded.toggled.connect(self._Recorded_Change)

    def _Coordinate_Commit(self, index: int, value: float) -> None:
        # Preserve imported precision on every axis the user did not edit.
        self._position = tuple(value if axis == index else existing
                               for axis, existing in enumerate(self._position))
        self.positionChanged.emit(self._position)

    def _Recorded_Change(self, checked: bool) -> None:
        for editor in self.coordinates.values():
            editor.setEnabled(checked)
        if checked:
            self.positionChanged.emit(self._position)
        else:
            self.positionChanged.emit(None)
