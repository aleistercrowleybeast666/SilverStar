"""Mission phase capsules; values are declarative desktop-reference data."""
from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QToolButton, QVBoxLayout, QWidget)

from silverstar_fccg.project.mission_process import (
    ACTIONS, EVENTS, SIGNALS, MissionProcess_Default, MissionProcess_Require)
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox


class MissionStageDialog(QDialog):
    def __init__(self, translator, process, index, targets, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._process = deepcopy(process)
        self._index = index
        self._result = None
        self._numeric_edited = False
        stage = process['stages'][index]
        text = translator.Text_Get
        self.setWindowTitle(text('process.detail'))
        self.resize(600, 420)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(stage['name'])
        self.name_edit.setMaxLength(128)
        identity = QLabel(stage['stage_id'])
        identity.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(text('process.identity'), identity)
        form.addRow(text('process.name'), self.name_edit)
        self.signal_combo = QComboBox()
        for signal in SIGNALS:
            self.signal_combo.addItem(text('process.signal.' + signal), signal)
        self.signal_combo.setCurrentIndex(self.signal_combo.findData(stage['condition']['signal']))
        form.addRow(text('process.condition'), self.signal_combo)
        self.operator = QComboBox()
        self.operator.addItems(('>=', '<='))
        self.operator.setCurrentText(stage['condition']['operator'])
        form.addRow(text('process.operator'), self.operator)
        self.number = QDoubleSpinBox()
        self.number.setDecimals(6)
        self.number.setRange(-1e7, 1e7)
        self.number.setValue(stage['condition']['value'] if stage['condition']['signal'] != 'event' else 0)
        self.number.valueChanged.connect(lambda _value: setattr(self, '_numeric_edited', True))
        form.addRow(text('process.threshold'), self.number)
        self.event_combo = QComboBox()
        for event in EVENTS:
            self.event_combo.addItem(text('process.event.' + event), event)
        self.event_combo.setCurrentIndex(max(0, self.event_combo.findData(stage['condition']['value'])))
        form.addRow(text('process.event'), self.event_combo)
        self.hold = QSpinBox()
        self.hold.setRange(0, 3600000)
        self.hold.setSuffix(' ms')
        self.hold.setValue(stage['hold_ms'])
        form.addRow(text('process.hold'), self.hold)
        self.action = QComboBox()
        for action in ACTIONS:
            self.action.addItem(text('process.action.' + action), action)
        self.action.setCurrentIndex(self.action.findData(stage['action']['kind']))
        form.addRow(text('process.action'), self.action)
        self.target = QComboBox()
        self.target.addItem('—', '')
        for target in targets:
            self.target.addItem(target, target)
        original = stage['action']['target']
        if original and self.target.findData(original) < 0:
            self.target.addItem(text('process.target_missing', target=original), original)
        self.target.setCurrentIndex(max(0, self.target.findData(original)))
        self._targets = set(targets)
        form.addRow(text('process.target'), self.target)
        root.addLayout(form)
        note = QLabel(text('process.reference_note'))
        note.setWordWrap(True)
        root.addWidget(note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.signal_combo.currentIndexChanged.connect(self._Fields_Refresh)
        self.action.currentIndexChanged.connect(self._Fields_Refresh)
        self._Fields_Refresh()

    def _Fields_Refresh(self):
        signal = self.signal_combo.currentData()
        event = signal == 'event'
        self.event_combo.setEnabled(event)
        self.number.setEnabled(not event)
        self.operator.setEnabled(not event and signal != 'stage_elapsed_s')
        self.hold.setEnabled(not event)
        self.number.setSuffix(' ' + SIGNALS[signal] if not event else '')
        self.target.setEnabled(self.action.currentData() == 'request_recovery')

    def accept(self):
        if (self.number.isEnabled() and not self.number.lineEdit().hasAcceptableInput()) or (self.hold.isEnabled() and not self.hold.lineEdit().hasAcceptableInput()):
            self.error.setText(self._translator.Text_Get('capsule.invalid'))
            return
        original = self._process['stages'][self._index]
        stage = deepcopy(original)
        signal = self.signal_combo.currentData()
        same_signal = original['condition']['signal'] == signal
        self.number.interpretText(); self.hold.interpretText()
        number = original['condition']['value'] if same_signal and not self._numeric_edited else self.number.value()
        stage.update(name=self.name_edit.text().strip(), condition={
            'signal': signal, 'operator': 'is' if signal == 'event' else '>=' if signal == 'stage_elapsed_s' else self.operator.currentText(),
            'value': self.event_combo.currentData() if signal == 'event' else number,
            'unit': SIGNALS[signal]}, hold_ms=0 if signal == 'event' else self.hold.value(),
            action={'kind': self.action.currentData(), 'target': self.target.currentData() if self.action.currentData() == 'request_recovery' else ''})
        candidate = deepcopy(self._process)
        candidate['stages'][self._index] = stage
        try:
            self._result = MissionProcess_Require(candidate, self._targets)
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        super().accept()

    def Process_Get(self):
        return deepcopy(self._result)


class MissionProcessPanel(QGroupBox):
    processChanged = Signal(object)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._process = None
        self._targets = ()
        self.cards = {}
        self.value_editors = {}
        self.root = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.root.addWidget(self.note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.root.addWidget(self.error)
        toolbar = QHBoxLayout()
        self.create_button = QPushButton()
        self.create_button.clicked.connect(self.Template_Create)
        toolbar.addWidget(self.create_button)
        self.insert_before = QComboBox()
        toolbar.addWidget(self.insert_before, 1)
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self.Stage_Add)
        toolbar.addWidget(self.add_button)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(lambda: self._Process_Emit(None))
        toolbar.addWidget(self.clear_button)
        self.root.addLayout(toolbar)
        self.start_policy = QComboBox()
        self.start_policy.currentIndexChanged.connect(self.StartPolicy_Change)
        self.root.addWidget(self.start_policy)
        self.container = QWidget()
        self.stages_layout = QVBoxLayout(self.container)
        self.stages_layout.setContentsMargins(0, 0, 0, 0)
        self.root.addWidget(self.container)
        self.Language_Apply(translator)

    def Language_Apply(self, translator):
        self._translator = translator
        self.setTitle(translator.Text_Get('process.title'))
        self.note.setText(translator.Text_Get('process.reference_note'))
        self.create_button.setText(translator.Text_Get('process.create'))
        self.add_button.setText(translator.Text_Get('process.add'))
        self.clear_button.setText(translator.Text_Get('process.legacy'))
        with QSignalBlocker(self.start_policy):
            self.start_policy.clear()
            self.start_policy.addItem(translator.Text_Get('process.start.separate'), 'separate')
            self.start_policy.addItem(translator.Text_Get('process.start.combined'), 'start_is_launch')
        self.Configuration_Set(self._process, self._targets)

    def Configuration_Set(self, process, targets=()):
        self._process = deepcopy(process)
        self._targets = tuple(targets)
        while self.stages_layout.count():
            widget = self.stages_layout.takeAt(0).widget()
            widget.hide(); widget.deleteLater()
        self.cards.clear()
        self.value_editors.clear()
        self.insert_before.clear()
        self.create_button.setVisible(process is None)
        for widget in (self.add_button, self.insert_before, self.clear_button):
            widget.setVisible(process is not None)
        self.start_policy.setVisible(process is not None)
        if process is None:
            return
        with QSignalBlocker(self.start_policy):
            self.start_policy.setCurrentIndex(self.start_policy.findData(process['start_policy']))
        self.add_button.setEnabled(len(process['stages']) < 32)
        for index, stage in enumerate(process['stages']):
            self.insert_before.addItem(self._translator.Text_Get('process.before', name=stage['name']), stage['stage_id'])
            card = QFrame()
            card.setObjectName('missionPhaseCapsule')
            card.setStyleSheet('QFrame#missionPhaseCapsule { border: 1px solid palette(mid); border-radius: 18px; background: palette(base); }')
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 10, 14, 10)
            row.addWidget(QLabel(str(index + 1)))
            name = QLineEdit(stage['name'])
            name.setMaxLength(128)
            name.setMaximumWidth(180)
            name.returnPressed.connect(lambda selected=stage['stage_id'], editor=name: self.Stage_Rename(selected, editor.text()))
            row.addWidget(name)
            condition = stage['condition']
            value = self._translator.Text_Get('process.event.' + condition['value']) if condition['signal'] == 'event' else str(condition['value']) + ' ' + condition['unit']
            description = QLabel(self._translator.Text_Get('process.signal.' + condition['signal']) +
                ' ' + ('=' if condition['signal'] == 'event' else condition['operator']) +
                (' ' + value if condition['signal'] == 'event' else ''))
            description.setWordWrap(True)
            description.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(description, 1 if condition['signal'] == 'event' else 0)
            if condition['signal'] != 'event':
                editor = EnterCommittedDoubleSpinBox()
                editor.setDecimals(6)
                editor.setRange(0 if condition['signal'] == 'stage_elapsed_s' else -1e7, 1e7)
                editor.setSuffix(' ' + condition['unit'])
                editor.setMaximumWidth(140)
                editor.CommittedValue_Set(condition['value'])
                editor.committed.connect(lambda new_value, identity=stage['stage_id']: self.Stage_ValueSet(identity, new_value))
                row.addWidget(editor)
                self.value_editors[stage['stage_id']] = editor
                row.addStretch(1)
            for label, enabled, callback in (
                ('↑', index > 0, lambda _checked=False, selected=stage['stage_id']: self.Stage_Move(selected, -1)),
                ('↓', index + 1 < len(process['stages']), lambda _checked=False, selected=stage['stage_id']: self.Stage_Move(selected, 1)),
                ('…', True, lambda _checked=False, selected=stage['stage_id']: self.Dialog_Open(selected)),
                ('×', len(process['stages']) > 1, lambda _checked=False, selected=stage['stage_id']: self.Stage_Remove(selected))):
                button = QToolButton()
                button.setText(label)
                button.setEnabled(enabled)
                button.clicked.connect(callback)
                button.setAccessibleName(self._translator.Text_Get('process.detail') if label == '…' else label)
                row.addWidget(button)
            self.stages_layout.addWidget(card)
            self.cards[stage['stage_id']] = card
        self.insert_before.addItem(self._translator.Text_Get('process.at_end'), '')
        self.insert_before.setCurrentIndex(max(0, self.insert_before.findData('deploy')))

    def Template_Create(self):
        process = MissionProcess_Default()
        if self._targets:
            process['stages'][5]['action'] = {'kind': 'request_recovery', 'target': self._targets[0]}
        self._Process_Emit(process)

    def StartPolicy_Change(self):
        if self._process is None:
            return
        candidate = deepcopy(self._process)
        policy = self.start_policy.currentData()
        start_phase = next((row for row in candidate['stages'] if row['stage_id'] == 'mission_start'), None)
        if policy == 'start_is_launch' and start_phase is not None and start_phase != MissionProcess_Default()['stages'][1]:
            self.error.setText(self._translator.Text_Get('process.start.preserve_custom'))
            with QSignalBlocker(self.start_policy):
                self.start_policy.setCurrentIndex(self.start_policy.findData(self._process['start_policy']))
            return
        candidate['start_policy'] = policy
        rows = candidate['stages']
        ascent = next((row for row in rows if row['stage_id'] == 'ascent'), None)
        if ascent is not None:
            ascent['condition'] = {'signal': 'event', 'operator': 'is', 'unit': 'event_id',
                'value': 'start_accepted' if policy == 'start_is_launch' else 'launch_detected'}
            ascent['hold_ms'] = 0
        if policy == 'start_is_launch':
            candidate['stages'] = [row for row in rows if row['stage_id'] != 'mission_start']
        elif ascent is not None and not any(row['stage_id'] == 'mission_start' for row in rows):
            rows.insert(rows.index(ascent), MissionProcess_Default()['stages'][1])
        self._Process_Emit(candidate)

    def Stage_Add(self):
        if self._process is None or len(self._process['stages']) >= 32:
            return
        candidate = deepcopy(self._process)
        selected = self.insert_before.currentData()
        index = next((i for i, stage in enumerate(candidate['stages']) if stage['stage_id'] == selected), len(candidate['stages']))
        candidate['stages'].insert(index, {'stage_id': 'phase_' + uuid4().hex[:12],
            'name': self._translator.Text_Get('process.new_stage'),
            'condition': {'signal': 'stage_elapsed_s', 'operator': '>=', 'value': 0.0, 'unit': 's'},
            'hold_ms': 0, 'action': {'kind': 'none', 'target': ''}})
        self._Process_Emit(candidate)

    def Stage_Rename(self, index, name):
        index = self._StageIndex_Get(index)
        if index is None:
            return
        candidate = deepcopy(self._process)
        candidate['stages'][index]['name'] = name.strip()
        self._Process_Emit(candidate)

    def Stage_Move(self, index, direction):
        index = self._StageIndex_Get(index)
        if index is None:
            return
        if self._process is None or direction not in (-1, 1) or not 0 <= index + direction < len(self._process['stages']):
            return
        candidate = deepcopy(self._process)
        rows = candidate['stages']
        rows[index], rows[index + direction] = rows[index + direction], rows[index]
        self._Process_Emit(candidate)

    def Stage_ValueSet(self, identity, value):
        index = self._StageIndex_Get(identity)
        if index is None:
            return
        candidate = deepcopy(self._process)
        candidate['stages'][index]['condition']['value'] = value
        self._Process_Emit(candidate)

    def Stage_Remove(self, index):
        index = self._StageIndex_Get(index)
        if index is None:
            return
        if self._process is None or len(self._process['stages']) <= 1:
            return
        candidate = deepcopy(self._process)
        candidate['stages'].pop(index)
        self._Process_Emit(candidate)

    def Dialog_Open(self, index):
        index = self._StageIndex_Get(index)
        if index is None:
            return
        dialog = MissionStageDialog(self._translator, self._process, index, self._targets, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._Process_Emit(dialog.Process_Get())
        dialog.deleteLater()

    def _StageIndex_Get(self, identity):
        if self._process is None:
            return None
        if type(identity) is int:
            return identity if 0 <= identity < len(self._process['stages']) else None
        return next((index for index, stage in enumerate(self._process['stages']) if stage['stage_id'] == identity), None)

    def _Process_Emit(self, candidate):
        try:
            validated = MissionProcess_Require(candidate, self._targets) if candidate is not None else None
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        self.error.clear()
        self._process = deepcopy(validated)
        self.processChanged.emit(validated)
