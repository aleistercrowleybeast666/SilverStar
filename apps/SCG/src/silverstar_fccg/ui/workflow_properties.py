"""Private editors for project choices shared by the mission function instances."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from silverstar_fccg.project.model import ProtocolSelection
from silverstar_fccg.ui.committed_spin import NumericDrafts_Collect
from silverstar_fccg.ui.pages.components import FlightConfigurationPage
from silverstar_fccg.ui.pages.navigation_alignment import AlignmentConfigurationEditor


class WorkflowPropertiesDialog(QDialog):
    def __init__(self, translator, display, catalog, section, parent=None):
        super().__init__(parent)
        self.setProperty('collectNumericDrafts', True)
        self._draft = deepcopy(display.model)
        self._original = deepcopy(display.model)
        self._catalog = catalog
        self._translator = translator
        self.setObjectName('workflowProperties_' + section)
        self.setWindowTitle(translator.Text_Get('workflow.options.' + section))
        self.resize(820, 650)
        layout = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        body = QVBoxLayout(content)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.editor = FlightConfigurationPage(translator)
        self.editor.setParent(self)
        self.editor.hide()
        model = self._draft
        self.editor.Configuration_Set(display.selectable_components, model.strategies, model.modes,
            mode_parameters=model.mode_parameters, strategy_availability=display.strategy_availability,
            mode_availability=display.mode_availability)
        self.editor.Capabilities_Set(display.capability_usage)
        self.editor.Protocols_Set(display.protocol_profiles, display.selected_protocol_profiles)
        self.alignment = None
        if section == 'algorithms':
            widgets = (self.editor.ins_strategy_group, self.editor.estimator_strategy_group)
        elif section == 'preparation':
            widgets = (self.editor.strategy_group, self.editor.mode_group, self.editor.mission_strategy_group,
                       self.editor.mission_mode_group, self.editor.capability_group)
            self.alignment = AlignmentConfigurationEditor(translator)
            self.alignment.Configuration_Set(model.alignment, model.strategies.get('alignment'), tuple(model.device_instances))
            self.alignment.confirm_button.hide()
            self.alignment.cancel_button.hide()
            self.alignment.configurationConfirmed.connect(self._Alignment_Collect)
            self.editor.strategy_group.layout().addWidget(self.alignment)
        elif section == 'protocols':
            widgets = (self.editor.protocol_group,)
        else:
            raise ValueError('Unknown workflow properties')
        for widget in widgets:
            body.addWidget(widget)
            widget.show()
        self.editor.strategyChanged.connect(self._Strategy_Set)
        self.editor.modeChanged.connect(lambda slot, values: model.modes.__setitem__(slot, list(values)))
        self.editor.modeParameterChanged.connect(lambda slot, option, key, value:
            model.mode_parameters.setdefault(slot, {}).setdefault(option, {}).__setitem__(key, value))
        def source_set(capability, value):
            choice = next((row for row in display.capability_usage if row.capability == capability), None)
            if value and (choice is None or not choice.providers or value != choice.providers[0][0]):
                model.capability_source_overrides[capability] = value
            else:
                model.capability_source_overrides.pop(capability, None)
        self.editor.capabilitySourceChanged.connect(source_set)
        def protocol_set(category, choice):
            if choice is None:
                model.protocols[category] = None
            else:
                component, profile = choice
                manifest = catalog.Component_Get(component)
                model.protocols[category] = ProtocolSelection(component, manifest.version, profile, manifest.ManifestSha256_Get())
        self.editor.protocolProfileChanged.connect(protocol_set)
        self.error = QLabel(self)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(translator.Text_Get('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(translator.Text_Get('capsule.cancel'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _Strategy_Set(self, slot, value):
        self._draft.strategies[slot] = value or None
        if slot == 'alignment' and self.alignment:
            self.alignment.DraftStrategy_Set(value or '')

    def _Alignment_Collect(self, strategy, configuration):
        self._draft.strategies['alignment'] = strategy or None
        self._draft.alignment = configuration
        self._alignment_valid = True

    def accept(self):
        if not NumericDrafts_Collect(self, self.error, self._translator.Text_Get('editor.invalid_number')):
            return
        if self.alignment and self.alignment.draft_dirty:
            self._alignment_valid = False
            self.alignment._Draft_Confirm()
            if not self._alignment_valid:
                self.error.setText(self.alignment._notice.text())
                return
        try:
            from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
            from silverstar_fccg.project.mission_functions import FunctionsStrategies_Synchronize, Functions_Issues
            candidate = ProjectConfiguration_Reconcile(self._draft, self._catalog).model
            candidate = FunctionsStrategies_Synchronize(self._original, candidate, self._catalog)
            before = {(item.code, item.function_id, item.message) for item in Functions_Issues(self._original, self._catalog)}
            introduced = [item for item in Functions_Issues(candidate, self._catalog)
                          if (item.code, item.function_id, item.message) not in before]
            if introduced:
                raise ValueError('\n'.join(item.function_id + ' · ' + item.message for item in introduced))
            self._draft = candidate
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        super().accept()

    def Configuration_Get(self):
        return deepcopy(self._draft) if self.result() == QDialog.DialogCode.Accepted else None
