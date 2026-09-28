from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage


class AirLinkPage(ScrollableLocalizedPage):
    configurationChanged = Signal(str, object)

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.air_link", "page.air_link.description")
        form = QFormLayout()
        self.fields: dict[str, object] = {}
        for name, key, minimum, maximum in (
            ("spreading_factor", "field.air_sf", 5, 12),
            ("bandwidth_hz", "field.air_bandwidth", 1000, 2000000),
            ("preamble_symbols", "field.air_preamble", 4, 65535),
            ("packet_mtu", "field.air_mtu", 1, 255),
        ):
            label = QLabel()
            self.Text_Register(label, key)
            value = QSpinBox()
            value.setRange(minimum, maximum)
            value.valueChanged.connect(
                lambda selected, field=name: self.configurationChanged.emit(field, selected)
            )
            form.addRow(label, value)
            self.fields[name] = value
        frequency_label = QLabel()
        self.Text_Register(frequency_label, "field.air_frequency")
        frequency = QDoubleSpinBox()
        frequency.setRange(100.0, 6000.0)
        frequency.setDecimals(3)
        frequency.setSuffix(" MHz")
        frequency.valueChanged.connect(
            lambda selected: self.configurationChanged.emit(
                "frequency_hz", round(selected * 1000000)
            )
        )
        form.insertRow(0, frequency_label, frequency)
        self.fields["frequency_hz"] = frequency
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

    def Configuration_Set(self, link, issues) -> None:
        for name, widget in self.fields.items():
            widget.blockSignals(True)
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(getattr(link, name) / 1000000)
            elif isinstance(widget, QSpinBox):
                widget.setValue(getattr(link, name))
            else:
                widget.setCurrentIndex(max(0, widget.findData(getattr(link, name))))
            widget.blockSignals(False)
        self.crc.blockSignals(True)
        self.crc.setChecked(link.crc_enabled)
        self.crc.blockSignals(False)
        self.status.setText(
            "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
            if issues else self._translator.Text_Get("status.air_link_ready")
        )


class GroundTargetPage(ScrollableLocalizedPage):
    enabledChanged = Signal(bool)
    configurationChanged = Signal(str, object)
    assignmentChanged = Signal(str, str)
    importRequested = Signal(bool)

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
        import_row.addWidget(self.import_ioc)
        import_row.addWidget(self.import_directory)
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
        radio_layout = QVBoxLayout()
        radio_layout.addLayout(radio_form)
        radio_layout.addLayout(self.assignment_form)
        self.root_layout.addWidget(self.Group_Create("group.ground_radio", radio_layout))
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
        self.baudrate = QSpinBox()
        self.baudrate.setRange(1200, 3000000)
        self.baudrate.valueChanged.connect(
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
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.root_layout.addWidget(self.status)
        self.root_layout.addStretch(1)

    def Configuration_Set(self, ground, boards, radios, requirements, issues) -> None:
        for widget in (self.enabled, self.board, self.radio, self.module, self.pc_interface,
                       self.pc_resource, self.baudrate):
            widget.blockSignals(True)
        self.enabled.setChecked(ground.enabled)
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
        for title, identity in radios:
            self.radio.addItem(title, identity)
        self.radio.setCurrentIndex(max(0, self.radio.findData(ground.radio_plugin)))
        self.module.clear()
        self.module.addItem("—", "")
        for title, identity in requirements.get("modules", ()):
            self.module.addItem(title, identity)
        self.module.setCurrentIndex(max(0, self.module.findData(ground.module_variant)))
        self.pc_interface.setCurrentIndex(max(0, self.pc_interface.findData(ground.pc_interface)))
        self.pc_resource.clear()
        self.pc_resource.addItem("—", "")
        for resource in ground.hardware.resources:
            if resource.kind == "uart":
                self.pc_resource.addItem(resource.resource_id, resource.resource_id)
        self.pc_resource.setCurrentIndex(max(0, self.pc_resource.findData(ground.pc_resource)))
        self.baudrate.setValue(ground.baudrate)
        self.build_summary.setText(
            f"{ground.build.make_command} · "
            f"{ground.build.toolchain_prefix}gcc · GroundStation.code-workspace"
        )
        for widget in (self.enabled, self.board, self.radio, self.module, self.pc_interface,
                       self.pc_resource, self.baudrate):
            widget.blockSignals(False)
        while self.assignment_form.rowCount():
            self.assignment_form.removeRow(0)
        self.assignments.clear()
        for name, kind in requirements.get("resources", ()):
            combo = QComboBox()
            combo.addItem("—", "")
            for resource in ground.hardware.resources:
                if resource.kind == kind:
                    combo.addItem(resource.resource_id, resource.resource_id)
            combo.setCurrentIndex(max(
                0, combo.findData(ground.resource_assignments.get(f"radio0:{name}", ""))
            ))
            combo.currentIndexChanged.connect(
                lambda _index, requirement=name, selected=combo:
                self.assignmentChanged.emit(requirement, selected.currentData() or "")
            )
            self.assignment_form.addRow(f"{name} ({kind})", combo)
            self.assignments[name] = combo
        self.status.setText(
            "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
            if issues else self._translator.Text_Get("status.ground_ready")
        )
