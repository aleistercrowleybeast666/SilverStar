from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from silverstar_fccg.project.model import GroundRadioConfigurations_Get, GroundRadioConfiguration
from silverstar_fccg.ui.widgets import StandardComboBox


class GroundRadioInstancesEditor(QWidget):
    configurationChanged = Signal(object, str)

    def __init__(self, translator):
        super().__init__()
        self._translator = translator
        self._ground = None
        self._contracts = {}
        self._choices = ()
        self._module_availability = {}
        self._radios = ()
        self.rows = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        initial_form = QFormLayout()
        self.initial_label = QLabel()
        self.initial_instance = StandardComboBox()
        self.initial_instance.currentIndexChanged.connect(self._Initial_Change)
        initial_form.addRow(self.initial_label, self.initial_instance)
        layout.addLayout(initial_form)
        self.rows_layout = QVBoxLayout()
        layout.addLayout(self.rows_layout)
        self.add_button = QPushButton()
        self.add_button.setObjectName("groundRadioAddButton")
        self.add_button.clicked.connect(self._Add)
        add_form = QFormLayout()
        add_form.addRow(QLabel(), self.add_button)
        layout.addLayout(add_form)
        self.power_editor = QWidget()
        self.power_form = QFormLayout(self.power_editor)
        self.power_form.setContentsMargins(0, 0, 0, 0)
        self.Language_Apply(translator)

    def Language_Apply(self, translator):
        self._translator = translator
        self.note.setText(translator.Text_Get("ground.radio_order_note"))
        self.initial_label.setText(translator.Text_Get("ground.initial_radio"))
        self.add_button.setText(translator.Text_Get(
            "action.add_device", device=translator.Text_Get("device.class.telemetry")))

    def Configuration_Set(self, ground, choices, contracts, module_availability=None):
        self._ground = ground
        self._contracts = contracts
        self._choices = tuple(choices)
        self._module_availability = module_availability or {}
        self._radios = tuple(radio for radio in GroundRadioConfigurations_Get(ground) if radio.plugin)
        self.rows.clear()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            item.widget().deleteLater()
        while self.power_form.rowCount():
            self.power_form.removeRow(0)
        self.Language_Apply(self._translator)
        with QSignalBlocker(self.initial_instance):
            self.initial_instance.clear()
            for radio in self._radios:
                self.initial_instance.addItem(radio.instance_id, radio.instance_id)
            self.initial_instance.setCurrentIndex(self.initial_instance.findData(ground.active_radio_instance))
        self.initial_instance.setEnabled(ground.enabled and len(self._radios) > 1)
        self.initial_instance.setVisible(len(self._radios) > 1)
        self.initial_label.setVisible(len(self._radios) > 1)
        self.add_button.setEnabled(ground.enabled and len(self._radios) < 4 and
            any(self._ModuleAvailability_Get(identity, module_id, available, reason)[0]
                for _, identity, available, reason in choices
                for module_id in (contracts[identity].modules if identity in contracts else ())))
        self.power_editor.setVisible(bool(self._radios))
        displayed = self._radios or (GroundRadioConfiguration("radio0", "", "", ground.tx_power_dbm),)
        for index, radio in enumerate(displayed):
            group = QWidget()
            group.setObjectName("groundRadioRow_" + radio.instance_id)
            form = QFormLayout(group)
            form.setContentsMargins(0, 0, 0, 0)
            suffix = radio.instance_id.removeprefix("radio")
            number = int(suffix) if suffix.isdecimal() else radio.instance_id
            title = self._translator.Text_Get("device.instance.telemetry", index=number)
            instance_title = QLabel(title)
            instance_title.setToolTip(radio.instance_id)
            plugin = StandardComboBox()
            plugin.setObjectName("groundRadioModule_" + radio.instance_id)
            plugin.addItem(self._translator.Text_Get("selection.none"), ("", ""))
            for title, identity, available, reason in choices:
                contract = contracts.get(identity)
                for module_id, data in (contract.modules.items() if contract is not None else ()):
                    module_available, module_reason = self._ModuleAvailability_Get(
                        identity, module_id, available, reason)
                    plugin.addItem(str(data.get("display_name", data.get("model", title))), (identity, module_id))
                    plugin.model().item(plugin.count() - 1).setEnabled(module_available)
                    plugin.setItemData(plugin.count() - 1, module_reason, Qt.ItemDataRole.ToolTipRole)
            selected = (radio.plugin, radio.module_variant)
            if plugin.findData(selected) < 0:
                plugin.addItem(f"{radio.plugin} / {radio.module_variant}", selected)
                plugin.model().item(plugin.count() - 1).setEnabled(False)
            plugin.setCurrentIndex(plugin.findData(selected))
            plugin.currentIndexChanged.connect(lambda _index, identity=radio.instance_id, combo=plugin:
                self._Selection_Change(identity, combo.currentData()))
            form.addRow(instance_title, plugin)
            contract = contracts.get(radio.plugin)
            modules = contract.modules if contract is not None else {}
            power = StandardComboBox()
            power.setObjectName("groundRadioPower_" + radio.instance_id)
            supported = tuple(modules.get(radio.module_variant, {}).get("supported_tx_powers_dbm", ()))
            for value in supported:
                power.addItem(f"{value} dBm", value)
            if power.findData(radio.tx_power_dbm) < 0:
                power.addItem(f"{radio.tx_power_dbm} dBm", radio.tx_power_dbm)
                power.model().item(power.count() - 1).setEnabled(False)
            power.setCurrentIndex(power.findData(radio.tx_power_dbm))
            power.setEnabled(ground.enabled and bool(supported))
            power.currentIndexChanged.connect(lambda _index, identity=radio.instance_id, combo=power:
                self._Field_Change(identity, "tx_power_dbm", combo.currentData()))
            self.power_form.addRow(
                self._translator.Text_Get("ground.radio_power", title=instance_title.text()), power)
            controls = {"title": instance_title, "selection": plugin, "tx_power_dbm": power}
            button = QPushButton(self._translator.Text_Get("action.remove_device"))
            button.setObjectName("groundRadio_remove_" + radio.instance_id)
            button.setEnabled(ground.enabled and bool(radio.plugin))
            button.clicked.connect(lambda _checked=False, identity=radio.instance_id: self._Remove(identity))
            form.addRow(QLabel(), button)
            controls["remove"] = button
            plugin.setEnabled(ground.enabled)
            self.rows[radio.instance_id] = controls
            self.rows_layout.addWidget(group)

    def _Commit(self, radios, active):
        self._radios = tuple(radios)
        self._ground = replace(self._ground, active_radio_instance=active)
        snapshot = self._radios
        # Deliver after the native combo popup has unwound before rebuilding rows.
        QTimer.singleShot(0, self, lambda: self.configurationChanged.emit(snapshot, active))

    def _ModuleAvailability_Get(self, plugin_id, module_id, available, reason):
        return self._module_availability.get((plugin_id, module_id), (available, reason))

    def _Initial_Change(self):
        active = self.initial_instance.currentData()
        if active:
            self._Commit(self._radios, active)

    def _Add(self):
        if not self._ground or not self._ground.enabled or len(self._radios) >= 4:
            return
        selected = next((radio for radio in self._radios
                         if radio.instance_id == self._ground.active_radio_instance),
                        self._radios[0] if self._radios else None)
        if selected is None:
            for _, plugin_id, available, reason in self._choices:
                contract = self._contracts.get(plugin_id)
                module_id = next((identity for identity in contract.modules
                                  if self._ModuleAvailability_Get(
                                      plugin_id, identity, available, reason)[0]), None
                                 ) if contract is not None else None
                if module_id:
                    selected = GroundRadioConfiguration(
                        "radio0", plugin_id, module_id, self._ground.tx_power_dbm)
                    break
        if selected is None:
            return
        identifiers = {radio.instance_id for radio in self._radios}
        identity = next((f"radio{i}" for i in range(4) if f"radio{i}" not in identifiers), None)
        if identity and selected.plugin and selected.module_variant:
            active = self._ground.active_radio_instance if self._radios else identity
            self._Commit((*self._radios, replace(selected, instance_id=identity)), active)

    def _Selection_Change(self, identity, selection):
        if not selection:
            return
        plugin, module = selection
        if not plugin:
            self._Remove(identity)
            return
        if not self._radios:
            self._Commit((GroundRadioConfiguration(
                identity, plugin, module, self._ground.tx_power_dbm),), identity)
            return
        updated = tuple(replace(radio, plugin=plugin, module_variant=module)
                        if radio.instance_id == identity else radio for radio in self._radios)
        self._Commit(updated, self._ground.active_radio_instance)

    def _Field_Change(self, identity, field, value):
        updated = tuple(replace(radio, **{field: value})
                        if radio.instance_id == identity else radio for radio in self._radios)
        self._Commit(updated, self._ground.active_radio_instance)

    def _Remove(self, identity):
        remaining = tuple(radio for radio in self._radios if radio.instance_id != identity)
        if len(remaining) == len(self._radios):
            return
        active = self._ground.active_radio_instance
        self._Commit(remaining, active if active != identity else
                     remaining[0].instance_id if remaining else "radio0")
