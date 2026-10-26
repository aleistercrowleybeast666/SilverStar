"""Modal workflow edit. Every child edits a private ProjectModel snapshot."""
from copy import deepcopy
from dataclasses import replace

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGroupBox, QLabel,
    QVBoxLayout, QScrollArea, QWidget, QCheckBox)

from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameterOwners_Get, AlgorithmParameters_Resolve)
from silverstar_fccg.project.mission_functions import Functions_Derive, Functions_Require
from silverstar_fccg.ui.function_bindings import FunctionBindingsEditor
from silverstar_fccg.ui.mission_process_panel import MissionStageEditor
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage
from silverstar_fccg.ui.widgets import CollapsibleSection


class MissionStageTransactionDialog(QDialog):
    def __init__(self, translator, model, catalog, stage_id, parent=None):
        super().__init__(parent)
        self._draft = deepcopy(model)
        self._catalog = catalog
        self._result = None
        self._translator = translator
        text = translator.Text_Get
        process = self._draft.mission_process
        index = next(i for i, row in enumerate(process['stages']) if row['stage_id'] == stage_id)
        self.setWindowTitle(text('process.detail') + ' · ' + process['stages'][index]['name'])
        self.resize(960, 760)
        self.setMinimumSize(640, 460)
        root = QVBoxLayout(self)
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        content = QWidget(scroll); layout = QVBoxLayout(content)
        scroll.setWidget(content); root.addWidget(scroll)
        targets = [row.instance_id for row in model.device_instances
                   if 'actuator.mission_action.parachute_deploy' in catalog.Component_Get(row.plugin).provides]
        self.stage_editor = MissionStageEditor(translator, process, index, targets, content)
        # One transaction owns the only pair of Apply/Cancel buttons.
        for buttons in self.stage_editor.findChildren(QDialogButtonBox): buttons.hide()
        basic = QGroupBox(text('workflow.group.condition'), content)
        QVBoxLayout(basic).addWidget(self.stage_editor); layout.addWidget(basic)
        self.bindings = []
        for key, categories in (('estimation', ('estimation', 'preparation')),
                                ('control', ('control',)), ('records', ('recording', 'telemetry'))):
            group = QGroupBox(text('workflow.group.' + key), content)
            editor = FunctionBindingsEditor(translator, categories, group, transactional=True)
            editor.Configuration_Set(self._draft, catalog, stage_id, process)
            editor.functionsChanged.connect(self._Functions_Set)
            # Adding/removing a plugin requires the canonical project selector;
            # this dialog edits references to the existing shared instances.
            editor.add_combo.parentWidget().hide()
            for button in editor.findChildren(QDialogButtonBox): button.hide()
            QVBoxLayout(group).addWidget(editor); layout.addWidget(group)
            self.bindings.append(editor)
        self.parameters = NavigationConfigurationPage(translator)
        self.parameters.Configuration_Set(AlgorithmParameterOwners_Get(self._draft, catalog),
                                          self._draft.algorithm_parameters)
        self._initial_editor_values = {key: (editor.CommittedValue_Get() if hasattr(editor, 'CommittedValue_Get')
                                           else editor.value()) for key, editor in self.parameters.editors.items()}
        self.parameters.parameterChanged.connect(self._Parameter_Set)
        self.parameters.sharedParameterChanged.connect(self._SharedParameter_Set)
        self.parameters.defaultsRequested.connect(self._Defaults_Set)
        self.parameters.sharedDefaultsRequested.connect(lambda key: self._SharedParameter_Set(key, None))
        section = CollapsibleSection(text('workflow.parameters'), expanded=False)
        body = QVBoxLayout(section.body)
        note = QLabel(text('workflow.transaction.shared')); note.setWordWrap(True); body.addWidget(note)
        body.addWidget(self.parameters._content)
        self.parameters.setParent(self); self.parameters.hide()
        layout.addWidget(section)
        for editor in self.bindings:
            editor.parametersRequested.connect(lambda _owner: section.toggle_button.setChecked(True))
        records = QGroupBox(text('workflow.recording_settings'), content)
        records_layout = QVBoxLayout(records); self.record_checks = []
        for stream in self._draft.logging_streams:
            check = QCheckBox(stream.record, records); check.setChecked(stream.enabled)
            records_layout.addWidget(check); self.record_checks.append(check)
        layout.addWidget(records)
        self.error = QLabel(self); self.error.setWordWrap(True); root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

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
        drafts = {}
        for editor in self.bindings: drafts.update(editor.Drafts_Collect())
        functions['functions'] = [drafts.get(row['instance_id'], row) for row in functions['functions']]
        if any(row[key]['kind']=='stage_exit' for row in functions['functions'] for key in ('start','stop')):
            functions['schema_version'] = 2
        try:
            candidate.mission_functions = Functions_Require(functions)
            AlgorithmParameters_Resolve(candidate, self._catalog)
        except (ValueError, TypeError) as error:
            self.error.setText(str(error)); return
        candidate.mission_process = process
        candidate.logging_streams = [replace(row, enabled=check.isChecked())
                                    for row, check in zip(candidate.logging_streams, self.record_checks)]
        self._result = candidate
        super().accept()

    def Configuration_Get(self):
        return deepcopy(self._result)
