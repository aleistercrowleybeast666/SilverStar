"""Tiny saved-source lifecycle; never operates on user projects or runs long replay."""
from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_flp.core.analysis_source import ReplayResultChangeResult, ReplayResultStore
from silverstar_flp.core.artifacts import FileHash_Get
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load, _Reference_Encode
from silverstar_flp.core.run_history import ProjectRun_BackupLoad, ProjectRun_Remove, ProjectRun_Restore
from tests.test_project_artifact_boundaries import _SmallRun
from tests.test_project_artifacts import _Document_Build
from tests.test_audit_block_artifacts import _Fingerprint


@pytest.fixture(scope='module')
def small_input(tmp_path_factory):
    opened, _, store = _SmallRun(tmp_path_factory.mktemp('provenance-input'))
    return opened, store.Entries_Get()[0].result


def _Restored(tmp_path, small_input):
    opened, result = small_input
    store = ReplayResultStore(); entry = store.Result_Add(result)
    document = _Document_Build(opened, tmp_path/'origin.ssflp')
    document.notes = 'keep provenance notes'
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    assert ProjectRun_Remove(document, store, entry.result_id) == ReplayResultChangeResult.REMOVED
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    document = Project_Load(document.project_path)
    store = ProjectResults_Load(document)
    restored = ProjectRun_BackupLoad(document, entry.result_id)
    backup = deepcopy(document.removed_results[entry.result_id]['backup'])
    assert ProjectRun_Restore(document, store, restored) == ReplayResultChangeResult.RESTORED
    return opened, document, store, restored, backup


@pytest.mark.parametrize('save_as', [False, True])
def test_restore_config_save_remove_retains_exact_historical_source(tmp_path, small_input, monkeypatch, save_as):
    opened, document, store, entry, backup = _Restored(tmp_path, small_input)
    origin = document.project_path
    manifest = origin.parent/backup['artifact_reference']['path']
    before = {file.name: FileHash_Get(file) for file in manifest.parent.iterdir()}
    document.save_data_and_results = False
    target = tmp_path/'elsewhere'/'config.ssflp' if save_as else origin
    import silverstar_flp.core.artifacts as artifacts
    # Configuration persistence and ordinary result reopening must not load or
    # copy historical arrays. Explicit recovery below is separately allowed.
    with monkeypatch.context() as patch:
        patch.setattr(artifacts, 'Artifact_Read', lambda *a, **k: pytest.fail('automatic historical result load'))
        Project_Save(document, target, replay_store=store, dataset=opened.dataset)
        reopened = Project_Load(target)
        assert reopened.result_artifact is None and reopened.parse_artifact is None
        assert ProjectResults_Load(reopened).Entries_Get() == ()
    assert reopened.notes == 'keep provenance notes'
    assert {file.name: FileHash_Get(file) for file in manifest.parent.iterdir()} == before
    if save_as:
        backup['project_reference'] = _Reference_Encode(origin, target.resolve())
        assert not (target.parent/(target.name+'.artifacts')).exists()
    assert ProjectRun_Remove(document, store, entry.result_id) == ReplayResultChangeResult.REMOVED
    assert document.removed_results[entry.result_id]['backup'] == backup
    Project_Save(document, target, replay_store=store, dataset=opened.dataset)
    deleted = Project_Load(target)
    assert ProjectResults_Load(deleted).Entries_Get() == ()
    recovered = ProjectRun_BackupLoad(deleted, entry.result_id)
    assert (recovered.result_id, recovered.source_id, recovered.run_index) == (
        entry.result_id, entry.source_id, entry.run_index)
    assert _Fingerprint(recovered.result) == _Fingerprint(entry.result)
    assert recovered.diagnostics['input_identity'] == entry.diagnostics['input_identity']
    assert recovered.diagnostics['engine_identity'] == entry.diagnostics['engine_identity']
    assert dict(recovered.parameters) == dict(entry.parameters)


@pytest.fixture(scope='module')
def active_history(tmp_path_factory, small_input):
    opened, document, store, entry, _ = _Restored(tmp_path_factory.mktemp('active-history'), small_input)
    document.save_data_and_results = False
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    return opened, document, entry


def _RemovedSnapshot(active_history):
    _, original, entry = active_history
    document = deepcopy(original)
    store = ReplayResultStore()
    store.Result_Add(entry.result, restored_run_index=entry.run_index, algorithm_name=entry.algorithm_name)
    store.IdentityState_Restore(document.run_identity_state)
    assert ProjectRun_Remove(document, store, entry.result_id) == ReplayResultChangeResult.REMOVED
    return document, store, entry


@pytest.mark.parametrize('fault', ['hash', 'input', 'engine', 'parameters'])
def test_historical_source_recovery_still_checks_identity_and_never_replays(active_history, monkeypatch, fault):
    document, _, entry = _RemovedSnapshot(active_history)
    import silverstar_flp.core.artifacts as artifacts
    from silverstar_flp.plugins.registry import builtin_registry
    plugin = builtin_registry().Algorithm_Get(entry.algorithm_id)
    monkeypatch.setattr(type(plugin), 'run', lambda *a, **k: pytest.fail('implicit replay'))
    if fault == 'hash':
        document.removed_results[entry.result_id]['backup']['artifact_reference']['sha256'] = '0'*64
        expected = '^artifact_manifest_corrupt$'
    elif fault == 'input':
        original_hash = artifacts.FileHash_Get
        monkeypatch.setattr(artifacts, 'FileHash_Get', lambda path, *a, **k:
            '0'*64 if path == document.LogPath_Resolve() else original_hash(path, *a, **k))
        expected = 'identity'
    elif fault == 'engine':
        monkeypatch.setattr(artifacts, 'EngineIdentity_Get', lambda: '0'*64)
        expected = 'identity'
    else:
        document.removed_results[entry.result_id]['configuration']['actual_values']['gravity_mps2'] += 0.01
        expected = 'configuration'
    with pytest.raises(ValueError, match=expected):
        ProjectRun_BackupLoad(document, entry.result_id)


