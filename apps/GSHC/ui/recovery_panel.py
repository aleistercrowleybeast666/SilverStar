"""Third-page recovery display and explicit TXT export, independent of log access."""
from pathlib import Path
import time
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QGroupBox, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout
from services.recovery_position import Recovery_Export, Recovery_Text
from ui.touch_scroll import TouchScroll_Enable


class RecoveryPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("落地寻回 / Recovery", parent)
        self.state = None
        layout = QVBoxLayout(self)
        self.confirm = QCheckBox("已确认发射点原点和初始 ENU 对向 / Confirm launch origin and true E/N orientation")
        self.confirm.setToolTip("仅确认显示基准，不更改飞控。ENU yaw=0 表示机体 +X 水平投影朝东；没有现场确认请勿勾选。")
        self.confirm.toggled.connect(self._Confirm)
        layout.addWidget(self.confirm)
        self.text = QPlainTextEdit()
        TouchScroll_Enable(self.text)
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(210)
        layout.addWidget(self.text)
        self.copy = QPushButton("复制 WGS84 坐标")
        self.copy.clicked.connect(self._Coordinates_Copy)
        self.map = QPushButton("手机地图入口 / OpenStreetMap")
        self.map.clicked.connect(self._Map_Open)
        layout.addWidget(self.copy)
        layout.addWidget(self.map)
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
        self.confirm.blockSignals(True)
        self.confirm.setChecked(bool(snapshot and snapshot["frame_confirmed"]))
        self.confirm.setEnabled(snapshot is not None and snapshot.get("kind") != "wgs84")
        self.confirm.blockSignals(False)
        text = Recovery_Text(snapshot)
        health = state.telemetry.HealthSnapshot_Get(time.monotonic_ns())
        if health is not None:
            battery = "未知" if health['battery_mv'] == 65535 else f"{health['battery_mv'] / 1000:.3f} V"
            age = "未知" if health['battery_age_s'] is None else f"{health['battery_age_s']:.1f} s"
            labels = ("电源", "主 IMU", "GNSS", "气压", "磁力计", "估计", "存储", "日志", "遥测", "调度", "配置/校准")
            states = [name + (":未知/过期" if not health['current_known_mask'] & (1 << bit) else
                             ":异常" if health['fault_mask'] & (1 << bit) else ":正常") for bit, name in enumerate(labels)]
            text += f"\n\n电压 {battery}；样本年龄 {age}\n" + "  ".join(states)
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
