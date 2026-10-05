from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import ComponentView
from silverstar_fccg.ui.pages.base import LocalizedPage
from silverstar_fccg.ui.widgets import EngineeringTable


class PluginManagerPanel(LocalizedPage):
    installRequested = Signal()
    removeRequested = Signal(str)

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.plugins", "page.plugins.description")
        notice = QLabel()
        notice.setObjectName("noticeLabel")
        notice.setWordWrap(True)
        self.Text_Register(notice, "plugin.execution_safety_notice")
        self.root_layout.addWidget(notice)

        toolbar = QHBoxLayout()
        self.install_button = QPushButton()
        self.install_button.setObjectName("primaryButton")
        self.Text_Register(self.install_button, "action.install_plugin")
        self.install_button.clicked.connect(
            lambda _checked=False: self.installRequested.emit()
        )
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("dangerButton")
        self.Text_Register(self.remove_button, "action.remove_plugin")
        self.remove_button.clicked.connect(self._Remove_Emit)
        toolbar.addWidget(self.install_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addStretch(1)
        self.root_layout.addLayout(toolbar)

        self.plugin_table = self.Table_Register(
            EngineeringTable(
                (
                    "column.id",
                    "column.name",
                    "column.type",
                    "column.class",
                    "column.version",
                    "column.source",
                    "column.dependencies",
                    "column.provides",
                    "column.status",
                )
            )
        )
        self.root_layout.addWidget(self.plugin_table, 1)
        self._components: list[ComponentView] = []
        self.Language_Apply(translator)

    def Components_Set(self, components: Iterable[ComponentView]) -> None:
        self._components = list(components)
        self.plugin_table.Rows_Set(
            (
                component.component_id,
                component.name,
                self._translator.Text_Get(
                    f"component.type.{component.component_type.value}"
                ),
                self._translator.Text_Get(
                    f"component.class.{component.component_class}"
                )
                if component.component_class
                else "—",
                component.version,
                self._translator.Text_Get(
                    f"plugin.source.{component.source}"
                )
                if component.source
                else "—",
                ", ".join(component.dependencies) or "—",
                ", ".join(component.provides) or "—",
                self._translator.Text_Get(f"component.status.{component.status}"),
            )
            for component in self._components
        )

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        self.Components_Set(self._components)

    def _SelectedId_Get(self) -> str:
        row = self.plugin_table.currentRow()
        return self._components[row].component_id if 0 <= row < len(self._components) else ""

    def _Remove_Emit(self) -> None:
        component_id = self._SelectedId_Get()
        if component_id:
            self.removeRequested.emit(component_id)

class PluginManagerDialog(QDialog):
    """Modal host for declarative plugin management."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.resize(1180, 680)
        layout = QVBoxLayout(self)
        self.panel = PluginManagerPanel(translator)
        layout.addWidget(self.panel, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.Language_Apply(translator)

    def Components_Set(self, components: Iterable[ComponentView]) -> None:
        self.panel.Components_Set(components)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.setWindowTitle(translator.Text_Get("dialog.plugin_manager"))
        self.panel.Language_Apply(translator)
        close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText(translator.Text_Get("action.close"))
