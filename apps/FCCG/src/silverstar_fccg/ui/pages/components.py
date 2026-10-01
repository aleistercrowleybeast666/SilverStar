from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import ClassVar

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import (
    BoardCompatibilityView,
    CapabilityUsageView,
    ComponentView,
    DeviceInstanceView,
    I2cPullupEvidenceView,
    LoggingStreamView,
    PlatformMatchView,
    ProtocolProfileView,
    ResourceRequirementView,
)
from silverstar_fccg.project.capabilities import (
    Capability_UserSelectable_Is,
    CapabilityKind,
    CapabilityKind_Get,
)
from silverstar_fccg.project.configuration import SelectionAvailability
from silverstar_fccg.ui.committed_spin import (
    EnterCommittedDoubleSpinBox,
    EnterCommittedSpinBox,
)
from silverstar_fccg.ui.device_initialization import InitializationSection_Create
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.widgets import (
    CollapsibleSection,
    LockedCheckBox,
    SmoothTableWidget,
    StandardCheckBox,
    StandardComboBox,
    StatusPill,
)


class DevicesPage(ScrollableLocalizedPage):
    instanceChanged = Signal(str, str)
    variantChanged = Signal(str, str, str)
    instanceAddRequested = Signal(str)
    otherDeviceToggled = Signal(str, bool)
    installRequested = Signal()

    _DEFAULT_INSTANCE_IDS: ClassVar[dict[str, str]] = {
        "imu": "imu0",
        "gnss": "gnss0",
        "telemetry": "telemetry0",
    }

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.devices", "page.devices.description")
        self.instance_order_note = QLabel()
        self.instance_order_note.setObjectName("deviceInstanceOrderNote")
        self.instance_order_note.setWordWrap(True)
        self.instance_order_note.setProperty("muted", True)
        self.Text_Register(
            self.instance_order_note, "device.instance_order_failover_note"
        )
        self.root_layout.addWidget(self.instance_order_note)
        self.primary_form = QFormLayout()
        self.primary_group = self.Group_Create("group.primary_devices", self.primary_form)
        self.root_layout.addWidget(self.primary_group)

        self.other_layout = QVBoxLayout()
        self.other_empty_label = QLabel()
        self.other_empty_label.setObjectName("otherSensorsEmptyLabel")
        self.other_empty_label.setWordWrap(True)
        self.Text_Register(self.other_empty_label, "device.other_empty")
        self.other_layout.addWidget(self.other_empty_label)
        self.other_form = QFormLayout()
        self.other_layout.addLayout(self.other_form)
        self.other_checks_container = QWidget()
        self.other_checks_layout = QVBoxLayout(self.other_checks_container)
        self.other_checks_layout.setContentsMargins(0, 0, 0, 0)
        self.other_layout.addWidget(self.other_checks_container)
        self.install_button = QPushButton()
        self.install_button.setObjectName("primaryButton")
        self.Text_Register(self.install_button, "action.install_plugin")
        self.install_button.clicked.connect(
            lambda _checked=False: self.installRequested.emit()
        )
        self.other_layout.addWidget(self.install_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.other_group = self.Group_Create("group.other_sensors", self.other_layout)
        self.other_group.setObjectName("otherSensorsGroup")
        self.root_layout.addWidget(self.other_group)

        self.indicator_layout = QVBoxLayout()
        self.indicator_checks_container = QWidget()
        self.indicator_checks_layout = QVBoxLayout(
            self.indicator_checks_container
        )
        self.indicator_checks_layout.setContentsMargins(0, 0, 0, 0)
        self.indicator_layout.addWidget(self.indicator_checks_container)
        self.indicator_group = self.Group_Create(
            "group.indicators", self.indicator_layout
        )
        self.indicator_group.setObjectName("indicatorsGroup")
        self.root_layout.addWidget(self.indicator_group)

        self.actuator_layout = QVBoxLayout()
        self.actuator_empty_label = QLabel()
        self.actuator_empty_label.setWordWrap(True)
        self.Text_Register(self.actuator_empty_label, "device.actuator_empty")
        self.actuator_layout.addWidget(self.actuator_empty_label)
        self.actuator_checks_container = QWidget()
        self.actuator_checks_layout = QVBoxLayout(self.actuator_checks_container)
        self.actuator_checks_layout.setContentsMargins(0, 0, 0, 0)
        self.actuator_layout.addWidget(self.actuator_checks_container)
        self.actuator_group = self.Group_Create(
            "group.actuators", self.actuator_layout
        )
        self.actuator_group.setObjectName("actuatorsGroup")
        self.root_layout.addWidget(self.actuator_group)

        self.telemetry_form = QFormLayout()
        self.telemetry_group = self.Group_Create(
            "group.communication_links", self.telemetry_form
        )
        self.telemetry_group.setObjectName("telemetryLinksGroup")
        self.root_layout.addWidget(self.telemetry_group)

        self.storage_layout = QVBoxLayout()
        self.storage_form = QFormLayout()
        self.storage_layout.addLayout(self.storage_form)
        self.storage_checks_container = QWidget()
        self.storage_checks_layout = QVBoxLayout(self.storage_checks_container)
        self.storage_checks_layout.setContentsMargins(0, 0, 0, 0)
        self.storage_layout.addWidget(self.storage_checks_container)
        self.storage_group = self.Group_Create("group.storage", self.storage_layout)
        self.storage_group.setObjectName("storageGroup")
        self.root_layout.addWidget(self.storage_group)

        self.root_layout.addStretch(1)
        self.device_combos: dict[str, StandardComboBox] = {}
        self.variant_combos: dict[str, StandardComboBox] = {}
        self.device_checks: dict[str, StandardCheckBox] = {}
        self.add_buttons: dict[str, QPushButton] = {}
        self.remove_buttons: dict[str, QPushButton] = {}
        self.initialization_sections: dict[str, CollapsibleSection] = {}
        self._components: tuple[ComponentView, ...] = ()
        self._instances: tuple[DeviceInstanceView, ...] = ()
        self._device_availability: dict[str, SelectionAvailability] = {}
        self.Language_Apply(translator)

    @staticmethod
    def _Layout_Clear(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                DevicesPage._Layout_Clear(item.layout())

    def Configuration_Set(
        self,
        components: Iterable[ComponentView],
        instances: Iterable[DeviceInstanceView],
        device_availability: dict[str, SelectionAvailability] | None = None,
    ) -> None:
        self._components = tuple(components)
        self._instances = tuple(instances)
        self._device_availability = dict(device_availability or {})

        initialization_expanded = {
            key: section.Expanded_Is() for key, section in self.initialization_sections.items()
        }
        self.initialization_sections.clear()
        self._Layout_Clear(self.primary_form)
        self._Layout_Clear(self.telemetry_form)
        self._Layout_Clear(self.other_form)
        self._Layout_Clear(self.storage_form)
        self.device_combos.clear()
        self.variant_combos.clear()
        self.add_buttons.clear()
        self.remove_buttons.clear()
        components_by_class: defaultdict[str, list[ComponentView]] = defaultdict(list)
        instances_by_class: defaultdict[str, list[DeviceInstanceView]] = defaultdict(list)
        for component in self._components:
            components_by_class[component.component_class].append(component)
        for instance in self._instances:
            instances_by_class[instance.component_class].append(instance)

        instance_components = tuple(
            component
            for component in self._components
            if component.options.get("device_selection_style") == "instance"
            and not component.options.get("internal", False)
            and component.component_class != "console"
            and component.component_class != "magnetometer"
        )
        instance_classes = sorted(
            {component.component_class for component in instance_components},
            key=lambda component_class: (0 if component_class == "imu" else 1 if component_class == "gnss" else 2, min(
                (
                    int(component.options.get("device_group_order", 100))
                    for component in instance_components
                    if component.component_class == component_class
                ),
                default=100,
            )),
        )
        group_forms = {
            "primary_devices": self.primary_form,
            "other_sensors": self.other_form,
            "communication_links": self.telemetry_form,
            "storage": self.storage_form,
        }
        populated_groups: set[str] = set()
        for component_class in instance_classes:
            candidates = sorted(
                components_by_class.get(component_class, ()), key=lambda item: item.name
            )
            candidates = [
                component
                for component in candidates
                if component.options.get("device_selection_style") == "instance"
            ]
            if not candidates:
                continue
            category = str(candidates[0].options.get("device_category", ""))
            if category in {"sensor.imu", "sensor.gnss"}:
                group_name = "primary_devices"
            elif category.startswith("sensor."):
                group_name = "other_sensors"
            elif category.startswith("link."):
                group_name = "communication_links"
            elif category.startswith("storage."):
                group_name = "storage"
            else:
                continue
            form = group_forms.get(group_name, self.primary_form)
            populated_groups.add(
                group_name if group_name in group_forms else "primary_devices"
            )
            selected_instances = sorted(
                instances_by_class.get(component_class, ()), key=lambda item: item.instance_id
            )
            selected_plugin_counts: defaultdict[str, int] = defaultdict(int)
            for selected_instance in selected_instances:
                selected_plugin_counts[selected_instance.plugin_id] += 1
            rows: list[DeviceInstanceView | None] = list(selected_instances) or [None]
            for row_index, instance in enumerate(rows):
                instance_id = (
                    instance.instance_id
                    if instance is not None
                    else str(
                        candidates[0].options.get("default_instance_id")
                        or self._DEFAULT_INSTANCE_IDS.get(
                            component_class, f"{component_class}0"
                        )
                    )
                )
                combo = StandardComboBox()
                combo.setObjectName(f"deviceCombo_{instance_id}")
                combo.addItem(self._translator.Text_Get("selection.none"), "")
                for component in candidates:
                    combo.addItem(component.name, component.component_id)
                    item = combo.model().item(combo.count() - 1)
                    plugin_limit = component.plugin_max or component.project_max
                    current_uses_plugin = (
                        instance is not None
                        and instance.plugin_id == component.component_id
                    )
                    plugin_available = (
                        selected_plugin_counts[component.component_id] < plugin_limit
                        or current_uses_plugin
                    )
                    availability = self._device_availability.get(
                        component.component_id, SelectionAvailability(True)
                    )
                    available = plugin_available and availability.available
                    detail = self._PhysicalDetails_Get(component)
                    if not plugin_available:
                        detail = self._translator.Text_Get(
                            "device.plugin_instance_limit", count=plugin_limit,
                        )
                    if not availability.available:
                        detail = "\n".join(filter(None, (
                            detail,
                            self._translator.Text_Get(availability.reason_code),
                        )))
                    if item is not None:
                        item.setEnabled(available)
                        if not available:
                            item.setForeground(
                                combo.palette().color(
                                    QPalette.ColorGroup.Disabled,
                                    QPalette.ColorRole.Text,
                                )
                            )
                            item.setBackground(
                                combo.palette().color(
                                    QPalette.ColorGroup.Disabled,
                                    QPalette.ColorRole.Base,
                                )
                            )
                    combo.setItemData(
                        combo.count() - 1,
                        detail,
                        Qt.ItemDataRole.ToolTipRole,
                    )
                selected_plugin = instance.plugin_id if instance is not None else ""
                selected_index = combo.findData(selected_plugin)
                combo.setCurrentIndex(max(0, selected_index))
                combo.currentIndexChanged.connect(
                    lambda _index, selected_instance=instance_id, editor=combo: self.instanceChanged.emit(
                        selected_instance, str(editor.currentData() or "")
                    )
                )
                form.addRow(
                    QLabel(
                        self._DeviceInstanceTitle_Get(candidates[0], row_index)
                    ),
                    combo,
                )
                self.device_combos[instance_id] = combo
                if instance is not None:
                    selected_component = next(
                        (item for item in candidates if item.component_id == selected_plugin),
                        None,
                    )
                    variants = (
                        selected_component.options.get("device_variants", ())
                        if selected_component is not None else ()
                    )
                    if variants:
                        variant_combo = StandardComboBox()
                        variant_combo.setObjectName(f"deviceVariant_{instance_id}")
                        for variant_id, interface, profile in variants:
                            variant_combo.addItem(
                                f"{interface.upper()} · {profile.replace('_', ' ')}",
                                (interface, profile),
                            )
                        selected_pair = (
                            instance.interface or variants[0][1],
                            instance.profile or variants[0][2],
                        )
                        selected_variant = variant_combo.findData(selected_pair)
                        variant_combo.setCurrentIndex(max(0, selected_variant))
                        variant_combo.currentIndexChanged.connect(
                            lambda _index, selected_instance=instance_id,
                            editor=variant_combo: self.variantChanged.emit(
                                selected_instance,
                                str(editor.currentData()[0]),
                                str(editor.currentData()[1]),
                            )
                        )
                        form.addRow(
                            QLabel(self._translator.Text_Get("device.interface_profile")),
                            variant_combo,
                        )
                        self.variant_combos[instance_id] = variant_combo
                    summary = QLabel(self._CapabilitySummary_Get(instance))
                    summary.setToolTip("\n".join(instance.provides))
                    summary.setObjectName(f"deviceCapabilitySummary_{instance_id}")
                    summary.setWordWrap(True)
                    summary.setProperty("muted", True)
                    form.addRow(QLabel(), summary)
                    if instance.initialization or instance.runtime_defaults:
                        section = InitializationSection_Create(
                            instance, self._translator,
                            expanded=initialization_expanded.get(instance_id, False),
                        )
                        form.addRow(section)
                        self.initialization_sections[instance_id] = section
                    remove_button = QPushButton(
                        self._translator.Text_Get("action.remove_device")
                    )
                    remove_button.setObjectName(
                        f"removeDeviceButton_{instance_id}"
                    )
                    remove_button.clicked.connect(
                        lambda _checked=False, selected_instance=instance_id: self.instanceChanged.emit(
                            selected_instance, ""
                        )
                    )
                    form.addRow(QLabel(), remove_button)
                    self.remove_buttons[instance_id] = remove_button
            class_max = max(
                (
                    item.class_max or item.project_max
                    for item in candidates
                ),
                default=1,
            )
            if (
                selected_instances
                and class_max > len(selected_instances)
                and any(
                    selected_plugin_counts[item.component_id]
                    < (item.plugin_max or item.project_max)
                    for item in candidates
                )
            ):
                add_button = QPushButton(
                    self._translator.Text_Get(
                        "action.add_device",
                        device=self._DeviceClassTitle_Get(candidates[0]),
                    )
                )
                add_button.setObjectName(f"addDeviceButton_{component_class}")
                add_button.clicked.connect(
                    lambda _checked=False, selected_class=component_class: self.instanceAddRequested.emit(
                        selected_class
                    )
                )
                form.addRow(QLabel(), add_button)
                self.add_buttons[component_class] = add_button

        self.primary_group.setVisible("primary_devices" in populated_groups)
        self.telemetry_group.setVisible("communication_links" in populated_groups)
        self.storage_group.setVisible("storage" in populated_groups)

        self._Layout_Clear(self.other_checks_layout)
        self._Layout_Clear(self.indicator_checks_layout)
        self._Layout_Clear(self.actuator_checks_layout)
        self._Layout_Clear(self.storage_checks_layout)
        self.device_checks.clear()
        other_components = sorted(
            (
                component
                for component in self._components
                if component.options.get("device_selection_style") != "instance"
                and str(component.options.get("device_category", "")).startswith(
                    "sensor."
                )
            ),
            key=lambda item: (
                int(item.options.get("device_group_order", 100)), item.name
            ),
        )
        actuator_components = sorted(
            (
                component
                for component in self._components
                if str(component.options.get("device_category", "")).startswith(
                    "actuator."
                )
            ),
            key=lambda item: (item.component_id, item.name),
        )
        indicator_components = sorted(
            (
                component
                for component in self._components
                if str(component.options.get("device_category", "")).startswith(
                    "indicator."
                )
            ),
            key=lambda item: (
                item.options.get("indicator_role") != "system",
                item.name,
            ),
        )
        selected_plugins = {instance.plugin_id for instance in self._instances}
        instances_by_plugin = {
            instance.plugin_id: instance for instance in self._instances
        }
        storage_components = sorted(
            (
                component
                for component in self._components
                if component.options.get("device_selection_style") != "instance"
                and str(component.options.get("device_category", "")).startswith(
                    "storage."
                )
            ),
            key=lambda item: item.name,
        )
        for component_group, layout in (
            (other_components, self.other_checks_layout),
            (storage_components, self.storage_checks_layout),
            (indicator_components, self.indicator_checks_layout),
            (actuator_components, self.actuator_checks_layout),
        ):
            for component in component_group:
                instance = instances_by_plugin.get(component.component_id)
                required = bool(
                    instance is not None
                    and instance.required
                    and not str(
                        component.options.get("device_category", "")
                    ).startswith(("actuator.", "storage.", "link."))
                )
                check = (
                    LockedCheckBox(component.name)
                    if required
                    else StandardCheckBox(component.name)
                )
                check.setProperty("componentId", component.component_id)
                with QSignalBlocker(check):
                    check.setChecked(component.component_id in selected_plugins)
                details = self._PhysicalDetails_Get(component)
                if required:
                    details = "\n".join(
                        filter(
                            None,
                            (
                                details,
                                self._translator.Text_Get(
                                    "device.required_tooltip"
                                ),
                            ),
                        )
                    )
                check.setToolTip(details)
                availability = self._device_availability.get(
                    component.component_id, SelectionAvailability(True)
                )
                if not availability.available:
                    reason = (
                        self._translator.Text_Get(availability.reason_code)
                        if availability.reason_code
                        else self._translator.Text_Get(
                            "selection.unavailable.capability",
                            missing=", ".join(
                                availability.missing_capabilities
                            ),
                        )
                    )
                    check.setEnabled(False)
                    check.setToolTip("\n".join(filter(None, (details, reason))))
                if not required:
                    check.toggled.connect(
                        lambda checked, plugin_id=component.component_id: self.otherDeviceToggled.emit(
                            plugin_id, checked
                        )
                    )
                layout.addWidget(check)
                self.device_checks[component.component_id] = check
        other_populated = bool(other_components) or (
            "other_sensors" in populated_groups
        )
        self.other_empty_label.setVisible(not other_populated)
        self.other_checks_container.setVisible(bool(other_components))
        self.install_button.setVisible(not other_populated)
        self.indicator_checks_container.setVisible(bool(indicator_components))
        self.indicator_group.setVisible(bool(indicator_components))
        self.storage_checks_container.setVisible(bool(storage_components))
        self.storage_group.setVisible(
            "storage" in populated_groups or bool(storage_components)
        )
        self.actuator_empty_label.setVisible(not actuator_components)
        self.actuator_checks_container.setVisible(bool(actuator_components))

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        if self._components:
            self.Configuration_Set(
                self._components,
                self._instances,
                self._device_availability,
            )

    def _DeviceClassTitle_Get(self, component: ComponentView) -> str:
        key = f"device.class.{component.component_class}"
        title = self._translator.Text_Get(key)
        return component.name if title == key else title

    def _DeviceInstanceTitle_Get(self, component: ComponentView, index: int) -> str:
        if component.component_class == "telemetry":
            return self._translator.Text_Get("device.class.telemetry")
        key = f"device.instance.{component.component_class}"
        title = self._translator.Text_Get(key, index=index)
        if title == key:
            return self._translator.Text_Get(
                "device.instance.named", device=self._DeviceClassTitle_Get(component),
                index=index,
            )
        return title

    def _CapabilityTitle_Get(self, capability: str) -> str:
        key = f"capability.{capability}"
        title = self._translator.Text_Get(key)
        return self._translator.Text_Get("capability.extension") if title == key else title

    def _CapabilitySummary_Get(self, instance: DeviceInstanceView) -> str:
        raw_capabilities = ", ".join(
            self._CapabilityTitle_Get(capability)
            for capability in instance.provides
            if Capability_UserSelectable_Is(capability)
            and not capability.startswith("magnetometer.")
            and CapabilityKind_Get(capability) == CapabilityKind.RAW_DATA
        )
        qualified_capabilities = ", ".join(
            self._CapabilityTitle_Get(capability)
            for capability in instance.provides
            if Capability_UserSelectable_Is(capability)
            and not capability.startswith("magnetometer.")
            and CapabilityKind_Get(capability) == CapabilityKind.QUALIFIED
        )
        unqualified_capabilities = ", ".join(
            self._CapabilityTitle_Get(capability)
            for capability in instance.unqualified
            if not capability.startswith("magnetometer.")
        )
        return self._translator.Text_Get(
            "device.provides_summary_typed",
            raw=raw_capabilities or "—",
            qualified=qualified_capabilities or "—",
            unqualified=unqualified_capabilities or "—",
        )

    @staticmethod
    def _PhysicalDetails_Get(component: ComponentView) -> str:
        values = (
            component.physical_vendor,
            component.physical_model,
            component.chipset,
            component.driver,
        )
        return " · ".join(value for value in values if value)


class BoardHardwarePage(ScrollableLocalizedPage):
    boardChanged = Signal(str)
    customSelected = Signal()
    importIocRequested = Signal()
    importDirectoryRequested = Signal()
    exportRequested = Signal()
    autoAssignRequested = Signal()
    assignmentChanged = Signal(str, str)
    prepareRequested = Signal()
    generateRequested = Signal()
    manualValidationRequested = Signal()
    i2cExternalPullupChanged = Signal(str, bool)

    def __init__(self, translator: Translator, *, target: str = "flight") -> None:
        page = "page.ground" if target == "ground" else "page.board_hardware"
        self.target_role = target
        super().__init__(translator, page, page + ".description")
        selection_form = QFormLayout()
        self.board_label = QLabel()
        self.Text_Register(self.board_label, "hardware.existing")
        self.board_combo = StandardComboBox()
        self.board_combo.currentIndexChanged.connect(self._Board_Emit)
        selection_form.addRow(self.board_label, self.board_combo)
        self.hardware_status_label = QLabel()
        self.Text_Register(self.hardware_status_label, "field.hardware_resources")
        self.hardware_status = StatusPill()
        selection_form.addRow(self.hardware_status_label, self.hardware_status)
        self.manual_validation_widget = QWidget()
        manual_validation_row = QHBoxLayout(self.manual_validation_widget)
        manual_validation_row.setContentsMargins(0, 0, 0, 0)
        self.manual_validation_button = QPushButton()
        self.manual_validation_button.setObjectName("primaryButton")
        self.Text_Register(
            self.manual_validation_button,
            "action.complete_manual_assignment_check",
        )
        self.manual_validation_button.clicked.connect(
            lambda _checked=False: self.manualValidationRequested.emit()
        )
        self.manual_validation_status = StatusPill()
        manual_validation_row.addWidget(self.manual_validation_button)
        manual_validation_row.addWidget(self.manual_validation_status, 1)
        self.preparation_label = QLabel()
        self.Text_Register(self.preparation_label, "field.hardware_preparation")
        self.preparation_widget = QWidget()
        preparation_row = QHBoxLayout(self.preparation_widget)
        preparation_row.setContentsMargins(0, 0, 0, 0)
        self.prepare_button = QPushButton()
        self.prepare_button.setObjectName("primaryButton")
        self.prepare_button.clicked.connect(
            lambda _checked=False: self.prepareRequested.emit()
        )
        self.preparation_status = StatusPill()
        preparation_row.addWidget(self.prepare_button)
        preparation_row.addWidget(self.preparation_status, 1)
        selection_form.addRow(self.preparation_label, self.preparation_widget)
        self.root_layout.addWidget(
            self.Group_Create("group.board_selection", selection_form)
        )
        self.generate_button = QPushButton()
        self.generate_button.setObjectName("primaryButton")
        self.Text_Register(self.generate_button, "action.generate_ground_project" if target == "ground" else "action.generate_flight_project")
        self.generate_button.clicked.connect(
            lambda _checked=False: self.generateRequested.emit()
        )
        self.root_layout.addWidget(self.generate_button)

        self.platform_form = QFormLayout()
        self.platform_values: dict[str, QLabel] = {}
        for field, key in (
            ("source", "field.hardware_source"),
            ("part", "field.detected_mcu_part"),
            ("family", "field.detected_mcu_family"),
            ("package", "field.detected_mcu_package"),
            ("core", "field.detected_mcu_core"),
            ("cubemx", "field.cubemx_version"),
            ("firmware_package", "field.stm32cube_firmware_package"),
            ("source_policy", "field.hal_cmsis_source_policy"),
            ("timebase", "field.hal_timebase"),
            ("storage", "field.sdio_fatfs_status"),
            ("i2c", "field.i2c_inventory"),
            ("pwm", "field.pwm_inventory"),
            ("can", "field.can_inventory"),
            ("plugin", "field.matched_platform"),
            ("reason", "field.platform_match_reason"),
            ("verification", "field.platform_verification"),
            ("provenance", "field.platform_provenance"),
        ):
            label = QLabel()
            self.Text_Register(label, key)
            value = QLabel("—")
            value.setObjectName(f"platform_{field}")
            value.setWordWrap(True)
            self.platform_form.addRow(label, value)
            self.platform_values[field] = value
        self.root_layout.addWidget(
            self.Group_Create("group.detected_platform", self.platform_form)
        )

        self.provider_notice = QLabel()
        self.provider_notice.setWordWrap(True)
        self.provider_notice.setObjectName("noticeLabel")
        self.root_layout.addWidget(self.provider_notice)

        custom_actions = QHBoxLayout()
        self.import_ioc_button = QPushButton()
        self.Text_Register(self.import_ioc_button, "action.import_cubemx_ioc")
        self.import_ioc_button.clicked.connect(
            lambda _checked=False: self.importIocRequested.emit()
        )
        self.import_directory_button = QPushButton()
        self.Text_Register(
            self.import_directory_button, "action.import_cubemx_directory"
        )
        self.import_directory_button.clicked.connect(
            lambda _checked=False: self.importDirectoryRequested.emit()
        )
        self.export_button = QPushButton()
        self.Text_Register(self.export_button, "action.save_hardware")
        self.export_button.clicked.connect(
            lambda _checked=False: self.exportRequested.emit()
        )
        custom_actions.addWidget(self.import_ioc_button)
        custom_actions.addWidget(self.import_directory_button)
        custom_actions.addWidget(self.export_button)
        custom_actions.addStretch(1)
        self.custom_widget = QWidget()
        self.custom_widget.setLayout(custom_actions)
        self.root_layout.insertWidget(2, self.custom_widget)

        pullup_layout = QVBoxLayout()
        self.i2c_pullup_notice = QLabel()
        self.i2c_pullup_notice.setWordWrap(True)
        self.Text_Register(
            self.i2c_pullup_notice, "hardware.i2c_external_pullup_notice"
        )
        pullup_layout.addWidget(self.i2c_pullup_notice)
        self.i2c_pullup_checks_widget = QWidget()
        self.i2c_pullup_checks_layout = QVBoxLayout(
            self.i2c_pullup_checks_widget
        )
        self.i2c_pullup_checks_layout.setContentsMargins(0, 0, 0, 0)
        pullup_layout.addWidget(self.i2c_pullup_checks_widget)
        self.i2c_pullup_group = self.Group_Create(
            "group.i2c_external_pullups", pullup_layout
        )
        self.root_layout.addWidget(self.i2c_pullup_group)

        advanced_layout = QVBoxLayout()
        advanced_toolbar = QHBoxLayout()
        advanced_explanation = QLabel()
        advanced_explanation.setWordWrap(True)
        self.Text_Register(advanced_explanation, "board.advanced_explanation")
        self.auto_button = QPushButton()
        self.auto_button.setObjectName("primaryButton")
        self.Text_Register(self.auto_button, "action.auto_assign")
        self.auto_button.clicked.connect(
            lambda _checked=False: self.autoAssignRequested.emit()
        )
        advanced_toolbar.addWidget(advanced_explanation, 1)
        advanced_toolbar.addWidget(self.auto_button)
        advanced_toolbar.addWidget(self.manual_validation_widget)
        advanced_layout.addLayout(advanced_toolbar)
        self.resource_table = SmoothTableWidget(0, 6)
        self.resource_table.setObjectName("engineeringTable")
        self.resource_table.setAlternatingRowColors(True)
        self.resource_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.resource_table.setWordWrap(True)
        self.resource_table.verticalHeader().setVisible(False)
        resource_header = self.resource_table.horizontalHeader()
        resource_header.setStretchLastSection(False)
        for column in (0, 1, 3):
            resource_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
        resource_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        resource_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        resource_header.setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.resource_table.setColumnWidth(0, 270)
        self.resource_table.setColumnWidth(1, 210)
        self.resource_table.setColumnWidth(3, 190)
        advanced_layout.addWidget(self.resource_table)
        self.advanced_section = CollapsibleSection(expanded=False)
        self.advanced_section.BodyLayout_Set(advanced_layout)
        self.advanced_group = self.advanced_section
        self.root_layout.addWidget(self.advanced_section)
        self.root_layout.addStretch(1)
        self._boards: tuple[BoardCompatibilityView, ...] = ()
        self._resources: tuple[ResourceRequirementView, ...] = ()
        self._selected_board = ""
        self._custom_available = False
        self._custom_selected = False
        self._custom_ready = False
        self._prepared = False
        self._hardware_mode = "unselected"
        self._resources_valid = False
        self._assignment_confirmed = False
        self._platform = PlatformMatchView()
        self._i2c_pullup_evidence: tuple[I2cPullupEvidenceView, ...] = ()
        self.Language_Apply(translator)

    def Platform_Set(self, platform: PlatformMatchView) -> None:
        self._platform = platform
        source_key = f"hardware.source.{platform.hardware_source}"
        source_text = self._translator.Text_Get(source_key)
        if source_text == source_key:
            source_text = platform.hardware_source or "—"
        values = {
            "source": source_text,
            "part": platform.detected_part or "—",
            "family": platform.detected_family or "—",
            "package": platform.detected_package or "—",
            "core": platform.detected_core or "—",
            "cubemx": platform.cubemx_version or "—",
            "firmware_package": platform.firmware_package or "—",
            "source_policy": platform.source_policy or "—",
            "timebase": platform.timebase_status or "—",
            "storage": platform.storage_status or "—",
            "i2c": platform.i2c_status or "—",
            "pwm": platform.pwm_status or "—",
            "can": platform.can_status or "—",
            "plugin": (
                f"{platform.component_name} ({platform.component_id})"
                if platform.component_id
                else "—"
            ),
            "reason": platform.reason or platform.error or "—",
            "verification": (
                self._translator.Text_Get(
                    f"platform.verification.{platform.verification}"
                )
                if platform.verification
                else "—"
            ),
            "provenance": platform.provenance or "—",
        }
        for field, text in values.items():
            self.platform_values[field].setText(text)
            self.platform_values[field].setToolTip(text)
            self.platform_values[field].setProperty(
                "validationIssue", bool(platform.error and field == "reason")
            )

    def Boards_Set(
        self,
        boards: Iterable[BoardCompatibilityView],
        selected: str,
        *,
        custom_available: bool,
        custom_selected: bool,
        custom_ready: bool,
        prepared: bool = False,
        hardware_mode: str = "unselected",
        assignment_confirmed: bool = False,
    ) -> None:
        self._boards = tuple(boards)
        self._selected_board = selected
        self._custom_available = custom_available
        self._custom_selected = custom_selected
        self._custom_ready = custom_ready
        self._prepared = prepared
        self._hardware_mode = hardware_mode
        self._assignment_confirmed = assignment_confirmed
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        if custom_available:
            self.board_combo.addItem(
                self._translator.Text_Get("board.custom_hardware"), "__custom__"
            )
        for board in self._boards:
            suffix = "" if board.compatible else self._translator.Text_Get(
                "board.incompatible_suffix", missing=board.missing_text or board.detail
            )
            self.board_combo.addItem(board.name + suffix, board.component_id)
            item = self.board_combo.model().item(self.board_combo.count() - 1)
            if item is not None:
                item.setEnabled(board.compatible)
        current_data = (
            "__custom__"
            if custom_selected
            else selected if hardware_mode == "board_plugin" else ""
        )
        index = self.board_combo.findData(current_data)
        self.board_combo.setCurrentIndex(index)
        self.board_combo.blockSignals(False)
        self.custom_widget.setVisible(custom_available)
        self.export_button.setEnabled(custom_ready)
        board_selected = hardware_mode == "board_plugin"
        self.preparation_label.setVisible(False)
        self.preparation_widget.setVisible(False)
        self.prepare_button.setEnabled(board_selected)
        self.generate_button.setEnabled(hardware_mode != "unselected")
        custom_actions_enabled = hardware_mode == "custom"
        self.auto_button.setEnabled(custom_actions_enabled)
        self.manual_validation_button.setEnabled(custom_actions_enabled)
        self.manual_validation_status.setVisible(custom_actions_enabled)
        self.manual_validation_status.Status_Set(
            self._translator.Text_Get(
                "status.manual_assignment_confirmed"
                if assignment_confirmed
                else "status.manual_assignment_unconfirmed"
            ),
            "success" if assignment_confirmed else "info",
        )
        self.prepare_button.setText(
            self._translator.Text_Get("action.prepare_hardware")
        )
        self.preparation_status.Status_Set(
            self._translator.Text_Get(
                "status.hardware_prepared"
                if prepared
                else "status.hardware_not_prepared"
            ),
            "success" if prepared else "info",
        )
        if hardware_mode == "unselected":
            self.provider_notice.setText(
                self._translator.Text_Get("board.ground_selection_pending" if self.target_role == "ground" else "board.selection_pending")
            )
        elif not custom_available:
            self.provider_notice.setText(
                self._translator.Text_Get("board.no_provider")
            )
        elif custom_selected:
            self.provider_notice.setText(
                self._translator.Text_Get("board.cubemx_steps")
            )
        else:
            self.provider_notice.setText(
                self._translator.Text_Get("board.automatic_summary")
            )

    def Resources_Set(
        self,
        resources: Iterable[ResourceRequirementView],
        valid: bool,
        *,
        hardware_selected: bool,
    ) -> None:
        self._resources = tuple(resources)
        self._resources_valid = valid
        self.resource_table.blockSignals(True)
        self.resource_table.setRowCount(len(self._resources))
        for row, requirement in enumerate(self._resources):
            requirement_item = QTableWidgetItem(
                requirement.display_name or requirement.name
            )

            requirement_item.setToolTip(requirement.key)
            self.resource_table.setItem(row, 0, requirement_item)
            contract_item = QTableWidgetItem(
                requirement.contract_summary or requirement.kind
            )
            contract_item.setToolTip(
                requirement.contract_summary or requirement.kind
            )
            self.resource_table.setItem(row, 1, contract_item)
            self.resource_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    self._translator.Text_Get(
                        "status.required" if requirement.required else "selection.optional"
                    )
                ),
            )
            if requirement.pending_hardware_confirmation:
                pending_value = QLabel(
                    self._translator.Text_Get(
                        "resource.pending_hardware_confirmation"
                    )
                )
                pending_value.setProperty("muted", True)
                self.resource_table.setCellWidget(row, 3, pending_value)
            elif requirement.fixed and requirement.assignment:
                fixed_value = QLabel(requirement.assignment or "—")
                fixed_value.setProperty("fixedResource", True)
                self.resource_table.setCellWidget(row, 3, fixed_value)
            else:
                combo = StandardComboBox()
                combo.setMinimumWidth(180)
                combo.addItem(self._translator.Text_Get("status.unassigned"), "")
                for candidate in requirement.candidates:
                    combo.addItem(candidate, candidate)
                index = combo.findData(requirement.assignment)
                if index >= 0:
                    combo.setCurrentIndex(index)
                combo.currentIndexChanged.connect(
                    lambda _index, key=requirement.key, editor=combo: self.assignmentChanged.emit(
                        key, str(editor.currentData() or "")
                    )
                )
                self.resource_table.setCellWidget(row, 3, combo)
            physical_item = QTableWidgetItem(
                requirement.physical_details
                or requirement.physical_resource
                or "—"
            )
            physical_item.setToolTip(physical_item.text())
            self.resource_table.setItem(row, 4, physical_item)
            if requirement.validation_error:
                status_text = self._translator.Text_Get(
                    "status.hardware_contract_error"
                )
            elif requirement.required and not requirement.assignment:
                status_text = self._translator.Text_Get("status.unassigned")
            else:
                status_text = self._translator.Text_Get(
                    "status.hardware_contract_valid"
                )
            status_item = QTableWidgetItem(status_text)
            status_item.setToolTip(requirement.validation_error)
            if requirement.validation_error:
                error_color = QColor("#d32f2f")
                for column in (0, 1, 2, 4):
                    item = self.resource_table.item(row, column)
                    if item is not None:
                        item.setForeground(error_color)
                        item.setToolTip(
                            "\n".join(
                                filter(
                                    None,
                                    (item.toolTip(), requirement.validation_error),
                                )
                            )
                        )
                status_item.setForeground(error_color)
            self.resource_table.setItem(row, 5, status_item)
        self.resource_table.blockSignals(False)
        self.resource_table.setHorizontalHeaderLabels(
            [
                self._translator.Text_Get("column.requirement"),
                self._translator.Text_Get("column.resource_contract"),
                self._translator.Text_Get("column.requiredness"),
                self._translator.Text_Get("column.current_connection"),
                self._translator.Text_Get("column.physical_configuration"),
                self._translator.Text_Get("column.status"),
            ]
        )
        self.resource_table.resizeRowsToContents()
        pending_count = sum(
            1
            for requirement in self._resources
            if requirement.required and not requirement.assignment
        )
        if not hardware_selected:
            self.hardware_status.Status_Set(
                self._translator.Text_Get(
                    "board.hardware_pending", count=pending_count
                ),
                "info",
            )
        else:
            self.hardware_status.Status_Set(
                self._translator.Text_Get(
                    "board.resources_valid" if valid else "board.resources_invalid"
                ),
                "success" if valid else "warning",
            )

    def I2cPullupEvidence_Set(
        self, evidence: Iterable[I2cPullupEvidenceView]
    ) -> None:
        self._i2c_pullup_evidence = tuple(evidence)
        while self.i2c_pullup_checks_layout.count():
            item = self.i2c_pullup_checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for value in self._i2c_pullup_evidence:
            check = StandardCheckBox(
                self._translator.Text_Get(
                    "hardware.i2c_external_pullup_confirmation",
                    resource=value.physical_resource,
                    pins=value.pins_text,
                )
            )
            check.setProperty("resourceId", value.resource_id)
            check.setChecked(value.confirmed)
            check.toggled.connect(
                lambda checked, resource_id=value.resource_id: (
                    self.i2cExternalPullupChanged.emit(resource_id, checked)
                )
            )
            self.i2c_pullup_checks_layout.addWidget(check)
        self.i2c_pullup_group.setVisible(bool(self._i2c_pullup_evidence))

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        self.Platform_Set(self._platform)
        self.advanced_section.Title_Set(
            translator.Text_Get("group.advanced_resources")
        )
        self.Boards_Set(
            self._boards,
            self._selected_board,
            custom_available=self._custom_available,
            custom_selected=self._custom_selected,
            custom_ready=self._custom_ready,
            prepared=self._prepared,
            hardware_mode=self._hardware_mode,
            assignment_confirmed=self._assignment_confirmed,
        )
        self.Resources_Set(
            self._resources,
            self._resources_valid,
            hardware_selected=self._hardware_mode != "unselected",
        )
        self.I2cPullupEvidence_Set(self._i2c_pullup_evidence)

    def _Board_Emit(self) -> None:
        value = str(self.board_combo.currentData() or "")
        if value == "__custom__":
            self.customSelected.emit()
        elif value:
            self.boardChanged.emit(value)


