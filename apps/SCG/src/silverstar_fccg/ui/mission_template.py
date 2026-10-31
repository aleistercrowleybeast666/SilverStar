"""Explicit template selection; preview and cancellation never change a project."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLabel, QVBoxLayout)

from silverstar_fccg.project.mission_process import MissionProcess_FirmwareDefault
from silverstar_fccg.ui.widgets import StandardComboBox


class MissionTemplateDialog(QDialog):
    def __init__(self, translator, targets, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._process = None
        text = translator.Text_Get
        self.setWindowTitle(text('workflow.template'))
        self.setMinimumWidth(520)
        self.resize(660, 430)
        self.setSizeGripEnabled(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        hint = QLabel(text('workflow.template_hint'), self)
        hint.setWordWrap(True)
        root.addWidget(hint)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.preset = StandardComboBox(self)
        self.preset.addItem(text('workflow.template.start'), 'start')
        self.preset.addItem(text('workflow.template.acceleration'), 'acceleration')
        form.addRow(text('workflow.template.preset'), self.preset)
        self.launch_threshold = QDoubleSpinBox(self)
        self.burnout_threshold = QDoubleSpinBox(self)
        for control in (self.launch_threshold, self.burnout_threshold):
            control.setDecimals(2)
            control.setRange(0, 100)
            control.setValue(2.0)
            control.setSuffix(' g')
        form.addRow(text('workflow.template.launch'), self.launch_threshold)
        form.addRow(text('workflow.template.burnout'), self.burnout_threshold)
        self.recovery = QCheckBox(text('workflow.template.recovery'), self)
        self.recovery.setChecked(False)
        self.recovery.setEnabled(bool(targets))
        form.addRow(self.recovery)
        self.target = StandardComboBox(self)
        for identity in targets:
            self.target.addItem(identity, identity)
        form.addRow(text('process.target'), self.target)
        if not targets:
            note = QLabel(text('workflow.template.no_recovery_output'), self)
            note.setWordWrap(True)
            form.addRow(note)
        root.addLayout(form)
        self.preview = QLabel(self)
        self.preview.setObjectName('noticeLabel')
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.preview)
        self.error = QLabel(self)
        self.error.setObjectName('workflowError')
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText(text('workflow.template.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Apply).setObjectName('primaryButton')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.preset.currentIndexChanged.connect(self._Preview_Refresh)
        self.recovery.toggled.connect(self._Preview_Refresh)
        self.target.currentIndexChanged.connect(self._Preview_Refresh)
        self.launch_threshold.valueChanged.connect(self._Preview_Refresh)
        self.burnout_threshold.valueChanged.connect(self._Preview_Refresh)
        self._Preview_Refresh()

    def _Candidate_Get(self):
        process = MissionProcess_FirmwareDefault(
            acceleration_detection=self.preset.currentData() == 'acceleration',
            recovery=self.recovery.isChecked(), recovery_target=self.target.currentData() or '')
        for stage in process['stages']:
            if stage['condition']['signal'] == 'acceleration_g':
                stage['condition']['value'] = (self.launch_threshold.value() if stage['stage_id'] == 'ascent'
                                              else self.burnout_threshold.value())
        return process

    def _Preview_Refresh(self, *_args):
        detection = self.preset.currentData() == 'acceleration'
        self.launch_threshold.setEnabled(detection)
        self.burnout_threshold.setEnabled(detection)
        self.target.setEnabled(self.recovery.isChecked())
        process = self._Candidate_Get()
        text = self._translator.Text_Get
        names = [text('workflow.stage.' + row['stage_id']) for row in process['stages']]
        self.preview.setText(' → '.join(names) + '\n\n' + text(
            'workflow.template.recovery_note' if self.recovery.isChecked() else 'workflow.template.recording_note') +
            ('\n\n' + text('workflow.template.acceleration_note') if detection else ''))

    def accept(self):
        if self.recovery.isChecked() and not self.target.currentData():
            self.error.setText(self._translator.Text_Get('workflow.template.no_recovery_output'))
            return
        self._process = self._Candidate_Get()
        super().accept()

    def Process_Get(self):
        return deepcopy(self._process)
