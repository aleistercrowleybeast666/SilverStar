"""Mission phase capsules; values are declarative desktop-reference data."""
from copy import deepcopy
import json
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QToolButton, QVBoxLayout, QWidget, QBoxLayout, QMessageBox, QScrollArea)

from silverstar_fccg.project.mission_process import (
    ACTIONS, EVENTS, SIGNALS, MissionProcess_Default, MissionProcess_Require)
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox
from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.ui.widgets import StandardComboBox, CollapsibleSection


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
        self.actions_widget = QWidget()
        action_form = QFormLayout(self.actions_widget)
        action_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit(stage['name'])
        self.name_edit.setMaxLength(128)
        identity = QLabel(stage['stage_id'])
        identity.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(text('process.identity'), identity)
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
            self.event_combo.addItem(text('process.event.' + event), event)
        self.event_combo.setCurrentIndex(max(0, self.event_combo.findData(stage['condition']['value'])))
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
    """Compatibility dialog; normal editing uses the same inline editor."""
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

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._process = None
        self._targets = ()
        self.cards = {}
        self.selected_stage_id = "ready"
        self._derived = True
        self.condition_editor = None
        self._condition_expanded = {}
        self.value_editors = {}
        self.root = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.root.addWidget(self.note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.root.addWidget(self.error)
        toolbar = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.toolbar = toolbar
        self.create_button = QPushButton()
        self.create_button.clicked.connect(self.Template_Create)
        toolbar.addWidget(self.create_button)
        self.insert_before = StandardComboBox()
        toolbar.addWidget(self.insert_before, 1)
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self.Stage_Add)
        toolbar.addWidget(self.add_button)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(lambda: self._Process_Emit(None))
        toolbar.addWidget(self.clear_button)
        self.root.addLayout(toolbar)
        self.start_policy = StandardComboBox()
        self.start_policy.currentIndexChanged.connect(self.StartPolicy_Change)
        self.root.addWidget(self.start_policy)
        self.container = QWidget()
        self.stages_layout = QVBoxLayout(self.container)
        self.stages_layout.setContentsMargins(0, 0, 0, 0)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.selector_scroll=QScrollArea();self.selector_scroll.setWidgetResizable(True)
        TouchScroll_Enable(self.selector_scroll);self.selector_scroll.setWidget(self.container)
        self.selector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.columns.addWidget(self.selector_scroll,1)
        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setContentsMargins(0,0,0,0)
        self.detail_groups = {}
        self.detail_bodies = {}
        for key in ('condition','estimation','control','records'):
            group = QGroupBox()
            body = QVBoxLayout(group)
            self.detail_layout.addWidget(group)
            self.detail_groups[key] = group
            self.detail_bodies[key] = body
        self.detail_scroll=QScrollArea();self.detail_scroll.setWidgetResizable(True)
        TouchScroll_Enable(self.detail_scroll);self.detail_scroll.setWidget(self.detail_widget)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.columns.addWidget(self.detail_scroll,2)
        self.root.addLayout(self.columns)
        self.Language_Apply(translator)

    def Language_Apply(self, translator):
        self._translator = translator
        self.setTitle(translator.Text_Get('process.title'))
        for key, group in self.detail_groups.items():
            group.setTitle(translator.Text_Get('workflow.group.' + key))
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
        selector_position=self.selector_scroll.verticalScrollBar().value()
        self._derived = process is None
        self._process = deepcopy(process if process is not None else MissionProcess_Default())
        self._targets = tuple(targets)
        while self.stages_layout.count():
            widget = self.stages_layout.takeAt(0).widget()
            if widget:widget.hide(); widget.deleteLater()
        self.cards.clear(); self.value_editors.clear(); self.insert_before.clear()
        self.create_button.setVisible(True)
        self.note.setText(self._translator.Text_Get('workflow.derived' if self._derived else 'process.reference_note'))
        for widget in (self.add_button, self.insert_before, self.clear_button, self.start_policy):
            widget.setVisible(not self._derived)
        with QSignalBlocker(self.start_policy):
            self.start_policy.setCurrentIndex(self.start_policy.findData(self._process['start_policy']))
        self.add_button.setEnabled(len(self._process['stages']) < 32)
        for index, stage in enumerate(self._process['stages']):
            identity = stage['stage_id']
            self.insert_before.addItem(self._translator.Text_Get('process.before',name=stage['name']),identity)
            card = QFrame(); card.setObjectName('missionPhaseCapsule')
            card.setStyleSheet('QFrame#missionPhaseCapsule {border:1px solid palette(mid);border-radius:14px;background:palette(base);}')
            row = QVBoxLayout(card)
            choose = QPushButton(f"{index+1}  {stage['name']}")
            choose.setCheckable(True); choose.setChecked(identity == self.selected_stage_id)
            choose.clicked.connect(lambda _checked=False, selected=identity: self.Stage_Select(selected))
            row.addWidget(choose)
            condition = stage['condition']
            value = self._translator.Text_Get('process.event.' + condition['value']) if condition['signal']=='event' else str(condition['value'])+' '+condition['unit']
            summary = QLabel(value); summary.setWordWrap(True);summary.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(summary)
            features = QLabel(); features.setWordWrap(True);features.setObjectName('phaseFunctions_'+identity)
            features.setTextFormat(Qt.TextFormat.PlainText);row.addWidget(features)
            if not self._derived:
                actions = QHBoxLayout()
                for label, enabled, callback in (
                    ('↑',index>0,lambda _c=False, selected=identity:self.Stage_Move(selected,-1)),
                    ('↓',index+1<len(self._process['stages']),lambda _c=False, selected=identity:self.Stage_Move(selected,1)),
                    ('×',len(self._process['stages'])>1,lambda _c=False, selected=identity:self.Stage_Remove(selected))):
                    button=QToolButton();button.setText(label);button.setEnabled(enabled);button.clicked.connect(callback);actions.addWidget(button)
                row.addLayout(actions)
            self.stages_layout.addWidget(card);self.cards[identity]=card
        self.stages_layout.addStretch(1)
        self.insert_before.addItem(self._translator.Text_Get('process.at_end'),'')
        self.insert_before.setCurrentIndex(max(0,self.insert_before.findData('deploy')))
        if self.selected_stage_id not in self.cards:
            self.selected_stage_id = self._process['stages'][0]['stage_id']
        self.Stage_Select(self.selected_stage_id,commit_pending=False)
        QTimer.singleShot(0,self,lambda:self.selector_scroll.verticalScrollBar().setValue(selector_position))

    def Stage_Select(self, identity, *, commit_pending=True):
        index=self._StageIndex_Get(identity)
        if index is None: return
        old_selected=self.selected_stage_id
        detail_position=self.detail_scroll.verticalScrollBar().value()
        if commit_pending and self.condition_editor is not None and self.condition_editor._dirty:
            pending=self.condition_editor.Process_Collect()
            if pending is None:return
            self._process=pending;self.processChanged.emit(deepcopy(pending))
        self.selected_stage_id=self._process['stages'][index]['stage_id']
        body=self.detail_bodies['condition']
        while body.count():
            widget=body.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        if self.condition_editor is not None:
            self.detail_bodies['control'].removeWidget(self.condition_editor.actions_widget)
            self.condition_editor.actions_widget.hide();self.condition_editor.actions_widget.deleteLater()
        self.condition_editor=MissionStageEditor(self._translator,self._process,index,self._targets,split_actions=True)
        self.condition_editor.setEnabled(not self._derived)
        self.condition_editor.actions_widget.setEnabled(not self._derived)
        self.detail_bodies['control'].insertWidget(0,self.condition_editor.actions_widget)
        self.condition_editor.processApplied.connect(self._Process_Emit)
        self.condition_editor.discarded.connect(lambda:QTimer.singleShot(0,self,lambda:self.Stage_Select(self.selected_stage_id)))
        row=self._process['stages'][index]
        condition=row['condition']
        value=self._translator.Text_Get('process.event.'+condition['value']) if condition['signal']=='event' else str(condition['value'])+' '+condition['unit']
        summary=QLabel(row['name']+' · '+value);summary.setWordWrap(True);body.addWidget(summary)
        details=CollapsibleSection(self._translator.Text_Get('workflow.condition_details'),
            expanded=self._condition_expanded.get(self.selected_stage_id,False))
        details.ExpandedChanged.connect(lambda expanded,key=self.selected_stage_id:self._condition_expanded.__setitem__(key,expanded))
        QVBoxLayout(details.body).addWidget(self.condition_editor);body.addWidget(details)
        for selected,card in self.cards.items():
            button=card.findChild(QPushButton)
            with QSignalBlocker(button):button.setChecked(selected==self.selected_stage_id)
        self.selectionChanged.emit(self.selected_stage_id)
        QTimer.singleShot(0,self,lambda:self.detail_scroll.verticalScrollBar().setValue(detail_position if old_selected==self.selected_stage_id else 0))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        narrow=self.width()<800
        self.toolbar.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        self.columns.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        height=max(430,min(700,self.window().height()-340))
        self.selector_scroll.setFixedHeight(210 if narrow else height)
        self.detail_scroll.setFixedHeight(height)

    def Template_Create(self):
        process = MissionProcess_Default()
        if self._targets:
            deploy = next(stage for stage in process['stages'] if stage['stage_id'] == 'deploy')
            deploy['action'] = {'kind': 'request_recovery', 'target': self._targets[0]}
        old = ' / '.join(stage['name'] for stage in self._process['stages'])
        new = ' / '.join(stage['name'] for stage in process['stages'])
        old_rows={row['stage_id']:row for row in self._process['stages']}
        new_rows={row['stage_id']:row for row in process['stages']}
        changes='\n'.join(identity+': '+json.dumps(old_rows.get(identity),ensure_ascii=False)+' → '+
            json.dumps(new_rows.get(identity),ensure_ascii=False) for identity in sorted(set(old_rows)|set(new_rows))
            if old_rows.get(identity)!=new_rows.get(identity))
        answer = QMessageBox.question(self,self._translator.Text_Get('workflow.template_preview'),
            self._translator.Text_Get('workflow.template_changes',old=old,new=new)+'\n\n'+changes,
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Apply:self._Process_Emit(process)

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
        removed=candidate['stages'].pop(index)
        affected=getattr(self,'boundary_references',{}).get(removed['stage_id'],[])
        self._Process_Emit(candidate)
        if affected:self.error.setText(self._translator.Text_Get('workflow.deleted_boundary',names=', '.join(affected)))

    def Dialog_Open(self,index):
        selected=self._StageIndex_Get(index)
        if selected is not None:self.Stage_Select(self._process['stages'][selected]['stage_id'])

    def _StageIndex_Get(self, identity):
        if self._process is None:
            return None
        if type(identity) is int:
            return identity if 0 <= identity < len(self._process['stages']) else None
        return next((index for index, stage in enumerate(self._process['stages']) if stage['stage_id'] == identity), None)

    def _Process_Emit(self, candidate):
        if candidate is not None and self.condition_editor is not None and self.condition_editor._dirty:
            pending=self.condition_editor.Process_Collect()
            if pending is None:return
            old={row['stage_id']:row for row in self._process['stages']}
            edited=next((row for row in pending['stages'] if row['stage_id']==self.selected_stage_id),None)
            selected=next((row for row in candidate['stages'] if row['stage_id']==self.selected_stage_id),None)
            if edited is not None and selected is not None:
                for key in ('name','condition','hold_ms','action'):
                    if selected[key]==old[self.selected_stage_id][key]:selected[key]=deepcopy(edited[key])
        try:
            validated = MissionProcess_Require(candidate, self._targets) if candidate is not None else None
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        self.error.clear()
        self._process = deepcopy(validated)
        self.processChanged.emit(validated)
