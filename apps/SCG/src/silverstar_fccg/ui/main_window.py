from __future__ import annotations

import json
import hashlib
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfile_Write
from silverstar_fccg.project.retired_cdc import NativeCdcMigration_Required
from silverstar_fccg.ui.log_stream_draft import LoggingSnapshot_Apply
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

from shiboken6 import isValid
from PySide6.QtCore import QSignalBlocker, Qt, QThreadPool, QTimer, QUrl
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
    QSizePolicy,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.version import PRODUCT_NAME, __version__
from silverstar_fccg.build.runner import (
    BuildAction,
    BuildProgress,
    BuildResult,
    BuildRunner,
)
from silverstar_fccg.build.toolchain import ArmGnuSubtoolPaths_Derive
from silverstar_fccg.build.quality_batch import QualityBatch_Run, QualityBatchResult, TargetQualityResult
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
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ApplyResult, GenerationPlan
from silverstar_fccg.generator.hardware_preparation import (
    HardwareAssignmentFingerprint_Get,
)
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.air_link import (
    AirLinkIssues_Get,
    GroundTargetIssues_Get,
    RadioCandidateIssues_Get,
)
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameterOwners_Get
from silverstar_fccg.project.alignment import (
    RETIRED_ALIGNMENT_STRATEGIES,
    AlignmentConfiguration,
)
from silverstar_fccg.project.build_audit import BuildAudit_Run
from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
from silverstar_fccg.project.configuration import (
    ModeOptionAvailabilities_Get,
    ProjectConfigurationResult,
    StrategyAvailabilities_Get,
    SelectionAvailabilityTransition_Apply,
)
from silverstar_fccg.project.folder_contract import (
    FLIGHT_DIRECTORY,
)
from silverstar_fccg.project.lifecycle import ProjectLifecycleState
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply, FeatureTier_LogRecordAllowed, FeatureTier_LogRecordRequired, FeatureTier_LogRecordReasonGet
from silverstar_fccg.project.compact_logging import CompactLogStreams_Get, CompactLogRequiredRecords_Get
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LogCadenceKind,
    LoggingProfile_AvailabilityTransitionApply,
    LogPolicyLevel,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.radio_variants import (
    RADIO_PLUGIN, FlightRadioConfiguration_Get, FlightRadioConfiguration_Apply, RadioManifest_Resolve,
)
from silverstar_fccg.project.model import (
    RAW_IMU_MOUNT_PLUGINS,
    DeviceInstance,
    GroundRadioConfigurations_Get,
    HardwareConfiguration,
    HardwareResource,
    LogStreamConfig,
    ProjectModel,
    ProtocolSelection,
)
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.protocols import ProtocolProfileAvailabilities_Get
from silverstar_fccg.project.quality_results import QualityResultRecord, QualityResult_Save
from silverstar_fccg.project.quality_inputs import QUALITY_TASKS, QualityInputHash_Get, QualityInput_Require
from silverstar_fccg.project.power10_report import (
    Power10Report_Create, Power10Report_Save, Power10Report_Load,
    Power10Report_Current_Is, Power10Report_Csv, Power10TextPassed_Is,
)
from silverstar_fccg.project.artifact_memory import ArtifactMemorySummary_Encode, ArtifactMemoryReportSummary_Encode
from silverstar_fccg.project.artifact_stack import ArtifactStackReportSummary_Encode
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.resources import BoardInventory_ReadScope, ResourceAssignments_Resolve
from silverstar_fccg.project.ground_activity import GroundActivityLedEnabled_Get
from silverstar_fccg.project.release_policy import (
    ReleaseCompatibilityIssues_Get, ReleaseMigrationModel_Create, ReleaseMigrationCopy_Save,
)
from silverstar_fccg.project.validation import (
    AlignmentConfigurationIssues_Get,
    Project_EditValidate,
    ValidationIssue,
)
from silverstar_fccg.ui.dialogs import NewProjectWizard
from silverstar_fccg.ui.message_box import MessageBoxButtons_Localize
from silverstar_fccg.ui.pages import (
    BoardHardwarePage,
    BuildPage,
    DevicesPage,
    FlightConfigurationPage,
    PluginManagerDialog,
)
from silverstar_fccg.ui.pages.algorithm_parameters import NavigationConfigurationPage
from silverstar_fccg.ui.pages.hardware_workspace import HardwareWorkspacePage
from silverstar_fccg.ui.pages.flight_workflow import FlightWorkflowPage
from silverstar_fccg.ui.pages.build import DefaultTools_Get
from silverstar_fccg.ui.pages.targets import AirLinkPage, GroundTargetPage, GroundIssues_PresentationGet
from silverstar_fccg.ui.pages.base import ScrollableLocalizedPage
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
    tier_device_conflicts: bool


@dataclass(frozen=True, slots=True)
class _WorkspaceLaunchResult:
    succeeded: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.succeeded


from silverstar_fccg.ui.hardware_editing import HardwareEditingActions


