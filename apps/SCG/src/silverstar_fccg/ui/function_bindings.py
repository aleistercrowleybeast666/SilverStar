"""Mission function views reference one model instance and canonical parameters."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QTimer, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QGroupBox)

from silverstar_fccg.project.mission_functions import (
    Functions_Derive, FunctionsCatalog_Get, FunctionCoverage_Get, Functions_Issues, FunctionsCanonical_Get)
from silverstar_fccg.project.capabilities import Capability_UserSelectable_Is
from silverstar_fccg.ui.widgets import StandardComboBox, CollapsibleSection
from silverstar_fccg.ui.mission_process_panel import MissionStageName_Get


class FunctionBindingsEditor(QWidget):
    functionsChanged = Signal(object)
    addRequested = Signal(str)
    removeRequested = Signal(str)
    parametersRequested = Signal(str)
    importRequested = Signal(str)
    exportRequested = Signal(str)

    def __init__(self, translator, categories, parent=None, *, transactional=False, shared_only=False, instance_ids=None,
                 catalog_only=False):
        super().__init__(parent)
        self._translator = translator
        self.categories = tuple(categories)
        self._transactional = transactional
        self._shared_only = shared_only
        self._instance_ids = None if instance_ids is None else frozenset(instance_ids)
        self._catalog_only = catalog_only
        self._model = None
        self._selected = ''
        self._sections = {}
        self._expanded = {}
        self._range_drafts = {}
        self.root = QVBoxLayout(self); self.root.setContentsMargins(0,0,0,0)

    def Configuration_Set(self, model, catalog, stage_id, process):
        self._model, self._catalog = model, catalog
        self._process, self._stage_id = process, stage_id
        self._configuration = Functions_Derive(model,catalog)
        self._declarations = {row['plugin_id']:row for row in FunctionsCatalog_Get(catalog)}
        self._issues = Functions_Issues(model,catalog)
        while self.root.count():
            widget=self.root.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        self._sections = {}
        text=self._translator.Text_Get
        self.add_combo=StandardComboBox()
        for row in self._declarations.values():
            if row['category'] in self.categories:
                self.add_combo.addItem(row['name'].get(self._translator.language,row['plugin_id']),row['plugin_id'])
        toolbar=QWidget(); bar=QHBoxLayout(toolbar);bar.setContentsMargins(0,0,0,0)
        bar.addWidget(self.add_combo,1)
        add=QPushButton(text('workflow.function.add'));add.setEnabled(self.add_combo.count()>0)
        add.clicked.connect(lambda:self.addRequested.emit(str(self.add_combo.currentData())))
        bar.addWidget(add);self.root.addWidget(toolbar)
        toolbar.setVisible(not self._transactional)
        if self._catalog_only:
            return
        functions=[row for row in self._configuration['functions'] if row['category'] in self.categories
                   and (self._instance_ids is None or row['instance_id'] in self._instance_ids)]
        if functions:
            self.add_combo.setCurrentIndex(max(0,self.add_combo.findData(functions[0]['plugin_id'])))
        if not functions:
            empty=QLabel(text('workflow.function.empty'));empty.setWordWrap(True);self.root.addWidget(empty)
            return
        if self._selected not in {row['instance_id'] for row in functions}:
            self._selected=functions[0]['instance_id']
        stage_ids=[stage['stage_id'] for stage in process['stages']]
        for function in functions:
            identity=function['instance_id'];declaration=self._declarations.get(function['plugin_id'],{})
            status=FunctionCoverage_Get(function,stage_ids,process).get(stage_id,'inactive')
            name=declaration.get('name',{}).get(self._translator.language,function['plugin_id'])
            single = self._transactional and self._instance_ids is not None and len(functions) == 1
            card = (QWidget(self) if single else
                    QGroupBox(name if self._shared_only else name+' · '+text('workflow.coverage.'+status), self))
            card.setObjectName('functionCard_'+identity)
            card_layout=QVBoxLayout(card)
            section=CollapsibleSection(text('workflow.function.details'), parent=card,
                expanded=self._expanded.get(identity, self._transactional and status in ('active', 'start', 'once')))
            section.setObjectName('functionDetails_'+identity)
            section.ExpandedChanged.connect(lambda expanded,key=identity:self._expanded.__setitem__(key,expanded))
            body=QVBoxLayout(section.body)
            if single:
                card_layout.setContentsMargins(0, 0, 0, 0)
                section.toggle_button.setChecked(True)
                section.toggle_button.hide()
                section.body.setObjectName('functionEditorBody')
                body.setContentsMargins(0, 0, 0, 0)
            summary=QLabel(text('workflow.function.compact_summary',
                mode=text('workflow.execution.'+function['execution']),
                start=self._BoundaryText_Get(function['start']),stop=self._BoundaryText_Get(function['stop'])))
            summary.setTextFormat(Qt.TextFormat.PlainText);summary.setWordWrap(True);card_layout.addWidget(summary)
            owner=declaration.get('parameter_owner','')
            manifest=catalog.Component_Get(owner) if owner else None
            modified=sum(model.algorithm_parameters.get(owner,{}).get(parameter.parameter_id,parameter.default)!=parameter.default
                for parameter in manifest.algorithm_parameters) if manifest else 0
            source=QLabel(text('workflow.parameter_source',count=modified));source.setWordWrap(True)
            if modified:
                card_layout.addWidget(source)
            inputs=', '.join(key+' → '+value for key,value in function['input_bindings'].items()) or '—'
            bindings=QLabel(text('workflow.function.bindings',inputs=inputs,output=function['output'],
                timing=text('workflow.parameter_timing.'+declaration.get('parameter_timing','build_only'))))
            bindings.setWordWrap(True);bindings.setTextFormat(Qt.TextFormat.PlainText)
            issue_text='\n'.join(issue.code+': '+issue.message for issue in self._issues if issue.function_id == identity)
            issues=QLabel(issue_text);issues.setWordWrap(True);issues.setTextFormat(Qt.TextFormat.PlainText)
            issues.setVisible(bool(issue_text))
            card_layout.addWidget(issues)
            self._RangeEditor_Add(body,function,declaration)
            diagnostics = CollapsibleSection(text('workflow.function.interface_details'), parent=section.body)
            technical = QVBoxLayout(diagnostics.body)
            if not modified:
                technical.addWidget(source)
            technical.addWidget(bindings)
            identity_label = QLabel(identity + ' · ' + function['plugin_id'] + ' · v' + declaration.get('version', '?'), diagnostics.body)
            identity_label.setWordWrap(True)
            identity_label.setTextFormat(Qt.TextFormat.PlainText)
            technical.addWidget(identity_label)
            body.addWidget(diagnostics)
            actions=QHBoxLayout()
            owner=declaration.get('parameter_owner','')
            for key,signal in (('parameters',self.parametersRequested),('import',self.importRequested),('export',self.exportRequested)):
                if self._transactional and key != 'parameters': continue
                button=QPushButton(text('workflow.function.'+key));button.setEnabled(bool(owner))
                button.clicked.connect(lambda _checked=False, selected=owner, callback=signal:callback.emit(selected))
                actions.addWidget(button)
            remove=QPushButton(text('workflow.function.remove'), section.body)
            remove.setVisible(not self._transactional)
            remove.setEnabled(function['category']=='estimation' and identity!='ins')
            remove.clicked.connect(lambda _checked=False, selected=identity:self.removeRequested.emit(selected))
            actions.addWidget(remove);body.addLayout(actions)
            card_layout.addWidget(section)
            self.root.addWidget(card);self._sections[identity]=section

    def _BoundaryText_Get(self,boundary):
        if boundary['kind'] in ('stage_enter', 'stage_exit'):
            name=next((MissionStageName_Get(row, self._translator) for row in self._process['stages'] if row['stage_id']==boundary['stage_id']),boundary['stage_id'])
            return self._translator.Text_Get('workflow.boundary.' + ('stage_exit' if boundary['kind']=='stage_exit' else 'stage'),name=name)
        return self._translator.Text_Get('workflow.boundary.'+boundary['kind'])

    def _BoundaryCombo_Create(self,boundary, *, stop=False):
        combo=StandardComboBox()
        for kind in ('system_prepare','mission_start','system_landed','lifecycle_end'):
            combo.addItem(self._translator.Text_Get('workflow.boundary.'+kind),(kind,''))
        for stage in self._process['stages']:
            kind = 'stage_exit' if stop else 'stage_enter'
            combo.addItem(self._translator.Text_Get('workflow.boundary.'+('stage_exit' if stop else 'stage'),name=MissionStageName_Get(stage, self._translator)),(kind,stage['stage_id']))
            # Preserve an old explicit entry-stop until the user migrates it.
            if stop and boundary == {'kind':'stage_enter','stage_id':stage['stage_id']}:
                combo.addItem(self._translator.Text_Get('workflow.boundary.legacy_stop',name=stage['name']),('stage_enter',stage['stage_id']))
        value=(boundary['kind'],boundary['stage_id'])
        index=combo.findData(value)
        if index<0:combo.addItem(self._translator.Text_Get('workflow.boundary.missing',id=boundary['stage_id']),value);index=combo.count()-1
        combo.setCurrentIndex(index)
        return combo

    def _RangeEditor_Add(self,body,function,declaration):
        range_key=function['instance_id']+'.range'
        section=CollapsibleSection(self._translator.Text_Get('workflow.function.range'),expanded=self._expanded.get(range_key,False))
        if self._transactional:
            section.toggle_button.setChecked(True)
            section.toggle_button.hide()
            section.body.setObjectName('functionEditorBody')
        section.ExpandedChanged.connect(lambda expanded,key=range_key:self._expanded.__setitem__(key,expanded))
        layout=QFormLayout(section.body)
        if self._transactional:
            layout.setContentsMargins(0, 0, 0, 0)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        draft=self._range_drafts.get(function['instance_id'],function)
        start=self._BoundaryCombo_Create(draft['start']);stop=self._BoundaryCombo_Create(draft['stop'],stop=True)
        layout.addRow(self._translator.Text_Get('workflow.start'),start)
        layout.addRow(self._translator.Text_Get('workflow.stop'),stop)
        mode = StandardComboBox(section.body)
        for execution in declaration.get('executions', (function['execution'],)):
            mode.addItem(self._translator.Text_Get('workflow.execution.' + execution), execution)
        mode.setCurrentIndex(mode.findData(draft['execution']))
        layout.addRow(self._translator.Text_Get('workflow.execution_mode'), mode)
        if self._shared_only:
            for widget in (start, stop, mode):
                layout.setRowVisible(widget, False)
        note=QLabel(self._translator.Text_Get('workflow.range_note'));note.setWordWrap(True);layout.addRow(note)
        connections = CollapsibleSection(self._translator.Text_Get('workflow.function.connections'), parent=section.body)
        connection_form = QFormLayout(connections.body)
        connection_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addRow(connections)
        input_editors={}
        for capability,identity in draft['input_bindings'].items():
            combo=StandardComboBox()
            combo.setObjectName('functionInput_' + function['instance_id'] + '_' + capability)
            for instance in self._model.device_instances:
                if capability in self._catalog.Component_Get(instance.plugin).provides:
                    combo.addItem(instance.instance_id,instance.instance_id)
            if combo.findData(identity)<0:combo.addItem(identity,identity)
            combo.setCurrentIndex(combo.findData(identity));input_editors[capability]=combo
            connection_form.addRow(capability,combo)
        dependencies={}
        for identity in sorted({row['instance_id'] for row in self._configuration['functions'] if row['instance_id']!=function['instance_id']} | set(function['depends_on'])):
            role = self._translator.Text_Get('workflow.role.' + identity)
            check=QCheckBox(role if role != 'workflow.role.' + identity else identity)
            check.setObjectName('functionDependency_' + function['instance_id'] + '_' + identity)
            check.setChecked(identity in draft['depends_on']);dependencies[identity]=check
            connection_form.addRow(self._translator.Text_Get('workflow.dependency'),check)
        apply=QPushButton(self._translator.Text_Get('capsule.apply'), section.body)
        native_stream = (self._process['execution'] == 'firmware_bounded'
                         and function['category'] in ('recording', 'telemetry'))
        native_navigation = (self._process['execution'] == 'firmware_bounded'
                             and function['instance_id'] in ('ins', 'estimator'))
        if native_navigation:
            accepted = {row['stage_id'] for row in self._process['stages']
                        if row['condition'] == {'signal': 'event', 'operator': 'is',
                            'value': 'start_accepted', 'unit': 'event_id'} and row['hold_ms'] == 0}
            for index in range(start.count()):
                kind, identity = start.itemData(index)
                start.model().item(index).setEnabled(kind == 'mission_start' or
                    (kind == 'stage_enter' and identity in accepted))
        lifecycle_only = function['category'] in ('recording', 'telemetry', 'preparation', 'control') and not native_stream
        def Collect():
            selected=deepcopy(function)
            selected.update(start=dict(zip(('kind','stage_id'),start.currentData())),
                stop=dict(zip(('kind','stage_id'),stop.currentData())),
                execution=mode.currentData(),
                input_bindings={key:str(combo.currentData()) for key,combo in input_editors.items()},
                depends_on=[key for key,check in dependencies.items() if check.isChecked()])
            return selected
        def Draft_Change(*_args):
            if start.currentData() is None or stop.currentData() is None: return
            self._range_drafts[function['instance_id']]=Collect()
        for combo in (start,stop,mode):
            combo.setEnabled(not lifecycle_only)
            if not lifecycle_only:combo.currentIndexChanged.connect(Draft_Change)
        # Edits are collected in this transaction. The model apply API changes
        # the canonical capability source authority and rebinds every consumer.
        native = self._process['execution'] == 'firmware_bounded'
        for capability, combo in input_editors.items():
            combo.setEnabled(native and Capability_UserSelectable_Is(capability) and combo.count() > 1)
            if combo.isEnabled(): combo.currentIndexChanged.connect(Draft_Change)
        for identity, check in dependencies.items():
            check.setEnabled(native_stream and identity in ('ins', 'estimator'))
            if check.isEnabled(): check.toggled.connect(Draft_Change)
        if native and input_editors:
            shared_note = QLabel(self._translator.Text_Get('workflow.function.source_shared'), connections.body)
            shared_note.setWordWrap(True); connection_form.addRow(shared_note)
        if native_stream:
            dependency_note = QLabel(self._translator.Text_Get('workflow.function.dependency_scope'), connections.body)
            dependency_note.setWordWrap(True); connection_form.addRow(dependency_note)
        def Apply():
            candidate=deepcopy(self._configuration)
            selected=next(row for row in candidate['functions'] if row['instance_id']==function['instance_id'])
            selected.update(Collect())
            if any(row[key]['kind']=='stage_exit' for row in candidate['functions'] for key in ('start','stop')):
                candidate['schema_version']=2
            self.functionsChanged.emit(candidate)
        apply.clicked.connect(Apply)
        # The outer dialog is the sole commit boundary for stage drafts.
        connections_editable = any(widget.isEnabled() for widget in (*input_editors.values(), *dependencies.values()))
        apply.setVisible((not lifecycle_only or connections_editable) and not self._transactional)
        layout.addRow(apply)
        if lifecycle_only:
            reason=QLabel(self._translator.Text_Get('workflow.lifecycle_only' if function['category'] in ('recording','telemetry')
                else 'workflow.owner_lifecycle'));reason.setWordWrap(True);layout.addRow(reason)
            restore=QPushButton(self._translator.Text_Get('workflow.restore_lifecycle'))
            def Restore():
                canonical=FunctionsCanonical_Get(self._model,self._catalog)
                replacement=next(row for row in canonical['functions'] if row['instance_id']==function['instance_id'])
                candidate=deepcopy(self._configuration)
                next(row for row in candidate['functions'] if row['instance_id']==function['instance_id']).update(replacement)
                self.functionsChanged.emit(candidate)
            restore.clicked.connect(Restore);layout.addRow(restore)
        elif native_stream:
            reason = QLabel(self._translator.Text_Get('workflow.stream_scope'))
            reason.setWordWrap(True); layout.addRow(reason)
        elif native_navigation:
            reason = QLabel(self._translator.Text_Get('workflow.navigation_scope'))
            reason.setWordWrap(True); layout.addRow(reason)
        body.addWidget(section)
        self._sections[function['instance_id']+'.range']=section

    def Drafts_Collect(self):
        return deepcopy(self._range_drafts)

    def Drafts_Clear(self):
        self._range_drafts.clear()

    def Reveal(self,identity):
        section=self._sections.get(identity)
        if section:section.toggle_button.setChecked(True)
