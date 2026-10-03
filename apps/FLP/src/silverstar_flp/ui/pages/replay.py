from __future__ import annotations

import math
from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.analysis_source import (
    AnalysisSourceKind,
    ReplayResultStore,
    ReplayStoredResult,
)
from silverstar_flp.core.comparison import Series_Compare
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmResult,
    ParameterSpec,
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
)
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox


class ReplayPage(QWidget):
    replayRequested = Signal(str, object)
    analysisSourceRequested = Signal(str)
    configurationChanged = Signal()

    def __init__(self, translator: Translator, registry: PluginRegistry) -> None:
        super().__init__()
        self._translator = translator
        self._registry = registry
        self._dataset: FlightDataset | None = None
        self._last_result: AlgorithmResult | None = None
        self._last_entry: ReplayStoredResult | None = None
        self._store: ReplayResultStore | None = None
        self._parameter_widgets: dict[str, QDoubleSpinBox] = {}
        self._parameter_labels: dict[str, QLabel] = {}
        self._parameter_specs: dict[str, ParameterSpec] = {}
        self._recorded_parameter_values: dict[str, float] = {}
        self._offline_parameter_values: dict[str, float] = {}
        self._parameter_baseline_values: dict[str, float] = {}
        self._parameters_dirty = False

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        TouchScroll_Enable(self.scroll_area)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.setContentsMargins(12, 10, 12, 14)
        content_layout.setSpacing(10)

        self.controls_group = QGroupBox()
        self.controls_form = QFormLayout(self.controls_group)
        self.controls_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.algorithm_label = QLabel()
        self.algorithm_combo = StandardComboBox()
        for plugin in registry.algorithms:
            self.algorithm_combo.addItem(plugin.metadata.display_name, plugin.metadata.plugin_id)
        self.mode_label = QLabel()
        self.mode_combo = StandardComboBox()
        self.quality_policy_label = QLabel()
        self.quality_policy_combo = StandardComboBox()
        self.quality_policy_combo.currentIndexChanged.connect(
            lambda _index: self._RuntimeParameters_Refresh()
        )
        self.fidelity_label = QLabel()
        self.availability_label = QLabel("—")
        self.availability_label.setWordWrap(True)
        self.controls_form.addRow(self.algorithm_label, self.algorithm_combo)
        self.controls_form.addRow(self.mode_label, self.mode_combo)
        self.controls_form.addRow(self.quality_policy_label, self.quality_policy_combo)
        self.controls_form.addRow(self.fidelity_label, self.availability_label)
        content_layout.addWidget(self.controls_group)

        self.analysis_source_group = QGroupBox()
        analysis_source_layout = QHBoxLayout(self.analysis_source_group)
        self.analysis_source_combo = StandardComboBox()
        self.analysis_source_combo.currentIndexChanged.connect(self._AnalysisSource_Selected)
        self.active_source_label = QLabel("—")
        self.active_source_label.setObjectName("muted")
        self.active_source_label.setWordWrap(True)
        analysis_source_layout.addWidget(self.analysis_source_combo, 1)
        analysis_source_layout.addWidget(self.active_source_label, 2)
        content_layout.addWidget(self.analysis_source_group)

        self.parameters_group = QGroupBox()
        parameters_layout = QVBoxLayout(self.parameters_group)
        parameter_controls = QHBoxLayout()
        self.parameter_group_label = QLabel()
        self.parameter_group_combo = StandardComboBox()
        self.parameter_group_combo.currentIndexChanged.connect(self._ParameterForm_Refresh)
        self.parameter_modified_label = QLabel()
        self.parameter_modified_label.setObjectName("warningLabel")
        self.parameter_reset_button = QPushButton()
        self.parameter_reset_button.clicked.connect(self._Parameters_Reset)
        parameter_controls.addWidget(self.parameter_group_label)
        parameter_controls.addWidget(self.parameter_group_combo)
        parameter_controls.addWidget(self.parameter_modified_label)
        parameter_controls.addStretch(1)
        parameter_controls.addWidget(self.parameter_reset_button)
        parameters_layout.addLayout(parameter_controls)
        self.parameters_form = QFormLayout()
        self.parameters_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        parameters_layout.addLayout(self.parameters_form)
        content_layout.addWidget(self.parameters_group)

        action_layout = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._Replay_Request)
        self.result_label = QLabel("—")
        self.result_label.setWordWrap(True)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.result_label, 1)
        content_layout.addLayout(action_layout)

        self.result_information_group = QGroupBox()
        result_information_layout = QVBoxLayout(self.result_information_group)
        self.result_information_label = QLabel("—")
        self.result_information_label.setWordWrap(True)
        self.result_information_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        result_information_layout.addWidget(self.result_information_label)
        content_layout.addWidget(self.result_information_group)

        self.stored_results_group = QGroupBox()
        stored_results_layout = QVBoxLayout(self.stored_results_group)
        self.stored_results_table = QTableWidget(0, 8)
        TouchScroll_Enable(self.stored_results_table)
        self.stored_results_table.setMinimumHeight(220)
        self.stored_results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stored_results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.stored_results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.stored_results_table.verticalHeader().setVisible(False)
        self.stored_results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.stored_results_table.horizontalHeader().setStretchLastSection(True)
        self.stored_results_table.itemSelectionChanged.connect(self._StoredResult_Selected)
        stored_results_layout.addWidget(self.stored_results_table)
        content_layout.addWidget(self.stored_results_group)

        self.comparison_group = QGroupBox()
        comparison_layout = QVBoxLayout(self.comparison_group)
        self.comparison_table = QTableWidget(0, 5)
        TouchScroll_Enable(self.comparison_table)
        self.comparison_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.comparison_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.comparison_table.setMinimumHeight(280)
        self.comparison_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.comparison_table.verticalHeader().setVisible(False)
        comparison_layout.addWidget(self.comparison_table)
        content_layout.addWidget(self.comparison_group)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(scroll_content)
        page_layout.addWidget(self.scroll_area)

        self.algorithm_combo.currentIndexChanged.connect(self._Algorithm_Refresh)
        self.mode_combo.currentIndexChanged.connect(self._Mode_Refresh)
        self.Language_Apply(translator)
        self._Algorithm_Refresh()

    def Dataset_Set(
        self,
        dataset: FlightDataset,
        results: ReplayResultStore | Mapping[str, AlgorithmResult] | None = None,
    ) -> None:
        dataset_changed = self._dataset is not dataset
        self._dataset = dataset
        if isinstance(results, ReplayResultStore):
            self._store = results
        elif self._store is None:
            self._store = ReplayResultStore()
        self._AlgorithmLabels_Refresh()
        self._AnalysisSources_Refresh()
        self._StoredResults_Refresh()
        if dataset_changed:
            self._Algorithm_Refresh()
        else:
            self._Availability_Refresh()

    def _AlgorithmLabels_Refresh(self) -> None:
        for index in range(self.algorithm_combo.count()):
            plugin_id = str(self.algorithm_combo.itemData(index))
            plugin = self._registry.Algorithm_Get(plugin_id)
            tags = [self._translator.Text_Get("replay.tag.offline_plugin")]
            if self._dataset is not None:
                configuration = plugin.ConfigurationAvailability_Get(self._dataset)
                if configuration.firmware_member:
                    tags.insert(0, self._translator.Text_Get("replay.tag.firmware_member"))
                if configuration.recorded_output_available:
                    tags.insert(
                        1,
                        self._translator.Text_Get("replay.tag.recorded_output"),
                    )
            self.algorithm_combo.setItemText(
                index,
                f"{plugin.metadata.display_name} · {' / '.join(tags)}",
            )

    def _Algorithm_Refresh(self) -> None:
        self._ParameterForm_Clear()
        for widget in (*self._parameter_labels.values(), *self._parameter_widgets.values()):
            widget.deleteLater()
        self._parameter_widgets = {}
        self._parameter_labels = {}
        self._parameter_specs = {}
        plugin = self._CurrentPlugin_Get()
        self.quality_policy_combo.blockSignals(True)
        self.quality_policy_combo.clear()
        self.quality_policy_combo.addItem(
            self._translator.Text_Get("replay.quality_recorded"), None
        )
        for revision in plugin.metadata.what_if_quality_revisions:
            self.quality_policy_combo.addItem(
                self._translator.Text_Get("replay.quality_revision", revision=revision), revision
            )
        self.quality_policy_combo.blockSignals(False)
        self._ComboLabels_Refresh()
        self._recorded_parameter_values = self._RecordedParameters_Get(plugin)
        self._offline_parameter_values = {
            key: value
            for key, value in plugin.OfflineParameters_Get().items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if self._dataset is not None:
            configuration = plugin.ConfigurationAvailability_Get(self._dataset)
            if (
                self.mode_combo.currentData() == ReplayMode.RECORDED_CONFIGURATION
                and not configuration.recorded_available
            ):
                offline_index = self.mode_combo.findData(ReplayMode.OFFLINE)
                self.mode_combo.setCurrentIndex(max(offline_index, 0))
        for parameter in plugin.metadata.parameter_schema:
            if parameter.kind not in ("float", "int"):
                continue
            editor = QDoubleSpinBox(self.parameters_group)
            editor.setDecimals(parameter.precision)
            editor.setKeyboardTracking(False)
            editor.setRange(
                parameter.minimum if parameter.minimum is not None else -1.0e12,
                parameter.maximum if parameter.maximum is not None else 1.0e12,
            )
            if parameter.step is not None:
                editor.setSingleStep(float(parameter.step))
            editor.setValue(
                self._offline_parameter_values.get(
                    parameter.parameter_id,
                    float(parameter.default),
                )
            )
            editor.setSuffix(f" {parameter.unit}" if parameter.unit else "")
            editor.valueChanged.connect(self._ParametersDirty_Refresh)
            label = QLabel(self._Parameter_Label(parameter), self.parameters_group)
            self._parameter_widgets[parameter.parameter_id] = editor
            self._parameter_labels[parameter.parameter_id] = label
            self._parameter_specs[parameter.parameter_id] = parameter
            self._ParameterTooltip_Apply(parameter)
        self._ParameterGroups_Refresh()
        if plugin.metadata.plugin_id == "silverstar.algorithm.sf6":
            self.parameter_group_combo.setCurrentIndex(
                self.parameter_group_combo.findData("parameter_group.sf6_gain")
            )
        self._ParameterForm_Refresh()
        self._ParametersDirty_Refresh()
        self._Mode_Refresh()
        self._Availability_Refresh()

    def _RecordedParameters_Get(self, plugin) -> dict[str, float]:
        if self._dataset is None:
            return {}
        try:
            recorded = plugin.recorded_parameters(self._dataset)
        except (IndexError, KeyError, TypeError, ValueError):
            return {}
        values: dict[str, float] = {}
        declared = {
            parameter.parameter_id
            for parameter in plugin.metadata.parameter_schema
            if parameter.kind in ("float", "int")
        }
        for parameter_id in declared:
            try:
                values[parameter_id] = recorded[parameter_id]
            except (KeyError, TypeError, ValueError):
                continue
        return values

    def _ParameterGroups_Refresh(self) -> None:
        selected = self.parameter_group_combo.currentData()
        group_keys = tuple(
            dict.fromkeys(
                parameter.group_key or "parameter_group.general"
                for parameter in self._parameter_specs.values()
            )
        )
        self.parameter_group_combo.blockSignals(True)
        self.parameter_group_combo.clear()
        for group_key in group_keys:
            self.parameter_group_combo.addItem(
                self._translator.Text_Get(group_key),
                group_key,
            )
        index = self.parameter_group_combo.findData(selected)
        self.parameter_group_combo.setCurrentIndex(max(index, 0))
        self.parameter_group_combo.blockSignals(False)

    def _ParameterForm_Refresh(self, *_args: object) -> None:
        self._ParameterForm_Clear()
        group_key = self.parameter_group_combo.currentData()
        for parameter_id, parameter in self._parameter_specs.items():
            current_group = parameter.group_key or "parameter_group.general"
            if current_group != group_key:
                continue
            label = self._parameter_labels[parameter_id]
            editor = self._parameter_widgets[parameter_id]
            label.show()
            editor.show()
            self.parameters_form.addRow(label, editor)
        self.parameters_form.invalidate()
        self.parameters_form.activate()
        self.parameters_group.updateGeometry()

    def _ParameterForm_Clear(self) -> None:
        for widget in (*self._parameter_labels.values(), *self._parameter_widgets.values()):
            widget.hide()
            self.parameters_form.removeWidget(widget)
        while self.parameters_form.rowCount():
            self.parameters_form.takeRow(0)
        self.parameters_form.invalidate()

    def _Parameters_Reset(self) -> None:
        for parameter_id, editor in self._parameter_widgets.items():
            editor.blockSignals(True)
            editor.setValue(
                self._parameter_baseline_values.get(
                    parameter_id,
                    self._offline_parameter_values.get(parameter_id, editor.value()),
                )
            )
            editor.setProperty("actualValue", self._parameter_baseline_values.get(parameter_id))
            editor.blockSignals(False)
        self._ParametersDirty_Refresh()

    def _ParametersDirty_Refresh(self, *_args: object) -> None:
        self._parameters_dirty = any(
            not math.isclose(
                editor.value(),
                self._parameter_baseline_values.get(parameter_id, editor.value()),
                rel_tol=1.0e-9,
                abs_tol=5.0e-7,
            )
            for parameter_id, editor in self._parameter_widgets.items()
        )
        what_if = self.mode_combo.currentData() == ReplayMode.WHAT_IF
        self.parameter_modified_label.setVisible(what_if and self._parameters_dirty)
        self.configurationChanged.emit()

    def _ParameterTooltip_Apply(self, parameter: ParameterSpec) -> None:
        tooltip = ""
        if parameter.tooltip_key:
            translated = self._translator.Text_Get(parameter.tooltip_key)
            if translated != parameter.tooltip_key:
                tooltip = translated
        identifier = self._translator.Text_Get(
            "replay.parameter_id",
            value=parameter.parameter_id,
        )
        text = f"{tooltip}\n{identifier}" if tooltip else identifier
        text += "\n" + self._translator.Text_Get(
            "replay.parameter_contract",
            representation=parameter.representation,
            minimum=parameter.minimum,
            maximum=parameter.maximum,
            unit=parameter.unit,
        )

        self._parameter_labels[parameter.parameter_id].setToolTip(text)
        self._parameter_widgets[parameter.parameter_id].setToolTip(text)

    def _Parameter_Label(self, parameter: ParameterSpec) -> str:
        code = parameter.label_key or f"parameter.{parameter.parameter_id}"
        translated = self._translator.Text_Get(code)
        return parameter.parameter_id if translated == code else translated

    def _Mode_Refresh(self) -> None:
        mode = self.mode_combo.currentData()
        what_if = mode == ReplayMode.WHAT_IF
        quality_visible = what_if and bool(
            self._CurrentPlugin_Get().metadata.what_if_quality_revisions
        )
        self.quality_policy_label.setVisible(quality_visible)
        self.quality_policy_combo.setVisible(quality_visible)
        if mode == ReplayMode.RECORDED_CONFIGURATION:
            self._parameter_baseline_values = dict(self._recorded_parameter_values)
        elif mode == ReplayMode.WHAT_IF:
            firmware = self._dataset is not None and self._CurrentPlugin_Get().FirmwareMember_Is(
                self._dataset
            )
            self._parameter_baseline_values = dict(
                self._recorded_parameter_values if firmware else self._offline_parameter_values
            )
        else:
            self._parameter_baseline_values = dict(self._offline_parameter_values)
        metadata = (
            self._dataset.semantic_context.raw_metadata
            if self._dataset is not None and self._dataset.semantic_context is not None
            else {}
        )
        revision = (
            metadata.get("metadata_declarations", {})
            .get("navigation_replay", {})
            .get("gnss_integrity_revision", 0)
        )
        if revision == 0 and "gnss_integrity_enable" in self._parameter_specs:
            self._parameter_baseline_values["gnss_integrity_enable"] = 0
        for parameter_id, editor in self._parameter_widgets.items():
            editor.blockSignals(True)
            editor.setValue(
                self._parameter_baseline_values.get(
                    parameter_id,
                    float(self._parameter_specs[parameter_id].default),
                )
            )
            editor.setProperty("actualValue", self._parameter_baseline_values.get(parameter_id))
            editor.blockSignals(False)
        self.parameters_group.setEnabled(True)
        self._RuntimeParameters_Refresh()
        firmware = self._dataset is not None and self._CurrentPlugin_Get().FirmwareMember_Is(
            self._dataset
        )
        self.parameter_reset_button.setText(
            self._translator.Text_Get(
                "action.reset_firmware_parameters"
                if firmware
                else "action.reset_offline_parameters"
            )
        )
        self.parameter_reset_button.setToolTip(self.parameter_reset_button.text())
        self.parameter_reset_button.setEnabled(what_if and self._dataset is not None)
        self._ParametersDirty_Refresh()
        self._Availability_Refresh()
        self.configurationChanged.emit()

    def _RuntimeParameters_Refresh(self) -> None:
        if not hasattr(self, "_parameter_widgets"):
            return
        mode = self.mode_combo.currentData()
        revision = self.quality_policy_combo.currentData() if mode == ReplayMode.WHAT_IF else None
        runtime = {
            p.parameter_id: p
            for p in self._CurrentPlugin_Get().RuntimeParameterSchema_Get(self._dataset, revision)
        }
        for name, editor in self._parameter_widgets.items():
            editor.setReadOnly(mode != ReplayMode.WHAT_IF or name not in runtime)
            self._ParameterTooltip_Apply(runtime.get(name, self._parameter_specs[name]))
            if name not in runtime:
                note = self._translator.Text_Get("replay.parameter_retired")
                editor.setToolTip(note)
                self._parameter_labels[name].setToolTip(note)
                self._parameter_labels[name].setText(
                    self._Parameter_Label(self._parameter_specs[name]) + " · " + note
                )
            else:
                self._parameter_labels[name].setText(
                    self._Parameter_Label(self._parameter_specs[name])
                )
        self.configurationChanged.emit()

    def _ActualValues_Get(self) -> dict[str, float]:
        values = {}
        for name, editor in self._parameter_widgets.items():
            actual = editor.property("actualValue")
            if actual is not None and editor.value() == round(actual, editor.decimals()):
                values[name] = actual
            else:
                values[name] = editor.value()
        for name in values:
            if self._parameter_specs[name].kind == "int":
                values[name] = int(values[name])
        return values

    def Configuration_Get(self) -> dict:
        plugin = self._CurrentPlugin_Get()
        mode = ReplayMode(self.mode_combo.currentData())
        values = (
            self._ActualValues_Get()
            if mode == ReplayMode.WHAT_IF
            else dict(self._parameter_baseline_values)
        )
        request = ReplayRequest(mode=mode, parameters=values)
        plugin.metadata.Parameters_Validate(values)
        configuration = {
            "algorithm_id": plugin.metadata.plugin_id,
            "algorithm_version": plugin.metadata.version,
            "mode": mode.value,
            "input_source": request.input_source,
            "actual_values": values,
            "parameter_schema_identity": plugin.metadata.ParameterSchemaIdentity_Get(),
            "provenance": plugin.ParameterAudit_Get(self._dataset, request)["config_source"],
        }
        if mode == ReplayMode.WHAT_IF and self.quality_policy_combo.currentData() is not None:
            configuration["quality_policy_revision"] = self.quality_policy_combo.currentData()
        return configuration

    def Configuration_Set(self, configuration: dict) -> None:
        from silverstar_flp.core.project import ReplayConfiguration_Validate

        ReplayConfiguration_Validate(configuration)
        plugin = self._registry.Algorithm_Get(configuration["algorithm_id"])
        request = ReplayRequest(
            mode=ReplayMode(configuration["mode"]),
            input_source=configuration["input_source"],
            parameters=configuration["actual_values"],
            quality_policy_revision=configuration.get("quality_policy_revision"),
        )
        plugin.Parameters_Resolve(self._dataset, request)
        self.algorithm_combo.setCurrentIndex(
            self.algorithm_combo.findData(configuration["algorithm_id"])
        )
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(request.mode))
        self.quality_policy_combo.setCurrentIndex(
            max(0, self.quality_policy_combo.findData(request.quality_policy_revision))
        )
        for name, value in request.parameters.items():
            self._parameter_widgets[name].setValue(value)
            self._parameter_widgets[name].setProperty("actualValue", value)
        self._ParametersDirty_Refresh()

    def _CurrentPlugin_Get(self):
        return self._registry.Algorithm_Get(str(self.algorithm_combo.currentData()))

    def Fidelity_Text_Get(self, fidelity: ReplayFidelity) -> str:
        return self._translator.Text_Get(f"replay.fidelity.{fidelity.value.lower()}")

    def _Warning_Text_Get(self, warning_code: str) -> str:
        translation_key = f"replay.warning.{warning_code}"
        translated = self._translator.Text_Get(translation_key)
        if translated == translation_key:
            return self._translator.Text_Get("replay.warning.unknown")
        return translated

    def _Warnings_Text_Get(self, warnings: tuple[str, ...]) -> str:
        if not warnings:
            return self._translator.Text_Get("status.none")
        return "; ".join(self._Warning_Text_Get(code) for code in warnings)

    def _Availability_Refresh(self) -> None:
        if self._dataset is None:
            self.availability_label.setText(self._translator.Text_Get("status.no_data"))
            self.run_button.setEnabled(False)
            return
        plugin = self._CurrentPlugin_Get()
        source = ReplayRequest().input_source
        availability = plugin.availability(self._dataset, source)
        configuration = plugin.ConfigurationAvailability_Get(
            self._dataset,
            input_available=availability.available,
        )
        mode = self.mode_combo.currentData()
        details = self.Fidelity_Text_Get(availability.fidelity)
        tags = [self._translator.Text_Get("replay.tag.offline_plugin")]
        if configuration.firmware_member:
            tags.append(self._translator.Text_Get("replay.tag.firmware_member"))
        if configuration.recorded_output_available:
            tags.append(self._translator.Text_Get("replay.tag.recorded_output"))
        details += " · " + " / ".join(tags)
        if availability.missing_inputs:
            details += " · " + self._translator.Text_Get(
                "replay.missing_inputs", values=", ".join(availability.missing_inputs)
            )
        if availability.warnings:
            details += " · " + self._Warnings_Text_Get(availability.warnings)
        self.availability_label.setText(details)
        self.availability_label.setToolTip("\n".join(availability.warnings))
        mode_available = (
            configuration.recorded_available
            if mode == ReplayMode.RECORDED_CONFIGURATION
            or (mode == ReplayMode.WHAT_IF and configuration.firmware_member)
            else configuration.offline_available
        )
        if mode != ReplayMode.OFFLINE and not mode_available:
            missing = ", ".join(configuration.missing_recorded_parameters)
            self.availability_label.setText(
                details
                + " · "
                + self._translator.Text_Get(
                    "replay.recorded_configuration_unavailable",
                    values=missing or self._translator.Text_Get("status.none"),
                )
            )
        if mode == ReplayMode.RECORDED_CONFIGURATION and mode_available:
            details += " · " + self._translator.Text_Get("replay.firmware_parameter_provenance")
            self.availability_label.setText(details)
        self.run_button.setEnabled(availability.available and mode_available)

    def _Request_Get(self) -> ReplayRequest:
        mode = self.mode_combo.currentData()
        parameters = (
            self._ActualValues_Get()
            if mode == ReplayMode.WHAT_IF
            else (dict(self._offline_parameter_values) if mode == ReplayMode.OFFLINE else {})
        )
        request = ReplayRequest(
            mode=mode,
            input_source=ReplayRequest().input_source,
            parameters=parameters,
            quality_policy_revision=self.quality_policy_combo.currentData()
            if mode == ReplayMode.WHAT_IF
            else None,
        )
        return request

    def _Replay_Request(self) -> None:
        request = self._Request_Get()
        self.run_button.setEnabled(False)
        self.result_label.setText(self._translator.Text_Get("replay.running"))
        self.replayRequested.emit(str(self.algorithm_combo.currentData()), request)

    def Result_Set(self, result: ReplayStoredResult | AlgorithmResult) -> None:
        if isinstance(result, ReplayStoredResult):
            entry = result
        else:
            if self._store is None:
                self._store = ReplayResultStore()
            plugin = self._registry.Algorithm_Get(result.algorithm_id)
            entry = self._store.Result_Add(result, algorithm_name=plugin.metadata.display_name)
        self._last_entry = entry
        self._last_result = entry.result
        provenance_codes = {
            "Recorded": "status.recorded",
            "Recomputed": "status.recomputed",
            "What-if": "status.what_if",
            "Offline": "status.recomputed",
            "Recomputed from recorded configuration": "status.recomputed",
        }
        provenance = self._translator.Text_Get(
            provenance_codes.get(entry.result.provenance, "status.recomputed")
        )
        self.result_label.setText(
            self._translator.Text_Get(
                "replay.result",
                provenance=provenance,
                fidelity=self.Fidelity_Text_Get(entry.fidelity),
                count=entry.diagnostics.get("output_count", entry.sample_count),
            )
        )
        self.run_button.setEnabled(True)
        self._ResultInformation_Set(entry)
        self._StoredResults_Refresh(select_result_id=entry.result_id)
        self._AnalysisSources_Refresh()
        self._Comparison_Set(entry.result)

    def _ResultInformation_Set(self, entry: ReplayStoredResult) -> None:
        coverage = entry.time_coverage_us
        if coverage is None:
            coverage_text = self._translator.Text_Get("status.na")
        else:
            coverage_text = (
                f"{(coverage[1] - coverage[0]) * 1.0e-6:.3f} s ({coverage[0]}–{coverage[1]} µs)"
            )
        mode_code = "status.what_if" if entry.mode == ReplayMode.WHAT_IF else "status.recomputed"
        input_text = self._InputSource_Text_Get(entry.input_source)
        plugin = self._registry.Algorithm_Get(entry.algorithm_id)
        specs = {
            parameter.parameter_id: parameter for parameter in plugin.metadata.parameter_schema
        }
        parameter_items: list[str] = []
        for key, value in sorted(entry.parameters.items()):
            spec = specs.get(key)
            label = self._Parameter_Label(spec) if spec is not None else key
            unit = f" {spec.unit}" if spec is not None and spec.unit not in ("", "1") else ""
            parameter_items.append(f"{label}={value}{unit}")
        parameters = ", ".join(parameter_items)
        warnings = self._Warnings_Text_Get(entry.warnings)
        channels = ", ".join(sorted(entry.channels))
        lines = (
            self._translator.Text_Get("replay.detail.algorithm", value=entry.algorithm_name),
            self._translator.Text_Get(
                "replay.detail.mode", value=self._translator.Text_Get(mode_code)
            ),
            self._translator.Text_Get("replay.detail.input", value=input_text),
            self._translator.Text_Get(
                "replay.detail.fidelity", value=self.Fidelity_Text_Get(entry.fidelity)
            ),
            self._translator.Text_Get("replay.detail.coverage", value=coverage_text),
            self._translator.Text_Get("replay.detail.samples", value=entry.sample_count),
            self._translator.Text_Get(
                "replay.detail.parameters",
                value=parameters or self._translator.Text_Get("status.none"),
            ),
            self._translator.Text_Get("replay.detail.warnings", value=warnings),
            self._translator.Text_Get("replay.detail.channels", value=channels),
        )
        verification = entry.diagnostics.get("mechanization_verification")
        if isinstance(verification, Mapping):
            rows = verification.get("intervals", ())
            matched = sum(1 for row in rows if row.get("passed"))
            first = verification.get("first_divergence")
            verification_lines = [
                self._translator.Text_Get(
                    "replay.mechanization_status",
                    value="PASS" if verification.get("passed") else "FAIL",
                ),
                self._translator.Text_Get(
                    "replay.mechanization_counts",
                    recorded=verification.get("recorded_count", 0),
                    computed=verification.get("computed_count", 0),
                    matched=matched,
                ),
                self._translator.Text_Get("replay.mechanization_first_none")
                if first is None
                else self._translator.Text_Get(
                    "replay.mechanization_first",
                    timestamp=first.get("timestamp_us", "—"),
                    sequence=first.get("source_sequence", "—"),
                    theta=first.get("delta_theta_difference", "—"),
                    velocity=first.get("delta_velocity_difference", "—"),
                    dt=first.get("dt_difference_s", "—"),
                    start=first.get("start_timestamp_difference_us", "—"),
                    end=first.get("end_timestamp_difference_us", "—"),
                ),
            ]
            lines = (*lines, *verification_lines)
        if entry.analysis_only:
            lines = (self._translator.Text_Get("diagnostic.analysis_notice"), *lines)
        self.result_information_label.setText("\n".join(lines))
        self.result_information_label.setToolTip("\n".join(entry.warnings))

    def _StoredResults_Refresh(self, select_result_id: str | None = None) -> None:
        if self._store is None:
            self.stored_results_table.setRowCount(0)
            return
        entries = self._store.Entries_Get()
        self.stored_results_table.blockSignals(True)
        self.stored_results_table.setRowCount(len(entries))
        selected_row = -1
        for row, entry in enumerate(entries):
            coverage = entry.time_coverage_us
            coverage_text = (
                f"{(coverage[1] - coverage[0]) * 1.0e-6:.3f} s" if coverage is not None else "—"
            )
            mode = self._translator.Text_Get(
                "status.what_if" if entry.mode == ReplayMode.WHAT_IF else "status.recomputed"
            )
            if entry.analysis_only:
                mode = self._translator.Text_Get("diagnostic.analysis")
            values = (
                entry.result_id,
                entry.algorithm_name,
                mode,
                self._InputSource_Text_Get(entry.input_source),
                self.Fidelity_Text_Get(entry.fidelity),
                coverage_text,
                str(entry.sample_count),
                str(len(entry.channels)),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, entry.result_id)
                self.stored_results_table.setItem(row, column, item)
            if select_result_id == entry.result_id:
                selected_row = row
        self.stored_results_table.blockSignals(False)
        if selected_row >= 0:
            self.stored_results_table.selectRow(selected_row)
        self._ActiveSourceLabel_Refresh()

    def _InputSource_Text_Get(self, input_source: str) -> str:
        code = {
            "recorded_inertial_increment": "replay.source.recorded_increment",
            "corrected_imu": "replay.source.corrected_imu",
        }.get(input_source)
        return self._translator.Text_Get(code) if code is not None else input_source

    def _StoredResult_Selected(self) -> None:
        entry = self._SelectedEntry_Get()
        if entry is not None:
            self._last_entry = entry
            self._last_result = entry.result
            self._ResultInformation_Set(entry)
            self._Comparison_Set(entry.result)

    def _SelectedEntry_Get(self) -> ReplayStoredResult | None:
        if self._store is None:
            return None
        selected = self.stored_results_table.selectedItems()
        if not selected:
            return None
        result_id = str(selected[0].data(Qt.ItemDataRole.UserRole))
        return self._store.Entry_Get(result_id)

    def _EntryMode_Text(self, entry, mode_code):
        key = "diagnostic.analysis" if entry.analysis_only else mode_code
        return self._translator.Text_Get(key)

    def _RecordedSourceLabel_Get(self):
        label = self._translator.Text_Get("status.recorded")
        if self._dataset is not None and self._store is not None:
            solution = (
                "SF6"
                if self._dataset.Series_Get("sf6.recorded.navigation.position_enu") is not None
                else "ESKF15"
                if self._dataset.Series_Get("eskf15.recorded.navigation.position_enu") is not None
                else
                "KF_6"
                if self._dataset.Series_Get("kf6.recorded.navigation.position_enu") is not None
                else "Pure INS"
            )
            label += " · " + solution
        return label

    def _AnalysisSources_Refresh(self) -> None:
        if self._store is None:
            self.analysis_source_combo.clear()
            self.active_source_label.setText("—")
            return
        active_source_id = self._store.ActiveSource_Get().source_id
        self.analysis_source_combo.blockSignals(True)
        self.analysis_source_combo.clear()
        self.analysis_source_combo.addItem(
            self._RecordedSourceLabel_Get(),
            ReplayResultStore.RECORDED_SOURCE_ID,
        )
        for source in self._store.Sources_Get():
            if source.kind == AnalysisSourceKind.RECORDED:
                continue
            entry = self._store.SourceEntry_Get(source.source_id)
            if entry is None:
                continue
            mode_code = (
                "status.what_if"
                if entry.kind == AnalysisSourceKind.WHAT_IF
                else "status.recomputed"
            )
            self.analysis_source_combo.addItem(
                f"{entry.algorithm_name} · "
                f"{self._EntryMode_Text(entry, mode_code)} #{entry.run_index}",
                entry.source_id,
            )
        index = self.analysis_source_combo.findData(active_source_id)
        self.analysis_source_combo.setCurrentIndex(max(index, 0))
        self.analysis_source_combo.blockSignals(False)
        self._ActiveSourceLabel_Refresh()

    def _AnalysisSource_Selected(self) -> None:
        if self._store is None:
            return
        source_id = str(
            self.analysis_source_combo.currentData() or ReplayResultStore.RECORDED_SOURCE_ID
        )
        if self._store.ActiveSource_Set(source_id):
            self.analysisSourceRequested.emit(source_id)
            self._ActiveSourceLabel_Refresh()

    def _ActiveSourceLabel_Refresh(self) -> None:
        if self._store is None:
            self.active_source_label.setText("—")
            return
        source = self._store.ActiveSource_Get()
        if source.kind.value == "recorded":
            value = self._RecordedSourceLabel_Get()
        else:
            entry = self._store.SourceEntry_Get(source.source_id)
            if entry is None:
                value = self._RecordedSourceLabel_Get()
            else:
                mode_code = (
                    "status.what_if"
                    if entry.kind == AnalysisSourceKind.WHAT_IF
                    else "status.recomputed"
                )
                value = (
                    f"{entry.algorithm_name} · "
                    f"{self._EntryMode_Text(entry, mode_code)} #{entry.run_index}"
                )
        self.active_source_label.setText(
            self._translator.Text_Get("replay.active_source", value=value)
        )

    def Result_Error(self, message: str) -> None:
        key = f"error.code.{message}"
        translated = self._translator.Text_Get(key)
        self.result_label.setText(message if translated == key else translated)
        self._Availability_Refresh()

    def Task_Busy(self) -> None:
        self.run_button.setEnabled(False)
        self.controls_group.setEnabled(False)
        self.parameters_group.setEnabled(False)

    def Task_Finish(self) -> None:
        self.controls_group.setEnabled(True)
        self.parameters_group.setEnabled(True)
        self._Availability_Refresh()

    def _Comparison_Set(self, result: AlgorithmResult) -> None:
        if self._dataset is None:
            return
        recorded_prefix = (
            "sf6.recorded"
            if self._dataset.Series_Get("sf6.recorded.navigation.position_enu") is not None
            else
            "eskf15.recorded"
            if self._dataset.Series_Get("eskf15.recorded.navigation.position_enu") is not None
            else "kf6.recorded"
            if self._dataset.Series_Get("kf6.recorded.navigation.position_enu") is not None
            else "pure_ins.recorded"
        )
        mappings = (
            ("comparison.attitude", f"{recorded_prefix}.attitude.q_nb", "attitude.q_nb", True),
            (
                "comparison.velocity",
                f"{recorded_prefix}.navigation.velocity_enu",
                "navigation.velocity_enu",
                False,
            ),
            (
                "comparison.position",
                f"{recorded_prefix}.navigation.position_enu",
                "navigation.position_enu",
                False,
            ),
        )
        rows: list[tuple[str, object]] = []
        for name_code, recorded_id, recomputed_id, quaternion in mappings:
            recorded = self._dataset.Series_Get(recorded_id)
            recomputed = result.channels.get(recomputed_id)
            if recorded is None or recomputed is None:
                continue
            comparison = Series_Compare(recorded, recomputed, quaternion=quaternion)
            rows.append((self._translator.Text_Get(name_code), comparison))
        self.comparison_table.setRowCount(len(rows))
        for row, (name, comparison) in enumerate(rows):
            statistics = comparison.statistics
            values = (
                name,
                str(statistics.sample_count),
                f"{statistics.mean_absolute_error:.6g} {comparison.unit}",
                f"{statistics.root_mean_square_error:.6g} {comparison.unit}",
                f"{statistics.maximum_absolute_error:.6g} {comparison.unit}",
            )
            for column, value in enumerate(values):
                self.comparison_table.setItem(row, column, QTableWidgetItem(value))
        header = self.comparison_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            self.comparison_table.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )

    def _ComboLabels_Refresh(self) -> None:
        mode = self.mode_combo.currentData() or ReplayMode.RECORDED_CONFIGURATION
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        self.mode_combo.addItem(
            self._translator.Text_Get("replay.mode.recorded"),
            ReplayMode.RECORDED_CONFIGURATION,
        )
        self.mode_combo.addItem(
            self._translator.Text_Get("replay.mode.offline"),
            ReplayMode.OFFLINE,
        )
        self.mode_combo.addItem(
            self._translator.Text_Get("replay.mode.what_if"), ReplayMode.WHAT_IF
        )
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(mode), 0))
        self.mode_combo.blockSignals(False)

    def Language_Apply(self, translator: Translator) -> None:
        edited = (
            self._ActualValues_Get() if self.mode_combo.currentData() == ReplayMode.WHAT_IF else {}
        )
        self._translator = translator
        self._ComboLabels_Refresh()
        self._AlgorithmLabels_Refresh()
        self.controls_group.setTitle(translator.Text_Get("replay.configuration"))
        self.algorithm_label.setText(translator.Text_Get("label.algorithm"))
        self.mode_label.setText(translator.Text_Get("label.mode"))
        self.quality_policy_label.setText(translator.Text_Get("replay.quality_policy"))
        for index in range(self.quality_policy_combo.count()):
            revision = self.quality_policy_combo.itemData(index)
            self.quality_policy_combo.setItemText(
                index,
                translator.Text_Get(
                    "replay.quality_recorded" if revision is None else "replay.quality_revision",
                    revision=revision,
                ),
            )
        self.fidelity_label.setText(translator.Text_Get("label.fidelity"))
        self.analysis_source_group.setTitle(translator.Text_Get("replay.analysis_data_source"))
        self.parameters_group.setTitle(translator.Text_Get("replay.what_if_parameters"))
        self.parameter_group_label.setText(translator.Text_Get("replay.parameter_group"))
        self.parameter_reset_button.setText(translator.Text_Get("action.reset_parameters"))
        self.parameter_reset_button.setToolTip(
            translator.Text_Get("action.reset_parameters_tooltip")
        )
        self.parameter_modified_label.setText(translator.Text_Get("replay.parameters_modified"))
        self.run_button.setText(translator.Text_Get("action.run_replay"))
        self.result_information_group.setTitle(translator.Text_Get("replay.result_information"))
        self.stored_results_group.setTitle(translator.Text_Get("replay.stored_results"))
        self.stored_results_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("replay.result_id"),
                translator.Text_Get("label.algorithm"),
                translator.Text_Get("label.mode"),
                translator.Text_Get("label.input_source"),
                translator.Text_Get("label.fidelity"),
                translator.Text_Get("replay.time_coverage"),
                translator.Text_Get("label.samples"),
                translator.Text_Get("replay.generated_channels"),
            ]
        )
        self.comparison_group.setTitle(translator.Text_Get("replay.comparison"))
        self.comparison_table.setHorizontalHeaderLabels(
            [
                translator.Text_Get("comparison.channel"),
                translator.Text_Get("comparison.samples"),
                "MAE",
                "RMSE",
                translator.Text_Get("comparison.maximum_error"),
            ]
        )
        for parameter_id, label in self._parameter_labels.items():
            parameter = self._parameter_specs[parameter_id]
            label.setText(self._Parameter_Label(parameter))
            self._ParameterTooltip_Apply(parameter)
        self._ParameterGroups_Refresh()
        self._ParameterForm_Refresh()
        self._ParametersDirty_Refresh()
        self._Mode_Refresh()
        for key, value in edited.items():
            self._parameter_widgets[key].setValue(value)
            self._parameter_widgets[key].setProperty("actualValue", value)
        self._ParametersDirty_Refresh()
        self._Availability_Refresh()
        if self._last_entry is not None:
            self._ResultInformation_Set(self._last_entry)
            self._StoredResults_Refresh(select_result_id=self._last_entry.result_id)
            self._Comparison_Set(self._last_entry.result)
        else:
            self._StoredResults_Refresh()
        self._AnalysisSources_Refresh()