class MainWindow(HardwareEditingActions, QMainWindow):
    PAGE_CODES = ("workspace.hardware.title", "workspace.workflow.title", "page.build")

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
        self._path_preferences = PathPreferences(
            WorkspacePolicy(self._settings.path.parent),
            self._settings.path.parent / "path_preferences.json",
        )
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
        self._task_progress_range = (0.0, 1.0)
        self._completion_worker: FunctionWorker | None = None
        self._disabled_strategy_choices: set[str] = set()
        self._disabled_mode_choices: set[tuple[str, str]] = set()
        self._selection_restore_project = None
        self._logging_transport_choice: ProtocolSelection | None = None
        self._logging_transport_streams: list[LogStreamConfig] | None = None
        self._retired_workers: list[FunctionWorker] = []
        self._progress_hide_timer = QTimer(self)
        self._progress_hide_timer.setSingleShot(True)
        self._progress_hide_timer.timeout.connect(self._Progress_CompletionHide)
        self._component_views: tuple[ComponentView, ...] = ()
        self._model: ProjectModel = self._service.ProjectDraft_Create("SilverStar")
        # File persistence is independent of generation readiness and editor drafts.
        self._saved_model_snapshot = deepcopy(self._model.Dictionary_Get())
        self._project_root: Path | None = None
        self._legacy_source_bytes: bytes | None = None
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
        self._pending_strategy_changes: dict[str, object] = {}
        self._strategy_refresh_scheduled = False
        self._alignment_commit_in_progress = False
        self._close_after_worker = False
        self._pending_mission_process = None
        self._mission_process_pending = False
        self._pending_functions = None
        self._last_workspace_index = 0
        self._pending_logging_streams: tuple[LoggingStreamView, ...] | None = None
        self._logging_refresh_scheduled = False
        self._validation_focus_widget: QWidget | None = None
        self._toolchain_dialog: QDialog | None = None
        self._toolchain_checked = False
        self._install_guide_dialog: QDialog | None = None
        self._action_enabled_snapshot: dict[object, bool] = {}
        self.setWindowTitle(PRODUCT_NAME)
        self.setAcceptDrops(True)
        self.resize(1460, 900)
        self.setMinimumSize(900, 700)
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
        self._header_layout = QVBoxLayout(header)
        self._header_layout.setContentsMargins(14, 6, 14, 6)
        self._header_layout.setSpacing(3)
        header_layout = QHBoxLayout()
        self._header_main_layout = header_layout
        self._header_layout.addLayout(header_layout)
        self.title_label = QLabel()
        self.title_label.setObjectName("headerTitle")
        self.title_label.setWordWrap(False)
        self.title_label.setStyleSheet("font-size: 16px;")
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        self.credit_label = QLabel()
        self.credit_label.setObjectName("headerCredit")
        self.current_project_label = QLabel()
        self.current_project_label.setObjectName("headerControlLabel")
        self.current_project_value = QLabel()
        self.current_project_value.setObjectName("headerProjectValue")
        self.current_project_value.setMinimumWidth(0)
        self.current_project_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
        header_layout.addWidget(self.current_project_value, 1)
        self._header_controls = QWidget()
        controls_layout = QHBoxLayout(self._header_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.language_label)
        controls_layout.addWidget(self.language_combo)
        controls_layout.addWidget(self.theme_label)
        controls_layout.addWidget(self.theme_combo)
        header_layout.addWidget(self._header_controls)
        self._header_compact = False
        root_layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        self.navigation_sidebar = sidebar
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
        self.legacy_migration_button = QPushButton()
        self.legacy_migration_button.clicked.connect(self._ReleaseMigration_Request)
        self.devices_page.root_layout.insertWidget(0, self.legacy_migration_button)
        self.flight_configuration_page = FlightConfigurationPage(self._translator)
        self.algorithm_parameters_page = NavigationConfigurationPage(self._translator)
        self.algorithm_parameters_page.parameterChanged.connect(self._AlgorithmParameter_Change)
        self.algorithm_parameters_page.defaultsRequested.connect(self._AlgorithmDefaults_Reset)
        self.algorithm_parameters_page.sharedParameterChanged.connect(self._SharedAlgorithmParameter_Change)
        self.algorithm_parameters_page.sharedDefaultsRequested.connect(self._SharedAlgorithmDefaults_Reset)
        self.algorithm_parameters_page.alignmentConfirmed.connect(self._AlignmentConfiguration_Confirm)
        self.algorithm_parameters_page.alignmentDraftCancelled.connect(self._AlignmentDraft_SelectorRestore)
        self.board_hardware_page = BoardHardwarePage(self._translator)
        self.air_link_page = AirLinkPage(self._translator)
        self.ground_target_page = GroundTargetPage(self._translator)
        self.ground_configuration_page = self.air_link_page
        self.build_page = BuildPage(self._translator)
        self.hardware_workspace = HardwareWorkspacePage(self._translator,self.devices_page,
            self.board_hardware_page,self.ground_target_page,self.air_link_page)
        # Explicit legacy-copy action stays reachable outside the private editor.
        self.hardware_workspace.root_layout.insertWidget(
            self.hardware_workspace.root_layout.count() - 1, self.legacy_migration_button)
        self.workflow_page = FlightWorkflowPage(self._translator,self.flight_configuration_page,
            self.algorithm_parameters_page)
        self.build_page.TargetEditors_Attach(self.board_hardware_page,self.ground_target_page)
        # One shared-link transaction owns protocol edits. Keep the old presenter
        # internal, rather than accidentally inserting a nested widget at row 0.
        protocol_group = self.flight_configuration_page.telemetry_protocol_group
        self.workflow_page.recording.body.layout().removeWidget(protocol_group)
        protocol_group.setParent(self.hardware_workspace)
        protocol_group.hide()

        self._page_widgets = (self.hardware_workspace,self.workflow_page,self.build_page)
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
        self.power10_export_button = QPushButton()
        self.power10_export_button.setEnabled(False)
        self.power10_export_button.clicked.connect(self._Power10Report_Export)
        self.system_log_button = QPushButton()
        self.system_log_button.setObjectName("systemLogButton")
        self.system_log_button.clicked.connect(self._SystemLog_Show)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setVisible(False)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.cancel_button)
        status.addPermanentWidget(self.progress_bar)
        status.addPermanentWidget(self.power10_export_button)
        status.addPermanentWidget(self.system_log_button)
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
        self.attachments_action = QAction("打开附加资料目录 / Open Attachments", self)
        self.attachments_action.triggered.connect(self._Attachments_Open)
        self.file_menu.addAction(self.attachments_action)
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
        self.navigation_list.currentRowChanged.connect(self._NavigationPage_Change)
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
        self.devices_page.radioSelectionChanged.connect(self._FlightRadioSelection_Change)
        self.devices_page.radioPowerChanged.connect(self._FlightRadioPower_Change)
        self.devices_page.variantChanged.connect(self._DeviceVariant_Change)
        self.devices_page.installationOrientationChanged.connect(
            self._Jy901bOrientation_Change)
        self.devices_page.mountNoseAxisChanged.connect(self._RawImuMount_Change)
        self.devices_page.mountXAxisChanged.connect(self._RawImuXAxis_Change)
        self.devices_page.installationReferenceAdoptRequested.connect(self._InstallationReference_Adopt)
        self.devices_page.sensorPositionChanged.connect(self._SensorPosition_Change)
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
            lambda: self._BoardInstanceSave_Request("flight")
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
        self.board_hardware_page.generateRequested.connect(
            lambda: self._Targets_Generate("generate_flight")
        )
        self.air_link_page.configurationChanged.connect(self._AirLink_Change)
        self.air_link_page.endpointPowerChanged.connect(self._EndpointPower_Change)
        self.hardware_workspace.linkEditRequested.connect(self._AirLinkTransaction_Open)
        self.hardware_workspace.targetEditRequested.connect(self._HardwareTransaction_Open)
        self.ground_target_page.configurationChanged.connect(self._GroundTarget_Change)
        self.ground_target_page.activityLedToggled.connect(self._GroundActivityLed_Toggle)
        self.ground_target_page.assignmentChanged.connect(self._GroundAssignment_Change)
        self.ground_target_page.prepareRequested.connect(self._GroundExistingHardware_Request)
        self.ground_target_page.importRequested.connect(self._GroundCubeMxImport_Request)
        self.ground_target_page.saveInstanceRequested.connect(
            lambda: self._BoardInstanceSave_Request("ground")
        )
        self.ground_target_page.generateRequested.connect(
            lambda: self._Targets_Generate("generate_ground")
        )
        self.ground_target_page.radiosChanged.connect(self._GroundRadios_Change)
        self.flight_configuration_page.strategyChanged.connect(
            self._Strategy_Change
        )
        self.flight_configuration_page.modeChanged.connect(self._Mode_Change)
        self.flight_configuration_page.mission_profile_panel.exportRequested.connect(self._MissionProfile_Export)
        self.flight_configuration_page.mission_process_panel.processChanged.connect(self._MissionProcess_Queue)
        self.workflow_page.functionsChanged.connect(self._Functions_Queue)
        self.workflow_page.configurationChanged.connect(self._WorkflowTransaction_Apply)
        self.workflow_page.functionAddRequested.connect(self._Function_Add)
        self.workflow_page.functionRemoveRequested.connect(self._Function_Remove)
        self.workflow_page.parameterImportRequested.connect(self._ParameterProfile_Import)
        self.workflow_page.parameterExportRequested.connect(self._ParameterProfile_Export)
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
        self.build_page.optionsRequested.connect(self._BuildOptions_Open)
        self.build_page.issueActivated.connect(lambda issue:self._ValidationIssue_Navigate((issue,)))
        self.build_page.actionRequested.connect(self._Build_Request)
        self.build_page.memoryLayoutChanged.connect(self._MemoryLayout_Change)
        self.devices_page.featureTierChanged.connect(self._FeatureTier_Change)
        self.devices_page.optionalResourceChanged.connect(self._OptionalResource_Change)
        self.plugin_manager_dialog.panel.installRequested.connect(
            self._PluginInstall_Dialog
        )
        self.plugin_manager_dialog.panel.removeRequested.connect(
            self._PluginRemove_Request
        )

    def _NavigationPage_Change(self, index: int) -> None:
        if self._component_views and not self._displaying_model and index != self._last_workspace_index:
            if not self._WorkflowDrafts_Commit():
                with QSignalBlocker(self.navigation_list):self.navigation_list.setCurrentRow(self._last_workspace_index)
                self.pages.setCurrentIndex(self._last_workspace_index)
                return
        self._last_workspace_index=index
        self._Workspace_Save()
        if index == self.PAGE_CODES.index("page.build") and not self._toolchain_checked:
            self._toolchain_checked = True
            QTimer.singleShot(0, self._Toolchains_Detect)

    def _WorkspaceKey_Get(self):
        identity=str(self._project_root or '__draft__')
        return 'workspaces/v1/'+hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]

    def _Workspace_Save(self):
        if not hasattr(self,'workflow_page'):return
        key=self._WorkspaceKey_Get()
        index=self.navigation_list.currentRow()
        if 0<=index<len(self.PAGE_CODES):self._settings.Value_Set(key+'/page',self.PAGE_CODES[index])
        self._settings.Value_Set(key+'/hardware',json.dumps(self.hardware_workspace.ExpandedState_Get()))
        self._settings.Value_Set(key+'/workflow',json.dumps(self.workflow_page.ExpandedState_Get()))
        self._settings.Value_Set(key+'/stage',self.workflow_page.stage_panel.selected_stage_id)

    def _Workspace_Restore(self):
        key=self._WorkspaceKey_Get()
        value=self._settings.Value_Get(key+'/page',self._settings.Value_Get('page_index',0))
        old={'page.devices':0,'page.flight_configuration':1,'page.navigation_configuration':1,
             'page.telemetry_configuration':0,'page.board_hardware':0,'page.ground':0,'page.build':2}
        if isinstance(value,str) and value in self.PAGE_CODES:index=self.PAGE_CODES.index(value)
        elif isinstance(value,str) and value in old:index=old[value]
        else:
            try:index=(0,1,1,0,0,0,2)[int(value)] if 0<=int(value)<7 else 0
            except (TypeError,ValueError):index=0
        for name,workspace in (('hardware',self.hardware_workspace),('workflow',self.workflow_page)):
            try:workspace.ExpandedState_Set(json.loads(str(self._settings.Value_Get(key+'/'+name,'{}'))))
            except (ValueError,TypeError):pass
        stage=self._settings.Value_Get(key+'/stage','')
        if stage in self.workflow_page.stage_panel.cards:self.workflow_page.stage_panel.Stage_Select(stage)
        self.navigation_list.setCurrentRow(index)

    def _Catalog_Load(self) -> None:
        self._project_display_state = None
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
            component for component in self._component_views
            if component.selection_kind
            and component.component_id not in RETIRED_ALIGNMENT_STRATEGIES
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
                    if category != 'telemetry' or profile.profile_id == 'ss_tm.s.0_1'
                )
        definitions = ProtocolLogDefinitions_Get(model, self._service.catalog)
        workspace_file = (
            self._project_root / FLIGHT_DIRECTORY / f"{FLIGHT_DIRECTORY}.code-workspace"
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
            tier_device_conflicts=any(issue.code in ("COMPACT_DEVICE_LIMIT", "FEATURE_TIER")
                for issue in (configuration.edit_validation if configuration is not None
                    else Project_EditValidate(model, self._service.catalog)).issues),
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
                self._service.QualityResults_Get(self._project_root / FLIGHT_DIRECTORY)
                if self._project_root is not None
                and (self._project_root / FLIGHT_DIRECTORY).is_dir()
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
                self._project_root / FLIGHT_DIRECTORY
                / "build"
                / "FCCG"
                / model.build.target_profile
                / configuration
            )
            if model.build.memory_layout != "legacy":
                directory /= model.build.memory_layout
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
            self.devices_page.FeatureTier_Set(display.model.build.feature_tier)
            self.devices_page.OptionalResources_Set(display.model.build)
            self.devices_page.InstallationReference_Set(display.model.sensor_installation)
            self.devices_page.FeatureTier_NoticeSet(self._translator.Text_Get(
                "configuration.feature_tier_devices_review") if display.tier_device_conflicts else "")
            self.devices_page.Configuration_Set(
                display.devices,
                display.device_instances,
                display.device_availability,
                {manifest.component_id: manifest.radio.modules
                 for manifest in self._service.catalog.Type_Get("device")
                 if manifest.radio is not None},
                {instance.instance_id: FlightRadioConfiguration_Get(display.model, instance)
                 for instance in display.model.device_instances if instance.plugin in {RADIO_PLUGIN, "silverstar.device.telemetry.sx1278"}},
            )
            self.flight_configuration_page.Configuration_Set(
                display.selectable_components,
                display.model.strategies,
                display.model.modes,
                mode_parameters=display.model.mode_parameters,
                strategy_availability=display.strategy_availability,
                mode_availability=display.mode_availability,
            )
            try:
                mission_profile = MissionProfile_Build(display.model, self._service.catalog)
            except ValueError:
                mission_profile = None
            self.flight_configuration_page.mission_profile_panel.Profile_Set(mission_profile)
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
            self.build_page.MemoryLayout_Set(display.model.build.memory_layout)
            self.devices_page.FeatureTier_Set(display.model.build.feature_tier)
            self.devices_page.OptionalResources_Set(display.model.build)
            if not self._alignment_commit_in_progress:
                self.algorithm_parameters_page.AlignmentConfiguration_Set(
                    display.model.alignment,
                    display.model.strategies.get("alignment"),
                    tuple(display.model.device_instances),
                )
                self._AlignmentDraft_SelectorRestore(
                    self.algorithm_parameters_page.alignment_editor.DraftStrategy_Get()
                )
            from silverstar_fccg.project.rate_plan import InertialRatePlan_Resolve

            try:
                rate_plan = InertialRatePlan_Resolve(
                    display.model, self._service.catalog,
                )
            except ValueError as error:
                self.algorithm_parameters_page.RatePlan_Set(None, str(error))
            else:
                self.algorithm_parameters_page.RatePlan_Set(rate_plan)
            project_root = self._project_root
            current_targets = {target: bool(project_root and ProjectTargetGenerated_IsCurrent(
                display.model, self._service.catalog, project_root / directory, target))
                for target, directory in (('flight', 'Flight_Controller'), ('ground', 'Ground_Station'))}
            self.build_page.Targets_Set(
                flight_generated=bool(
                    project_root and (project_root / "Flight_Controller" / "Makefile").is_file()
                ),
                ground_configured=display.model.ground_target.hardware.mode != "unselected",
                ground_generated=bool(
                    project_root and (project_root / "Ground_Station" / "Makefile").is_file()
                ),
                flight_current=current_targets['flight'], ground_current=current_targets['ground'],
            )
            self.build_page.FirmwareArtifact_Set(
                str(display.firmware_output_directory or ""),
                display.firmware_artifact_name,
            )
            self.build_page.QualityResults_Set(display.quality_results)
            self._TargetQualityResults_Refresh(display.model, current_targets=current_targets)
            self.power10_export_button.setEnabled(
                self._project_root is not None and Power10Report_Load(self._project_root / FLIGHT_DIRECTORY) is not None)
            self.legacy_migration_button.setVisible(bool(ReleaseCompatibilityIssues_Get(display.model)))
            self._BoardPage_Refresh(display)
            self._TargetPages_Refresh(display.model)
            self._TargetReadiness_Refresh(display.model)
            self.hardware_workspace.Configuration_Set(display.model)
            self.build_page.TargetConfiguration_Set(display.model)
            from silverstar_fccg.project.validation import Project_Validate
            checks=Project_Validate(display.model,self._service.catalog)
            self.build_page.Issues_Set(checks.issues)
            self.workflow_page._display = display
            self.workflow_page.Configuration_Set(display.model,self._service.catalog)
            self._HeaderProject_Refresh(display.model)
        finally:
            self._displaying_model = False
        self._project_display_state = display
        self._project_display_snapshot = display.model.Dictionary_Get()


    def _TargetReadiness_Refresh(self, model=None):
        model = model or self._model
        readiness = {target: self._service.TargetReadiness_Get(model, target)
                     for target in ('flight', 'ground')}
        for target, page in (('flight', self.board_hardware_page),
                             ('ground', self.ground_target_page)):
            result = readiness[target]
            page.generate_button.setEnabled(result.ready and self._active_worker is None)
            page.generate_button.setToolTip(
                self._translator.Text_Get('target.generation.ready') if result.ready else
                '\n'.join(issue.message for issue in result.issues))
            if not result.ready:
                label = self.build_page.target_status_labels[target]
                reasons = tuple(dict.fromkeys(issue.message for issue in result.issues))
                label.setText(self._translator.Text_Get('target.generation.blocked') + '\n' +
                              '\n'.join(reasons[:2]))
                label.setToolTip('\n'.join(issue.message for issue in result.issues))
            else:
                self.build_page.target_status_labels[target].setToolTip('')
        self.hardware_workspace.Readiness_Set(readiness)

    def _LoggingViews_Get(
        self,
        definitions,
        model: ProjectModel,
    ) -> tuple[LoggingStreamView, ...]:
        streams = {stream.record: stream for stream in CompactLogStreams_Get(model)}
        views: list[LoggingStreamView] = []
        for definition in definitions:
            stream = streams[definition.record]
            tier_allowed = FeatureTier_LogRecordAllowed(model, definition.record)
            tier_required = FeatureTier_LogRecordRequired(model, definition.record)
            availability = LogAvailability_Get(
                definition, model, self._service.catalog
            )
            reason = ""
            if not availability.available:
                reason = self._translator.Text_Get(
                    availability.reason_code,
                    missing=", ".join(availability.missing),
                )
            if not tier_allowed:
                reason = self._translator.Text_Get(FeatureTier_LogRecordReasonGet(model, definition.record))
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
                    required=(tier_allowed and (tier_required or definition.level == LogPolicyLevel.REQUIRED or
                        (model.build.feature_tier == "minimal" and stream.record in CompactLogRequiredRecords_Get(model)))),
                    available=availability.available and tier_allowed,
                    editable=model.build.logging_profile == "all_streams" and tier_allowed and not tier_required,
                    availability_reason=(self._translator.Text_Get("logging.profile.locked")
                        if tier_allowed and availability.available and model.build.logging_profile != "all_streams" else reason),
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
            self._model, self._project_root / FLIGHT_DIRECTORY
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

    _LoggingSnapshot_Apply = staticmethod(LoggingSnapshot_Apply)

    def _LoggingState_Apply(self, model: ProjectModel) -> None:
        self._LoggingSnapshot_Apply(
            model, self.flight_configuration_page.Streams_Get()
        )

    def _ProjectModel_Sync(self) -> None:
        self._LoggingState_Apply(self._model)

    def _MissionProfile_Export(self) -> None:
        if not self._WorkflowDrafts_Commit(): return
        if self._pending_logging_streams is not None:
            self._LoggingChanges_Apply()
        if self._pending_mode_changes or self._pending_mode_parameter_changes:
            self._ModeChanges_Apply()
        self._ProjectModel_Sync()
        selected, _filter = QFileDialog.getSaveFileName(self,
            self._translator.Text_Get('mission_profile.export'),
            str(Path.home() / 'Documents' / (self._model.identity.name + '.ssmission')),
            self._translator.Text_Get('mission_profile.filter'))
        if not selected:
            return
        target = Path(selected)
        if not target.suffix:
            target = target.with_suffix('.ssmission')
        try:
            profile = MissionProfile_Build(self._model, self._service.catalog)
            MissionProfile_Write(target, profile, replace_existing=target.exists())
            self.flight_configuration_page.mission_profile_panel.Profile_Set(profile)
            self.statusBar().showMessage(self._translator.Text_Get('mission_profile.saved', path=str(target)), 8000)
        except (ValueError, OSError) as error:
            self._Error_Show(error)

    def _MemoryLayout_Change(self, layout: str) -> None:
        if layout not in ("auto", "eskf_window_sram"):
            return
        def mutate(model: ProjectModel) -> None:
            model.build = replace(model.build, memory_layout=layout)
        self._ProjectConfiguration_Change(mutate)



    @BoardInventory_ReadScope()
    def _ProjectConfiguration_Change(
        self,
        mutator: Callable[[ProjectModel], None],
        *,
        status_key: str = "status.configuration_changed_simple",
        logging_snapshot: tuple[LoggingStreamView, ...] | None = None,
        logging_availability_changed: bool = False,
        include_workflow_drafts: bool = True,
    ) -> ProjectConfigurationResult | None:
        if self._displaying_model:
            return None
        try:
            pending_process=self.workflow_page.Pending_Commit() if include_workflow_drafts else None
            pending_functions=self.workflow_page.PendingFunctions_Collect() if include_workflow_drafts else None
        except ValueError as error:
            self._Error_Show(error);return None
        candidate = deepcopy(self._model)
        if pending_process is not None:candidate.mission_process=pending_process
        restore_project = (self._project_root, self._model.identity.name)
        logging_transport_choice = (self._logging_transport_choice
            if self._selection_restore_project == restore_project else None)
        logging_transport_streams = (self._logging_transport_streams
            if self._selection_restore_project == restore_project else None)
        if logging_snapshot is None:
            self._LoggingState_Apply(candidate)
        else:
            self._LoggingSnapshot_Apply(candidate, logging_snapshot)
        previous_lifecycle = self._project_state
        previous_display: _ProjectDisplayState | None = None
        try:
            if pending_functions is not None:
                self._FunctionsConfiguration_Update(candidate, pending_functions)
            cached_display = getattr(self, "_project_display_state", None)
            previous_display = (cached_display if cached_display is not None
                and cached_display.model is self._model
                and self._project_display_snapshot == self._model.Dictionary_Get()
                else self._ProjectDisplayState_Build(self._model))
            mutator(candidate)
            added = [item for item in candidate.device_instances if item not in self._model.device_instances]
            added_storage = [item for item in added
                if self._service.Plugin_Get(item.plugin).component_class == "storage"]
            if added_storage:
                storage_count = sum(self._service.Plugin_Get(item.plugin).component_class == "storage"
                    for item in candidate.device_instances)
                availability = self._service.DeviceSelectionAvailabilities_Get(candidate)
                if storage_count > 1 or any(availability[item.plugin].missing_components for item in added_storage):
                    raise ValueError(self._translator.Text_Get("device.storage_single_platform"))
            if added and candidate.build.feature_tier == self._model.build.feature_tier:
                from silverstar_fccg.project.compact import CompactErrors_Get
                from silverstar_fccg.project.feature_tiers import FeatureTier_ErrorsGet
                errors = CompactErrors_Get(candidate, self._service.catalog) + FeatureTier_ErrorsGet(candidate, self._service.catalog)
                if errors:
                    raise ValueError(self._translator.Text_Get("configuration.feature_tier_devices_review")
                                     + "\n" + "\n".join(errors))
            result = self._service.ProjectConfiguration_Reconcile(candidate)
            if any(notice.code == "configuration.protocol_transport_removed" and notice.slot == "logging"
                   for notice in result.notices):
                logging_transport_choice = deepcopy(candidate.protocols.get("logging"))
                logging_transport_streams = deepcopy(candidate.logging_streams)
            restore_project = (self._project_root, self._model.identity.name)
            if self._selection_restore_project != restore_project:
                self._disabled_strategy_choices.clear()
                self._disabled_mode_choices.clear()
                self._selection_restore_project = restore_project
            restored = SelectionAvailabilityTransition_Apply(
                self._model, result.model, self._service.catalog,
                self._disabled_strategy_choices, self._disabled_mode_choices)
            if restored:
                reconciled = self._service.ProjectConfiguration_Reconcile(result.model)
                result = replace(reconciled, notices=result.notices + restored + reconciled.notices)
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
            from silverstar_fccg.project.mission_functions import FunctionsStrategies_Synchronize
            synchronized=FunctionsStrategies_Synchronize(self._model,result.model,self._service.catalog)
            if synchronized.mission_functions != result.model.mission_functions:
                refreshed=self._service.ProjectConfiguration_Reconcile(synchronized)
                result=replace(refreshed,notices=result.notices+refreshed.notices)
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
        self.workflow_page.Drafts_Clear()
        self._logging_transport_choice = logging_transport_choice
        self._logging_transport_streams = logging_transport_streams
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
            indeterminate=False,
            progress_range=(0.0, 0.2),
        )

    def _HardwarePreparePlan_Complete(
        self, prepared: tuple[ProjectModel, GenerationPlan]
    ) -> None:
        candidate, plan = prepared
        if not self._GenerationPlan_ApplyAllowed(plan):
            self._Task_Cancel()
            return
        if (self._completion_worker is not None and
                self._completion_worker.context.cancelled):
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
            indeterminate=False,
            progress_range=(0.2, 1.0),
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


    def _AirLink_Change(self, field: str, value: object) -> None:
        if field == "radio_family" and value == "sx128x":
            self._ProjectConfiguration_Change(lambda candidate: setattr(candidate, "air_link",
                replace(candidate.air_link, radio_family="sx128x", radio_technology="lora", phy_mode="lora", nrf24=None)))
            return
        self._ProjectConfiguration_Change(
            lambda candidate: setattr(
                candidate, "air_link", replace(candidate.air_link, **{field: value})
            )
        )

    def _HardwareTransaction_Open(self, target, section='hardware'):
        if self._active_worker is not None or not self._WorkflowDrafts_Commit():
            return
        from dataclasses import fields
        from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
        original = deepcopy(self._model.Dictionary_Get())
        project = self._project_root
        dialog = HardwareTransactionDialog(self._translator, self._model, self._service,
                                           target, section, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        candidate, import_path = dialog.Configuration_Get(), dialog.ImportPath_Get()
        open_radio = dialog.open_shared_radio
        dialog.deleteLater()
        def publish(configuration):
            if self._project_root != project or self._model.Dictionary_Get() != original:
                self._Error_Show(self._translator.Text_Get('hardware.editor.stale'))
                return
            def apply(current):
                for field in fields(configuration):
                    setattr(current, field.name, deepcopy(getattr(configuration, field.name)))
            if configuration.Dictionary_Get() != original:
                result = self._ProjectConfiguration_Change(apply, logging_availability_changed=True,
                                                          include_workflow_drafts=False)
                if result is None:
                    return
            if open_radio:
                QTimer.singleShot(0, self, self._AirLinkTransaction_Open)

        if not import_path:
            publish(candidate)
            return

        def imported(result):
            if target == 'flight':
                candidate.board = ''
                candidate.hardware = result.hardware
                candidate.resource_assignments = {}
            else:
                from silverstar_fccg.hardware.platform import DetectedMcuFacts_FromInventory, PlatformMatch_Resolve
                match = PlatformMatch_Resolve(DetectedMcuFacts_FromInventory(
                    result.inventory, vendor='STM32', provider='stm32_cubemx'), self._service.catalog)
                candidate.ground_target = replace(candidate.ground_target,
                    mcu=match.selected.component_id, board='', hardware=result.hardware,
                    resource_assignments={}, pc_resource='',
                    pc_interface='usb_cdc' if NativeCdcMigration_Required(self._model)
                    else candidate.ground_target.pc_interface)
            publish(candidate)

        def importing(context):
            return self._service.CubeMxProject_Import(Path(import_path), candidate,
                risk_acknowledged=True, target=target)
        self.Task_Run(importing, imported)

    def _AirLinkTransaction_Open(self):
        from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog
        dialog = RadioTransactionDialog(self._translator, self._model, self._service.catalog, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            configuration = dialog.Configuration_Get()
            def Apply(candidate):
                for key in ('air_link', 'device_instances', 'resource_assignments', 'ground_target', 'protocols'):
                    setattr(candidate, key, deepcopy(getattr(configuration, key)))
            self._ProjectConfiguration_Change(Apply, logging_availability_changed=True)
        dialog.deleteLater()

    def _EndpointPower_Change(self, endpoint: str, value: int) -> None:
        if endpoint == "flight":
            self._ProjectConfiguration_Change(
                lambda candidate: setattr(candidate, "flight_tx_power_dbm", value)
            )
        elif endpoint == "ground":
            self._GroundTarget_Change("tx_power_dbm", value)






    def _GroundExistingHardware_Request(self) -> None:
        combo = self.ground_target_page.board_combo
        selected = str(combo.currentData() or "")
        if selected == "__custom__" or not selected:
            choices = tuple((combo.itemText(index), combo.itemData(index)) for index in range(combo.count())
                            if combo.itemData(index) != "__custom__" and combo.model().item(index).isEnabled())
            if not choices:
                self._Error_Show(self._translator.Text_Get("board.no_provider"))
                return
            name, accepted = QInputDialog.getItem(self, self._translator.Text_Get("hardware.existing"),
                self._translator.Text_Get("field.board_name"), [item[0] for item in choices], 0, False)
            if not accepted:
                return
            selected = next(identity for title, identity in choices if title == name)
        self._GroundBoard_Change(selected)

    def _GroundCubeMxImport_Request(self, directory: bool) -> None:
        if directory:
            selected = QFileDialog.getExistingDirectory(
                self, self._translator.Text_Get("dialog.import_cubemx_directory")
            )
        else:
            selected, _filter = QFileDialog.getOpenFileName(
                self, self._translator.Text_Get("dialog.import_cubemx_ioc"), "",
                self._translator.Text_Get("filter.cubemx_ioc"),
            )
        if not selected:
            return
        model, project, service = deepcopy(self._model), self._project_root, self._service
        def complete(result):
            if self._ProjectSnapshot_Current(model, project):
                self._GroundCubeMxImport_Complete(result)
        self.Task_Run(lambda context: service.CubeMxProject_Import(
            Path(selected), model, risk_acknowledged=True, target="ground"), complete)

    def _GroundCubeMxImport_Complete(self, result) -> None:
        from silverstar_fccg.hardware.platform import (
            DetectedMcuFacts_FromInventory,
            PlatformMatch_Resolve,
        )

        match = PlatformMatch_Resolve(
            DetectedMcuFacts_FromInventory(
                result.inventory, vendor="STM32", provider="stm32_cubemx"
            ),
            self._service.catalog,
        )
        def change(candidate: ProjectModel) -> None:
            candidate.ground_target = replace(
                candidate.ground_target, mcu=match.selected.component_id,
                board="", hardware=result.hardware,
                resource_assignments={}, pc_resource="",
            )
        self._ProjectConfiguration_Change(change)

    def _BoardInstanceSave_Request(self, target_role: str) -> None:
        name, accepted = QInputDialog.getText(
            self,
            self._translator.Text_Get("dialog.export_board_title"),
            self._translator.Text_Get("field.board_name"),
        )
        if not accepted or not name.strip():
            return
        default_id = "local.board." + target_role + "." + "_".join(
            name.lower().split()
        )
        component_id, accepted = QInputDialog.getText(
            self,
            self._translator.Text_Get("dialog.export_board_title"),
            self._translator.Text_Get("field.plugin_id"),
            text=default_id,
        )
        if not accepted:
            return
        try:
            installed = self._service.CustomBoardPlugin_SaveLocal(
                self._model,
                component_id=component_id.strip(),
                name=name.strip(),
                target_role=target_role,
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self.status_label.setText(
            self._translator.Text_Get(
                "status.pcb_instance_saved", identity=installed.component_id,
            )
        )
        self._Project_Refresh()





    def _Strategy_Change(self, slot: str, component_id: object) -> None:
        if slot == "alignment":
            self.algorithm_parameters_page.alignment_editor.DraftStrategy_Set(
                str(component_id) if component_id is not None else ""
            )
            return
        # A native QComboBox popup is still on the stack here.  Rebuilding its
        # QFormLayout synchronously deletes the emitting combo and can crash Qt.
        self._pending_strategy_changes[slot] = component_id
        if not self._strategy_refresh_scheduled:
            self._strategy_refresh_scheduled = True
            QTimer.singleShot(0, self, self._StrategyChanges_Apply)

    def _StrategyChanges_Apply(self) -> None:
        self._strategy_refresh_scheduled = False
        changes = self._pending_strategy_changes
        self._pending_strategy_changes = {}
        if changes:
            self._ProjectConfiguration_Change(
                lambda candidate: candidate.strategies.update({
                    slot: str(value) if value is not None else None
                    for slot, value in changes.items()
                }),
                logging_availability_changed=True,
            )

    def _MissionProcess_Queue(self,process):
        self._pending_mission_process=deepcopy(process)
        if self._mission_process_pending:return
        self._mission_process_pending=True
        QTimer.singleShot(0,self,self._MissionProcessChanges_Apply)

    def _WorkflowTransaction_Apply(self, configuration):
        def Apply(candidate):
            for key in ('mission_process', 'mission_functions', 'algorithm_parameters', 'logging_streams',
                        'capability_source_overrides', 'strategies', 'modes', 'mode_parameters', 'alignment', 'protocols', 'base_components'):
                setattr(candidate, key, deepcopy(getattr(configuration, key)))
        self._ProjectConfiguration_Change(Apply, include_workflow_drafts=False, logging_availability_changed=True)

    def _MissionProcessChanges_Apply(self):
        if not self._mission_process_pending:return
        candidate=self._pending_mission_process
        self._mission_process_pending=False
        return self._ProjectConfiguration_Change(lambda model:setattr(model,'mission_process',candidate))

    def _Functions_Queue(self,configuration):
        self._pending_functions=deepcopy(configuration)
        QTimer.singleShot(0,self,self._FunctionsChanges_Apply)

    def _FunctionsChanges_Apply(self):
        if self._pending_functions is None:return
        value=self._pending_functions;self._pending_functions=None
        return self._ProjectConfiguration_Change(lambda model:self._FunctionsConfiguration_Update(model,value))

    def _FunctionsConfiguration_Update(self, model, configuration):
        from silverstar_fccg.project.mission_functions import FunctionsConfiguration_Apply
        updated = FunctionsConfiguration_Apply(model, self._service.catalog, configuration)
        # The surrounding project transaction reconciles the complete model.
        model.capability_source_overrides = updated.capability_source_overrides
        model.mission_functions = updated.mission_functions

    def _WorkflowDrafts_Commit(self):
        try:
            if self._mission_process_pending and self._MissionProcessChanges_Apply() is None:
                return False
            if self._pending_functions is not None and self._FunctionsChanges_Apply() is None:
                return False
            if self._pending_strategy_changes:self._StrategyChanges_Apply()
            if self._pending_mode_changes or self._pending_mode_parameter_changes:self._ModeChanges_Apply()
            functions=self.workflow_page.PendingFunctions_Collect()
            if functions is not None:
                if self._ProjectConfiguration_Change(lambda model:self._FunctionsConfiguration_Update(model,functions)) is None:
                    return False
            value=self.workflow_page.Pending_Commit()
            if value is not None:
                self._ProjectConfiguration_Change(lambda model:setattr(model,'mission_process',value))
            return True
        except (ValueError,TypeError) as error:
            self._Error_Show(error);return False

    def _Function_Add(self,plugin_id):
        QTimer.singleShot(0,self,lambda:self._FunctionAdd_Apply(plugin_id))

    def _FunctionAdd_Apply(self,plugin_id):
        from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsCanonical_Get
        current = Functions_Derive(self._model, self._service.catalog)
        existing = next((row for row in current['functions'] if row['plugin_id'] == plugin_id), None)
        if existing:
            self.workflow_page._FunctionDialog_Open(existing['instance_id'])
            return
        candidate = deepcopy(self._model)
        manifest = self._service.catalog.Component_Get(plugin_id)
        try:
            if manifest.selection is not None and manifest.selection.slot in candidate.strategies:
                candidate.strategies[manifest.selection.slot] = plugin_id
            elif plugin_id not in candidate.ComponentIds_Get():
                raise ValueError(self._translator.Text_Get('workflow.function.select_owner'))
            candidate = self._service.ProjectConfiguration_Reconcile(candidate).model
            canonical = FunctionsCanonical_Get(candidate, self._service.catalog)
            function = next((row for row in canonical['functions'] if row['plugin_id'] == plugin_id), None)
            if function is None:
                raise ValueError(self._translator.Text_Get('workflow.function.select_owner'))
            rows = [row for row in current['functions'] if row['instance_id'] != function['instance_id']]
            candidate.mission_functions = {**current, 'functions': [*rows, function]}
        except (ValueError, TypeError) as error:
            self._Error_Show(error)
            return
        self.workflow_page._FunctionDialog_Open(function['instance_id'], candidate)

    def _Function_Remove(self,identity):
        def change(candidate):
            from silverstar_fccg.project.mission_functions import Functions_Derive
            functions=Functions_Derive(candidate,self._service.catalog)
            function=next(row for row in functions['functions'] if row['instance_id']==identity)
            references = [row['instance_id'] for row in functions['functions']
                          if identity in row['depends_on'] or identity in row['input_bindings'].values()]
            if references:
                raise ValueError(self._translator.Text_Get('workflow.function.referenced',
                    identity=identity, references=', '.join(references)))
            manifest=self._service.catalog.Component_Get(function['plugin_id'])
            if identity=='ins' or manifest.selection is None or manifest.selection.slot!='estimator':
                raise ValueError(self._translator.Text_Get('workflow.function.system_owned'))
            candidate.strategies['estimator']=None
            functions['functions']=[row for row in functions['functions'] if row['instance_id']!=identity]
            candidate.mission_functions=functions
        QTimer.singleShot(0,self,lambda:self._ProjectConfiguration_Change(change))

    def _ParameterProfile_Import(self,plugin_id):
        from silverstar_fccg.project.mission_functions import ParameterProfile_Read,ParameterProfile_Preview,ParameterProfile_Apply
        if not self._WorkflowDrafts_Commit():return
        path,_filter=QFileDialog.getOpenFileName(self,self._translator.Text_Get('workflow.function.import'),'',
            'Algorithm parameters (*.ssparams *.ssparameters *.sstuning.json *.json);;TreeDiagram bundle (*.sstuning.json)')
        if not path:return
        try:
            preview_model = deepcopy(self._model.Dictionary_Get())
            control_option = None
            control_candidate = None
            control_requested = False

            def ControlTaskOption_Record(checked):
                nonlocal control_requested
                control_requested = bool(checked)

            bundle = path.lower().endswith('.sstuning.json') or _filter.startswith('TreeDiagram')
            if bundle:
                from silverstar_fccg.project.tuning_bundle import TuningBundle_Read, TuningBundle_Preview, TuningBundle_Apply
                value = TuningBundle_Read(path)
                preview = TuningBundle_Preview(self._model, self._service.catalog, value)
                changes = preview['changes']
            else:
                value=ParameterProfile_Read(path)
                changes=ParameterProfile_Preview(self._model,self._service.catalog,plugin_id,value)
            details='\n'.join(row['plugin_id']+' / '+row['parameter_id']+': '+str(row['before'])+' → '+str(row['after'])+' '+row['unit']
                               + (' [shared]' if row['shared'] else '') for row in changes)
            if bundle:
                details += '\n\n' + self._translator.Text_Get('workflow.import.research_control')
                details += '\n' + '\n'.join(preview['limitations'])
                if value.get('control_research') is not None:
                    from PySide6.QtWidgets import QCheckBox
                    from silverstar_fccg.project.tuning_bundle import TuningBundle_ControlTaskAttach
                    control_option = QCheckBox(self._translator.Text_Get('workflow.import.control_task'), self)
                    control_option.setObjectName('includeControlResearchTask')
                    control_option.setChecked(False)
                    # QMessageBox owns this widget and may delete it before
                    # exec returns. Capture the user's choice while it lives;
                    # only ordinary Python state crosses the modal boundary.
                    control_option.toggled.connect(ControlTaskOption_Record)
                    try:
                        control_candidate = TuningBundle_ControlTaskAttach(self._model, self._service.catalog, value)
                    except ValueError as error:
                        control_option.setEnabled(False)
                        control_option.setToolTip(str(error))
                        details += '\n' + self._translator.Text_Get('workflow.import.control_unavailable') + ': ' + str(error)
                    else:
                        details += '\n\n' + self._translator.Text_Get('workflow.import.control_values')
                        details += '\n' + '\n'.join(name + ': ' + str(number)
                            for name, number in value['control_research']['parameters'].items())
            answer=self._MessageBox_Exec(QMessageBox.Icon.Question,self._translator.Text_Get('workflow.import.preview'),
                self._translator.Text_Get('workflow.import.control_changes' if control_option is not None
                    else 'workflow.import.changes',count=len(changes)),details=details,
                buttons=QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
                default=QMessageBox.StandardButton.Cancel, check_box=control_option)
            if answer!=QMessageBox.StandardButton.Apply:return
            if self._model.Dictionary_Get() != preview_model:
                raise ValueError(self._translator.Text_Get('workflow.import.stale'))
            include_control = control_requested and control_candidate is not None
            updated = (control_candidate if include_control else
                       TuningBundle_Apply(self._model,self._service.catalog,value) if bundle else
                       ParameterProfile_Apply(self._model,self._service.catalog,plugin_id,value))
            def apply(model):
                model.algorithm_parameters = deepcopy(updated.algorithm_parameters)
                if include_control:
                    model.base_components = deepcopy(updated.base_components)
                    model.mission_functions = deepcopy(updated.mission_functions)
            self._ProjectConfiguration_Change(apply)
        except (OSError,ValueError,TypeError) as error:self._Error_Show(error)

    def _ParameterProfile_Export(self,plugin_id):
        from silverstar_fccg.project.mission_functions import ParameterProfile_Build,ParameterProfile_Write
        if not self._WorkflowDrafts_Commit():return
        path,_filter=QFileDialog.getSaveFileName(self,self._translator.Text_Get('workflow.function.export'),plugin_id+'.ssparams','Algorithm parameters (*.ssparams)')
        if not path:return
        try:ParameterProfile_Write(path,ParameterProfile_Build(self._model,self._service.catalog,plugin_id),replace_existing=Path(path).exists())
        except (OSError,ValueError,TypeError) as error:self._Error_Show(error)

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
        if category == "maintenance" and selection is not None and self._model.build.feature_tier == "minimal":
            self._Error_Show(ValueError(self._translator.Text_Get("protocol.unavailable.feature_tier")))
            self._Project_Refresh()
            return
        if selection is None:
            result = self._ProjectConfiguration_Change(
                lambda candidate: candidate.protocols.__setitem__(
                    category, None
                ),
                logging_availability_changed=category == "logging",
            )
            if category == "logging" and result is not None:
                self._logging_transport_choice = None
                self._logging_transport_streams = None
            return
        if not isinstance(selection, tuple) or len(selection) != 2:
            return
        component_id, profile_id = (str(value) for value in selection)
        if not component_id or not profile_id:
            return
        manifest = self._service.Plugin_Get(component_id)
        def change(candidate):
            candidate.protocols[category] = ProtocolSelection(
                component=manifest.component_id, version=manifest.version,
                profile=profile_id, manifest_sha256=manifest.ManifestSha256_Get())
            if category == "telemetry":
                from dataclasses import replace
                candidate.air_link = replace(candidate.air_link, protocol_profile=profile_id)
        self._ProjectConfiguration_Change(change, logging_availability_changed=category == "logging")

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
        if not self._WorkflowDrafts_Commit(): return
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
        if widget is None or not isValid(widget):
            self._validation_focus_widget=None
            return
        widget.setProperty("validationIssue", False)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
        self._validation_focus_widget = None

    def _ValidationIssue_Navigate(
        self, issues: tuple[ValidationIssue, ...]
    ) -> None:
        issue = next((item for item in issues if item.level == "error"), next(iter(issues),None))
        if issue is None:
            return
        self._ValidationIssue_Clear()
        code = issue.code
        target: QWidget = self.build_page.tool_status_group
        if code.startswith(("hardware", "board", "resource", "platform", "mcu", "HCLK", "MCU_HCLK")) or code in {
            "protocol_transport",
            "protocol_transport_ambiguous",
            "hal_cmsis_source_policy",
        }:
            target = (
                self.board_hardware_page.resource_table
                if code.startswith("resource") or code.startswith("protocol_transport")
                else self.board_hardware_page.board_combo
            )
        elif code.startswith(("GROUND_", "GROUND", "GROUND_HCLK")):
            target = (self.ground_target_page.pc_interface
                      if code.startswith("GROUND_PC_") else self.ground_target_page)
        elif code.startswith("STORAGE_"):
            target = (self.devices_page if code in {
                "STORAGE_DEVICE_REQUIRED", "STORAGE_DEVICE_AMBIGUOUS",
                "STORAGE_COMPONENT_UNAVAILABLE",
            } else self.board_hardware_page.resource_table)
        elif code.startswith(('INSTALLATION_', 'AUGMENTED_LEVER_ARM')):
            target = self.devices_page.installation_map
        elif code.startswith(('ALIGNMENT_', 'EXPERIMENTAL_ESTIMATOR')):
            target = self.algorithm_parameters_page.alignment_editor
        elif code.startswith(('COMPACT_LOG', 'log_sink')):
            target = self.flight_configuration_page.logging_table
        elif code.startswith(("AIR_LINK", "protocol_telemetry")):
            target = self.air_link_page
        elif code.startswith(("strategy", "capability", "TIMING_PROFILE", "REPLAY", "IMU_RATE")):
            target = (
                next(iter(self.flight_configuration_page.strategy_combos.values()),
                     self.algorithm_parameters_page)
                if code.startswith("strategy") else self.algorithm_parameters_page
            )
        elif code.startswith(("mode", "logging", "protocol")):
            if code.startswith("mode"):
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
                target = self.flight_configuration_page
        elif code.startswith('MISSION_PROCESS'):
            target = self.workflow_page.stage_panel.condition_editor
            if target is None:
                target = self.workflow_page.stage_panel
        elif code.startswith('FUNCTION_'):
            from silverstar_fccg.project.mission_functions import Functions_Issues
            found=next((item for item in Functions_Issues(self._model,self._service.catalog)
                        if item.code == code and issue.message == item.function_id + ': ' + item.message),None)
            target=self.workflow_page
            if found:
                stage_id=getattr(found,'stage_id','')
                if stage_id in self.workflow_page.stage_panel.cards:
                    self.workflow_page.stage_panel.Stage_Select(stage_id)
                self.workflow_page.coverage.Function_Select(found.function_id)
                target=self.workflow_page.coverage
        elif code == "algorithm_parameters":
            matching=next((key for key in self.algorithm_parameters_page.editors
                if key[0] in issue.message and key[1] in issue.message),None)
            if matching:
                self.workflow_page.Parameters_Select(matching[0])
                target=self.workflow_page.function_buttons['parameters']
            else:target=self.workflow_page.option_buttons['algorithms']
        elif code.startswith("device"):
            target = next(
                iter(self.devices_page.device_combos.values()),
                self.devices_page,
            )
        # Editors can move between pages without changing their stable IDs.
        # Find the actual owner instead of retaining obsolete numeric indices.
        if target is self.ground_target_page:target=self.hardware_workspace._target_sections['ground']
        elif target is self.devices_page:target=self.hardware_workspace._target_sections['flight']
        elif target is self.algorithm_parameters_page:target=self.workflow_page.preparation
        elif target is self.flight_configuration_page:target=self.workflow_page
        elif target is self.air_link_page:target=self.hardware_workspace.link_summary
        page_index = next((index for index, page in enumerate(self._page_widgets)
                           if page is target or page.isAncestorOf(target)),
                          self.PAGE_CODES.index("page.build"))
        self.navigation_list.setCurrentRow(page_index)
        if page_index==0 and self.hardware_workspace.Reveal(target):
            # A private modal may refresh or replace the original hidden editor.
            # Do not retain or style its stale widget after the transaction.
            return
        elif page_index==1:self.workflow_page.Reveal(target)
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

    def _ProjectFile_DirtyGet(self, model: ProjectModel | None = None) -> bool:
        return (model or self._model).Dictionary_Get() != self._saved_model_snapshot

    def _WorkspaceDrafts_PendingGet(self) -> bool:
        editor = self.workflow_page.stage_panel.condition_editor
        try:
            functions_pending = self.workflow_page.PendingFunctions_Collect() is not None
        except (TypeError, ValueError):
            functions_pending = True  # Invalid text is still a private draft.
        return bool((editor is not None and editor._dirty) or functions_pending
            or self._mission_process_pending or self._pending_functions is not None
            or self._pending_strategy_changes or self._pending_mode_changes
            or self._pending_mode_parameter_changes or self._pending_logging_streams is not None
            or self.algorithm_parameters_page.alignment_editor.draft_dirty)

    def _WorkspaceDrafts_DiscardConfirm(self):
        if not self._WorkspaceDrafts_PendingGet() and not self._ProjectFile_DirtyGet():
            return True
        answer=self._MessageBox_Exec(QMessageBox.Icon.Question,PRODUCT_NAME,
            self._translator.Text_Get('project.unsaved_confirm'),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer not in (QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard):
            return False
        if answer==QMessageBox.StandardButton.Save:
            self._Project_Save()
            if (self._project_root is None or self._ProjectFile_DirtyGet()
                    or self._WorkspaceDrafts_PendingGet()):
                return False
            try:
                saved=self._service.Project_Open(self._project_root)
                if saved.Dictionary_Get()!=self._model.Dictionary_Get():return False
            except Exception:return False
        self._EditQueues_Clear()
        self.algorithm_parameters_page.alignment_editor.Draft_Discard()
        self._Project_Refresh()
        return True

    def _EditQueues_Clear(self):
        self._mission_process_pending=False;self._pending_mission_process=None;self._pending_functions=None
        self._pending_mode_changes.clear();self._pending_mode_parameter_changes.clear()
        self._pending_strategy_changes.clear();self._pending_logging_streams=None
        self.workflow_page.Drafts_Clear()
        if self.workflow_page.stage_panel.condition_editor is not None:
            self.workflow_page.stage_panel.condition_editor._dirty=False

    def _NewProject_Show(self) -> None:
        if not self._WorkspaceDrafts_DiscardConfirm():return
        wizard = NewProjectWizard(self._translator, self,
                                  default_root=self._path_preferences.DefaultProjectRoot_EffectiveGet())
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        values = wizard.WizardData_Get()
        try:
            model = self._service.ProjectDraft_Create(values["name"])
            project_root = Path(values["output_directory"]).resolve(strict=False)
            self._service.ProjectRoot_Save(model, project_root, create_new=True)
        except Exception as error:
            self._Error_Show(error)
            return
        self._EditQueues_Clear()
        self.algorithm_parameters_page.alignment_editor.Draft_Discard()
        self._model = model
        self._saved_model_snapshot = deepcopy(model.Dictionary_Get())
        self._logging_transport_choice = None
        self._logging_transport_streams = None
        self._project_root = project_root
        self._legacy_source_bytes = None
        self._generation_plan = None
        self._project_state = ProjectLifecycleState.DRAFT
        self._Project_Refresh()
        self.navigation_list.setCurrentRow(0)
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
        if not self._WorkspaceDrafts_DiscardConfirm():return
        try:
            descriptor = path / "SilverStar.ssproject" if path.is_dir() else path
            source_bytes = descriptor.read_bytes()
            loaded = self._service.Project_Open(path)
            # Keep legacy navigation until the user deliberately creates a copy.
            if ReleaseCompatibilityIssues_Get(loaded) or NativeCdcMigration_Required(loaded):
                reconciled = loaded
            else:
                opening = deepcopy(loaded)
                reconciled = self._service.ProjectConfiguration_Reconcile(opening).model
            changed_during_open = (
                loaded.Dictionary_Get() != reconciled.Dictionary_Get()
            )
            self._EditQueues_Clear()
            self.algorithm_parameters_page.alignment_editor.Draft_Discard()
            self._model = reconciled
            self._saved_model_snapshot = deepcopy(loaded.Dictionary_Get())
            self._logging_transport_choice = None
            self._logging_transport_streams = None
            self._legacy_source_bytes = source_bytes
            self._project_root = (
                path.resolve() if path.is_dir() else path.resolve().parent
            )
        except Exception as error:
            self._Error_Show(error)
            return
        self._generation_plan = None
        readiness = self._service.ProjectReadiness_Get(
            self._model, self._project_root / FLIGHT_DIRECTORY
        )
        self._project_state = (
            ProjectLifecycleState.DIRTY
            if changed_during_open
            else readiness.state
        )
        self._Project_Refresh()
        self._Workspace_Restore()
        self.status_label.setText(
            self._translator.Text_Get(
                "status.project_opened", name=self._model.identity.name
            )
        )

        if ReleaseCompatibilityIssues_Get(self._model):
            self._MessageBox_Exec(QMessageBox.Icon.Warning,
                self._translator.Text_Get("release.migrate"),
                self._translator.Text_Get("release.legacy_notice"),
                details="\n".join(ReleaseCompatibilityIssues_Get(self._model)))

    def _ReleaseMigration_Request(self) -> None:
        if self._active_worker is not None or not ReleaseCompatibilityIssues_Get(self._model):
            return
        answer = self._MessageBox_Exec(QMessageBox.Icon.Warning,
            self._translator.Text_Get("release.migrate"),
            self._translator.Text_Get("release.migrate_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        selected = QFileDialog.getExistingDirectory(self,
            self._translator.Text_Get("release.migrate_destination"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()))
        if not selected:
            return
        try:
            candidate = ReleaseMigrationModel_Create(self._model)
            candidate = self._service.ProjectConfiguration_Reconcile(candidate).model
            ReleaseMigrationCopy_Save(self._model, candidate, Path(selected), self._legacy_source_bytes,
                                      self._project_root)
        except Exception as error:
            self._Error_Show(error)
            return
        self._pending_strategy_changes.clear()
        self.algorithm_parameters_page.alignment_editor.Draft_Discard()
        self._model = candidate
        self._legacy_source_bytes = None
        self._Project_SaveAs_Complete(Path(selected).resolve())
        self.navigation_list.setCurrentRow(1)
        self._MessageBox_Exec(QMessageBox.Icon.Information,
            self._translator.Text_Get("release.migrate"),
            self._translator.Text_Get("release.migrated", path=str(Path(selected).resolve())))

    def _AlignmentDraft_SelectorRestore(self, strategy: str) -> None:
        combo = self.flight_configuration_page.strategy_combos.get("alignment")
        if combo is None:
            return
        index = combo.findData(strategy)
        if index >= 0:
            with QSignalBlocker(combo):
                combo.setCurrentIndex(index)

    def _AlignmentConfiguration_Confirm(self, strategy: str, configuration: object) -> None:
        if not isinstance(configuration, AlignmentConfiguration):
            return

        def update(candidate: ProjectModel) -> None:
            candidate.strategies["alignment"] = strategy
            candidate.alignment = configuration
            if configuration.external_source_instance:
                candidate.capability_source_overrides["attitude.external"] = (
                    configuration.external_source_instance
                )
            else:
                candidate.capability_source_overrides.pop("attitude.external", None)

        candidate = deepcopy(self._model)
        update(candidate)
        issues = AlignmentConfigurationIssues_Get(candidate, self._service.catalog)
        if issues:
            self.algorithm_parameters_page.alignment_editor.Issue_Show(
                "; ".join(f"{issue.code}: {issue.message}" for issue in issues)
            )
            return
        self._alignment_commit_in_progress = True
        try:
            result = self._ProjectConfiguration_Change(
                update, logging_availability_changed=True,
            )
        finally:
            self._alignment_commit_in_progress = False
        if result is not None:
            self.algorithm_parameters_page.alignment_editor.Draft_Commit(
                self._model.alignment,
                self._model.strategies.get("alignment") or "",
            )
        self._AlignmentDraft_SelectorRestore(
            self.algorithm_parameters_page.alignment_editor.DraftStrategy_Get()
        )

    def _Project_Save(self) -> None:
        if not self._WorkflowDrafts_Commit(): return
        draft_pending = self.algorithm_parameters_page.alignment_editor.draft_dirty
        self._ProjectModel_Sync()
        if self._project_root is None:
            self._Project_SaveAs()
            return
        try:
            self._service.ProjectRoot_Save(self._model, self._project_root)
        except Exception as error:
            self._Error_Show(error)
            return
        self._saved_model_snapshot = deepcopy(self._model.Dictionary_Get())
        self._project_state = ProjectLifecycleState.DIRTY
        self._Project_Refresh()
        self.status_label.setText(self._translator.Text_Get(
            "alignment.pending_not_saved" if draft_pending else "status.project_saved_ready"
        ))

    def _Project_Save_Complete(self, result: ApplyResult) -> None:
        self._project_root = result.project_root
        self._saved_model_snapshot = deepcopy(
            self._service.Project_Open(result.project_root).Dictionary_Get())
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
        if not self._WorkflowDrafts_Commit(): return
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
        try:
            destination = Path(selected).resolve(strict=False)
            if destination != self._project_root and destination.exists() and any(destination.iterdir()):
                raise ValueError("Save As destination must be empty")
            self._service.ProjectRoot_Save(self._model, destination)
        except Exception as error:
            self._Error_Show(error)
            return
        self._Project_SaveAs_Complete(destination)

    def _Project_SaveAs_Complete(self, destination: Path) -> None:
        self._project_root = destination
        self._saved_model_snapshot = deepcopy(self._model.Dictionary_Get())
        self._project_state = ProjectLifecycleState.DRAFT
        self._generation_plan = None
        self._Project_Refresh()
        self.status_label.setText(
            self._translator.Text_Get("alignment.pending_not_saved")
            if self.algorithm_parameters_page.alignment_editor.draft_dirty else
            self._translator.Text_Get("status.project_saved_as", path=str(destination))
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
            str(self._service.workspace_root / "SilverStar_SCG-source.zip"),
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
        # Tool discovery updates build availability, but it does not make an
        # unconfigured target ready or erase its configuration blockers.
        self._TargetReadiness_Refresh()

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

    def _BuildOptions_Open(self):
        from silverstar_fccg.ui.build_options_dialog import BuildOptionsDialog
        original = self._model.Dictionary_Get()
        dialog = BuildOptionsDialog(self._translator, self._model, self.build_page._tools, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and self._model.Dictionary_Get() == original:
            paths, layout = dialog.paths, dialog.memory.currentData()
            if paths != self._model.build.tool_paths or layout != self._model.build.memory_layout:
                def change(candidate):
                    candidate.build = replace(candidate.build, tool_paths=paths, memory_layout=layout)
                self._ProjectConfiguration_Change(change)
        dialog.deleteLater()

    def _Targets_Generate(self, action_text: str) -> None:
        if not self._WorkflowDrafts_Commit(): return
        if self._active_worker is not None:
            return
        if self.algorithm_parameters_page.alignment_editor.draft_dirty:
            self._Error_Show(self._translator.Text_Get("alignment.confirm_before_generation"))
            return
        self._ProjectModel_Sync()
        requested = ('flight', 'ground') if action_text == 'generate_all' else (
            'ground' if action_text == 'generate_ground' else 'flight',)
        issues = tuple(issue for target in requested
                       for issue in self._service.TargetReadiness_Get(self._model, target).issues)
        if issues:
            self._Error_Show(self._translator.Text_Get('target.generation.blocked'),
                             '\n'.join(issue.message for issue in issues))
            return
        if self._project_root is None:
            selected = QFileDialog.getExistingDirectory(
                self, self._translator.Text_Get("dialog.select_project_root")
            )
            if not selected:
                return
            self._project_root = Path(selected)
        scope = {
            "generate_flight": TargetScope.FLIGHT,
            "generate_ground": TargetScope.GROUND,
            "generate_all": TargetScope.ALL,
        }[action_text]
        model = deepcopy(self._model)
        if scope in {TargetScope.GROUND, TargetScope.ALL}:
            issues = GroundTargetIssues_Get(model, self._service.catalog)
            if issues:
                summary, details = GroundIssues_PresentationGet(issues, self._translator)
                self._Error_Show(summary, details)
                return
        destination = self._project_root
        try:
            self._service.ProjectRoot_Save(model, destination)
        except Exception as error:
            self._Error_Show(error)
            return
        self._saved_model_snapshot = deepcopy(model.Dictionary_Get())
        self._HeaderProject_Refresh()

        def generated(result) -> None:
            self._model.log_decoder_profile = model.log_decoder_profile
            # The worker persisted its own fixed model; never mark newer edits saved.
            self._saved_model_snapshot = deepcopy(model.Dictionary_Get())
            self._Project_Refresh()
            self.status_label.setText(
                self._translator.Text_Get("status.targets_generated")
                + ": " + ", ".join(result.targets)
            )

        def apply(confirm_dangerous: bool) -> None:
            self.Task_Run(
                lambda context: TargetGeneration_Apply(
                    model, self._service.catalog, self._service.policy,
                    destination, scope, confirm_dangerous=confirm_dangerous,
                    progress_callback=self._TaskProgressCallback_Get(context, "GENERATE", "status.task_running"),
                ),
                generated,
                indeterminate=False,
            )

        if scope == TargetScope.GROUND:
            apply(False)
            return
        flight_model = model

        def planned(plan: GenerationPlan) -> None:
            if self._GenerationPlan_ApplyAllowed(plan):
                apply(plan.dangerous)

        self.Task_Run(
            lambda _context: self._service.GenerationPlan_Create(
                flight_model, destination / FLIGHT_DIRECTORY
            ),
            planned,
        )

    def _Build_Request(self, action_text: str) -> None:
        if not self._WorkflowDrafts_Commit(): return
        if (action_text.startswith(("flight_build", "ground_build"))
                and self.algorithm_parameters_page.alignment_editor.draft_dirty):
            self._Error_Show(self._translator.Text_Get("alignment.confirm_before_generation"))
            return
        self._ProjectModel_Sync()
        if action_text.startswith(("flight_", "ground_")):
            self._TargetAction_Request(action_text)
            return
        if action_text in {"generate_flight", "generate_ground", "generate_all"}:
            self._Targets_Generate(action_text)
            return
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
        if action_text in QUALITY_TASKS:
            self._QualityChecks_Request(BuildAction(action_text))
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
            "stack_report": BuildAction.STACK_REPORT,
        }
        action = actions.get(action_text)
        if action is None:
            return
        project_root = self._project_root / FLIGHT_DIRECTORY
        project_file = project_root / "SilverStar.ssproject"
        if not project_file.is_file():
            self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
            return
        try:
            generated_model = self._service.Project_Open(project_file)
        except Exception as error:
            self._Error_Show(error)
            return
        self._project_state = ProjectLifecycleState.BUILDING
        self._active_build_action = action
        self._build_started_at = time.perf_counter()
        self.build_page.BuildLog_Set("")
        self.build_page.BuildDetailLog_Set("")

        def build(context) -> BuildResult:
            context.Progress_Report(
                0.0,
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
                    max(0.0, min(0.99, fraction)),
                    "status.build_running",
                )
                context.Line_Report(
                    "FCCG_UI_PROGRESS|"
                    f"{progress.stage}|{progress.stage_completed}|"
                    f"{progress.stage_total}|{progress.subject}"
                )

            result = self._service.Build_Run(
                generated_model,
                project_root,
                action,
                context.token if hasattr(context, "token") else context,
                line_callback=context.Line_Report,
                progress_callback=progress_report,
                ensure_buildable=False,
            )
            if result.succeeded and (
                action != BuildAction.POWER10_CHECK
                or Power10TextPassed_Is(result.output, result.return_code)
            ):
                context.Progress_Report(1.0, "status.build_running")
            return result

        self.Task_Run(
            build,
            self._Build_Complete,
            self._Build_Error,
            indeterminate=False,
            line_callback=self._BuildLine_Append,
        )

    def _TargetQualityInputs_Get(self, target: str):
        if self._project_root is None:
            raise ValueError(self._translator.Text_Get("quality.target.unavailable"))
        root = self._project_root / (FLIGHT_DIRECTORY if target == "flight" else "Ground_Station")
        WorkspacePolicy(self._project_root).Path_Resolve(root, allow_root=False)
        if target == "flight":
            model = self._service.Project_Open(root / "SilverStar.ssproject")
            # Generated configuration, with the user's current tool locations.
            model.build = replace(model.build, tool_paths=deepcopy(self._model.build.tool_paths))
        else:
            model = deepcopy(self._model)
            ground_build = model.ground_target.build
            model.build = replace(ground_build, tool_paths={
                **self._model.build.tool_paths, **ground_build.tool_paths})
        return root, model

    def _TargetQualityResults_Refresh(self, model=None, *, current_targets=None) -> None:
        displayed = self._model if model is None else model
        for target in ("flight", "ground"):
            records = ()
            states = {}
            try:
                root, model = self._TargetQualityInputs_Get(target)
                records = self._service.QualityResults_Get(root)
                runner = BuildRunner(WorkspacePolicy(root))
                by_task = {record.task: record for record in records}
                current = (current_targets[target] if current_targets is not None else
                    ProjectTargetGenerated_IsCurrent(displayed, self._service.catalog, root, target))
                for task in QUALITY_TASKS:
                    if not current:
                        if task in by_task:
                            states[task] = 'stale'
                        continue
                    try:
                        QualityInput_Require(root, target, task)
                        record = by_task.get(task)
                        if record is not None and (not record.input_sha256 or
                            record.input_sha256 != QualityInputHash_Get(root, target, task,
                                runner.Command_Get(model, BuildAction(task)))):
                            states[task] = "stale"
                    except (OSError, ValueError):
                        states[task] = "unavailable"
                self.build_page.target_quality_status[target].setText(
                    self._translator.Text_Get("quality.target.generated_input", path=str(root)))
            except Exception:
                states = {task: "unavailable" for task in QUALITY_TASKS}
                self.build_page.target_quality_status[target].setText(
                    self._translator.Text_Get("quality.target.unavailable"))
            self.build_page.TargetQualityResults_Set(target, records, states)


    def _ProjectSnapshot_Current(self, model, project) -> bool:
        return (not self._close_after_worker and project == self._project_root and
                model.Dictionary_Get() == self._model.Dictionary_Get())




    def _QualityChecks_Request(self, action: BuildAction) -> None:
        if self._active_worker is not None:
            self._Error_Show(self._translator.Text_Get("error.background_task_active"))
            return
        selected = self.build_page.QualityTargets_Get()
        self._TargetQualityResults_Refresh()
        if not selected:
            self.status_label.setText(self._translator.Text_Get("quality.target.none"))
            return
        if self._project_root is None:
            self.status_label.setText(self._translator.Text_Get("quality.target.unavailable"))
            return
        inputs = []
        for target in selected:
            try:
                root, model = self._TargetQualityInputs_Get(target)
            except Exception:
                root = (self._project_root or Path(".")) / (
                    FLIGHT_DIRECTORY if target == "flight" else "Ground_Station")
                model = deepcopy(self._model)
            # Missing inputs are reported independently by the batch; no SaveAs
            # or generation is implicitly performed by a quality action.
            inputs.append((target, root, model))
            self.build_page.TargetQualityProgress_Set(target, None,
                self._translator.Text_Get("quality.target.waiting"))
            states = dict(self.build_page._target_quality_states[target])
            states[action.value] = "waiting"
            self.build_page.TargetQualityResults_Set(target,
                self.build_page._target_quality_records[target], states)
        self._project_state = ProjectLifecycleState.BUILDING
        self.build_page.BuildLog_Set("")
        self.build_page.BuildDetailLog_Set("")
        self._active_quality_targets = selected
        self._active_quality_action = action.value
        requested_model, requested_project = deepcopy(self._model), self._project_root
        def quality_run(context):
            outcomes = []
            for target, root, model in inputs:
                context.Cancel_RaiseIfRequested()
                if not ProjectTargetGenerated_IsCurrent(requested_model, self._service.catalog, root, target):
                    outcome = TargetQualityResult(target, root, model, None, '', 0.0,
                        'Target inputs or plugin payload changed; regenerate this target before checking')
                    context.Line_Report('FCCG_QUALITY|' + json.dumps(dict(target=target, kind='done',
                        succeeded=False, error=outcome.error)))
                else:
                    outcome = QualityBatch_Run(((target, root, model),), action, context).targets[0]
                    if not ProjectTargetGenerated_IsCurrent(requested_model, self._service.catalog, root, target):
                        outcome = replace(outcome, input_sha256='',
                            error='Target provenance changed during check; result is NOT PROVEN')
                outcomes.append(outcome)
            return QualityBatchResult(tuple(outcomes))
        def complete(batch):
            if self._ProjectSnapshot_Current(requested_model, requested_project):
                self._QualityChecks_Complete(batch)
            else:
                self._active_quality_targets = ()
        def error(exception):
            if self._ProjectSnapshot_Current(requested_model, requested_project):
                self._QualityChecks_Error(exception)
            else:
                self._active_quality_targets = ()
        self.Task_Run(quality_run,
                      complete, error,
                      line_callback=self._QualityLine_Append)

    def _QualityLine_Append(self, line: str) -> None:
        if not line.startswith("FCCG_QUALITY|"):
            self._BuildLine_Append(line)
            return
        event = json.loads(line.partition("|")[2])
        target = event["target"]
        kind = event["kind"]
        if kind == "line":
            self.build_page.BuildDetailLog_Append(f"[{target}] {event['line']}")
            self._BuildLine_Append(f"[{target}] {event['line']}")
        elif kind == "progress":
            text = f"{event['stage']} {event['current']}/{event['total']} {event['subject']}"
            self.build_page.TargetQualityProgress_Set(target, event["fraction"], text)
            self.build_page.BuildLog_Append(f"[{target}] {text}")
        else:
            done = kind == "done"
            succeeded = event.get("succeeded", False)
            text = self._translator.Text_Get("quality.target." + (
                "completed" if succeeded else "failed" if done else "running"))
            if event.get("error"):
                text += "\n" + event["error"]
            bar = self.build_page.target_quality_progress[target]
            fraction = (0.99 if succeeded else max(0, bar.value()) / 1000) if done else None
            self.build_page.TargetQualityProgress_Set(target, fraction, text)
            self.build_page.BuildLog_Append(f"[{target}] {text}")

    def _QualityChecks_Complete(self, batch: QualityBatchResult) -> None:
        unavailable = {}
        for outcome in batch.targets:
            result = outcome.result
            if result is None:
                unavailable[outcome.target] = "unavailable"
                continue
            details = "> " + " ".join(result.command) + "\n" + result.output
            if outcome.error:
                details += "\n" + outcome.error
            try:
                if (outcome.target == "flight"
                        and result.action == BuildAction.POWER10_CHECK and not outcome.error):
                    Power10Report_Save(outcome.root, Power10Report_Create(
                        outcome.root, outcome.model, result.output, result.return_code))
                QualityResult_Save(outcome.root, task=result.action.value,
                    succeeded=outcome.succeeded, duration=outcome.duration,
                    summary=self._QualitySummary_Get(result, outcome.root, outcome.target) + ("; " + outcome.error if outcome.error else ""),
                    input_sha256=outcome.input_sha256, command=result.command, details=details)
            except (OSError, ValueError) as error:
                # A gate outcome without durable evidence is not displayed green.
                self.build_page.BuildDetailLog_Append(f"[{outcome.target}] {error}")
                self.build_page.TargetQualityProgress_Set(outcome.target, 0.99, str(error))
                batch.evidence_saved = False
                unavailable[outcome.target] = "unavailable"
        self._TargetQualityResults_Refresh()
        for target, state in unavailable.items():
            states = dict(self.build_page._target_quality_states[target])
            states[self._active_quality_action] = state
            self.build_page.TargetQualityResults_Set(target,
                self.build_page._target_quality_records[target], states)
        for outcome in batch.targets:
            if outcome.target not in unavailable and outcome.succeeded:
                self.build_page.TargetQualityProgress_Set(outcome.target, 1.0,
                    self._translator.Text_Get("quality.target.completed"), succeeded=True)
        self._project_state = ProjectLifecycleState.READY if batch.succeeded else ProjectLifecycleState.ERROR
        self.status_label.setText(self._translator.Text_Get("quality.target.completed" if batch.succeeded else "quality.target.failed"))
        self.power10_export_button.setEnabled(self._project_root is not None and
            Power10Report_Load(self._project_root / FLIGHT_DIRECTORY) is not None)
        self._active_quality_targets = ()

    def _QualityChecks_Error(self, error: object) -> None:
        self.build_page.BuildDetailLog_Append(str(error))
        self._TargetQualityResults_Refresh()
        self._project_state = ProjectLifecycleState.ERROR
        self._active_quality_targets = ()



    def _TargetAction_Request(self, action_text: str) -> None:
        target, separator, operation = action_text.partition("_")
        if not separator or target not in {"flight", "ground"}:
            return
        if self._project_root is None:
            self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
            return
        directory_name = "Flight_Controller" if target == "flight" else "Ground_Station"
        output_policy = WorkspacePolicy(self._project_root)
        target_root = output_policy.Path_Resolve(self._project_root / directory_name, allow_root=False)
        if not (target_root / "Makefile").is_file():
            self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
            return
        if operation in {"open_vscode", "open_folder"}:
            destination = (
                target_root / f"{directory_name}.code-workspace"
                if operation == "open_vscode" else target_root
            )
            if not destination.exists():
                self._Error_Show(self._translator.Text_Get("error.generate_before_open"))
                return
            opened = (
                self._VsCodeWorkspace_Launch(destination).succeeded
                if operation == "open_vscode" else
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(destination)))
            )
            if not opened:
                self._Error_Show(self._translator.Text_Get(
                    "error.open_generated_project", path=str(destination)
                ))
            return
        if operation == "artifact_check":
            artifact = target_root / "build" / (
                "ground.elf" if target == "ground" else ""
            )
            found = artifact.is_file() if target == "ground" else any(
                (target_root / "build").rglob("*.elf")
            )
            self.build_page.BuildLog_Append(
                f"{directory_name}: {'ELF present' if found else 'no ELF artifact'}; integrity NOT CHECKED"
            )
            return
        if operation not in {"build", "clean"}:
            return
        action = BuildAction.BUILD if operation == "build" else BuildAction.CLEAN
        authority_model = deepcopy(self._model)
        selected_model = deepcopy(self._model)
        if target == "ground":
            selected_model.build = selected_model.ground_target.build
        self.build_page.BuildLog_Set("")

        def run(context) -> BuildResult:
            if action == BuildAction.CLEAN:
                build_root = output_policy.Path_Resolve(target_root / "build", allow_root=False)
                if build_root.exists():
                    if not build_root.is_dir() or build_root.is_symlink():
                        raise ValueError("Target build path is not a normal directory")
                    shutil.rmtree(build_root)
                return BuildResult(action, ("clean", str(build_root)), 0, "Build directory cleaned")
            if not ProjectTargetGenerated_IsCurrent(authority_model, self._service.catalog, target_root, target):
                raise ValueError(self._translator.Text_Get('target.status.stale'))
            runner = BuildRunner(output_policy)
            def progress_report(progress: BuildProgress) -> None:
                total = progress.total_steps + 1  # the actual artifact audit
                context.Progress_Report(progress.completed_steps / total, "status.build_running")
                if progress.stage == "PLAN":
                    context.Line_Report(f"FCCG_UI_PLAN|{total}|{progress.stage_total}")
                else:
                    context.Line_Report(f"FCCG_UI_PROGRESS|{progress.stage}|{progress.stage_completed}|"
                                        f"{progress.stage_total}|{progress.subject}")
            built = runner.Target_Run(selected_model, target_root,
                context.token if hasattr(context, "token") else context,
                line_callback=context.Line_Report, progress_callback=progress_report)
            command = built.command
            environment = runner._Environment_Get(selected_model, action)
            return_code, lines = built.return_code, [built.output]
            if return_code == 0:
                context.Line_Report(f"FCCG_UI_PROGRESS|AUDIT|0|1|{target}_artifact_audit")
                try:
                    if target == "ground":
                        elf = target_root / "build/ground.elf"
                        mcu_id = selected_model.ground_target.mcu
                    else:
                        release = (target_root / "build/FCCG"
                                   / selected_model.build.target_profile / "Release")
                        if selected_model.build.memory_layout != "legacy":
                            release /= selected_model.build.memory_layout
                        artifacts = tuple(release.glob("*.elf"))
                        if len(artifacts) != 1:
                            raise ValueError("Flight build has no unique Release ELF")
                        elf = artifacts[0]
                        mcu_id = selected_model.mcu
                    exact = self._service.catalog.Component_Get(mcu_id)
                    linker = target_root / exact.build.linker_script
                    if (target == "ground" and selected_model.ground_target.hardware.hal_cmsis_source_policy
                            == "imported_tree_authoritative"):
                        graph = json.loads((target_root / "Generated/ground_source_graph.json").read_text(encoding="utf8"))
                        if not isinstance(graph, dict) or not isinstance(graph.get("linker_script"), str):
                            raise ValueError("Imported Ground source graph has no selected linker script")
                        relative = output_policy.RelativePath_Validate(graph["linker_script"])
                        linker = WorkspacePolicy(target_root).Path_Resolve(relative.as_posix(), allow_root=False)
                    audit = BuildAudit_Run(
                        elf, elf.with_suffix(".map"),
                        linker,
                        target_root / "build", exact.metadata,
                        toolchain_prefix=selected_model.build.toolchain_prefix,
                        environment=environment,
                    )
                    audit_line = (
                        "Target static audit: "
                        + (", ".join(audit.errors) if audit.errors else "PASS")
                        + " | " + ", ".join(
                            f"{region.name} {region.occupied_bytes}/{region.official_bytes} B"
                            for region in audit.regions
                        )
                    )
                    context.Line_Report(audit_line)
                    lines.append(audit_line + "\n")
                    if audit.errors:
                        return_code = 1
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    context.Line_Report(f"Target static audit failed: {error}")
                    lines.append(f"Target static audit failed: {error}\n")
                    return_code = 1
                context.Progress_Report(0.99, "status.build_running")
                context.Line_Report(f"FCCG_UI_PROGRESS|AUDIT|1|1|{target}_artifact_audit")
            return BuildResult(action, command, return_code, "".join(lines),
                               built.plan, built.completed_steps, live_streamed=True)

        self.Task_Run(
            run, self._TargetBuild_Complete, self._Build_Error,
            indeterminate=False, line_callback=self._BuildLine_Append,
        )

    def _TargetBuild_Complete(self, result: BuildResult) -> None:
        self.status_label.setText(
            self._translator.Text_Get(
                "status.build_succeeded" if result.succeeded else "status.build_failed",
                action=result.action.value,
            )
        )
        if not result.succeeded:
            self._Error_Show(
                self._translator.Text_Get("error.build_failed_summary"), result.output
            )

    def _Attachments_Open(self) -> None:
        from silverstar_fccg.project.folder_contract import AttachmentsDirectory_Ensure
        if self._project_root is None:
            self._Error_Show("请先打开或保存工程 / Open or save a project first")
            return
        try:
            directory = AttachmentsDirectory_Ensure(self._project_root)
        except (OSError, ValueError) as exc:
            self._Error_Show(str(exc))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self._Error_Show("无法打开附加资料目录 / Cannot open Attachments directory")

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
            self._project_root / FLIGHT_DIRECTORY / f"{FLIGHT_DIRECTORY}.code-workspace"
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
        passed = result.succeeded
        if result.action == BuildAction.POWER10_CHECK:
            passed = Power10TextPassed_Is(result.output, result.return_code)
            if self._project_root is not None:
                try:
                    root = self._project_root / FLIGHT_DIRECTORY
                    Power10Report_Save(root, Power10Report_Create(root, self._model, result.output, result.return_code))
                    self.power10_export_button.setEnabled(True)
                except (OSError, ValueError) as error:
                    self.build_page.BuildLog_Append(str(error))
        if raw_output and not result.live_streamed:
            self.build_page.BuildLog_Append(raw_output)
        self.build_page.BuildLog_Append(f"> {command_text}")
        key = "status.build_succeeded" if passed else "status.build_failed"
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
            if passed
            else ProjectLifecycleState.ERROR
        )
        self._QualityResult_Record(
            result.action,
            passed,
            self._QualitySummary_Get(result, self._project_root / FLIGHT_DIRECTORY if self._project_root else None),
        )
        if not passed:
            self.build_page.advanced_section.toggle_button.setChecked(True)
            self._Error_Show(
                self._translator.Text_Get(
                    self._BuildFailureSummaryKey_Get(result.action)
                ),
                raw_output,
            )
        else:
            self._Project_Refresh()
            if result.action == BuildAction.POWER10_CHECK:
                # Commit terminal progress before the modal dialog's event loop.
                QTimer.singleShot(0, self, lambda: self._MessageBox_Exec(
                    QMessageBox.Icon.Information,
                    self._translator.Text_Get("action.power10_check"),
                    self._translator.Text_Get("power10.review_pending"), details=raw_output))
        self._active_build_action = None

    def _SystemLog_Show(self) -> None:
        existing = getattr(self, "_system_log_dialog", None)
        if existing is not None:
            existing.show()
            existing.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translator.Text_Get("action.system_log"))
        dialog.resize(1000, 640)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setObjectName("systemLogOutput")
        text.setReadOnly(True)
        output = self.build_page.build_log.toPlainText()
        details = self.build_page.build_detail_log.toPlainText()
        report = None
        if self._project_root is not None:
            root = self._project_root / FLIGHT_DIRECTORY
            candidate = Power10Report_Load(root)
            if Power10Report_Current_Is(root, self._model, candidate):
                report = candidate
        text.setPlainText("\n\n".join(filter(None, (
            output, details, Power10Report_Csv(report) if report else ""))))
        layout.addWidget(text)
        export = QPushButton(self._translator.Text_Get("power10.export"))
        export.setObjectName("systemLogExport")
        export.setEnabled(report is not None)
        export.clicked.connect(self._Power10Report_Export)
        layout.addWidget(export)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda: setattr(self, "_system_log_dialog", None))
        self._system_log_dialog = dialog
        dialog.show()

    def _Power10Report_Export(self) -> None:
        if self._project_root is None:
            return
        root = self._project_root / FLIGHT_DIRECTORY
        report = Power10Report_Load(root)
        if not Power10Report_Current_Is(root, self._model, report):
            self._Error_Show(self._translator.Text_Get("power10.report_stale"))
            return
        destination, _ = QFileDialog.getSaveFileName(self,
            self._translator.Text_Get("power10.export"), str(self._project_root / "Power10-review.csv"), "CSV (*.csv)")
        if not destination:
            return
        try:
            path = Path(destination)
            WorkspacePolicy(path.parent).Text_AtomicWrite(path.name, "\ufeff" + Power10Report_Csv(report))
        except (OSError, ValueError) as error:
            self._Error_Show(self._translator.Text_Get("power10.export_failed"), str(error))

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
            if stage == "UNMEASURED":
                text = self._translator.Text_Get("build.progress.unmeasured", count=current)
                self.status_label.setText(text)
                self.build_page.BuildLog_Append(text)
                return
            if stage == "NO_WORK":
                text = self._translator.Text_Get("build.progress.no_work")
                self.status_label.setText(text)
                self.build_page.BuildLog_Append(text)
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
            BuildAction.STACK_REPORT,
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
            BuildAction.STACK_REPORT: "error.stack_report_failed_summary",
        }.get(action, "error.build_failed_summary")

    @staticmethod
    def _QualitySummary_Get(result: BuildResult, root: Path | None = None, target: str = 'flight') -> str:
        if result.action == BuildAction.STACK_REPORT:
            return (ArtifactStackReportSummary_Encode(result.output, root) if root else '') or 'stack_report_unverified'
        if result.action == BuildAction.POWER10_CHECK:
            review_state = "FAIL" if "POWER10_CONTRACT_REVIEW|FAIL|" in result.output else "NOT_PROVEN"
            return f"POWER10_CONTRACT_REVIEW|{review_state}|manual_acceptance_pending; " + (
                "text_checks_passed" if Power10TextPassed_Is(result.output, result.return_code)
                else "text_checks_failed")
        if result.action == BuildAction.ARTIFACT_CHECK:
            report = ArtifactMemoryReportSummary_Encode(result.output, root, target) if root else ''
            if report:
                return report
            if 'FIRMWARE_MEMORY_REPORT|' in result.output:
                return 'memory_report_unverified'
            memory = ArtifactMemorySummary_Encode(result.output)
            if memory:
                return memory
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
            BuildAction.STACK_REPORT,
        } or self._project_root is None:
            return
        duration = (
            time.perf_counter() - self._build_started_at
            if self._build_started_at > 0.0
            else 0.0
        )
        try:
            record = self._service.QualityResult_Record(
                self._project_root / FLIGHT_DIRECTORY,
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
            for saved in self._service.QualityResults_Get(
                self._project_root / FLIGHT_DIRECTORY
            )
        }
        records[record.task] = record
        self.build_page.QualityResults_Set(records.values())

    def Task_Run(
        self,
        function: Callable[[Any], Any],
        result_callback: Callable[[Any], None],
        error_callback: Callable[[object], None] | None = None,
        *,
        indeterminate: bool = True,
        line_callback: Callable[[str], None] | None = None,
        progress_range: tuple[float, float] = (0.0, 1.0),
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
        self._task_progress_range = progress_range
        self._last_task_progress = round(progress_range[0] * 1000)
        self._task_indeterminate = indeterminate
        worker.signals.progress.connect(self._Task_Progress)
        worker.signals.line.connect(self._Task_Line)
        worker.signals.result.connect(self._Task_Result)
        worker.signals.error.connect(self._Task_Error)
        worker.signals.cancelled.connect(self._Task_Cancelled)
        worker.signals.finished.connect(self._Task_Finish)
        self.progress_bar.setRange(0, 0 if indeterminate else 1000)
        if not indeterminate:
            self.progress_bar.setValue(self._last_task_progress)
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
        # A completed phase is not a successful task; only _Task_Finish may
        # show 100%. A real report replaces the initial unknown-duration busy state.
        start, end = self._task_progress_range
        fraction = start + (end - start) * max(0.0, min(1.0, progress))
        self._last_task_progress = max(self._last_task_progress, min(999, int(
            fraction * 1000
        )))
        if not self._task_indeterminate or progress > 0.0:
            self._task_indeterminate = False
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(self._last_task_progress)
        self.status_label.setText(self._translator.Text_Get(code))

    def _Task_Result(self, result: Any) -> None:
        self._worker_outcome = ("result", result, "")

    def _Task_Line(self, line: str) -> None:
        progress_event = TaskProgressEvent_Parse(line)
        if progress_event is not None:
            # A parsed event has a positive total; an isolated 0% report does not.
            self._task_indeterminate = False
            completed = (0 if progress_event.state == TaskProgressState.PLAN else
                         progress_event.current - 1 if progress_event.state == TaskProgressState.BEGIN else
                         progress_event.current)
            self._Task_Progress(completed / progress_event.total, "status.task_running")
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
        self._QualityChecks_Cancel()

    def _QualityChecks_Cancel(self) -> None:
        targets = getattr(self, "_active_quality_targets", ())
        for target in targets:
            states = dict(self.build_page._target_quality_states[target])
            states[self._active_quality_action] = "cancelled"
            self.build_page.TargetQualityResults_Set(target,
                self.build_page._target_quality_records[target], states)
            self.build_page.TargetQualityProgress_Set(target, 0.0,
                self._translator.Text_Get("status.task_cancelled"))
        self._active_quality_targets = ()
        if targets:
            self._project_state = ProjectLifecycleState.ERROR

    def _Task_Finish(self) -> None:
        worker = self._active_worker
        closing = self._close_after_worker
        result_callback = self._worker_result_callback
        error_callback = self._worker_error_callback
        outcome = self._worker_outcome
        if worker is not None and worker.context.cancelled:
            outcome = ("cancelled", None, "")
            self.status_label.setText(self._translator.Text_Get("status.task_cancelled"))
            self._QualityChecks_Cancel()
        self._active_worker = None
        self._worker_result_callback = None
        self._worker_error_callback = None
        self._worker_line_callback = None
        self._worker_outcome = None
        self._Actions_SetEnabled(True)
        dispatched = False
        self._completion_worker = worker
        try:
            if not closing:
                dispatched = self._TaskOutcome_Dispatch(
                    outcome, result_callback, error_callback)
        finally:
            self._completion_worker = None
        if worker is not None and worker.context.cancelled:
            outcome = ("cancelled", None, "")
            self.status_label.setText(self._translator.Text_Get("status.task_cancelled"))
            self._QualityChecks_Cancel()
        succeeded = bool(
            dispatched
            and
            outcome is not None
            and outcome[0] == "result"
            and bool(getattr(outcome[1], "succeeded", True))
        )
        if succeeded and isinstance(outcome[1], BuildResult):
            result = outcome[1]
            if result.action == BuildAction.POWER10_CHECK:
                succeeded = Power10TextPassed_Is(result.output, result.return_code)
        if worker is not None:
            self._retired_workers.append(worker)
            QTimer.singleShot(
                0, lambda retired=worker: self._TaskWorker_Release(retired))
        # A result callback may start the next phase or a separate operation.
        # Its progress and control state now belong to the new worker.
        if self._active_worker is not None:
            return
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
        self._progress_hide_timer.start(350)
        if closing:
            QTimer.singleShot(0, self, self.close)

    def _TaskOutcome_Dispatch(
        self,
        outcome: tuple[str, object, str] | None,
        result_callback: Callable[[Any], None] | None,
        error_callback: Callable[[object], None] | None,
    ) -> bool:
        if outcome is None or outcome[0] == "cancelled":
            return False
        try:
            if outcome[0] == "result":
                if result_callback is not None:
                    result_callback(outcome[1])
            elif error_callback is not None:
                error_callback(outcome[1])
            else:
                self._Error_Show(outcome[1], outcome[2])
            return outcome[0] == "result"
        except Exception as error:
            logging.exception("Background task completion callback failed")
            self._Error_Show(error)
            return False

    def _TaskWorker_Release(self, worker: FunctionWorker) -> None:
        if worker in self._retired_workers:
            self._retired_workers.remove(worker)

    def _Progress_CompletionHide(self) -> None:
        if self._active_worker is None:
            self.progress_bar.setVisible(False)

    def _Task_Cancel(self) -> None:
        worker = self._active_worker or self._completion_worker
        if worker is not None:
            worker.Worker_Cancel()

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
            self.hardware_workspace,
            self.workflow_page,
            self.board_hardware_page.prepare_button,
            self.board_hardware_page.generate_button,
            self.ground_target_page.generate_button,
            *self.build_page.action_buttons.values(),
            *self.build_page.quality_target_checks.values(),
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
        self._TargetReadiness_Refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, '_header_controls'):
            return
        compact = self.width() < 1180
        if compact == self._header_compact:
            return
        self._header_compact = compact
        if compact:
            self._header_main_layout.removeWidget(self._header_controls)
            self._header_layout.addWidget(self._header_controls)
        else:
            self._header_layout.removeWidget(self._header_controls)
            self._header_main_layout.addWidget(self._header_controls)

    def _HeaderProject_Refresh(self, model: ProjectModel | None = None) -> None:
        displayed_model = model or self._model
        path = str(self._project_root) if self._project_root is not None else "—"
        unsaved = self._ProjectFile_DirtyGet(displayed_model)
        file_status = self._translator.Text_Get('project.file_unsaved' if unsaved else 'project.file_saved')
        self.current_project_value.setText(displayed_model.identity.name + (' · ' + file_status if unsaved else ''))
        self.setWindowTitle(PRODUCT_NAME + (' *' if unsaved else ''))
        self.current_project_value.setToolTip(
            self._translator.Text_Get(
                "project.state_tooltip",
                path=path,
                state=self._translator.Text_Get(
                    f"project.state.{self._project_state.value}"
                ),
            ) + '\n' + file_status
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
        if self._component_views and not self._WorkflowDrafts_Commit():return
        self._translator.Language_Set(language)
        self.legacy_migration_button.setText(self._translator.Text_Get("release.migrate"))
        self.power10_export_button.setText(self._translator.Text_Get("power10.export"))
        self.system_log_button.setText(self._translator.Text_Get("action.system_log"))
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
        self.navigation_sidebar.setFixedWidth(
            max(190, self.navigation_list.sizeHintForColumn(0)
                + 2 * self.navigation_list.frameWidth())
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
        # Every entry point (startup, settings restore, direct application and
        # the combo itself) must present the same selected theme.
        with QSignalBlocker(self.theme_combo):
            self.theme_combo.setCurrentIndex(self.theme_combo.findData(self._theme))
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
        check_box=None,
    ) -> QMessageBox.StandardButton:
        box = self._MessageBox_Create(
            icon, title, text, buttons, default, details=details, check_box=check_box
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
        check_box=None,
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
        if check_box is not None:
            box.setCheckBox(check_box)
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
        self._Workspace_Save()
        if self._active_worker is not None:
            if self._close_after_worker:
                event.ignore()
                return
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
            self._close_after_worker = True
            self._active_worker.Worker_Cancel()
            event.ignore()
            return
        if not self._WorkspaceDrafts_DiscardConfirm():
            # A cancelled close may follow asynchronous worker cancellation.
            # The window remains usable and later results must be publishable.
            self._close_after_worker = False
            event.ignore();return
        self._close_after_worker = True
        event.accept()
