"""Mission function views reference one model instance and canonical parameters."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QTimer, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QGroupBox)

from silverstar_fccg.project.mission_functions import (
    Functions_Derive, FunctionsCatalog_Get, FunctionCoverage_Get, Functions_Issues, FunctionsCanonical_Get)
from silverstar_fccg.ui.widgets import StandardComboBox, CollapsibleSection


class FunctionBindingsEditor(QWidget):
    functionsChanged = Signal(object)
    addRequested = Signal(str)
    removeRequested = Signal(str)
    parametersRequested = Signal(str)
    importRequested = Signal(str)
    exportRequested = Signal(str)

    def __init__(self, translator, categories, parent=None, *, transactional=False):
        super().__init__(parent)
        self._translator = translator
        self.categories = tuple(categories)
        self._transactional = transactional
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
        functions=[row for row in self._configuration['functions'] if row['category'] in self.categories]
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
            status=FunctionCoverage_Get(function,stage_ids).get(stage_id,'inactive')
            name=declaration.get('name',{}).get(self._translator.language,function['plugin_id'])
            card=QGroupBox(name+' · '+text('workflow.coverage.'+status))
            card.setObjectName('functionCard_'+identity)
            card_layout=QVBoxLayout(card)
            section=CollapsibleSection(text('workflow.function.details'),
                expanded=self._expanded.get(identity,False))
            section.setObjectName('functionDetails_'+identity)
            section.ExpandedChanged.connect(lambda expanded,key=identity:self._expanded.__setitem__(key,expanded))
            body=QVBoxLayout(section.body)
            summary=QLabel(text('workflow.function.summary',id=identity,version=declaration.get('version','?'),
                mode=text('workflow.execution.'+function['execution']),
                start=self._BoundaryText_Get(function['start']),stop=self._BoundaryText_Get(function['stop'])))
            summary.setTextFormat(Qt.TextFormat.PlainText);summary.setWordWrap(True);card_layout.addWidget(summary)
            owner=declaration.get('parameter_owner','')
            manifest=catalog.Component_Get(owner) if owner else None
            modified=sum(model.algorithm_parameters.get(owner,{}).get(parameter.parameter_id,parameter.default)!=parameter.default
                for parameter in manifest.algorithm_parameters) if manifest else 0
            source=QLabel(text('workflow.parameter_source',count=modified));source.setWordWrap(True);card_layout.addWidget(source)
            inputs=', '.join(key+' → '+value for key,value in function['input_bindings'].items()) or '—'
            bindings=QLabel(text('workflow.function.bindings',inputs=inputs,output=function['output'],
                timing=text('workflow.parameter_timing.'+declaration.get('parameter_timing','build_only'))))
            bindings.setWordWrap(True);bindings.setTextFormat(Qt.TextFormat.PlainText);card_layout.addWidget(bindings)
            issue_text='\n'.join(issue.code+': '+issue.message for issue in self._issues if issue.function_id in (identity,''))
            issues=QLabel(issue_text);issues.setWordWrap(True);issues.setTextFormat(Qt.TextFormat.PlainText)
            card_layout.addWidget(issues)
            self._RangeEditor_Add(body,function,declaration)
            actions=QHBoxLayout()
            owner=declaration.get('parameter_owner','')
            for key,signal in (('parameters',self.parametersRequested),('import',self.importRequested),('export',self.exportRequested)):
                if self._transactional and key != 'parameters': continue
                button=QPushButton(text('workflow.function.'+key));button.setEnabled(bool(owner))
                button.clicked.connect(lambda _checked=False, selected=owner, callback=signal:callback.emit(selected))
                actions.addWidget(button)
            remove=QPushButton(text('workflow.function.remove'))
            remove.setVisible(not self._transactional)
            remove.setEnabled(function['category']=='estimation' and identity!='ins')
            remove.clicked.connect(lambda _checked=False, selected=identity:self.removeRequested.emit(selected))
            actions.addWidget(remove);body.addLayout(actions)
            card_layout.addWidget(section)
            self.root.addWidget(card);self._sections[identity]=section

    def _BoundaryText_Get(self,boundary):
        if boundary['kind'] in ('stage_enter', 'stage_exit'):
            name=next((row['name'] for row in self._process['stages'] if row['stage_id']==boundary['stage_id']),boundary['stage_id'])
            return self._translator.Text_Get('workflow.boundary.' + ('stage_exit' if boundary['kind']=='stage_exit' else 'stage'),name=name)
        return self._translator.Text_Get('workflow.boundary.'+boundary['kind'])

    def _BoundaryCombo_Create(self,boundary, *, stop=False):
        combo=StandardComboBox()
        for kind in ('system_prepare','mission_start','system_landed','lifecycle_end'):
            combo.addItem(self._translator.Text_Get('workflow.boundary.'+kind),(kind,''))
        for stage in self._process['stages']:
            kind = 'stage_exit' if stop else 'stage_enter'
            combo.addItem(self._translator.Text_Get('workflow.boundary.'+('stage_exit' if stop else 'stage'),name=stage['name']),(kind,stage['stage_id']))
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
        section.ExpandedChanged.connect(lambda expanded,key=range_key:self._expanded.__setitem__(key,expanded))
        layout=QFormLayout(section.body)
        draft=self._range_drafts.get(function['instance_id'],function)
        start=self._BoundaryCombo_Create(draft['start']);stop=self._BoundaryCombo_Create(draft['stop'],stop=True)
        layout.addRow(self._translator.Text_Get('workflow.start'),start)
        layout.addRow(self._translator.Text_Get('workflow.stop'),stop)
        note=QLabel(self._translator.Text_Get('workflow.range_note'));note.setWordWrap(True);layout.addRow(note)
        input_editors={}
        for capability,identity in draft['input_bindings'].items():
            combo=StandardComboBox()
            for instance in self._model.device_instances:
                if capability in self._catalog.Component_Get(instance.plugin).provides:
                    combo.addItem(instance.instance_id,instance.instance_id)
            if combo.findData(identity)<0:combo.addItem(identity,identity)
            combo.setCurrentIndex(combo.findData(identity));input_editors[capability]=combo
            layout.addRow(capability,combo)
        dependencies={}
        for identity in sorted({row['instance_id'] for row in self._configuration['functions'] if row['instance_id']!=function['instance_id']} | set(function['depends_on'])):
            check=QCheckBox(identity);check.setChecked(identity in draft['depends_on']);dependencies[identity]=check
            layout.addRow(self._translator.Text_Get('workflow.dependency'),check)
        apply=QPushButton(self._translator.Text_Get('capsule.apply'))
        lifecycle_only=function['category'] in ('recording','telemetry')
        def Collect():
            selected=deepcopy(function)
            selected.update(start=dict(zip(('kind','stage_id'),start.currentData())),
                stop=dict(zip(('kind','stage_id'),stop.currentData())),
                input_bindings={key:str(combo.currentData()) for key,combo in input_editors.items()},
                depends_on=[key for key,check in dependencies.items() if check.isChecked()])
            return selected
        def Draft_Change(*_args):
            if start.currentData() is None or stop.currentData() is None: return
            self._range_drafts[function['instance_id']]=Collect()
        for combo in (start,stop,*input_editors.values()):
            combo.setEnabled(not lifecycle_only)
            if not lifecycle_only:combo.currentIndexChanged.connect(Draft_Change)
        for check in dependencies.values():
            check.setEnabled(not lifecycle_only)
            if not lifecycle_only:check.toggled.connect(Draft_Change)
        def Apply():
            candidate=deepcopy(self._configuration)
            selected=next(row for row in candidate['functions'] if row['instance_id']==function['instance_id'])
            selected.update(Collect())
            if any(row[key]['kind']=='stage_exit' for row in candidate['functions'] for key in ('start','stop')):
                candidate['schema_version']=2
            self._range_drafts.pop(function['instance_id'],None)
            self.functionsChanged.emit(candidate)
        apply.clicked.connect(Apply);apply.setVisible(not lifecycle_only);layout.addRow(apply)
        if lifecycle_only:
            reason=QLabel(self._translator.Text_Get('workflow.lifecycle_only'));reason.setWordWrap(True);layout.addRow(reason)
            restore=QPushButton(self._translator.Text_Get('workflow.restore_lifecycle'))
            def Restore():
                canonical=FunctionsCanonical_Get(self._model,self._catalog)
                replacement=next(row for row in canonical['functions'] if row['instance_id']==function['instance_id'])
                candidate=deepcopy(self._configuration)
                next(row for row in candidate['functions'] if row['instance_id']==function['instance_id']).update(replacement)
                self.functionsChanged.emit(candidate)
            restore.clicked.connect(Restore);layout.addRow(restore)
        body.addWidget(section)
        self._sections[function['instance_id']+'.range']=section

    def Drafts_Collect(self):
        return deepcopy(self._range_drafts)

    def Drafts_Clear(self):
        self._range_drafts.clear()

    def Reveal(self,identity):
        section=self._sections.get(identity)
        if section:section.toggle_button.setChecked(True)
