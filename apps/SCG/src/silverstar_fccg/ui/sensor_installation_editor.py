"""Explicit measured position entry, independent of sensor orientation and calibration."""

from html import escape
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QWidget

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
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        heading = QHBoxLayout()
        heading.addWidget(self.recorded)
        self.vector_label = QLabel('<b>r</b><sup>b</sup><sub>' + escape(instance_id) + '</sub> (m)')
        self.vector_label.setTextFormat(Qt.TextFormat.RichText)
        self.vector_label.setToolTip(translator.Text_Get('installation.position.note'))
        heading.addWidget(self.vector_label)
        heading.addStretch(1)
        root.addLayout(heading)
        layout = QHBoxLayout()
        root.addLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.coordinates = {}
        self.axis_labels = {}
        for index, axis in enumerate(("x", "y", "z")):
            pair = QWidget()
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(6)
            label = QLabel(axis)
            pair_layout.addWidget(label)
            self.axis_labels[axis] = label
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
            editor.setMinimumWidth(112)
            editor.setMaximumWidth(172)
            label.setBuddy(editor)
            pair_layout.addWidget(editor)
            layout.addWidget(pair)
            self.coordinates[axis] = editor
        layout.addStretch(1)
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
