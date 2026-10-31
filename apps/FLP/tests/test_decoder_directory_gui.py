from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.path_preferences import PathPreferences
from silverstar_flp.core.project import ProjectDocument, Project_Save
from silverstar_flp.decoder_profiles import DecoderProfileCache, DecoderProfileError
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest, LogOpenSourceMode
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.export_settings import ImportDialog
from tests.sslog_synthetic import START_TIMESTAMP_US, Event_Payload, SyntheticSslogBuilder
from tests.test_decoder_profiles import _Package_Write, _DescriptorPayload_Build, _CalibrationNonePayload_Build


def pair(tmp_path):
    directory = tmp_path / 'decoder archive'
    directory.mkdir()
    package, hashes = _Package_Write(directory / 'identity.ssdecoder')
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    logs = tmp_path / 'logs'; logs.mkdir()
    log = builder.File_Write(logs / 'flight.sslog')
    return log, package


def test_preferences_preserve_other_settings_and_bound_search(tmp_path):
    store = PathPreferences(tmp_path / 'preferences.json')
    directories = tuple(tmp_path / str(index) for index in range(4))
    store.DecoderDirectories_Set(directories)
    store.DefaultProjectRoot_Set(tmp_path)
    assert store.DecoderDirectories_Get() == directories
    store.DecoderDirectories_Set(directories[:1])
    assert store.DefaultProjectRoot_Get() == tmp_path
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.DecoderDirectories_Set(directories + (tmp_path / 'fifth',))
    assert store.path.read_bytes() == before


def test_manual_blank_decoder_requests_exact_discovery_and_custom_still_requires_package(qtbot, tmp_path):
    dialog = ImportDialog(Translator('en_US')); qtbot.addWidget(dialog)
    automatic = []; manual = []
    dialog.autoImportRequested.connect(automatic.append)
    dialog.customImportRequested.connect(lambda *args: manual.append(args))
    dialog.Paths_Set(log_path=tmp_path / 'flight.sslog')
    dialog.custom_decoder_check.setChecked(True)
    dialog._Import_Request()
    assert not automatic and not manual
    dialog.custom_decoder_check.setChecked(False)
    dialog._Import_Request()
    assert automatic == [tmp_path / 'flight.sslog']


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    import silverstar_flp.ui.main_window as module
    monkeypatch.setattr(module, 'QSettings', lambda *args: QSettings(str(tmp_path / 'private.ini'), QSettings.Format.IniFormat))
    result = MainWindow(builtin_registry(), path_preferences=PathPreferences(tmp_path / 'preferences.json'))
    result._log_open_coordinator.cache = DecoderProfileCache(tmp_path / 'cache')
    qtbot.addWidget(result)
    yield result
    result._Project_SetDirty(False); result.close()


def test_normal_gui_routes_directories_to_actual_exact_coordinator(window, tmp_path, monkeypatch):
    log, package = pair(tmp_path)
    original = {path: path.read_bytes() for path in (log, package)}
    window._path_preferences.DecoderDirectories_Set((package.parent,))
    requests = []
    monkeypatch.setattr(window, '_Task_Start', lambda worker, *args: None)
    from silverstar_flp.ui import main_window as module
    class Worker:
        def __init__(self, action):
            requests.append(action(TaskContext()))
    monkeypatch.setattr(module, 'FunctionWorker', Worker)
    window.import_dialog.Paths_Set(log_path=log)
    window.import_dialog._Import_Request()
    assert len(requests) == 1 and requests[0].source_package_path == package.resolve()
    assert {path: path.read_bytes() for path in original} == original


def test_missing_explicit_manual_package_cannot_silently_use_good_cache(tmp_path):
    log, package = pair(tmp_path)
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / 'cache'))
    opened = coordinator.Open(LogOpenRequest(log, decoder_package_path=package))
    with pytest.raises(DecoderProfileError, match='decoder_package_open_failed'):
        coordinator.Open(LogOpenRequest(log, decoder_package_path=tmp_path / 'missing.ssdecoder',
            cache_reference=opened.cache_reference))


def test_project_gui_recovers_missing_source_by_exact_cache_and_configured_directory(window, tmp_path):
    log, package = pair(tmp_path)
    opened = window._log_open_coordinator.Open(LogOpenRequest(log, decoder_package_path=package))
    profile = replace(window._DecoderProfile_Build(opened), source_reference=str(tmp_path / 'missing.ssdecoder'))
    projects = tmp_path / 'projects'; projects.mkdir()
    document = ProjectDocument(project_path=projects / 'saved.ssflp', log_reference=str(log), decoder_profile=profile)
    Project_Save(document, document.project_path)
    cached, _ = window._ProjectOpen_Run(document.project_path, TaskContext())
    assert cached.package.package_sha256 == opened.package.package_sha256
    window._log_open_coordinator.cache = DecoderProfileCache(tmp_path / 'empty-cache')
    window._path_preferences.DecoderDirectories_Set((package.parent,))
    discovered, _ = window._ProjectOpen_Run(document.project_path, TaskContext())
    assert discovered.source_package_path == package.resolve()


def test_failed_exact_open_keeps_log_in_manual_chooser(window, tmp_path):
    log = tmp_path / 'flight.sslog'
    window._LogOpen_Error('decoder_profile_exact_match_missing:Descriptor required', log)
    assert window.import_dialog.isVisible()
    assert window.import_dialog.path_edit.text() == str(log)
    assert window.import_dialog.source_type_combo.currentData() == 'manual'
    assert not window.import_dialog.custom_decoder_check.isChecked()
    window.import_dialog.reject()
