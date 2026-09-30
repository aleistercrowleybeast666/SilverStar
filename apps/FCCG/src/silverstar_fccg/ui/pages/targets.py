from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox, EnterCommittedSpinBox
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage


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


class GroundTargetPage(ScrollableLocalizedPage):
    enabledChanged = Signal(bool)
    configurationChanged = Signal(str, object)
    assignmentChanged = Signal(str, str)
    importRequested = Signal(bool)
    saveInstanceRequested = Signal()
    generateRequested = Signal()

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.ground", "page.ground.description")
        self.enabled = QCheckBox()
        self.Text_Register(self.enabled, "field.ground_enabled")
        self.enabled.toggled.connect(self.enabledChanged.emit)
        self.root_layout.addWidget(self.enabled)
        hardware_form = QFormLayout()
        self.hardware_summary = QLabel("—")
        self.hardware_summary.setWordWrap(True)
        label = QLabel()
        self.Text_Register(label, "field.ground_hardware")
        hardware_form.addRow(label, self.hardware_summary)
        board_label = QLabel()
        self.Text_Register(board_label, "field.ground_board")
        self.board = QComboBox()
        self.board.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("board", self.board.currentData())
        )
        hardware_form.addRow(board_label, self.board)
        self.root_layout.addWidget(self.Group_Create("group.ground_hardware", hardware_form))
        import_row = QHBoxLayout()
        self.import_ioc = QPushButton()
        self.Text_Register(self.import_ioc, "action.import_cubemx_ioc")
        self.import_ioc.clicked.connect(lambda: self.importRequested.emit(False))
        self.import_directory = QPushButton()
        self.Text_Register(self.import_directory, "action.import_cubemx_directory")
        self.import_directory.clicked.connect(lambda: self.importRequested.emit(True))
        self.save_instance = QPushButton()
        self.Text_Register(self.save_instance, "action.save_pcb_instance")
        self.save_instance.clicked.connect(self.saveInstanceRequested.emit)
        import_row.addWidget(self.import_ioc)
        import_row.addWidget(self.import_directory)
        import_row.addWidget(self.save_instance)
        import_row.addStretch(1)
        self.root_layout.addLayout(import_row)
        radio_form = QFormLayout()
        label = QLabel()
        self.Text_Register(label, "field.ground_radio")
        self.radio = QComboBox()
        self.radio.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("radio_plugin", self.radio.currentData())
        )
        radio_form.addRow(label, self.radio)
        label = QLabel()
        self.Text_Register(label, "field.ground_module")
        self.module = QComboBox()
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
        self.root_layout.addWidget(self.Group_Create(
            "group.ground_radio_resources", self.assignment_form
        ))
        pc_form = QFormLayout()
        label = QLabel()
        self.Text_Register(label, "field.ground_pc_interface")
        self.pc_interface = QComboBox()
        self.pc_interface.addItem("—", "")
        self.pc_interface.addItem("UART Serial", "uart")
        self.pc_interface.addItem("USB CDC Virtual Serial", "usb_cdc")
        self.pc_interface.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("pc_interface", self.pc_interface.currentData())
        )
        pc_form.addRow(label, self.pc_interface)
        label = QLabel()
        self.Text_Register(label, "field.ground_pc_resource")
        self.pc_resource = QComboBox()
        self.pc_resource.currentIndexChanged.connect(
            lambda: self.configurationChanged.emit("pc_resource", self.pc_resource.currentData())
        )
        pc_form.addRow(label, self.pc_resource)
        label = QLabel()
        self.Text_Register(label, "field.ground_baud")
        self.baudrate = EnterCommittedSpinBox()
        self.baudrate.setRange(1200, 3000000)
        self.baudrate.committed.connect(
            lambda selected: self.configurationChanged.emit("baudrate", selected)
        )
        pc_form.addRow(label, self.baudrate)
        self.root_layout.addWidget(self.Group_Create("group.ground_pc", pc_form))
        build_form = QFormLayout()
        build_label = QLabel()
        self.Text_Register(build_label, "field.ground_build")
        self.build_summary = QLabel("—")
        self.build_summary.setWordWrap(True)
        build_form.addRow(build_label, self.build_summary)
        self.root_layout.addWidget(self.Group_Create("group.ground_build", build_form))
        self.generate_button = QPushButton()
        self.Text_Register(self.generate_button, "action.generate_ground_project")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(
            lambda _checked=False: self.generateRequested.emit()
        )
        self.root_layout.addWidget(self.generate_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.root_layout.addWidget(self.status)
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
        self.board.clear()
        self.board.addItem("Custom CubeMX", "")
        for title, identity in boards:
            self.board.addItem(title, identity)
        self.board.setCurrentIndex(max(0, self.board.findData(ground.board)))
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
        for resource in ground.hardware.resources:
            if resource.kind == "uart":
                self.pc_resource.addItem(resource.resource_id, resource.resource_id)
        self.pc_resource.setCurrentIndex(max(0, self.pc_resource.findData(ground.pc_resource)))
        self.baudrate.CommittedValue_Set(ground.baudrate)
        self.build_summary.setText(
            f"{ground.build.make_command} · "
            f"{ground.build.toolchain_prefix}gcc · Ground_Station.code-workspace"
        )
        for widget in (self.enabled, self.board, self.radio, self.module, self.pc_interface,
                       self.pc_resource, self.baudrate):
            widget.blockSignals(False)
        required = tuple(requirements.get("resources", ()))
        signature = (
            required,
            tuple((resource.resource_id, resource.kind)
                  for resource in ground.hardware.resources),
        )
        if signature != self._assignment_signature:
            for combo in self.assignments.values():
                combo.blockSignals(True)
            while self.assignment_form.rowCount():
                self.assignment_form.removeRow(0)
            self.assignments.clear()
            for name, kind in required:
                combo = QComboBox()
                combo.addItem("—", "")
                for resource in ground.hardware.resources:
                    if resource.kind == kind:
                        combo.addItem(resource.resource_id, resource.resource_id)
                combo.currentIndexChanged.connect(
                    lambda _index, requirement=name, selected=combo:
                    self.assignmentChanged.emit(requirement, selected.currentData() or "")
                )
                self.assignment_form.addRow(f"{name} ({kind})", combo)
                self.assignments[name] = combo
            self._assignment_signature = signature
        for name, combo in self.assignments.items():
            combo.blockSignals(True)
            combo.setCurrentIndex(max(
                0, combo.findData(ground.resource_assignments.get(f"radio0:{name}", ""))
            ))
            combo.blockSignals(False)
        self.status.setText(
            "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
            if issues else self._translator.Text_Get("status.ground_ready")
        )
