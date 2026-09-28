from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.version import PRODUCT_NAME, __version__
from silverstar_fccg.build.runner import BuildAction, BuildProgress, BuildResult
from silverstar_fccg.build.toolchain import ArmGnuSubtoolPaths_Derive
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.path_preferences import PathPreferences
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.task import (
    TaskProgressEvent_Parse,
    TaskProgressState,
)
from silverstar_fccg.core.view_models import (
    ComponentType,
    ComponentView,
    LoggingStreamView,
    PlatformMatchView,
    ProtocolProfileView,
    ToolchainToolView,
)
from silverstar_fccg.generator.assembler import ApplyResult, GenerationPlan
from silverstar_fccg.generator.hardware_preparation import (
    HardwareAssignmentFingerprint_Get,
)
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameterOwners_Get
from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
from silverstar_fccg.project.configuration import (
    ModeOptionAvailabilities_Get,
    ProjectConfigurationResult,
    StrategyAvailabilities_Get,
)
from silverstar_fccg.project.lifecycle import ProjectLifecycleState
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LogCadenceKind,
    LoggingProfile_AvailabilityTransitionApply,
    LogPolicyLevel,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    DeviceInstance,
    HardwareConfiguration,
    LogStreamConfig,
    ProjectModel,
    ProtocolSelection,
)
from silverstar_fccg.project.protocols import ProtocolProfileAvailabilities_Get
from silverstar_fccg.project.quality_results import QualityResultRecord
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_EditValidate, ValidationIssue
from silverstar_fccg.ui.dialogs import NewProjectWizard
from silverstar_fccg.ui.message_box import MessageBoxButtons_Localize
from silverstar_fccg.ui.pages import (
    BoardHardwarePage,
    BuildPage,
    DevicesPage,
    FlightConfigurationPage,
    PluginManagerDialog,
)
from silverstar_fccg.ui.pages.algorithm_parameters import AlgorithmParametersPage
from silverstar_fccg.ui.pages.build import DefaultTools_Get
from silverstar_fccg.ui.theme import Theme_Apply, WindowCaption_Apply
from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable
from silverstar_fccg.ui.widgets import EngineeringTable, HeaderComboBox
from silverstar_fccg.ui.workers import FunctionWorker


@dataclass(frozen=True, slots=True)
class _ProjectDisplayState:
    model: ProjectModel
    devices: tuple[ComponentView, ...]
    device_instances: tuple[Any, ...]
    device_availability: dict[str, Any]
    selectable_components: tuple[ComponentView, ...]
    protocol_profiles: dict[str, tuple[ProtocolProfileView, ...]]
    selected_protocol_profiles: dict[str, tuple[str, str] | None]
    platform_match: PlatformMatchView
    strategy_availability: dict[str, Any]
    mode_availability: dict[tuple[str, str], Any]
    capability_usage: tuple[Any, ...]
    logging_streams: tuple[LoggingStreamView, ...]
    i2c_pullup_evidence: tuple[Any, ...]
    hardware_provider: str
    boards: tuple[Any, ...]
    resources: tuple[Any, ...]
    resources_valid: bool
    generated_project: bool
    firmware_output_directory: Path | None
    firmware_artifact_name: str
    quality_results: tuple[QualityResultRecord, ...]


@dataclass(frozen=True, slots=True)
class _WorkspaceLaunchResult:
    succeeded: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.succeeded


