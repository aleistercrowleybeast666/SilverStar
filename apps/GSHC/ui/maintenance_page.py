"""Read-only FC debug RAM status and separately identified AIR diagnostics."""
from __future__ import annotations

import time
from services.legacy_firmware_status import LegacyFirmwareSnapshot

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
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
        self.details = QDialog(self)
        self.details.resize(800, 480)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        detail_layout = QVBoxLayout(self.details)
        self.detail_source = QLabel()
        self.detail_source.setWordWrap(True)
        detail_layout.addWidget(self.detail_source)
        detail_layout.addWidget(self.tree)
        layout = QVBoxLayout(self)
        self.firmware_summary = QLabel()
        self.firmware_summary.setWordWrap(True)
        layout.addWidget(self.firmware_summary)
        self.swd_status = QLabel()
        self.swd_status.setWordWrap(True)
        layout.addWidget(self.swd_status)
        swd_row = QHBoxLayout()
        self.btn_swd_attach = QPushButton()
        self.btn_swd_detach = QPushButton()
        self.btn_swd_attach.setEnabled(False)
        self.btn_swd_detach.setEnabled(False)
        swd_row.addWidget(self.btn_swd_attach)
        swd_row.addWidget(self.btn_swd_detach)
        swd_row.addStretch(1)
        layout.addLayout(swd_row)
        self.swd_target_status = QLabel()
        self.swd_target_status.setTextFormat(Qt.PlainText)
        self.swd_target_status.setWordWrap(True)
        layout.addWidget(self.swd_target_status)
        self.diagnostic_status = QLabel()
        self.diagnostic_status.setWordWrap(True)
        layout.addWidget(self.diagnostic_status)
        self.diagnostic_tree = QTreeWidget()
        self.diagnostic_tree.setColumnCount(5)
        self.diagnostic_tree.setMinimumHeight(220)
        layout.addWidget(self.diagnostic_tree)
        self.source = QLabel()
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.summary = QGroupBox()
        grid = QGridLayout(self.summary)
        self.labels = {}
        for row, key in enumerate(("system", "sensors", "mission", "storage", "communication")):
            name, value = QLabel(), QLabel()
            name.setMaximumWidth(175)
            value.setWordWrap(True)
            self.labels[key] = (name, value)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        self.btn_details = QPushButton()
        self.btn_details.clicked.connect(self._show_details)
        grid.addWidget(self.btn_details, 5, 0, 1, 2)
        layout.addWidget(self.summary)
        self.tools = QVBoxLayout()
        layout.addLayout(self.tools)
        destination_row = QHBoxLayout()
        self.destination_label = QLabel()
        self.destination_path = QLineEdit()
        self.destination_path.setReadOnly(True)
        destination_row.addWidget(self.destination_label)
        destination_row.addWidget(self.destination_path, 1)
        layout.addLayout(destination_row)
        self.set_destination(str(i18n.settings.value(self.TF_DIRECTORY_KEY, "")))
        self.service_status = QLabel("LOGFILE: not negotiated")
        self.service_status.setWordWrap(True)
        layout.addWidget(self.service_status)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.catalog = QListWidget()
        self.catalog.setMaximumHeight(150)
        layout.addWidget(self.catalog)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.cancel = QPushButton()
        self.cancel.setEnabled(False)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel)
        layout.addLayout(progress_row)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.retranslate()

    def set_firmware_status(self, snapshot, detail=""):
        self.firmware_snapshot = snapshot
        self.firmware_detail = detail
        self._render_firmware()

    def set_diagnostics(self, entries, detail=""):
        self.diagnostic_entries = list(entries or [])[:16]
        self.diagnostic_status.setText(detail)
        self._diagnostic_render_ns = 0
        self._render_diagnostics()

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
            if receive_age > 3 or entry.age_ms is not None and receive_age + entry.age_ms / 1000 > 3:
                age += " · " + self.i18n.tr("maintenance.stale")
            fields = dict(entry.fields)
            for key in ('work_age_ms', 'data_age_ms'):
                if key in fields:
                    fields[key] = '?' if fields[key] == '4294967295' else str(int(fields[key]) + int(receive_age * 1000))
            values = " · ".join(f"{key}={value}" for key, value in fields.items())
            row = QTreeWidgetItem([entry.name.replace('_', ' ') + "\n" + entry.id,
                entry.state + ": " + entry.reason, values, age, entry.source])
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
            f"Lifecycle={states[snap.lifecycle]} · maintenance={maintenance} · cleanup_pending={snap.cleanup_pending}\n"
            f"TF: {storage} · log_fault={snap.log_fault} · reboot_required={snap.reboot_required}")

    def _render_legacy_firmware(self, snap):
        now = time.monotonic_ns()
        age = max(0, (now - snap.received_ns) / 1e9)
        freshness = self.i18n.tr("maintenance.stale" if age > 3 else "maintenance.received")
        states = ("BOOT", "SELF_TEST", "PREFLIGHT", "READY", "FLIGHT", "RECOVERY", "LANDED", "POSTFLIGHT", "FAULT")
        lines = [f"FC maintenance.serial.0_0 · firmware {snap.firmware} · {age:.1f}s · {freshness}",
            f"Lifecycle={states[snap.lifecycle]} · ready={int(snap.ready)} · block=0x{snap.blocking_mask:08X} · warn=0x{snap.warning_mask:08X} · attitude={snap.attitude}"]
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
        tr = self.i18n.tr
        self._render_firmware()
        self.diagnostic_tree.setHeaderLabels([tr("maintenance.entry"), tr("maintenance.state_reason"), tr("maintenance.value"), tr("maintenance.age"), tr("maintenance.origin")])
        self._diagnostic_render_ns = 0
        self._render_diagnostics()
        self.swd_status.setText(tr("maintenance.swd_unavailable"))
        self.btn_swd_attach.setText(tr('swd.attach'))
        self.btn_swd_detach.setText(tr('swd.detach'))
        self.swd_target_status.setText(tr('swd.detached'))
        self.summary.setTitle(tr("maintenance.summary"))
        self.source.setText(tr("maintenance.source"))
        self.detail_source.setText(tr("maintenance.source"))
        for key, (label, _) in self.labels.items():
            label.setText(tr("maintenance." + key))
        self.btn_details.setText(tr("maintenance.details"))
        self.details.setWindowTitle(tr("maintenance.details"))
        self.tree.setHeaderLabels([tr("maintenance.variable"), tr("maintenance.value"), tr("maintenance.age")])
        self.note.setText(tr("maintenance.note"))
        self.destination_label.setText(tr("maintenance.destination"))
        self.destination_path.setPlaceholderText(tr("maintenance.destination_none"))
        self.cancel.setText(tr("transfer.cancel"))
        if self.state is not None:
            self.render(self.state)

    def _age(self, stamp, connected=True):
        if stamp is None:
            return self.i18n.tr("maintenance.unavailable")
        age = max(0, (time.monotonic_ns() - stamp) / 1_000_000_000)
        return f"{age:.1f}s · " + self.i18n.tr("maintenance.stale" if age > 3 or not connected else "maintenance.received")

    def set_destination(self, destination):
        self.destination_path.setText(destination)
        self.destination_path.setToolTip(destination)
        self.destination_path.setCursorPosition(0)

    def render(self, state):
        self._render_firmware()
        self._render_diagnostics()
        self.state = state
        unavailable = self.i18n.tr("maintenance.unavailable")
        system_stamp = state.handshake.last_preflight_status_rx_monotonic_ns
        sensor_stamp = state.sensor.host_rx_monotonic_ns
        receive_stamp = state.receive_health.last_rx_monotonic_ns
        rows = {
            "system": [("selftest_passed", state.selftest_passed if system_stamp else unavailable),
                       ("system_ready", state.system_ready if system_stamp else unavailable)],
            "sensors": [("online", self.i18n.tr("maintenance.no_online")),
                        ("accel_mps2", state.sensor.accel_mps2 if sensor_stamp else unavailable),
                        ("gyro_radps", state.sensor.gyro_radps if sensor_stamp else unavailable)],
            "mission": [("mission_started", state.mission_started if state.connected and (system_stamp or state.mission_started) else unavailable),
                        ("source", state.mission_start_source or unavailable)],
            "storage": [("LOG INFO", self.i18n.tr("maintenance.not_queried"))],
            "communication": [("gsp_crc_errors", state.receive_health.gsp_crc_errors if receive_stamp else unavailable),
                              ("air_parse_errors", state.receive_health.air_parse_errors if receive_stamp else unavailable),
                              ("warning", state.receive_health.warning or ("none" if receive_stamp else unavailable))],
        }
        ages = {"system": self._age(system_stamp, state.connected), "sensors": self.i18n.tr("maintenance.time_unknown"),
                "mission": self.i18n.tr("maintenance.time_unknown"), "storage": unavailable,
                "communication": self.i18n.tr("maintenance.time_unknown")}
        for key, values in rows.items():
            summary = "; ".join(f"{name}={value}" for name, value in values[:2])
            if key in {"system", "communication"} and ages[key] == unavailable:
                summary = unavailable
            elif key == "sensors":
                summary = self.i18n.tr("maintenance.sample") + self._age(sensor_stamp, state.connected)
            elif key == "storage":
                summary = self.i18n.tr("maintenance.not_queried")
            self.labels[key][1].setText(summary + (" · " + ages[key] if ages[key] != unavailable and key != "sensors" else ""))
        if self.details.isVisible():
            self.tree.clear()
            for key, values in rows.items():
                category = QTreeWidgetItem([self.i18n.tr("maintenance." + key)])
                self.tree.addTopLevelItem(category)
                if key == "sensors":
                    category.addChild(QTreeWidgetItem([self.i18n.tr("maintenance.sample"),
                        self._age(sensor_stamp, state.connected), self.i18n.tr("maintenance.time_unknown")]))
                for name, value in values:
                    category.addChild(QTreeWidgetItem([name, str(value), ages[key]]))
                category.setExpanded(True)
            self.tree.resizeColumnToContents(0)
            self.tree.resizeColumnToContents(1)

    def _show_details(self):
        self.details.show()
        if self.state is not None:
            self.render(self.state)

    def show_catalog(self, ids):
        self.catalog.clear()
        if not ids:
            self.catalog.addItem(self.i18n.tr("maintenance.empty"))
        for file_id in ids:
            self.catalog.addItem(f"Mission {file_id:06d} · flight.sslog · closed")
