from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from silverstar_fccg.project.model import GroundRadioConfigurations_Get
from silverstar_fccg.ui.widgets import StandardComboBox


class GroundRadioInstancesEditor(QWidget):
    configurationChanged = Signal(object, str)
    legacyConfigurationChanged = Signal(str, object)

    def __init__(self, translator):
        super().__init__()
        self._translator = translator
        self._ground = None
        self._contracts = {}
        self._choices = ()
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
        layout.addWidget(self.add_button)
        self.Language_Apply(translator)

    def Language_Apply(self, translator):
        self._translator = translator
        self.note.setText(translator.Text_Get("ground.radio_order_note"))
        self.initial_label.setText(translator.Text_Get("ground.initial_radio"))
        self.add_button.setText(translator.Text_Get("ground.add_radio"))

    def Configuration_Set(self, ground, choices, contracts):
        self._ground = ground
        self._contracts = contracts
        self._choices = tuple(choices)
        self._radios = GroundRadioConfigurations_Get(ground)
        self.rows.clear()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            item.widget().deleteLater()
        self.Language_Apply(self._translator)
        with QSignalBlocker(self.initial_instance):
            self.initial_instance.clear()
            for radio in self._radios:
                self.initial_instance.addItem(radio.instance_id, radio.instance_id)
            self.initial_instance.setCurrentIndex(self.initial_instance.findData(ground.active_radio_instance))
        self.initial_instance.setEnabled(ground.enabled and len(self._radios) > 1)
        self.initial_instance.setVisible(bool(ground.radio_instances))
        self.initial_label.setVisible(bool(ground.radio_instances))
        self.add_button.setEnabled(ground.enabled and len(self._radios) < 4 and
            ((bool(ground.radio_plugin) and bool(ground.module_variant)) or
             (not ground.radio_plugin and any(available for _, _, available, _ in choices))))
        for index, radio in enumerate(self._radios):
            group = QWidget()
            group.setObjectName("groundRadioRow_" + radio.instance_id)
            form = QFormLayout(group)
            form.setContentsMargins(0, 0, 0, 0)
            suffix = radio.instance_id.removeprefix("radio")
            number = int(suffix) if suffix.isdecimal() else radio.instance_id
            instance_title = QLabel(self._translator.Text_Get("ground.radio_title", id=number))
            instance_title.setToolTip(radio.instance_id)
            plugin = StandardComboBox()
            plugin.setObjectName("groundRadioPlugin_" + radio.instance_id)
            plugin.addItem(self._translator.Text_Get("selection.none"), "")
            for title, identity, available, reason in choices:
                plugin.addItem(title, identity)
                plugin.model().item(plugin.count() - 1).setEnabled(available)
                plugin.setItemData(plugin.count() - 1, reason, Qt.ItemDataRole.ToolTipRole)
            if plugin.findData(radio.plugin) < 0:
                plugin.addItem(radio.plugin, radio.plugin)
                plugin.model().item(plugin.count() - 1).setEnabled(False)
            plugin.setCurrentIndex(plugin.findData(radio.plugin))
            plugin.currentIndexChanged.connect(lambda _index, identity=radio.instance_id, combo=plugin:
                self._Field_Change(identity, "plugin", combo.currentData()))
            form.addRow(instance_title, plugin)
            module = StandardComboBox()
            contract = contracts.get(radio.plugin)
            modules = contract.modules if contract is not None else {}
            for identity, data in modules.items():
                module.addItem(str(data.get("display_name", identity)), identity)
            if module.findData(radio.module_variant) < 0:
                module.addItem(radio.module_variant or "—", radio.module_variant)
                module.model().item(module.count() - 1).setEnabled(False)
            module.setCurrentIndex(module.findData(radio.module_variant))
            module.currentIndexChanged.connect(lambda _index, identity=radio.instance_id, combo=module:
                self._Field_Change(identity, "module_variant", combo.currentData()))
            form.addRow(self._translator.Text_Get("field.ground_module"), module)
            power = StandardComboBox()
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
            form.addRow(self._translator.Text_Get("field.ground_tx_power"), power)
            buttons = QHBoxLayout()
            controls = {"title": instance_title, "plugin": plugin, "module_variant": module, "tx_power_dbm": power}
            for name, key, available, operation in (
                ("up", "ground.radio_up", index > 0, lambda identity=radio.instance_id: self._Move(identity, -1)),
                ("down", "ground.radio_down", index < len(self._radios) - 1, lambda identity=radio.instance_id: self._Move(identity, 1)),
                ("remove", "action.remove_device", bool(radio.plugin), lambda identity=radio.instance_id: self._Remove(identity))):
                button = QPushButton(self._translator.Text_Get(key))
                button.setObjectName("groundRadio_" + name + "_" + radio.instance_id)
                button.setEnabled(ground.enabled and available)
                button.clicked.connect(lambda _checked=False, action=operation: action())
                buttons.addWidget(button)
                controls[name] = button
            form.addRow(buttons)
            plugin.setEnabled(ground.enabled)
            module.setEnabled(ground.enabled)
            self.rows[radio.instance_id] = controls
            self.rows_layout.addWidget(group)

    def _Commit(self, radios, active):
        self._radios = tuple(radios)
        self._ground = replace(self._ground, active_radio_instance=active)
        snapshot = self._radios
        # Deliver after the native combo popup has unwound before rebuilding rows.
        QTimer.singleShot(0, self, lambda: self.configurationChanged.emit(snapshot, active))

    def _Initial_Change(self):
        active = self.initial_instance.currentData()
        if active:
            self._Commit(self._radios, active)

    def _Add(self):
        if not self._ground or not self._ground.enabled or len(self._radios) >= 4:
            return
        selected = next((radio for radio in self._radios
                         if radio.instance_id == self._ground.active_radio_instance),
                        GroundRadioConfigurations_Get(self._ground)[0])
        if not selected.plugin:
            identity = next((identity for _, identity, available, _ in self._choices if available), None)
            if identity:
                self._LegacyField_Commit("radio_plugin", identity)
            return
        identifiers = {radio.instance_id for radio in self._radios}
        identity = next((f"radio{i}" for i in range(4) if f"radio{i}" not in identifiers), None)
        if identity and selected.plugin and selected.module_variant:
            self._Commit((*self._radios, replace(selected, instance_id=identity)), selected.instance_id)

    def _LegacyField_Commit(self, field, value):
        QTimer.singleShot(0, self, lambda: self.legacyConfigurationChanged.emit(field, value))

    def _Field_Change(self, identity, field, value):
        if field == "plugin" and not value:
            self._Remove(identity)
            return
        if not self._ground.radio_instances:
            self._LegacyField_Commit("radio_plugin" if field == "plugin" else field, value)
            return
        updated = []
        for radio in self._radios:
            if radio.instance_id == identity:
                changes = {field: value}
                if field == "plugin":
                    contract = self._contracts.get(value)
                    modules = contract.modules if contract is not None else {}
                    changes["module_variant"] = (radio.module_variant if radio.module_variant in modules
                        else next(iter(modules)) if len(modules) == 1 else "")
                radio = replace(radio, **changes)
            updated.append(radio)
        self._Commit(updated, self._ground.active_radio_instance)

    def _Move(self, identity, offset):
        index = next(i for i, radio in enumerate(self._radios) if radio.instance_id == identity)
        destination = index + offset
        if 0 <= destination < len(self._radios):
            radios = list(self._radios)
            radios[index], radios[destination] = radios[destination], radios[index]
            self._Commit(radios, self._ground.active_radio_instance)

    def _Remove(self, identity):
        remaining = tuple(radio for radio in self._radios if radio.instance_id != identity)
        if len(remaining) == len(self._radios):
            return
        active = self._ground.active_radio_instance
        self._Commit(remaining, active if active != identity else
                     remaining[0].instance_id if remaining else "radio0")
