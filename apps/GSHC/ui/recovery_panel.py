"""Third-page recovery display and explicit TXT export, independent of log access."""
from pathlib import Path
import time
from PySide6.QtWidgets import QCheckBox, QFileDialog, QGroupBox, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout
from services.recovery_position import Recovery_Export, Recovery_Text


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
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(210)
        layout.addWidget(self.text)
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
        self.confirm.setEnabled(snapshot is not None)
        self.confirm.blockSignals(False)
        self.text.setPlainText(Recovery_Text(snapshot))
        self.export.setEnabled(snapshot is not None)

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
