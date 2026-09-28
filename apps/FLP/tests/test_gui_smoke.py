from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton, QToolBar

from silverstar_flp.app.application import _RuntimeDiagnostics_Log
from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.core.project import ProjectDecoderProfile
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCacheReference
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.export.service import (
    ExportFailure,
    ExportLanguage,
    ExportManifest,
    ExportTheme,
)
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.widgets import StandardComboBox
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse


def _ProjectIdentity_Set(window: MainWindow, source_path: Path, root: Path) -> None:
    package_hash = "2" * 64
    generation_hash = "3" * 64
    window._project.LogReference_Set(source_path)
    window._project.decoder_profile = ProjectDecoderProfile(
        source_reference=str(root / "synthetic.ssdecoder"),
        cache_reference=DecoderProfileCacheReference(
            generation_profile_sha256=generation_hash,
            package_sha256=package_hash,
            relative_path=f"{generation_hash[:32]}/{package_hash}.ssdecoder",
        ),
        package_sha256=package_hash,
        generation_profile_sha256=generation_hash,
        record_catalog_sha256="4" * 64,
        record_catalog_hash_128="4" * 32,
        project_semantics_sha256="5" * 64,
        project_semantics_hash_128="5" * 32,
        container_plugin_id="silverstar.flight_log.container.0_0",
        container_plugin_version="0.0.0",
        exact_match_mode="exact_generation_profile",
    )


def test_runtime_diagnostics_log_version_python_package_and_export_path(
    caplog,
) -> None:
    with caplog.at_level("INFO"):
        _RuntimeDiagnostics_Log()
    text = caplog.text
    assert f"SilverStar_FLP version={__version__}" in text
    assert "Python executable=" in text
    assert "silverstar_flp package path=" in text
    assert "export.service path=" in text
    assert r"src\silverstar_flp\export\service.py" in text


