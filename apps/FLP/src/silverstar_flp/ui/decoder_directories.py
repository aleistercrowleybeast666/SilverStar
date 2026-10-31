"""User-owned bounded exact-decoder search locations, independent of projects."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QVBoxLayout,
)


class DecoderDirectoriesDialog(QDialog):
    def __init__(self, translator, directories, parent=None):
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.Text_Get("action.decoder_directories"))
        self.resize(660, 350)
        layout = QVBoxLayout(self)
        note = QLabel(translator.Text_Get("decoder_directories.note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.directories = QListWidget()
        self.directories.addItems([str(path) for path in directories])
        layout.addWidget(self.directories, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton(translator.Text_Get("decoder_directories.add"))
        self.remove_button = QPushButton(translator.Text_Get("decoder_directories.remove"))
        self.add_button.clicked.connect(self._Directory_Add)
        self.remove_button.clicked.connect(self._Directory_Remove)
        self.directories.currentRowChanged.connect(self._Controls_Update)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._Controls_Update()

    def Directories_Get(self):
        return tuple(Path(self.directories.item(index).text()) for index in range(self.directories.count()))

    def _Directory_Add(self):
        if self.directories.count() >= 4:
            return
        selected = QFileDialog.getExistingDirectory(self, self.windowTitle())
        if selected and Path(selected).resolve() not in self.Directories_Get():
            self.directories.addItem(str(Path(selected).resolve()))
        self._Controls_Update()

    def _Directory_Remove(self):
        row = self.directories.currentRow()
        if row >= 0:
            self.directories.takeItem(row)
        self._Controls_Update()

    def _Controls_Update(self, *_args):
        self.add_button.setEnabled(self.directories.count() < 4)
        self.remove_button.setEnabled(self.directories.currentRow() >= 0)
