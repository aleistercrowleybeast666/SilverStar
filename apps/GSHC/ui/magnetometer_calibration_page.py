"""Maintenance UART magnetometer collection and bounded ellipsoid fitting UI."""

from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from services.i18n import I18n, Language
from services.magnetometer_calibration import (
    MAG_CALIBRATION_MAX_SAMPLES,
    MagCalibration_Fit,
    MagCalibrationFitResult,
    MagCalibrationFitStatus,
)
from services.magnetometer_maintenance import (
    MagMaintenance_CalibrationCommandBuild,
    MagMaintenanceSample,
)
from transport.maintenance_backend import MagMaintenanceSession
from transport.serial_backend import list_serial_port_names
from ui.touch_scroll import TouchScroll_Wrap


class MagnetometerCalibrationPage(QWidget):
    def __init__(self, i18n: I18n, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.session = MagMaintenanceSession(self)
        self.session.sample_received.connect(self._on_sample)
        self.session.response_received.connect(self._on_response)
        self.session.connection_changed.connect(self._on_connection)
        self.session.error_occurred.connect(self._on_error)
        self.samples: list[tuple[float, float, float]] = []
        self.physical_device_id: int | None = None
        self.last_sequence: int | None = None
        self.collecting = False
        self.fit_result: MagCalibrationFitResult | None = None
        self.applied = False
        self.saved_generation: int | None = None
        self._save_poll_count = 0
        self._save_poll_timer = QTimer(self)
        self._save_poll_timer.setInterval(200)
        self._save_poll_timer.timeout.connect(self._poll_save)
        self._build_ui()
        self.refresh_ports()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        connection_content = QWidget()
        connection_layout = QVBoxLayout(connection_content)
        connection = QHBoxLayout()
        self.port_label = QLabel()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.baud_label = QLabel()
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(9600, 921600)
        self.baud_spin.setValue(230400)
        self.refresh_button = QPushButton()
        self.connect_button = QPushButton()
        self.disconnect_button = QPushButton()
        for widget in (
            self.port_label, self.port_combo, self.baud_label,
            self.baud_spin, self.refresh_button, self.connect_button,
            self.disconnect_button,
        ):
            connection.addWidget(widget)
        connection_layout.addLayout(connection)

        controls = QHBoxLayout()
        self.instance_label = QLabel()
        self.instance_spin = QSpinBox()
        self.instance_spin.setRange(0, 255)
        self.reference_label = QLabel()
        self.reference_spin = QDoubleSpinBox()
        self.reference_spin.setRange(10.0, 100.0)
        self.reference_spin.setDecimals(2)
        self.reference_spin.setValue(50.0)
        self.start_button = QPushButton()
        self.stop_button = QPushButton()
        self.clear_button = QPushButton()
        self.apply_button = QPushButton()
        self.save_button = QPushButton()
        self.read_button = QPushButton()
        self.clear_device_button = QPushButton()
        for widget in (
            self.instance_label, self.instance_spin,
            self.reference_label, self.reference_spin,
            self.start_button, self.stop_button, self.clear_button,
            self.apply_button, self.save_button, self.read_button,
            self.clear_device_button,
        ):
            controls.addWidget(widget)
        connection_layout.addLayout(controls)
        layout.addWidget(TouchScroll_Wrap(connection_content))

        self.cloud_view = gl.GLViewWidget()
        self.cloud_view.setMinimumHeight(300)
        self.cloud_view.opts["distance"] = 180
        self.cloud_item = gl.GLScatterPlotItem(
            pos=np.zeros((0, 3), dtype=np.float32), size=3.0,
            color=(0.1, 0.7, 1.0, 0.8), pxMode=True,
        )
        self.cloud_view.addItem(self.cloud_item)
        layout.addWidget(self.cloud_view, 1)

        metrics_content = QWidget()
        metrics_layout = QVBoxLayout(metrics_content)
        metrics = QGridLayout()
        self.status_label = QLabel()
        self.count_label = QLabel()
        self.identity_label = QLabel()
        self.generation_label = QLabel()
        self.coverage_label = QLabel()
        self.residual_label = QLabel()
        self.condition_label = QLabel()
        self.hard_iron_label = QLabel()
        self.soft_iron_label = QLabel()
        for row, widget in enumerate((
            self.status_label, self.count_label, self.identity_label,
            self.generation_label,
            self.coverage_label, self.residual_label, self.condition_label,
            self.hard_iron_label, self.soft_iron_label,
        )):
            metrics.addWidget(widget, row // 2, row % 2)
        metrics_layout.addLayout(metrics)
        layout.addWidget(TouchScroll_Wrap(metrics_content))

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button.clicked.connect(self._disconnect)
        self.start_button.clicked.connect(self.start_collection)
        self.stop_button.clicked.connect(self.stop_collection)
        self.clear_button.clicked.connect(self.clear_collection)
        self.apply_button.clicked.connect(self.apply_calibration)
        self.save_button.clicked.connect(self.save_calibration)
        self.read_button.clicked.connect(self.read_calibration)
        self.clear_device_button.clicked.connect(self.clear_device_calibration)
        self.instance_spin.valueChanged.connect(lambda _value: self.clear_collection())
        self.stop_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.status_text = "Disconnected"
        self._render_metrics()

    def _tr(self, zh: str, en: str) -> str:
        return zh if self.i18n.language is Language.ZH_CN else en

    def retranslate_ui(self) -> None:
        labels = (
            (self.port_label, "飞控维护串口", "FC maintenance port"),
            (self.baud_label, "波特率", "Baudrate"),
            (self.refresh_button, "刷新", "Refresh"),
            (self.connect_button, "连接", "Connect"),
            (self.disconnect_button, "断开", "Disconnect"),
            (self.instance_label, "磁力计实例", "Magnetometer instance"),
            (self.reference_label, "参考磁场 (µT)", "Reference field (µT)"),
            (self.start_button, "开始采集", "Start Collection"),
            (self.stop_button, "停止采集 / 拟合", "Stop Collection / Fit"),
            (self.clear_button, "清除", "Clear"),
            (self.apply_button, "应用到飞控", "Apply to FC"),
            (self.save_button, "保存校准", "Save Calibration"),
            (self.read_button, "读取状态", "Read Status"),
            (self.clear_device_button, "清除飞控校准", "Clear FC Calibration"),
        )
        for widget, zh, en in labels:
            widget.setText(self._tr(zh, en))
        self._render_metrics()

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        ports = list_serial_port_names()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current and current not in ports:
            self.port_combo.addItem(current)
        if current:
            self.port_combo.setCurrentText(current)

    def _connect(self) -> None:
        port = self.port_combo.currentText().strip()
        if not port:
            self.status_text = self._tr("请选择维护串口", "Select a maintenance port")
            self._render_metrics()
            return
        try:
            self.session.open(port, self.baud_spin.value())
        except RuntimeError as error:
            self._on_error(str(error))

    def _disconnect(self) -> None:
        self._save_poll_timer.stop()
        self.collecting = False
        self.session.close()
        self.stop_button.setEnabled(False)
        self.instance_spin.setEnabled(True)
        self.status_text = self._tr("已断开", "Disconnected")
        self._render_metrics()

    def close_session(self) -> bool:
        self._save_poll_timer.stop()
        self.collecting = False
        self.stop_button.setEnabled(False)
        self.instance_spin.setEnabled(True)
        return self.session.close()

    def clear_collection(self) -> None:
        if self.collecting:
            self.session.send(f"MAG {self.instance_spin.value()} STREAM STOP")
        self.collecting = False
        self.stop_button.setEnabled(False)
        self.instance_spin.setEnabled(True)
        self.samples.clear()
        self.fit_result = None
        self.applied = False
        self.saved_generation = None
        self.apply_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.physical_device_id = None
        self.last_sequence = None
        self.cloud_item.setData(pos=np.zeros((0, 3), dtype=np.float32))
        self._render_metrics()

    def start_collection(self) -> None:
        self.clear_collection()
        instance = self.instance_spin.value()
        if not self.session.send(f"MAG {instance} STREAM START"):
            self._on_error(self._tr("维护串口未连接", "Maintenance port is disconnected"))
            return
        self.collecting = True
        self.instance_spin.setEnabled(False)
        self.status_text = self._tr("正在采集", "Collecting")
        self.stop_button.setEnabled(True)
        self._render_metrics()

    def stop_collection(self) -> None:
        if not self.collecting:
            return
        self.collecting = False
        self.instance_spin.setEnabled(True)
        self.session.send(f"MAG {self.instance_spin.value()} STREAM STOP")
        self.stop_button.setEnabled(False)
        self.fit_result = MagCalibration_Fit(
            np.asarray(self.samples, dtype=np.float64).reshape((-1, 3)),
            self.reference_spin.value(),
        )
        self.status_text = self.fit_result.status.name
        self.apply_button.setEnabled(self.fit_ready)
        self._render_metrics()

    def apply_calibration(self) -> None:
        if not self.fit_ready or self.physical_device_id is None:
            return
        try:
            command = MagMaintenance_CalibrationCommandBuild(
                self.instance_spin.value(), self.physical_device_id,
                self.fit_result,
            )
        except ValueError as error:
            self._on_error(str(error))
            return
        if self.session.send(command):
            self.applied = False
            self.save_button.setEnabled(False)
            self.status_text = self._tr("等待飞控确认应用", "Waiting for FC apply confirmation")
            self._render_metrics()

    def save_calibration(self) -> None:
        if not self.applied:
            return
        if self.session.send(f"MAG {self.instance_spin.value()} CAL SAVE"):
            self._save_poll_count = 0
            self._save_poll_timer.start()
            self.status_text = self._tr("正在等待持久化确认", "Waiting for persistence")
            self._render_metrics()

    def read_calibration(self) -> None:
        self.session.send(f"MAG {self.instance_spin.value()} CAL READ")

    def clear_device_calibration(self) -> None:
        if self.session.send(f"MAG {self.instance_spin.value()} CAL CLEAR"):
            self.applied = False
            self.save_button.setEnabled(False)
            self.saved_generation = None
            self._save_poll_count = 0
            self._save_poll_timer.start()

    def _poll_save(self) -> None:
        self._save_poll_count += 1
        if self._save_poll_count > 25:
            self._save_poll_timer.stop()
            self._on_error(self._tr("保存确认超时", "Save confirmation timed out"))
            return
        self.read_calibration()

    def _on_sample(self, sample: MagMaintenanceSample) -> None:
        if not self.collecting or sample.instance != self.instance_spin.value():
            return
        if self.physical_device_id is None:
            self.physical_device_id = sample.physical_device_id
        if sample.physical_device_id != self.physical_device_id:
            self.collecting = False
            self.session.send(f"MAG {self.instance_spin.value()} STREAM STOP")
            self.stop_button.setEnabled(False)
            self.instance_spin.setEnabled(True)
            self._on_error(self._tr("设备身份在采集中变化", "Device identity changed"))
            return
        if self.last_sequence == sample.sequence:
            return
        self.last_sequence = sample.sequence
        if len(self.samples) >= MAG_CALIBRATION_MAX_SAMPLES:
            self.stop_collection()
            return
        self.samples.append(sample.field_uT)
        if len(self.samples) % 8 == 0:
            self.cloud_item.setData(pos=np.asarray(self.samples, dtype=np.float32))
        self._render_metrics()
        if len(self.samples) == MAG_CALIBRATION_MAX_SAMPLES:
            self.stop_collection()

    def _on_response(self, response: str) -> None:
        if response.startswith("ERR MAG "):
            self._save_poll_timer.stop()
            self.collecting = False
            self.stop_button.setEnabled(False)
            self.instance_spin.setEnabled(True)
            self.status_text = response
            self._render_metrics()
            return
        prefix = f"OK MAG {self.instance_spin.value()} CAL "
        if not response.startswith(prefix):
            return
        fields = dict(
            item.split("=", 1) for item in response[len(prefix):].split()
            if "=" in item
        )
        if fields.get("action") == "APPLY" and fields.get("accepted") == "1":
            self.applied = True
            self.save_button.setEnabled(True)
            self.status_text = self._tr("飞控已应用；尚未保存", "Applied on FC; not saved")
        elif "generation" in fields:
            self._on_calibration_status(fields)
        self._render_metrics()

    def _on_calibration_status(self, fields: dict[str, str]) -> None:
        if fields.get("load_error", "OK") != "OK":
            self._save_poll_timer.stop()
            self.status_text = self._tr(
                "飞控存储的校准无效：", "Stored FC calibration invalid: "
            ) + fields["load_error"]
            return
        if fields.get("failed") == "1":
            self._save_poll_timer.stop()
            self.status_text = self._tr("飞控持久保存失败", "FC persistence failed")
            return
        if fields.get("pending") == "1":
            return
        if fields.get("saved") == "1":
            try:
                generation = int(fields["generation"])
                physical_id = int(fields["physical_device_id"])
            except (KeyError, ValueError):
                return
            if self.physical_device_id is not None and physical_id != self.physical_device_id:
                self._save_poll_timer.stop()
                self.status_text = self._tr("飞控校准设备身份不匹配", "FC calibration identity mismatch")
                return
            if generation > 0:
                self.saved_generation = generation
                self._save_poll_timer.stop()
                self.status_text = self._tr("飞控已确认保存", "FC confirmed saved")
        elif fields.get("state") == "EMPTY" and self._save_poll_timer.isActive():
            self._save_poll_timer.stop()
            self.status_text = self._tr("飞控校准已清除", "FC calibration cleared")

    def _on_connection(self, connected: bool, text: str) -> None:
        if not connected:
            self.collecting = False
            self.stop_button.setEnabled(False)
            self.instance_spin.setEnabled(True)
        self.status_text = text
        self._render_metrics()

    def _on_error(self, text: str) -> None:
        self.status_text = text
        self._render_metrics()

    def _render_metrics(self) -> None:
        fit = self.fit_result
        self.status_label.setText(f"{self._tr('状态', 'Status')}: {self.status_text}")
        self.count_label.setText(f"{self._tr('样本', 'Samples')}: {len(self.samples)}")
        self.identity_label.setText(
            f"{self._tr('物理设备 ID', 'Physical device ID')}: "
            f"{self.physical_device_id if self.physical_device_id is not None else '—'}"
        )
        self.generation_label.setText(
            f"{self._tr('已保存代数', 'Saved generation')}: "
            f"{self.saved_generation if self.saved_generation is not None else '—'}"
        )
        if fit is None:
            for label in (self.coverage_label, self.residual_label,
                          self.condition_label, self.hard_iron_label,
                          self.soft_iron_label):
                label.setText("—")
            return
        self.coverage_label.setText(
            f"{self._tr('八象限覆盖', '8-octant coverage')}: {fit.octant_counts}"
        )
        self.residual_label.setText(
            f"RMS / max (µT): {fit.rms_residual_uT} / {fit.max_residual_uT}"
        )
        self.condition_label.setText(f"{self._tr('轴条件数', 'Axis condition')}: {fit.axis_condition}")
        self.hard_iron_label.setText(f"hard iron b (µT): {fit.hard_iron_uT}")
        self.soft_iron_label.setText(f"soft iron M: {fit.soft_iron}")

    @property
    def fit_ready(self) -> bool:
        return self.fit_result is not None and self.fit_result.status is MagCalibrationFitStatus.READY
