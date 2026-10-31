"""Modal workflow edit. Every child edits a private ProjectModel snapshot."""
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGroupBox, QLabel,
    QVBoxLayout, QScrollArea, QWidget, QCheckBox, QHBoxLayout, QPushButton, QFrame)

from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameterOwners_Get, AlgorithmParameters_Resolve)
from silverstar_fccg.project.mission_functions import Functions_Derive, Functions_Require, Functions_Issues, FunctionCoverage_Get, FunctionsCatalog_Get
from silverstar_fccg.ui.function_bindings import FunctionBindingsEditor
from silverstar_fccg.ui.mission_process_panel import MissionStageEditor, MissionStageName_Get
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage
from silverstar_fccg.ui.widgets import CollapsibleSection, StandardComboBox
from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.project.mission_process import MissionProcess_Default, MissionProcessFirmware_Require


class MissionStageTransactionDialog(QDialog):
    def __init__(self, translator, model, catalog, stage_id, parent=None, *, function_drafts=None,
                 stage_only=False, function_id=None):
        super().__init__(parent)
        self._original = deepcopy(model)
        self._draft = deepcopy(model)
        original_functions = {row['instance_id']: row for row in Functions_Derive(model, catalog)['functions']}
        self._pending_function_drafts = ({identity: deepcopy(row) for identity, row in (function_drafts or {}).items()
                                         if row != original_functions.get(identity)} if stage_only else {})
        if self._draft.mission_process is None:
            self._draft.mission_process = MissionProcess_Default()
        self._initial_process = deepcopy(self._draft.mission_process)
        self._catalog = catalog
        self._result = None
        self._translator = translator
        self._stage_only = stage_only
        self._function_id = function_id
        text = translator.Text_Get
        process = self._draft.mission_process
        index = next(i for i, row in enumerate(process['stages']) if row['stage_id'] == stage_id)
        display_name = MissionStageName_Get(process['stages'][index], translator)
        self.setWindowTitle(text('process.detail') + ' · ' + display_name)
        if function_id:
            self.setWindowTitle(text('workflow.function_properties') + ' · ' + function_id)
        self.setObjectName("missionStageTransaction")
        self.setSizeGripEnabled(True)
        self.resize(1020, 780)
        self.setMinimumSize(640, 460)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        heading = QLabel(f"{index + 1:02d} / {len(process['stages']):02d}   " + display_name, self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName('workflowDialogTitle')
        heading.setWordWrap(True)
        root.addWidget(heading)
        note = QLabel(text('workflow.transaction.hint'), self)
        if stage_only:
            note.setText(text('workflow.stage_only_hint'))
        note.setObjectName('muted')
        note.setWordWrap(True)
        root.addWidget(note)
        jump = QHBoxLayout()
        root.addLayout(jump)
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        TouchScroll_Enable(scroll)
        self.scroll = scroll
        content = QWidget(scroll); layout = QVBoxLayout(content)
        scroll.setWidget(content); root.addWidget(scroll)
        targets = [row.instance_id for row in model.device_instances
                   if 'actuator.mission_action.parachute_deploy' in catalog.Component_Get(row.plugin).provides]
        self.stage_editor = MissionStageEditor(translator, process, index, targets, content, split_actions=True)
        # One transaction owns the only pair of Apply/Cancel buttons.
        for buttons in self.stage_editor.findChildren(QDialogButtonBox): buttons.hide()
        basic = QGroupBox(text('workflow.group.condition'), content)
        QVBoxLayout(basic).addWidget(self.stage_editor); layout.addWidget(basic)
        self.groups = {'condition': basic}
        basic.setVisible(function_id is None)
        self.bindings = []
        all_functions = Functions_Derive(self._draft, catalog)['functions']
        selected_function = next((row for row in all_functions if row['instance_id'] == function_id), None)
        if function_id and selected_function is None:
            raise ValueError('FUNCTION_UNKNOWN: ' + function_id)
        if function_id:
            heading.setText(text('workflow.function_properties') + ' · ' + function_id)
        for key, categories in (('estimation', ('estimation', 'preparation')),
                                ('control', ('control',)), ('records', ('recording', 'telemetry'))):
            if stage_only or (selected_function and selected_function['category'] not in categories):
                continue
            group = CollapsibleSection(text('workflow.group.' + key), expanded=True, parent=content)
            group_body = QVBoxLayout(group.body)
            if key == 'control' and not function_id:
                group_body.addWidget(self.stage_editor.actions_widget)
            self.groups[key] = group
            editor = FunctionBindingsEditor(translator, categories, group, transactional=True,
                                             instance_ids=(function_id,) if function_id else None)
            owned = {row['instance_id'] for row in Functions_Derive(self._draft, catalog)['functions']
                     if row['category'] in categories}
            editor._range_drafts = {identity: deepcopy(value) for identity, value in (function_drafts or {}).items()
                                    if identity in owned}
            editor.Configuration_Set(self._draft, catalog, stage_id, process)
            editor.functionsChanged.connect(self._Functions_Set)
            # Adding/removing a plugin requires the canonical project selector;
            # this dialog edits references to the existing shared instances.
            editor.add_combo.parentWidget().hide()
            for button in editor.findChildren(QDialogButtonBox): button.hide()
            group_body.addWidget(editor); layout.addWidget(group)
            self.bindings.append(editor)
        for key, group in self.groups.items():
            button = QPushButton(text('workflow.group.' + key), self)
            button.clicked.connect(lambda _checked=False, selected=group: self._Group_Reveal(selected))
            jump.addWidget(button)
        self.parameters = NavigationConfigurationPage(translator)
        self.parameters.setParent(self)
        self.parameters.hide()
        declarations = {row['plugin_id']: row for row in FunctionsCatalog_Get(catalog)}
        parameter_owner = declarations.get(selected_function['plugin_id'], {}).get('parameter_owner') if selected_function else None
        owners = tuple(owner for owner in AlgorithmParameterOwners_Get(self._draft, catalog)
                       if not stage_only and (not function_id or owner.component_id == parameter_owner))
        self.parameters.Configuration_Set(owners,
                                          self._draft.algorithm_parameters)
        self._initial_editor_values = {key: (editor.CommittedValue_Get() if hasattr(editor, 'CommittedValue_Get')
                                           else editor.value()) for key, editor in self.parameters.editors.items()}
        self.parameters.parameterChanged.connect(self._Parameter_Set)
        self.parameters.sharedParameterChanged.connect(self._SharedParameter_Set)
        self.parameters.defaultsRequested.connect(self._Defaults_Set)
        self.parameters.sharedDefaultsRequested.connect(lambda key: self._SharedParameter_Set(key, None))
        section = CollapsibleSection(text('workflow.parameters'), expanded=False, parent=content)
        self.parameter_section = section
        body = QVBoxLayout(section.body)
        self.parameter_owner = StandardComboBox(section.body)
        for owner in owners:
            self.parameter_owner.addItem(owner.DisplayName_Get(translator.language), owner.component_id)
        body.addWidget(self.parameter_owner)
        self.parameter_impact = QLabel(section.body)
        self.parameter_impact.setWordWrap(True)
        self.parameter_impact.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self.parameter_impact)
        self.parameter_owner.currentIndexChanged.connect(lambda: self._Parameters_Filter())
        body.addWidget(self.parameters._content)
        self.parameters.setParent(self); self.parameters.hide()
        layout.addWidget(section)
        section.setVisible(bool(owners))
        for editor in self.bindings:
            editor.parametersRequested.connect(self._Parameters_Reveal)
        records = CollapsibleSection(text('workflow.recording_settings'), expanded=False, parent=content)
        records_layout = QVBoxLayout(records.body)
        record_note = QLabel(text('workflow.transaction.shared'), records.body)
        record_note.setWordWrap(True)
        records_layout.addWidget(record_note)
        self.record_checks = []
        record_streams = (self._draft.logging_streams if not stage_only and
                          (not function_id or selected_function['category'] == 'recording') else ())
        for stream in record_streams:
            check = QCheckBox(stream.record, records); check.setChecked(stream.enabled)
            records_layout.addWidget(check); self.record_checks.append(check)
        if 'records' in self.groups:
            self.groups['records'].body.layout().addWidget(records)
        else:
            records.hide()
        if stage_only:
            references = QGroupBox(text('workflow.stage_references'), content)
            references_body = QVBoxLayout(references)
            stage_ids = [row['stage_id'] for row in process['stages']]
            for function in all_functions:
                if stage_id not in FunctionCoverage_Get(function, stage_ids, process):
                    continue
                name = declarations.get(function['plugin_id'], {}).get('name', {}).get(translator.language, function['instance_id'])
                button = QPushButton(name, references)
                button.clicked.connect(lambda _checked=False, identity=function['instance_id']:
                                       self._FunctionDialog_Open(identity, stage_id))
                references_body.addWidget(button)
            layout.addWidget(references)
        self._Parameters_Filter()
        self.error = QLabel(self); self.error.setWordWrap(True); self.error.setObjectName("workflowError"); root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('workflow.transaction.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName('primaryButton')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _FunctionDialog_Open(self, identity, stage_id):
        dialog = MissionStageTransactionDialog(self._translator, self._draft, self._catalog,
            stage_id, self, function_id=identity, function_drafts=self._pending_function_drafts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._draft = dialog.Configuration_Get()
            self._pending_function_drafts.pop(identity, None)
        dialog.deleteLater()

    def _Group_Reveal(self, group):
        if isinstance(group, CollapsibleSection):
            group.toggle_button.setChecked(True)
        self.scroll.ensureWidgetVisible(group, 8, 12)

    def _Parameters_Reveal(self, owner):
        self.parameter_owner.setCurrentIndex(self.parameter_owner.findData(owner))
        self._Parameters_Filter()
        self._Group_Reveal(self.parameter_section)

    def _Parameters_Filter(self):
        owner = self.parameter_owner.currentData()
        for group in self.parameters._content.findChildren(QGroupBox, options=Qt.FindChildOption.FindDirectChildrenOnly):
            group.setVisible(group.objectName() in ('algorithmParameters_' + str(owner), 'sharedAlgorithmParameters'))
        declarations = {row['plugin_id']: row for row in FunctionsCatalog_Get(self._catalog)}
        stages = self._draft.mission_process['stages']
        stage_ids = [row['stage_id'] for row in stages]
        affected = set()
        for function in Functions_Derive(self._draft, self._catalog)['functions']:
            if declarations.get(function['plugin_id'], {}).get('parameter_owner') == owner:
                affected.update(FunctionCoverage_Get(function, stage_ids, self._draft.mission_process))
        names = [MissionStageName_Get(row, self._translator) for row in stages if row['stage_id'] in affected]
        self.parameter_impact.setText(self._translator.Text_Get('workflow.transaction.affected',
            stages=' / '.join(names) or self._translator.Text_Get('workflow.lifecycle_scope')))

    def _Functions_Set(self, value):
        self._draft.mission_functions = Functions_Require(value)
        # Keep every category editor on the same private shared-instance set.
        for editor in self.bindings: editor._configuration = deepcopy(value)

    def _Parameter_Set(self, component, parameter, value):
        self._draft.algorithm_parameters[component][parameter] = value
        editor = self.parameters.editors.get((component, parameter))
        if editor is not None: editor.CommittedValue_Set(value)

    def _SharedParameter_Set(self, key, value):
        for owner in AlgorithmParameterOwners_Get(self._draft, self._catalog):
            for parameter in owner.algorithm_parameters:
                if parameter.shared_key == key:
                    self._Parameter_Set(owner.component_id, parameter.parameter_id,
                                        parameter.default if value is None else value)
        editor = self.parameters.editors.get(('shared', key))
        if editor is not None:
            for owner in AlgorithmParameterOwners_Get(self._draft, self._catalog):
                matching = next((p for p in owner.algorithm_parameters if p.shared_key == key), None)
                if matching is not None:
                    editor.CommittedValue_Set(self._draft.algorithm_parameters[owner.component_id][matching.parameter_id])
                    break

    def _Defaults_Set(self, component):
        for parameter in self._catalog.Component_Get(component).algorithm_parameters:
            if not parameter.shared_key and parameter.lifecycle == 'active':
                self._Parameter_Set(component, parameter.parameter_id, parameter.default)

    def _ValidationError_Show(self, error):
        detail = str(error)
        code, _, remaining = detail.partition(':')
        identity = remaining.partition(':')[0].strip()
        key = ('dependency_interval' if code == 'FUNCTION_INPUT_INTERVAL' else
               'dependency' if code.startswith('FUNCTION_DEPENDENCY') else
               'source' if code.startswith('FUNCTION_INPUT') else 'general')
        self.error.setText(self._translator.Text_Get('workflow.validation.' + key) + '\n' + detail)
        for editor in self.bindings:
            section = editor._sections.get(identity + '.range')
            if section is None:
                continue
            parent = section
            while parent is not None and parent is not self:
                if isinstance(parent, CollapsibleSection):
                    parent.toggle_button.setChecked(True)
                parent = parent.parentWidget()
            self.scroll.ensureWidgetVisible(section, 8, 12)
            first = section.body.layout().itemAt(0, section.body.layout().ItemRole.FieldRole)
            if first is not None and first.widget() is not None:
                first.widget().setFocus(Qt.FocusReason.OtherFocusReason)
            break

    def accept(self):
        process = self.stage_editor.Process_Collect()
        if process is None: return
        candidate = deepcopy(self._draft)
        # Collect committed widget values synchronously; queued UI refresh
        # signals cannot race the final transaction copy.
        for (component, parameter), editor in self.parameters.editors.items():
            value = editor.CommittedValue_Get() if hasattr(editor, 'CommittedValue_Get') else editor.value()
            if value == self._initial_editor_values[(component, parameter)]: continue
            if component == 'shared':
                for owner in AlgorithmParameterOwners_Get(candidate, self._catalog):
                    for definition in owner.algorithm_parameters:
                        if definition.shared_key == parameter:
                            candidate.algorithm_parameters[owner.component_id][definition.parameter_id] = int(value) if definition.value_type=='integer' else value
            else:
                definition = next(row for row in self._catalog.Component_Get(component).algorithm_parameters
                                  if row.parameter_id == parameter)
                candidate.algorithm_parameters[component][parameter] = int(value) if definition.value_type=='integer' else value
        functions = Functions_Derive(candidate, self._catalog)
        drafts = deepcopy(self._pending_function_drafts)
        for editor in self.bindings: drafts.update(editor.Drafts_Collect())
        functions['functions'] = [drafts.get(row['instance_id'], row) for row in functions['functions']]
        if any(row[key]['kind']=='stage_exit' for row in functions['functions'] for key in ('start','stop')):
            functions['schema_version'] = 2
        try:
            candidate.mission_process = process
            from silverstar_fccg.project.mission_functions import FunctionsConfiguration_Apply
            candidate = FunctionsConfiguration_Apply(candidate, self._catalog, functions)
            if process['execution'] == 'firmware_bounded':
                MissionProcessFirmware_Require(candidate, self._catalog)
            AlgorithmParameters_Resolve(candidate, self._catalog)
        except (ValueError, TypeError) as error:
            self._ValidationError_Show(error); return
        candidate.mission_process = process
        baseline = {(row.code, row.function_id, row.message) for row in Functions_Issues(self._original, self._catalog)}
        issues = [row for row in Functions_Issues(candidate, self._catalog)
                  if not row.code.endswith('REFERENCE_ONLY')
                  and (row.code, row.function_id, row.message) not in baseline]
        if issues:
            self.error.setText('\n'.join(row.function_id + ': ' + row.message for row in issues))
            return
        if self._original.mission_process is None and process == self._initial_process:
            candidate.mission_process = None
        if self._original.mission_functions is None and candidate.mission_functions == Functions_Derive(self._original, self._catalog):
            candidate.mission_functions = None
        if self.record_checks:
            candidate.logging_streams = [replace(row, enabled=check.isChecked())
                                        for row, check in zip(candidate.logging_streams, self.record_checks)]
        self._result = candidate
        super().accept()

    def Configuration_Get(self):
        return deepcopy(self._result)
