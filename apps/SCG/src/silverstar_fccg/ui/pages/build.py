from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSignalBlocker, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
)

from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.ui.theme import ThemeTokens_Get
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import ToolchainToolView
from silverstar_fccg.project.artifact_memory import ArtifactMemorySummary_Decode, ArtifactMemoryMarginLevel_Get
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
from silverstar_fccg.ui.pages.native_usb import NativeUsbPanel
from silverstar_fccg.ui.widgets import (
    CollapsibleSection,
)


class BuildPage(ScrollableLocalizedPage):
    issueActivated = Signal(object)
    detectionRequested = Signal()
    actionRequested = Signal(str)
    memoryLayoutChanged = Signal(str)

    _PRIMARY_ACTIONS: tuple[tuple[str, str], ...] = ()
    _TARGET_ACTIONS = (
        ("build", "action.target_build"),
        ("clean", "action.target_clean"),
        ("open_vscode", "action.open_vscode_workspace"),
        ("open_folder", "action.open_project_folder"),
        ("artifact_check", "action.target_artifact_check"),
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
        self.issues_section=CollapsibleSection(translator.Text_Get('workspace.checks.issues'),expanded=False)
        issue_layout=QVBoxLayout(self.issues_section.body)
        self.issue_summary=QLabel();self.issue_summary.setWordWrap(True)
        self.root_layout.addWidget(self.issue_summary)
        self.issues_list=QListWidget();self.issues_list.setMaximumHeight(180)
        TouchScroll_Enable(self.issues_list)
        self.issues_list.itemClicked.connect(lambda item:self.issueActivated.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.issues_list.itemActivated.connect(lambda item:self.issueActivated.emit(item.data(Qt.ItemDataRole.UserRole)))
        issue_layout.addWidget(self.issues_list);self.root_layout.addWidget(self.issues_section)
        summary_form = QFormLayout()
        self.target_label = QLabel()
        self.Text_Register(self.target_label, "field.build_target")
        self.target_value = QLabel("—")
        summary_form.addRow(self.target_label, self.target_value)
        self.environment_label = QLabel()
        self.Text_Register(self.environment_label, "field.development_environment")
        self.environment_value = QLabel("VS Code + EIDE")
        summary_form.addRow(self.environment_label, self.environment_value)
        self.memory_layout_label = QLabel()
        self.Text_Register(self.memory_layout_label, "field.memory_layout")
        self.memory_layout_combo = QComboBox()
        for layout in ("auto", "eskf_window_sram"):
            self.memory_layout_combo.addItem(translator.Text_Get("memory.layout." + layout), layout)
        self.memory_layout_combo.currentIndexChanged.connect(
            lambda _: self.memoryLayoutChanged.emit(self.memory_layout_combo.currentData())
        )
        summary_form.addRow(self.memory_layout_label, self.memory_layout_combo)
        self.memory_margin_label = QLabel()
        self.Text_Register(self.memory_margin_label, "field.linked_memory")
        self.memory_margin_value = QLabel()
        self.memory_margin_value.setWordWrap(True)
        summary_form.addRow(self.memory_margin_label, self.memory_margin_value)
        summary_layout = QVBoxLayout()
        summary_layout.addLayout(summary_form)
        self.configuration_group = self.Group_Create("group.build_configuration", summary_layout)

        self.action_buttons: dict[str, QPushButton] = {}
        self.native_usb = NativeUsbPanel(translator.language)
        self.target_status_labels: dict[str, QLabel] = {}
        self.target_summary_labels: dict[str, QLabel] = {}
        self.target_action_layouts = {}
        for target, group_key in (
            ("flight", "group.flight_build"),
            ("ground", "group.ground_build_target"),
        ):
            target_layout = QVBoxLayout()
            status_label = QLabel()
            self.target_status_labels[target] = status_label
            target_layout.addWidget(status_label)
            summary = QLabel()
            summary.setWordWrap(True)
            summary.setTextFormat(Qt.TextFormat.PlainText)
            target_layout.addWidget(summary)
            self.target_summary_labels[target] = summary
            actions = QGridLayout()
            self.target_action_layouts[target] = actions
            for index, (action_id, key) in enumerate(self._TARGET_ACTIONS, start=1):
                actions.addWidget(self._ActionButton_Create(f"{target}_{action_id}", key), index // 3, index % 3)
            target_layout.addLayout(actions)
            self.root_layout.addWidget(self.Group_Create(group_key, target_layout))


        advanced_layout = QVBoxLayout()
        advanced_layout.addWidget(self.configuration_group)
        advanced_layout.addWidget(self.native_usb)
        quality_label = QLabel()
        quality_label.setObjectName("sectionLabel")
        self.Text_Register(quality_label, "build.section.quality")
        advanced_layout.addWidget(quality_label)
        quality_help = QLabel()
        quality_help.setWordWrap(True)
        quality_help.setProperty("muted", True)
        self.Text_Register(quality_help, "build.help.quality")
        advanced_layout.addWidget(quality_help)
        quality_actions = QHBoxLayout()
        for action_id, key in self._QUALITY_ACTIONS:
            button = self._ActionButton_Create(action_id, key)
            quality_actions.addWidget(button)
        advanced_layout.addLayout(quality_actions)
        self.quality_target_checks = {}
        self.target_quality_labels = {}
        self.target_quality_reviews = {}
        self.target_quality_progress = {}
        self.target_quality_status = {}
        self._target_quality_records = {"flight": (), "ground": ()}
        self._target_quality_states = {"flight": {}, "ground": {}}
        for target, key in (("flight", "group.flight_build"), ("ground", "group.ground_build_target")):
            layout = QVBoxLayout()
            check = QCheckBox()
            self.Text_Register(check, "quality.target.include")
            check.setChecked(target == "flight")
            self.quality_target_checks[target] = check
            layout.addWidget(check)
            status = QLabel()
            status.setWordWrap(True)
            self.target_quality_status[target] = status
            layout.addWidget(status)
            progress = QProgressBar()
            progress.setRange(0, 1000)
            progress.setValue(0)
            self.target_quality_progress[target] = progress
            layout.addWidget(progress)
            grid = QGridLayout()
            labels = {}
            for row, (action_id, action_key) in enumerate(self._QUALITY_ACTIONS):
                name = QLabel()
                self.Text_Register(name, action_key)
                grid.addWidget(name, row, 0)
                label = QLabel()
                label.setObjectName("statusPill")
                label.setWordWrap(True)
                labels[action_id] = label
                grid.addWidget(label, row, 1)
            review = QLabel()
            review.setObjectName("statusPill")
            review.setWordWrap(True)
            self.target_quality_reviews[target] = review
            self.target_quality_labels[target] = labels
            layout.addLayout(grid)
            layout.addWidget(review)
            advanced_layout.addWidget(self.Group_Create(key, layout))
            check.toggled.connect(lambda _checked, selected=target: self._QualitySelection_Update(selected))
        # Compatibility aliases denote Flight only; Ground has its own state.
        self.quality_result_labels = self.target_quality_labels["flight"]
        self.power10_review_label = self.target_quality_reviews["flight"]

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
        self.root_layout.insertWidget(1, self.tool_status_group)
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
        self.root_layout.insertLayout(2, detect_row)
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
        self._target_generated = {"flight": False, "ground": False}
        self._ground_enabled = False
        self._action_keys = {
            action_id: key
            for action_id, key in (
                *self._PRIMARY_ACTIONS,
                *self._QUALITY_ACTIONS,
                ("open_firmware_output", "action.open_firmware_output"),
                ("tool_install_guide", "action.install_guide"),
                *((f"{target}_{action}", key)
                  for target in ("flight", "ground")
                  for action, key in self._TARGET_ACTIONS),
            )
        }
        self.Language_Apply(translator)
        self.Tools_Set(())
        self.QualityResults_Set(())
        self.GeneratedProject_Set(False)
        self.FirmwareArtifact_Set("", "")

    def Issues_Set(self,issues):
        self.issues_list.clear()
        errors=sum(issue.level=='error' for issue in issues)
        warnings=sum(issue.level=='warning' for issue in issues)
        self.issue_summary.setText(self._translator.Text_Get('workspace.checks.issue_summary',errors=errors,warnings=warnings))
        self.issues_section.Title_Set(self._translator.Text_Get('workspace.checks.issues'))
        for issue in issues:
            item=QListWidgetItem('['+issue.level+'] '+issue.code+' · '+issue.message)
            item.setData(Qt.ItemDataRole.UserRole,issue);item.setToolTip(issue.message)
            self.issues_list.addItem(item)
        self.issues_section.setVisible(bool(issues))

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

    def TargetEditors_Attach(self, flight_page, ground_page):
        """Move existing generation commands to their target cards exactly once."""
        owners = (flight_page, ground_page)
        if getattr(self, '_target_editor_owners', None) == owners:
            return
        if hasattr(self, '_target_editor_owners'):
            raise ValueError('Generation target editors already belong to this workspace')
        self._target_editor_owners = owners
        for target, page in (('flight', flight_page), ('ground', ground_page)):
            page.root_layout.removeWidget(page.generate_button)
            self.target_action_layouts[target].addWidget(page.generate_button, 0, 0)
            page.generate_button.show()
        self.target_action_layouts['ground'].addWidget(ground_page.enabled, 0, 1)
        ground_page.enabled.show()
        self.advanced_section.body.layout().addWidget(ground_page.build_group)

    def TargetConfiguration_Set(self, model):
        for target, hardware, identity, version in (
            ('flight', model.hardware, model.board, model.identity.firmware_version),
            ('ground', model.ground_target.hardware, model.ground_target.board,
             model.identity.firmware_version),
        ):
            self.target_summary_labels[target].setText(self._translator.Text_Get(
                'workspace.checks.target_summary', board=hardware.source_label or identity or '—',
                mcu=hardware.mcu or str(hardware.inventory.get('mcu_part', '')) or '—',
                version=version))
        self._configuration_model = model

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
            "host_tests": host_found and make_found,
            "architecture_check": make_found,
            "power10_check": make_found,
            "static_analysis": compiler_found and make_found,
            "artifact_check": compiler_found and make_found,
        }
        for action_id, enabled in enabled_by_action.items():
            self.action_buttons[action_id].setEnabled(enabled)
        self._TargetActions_Update()
        self._ActionTooltips_Apply()

    def Targets_Set(self, *, flight_generated: bool, ground_enabled: bool,
                    ground_generated: bool, usb_candidate: bool = False) -> None:
        self._target_generated = {
            "flight": flight_generated, "ground": ground_generated,
        }
        self._ground_enabled = ground_enabled
        self._usb_candidate = usb_candidate
        self._TargetActions_Update()

    def _TargetActions_Update(self) -> None:
        statuses = {tool.tool_id: tool.status for tool in self._tools}
        for target in ("flight", "ground"):
            generated = self._target_generated[target]
            configured = target == "flight" or self._ground_enabled
            status_key = (
                "target.status.not_configured" if not configured
                else "target.status.not_generated" if not generated
                else "target.status.generated"
            )
            self.target_status_labels[target].setText(self._translator.Text_Get(status_key))
            for action, _key in self._TARGET_ACTIONS:
                enabled = generated and configured
                if action == "build":
                    enabled = enabled and statuses.get("compiler") == "found" and (
                        (target == 'ground' and getattr(self, '_usb_candidate', False))
                        or statuses.get("make") == "found")
                elif action == "clean":
                    enabled = enabled and ((target == 'ground' and getattr(self, '_usb_candidate', False))
                                           or statuses.get("make") == "found")
                self.action_buttons[f"{target}_{action}"].setEnabled(enabled)

    def QualityResults_Set(self, records: Iterable[object]) -> None:
        # Explicit presentation API; project input validation is supplied by
        # MainWindow.TargetQualityResults_Refresh via the target-aware setter.
        self.TargetQualityResults_Set("flight", records, {})

    def QualityTargets_Get(self) -> tuple[str, ...]:
        return tuple(target for target, check in self.quality_target_checks.items() if check.isChecked())

    def _QualitySelection_Update(self, target: str) -> None:
        self.TargetQualityResults_Set(target, self._target_quality_records[target],
                                     self._target_quality_states[target])

    def TargetQualityProgress_Set(self, target: str, fraction: float | None, text: str,
                                 *, succeeded: bool = False) -> None:
        progress = self.target_quality_progress[target]
        progress.setRange(0, 0 if fraction is None else 1000)
        if fraction is not None:
            progress.setValue(1000 if succeeded else min(999, max(0, int(fraction * 1000))))
        self.target_quality_status[target].setText(text)

    def TargetQualityResults_Set(self, target: str, records: Iterable[object],
                                 states: dict[str, str] | None = None) -> None:
        records = tuple(records)
        self._target_quality_records[target] = records
        if states is not None:
            self._target_quality_states[target] = states
        states = self._target_quality_states[target]
        selected = self.quality_target_checks[target].isChecked()
        if not selected:
            self.TargetQualityProgress_Set(target, 0.0, self._translator.Text_Get("quality.target.not_selected"))
        labels = self.target_quality_labels[target]
        review_label = self.target_quality_reviews[target]
        if target == "flight":
            self._quality_records = records
        by_task = {
            str(getattr(record, "task", "")): record
            for record in records
        }
        artifact = by_task.get("artifact_check")
        regions = ArtifactMemorySummary_Decode(str(getattr(artifact, "summary", "")))
        if target == "flight" and regions and selected and not states.get("artifact_check"):
            levels = [ArtifactMemoryMarginLevel_Get(remaining, capacity) for _, remaining, capacity in regions]
            application = QApplication.instance()
            theme = application.property("fccgAppliedTheme") if application else "light"
            tokens = ThemeTokens_Get(theme)
            colors = {"error": tokens.error, "warning": tokens.warning, "success": tokens.success}
            text = "<br>".join('<span style="color:' + colors[level] + '">' + self._translator.Text_Get(
                "memory.region", name=name, used=f"{used:,}", capacity=f"{capacity:,}",
                remaining=f"{remaining:,}") + f" ({remaining / capacity * 100:.2f}%)</span>"
                for name, (used, remaining, capacity), level in zip(("Flash", "SRAM", "CCMRAM"), regions, levels))
            narrow = regions[2][1] < 4096
            text += "<br>" + self._translator.Text_Get("memory.ccm_narrow" if narrow else "memory.static_only")
            text += "<br>" + self._translator.Text_Get("memory.keep_green")
            self.memory_margin_value.setText(text)
            self.memory_margin_value.setProperty("statusLevel", "error" if "error" in levels else "warning" if "warning" in levels else "success")
            self.memory_margin_value.setToolTip(str(getattr(artifact, "timestamp", "")))
        elif target == "flight":
            self.memory_margin_value.setText(self._translator.Text_Get("memory.not_checked"))
            self.memory_margin_value.setProperty("statusLevel", "info")
            self.memory_margin_value.setToolTip("")
        for task, label in labels.items():
            record = by_task.get(task)
            raw_summary = str(getattr(record, "summary", "")).strip()
            critical_failure = task == "power10_check" and "POWER10_CONTRACT_REVIEW|FAIL|" in raw_summary
            if task == "power10_check":
                review = review_label
                review.setVisible(record is not None and selected)
                review.setText(self._translator.Text_Get(
                    "power10.contract_review_failed" if critical_failure else "power10.contract_review_pending")
                    if record is not None else "")
                review.setProperty("statusLevel", "error" if critical_failure else "warning" if record is not None else "info")
                review.style().unpolish(review)
                review.style().polish(review)
            if not selected or states.get(task):
                state = "not_selected" if not selected else states[task]
                label.setText(self._translator.Text_Get("quality.target." + state))
                label.setProperty("statusLevel", "warning" if state == "stale" else "info")
                label.setToolTip("\n".join(str(getattr(record, field, ""))
                                          for field in ("timestamp", "summary", "details")))
            elif record is None:
                label.setText(self._translator.Text_Get("quality.result.not_run"))
                label.setProperty("statusLevel", "info")
                label.setToolTip("")
            else:
                passed = getattr(record, "result", "") == "passed" and not critical_failure
                status = self._translator.Text_Get(
                    "quality.result.passed" if passed else "quality.result.failed"
                )
                summary = raw_summary
                if task == "power10_check":
                    summary = self._translator.Text_Get("power10.automatic_checks")
                if ArtifactMemorySummary_Decode(summary):
                    summary = self._translator.Text_Get(
                        "quality.summary.artifact_validated" if passed else "quality.summary.completed")
                elif summary.startswith("checks="):
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
                    ) + "\n" + str(getattr(record, "summary", ""))
                    + "\n" + str(getattr(record, "details", ""))
                )
            label.style().unpolish(label)
            label.style().polish(label)

    def _ActionTooltips_Apply(self) -> None:
        if not hasattr(self, "_action_keys"):
            return
        status = {tool.tool_id: tool.status for tool in self._tools}
        requirements = {
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

    def MemoryLayout_Set(self, layout: str) -> None:
        with QSignalBlocker(self.memory_layout_combo):
            legacy_index = self.memory_layout_combo.findData("legacy")
            if layout == "legacy" and legacy_index < 0:
                self.memory_layout_combo.insertItem(
                    0, self._translator.Text_Get("memory.layout.legacy"), "legacy")
                self.memory_layout_combo.model().item(0).setEnabled(False)
            elif layout != "legacy" and legacy_index >= 0:
                self.memory_layout_combo.removeItem(legacy_index)
            self.memory_layout_combo.setCurrentIndex(self.memory_layout_combo.findData(layout))

    def GeneratedProject_Set(self, available: bool) -> None:
        self._target_generated["flight"] = available
        self._TargetActions_Update()

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
        self.native_usb.Language_Set(translator.language)
        for index in range(self.memory_layout_combo.count()):
            self.memory_layout_combo.setItemText(index, translator.Text_Get("memory.layout." + self.memory_layout_combo.itemData(index)))
        self.advanced_section.Title_Set(translator.Text_Get("group.advanced_build"))
        self.build_detail_section.Title_Set(
            translator.Text_Get("group.build_detail_log")
        )
        if hasattr(self, "_tools"):
            self.Tools_Set(self._tools)
        if hasattr(self, "quality_result_labels"):
            for target in ("flight", "ground"):
                self._QualitySelection_Update(target)
        self._ActionTooltips_Apply()
        self._TargetActions_Update()
        if hasattr(self, '_configuration_model'):
            self.TargetConfiguration_Set(self._configuration_model)


def DefaultTools_Get() -> tuple[ToolchainToolView, ...]:
    return (
        ToolchainToolView("compiler", "Arm GNU Toolchain", "arm-none-eabi-gcc"),
        ToolchainToolView("make", "GNU Make", "mingw32-make"),
        ToolchainToolView("host_gcc", "Host GCC", "gcc"),
    )
