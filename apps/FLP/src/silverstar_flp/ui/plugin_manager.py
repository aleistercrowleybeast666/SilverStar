from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.container_packages import ContainerPluginDiscovery
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable


@dataclass(frozen=True, slots=True)
class PluginDisplayRow:
    plugin_type: str
    display_name: str
    plugin_id: str
    version: str
    source: str
    status: str


class PluginManagerDialog(QDialog):
    """Read-only view of active runtime plugins and safely discovered packages."""

    installRequested = Signal()
    refreshRequested = Signal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.resize(1180, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(12)
        self.title_label = QLabel()
        self.title_label.setObjectName("dialogHeading")
        layout.addWidget(self.title_label)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("muted")
        layout.addWidget(self.description_label)
        self.notice_label = QLabel()
        self.notice_label.setObjectName("noticeLabel")
        self.notice_label.setWordWrap(True)
        layout.addWidget(self.notice_label)
        toolbar = QHBoxLayout()
        self.install_button = QPushButton()
        self.install_button.setObjectName("primaryButton")
        self.install_button.clicked.connect(self.installRequested.emit)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        toolbar.addWidget(self.install_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 6)
        TouchScroll_Enable(self.table)
        self.table.setObjectName("pluginManagerTable")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._buttons = buttons
        self.Language_Apply(translator)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.setWindowTitle(translator.Text_Get("dialog.plugins.title"))
        self.title_label.setText(translator.Text_Get("dialog.plugins.heading"))
        self.description_label.setText(translator.Text_Get("dialog.plugins.description"))
        self.notice_label.setText(translator.Text_Get("dialog.plugins.notice"))
        self.install_button.setText(translator.Text_Get("action.install_plugin"))
        self.refresh_button.setText(translator.Text_Get("action.refresh_plugins"))
        headers = (
            "plugin.column.id",
            "plugin.column.display_name",
            "plugin.column.type",
            "plugin.column.version",
            "plugin.column.source",
            "plugin.column.status",
        )
        self.table.setHorizontalHeaderLabels([translator.Text_Get(key) for key in headers])
        self._buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            translator.Text_Get("action.close")
        )

    def Registry_Set(
        self,
        registry: PluginRegistry,
        discovery: ContainerPluginDiscovery,
    ) -> None:
        rows: list[PluginDisplayRow] = []
        active_ids: set[str] = set()
        for plugin in registry.algorithms:
            metadata = plugin.metadata
            active_ids.add(metadata.plugin_id)
            rows.append(
                PluginDisplayRow(
                    "plugin.type.algorithm",
                    metadata.display_name,
                    metadata.plugin_id,
                    metadata.version,
                    "plugin.source.builtin"
                    if plugin.__class__.__module__.startswith("silverstar_flp.plugins.")
                    else "plugin.source.installed",
                    "plugin.status.active",
                )
            )
        for plugin in registry.log_containers:
            metadata = plugin.metadata
            active_ids.add(metadata.plugin_id)
            rows.append(
                PluginDisplayRow(
                    "plugin.type.log_container",
                    f"{metadata.container_format_id} — {metadata.display_name}",
                    metadata.plugin_id,
                    metadata.version,
                    "plugin.source.builtin" if metadata.builtin else "plugin.source.installed",
                    "plugin.status.active",
                )
            )
        for manifest in discovery.manifests:
            if manifest.plugin_id not in active_ids:
                rows.append(
                    PluginDisplayRow(
                        "plugin.type.log_container",
                        manifest.plugin_id,
                        manifest.plugin_id,
                        manifest.version,
                        "plugin.source.installed",
                        "plugin.status.restart_required",
                    )
                )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (
                row.plugin_id,
                row.display_name,
                self._translator.Text_Get(row.plugin_type),
                row.version,
                self._translator.Text_Get(row.source),
                self._translator.Text_Get(row.status),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.plugin_id)
                self.table.setItem(row_index, column, item)


class AboutDialog(QDialog):
    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(16)
        body = QHBoxLayout()
        body.setSpacing(22)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation).pixmap(60, 60)
        )
        body.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        self.product_label = QLabel()
        self.version_label = QLabel()
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setMinimumWidth(460)
        text.addWidget(self.product_label)
        text.addWidget(self.version_label)
        text.addSpacing(14)
        text.addWidget(self.description_label)
        body.addLayout(text, 1)
        layout.addLayout(body)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self._buttons.accepted.connect(self.accept)
        layout.addWidget(self._buttons)
        self.Language_Apply(translator)

    def Language_Apply(self, translator: Translator) -> None:
        self.setWindowTitle(PRODUCT_NAME)
        self.product_label.setText(translator.Text_Get("dialog.about.product"))
        self.version_label.setText(f"{translator.Text_Get('label.version')} {__version__}")
        self.description_label.setText(translator.Text_Get("dialog.about.description"))
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            translator.Text_Get("action.ok")
        )
