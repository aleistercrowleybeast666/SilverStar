"""Third-page recovery display and explicit TXT export, independent of log access."""
from pathlib import Path
import time
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QGroupBox, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout, QHBoxLayout, QLabel)
from services.recovery_position import Recovery_Export, Recovery_Text
from ui.touch_scroll import TouchScroll_Enable


class RecoveryPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("落地寻回 / Recovery", parent)
        self.state = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("尚无有效位置 / No received position", self)
        self.summary.setWordWrap(True)
        self.summary.setObjectName('recoverySummary')
        layout.addWidget(self.summary)
        self.health_summary = QLabel(self)
        self.health_summary.setWordWrap(True)
        layout.addWidget(self.health_summary)
        self.confirm = QCheckBox("已确认发射点原点和初始 ENU 对向 / Confirm launch origin and true E/N orientation")
        self.confirm.setToolTip("仅确认显示基准，不更改飞控。ENU yaw=0 表示机体 +X 水平投影朝东；没有现场确认请勿勾选。")
        self.confirm.toggled.connect(self._Confirm)
        layout.addWidget(self.confirm)
        self.text = QPlainTextEdit()
        TouchScroll_Enable(self.text)
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(210)
        self.details = QPushButton("遥测与来源详情 / Telemetry details", self)
        self.details.setCheckable(True)
        self.details.toggled.connect(self.text.setVisible)
        layout.addWidget(self.details)
        layout.addWidget(self.text)
        self.text.hide()
        actions = QHBoxLayout()
        self.copy = QPushButton("复制 WGS84 坐标")
        self.copy.clicked.connect(self._Coordinates_Copy)
        self.map = QPushButton("手机地图入口 / OpenStreetMap")
        self.map.clicked.connect(self._Map_Open)
        actions.addWidget(self.copy)
        actions.addWidget(self.map)
        layout.addLayout(actions)
        self.export = QPushButton("导出寻回 TXT… / Export recovery TXT…")
        self.export.clicked.connect(self._Export)
        layout.addWidget(self.export)

    def _Snapshot(self):
        if self.state is None:
            return None
        return self.state.recovery.Snapshot_Get(time.monotonic_ns(), connected=self.state.connected,
                                                current_session=self.state.recovery_current_session)

    def _Confirm(self, confirmed):
        if self.state is not None:
            self.state.recovery.Frame_Confirm(confirmed)
            self.Render(self.state)

    def Render(self, state):
        self.state = state
        snapshot = self._Snapshot()
        now_ns = time.monotonic_ns()
        self.confirm.blockSignals(True)
        self.confirm.setChecked(bool(snapshot and snapshot["frame_confirmed"]))
        self.confirm.setEnabled(snapshot is not None and snapshot.get("kind") != "wgs84")
        self.confirm.setVisible(snapshot is None or snapshot.get("kind") != "wgs84")
        self.confirm.blockSignals(False)
        text = Recovery_Text(snapshot)
        health = state.telemetry.HealthSnapshot_Get(now_ns)
        received = state.handshake.last_air_rx_monotonic_ns
        link = "尚未收到遥测" if received is None else f"最近遥测 {max(0, now_ns - received) / 1e9:.1f} s 前"
        stage = "阶段未知" if state.telemetry.last_stage_id is None else f"已收阶段 ID {state.telemetry.last_stage_id}"
        health_text = f"{link}  ·  {stage}（事件历史不完整）\n健康信息：尚未采集 / 未收到"
        if health is not None:
            battery = "未知" if health['battery_mv'] == 65535 else f"{health['battery_mv'] / 1000:.3f} V"
            age = "未知" if health['battery_age_s'] is None else f"{health['battery_age_s']:.1f} s"
            labels = ("电源", "主 IMU", "GNSS", "气压", "磁力计", "估计", "存储", "日志", "遥测", "调度", "配置/校准")
            states = [name + (":未知/过期" if not health['current_known_mask'] & (1 << bit) else
                             ":异常" if health['fault_mask'] & (1 << bit) else ":正常") for bit, name in enumerate(labels)]
            text += f"\n\n电压 {battery}；样本年龄 {age}\n" + "  ".join(states)
            health_text = f"{link}  ·  电压 {battery}（样本 {age}）\n{stage}（事件历史不完整）\n" + "  ".join(states)
        self.health_summary.setText(health_text)
        if snapshot and snapshot.get('kind') == 'wgs84':
            age = '未知' if snapshot['age_s'] is None else f"{snapshot['age_s']:.1f} s"
            provenance = '当前连接的观测' if snapshot['source_current'] else '历史观测 / 未连接当前来源'
            self.summary.setText(f"{snapshot['latitude']:.7f}, {snapshot['longitude']:.7f}\n"
                                 f"WGS84 · 定位年龄 {age} · {provenance}")
        else:
            self.summary.setText('ENU 相对轨迹：请确认原点与初始朝向' if snapshot else '尚无有效实收位置 / No valid received position')
        self.text.setPlainText(text)
        absolute = bool(snapshot and snapshot.get("kind") == "wgs84")
        self.copy.setEnabled(absolute)
        self.map.setEnabled(absolute)
        self.export.setEnabled(snapshot is not None)

    def _Coordinates_Copy(self):
        snapshot = self._Snapshot()
        if snapshot and snapshot.get("kind") == "wgs84":
            QApplication.clipboard().setText(f"{snapshot['latitude']:.7f}, {snapshot['longitude']:.7f}")

    def _Map_Open(self):
        snapshot = self._Snapshot()
        if snapshot and snapshot.get("kind") == "wgs84":
            QDesktopServices.openUrl(QUrl(snapshot['map_url']))

    def _Export(self):
        snapshot = self._Snapshot()
        if snapshot is None:
            return
        selected, _ = QFileDialog.getSaveFileName(self, "导出最后观测位置 / Export last observation",
                                                  "recovery.txt", "Text (*.txt)")
        if not selected:
            return
        try:
            Recovery_Export(Path(selected), snapshot)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "寻回导出 / Recovery export",
                                f"未写入；请为历史输出选择新文件名。 / Not written; choose a new filename.\n{exc}")