def test_different_parameters_cannot_restore_same_run_or_relabel_saved_source(active_history):
    document, store, entry = _RemovedSnapshot(active_history)
    before = deepcopy(document.removed_results)
    parameters = dict(entry.parameters); parameters['gravity_mps2'] += 0.01
    wrong = replace(entry, parameters=parameters, result=replace(entry.result, parameters=parameters))
    assert ProjectRun_Restore(document, store, wrong) == ReplayResultChangeResult.CONFLICT
    assert store.Entries_Get() == () and document.removed_results == before
    assert document.recovery_sources == {}


@pytest.mark.parametrize('fault', ['path', 'id', 'overlap', 'null', 'mode'])
def test_recovery_source_metadata_is_strict(active_history, fault):
    _, original, entry = active_history
    document = deepcopy(original)
    source = document.recovery_sources[entry.result_id]
    if fault == 'path':
        source['backup']['artifact_reference']['path'] = '../escape/manifest.json'
    elif fault == 'id':
        document.recovery_sources['recorded'] = document.recovery_sources.pop(entry.result_id)
    elif fault == 'overlap':
        document.run_identity_state['deleted'] = [entry.result_id]
        document.removed_results[entry.result_id] = deepcopy(source)
    elif fault == 'null':
        source['backup'] = None
    else:
        source['configuration']['mode'] = 'offline'
    from silverstar_flp.core.run_history import RunHistory_Validate
    with pytest.raises(ValueError, match='artifact_path|run_identity|recovery_sources'):
        RunHistory_Validate(document)


@pytest.mark.parametrize('fault', ['cancel', 'disk_full'])
def test_failed_config_save_as_keeps_committed_source_metadata(tmp_path, active_history, monkeypatch, fault):
    _, original, _ = active_history
    document = deepcopy(original)
    committed = document.project_path.read_bytes()
    old_path = document.project_path
    before = deepcopy(document.recovery_sources)
    from silverstar_flp.core.context import TaskContext, TaskCancelledError
    context = TaskContext()
    if fault == 'cancel':
        context.Cancel_Request(); expected = TaskCancelledError
    else:
        import silverstar_flp.core.project as module
        monkeypatch.setattr(module.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
        expected = OSError
    target = tmp_path/'failed.ssflp'
    with pytest.raises(expected):
        Project_Save(document, target, context=context)
    assert not target.exists() and document.project_path == old_path
    assert document.recovery_sources == before and old_path.read_bytes() == committed


@pytest.mark.parametrize('language', ['zh_CN', 'en_US'])
def test_ui_distinguishes_current_memory_history_and_saved_membership(qtbot, qapp, active_history, language):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PySide6.QtWidgets import QLabel
    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.main_window import MainWindow
    from silverstar_flp.ui.pages.replay import ReplayPage
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.ui.theme import Theme_Apply
    opened, document, entry = active_history
    translator = Translator(language)
    page = ReplayPage(translator, builtin_registry()); qtbot.addWidget(page)
    store = ReplayResultStore(); current = store.Result_Add(entry.result)
    page.Dataset_Set(opened.dataset, store); page.Result_Set(current)
    for theme in ('dark', 'light'):
        Theme_Apply(qapp, theme)
        for sources, saved_ids, code in (
            ({}, (), 'replay.run_memory_only'),
            (document.recovery_sources, (), 'replay.run_memory_with_history'),
            (document.recovery_sources, (current.result_id,), 'replay.run_current_saved')):
            page.RecoverySources_Set(sources, saved_ids)
            text = translator.Text_Get(code)
            assert text != code and text == page.result_storage_label.text()
            assert page.stored_results_table.item(0, 0).toolTip() == text
    page.Dataset_Set(replace(opened.dataset), store); page.Result_Set(current)
    assert page.result_storage_label.text() == translator.Text_Get('replay.run_memory_only')
    page.Dataset_Set(opened.dataset, store); page.Result_Set(current)
    # The real commit callback updates this status after config-only save.
    shell = SimpleNamespace(replay_page=page, _project_edit_serial=7,
        _Project_SetDirty=Mock(), _ProjectHeader_Refresh=Mock(), status_label=QLabel(), _translator=translator)
    MainWindow._ProjectSave_ResultSet(shell, document, 7)
    assert translator.Text_Get('replay.run_memory_with_history') == page.result_storage_label.text()
    shell._Project_SetDirty.assert_called_once_with(False)


def test_config_only_reopen_does_not_trust_serialized_saved_membership(tmp_path, active_history, monkeypatch):
    import json
    import silverstar_flp.core.artifacts as artifacts
    _, original, entry = active_history
    document = deepcopy(original)
    target = tmp_path/'configuration.ssflp'
    monkeypatch.setattr(artifacts, 'Artifact_Read', lambda *a, **k: pytest.fail('automatic candidate read'))
    Project_Save(document, target)
    payload = json.loads(target.read_text(encoding='utf-8'))
    payload['saved_result_ids'] = [entry.result_id]  # Unknown, untrusted JSON has no runtime proof.
    target.write_text(json.dumps(payload), encoding='utf-8')
    loaded = Project_Load(target)
    assert entry.result_id in loaded.recovery_sources
    assert loaded.saved_result_ids == () and loaded.result_artifact is None
    assert ProjectResults_Load(loaded).Entries_Get() == () and loaded.saved_result_ids == ()
