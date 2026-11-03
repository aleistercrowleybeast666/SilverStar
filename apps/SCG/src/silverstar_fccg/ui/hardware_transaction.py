"""Object-scoped hardware options with an isolated in-memory editing controller."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QPushButton,
    QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from silverstar_fccg.core.view_models import ComponentType
from silverstar_fccg.project.retired_cdc import NativeCdcHardware_Is, NativeCdcMigration_Required
from silverstar_fccg.ui.committed_spin import NumericDrafts_Collect
from silverstar_fccg.ui.widgets import CollapsibleSection
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
from silverstar_fccg.project.mission_functions import FunctionsStrategies_Synchronize
from silverstar_fccg.project.radio_variants import FlightRadioConfiguration_Get, RADIO_PLUGIN
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.ui.hardware_editing import HardwareEditingActions
from silverstar_fccg.ui.pages.components import BoardHardwarePage, DevicesPage
from silverstar_fccg.ui.pages.targets import AirLinkPage, GroundTargetPage


class HardwareDraftController(HardwareEditingActions, QObject):
    """Reuse domain actions, without a main window, settings or filesystem slots."""
    def __init__(self, model, service, translator, parent):
        super().__init__(parent)
        self._model = deepcopy(model)
        self._service, self._translator = service, translator
        self._project_root = None
        self._displaying_model = False
        self._closed = False
        self._collecting = False
        self._migration = getattr(parent, 'target', None) == 'ground' and NativeCdcMigration_Required(model)
        self._collect_error = None
        self._explicit_uart = False
        self._explicit_resource = ''
        self._logging_transport_choice = None
        self._logging_transport_streams = None
        self._selection_restore_project = None
        self._component_views = service.ComponentViews_Get(translator.language)
        self.status_label = QLabel(parent)
        self.status_label.setWordWrap(True)
        self.devices_page = DevicesPage(translator)
        self.board_hardware_page = BoardHardwarePage(translator)
        self.ground_target_page = GroundTargetPage(translator)
        self.air_link_page = AirLinkPage(translator)
        # These legacy sub-editors are separately mountable. Give even the
        # inactive target's editor an owner before Configuration_Set may show it.
        # Otherwise a Ground dialog can leave a parentless Flight power window
        # alive after Cancel, preventing QApplication from quitting.
        self.devices_page.radio_power_editor.setParent(self.devices_page)
        self.ground_target_page.radio_instances_editor.power_editor.setParent(self.ground_target_page)
        for page in (self.devices_page, self.board_hardware_page,
                     self.ground_target_page, self.air_link_page):
            page.setParent(parent)
            page.hide()
            page.Language_Apply(translator)
        bindings = {
            self.devices_page: {
                'instanceChanged': '_DeviceInstance_Change',
                'variantChanged': '_DeviceVariant_Change',
                'radioSelectionChanged': '_FlightRadioSelection_Change',
                'radioPowerChanged': '_FlightRadioPower_Change',
                'installationOrientationChanged': '_Jy901bOrientation_Change',
                'mountNoseAxisChanged': '_RawImuMount_Change',
                'mountXAxisChanged': '_RawImuXAxis_Change',
                'installationReferenceAdoptRequested': '_InstallationReference_Adopt',
                'sensorPositionChanged': '_SensorPosition_Change',
                'instanceAddRequested': '_DeviceInstance_Add',
                'otherDeviceToggled': '_OtherDevice_Toggle',
                'featureTierChanged': '_FeatureTier_Change',
                'optionalResourceChanged': '_OptionalResource_Change',
            },
            self.board_hardware_page: {
                'boardChanged': '_BoardSelection_Change',
                'customSelected': '_CustomHardware_Select',
                'autoAssignRequested': '_Resources_AutoAssign',
                'assignmentChanged': '_ResourceAssignment_Change',
                'manualValidationRequested': '_HardwareAssignments_Validate',
                'i2cExternalPullupChanged': '_I2cExternalPullup_Change',
            },
            self.ground_target_page: {
                'configurationChanged': '_GroundTarget_Change',
                'activityLedToggled': '_GroundActivityLed_Toggle',
                'assignmentChanged': '_GroundAssignment_Change',
                'radiosChanged': '_GroundRadios_Change',
            },
        }
        for page, signals in bindings.items():
            for signal, method in signals.items():
                getattr(page, signal).connect(getattr(self, method))
        self._Project_Refresh()

    def _Error_Show(self, error, technical_detail=''):
        self.status_label.setText(str(error) + ('\n' + technical_detail if technical_detail else ''))

    def _ProjectConfiguration_Change(self, mutator, *, logging_availability_changed=False, **_kwargs):
        if self._displaying_model or self._closed:
            return None
        candidate = deepcopy(self._model)
        try:
            mutator(candidate)
            result = self._service.ProjectConfiguration_Reconcile(candidate)
            if logging_availability_changed:
                LoggingProfile_AvailabilityTransitionApply(self._model, result.model, self._service.catalog)
            candidate = FunctionsStrategies_Synchronize(self._model, result.model, self._service.catalog)
            result = self._service.ProjectConfiguration_Reconcile(candidate)
        except Exception as error:
            self._Error_Show(error)
            if self._collecting:
                self._collect_error = error
            return None
        self._model = result.model
        if self._migration:
            self._model.ground_target = replace(self._model.ground_target,
                pc_interface='uart' if self._explicit_uart else 'usb_cdc', pc_resource=self._explicit_resource)
        self._Project_Refresh()
        return result

    def _Project_Refresh(self):
        if self._collecting:
            return
        self._displaying_model = True
        try:
            model, service = self._model, self._service
            devices = self.devices_page
            devices.FeatureTier_Set(model.build.feature_tier)
            devices.OptionalResources_Set(model.build)
            devices.InstallationReference_Set(model.sensor_installation)
            devices.Configuration_Set(
                tuple(item for item in self._component_views if item.component_type == ComponentType.DEVICE),
                service.DeviceInstanceViews_Get(model, self._translator.language),
                service.DeviceSelectionAvailabilities_Get(model),
                {item.component_id: item.radio.modules for item in service.catalog.Type_Get('device') if item.radio},
                {item.instance_id: FlightRadioConfiguration_Get(model, item)
                 for item in model.device_instances if item.plugin in (RADIO_PLUGIN, 'silverstar.device.telemetry.sx1278')})
            self._BoardPage_Refresh(SimpleNamespace(model=model,
                boards=service.BoardCompatibilities_Get(model, language=self._translator.language),
                hardware_provider=service.HardwareProviderForMcu_Get(model.mcu),
                platform_match=service.PlatformMatchView_Get(model, self._translator.language),
                resources=service.ResourceRequirementViews_Get(model, self._translator.language),
                resources_valid=ResourceAssignments_Resolve(model, service.catalog, auto_assign=False).valid,
                i2c_pullup_evidence=service.I2cPullupEvidenceViews_Get(model)))
            self._TargetPages_Refresh(model)
            devices.install_button.hide()
            self.parent()._EmptyState_Refresh(model)
        finally:
            self._displaying_model = False

    def _GroundTarget_Change(self, field, value):
        if self._migration and not self._displaying_model:
            if field in ('board', 'pc_interface'):
                self._explicit_uart = field == 'pc_interface' and value == 'uart'
                self._explicit_resource = ''
            elif field == 'pc_resource':
                self._explicit_resource = str(value or '')
        super()._GroundTarget_Change(field, value)


class HardwareTransactionDialog(QDialog):
    def __init__(self, translator, model, service, target, section='hardware', parent=None):
        super().__init__(parent)
        self.setProperty('collectNumericDrafts', True)
        if target not in ('flight', 'ground'):
            raise ValueError('Unknown hardware target')
        self.target = target
        self._result = None
        self._import_path = None
        self.open_shared_radio = False
        self._translator = translator
        text = translator.Text_Get
        self.setObjectName('hardwareTransaction_' + target)
        self.setWindowTitle(text('workspace.hardware.' + target) + ' · ' + text('hardware.editor.configure'))
        self.resize(960, 750)
        self.setMinimumSize(680, 500)
        root = QVBoxLayout(self)
        hint = QLabel(text('hardware.editor.private_hint'), self)
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.controller = HardwareDraftController(model, service, translator, self)
        if target == 'ground' and self.controller._migration:
            hint.setText(text('hardware.editor.retired_cdc'))
            self.controller._model.ground_target = replace(self.controller._model.ground_target,
                pc_interface='usb_cdc', pc_resource='')
            self.controller._Project_Refresh()
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)
        bodies = {}
        for name in ('hardware', 'devices', 'resources'):
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content = QWidget(scroll)
            layout = QVBoxLayout(content)
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, text('hardware.editor.' + name))
            bodies[name] = layout
        owner = self.controller.board_hardware_page if target == 'flight' else self.controller.ground_target_page
        for widget in (owner.selection_group, owner.custom_widget, owner.provider_notice, owner.platform_group):
            bodies['hardware'].addWidget(widget)
            widget.show()
        owner.selection_group.layout().setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        # Provenance hashes belong to the retained audit data, not ordinary
        # hardware options; keep detected facts and qualification visible.
        owner.platform_form.setRowVisible(owner.platform_values['provenance'], False)
        self.pending_import = QLabel(self)
        self.pending_import.setWordWrap(True)
        bodies['hardware'].addWidget(self.pending_import)
        bodies['resources'].addWidget(owner.advanced_section)
        self.resource_hint = QLabel(text('hardware.editor.import_required'), self)
        self.resource_hint.setWordWrap(True)
        bodies['resources'].addWidget(self.resource_hint)
        self.owner = owner
        owner.advanced_section.toggle_button.setChecked(True)
        owner.advanced_section.show()
        owner.resource_table.setMinimumHeight(320)
        devices = self.controller.devices_page
        if target == 'flight':
            widgets = (devices.primary_group,
                       devices.storage_group, devices.other_group, devices.indicator_group,
                       devices.actuator_group, devices.global_configuration_group)
        else:
            widgets = (owner.pc_group, owner.activity_led_group)
        for widget in widgets:
            bodies['devices'].addWidget(widget)
            widget.show()
        from silverstar_fccg.project.model import GroundRadioSelection_Get
        if target == 'ground':
            selected = GroundRadioSelection_Get(model.ground_target)
            module, power = selected.module_variant, selected.tx_power_dbm
        else:
            selected = model.DeviceInstance_Get(model.air_link.flight_radio_instance)
            module, power = FlightRadioConfiguration_Get(model, selected) if selected else ('', 0)
        self.radio_note = QLabel(text('hardware.editor.shared_radio') + ' · ' +
            (f'{module} · {power} dBm' if module else '—'), self)
        self.radio_note.setWordWrap(True)
        bodies['devices'].addWidget(self.radio_note)
        radio_button = QPushButton(text('hardware.editor.open_radio'), self)
        radio_button.clicked.connect(self._SharedRadio_Request)
        bodies['devices'].addWidget(radio_button)
        if target == 'flight':
            self.rotation_option = QCheckBox(text('hardware.editor.experimental_rotation'), self)
            self.rotation_option.setChecked('silverstar.installation.mag_rotation' in model.base_components)
            advanced = CollapsibleSection(text('hardware.editor.experimental_options'),
                                         expanded=self.rotation_option.isChecked(), parent=self)
            QVBoxLayout(advanced.body).addWidget(self.rotation_option)
            bodies['devices'].addWidget(advanced)
        for body in bodies.values():
            body.addStretch(1)
        # Import only records a path. No importer/cache/settings operation is
        # reachable until the outer controller handles an accepted transaction.
        if target == 'flight':
            owner.importIocRequested.connect(lambda: self._Import_Select(False))
            owner.importDirectoryRequested.connect(lambda: self._Import_Select(True))
        else:
            owner.importRequested.connect(self._Import_Select)
        # Persistent export and preparation remain outside this draft editor.
        for name in ('export_button', 'save_instance', 'prepare_button'):
            button = getattr(owner, name, None)
            if button is not None:
                button.hide()
        root.addWidget(self.controller.status_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.tabs.setCurrentIndex(('hardware', 'devices', 'resources').index(section))
        self._EmptyState_Refresh(self.controller._model)

    def _EmptyState_Refresh(self, model):
        if not hasattr(self, 'owner'):
            return
        hardware = model.hardware if self.target == 'flight' else model.ground_target.hardware
        missing = not hardware.inventory and not hardware.resources
        self.owner.advanced_section.setVisible(not missing)
        self.owner.platform_group.setVisible(not missing)
        self.resource_hint.setVisible(missing)

    def _Import_Select(self, directory):
        if directory:
            selected = QFileDialog.getExistingDirectory(self, self._translator.Text_Get('dialog.import_cubemx_directory'))
        else:
            selected, _ = QFileDialog.getOpenFileName(self,
                self._translator.Text_Get('dialog.import_cubemx_ioc'), '', '*.ioc')
        if selected:
            self._import_path = selected
            self.pending_import.setText(self._translator.Text_Get('hardware.editor.pending_import', path=selected)
                + '\n' + self._translator.Text_Get('dialog.custom_hardware_risk_message'))

    def _SharedRadio_Request(self):
        self.open_shared_radio = True
        self.accept()
        if self.result() != QDialog.DialogCode.Accepted:
            self.open_shared_radio = False

    def accept(self):
        self.controller._collecting = True
        self.controller._collect_error = None
        try:
            if not NumericDrafts_Collect(self, self.controller.status_label, self._translator.Text_Get('editor.invalid_number')):
                return
        finally:
            self.controller._collecting = False
        if self.controller._collect_error is not None:
            return
        candidate = deepcopy(self.controller._model)
        if self.target == 'ground' and self.controller._migration and not self._import_path:
            if (not self.controller._explicit_uart or not self.controller._explicit_resource or
                    NativeCdcHardware_Is(candidate.ground_target.hardware)):
                self.controller.status_label.setText(self._translator.Text_Get('hardware.editor.retired_cdc'))
                return
            candidate.native_usb = None
            from silverstar_fccg.project.air_link import GroundTargetIssues_Get
            uart_issues = [issue for issue in GroundTargetIssues_Get(candidate, self.controller._service.catalog)
                           if issue.code.startswith('GROUND_UART')]
            if uart_issues:
                self.controller.status_label.setText(uart_issues[0].message)
                return
        if self.target == 'flight':
            optional = 'silverstar.installation.mag_rotation'
            if self.rotation_option.isChecked() and optional not in candidate.base_components:
                candidate.base_components.append(optional)
            elif not self.rotation_option.isChecked() and optional in candidate.base_components:
                candidate.base_components.remove(optional)
            if optional in candidate.base_components:
                try:
                    from silverstar_fccg.project.mag_rotation import MagRotationConfiguration_Validate
                    MagRotationConfiguration_Validate(candidate, self.controller._service.catalog)
                except ValueError as error:
                    self.controller.status_label.setText(str(error))
                    return
        self._result = candidate
        self.controller._closed = True
        super().accept()

    def reject(self):
        self.controller._closed = True
        self._result = None
        super().reject()

    def Configuration_Get(self):
        return deepcopy(self._result)

    def ImportPath_Get(self):
        return self._import_path
