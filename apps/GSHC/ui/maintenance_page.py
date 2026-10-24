"""Read-only FC debug RAM status and separately identified AIR diagnostics."""
from __future__ import annotations

import time
from services.legacy_firmware_status import LegacyFirmwareSnapshot
from ui.touch_scroll import TouchScroll_Enable, TouchScroll_Wrap
from ui.diagnostic_labels import Text, DiagnosticValue_Format, DiagnosticReason_Format, DiagnosticState_Format

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class MaintenancePage(QWidget):
    TF_DIRECTORY_KEY = "maintenance/tf_download_directory"

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.state = None
        self.firmware_snapshot = None
        self.firmware_detail = ""
        self.diagnostic_entries = []
        self._diagnostic_render_ns = 0
        self._summary_rows = []
        self._swd_firmware_matched = False
        self._tf_job_busy = False
        self._telemetry_generation = None
        self._telemetry_stamps = dict(system=0, sensors=0, communication=0)
        self._telemetry_after = dict(self._telemetry_stamps)
        self._telemetry_render_ns = 0
        self._telemetry_connected = None
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.detail_source = QLabel(self)
        self.detail_source.setWordWrap(True)
        self.detail_source.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8,6,8,6)
        layout.setSpacing(6)
        actions = QGridLayout()
        self.btn_swd_attach = QPushButton(self)
        self.btn_swd_detach = QPushButton(self)
        self.btn_swd_attach.hide()
        self.btn_swd_detach.hide()
        self.btn_swd_import = QPushButton()
        self.btn_swd_relocate = QPushButton()
        self.btn_swd_variables = QPushButton()
        self.btn_swd_details = QPushButton()
        for index,button in enumerate((self.btn_swd_import,self.btn_swd_variables,self.btn_swd_details)):
            actions.addWidget(button,0,index)
        self.btn_swd_relocate.hide()
        actions.addWidget(self.btn_swd_relocate,1,0,1,3)
        self.btn_swd_attach.setEnabled(False)
        self.btn_swd_detach.setEnabled(False)
        self.btn_swd_variables.setEnabled(False)
        self.target_identity = QLabel()
        self.swd_import_status = QLabel()
        self.swd_target_status = QLabel()
        for label in (self.target_identity,self.swd_import_status,self.swd_target_status):
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)

        self.swd_details = QDialog(self)
        self.swd_details.resize(980,620)
        swd_details_layout = QVBoxLayout(self.swd_details)
        self.swd_status = QLabel()
        self.swd_status.setWordWrap(True)
        self.swd_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_actions = QHBoxLayout()
        details_actions.addWidget(self.swd_status,1)
        self.swd_copy = QPushButton()
        self.swd_copy.clicked.connect(self._SwdDetails_Copy)
        details_actions.addWidget(self.swd_copy)
        swd_details_layout.addLayout(details_actions)
        self.swd_splitter = QSplitter(Qt.Vertical)
        self.swd_details_text = QPlainTextEdit()
        self.swd_details_text.setReadOnly(True)
        self.swd_details_text.setMinimumHeight(80)
        self.swd_splitter.addWidget(self.swd_details_text)
        self.swd_diagnostics = QTreeWidget()
        self.swd_diagnostics.setColumnCount(4)
        self.swd_diagnostics.setWordWrap(True)
        self.swd_diagnostics.setTextElideMode(Qt.ElideNone)
        self.swd_diagnostics.setMinimumHeight(160)
        for column,width in enumerate((190,270,280,180)):
            self.swd_diagnostics.setColumnWidth(column,width)
        self.swd_splitter.addWidget(self.swd_diagnostics)
        self.swd_splitter.setSizes([150,360])
        self.swd_splitter.setStretchFactor(0,1)
        self.swd_splitter.setStretchFactor(1,3)
        swd_details_layout.addWidget(self.swd_splitter,1)
        self.swd_reason_text = QPlainTextEdit()
        self.swd_reason_text.setReadOnly(True)
        self.swd_reason_text.setMinimumHeight(80)
        self.swd_reason_text.setMaximumHeight(110)
        swd_details_layout.addWidget(self.swd_reason_text)
        self.swd_diagnostics.itemSelectionChanged.connect(self._SwdReason_Render)
        self.btn_swd_details.clicked.connect(self.swd_details.show)

        from ui.swd_watch import SwdWatchDialog
        self.watch_dialog = SwdWatchDialog(i18n,self)
        self.swd_watch = self.watch_dialog.panel
        self.sections = QTabWidget()
        self.sections.setObjectName('maintenanceSections')
        self.sections.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
        self.runtime_section = QWidget()
        runtime = QVBoxLayout(self.runtime_section)
        self.swd_group = QGroupBox()
        swd = QVBoxLayout(self.swd_group)
        swd.addLayout(actions)
        for label in (self.target_identity,self.swd_import_status,self.swd_target_status):swd.addWidget(label)
        runtime.addWidget(self.swd_group)
        cards = QGridLayout()
        self.summary_cards = {}
        for index,identifier in enumerate(('task.preparation','thread.estimator','sensor.ins_solution','thread.logger')):
            box = QGroupBox()
            box.setObjectName('swdCard_'+identifier.replace('.','_'))
            content = QVBoxLayout(box)
            value,age = QLabel(),QLabel()
            value.setWordWrap(True)
            age.setWordWrap(True)
            content.addWidget(value)
            content.addWidget(age)
            self.summary_cards[identifier] = (box,value,age)
            cards.addWidget(box,index//2,index%2)
        cards.setColumnStretch(0,1)
        cards.setColumnStretch(1,1)
        runtime.addLayout(cards)
        self.serial_brief = QLabel()
        self.serial_brief.setWordWrap(True)
        self.btn_serial_details = QPushButton()
        runtime.addStretch(1)
        self.runtime_scroll = TouchScroll_Wrap(self.runtime_section)
        self.sections.addTab(self.runtime_scroll,'')

        serial_body = QGroupBox()
        self.serial_group = serial_body
        serial_layout = QVBoxLayout(serial_body)
        from ui.maintenance_console import MaintenanceConsole
        self.console = MaintenanceConsole(i18n,self)
        serial_layout.addWidget(self.console)
        self.firmware_summary = QLabel()
        self.firmware_summary.setWordWrap(True)
        self.diagnostic_status = QLabel()
        self.diagnostic_status.setWordWrap(True)
        self.diagnostic_tree = QTreeWidget()
        self.diagnostic_tree.setColumnCount(5)
        self.diagnostic_tree.setMinimumHeight(220)
        self.serial_details_dialog = QDialog(self)
        self.serial_details_dialog.resize(900,600)
        serial_details_layout = QVBoxLayout(self.serial_details_dialog)
        serial_details_layout.addWidget(self.firmware_summary)
        serial_details_layout.addWidget(self.diagnostic_status)
        serial_details_layout.addWidget(self.diagnostic_tree,1)
        self.btn_serial_details.clicked.connect(self.serial_details_dialog.show)
        self.source = QLabel()
        self.source.setParent(self)
        self.source.setWordWrap(True)
        self.source.hide()
        self.summary = QGroupBox()
        grid = QGridLayout(self.summary)
        self.labels = {}
        for row,key in enumerate(('system','sensors','mission','storage','communication')):
            name,value = QLabel(),QLabel()
            value.setWordWrap(True)
            self.labels[key] = (name,value)
            grid.addWidget(name,row,0)
            grid.addWidget(value,row,1)
        grid.setColumnStretch(1,1)
        self.btn_details = QPushButton()
        self.btn_details.setParent(self)
        self.btn_details.clicked.connect(self._show_details)
        self.btn_details.hide()
        self.tree.setMaximumHeight(260)
        grid.addWidget(self.tree,5,0,1,2)
        runtime.insertWidget(2,self.summary)
        for widget in self.labels['storage']:
            widget.hide()
        self.serial_section = TouchScroll_Wrap(serial_body)
        self.serial_details = self.serial_section

        tf_body = QGroupBox()
        self.tf_group = tf_body
        tf = QVBoxLayout(tf_body)
        brief_row = QHBoxLayout()
        brief_row.addWidget(self.serial_brief,1)
        brief_row.addWidget(self.btn_serial_details)
        serial_layout.insertLayout(1,brief_row)
        self.tools = QVBoxLayout()
        tf.addLayout(self.tools)
        destination_row = QHBoxLayout()
        self.destination_label = QLabel()
        self.destination_path = QLineEdit()
        self.destination_path.setReadOnly(True)
        self.btn_destination = QPushButton()
        destination_row.addWidget(self.destination_label)
        destination_row.addWidget(self.destination_path,1)
        destination_row.addWidget(self.btn_destination)
        tf.addLayout(destination_row)
        self.set_destination(str(i18n.settings.value(self.TF_DIRECTORY_KEY,'')))
        self.service_status = QLabel('LOGFILE: not negotiated')
        self.service_status.setWordWrap(True)
        tf.addWidget(self.service_status)
        self.note = QLabel()
        self.note.setParent(self)
        self.note.setWordWrap(True)
        self.note.hide()
        self.catalog = QListWidget()
        self.catalog.setMaximumHeight(150)
        self.catalog.setParent(self)
        self.catalog.hide()
        self.btn_selected_download = QPushButton()
        self.btn_selected_download.setEnabled(False)
        self.catalog.itemSelectionChanged.connect(self._Selection_Update)
        self.btn_selected_download.hide()
        for view in (self.tree,self.swd_diagnostics,self.diagnostic_tree,self.catalog):
            view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            TouchScroll_Enable(view)
        TouchScroll_Enable(self.swd_details_text)
        TouchScroll_Enable(self.swd_reason_text)
        self.progress = QProgressBar()
        self.progress.setParent(self)
        self.progress.setRange(0,1000)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.cancel = QPushButton()
        self.cancel.setParent(self)
        self.cancel.setEnabled(False)
        self.progress.hide()
        self.cancel.hide()
        tf.addWidget(self.status)
        tf.addStretch(1)
        serial_layout.insertWidget(2,tf_body)
        self.tf_section = self.serial_section
        self.sections.addTab(self.serial_section,'')
        layout.addWidget(self.sections,1)
        self.retranslate()

    def _SwdDetails_Copy(self):
        lines = [self.swd_status.text(),self.swd_details_text.toPlainText()]
        for index in range(self.swd_diagnostics.topLevelItemCount()):
            item = self.swd_diagnostics.topLevelItem(index)
            lines.append(' | '.join(item.text(column) for column in range(4)))
            lines.append(item.data(0,Qt.UserRole) or '')
        QApplication.clipboard().setText('\n'.join(lines))

    def _SwdReason_Render(self):
        items = self.swd_diagnostics.selectedItems()
        item = items[0] if items else None
        if item is None:
            self.swd_reason_text.setPlainText(Text(self.i18n,'选择运行诊断行，查看完整原因与原始标识。','Select a diagnostic row for its full reason and raw identifiers.'))
        else:
            self.swd_reason_text.setPlainText('\n'.join(item.text(column) for column in range(4))
                +'\n'+(item.data(0,Qt.UserRole) or ''))

    def set_swd_summary(self, rows, *, matched=None):
        if matched is not None:
            self._swd_firmware_matched = bool(matched)
        self._summary_rows = list(rows or [])[:4]
        indexed = {row['id']:row for row in self._summary_rows}
        tr = self.i18n.tr
        captions = {'ready':'card.ready','start_blocking_mask':'card.block','warning_mask':'card.warn',
            'attitude_status':'card.attitude','last_duration_us':'card.duration','last_prediction_count':'card.predictions',
            'prediction_cap_count':'card.caps','ins_valid':'card.ins','alignment_valid':'card.alignment',
            'mission_running':'card.mission','update_seq':'card.sequence','completed_writes':'card.writes',
            'writer_open':'card.writer','log_fault':'card.log_fault','finalization':'card.finalization','healthy':'card.storage'}
        for identifier,(box,value,age) in self.summary_cards.items():
            box.setTitle(tr('watch.summary.'+identifier))
            row = indexed.get(identifier)
            available = bool(self._swd_firmware_matched and row and row['values'])
            box.setEnabled(self._swd_firmware_matched)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            age.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if available:
                values = []
                for key,item in row['values'].items():
                    text = DiagnosticValue_Format(identifier,key,item,self.i18n)
                    values.append(tr(captions.get(key,key))+': '+text)
                prefix = Text(self.i18n,'历史观测：','Previous observation: ') if row['state']!='OBSERVED' else ''
                value.setText(prefix+' · '.join(values))
                age.setText(DiagnosticState_Format(row['state'],self.i18n)+f" · RX {row['host_age_ms']/1000:.1f}s · "+tr('swd.sample_time_unknown'))
            else:
                value.setText(tr('swd.card_unknown'))
                reason = row.get('reason','') if row else ''
                if not self._swd_firmware_matched:
                    age.setText(Text(self.i18n,'尚未连接并匹配目标固件。','Target connection and firmware match are not confirmed.'))
                else:
                    from ui.diagnostic_labels import DiagnosticReason_Format
                    age.setText('UNKNOWN · '+DiagnosticReason_Format(reason,self.i18n))
                age.setToolTip(reason)

    def _render_serial_brief(self):
        tr = self.i18n.tr
        snapshot = self.firmware_snapshot
        if snapshot is None:
            state = tr('maintenance.unavailable')
        else:
            age = max(0,(time.monotonic_ns()-snapshot.received_ns)/1e9)
            state = f'firmware {snapshot.firmware} · RX {age:.1f}s'
            if age>3: state += ' · '+tr('maintenance.stale')
        self.serial_brief.setText(tr('maintenance.port_title')+': '+state+' · '+tr('maintenance.diagnostic_count').format(count=len(self.diagnostic_entries)))

    def set_firmware_status(self, snapshot, detail=""):
        self.firmware_snapshot = snapshot
        self.firmware_detail = detail
        self._render_firmware()
        self._render_serial_brief()

    def set_diagnostics(self, entries, detail=""):
        self.diagnostic_entries = list(entries or [])[:16]
        self.diagnostic_status.setText(detail)
        self._diagnostic_render_ns = 0
        self._render_diagnostics()
        self._render_serial_brief()

    def _render_diagnostics(self):
        now = time.monotonic_ns()
        if now - self._diagnostic_render_ns < 250_000_000:
            return
        self._diagnostic_render_ns = now
        self.diagnostic_tree.clear()
        groups = {}
        for entry in self.diagnostic_entries:
            if entry.group not in groups:
                group = QTreeWidgetItem([entry.group])
                self.diagnostic_tree.addTopLevelItem(group)
                groups[entry.group] = group
            receive_age = max(0, (now - entry.received_ns) / 1e9)
            age = (f"{receive_age:.1f}s RX; sample ?" if entry.age_ms is None else
                   f"{receive_age + entry.age_ms / 1000:.1f}s sample")
            stale = receive_age > 3 or entry.age_ms is not None and receive_age + entry.age_ms / 1000 > 3
            if stale:
                age += " · " + self.i18n.tr("maintenance.stale")
            fields = dict(entry.fields)
            for key in ('work_age_ms', 'data_age_ms'):
                if key in fields:
                    fields[key] = '?' if fields[key] == '4294967295' else str(int(fields[key]) + int(receive_age * 1000))
            values = " · ".join(f"{key}={DiagnosticValue_Format(entry.id,key,value,self.i18n)}" for key, value in fields.items())
            row = QTreeWidgetItem([entry.name.replace('_', ' ') + "\n" + entry.id,
                DiagnosticState_Format("STALE" if stale else entry.state,self.i18n) + ": " + DiagnosticReason_Format(entry.reason,self.i18n), values, age, entry.source])
            for column in range(5): row.setToolTip(column, row.text(column))
            groups[entry.group].addChild(row)
        self.diagnostic_tree.expandAll()
        for column in range(5):
            self.diagnostic_tree.resizeColumnToContents(column)
            self.diagnostic_tree.setColumnWidth(column, min(420, self.diagnostic_tree.columnWidth(column)))

    def _render_firmware(self):
        snap = self.firmware_snapshot
        if snap is None:
            detail = self.firmware_detail or self.i18n.tr("maintenance.firmware_not_received")
            self.firmware_summary.setText(self.i18n.tr("maintenance.firmware_source") + ": " + detail)
            return
        if isinstance(snap, LegacyFirmwareSnapshot):
            self._render_legacy_firmware(snap)
            return
        age = snap.age_ms / 1000 + max(0, (time.monotonic_ns() - snap.received_ns) / 1e9)
        freshness = self.i18n.tr("maintenance.stale" if age > 3 else "maintenance.received")
        states = ("BOOT", "SELF_TEST", "PREFLIGHT", "READY", "FLIGHT", "RECOVERY", "LANDED", "POSTFLIGHT", "FAULT")
        maintenance = ("OFF", "DRAINING", "READY", "FAILED")[snap.maintenance]
        storage = (f"mounted={snap.mounted}, healthy={snap.healthy}, writer_open={snap.writer_open}"
                   if snap.storage_valid else self.i18n.tr("maintenance.unavailable"))
        self.firmware_summary.setText(
            f"{self.i18n.tr('maintenance.firmware_source')} · firmware {snap.firmware} · sample #{snap.sequence} · {age:.1f}s · {freshness}\n"
            f"Lifecycle={DiagnosticValue_Format('firmware','lifecycle',snap.lifecycle,self.i18n)} · maintenance={DiagnosticValue_Format('firmware','maintenance',snap.maintenance,self.i18n)} · cleanup_pending={snap.cleanup_pending}\n"
            f"TF: {storage} · log_fault={DiagnosticValue_Format('firmware','log_fault',snap.log_fault,self.i18n)} · reboot_required={snap.reboot_required}")

    def _render_legacy_firmware(self, snap):
        now = time.monotonic_ns()
        age = max(0, (now - snap.received_ns) / 1e9)
        freshness = self.i18n.tr("maintenance.stale" if age > 3 else "maintenance.received")
        states = ("BOOT", "SELF_TEST", "PREFLIGHT", "READY", "FLIGHT", "RECOVERY", "LANDED", "POSTFLIGHT", "FAULT")
        lines = [f"FC maintenance.serial.0_0 · firmware {snap.firmware} · {age:.1f}s · {freshness}",
            f"Lifecycle={DiagnosticValue_Format('firmware','lifecycle',snap.lifecycle,self.i18n)} · ready={int(snap.ready)} · block={DiagnosticValue_Format('firmware','block',snap.blocking_mask,self.i18n)} · warn={DiagnosticValue_Format('firmware','warn',snap.warning_mask,self.i18n)} · attitude={DiagnosticValue_Format('firmware','attitude',snap.attitude,self.i18n)}"]
        if snap.capabilities is not None:
            lines.append("Capabilities: " + " · ".join(f"{key}=0x{value:08X}" for key, value in
                zip(("compiled", "enabled", "present", "healthy"), snap.capabilities)))
        log = snap.storage
        if log is None:
            lines.append("LOG STATUS: " + (snap.storage_detail or self.i18n.tr("maintenance.unavailable")))
        else:
            log_age = max(0, (now - log.received_ns) / 1e9)
            log_fresh = self.i18n.tr("maintenance.stale" if log_age > 3 else "maintenance.received")
            lines.append(f"LOG STATUS: {log_age:.1f}s · {log_fresh} · initialized={int(log.initialized)} · mounted={int(log.mounted)} · open={int(log.writer_open)} · healthy={int(log.healthy)} · writes={log.writes} · syncs={log.syncs} · errors={log.errors}")
        lines.append(self.i18n.tr("maintenance.legacy_age"))
        self.firmware_summary.setText("\n".join(lines))

    def retranslate(self):
        self.swd_copy.setText(Text(self.i18n,'复制全部详情','Copy all details'))
        tr = self.i18n.tr
        self._telemetry_render_ns = 0
        self._render_firmware()
        self.diagnostic_tree.setHeaderLabels([tr("maintenance.entry"), tr("maintenance.state_reason"), tr("maintenance.value"), tr("maintenance.age"), tr("maintenance.origin")])
        self._diagnostic_render_ns = 0
        self._render_diagnostics()
        self.swd_status.setText(tr("maintenance.swd_unavailable"))
        self.btn_swd_attach.setText(Text(self.i18n,'连接','Connect'))
        self.btn_swd_detach.setText(Text(self.i18n,'断开','Disconnect'))
        self.btn_swd_attach.setToolTip(tr('swd.attach'))
        self.btn_swd_detach.setToolTip(tr('swd.detach'))
        self.btn_swd_import.setText(Text(self.i18n,'导入 ssdiag…','Import ssdiag…'))
        self.btn_swd_relocate.setText(Text(self.i18n,'选择 / 重定位 ELF…','Select / relocate ELF…'))
        self.btn_swd_relocate.setEnabled(False)
        self.swd_diagnostics.setHeaderLabels([tr('maintenance.entry'),tr('maintenance.state_reason'),tr('maintenance.value'),tr('maintenance.age')])
        self.swd_target_status.setText(tr('swd.detached'))
        self.target_identity.setText(tr('swd.target_unknown'))
        self.btn_swd_variables.setText(tr('watch.open'))
        self.btn_swd_details.setText(tr('swd.details'))
        self.swd_details.setWindowTitle(tr('swd.details'))
        self.btn_serial_details.setText(Text(self.i18n,'状态详情…','Status details…'))
        self.serial_details_dialog.setWindowTitle(Text(self.i18n,'维护状态详情','Maintenance status details'))
        self.sections.setTabText(0,Text(self.i18n,'SWD 调试','SWD debugging'))
        self.sections.setTabText(1,Text(self.i18n,'串口','Serial'))
        self.swd_group.setTitle(Text(self.i18n,'ssdiag 固件匹配与只读观测','ssdiag firmware match and read-only observations'))
        self.serial_group.setTitle(Text(self.i18n,'维护命令与 TF 导出','Maintenance commands and TF export'))
        self.tf_group.setTitle(Text(self.i18n,'TF 日志导出','TF log export'))
        self.console.retranslate()
        if hasattr(self,'export_dialog'):self.export_dialog.retranslate()
        self.watch_dialog.retranslate()
        self.set_swd_summary(self._summary_rows)
        self._render_serial_brief()
        self.summary.setTitle(Text(self.i18n,'遥测状态','Telemetry status'))
        self.summary.setToolTip(Text(self.i18n,'按遥测连接和接收时间独立更新；不会合并维护口或 SWD 的状态。','Updated independently from the telemetry connection and receive times; maintenance/SWD state is not merged.'))
        self.source.setText(tr("maintenance.source"))
        self.detail_source.setText(tr("maintenance.source"))
        for key, (label, _) in self.labels.items():
            label.setText(tr("maintenance." + key))
        self.btn_details.setText(tr("maintenance.details"))
        self.tree.setHeaderLabels([tr("maintenance.variable"), tr("maintenance.value"), tr("maintenance.age")])
        self.note.setText(tr("maintenance.note"))
        self.destination_label.setText(tr("maintenance.destination"))
        self.btn_destination.setText(Text(self.i18n,'设置默认目录…','Set default…'))
        self.btn_selected_download.setText(tr('maintenance.selected_copy'))
        self.destination_path.setPlaceholderText(tr("maintenance.destination_none"))
        self.cancel.setText(tr("transfer.cancel"))
        if self.state is not None:
            self.render(self.state)

    def _age(self, stamp, connected=True):
        if not stamp:
            return self.i18n.tr("maintenance.unavailable")
        age = max(0, (time.monotonic_ns() - stamp) / 1_000_000_000)
        return f"{age:.1f}s · " + self.i18n.tr("maintenance.stale" if age > 3 or not connected else "maintenance.received")

    def set_destination(self, destination):
        self.destination_path.setText(destination)
        self.destination_path.setToolTip(destination)
        self.destination_path.setCursorPosition(0)

    def render(self, state):
        self._render_firmware()
        self._render_serial_brief()
        self._render_diagnostics()
        self.state = state
        now = time.monotonic_ns()
        generation = state.session_generation
        if generation != self._telemetry_generation:
            if self._telemetry_generation is not None:
                self._telemetry_after = dict(self._telemetry_stamps)
            self._telemetry_generation = generation
            self._telemetry_render_ns = 0
        if (now-self._telemetry_render_ns < 250_000_000 and
                self._telemetry_connected == state.connected):
            return
        self._telemetry_render_ns = now
        self._telemetry_connected = state.connected
        unavailable = self.i18n.tr("maintenance.unavailable")
        system_stamp = state.handshake.last_preflight_status_rx_monotonic_ns
        sensor_stamp = state.sensor.host_rx_monotonic_ns
        receive_stamp = state.receive_health.last_rx_monotonic_ns
        stamps = dict(system=system_stamp, sensors=sensor_stamp, communication=receive_stamp)
        fresh = {key:bool(state.connected and stamp and
                          stamp > self._telemetry_after[key] and 0 <= now-stamp <= 3_000_000_000)
                 for key,stamp in stamps.items()}
        for key,stamp in stamps.items():
            self._telemetry_stamps[key] = max(self._telemetry_stamps[key],stamp or 0)
        mission_valid = fresh['system'] or (state.mission_started and fresh['communication'])
        warning = state.receive_health.warning or "none"
        if state.controller_restart_suspected:
            warning = Text(self.i18n,'检测到设备重启，等待重新确认状态','Device restart detected; waiting for renewed status')
        rows = {
            "system": [("selftest_passed", state.selftest_passed if fresh['system'] else unavailable),
                       ("system_ready", state.system_ready if fresh['system'] else unavailable)],
            "sensors": [("online", self.i18n.tr("maintenance.no_online")),
                        ("accel_mps2", state.sensor.accel_mps2 if fresh['sensors'] else unavailable),
                        ("gyro_radps", state.sensor.gyro_radps if fresh['sensors'] else unavailable)],
            "mission": [("mission_started", state.mission_started if mission_valid else unavailable),
                        ("source", (state.mission_start_source or unavailable) if mission_valid else unavailable)],
            "communication": [("gsp_crc_errors", state.receive_health.gsp_crc_errors if fresh['communication'] else unavailable),
                              ("air_parse_errors", state.receive_health.air_parse_errors if fresh['communication'] else unavailable),
                              ("warning", warning if fresh['communication'] else unavailable)],
        }
        ages = {key:self._age(stamp,state.connected) for key,stamp in stamps.items()}
        ages['mission'] = ages['communication'] if state.mission_started else ages['system']
        # Unknown/stale observations still need a scrollable inspection view.
        # Individual value labels carry validity; the frame does not gate input.
        self.summary.setEnabled(True)
        for key, values in rows.items():
            summary = "; ".join(f"{name}={value}" for name, value in values[:2])
            valid = mission_valid if key=='mission' else fresh[key]
            if not valid:summary = unavailable
            self.labels[key][1].setText(summary+' · '+ages[key])
            self.labels[key][1].setEnabled(valid)
        self.tree.clear()
        for key, values in rows.items():
            category = QTreeWidgetItem([self.i18n.tr("maintenance." + key)])
            self.tree.addTopLevelItem(category)
            for name, value in values:
                category.addChild(QTreeWidgetItem([name,str(value),ages[key]]))
            category.setExpanded(True)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)

    def _show_details(self):
        self.sections.setCurrentIndex(0)
        self._telemetry_render_ns = 0
        if self.state is not None:
            self.render(self.state)

    def show_catalog(self, ids):
        self.catalog.clear()
        if not ids:
            self.catalog.addItem(self.i18n.tr("maintenance.empty"))
        for file_id in ids:
            self.catalog.addItem(f"Mission {file_id:06d} · flight.sslog · closed")
            self.catalog.item(self.catalog.count()-1).setData(Qt.UserRole,file_id)
        self._Selection_Update()

    def FileJob_SetBusy(self,busy):
        self._tf_job_busy=bool(busy)
        self._Selection_Update()

    def _Selection_Update(self):
        item=self.catalog.currentItem()
        self.btn_selected_download.setEnabled(not self._tf_job_busy and item is not None and type(item.data(Qt.UserRole)) is int)