def test_five_page_gui_and_top_bar_accept_a_parsed_dataset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_gui_source.BIN")
    )
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    _ProjectIdentity_Set(window, dataset.source_path, tmp_path)
    window.show()
    application.processEvents()
    assert window.pages.count() == 5
    assert window.windowTitle() == PRODUCT_NAME
    assert window.title_label.text() == "SilverStar 飞行日志解析器"
    assert window.version_label.text() == f"v{__version__}" == "v0.1.0"
    assert window.credit_label.text() == "辰星引力开发"
    assert window.project_name_label.text() == "未保存工程"
    assert window.project_name_label.toolTip() == ""
    assert dataset.source_path.name not in window.windowTitle()
    assert not hasattr(window, "timeline_frame")
    assert not hasattr(window, "timeline_slider")
    assert not hasattr(window, "attitude_page")
    assert not hasattr(window, "navigation_page")
    assert window.flight_page.tabs.count() == 6
    assert window.state_estimation_page.tabs.count() == 6
    for row, visible in enumerate((False, False, True, True, False)):
        window.navigation_list.setCurrentRow(row)
        application.processEvents()
        assert window.time_range.isVisible() is visible
    assert window.explorer_page._time_range is None
    window.navigation_list.setCurrentRow(0)
    assert window.explorer_page.tabs.count() == 3
    assert (
        window.overview_page.calibration_group.geometry().top()
        == window.overview_page.alignment_group.geometry().top()
    )
    assert (
        window.overview_page.timeline_group.geometry().top()
        >= window.overview_page.calibration_group.geometry().bottom()
    )
    overview_buttons = window.overview_page.findChildren(QPushButton)
    assert all(button.text() not in ("查看详情", "Details") for button in overview_buttons)
    assert window.overview_page.calibration_group.property("statusLevel") == "success"
    assert window.overview_page.alignment_group.property("statusLevel") == "success"
    assert window.overview_page.quality_card.property("statusLevel") == "success"
    assert window.explorer_page.channel_list.count() == len(dataset.series)
    assert window.explorer_page.diagnostics_table.rowCount() == len(dataset.diagnostics.diagnostics)
    record_headers = [
        window.explorer_page.record_table.horizontalHeaderItem(column).text()
        for column in range(window.explorer_page.record_table.columnCount())
    ]
    assert "file_offset" in record_headers
    assert window.pages.indexOf(window.export_dialog) == -1
    assert window.import_dialog.isModal()
    assert window.export_dialog.isModal()
    assert window.export_action.isEnabled()
    assert not hasattr(window, "export_button")
    assert not hasattr(window, "import_button")
    assert window.findChildren(QToolBar) == []
    assert [action.menu() for action in window.menuBar().actions()] == [
        window.file_menu,
        window.plugins_menu,
        window.help_menu,
    ]
    header_layout = window.title_label.parentWidget().layout()
    assert [
        header_layout.indexOf(widget)
        for widget in (
            window.title_label,
            window.version_label,
            window.credit_label,
            window.project_caption_label,
            window.project_name_label,
            window.language_label,
            window.language_combo,
            window.theme_label,
            window.theme_combo,
        )
    ] == [0, 1, 2, 3, 4, 6, 7, 8, 9]
    assert [action for action in window.file_menu.actions() if not action.isSeparator()] == [
        window.new_project_action,
        window.open_project_action,
        window.save_project_action,
        window.save_project_as_action,
        window.default_root_action,
        window.import_action,
        window.export_action,
        window.exit_action,
    ]
    shortcuts = {
        action.shortcut().toString()
        for action in window.file_menu.actions()
        if not action.shortcut().isEmpty()
    }
    assert shortcuts == {"Ctrl+N", "Ctrl+O", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+E"}
    assert len(shortcuts) == 5
    assert window.plugins_menu.actions() == [
        window.manage_plugins_action,
        window.install_plugin_action,
        window.refresh_plugins_action,
    ]
    assert window.help_menu.actions() == [window.about_action]
    window._PluginManager_Show()
    application.processEvents()
    plugin_cells = {
        window.plugin_manager_dialog.table.item(row, column).text()
        for row in range(window.plugin_manager_dialog.table.rowCount())
        for column in range(window.plugin_manager_dialog.table.columnCount())
    }
    assert any("Pure INS" in cell for cell in plugin_cells)
    assert any("KF_6" in cell for cell in plugin_cells)
    assert any("SSLOG0" in cell for cell in plugin_cells)
    window.plugin_manager_dialog.reject()
    window._About_Show()
    application.processEvents()
    assert window.about_dialog.isVisible()
    assert window.about_dialog.product_label.text() == "SilverStar 飞行日志解析器"
    assert window.about_dialog.version_label.text() == "版本 0.1.0"
    assert "离线算法复算" in window.about_dialog.description_label.text()
    assert window.about_dialog.windowTitle() == "SilverStar_FLP"
    window.about_dialog.reject()
    saved_as_path = tmp_path / "SYNTHETIC_gui_project_copy.ssflp"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(saved_as_path), "SilverStar project (*.ssflp)"),
    )
    window.save_project_as_action.trigger()
    assert saved_as_path.is_file()
    assert window._project.project_path == saved_as_path.resolve()
    assert window.project_name_label.text() == saved_as_path.stem
    assert window.project_name_label.toolTip() == str(saved_as_path.resolve())
    assert not hasattr(window.flight_page, "source_combo")
    assert not hasattr(window.state_estimation_page, "source_combo")
    assert not hasattr(window.replay_page, "source_combo")

    combos = (
        window.language_combo,
        window.theme_combo,
        window.flight_page.playback_speed_combo,
        window.replay_page.algorithm_combo,
        window.replay_page.analysis_source_combo,
        window.replay_page.mode_combo,
        window.replay_page.parameter_group_combo,
        window.state_estimation_page.state_group_combo,
        window.state_estimation_page.covariance_display_combo,
        window.state_estimation_page.innovation_measurement_combo,
        window.state_estimation_page.nis_measurement_combo,
        window.state_estimation_page.measurement_group_combo,
        window.explorer_page.record_combo,
        window.import_dialog.source_type_combo,
        window.export_dialog.export_language_combo,
        window.export_dialog.export_theme_combo,
    )
    assert all(isinstance(combo, StandardComboBox) for combo in combos)
    assert all(combo.maxVisibleItems() == 10 for combo in combos)
    assert window.language_combo.view().objectName() == "headerComboPopup"
    assert window.theme_combo.view().objectName() == "headerComboPopup"
    long_combo = StandardComboBox(window)
    long_combo.addItems([f"item-{index}" for index in range(11)])
    long_combo.setCurrentIndex(10)
    long_combo.move(260, 140)
    long_combo.resize(180, 30)
    long_combo.show()
    long_combo.showPopup()
    application.processEvents()
    assert long_combo.view().verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    combo_bottom = long_combo.mapToGlobal(QPoint(0, long_combo.height())).y()
    assert long_combo.view().window().geometry().top() >= combo_bottom - 1
    long_combo.hidePopup()

    if window.flight_page.trajectory_view is not None:
        window.flight_page.trajectory_view.opts["distance"] = 73.0
    window.Language_Apply("zh_CN")
    assert window.new_project_action.text() == "新建工程"
    assert window.import_action.text() == "导入日志 / 解码包"
    assert window.save_project_action.text() == "保存工程"
    assert window.open_project_action.text() == "打开工程"
    assert window.save_project_as_action.text() == "工程另存为…"
    assert window.title_label.text() == "SilverStar 飞行日志解析器"
    assert window.credit_label.text() == "辰星引力开发"
    assert window.replay_page.parameters_group.title() == "假设参数"
    window.Language_Apply("en_US")
    assert window.new_project_action.text() == "New Project"
    assert window.import_action.text() == "Import Log / Decoder"
    assert window.save_project_action.text() == "Save Project"
    assert window.open_project_action.text() == "Open Project"
    assert window.save_project_as_action.text() == "Save Project As…"
    assert window.title_label.text() == "SilverStar Flight Log Parser"
    assert window.credit_label.text() == "By CXYL"
    assert [menu.title() for menu in (window.file_menu, window.plugins_menu, window.help_menu)] == [
        "File",
        "Plugins",
        "Help",
    ]
    assert window.replay_page.parameters_group.title() == "What-if parameters"
    assert window.windowTitle() == PRODUCT_NAME
    if window.flight_page.trajectory_view is not None:
        assert window.flight_page.trajectory_view.opts["distance"] == 73.0

    window.Theme_Apply("light")
    style_sheet = application.styleSheet()
    assert "#123A78" in style_sheet
    assert "#D6E6FF" in style_sheet
    assert "QAbstractItemView#headerComboPopup" in style_sheet
    assert (
        "QListWidget#navigation::item:selected { background: #2F6FED; color: #FFFFFF; }"
        in style_sheet
    )
    assert "QTabBar::tab:selected" in style_sheet
    window.navigation_list.setCurrentRow(2)
    application.processEvents()
    attitude_width, trajectory_width = window.flight_page.replay_splitter.sizes()
    assert trajectory_width >= attitude_width * 0.9
    assert window.flight_page.playback_slider.maximum() == 10000
    assert (
        window.replay_page.scroll_area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    window.navigation_list.setCurrentRow(1)
    window.replay_page.algorithm_combo.setCurrentIndex(1)
    window.replay_page.mode_combo.setCurrentIndex(1)
    application.processEvents()
    assert window.replay_page.scroll_area.verticalScrollBar().maximum() > 0
    assert window.overview_page.scroll_area.widgetResizable()
    window._Project_SetDirty(False)
    window.close()


def test_export_dialog_uses_project_or_source_default_and_opens_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_default_export.BIN")
    )
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    window.show()

    window._ExportDialog_Show()
    application.processEvents()
    assert Path(window.export_dialog.folder_edit.text()) == (
        tmp_path / "Result_SYNTHETIC_default_export"
    )
    assert not window.export_dialog.folder_edit.isReadOnly()
    window.export_dialog.folder_edit.setText(str(tmp_path / "custom_export"))
    assert Path(window.export_dialog.folder_edit.text()) == tmp_path / "custom_export"
    window.export_dialog.reject()

    window._project.project_path = tmp_path / "Named Flight.ssflp"
    window._ExportDialog_Show()
    application.processEvents()
    assert Path(window.export_dialog.folder_edit.text()) == (
        tmp_path / "Result_SYNTHETIC_default_export"
    )

    source_text = Path("src/silverstar_flp/ui/main_window.py").read_text(encoding="utf-8")
    assert "_DEFAULT_EXPORT_ROOT" not in source_text
    assert "SilverStar_FLP_Data" not in source_text

    manifest_directory = tmp_path / "manifest_export"
    manifest_directory.mkdir()
    manifest_path = manifest_directory / "Export_Manifest_ZH.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = ExportManifest(
        manifest_directory,
        (manifest_path,),
        ExportLanguage.ZH,
        ExportTheme.LIGHT,
    )
    opened_urls = []

    class DesktopServicesStub:
        @staticmethod
        def openUrl(url):
            opened_urls.append(url)
            return True

    monkeypatch.setattr(
        "silverstar_flp.ui.main_window.QDesktopServices",
        DesktopServicesStub,
    )
    window._Export_ResultSet(manifest)
    assert manifest.ManifestPath_Get() == manifest_path
    assert not window.export_dialog.manifest_button.isHidden()
    assert window.export_dialog.manifest_button.isEnabled()
    assert window.export_dialog.manifest_button.text() == "打开导出清单"
    window.export_dialog.manifest_button.click()
    application.processEvents()
    assert len(opened_urls) == 1
    assert Path(opened_urls[0].toLocalFile()) == manifest_path.resolve()
    window.Language_Apply("en_US")
    assert window.export_dialog.manifest_button.text() == "Open Export Manifest"
    window._Project_SetDirty(False)
    window.close()


