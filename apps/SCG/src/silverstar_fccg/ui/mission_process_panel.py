"""Ordered mission capsules. Stage editing belongs exclusively to a transaction."""
from copy import deepcopy
import json
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QToolButton, QVBoxLayout, QWidget, QBoxLayout, QMessageBox, QScrollArea)

from silverstar_fccg.project.mission_process import (
    ACTIONS, EVENTS, SIGNALS, MissionProcess_Default, MissionProcess_FirmwareDefault, MissionProcess_Require)
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox
from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.ui.widgets import StandardComboBox, CollapsibleSection


def MissionStageName_Get(stage, translator):
    definitions = (*MissionProcess_Default()['stages'], *MissionProcess_FirmwareDefault()['stages'],
        *MissionProcess_FirmwareDefault(acceleration_detection=True, recovery=True, recovery_target='preview')['stages'])
    defaults = {row['name'] for row in definitions if row['stage_id'] == stage['stage_id']}
    return translator.Text_Get('workflow.stage.' + stage['stage_id']) if stage['name'] in defaults else stage['name']


class MissionStageEditor(QWidget):
    processApplied = Signal(object)
    discarded = Signal()

    def __init__(self, translator, process, index, targets, parent=None, *, split_actions=False):
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
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.form = form
        self.actions_widget = QWidget(self)
        action_form = QFormLayout(self.actions_widget)
        action_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit(stage['name'])
        self.name_edit.setMaxLength(128)
        self.name_edit.setToolTip(text('process.identity') + ': ' + stage['stage_id'])
        form.addRow(text('process.name'), self.name_edit)
        self.signal_combo = StandardComboBox()
        for signal in SIGNALS:
            self.signal_combo.addItem(text('process.signal.' + signal), signal)
        self.signal_combo.setCurrentIndex(self.signal_combo.findData(stage['condition']['signal']))
        form.addRow(text('process.condition'), self.signal_combo)
        self.operator = StandardComboBox()
        self.operator.addItems(('>=', '<='))
        self.operator.setCurrentText(stage['condition']['operator'])
        form.addRow(text('process.operator'), self.operator)
        self.number = QDoubleSpinBox()
        self.number.setDecimals(6)
        self.number.setRange(-1e7, 1e7)
        self.number.setValue(stage['condition']['value'] if stage['condition']['signal'] != 'event' else 0)
        self.number.valueChanged.connect(lambda _value: setattr(self, '_numeric_edited', True))
        form.addRow(text('process.threshold'), self.number)
        self.event_combo = StandardComboBox()
        for event in EVENTS:
            if process['execution'] == 'firmware_bounded' and event in ('launch_detected', 'burnout_detected'):
                continue
            self.event_combo.addItem(text('process.event.' + event), event)
        event_value = stage['condition']['value']
        if stage['condition']['signal'] == 'event' and self.event_combo.findData(event_value) < 0:
            self.event_combo.addItem(text('process.event.' + event_value), event_value)
            self.event_combo.model().item(self.event_combo.count() - 1).setEnabled(False)
        self.event_combo.setCurrentIndex(max(0, self.event_combo.findData(event_value)))
        form.addRow(text('process.event'), self.event_combo)
        self.hold = QSpinBox()
        self.hold.setRange(0, 3600000)
        self.hold.setSuffix(' ms')
        self.hold.setValue(stage['hold_ms'])
        form.addRow(text('process.hold'), self.hold)
        self.action = StandardComboBox()
        for action in ACTIONS:
            self.action.addItem(text('process.action.' + action), action)
        self.action.setCurrentIndex(self.action.findData(stage['action']['kind']))
        action_form.addRow(text('process.action'), self.action)
        self.target = StandardComboBox()
        self.target.addItem('—', '')
        for target in targets:
            self.target.addItem(target, target)
        original = stage['action']['target']
        if original and self.target.findData(original) < 0:
            self.target.addItem(text('process.target_missing', target=original), original)
        self.target.setCurrentIndex(max(0, self.target.findData(original)))
        self._targets = set(targets)
        action_form.addRow(text('process.target'), self.target)
        root.addLayout(form)
        if not split_actions: root.addWidget(self.actions_widget)
        note = QLabel(text('workflow.stage_boundary_note'))
        note.setWordWrap(True)
        root.addWidget(note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self._Discard_Click)
        root.addWidget(buttons)
        self.signal_combo.currentIndexChanged.connect(self._Fields_Refresh)
        self.action.currentIndexChanged.connect(self._Fields_Refresh)
        self._Fields_Refresh()
        self._dirty = False
        for widget in (self.name_edit,self.signal_combo,self.operator,self.event_combo,self.action,self.target,self.number,self.hold):
            signal = widget.textEdited if isinstance(widget,QLineEdit) else widget.currentIndexChanged if hasattr(widget,'currentIndexChanged') else widget.valueChanged
            signal.connect(lambda *_args:setattr(self,'_dirty',True))
        for widget in (self.number,self.hold):widget.lineEdit().textEdited.connect(lambda *_args:setattr(self,'_dirty',True))

    def _Discard_Click(self):
        self._dirty=False
        self.discarded.emit()

    def _Fields_Refresh(self):
        signal = self.signal_combo.currentData()
        event = signal == 'event'
        self.event_combo.setEnabled(event)
        self.number.setEnabled(not event)
        self.operator.setEnabled(not event and signal != 'stage_elapsed_s')
        self.hold.setEnabled(not event)
        for widget,visible in ((self.operator,not event and signal!='stage_elapsed_s'),(self.number,not event),(self.event_combo,event),(self.hold,not event)):
            self.form.setRowVisible(widget,visible)
        self.number.setSuffix(' ' + SIGNALS[signal] if not event else '')
        self.target.setEnabled(self.action.currentData() == 'request_recovery')

    def Process_Collect(self):
        if (self.number.isEnabled() and not self.number.lineEdit().hasAcceptableInput()) or (self.hold.isEnabled() and not self.hold.lineEdit().hasAcceptableInput()):
            self.error.setText(self._translator.Text_Get('capsule.invalid'))
            return
        original = self._process['stages'][self._index]
        stage = deepcopy(original)
        signal = self.signal_combo.currentData()
        same_signal = original['condition']['signal'] == signal
        self.number.interpretText(); self.hold.interpretText()
        number = original['condition']['value'] if same_signal and not self._numeric_edited else self.number.value()
        name=self.name_edit.text()
        stage.update(name=original['name'] if name==original['name'] else name.strip(), condition={
            'signal': signal, 'operator': 'is' if signal == 'event' else '>=' if signal == 'stage_elapsed_s' else self.operator.currentText(),
            'value': self.event_combo.currentData() if signal == 'event' else number,
            'unit': SIGNALS[signal]}, hold_ms=0 if signal == 'event' else self.hold.value(),
            action={'kind': self.action.currentData(), 'target': self.target.currentData() if self.action.currentData() == 'request_recovery' else ''})
        candidate = deepcopy(self._process)
        candidate['stages'][self._index] = stage
        try:
            result = MissionProcess_Require(candidate, self._targets)
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        return result

    def accept(self):
        result=self.Process_Collect()
        if result is None:return
        self._result=result;self._dirty=False
        self.processApplied.emit(deepcopy(result))

    def Process_Get(self):
        return deepcopy(self._result)


