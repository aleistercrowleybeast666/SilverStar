"""One draft for both endpoints and the common PHY; no live-project mutation."""
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget)

from silverstar_fccg.project.model import ProtocolSelection
from silverstar_fccg.project.radio_transaction import (
    RadioTransaction_Commit, RadioTransaction_EndpointSet, RadioTransaction_IssuesGet)
from silverstar_fccg.project.radio_variants import FlightRadioConfiguration_Get
from silverstar_fccg.ui.pages.targets import AirLinkPage
from silverstar_fccg.ui.widgets import StandardComboBox


class RadioTransactionDialog(QDialog):
    def __init__(self, translator, model, catalog, parent=None):
        super().__init__(parent)
        self._draft = deepcopy(model)
        self._catalog = catalog
        self._result = None
        self._translator = translator
        text = translator.Text_Get
        self.setWindowTitle(text('radio.transaction.title'))
        self.setObjectName('radioTransaction')
        self.resize(780, 680)
        self.setMinimumSize(620, 440)
        root = QVBoxLayout(self)
        description = QLabel(text('radio.transaction.hint'), self)
        description.setWordWrap(True)
        root.addWidget(description)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        body = QVBoxLayout(content)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.endpoints = {}
        endpoint_layout = QHBoxLayout()
        body.addLayout(endpoint_layout)
        for endpoint in ('flight', 'ground'):
            group = QGroupBox(text('workspace.hardware.' + endpoint), content)
            form = QFormLayout(group)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            combo, power = StandardComboBox(group), StandardComboBox(group)
            combo.addItem(text('radio.transaction.unselected'), None)
            for manifest in catalog.Type_Get('device'):
                if manifest.radio is None:
                    continue
                for module_id, module in manifest.radio.modules.items():
                    title = str(module.get('display_name', module.get('model', module_id)))
                    combo.addItem(title, (manifest.component_id, module_id))
                    combo.setItemData(combo.count() - 1, text('radio.transaction.reconfigure'), Qt.ItemDataRole.ToolTipRole)
            form.addRow(text('field.air_family'), combo)
            form.addRow(text('field.' + endpoint + '_tx_power'), power)
            endpoint_layout.addWidget(group)
            self.endpoints[endpoint] = (combo, power)
            if endpoint == 'flight':
                instance = model.DeviceInstance_Get(model.air_link.flight_radio_instance)
                selected = (instance.plugin, FlightRadioConfiguration_Get(model, instance)[0]) if instance else None
            else:
                selected = (model.ground_target.radio_plugin, model.ground_target.module_variant) if model.ground_target.radio_plugin else None
            combo.setCurrentIndex(max(0, combo.findData(selected)))
            self._Powers_Refresh(endpoint)
            combo.currentIndexChanged.connect(lambda _index, selected=endpoint: self._Endpoint_Change(selected))
            power.currentIndexChanged.connect(lambda _index, selected=endpoint: self._Endpoint_Change(selected, refresh_power=False))
        preset_row = QHBoxLayout()
        self.preset = StandardComboBox(content)
        self.preset.addItem('SX1281 · 2473 MHz / SF10 / BW800 / CR4/5', 'sx128x')
        self.preset.addItem('SX1278 · 433 MHz / SF7 / BW125 / CR4/5', 'sx127x')
        preview = QPushButton(text('radio.transaction.preset'), content)
        preview.clicked.connect(self._Preset_Apply)
        preset_row.addWidget(self.preset, 1)
        preset_row.addWidget(preview)
        body.addLayout(preset_row)
        self.preset_note = QLabel(text('radio.transaction.preset_hint'), content)
        self.preset_note.setWordWrap(True)
        body.addWidget(self.preset_note)
        self.editor = AirLinkPage(translator)
        self.editor.Language_Apply(translator)
        self.editor._air_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.editor.setParent(content)
        self.editor.RadioOptions_Set(tuple(item.radio for item in catalog.Type_Get('device') if item.radio))
        self.editor.fields['frequency_hz'].setRange(1, 6000)
        self.editor.fields['frequency_hz'].setEnabled(True)
        self.editor.configurationChanged.connect(self._Link_Change)
        self.editor.root_layout.removeWidget(self.editor.air_link_group)
        body.addWidget(self.editor.air_link_group)
        self.editor.air_link_group.toggle_button.setChecked(True)
        self.editor.hide()
        self.migrate = QCheckBox(text('radio.transaction.migrate'), content)
        self.migrate.setChecked(model.air_link.protocol_profile == 'ss_tm.s.0_1')
        self.migrate.setVisible(model.air_link.protocol_profile != 'ss_tm.s.0_1')
        body.addWidget(self.migrate)
        self.error = QLabel(self)
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._Refresh()

    def _Powers_Refresh(self, endpoint):
        combo, power = self.endpoints[endpoint]
        previous = power.currentData()
        power.blockSignals(True)
        power.clear()
        if combo.currentData():
            plugin, module_id = combo.currentData()
            module = self._catalog.Component_Get(plugin).radio.modules[module_id]
            for value in module['supported_tx_powers_dbm']:
                power.addItem(str(value) + ' dBm', value)
            power.setCurrentIndex(max(0, power.findData(previous)))
        power.blockSignals(False)

    def _Endpoint_Change(self, endpoint, *, refresh_power=True):
        if refresh_power:
            self._Powers_Refresh(endpoint)
        combo, power = self.endpoints[endpoint]
        if combo.currentData() is None:
            # Existing endpoint removal belongs to its device editor. An empty
            # previously unconfigured peer is valid for single-target projects.
            self._Refresh()
            return
        plugin, module = combo.currentData()
        self._draft = RadioTransaction_EndpointSet(self._draft, self._catalog, endpoint,
                                                   plugin, module, power.currentData())
        self._Refresh()

    def _Link_Change(self, field, value):
        self._draft.air_link = replace(self._draft.air_link, **{field: value})
        self._Refresh()

    def _Preset_Apply(self):
        family = self.preset.currentData()
        changes = dict(radio_family=family, radio_technology='lora', phy_mode='lora',
            frequency_hz=433000000 if family == 'sx127x' else 2473000000,
            spreading_factor=7 if family == 'sx127x' else 10,
            bandwidth_hz=125000 if family == 'sx127x' else 800000,
            coding_rate='4/5', preamble_symbols=16, header_mode='explicit',
            crc_enabled=True, iq_mode='normal', packet_mtu=61, nrf24=None)
        labels = dict(radio_family='field.air_family', radio_technology='field.air_technology',
            phy_mode='field.air_phy', frequency_hz='field.air_frequency', spreading_factor='field.air_sf',
            bandwidth_hz='field.air_bandwidth', coding_rate='field.air_coding_rate',
            preamble_symbols='field.air_preamble', header_mode='field.air_header',
            crc_enabled='field.air_crc', iq_mode='field.air_iq', packet_mtu='field.air_mtu')
        differences = []
        for key, value in changes.items():
            if key not in labels or value == getattr(self._draft.air_link, key):
                continue
            shown = str(value)
            if key == 'frequency_hz':
                shown = f'{value / 1000000:g} MHz'
            elif key == 'bandwidth_hz':
                shown = f'{value / 1000:g} kHz'
            differences.append(self._translator.Text_Get(labels[key]) + ': ' + shown)
        self._draft.air_link = replace(self._draft.air_link, **changes)
        self.preset_note.setText(self._translator.Text_Get('radio.transaction.changed') + '\n' +
                                 ' · '.join(differences))
        self._Refresh()

    def _Refresh(self):
        if not hasattr(self, 'editor'):
            return
        issues = RadioTransaction_IssuesGet(self._draft, self._catalog)
        self.editor.Configuration_Set(self._draft.air_link, issues)
        self.error.setText('\n'.join(issue.code + ': ' + issue.message for issue in issues)
                           or self._translator.Text_Get('radio.transaction.valid'))

    def accept(self):
        candidate = deepcopy(self._draft)
        # Read pending spin-box text before the modal transaction commits.
        for field, widget in self.editor.fields.items():
            if hasattr(widget, 'interpretText'):
                widget.interpretText()
                value = widget.value()
                candidate.air_link = replace(candidate.air_link, **{
                    field: round(value * 1000000) if field == 'frequency_hz' else value})
        if self.migrate.isChecked():
            candidate.air_link = replace(candidate.air_link, protocol_profile='ss_tm.s.0_1')
            manifest = self._catalog.Component_Get('silverstar.protocol.telemetry.ss_tm')
            candidate.protocols['telemetry'] = ProtocolSelection(manifest.component_id, manifest.version,
                'ss_tm.s.0_1', manifest.ManifestSha256_Get())
        try:
            self._result = RadioTransaction_Commit(candidate, self._catalog)
        except ValueError as error:
            self.error.setText(str(error))
            return
        super().accept()

    def Configuration_Get(self):
        return deepcopy(self._result)
