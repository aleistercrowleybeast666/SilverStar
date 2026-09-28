from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.plugins.manifest import PluginManifest
from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameterSharedGroups_Get,
)
from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.widgets import CollapsibleSection


class AlgorithmParametersPage(ScrollableLocalizedPage):
    parameterChanged = Signal(str, str, object)
    defaultsRequested = Signal(str)
    sharedParameterChanged = Signal(str, object)
    sharedDefaultsRequested = Signal(str)

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.navigation_configuration", "page.navigation_configuration.description")
        self._content = QWidget()
        self.root_layout.addWidget(self._content)
        self.root_layout.addStretch(1)
        self._owners: tuple[PluginManifest, ...] = ()
        self._values: dict = {}
        self._recommendations: tuple[dict, ...] = ()
        self._expanded: dict[tuple[str, str], bool] = {}
        self.editors: dict[tuple[str, str], EnterCommittedDoubleSpinBox] = {}

    def Configuration_Set(self, owners: tuple[PluginManifest, ...], values: dict, recommendations: tuple[dict, ...] = ()) -> None:
        self._owners = owners
        self._values = values
        self._recommendations = recommendations
        content = QWidget()
        layout = QVBoxLayout(content)
        self.editors = {}
        language = self._translator.language
        if not owners:
            layout.addWidget(QLabel(self._translator.Text_Get("algorithm_parameters.empty")))
        shared_groups = AlgorithmParameterSharedGroups_Get(owners)
        if shared_groups:
            common = QGroupBox(self._translator.Text_Get("algorithm_parameters.shared"))
            common_layout = QVBoxLayout(common)
            form = QFormLayout()
            for shared_key, members in shared_groups.items():
                owner, parameter = members[0]
                editor = self._Editor_Create(parameter, values[owner.component_id][parameter.parameter_id], language)
                editor.committed.connect(
                    lambda value, key=shared_key, p=parameter: QTimer.singleShot(
                        0, self, lambda: self.sharedParameterChanged.emit(
                            key, int(value) if p.value_type == "integer" else value)))
                form.addRow(parameter.DisplayName_Get(language), editor)
                self.editors[("shared", shared_key)] = editor
            common_layout.addLayout(form)
            reset = QPushButton(self._translator.Text_Get("algorithm_parameters.shared_reset"))
            reset.clicked.connect(lambda: [self.sharedDefaultsRequested.emit(key) for key in shared_groups])
            common_layout.addWidget(reset)
            layout.addWidget(common)
        for owner in owners:
            group = QGroupBox(owner.DisplayName_Get(language))
            group_layout = QVBoxLayout(group)
            for level in ("basic", "advanced", "gnss_integrity"):
                parameters = [p for p in owner.algorithm_parameters if p.group == level and not p.shared_key]
                if not parameters:
                    continue
                key = (owner.component_id, level)
                section = CollapsibleSection(expanded=self._expanded.get(key, level == "basic"))
                section.ExpandedChanged.connect(lambda expanded, k=key: self._expanded.__setitem__(k, expanded))
                section.Title_Set(self._translator.Text_Get("algorithm_parameters." + level))
                form = QFormLayout(section.body)
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                for parameter in parameters:
                    editor = self._Editor_Create(parameter, values.get(owner.component_id, {}).get(parameter.parameter_id, parameter.default), language)
                    editor.committed.connect(
                        lambda value, c=owner.component_id, p=parameter:
                        QTimer.singleShot(0, self, lambda:
                            self.parameterChanged.emit(c, p.parameter_id, int(value) if p.value_type == "integer" else value)))
                    form.addRow(parameter.DisplayName_Get(language), editor)
                    for recommendation in recommendations:
                        if (recommendation["parameter_id"] == parameter.parameter_id
                                and recommendation["unit"] == parameter.unit
                                and recommendation["representation"] == parameter.representation):
                            text = self._translator.Text_Get("algorithm_parameters.recommendation").format(
                                source=recommendation["source"], value=recommendation["value"],
                                unit=recommendation["unit"])
                            label = QLabel(text)
                            label.setWordWrap(True)
                            label.setToolTip(recommendation["description"].get(language,
                                recommendation["description"].get("en_US", "")))
                            form.addRow("", label)
                    self.editors[(owner.component_id, parameter.parameter_id)] = editor
                group_layout.addWidget(section)
            non_shared = [p for p in owner.algorithm_parameters if not p.shared_key]
            if non_shared:
                reset = QPushButton(self._translator.Text_Get("algorithm_parameters.reset"))
                reset.clicked.connect(lambda _checked=False, c=owner.component_id:
                                      QTimer.singleShot(0, self, lambda: self.defaultsRequested.emit(c)))
                group_layout.addWidget(reset)
            else:
                group_layout.addWidget(QLabel(self._translator.Text_Get("algorithm_parameters.no_private")))
            layout.addWidget(group)
        self.root_layout.replaceWidget(self._content, content)
        self._content.hide()
        self._content.deleteLater()
        self._content = content

    def _Editor_Create(self, parameter, value: object, language: str) -> EnterCommittedDoubleSpinBox:
        editor = EnterCommittedDoubleSpinBox()
        editor.setDecimals(parameter.precision)
        editor.setRange(parameter.minimum, parameter.maximum)
        editor.setSingleStep(parameter.step)
        editor.setSuffix(" " + parameter.unit)
        editor.setToolTip(parameter.Description_Get(language) + "\n" +
                          self._translator.Text_Get(
                              "mode.parameter_range", minimum=parameter.minimum,
                              maximum=parameter.maximum, unit=parameter.unit))
        editor.CommittedValue_Set(value)
        editor.setReadOnly(parameter.lifecycle == "legacy_read_only")
        return editor

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        self.Configuration_Set(self._owners, self._values, self._recommendations)
