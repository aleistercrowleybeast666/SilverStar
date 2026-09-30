"""Local draft editor for bounded preflight alignment."""

from __future__ import annotations

import math
from dataclasses import asdict

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.alignment import (
    ALIGNMENT_MAX_CONSTRAINTS, BODY_AXES, AlignmentConfiguration,
    AlignmentConfiguration_Parse, AlignmentConstraint,
)
from silverstar_fccg.project.model import DeviceInstance


class AlignmentConfigurationEditor(QWidget):
    configurationConfirmed = Signal(str, object)
    draftCancelled = Signal(str)

    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._committed = AlignmentConfiguration()
        self._committed_strategy = ""
        self._draft_strategy = ""
        self._sources: tuple[DeviceInstance, ...] = ()
        self._dirty = False
        self._constraints = list(self._committed.constraints)
        self._rows: list[dict] = []
        self._row_revision = 0
        self._layout = QVBoxLayout(self)
        self._vector_panel = QWidget()
        self._vector_layout = QVBoxLayout(self._vector_panel)
        self._layout.addWidget(self._vector_panel)
        self._external_panel = QWidget()
        self._external_form = QFormLayout(self._external_panel)
        self._layout.addWidget(self._external_panel)
        self._source = QComboBox()
        self._external_form.addRow(translator.Text_Get("alignment.external_source"), self._source)
        self._authority = QCheckBox(translator.Text_Get("alignment.yaw_authoritative"))
        self._external_form.addRow(self._authority)
        self._azimuth = self._Number_Create(90.0)
        self._external_form.addRow(translator.Text_Get("alignment.known_azimuth"), self._azimuth)
        self._source.currentIndexChanged.connect(self._Draft_MarkDirty)
        self._authority.toggled.connect(self._Authority_Change)
        self._azimuth.textEdited.connect(self._Draft_MarkDirty)
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        self._notice = QLabel()
        self._notice.setWordWrap(True)
        action_layout.addWidget(self._notice, 1)
        self.confirm_button = QPushButton(translator.Text_Get("alignment.confirm"))
        self.cancel_button = QPushButton(translator.Text_Get("alignment.cancel"))
        self.confirm_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        action_layout.addWidget(self.confirm_button)
        action_layout.addWidget(self.cancel_button)
        self._layout.addWidget(actions)
        self.confirm_button.clicked.connect(self._Draft_Confirm)
        self.cancel_button.clicked.connect(self._Draft_Cancel)
        self.Configuration_Set(self._committed, "", ())

    @property
    def draft_dirty(self) -> bool:
        return self._dirty

    def DraftStrategy_Get(self) -> str:
        return self._draft_strategy

    def Configuration_Set(
        self, configuration: AlignmentConfiguration, strategy: str | None,
        sources: tuple[DeviceInstance, ...],
    ) -> None:
        selected = strategy or ""
        if self._dirty and (configuration, selected) == (
            self._committed, self._committed_strategy,
        ):
            self._Sources_Set(sources)
            return
        self._committed = configuration
        self._committed_strategy = selected
        self._sources = sources
        self._dirty = False
        self._draft_strategy = selected
        self._constraints = list(configuration.constraints)
        self._Vector_Rebuild()
        self._Sources_Set(sources, configuration.external_source_instance)
        with QSignalBlocker(self._authority):
            self._authority.setChecked(configuration.external_yaw_authoritative)
        self._azimuth.setText(str(configuration.external_known_azimuth_deg
                                  if configuration.external_known_azimuth_deg is not None else 90.0))
        self._Strategy_Display()
        self._notice.clear()

    def DraftStrategy_Set(self, strategy: str) -> None:
        if strategy == self._draft_strategy:
            return
        self._draft_strategy = strategy
        self._dirty = True
        self._Strategy_Display()
        self._notice.setText(self._translator.Text_Get("alignment.pending"))

    def Draft_Commit(self, configuration: AlignmentConfiguration, strategy: str) -> None:
        self._dirty = False
        self.Configuration_Set(configuration, strategy, self._sources)

    def Draft_Discard(self) -> None:
        self._dirty = False
        self.Configuration_Set(self._committed, self._committed_strategy, self._sources)

    def Issue_Show(self, message: str) -> None:
        self._notice.setText(message)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.confirm_button.setText(translator.Text_Get("alignment.confirm"))
        self.cancel_button.setText(translator.Text_Get("alignment.cancel"))
        self._authority.setText(translator.Text_Get("alignment.yaw_authoritative"))
        self._external_form.labelForField(self._source).setText(
            translator.Text_Get("alignment.external_source"))
        self._external_form.labelForField(self._azimuth).setText(
            translator.Text_Get("alignment.known_azimuth"))
        # Language changes are explicit, so preserve valid pending numeric text.
        current = self._Vector_Read()
        if current is not None:
            self._constraints = list(current)
            self._Vector_Rebuild()
        self._Sources_Set(self._sources)

    @staticmethod
    def _Number_Create(value: float) -> QLineEdit:
        editor = QLineEdit(str(value))
        editor.setMaxLength(32)
        return editor

    def _Sources_Set(self, sources: tuple[DeviceInstance, ...], selected: str | None = None) -> None:
        self._sources = sources
        current = selected if selected is not None else str(self._source.currentData() or "")
        with QSignalBlocker(self._source):
            self._source.clear()
            self._source.addItem(self._translator.Text_Get("alignment.source_select"), "")
            for instance in sources:
                if instance.plugin == "silverstar.device.imu.jy901b":
                    self._source.addItem(instance.instance_id, instance.instance_id)
            if current and self._source.findData(current) < 0:
                self._source.addItem(f"{current} — unavailable", current)
            self._source.setCurrentIndex(max(0, self._source.findData(current)))

    def _Strategy_Display(self) -> None:
        self._vector_panel.setVisible(self._draft_strategy.endswith("vector_constraints"))
        self._external_panel.setVisible(self._draft_strategy.endswith("external_attitude_source"))
        self._azimuth.setEnabled(not self._authority.isChecked())

    def _Draft_MarkDirty(self, *_args: object) -> None:
        self._dirty = True
        sender = self.sender()
        if isinstance(sender, QLineEdit):
            if sender is self._azimuth:
                try:
                    self._Number_Read(self._azimuth, 0.0, 359.999)
                except ValueError as problem:
                    self._notice.setText(str(problem))
                    return
            elif self._Vector_Read() is None:
                return
        self._notice.setText(self._translator.Text_Get("alignment.pending"))

    def _Authority_Change(self, _checked: bool) -> None:
        self._azimuth.setEnabled(not self._authority.isChecked())
        self._Draft_MarkDirty()

    def _Vector_Rebuild(self) -> None:
        self._row_revision += 1
        while self._vector_layout.count():
            item = self._vector_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows = []
        for index, constraint in enumerate(self._constraints):
            row = QWidget()
            form = QFormLayout(row)
            kind = QComboBox()
            for value, key in (
                ("gravity", "alignment.gravity"),
                ("magnetic_field", "alignment.magnetic"),
                ("reference_direction", "alignment.reference"),
            ):
                kind.addItem(self._translator.Text_Get(key), value)
            kind.setCurrentIndex(kind.findData(constraint.kind))
            kind.currentIndexChanged.connect(
                lambda _value, position=index: self._RowKind_Change(position))
            form.addRow(self._translator.Text_Get("alignment.constraint_type"), kind)
            weight = self._Number_Create(constraint.weight)
            form.addRow(self._translator.Text_Get("alignment.weight"), weight)
            declination = self._Number_Create(constraint.declination_deg)
            axis = QComboBox()
            for value in BODY_AXES:
                axis.addItem(value, value)
            axis.setCurrentIndex(axis.findData(constraint.body_axis))
            azimuth = self._Number_Create(constraint.nav_azimuth_deg)
            if constraint.kind == "magnetic_field":
                form.addRow(self._translator.Text_Get("alignment.declination"), declination)
            if constraint.kind == "reference_direction":
                form.addRow(self._translator.Text_Get("alignment.body_axis"), axis)
                form.addRow(self._translator.Text_Get("alignment.azimuth"), azimuth)
            error = QLabel()
            error.setWordWrap(True)
            form.addRow(error)
            remove = QPushButton(self._translator.Text_Get("alignment.remove_constraint"))
            remove.setEnabled(len(self._constraints) > 2)
            remove.clicked.connect(lambda _checked=False, position=index: self._Row_Remove(position))
            form.addRow(remove)
            for editor in (weight, declination, azimuth):
                editor.textEdited.connect(self._Draft_MarkDirty)
            axis.currentIndexChanged.connect(self._Draft_MarkDirty)
            self._rows.append({"kind": kind, "weight": weight, "declination": declination,
                               "axis": axis, "azimuth": azimuth, "error": error})
            self._vector_layout.addWidget(row)
        add = QPushButton(self._translator.Text_Get("alignment.add_constraint"))
        add.setEnabled(len(self._constraints) < ALIGNMENT_MAX_CONSTRAINTS)
        add.clicked.connect(self._Row_Add)
        self._vector_layout.addWidget(add)

    @staticmethod
    def _Number_Read(editor: QLineEdit, low: float, high: float) -> float:
        try:
            value = float(editor.text().strip())
        except ValueError as error:
            raise ValueError("finite number required") from error
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"expected {low:g} to {high:g}")
        return value

    def _Vector_Read(self) -> tuple[AlignmentConstraint, ...] | None:
        constraints = []
        for index, row in enumerate(self._rows):
            error = row["error"]
            error.clear()
            try:
                constraints.append(AlignmentConstraint(
                    str(row["kind"].currentData()),
                    self._Number_Read(row["weight"], 0.01, 100.0),
                    self._Number_Read(row["declination"], -180.0, 180.0),
                    str(row["axis"].currentData()),
                    self._Number_Read(row["azimuth"], 0.0, 359.999),
                ))
            except ValueError as problem:
                error.setText(f"Row {index + 1}: {problem}")
                return None
        return tuple(constraints)

    def _Row_Add(self) -> None:
        revision = self._row_revision
        QTimer.singleShot(0, self, lambda: self._Row_AddApply(revision))

    def _Row_AddApply(self, revision: int) -> None:
        if revision != self._row_revision:
            return
        if len(self._rows) >= ALIGNMENT_MAX_CONSTRAINTS:
            return
        current = self._Vector_Read()
        if current is None:
            return
        self._constraints = [*current, AlignmentConstraint("reference_direction")]
        self._Vector_Rebuild()
        self._Draft_MarkDirty()

    def _Row_Remove(self, index: int) -> None:
        revision = self._row_revision
        QTimer.singleShot(0, self, lambda: self._Row_RemoveApply(index, revision))

    def _Row_RemoveApply(self, index: int, revision: int) -> None:
        if revision != self._row_revision:
            return
        if len(self._rows) <= 2 or not 0 <= index < len(self._rows):
            return
        current = self._Vector_Read()
        if current is None:
            return
        self._constraints = [item for position, item in enumerate(current) if position != index]
        self._Vector_Rebuild()
        self._Draft_MarkDirty()

    def _RowKind_Change(self, _index: int) -> None:
        revision = self._row_revision
        QTimer.singleShot(0, self, lambda: self._RowKind_Apply(revision))

    def _RowKind_Apply(self, revision: int) -> None:
        if revision != self._row_revision:
            return
        current = self._Vector_Read()
        if current is None:
            return
        self._constraints = list(current)
        self._Vector_Rebuild()
        self._Draft_MarkDirty()
        kinds = [item.kind for item in self._constraints]
        if kinds.count("gravity") != 1 or kinds.count("magnetic_field") > 1:
            self._notice.setText(self._translator.Text_Get("alignment.invalid_structure"))

    def _Draft_Confirm(self) -> None:
        constraints = self._Vector_Read()
        if constraints is None:
            return
        try:
            known = self._Number_Read(self._azimuth, 0.0, 359.999)
            data = self._committed.Dictionary_Get()
            data.update(constraints=[asdict(item) for item in constraints],
                        external_source_instance=str(self._source.currentData() or ""),
                        external_yaw_authoritative=self._authority.isChecked(),
                        external_known_azimuth_deg=known)
            configuration = AlignmentConfiguration_Parse(data)
            if self._draft_strategy.endswith("external_attitude_source"):
                selected = configuration.external_source_instance
                if not selected or not any(item.instance_id == selected and
                    item.plugin == "silverstar.device.imu.jy901b" for item in self._sources):
                    raise ValueError("Select an available JY901B attitude source")
            if self._draft_strategy.endswith("vector_constraints"):
                references = [(item.body_axis, item.nav_azimuth_deg) for item in constraints
                              if item.kind == "reference_direction"]
                if len(set(references)) != len(references):
                    raise ValueError("Reference directions must be independent")
        except ValueError as problem:
            self._notice.setText(str(problem))
            return
        self.configurationConfirmed.emit(self._draft_strategy, configuration)

    def _Draft_Cancel(self) -> None:
        self._dirty = False
        self.Configuration_Set(self._committed, self._committed_strategy, self._sources)
        self.draftCancelled.emit(self._committed_strategy)

