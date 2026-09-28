from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import ToolchainToolView
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.widgets import (
    CollapsibleSection,
)


class BuildPage(ScrollableLocalizedPage):
    detectionRequested = Signal()
    actionRequested = Signal(str)

    _PRIMARY_ACTIONS = (
        ("generate_apply", "action.generate_apply_project"),
        ("open_vscode", "action.open_vscode_workspace"),
        ("open_folder", "action.open_project_folder"),
    )
    _QUALITY_ACTIONS = (
        ("host_tests", "action.host_tests"),
        ("architecture_check", "action.architecture_check"),
        ("power10_check", "action.power10_check"),
        ("static_analysis", "action.static_analysis"),
        ("artifact_check", "action.artifact_check"),
    )
    def __init__(self, translator: Translator) -> None:
        super().__init__(translator, "page.build", "page.build.description")
        summary_form = QFormLayout()
        self.target_label = QLabel()
        self.Text_Register(self.target_label, "field.build_target")
        self.target_value = QLabel("—")
        summary_form.addRow(self.target_label, self.target_value)
        self.environment_label = QLabel()
        self.Text_Register(self.environment_label, "field.development_environment")
        self.environment_value = QLabel("VS Code + EIDE")
        summary_form.addRow(self.environment_label, self.environment_value)
        summary_layout = QVBoxLayout()
        summary_layout.addLayout(summary_form)
        self.root_layout.addWidget(
            self.Group_Create("group.build_configuration", summary_layout)
        )

        primary_actions = QHBoxLayout()
        self.action_buttons: dict[str, QPushButton] = {}
        for action_id, key in self._PRIMARY_ACTIONS:
            button = self._ActionButton_Create(action_id, key)
            if action_id == "generate_apply":
                button.setObjectName("primaryButton")
            primary_actions.addWidget(button)
        primary_actions.addStretch(1)
        self.root_layout.addLayout(primary_actions)

        advanced_layout = QVBoxLayout()
        verification_label = QLabel()
        verification_label.setObjectName("sectionLabel")
        self.Text_Register(verification_label, "build.section.verification")
        advanced_layout.addWidget(verification_label)
        verification_help = QLabel()
        verification_help.setWordWrap(True)
        verification_help.setProperty("muted", True)
        self.Text_Register(verification_help, "build.help.verification")
        advanced_layout.addWidget(verification_help)
        verification_row = QHBoxLayout()
        verification_button = self._ActionButton_Create(
            "build", "action.validation_build"
        )
        verification_button.setMinimumWidth(180)
        verification_row.addWidget(verification_button)
        clean_button = self._ActionButton_Create("clean", "action.clean")
        clean_button.setMinimumWidth(120)
        verification_row.addWidget(clean_button)
        clean_all_button = self._ActionButton_Create(
            "clean_all", "action.clean_all"
        )
        clean_all_button.setMinimumWidth(120)
        verification_row.addWidget(clean_all_button)
        verification_row.addStretch(1)
        advanced_layout.addLayout(verification_row)

        quality_label = QLabel()
        quality_label.setObjectName("sectionLabel")
        self.Text_Register(quality_label, "build.section.quality")
        advanced_layout.addWidget(quality_label)
        quality_help = QLabel()
        quality_help.setWordWrap(True)
        quality_help.setProperty("muted", True)
        self.Text_Register(quality_help, "build.help.quality")
        advanced_layout.addWidget(quality_help)
        quality_grid = QGridLayout()
        quality_grid.setColumnStretch(0, 0)
        quality_grid.setColumnStretch(1, 1)
        self.quality_result_labels: dict[str, QLabel] = {}
        for index, (action_id, key) in enumerate(self._QUALITY_ACTIONS):
            button = self._ActionButton_Create(action_id, key)
            button.setMinimumWidth(180)
            result_label = QLabel()
            result_label.setObjectName("statusPill")
            result_label.setProperty("statusLevel", "info")
            result_label.setWordWrap(True)
            self.quality_result_labels[action_id] = result_label
            quality_grid.addWidget(button, index, 0)
            quality_grid.addWidget(result_label, index, 1)
        advanced_layout.addLayout(quality_grid)

        output_form = QFormLayout()
        self.latest_artifact_label = QLabel()
        self.Text_Register(self.latest_artifact_label, "field.latest_firmware")
        self.latest_artifact_value = QLabel("—")
        output_form.addRow(
            self.latest_artifact_label, self.latest_artifact_value
        )
        self.firmware_output_label = QLabel()
        self.Text_Register(self.firmware_output_label, "field.firmware_output_directory")
        self.firmware_output_value = QLabel("—")
        self.firmware_output_value.setWordWrap(True)
        output_form.addRow(
            self.firmware_output_label, self.firmware_output_value
        )
        advanced_layout.addLayout(output_form)
        firmware_output_button = self._ActionButton_Create(
            "open_firmware_output", "action.open_firmware_output"
        )
        firmware_output_button.setMinimumWidth(180)
        advanced_layout.addWidget(firmware_output_button)

        tool_status_layout = QGridLayout()
        tool_status_layout.setColumnStretch(0, 0)
        tool_status_layout.setColumnStretch(1, 1)
        firmware_tools_label = QLabel()
        firmware_tools_label.setObjectName("sectionLabel")
        self.Text_Register(
            firmware_tools_label, "build.section.firmware_environment"
        )
        tool_status_layout.addWidget(firmware_tools_label, 0, 0, 1, 2)
        self.tool_name_labels: dict[str, QLabel] = {}
        self.tool_status_labels: dict[str, QLabel] = {}
        for row, tool_id in enumerate(("compiler", "make"), start=1):
            name_label = QLabel()
            self.Text_Register(name_label, f"tool.{tool_id}")
            status_label = QLabel()
            status_label.setObjectName("statusPill")
            status_label.setProperty("statusLevel", "info")
            self.tool_name_labels[tool_id] = name_label
            self.tool_status_labels[tool_id] = status_label
            tool_status_layout.addWidget(name_label, row, 0)
            tool_status_layout.addWidget(status_label, row, 1)
        host_tools_label = QLabel()
        host_tools_label.setObjectName("sectionLabel")
        self.Text_Register(host_tools_label, "build.section.host_environment")
        tool_status_layout.addWidget(host_tools_label, 3, 0, 1, 2)
        host_name_label = QLabel()
        self.Text_Register(host_name_label, "tool.host_gcc")
        host_status_label = QLabel()
        host_status_label.setObjectName("statusPill")
        host_status_label.setProperty("statusLevel", "info")
        self.tool_name_labels["host_gcc"] = host_name_label
        self.tool_status_labels["host_gcc"] = host_status_label
        tool_status_layout.addWidget(host_name_label, 4, 0)
        tool_status_layout.addWidget(host_status_label, 4, 1)
        self.tool_status_group = self.Group_Create(
            "build.section.toolchain", tool_status_layout
        )
        advanced_layout.addWidget(self.tool_status_group)
        detect_row = QHBoxLayout()
        self.detect_button = QPushButton()
        self.detect_button.setMinimumWidth(120)
        self.Text_Register(self.detect_button, "action.detect_toolchain")
        self.detect_button.clicked.connect(
            lambda _checked=False: self.detectionRequested.emit()
        )
        detect_row.addWidget(self.detect_button)
        self.install_guide_button = self._ActionButton_Create(
            "tool_install_guide", "action.install_guide"
        )
        self.install_guide_button.setMinimumWidth(120)
        detect_row.addWidget(self.install_guide_button)
        detect_row.addStretch(1)
        advanced_layout.addLayout(detect_row)
        self.advanced_section = CollapsibleSection(expanded=False)
        self.advanced_section.BodyLayout_Set(advanced_layout)
        self.advanced_group = self.advanced_section
        self.root_layout.addWidget(self.advanced_section)

        log_layout = QVBoxLayout()
        self.build_log = QPlainTextEdit()
        TouchScroll_Enable(self.build_log)
        self.build_log.setObjectName("buildLog")
        self.build_log.setReadOnly(True)
        self.build_log.setMaximumBlockCount(20_000)
        self.build_log.setMinimumHeight(220)
        log_layout.addWidget(self.build_log)
        advanced_layout.addWidget(self.Group_Create("group.build_log", log_layout))
        detail_layout = QVBoxLayout()
        self.build_detail_log = QPlainTextEdit()
        TouchScroll_Enable(self.build_detail_log)
        self.build_detail_log.setObjectName("buildDetailLog")
        self.build_detail_log.setReadOnly(True)
        self.build_detail_log.setMaximumBlockCount(20_000)
        self.build_detail_log.setMinimumHeight(180)
        detail_layout.addWidget(self.build_detail_log)
        self.build_detail_section = CollapsibleSection(expanded=False)
        self.build_detail_section.BodyLayout_Set(detail_layout)
        advanced_layout.addWidget(self.build_detail_section)
        self.root_layout.addStretch(1)
        self._tools: tuple[ToolchainToolView, ...] = ()
        self._action_keys = {
            action_id: key
            for action_id, key in (
                *self._PRIMARY_ACTIONS,
                *self._QUALITY_ACTIONS,
                ("build", "action.validation_build"),
                ("clean", "action.clean"),
                ("clean_all", "action.clean_all"),
                ("open_firmware_output", "action.open_firmware_output"),
                ("tool_install_guide", "action.install_guide"),
            )
        }
        self.Language_Apply(translator)
        self.Tools_Set(())
        self.QualityResults_Set(())
        self.GeneratedProject_Set(False)
        self.FirmwareArtifact_Set("", "")

    def _ActionButton_Create(self, action_id: str, key: str) -> QPushButton:
        button = QPushButton()
        button.setMinimumWidth(120)
        self.Text_Register(button, key)
        button.clicked.connect(
            lambda _checked=False, selected=action_id: self.actionRequested.emit(
                selected
            )
        )
        self.action_buttons[action_id] = button
        return button

    def Tools_Set(self, tools: Iterable[ToolchainToolView]) -> None:
        self._tools = tuple(tools)
        by_id = {tool.tool_id: tool for tool in self._tools}
        for tool_id, label in self.tool_status_labels.items():
            tool = by_id.get(tool_id)
            status = tool.status if tool is not None else "not_checked"
            status_text = self._translator.Text_Get(f"tool.status.{status}")
            version = tool.version if tool is not None else ""
            label.setText(
                " · ".join(value for value in (version, status_text) if value)
            )
            label.setToolTip(
                "\n".join(
                    value
                    for value in (
                        tool.path if tool is not None else "",
                        getattr(tool, "target", "") if tool is not None else "",
                    )
                    if value
                )
            )
            label.setProperty(
                "statusLevel",
                "success"
                if status == "found"
                else "error" if status in {"invalid", "not_found"} else "info",
            )
            label.style().unpolish(label)
            label.style().polish(label)
        status = {tool.tool_id: tool.status for tool in self._tools}
        compiler_found = status.get("compiler") == "found"
        make_found = status.get("make") == "found"
        host_found = status.get("host_gcc") == "found"
        enabled_by_action = {
            "build": compiler_found and make_found,
            "clean": make_found,
            "clean_all": make_found,
            "host_tests": host_found and make_found,
            "architecture_check": make_found,
            "power10_check": make_found,
            "static_analysis": compiler_found and make_found,
            "artifact_check": compiler_found and make_found,
        }
        for action_id, enabled in enabled_by_action.items():
            self.action_buttons[action_id].setEnabled(enabled)
        self._ActionTooltips_Apply()

    def QualityResults_Set(self, records: Iterable[object]) -> None:
        self._quality_records = tuple(records)
        by_task = {
            str(getattr(record, "task", "")): record
            for record in self._quality_records
        }
        for task, label in self.quality_result_labels.items():
            record = by_task.get(task)
            if record is None:
                label.setText(self._translator.Text_Get("quality.result.not_run"))
                label.setProperty("statusLevel", "info")
                label.setToolTip("")
            else:
                passed = getattr(record, "result", "") == "passed"
                status = self._translator.Text_Get(
                    "quality.result.passed" if passed else "quality.result.failed"
                )
                summary = str(getattr(record, "summary", "")).strip()
                if summary.startswith("checks="):
                    summary = self._translator.Text_Get(
                        "quality.summary.checks",
                        count=summary.partition("=")[2],
                    )
                elif summary.startswith("exit_code="):
                    summary = self._translator.Text_Get(
                        "quality.summary.exit_code",
                        code=summary.partition("=")[2],
                    )
                elif summary in {
                    "analysis_passed",
                    "artifact_validated",
                    "completed",
                    "error",
                }:
                    summary = self._translator.Text_Get(
                        f"quality.summary.{summary}"
                    )
                label.setText(
                    " · ".join(value for value in (status, summary) if value)
                )
                label.setProperty("statusLevel", "success" if passed else "error")
                label.setToolTip(
                    self._translator.Text_Get(
                        "quality.result.tooltip",
                        timestamp=str(getattr(record, "timestamp", "")),
                        duration=f"{float(getattr(record, 'duration', 0.0)):.2f}",
                    )
                )
            label.style().unpolish(label)
            label.style().polish(label)

    def _ActionTooltips_Apply(self) -> None:
        if not hasattr(self, "_action_keys"):
            return
        status = {tool.tool_id: tool.status for tool in self._tools}
        requirements = {
            "build": ("compiler", "make"),
            "clean": ("make",),
            "clean_all": ("make",),
            "host_tests": ("host_gcc", "make"),
            "architecture_check": ("make",),
            "power10_check": ("make",),
            "static_analysis": ("compiler", "make"),
            "artifact_check": ("compiler", "make"),
        }
        for action_id, key in self._action_keys.items():
            button = self.action_buttons.get(action_id)
            if button is None:
                continue
            tooltip = self._translator.Text_Get(f"{key}.tooltip")
            missing = tuple(
                self._translator.Text_Get(f"tool.{tool_id}")
                for tool_id in requirements.get(action_id, ())
                if status.get(tool_id) != "found"
            )
            if missing:
                tooltip += "\n" + self._translator.Text_Get(
                    "tool.missing_reason", missing=", ".join(missing)
                )
            button.setToolTip(tooltip)

    def Project_Set(
        self, target: str, environment: str = "VS Code + EIDE"
    ) -> None:
        self.target_value.setText(target or "—")
        self.environment_value.setText(environment or "—")

    def GeneratedProject_Set(self, available: bool) -> None:
        for action_id in ("open_vscode", "open_folder"):
            button = self.action_buttons.get(action_id)
            if button is not None:
                button.setEnabled(available)

    def FirmwareArtifact_Set(self, directory: str, artifact_name: str) -> None:
        self.firmware_output_value.setText(directory or "—")
        self.firmware_output_value.setToolTip(directory)
        self.latest_artifact_value.setText(artifact_name or "—")
        button = self.action_buttons.get("open_firmware_output")
        if button is not None:
            button.setEnabled(bool(directory and artifact_name))

    def BuildLog_Set(self, text: str) -> None:
        self.build_log.setPlainText(text)

    def BuildLog_Append(self, text: str) -> None:
        if text:
            self.build_log.appendPlainText(text.rstrip())

    def BuildDetailLog_Set(self, text: str) -> None:
        self.build_detail_log.setPlainText(text)

    def BuildDetailLog_Append(self, text: str) -> None:
        if text:
            self.build_detail_log.appendPlainText(text.rstrip())

    def Language_Apply(self, translator: Translator) -> None:
        super().Language_Apply(translator)
        self.advanced_section.Title_Set(translator.Text_Get("group.advanced_build"))
        self.build_detail_section.Title_Set(
            translator.Text_Get("group.build_detail_log")
        )
        if hasattr(self, "_tools"):
            self.Tools_Set(self._tools)
        if hasattr(self, "quality_result_labels"):
            self.QualityResults_Set(getattr(self, "_quality_records", ()))
        self._ActionTooltips_Apply()


def DefaultTools_Get() -> tuple[ToolchainToolView, ...]:
    return (
        ToolchainToolView("compiler", "Arm GNU Toolchain", "arm-none-eabi-gcc"),
        ToolchainToolView("make", "GNU Make", "mingw32-make"),
        ToolchainToolView("host_gcc", "Host GCC", "gcc"),
    )
