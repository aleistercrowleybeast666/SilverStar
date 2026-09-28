from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.path_preferences import ExistingDirectory_Get


class ProjectIdentityForm(QWidget):
    completionChanged = Signal()

    def __init__(self, translator: Translator, default_root: Path | None = None) -> None:
        super().__init__()
        self._translator = translator
        self._default_root = ExistingDirectory_Get(default_root)
        self._output_automatic = True
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)
        layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.setFormAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self.name_label = QLabel()
        self.name_label.setMinimumHeight(32)
        self.name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumSize(480, 32)
        self.name_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.name_edit.textChanged.connect(
            lambda _text: self.completionChanged.emit()
        )
        layout.addRow(self.name_label, self.name_edit)

        self.output_label = QLabel()
        self.output_label.setMinimumHeight(32)
        self.output_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        output_widget = QWidget()
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(10)
        self.output_edit = QLineEdit()
        self.output_edit.setMinimumHeight(32)
        self.output_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.output_edit.textChanged.connect(
            lambda _text: self.completionChanged.emit()
        )
        self.browse_button = QPushButton()
        self.browse_button.setMinimumHeight(32)
        self.browse_button.clicked.connect(self._Output_Browse)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.browse_button)
        layout.addRow(self.output_label, output_widget)
        self.name_edit.textChanged.connect(self._Output_Derive)
        self.output_edit.textEdited.connect(self._Output_Customize)
        self._Output_Derive()
        self.Language_Apply(translator)

    def isComplete(self) -> bool:
        return bool(self.name_edit.text().strip() and self.output_edit.text().strip())

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.name_label.setText(translator.Text_Get("field.project_name"))
        self.name_edit.setPlaceholderText(
            translator.Text_Get("placeholder.project_name")
        )
        self.output_label.setText(translator.Text_Get("field.output_directory"))
        self.output_edit.setPlaceholderText(
            translator.Text_Get("placeholder.output_directory")
        )
        self.browse_button.setText(translator.Text_Get("action.browse"))

    def _Output_Customize(self) -> None:
        self._output_automatic = False

    def _Output_Derive(self) -> None:
        if self._output_automatic:
            name = self.name_edit.text().strip()
            # Invalid names are rejected by project creation, never used as paths.
            if name not in (".", "..") and not any(c in name for c in '<>:"/\\|?*'):
                self.output_edit.setText(str(self._default_root / name))

    def _Output_Browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("dialog.select_output_directory"),
            str(self._default_root if self._output_automatic else
                ExistingDirectory_Get(Path(self.output_edit.text()), self._default_root)),
        )
        if selected:
            self._Output_Customize()
            self.output_edit.setText(selected)


class NewProjectWizard(QDialog):
    """Compact identity dialog; configuration continues through the main pages."""

    def __init__(self, translator: Translator, parent=None, *, default_root: Path | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setModal(True)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("muted")
        layout.addWidget(self.summary_label)

        self.identity_page = ProjectIdentityForm(translator, default_root)
        self.identity_page.completionChanged.connect(self._Completion_Refresh)
        layout.addWidget(self.identity_page)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.setMinimumWidth(720)
        self.Language_Apply(translator)
        self._Completion_Refresh()

    def WizardData_Get(self) -> dict[str, Any]:
        return {
            "name": self.identity_page.name_edit.text().strip(),
            "output_directory": self.identity_page.output_edit.text().strip(),
        }

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.setWindowTitle(translator.Text_Get("dialog.new_project"))
        self.summary_label.setText(translator.Text_Get("wizard.identity_summary"))
        self.identity_page.Language_Apply(translator)
        create_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if create_button is not None:
            create_button.setText(translator.Text_Get("wizard.finish"))
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText(translator.Text_Get("action.cancel"))

    def _Completion_Refresh(self) -> None:
        create_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if create_button is not None:
            create_button.setEnabled(self.identity_page.isComplete())
