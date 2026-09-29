"""Editor for the bounded preflight alignment configuration."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.alignment import (
    ALIGNMENT_MAX_CONSTRAINTS,
    BODY_AXES,
    AlignmentConfiguration,
    AlignmentConstraint,
)
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox


class AlignmentConfigurationEditor(QWidget):
    configurationChanged = Signal(object)

    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._configuration = AlignmentConfiguration()
        self._strategy = ""
        self._sources: tuple[DeviceInstance, ...] = ()
        self._layout = QVBoxLayout(self)

    def Configuration_Set(
        self, configuration: AlignmentConfiguration,
        strategy: str | None,
        sources: tuple[DeviceInstance, ...],
    ) -> None:
        self._configuration = configuration
        self._strategy = strategy or ""
        self._sources = sources
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if self._strategy.endswith("vector_constraints"):
            self._Vector_Build()
        elif self._strategy.endswith("external_attitude_source"):
            self._External_Build()

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.Configuration_Set(
            self._configuration, self._strategy, self._sources,
        )

    def _Number_Create(
        self, value: float, minimum: float, maximum: float,
        callback,
    ) -> EnterCommittedDoubleSpinBox:
        editor = EnterCommittedDoubleSpinBox()
        editor.setDecimals(3)
        editor.setRange(minimum, maximum)
        editor.CommittedValue_Set(value)
        editor.committed.connect(callback)
        return editor

    def _Constraints_Commit(self, constraints: tuple[AlignmentConstraint, ...]) -> None:
        self.configurationChanged.emit(
            replace(self._configuration, constraints=constraints)
        )

    def _Constraint_Replace(self, index: int, **fields) -> None:
        constraints = list(self._configuration.constraints)
        constraints[index] = replace(constraints[index], **fields)
        self._Constraints_Commit(tuple(constraints))

    def _Magnetic_Toggle(self, enabled: bool) -> None:
        constraints = [
            item for item in self._configuration.constraints
            if item.kind != "magnetic_field"
        ]
        if enabled:
            constraints.insert(1, AlignmentConstraint("magnetic_field"))
        elif len(constraints) == 1:
            constraints.append(AlignmentConstraint("reference_direction"))
        self._Constraints_Commit(tuple(constraints))

    def _Reference_Add(self) -> None:
        if len(self._configuration.constraints) < ALIGNMENT_MAX_CONSTRAINTS:
            self._Constraints_Commit((*self._configuration.constraints,
                AlignmentConstraint("reference_direction")))

    def _Reference_Remove(self, index: int) -> None:
        constraints = list(self._configuration.constraints)
        if len(constraints) <= 2:
            return
        del constraints[index]
        self._Constraints_Commit(tuple(constraints))

    def _Vector_Build(self) -> None:
        for index, constraint in enumerate(self._configuration.constraints):
            row = QWidget()
            form = QFormLayout(row)
            form.addRow(self._translator.Text_Get("alignment.weight"),
                self._Number_Create(constraint.weight, 0.01, 100.0,
                    lambda value, position=index: self._Constraint_Replace(
                        position, weight=float(value))))
            if constraint.kind == "gravity":
                title = self._translator.Text_Get("alignment.gravity")
            elif constraint.kind == "magnetic_field":
                title = self._translator.Text_Get("alignment.magnetic")
                form.addRow(self._translator.Text_Get("alignment.declination"),
                    self._Number_Create(constraint.declination_deg,
                        -180.0, 180.0,
                        lambda value, position=index: self._Constraint_Replace(
                            position, declination_deg=float(value))))
            else:
                title = self._translator.Text_Get("alignment.reference")
                axis = QComboBox()
                for option in BODY_AXES:
                    axis.addItem(option, option)
                axis.setCurrentIndex(axis.findData(constraint.body_axis))
                axis.currentIndexChanged.connect(
                    lambda _index, position=index, editor=axis:
                        self._Constraint_Replace(
                            position, body_axis=str(editor.currentData())))
                form.addRow(self._translator.Text_Get("alignment.body_axis"), axis)
                form.addRow(self._translator.Text_Get("alignment.azimuth"),
                    self._Number_Create(constraint.nav_azimuth_deg,
                        0.0, 359.999,
                        lambda value, position=index: self._Constraint_Replace(
                            position, nav_azimuth_deg=float(value))))
                remove = QPushButton(self._translator.Text_Get("alignment.remove_reference"))
                remove.setEnabled(len(self._configuration.constraints) > 2)
                remove.clicked.connect(
                    lambda _checked=False, position=index:
                        self._Reference_Remove(position))
                form.addRow(remove)
            caption = QLabel(title)
            caption.setProperty("secondaryText", True)
            self._layout.addWidget(caption)
            self._layout.addWidget(row)
        controls = QWidget()
        control_layout = QHBoxLayout(controls)
        magnetic = QCheckBox(self._translator.Text_Get("alignment.use_magnetic"))
        magnetic.setChecked(any(
            item.kind == "magnetic_field"
            for item in self._configuration.constraints
        ))
        magnetic.setEnabled(magnetic.isChecked() or
            len(self._configuration.constraints) < ALIGNMENT_MAX_CONSTRAINTS)
        magnetic.toggled.connect(self._Magnetic_Toggle)
        control_layout.addWidget(magnetic)
        add = QPushButton(self._translator.Text_Get("alignment.add_reference"))
        add.setEnabled(len(self._configuration.constraints) < ALIGNMENT_MAX_CONSTRAINTS)
        add.clicked.connect(self._Reference_Add)
        control_layout.addWidget(add)
        self._layout.addWidget(controls)

    def _External_Build(self) -> None:
        form = QFormLayout()
        source = QComboBox()
        source.addItem(self._translator.Text_Get("alignment.source_select"), "")
        for instance in self._sources:
            if instance.plugin == "silverstar.device.imu.jy901b":
                source.addItem(instance.instance_id, instance.instance_id)
        source.setCurrentIndex(max(0, source.findData(
            self._configuration.external_source_instance)))
        source.currentIndexChanged.connect(
            lambda _index: self.configurationChanged.emit(replace(
                self._configuration,
                external_source_instance=str(source.currentData()))))
        form.addRow(self._translator.Text_Get("alignment.external_source"), source)
        authoritative = QCheckBox(self._translator.Text_Get("alignment.yaw_authoritative"))
        authoritative.setChecked(self._configuration.external_yaw_authoritative)
        known_azimuth = self._configuration.external_known_azimuth_deg
        if known_azimuth is None:
            known_azimuth = 90.0
        authoritative.toggled.connect(lambda checked: self.configurationChanged.emit(
            replace(self._configuration,
                external_yaw_authoritative=checked,
                external_known_azimuth_deg=known_azimuth)))
        form.addRow(authoritative)
        if not self._configuration.external_yaw_authoritative:
            form.addRow(self._translator.Text_Get("alignment.known_azimuth"),
                self._Number_Create(
                    known_azimuth,
                    0.0, 359.999,
                    lambda value: self.configurationChanged.emit(replace(
                        self._configuration,
                        external_known_azimuth_deg=float(value)))))
        panel = QWidget()
        panel.setLayout(form)
        self._layout.addWidget(panel)
