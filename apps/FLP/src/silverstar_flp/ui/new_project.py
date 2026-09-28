from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.path_preferences import ExistingDirectory_Get


class NewProjectDialog(QDialog):
    """Choose the project identity before importing its exact log/decoder pair."""

    def __init__(self, translator: Translator, directory: Path, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._default_root = ExistingDirectory_Get(directory)
        self._directory_automatic = True
        self.setModal(True)
        self.setWindowTitle(translator.Text_Get("action.new_project"))
        self.setMinimumWidth(720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(16)
        summary = QLabel(translator.Text_Get("dialog.new.summary"))
        summary.setWordWrap(True)
        summary.setObjectName("muted")
        layout.addWidget(summary)
        form = QFormLayout()
        form.setSpacing(14)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(translator.Text_Get("dialog.new.name_hint"))
        self.directory_edit = QLineEdit(str(directory))
        self.directory_edit.setPlaceholderText(translator.Text_Get("dialog.new.directory"))
        browse = QPushButton(translator.Text_Get("action.browse"))
        browse.clicked.connect(self._Directory_Select)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory_edit, 1)
        directory_row.addWidget(browse)
        form.addRow(translator.Text_Get("dialog.new.name"), self.name_edit)
        form.addRow(translator.Text_Get("dialog.new.directory"), directory_row)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            translator.Text_Get("dialog.new.create")
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            translator.Text_Get("dialog.new.cancel")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.name_edit.textChanged.connect(self._Directory_Derive)
        self.directory_edit.textEdited.connect(self._Directory_Customize)
        self.name_edit.textChanged.connect(self._Completion_Refresh)
        self.directory_edit.textChanged.connect(self._Completion_Refresh)
        self._Completion_Refresh()

    def Path_Get(self) -> Path:
        name = self.name_edit.text().strip()
        if not name.lower().endswith(".ssflp"):
            name += ".ssflp"
        return Path(self.directory_edit.text().strip()) / name

    def _Completion_Refresh(self) -> None:
        name = self.name_edit.text().strip()
        stem = name[:-6] if name.lower().endswith(".ssflp") else name
        reserved = {"CON", "PRN", "AUX", "NUL"} | {
            f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
        }
        valid = bool(stem) and not any(c in name for c in '<>:"/\\|?*')
        valid = valid and not any(ord(c) < 32 for c in name) and not stem.endswith((".", " "))
        valid = valid and stem.split(".")[0].upper() not in reserved
        valid = (
            valid
            and (
                not Path(self.directory_edit.text().strip()).exists()
                or Path(self.directory_edit.text().strip()).is_dir()
            )
            and bool(self.directory_edit.text().strip())
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def _Directory_Customize(self) -> None:
        self._directory_automatic = False

    def _Directory_Derive(self) -> None:
        if self._directory_automatic:
            name = self.name_edit.text().strip()
            if name.lower().endswith(".ssflp"):
                name = name[:-6]
            if name not in (".", "..") and not any(c in name for c in '<>:"/\\|?*'):
                self.directory_edit.setText(str(self._default_root / name))

    def _Directory_Select(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("dialog.new.directory"),
            str(ExistingDirectory_Get(Path(self.directory_edit.text()), self._default_root)),
        )
        if selected:
            self._Directory_Customize()
            self.directory_edit.setText(selected)
