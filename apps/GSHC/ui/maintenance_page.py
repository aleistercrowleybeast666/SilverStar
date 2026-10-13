"""Read-only diagnostics from existing telemetry; no variable read/write wire."""
from __future__ import annotations

import time

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

    def retranslate(self):
        tr = self.i18n.tr
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
