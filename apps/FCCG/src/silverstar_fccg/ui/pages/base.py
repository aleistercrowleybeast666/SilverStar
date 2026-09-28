from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.widgets import EngineeringTable, PageHeader


class LocalizedPage(QWidget):
    def __init__(self, translator: Translator, title_key: str, description_key: str) -> None:
        super().__init__()
        self._translator = translator
        self._text_widgets: list[tuple[object, str]] = []
        self._title_widgets: list[tuple[object, str]] = []
        self._placeholder_widgets: list[tuple[object, str]] = []
        self._tables: list[EngineeringTable] = []
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(18, 16, 18, 16)
        self.root_layout.setSpacing(10)
        self.header = PageHeader(title_key, description_key)
        self.root_layout.addWidget(self.header)

    def Text_Register(self, widget: object, key: str) -> object:
        self._text_widgets.append((widget, key))
        return widget

    def Title_Register(self, widget: object, key: str) -> object:
        self._title_widgets.append((widget, key))
        return widget

    def Placeholder_Register(self, widget: object, key: str) -> object:
        self._placeholder_widgets.append((widget, key))
        return widget

    def Table_Register(self, table: EngineeringTable) -> EngineeringTable:
        self._tables.append(table)
        return table

    def Group_Create(self, key: str, layout: QLayout | None = None) -> QGroupBox:
        group = QGroupBox()
        self.Title_Register(group, key)
        if layout is not None:
            group.setLayout(layout)
        return group

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        self.header.Language_Apply(translator)
        for widget, key in self._text_widgets:
            widget.setText(translator.Text_Get(key))
        for widget, key in self._title_widgets:
            widget.setTitle(translator.Text_Get(key))
        for widget, key in self._placeholder_widgets:
            widget.setPlaceholderText(translator.Text_Get(key))
        for table in self._tables:
            table.Language_Apply(translator)


class ScrollableLocalizedPage(LocalizedPage):
    def __init__(self, translator: Translator, title_key: str, description_key: str) -> None:
        QWidget.__init__(self)
        self._translator = translator
        self._text_widgets = []
        self._title_widgets = []
        self._placeholder_widgets = []
        self._tables = []
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        TouchScroll_Enable(scroll)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.root_layout = QVBoxLayout(content)
        self.root_layout.setContentsMargins(18, 16, 18, 16)
        self.root_layout.setSpacing(10)
        self.header = PageHeader(title_key, description_key)
        self.root_layout.addWidget(self.header)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

