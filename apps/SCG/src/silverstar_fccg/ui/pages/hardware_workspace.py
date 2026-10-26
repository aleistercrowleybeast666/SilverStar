"""One ownership boundary for Flight/Ground hardware editors and their shared link.

Editors keep their signals and authoritative project fields.  This composition
mounts each existing widget once; refresh never copies controls or configuration.
"""
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QBoxLayout, QFormLayout, QGridLayout, QGroupBox, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from silverstar_fccg.project.model import GroundRadioConfigurations_Get
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.widgets import CollapsibleSection


class HardwareWorkspacePage(ScrollableLocalizedPage):
    def __init__(self, translator, devices_page, board_hardware_page, ground_target_page, air_link_page):
        super().__init__(translator, 'workspace.hardware.title', 'workspace.hardware.description')
        for page in (devices_page, board_hardware_page, ground_target_page, air_link_page):
            if hasattr(page, '_hardware_workspace_owner'):
                raise ValueError('Hardware editor already has a workspace owner')
            page._hardware_workspace_owner = self
        self.devices_page = devices_page
        self.board_hardware_page = board_hardware_page
        self.ground_target_page = ground_target_page
        self.air_link_page = air_link_page
        self._model = None
        self._scroll = self.findChild(QScrollArea)
        self._scroll.viewport().installEventFilter(self)
        self._columns = 0
        self._details_columns = 0
        self._header_sync_pending = False
        self._header_layouts = {}
        self._header_rows = {}
        self._sections = {}
        self._device_rows = {}
        self.target_cards = {}
        self.target_summaries = {}
        self.device_summaries = {}
        self.target_buttons = {}
        self.target_grid = QGridLayout()
        self.target_grid.setContentsMargins(0, 0, 0, 0)
        self.root_layout.addLayout(self.target_grid)
        for target, page in (('flight', board_hardware_page), ('ground', ground_target_page)):
            card = QGroupBox()
            card.setObjectName('hardwareTarget_' + target)
            body = QGridLayout(card)
            body.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._header_layouts[target] = body
            summary = QLabel()
            summary.setWordWrap(True)
            summary.setTextFormat(Qt.TextFormat.PlainText)
            summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            body.addWidget(summary, 2, 0)
            device_summary = QLabel()
            device_summary.setWordWrap(True)
            device_summary.setTextFormat(Qt.TextFormat.PlainText)
            device_summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            body.addWidget(device_summary, 3, 0)
            self.device_summaries[target] = device_summary
            # A long English status must wrap inside its target, rather than
            # increase the scroll content width beyond the visible viewport.
            page.hardware_status.setWordWrap(True)
            page.selection_group.layout().setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            page.root_layout.removeWidget(page.selection_group)
            body.addWidget(page.selection_group, 0, 0)
            page.root_layout.removeWidget(page.custom_widget)
            body.addWidget(page.custom_widget, 1, 0)
            page.root_layout.removeWidget(page.provider_notice)
            option = QWidget()
            if target == 'ground':
                ground_target_page.radio_form.removeWidget(ground_target_page.enabled)
                ground_target_page.enabled.hide()
            body.addWidget(option, 4, 0)
            button = QPushButton()
            button.clicked.connect(lambda _checked=False, selected=target: self.Reveal(self._target_sections[selected]))
            body.addWidget(button, 5, 0)
            self._header_rows[target] = (page.selection_group, page.custom_widget, summary, device_summary, option, button)
            self.target_cards[target] = card
            self.target_summaries[target] = summary
            self.target_buttons[target] = button
        self.link_summary = QLabel()
        self.link_summary.setWordWrap(True)
        self.link_summary.setTextFormat(Qt.TextFormat.PlainText)
        self._target_sections = {}
        for target in ('flight', 'ground'):
            section = self._Section_Create('workspace.hardware.' + target + '.devices', expanded=True)
            section.setObjectName('hardwareDevices_' + target)
            self._sections[target + '.devices'] = section
            self._target_sections[target] = section
        flight_body = self._target_sections['flight'].body.layout()
        installation = self._Section_Create('workspace.hardware.installation')
        self._Widget_Attach(devices_page.root_layout, devices_page.global_configuration_group, installation.body.layout())
        for form in (devices_page.primary_form, devices_page.other_form,
                     devices_page.telemetry_form, devices_page.storage_form,
                     devices_page.radio_power_form, devices_page.global_configuration_group.layout()):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._sections['flight.installation'] = installation
        flight_body.addWidget(installation)
        self._PageWidgets_Attach(devices_page, flight_body)
        flight_body.addWidget(devices_page.radio_power_editor)
        ground_body = self._target_sections['ground'].body.layout()
        ground_body.addWidget(ground_target_page.status)
        self._Widget_Attach(ground_target_page.root_layout, ground_target_page.pc_group, ground_body)
        ground_body.addWidget(ground_target_page.radio_selection_group)
        ground_body.addWidget(ground_target_page.radio_instances_editor.power_editor)
        led = self._Section_Create('workspace.hardware.ground.indicators')
        self._Widget_Attach(ground_target_page.root_layout, ground_target_page.activity_led_group, led.body.layout())
        self._sections['ground.indicators'] = led
        ground_body.addWidget(led)
        for target, page, body in (('flight', board_hardware_page, flight_body), ('ground', ground_target_page, ground_body)):
            platform = self._Section_Create('workspace.hardware.platform')
            self._Widget_Attach(page.root_layout, page.platform_group, platform.body.layout())
            platform.body.layout().addWidget(page.provider_notice)
            self._sections[target + '.platform'] = platform
            page.root_layout.removeWidget(page.advanced_section)
            # All board-resource details stay with their target, never the mission editor.
            body.addWidget(platform)
            body.addWidget(page.advanced_section)
            self._sections[target + '.resources'] = page.advanced_section
            skip = {page.generate_button, getattr(page, 'build_group', None)}
            self._PageWidgets_Attach(page, body, skip=skip)
        # The complete target editors stay in their own column; the single
        # shared air-link configuration follows both targets at the page end.
        self.root_layout.addWidget(self.link_summary)
        self.root_layout.addWidget(air_link_page.status)
        self._PageWidgets_Attach(air_link_page, self.root_layout, skip={air_link_page.status})
        self._sections['link.details'] = air_link_page.air_link_group
        self.root_layout.addStretch(1)
        self._Targets_Layout()
        self.Language_Apply(translator)

    @staticmethod
    def _Widget_Attach(source, widget, destination):
        source.removeWidget(widget)
        destination.addWidget(widget)

    def _PageWidgets_Attach(self, page, destination, skip=()):
        while page.root_layout.count():
            item = page.root_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not page.header and widget not in skip:
                destination.addWidget(widget)
        page.setParent(self)
        page.hide()

    def _Section_Create(self, key, expanded=False):
        section = CollapsibleSection(expanded=expanded)
        section.setProperty('workspaceTitleKey', key)
        section.BodyLayout_Set(QVBoxLayout())
        return section

    def _Targets_Layout(self):
        # At the supported 900px main-window width the workspace has ~695px.
        # Keep both real board/import entries above the fold at that width.
        columns = 2 if self.width() >= 620 else 1
        details_columns = 2 if self.width() >= 1120 else 1
        available = (self.width() - 36 - (columns - 1) * 10) / columns
        direction = (QBoxLayout.Direction.TopToBottom if available < 360
                     else QBoxLayout.Direction.LeftToRight)
        for owner in (self.board_hardware_page, self.ground_target_page):
            owner.custom_widget.layout().setDirection(direction)
        if columns != self._columns or details_columns != self._details_columns:
            self._columns, self._details_columns = columns, details_columns
            for widget in (*self.target_cards.values(), *self._target_sections.values()):
                self.target_grid.removeWidget(widget)
            for index, card in enumerate(self.target_cards.values()):
                self.target_grid.addWidget(card, index // columns, index % columns)
            first_detail_row = 1 if columns == 2 else 2
            for index, section in enumerate(self._target_sections.values()):
                self.target_grid.addWidget(section, first_detail_row + index // details_columns,
                                           index % details_columns, 1, columns // details_columns,
                                           Qt.AlignmentFlag.AlignTop)
            self.target_grid.setColumnStretch(0, 1)
            self.target_grid.setColumnStretch(1, 1 if columns == 2 else 0)
        self._HeaderRows_Queue()

    def _HeaderRows_Queue(self):
        if not self._header_sync_pending:
            self._header_sync_pending = True
            QTimer.singleShot(0, self, self._HeaderRows_Align)

    def _HeaderRows_Align(self):
        """Align equivalent rows using current font, wrapping and real width."""
        self._header_sync_pending = False
        for row in range(6):
            heights = []
            for target, widgets in self._header_rows.items():
                margins = self._header_layouts[target].contentsMargins()
                width = self.target_cards[target].contentsRect().width() - margins.left() - margins.right()
                widget = widgets[row]
                height = widget.heightForWidth(max(1, width)) if widget.hasHeightForWidth() else widget.sizeHint().height()
                heights.append(max(0, height))
            for layout in self._header_layouts.values():
                if layout.rowMinimumHeight(row) != max(heights):
                    layout.setRowMinimumHeight(row, max(heights))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._Targets_Layout()
        self._DeviceSummaries_Refresh()
        QTimer.singleShot(0, self, self._ViewportWidth_Apply)

    def eventFilter(self, watched, event):
        if watched is getattr(self, '_scroll', None).viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self, self._ViewportWidth_Apply)
        return super().eventFilter(watched, event)

    def _ViewportWidth_Apply(self):
        # A long editor lower down must not widen both target entry cards.
        # Forms wrap their rows; the scroll content follows its real viewport.
        width = self._scroll.viewport().width()
        if width >= 200 and self._scroll.widget().maximumWidth() != width:
            self._scroll.widget().setMaximumWidth(width)

    def Configuration_Set(self, model):
        """Render declared configuration, never claim a physical connection."""
        self._model = model
        text = self._translator.Text_Get
        flight = model.hardware
        ground = model.ground_target
        for target, hardware, board in (('flight', flight, model.board), ('ground', ground.hardware, ground.board)):
            owner = self.board_hardware_page if target == 'flight' else self.ground_target_page
            part = hardware.mcu or str(hardware.inventory.get('mcu_part', '')) or '—'
            self.target_summaries[target].setText(text('workspace.hardware.target_summary',
                board=hardware.source_label or board or text('workspace.hardware.pending'),
                mcu=part, source=hardware.source_kind or hardware.mode,
                status=owner.hardware_status.text() or text('workspace.hardware.pending')))
        flight_radios = [item for item in model.device_instances
                         if item.instance_id in self.devices_page._radio_configurations]
        flight_text = ', '.join(item.instance_id + ': ' +
            str(self.devices_page._radio_configurations[item.instance_id][0] or item.plugin) + ' / ' +
            str(self.devices_page._radio_configurations[item.instance_id][1]) + ' dBm'
            for item in flight_radios) or '—'
        ground_text = ', '.join(item.instance_id + ': ' + (item.module_variant or item.plugin) +
            ' / ' + str(item.tx_power_dbm) + ' dBm' for item in GroundRadioConfigurations_Get(ground) if item.plugin) or '—'
        self.link_summary.setText(text('workspace.hardware.link_summary',
            frequency=f'{model.air_link.frequency_hz/1000000:g}', flight=flight_text, ground=ground_text))
        profile = model.air_link.protocol_profile
        summary = text('telemetry.mode.s' if profile == 'ss_tm.s.0_1' else
                       'telemetry.mode.h' if profile == 'ss_tm.h.0_1' else 'telemetry.mode.legacy')
        if profile in ('ss_tm.s.0_1', 'ss_tm.h.0_1') and model.air_link.radio_family == 'sx128x':
            from silverstar_telemetry.plan import TelemetryPlan_Get
            try:
                plan = TelemetryPlan_Get('S' if profile == 'ss_tm.s.0_1' else 'H',
                    sf=model.air_link.spreading_factor, bandwidth_hz=model.air_link.bandwidth_hz,
                    coding_rate=model.air_link.coding_rate, preamble=model.air_link.preamble_symbols)
                summary += '\n' + text('telemetry.budget', tx=f"{plan['tx_fraction']*100:.2f}",
                                        scheduler=f"{plan['scheduler_fraction']*100:.2f}")
            except ValueError as error:
                summary += '\n' + str(error)
        self.link_summary.setText(self.link_summary.text() + '\n' + summary)

        selected = set(model.ComponentIds_Get())
        devices = [item.instance_id + ': ' + item.name + (' / ' + item.interface if item.interface else '')
                   for item in self.devices_page._instances]
        represented = {item.plugin_id for item in self.devices_page._instances}
        devices.extend(item.name for item in self.devices_page._components
            if item.component_type.value == 'device' and item.component_id in selected
            and item.component_id not in represented
            and item.options.get('device_selection_style') != 'instance' and not item.options.get('internal'))
        pc = ground.pc_interface or '—'
        if ground.pc_resource:
            pc += ' / ' + ground.pc_resource
        self._device_rows = {'flight': tuple(dict.fromkeys(devices)),
            'ground': ('PC ' + pc,) + tuple(item.instance_id + ': ' + (item.module_variant or item.plugin) +
                ' / ' + str(item.tx_power_dbm) + ' dBm'
                for item in GroundRadioConfigurations_Get(ground) if item.plugin)}
        self._DeviceSummaries_Refresh()

    def _DeviceSummaries_Refresh(self):
        available = max(120, int(self.width() / (self._columns or 1)) - 84)
        for target, rows in self._device_rows.items():
            label = self.device_summaries[target]
            visible = [label.fontMetrics().elidedText(row, Qt.TextElideMode.ElideRight, available)
                       for row in rows[:3]]
            if len(rows) > 3:
                visible.append(self._translator.Text_Get('workspace.hardware.more', count=len(rows)-3))
            label.setText(self._translator.Text_Get('workspace.hardware.device_summary', devices='\n'.join(visible) or '—'))
            label.setToolTip('\n'.join(rows))
        self._HeaderRows_Queue()

    def ExpandedState_Get(self):
        return {key: section.Expanded_Is() for key, section in self._sections.items()}

    def ExpandedState_Set(self, values):
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            if key in self._sections and type(value) is bool:
                self._sections[key].toggle_button.setChecked(value)

    def Reveal(self, widget):
        owners = {self.devices_page: self._target_sections['flight'],
                  self.board_hardware_page: self.target_cards['flight'],
                  self.ground_target_page: self.target_cards['ground'],
                  self.air_link_page: self.link_summary}
        widget = owners.get(widget, widget)
        if widget is None or not self.isAncestorOf(widget):
            return False
        current = widget
        while current is not None and current is not self:
            if isinstance(current, CollapsibleSection):
                current.toggle_button.setChecked(True)
            current = current.parentWidget()
        scroll = self.findChild(QScrollArea)
        if scroll is not None:
            scroll.ensureWidgetVisible(widget, 18, 18)
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def Language_Apply(self, translator):
        super().Language_Apply(translator)
        for page in (self.devices_page, self.board_hardware_page, self.ground_target_page, self.air_link_page):
            page.Language_Apply(translator)
        for target, card in self.target_cards.items():
            card.setTitle(translator.Text_Get('workspace.hardware.' + target))
            self.target_buttons[target].setText(translator.Text_Get('workspace.hardware.' + target + '.edit'))
        for section in self._sections.values():
            key = section.property('workspaceTitleKey')
            if key:
                section.Title_Set(translator.Text_Get(key))
        if self._model is not None:
            self.Configuration_Set(self._model)