class MainWindow(QMainWindow):
    PAGE_CODES = (
        "page.devices",
        "page.flight_configuration",
        "page.algorithm_parameters",
        "page.board_hardware",
        "page.build",
    )

    def __init__(
        self,
        settings: SettingsStore,
        *,
        service: FccgService | None = None,
        language: str = "zh_CN",
        theme: str = "light",
    ) -> None:
        super().__init__()
        self._settings = settings
        workspace_root = Path(__file__).resolve().parents[3]
        self._service = service or FccgService(workspace_root)
        self._path_preferences = PathPreferences(self._service.policy, self._settings.path.parent / "path_preferences.json")
        self._translator = Translator(language)
        self._theme = theme if theme in {"light", "dark"} else "light"
        self._thread_pool = QThreadPool.globalInstance()
        self._active_worker: FunctionWorker | None = None
        self._worker_result_callback: Callable[[Any], None] | None = None
        self._worker_error_callback: Callable[[object], None] | None = None
        self._worker_line_callback: Callable[[str], None] | None = None
        self._worker_outcome: tuple[str, object, str] | None = None
        self._last_task_progress = 0
        self._task_indeterminate = False
        self._retired_workers: list[FunctionWorker] = []
        self._progress_hide_timer = QTimer(self)
        self._progress_hide_timer.setSingleShot(True)
        self._progress_hide_timer.timeout.connect(self._Progress_CompletionHide)
        self._component_views: tuple[ComponentView, ...] = ()
        self._model: ProjectModel = self._service.ProjectDraft_Create("SilverStar")
        self._project_root: Path | None = None
        self._generation_plan: GenerationPlan | None = None
        self._displaying_model = False
        self._project_state = ProjectLifecycleState.DRAFT
        self._pending_build_action: str | None = None
        self._active_build_action: BuildAction | None = None
        self._build_started_at = 0.0
        self._pending_mode_changes: dict[str, list[str]] = {}
        self._pending_mode_parameter_changes: dict[
            tuple[str, str, str], float | int
        ] = {}
        self._mode_refresh_scheduled = False
        self._pending_logging_streams: tuple[LoggingStreamView, ...] | None = None
        self._logging_refresh_scheduled = False
        self._validation_focus_widget: QWidget | None = None
        self._toolchain_dialog: QDialog | None = None
        self._install_guide_dialog: QDialog | None = None
        self._action_enabled_snapshot: dict[object, bool] = {}
        self.setWindowTitle(PRODUCT_NAME)
        self.setAcceptDrops(True)
        self.resize(1460, 900)
        self.setMinimumSize(1000, 700)
        self._Ui_Build()
        self._Menu_Build()
        self._Signals_Connect()
        self.Language_Apply(language)
        self.Theme_Apply(self._theme)
        self.build_page.Tools_Set(DefaultTools_Get())
        self._Catalog_Load()
        self._Project_Refresh()

    def _Ui_Build(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerBar")
        header.setMinimumHeight(58)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 6, 14, 6)
        self.title_label = QLabel()
        self.title_label.setObjectName("headerTitle")
        self.title_label.setWordWrap(True)
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        self.credit_label = QLabel()
        self.credit_label.setObjectName("headerCredit")
        self.current_project_label = QLabel()
        self.current_project_label.setObjectName("headerControlLabel")
        self.current_project_value = QLabel()
        self.current_project_value.setObjectName("headerProjectValue")
        self.language_label = QLabel()
        self.language_label.setObjectName("headerControlLabel")
        self.language_combo = HeaderComboBox("headerLanguageCombo")
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.theme_label = QLabel()
        self.theme_label.setObjectName("headerControlLabel")
        self.theme_combo = HeaderComboBox("headerThemeCombo")
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.version_label)
        header_layout.addWidget(self.credit_label)
        header_layout.addSpacing(16)
        header_layout.addWidget(self.current_project_label)
        header_layout.addWidget(self.current_project_value)
        header_layout.addStretch(1)
        header_layout.addWidget(self.language_label)
        header_layout.addWidget(self.language_combo)
        header_layout.addWidget(self.theme_label)
        header_layout.addWidget(self.theme_combo)
        root_layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        self.navigation_list = QListWidget()
        TouchScroll_Enable(self.navigation_list)
        self.navigation_list.setObjectName("navigation")
        self.navigation_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for code in self.PAGE_CODES:
            item = QListWidgetItem(code)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.navigation_list.addItem(item)
        sidebar_layout.addWidget(self.navigation_list)
        body_layout.addWidget(sidebar)

        self.pages = QStackedWidget()
        self.devices_page = DevicesPage(self._translator)
        self.flight_configuration_page = FlightConfigurationPage(self._translator)
        self.algorithm_parameters_page = AlgorithmParametersPage(self._translator)
        self.algorithm_parameters_page.parameterChanged.connect(self._AlgorithmParameter_Change)
        self.algorithm_parameters_page.defaultsRequested.connect(self._AlgorithmDefaults_Reset)
        self.algorithm_parameters_page.sharedParameterChanged.connect(self._SharedAlgorithmParameter_Change)
        self.algorithm_parameters_page.sharedDefaultsRequested.connect(self._SharedAlgorithmDefaults_Reset)
        self.board_hardware_page = BoardHardwarePage(self._translator)
        self.build_page = BuildPage(self._translator)
        self._page_widgets = (
            self.devices_page,
            self.flight_configuration_page,
            self.algorithm_parameters_page,
            self.board_hardware_page,
            self.build_page,
        )
        for page in self._page_widgets:
            self.pages.addWidget(page)
        self.plugin_manager_dialog = PluginManagerDialog(self._translator, self)
        body_layout.addWidget(self.pages, 1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.status_label = QLabel()
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self._Task_Cancel)
        self.cancel_button.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setVisible(False)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.cancel_button)
        status.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status)
        self.navigation_list.setCurrentRow(0)

    def _Menu_Build(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.default_root_action = QAction(self)
        self.default_root_action.triggered.connect(self._DefaultProjectRoot_Select)
        self.new_action = QAction(self)
        self.new_action.setShortcut("Ctrl+N")
        self.open_action = QAction(self)
        self.open_action.setShortcut("Ctrl+O")
        self.save_action = QAction(self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_as_action = QAction(self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.export_source_action = QAction(self)
        self.exit_action = QAction(self)
        self.file_menu.addActions(
            (self.new_action, self.open_action, self.save_action, self.save_as_action)
        )
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.default_root_action)
        self.file_menu.addAction(self.export_source_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self.plugin_menu = self.menuBar().addMenu("")
        self.manage_plugins_action = QAction(self)
        self.install_plugin_action = QAction(self)
        self.refresh_plugins_action = QAction(self)
        self.plugin_menu.addActions(
            (
                self.manage_plugins_action,
                self.install_plugin_action,
                self.refresh_plugins_action,
            )
        )
        self.help_menu = self.menuBar().addMenu("")
        self.about_action = QAction(self)
        self.help_menu.addAction(self.about_action)

    def _Signals_Connect(self) -> None:
        self.navigation_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.language_combo.currentIndexChanged.connect(self._Language_Selected)
        self.theme_combo.currentIndexChanged.connect(self._Theme_Selected)
        self.new_action.triggered.connect(self._NewProject_Show)
        self.open_action.triggered.connect(self._Project_OpenDialog)
        self.save_action.triggered.connect(self._Project_Save)
        self.save_as_action.triggered.connect(self._Project_SaveAs)
        self.export_source_action.triggered.connect(
            self._SourcePackageExport_Request
        )
        self.exit_action.triggered.connect(self.close)
        self.manage_plugins_action.triggered.connect(self._PluginManager_Show)
        self.install_plugin_action.triggered.connect(self._PluginInstall_Dialog)
        self.refresh_plugins_action.triggered.connect(self._Plugins_Refresh)
        self.about_action.triggered.connect(self._About_Show)
        self.devices_page.instanceChanged.connect(self._DeviceInstance_Change)
        self.devices_page.instanceAddRequested.connect(self._DeviceInstance_Add)
        self.devices_page.otherDeviceToggled.connect(self._OtherDevice_Toggle)
        self.devices_page.installRequested.connect(self._PluginInstall_Dialog)
        self.board_hardware_page.boardChanged.connect(self._BoardSelection_Change)
        self.board_hardware_page.customSelected.connect(self._CustomHardware_Select)
        self.board_hardware_page.importIocRequested.connect(
            lambda: self._CubeMxImport_Request(False)
        )
        self.board_hardware_page.importDirectoryRequested.connect(
            lambda: self._CubeMxImport_Request(True)
        )
        self.board_hardware_page.exportRequested.connect(
            self._CustomBoardExport_Request
        )
        self.board_hardware_page.autoAssignRequested.connect(
            self._Resources_AutoAssign
        )
        self.board_hardware_page.assignmentChanged.connect(
            self._ResourceAssignment_Change
        )
        self.board_hardware_page.manualValidationRequested.connect(
            self._HardwareAssignments_Validate
        )
        self.board_hardware_page.i2cExternalPullupChanged.connect(
            self._I2cExternalPullup_Change
        )
        self.board_hardware_page.prepareRequested.connect(
            self._HardwarePrepare_Request
        )
        self.flight_configuration_page.strategyChanged.connect(
            self._Strategy_Change
        )
        self.flight_configuration_page.modeChanged.connect(self._Mode_Change)
        self.flight_configuration_page.modeParameterChanged.connect(
            self._ModeParameter_Change
        )
        self.flight_configuration_page.protocolProfileChanged.connect(
            self._ProtocolProfile_Change
        )
        self.flight_configuration_page.capabilitySourceChanged.connect(
            self._CapabilitySource_Change
        )
        self.flight_configuration_page.loggingChanged.connect(
            self._Logging_Change
        )
        self.flight_configuration_page.logDecoderExportRequested.connect(
            self._LogDecoderProfileExport_Request
        )
        self.build_page.detectionRequested.connect(self._Toolchains_Detect)
        self.build_page.actionRequested.connect(self._Build_Request)
        self.plugin_manager_dialog.panel.installRequested.connect(
            self._PluginInstall_Dialog
        )
        self.plugin_manager_dialog.panel.removeRequested.connect(
            self._PluginRemove_Request
        )

    def _Catalog_Load(self) -> None:
        self._component_views = self._service.ComponentViews_Get(
            self._translator.language
        )
        self.plugin_manager_dialog.Components_Set(self._component_views)

    def _ProjectDisplayState_Build(
        self,
        model: ProjectModel,
        configuration: ProjectConfigurationResult | None = None,
    ) -> _ProjectDisplayState:
        devices = tuple(
            component
            for component in self._component_views
            if component.component_type == ComponentType.DEVICE
        )
        selectable = tuple(
            component for component in self._component_views if component.selection_kind
        )
        protocol_profiles: dict[str, list[ProtocolProfileView]] = {}
        protocol_availability = ProtocolProfileAvailabilities_Get(
            model, self._service.catalog
        )
        for manifest in self._service.catalog.Type_Get("protocol"):
            contribution = manifest.protocol
            if contribution is None:
                continue
            for category, profiles in contribution.profiles.items():
                protocol_profiles.setdefault(category, []).extend(
                    ProtocolProfileView(
                        component_id=manifest.component_id,
                        profile_id=profile.profile_id,
                        display_name=profile.DisplayName_Get(
                            self._translator.language
                        ),
                        component_name=manifest.DisplayName_Get(
                            self._translator.language
                        ),
                        version=manifest.version,
                        available=protocol_availability[
                            (category, manifest.component_id, profile.profile_id)
                        ].available,
                        availability_reason=(
                            self._translator.Text_Get(
                                protocol_availability[
                                    (
                                        category,
                                        manifest.component_id,
                                        profile.profile_id,
                                    )
                                ].reason_code
                            )
                            if protocol_availability[
                                (category, manifest.component_id, profile.profile_id)
                            ].reason_code
                            else ""
                        ),
                    )
                    for profile in profiles
                )
        definitions = ProtocolLogDefinitions_Get(model, self._service.catalog)
        workspace_file = (
            self._project_root / f"{model.identity.name}.code-workspace"
            if self._project_root is not None
            else None
        )
        resource_resolution = (
            configuration.resource_resolution
            if configuration is not None
            else ResourceAssignments_Resolve(
                model, self._service.catalog, auto_assign=False
            )
        )
        firmware_output_directory, firmware_artifact_name = (
            self._FirmwareArtifact_Get(model)
        )
        return _ProjectDisplayState(
            model=model,
            devices=devices,
            device_instances=self._service.DeviceInstanceViews_Get(
                model, self._translator.language
            ),
            device_availability=self._service.DeviceSelectionAvailabilities_Get(
                model
            ),
            selectable_components=selectable,
            protocol_profiles={
                category: tuple(
                    sorted(
                        values,
                        key=lambda value: (
                            value.component_name.casefold(),
                            value.display_name.casefold(),
                            value.component_id,
                            value.profile_id,
                        ),
                    )
                )
                for category, values in protocol_profiles.items()
            },
            selected_protocol_profiles={
                category: (
                    (selection.component, selection.profile)
                    if selection is not None
                    else None
                )
                for category, selection in model.protocols.items()
            },
            platform_match=self._service.PlatformMatchView_Get(
                model, self._translator.language
            ),
            strategy_availability=(
                configuration.strategy_availability
                if configuration is not None
                else StrategyAvailabilities_Get(model, self._service.catalog)
            ),
            mode_availability=(
                configuration.mode_availability
                if configuration is not None
                else ModeOptionAvailabilities_Get(model, self._service.catalog)
            ),
            capability_usage=self._service.CapabilityUsageViews_Get(
                model, self._translator.language
            ),
            logging_streams=self._LoggingViews_Get(definitions, model),
            i2c_pullup_evidence=(
                self._service.I2cPullupEvidenceViews_Get(model)
            ),
            hardware_provider=self._service.HardwareProviderForMcu_Get(model.mcu),
            boards=self._service.BoardCompatibilities_Get(
                model, language=self._translator.language
            ),
            resources=self._service.ResourceRequirementViews_Get(
                model, self._translator.language
            ),
            resources_valid=resource_resolution.valid,
            generated_project=bool(
                workspace_file is not None and workspace_file.is_file()
            ),
            firmware_output_directory=firmware_output_directory,
            firmware_artifact_name=firmware_artifact_name,
            quality_results=(
                self._service.QualityResults_Get(self._project_root)
                if self._project_root is not None
                else ()
            ),
        )

    def _FirmwareArtifact_Get(
        self, model: ProjectModel
    ) -> tuple[Path | None, str]:
        if self._project_root is None:
            return None, ""
        candidates: list[tuple[float, int, Path, Path]] = []
        for priority, configuration in enumerate(("Debug", "Release")):
            directory = (
                self._project_root
                / "build"
                / "FCCG"
                / model.build.target_profile
                / configuration
            )
            if not directory.is_dir() or directory.is_symlink():
                continue
            for artifact in directory.iterdir():
                if (
                    artifact.is_file()
                    and not artifact.is_symlink()
                    and artifact.suffix.casefold()
                    in {".bin", ".hex", ".elf", ".map"}
                ):
                    try:
                        candidates.append(
                            (artifact.stat().st_mtime, priority, directory, artifact)
                        )
                    except OSError:
                        continue
        if not candidates:
            return None, ""
        _modified, _priority, directory, artifact = max(candidates)
        return directory, artifact.name

    def _Project_Refresh(self) -> None:
        self._Project_Display(self._ProjectDisplayState_Build(self._model))

    def _Project_Display(self, display: _ProjectDisplayState) -> None:
        self._ValidationIssue_Clear()
        self._displaying_model = True
        try:
            self.algorithm_parameters_page.Configuration_Set(
                AlgorithmParameterOwners_Get(display.model, self._service.catalog),
                display.model.algorithm_parameters,
                tuple(recommendation
                      for component_id in display.model.ComponentIds_Get()
                      for recommendation in self._service.catalog.Component_Get(component_id).metadata.get(
                          "sensor_recommendations", [])),
            )
            self.devices_page.Configuration_Set(
                display.devices,
                display.device_instances,
                display.device_availability,
            )
            self.flight_configuration_page.Configuration_Set(
                display.selectable_components,
                display.model.strategies,
                display.model.modes,
                mode_parameters=display.model.mode_parameters,
                strategy_availability=display.strategy_availability,
                mode_availability=display.mode_availability,
            )
            self.flight_configuration_page.Protocols_Set(
                display.protocol_profiles,
                display.selected_protocol_profiles,
            )
            self.flight_configuration_page.LoggingProtocolEnabled_Set(
                display.model.protocols.get("logging") is not None
            )
            self.flight_configuration_page.Capabilities_Set(
                display.capability_usage
            )
            self.flight_configuration_page.Streams_Set(
                display.logging_streams
            )
            self.build_page.Project_Set(
                " / ".join(
                    filter(
                        None,
                        (
                            self._service.Plugin_Get(
                                display.model.mcu
                            ).DisplayName_Get(self._translator.language),
                            (
                                self._service.Plugin_Get(
                                    display.model.board
                                ).DisplayName_Get(self._translator.language)
                                if display.model.board
                                else self._translator.Text_Get(
                                    "board.custom_hardware"
                                )
                            ),
                        ),
                    )
                ),
                self._translator.Text_Get("build.environment.vscode_eide"),
            )
            self.build_page.GeneratedProject_Set(
                display.generated_project
            )
            self.build_page.FirmwareArtifact_Set(
                str(display.firmware_output_directory or ""),
                display.firmware_artifact_name,
            )
            self.build_page.QualityResults_Set(display.quality_results)
            self._BoardPage_Refresh(display)
            self._HeaderProject_Refresh(display.model)
        finally:
            self._displaying_model = False

    def _BoardPage_Refresh(self, display: _ProjectDisplayState) -> None:
        model = display.model
        custom_selected = model.hardware.mode == "custom"
        self.board_hardware_page.Boards_Set(
            display.boards,
            model.board,
            custom_available=bool(display.hardware_provider),
            custom_selected=custom_selected,
            custom_ready=custom_selected and bool(model.hardware.snapshot_id),
            prepared=(
                self._project_root is not None
                and self._service.Project_HardwarePrepared_Is(
                    model, self._project_root
                )
            ),
            hardware_mode=model.hardware.mode,
            assignment_confirmed=bool(
                model.hardware.assignment_fingerprint
            ),
        )
        self.board_hardware_page.Platform_Set(display.platform_match)
        self.board_hardware_page.Resources_Set(
            display.resources,
            display.resources_valid,
            hardware_selected=model.hardware.mode != "unselected",
        )
        self.board_hardware_page.I2cPullupEvidence_Set(
            display.i2c_pullup_evidence
        )

    def _LoggingViews_Get(
        self,
        definitions,
        model: ProjectModel,
    ) -> tuple[LoggingStreamView, ...]:
        streams = {stream.record: stream for stream in model.logging_streams}
        views: list[LoggingStreamView] = []
        for definition in definitions:
            stream = streams[definition.record]
            availability = LogAvailability_Get(
                definition, model, self._service.catalog
            )
            reason = ""
            if not availability.available:
                reason = self._translator.Text_Get(
                    availability.reason_code,
                    missing=", ".join(availability.missing),
                )
            description = self._translator.Text_Get(
                "logging.record_metadata",
                id=definition.record_id,
                version=definition.version,
                size=definition.payload_size,
            )
            cadence_kind = definition.cadence.kind.value
            cadence_text = definition.cadence.DisplayName_Get(
                self._translator.language
            )
            if definition.cadence.kind == LogCadenceKind.PERIODIC:
                cadence_text = self._PeriodText_Get(stream.period_us)
            elif not cadence_text:
                cadence_text = self._translator.Text_Get(
                    f"logging.cadence.{cadence_kind}"
                )
            views.append(
                LoggingStreamView(
                    stream_id=stream.record,
                    name=definition.DisplayName_Get(self._translator.language),
                    enabled=stream.enabled,
                    decimation=stream.decimation,
                    cadence_kind=cadence_kind,
                    cadence_text=cadence_text,
                    cadence_source=definition.cadence.source,
                    description=description,
                    policy=stream.policy,
                    period_us=stream.period_us,
                    level=definition.level.value,
                    purpose=definition.purpose.value,
                    required=definition.level == LogPolicyLevel.REQUIRED,
                    available=availability.available,
                    availability_reason=reason,
                    record_id=definition.record_id,
                    version=definition.version,
                    payload_size=definition.payload_size,
                )
            )
        return tuple(views)

    @staticmethod
    def _PeriodText_Get(period_us: int) -> str:
        if period_us <= 0:
            return "—"
        if period_us % 1_000_000 == 0:
            return f"{period_us // 1_000_000} s"
        if period_us % 1_000 == 0:
            return f"{period_us // 1_000} ms"
        return f"{period_us} us"

    def _LogDecoderProfileExport_Request(self) -> None:
        if self._project_root is None:
            self._Error_Show(
                FccgError(
                    "error.log_decoder_profile_project_not_ready",
                    {},
                    "The project has not been generated yet",
                )
            )
            return
        readiness = self._service.ProjectReadiness_Get(
            self._model, self._project_root
        )
        if not readiness.ready:
            detail = "\n".join(
                (
                    *(f"missing: {path}" for path in readiness.missing),
                    *(f"stale: {path}" for path in readiness.stale),
                )
            )
            self._Error_Show(
                FccgError(
                    "error.log_decoder_profile_project_not_ready",
                    {},
                    detail or readiness.technical_detail,
                )
            )
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get("dialog.export_log_decoder_profile"),
            str(
                Path.home()
                / "Documents"
                / f"{self._model.identity.name}.ssdecoder"
            ),
            self._translator.Text_Get("filter.silverstar_decoder_profile"),
        )
        if not selected:
            return
        try:
            result = self._service.LogDecoderProfile_Export(
                self._model,
                self._project_root,
                Path(selected),
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self.status_label.setText(
            self._translator.Text_Get(
                "status.log_decoder_profile_exported",
                path=str(result.destination),
            )
        )

    @staticmethod
    def _LoggingSnapshot_Apply(
        model: ProjectModel,
        stream_views: tuple[LoggingStreamView, ...],
    ) -> None:
        if stream_views:
            model.logging_streams = [
                LogStreamConfig(
                    record=stream.stream_id,
                    enabled=stream.enabled,
                    policy=stream.policy,
                    decimation=stream.decimation,
                    period_us=stream.period_us,
                )
                for stream in stream_views
            ]

    def _LoggingState_Apply(self, model: ProjectModel) -> None:
        self._LoggingSnapshot_Apply(
            model, self.flight_configuration_page.Streams_Get()
        )

    def _ProjectModel_Sync(self) -> None:
        self._LoggingState_Apply(self._model)

    def _ProjectConfiguration_Change(
        self,
        mutator: Callable[[ProjectModel], None],
        *,
        status_key: str = "status.configuration_changed_simple",
        logging_snapshot: tuple[LoggingStreamView, ...] | None = None,
        logging_availability_changed: bool = False,
    ) -> ProjectConfigurationResult | None:
        if self._displaying_model:
            return None
        candidate = deepcopy(self._model)
        if logging_snapshot is None:
            self._LoggingState_Apply(candidate)
        else:
            self._LoggingSnapshot_Apply(candidate, logging_snapshot)
        previous_lifecycle = self._project_state
        previous_display: _ProjectDisplayState | None = None
        try:
            previous_display = self._ProjectDisplayState_Build(self._model)
            mutator(candidate)
            result = self._service.ProjectConfiguration_Reconcile(candidate)
            if logging_availability_changed:
                LoggingProfile_AvailabilityTransitionApply(
                    self._model, result.model, self._service.catalog
                )
                result = replace(
                    result,
                    edit_validation=Project_EditValidate(
                        result.model, self._service.catalog
                    ),
                )
            candidate_display = self._ProjectDisplayState_Build(
                result.model, result
            )
            self._project_state = ProjectLifecycleState.DIRTY
            self._Project_Display(candidate_display)
        except Exception as error:
            logging.exception("Configuration transaction failed")
            self._project_state = previous_lifecycle
            if previous_display is not None:
                try:
                    self._Project_Display(previous_display)
                except Exception:
                    logging.exception("Failed to restore the previous project view")
            self._Error_Show(error)
            return None
        self._model = result.model
        self._generation_plan = None
        if result.notices:
            self.status_label.setText(
                self._translator.Text_Get(result.notices[-1].code)
            )
        else:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.configuration_reconciled"
                    if result.cleared_assignments or result.pending_assignments
                    else status_key,
                    retained=result.retained_assignments,
                    cleared=result.cleared_assignments,
                    pending=result.pending_assignments,
                )
            )
        self._HeaderProject_Refresh(self._model)
        return result

    def _ConfigurationDirty_Set(self, *_unused: object) -> None:
        if self._displaying_model:
            return
        self._generation_plan = None
        self._project_state = ProjectLifecycleState.DIRTY
        self.status_label.setText(
            self._translator.Text_Get("status.configuration_changed_simple")
        )
        self._HeaderProject_Refresh()

    def _DeviceInstance_Change(self, instance_id: str, component_id: str) -> None:
        if self._displaying_model:
            return
        def change(candidate: ProjectModel) -> None:
            existing = candidate.DeviceInstance_Get(instance_id)
            if component_id:
                replacement = DeviceInstance(instance_id, component_id)
                if existing is None:
                    candidate.device_instances.append(replacement)
                else:
                    candidate.device_instances = [
                        replacement if item.instance_id == instance_id else item
                        for item in candidate.device_instances
                    ]
            else:
                candidate.device_instances = [
                    item
                    for item in candidate.device_instances
                    if item.instance_id != instance_id
                ]

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _DeviceInstance_Add(self, component_class: str) -> None:
        candidates = sorted(
            (
                component
                for component in self._component_views
                if component.component_type == ComponentType.DEVICE
                and component.component_class == component_class
                and not component.options.get("internal", False)
            ),
            key=lambda item: item.name,
        )
        if not candidates:
            return
        selected = [
            instance
            for instance in self._model.device_instances
            if self._service.Plugin_Get(instance.plugin).component_class
            == component_class
        ]
        class_max = max(
            (component.class_max or component.project_max for component in candidates),
            default=1,
        )
        if len(selected) >= class_max:
            return
        plugin_counts: dict[str, int] = {}
        for instance in selected:
            plugin_counts[instance.plugin] = plugin_counts.get(instance.plugin, 0) + 1
        available_candidates = [
            component
            for component in candidates
            if plugin_counts.get(component.component_id, 0)
            < (component.plugin_max or component.project_max)
        ]
        if not available_candidates:
            return
        selected_plugins = {instance.plugin for instance in selected}
        preferred = next(
            (component for component in available_candidates
             if component.component_id in selected_plugins),
            available_candidates[0],
        )
        instance_id = self._DeviceInstanceId_Next(component_class)
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.device_instances.append(
                DeviceInstance(instance_id, preferred.component_id)
            ),
            logging_availability_changed=True,
        )

    def _OtherDevice_Toggle(self, component_id: str, selected: bool) -> None:
        manifest = self._service.Plugin_Get(component_id)
        def change(candidate: ProjectModel) -> None:
            if selected:
                if any(
                    instance.plugin == component_id
                    for instance in candidate.device_instances
                ):
                    return
                previous_availability = ModeOptionAvailabilities_Get(
                    candidate, self._service.catalog
                )
                preferred_instance_id = str(
                    manifest.metadata.get("default_instance_id", "")
                )
                used_instance_ids = {
                    instance.instance_id
                    for instance in candidate.device_instances
                }
                instance_id = (
                    preferred_instance_id
                    if preferred_instance_id
                    and preferred_instance_id not in used_instance_ids
                    else self._DeviceInstanceId_Next(
                        manifest.component_class or "sensor",
                        model=candidate,
                    )
                )
                candidate.device_instances.append(
                    DeviceInstance(instance_id, component_id)
                )
                availability = ModeOptionAvailabilities_Get(
                    candidate, self._service.catalog
                )
                for base_component_id in candidate.base_components:
                    selection = self._service.Plugin_Get(
                        base_component_id
                    ).selection
                    if (
                        selection is None
                        or selection.kind.value != "mode"
                        or candidate.modes.get(selection.slot)
                    ):
                        continue
                    restored = [
                        option
                        for option in selection.default
                        if (
                            availability.get((selection.slot, option))
                            is not None
                            and availability[(selection.slot, option)].available
                            and not previous_availability.get(
                                (selection.slot, option),
                                availability[(selection.slot, option)],
                            ).available
                        )
                    ]
                    if restored:
                        candidate.modes[selection.slot] = restored
            else:
                candidate.device_instances = [
                    instance
                    for instance in candidate.device_instances
                    if instance.plugin != component_id
                ]

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _CapabilitySource_Change(self, capability: str, instance_id: str) -> None:
        def change(candidate: ProjectModel) -> None:
            resolution = CapabilityResolution_Resolve(
                candidate, self._service.catalog
            )
            choice = next(
                (
                    item
                    for item in resolution.choices
                    if item.capability == capability
                ),
                None,
            )
            default_instance_id = (
                choice.providers[0].instance_id
                if choice is not None and choice.providers
                else ""
            )
            if instance_id and instance_id != default_instance_id:
                candidate.capability_source_overrides[capability] = instance_id
            else:
                candidate.capability_source_overrides.pop(capability, None)

        self._ProjectConfiguration_Change(change)

    def _DeviceInstanceId_Next(
        self, component_class: str, *, model: ProjectModel | None = None
    ) -> str:
        prefix = "maintenance" if component_class == "console" else component_class
        prefix = prefix.replace(".", "_").replace("-", "_") or "device"
        selected_model = model or self._model
        used = {instance.instance_id for instance in selected_model.device_instances}
        for index in range(64):
            candidate = f"{prefix}{index}"
            if candidate not in used:
                return candidate
        raise FccgError(
            "error.device_instance_limit",
            {"device": component_class},
            f"No free instance id for device class {component_class}",
        )

    def _BoardSelection_Change(self, board_id: str) -> None:
        board = self._service.Plugin_Get(board_id)
        def change(candidate: ProjectModel) -> None:
            candidate.board = board_id
            candidate.hardware = HardwareConfiguration(
                mode="board_plugin",
                source_kind=(
                    board.board.source_kind if board.board else "third_party"
                ),
            )
            candidate.resource_assignments = {}

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _CustomHardware_Select(self) -> None:
        provider = self._service.HardwareProviderForMcu_Get(self._model.mcu)
        if not provider:
            self._Error_Show(self._translator.Text_Get("board.no_provider"))
            return
        def change(candidate: ProjectModel) -> None:
            candidate.board = ""
            candidate.hardware = HardwareConfiguration(
                mode="custom",
                source_kind="manual_import",
                provider=provider,
            )
            candidate.resource_assignments = {}

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )

    def _HardwarePrepare_Request(self) -> None:
        if self._model.hardware.mode == "custom":
            return
        self._ProjectModel_Sync()
        if self._project_root is None:
            self._Error_Show(
                self._translator.Text_Get("error.save_before_hardware_prepare")
            )
            return
        candidate = deepcopy(self._model)
        project_root = self._project_root

        def prepare_plan(context) -> tuple[ProjectModel, GenerationPlan]:
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE_PLAN",
                TaskProgressState.PLAN,
                total=2,
                code="status.hardware_preparing",
            )
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE_PLAN",
                TaskProgressState.BEGIN,
                current=1,
                total=2,
                subject="validate_configuration",
                code="status.hardware_validating",
            )
            configuration = self._service.ProjectConfiguration_Reconcile(candidate)
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE_PLAN",
                TaskProgressState.DONE,
                current=1,
                total=2,
                subject="validate_configuration",
                code="status.hardware_validating",
            )
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE_PLAN",
                TaskProgressState.BEGIN,
                current=2,
                total=2,
                subject="plan_files",
                code="status.hardware_preparing",
            )
            plan = self._service.GenerationPlan_Create(
                configuration.model, project_root
            )
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE_PLAN",
                TaskProgressState.DONE,
                current=2,
                total=2,
                subject="plan_files",
                code="status.hardware_preparing",
            )
            return configuration.model, plan

        self.status_label.setText(
            self._translator.Text_Get("status.hardware_preparing")
        )
        self.Task_Run(
            prepare_plan,
            self._HardwarePreparePlan_Complete,
            self._HardwarePreparePlan_Error,
        )

    def _HardwarePreparePlan_Complete(
        self, prepared: tuple[ProjectModel, GenerationPlan]
    ) -> None:
        candidate, plan = prepared
        if not self._GenerationPlan_ApplyAllowed(plan):
            return
        self._project_state = ProjectLifecycleState.MATERIALIZING

        def prepare(context) -> tuple[ProjectModel, ApplyResult]:
            context.ProgressEvent_Report(
                "HARDWARE_PREPARE",
                TaskProgressState.PLAN,
                total=7,
                code="status.hardware_preparing",
            )
            result = self._service.Project_HardwarePrepare(
                candidate,
                plan.project_root,
                confirm_dangerous=plan.dangerous,
                progress_callback=self._TaskProgressCallback_Get(
                    context,
                    "HARDWARE_PREPARE",
                    "status.hardware_preparing",
                ),
            )
            return candidate, result

        self.Task_Run(
            prepare,
            self._HardwarePrepareApply_Complete,
            self._Project_Materialization_Error,
        )

    def _HardwarePreparePlan_Error(self, error: object) -> None:
        self._Error_Show(error)

    def _HardwarePrepareApply_Complete(
        self, prepared: tuple[ProjectModel, ApplyResult]
    ) -> None:
        self._model, result = prepared
        self._HardwarePrepare_Complete(result)

    def _HardwarePrepare_Complete(self, result: ApplyResult) -> None:
        self._project_root = result.project_root
        self._project_state = ProjectLifecycleState.READY
        self._generation_plan = None
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get(
                "status.hardware_already_prepared"
                if result.files_added == 0 and result.files_modified == 0
                else "status.hardware_prepared"
            )
        )

    def _CubeMxImport_Request(self, directory: bool) -> None:
        warning = self._MessageBox_Exec(
            QMessageBox.Icon.Warning,
            self._translator.Text_Get("dialog.custom_hardware_risk_title"),
            self._translator.Text_Get("dialog.custom_hardware_risk_message"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if warning != QMessageBox.StandardButton.Ok:
            return
        if directory:
            selected = QFileDialog.getExistingDirectory(
                self, self._translator.Text_Get("dialog.import_cubemx_directory")
            )
        else:
            selected, _filter = QFileDialog.getOpenFileName(
                self,
                self._translator.Text_Get("dialog.import_cubemx_ioc"),
                "",
                self._translator.Text_Get("filter.cubemx_ioc"),
            )
        if not selected:
            return
        def import_project(context):
            context.ProgressEvent_Report(
                "CUBEMX_IMPORT",
                TaskProgressState.PLAN,
                total=6,
                code="status.cubemx_importing",
            )

            def progress(
                current: int, total: int, subject: str, done: bool
            ) -> None:
                context.ProgressEvent_Report(
                    "CUBEMX_IMPORT",
                    TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                    current=current,
                    total=total,
                    subject=subject,
                    code="status.cubemx_importing",
                )

            return self._service.CubeMxProject_Import(
                Path(selected),
                self._model,
                risk_acknowledged=True,
                progress_callback=progress,
            )

        self.Task_Run(import_project, self._CubeMxImport_Complete)

    def _CubeMxImport_Complete(self, result) -> None:
        def change(candidate: ProjectModel) -> None:
            candidate.board = ""
            candidate.hardware = result.hardware
            candidate.resource_assignments = {}

        self._ProjectConfiguration_Change(
            change, logging_availability_changed=True
        )
        self.status_label.setText(
            self._translator.Text_Get(
                "status.cubemx_imported", count=len(result.peripherals)
            )
        )

    def _CustomBoardExport_Request(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            self._translator.Text_Get("dialog.export_board_title"),
            self._translator.Text_Get("field.board_name"),
        )
        if not accepted or not name.strip():
            return
        default_id = "local.board." + "_".join(name.lower().split())
        component_id, accepted = QInputDialog.getText(
            self,
            self._translator.Text_Get("dialog.export_board_title"),
            self._translator.Text_Get("field.plugin_id"),
            text=default_id,
        )
        if not accepted:
            return
        default_path = Path.home() / "Documents" / f"{name}.ssplugin"
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get("dialog.export_board_title"),
            str(default_path),
            self._translator.Text_Get("filter.silverstar_plugin"),
        )
        if not selected:
            return
        try:
            path = self._service.CustomBoardPlugin_Export(
                self._model,
                Path(selected),
                component_id=component_id.strip(),
                name=name.strip(),
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self.status_label.setText(
            self._translator.Text_Get("status.board_exported", path=str(path))
        )

    def _Resources_AutoAssign(self, *, silent: bool = False) -> None:
        if self._model.hardware.mode != "custom":
            return
        result = self._ProjectConfiguration_Change(lambda _candidate: None)
        if not silent and result is not None:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.resources_assigned"
                    if result.resource_resolution.valid
                    else "status.resources_incomplete",
                    count=len(result.resource_resolution.errors),
                )
            )

    def _ResourceAssignment_Change(self, key: str, resource_id: str) -> None:
        if self._model.hardware.mode != "custom":
            return

        def change(candidate: ProjectModel) -> None:
            if resource_id:
                candidate.resource_assignments[key] = resource_id
            else:
                candidate.resource_assignments.pop(key, None)

        self._ProjectConfiguration_Change(change)

    def _HardwareAssignments_Validate(self) -> None:
        if self._model.hardware.mode != "custom":
            return
        result = ResourceAssignments_Resolve(
            self._model, self._service.catalog, auto_assign=False
        )
        if not result.valid:
            self._Project_Refresh()
            self._Error_Show(
                self._translator.Text_Get(
                    "error.manual_hardware_validation_failed",
                    count=len(result.errors),
                ),
                "\n".join(result.errors),
            )
            return

        def confirm(candidate: ProjectModel) -> None:
            candidate.hardware = replace(
                candidate.hardware,
                assignment_fingerprint=HardwareAssignmentFingerprint_Get(
                    candidate, self._service.catalog
                ),
            )

        applied = self._ProjectConfiguration_Change(
            confirm,
            status_key="status.manual_assignment_confirmed",
        )
        if applied is not None:
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.manual_assignment_confirmed"
                )
            )

    def _I2cExternalPullup_Change(
        self, resource_id: str, confirmed: bool
    ) -> None:
        if self._displaying_model or self._model.hardware.mode != "custom":
            return

        def change(candidate: ProjectModel) -> None:
            bindings = {
                key: dict(value)
                for key, value in (
                    candidate.hardware.i2c_external_pullup_confirmations.items()
                )
            }
            if (
                confirmed
                and candidate.hardware.source_digest
                and candidate.hardware.snapshot_id
            ):
                bindings[resource_id] = {
                    "source_digest": candidate.hardware.source_digest,
                    "snapshot_id": candidate.hardware.snapshot_id,
                }
            else:
                bindings.pop(resource_id, None)
            candidate.hardware = replace(
                candidate.hardware,
                i2c_external_pullup_confirmations=bindings,
            )

        self._ProjectConfiguration_Change(change)

    def _Strategy_Change(self, slot: str, component_id: object) -> None:
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.strategies.__setitem__(
                slot, str(component_id) if component_id is not None else None
            ),
            logging_availability_changed=True,
        )

    def _Mode_Change(self, slot: str, values: object) -> None:
        self._pending_mode_changes[slot] = (
            list(values) if isinstance(values, list) else []
        )
        if self._mode_refresh_scheduled:
            return
        self._mode_refresh_scheduled = True
        QTimer.singleShot(0, self._ModeChanges_Apply)

    def _AlgorithmParameter_Change(self, component: str, parameter: str, value: object) -> None:
        definition = next(p for p in self._service.Plugin_Get(component).algorithm_parameters
                          if p.parameter_id == parameter)
        if definition.lifecycle != "active":
            return
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.algorithm_parameters[component].__setitem__(parameter, value)
        )

    def _SharedAlgorithmParameter_Change(self, shared_key: str, value: object) -> None:
        def update(candidate) -> None:
            for owner in AlgorithmParameterOwners_Get(candidate, self._service.catalog):
                for parameter in owner.algorithm_parameters:
                    if parameter.shared_key == shared_key:
                        candidate.algorithm_parameters[owner.component_id][parameter.parameter_id] = value
        self._ProjectConfiguration_Change(update)

    def _SharedAlgorithmDefaults_Reset(self, shared_key: str) -> None:
        def reset(candidate) -> None:
            for owner in AlgorithmParameterOwners_Get(candidate, self._service.catalog):
                for parameter in owner.algorithm_parameters:
                    if parameter.shared_key == shared_key:
                        candidate.algorithm_parameters[owner.component_id][parameter.parameter_id] = parameter.default
        self._ProjectConfiguration_Change(reset)

    def _AlgorithmDefaults_Reset(self, component: str) -> None:
        defaults = {p.parameter_id: p.default
                      for p in self._service.Plugin_Get(component).algorithm_parameters
                      if not p.shared_key and p.lifecycle == "active"}
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.algorithm_parameters[component].update(defaults)
        )

    def _ModeParameter_Change(
        self,
        slot: str,
        option: str,
        parameter_id: str,
        value: object,
    ) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        self._pending_mode_parameter_changes[(slot, option, parameter_id)] = value
        if self._mode_refresh_scheduled:
            return
        self._mode_refresh_scheduled = True
        QTimer.singleShot(0, self._ModeChanges_Apply)

    def _ModeChanges_Apply(self) -> None:
        changes = self._pending_mode_changes
        parameter_changes = self._pending_mode_parameter_changes
        self._pending_mode_changes = {}
        self._pending_mode_parameter_changes = {}
        self._mode_refresh_scheduled = False
        if not changes and not parameter_changes:
            return

        def change(candidate: ProjectModel) -> None:
            for slot, values in changes.items():
                candidate.modes[slot] = list(values)
            for (slot, option, parameter_id), value in parameter_changes.items():
                candidate.mode_parameters.setdefault(slot, {}).setdefault(
                    option, {}
                )[parameter_id] = value

        self._ProjectConfiguration_Change(
            change,
            logging_availability_changed=bool(changes),
        )

    def _ProtocolProfile_Change(
        self, category: str, selection: object
    ) -> None:
        if selection is None:
            self._ProjectConfiguration_Change(
                lambda candidate: candidate.protocols.__setitem__(
                    category, None
                ),
                logging_availability_changed=category == "logging",
            )
            return
        if not isinstance(selection, tuple) or len(selection) != 2:
            return
        component_id, profile_id = (str(value) for value in selection)
        if not component_id or not profile_id:
            return
        manifest = self._service.Plugin_Get(component_id)
        self._ProjectConfiguration_Change(
            lambda candidate: candidate.protocols.__setitem__(
                category,
                ProtocolSelection(
                    component=manifest.component_id,
                    version=manifest.version,
                    profile=profile_id,
                    manifest_sha256=manifest.ManifestSha256_Get(),
                ),
            ),
            logging_availability_changed=category == "logging",
        )

    def _Logging_Change(self) -> None:
        if self._displaying_model:
            return
        self._pending_logging_streams = (
            self.flight_configuration_page.Streams_Get()
        )
        if self._logging_refresh_scheduled:
            return
        self._logging_refresh_scheduled = True
        QTimer.singleShot(0, self._LoggingChanges_Apply)

    def _LoggingChanges_Apply(self) -> None:
        snapshot = self._pending_logging_streams
        self._pending_logging_streams = None
        self._logging_refresh_scheduled = False
        if snapshot is None:
            return
        self._ProjectConfiguration_Change(
            lambda _candidate: None,
            logging_snapshot=snapshot,
        )

    def _GenerateOrApply_Request(self) -> None:
        self._ProjectModel_Sync()
        if self._project_root is None:
            self._Error_Show(self._translator.Text_Get("error.output_required"))
            return
        try:
            plan = self._service.GenerationPlan_Create(
                self._model, self._project_root
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self._generation_plan = plan
        if not plan.valid:
            validation_details = "\n".join(
                f"[{issue.code}] {issue.message}" for issue in plan.validation.issues
            )
            conflicts = "\n".join(
                f"{operation.target}: {operation.detail}"
                for operation in plan.operations
                if operation.operation == "CONFLICT"
            )
            localized = "\n".join(
                self._translator.Text_Get(
                    "validation.issue_summary", code=issue.code
                )
                for issue in plan.validation.issues
            )
            if conflicts:
                localized = "\n".join(
                    filter(
                        None,
                        (
                            localized,
                            self._translator.Text_Get("validation.file_conflict"),
                        ),
                    )
                )
            self._Error_Show(
                localized or self._translator.Text_Get("error.plan_invalid"),
                "\n".join(filter(None, (validation_details, conflicts))),
            )
            return
        confirmed = not plan.dangerous or self._DangerousPlan_Confirm(plan)
        if not confirmed:
            return

        def generate(context) -> ApplyResult:
            context.ProgressEvent_Report(
                "GENERATE_CODE",
                TaskProgressState.PLAN,
                total=7,
                code="status.generation_running",
            )
            return self._service.GenerationPlan_Apply(
                self._model,
                plan,
                confirm_dangerous=plan.dangerous,
                progress_callback=self._TaskProgressCallback_Get(
                    context,
                    "GENERATE_CODE",
                    "status.generation_running",
                ),
            )

        self.status_label.setText(
            self._translator.Text_Get("status.generation_running")
        )
        self.Task_Run(generate, self._Generation_Complete)

    def _DangerousPlan_Confirm(self, plan: GenerationPlan) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(
            self._translator.Text_Get("dialog.dangerous_changes_title")
        )
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        eide_modified = any(
            operation.target == ".eide/eide.yml" and operation.dangerous
            for operation in plan.operations
        )
        notice = QLabel(
            self._translator.Text_Get(
                "dialog.eide_manual_modified"
                if eide_modified
                else "dialog.dangerous_changes_message"
            )
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        table = EngineeringTable(
            ("column.operation", "column.target", "column.detail")
        )
        table.Language_Apply(self._translator)
        table.Rows_Set(
            (operation.operation, operation.target, operation.detail)
            for operation in plan.operations
            if operation.dangerous or operation.operation == "CONFLICT"
        )
        layout.addWidget(table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self._translator.Text_Get("action.continue")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self._translator.Text_Get("action.cancel")
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _GenerationPlan_ApplyAllowed(self, plan: GenerationPlan) -> bool:
        if not plan.valid:
            self._ValidationIssue_Navigate(plan.validation.issues)
            validation_details = "\n".join(
                f"[{issue.code}] {issue.message}"
                for issue in plan.validation.issues
            )
            conflicts = "\n".join(
                f"{operation.target}: {operation.detail}"
                for operation in plan.operations
                if operation.operation == "CONFLICT"
            )
            localized = "\n".join(
                self._translator.Text_Get(
                    "validation.issue_summary", code=issue.code
                )
                for issue in plan.validation.issues
            )
            if conflicts:
                localized = "\n".join(
                    filter(
                        None,
                        (
                            localized,
                            self._translator.Text_Get(
                                "validation.file_conflict"
                            ),
                        ),
                    )
                )
            self._Error_Show(
                localized or self._translator.Text_Get("error.plan_invalid"),
                "\n".join(filter(None, (validation_details, conflicts))),
            )
            return False
        return not plan.dangerous or self._DangerousPlan_Confirm(plan)

    def _ValidationIssue_Clear(self) -> None:
        widget = self._validation_focus_widget
        if widget is None:
            return
        widget.setProperty("validationIssue", False)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
        self._validation_focus_widget = None

    def _ValidationIssue_Navigate(
        self, issues: tuple[ValidationIssue, ...]
    ) -> None:
        issue = next((item for item in issues if item.level == "error"), None)
        if issue is None:
            return
        self._ValidationIssue_Clear()
        code = issue.code
        page_index = 4
        target: QWidget = self.build_page.tool_status_group
        if code.startswith(("hardware", "board", "resource", "platform")) or code in {
            "protocol_transport",
            "protocol_transport_ambiguous",
            "hal_cmsis_source_policy",
        }:
            page_index = 3
            target = (
                self.board_hardware_page.resource_table
                if code.startswith("resource") or code.startswith("protocol_transport")
                else self.board_hardware_page.board_combo
            )
        elif code.startswith(
            ("strategy", "mode", "capability", "logging", "protocol")
        ):
            page_index = 1
            if code.startswith("strategy"):
                target = next(
                    iter(self.flight_configuration_page.strategy_combos.values()),
                    self.flight_configuration_page,
                )
            elif code.startswith("mode"):
                target = next(
                    (
                        check
                        for checks in self.flight_configuration_page.mode_checks.values()
                        for check in checks
                    ),
                    self.flight_configuration_page,
                )
            elif code.startswith("logging"):
                target = self.flight_configuration_page.logging_table
            elif code.startswith("protocol"):
                target = next(
                    iter(self.flight_configuration_page.protocol_combos.values()),
                    self.flight_configuration_page,
                )
            else:
                target = self.flight_configuration_page.capability_table
        elif code == "algorithm_parameters":
            page_index = 2
            target = self.algorithm_parameters_page
        elif code.startswith("mcu"):
            page_index = 3
            target = self.board_hardware_page.board_combo
        elif code.startswith("device"):
            page_index = 0
            target = next(
                iter(self.devices_page.device_combos.values()),
                self.devices_page,
            )
        self.navigation_list.setCurrentRow(page_index)
        target.setProperty("validationIssue", True)
        target.style().unpolish(target)
        target.style().polish(target)
        target.update()
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        self._validation_focus_widget = target

    def _Generation_Complete(self, result: ApplyResult) -> None:
        self._project_root = result.project_root
        self._generation_plan = None
        self.status_label.setText(
            self._translator.Text_Get(
                "status.generation_complete",
                added=result.files_added,
                modified=result.files_modified,
            )
        )
        self._Project_Refresh()

    def _DefaultProjectRoot_Select(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, self._translator.Text_Get("action.default_project_root"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
        )
        if selected:
            try:
                self._path_preferences.DefaultProjectRoot_Set(Path(selected))
            except (OSError, ValueError) as error:
                self._Error_Show(error)

    def _NewProject_Show(self) -> None:
        wizard = NewProjectWizard(self._translator, self,
                                  default_root=self._path_preferences.DefaultProjectRoot_EffectiveGet())
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        values = wizard.WizardData_Get()
        self._model = self._service.ProjectDraft_Create(values["name"])
        self._project_root = Path(values["output_directory"]).resolve(strict=False)
        self._generation_plan = None
        self._project_state = ProjectLifecycleState.DRAFT
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get("status.project_draft")
        )

    def _Project_OpenDialog(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.open_project"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
            self._translator.Text_Get("filter.silverstar_project"),
        )
        if selected:
            self._Project_Open(Path(selected))

    def _Project_Open(self, path: Path) -> None:
        try:
            loaded = self._service.Project_Open(path)
            configuration = self._service.ProjectConfiguration_Reconcile(loaded)
            reconciled = configuration.model
            changed_during_open = (
                loaded.Dictionary_Get() != reconciled.Dictionary_Get()
            )
            self._model = reconciled
            self._project_root = (
                path.resolve() if path.is_dir() else path.resolve().parent
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self._generation_plan = None
        readiness = self._service.ProjectReadiness_Get(
            self._model, self._project_root
        )
        self._project_state = (
            ProjectLifecycleState.DIRTY
            if changed_during_open
            else readiness.state
        )
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get(
                "status.project_opened", name=self._model.identity.name
            )
        )

    def _Project_Save(self) -> None:
        self._ProjectModel_Sync()
        if self._project_root is None:
            self._Project_SaveAs()
            return
        try:
            plan = self._service.GenerationPlan_Create(
                self._model, self._project_root
            )
        except Exception as error:
            self._Error_Show(error)
            return
        if not self._GenerationPlan_ApplyAllowed(plan):
            return
        self._project_state = ProjectLifecycleState.MATERIALIZING

        def save(context) -> ApplyResult:
            context.ProgressEvent_Report(
                "SAVE_PROJECT",
                TaskProgressState.PLAN,
                total=7,
                code="status.project_validating",
            )
            return self._service.Project_Save(
                self._model,
                self._project_root,
                confirm_dangerous=plan.dangerous,
                progress_callback=self._TaskProgressCallback_Get(
                    context,
                    "SAVE_PROJECT",
                    "status.project_materializing",
                ),
            )

        self.Task_Run(
            save,
            self._Project_Save_Complete,
            self._Project_Materialization_Error,
        )

    def _Project_Save_Complete(self, result: ApplyResult) -> None:
        self._project_root = result.project_root
        self._project_state = ProjectLifecycleState.READY
        self._generation_plan = None
        self.status_label.setText(
            self._translator.Text_Get("status.project_saved_ready")
        )
        self._Project_Refresh()

    def _Project_Materialization_Error(self, error: object) -> None:
        self._project_state = ProjectLifecycleState.ERROR
        self._Error_Show(error)

    def _Project_SaveAs(self) -> None:
        self._ProjectModel_Sync()
        dialog = QFileDialog(
            self,
            self._translator.Text_Get("dialog.save_project_as"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
        )
        # Keep the root visible while prefilling the directory name, even if it exists.
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.selectFile(self._model.identity.name)
        selected_paths = dialog.selectedFiles() if dialog.exec() == QDialog.DialogCode.Accepted else []
        dialog.deleteLater()
        if not selected_paths:
            return
        selected = selected_paths[0]
        dangerous = False
        if self._project_root is not None and (
            self._project_root / "SilverStar.ssproject"
        ).is_file():
            try:
                source_plan = self._service.GenerationPlan_Create(
                    self._model, self._project_root
                )
            except Exception as error:
                self._Error_Show(error)
                return
            if not self._GenerationPlan_ApplyAllowed(source_plan):
                return
            dangerous = source_plan.dangerous
        self._project_state = ProjectLifecycleState.MATERIALIZING

        def save_as(context) -> Path:
            context.ProgressEvent_Report(
                "SAVE_PROJECT_AS",
                TaskProgressState.PLAN,
                total=3,
                code="status.project_copying",
            )
            return self._service.Project_SaveAs(
                self._model,
                self._project_root,
                Path(selected),
                confirm_dangerous=dangerous,
                progress_callback=self._TaskProgressCallback_Get(
                    context,
                    "SAVE_PROJECT_AS",
                    "status.project_copying",
                ),
            )

        self.Task_Run(
            save_as,
            self._Project_SaveAs_Complete,
            self._Project_Materialization_Error,
        )

    def _Project_SaveAs_Complete(self, destination: Path) -> None:
        self._project_root = destination
        self._project_state = ProjectLifecycleState.READY
        self._generation_plan = None
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get(
                "status.project_saved_as", path=str(destination)
            )
        )
        if self._pending_build_action is not None:
            pending = self._pending_build_action
            self._pending_build_action = None
            QTimer.singleShot(0, lambda: self._Build_Request(pending))

    def _PluginManager_Show(self) -> None:
        self.plugin_manager_dialog.Components_Set(self._component_views)
        self.plugin_manager_dialog.show()
        self.plugin_manager_dialog.raise_()
        self.plugin_manager_dialog.activateWindow()

    def _Plugins_Refresh(self) -> None:
        try:
            self._service.Plugins_Refresh()
            self._Catalog_Load()
            self._Project_Refresh()
        except Exception as error:
            self._Error_Show(error)
            return
        self.status_label.setText(
            self._translator.Text_Get("status.plugins_refreshed")
        )

    def _PluginInstall_Dialog(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.install_plugin"),
            str(self._service.workspace_root),
            self._translator.Text_Get("filter.silverstar_plugin"),
        )
        if not selected:
            return
        self.Task_Run(
            lambda context: self._PluginInstall_Task(
                context, Path(selected)
            ),
            self._PluginChange_Complete,
        )

    def _PluginInstall_Task(self, context, archive: Path):
        context.ProgressEvent_Report(
            "PLUGIN_INSTALL",
            TaskProgressState.PLAN,
            total=4,
        )

        def progress(
            current: int, total: int, subject: str, done: bool
        ) -> None:
            context.ProgressEvent_Report(
                "PLUGIN_INSTALL",
                TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                current=current,
                total=total,
                subject=subject,
            )

        return self._service.Plugin_Install(archive, progress)

    def _PluginRemove_Request(self, component_id: str) -> None:
        manifest = self._service.Plugin_Get(component_id)
        if manifest.source != "installed":
            self._Error_Show(
                self._translator.Text_Get(
                    "error.plugin_builtin_readonly", name=manifest.name
                )
            )
            return
        answer = self._MessageBox_Exec(
            QMessageBox.Icon.Question,
            self._translator.Text_Get("dialog.plugin_remove_title"),
            self._translator.Text_Get(
                "dialog.plugin_remove_message",
                name=manifest.name,
                id=manifest.component_id,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            def remove(context):
                context.ProgressEvent_Report(
                    "PLUGIN_REMOVE",
                    TaskProgressState.PLAN,
                    total=4,
                )

                def progress(
                    current: int, total: int, subject: str, done: bool
                ) -> None:
                    context.ProgressEvent_Report(
                        "PLUGIN_REMOVE",
                        TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                        current=current,
                        total=total,
                        subject=subject,
                    )

                return self._service.Plugin_Remove(component_id, progress)

            self.Task_Run(remove, self._PluginChange_Complete)

    def _PluginChange_Complete(self, manifest) -> None:
        self._Catalog_Load()
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get("status.plugin_changed", name=manifest.name)
        )

    def _Toolchains_Detect(self) -> None:
        def detect(context):
            context.ProgressEvent_Report(
                "TOOLCHAIN_DETECT",
                TaskProgressState.PLAN,
                total=3,
            )

            def progress(current: int, total: int, subject: str, done: bool) -> None:
                context.ProgressEvent_Report(
                    "TOOLCHAIN_DETECT",
                    TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                    current=current,
                    total=total,
                    subject=subject,
                )

            return self._service.Toolchains_Detect(
                self._model.build.tool_paths,
                progress,
            )

        self.Task_Run(detect, self._Toolchains_Show)

    def _SourcePackageExport_Request(self) -> None:
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get("dialog.export_source_package"),
            str(self._service.workspace_root / "SilverStar_FCCG-source.zip"),
            self._translator.Text_Get("filter.zip_archive"),
        )
        if not selected:
            return
        destination = Path(selected).resolve(strict=False)
        def export(context):
            planned = False

            def progress(current: int, total: int, subject: str, done: bool) -> None:
                nonlocal planned
                if not planned:
                    context.ProgressEvent_Report(
                        "SOURCE_EXPORT",
                        TaskProgressState.PLAN,
                        total=total,
                        code="status.exporting_source_package",
                    )
                    planned = True
                context.ProgressEvent_Report(
                    "SOURCE_EXPORT",
                    TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                    current=current,
                    total=total,
                    subject=subject,
                    code="status.exporting_source_package",
                )

            return self._service.SourcePackage_Export(destination, progress)

        self.Task_Run(export, self._SourcePackageExport_Complete)

    def _SourcePackageExport_Complete(self, result) -> None:
        self.status_label.setText(
            self._translator.Text_Get(
                "status.source_package_exported",
                path=str(result.destination),
                count=result.file_count,
            )
        )

    def _Toolchains_Show(self, results) -> None:
        display_names = {
            tool.tool_id: self._translator.Text_Get(f"tool.{tool.tool_id}")
            for tool in DefaultTools_Get()
        }
        views = tuple(
            ToolchainToolView(
                tool_id=result.tool_id,
                display_name=display_names.get(result.tool_id, result.tool_id),
                command=result.command,
                path=result.path,
                version=result.version,
                status=(
                    "found"
                    if result.available and result.compatible
                    else "invalid" if result.available else "not_found"
                ),
                target=result.target,
            )
            for result in results
        )
        self.build_page.Tools_Set(views)

        if self._toolchain_dialog is not None:
            self._toolchain_dialog.close()
        dialog = QDialog(self)
        dialog.setWindowTitle(
            self._translator.Text_Get("dialog.toolchain_detection_results")
        )
        dialog.setMinimumWidth(760)
        layout = QVBoxLayout(dialog)
        for result, view in zip(results, views, strict=True):
            row = QWidget(dialog)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 3, 0, 3)
            name = QLabel(view.display_name)
            name.setMinimumWidth(170)
            detail = QLabel(
                "\n".join(
                    value
                    for value in (
                        view.path or view.command,
                        view.version,
                        result.target,
                    )
                    if value
                )
            )
            detail.setWordWrap(True)
            status = QLabel(
                self._translator.Text_Get(f"tool.status.{view.status}")
            )
            status.setObjectName("statusPill")
            status.setProperty(
                "statusLevel",
                "success" if view.status == "found" else "error",
            )
            choose = QPushButton(
                self._translator.Text_Get("action.select_installed_location")
            )
            choose.clicked.connect(
                lambda _checked=False, tool_id=view.tool_id: self._ToolchainBrowse(
                    tool_id
                )
            )
            row_layout.addWidget(name)
            row_layout.addWidget(detail, 1)
            row_layout.addWidget(status)
            row_layout.addWidget(choose)
            layout.addWidget(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(
            lambda _object=None: setattr(self, "_toolchain_dialog", None)
        )
        self._toolchain_dialog = dialog
        dialog.show()

    def _ToolchainBrowse(self, tool_id: str) -> bool:
        tool_name = self._translator.Text_Get(f"tool.{tool_id}")
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.select_tool", tool=tool_name),
        )
        if selected:
            def change(candidate: ProjectModel) -> None:
                paths = dict(candidate.build.tool_paths)
                paths[tool_id] = selected
                if tool_id == "compiler":
                    paths.pop("objcopy", None)
                    paths.pop("size", None)
                    paths.update(ArmGnuSubtoolPaths_Derive(selected))
                candidate.build = replace(candidate.build, tool_paths=paths)

            self._ProjectConfiguration_Change(change)
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.tool_path_selected", tool=tool_name
                )
            )
            return True
        return False

    def _Build_Request(self, action_text: str) -> None:
        self._ProjectModel_Sync()
        if action_text == "generate_apply":
            self._Project_Save()
            return
        if action_text == "tool_install_guide":
            self._ToolInstallGuide_Show()
            return
        if action_text in {"open_vscode", "open_folder"}:
            self._GeneratedProject_Open(action_text)
            return
        if action_text == "open_firmware_output":
            self._FirmwareOutput_Open()
            return
        if self._project_root is None:
            self._pending_build_action = action_text
            self.status_label.setText(
                self._translator.Text_Get("error.save_before_build")
            )
            self._Project_SaveAs()
            return
        actions = {
            "build": BuildAction.BUILD,
            "clean": BuildAction.CLEAN,
            "clean_all": BuildAction.CLEAN_ALL,
            "host_tests": BuildAction.HOST_TESTS,
            "architecture_check": BuildAction.ARCHITECTURE_CHECK,
            "power10_check": BuildAction.POWER10_CHECK,
            "static_analysis": BuildAction.STATIC_ANALYSIS,
            "artifact_check": BuildAction.ARTIFACT_CHECK,
        }
        action = actions.get(action_text)
        if action is None:
            return
        project_root = self._project_root
        readiness = self._service.ProjectReadiness_Get(self._model, project_root)
        materialization_required = not readiness.ready
        plan: GenerationPlan | None = None
        if materialization_required:
            try:
                plan = self._service.GenerationPlan_Create(
                    self._model, project_root
                )
            except Exception as error:
                self._Error_Show(error)
                return
            if not self._GenerationPlan_ApplyAllowed(plan):
                return
        self._project_state = ProjectLifecycleState.BUILDING
        self._active_build_action = action
        self._build_started_at = time.perf_counter()
        self.build_page.BuildLog_Set("")
        self.build_page.BuildDetailLog_Set("")

        def build(context) -> BuildResult:
            if materialization_required:
                assert plan is not None
                context.Progress_Report(0.04, "status.project_materializing")
                self._service.Project_EnsureBuildable(
                    self._model,
                    project_root,
                    confirm_dangerous=plan.dangerous,
                )
            context.Progress_Report(
                0.10 if materialization_required else 0.0,
                (
                    "status.build_planning"
                    if action == BuildAction.BUILD
                    else f"status.task.{action.value}"
                ),
            )

            def progress_report(progress: BuildProgress) -> None:
                if progress.stage == "PLAN":
                    if action == BuildAction.BUILD:
                        context.Line_Report(
                            "FCCG_UI_PLAN|"
                            f"{progress.total_steps}|{progress.stage_total}"
                        )
                    else:
                        context.Line_Report(f"FCCG_UI_TASK|{action.value}")
                    return
                if progress.stage == "COMPLETE":
                    fraction = 1.0
                elif progress.total_steps:
                    fraction = progress.completed_steps / progress.total_steps
                else:
                    fraction = 0.0
                context.Progress_Report(
                    (
                        0.10 + (0.89 * max(0.0, min(1.0, fraction)))
                        if materialization_required
                        else max(0.0, min(0.99, fraction))
                    ),
                    "status.build_running",
                )
                context.Line_Report(
                    "FCCG_UI_PROGRESS|"
                    f"{progress.stage}|{progress.stage_completed}|"
                    f"{progress.stage_total}|{progress.subject}"
                )

            result = self._service.Build_Run(
                self._model,
                project_root,
                action,
                context.token if hasattr(context, "token") else context,
                confirm_dangerous=bool(plan and plan.dangerous),
                line_callback=context.Line_Report,
                progress_callback=progress_report,
                ensure_buildable=False,
            )
            if result.succeeded:
                context.Progress_Report(1.0, "status.build_running")
            return result

        self.Task_Run(
            build,
            self._Build_Complete,
            self._Build_Error,
            indeterminate=False,
            line_callback=self._BuildLine_Append,
        )

    def _FirmwareOutput_Open(self) -> None:
        directory, artifact_name = self._FirmwareArtifact_Get(self._model)
        if directory is None or not artifact_name:
            self._Error_Show(
                self._translator.Text_Get("error.firmware_artifact_missing")
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self._Error_Show(
                self._translator.Text_Get(
                    "error.open_firmware_output_failed", path=str(directory)
                )
            )
            return
        self.status_label.setText(
            self._translator.Text_Get(
                "status.firmware_output_opened", path=str(directory)
            )
        )

    def _GeneratedProject_Open(self, action_text: str) -> None:
        if self._project_root is None:
            self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
            return
        target = (
            self._project_root / f"{self._model.identity.name}.code-workspace"
            if action_text == "open_vscode"
            else self._project_root
        )
        if not target.exists():
            self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
            return
        if action_text == "open_vscode":
            launch_result = self._VsCodeWorkspace_Launch(target)
            launched = launch_result.succeeded
        else:
            launched = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        if not launched:
            if action_text == "open_vscode":
                logging.error(
                    "VS Code workspace launch failed: %s\n%s",
                    target,
                    launch_result.reason,
                )
                self._MessageBox_Exec(
                    QMessageBox.Icon.Critical,
                    self._translator.Text_Get("dialog.vscode_launch_failed"),
                    self._translator.Text_Get(
                        "error.vscode_launch_failed",
                        path=str(target.resolve()),
                    ),
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )
            else:
                self._Error_Show(
                    self._translator.Text_Get(
                        "error.open_generated_project",
                        path=str(target.resolve()),
                    )
                )
            return
        status_key = (
            "status.vscode_launch_requested"
            if action_text == "open_vscode"
            else "status.generated_project_opened"
        )
        self.status_label.setText(
            self._translator.Text_Get(status_key, path=str(target))
        )

    def _ToolInstallGuide_Show(self) -> None:
        if self._install_guide_dialog is not None:
            self._install_guide_dialog.raise_()
            self._install_guide_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(
            self._translator.Text_Get("dialog.tool_install_guide")
        )
        dialog.setMinimumWidth(620)
        layout = QVBoxLayout(dialog)
        introduction = QLabel(
            self._translator.Text_Get("tool.install_guide.introduction")
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        for title_key, purpose_key, label, url in (
            (
                "tool.compiler",
                "tool.install_guide.arm_purpose",
                "https://learn.arm.com/install-guides/gcc/arm-gnu/",
                "https://learn.arm.com/install-guides/gcc/arm-gnu/",
            ),
            (
                "tool.install_guide.msys2_title",
                "tool.install_guide.msys2_purpose",
                "https://www.msys2.org/",
                "https://www.msys2.org/",
            ),
        ):
            title = QLabel(self._translator.Text_Get(title_key))
            title.setObjectName("sectionLabel")
            layout.addWidget(title)
            purpose = QLabel(self._translator.Text_Get(purpose_key))
            purpose.setWordWrap(True)
            layout.addWidget(purpose)
            link = QLabel(f'<a href="{url}">{label}</a>')
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link.setOpenExternalLinks(False)
            link.linkActivated.connect(self._OfficialLink_Open)
            layout.addWidget(link)
        closing = QLabel(self._translator.Text_Get("tool.install_guide.closing"))
        closing.setWordWrap(True)
        layout.addWidget(closing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(
            lambda _object=None: setattr(self, "_install_guide_dialog", None)
        )
        self._install_guide_dialog = dialog
        dialog.show()

    def _OfficialLink_Open(self, url: str) -> None:
        if not QDesktopServices.openUrl(QUrl(url)):
            self._Error_Show(
                self._translator.Text_Get("error.open_official_link", url=url)
            )

    def _VsCodeWorkspace_Validate(self, workspace_file: Path) -> str:
        if not workspace_file.is_file():
            return self._translator.Text_Get("error.vscode_workspace_missing")
        try:
            workspace = json.loads(workspace_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return self._translator.Text_Get(
                "error.vscode_workspace_json", reason=str(error)
            )
        folders = workspace.get("folders") if isinstance(workspace, dict) else None
        if not isinstance(folders, list) or not folders or not isinstance(
            folders[0], dict
        ):
            return self._translator.Text_Get("error.vscode_workspace_folder")
        folder_path = folders[0].get("path")
        if not isinstance(folder_path, str) or not folder_path:
            return self._translator.Text_Get("error.vscode_workspace_folder")
        resolved_folder = (
            workspace_file.parent / folder_path
        ).resolve(strict=False)
        if resolved_folder != workspace_file.parent.resolve(strict=False):
            return self._translator.Text_Get("error.vscode_workspace_folder")
        if not (workspace_file.parent / ".eide" / "eide.yml").is_file():
            return self._translator.Text_Get("error.vscode_eide_missing")
        return ""

    def _VsCodeWorkspace_Launch(
        self, workspace_file: Path
    ) -> _WorkspaceLaunchResult:
        validation_error = self._VsCodeWorkspace_Validate(workspace_file)
        if validation_error:
            return _WorkspaceLaunchResult(False, validation_error)
        candidates: list[Path] = []
        for command in ("code.cmd", "code.exe", "code"):
            resolved = shutil.which(command)
            if resolved:
                candidates.append(Path(resolved))
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        for root in filter(None, (local_app_data, program_files, program_files_x86)):
            base = Path(root) / "Microsoft VS Code"
            if root == local_app_data:
                base = Path(root) / "Programs" / "Microsoft VS Code"
            candidates.extend((base / "Code.exe", base / "bin" / "code.cmd"))
        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.resolve(strict=False)).casefold()
            if key not in seen and candidate.is_file():
                seen.add(key)
                unique.append(candidate)

        failures: list[str] = []
        if not unique:
            failures.append(self._translator.Text_Get("error.vscode_not_found"))
        workspace_path = workspace_file.resolve()
        for candidate in unique:
            if candidate.suffix.casefold() in {".cmd", ".bat"}:
                batch_command = subprocess.list2cmdline(
                    [str(candidate), "--new-window", str(workspace_path)]
                )
                command_prefix = subprocess.list2cmdline(
                    [
                        os.environ.get("COMSPEC", "cmd.exe"),
                        "/d",
                        "/s",
                        "/c",
                    ]
                )
                # cmd.exe /s /c requires one extra outer quote pair when the
                # batch path itself is quoted. Passing the complete command
                # line avoids Python's CRT argument quoting from turning those
                # inner quotes into literal characters.
                command_line: str | list[str] = (
                    f'{command_prefix} "{batch_command}"'
                )
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            else:
                command_line = [
                    str(candidate),
                    "--new-window",
                    str(workspace_path),
                ]
                creation_flags = 0
            try:
                logging.info(
                    "VS Code launcher command=%r workspace=%s cwd=%s",
                    command_line,
                    workspace_path,
                    workspace_file.parent.resolve(),
                )
                process = subprocess.Popen(
                    command_line,
                    cwd=str(workspace_file.parent.resolve()),
                    creationflags=creation_flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except OSError as error:
                logging.exception("VS Code launcher failed: %s", candidate)
                failures.append(
                    self._translator.Text_Get(
                        "error.vscode_launcher_error",
                        launcher=str(candidate),
                        reason=str(error),
                    )
                )
                continue
            try:
                return_code = process.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                return_code = None
            stderr = ""
            if return_code is not None and process.stderr is not None:
                stderr = process.stderr.read().strip()
            if return_code is None or return_code == 0:
                logging.info(
                    "VS Code workspace launch accepted: launcher=%s return=%s stderr=%s",
                    candidate,
                    return_code,
                    stderr,
                )
                return _WorkspaceLaunchResult(True)
            logging.warning(
                "VS Code launcher exited immediately with %s: %s",
                return_code,
                candidate,
            )
            if stderr:
                logging.warning("VS Code launcher stderr: %s", stderr)
            failures.append(
                self._translator.Text_Get(
                    "error.vscode_launcher_exit",
                    launcher=str(candidate),
                    code=return_code,
                )
            )
        associated = QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(workspace_path))
        )
        if associated:
            logging.info(
                "VS Code workspace opened through the system association: %s",
                workspace_file,
            )
            return _WorkspaceLaunchResult(True)
        failures.append(
            self._translator.Text_Get("error.vscode_association_failed")
        )
        return _WorkspaceLaunchResult(False, "\n".join(failures))

    def _Build_Complete(self, result: BuildResult) -> None:
        command_text = " ".join(result.command)
        raw_output = result.output.rstrip()
        if raw_output and not result.live_streamed:
            self.build_page.BuildLog_Append(raw_output)
        self.build_page.BuildLog_Append(f"> {command_text}")
        key = "status.build_succeeded" if result.succeeded else "status.build_failed"
        self.status_label.setText(
            self._translator.Text_Get(
                key,
                action=self._translator.Text_Get(
                    f"build.action.{result.action.value}"
                ),
            )
        )
        self._project_state = (
            ProjectLifecycleState.READY
            if result.succeeded
            else ProjectLifecycleState.ERROR
        )
        self._QualityResult_Record(
            result.action,
            result.succeeded,
            self._QualitySummary_Get(result),
        )
        if not result.succeeded:
            self.build_page.advanced_section.toggle_button.setChecked(True)
            self._Error_Show(
                self._translator.Text_Get(
                    self._BuildFailureSummaryKey_Get(result.action)
                ),
                raw_output,
            )
        else:
            self._Project_Refresh()
        self._active_build_action = None

    def _BuildLine_Append(self, line: str) -> None:
        if line.startswith("FCCG_DETAIL|"):
            self.build_page.BuildDetailLog_Append(line.split("|", 1)[1])
            return
        if line.startswith("FCCG_EXPECTED_REJECTION|"):
            _prefix, subject = line.split("|", 1)
            subject_key = f"host.expected_rejection.{subject}"
            subject_text = self._translator.Text_Get(subject_key)
            if subject_text == subject_key:
                subject_text = subject.replace("_", " ")
            text = self._translator.Text_Get(
                "host.expected_rejection_passed",
                subject=subject_text,
            )
            self.status_label.setText(text)
            self.build_page.BuildLog_Append(text)
            return
        if line.startswith("FCCG_UI_TASK|"):
            _prefix, action = line.split("|", 1)
            text = self._translator.Text_Get(f"status.task.{action}")
            self.status_label.setText(text)
            self.build_page.BuildLog_Append(text)
            return
        if line.startswith("FCCG_UI_PLAN|"):
            _prefix, total, compile_count = line.split("|", 2)
            text = self._translator.Text_Get(
                "build.progress.plan",
                total=total,
                compile=compile_count,
            )
            self.status_label.setText(text)
            self.build_page.BuildLog_Append(text)
            return
        if line.startswith("FCCG_UI_PROGRESS|"):
            _prefix, stage, current, total, subject = line.split("|", 4)
            if stage == "COMPLETE":
                return
            key = {
                "ANALYZE": "build.progress.static_analysis",
                "DEPENDENCY_COMPILE": "build.progress.dependency_compile",
                "HOST_TEST": "build.progress.host_test",
                "HOST_COMPILE_PASS": "build.progress.host_compile_pass",
                "HOST_EXPECTED_FAILURE": "build.progress.host_expected_failure",
            }.get(
                stage,
                "build.progress.compile"
                if stage == "COMPILE"
                else "build.progress.stage",
            )
            text = self._translator.Text_Get(
                key,
                stage=self._translator.Text_Get(
                    f"build.progress.stage.{stage.casefold()}"
                ),
                current=current,
                total=total,
                source=Path(subject).name or subject,
            )
            self.status_label.setText(text)
            self.build_page.BuildLog_Append(text)
            return
        self.build_page.BuildLog_Append(line)

    def _Build_Error(self, error: object) -> None:
        self._project_state = ProjectLifecycleState.ERROR
        technical_detail = (
            error.technical_detail
            if isinstance(error, FccgError)
            else str(error)
        )
        self.build_page.BuildLog_Append(technical_detail)
        action = self._active_build_action
        if action is not None:
            self._QualityResult_Record(action, False, "error")
        self.build_page.advanced_section.toggle_button.setChecked(True)
        self.build_page.build_detail_section.toggle_button.setChecked(True)
        if action in {
            BuildAction.HOST_TESTS,
            BuildAction.ARCHITECTURE_CHECK,
            BuildAction.POWER10_CHECK,
            BuildAction.STATIC_ANALYSIS,
            BuildAction.ARTIFACT_CHECK,
        }:
            self._Error_Show(
                self._translator.Text_Get(
                    self._BuildFailureSummaryKey_Get(action)
                ),
                technical_detail,
            )
        else:
            self._Error_Show(error)
        self._active_build_action = None

    @staticmethod
    def _BuildFailureSummaryKey_Get(action: BuildAction) -> str:
        return {
            BuildAction.HOST_TESTS: "error.host_tests_failed_summary",
            BuildAction.ARCHITECTURE_CHECK: "error.architecture_check_failed_summary",
            BuildAction.POWER10_CHECK: "error.power10_check_failed_summary",
            BuildAction.STATIC_ANALYSIS: "error.static_analysis_failed_summary",
            BuildAction.ARTIFACT_CHECK: "error.artifact_check_failed_summary",
        }.get(action, "error.build_failed_summary")

    @staticmethod
    def _QualitySummary_Get(result: BuildResult) -> str:
        if not result.succeeded:
            return f"exit_code={result.return_code}"
        patterns = (
            r"SilverStar host summary:.*?checks=(\d+)",
            r"architecture check passed:\s*checks=(\d+)",
            r"Power of Ten check passed:\s*(\d+)\s+checks",
        )
        for pattern in patterns:
            match = re.search(pattern, result.output, re.IGNORECASE)
            if match is not None:
                return f"checks={match.group(1)}"
        return {
            BuildAction.STATIC_ANALYSIS: "analysis_passed",
            BuildAction.ARTIFACT_CHECK: "artifact_validated",
        }.get(result.action, "completed")

    def _QualityResult_Record(
        self, action: BuildAction, succeeded: bool, summary: str
    ) -> None:
        if action not in {
            BuildAction.HOST_TESTS,
            BuildAction.ARCHITECTURE_CHECK,
            BuildAction.POWER10_CHECK,
            BuildAction.STATIC_ANALYSIS,
            BuildAction.ARTIFACT_CHECK,
        } or self._project_root is None:
            return
        duration = (
            time.perf_counter() - self._build_started_at
            if self._build_started_at > 0.0
            else 0.0
        )
        try:
            record = self._service.QualityResult_Record(
                self._project_root,
                task=action.value,
                succeeded=succeeded,
                duration=duration,
                summary=summary,
            )
        except Exception as error:
            self.build_page.BuildLog_Append(str(error))
            return
        records = {
            saved.task: saved
            for saved in self._service.QualityResults_Get(self._project_root)
        }
        records[record.task] = record
        self.build_page.QualityResults_Set(records.values())

    def Task_Run(
        self,
        function: Callable[[Any], Any],
        result_callback: Callable[[Any], None],
        error_callback: Callable[[object], None] | None = None,
        *,
        indeterminate: bool = False,
        line_callback: Callable[[str], None] | None = None,
    ) -> bool:
        if self._active_worker is not None:
            self._Error_Show(
                self._translator.Text_Get("error.background_task_active")
            )
            return False
        worker = FunctionWorker(function)
        self._progress_hide_timer.stop()
        self._active_worker = worker
        self._worker_result_callback = result_callback
        self._worker_error_callback = error_callback
        self._worker_line_callback = line_callback
        self._worker_outcome = None
        self._last_task_progress = 0
        self._task_indeterminate = indeterminate
        worker.signals.progress.connect(self._Task_Progress)
        worker.signals.line.connect(self._Task_Line)
        worker.signals.result.connect(self._Task_Result)
        worker.signals.error.connect(self._Task_Error)
        worker.signals.cancelled.connect(self._Task_Cancelled)
        worker.signals.finished.connect(self._Task_Finish)
        self.progress_bar.setRange(0, 0 if indeterminate else 1000)
        if not indeterminate:
            self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setVisible(True)
        self._Actions_SetEnabled(False)
        self._thread_pool.start(worker)
        return True

    @staticmethod
    def _TaskProgressCallback_Get(context, task: str, code: str):
        def progress(
            current: int, total: int, subject: str, done: bool
        ) -> None:
            context.ProgressEvent_Report(
                task,
                TaskProgressState.DONE if done else TaskProgressState.BEGIN,
                current=current,
                total=total,
                subject=subject,
                code=code,
                check_cancellation=not (done and current == total),
            )

        return progress

    def _Task_Progress(self, progress: float, code: str) -> None:
        self._last_task_progress = int(
            max(0.0, min(1.0, progress)) * 1000
        )
        if not self._task_indeterminate:
            self.progress_bar.setValue(self._last_task_progress)
        self.status_label.setText(self._translator.Text_Get(code))

    def _Task_Result(self, result: Any) -> None:
        self._worker_outcome = ("result", result, "")

    def _Task_Line(self, line: str) -> None:
        progress_event = TaskProgressEvent_Parse(line)
        if progress_event is not None:
            current = (
                0
                if progress_event.state == TaskProgressState.PLAN
                else progress_event.current
            )
            self.status_label.setText(
                self._translator.Text_Get(
                    "task.progress.running",
                    task=progress_event.task.replace("_", " "),
                    current=current,
                    total=progress_event.total,
                    subject=progress_event.subject.replace("_", " ") or "—",
                )
            )
        if self._worker_line_callback is not None:
            self._worker_line_callback(line)

    def _Task_Error(self, error: object, traceback_text: str) -> None:
        logging.error("Background task failed:\n%s", traceback_text)
        self._worker_outcome = ("error", error, traceback_text)
        self.status_label.setText(self._translator.Text_Get("status.failed"))

    def _Task_Cancelled(self) -> None:
        self._worker_outcome = ("cancelled", None, "")
        self.status_label.setText(
            self._translator.Text_Get("status.task_cancelled")
        )

    def _Task_Finish(self) -> None:
        worker = self._active_worker
        result_callback = self._worker_result_callback
        error_callback = self._worker_error_callback
        outcome = self._worker_outcome
        self._active_worker = None
        self._worker_result_callback = None
        self._worker_error_callback = None
        self._worker_line_callback = None
        self._worker_outcome = None
        succeeded = bool(
            outcome is not None
            and outcome[0] == "result"
            and bool(getattr(outcome[1], "succeeded", True))
        )
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(1000 if succeeded else self._last_task_progress)
        self.progress_bar.setProperty(
            "taskState",
            "success"
            if succeeded
            else "cancelled"
            if outcome is not None and outcome[0] == "cancelled"
            else "error",
        )
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)
        self._task_indeterminate = False
        self.cancel_button.setVisible(False)
        self._Actions_SetEnabled(True)
        self._progress_hide_timer.start(350)
        if worker is not None:
            self._retired_workers.append(worker)
        self._TaskOutcome_Dispatch(outcome, result_callback, error_callback)
        if worker is not None:
            QTimer.singleShot(
                0, lambda retired=worker: self._TaskWorker_Release(retired)
            )

    def _TaskOutcome_Dispatch(
        self,
        outcome: tuple[str, object, str] | None,
        result_callback: Callable[[Any], None] | None,
        error_callback: Callable[[object], None] | None,
    ) -> None:
        if outcome is None or outcome[0] == "cancelled":
            return
        try:
            if outcome[0] == "result":
                if result_callback is not None:
                    result_callback(outcome[1])
            elif error_callback is not None:
                error_callback(outcome[1])
            else:
                self._Error_Show(outcome[1], outcome[2])
        except Exception as error:
            logging.exception("Background task completion callback failed")
            self._Error_Show(error)

    def _TaskWorker_Release(self, worker: FunctionWorker) -> None:
        if worker in self._retired_workers:
            self._retired_workers.remove(worker)

    def _Progress_CompletionHide(self) -> None:
        if self._active_worker is None:
            self.progress_bar.setVisible(False)

    def _Task_Cancel(self) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()

    def _Actions_SetEnabled(self, enabled: bool) -> None:
        controls = (
            self.new_action,
            self.open_action,
            self.save_action,
            self.save_as_action,
            self.export_source_action,
            self.manage_plugins_action,
            self.install_plugin_action,
            self.refresh_plugins_action,
            self.board_hardware_page.prepare_button,
            *self.build_page.action_buttons.values(),
            self.build_page.detect_button,
        )
        if not enabled:
            self._action_enabled_snapshot = {
                control: control.isEnabled() for control in controls
            }
            for control in controls:
                control.setEnabled(False)
            return
        snapshot = self._action_enabled_snapshot
        self._action_enabled_snapshot = {}
        for control in controls:
            control.setEnabled(snapshot.get(control, True))

    def _HeaderProject_Refresh(self, model: ProjectModel | None = None) -> None:
        displayed_model = model or self._model
        path = str(self._project_root) if self._project_root is not None else "—"
        self.current_project_value.setText(displayed_model.identity.name)
        self.current_project_value.setToolTip(
            self._translator.Text_Get(
                "project.state_tooltip",
                path=path,
                state=self._translator.Text_Get(
                    f"project.state.{self._project_state.value}"
                ),
            )
        )

    def _Language_Selected(self) -> None:
        language = str(self.language_combo.currentData() or "zh_CN")
        if language != self._translator.language:
            self.Language_Apply(language)

    def _Theme_Selected(self) -> None:
        theme = str(self.theme_combo.currentData() or "light")
        if theme != self._theme:
            self.Theme_Apply(theme)

    def Language_Apply(self, language: str) -> None:
        self._translator.Language_Set(language)
        self.title_label.setText(self._translator.Text_Get("app.title"))
        self.credit_label.setText(self._translator.Text_Get("app.credit"))
        self.current_project_label.setText(
            self._translator.Text_Get("label.current_project")
        )
        self.language_label.setText(
            self._translator.Text_Get("label.interface_language")
        )
        self.theme_label.setText(self._translator.Text_Get("label.theme"))
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem(self._translator.Text_Get("theme.light"), "light")
        self.theme_combo.addItem(self._translator.Text_Get("theme.dark"), "dark")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self._theme)))
        self.theme_combo.blockSignals(False)
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(
            max(0, self.language_combo.findData(language))
        )
        self.language_combo.blockSignals(False)
        for index, code in enumerate(self.PAGE_CODES):
            self.navigation_list.item(index).setText(
                self._translator.Text_Get(code)
            )
        for page in self._page_widgets:
            page.Language_Apply(self._translator)
        self.plugin_manager_dialog.Language_Apply(self._translator)
        self.file_menu.setTitle(self._translator.Text_Get("menu.file"))
        self.plugin_menu.setTitle(self._translator.Text_Get("menu.plugins"))
        self.help_menu.setTitle(self._translator.Text_Get("menu.help"))
        for action, key in (
            (self.new_action, "action.new_project"),
            (self.default_root_action, "action.default_project_root"),
            (self.open_action, "action.open_project"),
            (self.save_action, "action.save_project"),
            (self.save_as_action, "action.save_project_as"),
            (self.export_source_action, "action.export_source_package"),
            (self.exit_action, "action.exit"),
            (self.manage_plugins_action, "action.manage_plugins"),
            (self.install_plugin_action, "action.install_plugin"),
            (self.refresh_plugins_action, "action.refresh_plugins"),
            (self.about_action, "action.about"),
        ):
            action.setText(self._translator.Text_Get(key))
        self.cancel_button.setText(
            self._translator.Text_Get("action.cancel_task")
        )
        self._settings.Value_Set("language", language)
        if self._component_views:
            self._Catalog_Load()
            self._Project_Refresh()
        self._HeaderProject_Refresh()

    def Theme_Apply(self, theme: str) -> None:
        self._theme = theme if theme in {"light", "dark"} else "light"
        application = QApplication.instance()
        if application is not None:
            Theme_Apply(application, self._theme)
        WindowCaption_Apply(self, self._theme)
        self._settings.Value_Set("theme", self._theme)
        if self._component_views:
            self._Project_Refresh()

    def _About_Show(self) -> None:
        self._MessageBox_Exec(
            QMessageBox.Icon.Information,
            PRODUCT_NAME,
            self._translator.Text_Get("about.text", version=__version__),
        )

    def _Error_Show(self, error: object, technical_detail: str = "") -> None:
        if isinstance(error, FccgError):
            message = self._translator.Text_Get(error.code, **error.params)
            if message == error.code:
                message = self._translator.Text_Get("error.operation_failed")
            technical_detail = technical_detail or error.technical_detail
        elif isinstance(error, Exception):
            message = self._translator.Text_Get("error.operation_failed")
            technical_detail = technical_detail or str(error)
        else:
            message = str(error)
        self._MessageBox_Exec(
            QMessageBox.Icon.Critical,
            self._translator.Text_Get("dialog.error_title"),
            message or self._translator.Text_Get("status.failed"),
            details=technical_detail,
        )

    def _MessageBox_Exec(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
        *,
        details: str = "",
    ) -> QMessageBox.StandardButton:
        box = self._MessageBox_Create(
            icon, title, text, buttons, default, details=details
        )
        return QMessageBox.StandardButton(box.exec())

    def _MessageBox_Create(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
        *,
        details: str = "",
    ) -> QMessageBox:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default != QMessageBox.StandardButton.NoButton:
            box.setDefaultButton(default)
        if details:
            box.setDetailedText(details)
        MessageBoxButtons_Localize(box, self._translator)
        return box

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if any(
            Path(url.toLocalFile()).suffix.casefold() in {".ssproject", ".ssplugin"}
            or Path(url.toLocalFile()).name == "SilverStar.ssproject"
            for url in urls
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.casefold() == ".ssplugin":
                self.Task_Run(
                    lambda context, archive=path: self._PluginInstall_Task(
                        context, archive
                    ),
                    self._PluginChange_Complete,
                )
                break
            if path.name == "SilverStar.ssproject" or path.suffix.casefold() == ".ssproject":
                self._Project_Open(path)
                break
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_worker is not None:
            answer = self._MessageBox_Exec(
                QMessageBox.Icon.Question,
                PRODUCT_NAME,
                self._translator.Text_Get("dialog.close_active_task"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._active_worker.Worker_Cancel()
        event.accept()
