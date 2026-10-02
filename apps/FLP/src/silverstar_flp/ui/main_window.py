from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool, QTimer, QUrl
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
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import FlightDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.path_preferences import (
    ExistingDirectory_Get,
    ExportDirectory_Default,
    PathPreferences,
    ProjectDirectory_Prepare,
)
from silverstar_flp.core.project import (
    Project_Load,
    Project_Save,
    ProjectDecoderProfile,
    ProjectDocument,
)
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.export.service import ExportManifest, FlightExporter
from silverstar_flp.log_open import (
    LogOpenCoordinator,
    LogOpenRequest,
    LogOpenResult,
    LogOpenSourceMode,
)
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayRequest
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.new_project import NewProjectDialog
from silverstar_flp.ui.pages import (
    DataExplorerPage,
    ExportDialog,
    FlightPage,
    ImportDialog,
    OverviewPage,
    ReplayPage,
    StateEstimationPage,
)
from silverstar_flp.ui.plugin_manager import AboutDialog, PluginManagerDialog
from silverstar_flp.ui.theme import Theme_Apply, WindowCaption_Apply
from silverstar_flp.ui.time_range import TimeRangeBar
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox, ProjectHeaderLabel
from silverstar_flp.ui.workers import FunctionWorker


class MainWindow(QMainWindow):
    PAGE_CODES = (
        "page.overview",
        "page.replay",
        "page.flight",
        "page.state_estimation",
        "page.data_explorer",
    )

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        language: str = "zh_CN",
        theme: str = "light",
        initial_path: Path | None = None,
        initial_decoder_path: Path | None = None,
        initial_auto_find: bool = False,
        plugin_manager: TrustedContainerPluginManager | None = None,
        path_preferences: PathPreferences | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._path_preferences = path_preferences or PathPreferences(
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppLocalDataLocation
                )
            )
            / "path_preferences.json"
        )
        self._last_import_directory: Path | None = None
        self._silverstar_project_root: Path | None = None
        self._plugin_manager = plugin_manager or TrustedContainerPluginManager(
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppLocalDataLocation
                )
            )
            / "plugins"
        )
        self._plugin_discovery = self._plugin_manager.Discover()
        self._log_open_coordinator = LogOpenCoordinator(registry)
        self._translator = Translator(language)
        self._theme = theme
        self._dataset: FlightDataset | None = None
        self._log_open_result: LogOpenResult | None = None
        self._replay_store = ReplayResultStore()
        self._channel_resolver: ChannelResolver | None = None
        self._project = ProjectDocument()
        self._project_dirty = False
        self._source_restore_pending = None
        self._source_restore_index = None
        self._pending_new_project_path: Path | None = None
        self._suspend_dirty = False
        self._thread_pool = QThreadPool.globalInstance()
        self._active_worker: FunctionWorker | None = None
        self._worker_error_callback = None
        self._settings = QSettings("SilverStar", "SilverStar_FLP")
        self.setAcceptDrops(True)
        self.setWindowTitle(PRODUCT_NAME)
        self.resize(1480, 920)
        self.setMinimumSize(1000, 700)
        self._Ui_Build()
        self._Menu_Build()
        self.Language_Apply(language)
        self.Theme_Apply(theme)
        if initial_path is not None:
            QTimer.singleShot(
                0,
                lambda: self.Path_Open(
                    initial_path,
                    decoder_path=initial_decoder_path,
                    auto_find=initial_auto_find,
                ),
            )

    def _Ui_Build(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerBar")
        header.setMinimumHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 6, 14, 6)
        header_layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("headerTitle")
        self.title_label.setStyleSheet("font-size: 16px;")
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        self.credit_label = QLabel()
        self.credit_label.setObjectName("headerCredit")
        self.project_caption_label = QLabel()
        self.project_caption_label.setObjectName("headerControlLabel")
        self.project_name_label = ProjectHeaderLabel()
        self.project_name_label.setObjectName("headerProject")
        self.language_label = QLabel()
        self.language_label.setObjectName("headerControlLabel")
        self.language_combo = StandardComboBox()
        self.language_combo.setObjectName("headerLanguageCombo")
        self.language_combo.view().setObjectName("headerComboPopup")
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        self.language_combo.currentIndexChanged.connect(self._Language_Selected)
        self.theme_label = QLabel()
        self.theme_label.setObjectName("headerControlLabel")
        self.theme_combo = StandardComboBox()
        self.theme_combo.setObjectName("headerThemeCombo")
        self.theme_combo.view().setObjectName("headerComboPopup")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.currentIndexChanged.connect(self._Theme_Selected)
        identity_row = header_layout
        identity_row.addWidget(self.title_label)
        identity_row.addWidget(self.version_label)
        identity_row.addWidget(self.credit_label)
        identity_row.addWidget(self.project_caption_label)
        identity_row.addWidget(self.project_name_label, 1)
        identity_row.addWidget(self.language_label)
        identity_row.addWidget(self.language_combo)
        identity_row.addWidget(self.theme_label)
        identity_row.addWidget(self.theme_combo)
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
        for page_code in self.PAGE_CODES:
            item = QListWidgetItem(page_code)
            item.setData(Qt.ItemDataRole.UserRole, page_code)
            self.navigation_list.addItem(item)
        self.navigation_list.currentRowChanged.connect(self._Page_Select)
        sidebar_layout.addWidget(self.navigation_list)
        body_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.time_range = TimeRangeBar(self._translator)
        self.time_range.rangeChanged.connect(self._TimeRange_Changed)
        content_layout.addWidget(self.time_range)
        self.pages = QStackedWidget()
        self.overview_page = OverviewPage(self._translator)
        self.replay_page = ReplayPage(self._translator, self._registry)
        self.flight_page = FlightPage(self._translator)
        self.state_estimation_page = StateEstimationPage(
            self._translator,
            self._registry,
        )
        self.explorer_page = DataExplorerPage(self._translator)
        self._page_widgets = (
            self.overview_page,
            self.replay_page,
            self.flight_page,
            self.state_estimation_page,
            self.explorer_page,
        )
        for page in self._page_widgets:
            self.pages.addWidget(page)
        content_layout.addWidget(self.pages, 1)
        body_layout.addWidget(content, 1)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(central)

        status_bar = QStatusBar()
        self.status_label = QLabel()
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self._Task_Cancel)
        self.cancel_button.setVisible(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedWidth(240)
        self.progress_bar.setVisible(False)
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.cancel_button)
        status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status_bar)

        self.replay_page.replayRequested.connect(self._Replay_Start)
        self.replay_page.analysisSourceRequested.connect(self._AnalysisSource_Set)
        self.replay_page.configurationChanged.connect(self._Project_MarkDirty)
        self.import_dialog = ImportDialog(self._translator, self)
        self.import_dialog.importRequested.connect(self.LogPair_Open)
        self.import_dialog.folderSearchRequested.connect(self._FolderSearch_Start)
        self.import_dialog.rejected.connect(self._PendingProject_Cancel)
        self.export_dialog = ExportDialog(self._translator, self)
        self.export_dialog.exportRequested.connect(self._Export_Start)
        self.export_dialog.manifestOpenRequested.connect(self._ExportManifest_Open)
        self.plugin_manager_dialog = PluginManagerDialog(self._translator, self)
        self.plugin_manager_dialog.installRequested.connect(self._Plugin_InstallDialog_Show)
        self.plugin_manager_dialog.refreshRequested.connect(self._Plugins_Refresh)
        self.about_dialog = AboutDialog(self._translator, self)
        self._Plugins_Refresh(show_message=False)
        self.navigation_list.setCurrentRow(0)

    def _Menu_Build(self) -> None:
        self._menu_bar = self.menuBar()
        self._menu_bar.setObjectName("mainMenuBar")
        self.file_menu = QMenu(self._menu_bar)
        self.plugins_menu = QMenu(self._menu_bar)
        self.help_menu = QMenu(self._menu_bar)
        self._menu_actions = [
            self._menu_bar.addMenu(menu)
            for menu in (self.file_menu, self.plugins_menu, self.help_menu)
        ]
        self.default_root_action = QAction(self)
        self.default_root_action.triggered.connect(self._DefaultProjectRoot_Select)
        self.new_project_action = QAction(self)
        self.new_project_action.setShortcut("Ctrl+N")
        self.new_project_action.triggered.connect(self._Project_New)
        self.open_project_action = QAction(self)
        self.open_project_action.setShortcut("Ctrl+O")
        self.open_project_action.triggered.connect(self._ProjectDialog_Open)
        self.open_silverstar_project_action = QAction(self)
        self.open_silverstar_project_action.triggered.connect(
            self._SilverStarProjectDialog_Open
        )
        self.save_project_action = QAction(self)
        self.save_project_action.setShortcut("Ctrl+S")
        self.save_project_action.triggered.connect(self._Project_Save)
        self.save_project_as_action = QAction(self)
        self.save_project_as_action.setShortcut("Ctrl+Shift+S")
        self.save_project_as_action.triggered.connect(self._Project_SaveAs)
        self.import_action = QAction(self)
        self.import_action.triggered.connect(self._ImportDialog_Show)
        self.export_action = QAction(self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._ExportDialog_Show)
        self.exit_action = QAction(self)
        self.exit_action.triggered.connect(self.close)
        self.manage_plugins_action = QAction(self)
        self.manage_plugins_action.triggered.connect(self._PluginManager_Show)
        self.install_plugin_action = QAction(self)
        self.install_plugin_action.triggered.connect(self._PluginManager_Show)
        self.refresh_plugins_action = QAction(self)
        self.refresh_plugins_action.triggered.connect(
            lambda _checked=False: self._Plugins_Refresh()
        )
        self.about_action = QAction(self)
        self.about_action.triggered.connect(self._About_Show)
        self.file_menu.addAction(self.new_project_action)
        self.file_menu.addAction(self.open_project_action)
        self.file_menu.addAction(self.open_silverstar_project_action)
        self.file_menu.addAction(self.save_project_action)
        self.file_menu.addAction(self.save_project_as_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.default_root_action)
        self.file_menu.addAction(self.import_action)
        self.file_menu.addAction(self.export_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self.plugins_menu.addAction(self.manage_plugins_action)
        self.plugins_menu.addAction(self.install_plugin_action)
        self.plugins_menu.addAction(self.refresh_plugins_action)
        self.help_menu.addAction(self.about_action)

    def _PluginManager_Show(self) -> None:
        self.plugin_manager_dialog.Registry_Set(self._registry, self._plugin_discovery)
        self.plugin_manager_dialog.open()

    def _About_Show(self) -> None:
        self.about_dialog.open()

    def _Plugin_InstallDialog_Show(self) -> None:
        source_name, _ = QFileDialog.getOpenFileName(
            self.plugin_manager_dialog if self.plugin_manager_dialog.isVisible() else self,
            self._translator.Text_Get("dialog.plugin_install.title"),
            "",
            self._translator.Text_Get("dialog.plugin_install.filter"),
        )
        if not source_name:
            return
        answer = QMessageBox.warning(
            self,
            self._translator.Text_Get("dialog.plugin_trust.title"),
            self._translator.Text_Get("dialog.plugin_trust.message").format(path=source_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.Plugin_Install(Path(source_name), explicitly_trusted=True)
        except DecoderProfileError as exc:
            QMessageBox.critical(
                self,
                self._translator.Text_Get("error.title"),
                self._translator.Text_Get("plugin.install.rejected").format(reason=str(exc)),
            )
            return
        QMessageBox.information(
            self,
            self._translator.Text_Get("dialog.plugin_install.title"),
            self._translator.Text_Get("plugin.install.success_restart"),
        )

    def Plugin_Install(self, path: Path, *, explicitly_trusted: bool) -> None:
        """Install only a validated container package; never execute package Python."""
        self._plugin_manager.Package_Install(path, explicitly_trusted=explicitly_trusted)
        self._Plugins_Refresh(show_message=False)

    def _Plugins_Refresh(self, *, show_message: bool = True) -> None:
        """Rediscover inert packages without mutating the active runtime registry."""
        self._plugin_discovery = self._plugin_manager.Discover()
        if hasattr(self, "plugin_manager_dialog"):
            self.plugin_manager_dialog.Registry_Set(self._registry, self._plugin_discovery)
        if show_message:
            self.status_label.setText(self._translator.Text_Get("plugin.refresh.complete"))

    def _Page_Select(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.pages.setCurrentIndex(index)
            self.time_range.setVisible(index in (2, 3))
            if self._dataset is not None and not self._suspend_dirty:
                previous = self._project.ui_state.get("page_index", 0)
                if previous != index:
                    self._Project_MarkDirty()

    def _DefaultProjectRoot_Select(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("action.default_project_root"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
        )
        if selected:
            try:
                self._path_preferences.DefaultProjectRoot_Set(Path(selected))
            except (OSError, ValueError) as error:
                self._Error_Show(str(error))

    def _ImportDirectory_Get(self) -> Path:
        project_path = self._pending_new_project_path or self._project.project_path
        if project_path is not None:
            return project_path.parent
        return ExistingDirectory_Get(
            self._path_preferences.DefaultProjectRoot_Get(), self._last_import_directory
        )

    def _ImportDialog_Show(self) -> None:
        self.import_dialog.Folder_Set(self._ImportDirectory_Get())
        self.import_dialog.result_label.hide()
        self.import_dialog.open()

    def _ExportDialog_Show(self) -> None:
        if self._dataset is None:
            return
        self.export_dialog.OutputDirectory_Set(self._ExportDirectory_Default())
        recorded_name = (
            self._channel_resolver.RecordedNavigationSource_Get()
            if self._channel_resolver is not None else "N/A"
        ).replace("KF_6", "KF6")
        sources = [(
            self._replay_store.RECORDED_SOURCE_ID,
            self._translator.Text_Get(
                "export.source_recorded", algorithm=recorded_name
            ),
        )]
        sources.extend((
            entry.source_id,
            self._translator.Text_Get(
                "export.source_replay",
                index=entry.run_index,
                algorithm=entry.algorithm_name,
            ),
        ) for entry in self._replay_store.Entries_Get() if entry.analysis_ready)
        self.export_dialog.Sources_Set(tuple(sources))
        self.export_dialog.Result_Clear()
        model = self.time_range.controller.model
        self.export_dialog.Range_Set((model.start, model.end), model.mission_duration)
        self.export_dialog.open()

    def _ExportDirectory_Default(self) -> Path:
        log_path = self._dataset.source_path if self._dataset is not None else Path.cwd() / "Log"
        if self._silverstar_project_root is not None and self._dataset is not None:
            log_root = self._silverstar_project_root / "Log"
            try:
                log_path.resolve().relative_to(log_root.resolve())
            except ValueError:
                pass
            else:
                return log_path.parent / f"{log_path.stem}_Export"
        return ExportDirectory_Default(log_path, self._project.project_path)

    def _Language_Selected(self) -> None:
        language = self.language_combo.currentData()
        if language is not None:
            self.Language_Apply(str(language))

    def _Theme_Selected(self) -> None:
        theme = self.theme_combo.currentData()
        if theme is not None:
            self.Theme_Apply(str(theme))

    def Path_Open(
        self,
        path: Path,
        *,
        decoder_path: Path | None = None,
        auto_find: bool = False,
    ) -> None:
        source_path = Path(path)
        if source_path.is_dir():
            if (source_path / "SilverStar.ssproject").is_file():
                self.SilverStarProjectRoot_Open(source_path)
            else:
                self.import_dialog.Folder_Set(source_path)
                self._FolderSearch_Start(source_path)
            return
        suffix = source_path.suffix.casefold()
        if suffix == ".ssflp":
            self._Project_Open(source_path)
            return
        if suffix == ".ssdecoder":
            self.import_dialog.Paths_Set(decoder_path=source_path)
            self.import_dialog.open()
            return
        if suffix not in (".bin", ".sslog"):
            self._Error_Show(f"log_open_extension_unsupported:{suffix}")
            return
        if decoder_path is not None:
            self.LogPair_Open(source_path, decoder_path)
        elif auto_find:
            self.Log_Open(
                source_path,
                auto_find=True,
                source_mode=LogOpenSourceMode.FOLDER_SEARCH,
            )
        else:
            self.import_dialog.Paths_Set(log_path=source_path)
            self.import_dialog.open()

    def LogPair_Open(self, log_path: Path, decoder_path: Path) -> None:
        self.Log_Open(
            log_path,
            decoder_path=decoder_path,
            source_mode=LogOpenSourceMode.MANUAL,
        )

    def Log_Open(
        self,
        path: Path,
        *,
        decoder_path: Path | None = None,
        auto_find: bool = False,
        source_mode: LogOpenSourceMode = LogOpenSourceMode.MANUAL,
        project: ProjectDocument | None = None,
    ) -> None:
        if self._active_worker is not None:
            self._Error_Show("another_background_task_is_running")
            return
        if project is None and not self._ProjectChanges_Confirm():
            return
        source_path = Path(path)
        target_project = project or self._Project_ForImport()
        mark_dirty_on_success = project is None and self._pending_new_project_path is None
        request = LogOpenRequest(
            log_path=source_path,
            decoder_package_path=decoder_path,
            auto_find=auto_find,
            task_directory=source_path.parent if auto_find else None,
            source_mode=source_mode,
        )
        self.status_label.setText(self._translator.Text_Get("status.loading"))
        worker = FunctionWorker(lambda context: self._log_open_coordinator.Open(request, context))
        self._Task_Start(
            worker,
            lambda result: self._LogOpenResult_Set(
                result,
                target_project,
                mark_dirty=mark_dirty_on_success,
                silverstar_root=self._SilverStarRootForPair_Get(source_path, decoder_path),
            ),
            self._LogOpen_Error,
        )

    def _ProjectLogOpen_Run(
        self,
        project: ProjectDocument,
        request: LogOpenRequest,
        context: object,
    ) -> LogOpenResult:
        result = self._log_open_coordinator.Open(request, context)
        expected = project.decoder_profile
        if expected is None:
            raise ValueError("project_decoder_profile_missing")
        actual = self._DecoderProfile_Build(result)
        comparisons = (
            (expected.package_sha256, actual.package_sha256),
            (
                expected.generation_profile_sha256,
                actual.generation_profile_sha256,
            ),
            (expected.record_catalog_sha256, actual.record_catalog_sha256),
            (expected.record_catalog_hash_128, actual.record_catalog_hash_128),
            (
                expected.project_semantics_sha256,
                actual.project_semantics_sha256,
            ),
            (
                expected.project_semantics_hash_128,
                actual.project_semantics_hash_128,
            ),
            (expected.container_plugin_id, actual.container_plugin_id),
            (expected.container_plugin_version, actual.container_plugin_version),
            (expected.exact_match_mode, actual.exact_match_mode),
        )
        if any(saved != opened for saved, opened in comparisons):
            raise ValueError("project_decoder_identity_mismatch")
        return result

    def _Project_Open(self, path: Path) -> None:
        if self._active_worker is not None:
            self._Error_Show("another_background_task_is_running")
            return
        try:
            project = Project_Load(Path(path))
            if project.decoder_profile is None:
                raise ValueError("project_decoder_profile_missing")
            decoder_source_path = project.DecoderSourcePath_Resolve()
            log_path = project.LogPath_Resolve()
            if not log_path.is_file():
                raise ValueError(f"project_log_missing:{log_path}")
            if decoder_source_path is None or not decoder_source_path.is_file():
                raise ValueError(f"project_decoder_missing:{decoder_source_path}")
            request = LogOpenRequest(
                log_path=log_path,
                decoder_package_path=decoder_source_path,
                task_directory=(
                    decoder_source_path.parent
                    if decoder_source_path is not None
                    else project.project_path.parent
                    if project.project_path is not None
                    else None
                ),
                source_mode=LogOpenSourceMode.PROJECT,
            )
        except Exception as exc:
            logging.exception("Project open failed")
            self._Error_Show(str(exc))
            return
        self.status_label.setText(self._translator.Text_Get("status.loading"))
        worker = FunctionWorker(lambda context: self._ProjectLogOpen_Run(project, request, context))
        self._Task_Start(
            worker,
            lambda result: self._LogOpenResult_Set(result, project, mark_dirty=False,
                silverstar_root=self._SilverStarRootForPair_Get(log_path, decoder_source_path)),
            lambda message: self._Error_Show(message),
        )

    def _FolderSearch_Start(self, folder_path: Path) -> None:
        if self._active_worker is not None:
            self._Error_Show("another_background_task_is_running")
            return
        selected_path = Path(folder_path)
        self.status_label.setText(self._translator.Text_Get("status.searching_pairs"))
        worker = FunctionWorker(
            lambda context: self._log_open_coordinator.PairDiscovery_Run(selected_path)
        )
        self._Task_Start(
            worker,
            self._FolderSearch_Set,
            lambda message: self._Error_Show(message),
        )

    def _SilverStarProjectDialog_Open(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("action.open_silverstar_project"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
        )
        if selected:
            self.SilverStarProjectRoot_Open(Path(selected))

    def SilverStarProjectRoot_Open(self, path: Path) -> None:
        if self._active_worker is not None:
            self._Error_Show("another_background_task_is_running")
            return
        if not self._ProjectChanges_Confirm():
            return
        root = Path(path).resolve()
        if not (root / "SilverStar.ssproject").is_file() or not (root / "Log").is_dir():
            self._Error_Show("silverstar_project_root_invalid")
            return
        self.import_dialog.Folder_Set(root)
        self._FolderSearch_Start(root)

    @staticmethod
    def _SilverStarRootForPair_Get(log_path: Path, decoder_path: Path | None) -> Path | None:
        if decoder_path is None:
            return None
        root = Path(decoder_path).resolve().parent
        if ((root / "SilverStar.ssproject").is_file() and (root / "Log").is_dir()
                and Path(log_path).resolve().is_relative_to(root / "Log")):
            return root
        return None

    def _FolderSearch_Set(self, discovery: object) -> None:
        self.import_dialog.PairDiscovery_Set(discovery)
        self.import_dialog.show()
        self.import_dialog.raise_()
        self.status_label.setText(self._translator.Text_Get("status.ready"))

    def _DecoderProfile_Build(
        self,
        result: LogOpenResult,
    ) -> ProjectDecoderProfile:
        package = result.package
        container = self._registry.LogContainer_Get(package.required_container_plugin_id)
        return ProjectDecoderProfile(
            source_reference=str(result.source_package_path.resolve()),
            cache_reference=result.cache_reference,
            package_sha256=package.package_sha256,
            generation_profile_sha256=package.generation_profile_sha256,
            record_catalog_sha256=package.checksums["record_catalog.json"],
            record_catalog_hash_128=package.record_catalog_hash_128,
            project_semantics_sha256=package.checksums["project_semantics.json"],
            project_semantics_hash_128=package.project_semantics_hash_128,
            container_plugin_id=container.metadata.plugin_id,
            container_plugin_version=container.metadata.version,
            exact_match_mode=result.match_mode,
        )

    def _LogOpenResult_Set(
        self,
        result: LogOpenResult,
        project: ProjectDocument,
        *,
        mark_dirty: bool = False,
        silverstar_root: Path | None = None,
    ) -> None:
        try:
            for configuration in project.replay_configurations.values():
                plugin = self._registry.Algorithm_Get(configuration["algorithm_id"])
                request = ReplayRequest(
                    mode=configuration["mode"],
                    input_source=configuration["input_source"],
                    parameters=configuration["actual_values"],
                    quality_policy_revision=configuration.get("quality_policy_revision"),
                )
                plugin.Parameters_Resolve(result.dataset, request)
                provenance = plugin.ParameterAudit_Get(result.dataset, request)["config_source"]
                if configuration["provenance"] != provenance:
                    raise ValueError("project_parameter_provenance_invalid")
        except (KeyError, ValueError) as exc:
            self._pending_new_project_path = None
            self._Error_Show(str(exc))
            return
        self._last_import_directory = result.dataset.source_path.parent
        project.LogReference_Set(result.dataset.source_path)
        project.decoder_profile = self._DecoderProfile_Build(result)
        if self._pending_new_project_path is not None:
            project.project_path = self._pending_new_project_path
            try:
                Project_Save(project, self._pending_new_project_path)
            except Exception as exc:
                self._pending_new_project_path = None
                logging.exception("Initial project save failed")
                self._Error_Show(str(exc))
                return
            self._pending_new_project_path = None
        self._project = project
        self._silverstar_project_root = silverstar_root or self._SilverStarRootForPair_Get(
            result.dataset.source_path, result.source_package_path)
        self._log_open_result = result
        self._suspend_dirty = True
        try:
            self._Dataset_Set(result.dataset)
            if "draft" in project.replay_configurations:
                try:
                    self.replay_page.Configuration_Set(project.replay_configurations["draft"])
                except ValueError as exc:
                    self._Error_Show(str(exc))
            if "time_range" in project.ui_state:
                self.time_range.State_Restore(project.ui_state["time_range"])
            selected_source = project.ui_state.get("analysis_source", "recorded")
            if isinstance(selected_source, str) and selected_source.startswith("replay:"):
                key = selected_source.removeprefix("replay:")
                configuration = project.replay_configurations.get(key)
                if configuration is not None:
                    self._source_restore_pending = (key, configuration)
            page_index = project.ui_state.get("page_index")
            if isinstance(page_index, int) and 0 <= page_index < self.pages.count():
                self.navigation_list.setCurrentRow(page_index)
        finally:
            self._suspend_dirty = False
        self._Project_SetDirty(mark_dirty)
        self._ProjectHeader_Refresh()

    def _Dataset_Set(self, dataset: FlightDataset) -> None:
        was_suspended = self._suspend_dirty
        self._suspend_dirty = True
        self._dataset = dataset
        self._source_restore_pending = None
        self._source_restore_index = None
        self._replay_store.Clear()
        self._channel_resolver = ChannelResolver(dataset, self._replay_store)
        bounds = self._channel_resolver.MissionReplayBounds_Get()
        self.time_range.Mission_Set((bounds.end_timestamp_us - bounds.start_timestamp_us) * 1e-6)
        self.export_action.setEnabled(True)
        self.status_label.setText(self._DatasetStatus_TextGet(dataset))
        try:
            self._Pages_Refresh()
        finally:
            self._suspend_dirty = was_suspended

    def _DatasetStatus_TextGet(self, dataset: FlightDataset) -> str:
        warning = bool(
            dataset.data_quality is not None and dataset.data_quality.status.value == "warnings"
        )
        semantic_context = dataset.semantic_context
        if semantic_context is None:
            return self._translator.Text_Get(
                ("status.loaded_file_warnings" if warning else "status.loaded_file"),
                name=dataset.source_path.name,
                count=dataset.diagnostics.decoded_record_count,
            )
        identity = semantic_context.PackageIdentity_Get()
        return self._translator.Text_Get(
            ("status.loaded_exact_warnings" if warning else "status.loaded_exact"),
            name=dataset.source_path.name,
            project=semantic_context.Project_Get(),
            firmware=semantic_context.FirmwareVersion_Get(),
            package_hash=identity.package_sha256[:12],
        )

    def _Pages_Refresh(self) -> None:
        if self._dataset is None or self._channel_resolver is None:
            return
        self.overview_page.Dataset_Set(self._dataset)
        self.replay_page.Dataset_Set(self._dataset, self._replay_store)
        self.flight_page.Dataset_Set(self._dataset, self._channel_resolver)
        self.state_estimation_page.Dataset_Set(self._dataset, self._channel_resolver)
        self.explorer_page.Dataset_Set(self._dataset, self._replay_store)
        self._TimeRange_Changed(self.time_range.controller.model)

    def _TimeRange_Changed(self, model) -> None:
        import pyqtgraph as pg
        if self._dataset is None or not hasattr(self, "pages"):
            return
        for page in (self.flight_page, self.state_estimation_page):
            for plot in page.findChildren(pg.PlotWidget):
                plot.setLimits(xMin=model.start, xMax=max(model.end, model.start + .001))
                plot.setXRange(model.start, max(model.end, model.start + .001), padding=0)
        if self._channel_resolver is not None:
            origin = self._channel_resolver.MissionReplayBounds_Get().start_timestamp_us
            self.flight_page.TimeRange_Set(origin + round(model.start * 1e6),
                                           origin + round(model.end * 1e6))
        self.state_estimation_page.TimeRange_Set(model.start, model.end)
        for kind, panel in self.state_estimation_page.navigation_diagnostics.items():
            if kind != "landing":
                panel.TimeRange_Set(model.start, model.end)
        self.state_estimation_page.gnss_integrity.TimeRange_Set(model.start, model.end)
        self._Project_MarkDirty()

    def _Replay_Start(self, algorithm_id: str, request: ReplayRequest) -> None:
        if self._dataset is None:
            self.replay_page.Result_Error(self._translator.Text_Get("status.no_data"))
            return
        plugin = self._registry.Algorithm_Get(algorithm_id)
        dataset = self._dataset
        worker = FunctionWorker(lambda context: plugin.run(dataset, request, context))
        self._Task_Start(
            worker,
            self._Replay_ResultSet,
            self.replay_page.Result_Error,
        )

    def _Replay_ResultSet(self, result: AlgorithmResult) -> None:
        display_name = self._registry.Algorithm_Get(result.algorithm_id).metadata.display_name
        restore_index = self._source_restore_index
        self._source_restore_index = None
        entry = self._replay_store.Result_Add(result, algorithm_name=display_name,
                                              restored_run_index=restore_index)
        if restore_index is not None:
            self._replay_store.ActiveSource_Set(entry.source_id)
        self.replay_page.Result_Set(entry)
        self._Pages_Refresh()
        self.status_label.setText(
            self._translator.Text_Get(
                "replay.complete",
                fidelity=self._translator.Text_Get(
                    f"replay.fidelity.{result.fidelity.value.lower()}"
                ),
            )
        )

    def _AnalysisSource_Set(self, source_id: str) -> None:
        if not self._replay_store.ActiveSource_Set(source_id):
            return
        self._Pages_Refresh()
        self._Project_MarkDirty()
        if self._channel_resolver is not None:
            source = self._channel_resolver.Source_Get(source_id)
            self.status_label.setText(
                self._translator.Text_Get(
                    "status.analysis_source_changed",
                    value=self._translator.Text_Get(f"status.{source.kind.value}"),
                )
            )

    def _Export_Start(self, output_path: Path, options: Any) -> None:
        if self._dataset is None:
            self.export_dialog.Result_Error(self._translator.Text_Get("status.no_data"))
            return
        selected = self.explorer_page.ExportChannels_Get()
        options = replace(options, selected_channels=selected, ui_theme=self._theme,
                          current_range=(self.time_range.controller.model.start,
                                         self.time_range.controller.model.end))
        source_id = options.source_id or self._replay_store.ActiveSource_Get().source_id
        try:
            export_store = self._replay_store.Snapshot_Create(source_id)
        except ValueError as error:
            self.export_dialog.Result_Error(str(error))
            return
        options = replace(options, source_id=source_id)
        dataset = self._dataset
        exporter = FlightExporter(self._registry)
        worker = FunctionWorker(
            lambda context: exporter.export(
                dataset,
                output_path,
                options=options,
                replay_store=export_store,
                context=context,
            )
        )
        self._Task_Start(
            worker,
            self._Export_ResultSet,
            self.export_dialog.Result_Error,
        )

    def _Export_ResultSet(self, manifest: ExportManifest) -> None:
        self.export_dialog.Result_Set(manifest)
        code = "export.complete_with_failures" if manifest.failures else "export.complete"
        self.status_label.setText(
            self._translator.Text_Get(
                code,
                count=len(manifest.files),
                failures=len(manifest.failures),
            )
        )

    def _ExportManifest_Open(self, manifest_path: Path) -> None:
        path = Path(manifest_path)
        try:
            opened = path.is_file() and QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path.resolve()))
            )
        except Exception:
            logging.exception("Export manifest open failed: %s", path)
            opened = False
        if not opened:
            self.export_dialog.ManifestOpen_Error()

    def _Task_Start(self, worker, result_callback, error_callback) -> None:
        if self._active_worker is not None:
            error_callback("another_background_task_is_running")
            return
        self._active_worker = worker
        self.replay_page.Task_Busy()
        self._worker_error_callback = error_callback
        worker.signals.progress.connect(self._Task_Progress)
        worker.signals.result.connect(result_callback)
        worker.signals.error.connect(self._Task_Error)
        worker.signals.cancelled.connect(
            lambda: self.status_label.setText(self._translator.Text_Get("status.task_cancelled"))
        )
        worker.signals.finished.connect(self._Task_Finish)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.import_action.setEnabled(False)
        self.export_action.setEnabled(False)
        self.open_project_action.setEnabled(False)
        self.open_silverstar_project_action.setEnabled(False)
        self.save_project_action.setEnabled(False)
        self.save_project_as_action.setEnabled(False)
        self.new_project_action.setEnabled(False)
        self._thread_pool.start(worker)

    def _Task_Progress(self, progress: float, code: str) -> None:
        self.progress_bar.setValue(int(progress * 1000))
        self.status_label.setText(self._translator.Text_Get(code))

    def _Task_Error(self, message: str, traceback_text: str) -> None:
        logging.error("Background task failed: %s\n%s", message, traceback_text)
        if self._worker_error_callback is not None:
            self._worker_error_callback(message)
        else:
            self._Error_Show(message)

    def _Task_Finish(self) -> None:
        self._source_restore_index = None
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.import_action.setEnabled(True)
        self.export_action.setEnabled(self._dataset is not None)
        self.open_project_action.setEnabled(True)
        self.open_silverstar_project_action.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.save_project_as_action.setEnabled(True)
        self.new_project_action.setEnabled(True)
        self.export_dialog.Task_Finish()
        self.replay_page.Task_Finish()
        self._active_worker = None
        self._worker_error_callback = None
        if self._source_restore_pending is not None:
            QTimer.singleShot(0, self._AnalysisSource_Restore)

    def _AnalysisSource_Restore(self):
        pending = self._source_restore_pending
        self._source_restore_pending = None
        if pending is None or self._dataset is None:
            return
        key, configuration = pending
        try:
            self.replay_page.Configuration_Set(configuration)
            self._source_restore_index = int(key.rsplit(":", 1)[1])
            request = ReplayRequest(
                mode=configuration["mode"],
                input_source=configuration["input_source"],
                parameters=configuration["actual_values"],
                quality_policy_revision=configuration.get("quality_policy_revision"),
            )
            self._Replay_Start(configuration["algorithm_id"], request)
        except (ValueError, KeyError) as exc:
            self._source_restore_index = None
            self._Error_Show(str(exc))

    def _Task_Cancel(self) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
            self.cancel_button.setEnabled(False)

    def _ProjectDialog_Open(self) -> None:
        if not self._ProjectChanges_Confirm():
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("action.open_project"),
            str(self._path_preferences.DefaultProjectRoot_EffectiveGet()),
            "SilverStar project (*.ssflp)",
        )
        if not selected:
            return
        self._Project_Open(Path(selected))

    def _Project_New(self) -> None:
        if self._active_worker is not None:
            self._Error_Show("another_background_task_is_running")
            return
        if not self._ProjectChanges_Confirm():
            return
        directory = self._path_preferences.DefaultProjectRoot_EffectiveGet()
        dialog = NewProjectDialog(self._translator, directory, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path = dialog.Path_Get()
        if path is None or not self._Overwrite_Confirm(path):
            return
        try:
            ProjectDirectory_Prepare(path)
        except OSError as error:
            self._Error_Show(str(error))
            return
        self._pending_new_project_path = path.resolve()
        self.import_dialog.result_label.hide()
        self.import_dialog.Folder_Set(self._ImportDirectory_Get())
        self.import_dialog.open()

    def _PendingProject_Cancel(self) -> None:
        self._pending_new_project_path = None

    def _Overwrite_Confirm(self, path: Path) -> bool:
        if not path.exists():
            return True
        answer = QMessageBox.question(
            self,
            self._translator.Text_Get("dialog.overwrite.title"),
            self._translator.Text_Get("dialog.overwrite.message", path=path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _Project_ForImport(self) -> ProjectDocument:
        if self._pending_new_project_path is not None:
            return ProjectDocument(project_path=self._pending_new_project_path)
        return ProjectDocument(
            replay_configurations=dict(self._project.replay_configurations),
            notes=self._project.notes,
            ui_state=dict(self._project.ui_state),
            project_path=self._project.project_path,
        )

    def _LogOpen_Error(self, message: str) -> None:
        self._pending_new_project_path = None
        if message.partition(":")[0].strip() == "calibration_selection_boundary_missing":
            self.status_label.setText(self._translator.Text_Get("import.startup_fragment"))
            QMessageBox.information(
                self,
                self._translator.Text_Get("dialog.import.title"),
                self._translator.Text_Get("import.startup_fragment"),
            )
            return
        self._Error_Show(message)

    def _Project_Save(self) -> None:
        path = self._project.project_path
        if path is None:
            path = self._ProjectPath_Select("action.save_project")
            if path is not None and not self._Overwrite_Confirm(path):
                return
        if path is not None:
            self._Project_Write(path)

    def _Project_SaveAs(self) -> None:
        path = self._ProjectPath_Select("action.save_project_as")
        if path is not None and self._Overwrite_Confirm(path):
            self._Project_Write(path)

    def _ProjectPath_Select(self, title_key: str) -> Path | None:
        filename = self._project.project_path.name if self._project.project_path else "flight.ssflp"
        suggested_path = self._path_preferences.DefaultProjectRoot_EffectiveGet() / filename
        selected, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.Text_Get(title_key),
            str(suggested_path),
            "SilverStar project (*.ssflp)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not selected:
            return None
        path = Path(selected)
        return path if path.suffix.lower() == ".ssflp" else path.with_suffix(".ssflp")

    def _Project_Write(self, path: Path) -> None:
        try:
            self._project.ui_state["page_index"] = self.navigation_list.currentRow()
            self._project.ui_state["time_range"] = self.time_range.controller.model.State_Get()
            self._project.ui_state["analysis_source"] = (
                self._replay_store.ActiveSource_Get().source_id
            )
            self._project.replay_configurations["draft"] = self.replay_page.Configuration_Get()
            for entry in self._replay_store.Entries_Get():
                if entry.analysis_only:
                    continue
                self._project.replay_configurations[entry.result_id] = {
                    "algorithm_id": entry.algorithm_id,
                    "algorithm_version": entry.algorithm_version,
                    "mode": entry.mode.value,
                    "input_source": entry.input_source,
                    "actual_values": dict(entry.parameters),
                    "parameter_schema_identity": entry.diagnostics["parameter_schema_identity"],
                    "provenance": entry.diagnostics["config_source"],
                }
                if entry.diagnostics.get("quality_policy_override") is not None:
                    saved_configuration = self._project.replay_configurations[entry.result_id]
                    saved_configuration["quality_policy_revision"] = entry.diagnostics[
                        "quality_policy_override"
                    ]
            Project_Save(self._project, path)
            self._Project_SetDirty(False)
            self._ProjectHeader_Refresh()
            self.status_label.setText(self._translator.Text_Get("status.project_saved", path=path))
        except Exception as exc:
            logging.exception("Project save failed")
            self._Error_Show(str(exc))

    def _Project_MarkDirty(self) -> None:
        if not self._suspend_dirty and self._dataset is not None:
            self._Project_SetDirty(True)

    def _Project_SetDirty(self, dirty: bool) -> None:
        self._project_dirty = dirty
        self._ProjectHeader_Refresh()

    def _ProjectHeader_Refresh(self) -> None:
        path = self._project.project_path
        full_name = path.stem if path is not None else self._translator.Text_Get("project.unsaved")
        if self._silverstar_project_root is not None:
            session = path.stem if path is not None else self._translator.Text_Get("project.analysis_unsaved")
            full_name = self._silverstar_project_root.name + " / " + session
        self.project_name_label.ProjectName_Set(full_name, self._project_dirty)
        if self._project_dirty:
            full_name += " *"
        if self._silverstar_project_root is not None:
            tooltip = "\n".join(value for value in (
                full_name, str(self._silverstar_project_root),
                str(path.resolve()) if path is not None else "") if value)
        else:
            tooltip = str(path.resolve()) if path is not None else ""
        self.project_name_label.setToolTip(tooltip)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "project_name_label"):
            self._ProjectHeader_Refresh()

    def _ProjectChanges_Confirm(self) -> bool:
        if not self._project_dirty:
            return True
        answer = QMessageBox.warning(
            self,
            self._translator.Text_Get("dialog.unsaved.title"),
            self._translator.Text_Get("dialog.unsaved.message"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        self._Project_Save()
        return not self._project_dirty

    def _Error_Show(self, message: str) -> None:
        code, separator, details = message.partition(":")
        translation_key = f"error.code.{code.strip()}"
        translated = self._translator.Text_Get(translation_key)
        display_message = (
            translated + (f"\n{details.strip()}" if separator and details.strip() else "")
            if translated != translation_key
            else message
        )
        QMessageBox.critical(
            self,
            self._translator.Text_Get("error.title"),
            f"{display_message}\n\n{self._translator.Text_Get('error.detail_saved')}",
        )

    def Language_Apply(self, language: str) -> None:
        try:
            self._translator.Language_Set(language)
        except ValueError:
            return
        self.time_range.Language_Apply()
        self._settings.setValue("language", language)
        language_index = self.language_combo.findData(language)
        if language_index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(language_index)
            self.language_combo.blockSignals(False)

        selected_theme = self.theme_combo.currentData() or self._theme
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem(self._translator.Text_Get("theme.light"), "light")
        self.theme_combo.addItem(self._translator.Text_Get("theme.dark"), "dark")
        self.theme_combo.setCurrentIndex(max(self.theme_combo.findData(selected_theme), 0))
        self.theme_combo.blockSignals(False)

        self.title_label.setText(self._translator.Text_Get("app.title"))
        self.version_label.setText(f"v{__version__}")
        self.credit_label.setText(self._translator.Text_Get("app.credit"))
        self.project_caption_label.setText(self._translator.Text_Get("label.current_project"))
        self._ProjectHeader_Refresh()
        self.language_label.setText(self._translator.Text_Get("label.interface_language"))
        self.theme_label.setText(self._translator.Text_Get("label.theme"))
        self.cancel_button.setText(self._translator.Text_Get("action.cancel"))
        self.file_menu.setTitle(self._translator.Text_Get("menu.file"))
        self.plugins_menu.setTitle(self._translator.Text_Get("menu.plugins"))
        self.help_menu.setTitle(self._translator.Text_Get("menu.help"))
        self.new_project_action.setText(self._translator.Text_Get("action.new_project"))
        self.default_root_action.setText(self._translator.Text_Get("action.default_project_root"))
        self.import_action.setText(self._translator.Text_Get("action.import"))
        self.export_action.setText(self._translator.Text_Get("action.export"))
        self.open_project_action.setText(self._translator.Text_Get("action.open_project"))
        self.open_silverstar_project_action.setText(
            self._translator.Text_Get("action.open_silverstar_project")
        )
        self.save_project_action.setText(self._translator.Text_Get("action.save_project"))
        self.save_project_as_action.setText(self._translator.Text_Get("action.save_project_as"))
        self.exit_action.setText(self._translator.Text_Get("action.exit"))
        self.manage_plugins_action.setText(self._translator.Text_Get("action.manage_plugins"))
        self.install_plugin_action.setText(self._translator.Text_Get("action.install_plugin"))
        self.refresh_plugins_action.setText(self._translator.Text_Get("action.refresh_plugins"))
        self.about_action.setText(self._translator.Text_Get("action.about"))
        self.plugin_manager_dialog.Language_Apply(self._translator)
        self.plugin_manager_dialog.Registry_Set(self._registry, self._plugin_discovery)
        self.about_dialog.Language_Apply(self._translator)
        for index in range(self.navigation_list.count()):
            item = self.navigation_list.item(index)
            page_code = str(item.data(Qt.ItemDataRole.UserRole))
            item.setText(self._translator.Text_Get(page_code))
        for page in self._page_widgets:
            page.Language_Apply(self._translator)
        self.import_dialog.Language_Apply(self._translator)
        self.export_dialog.Language_Apply(self._translator)
        if self._dataset is None:
            self.status_label.setText(self._translator.Text_Get("status.ready"))
        else:
            self.status_label.setText(self._DatasetStatus_TextGet(self._dataset))
        self.setWindowTitle(PRODUCT_NAME)

    def Theme_Apply(self, theme: str) -> None:
        if theme not in ("light", "dark"):
            return
        self._theme = theme
        self._settings.setValue("theme", theme)
        theme_index = self.theme_combo.findData(theme)
        if theme_index >= 0:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(theme_index)
            self.theme_combo.blockSignals(False)
        application = QApplication.instance()
        if application is not None:
            Theme_Apply(application, theme)
        WindowCaption_Apply(self, theme)
        self.flight_page.Theme_Apply(theme)
        self.state_estimation_page.Theme_Apply(theme)

    @staticmethod
    def _DropPaths_Validate(urls: list[QUrl]) -> tuple[Path, ...] | None:
        if not urls or any(not url.isLocalFile() for url in urls):
            return None
        paths = tuple(Path(url.toLocalFile()) for url in urls)
        if len(paths) == 1 and paths[0].is_dir():
            return paths
        project_paths = tuple(path for path in paths if path.suffix.casefold() == ".ssflp")
        log_paths = tuple(path for path in paths if path.suffix.casefold() in (".bin", ".sslog"))
        decoder_paths = tuple(path for path in paths if path.suffix.casefold() == ".ssdecoder")
        if len(project_paths) == 1 and len(paths) == 1:
            return paths
        if (
            len(log_paths) == 1
            and len(decoder_paths) <= 1
            and len(paths) == len(log_paths) + len(decoder_paths)
        ):
            return paths
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._DropPaths_Validate(event.mimeData().urls()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._DropPaths_Validate(event.mimeData().urls())
        if paths is None:
            self._Error_Show("drop_selection_invalid")
            event.ignore()
            return
        if len(paths) == 1 and paths[0].is_dir():
            self.Path_Open(paths[0])
            event.acceptProposedAction()
            return
        project_paths = tuple(path for path in paths if path.suffix.casefold() == ".ssflp")
        if project_paths:
            if not self._ProjectChanges_Confirm():
                event.ignore()
                return
            self._Project_Open(project_paths[0])
            event.acceptProposedAction()
            return
        log_path = next(path for path in paths if path.suffix.casefold() in (".bin", ".sslog"))
        decoder_path = next(
            (path for path in paths if path.suffix.casefold() == ".ssdecoder"),
            None,
        )
        if decoder_path is None:
            self.Log_Open(
                log_path,
                auto_find=True,
                source_mode=LogOpenSourceMode.DRAG_DROP,
            )
        else:
            self.Log_Open(
                log_path,
                decoder_path=decoder_path,
                source_mode=LogOpenSourceMode.DRAG_DROP,
            )
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_worker is not None:
            self._active_worker.Worker_Cancel()
        if self._ProjectChanges_Confirm():
            event.accept()
        else:
            event.ignore()
