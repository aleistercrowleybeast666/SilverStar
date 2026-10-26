"""One workflow workspace. Legacy editors are mounted once, never copied."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QMessageBox)

from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionCoverage_Get, Functions_Issues
from silverstar_fccg.ui.function_bindings import FunctionBindingsEditor
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
        super().__init__(translator,'workspace.workflow.title','workspace.workflow.description')
        self.legacy, self.navigation = legacy, navigation
        self._model = None
        self._selected_parameter_owner = ''
        self._refreshing = False
        self._scroll = self.findChild(QScrollArea)
        self._scroll.viewport().installEventFilter(self)
        self.sections = {}
        self.function_editors = []
        self.stage_panel = legacy.mission_process_panel
        self.root_layout.addWidget(legacy.mission_profile_panel)
        self.root_layout.addWidget(self.stage_panel)
        self.preparation = self._Section_Add('workflow.preparation', False)
        self.preparation_functions = self._Functions_Create(('preparation',),self.preparation.body.layout())
        navigation.ExistingEditors_Attach(sources=legacy.capability_group,calibration=legacy.mode_group,
            alignment=legacy.strategy_group,ins=legacy.ins_strategy_group,estimator=legacy.estimator_strategy_group)
        for widget in (legacy.mission_strategy_group,navigation.sources_section,
                       navigation.calibration_section,navigation.alignment_section,navigation.impact_section):
            self.preparation.body.layout().addWidget(widget)
        self.estimation_functions = self._Functions_Create(('estimation',),self.stage_panel.detail_bodies['estimation'])
        self.control_functions = self._Functions_Create(('control',),self.stage_panel.detail_bodies['control'])
        # The existing deployment rule editor remains the real legacy consumer.
        self.deployment = CollapsibleSection(translator.Text_Get('workflow.legacy_actions'),expanded=False)
        QVBoxLayout(self.deployment.body).addWidget(legacy.mission_mode_group)
        self.stage_panel.detail_bodies['control'].addWidget(self.deployment)
        self.estimation_definition = CollapsibleSection(translator.Text_Get('workflow.algorithm_selection'),expanded=False)
        definition = QVBoxLayout(self.estimation_definition.body)
        definition.addWidget(navigation.ins_section);definition.addWidget(navigation.estimator_section)
        self.stage_panel.detail_bodies['estimation'].addWidget(self.estimation_definition)
        self.parameters = CollapsibleSection(translator.Text_Get('workflow.parameters'),expanded=False)
        QVBoxLayout(self.parameters.body).addWidget(navigation.parameters_section)
        self.stage_panel.detail_bodies['estimation'].addWidget(self.parameters)
        self.records_summary = QLabel();self.records_summary.setWordWrap(True)
        self.stage_panel.detail_bodies['records'].addWidget(self.records_summary)
        self.recording_functions = self._Functions_Create(('recording','telemetry'),self.stage_panel.detail_bodies['records'])
        self.records_button = QPushButton()
        self.records_button.clicked.connect(lambda:self.Reveal(legacy.logging_table))
        self.stage_panel.detail_bodies['records'].addWidget(self.records_button)
        self.recording = self._Section_Add('workflow.task_recording',False)
        self.recording_summary = QLabel();self.recording_summary.setWordWrap(True)
        self.root_layout.insertWidget(self.root_layout.indexOf(self.recording),self.recording_summary)
        for widget in (legacy.logging_group,legacy.protocol_group,legacy.telemetry_protocol_group):
            self.recording.body.layout().addWidget(widget)
        self.overview = self._Section_Add('workflow.overview',False)
        self.overview_label = QLabel();self.overview_label.setWordWrap(True)
        self.overview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.overview.body.layout().addWidget(self.overview_label)
        self.root_layout.addStretch(1)
        for owner in (legacy,navigation):
            owner.hide();owner.setParent(self)
        self.stage_panel.selectionChanged.connect(self._Stage_Changed)
        self.stage_panel.editRequested.connect(self._StageDialog_Open)
        self.Language_Apply(translator)

    def _StageDialog_Open(self, identity):
        if self._model is None or self._model.mission_process is None: return
        from PySide6.QtWidgets import QDialog
        from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
        snapshot = deepcopy(self._model)
        snapshot.mission_process = deepcopy(self.stage_panel._process)
        functions = self.PendingFunctions_Collect()
        if functions is not None: snapshot.mission_functions = functions
        dialog = MissionStageTransactionDialog(self._translator, snapshot, self._catalog, identity, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.configurationChanged.emit(dialog.Configuration_Get())
        dialog.deleteLater()

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
        editor=FunctionBindingsEditor(self._translator,categories)
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
        issues=Functions_Issues(self._model,self._catalog)
        for stage_id,card in self.stage_panel.cards.items():
            parts=[]
            for function in Functions_Derive(self._model,self._catalog)['functions']:
                status=FunctionCoverage_Get(function,stage_ids).get(stage_id)
                if status:
                    role_key='workflow.role.'+function['instance_id']
                    role=self._translator.Text_Get(role_key)
                    if role==role_key:role=function['instance_id']
                    parts.append(self._translator.Text_Get('workflow.coverage.'+status)+': '+role)
            label=card.findChild(QLabel,'phaseFunctions_'+stage_id)
            warnings=[self._translator.Text_Get('workflow.needs_repair',id=issue.function_id,code=issue.code) for issue in issues[:3]]
            label.setText('\n'.join(parts+warnings) or self._translator.Text_Get('workflow.function.empty_stage'))

    def Parameters_Select(self,owner,expand=True):
        self._selected_parameter_owner=owner
        for group in self.navigation._content.findChildren(QGroupBox,options=Qt.FindChildOption.FindDirectChildrenOnly):
            selected=group.objectName() in ('algorithmParameters_'+owner,'sharedAlgorithmParameters')
            group.setVisible(selected)
        if expand:
            self.parameters.toggle_button.setChecked(True)
            self.Reveal(self.parameters)

    def Pending_Commit(self):
        """Return the pending inline condition snapshot without mutating a model."""
        editor=self.stage_panel.condition_editor
        if editor is None or self.stage_panel._derived:return None
        if not editor._dirty:return None
        candidate=editor.Process_Collect()
        if candidate is None:
            raise ValueError(editor.error.text() or self._translator.Text_Get('capsule.invalid'))
        return candidate if candidate!=self.stage_panel._process else None

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
        self.records_button.setText(translator.Text_Get('workflow.recording_settings'))
        for editor in self.function_editors:editor._translator=translator
        if self._model is not None:self.Configuration_Set(self._model,self._catalog)