class CadenceEditor(QWidget):
    changed = Signal()

    _UNIT_FACTORS: ClassVar[dict[str, int]] = {
        "us": 1,
        "ms": 1_000,
        "s": 1_000_000,
    }
    _PERIOD_US_MAX = 4_294_967_295

    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.value_spin = EnterCommittedDoubleSpinBox()
        self.value_spin.setObjectName("cadenceValueSpin")
        self.value_spin.setDecimals(3)
        self.value_spin.setMinimum(0.0)
        self.value_spin.setSpecialValueText("—")
        self.value_spin.committed.connect(self._Value_Change)
        self.unit_combo = StandardComboBox()
        self.unit_combo.setObjectName("cadenceUnitCombo")
        for unit in ("us", "ms", "s"):
            self.unit_combo.addItem(unit, unit)
        self.unit_combo.currentIndexChanged.connect(self._Unit_Change)
        self.text_label = QLabel("—")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.value_spin, 1)
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.text_label, 1)
        self._period_us = 0
        self._unit_factor = 1
        self._periodic = False

    def Cadence_Set(
        self,
        *,
        kind: str,
        text: str,
        period_us: int,
        enabled: bool,
    ) -> None:
        self._periodic = kind == "periodic"
        self._period_us = min(
            self._PERIOD_US_MAX,
            max(0, int(period_us)),
        )
        self.value_spin.setVisible(self._periodic)
        self.unit_combo.setVisible(self._periodic)
        self.text_label.setVisible(not self._periodic)
        if not self._periodic:
            self.text_label.setText(text or "—")
            self.text_label.setToolTip(text)
            return
        unit, factor = self._BestUnit_Get(self._period_us)
        self._unit_factor = factor
        self._Range_Apply(factor)
        with QSignalBlocker(self.unit_combo):
            self.unit_combo.setCurrentIndex(
                max(0, self.unit_combo.findData(unit))
            )
        with QSignalBlocker(self.value_spin):
            self.value_spin.CommittedValue_Set(self._period_us / factor)
        self.value_spin.setEnabled(enabled)
        self.unit_combo.setEnabled(enabled)

    def PeriodUs_Get(self) -> int:
        return self._period_us

    @classmethod
    def _BestUnit_Get(cls, period_us: int) -> tuple[str, int]:
        if period_us > 0 and period_us % cls._UNIT_FACTORS["s"] == 0:
            return "s", cls._UNIT_FACTORS["s"]
        if period_us > 0 and period_us % cls._UNIT_FACTORS["ms"] == 0:
            return "ms", cls._UNIT_FACTORS["ms"]
        return "us", cls._UNIT_FACTORS["us"]

    def _Value_Change(self, value: float) -> None:
        period_us = min(
            self._PERIOD_US_MAX,
            max(0, round(value * self._unit_factor)),
        )
        if period_us != self._period_us:
            self._period_us = period_us
            self.changed.emit()

    def _Unit_Change(self, _index: int) -> None:
        unit = str(self.unit_combo.currentData() or "us")
        factor = self._UNIT_FACTORS[unit]
        self._unit_factor = factor
        self._Range_Apply(factor)
        with QSignalBlocker(self.value_spin):
            self.value_spin.CommittedValue_Set(self._period_us / factor)

    def _Range_Apply(self, factor: int) -> None:
        self.value_spin.setDecimals({1: 0, 1_000: 3, 1_000_000: 6}[factor])
        maximum = self._PERIOD_US_MAX / factor
        self.value_spin.setMaximum(maximum)
        unit = next(name for name, value in self._UNIT_FACTORS.items()
                    if value == factor)
        self.value_spin.setToolTip(self._translator.Text_Get(
            "mode.parameter_range", minimum=0, maximum=round(maximum, self.value_spin.decimals()),
            unit=unit))