def test_plugin_install_rejects_unsupported_algorithm_and_refresh_preserves_runtime(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    manager = TrustedContainerPluginManager(tmp_path / "installed")
    window = MainWindow(builtin_registry(), plugin_manager=manager)
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_plugin_refresh.BIN")
    )
    window._Dataset_Set(dataset)
    algorithms_before = window._registry.algorithms
    containers_before = window._registry.log_containers

    unsupported = tmp_path / "algorithm.ssplugin"
    with zipfile.ZipFile(unsupported, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "SilverStar.ssplugin",
                    "plugin_type": "algorithm",
                    "plugin_id": "example.algorithm.unsafe",
                    "version": "1.0.0",
                    "api_version": 1,
                    "entry_point": "unsafe.algorithm:factory",
                }
            ),
        )
    with pytest.raises(DecoderProfileError, match="container_plugin_type_invalid"):
        window.Plugin_Install(unsupported, explicitly_trusted=True)

    window._Plugins_Refresh(show_message=False)
    assert window._registry.algorithms == algorithms_before
    assert window._registry.log_containers == containers_before
    assert window._dataset is dataset
    assert manager.Discover().manifests == ()
    window._Project_SetDirty(False)
    window.close()


def test_new_project_selects_destination_before_import_and_cancel_leaves_no_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    target = tmp_path / "Flight" / "Flight.ssflp"
    from silverstar_flp.ui.new_project import NewProjectDialog

    monkeypatch.setattr(NewProjectDialog, "exec", lambda self: 1)
    monkeypatch.setattr(NewProjectDialog, "Path_Get", lambda self: target)
    window.new_project_action.trigger()
    application.processEvents()
    assert window._pending_new_project_path == target.resolve()
    assert window.import_dialog.isVisible()
    assert not target.exists()
    window.import_dialog.reject()
    assert window._pending_new_project_path is None
    assert not target.exists()
    window._Project_SetDirty(False)
    window.close()


