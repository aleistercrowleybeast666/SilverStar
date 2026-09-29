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
from silverstar_fccg.ui.pages.navigation_alignment import AlignmentConfigurationEditor
from silverstar_fccg.ui.widgets import CollapsibleSection


class NavigationConfigurationPage(ScrollableLocalizedPage):
    alignmentChanged = Signal(object)
    parameterChanged = Signal(str, str, object)
    defaultsRequested = Signal(str)
    sharedParameterChanged = Signal(str, object)
    sharedDefaultsRequested = Signal(str)

    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.navigation_configuration", "page.navigation_configuration.description")
        self.sources_section, self.sources_layout = self._Section_Create("navigation.sources")
        self.calibration_section, self.calibration_layout = self._Section_Create("navigation.calibration")
        self.alignment_section, self.alignment_layout = self._Section_Create("navigation.initial_alignment")
        self.alignment_editor = AlignmentConfigurationEditor(translator)
        self.alignment_editor.configurationChanged.connect(self.alignmentChanged)
        self.alignment_layout.addWidget(self.alignment_editor)
        self.ins_section, self.ins_layout = self._Section_Create("navigation.ins")
        self.estimator_section, self.estimator_layout = self._Section_Create("navigation.estimator")
        self.parameters_section, self.parameters_layout = self._Section_Create("navigation.parameters")
        self.impact_section, self.impact_layout = self._Section_Create("navigation.resource_timing")
        self.rate_label = QLabel()
        self.rate_label.setWordWrap(True)
        self.ins_layout.addWidget(self.rate_label)
        self.impact_label = QLabel()
        self.impact_label.setWordWrap(True)
        self.impact_layout.addWidget(self.impact_label)
        self._content = QWidget()
        self.parameters_layout.addWidget(self._content)
        self.root_layout.addStretch(1)
        self._owners: tuple[PluginManifest, ...] = ()
        self._values: dict = {}
        self._recommendations: tuple[dict, ...] = ()
        self._expanded: dict[tuple[str, str], bool] = {}
        self.editors: dict[tuple[str, str], EnterCommittedDoubleSpinBox] = {}
        self._rate_plan = None
        self._rate_error = ""
        self.Language_Apply(translator)

    def _Section_Create(self, key: str) -> tuple[QGroupBox, QVBoxLayout]:
        section = QGroupBox(self._translator.Text_Get(key))
        section.setProperty("navigationSectionKey", key)
        layout = QVBoxLayout(section)
        self.root_layout.addWidget(section)
        return section, layout

    def ExistingEditors_Attach(
        self, *, sources: QWidget, calibration: QWidget,
        alignment: QWidget, ins: QWidget, estimator: QWidget,
    ) -> None:
        self.sources_layout.addWidget(sources)
        self.calibration_layout.addWidget(calibration)
        self.alignment_layout.addWidget(alignment)
        self.ins_layout.insertWidget(0, ins)
        self.estimator_layout.addWidget(estimator)

    def RatePlan_Set(self, rate_plan: object | None, error: str = "") -> None:
        self._rate_plan = rate_plan
        self._rate_error = error
        if rate_plan is None:
            self.rate_label.setText(error or self._translator.Text_Get("navigation.rate_unavailable"))
            self.impact_label.setText(error or self._translator.Text_Get("navigation.rate_unavailable"))
            return
        self.rate_label.setText(self._translator.Text_Get(
            "navigation.rate_summary",
            odr=rate_plan.raw_imu_odr_hz,
            aggregation=rate_plan.aggregation,
            propagation=f"{rate_plan.effective_propagation_rate_hz:g}",
        ))
        issue_text = "; ".join(issue.code for issue in rate_plan.issues)
        self.impact_label.setText(self._translator.Text_Get(
            "navigation.impact_summary",
            replay=rate_plan.maximum_replay_steps,
            history=rate_plan.required_history_steps,
            capacity=rate_plan.history_capacity,
            cpu=rate_plan.cpu_profile,
            issues=issue_text or "READY",
        ))

    def AlignmentConfiguration_Set(
        self, configuration: object, strategy: str | None,
        device_instances: tuple,
    ) -> None:
        self.alignment_editor.Configuration_Set(
            configuration, strategy, device_instances,
        )

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
        self.parameters_layout.replaceWidget(self._content, content)
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
        for section in self.findChildren(QGroupBox):
            key = section.property("navigationSectionKey")
            if key:
                section.setTitle(self._translator.Text_Get(key))
        self.Configuration_Set(self._owners, self._values, self._recommendations)
        self.alignment_editor.Language_Apply(translator)
        self.RatePlan_Set(self._rate_plan, self._rate_error)


AlgorithmParametersPage = NavigationConfigurationPage
