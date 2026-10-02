from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPalette
from silverstar_fccg.ui.widgets import StandardComboBox
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox, EnterCommittedSpinBox
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.pages.components import BoardHardwarePage
from silverstar_fccg.core.view_models import BoardCompatibilityView, ResourceRequirementView, PlatformMatchView


class AirLinkPage(ScrollableLocalizedPage):
    configurationChanged = Signal(str, object)
    endpointPowerChanged = Signal(str, int)

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.telemetry_configuration", "page.telemetry_configuration.description")
        form = QFormLayout()
        self.fields: dict[str, object] = {}
        self._radio_choices: dict[str, tuple[tuple[str, str], ...]] = {}
        self._radio_technologies: set[str] = set()
        for name, key, minimum, maximum in (
            ("spreading_factor", "field.air_sf", 5, 12),
            ("bandwidth_hz", "field.air_bandwidth", 1000, 2000000),
            ("preamble_symbols", "field.air_preamble", 4, 65535),
            ("packet_mtu", "field.air_mtu", 1, 255),
        ):
            label = QLabel()
            self.Text_Register(label, key)
            value = EnterCommittedSpinBox()
            value.setRange(minimum, maximum)
            value.committed.connect(
                lambda selected, field=name: self.configurationChanged.emit(field, selected)
            )
            form.addRow(label, value)
            self.fields[name] = value
        frequency_label = QLabel()
        self.Text_Register(frequency_label, "field.air_frequency")
        frequency = EnterCommittedDoubleSpinBox()
        frequency.setRange(0.0, 0.0)
        frequency.setEnabled(False)
        frequency.setDecimals(3)
        frequency.setSuffix(" MHz")
        frequency.committed.connect(
            lambda selected: self.configurationChanged.emit(
                "frequency_hz", round(selected * 1000000)
            )
        )
        frequency.rejected.connect(
            lambda _draft: self.status.setText(
                "AIR_LINK_FREQUENCY_OUT_OF_RANGE: " + frequency.toolTip()
            )
        )
        form.insertRow(0, frequency_label, frequency)
        self.fields["frequency_hz"] = frequency
        self.flight_tx_power = EnterCommittedSpinBox()
        self._ground_power_available = False
        self.flight_tx_power.setRange(0, 0)
        self.flight_tx_power.setEnabled(False)
        self.flight_tx_power.setSuffix(" dBm")
        self.flight_tx_power.committed.connect(
            lambda value: self.endpointPowerChanged.emit("flight", value)
        )
        self.flight_tx_power.rejected.connect(
            lambda _draft: self.status.setText(
                "AIR_LINK_TX_POWER_UNSUPPORTED: " + self.flight_tx_power.toolTip()
            )
        )
        flight_power_label = QLabel()
        self.Text_Register(flight_power_label, "field.flight_tx_power")
        form.addRow(flight_power_label, self.flight_tx_power)
        self.ground_tx_power = EnterCommittedSpinBox()
        self.ground_tx_power.setRange(0, 0)
        self.ground_tx_power.setEnabled(False)
        self.ground_tx_power.setSuffix(" dBm")
        self.ground_tx_power.committed.connect(
            lambda value: self.endpointPowerChanged.emit("ground", value)
        )
        self.ground_tx_power.rejected.connect(
            lambda _draft: self.status.setText(
                "AIR_LINK_TX_POWER_UNSUPPORTED: " + self.ground_tx_power.toolTip()
            )
        )
        ground_power_label = QLabel()
        self.Text_Register(ground_power_label, "field.ground_tx_power")
        form.addRow(ground_power_label, self.ground_tx_power)
        for name, key, choices in (
            ("radio_technology", "field.air_technology",
             (("LoRa", "lora"), ("Packet Radio / Other", "packet"))),
            ("radio_family", "field.air_family", (("SX128x", "sx128x"),)),
            ("phy_mode", "field.air_phy", (("LoRa", "lora"),)),
            ("coding_rate", "field.air_coding_rate", (("4/5", "4/5"),)),
            ("header_mode", "field.air_header", (("Explicit", "explicit"),)),
            ("iq_mode", "field.air_iq", (("Normal", "normal"),)),
        ):
            label = QLabel()
            self.Text_Register(label, key)
            value = QComboBox()
            for title, identity in choices:
                value.addItem(title, identity)
            self._radio_choices[name] = choices
            value.currentIndexChanged.connect(
                lambda _index, field=name, combo=value:
                self.configurationChanged.emit(field, combo.currentData())
            )
            form.addRow(label, value)
            self.fields[name] = value
        crc_label = QLabel()
        self.Text_Register(crc_label, "field.air_crc")
        self.crc = QCheckBox()
        self.crc.setObjectName("standardCheckBox")
        self.crc.toggled.connect(
            lambda checked: self.configurationChanged.emit("crc_enabled", checked)
        )
        form.addRow(crc_label, self.crc)
        self.root_layout.addWidget(self.Group_Create("group.air_link", form))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.root_layout.addWidget(self.status)
        self.root_layout.addStretch(1)

    def RadioOptions_Set(self, radios: tuple[object, ...]) -> None:
        self._radio_technologies = {radio.technology for radio in radios}

    def Configuration_Set(self, link, issues) -> None:
        for name, widget in self.fields.items():
            widget.blockSignals(True)
            if isinstance(widget, QDoubleSpinBox):
                widget.CommittedValue_Set(getattr(link, name) / 1000000)
            elif isinstance(widget, QSpinBox):
                widget.CommittedValue_Set(getattr(link, name))
            else:
                widget.clear()
                for title, identity in self._radio_choices[name]:
                    widget.addItem(title, identity)
                    item = widget.model().item(widget.count() - 1)
                    if (name == "radio_technology" and
                            identity not in self._radio_technologies and item is not None):
                        item.setEnabled(False)
                        item.setToolTip("No installed radio supports this technology")
                selected = getattr(link, name)
                if widget.findData(selected) < 0:
                    widget.addItem(f"{selected} — unavailable", selected)
                    item = widget.model().item(widget.count() - 1)
                    if item is not None:
                        item.setEnabled(False)
                        item.setToolTip("Selected AIR option is unavailable")
                widget.setCurrentIndex(max(0, widget.findData(selected)))
            widget.blockSignals(False)
        self.crc.blockSignals(True)
        self.crc.setChecked(link.crc_enabled)
        self.crc.blockSignals(False)
        self.status.setText(
            "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
            if issues else self._translator.Text_Get("status.air_link_ready")
        )

    def EndpointPowers_Set(self, flight_power: int, ground_power: int, ground_enabled: bool) -> None:
        self.flight_tx_power.CommittedValue_Set(flight_power)
        self.ground_tx_power.CommittedValue_Set(ground_power)
        self.ground_tx_power.setEnabled(ground_enabled and self._ground_power_available)

    def RadioConstraints_Set(
        self, frequency_range_hz: tuple[int, int] | None,
        flight_powers_dbm: tuple[int, ...],
        ground_powers_dbm: tuple[int, ...],
        ground_enabled: bool,
    ) -> None:
        self._ground_power_available = bool(ground_powers_dbm)
        frequency = self.fields["frequency_hz"]
        if frequency_range_hz is None:
            frequency.setEnabled(False)
        else:
            low, high = frequency_range_hz
            frequency.setRange(low / 1000000, high / 1000000)
            frequency.setToolTip(f"Validated module frequency: {low / 1000000:g}–{high / 1000000:g} MHz")
            frequency.setEnabled(True)
        for widget, powers, enabled in (
            (self.flight_tx_power, flight_powers_dbm, True),
            (self.ground_tx_power, ground_powers_dbm, ground_enabled),
        ):
            if powers:
                widget.setRange(min(powers), max(powers))
                widget.setToolTip("Validated module TX power: " +
                                  ", ".join(str(value) for value in powers) + " dBm")
            widget.setEnabled(enabled and bool(powers))