def test_new_project_requires_overwrite_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    target = tmp_path / "Existing.ssflp"
    target.write_text("original", encoding="utf-8")
    from silverstar_flp.ui.new_project import NewProjectDialog

    monkeypatch.setattr(NewProjectDialog, "exec", lambda self: 1)
    monkeypatch.setattr(NewProjectDialog, "Path_Get", lambda self: target)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.new_project_action.trigger()
    application.processEvents()
    assert window._pending_new_project_path is None
    assert not window.import_dialog.isVisible()
    assert target.read_text(encoding="utf-8") == "original"
    window._Project_SetDirty(False)
    window.close()


def test_export_dialog_lists_failed_items_and_toggles_error_details(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    output = tmp_path / "failed_export"
    output.mkdir()
    failure = ExportFailure(
        item_id="flight_replay_gif",
        localized_name="三维飞行回放 GIF",
        exception_type="AttributeError",
        exception_message="'str' object has no attribute 'value'",
    )
    manifest = ExportManifest(
        output,
        (),
        ExportLanguage.ZH,
        ExportTheme.LIGHT,
        (failure,),
    )

    window._Export_ResultSet(manifest)
    assert "失败项目：" in window.export_dialog.result_label.text()
    assert "- 三维飞行回放 GIF" in window.export_dialog.result_label.text()
    assert not window.export_dialog.failure_details_button.isHidden()
    window.export_dialog.failure_details_button.click()
    application.processEvents()
    assert not window.export_dialog.failure_details_edit.isHidden()
    detail = window.export_dialog.failure_details_edit.toPlainText()
    assert "[flight_replay_gif] 三维飞行回放 GIF" in detail
    assert "AttributeError" in detail
    assert "'str' object has no attribute 'value'" in detail
    window._Project_SetDirty(False)
    window.close()


def test_export_dialog_runs_gif_and_manifest_through_real_qthreadpool_worker(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_gui_worker_export.BIN")
    )
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    dialog = window.export_dialog
    output = tmp_path / "gui_worker_export"
    dialog.folder_edit.setText(str(output))
    for checkbox in dialog._checks:
        checkbox.setChecked(False)
    dialog.gif_check.setChecked(True)
    assert isinstance(dialog.export_language_combo.currentData(), str)
    assert isinstance(dialog.export_theme_combo.currentData(), str)

    dialog._Export_Request()
    worker = window._active_worker
    assert worker is not None
    errors: list[tuple[str, str]] = []
    worker.signals.error.connect(
        lambda message, traceback_text: errors.append((message, traceback_text))
    )
    loop = QEventLoop()
    worker.signals.finished.connect(loop.quit)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(60_000)
    loop.exec()
    timed_out = not timeout.isActive()
    timeout.stop()
    application.processEvents()

    assert not timed_out
    assert not errors
    assert window._active_worker is None
    assert (output / "GIF" / "Flight_Replay_ZH.gif").is_file()
    assert (output / "Export_Manifest_ZH.json").is_file()
    assert not (output / "Export_Failures_ZH.txt").exists()
    assert dialog._result_manifest is not None
    assert not dialog._result_manifest.failures
    window._Project_SetDirty(False)
    window.close()


def test_new_project_form_validates_identity_and_preserves_suffix(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QDialogButtonBox

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.new_project import NewProjectDialog

    application = QApplication.instance() or QApplication([])
    dialog = NewProjectDialog(Translator("zh_CN"), tmp_path)
    button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    for name in ("", "../Flight", "CON", "flight?", ".ssflp"):
        dialog.name_edit.setText(name)
        assert not button.isEnabled()
    dialog.name_edit.setText("Flight.ssflp")
    assert button.isEnabled()
    assert dialog.Path_Get() == tmp_path / "Flight" / "Flight.ssflp"
    dialog.directory_edit.setText(str(tmp_path / "missing"))
    assert button.isEnabled()
    assert not (tmp_path / "missing").exists()
    dialog.reject()
    application.processEvents()
