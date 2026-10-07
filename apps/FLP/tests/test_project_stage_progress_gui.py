"""Private offscreen GUI fixtures and one reused 21-sample actual input/run."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent

from silverstar_flp.core.project import Project_Save, Project_Load
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.decoder_profiles.parser import DecoderProfileParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from tests.test_project_artifact_boundaries import _SmallRun


@pytest.fixture(scope='module')
def small_input(tmp_path_factory):
    return _SmallRun(tmp_path_factory.mktemp('input'))


@pytest.fixture
def private_settings(monkeypatch, tmp_path):
    import silverstar_flp.ui.main_window as module
    monkeypatch.setattr(module, 'QSettings', lambda *args:
        QSettings(str(tmp_path/'private.ini'), QSettings.Format.IniFormat))


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path, private_settings):
    result = MainWindow(builtin_registry()); qtbot.addWidget(result)
    result._log_open_coordinator.cache = DecoderProfileCache(tmp_path/'decoder')
    result.test_errors = []; monkeypatch.setattr(result, '_Error_Show', result.test_errors.append)
    result.test_values = []; result.test_reports = []; result.test_threads = []
    def changed(value):
        result.test_values.append(value); result.test_threads.append(get_ident())
    result.progress_bar.valueChanged.connect(changed)
    start = result._Task_Start
    def observe(worker, *args, **kwargs):
        worker.signals.progress.connect(lambda value, code:
            result.test_reports.append((value, code)), Qt.ConnectionType.DirectConnection)
        return start(worker, *args, **kwargs)
    monkeypatch.setattr(result, '_Task_Start', observe)
    yield result
    if result._active_worker is not None:
        result._active_worker.Worker_Cancel()
        qtbot.waitUntil(lambda: result._active_worker is None, timeout=15000)
    result._Project_SetDirty(False); result.close()


def _Document(small_input):
    opened, original, store = small_input
    document = replace(original, replay_configurations=deepcopy(original.replay_configurations),
        removed_results={}, recovery_sources={}, result_artifact=None, parse_artifact=None)
    return opened, document, store


def _Finished(qtbot, window, *, success):
    qtbot.waitUntil(lambda: window._active_worker is None, timeout=15000)
    assert window.test_values == sorted(window.test_values)
    assert all(0 <= value <= 1000 for value in window.test_values)
    assert all(value < 1 for value, _ in window.test_reports)
    assert window.progress_bar.value() == 1000 if success else window.progress_bar.value() < 1000
    assert all(thread == get_ident() for thread in window.test_threads)


@pytest.mark.parametrize('save_data', [False, True])
def test_background_save_stages_finish_only_after_gui_publication(qtbot, tmp_path, small_input, window, monkeypatch, save_data):
    opened, document, store = _Document(small_input)
    window._LogOpenResult_Set(opened, document)
    window._replay_store.Result_Add(store.Entries_Get()[0].result)
    callback = window._ProjectSave_ResultSet; entered = []
    def publish(*args):
        entered.append(window.progress_bar.value())
        return callback(*args)
    monkeypatch.setattr(window, '_ProjectSave_ResultSet', publish)
    path = tmp_path/'save.ssflp'
    assert window._Project_Write(path, background=True, save_data=save_data)
    _Finished(qtbot, window, success=True)
    assert entered and entered[0] < 1000 and not window.test_errors
    assert Project_Load(path).save_data_and_results == save_data
    assert 'progress.save.commit' in [code for _, code in window.test_reports]
    assert window.progress_bar.format() == window._translator.Text_Get('progress.stage_percent')


@pytest.mark.parametrize('cache', ['valid', 'missing', 'corrupt'])
def test_project_open_reads_in_worker_and_reports_cache_or_parse(qtbot, tmp_path, small_input, window, monkeypatch, cache):
    import silverstar_flp.ui.main_window as module
    opened, document, store = _Document(small_input)
    path = tmp_path/'open.ssflp'
    Project_Save(document, path, replay_store=store, dataset=opened.dataset)
    if cache == 'missing':
        import json
        payload = __import__('json').loads(path.read_text()); payload['parse_artifact'] = None
        path.write_text(json.dumps(payload), encoding='utf-8')
    if cache == 'corrupt':
        manifest = path.parent/document.parse_artifact['path']; manifest.write_bytes(b'corrupt synthetic cache')
    gui = get_ident(); read_threads = []; parsed = []
    load = module.Project_Load; parse = DecoderProfileParserPlugin.parse
    def read(*args):
        read_threads.append(get_ident()); assert get_ident() != gui
        return load(*args)
    def parser(*args, **kwargs):
        assert get_ident() != gui; parsed.append(True)
        assert cache != 'valid', 'Valid cache must not parse'
        return parse(*args, **kwargs)
    monkeypatch.setattr(module, 'Project_Load', read)
    monkeypatch.setattr(DecoderProfileParserPlugin, 'parse', parser)
    worker_plugin = builtin_registry().Algorithm_Get(store.Entries_Get()[0].algorithm_id)
    monkeypatch.setattr(type(worker_plugin), 'run', lambda *args: pytest.fail('No automatic replay'))
    entered = []; publish = window._LogOpenResult_Set
    def callback(*args, **kwargs):
        entered.append(window.progress_bar.value()); return publish(*args, **kwargs)
    monkeypatch.setattr(window, '_LogOpenResult_Set', callback)
    window._Project_Open(path)
    _Finished(qtbot, window, success=True)
    assert read_threads and entered[0] < 1000 and not window.test_errors
    assert len(window._replay_store.Entries_Get()) == 1
    codes = [code for _, code in window.test_reports]
    assert ('progress.open.dataset_cache' in codes) == (cache != 'missing')
    assert bool(parsed) == (cache != 'valid')


@pytest.mark.parametrize('action', ['cancel', 'close'])
def test_cancelled_or_closed_open_never_publishes_complete(qtbot, tmp_path, small_input, window, monkeypatch, action):
    import silverstar_flp.ui.main_window as module
    opened, document, store = _Document(small_input)
    path = tmp_path/'open.ssflp'; document.save_data_and_results = False
    Project_Save(document, path, replay_store=store, dataset=opened.dataset)
    entered, release = Event(), Event(); load = module.Project_Load
    def held(*args):
        entered.set(); assert release.wait(5); return load(*args)
    monkeypatch.setattr(module, 'Project_Load', held)
    previous = window._project
    try:
        window._Project_Open(path); qtbot.waitUntil(entered.is_set, timeout=5000)
        if action == 'cancel': window._Task_Cancel()
        else:
            event = QCloseEvent(); window.closeEvent(event); assert not event.isAccepted()
    finally: release.set()
    _Finished(qtbot, window, success=False)
    assert window._project is previous and window._dataset is None


def test_failed_open_never_reports_complete(qtbot, tmp_path, window):
    window._Project_Open(tmp_path/'missing.ssflp')
    _Finished(qtbot, window, success=False)
    assert window.test_errors


@pytest.mark.parametrize('case', ['clean_close','cancel_close_option','cancel_after_commit','snapshot_removed'])
def test_original_save_lifecycle_unchanged(qtbot, tmp_path, monkeypatch, private_settings, case):
    # Execute the original four bodies unchanged; private settings and offscreen Qt.
    from tests.test_project_save_lifecycle import test_save_lifecycle_respects_request_cancel_and_commit
    test_save_lifecycle_respects_request_cancel_and_commit(qtbot, tmp_path, monkeypatch, case)


@pytest.mark.parametrize('action', ['finish', 'cancel', 'close'])
def test_slow_array_save_keeps_gui_responsive_and_atomic(qtbot, tmp_path, small_input, window, monkeypatch, action):
    import numpy as np
    from PySide6.QtCore import QTimer
    from silverstar_flp.core.artifacts import _ProgressStream
    opened, document, store = _Document(small_input)
    window._LogOpenResult_Set(opened, document)
    result = store.Entries_Get()[0].result
    result = replace(result, diagnostics={**result.diagnostics,
        'slow_write_fixture': np.arange(400000, dtype='float64')})
    window._replay_store.Result_Add(result)
    entered, release = Event(), Event()
    original = _ProgressStream.write
    gui = get_ident()
    def held(stream, data):
        assert get_ident() != gui
        if len(data) >= 1024 * 1024:
            entered.set()
            assert release.wait(5)
            stream.context.Cancel_RaiseIfRequested()
        return original(stream, data)
    monkeypatch.setattr(_ProgressStream, 'write', held)
    path = tmp_path/'slow.ssflp'
    previous = b'old user file'; path.write_bytes(previous)
    try:
        assert window._Project_Write(path, background=True, save_data=True)
        qtbot.waitUntil(entered.is_set, timeout=15000)
        alive = []
        QTimer.singleShot(0, lambda: alive.append(True))
        qtbot.waitUntil(lambda: bool(alive), timeout=1000)
        assert window.progress_bar.value() < 1000
        assert path.read_bytes() == previous
        if action == 'cancel':
            window._Task_Cancel()
        elif action == 'close':
            # Established save lifecycle: close waits for this committed save;
            # cancellation is the separate explicit Cancel action above.
            window._Project_SetDirty(False)
            event = QCloseEvent(); window.closeEvent(event)
            assert not event.isAccepted()
    finally:
        release.set()
    _Finished(qtbot, window, success=action != 'cancel')
    if action != 'cancel':
        assert Project_Load(path).save_data_and_results
        assert any('|' in code for _, code in window.test_reports)
    else:
        assert path.read_bytes() == previous