class GroundTargetPage(BoardHardwarePage):
    enabledChanged = Signal(bool)
    configurationChanged = Signal(str, object)
    assignmentChanged = Signal(str, str)
    importRequested = Signal(bool)
    saveInstanceRequested = Signal()
    generateRequested = Signal()

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, target="ground")
        self.enabled = QCheckBox()
        self.enabled.setObjectName("standardCheckBox")
        self.Text_Register(self.enabled, "field.ground_enabled")
        self.enabled.toggled.connect(self.enabledChanged.emit)
        self.root_layout.addWidget(self.enabled)
        self.board = self.board_combo
        self.hardware_summary = self.platform_values["part"]
        self.import_ioc = self.import_ioc_button
        self.import_directory = self.import_directory_button
        self.save_instance = self.export_button
        self.boardChanged.connect(lambda value: self.configurationChanged.emit("board", value))
        self.customSelected.connect(lambda: self.configurationChanged.emit("board", ""))
        self.importIocRequested.connect(lambda: self.importRequested.emit(False))
        self.importDirectoryRequested.connect(lambda: self.importRequested.emit(True))
        self.exportRequested.connect(self.saveInstanceRequested.emit)
        radio_form = QFormLayout()
        label = QLabel()
        self.Text_Register(label, "field.ground_radio")
        self.radio = StandardComboBox()
        self.radio.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("radio_plugin", self.radio.currentData())
        )
        radio_form.addRow(label, self.radio)
        label = QLabel()
        self.Text_Register(label, "field.ground_module")
        self.module = StandardComboBox()
        self.module.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("module_variant", self.module.currentData())
        )
        radio_form.addRow(label, self.module)
        self.assignment_form = QFormLayout()
        self.assignments: dict[str, QComboBox] = {}
        self._assignment_signature: tuple[object, ...] = ()
        self.radio_selection_group = self.Group_Create(
            "group.ground_radio", radio_form
        )
        pc_form = QFormLayout()
        label = QLabel()
        self.Text_Register(label, "field.ground_pc_interface")
        self.pc_interface = StandardComboBox()
        self.pc_interface.addItem("—", "")
        self.pc_interface.addItem("UART Serial", "uart")
        self.pc_interface.addItem("USB CDC Virtual Serial", "usb_cdc")
        self.pc_interface.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("pc_interface", self.pc_interface.currentData())
        )
        pc_form.addRow(label, self.pc_interface)
        label = QLabel()
        self.Text_Register(label, "field.ground_pc_resource")
        self.pc_resource_label = label
        self.pc_form = pc_form
        self.pc_resource = StandardComboBox()
        self.pc_resource.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("pc_resource", self.pc_resource.currentData())
        )
        pc_form.addRow(label, self.pc_resource)
        self.pc_resource_source = QLabel()
        self.pc_resource_source.setWordWrap(True)
        pc_form.addRow(self.pc_resource_source)
        self.pc_resource_notice = QLabel()
        self.pc_resource_notice.setWordWrap(True)
        pc_form.addRow(self.pc_resource_notice)
        label = QLabel()
        self.Text_Register(label, "field.ground_baud")
        self.baudrate = EnterCommittedSpinBox()
        self.baudrate.setRange(1200, 3000000)
        self.baudrate.committed.connect(
            lambda selected: self.configurationChanged.emit("baudrate", selected)
        )
        pc_form.addRow(label, self.baudrate)
        self.pc_group = self.Group_Create("group.ground_pc", pc_form)
        self.root_layout.addWidget(self.pc_group)
        build_form = QFormLayout()
        build_label = QLabel()
        self.Text_Register(build_label, "field.ground_build")
        self.build_summary = QLabel("—")
        self.build_summary.setWordWrap(True)
        build_form.addRow(build_label, self.build_summary)
        self.build_group = self.Group_Create("group.ground_build", build_form)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.root_layout.addStretch(1)

    def Configuration_Set(self, ground, boards, radios, requirements, issues) -> None:
        for widget in (self.enabled, self.board, self.radio, self.module, self.pc_interface,
                       self.pc_resource, self.baudrate):
            widget.blockSignals(True)
        self.enabled.setChecked(ground.enabled)
        self.generate_button.setEnabled(ground.enabled)
        self.save_instance.setEnabled(
            ground.hardware.mode == "custom"
            and bool(ground.hardware.snapshot_id)
            and bool(ground.hardware.build_sources)
        )
        self.hardware_summary.setText(
            f"{ground.hardware.mcu or '—'} · {ground.hardware.source_label or ground.hardware.mode}"
        )
        self.Boards_Set((BoardCompatibilityView(identity, title, True) for title, identity in boards),
            ground.board, custom_available=True, custom_selected=ground.hardware.mode == "custom",
            custom_ready=bool(ground.hardware.build_sources), prepared=not issues,
            hardware_mode=ground.hardware.mode, assignment_confirmed=not issues)
        self.Platform_Set(PlatformMatchView(hardware_source=ground.hardware.source_kind,
            detected_part=ground.hardware.mcu or str(ground.hardware.inventory.get("mcu_part", "")),
            detected_family=str(ground.hardware.inventory.get("mcu_family", "")),
            detected_package=str(ground.hardware.inventory.get("package", "")),
            detected_core=str(ground.hardware.inventory.get("core", "")),
            cubemx_version=ground.hardware.cubemx_version, firmware_package=ground.hardware.firmware_package))
        self.radio.clear()
        self.radio.addItem("—", "")
        for title, identity, available, reason in radios:
            self.radio.addItem(title, identity)
            item = self.radio.model().item(self.radio.count() - 1)
            if item is not None:
                item.setEnabled(available)
                item.setToolTip(reason)
                if not available:
                    item.setForeground(self.radio.palette().color(
                        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
        if ground.radio_plugin and self.radio.findData(ground.radio_plugin) < 0:
            self.radio.addItem(f"{ground.radio_plugin} — unavailable", ground.radio_plugin)
            item = self.radio.model().item(self.radio.count() - 1)
            if item is not None:
                item.setEnabled(False)
                item.setToolTip("AIR_LINK_NO_RADIO: selected radio plugin is unavailable")
        self.radio.setCurrentIndex(max(0, self.radio.findData(ground.radio_plugin)))
        self.module.clear()
        self.module.addItem("—", "")
        for title, identity in requirements.get("modules", ()):
            self.module.addItem(title, identity)
        if ground.module_variant and self.module.findData(ground.module_variant) < 0:
            self.module.addItem(f"{ground.module_variant} — unavailable", ground.module_variant)
            item = self.module.model().item(self.module.count() - 1)
            if item is not None:
                item.setEnabled(False)
                item.setToolTip("AIR_LINK_NO_RADIO: selected module variant is unavailable")
        self.module.setCurrentIndex(max(0, self.module.findData(ground.module_variant)))
        self.pc_interface.setCurrentIndex(max(0, self.pc_interface.findData(ground.pc_interface)))
        uart_selected = ground.enabled and ground.pc_interface == "uart"
        self.pc_resource.setEnabled(uart_selected)
        self.baudrate.setEnabled(uart_selected)
        self.pc_resource.clear()
        self.pc_resource.addItem("—", "")
        uarts = tuple(resource for resource in ground.hardware.resources if resource.kind == "uart")
        for resource in uarts:
            physical = resource.metadata.get("physical_resource", resource.resource_id)
            self.pc_resource.addItem(f"{physical} · {resource.resource_id}", resource.resource_id)
        missing = bool(ground.pc_resource) and self.pc_resource.findData(ground.pc_resource) < 0
        if missing:
            self.pc_resource.addItem(
                self._translator.Text_Get("ground.uart_unavailable", resource=ground.pc_resource),
                ground.pc_resource,
            )
            self.pc_resource.model().item(self.pc_resource.count() - 1).setEnabled(False)
        self.pc_resource.setCurrentIndex(max(0, self.pc_resource.findData(ground.pc_resource)))
        reason = ("ground.uart_select_hardware" if not ground.hardware.inventory else
                  "ground.uart_none" if not uarts else
                  "ground.uart_missing_binding" if missing else "")
        self.pc_resource_notice.setVisible(ground.pc_interface == "uart" and bool(reason))
        self.pc_resource_notice.setText(self._translator.Text_Get(reason) if reason else "")
        self.pc_resource.setToolTip(self.pc_resource_notice.text())
        self.pc_resource.setEnabled(uart_selected and bool(uarts))
        selected_uart = next((item for item in uarts if item.resource_id == ground.pc_resource), None)
        redundant = len(uarts) <= 1 and (selected_uart is not None or not uarts)
        self.pc_form.setRowVisible(self.pc_resource, ground.pc_interface == "uart" and not redundant)
        self.pc_resource_source.setVisible(ground.pc_interface == "uart" and selected_uart is not None)
        self.pc_resource_source.setText(self._translator.Text_Get(
            "ground.uart_binding_source",
            physical=selected_uart.metadata.get("physical_resource", selected_uart.resource_id),
            resource=selected_uart.resource_id,
            source=ground.hardware.source_label or ground.board or ground.hardware.source_kind,
        ) if selected_uart is not None else "")
        self.baudrate.CommittedValue_Set(ground.baudrate)
        self.build_summary.setText(
            f"{ground.build.make_command} · "
            f"{ground.build.toolchain_prefix}gcc · Ground_Station.code-workspace"
        )
        for widget in (self.enabled, self.board, self.radio, self.module, self.pc_interface,
                       self.pc_resource, self.baudrate):
            widget.blockSignals(False)
        required = tuple(requirements.get("resources", ()))
        fixed_resources = requirements.get("fixed_resources", {})
        resource_views = tuple(ResourceRequirementView(kind=kind, name=name, key=name,
            fixed=name in fixed_resources,
            assignment=ground.resource_assignments.get(f"radio0:{name}", ""),
            candidates=tuple(item.resource_id for item in ground.hardware.resources if item.kind == kind))
            for name, kind in required)
        self.Resources_Set(resource_views, not issues, hardware_selected=ground.hardware.mode != "unselected")
        self.assignments = {name: self.resource_table.cellWidget(row, 3) for row, (name, _kind) in enumerate(required)}
        # Ground generation checks the fixed radio/PC contracts; preparation
        # operations requiring flight task ownership do not apply to Ground.
        for button in (self.manual_validation_button, self.auto_button):
            button.setEnabled(False)
        self.prepare_button.setEnabled(bool(boards))
        self.prepare_button.setToolTip("" if boards else self._translator.Text_Get("board.no_provider"))
        self.i2c_pullup_group.setVisible(False)
        self.status.setText(
            self._translator.Text_Get("status.ground_disabled") if not ground.enabled else
            "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
            if issues else self._translator.Text_Get("status.ground_ready")
        )
        self.generate_button.setToolTip(self._translator.Text_Get(
            "status.ground_disabled" if not ground.enabled else
            "status.ground_configuration_required" if issues else "status.ground_ready"))
        self.generate_button.setEnabled(ground.enabled and ground.hardware.mode != "unselected")
        self.save_instance.setEnabled(
            ground.hardware.mode == "custom" and bool(ground.hardware.snapshot_id)
            and bool(ground.hardware.build_sources)
        )