class FlightConfigurationPage(ScrollableLocalizedPage):
    strategyChanged = Signal(str, object)
    modeChanged = Signal(str, object)
    capabilitySourceChanged = Signal(str, str)
    loggingChanged = Signal()
    modeParameterChanged = Signal(str, str, str, object)
    protocolProfileChanged = Signal(str, object)
    logDecoderExportRequested = Signal()

    def __init__(self, translator: Translator) -> None:
        super().__init__(
            translator, "page.flight_configuration", "page.flight_configuration.description"
        )
        self.protocol_form = QFormLayout()
        self.protocol_group = self.Group_Create(
            "group.communication_protocols", self.protocol_form
        )
        self.root_layout.addWidget(self.protocol_group)
        self.telemetry_protocol_form = QFormLayout()
        self.telemetry_protocol_group = self.Group_Create(
            "group.telemetry_protocol", self.telemetry_protocol_form
        )
        self.mission_strategy_form = QFormLayout()
        self.mission_strategy_group = self.Group_Create(
            "group.mission_strategy", self.mission_strategy_form
        )
        self.root_layout.addWidget(self.mission_strategy_group)
        self.strategy_form = QFormLayout()
        strategy_layout = QVBoxLayout()
        strategy_layout.addLayout(self.strategy_form)
        self.strategy_group = self.Group_Create(
            "group.strategy_selection", strategy_layout
        )
        self.root_layout.addWidget(self.strategy_group)
        self.ins_strategy_form = QFormLayout()
        self.ins_strategy_group = self.Group_Create(
            "navigation.ins", self.ins_strategy_form
        )
        self.root_layout.addWidget(self.ins_strategy_group)
        self.estimator_strategy_form = QFormLayout()
        self.estimator_strategy_group = self.Group_Create(
            "navigation.estimator", self.estimator_strategy_form
        )
        self.root_layout.addWidget(self.estimator_strategy_group)
        self.mission_mode_layout = QVBoxLayout()
        self.mission_mode_group = self.Group_Create(
            "group.mission_modes", self.mission_mode_layout
        )
        self.root_layout.addWidget(self.mission_mode_group)
        self.mode_layout = QVBoxLayout()
        self.mode_group = self.Group_Create("group.mode_selection", self.mode_layout)
        self.root_layout.addWidget(self.mode_group)
        capability_layout = QVBoxLayout()
        capability_notice = QLabel()
        capability_notice.setWordWrap(True)
        self.Text_Register(capability_notice, "capability.flight_summary")
        capability_layout.addWidget(capability_notice)
        self.capability_table = SmoothTableWidget(0, 5)
        self.capability_table.setObjectName("engineeringTable")
        self.capability_table.setAlternatingRowColors(True)
        self.capability_table.verticalHeader().setVisible(False)
        capability_header = self.capability_table.horizontalHeader()
        capability_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        capability_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        capability_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        capability_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        capability_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        capability_layout.addWidget(self.capability_table)
        self.capability_group = self.Group_Create(
            "group.capability_data_sources", capability_layout
        )
        self.root_layout.addWidget(self.capability_group)
        logging_layout = QVBoxLayout()
        self.logging_group = self.Group_Create("group.logging", logging_layout)
        self._logging_header_layout = QGridLayout()
        self._logging_button_columns = 4
        logging_notice = QLabel()
        logging_notice.setWordWrap(True)
        self.Text_Register(logging_notice, "logging.thin_glue_notice")
        logging_layout.addWidget(logging_notice)
        self.logging_disabled_label = QLabel()
        self.logging_disabled_label.setWordWrap(True)
        self.Text_Register(
            self.logging_disabled_label, "logging.protocol_disabled"
        )
        self.logging_disabled_label.hide()
        logging_layout.addWidget(self.logging_disabled_label)
        self.logging_select_all_button = QPushButton()
        self.logging_select_all_button.setObjectName(
            "loggingEnableAllButton"
        )
        self.Text_Register(
            self.logging_select_all_button,
            "action.logging_enable_all",
        )
        self.logging_select_all_button.clicked.connect(
            lambda _checked=False: self.Streams_SelectAllAvailable()
        )
        self._logging_header_layout.addWidget(
            self.logging_select_all_button, 0, 0, alignment=Qt.AlignmentFlag.AlignTop
        )
        self.logging_flight_only_button = QPushButton()
        self.logging_flight_only_button.setObjectName(
            "loggingKeepFlightOnlyButton"
        )
        self.Text_Register(
            self.logging_flight_only_button,
            "action.logging_keep_flight_only",
        )
        self.logging_flight_only_button.clicked.connect(
            lambda _checked=False: self.Streams_KeepFlightOnly()
        )
        self._logging_header_layout.addWidget(
            self.logging_flight_only_button, 0, 1, alignment=Qt.AlignmentFlag.AlignTop
        )
        self.logging_required_only_button = QPushButton()
        self.logging_required_only_button.setObjectName(
            "loggingKeepRequiredOnlyButton"
        )
        self.Text_Register(
            self.logging_required_only_button,
            "action.logging_keep_required_only",
        )
        self.logging_required_only_button.clicked.connect(
            lambda _checked=False: self.Streams_KeepRequiredOnly()
        )
        self._logging_header_layout.addWidget(
            self.logging_required_only_button, 0, 2, alignment=Qt.AlignmentFlag.AlignTop
        )
        self.log_decoder_export_button = QPushButton()
        self.log_decoder_export_button.setObjectName("logDecoderExportButton")
        self.Text_Register(
            self.log_decoder_export_button,
            "action.export_log_decoder_profile",
        )
        self.log_decoder_export_button.clicked.connect(
            lambda _checked=False: self.logDecoderExportRequested.emit()
        )
        self._logging_header_layout.addWidget(
            self.log_decoder_export_button, 0, 3, alignment=Qt.AlignmentFlag.AlignTop
        )
        logging_layout.addLayout(self._logging_header_layout)
        self.logging_table = SmoothTableWidget(0, 7)
        self.logging_table.setObjectName("engineeringTable")
        self.logging_table.setAlternatingRowColors(True)
        self.logging_table.verticalHeader().setVisible(False)
        logging_header = self.logging_table.horizontalHeader()
        logging_header.setStretchLastSection(False)
        for column in (0, 2, 3, 4):
            logging_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        logging_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        logging_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        logging_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        logging_layout.addWidget(self.logging_table)
        self.root_layout.addWidget(self.logging_group)
        self.root_layout.addStretch(1)
        self.strategy_combos: dict[str, StandardComboBox] = {}
        self.mode_checks: dict[str, list[StandardCheckBox]] = {}
        self.mode_parameter_spins: dict[
            tuple[str, str, str], EnterCommittedDoubleSpinBox | EnterCommittedSpinBox
        ] = {}
        self.protocol_combos: dict[str, StandardComboBox] = {}
        self._components: tuple[ComponentView, ...] = ()
        self._strategies: dict[str, str | None] = {}
        self._modes: dict[str, list[str]] = {}
        self._mode_parameters: dict[
            str, dict[str, dict[str, float | int]]
        ] = {}
        self._protocol_profiles: dict[str, tuple[ProtocolProfileView, ...]] = {}
        self._selected_protocol_profiles: dict[
            str, tuple[str, str] | None
        ] = {}
        self._logging_protocol_enabled = True
        self._streams: list[LoggingStreamView] = []
        self._capabilities: tuple[CapabilityUsageView, ...] = ()
        self._strategy_availability: dict[str, SelectionAvailability] = {}
        self._mode_availability: dict[tuple[str, str], SelectionAvailability] = {}
        self.Language_Apply(translator)

    def Configuration_Set(
        self,
        components: Iterable[ComponentView],
        strategies: dict[str, str | None],
        modes: dict[str, list[str]],
        mode_parameters: dict[str, dict[str, dict[str, float | int]]] | None = None,
        strategy_availability: dict[str, SelectionAvailability] | None = None,
        mode_availability: dict[tuple[str, str], SelectionAvailability] | None = None,
    ) -> None:
        self._components = tuple(components)
        self._strategies = dict(strategies)
        self._modes = {key: list(value) for key, value in modes.items()}
        self._mode_parameters = {
            slot: {
                option: dict(parameters)
                for option, parameters in options.items()
            }
            for slot, options in (mode_parameters or {}).items()
        }
        self._strategy_availability = dict(strategy_availability or {})
        self._mode_availability = dict(mode_availability or {})
        while self.strategy_form.rowCount():
            self.strategy_form.removeRow(0)
        while self.ins_strategy_form.rowCount():
            self.ins_strategy_form.removeRow(0)
        while self.estimator_strategy_form.rowCount():
            self.estimator_strategy_form.removeRow(0)
        while self.mission_strategy_form.rowCount():
            self.mission_strategy_form.removeRow(0)
        for target_layout in (self.mode_layout, self.mission_mode_layout):
            while target_layout.count():
                item = target_layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
        self.strategy_combos.clear()
        self.mode_checks.clear()
        self.mode_parameter_spins.clear()
        strategy_slots: defaultdict[str, list[ComponentView]] = defaultdict(list)
        mode_owners: list[ComponentView] = []
        for component in self._components:
            if component.selection_kind == "strategy":
                strategy_slots[component.selection_slot].append(component)
            elif component.selection_kind == "mode":
                mode_owners.append(component)
        for slot, candidates in sorted(
            strategy_slots.items(), key=lambda item: min(value.ui_order for value in item[1])
        ):
            combo = StandardComboBox()
            allow_none = any(candidate.allow_none for candidate in candidates)
            if allow_none:
                none_key = "strategy.estimator.none" if slot == "estimator" else "strategy.none"
                combo.addItem(self._translator.Text_Get(none_key), None)
            ordered = (
                sorted(candidates, key=lambda item: (
                    0 if item.component_id == "silverstar.algorithm.estimator.kf6" else
                    1 if item.component_id == "silverstar.algorithm.estimator.eskf15" else
                    2 if item.component_id == "silverstar.algorithm.estimator.sf6" else 3,
                    item.ui_order,
                ))
                if slot == "estimator" else sorted(candidates, key=lambda item: item.name)
            )
            for candidate in ordered:
                availability = self._strategy_availability.get(
                    candidate.component_id, SelectionAvailability(True)
                )
                name = (
                    self._translator.Text_Get("strategy.estimator.kf6")
                    if candidate.component_id == "silverstar.algorithm.estimator.kf6" else
                    self._translator.Text_Get("strategy.estimator.eskf15")
                    if candidate.component_id == "silverstar.algorithm.estimator.eskf15" else
                    self._translator.Text_Get("strategy.estimator.sf6")
                    if candidate.component_id == "silverstar.algorithm.estimator.sf6" else
                    candidate.name
                )
                combo.addItem(name, candidate.component_id)
                item = combo.model().item(combo.count() - 1)
                if item is not None:
                    item.setEnabled(availability.available)
                    if not availability.available:
                        item.setForeground(
                            combo.palette().color(
                                QPalette.ColorGroup.Disabled,
                                QPalette.ColorRole.Text,
                            )
                        )
                        item.setBackground(
                            combo.palette().color(
                                QPalette.ColorGroup.Disabled,
                                QPalette.ColorRole.Base,
                            )
                        )
                    item.setToolTip(
                        self._AvailabilityText_Get(availability, candidate.description)
                    )
            index = combo.findData(self._strategies.get(slot))
            combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(
                lambda _index, selected_slot=slot, editor=combo: self.strategyChanged.emit(
                    selected_slot, editor.currentData()
                )
            )
            target_form = {
                "alignment": self.strategy_form,
                "ins": self.ins_strategy_form,
                "estimator": self.estimator_strategy_form,
            }.get(slot, self.mission_strategy_form)
            target_form.addRow(
                QLabel(self._translator.Text_Get(f"strategy.slot.{slot}")), combo
            )
            self.strategy_combos[slot] = combo
        for owner in sorted(mode_owners, key=lambda item: item.ui_order):
            slot = owner.selection_slot
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.addWidget(
                QLabel(self._translator.Text_Get(f"mode.slot.{slot}"))
            )
            selection_note = str(owner.options.get("selection_note", ""))
            if selection_note:
                note = QLabel(selection_note)
                note.setWordWrap(True)
                note.setProperty("secondaryText", True)
                section_layout.addWidget(note)
            checks: list[StandardCheckBox] = []
            labels = owner.options.get("selection_labels", {})
            parameter_definitions = owner.options.get(
                "selection_parameters", {}
            )
            for option in owner.selection_options:
                availability = self._mode_availability.get(
                    (slot, option), SelectionAvailability(True)
                )
                label = str(labels.get(option, option))
                option_widget = QWidget()
                option_layout = QVBoxLayout(option_widget)
                option_layout.setContentsMargins(18, 0, 0, 4)
                check = StandardCheckBox(label)
                check.setProperty("selectionOption", option)
                with QSignalBlocker(check):
                    check.setChecked(option in self._modes.get(slot, []))
                check.setEnabled(availability.available)
                check.setToolTip(self._AvailabilityText_Get(availability))
                check.toggled.connect(
                    lambda _checked, selected_slot=slot: self._Mode_Emit(selected_slot)
                )
                option_layout.addWidget(check)
                parameter_form = QFormLayout()
                parameter_form.setContentsMargins(24, 0, 0, 0)
                for parameter in parameter_definitions.get(option, ()):
                    parameter_id = str(parameter["id"])
                    if parameter["type"] == "integer":
                        spin = EnterCommittedSpinBox()
                        spin.setRange(
                            int(parameter["minimum"]),
                            int(parameter["maximum"]),
                        )
                        spin.setSingleStep(1)
                    else:
                        spin = EnterCommittedDoubleSpinBox()
                        spin.setDecimals(3)
                        spin.setRange(
                            float(parameter["minimum"]),
                            float(parameter["maximum"]),
                        )
                        spin.setSingleStep(0.1)
                    spin.setButtonSymbols(
                        QAbstractSpinBox.ButtonSymbols.PlusMinus
                    )
                    spin.setObjectName(
                        f"modeParameter_{slot}_{option}_{parameter_id}"
                    )
                    spin.setSuffix(f" {parameter['unit']}")
                    value = self._mode_parameters.get(slot, {}).get(
                        option, {}
                    ).get(parameter_id, parameter["default"])
                    with QSignalBlocker(spin):
                        spin.CommittedValue_Set(
                            int(value)
                            if parameter["type"] == "integer"
                            else float(value)
                        )
                    spin.setToolTip(
                        self._translator.Text_Get(
                            "mode.parameter_range",
                            minimum=parameter["minimum"],
                            maximum=parameter["maximum"],
                            unit=parameter["unit"],
                        )
                    )
                    spin.setEnabled(
                        availability.available
                        and option in self._modes.get(slot, [])
                    )
                    spin.committed.connect(
                        lambda value, selected_slot=slot,
                        selected_option=option,
                        selected_parameter=parameter_id: self.modeParameterChanged.emit(
                            selected_slot,
                            selected_option,
                            selected_parameter,
                            value,
                        )
                    )
                    parameter_form.addRow(
                        QLabel(str(parameter["display_name"])), spin
                    )
                    self.mode_parameter_spins[
                        (slot, option, parameter_id)
                    ] = spin
                if parameter_form.rowCount():
                    option_layout.addLayout(parameter_form)
                section_layout.addWidget(option_widget)
                checks.append(check)
            section_layout.addStretch(1)
            target_layout = (
                self.mode_layout if slot == "calibration" else self.mission_mode_layout
            )
            target_layout.addWidget(section)
            self.mode_checks[slot] = checks

    def Protocols_Set(
        self,
        profiles: dict[str, tuple[ProtocolProfileView, ...]],
        selected: dict[str, tuple[str, str] | None],
    ) -> None:
        self._protocol_profiles = {
            category: tuple(values) for category, values in profiles.items()
        }
        self._selected_protocol_profiles = dict(selected)
        while self.protocol_form.count():
            item = self.protocol_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        while self.telemetry_protocol_form.count():
            item = self.telemetry_protocol_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.protocol_combos.clear()
        ordered_categories = ("telemetry", "maintenance", "logging")
        for category in ordered_categories:
            values = self._protocol_profiles.get(category, ())
            combo = StandardComboBox()
            combo.setObjectName(f"protocolProfile_{category}")
            combo.addItem(self._translator.Text_Get("selection.none"), None)
            component_count = len({value.component_id for value in values})
            for value in values:
                display_name = value.display_name
                if component_count > 1:
                    display_name = f"{value.component_name} · {display_name}"
                combo.addItem(
                    display_name,
                    (value.component_id, value.profile_id),
                )
                index = combo.count() - 1
                item = combo.model().item(index)
                if item is not None:
                    item.setEnabled(value.available)
                    if not value.available:
                        item.setForeground(
                            combo.palette().color(
                                QPalette.ColorGroup.Disabled,
                                QPalette.ColorRole.Text,
                            )
                        )
                        item.setBackground(
                            combo.palette().color(
                                QPalette.ColorGroup.Disabled,
                                QPalette.ColorRole.Base,
                            )
                        )
                    if value.availability_reason:
                        item.setToolTip(value.availability_reason)
            selection = selected.get(category)
            index = 0
            if selection is not None:
                key = (str(selection[0]), str(selection[1]))
                index = next(
                    (
                        row for row in range(1, combo.count())
                        if isinstance(data := combo.itemData(row), (tuple, list))
                        and len(data) == 2
                        and (str(data[0]), str(data[1])) == key
                    ),
                    -1,
                )
                if index < 0:
                    message = self._translator.Text_Get(
                        "protocol.selection_unavailable",
                        component=key[0], profile=key[1],
                    )
                    combo.addItem(message, key)
                    index = combo.count() - 1
                    combo.model().item(index).setEnabled(False)
                    combo.model().item(index).setToolTip(message)
                    combo.setToolTip(message)
                    combo.setProperty("validationIssue", True)
            combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(
                lambda _index, selected_category=category,
                selected_combo=combo: self._Protocol_Emit(
                    selected_category, selected_combo
                )
            )
            editor = combo
            self.protocol_combos[category] = combo
            target_form = (
                self.telemetry_protocol_form if category == "telemetry"
                else self.protocol_form
            )
            target_form.addRow(
                QLabel(
                    self._translator.Text_Get(
                        f"protocol.category.{category}"
                    )
                ),
                editor,
            )

    def _Protocol_Emit(
        self, category: str, combo: StandardComboBox
    ) -> None:
        value = combo.currentData()
        if value is None:
            self.protocolProfileChanged.emit(category, None)
            return
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return
        self.protocolProfileChanged.emit(
            category, (str(value[0]), str(value[1]))
        )

    def LoggingProtocolEnabled_Set(self, enabled: bool) -> None:
        self._logging_protocol_enabled = enabled
        self.logging_disabled_label.setVisible(not enabled)
        self.logging_table.setEnabled(enabled)
        self.logging_select_all_button.setEnabled(enabled)
        self.logging_flight_only_button.setEnabled(enabled)
        self.logging_required_only_button.setEnabled(enabled)
        self.log_decoder_export_button.setEnabled(enabled)

    def Capabilities_Set(
        self, capabilities: Iterable[CapabilityUsageView]
    ) -> None:
        self._capabilities = tuple(item for item in capabilities
                                   if not item.capability.startswith("magnetometer."))
        self.capability_table.blockSignals(True)
        self.capability_table.setRowCount(len(self._capabilities))
        for row, capability in enumerate(self._capabilities):
            capability_name = self._translator.Text_Get(
                f"capability.{capability.capability}"
            )
            capability_item = QTableWidgetItem(capability_name)
            capability_item.setToolTip(capability.capability)
            self.capability_table.setItem(row, 0, capability_item)
            self.capability_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    self._translator.Text_Get(f"capability.kind.{capability.kind}")
                ),
            )
            if capability.missing:
                status_key = "capability.status.missing"
            elif capability.ambiguous:
                status_key = "capability.status.source_required"
            elif capability.used:
                status_key = "capability.status.used"
            else:
                status_key = "capability.status.unused"
            self.capability_table.setItem(
                row, 2, QTableWidgetItem(self._translator.Text_Get(status_key))
            )
            if capability.consumers and len(capability.providers) > 1:
                source_combo = StandardComboBox()
                for instance_id, name in capability.providers:
                    source_combo.addItem(name, instance_id)
                selected_index = source_combo.findData(capability.source_instance_id)
                source_combo.setCurrentIndex(max(0, selected_index))
                source_combo.currentIndexChanged.connect(
                    lambda _index, capability_id=capability.capability, editor=source_combo: self.capabilitySourceChanged.emit(
                        capability_id, str(editor.currentData() or "")
                    )
                )
                self.capability_table.setCellWidget(row, 3, source_combo)
            else:
                self.capability_table.setItem(
                    row, 3, QTableWidgetItem(capability.source_name or "—")
                )
            purpose_text = ", ".join(
                self._translator.Text_Get(f"capability.purpose.{purpose}")
                for purpose in capability.purposes
            )
            consumer_text = ", ".join(capability.consumers)
            details = " · ".join(value for value in (consumer_text, purpose_text) if value)
            self.capability_table.setItem(row, 4, QTableWidgetItem(details or "—"))
        self.capability_table.blockSignals(False)
        self._CapabilityHeaders_Apply()

    def Streams_Set(self, streams: Iterable[LoggingStreamView]) -> None:
        updated_streams = list(streams)
        same_records = (
            len(updated_streams) == len(self._streams)
            and all(
                current.stream_id == updated.stream_id
                for current, updated in zip(self._streams, updated_streams)
            )
        )
        self.logging_table.blockSignals(True)
        if not same_records:
            self.logging_table.setRowCount(len(updated_streams))
        for row, stream in enumerate(updated_streams):
            enabled_container = self.logging_table.cellWidget(row, 0)
            enabled_check = (
                enabled_container.findChild(StandardCheckBox)
                if isinstance(enabled_container, QWidget)
                else None
            )
            decimation = self.logging_table.cellWidget(row, 4)
            cadence = self.logging_table.cellWidget(row, 5)
            if not same_records or enabled_check is None:
                enabled_check = (
                    LockedCheckBox() if stream.required else StandardCheckBox()
                )
                enabled_check.setProperty("streamId", stream.stream_id)
                enabled_check.toggled.connect(
                    lambda _checked: self.loggingChanged.emit()
                )
                enabled_container = QWidget()
                enabled_layout = QHBoxLayout(enabled_container)
                enabled_layout.setContentsMargins(8, 0, 0, 0)
                enabled_layout.addWidget(enabled_check)
                enabled_layout.addStretch(1)
                self.logging_table.setCellWidget(row, 0, enabled_container)
            if stream.policy == "DECIMATION":
                if not isinstance(decimation, EnterCommittedSpinBox):
                    if isinstance(decimation, QWidget):
                        self.logging_table.removeCellWidget(row, 4)
                        decimation.deleteLater()
                    decimation = EnterCommittedSpinBox()
                    decimation.setRange(1, 65535)
                    decimation.setMinimumWidth(190)
                    decimation.committed.connect(
                        lambda _value: self.loggingChanged.emit()
                    )
                    self.logging_table.setCellWidget(row, 4, decimation)
                with QSignalBlocker(decimation):
                    decimation.setPrefix(
                        self._translator.Text_Get("logging.decimation_prefix")
                    )
                    decimation.setSuffix(
                        self._translator.Text_Get("logging.decimation_suffix")
                    )
                    decimation.CommittedValue_Set(max(1, stream.decimation))
                    decimation.setEnabled(stream.available)
                decimation.setToolTip(
                    self._translator.Text_Get("logging.decimation_help")
                )
            else:
                if isinstance(decimation, QWidget):
                    self.logging_table.removeCellWidget(row, 4)
                    decimation.deleteLater()
                self.logging_table.setItem(row, 4, QTableWidgetItem("—"))
                decimation = None
            if not isinstance(cadence, CadenceEditor):
                if isinstance(cadence, QWidget):
                    self.logging_table.removeCellWidget(row, 5)
                    cadence.deleteLater()
                cadence = CadenceEditor(self._translator)
                cadence.changed.connect(lambda: self.loggingChanged.emit())
                self.logging_table.setCellWidget(row, 5, cadence)
            assert isinstance(enabled_check, StandardCheckBox)
            assert isinstance(cadence, CadenceEditor)
            with QSignalBlocker(enabled_check):
                if isinstance(enabled_check, LockedCheckBox):
                    enabled_check.LockedState_Set(stream.available)
                else:
                    enabled_check.setChecked(stream.enabled)
                    enabled_check.setEnabled(stream.available)
            enabled_check.setToolTip(
                self._translator.Text_Get("logging.required_tooltip")
                if stream.required and stream.available
                else stream.availability_reason
            )
            cadence.Cadence_Set(
                kind=stream.cadence_kind,
                text=stream.cadence_text,
                period_us=stream.period_us,
                enabled=stream.available,
            )
            name_item = self.logging_table.item(row, 1)
            if name_item is None:
                name_item = QTableWidgetItem()
                self.logging_table.setItem(row, 1, name_item)
            name_item.setText(stream.name)
            name_item.setToolTip(stream.name)
            purpose_item = self.logging_table.item(row, 2)
            if purpose_item is None:
                purpose_item = QTableWidgetItem()
                self.logging_table.setItem(row, 2, purpose_item)
            purpose_item.setText(
                self._translator.Text_Get(f"logging.purpose.{stream.purpose}")
            )
            level_item = self.logging_table.item(row, 3)
            if level_item is None:
                level_item = QTableWidgetItem()
                self.logging_table.setItem(row, 3, level_item)
            level_item.setText(
                self._translator.Text_Get(f"logging.level.{stream.level}")
            )
            description = stream.description or "—"
            if not stream.available and stream.availability_reason:
                description = stream.availability_reason
            elif stream.required:
                description = self._translator.Text_Get("logging.required_tooltip")
            description_item = self.logging_table.item(row, 6)
            if description_item is None:
                description_item = QTableWidgetItem()
                self.logging_table.setItem(row, 6, description_item)
            description_item.setText(description)
            description_item.setToolTip(description)
        self._streams = updated_streams
        self.logging_table.blockSignals(False)
        self._LoggingHeaders_Apply()

    def Streams_Get(self) -> tuple[LoggingStreamView, ...]:
        values: list[LoggingStreamView] = []
        for row, original in enumerate(self._streams):
            enabled_container = self.logging_table.cellWidget(row, 0)
            enabled_check = (
                enabled_container.findChild(StandardCheckBox)
                if isinstance(enabled_container, QWidget)
                else None
            )
            decimation = self.logging_table.cellWidget(row, 4)
            cadence = self.logging_table.cellWidget(row, 5)
            values.append(
                LoggingStreamView(
                    stream_id=original.stream_id,
                    name=original.name,
                    enabled=(
                        original.available and (
                            original.required
                            or bool(enabled_check and enabled_check.isChecked())
                        )
                    ),
                    decimation=(int(decimation.CommittedValue_Get()) if isinstance(decimation, EnterCommittedSpinBox) else original.decimation),
                    cadence_kind=original.cadence_kind,
                    cadence_text=original.cadence_text,
                    cadence_source=original.cadence_source,
                    description=original.description,
                    policy=original.policy,
                    period_us=(cadence.PeriodUs_Get() if isinstance(cadence, CadenceEditor) else original.period_us),
                    level=original.level,
                    purpose=original.purpose,
                    required=original.required,
                    available=original.available,
                    availability_reason=original.availability_reason,
                    record_id=original.record_id,
                    version=original.version,
                    payload_size=original.payload_size,
                )
            )
        return tuple(values)

    def Streams_SelectAllAvailable(self) -> None:
        self._LoggingSelection_Apply(include_available=True)

    def Streams_KeepFlightOnly(self) -> None:
        self._LoggingSelection_Apply(
            include_available=True, allowed_purpose="flight"
        )

    def Streams_KeepRequiredOnly(self) -> None:
        self._LoggingSelection_Apply(include_available=False)

    def _LoggingSelection_Apply(
        self, *, include_available: bool, allowed_purpose: str | None = None
    ) -> None:
        changed = False
        for row, stream in enumerate(self._streams):
            enabled_container = self.logging_table.cellWidget(row, 0)
            enabled_check = (
                enabled_container.findChild(StandardCheckBox)
                if isinstance(enabled_container, QWidget)
                else None
            )
            if enabled_check is None:
                continue
            selected = stream.available and (
                stream.required or (
                    include_available
                    and (allowed_purpose is None or stream.purpose == allowed_purpose)
                )
            )
            if enabled_check.isChecked() == selected:
                continue
            with QSignalBlocker(enabled_check):
                enabled_check.setChecked(selected)
            changed = True
        if changed:
            self.loggingChanged.emit()

    def _LoggingButtons_LayoutUpdate(self) -> None:
        buttons = (
            self.logging_select_all_button,
            self.logging_flight_only_button,
            self.logging_required_only_button,
            self.log_decoder_export_button,
        )
        spacing = max(0, self._logging_header_layout.horizontalSpacing())
        required_width = sum(button.sizeHint().width() for button in buttons)
        required_width += spacing * (len(buttons) - 1)
        available_width = self.logging_group.width() - 24
        columns = 4 if available_width >= required_width else 2
        if columns == self._logging_button_columns:
            return
        for button in buttons:
            self._logging_header_layout.removeWidget(button)
        for index, button in enumerate(buttons):
            self._logging_header_layout.addWidget(
                button,
                index // columns,
                index % columns,
                alignment=Qt.AlignmentFlag.AlignTop,
            )
        self._logging_button_columns = columns

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_logging_header_layout"):
            self._LoggingButtons_LayoutUpdate()

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        self._LoggingHeaders_Apply()
        self._LoggingButtons_LayoutUpdate()
        self.logging_select_all_button.setToolTip(
            self._translator.Text_Get("action.logging_enable_all_tooltip")
        )
        self.logging_flight_only_button.setToolTip(
            self._translator.Text_Get("action.logging_keep_flight_only_tooltip")
        )
        self.logging_required_only_button.setToolTip(
            self._translator.Text_Get("action.logging_keep_required_only_tooltip")
        )
        self._CapabilityHeaders_Apply()
        if self._components:
            self.Configuration_Set(
                self._components,
                self._strategies,
                self._modes,
                mode_parameters=self._mode_parameters,
                strategy_availability=self._strategy_availability,
                mode_availability=self._mode_availability,
            )
        self.Protocols_Set(
            self._protocol_profiles,
            self._selected_protocol_profiles,
        )
        self.Capabilities_Set(self._capabilities)

    def _Mode_Emit(self, slot: str) -> None:
        selected = [
            str(check.property("selectionOption"))
            for check in self.mode_checks.get(slot, [])
            if check.isChecked()
        ]
        for (parameter_slot, option, _parameter_id), spin in (
            self.mode_parameter_spins.items()
        ):
            if parameter_slot != slot:
                continue
            availability = self._mode_availability.get(
                (slot, option), SelectionAvailability(True)
            )
            spin.setEnabled(availability.available and option in selected)
        self.modeChanged.emit(slot, selected)

    def _LoggingHeaders_Apply(self) -> None:
        self.logging_table.setHorizontalHeaderLabels(
            [
                self._translator.Text_Get("column.enabled"),
                self._translator.Text_Get("column.record_stream"),
                self._translator.Text_Get("column.log_purpose"),
                self._translator.Text_Get("column.policy_level"),
                self._translator.Text_Get("column.decimation"),
                self._translator.Text_Get("column.cadence"),
                self._translator.Text_Get("column.description"),
            ]
        )

    def _CapabilityHeaders_Apply(self) -> None:
        self.capability_table.setHorizontalHeaderLabels(
            [
                self._translator.Text_Get("column.capability"),
                self._translator.Text_Get("column.capability_kind"),
                self._translator.Text_Get("column.status"),
                self._translator.Text_Get("column.data_source"),
                self._translator.Text_Get("column.consumers_purpose"),
            ]
        )

    def _AvailabilityText_Get(
        self,
        availability: SelectionAvailability,
        description: str = "",
    ) -> str:
        parts = [description] if description else []
        if availability.missing_capabilities:
            generic: list[str] = []
            catalog_keys = self._translator.CatalogKeys_Get()
            for capability in availability.missing_capabilities:
                reason_key = f"capability.unavailable.{capability}"
                if reason_key in catalog_keys:
                    parts.append(self._translator.Text_Get(reason_key))
                else:
                    generic.append(
                        self._translator.Text_Get(f"capability.{capability}")
                    )
            if generic:
                parts.append(
                    self._translator.Text_Get(
                        "selection.unavailable.capability",
                        missing=", ".join(generic),
                    )
                )
        if availability.missing_components:
            parts.append(
                self._translator.Text_Get(
                    "selection.unavailable.component",
                    missing=", ".join(availability.missing_components),
                )
            )
        return "\n".join(parts)