class MissionStageDialog(QDialog):
    """Compatibility dialog using the same condition editor as the transaction."""
    def __init__(self, translator, process, index, targets, parent=None):
        super().__init__(parent)
        self.editor = MissionStageEditor(translator, process, index, targets, self)
        self.setWindowTitle(translator.Text_Get('process.detail'))
        layout = QVBoxLayout(self); layout.addWidget(self.editor)
        for name in ('name_edit','signal_combo','operator','number','event_combo','hold','action','target','error'):
            setattr(self, name, getattr(self.editor, name))
        self.editor.processApplied.connect(lambda _value: super(MissionStageDialog,self).accept())
        self.editor.discarded.connect(self.reject)

    def accept(self):
        self.editor.accept()

    def Process_Get(self):
        return self.editor.Process_Get()


class MissionProcessPanel(QGroupBox):
    processChanged = Signal(object)
    selectionChanged = Signal(str)
    editRequested = Signal(str)
    stageAddRequested = Signal(object, str)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.setObjectName('missionSequence')
        self._translator = translator
        self._process = None
        self._targets = ()
        self.cards = {}
        self.selected_stage_id = 'ready'
        self._derived = True
        self.condition_editor = None
        self._condition_expanded = {}
        self.value_editors = {}
        self.boundary_references = {}
        self.process_validator = None
        self.root = QVBoxLayout(self)
        self.root.setSpacing(12)
        self.note = QLabel(self)
        self.note.setObjectName('muted')
        self.note.setWordWrap(True)
        self.root.addWidget(self.note)
        self.toolbar = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.create_button = QPushButton(self)
        self.create_button.clicked.connect(self.Template_Create)
        self.toolbar.addWidget(self.create_button)
        self.insert_before = StandardComboBox(self)
        self.toolbar.addWidget(self.insert_before, 1)
        self.add_button = QPushButton(self)
        self.add_button.clicked.connect(self.Stage_Add)
        self.toolbar.addWidget(self.add_button)
        self.root.addLayout(self.toolbar)
        self.start_policy = StandardComboBox(self)
        self.start_policy.currentIndexChanged.connect(self.StartPolicy_Change)
        self.root.addWidget(self.start_policy)
        self.policy_summary = QLabel(self)
        self.policy_summary.setObjectName('muted')
        self.policy_summary.setWordWrap(True)
        self.root.addWidget(self.policy_summary)
        self.selector_scroll = QScrollArea(self)
        self.selector_scroll.setObjectName('missionTimeline')
        self.selector_scroll.setWidgetResizable(True)
        self.selector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.selector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        TouchScroll_Enable(self.selector_scroll)
        self.container = QWidget(self.selector_scroll)
        self.stages_layout = QHBoxLayout(self.container)
        self.stages_layout.setContentsMargins(2, 6, 2, 8)
        self.stages_layout.setSpacing(8)
        self.selector_scroll.setWidget(self.container)
        self.root.addWidget(self.selector_scroll)
        self.error = QLabel(self)
        self.error.setObjectName('workflowError')
        self.error.setWordWrap(True)
        self.error.hide()
        self.root.addWidget(self.error)
        self.Language_Apply(translator)

    def StageName_Get(self, stage):
        return MissionStageName_Get(stage, self._translator)

    def Language_Apply(self, translator):
        self._translator = translator
        self.setTitle(translator.Text_Get('workflow.sequence'))
        self.create_button.setText(translator.Text_Get('workflow.template'))
        self.add_button.setText(translator.Text_Get('process.add'))
        with QSignalBlocker(self.start_policy):
            self.start_policy.clear()
            self.start_policy.addItem(translator.Text_Get('process.start.separate'), 'separate')
            self.start_policy.addItem(translator.Text_Get('process.start.combined'), 'start_is_launch')
        self.Configuration_Set(None if self._derived else self._process, self._targets)

    def Configuration_Set(self, process, targets=()):
        position = self.selector_scroll.horizontalScrollBar().value()
        self._derived = process is None
        self._process = deepcopy(process if process is not None else MissionProcess_Default())
        self._targets = tuple(targets)
        while self.stages_layout.count():
            widget = self.stages_layout.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.cards.clear()
        with QSignalBlocker(self.insert_before):
            self.insert_before.clear()
            for stage in self._process['stages']:
                self.insert_before.addItem(self._translator.Text_Get('process.before',
                    name=self.StageName_Get(stage)), stage['stage_id'])
            self.insert_before.addItem(self._translator.Text_Get('process.at_end'), '')
            self.insert_before.setCurrentIndex(self.insert_before.count() - 1)
        self.note.setText(self._translator.Text_Get('workflow.legacy_sequence_hint' if self._derived else 'workflow.sequence_hint'))
        with QSignalBlocker(self.start_policy):
            self.start_policy.setCurrentIndex(self.start_policy.findData(self._process['start_policy']))
        firmware = self._process['execution'] == 'firmware_bounded'
        self.start_policy.setVisible(not firmware)
        self.policy_summary.setVisible(firmware)
        self.policy_summary.setText(self._translator.Text_Get('workflow.policy.' + self._process['start_policy']))
        self.add_button.setEnabled(len(self._process['stages']) < 32)
        for index, stage in enumerate(self._process['stages']):
            self._Card_Add(index, stage)
        self.add_card = QPushButton(self._translator.Text_Get('workflow.add_card'), self.container)
        self.add_card.setObjectName('missionAddCard')
        self.add_card.setMinimumWidth(150)
        self.add_card.setMaximumWidth(180)
        self.add_card.setEnabled(len(self._process['stages']) < 32)
        self.add_card.clicked.connect(self.Stage_Add)
        self.stages_layout.addWidget(self.add_card)
        self.stages_layout.addStretch(1)
        if self.selected_stage_id not in self.cards:
            self.selected_stage_id = self._process['stages'][0]['stage_id']
        self.Stage_Select(self.selected_stage_id)
        self._TimelineHeight_Apply()
        QTimer.singleShot(0, self, lambda: self.selector_scroll.horizontalScrollBar().setValue(position))

    def _Card_Add(self, index, stage):
        text = self._translator.Text_Get
        identity = stage['stage_id']
        card = QFrame(self.container)
        card.setObjectName('missionPhaseCapsule')
        card.setMinimumWidth(166)
        card.setMaximumWidth(212)
        row = QVBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(8)
        boundary = stage['condition']
        value = (text('process.event.' + boundary['value']) if boundary['signal'] == 'event'
                 else text('process.signal.' + boundary['signal']) + ' ' + boundary['operator'] +
                 ' ' + str(boundary['value']) + ' ' + boundary['unit'])
        event = QLabel(text('workflow.boundary_label', value=value), card)
        event.setWordWrap(True)
        event.setObjectName('phaseBoundary')
        event.setToolTip(value)
        event.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(event)
        choose = QPushButton(f'{index + 1:02d}  {self.StageName_Get(stage)}', card)
        choose.setObjectName('phaseSelect')
        choose.setCheckable(True)
        choose.setAccessibleName(text('workflow.configure_stage', name=self.StageName_Get(stage)))
        choose.setToolTip(text('workflow.configure_stage', name=self.StageName_Get(stage)))
        choose.clicked.connect(lambda _checked=False, selected=identity: self.Dialog_Open(selected))
        row.addWidget(choose)
        features = QLabel(card)
        features.setWordWrap(True)
        features.setObjectName('phaseFunctions_' + identity)
        features.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(features, 1)
        actions = QHBoxLayout()
        for label, key, enabled, callback in (
            ('←', 'workflow.move_earlier', index > 0, lambda _c=False, selected=identity: self.Stage_Move(selected, -1)),
            ('→', 'workflow.move_later', index + 1 < len(self._process['stages']), lambda _c=False, selected=identity: self.Stage_Move(selected, 1)),
            ('×', 'workflow.remove_stage', len(self._process['stages']) > 1, lambda _c=False, selected=identity: self.Stage_Remove(selected))):
            button = QToolButton(card)
            button.setObjectName('phaseTool')
            button.setText(label)
            button.setToolTip(text(key))
            button.setAccessibleName(text(key))
            button.setEnabled(enabled)
            button.clicked.connect(callback)
            actions.addWidget(button)
        row.addLayout(actions)
        self.stages_layout.addWidget(card)
        self.cards[identity] = card

    def _TimelineHeight_Apply(self):
        # Adapt to the selected font/zoom; retain horizontal order at every width.
        height = max((card.sizeHint().height() for card in self.cards.values()), default=130)
        self.selector_scroll.setFixedHeight(max(152, height + 30))

    def Stage_Select(self, identity, *, commit_pending=False):
        index = self._StageIndex_Get(identity)
        if index is None:
            return
        self.selected_stage_id = self._process['stages'][index]['stage_id']
        for selected, card in self.cards.items():
            button = card.findChild(QPushButton, 'phaseSelect')
            with QSignalBlocker(button):
                button.setChecked(selected == self.selected_stage_id)
            card.setProperty('selected', selected == self.selected_stage_id)
            card.style().unpolish(card)
            card.style().polish(card)
        self.selectionChanged.emit(self.selected_stage_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toolbar.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 760
                                  else QBoxLayout.Direction.LeftToRight)

    def Template_Create(self):
        from silverstar_fccg.ui.mission_template import MissionTemplateDialog
        dialog = MissionTemplateDialog(self._translator, self._targets, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._Process_Emit(dialog.Process_Get())
        dialog.deleteLater()

    def StartPolicy_Change(self):
        if self._process is None:
            return
        candidate = deepcopy(self._process)
        policy = self.start_policy.currentData()
        start_phase = next((row for row in candidate['stages'] if row['stage_id'] == 'mission_start'), None)
        if policy == 'start_is_launch' and start_phase is not None and start_phase != MissionProcess_Default()['stages'][1]:
            self._Error_Set(self._translator.Text_Get('process.start.preserve_custom'))
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
        if not self._Process_Emit(candidate):
            with QSignalBlocker(self.start_policy):
                self.start_policy.setCurrentIndex(self.start_policy.findData(self._process['start_policy']))

    def Stage_Add(self):
        if self._process is None or len(self._process['stages']) >= 32:
            return
        candidate = deepcopy(self._process)
        selected = self.insert_before.currentData()
        index = next((i for i, stage in enumerate(candidate['stages']) if stage['stage_id'] == selected), len(candidate['stages']))
        identity = 'phase_' + uuid4().hex[:12]
        candidate['stages'].insert(index, {'stage_id': identity,
            'name': self._translator.Text_Get('process.new_stage'),
            'condition': {'signal': 'stage_elapsed_s', 'operator': '>=', 'value': 0.0, 'unit': 's'},
            'hold_ms': 0, 'action': {'kind': 'none', 'target': ''}})
        self.stageAddRequested.emit(candidate, identity)

    def Stage_Rename(self, index, name):
        index = self._StageIndex_Get(index)
        if index is not None:
            candidate = deepcopy(self._process)
            candidate['stages'][index]['name'] = name.strip()
            self._Process_Emit(candidate)

    def Stage_Move(self, index, direction):
        index = self._StageIndex_Get(index)
        if index is None or direction not in (-1, 1) or not 0 <= index + direction < len(self._process['stages']):
            return
        candidate = deepcopy(self._process)
        rows = candidate['stages']
        rows[index], rows[index + direction] = rows[index + direction], rows[index]
        self._Process_Emit(candidate)

    def Stage_ValueSet(self, identity, value):
        index = self._StageIndex_Get(identity)
        if index is not None:
            candidate = deepcopy(self._process)
            candidate['stages'][index]['condition']['value'] = value
            self._Process_Emit(candidate)

    def Stage_Remove(self, index):
        index = self._StageIndex_Get(index)
        if index is None or len(self._process['stages']) <= 1:
            return
        identity = self._process['stages'][index]['stage_id']
        affected = self.boundary_references.get(identity, [])
        if affected:
            self._Error_Set(self._translator.Text_Get('workflow.boundary_in_use', names=', '.join(sorted(set(affected)))))
            return
        candidate = deepcopy(self._process)
        candidate['stages'].pop(index)
        self._Process_Emit(candidate)

    def Dialog_Open(self, index):
        selected = self._StageIndex_Get(index)
        if selected is not None:
            identity = self._process['stages'][selected]['stage_id']
            self.Stage_Select(identity)
            self.editRequested.emit(identity)

    def _StageIndex_Get(self, identity):
        if self._process is None:
            return None
        if type(identity) is int:
            return identity if 0 <= identity < len(self._process['stages']) else None
        return next((index for index, stage in enumerate(self._process['stages']) if stage['stage_id'] == identity), None)

    def _Error_Set(self, message):
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def _Process_Emit(self, candidate):
        try:
            validated = MissionProcess_Require(candidate, self._targets) if candidate is not None else None
            if self.process_validator is not None:
                self.process_validator(validated)
        except (ValueError, TypeError) as error:
            self._Error_Set(str(error))
            return False
        self._Error_Set('')
        self._process = deepcopy(validated if validated is not None else MissionProcess_Default())
        self._derived = validated is None
        self.processChanged.emit(deepcopy(validated))
        return True
