"""Small preflight magnetic-calibration workflow; all I/O stays in its owner."""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from services.magnetometer_calibration import (
    MAG_CALIBRATION_MAX_SAMPLES, MAG_CALIBRATION_MIN_OCTANT_SAMPLES,
    MAG_CALIBRATION_MIN_SAMPLES, MagCalibration_Fit, MagCalibrationFitStatus,
)
from services.magnetometer_workflow import (
    MagCalibrationDevice, MagCalibrationStatus, MagCalibrationTransport, MagSampleCollection,
)
from ui.diagnostic_labels import Text
from ui.magnetometer_preview import MagProjectionPreview
from ui.touch_scroll import TouchScroll_Wrap


class _MagFitWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, points, reference, parent):
        super().__init__(parent)
        self.points, self.reference = tuple(points), reference

    def run(self):
        try:
            result = MagCalibration_Fit(np.asarray(self.points).reshape((-1, 3)), self.reference)
            if not self.isInterruptionRequested():
                self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MagCalibrationDialog(QDialog):
    def __init__(self, transport: MagCalibrationTransport, i18n, parent=None):
        super().__init__(parent)
        self.transport, self.i18n = transport, i18n
        self.setModal(False)
        self.resize(640, 680)
        self.setMinimumWidth(510)
        self.devices_data = ()
        self.collection = self.fit_result = self.last_status = None
        self.fit_worker = None
        self.pending = ""
        self.read_role = "probe"
        self.capable = self.collecting = self.stopping = False
        self.closing = self.cleanup_done = self._allow_close = False
        self.applied_generation = None
        self._apply_base = None
        self.saved = False
        self._firmware_lock = ''
        self._collection_start = None
        self._collection_elapsed = 0.0
        self._fit_after_stop = False
        self.transport_dropped = 0
        self._message_pair = ("请先连接飞控维护串口。", "Connect the Flight Controller maintenance port first.")
        self._save_deadline = 0.0
        self.save_poll = QTimer(self)
        self.save_poll.setSingleShot(True)
        self.save_poll.setInterval(250)
        self.save_poll.timeout.connect(self._poll_save)
        outer = QVBoxLayout(self)
        body = QWidget()
        root = QVBoxLayout(body)
        self.body_scroll = TouchScroll_Wrap(body)
        outer.addWidget(self.body_scroll, 1)
        self.link = QLabel()
        self.note = QLabel()
        self.note.setWordWrap(True)
        root.addWidget(self.link)
        root.addWidget(self.note)
        form = QFormLayout()
        device_row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumContentsLength(12)
        self.refresh = QPushButton()
        device_row.addWidget(self.device, 1)
        device_row.addWidget(self.refresh)
        self.device_label = QLabel()
        form.addRow(self.device_label, device_row)
        self.reference = QDoubleSpinBox()
        self.reference.setRange(10.0, 100.0)
        self.reference.setDecimals(2)
        self.reference.setValue(50.0)
        self.reference.setSuffix(" µT")
        self.reference_label = QLabel()
        form.addRow(self.reference_label, self.reference)
        root.addLayout(form)
        self.count = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, MAG_CALIBRATION_MAX_SAMPLES)
        self.progress.setFormat("%v / %m")
        self.coverage = QLabel()
        self.quality = QLabel()
        self.device_state = QLabel()
        self.stage = QLabel()
        self.status = QLabel()
        for label in (self.link, self.note, self.count, self.coverage, self.quality, self.device_state, self.stage, self.status):
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
        root.addWidget(self.count)
        root.addWidget(self.progress)
        self.preview = MagProjectionPreview(i18n)
        self.preview_note = QLabel()
        self.preview_note.setWordWrap(True)
        root.addWidget(self.preview)
        root.addWidget(self.preview_note)
        root.addWidget(self.coverage)
        root.addWidget(self.quality)
        root.addWidget(self.device_state)
        root.addWidget(self.stage)
        root.addWidget(self.status)
        root.addStretch()
        actions = QGridLayout()
        self.start = QPushButton()
        self.stop_fit = QPushButton()
        self.apply_ram = QPushButton()
        self.save_device = QPushButton()
        for index, button in enumerate((self.start, self.stop_fit, self.apply_ram, self.save_device)):
            button.setMinimumHeight(34)
            actions.addWidget(button, index // 2, index % 2)
        outer.addLayout(actions)
        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = QPushButton()
        footer.addWidget(self.cancel_button)
        outer.addLayout(footer)
        self.refresh.clicked.connect(self._discover)
        self.device.currentIndexChanged.connect(self._device_changed)
        self.reference.valueChanged.connect(self._reference_changed)
        self.start.clicked.connect(self._start)
        self.stop_fit.clicked.connect(lambda: self._stop(True))
        self.apply_ram.clicked.connect(self._apply)
        self.save_device.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.request_close)
        transport.result_received.connect(self._result)
        transport.samples_received.connect(self._samples)
        transport.connection_changed.connect(self._connection)
        transport.ended.connect(self._ended)
        self.retranslate()

    def text(self, zh, en):
        return Text(self.i18n, zh, en)

    def _message(self, zh, en):
        self._message_pair = (zh, en)
        self.status.setText(self.text(zh, en))

    def retranslate(self):
        self.setWindowTitle(self.text("磁力计校准", "Magnetometer calibration"))
        self.device_label.setText(self.text("磁设备", "Magnetic device"))
        self.reference_label.setText(self.text("拟合参考场强", "Fit reference field"))
        self.refresh.setText(self.text("刷新设备", "Refresh devices"))
        self.start.setText(self.text("开始采集", "Start collection"))
        self.stop_fit.setText(self.text("停止并拟合", "Stop and fit"))
        self.apply_ram.setText(self.text("应用至 RAM", "Apply to RAM"))
        self.save_device.setText(self.text("保存至设备", "Save to device"))
        self.cancel_button.setText(self.text("关闭 / 取消", "Close / cancel"))
        self.note.setText(self.text(
            "在 PC 拟合硬铁偏置和软铁矩阵。请缓慢转动设备，覆盖所有方向。安装方向尚未验证；结果不代表机体系校准或导航就绪。",
            "The PC fits hard-iron bias and the soft-iron matrix. Slowly rotate through all directions. Installation axes are unverified; this does not establish body-frame calibration or navigation readiness."))
        self.reference.setToolTip(self.text("输入本次拟合使用的参考磁场强度。", "Reference magnetic-field magnitude used for this fit."))
        self.device.setToolTip(self.text("ID 是工程物理设备编号，不是硬件序列号。", "ID is the project physical-device identifier, not a hardware serial number."))
        self.preview.retranslate()
        self.preview_note.setText(self.text(
            '三平面预览：蓝色原始点，绿色拟合校正点（尚非设备回读），虚线为参考场。显示最多1024点，完整样本参与拟合；图形不能代替覆盖与质量检查。',
            'Three-plane preview: blue raw, green fit correction (not device readback), dashed reference field. Display is limited to 1024 points; fitting uses every sample. Coverage and quality checks remain authoritative.'))
        self._render()

    def open_session(self):
        if self.isVisible():
            return
        self.closing = self.cleanup_done = self._allow_close = False
        self.collection = self.fit_result = self.last_status = None
        self.applied_generation = None
        self.saved = self.capable = self.collecting = self.stopping = False
        self.pending = ""
        self.retranslate()
        self.show()
        self._discover()

    def _selected(self):
        return self.device.currentData()

    def _send(self, operation, action):
        if self.pending or self.closing:
            return False
        try:
            accepted = action()
        except (ValueError, TypeError, OverflowError) as exc:
            self._message("未发送：" + str(exc), "Not sent: " + str(exc))
            self._render()
            return False
        if not accepted:
            self._message("未发送：维护串口繁忙或已断开。", "Not sent: maintenance port busy or disconnected.")
            self._render()
            return False
        self.pending = operation
        self._render()
        return True

    def _discover(self):
        if self.pending or self.collecting or self.fit_worker or self.transport.stream_device is not None:
            return
        self.capable = False
        self.devices_data = ()
        self.device.clear()
        if not self.transport.begin():
            self._message("请先连接飞控维护串口，且结束其他传输。", "Connect the maintenance port and finish other transfers first.")
            self._render()
            return
        self._send("devices", self.transport.devices)

    def _device_changed(self, *_):
        self._firmware_lock = ''
        self.fit_result = self.collection = self.last_status = None
        self.applied_generation = None
        self.saved = self.capable = False
        selected = self._selected()
        if selected is not None and not self.pending and not self.closing:
            self.read_role = "probe"
            self._send("read", lambda: self.transport.read(selected))
        self._render()

    def _reference_changed(self, *_):
        # A changed fit input invalidates the previous solution, not device RAM.
        if self.fit_result is not None:
            self.fit_result = None
            self.applied_generation = None
            self.saved = False
            self._message("参考场强已改变，请重新采集拟合。", "Reference field changed; collect and fit again.")
            self._render()

    def _start(self):
        selected = self._selected()
        if not self.start.isEnabled() or selected is None:
            return
        self.collection = MagSampleCollection(selected)
        self.fit_result = None
        self.applied_generation = None
        self.saved = False
        self.transport_dropped = 0
        self._collection_start = None
        self._collection_elapsed = 0.0
        self._send("start", lambda: self.transport.stream(selected, True))

    def _CollectionClock_Stop(self):
        if self._collection_start is not None:
            self._collection_elapsed = max(0,time.monotonic()-self._collection_start)
            self._collection_start = None

    def _stop(self, fit=True):
        selected = self._selected()
        if selected is None or self.pending or self.transport.stream_device is None:
            return
        self.collecting = False
        self._CollectionClock_Stop()
        self._fit_after_stop = fit
        self.stopping = True
        self._message("正在确认停止采集…", "Waiting for stream STOP confirmation…")
        self._send("stop", lambda: self.transport.stream(selected, False))

    def _samples(self, samples, dropped):
        if not self.collecting or self.collection is None or self.closing:
            return
        self.transport_dropped = dropped
        try:
            for sample in samples:
                self.collection.add(sample)
        except ValueError as exc:
            self.fit_result = None
            self._stop(False)
            self._message(str(exc), str(exc))
            return
        self._render()
        if len(self.collection.points) == MAG_CALIBRATION_MAX_SAMPLES:
            self._stop(True)

    def _fit(self):
        if self.collection is None or self.fit_worker is not None:
            return
        worker = _MagFitWorker(self.collection.points, self.reference.value(), self)
        self.fit_worker = worker
        worker.completed.connect(self._fitted)
        worker.failed.connect(lambda error: self._message(error, error))
        worker.finished.connect(self._fit_finished)
        self._message("正在 PC 拟合…", "Fitting on the PC…")
        self._render()
        worker.start()

    def _fitted(self, result):
        if self.closing:
            return
        self.fit_result = result
        if result.status is MagCalibrationFitStatus.READY:
            self._message("拟合通过，尚未应用。", "Fit passed; not applied yet.")
        else:
            self._message("拟合未通过，请改善覆盖后重新采集。", "Fit rejected; improve coverage and collect again.")
        self._render()

    def _fit_finished(self):
        worker, self.fit_worker = self.fit_worker, None
        if worker is not None:
            worker.deleteLater()
        self._render()
        self._maybe_close()

    def _apply(self):
        if not self.apply_ram.isEnabled():
            return
        self._apply_base = self.last_status.generation
        self.applied_generation = None
        self.saved = False
        self._send("apply", lambda: self.transport.apply(self._selected(), self.fit_result))

    def _save(self):
        if not self.save_device.isEnabled():
            return
        self.saved = False
        self._save_deadline = time.monotonic() + 30.0
        self._send("save", lambda: self.transport.save(self._selected()))

    def _poll_save(self):
        if self.closing or self.applied_generation is None:
            return
        if time.monotonic() >= self._save_deadline:
            self._message("保存超时，未确认持久化；当前仅 RAM 已确认生效。", "Save timed out; persistence unconfirmed. Only RAM application was confirmed.")
            self._render()
            return
        self.read_role = "save"
        self._send("read", lambda: self.transport.read(self._selected()))

    def _result(self, operation, result, error):
        if operation != self.pending:
            return
        self.pending = ""
        if self.closing:
            self._render()
            return
        try:
            if error:
                if operation == "read":
                    self.applied_generation = None
                raise ValueError(error)
            if operation == "devices":
                if not isinstance(result, tuple) or len(result) > 32 or not all(
                        isinstance(row, MagCalibrationDevice) for row in result):
                    raise ValueError("Invalid magnetic device result")
                self.devices_data = result
                self.device.blockSignals(True)
                self.device.clear()
                for row in self.devices_data:
                    self.device.addItem(f"MAG {row.instance} · {row.name} · ID {row.physical_device_id}", row)
                self.device.blockSignals(False)
                if not self.devices_data:
                    self._message("未发现磁设备。", "No magnetic devices found.")
                self._device_changed()
            elif operation == "read":
                if not isinstance(result, MagCalibrationStatus):
                    raise ValueError("Invalid magnetic calibration status result")
                self._read_result(result)
            else:
                selected = self._selected()
                if not isinstance(result, dict):
                    raise ValueError("Invalid magnetic calibration action result")
                if operation in ("start", "stop"):
                    expected = "STARTED" if operation == "start" else "STOPPED"
                    if result.get("state") != expected:
                        raise ValueError("Magnetic stream state was not confirmed")
                    self.collecting = operation == "start"
                    self.stopping = False
                    if self.collecting:
                        self._collection_start = time.monotonic()
                        self._message("采集中，请覆盖各个方向。", "Collecting; rotate through all directions.")
                    elif self._fit_after_stop:
                        self._fit()
                elif result.get("action") != operation.upper() or result.get("accepted") != "1":
                    raise ValueError("Magnetic calibration action was not accepted")
                else:
                    self.read_role = operation
                    self._message("设备已受理，正在读取确认…", "Accepted; reading device state for confirmation…")
                    self._send("read", lambda: self.transport.read(selected))
        except (ValueError, TypeError) as exc:
            self.saved = False
            if 'code=LOCKED' in str(exc).split():
                self._firmware_lock = next((word[7:] for word in str(exc).split() if word.startswith('reason=')), 'UNKNOWN')
                self.capable = False
            if operation == "save" or operation == "read" and self.read_role == "save":
                if self.applied_generation is None:
                    self._message("保存未确认；设备校准状态已改变或未知。 " + str(exc),
                                  "Save unconfirmed; device calibration changed or is unknown. " + str(exc))
                else:
                    self._message("保存失败或未确认；当前仅 RAM 已确认生效。 " + str(exc),
                                  "Save failed or unconfirmed; only RAM application was confirmed. " + str(exc))
            else:
                if operation == "read":
                    self.capable = False
                    self.applied_generation = None
                self._message("操作失败，未确认成功：" + str(exc), "Operation failed; success unconfirmed: " + str(exc))
        self._render()

    def _read_result(self, status):
        self._firmware_lock = ''
        self.last_status = status
        if self.read_role == "probe":
            self.capable = True
            self._message("磁校准接口已响应，可开始采集。", "Magnetic calibration interface responded; collection is available.")
        elif self.read_role == "apply":
            if (status.state != "APPLIED" or status.generation == self._apply_base
                    or status.pending or status.failed or status.load_error != "OK"):
                raise ValueError("New RAM calibration generation was not confirmed")
            self.applied_generation = status.generation
            self._message("RAM 已生效；尚未保存，断电会丢失。", "Applied in RAM; not saved and may be lost on power-off.")
        elif self.read_role == "save":
            if status.state != "APPLIED" or status.generation != self.applied_generation:
                self.applied_generation = None
                raise ValueError("Calibration generation changed; RAM identity is unconfirmed")
            # SAVE retains previous failure fields until the new owner write
            # completes. A pending retry is not a terminal result for this SAVE.
            if not status.pending and (status.failed or status.load_error != "OK"):
                raise ValueError("Device persistence failed: " + status.load_error)
            if status.saved and not status.pending:
                self.saved = True
                self._message("已保存：READ 已确认同一 generation，saved=1、pending=0。",
                              "Saved: READ confirmed the same generation, saved=1 and pending=0.")
            else:
                self._message("保存处理中；尚未确认持久化。", "Save pending; persistence is not confirmed yet.")
                self.save_poll.start()

    def _connection(self, connected, detail):
        if not connected:
            self._firmware_lock = ''
            self._CollectionClock_Stop()
            self.save_poll.stop()
            self.collecting = self.capable = self.saved = False
            self.pending = ""
            self.applied_generation = self.last_status = self.fit_result = None
            self._message("连接已失效，已取消本地采集；设备状态未知。 " + detail,
                          "Connection lost; local collection cancelled. Device state is unknown. " + detail)
        self._render()

    def _render(self):
        self.preview.set_samples(self.collection.points if self.collection is not None else (),
                                 self.fit_result, self.reference.value())
        capabilities = self.transport.capabilities()
        connected = capabilities.connected
        operations = capabilities.operations
        label = self.text("传输：维护串口（当前唯一实现） · ", "Transport: maintenance serial (only implementation) · ")
        if capabilities.transport != "maintenance_serial":
            label = self.text("传输：", "Transport: ") + capabilities.transport + " · "
        self.link.setText(label
                          + self.text("已连接" if connected else "未连接", "Connected" if connected else "Disconnected"))
        count = len(self.collection.points) if self.collection else 0
        discarded = (self.collection.discarded if self.collection else 0) + self.transport_dropped
        elapsed = max(0,time.monotonic()-self._collection_start) if self._collection_start is not None else self._collection_elapsed
        self.count.setText(self.text(f"样本容量 {count}/{MAG_CALIBRATION_MAX_SAMPLES}（不是质量进度），最少 {MAG_CALIBRATION_MIN_SAMPLES}；丢弃 {discarded}；采集 {elapsed:.1f}s",
                                     f"Sample capacity {count}/{MAG_CALIBRATION_MAX_SAMPLES} (not quality), minimum {MAG_CALIBRATION_MIN_SAMPLES}; discarded {discarded}; collection {elapsed:.1f}s"))
        self.progress.setFormat(self.text('样本容量 %v / %m','Sample capacity %v / %m'))
        phase = ((f'固件锁定（{self._firmware_lock}）',f'Firmware locked ({self._firmware_lock})') if self._firmware_lock else
                 ('已保存','Saved') if self.saved else
                 ('保存并读取确认','Saving and verifying') if self.pending=='save' or self.save_poll.isActive() else
                 ('读取确认','Verifying device state') if self.pending=='read' else
                 ('应用至 RAM','Applying to RAM') if self.pending=='apply' else
                 ('PC 拟合','PC fitting') if self.fit_worker is not None else
                 ('停止采集确认','Confirming STOP') if self.stopping else
                 ('采集','Collecting') if self.collecting else
                 ('RAM 已确认，尚未保存','RAM confirmed; not saved') if self.applied_generation is not None else
                 ('拟合已评估，尚未应用','Fit evaluated; not applied') if self.fit_result is not None else
                 ('等待采集','Awaiting collection'))
        self.stage.setText(self.text('阶段：','Stage: ')+self.text(*phase))
        self.progress.setValue(count)
        device_status = self.last_status
        if device_status is None:
            state_text = self.text("设备状态：未确认", "Device state: unconfirmed")
        elif device_status.state == "EMPTY":
            state_text = self.text("设备状态：尚未应用磁校准", "Device state: no magnetic calibration applied")
        else:
            if device_status.pending:
                persistence = self.text("保存处理中", "save pending")
            elif device_status.failed or device_status.load_error != "OK":
                persistence = self.text("保存失败，仅 RAM", "save failed; RAM only")
            elif device_status.saved:
                persistence = self.text("已保存", "saved")
            else:
                persistence = self.text("尚未保存，仅 RAM", "not saved; RAM only")
            state_text = self.text("设备 READ 状态：RAM 生效 · ", "Device READ state: RAM applied · ") + persistence
        self.device_state.setText(state_text)
        self.device_state.setToolTip(str(device_status) if device_status else "")
        fit = self.fit_result
        if fit is None:
            self.coverage.setText(self.text("覆盖：停止并拟合后评估。", "Coverage: evaluated after STOP and fit."))
            self.quality.setText(self.text("质量：尚未拟合。", "Quality: not fitted."))
        else:
            covered = sum(c >= MAG_CALIBRATION_MIN_OCTANT_SAMPLES for c in fit.octant_counts)
            self.coverage.setText(self.text(f"覆盖 {covered}/8 · 八分区计数 {fit.octant_counts}", f"Coverage {covered}/8 · Octant counts {fit.octant_counts}"))
            metrics = ""
            if fit.rms_residual_uT is not None:
                metrics = f" · RMS {fit.rms_residual_uT:.3f} µT · max {fit.max_residual_uT:.3f} µT · condition {fit.axis_condition:.3f}"
            names = {
                MagCalibrationFitStatus.READY: ("通过", "Passed"),
                MagCalibrationFitStatus.INVALID_INPUT: ("输入无效", "Invalid input"),
                MagCalibrationFitStatus.INSUFFICIENT_SAMPLES: ("样本不足", "Insufficient samples"),
                MagCalibrationFitStatus.DEGENERATE_GEOMETRY: ("采样几何退化", "Degenerate geometry"),
                MagCalibrationFitStatus.INSUFFICIENT_COVERAGE: ("方向覆盖不足", "Insufficient coverage"),
                MagCalibrationFitStatus.EXCESSIVE_RESIDUAL: ("残差过大", "Excessive residual"),
            }
            self.quality.setText(self.text("质量：", "Quality: ") + self.text(*names[fit.status]) + metrics)
        busy = bool(self.pending or self.fit_worker or self.closing or self.save_poll.isActive())
        stream = self.transport.stream_device is not None
        ready = connected and self.capable and self._selected() is not None and not busy
        self.device.setEnabled(not busy and not stream)
        self.refresh.setEnabled(not busy and not stream and "devices" in operations)
        self.reference.setEnabled(not busy and not stream)
        self.start.setEnabled(ready and not stream and "stream" in operations)
        self.stop_fit.setEnabled(connected and stream and not self.pending and not self.closing)
        self.apply_ram.setEnabled(ready and not stream and fit is not None
                                  and fit.status is MagCalibrationFitStatus.READY and self.last_status is not None
                                  and {"apply", "read"} <= operations)
        self.save_device.setEnabled(ready and not stream and self.applied_generation is not None and not self.saved
                                    and {"save", "read"} <= operations)
        self.status.setText(self.text(*self._message_pair))

    def request_close(self):
        if self._allow_close:
            return self.fit_worker is None
        if not self.isVisible() and not self.transport.session_active and self.fit_worker is None:
            self._allow_close = True
            return True
        self.closing = True
        self.collecting = False
        self._CollectionClock_Stop()
        self.save_poll.stop()
        if self.fit_worker is not None:
            self.fit_worker.requestInterruption()
        self._message("正在清理采集订阅并确认停止…", "Removing the sample subscription and confirming STOP…")
        self.transport.end()
        self._render()
        if self.cleanup_done and self.fit_worker is None:
            self._maybe_close()
        return self._allow_close and self.fit_worker is None

    def _ended(self, confirmed, detail):
        if not confirmed and self.transport.capabilities().connected:
            self.closing = False
            self._message("停止未确认，请重试关闭或断开维护串口。 " + detail,
                          "STOP unconfirmed; retry closing or disconnect maintenance. " + detail)
            self._render()
            return
        self.cleanup_done = True
        QTimer.singleShot(0, self._maybe_close)

    def _maybe_close(self):
        if self.closing and self.cleanup_done and self.fit_worker is None:
            self._allow_close = True
            super().reject()

    def reject(self):
        self.request_close()

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.request_close()

    def shutdown(self):
        if self.fit_worker is not None:
            self.fit_worker.requestInterruption()
            return self.fit_worker.wait(1000)
        return True
