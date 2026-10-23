"""Real Qt widgets, synthetic logs and temporary files; no hardware or native dialogs."""
from pathlib import Path
from types import SimpleNamespace as NS
import os
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings

@pytest.fixture(scope='module')
def app():
    value = QApplication.instance() or QApplication([])
    yield value

def capture(widget, name):
    if os.environ.get('SILVERSTAR_QA_DIRECTORY'):
        widget.grab().save(str(Path(os.environ['SILVERSTAR_QA_DIRECTORY']) / name))

def test_import_dialog_requires_manual_opt_in(app, tmp_path):
    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.pages.export_settings import ImportDialog
    dialog = ImportDialog(Translator('en_US'))
    assert not dialog.custom_decoder_check.isChecked()
    dialog.Paths_Set(log_path=tmp_path / 'record.sslog', decoder_path=tmp_path / 'edited.ssdecoder')
    received = []
    dialog.customImportRequested.connect(lambda *args: received.append(args))
    dialog.custom_decoder_check.setChecked(True)
    dialog.show()
    app.processEvents()
    capture(dialog, 'custom-import.png')
    dialog._Import_Request()
    assert len(received) == 1 and (not dialog.custom_decoder_check.isChecked())
    dialog.deleteLater()

def test_custom_then_exact_restores_time_controls_and_navigation(app, tmp_path, monkeypatch):
    from silverstar_flp.ui import main_window
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
    from silverstar_flp.core.path_preferences import PathPreferences
    from silverstar_flp.core.project import ProjectDocument
    from silverstar_flp.decoder_profiles import DecoderProfileCache
    from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
    from tests.test_user_custom_decoder import pair
    monkeypatch.setattr(main_window, 'QSettings', lambda *a: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    registry = builtin_registry()
    window = main_window.MainWindow(registry, plugin_manager=TrustedContainerPluginManager(tmp_path / 'plugins'), path_preferences=PathPreferences(tmp_path / 'paths.json'))
    log, decoder = pair(tmp_path)
    coordinator = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / 'cache'))
    custom = coordinator.Open(LogOpenRequest(log, decoder, allow_unverified_decoder=True))
    assert window._LogOpenResult_Set(custom, ProjectDocument())
    assert not window.custom_decoder_banner.isHidden()
    assert window.time_range.isHidden() and (not window.export_action.isEnabled())
    assert window.pages.currentIndex() == 4
    window.show()
    app.processEvents()
    capture(window, 'custom-view.png')
    from tests.test_decoder_profiles import _Package_Write, _DescriptorPayload_Build, _CalibrationNonePayload_Build, START_TIMESTAMP_US, DESCRIPTOR_RECORD_TYPE
    from tests.sslog_synthetic import SyntheticSslogBuilder, Event_Payload
    package, hashes = _Package_Write(tmp_path / 'exact.ssdecoder')
    builder = SyntheticSslogBuilder()
    builder.Record_Add(DESCRIPTOR_RECORD_TYPE, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    builder.Record_Add(23, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(2, Event_Payload(3), START_TIMESTAMP_US)
    exact = coordinator.Open(LogOpenRequest(builder.File_Write(tmp_path / 'exact.sslog'), package))
    assert window._LogOpenResult_Set(exact, ProjectDocument())
    assert window.custom_decoder_banner.isHidden()
    assert not window.time_range.isHidden()
    assert window.export_action.isEnabled()
    assert all((window.navigation_list.item(i).flags() & Qt.ItemFlag.ItemIsEnabled for i in range(window.navigation_list.count())))
    window.deleteLater()
