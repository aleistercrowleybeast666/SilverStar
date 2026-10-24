"""Choose a destination for existing local files; no transport or copy work here."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout,
)
from ui.diagnostic_labels import Text
from ui.touch_scroll import TouchScroll_Enable


class DeviceExportDialog(QDialog):
    def __init__(self, i18n, sources, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.setWindowTitle(Text(i18n, "导出本机记录（仅复制）", "Export local recordings (copy only)"))
        self.resize(620, 360)
        layout = QVBoxLayout(self)
        source_label = QLabel(Text(i18n, f"来源：已选本机文件，共 {len(sources)} 个",
                                  f"Source: {len(sources)} selected local files"))
        source_label.setTextFormat(Qt.PlainText)
        layout.addWidget(source_label)
        self.files = QListWidget()
        self.files.addItems([str(path) for path in sources])
        TouchScroll_Enable(self.files)
        layout.addWidget(self.files)
        layout.addWidget(QLabel(Text(i18n, "导出目标", "Export destination")))
        self.target = QComboBox()
        self.target.addItem(Text(i18n, "电脑目录 / 有盘符的可移动盘", "PC folder / drive letter"), "directory")
        self.target.addItem(Text(i18n, "手机（MTP）", "Phone (MTP)"), "mtp")
        layout.addWidget(self.target)
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText(Text(i18n, "选择保存目录", "Choose a destination folder"))
        self.browse = QPushButton(Text(i18n, "浏览…", "Browse…"))
        row.addWidget(self.path, 1)
        row.addWidget(self.browse)
        layout.addLayout(row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Cancel).setText(Text(i18n, "取消", "Cancel"))
        layout.addWidget(self.buttons)
        self.target.currentIndexChanged.connect(self._update)
        self.path.textChanged.connect(self._update)
        self.browse.clicked.connect(self._browse)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._update()

    def _update(self, *_):
        phone = self.target.currentData() == "mtp"
        self.path.setVisible(not phone)
        self.browse.setVisible(not phone)
        self.note.setText(Text(self.i18n,
            "下一步选择已解锁手机的 MTP 文件夹。复制后回读校验，保留源文件。" if phone else
            "手机没有盘符时，请在上方选择“手机（MTP）”；普通目录选择器不会列出手机。复制并校验，保留源文件。",
            "Next, select an unlocked phone's MTP folder. Copy and verify by readback; keep sources." if phone else
            "For a phone without a drive letter, select Phone (MTP) above; the folder picker only lists filesystem destinations. Copy and verify; keep sources."))
        start = self.buttons.button(QDialogButtonBox.Ok)
        start.setText(Text(self.i18n, "下一步：选择手机位置…" if phone else "导出并校验",
                           "Next: choose phone folder…" if phone else "Export and verify"))
        start.setEnabled(phone or bool(self.path.text().strip()))

    def _browse(self):
        selected = QFileDialog.getExistingDirectory(self, self.windowTitle(), self.path.text())
        if selected:
            self.path.setText(selected)

    def selection(self):
        kind = self.target.currentData()
        destination = self.path.text().strip()
        return (kind, destination if kind == "directory" else "") if kind == "mtp" or destination else None


def DeviceExportDestination_Choose(i18n, sources, parent=None):
    dialog = DeviceExportDialog(i18n, sources, parent)
    try:
        return dialog.selection() if dialog.exec() == QDialog.Accepted else None
    finally:
        dialog.deleteLater()
