from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportFailure, ExportLanguage, ExportManifest, ExportTheme, FlightExporter
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.export_settings import ExportDialog


@pytest.mark.parametrize('language,phrase', [('zh_CN', '启动'), ('en_US', 'startup')])
def test_startup_fragment_is_information_and_keeps_published_session(monkeypatch, language, phrase):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry(), language=language)
    information, critical = [], []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, text: information.append(text))
    monkeypatch.setattr(window, '_Error_Show', critical.append)
    original_project = window._project
    original_dataset = object()
    window._dataset = original_dataset
    window._pending_new_project_path = Path('pending.ssflp')
    try:
        window._LogOpen_Error('calibration_selection_boundary_missing')
        assert not critical and len(information) == 1
        assert phrase in information[0]
        assert 'calibration_selection_boundary_missing' not in information[0]
        assert window._dataset is original_dataset and window._project is original_project
        assert window._pending_new_project_path is None
        window._LogOpen_Error('decoder_profile_descriptor_missing')
        assert critical == ['decoder_profile_descriptor_missing']
    finally:
        window._dataset = None
        window.close()
        app.processEvents()


@pytest.mark.parametrize('language,phrase', [('zh_CN', '空文件夹'), ('en_US', 'empty folder')])
def test_nonempty_export_directory_is_protected_and_gui_explains_retry(tmp_path, language, phrase):
    app = QApplication.instance() or QApplication([])
    sentinel = tmp_path / 'existing_result.txt'
    sentinel.write_bytes(b'USER RESULT MUST STAY UNCHANGED')
    # The directory check occurs before the exporter reads the dataset.
    with pytest.raises(FileExistsError, match='export_directory_not_empty') as error:
        FlightExporter(builtin_registry()).export(None, tmp_path)
    dialog = ExportDialog(Translator(language))
    try:
        dialog.Result_Error(str(error.value))
        assert phrase in dialog.result_label.text()
        assert str(tmp_path) in dialog.result_label.toolTip()
        assert 'export_directory_not_empty' not in dialog.result_label.text()
        assert dialog.export_button.isEnabled()
        assert dialog._result_manifest is None
        assert sentinel.read_bytes() == b'USER RESULT MUST STAY UNCHANGED'
        dialog.Result_Error('unrecognized_detail:retain this original')
        assert dialog.result_label.text() == 'unrecognized_detail:retain this original'
    finally:
        dialog.reject()
        app.processEvents()


@pytest.mark.parametrize('language,phrase', [('zh_CN', '缺少'), ('en_US', 'missing')])
def test_partial_export_explains_missing_channels_and_keeps_original_failure(language, phrase, tmp_path):
    app = QApplication.instance() or QApplication([])
    failure = ExportFailure('standard_plot:Flight_Velocity_ENU', 'Velocity', 'ValueError', 'channel_unavailable:navigation.velocity_enu')
    manifest = ExportManifest(tmp_path, (), ExportLanguage(language), ExportTheme.LIGHT, failures=(failure,))
    dialog = ExportDialog(Translator(language))
    try:
        dialog.Result_Set(manifest)
        assert phrase in dialog.result_label.text()
        assert 'channel_unavailable:navigation.velocity_enu' in dialog.failure_details_edit.toPlainText()
        assert dialog._result_manifest.failures == (failure,)
    finally:
        dialog.reject()
        app.processEvents()
