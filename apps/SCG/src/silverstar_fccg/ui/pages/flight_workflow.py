"""One workflow workspace. Legacy editors are mounted once, never copied."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu,
    QGroupBox, QScrollArea, QMessageBox, QFrame)

from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsCatalog_Get, FunctionCoverage_Get, Functions_Issues
from silverstar_fccg.ui.function_bindings import FunctionBindingsEditor
from silverstar_fccg.ui.mission_coverage import MissionCoverageTable
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.widgets import CollapsibleSection


class FlightWorkflowPage(ScrollableLocalizedPage):
    configurationChanged = Signal(object)
    functionsChanged = Signal(object)
    functionAddRequested = Signal(str)
    functionRemoveRequested = Signal(str)
    parameterImportRequested = Signal(str)
    parameterExportRequested = Signal(str)

    def __init__(self, translator, legacy, navigation):
        super().__init__(translator, 'workspace.workflow.title', 'workspace.workflow.description')
        self.setObjectName('flightWorkflowWorkspace')
        self.legacy, self.navigation = legacy, navigation
        self._model = None
        self._selected_parameter_owner = ''
        self._refreshing = False
        self._scroll = self.findChild(QScrollArea)
        self._scroll.viewport().installEventFilter(self)
        self.sections = {}
        self.function_editors = []
        self.stage_panel = legacy.mission_process_panel
        self.stage_panel.process_validator = self._Process_Validate
        self.summary_strip = QFrame(self)
        self.summary_strip.setObjectName('workflowSummaryStrip')
        strip = QHBoxLayout(self.summary_strip)
        self.summary_label = QLabel(self.summary_strip)
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName('workflowSummary')
        strip.addWidget(self.summary_label, 1)
        self.library_button = QPushButton(self.summary_strip)
        self.library_button.setObjectName('primaryButton')
        self.library_button.clicked.connect(self._Library_Open)
        strip.addWidget(self.library_button)
        self.root_layout.addWidget(self.summary_strip)
        self.root_layout.addWidget(self.stage_panel)
        self.coverage_group = QGroupBox(self)
        coverage_body = QVBoxLayout(self.coverage_group)
        self.coverage_hint = QLabel(self.coverage_group)
        self.coverage_hint.setObjectName('muted')
        self.coverage_hint.setWordWrap(True)
        coverage_body.addWidget(self.coverage_hint)
        self.coverage = MissionCoverageTable(self.coverage_group)
        self.coverage.stageRequested.connect(self.stage_panel.Dialog_Open)
        self.coverage.functionRequested.connect(self._FunctionDialog_Open)
        self.coverage.currentCellChanged.connect(lambda *_args: self._FunctionActions_Refresh())
        coverage_body.addWidget(self.coverage)
        actions = QHBoxLayout()
        self.function_buttons = {}
        for key in ('parameters', 'import', 'export', 'remove'):
            button = QPushButton(self.coverage_group)
            button.clicked.connect(lambda _checked=False, action=key: self._FunctionAction_Run(action))
            actions.addWidget(button)
            self.function_buttons[key] = button
        coverage_body.addLayout(actions)
        self.root_layout.addWidget(self.coverage_group)
        self.shared = self._Section_Add('workflow.shared_library', False)
        self.shared_note = QLabel(self.shared.body)
        self.shared_note.setWordWrap(True)
        self.shared.body.layout().addWidget(self.shared_note)
        self.preparation_functions = self._Functions_Create(('preparation',), self.shared.body.layout())
        self.estimation_functions = self._Functions_Create(('estimation',), self.shared.body.layout())
        self.control_functions = self._Functions_Create(('control',), self.shared.body.layout())
        self.recording_functions = self._Functions_Create(('recording', 'telemetry'), self.shared.body.layout())
        navigation.ExistingEditors_Attach(sources=legacy.capability_group, calibration=legacy.mode_group,
            alignment=legacy.strategy_group, ins=legacy.ins_strategy_group, estimator=legacy.estimator_strategy_group)
        self.estimation_definition = CollapsibleSection(translator.Text_Get('workflow.algorithm_selection'), expanded=False, parent=self.shared.body)
        definition = QVBoxLayout(self.estimation_definition.body)
        definition.addWidget(navigation.ins_section)
        definition.addWidget(navigation.estimator_section)
        self.shared.body.layout().addWidget(self.estimation_definition)
        self.parameters = CollapsibleSection(translator.Text_Get('workflow.parameters'), expanded=False, parent=self.shared.body)
        QVBoxLayout(self.parameters.body).addWidget(navigation.parameters_section)
        self.shared.body.layout().addWidget(self.parameters)
        self.preparation = self._Section_Add('workflow.preparation', False)
        for widget in (legacy.mission_strategy_group, navigation.sources_section,
                       navigation.calibration_section, navigation.alignment_section, navigation.impact_section):
            self.preparation.body.layout().addWidget(widget)
        self.deployment = CollapsibleSection(translator.Text_Get('workflow.legacy_actions'), expanded=False, parent=self.preparation.body)
        QVBoxLayout(self.deployment.body).addWidget(legacy.mission_mode_group)
        self.preparation.body.layout().addWidget(self.deployment)
        self.recording = self._Section_Add('workflow.task_recording', False)
        self.recording_summary = QLabel(self.recording.body)
        self.recording_summary.setWordWrap(True)
        self.recording.body.layout().addWidget(self.recording_summary)
        self.records_summary = self.recording_summary
        for widget in (legacy.logging_group, legacy.protocol_group, legacy.telemetry_protocol_group):
            self.recording.body.layout().addWidget(widget)
        self.overview = self._Section_Add('workflow.overview', False)
        self.overview.body.layout().addWidget(legacy.mission_profile_panel)
        self.overview_label = QLabel(self.overview.body)
        self.overview_label.setWordWrap(True)
        self.overview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.overview.body.layout().addWidget(self.overview_label)
        self.root_layout.addStretch(1)
        # The workspace is an execution overview. Editors operate on one private
        # property transaction; retained backing views supply no live form here.
        for section in self.sections.values():
            section.hide()
        self.option_buttons = {}
        options = QHBoxLayout()
        for scope in ('algorithms', 'preparation', 'protocols'):
            button = QPushButton(self)
            button.clicked.connect(lambda _checked=False, selected=scope: self._Options_Open(selected))
            self.option_buttons[scope] = button
            options.addWidget(button)
        self.root_layout.insertLayout(self.root_layout.indexOf(self.coverage_group) + 1, options)
        for owner in (legacy, navigation):
            owner.hide()
            owner.setParent(self)
        self.stage_panel.selectionChanged.connect(self._Stage_Changed)
        self.stage_panel.editRequested.connect(self._StageDialog_Open)
        self.stage_panel.stageAddRequested.connect(self._StageAddDialog_Open)
        self.Language_Apply(translator)

    def _Library_Open(self):
        if self._model is None:
            return
        menu = QMenu(self.library_button)
        instances = {row['plugin_id']: row['instance_id'] for row in Functions_Derive(self._model, self._catalog)['functions']}
        for row in FunctionsCatalog_Get(self._catalog):
            plugin = row['plugin_id']
            instance = instances.get(plugin)
            component = self._catalog.Component_Get(plugin)
            if not instance and component.selection is None and plugin not in self._model.ComponentIds_Get():
                continue
            action = menu.addAction(row['name'].get(self._translator.language, plugin))
            if instance:
                action.triggered.connect(lambda _checked=False, identity=instance: self._FunctionDialog_Open(identity))
            else:
                action.triggered.connect(lambda _checked=False, identity=plugin: self.functionAddRequested.emit(identity))
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(self.library_button.mapToGlobal(self.library_button.rect().bottomLeft()))

    def _Options_Open(self, scope):
        from silverstar_fccg.ui.workflow_properties import WorkflowPropertiesDialog
        context = getattr(self, '_display', None)
        if context is None:
            return
        original = self._model.Dictionary_Get()
        dialog = WorkflowPropertiesDialog(self._translator, context, self._catalog, scope, self)
        if dialog.exec() and self._model.Dictionary_Get() == original:
            candidate = dialog.Configuration_Get()
            if candidate.Dictionary_Get() != original:
                self.configurationChanged.emit(candidate)
        dialog.deleteLater()

    def _Process_Validate(self, process):
        if self._model is None:
            return
        candidate = deepcopy(self._model)
        candidate.mission_process = process
        if process and process['execution'] == 'firmware_bounded':
            from silverstar_fccg.project.mission_process import MissionProcessFirmware_Require
            MissionProcessFirmware_Require(candidate, self._catalog)
        before = {(row.code, row.function_id, row.message) for row in Functions_Issues(self._model, self._catalog)}
        issues = [row for row in Functions_Issues(candidate, self._catalog)
                  if not row.code.endswith('REFERENCE_ONLY')
                  and (row.code, row.function_id, row.message) not in before]
        if issues:
            raise ValueError('\n'.join(row.function_id + ': ' + row.message for row in issues))

    def _StageDialog_Open(self, identity):
        if self._model is None: return
        self._Transaction_Open(deepcopy(self._model), identity)

    def _StageAddDialog_Open(self, process, identity):
        if self._model is None:
            return
        snapshot = deepcopy(self._model)
        snapshot.mission_process = process
        self._Transaction_Open(snapshot, identity)

    def _Transaction_Open(self, snapshot, identity):
        from PySide6.QtWidgets import QDialog
        from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
        pending = self.PendingFunctions_Collect()
        drafts = {row['instance_id']: row for row in pending['functions']} if pending else None
        dialog = MissionStageTransactionDialog(self._translator, snapshot, self._catalog, identity, self,
                                               function_drafts=drafts, stage_only=True)
        original = self._model.Dictionary_Get()
        if dialog.exec() == QDialog.DialogCode.Accepted and self._model.Dictionary_Get() == original:
            candidate = dialog.Configuration_Get()
            if candidate.Dictionary_Get() != original:
                self.configurationChanged.emit(candidate)
            if dialog.next_function:
                QTimer.singleShot(0, self, lambda identity=dialog.next_function: self._FunctionDialog_Open(identity))
        dialog.deleteLater()

    def _FunctionDialog_Open(self, identity, proposed=None):
        if self._model is None:
            return
        from PySide6.QtWidgets import QDialog
        from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
        stage = self.stage_panel.selected_stage_id or self.stage_panel._process['stages'][0]['stage_id']
        pending = self.PendingFunctions_Collect()
        drafts = {row['instance_id']: row for row in pending['functions']} if pending else None
        original = self._model.Dictionary_Get()
        dialog = MissionStageTransactionDialog(self._translator, proposed or self._model, self._catalog,
            stage, self, function_drafts=drafts, function_id=identity, display=getattr(self, '_display', None))
        if dialog.exec() == QDialog.DialogCode.Accepted and self._model.Dictionary_Get() == original:
            candidate = dialog.Configuration_Get()
            if candidate.Dictionary_Get() != original:
                self.configurationChanged.emit(candidate)
        dialog.deleteLater()

    def _SelectedFunction_Get(self):
        if self._model is None:
            return None, ''
        row = self.coverage.currentRow()
        identity = self.coverage._functions[row] if 0 <= row < len(self.coverage._functions) else ''
        function = next((item for item in Functions_Derive(self._model, self._catalog)['functions']
                         if item['instance_id'] == identity), None)
        declaration = next((item for item in FunctionsCatalog_Get(self._catalog)
                            if function and item['plugin_id'] == function['plugin_id']), {})
        return function, declaration.get('parameter_owner', '')

    def _FunctionActions_Refresh(self):
        if not hasattr(self, 'function_buttons'):
            return
        function, owner = self._SelectedFunction_Get()
        for key, button in self.function_buttons.items():
            enabled = bool(function)
            if key in ('import', 'export'):
                enabled = bool(owner)
            elif key == 'remove':
                enabled = bool(function and function['category'] == 'estimation' and function['instance_id'] != 'ins')
            button.setEnabled(enabled)

    def _FunctionAction_Run(self, action):
        function, owner = self._SelectedFunction_Get()
        if not function:
            return
        if action == 'parameters':
            self._FunctionDialog_Open(function['instance_id'])
        elif action == 'import' and owner:
            self.parameterImportRequested.emit(owner)
        elif action == 'export' and owner:
            self.parameterExportRequested.emit(owner)
        elif action == 'remove' and function['category'] == 'estimation' and function['instance_id'] != 'ins':
            self.functionRemoveRequested.emit(function['instance_id'])

    def eventFilter(self, watched, event):
        if watched is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self, self._ViewportWidth_Apply)
        return super().eventFilter(watched, event)

    def _ViewportWidth_Apply(self):
        width = self._scroll.viewport().width()
        if width >= 200 and self._scroll.widget().maximumWidth() != width:
            self._scroll.widget().setMaximumWidth(width)

    def _Section_Add(self,key,expanded):
        section=CollapsibleSection(self._translator.Text_Get(key),expanded=expanded)
        QVBoxLayout(section.body);self.root_layout.addWidget(section);self.sections[key]=section
        return section

    def _Functions_Create(self,categories,layout):
        editor=FunctionBindingsEditor(self._translator,categories, self, shared_only=True, catalog_only=True)
        editor.functionsChanged.connect(self.functionsChanged)
        editor.addRequested.connect(self.functionAddRequested)
        editor.removeRequested.connect(self.functionRemoveRequested)
        editor.parametersRequested.connect(self.Parameters_Select)
        editor.importRequested.connect(self.parameterImportRequested)
        editor.exportRequested.connect(self.parameterExportRequested)
        self.function_editors.append(editor);layout.addWidget(editor)
        return editor

    def Configuration_Set(self,model,catalog):
        scroll=self.findChild(QScrollArea)
        position=scroll.verticalScrollBar().value()
        self._model,self._catalog=model,catalog
        references={}
        for function in Functions_Derive(model,catalog)['functions']:
            for key in ('start','stop'):
                if function[key]['kind'] in ('stage_enter','stage_exit'):
                    references.setdefault(function[key]['stage_id'],[]).append(function['instance_id'])
        self.stage_panel.boundary_references=references
        self._refreshing=True
        self.stage_panel.Configuration_Set(model.mission_process,[item.instance_id for item in model.device_instances
            if 'actuator.mission_action.parachute_deploy' in catalog.Component_Get(item.plugin).provides])
        self._refreshing=False
        self._Stage_Changed(self.stage_panel.selected_stage_id)
        self.Parameters_Select(self._selected_parameter_owner,expand=False)
        enabled=sum(row.enabled for row in model.logging_streams)
        storage=', '.join(row.instance_id for row in model.device_instances if catalog.Component_Get(row.plugin).component_class=='storage') or '—'
        summary=self._translator.Text_Get('workflow.recording_summary',storage=storage,count=enabled)
        self.recording_summary.setText(summary);self.records_summary.setText(summary)
        functions=Functions_Derive(model,catalog)
        self.summary_label.setText(self._translator.Text_Get('workflow.summary', stages=len(self.stage_panel._process['stages']), functions=len(functions['functions'])))
        self.coverage.Configuration_Set(functions['functions'], self.stage_panel._process, self._translator, self.stage_panel.StageName_Get)
        if self.coverage.currentRow() < 0 and self.coverage.rowCount():
            self.coverage.setCurrentCell(0, 0)
        self._FunctionActions_Refresh()
        self.overview_label.setText('\n'.join(row['instance_id']+' · '+row['plugin_id']+' · '+
            row['start']['kind']+':'+row['start']['stage_id']+' → '+row['stop']['kind']+':'+row['stop']['stage_id']
            for row in functions['functions']))
        QTimer.singleShot(0,self,lambda:scroll.verticalScrollBar().setValue(position))

    def _Stage_Changed(self,identity):
        if self._refreshing or self._model is None:return
        process=self.stage_panel._process
        for editor in self.function_editors:
            editor.Configuration_Set(self._model,self._catalog,identity,process)
        stage_ids=[row['stage_id'] for row in process['stages']]
        for stage_id,card in self.stage_panel.cards.items():
            parts=[]
            for function in Functions_Derive(self._model,self._catalog)['functions']:
                status=FunctionCoverage_Get(function,stage_ids,process).get(stage_id)
                if status:
                    role_key='workflow.role.'+function['instance_id']
                    role=self._translator.Text_Get(role_key)
                    if role==role_key:role=function['instance_id']
                    marker = '◆' if status == 'once' else '○' if status == 'stop' else '●'
                    parts.append(marker + ' ' + role)
            label=card.findChild(QLabel,'phaseFunctions_'+stage_id)
            label.setText(self._translator.Text_Get('workflow.stage_function_count', count=len(parts))
                          if parts else self._translator.Text_Get('workflow.function.empty_stage'))
            label.setToolTip('\n'.join(parts))
        self.stage_panel._TimelineHeight_Apply()

    def Parameters_Select(self,owner,expand=True):
        self._selected_parameter_owner=owner
        for group in self.navigation._content.findChildren(QGroupBox,options=Qt.FindChildOption.FindDirectChildrenOnly):
            selected=group.objectName() in ('algorithmParameters_'+owner,'sharedAlgorithmParameters')
            group.setVisible(selected)
        if expand and self._model is not None:
            declarations = {row['plugin_id']: row.get('parameter_owner') for row in FunctionsCatalog_Get(self._catalog)}
            match = next((row for row in Functions_Derive(self._model, self._catalog)['functions']
                          if declarations.get(row['plugin_id']) == owner), None)
            if match:
                self.coverage.Function_Select(match['instance_id'])
                self.Reveal(self.function_buttons['parameters'])

    def Pending_Commit(self):
        # Stage changes exist only inside a modal transaction until confirmation.
        return None

    def PendingFunctions_Collect(self):
        if self._model is None:return None
        drafts={}
        for editor in self.function_editors:drafts.update(editor.Drafts_Collect())
        if not drafts:return None
        value=Functions_Derive(self._model,self._catalog)
        value['functions']=[drafts.get(row['instance_id'],row) for row in value['functions']]
        if any(row[key]['kind']=='stage_exit' for row in value['functions'] for key in ('start','stop')):
            value['schema_version']=2
        return value

    def Drafts_Clear(self):
        for editor in self.function_editors:editor.Drafts_Clear()

    def Reveal(self,widget):
        current=widget
        while current is not None and current is not self:
            if isinstance(current,CollapsibleSection):current.toggle_button.setChecked(True)
            current=current.parentWidget()
        scroll=self.findChild(QScrollArea)
        areas=[];current=widget.parentWidget()
        while current is not None:
            if isinstance(current,QScrollArea):areas.append(current)
            current=current.parentWidget()
        def Scroll():
            for area in areas:area.ensureWidgetVisible(widget)
        QTimer.singleShot(0,self,Scroll)
        widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def ExpandedState_Get(self):
        return {**{key:section.Expanded_Is() for key,section in self.sections.items()},
            '__functions':{','.join(editor.categories):editor._expanded for editor in self.function_editors},
            '__conditions':self.stage_panel._condition_expanded,
            '__parameters':self.parameters.Expanded_Is(),
            '__selected_parameter':self._selected_parameter_owner}

    def ExpandedState_Set(self,values):
        if type(values) is dict:
            for key,value in values.items():
                if key in self.sections and type(value) is bool:self.sections[key].toggle_button.setChecked(value)
            functions=values.get('__functions',{})
            if type(functions) is dict:
                for editor in self.function_editors:
                    saved=functions.get(','.join(editor.categories),{})
                    if type(saved) is dict:editor._expanded={key:value for key,value in list(saved.items())[:64] if type(key) is str and type(value) is bool}
            conditions=values.get('__conditions',{})
            if type(conditions) is dict:self.stage_panel._condition_expanded={key:value for key,value in list(conditions.items())[:32] if type(key) is str and type(value) is bool}
            owner=values.get('__selected_parameter','')
            if type(owner) is str:self.Parameters_Select(owner,expand=values.get('__parameters') is True)

    def Language_Apply(self,translator):
        super().Language_Apply(translator)
        self.legacy.Language_Apply(translator);self.navigation.Language_Apply(translator)
        for key,section in self.sections.items():section.Title_Set(translator.Text_Get(key))
        self.deployment.Title_Set(translator.Text_Get('workflow.legacy_actions'))
        self.estimation_definition.Title_Set(translator.Text_Get('workflow.algorithm_selection'))
        self.parameters.Title_Set(translator.Text_Get('workflow.parameters'))
        self.library_button.setText(translator.Text_Get('workflow.open_library'))
        for scope, button in self.option_buttons.items():
            button.setText(translator.Text_Get('workflow.options.' + scope))
        self.coverage_group.setTitle(translator.Text_Get('workflow.execution_map'))
        self.coverage_hint.setText(translator.Text_Get('workflow.execution_map_hint'))
        for key, button in self.function_buttons.items():
            button.setText(translator.Text_Get('workflow.function_properties' if key == 'parameters' else 'workflow.function.' + key))
        self.shared_note.setText(translator.Text_Get('workflow.shared_library_hint'))
        for editor in self.function_editors:editor._translator=translator
        if self._model is not None:self.Configuration_Set(self._model,self._catalog)
