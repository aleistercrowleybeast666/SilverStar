"""Small isolated logical-removal transactions; never operates on a user's project."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QMessageBox

from silverstar_flp.core.analysis_source import ReplayResultChangeResult, ReplayResultStore
from silverstar_flp.core.artifacts import Artifact_Read, FileHash_Get
from silverstar_flp.core.context import TaskContext, TaskCancelledError
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load, ProjectNumericalIdentity_Get
from silverstar_flp.core.project_cache import ProjectCache_Inspect, ProjectCache_UnusedRemove
from silverstar_flp.core.replay_execution import Replay_Execute
from silverstar_flp.core.run_history import ProjectRun_Remove, ProjectRun_Restore, ProjectRun_BackupLoad
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_project_artifacts import _Document_Build, _Assert_Result


@pytest.fixture(scope='module')
def small_runs(tmp_path_factory):
    opened = NavigationPair_Open(tmp_path_factory.mktemp('delete-input'), flight_samples=21)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.pure_ins')
    results = tuple(Replay_Execute(plugin, opened.dataset,
        ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={'gravity_mps2': gravity}))
        for gravity in (9.8, 9.81))
    return opened, results


def _Saved(tmp_path, small_runs):
    opened, results = small_runs
    store = ReplayResultStore()
    entries = tuple(store.Result_Add(result) for result in results)
    document = _Document_Build(opened, tmp_path / 'flight.ssflp')
    document.notes = 'preserve notes'
    document.ui_state = {'analysis_source': entries[1].source_id, 'secondary_source': entries[0].source_id}
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    return document, store, entries


def test_removed_highest_index_is_never_reused_and_undo_is_exact(small_runs):
    _, results = small_runs
    store = ReplayResultStore()
    first, second = [store.Result_Add(result) for result in results]
    store.ActiveSource_Set(second.source_id)
    assert store.Result_Remove(second.result_id) == ReplayResultChangeResult.REMOVED
    assert not store.ActiveSource_Get().available
    third = store.Result_Add(results[1])
    assert third.run_index == 3
    assert store.Entry_Get(first.result_id) is first
    assert store.Result_Restore(second) == ReplayResultChangeResult.RESTORED
    assert store.ActiveSource_Get().source_id == second.source_id and store.ActiveSource_Get().available
    assert store.Result_Restore(second) == ReplayResultChangeResult.NOT_DELETED
    assert store.Result_Remove(second.result_id) == ReplayResultChangeResult.REMOVED
    assert store.Result_Restore(replace(second, source_id=first.source_id)) == ReplayResultChangeResult.CONFLICT
    assert store.Entry_Get(second.result_id) is None
    assert store.Result_Remove('recorded:kf6') == ReplayResultChangeResult.NOT_FOUND


@pytest.mark.parametrize('save_data', [True, False])
def test_delete_save_reopen_recover_and_reserved_index(tmp_path, small_runs, monkeypatch, save_data):
    opened, results = small_runs
    document, store, entries = _Saved(tmp_path, small_runs)
    original_reference = deepcopy(document.result_artifact)
    original_hash = FileHash_Get(tmp_path / original_reference['path'])
    assert ProjectRun_Remove(document, store, entries[1].result_id) == ReplayResultChangeResult.REMOVED
    document.save_data_and_results = save_data
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    monkeypatch.setattr(type(builtin_registry().Algorithm_Get('silverstar.algorithm.pure_ins')),
                        'run', lambda *args: pytest.fail('No automatic replay'))
    loaded = Project_Load(document.project_path)
    restored = ProjectResults_Load(loaded)
    assert [entry.result_id for entry in restored.Entries_Get()] == ([entries[0].result_id] if save_data else [])
    assert entries[1].result_id not in loaded.replay_configurations
    assert loaded.notes == 'preserve notes'
    assert restored.Result_Add(results[1]).run_index == 3
    backup = ProjectRun_BackupLoad(loaded, entries[1].result_id)
    _Assert_Result(entries[1].result, backup.result)
    assert ProjectRun_Restore(loaded, restored, backup) == ReplayResultChangeResult.RESTORED
    assert entries[1].result_id not in loaded.removed_results
    assert FileHash_Get(tmp_path / original_reference['path']) == original_hash
    if save_data:
        payload = Artifact_Read(document.project_path, document.result_artifact, ProjectNumericalIdentity_Get(document))
        assert [item['result_id'] for item in payload] == [entries[0].result_id]


@pytest.mark.parametrize('fault', ['cancel', 'disk_full'])
def test_failed_save_keeps_committed_references_and_window_undo(tmp_path, small_runs, monkeypatch, fault):
    opened, _ = small_runs
    document, store, entries = _Saved(tmp_path, small_runs)
    committed = document.project_path.read_bytes()
    reference = deepcopy(document.result_artifact)
    ProjectRun_Remove(document, store, entries[1].result_id)
    if fault == 'cancel':
        context = TaskContext(); context.Cancel_Request()
        with pytest.raises(TaskCancelledError):
            Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset, context=context)
    else:
        import silverstar_flp.core.project as module
        monkeypatch.setattr(module.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(OSError, match='disk full'):
            Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    assert document.project_path.read_bytes() == committed
    assert document.result_artifact == reference
    assert len(ProjectResults_Load(Project_Load(document.project_path)).Entries_Get()) == 2
    assert ProjectRun_Restore(document, store, store.RemovedEntry_Get(entries[1].result_id)) == ReplayResultChangeResult.RESTORED
    assert len(store.Entries_Get()) == 2


@pytest.mark.parametrize('save_data', [True, False])
def test_save_as_recovery_dependency_and_local_move(tmp_path, small_runs, save_data):
    opened, _ = small_runs
    origin = tmp_path / 'origin'; origin.mkdir()
    document, store, entries = _Saved(origin, small_runs)
    original_bytes = document.project_path.read_bytes()
    original_manifest = origin / document.result_artifact['path']
    original_hash = FileHash_Get(original_manifest)
    ProjectRun_Remove(document, store, entries[1].result_id)
    document.save_data_and_results = save_data
    target = tmp_path / 'copy' / 'other.ssflp'
    Project_Save(document, target, replay_store=store, dataset=opened.dataset)
    backup = document.removed_results[entries[1].result_id]['backup']
    assert (backup['project_reference'] is None) == save_data
    target.parent.rename(tmp_path / 'moved')
    moved = Project_Load(tmp_path / 'moved' / target.name)
    _Assert_Result(entries[1].result, ProjectRun_BackupLoad(moved, entries[1].result_id).result)
    assert (origin / 'flight.ssflp').read_bytes() == original_bytes
    assert FileHash_Get(original_manifest) == original_hash
    if save_data:
        inventory = ProjectCache_Inspect(moved.project_path)
        generation = next(item['generation'] for item in inventory['generations'] if item['role'] == 'deleted_run_backup')
        with pytest.raises(ValueError, match='protected'):
            ProjectCache_UnusedRemove(moved.project_path, generation)


def test_missing_recovery_candidate_never_substitutes_another_run(tmp_path, small_runs):
    opened, _ = small_runs
    document, store, entries = _Saved(tmp_path, small_runs)
    # Add an unsaved run; the old bundle contains only runs #1 and #2.
    third = store.Result_Add(entries[1].result)
    ProjectRun_Remove(document, store, third.result_id)
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    with pytest.raises(ValueError, match='backup_unavailable'):
        ProjectRun_BackupLoad(Project_Load(document.project_path), third.result_id)
    assert len(store.Entries_Get()) == 2 and store.RemovedEntry_Get(third.result_id) is third


def test_old_v3_configuration_only_run_indices_are_reserved(tmp_path, small_runs):
    document, store, entries = _Saved(tmp_path, small_runs)
    entry = entries[1]
    configuration = {'algorithm_id': entry.algorithm_id, 'algorithm_version': entry.algorithm_version,
        'mode': entry.mode.value, 'input_source': entry.input_source, 'actual_values': dict(entry.parameters),
        'parameter_schema_identity': entry.diagnostics['parameter_schema_identity'],
        'provenance': entry.diagnostics['config_source']}
    payload = json.loads(document.project_path.read_text())
    payload.pop('run_identity_state'); payload.pop('removed_results')
    payload.update(save_data_and_results=False, result_artifact=None, parse_artifact=None,
                   replay_configurations={entry.result_id: configuration})
    document.project_path.write_text(json.dumps(payload), encoding='utf-8')
    loaded = Project_Load(document.project_path)
    restored = ProjectResults_Load(loaded)
    assert restored.Result_Add(entry.result).run_index == 3


def test_gui_cancel_delete_primary_secondary_busy_and_undo(qtbot, tmp_path, small_runs, monkeypatch):
    from silverstar_flp.ui.main_window import MainWindow
    from silverstar_flp.core.project import ProjectDocument
    opened, results = small_runs
    window = MainWindow(builtin_registry()); qtbot.addWidget(window)
    errors = []; monkeypatch.setattr(window, '_Error_Show', errors.append)
    window._LogOpenResult_Set(opened, ProjectDocument())
    entries = [window._replay_store.Result_Add(result) for result in results]
    window._AnalysisSource_Set(entries[1].source_id)
    window._SecondarySource_Set(entries[0].source_id)
    assert window._Project_Write(tmp_path / 'flight.ssflp')
    confirmations = []
    def cancel(*args):
        confirmations.append(args[2]); return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, 'warning', cancel)
    window._ReplayRun_Delete(entries[1].result_id)
    assert len(window._replay_store.Entries_Get()) == 2 and not window._project_dirty
    assert '原始日志' in confirmations[-1] and '不回收磁盘空间' in confirmations[-1]
    monkeypatch.setattr(QMessageBox, 'warning', lambda *_: QMessageBox.StandardButton.Yes)
    window._ReplayRun_Delete(entries[1].result_id)
    assert not window._replay_store.ActiveSource_Get().available and window._project_dirty
    assert window._replay_store.ActiveSource_Get().source_id == entries[1].source_id
    window._ReplayRun_Delete(entries[0].result_id)
    assert window._secondary_source_id is None and window.replay_page._last_entry is None
    window.replay_page.Task_Busy()
    assert not window.replay_page.result_delete_button.isEnabled()
    assert not window.replay_page.result_restore_button.isEnabled()
    window.replay_page.Task_Finish()
    window._ReplayRun_Restore(entries[1].result_id)
    assert window._replay_store.ActiveSource_Get().available
    assert window._replay_store.Entry_Get(entries[0].result_id) is None
    assert window._Project_Write(tmp_path / 'flight.ssflp') and not errors
    assert len(ProjectResults_Load(Project_Load(tmp_path / 'flight.ssflp')).Entries_Get()) == 1
    window._Project_SetDirty(False); window.close()


def test_gui_saved_recovery_runs_off_gui_thread_and_reopen_retains_missing_primary(qtbot, tmp_path, small_runs, monkeypatch):
    import threading
    import silverstar_flp.ui.main_window as module
    opened, _ = small_runs
    document, store, entries = _Saved(tmp_path, small_runs)
    ProjectRun_Remove(document, store, entries[1].result_id)
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    loaded = Project_Load(document.project_path)
    loaded.restored_results = ProjectResults_Load(loaded).Entries_Get()
    window = module.MainWindow(builtin_registry()); qtbot.addWidget(window)
    errors = []; monkeypatch.setattr(window, '_Error_Show', errors.append)
    window._LogOpenResult_Set(opened, loaded)
    assert window._replay_store.ActiveSource_Get().source_id == entries[1].source_id
    assert not window._replay_store.ActiveSource_Get().available
    assert errors == ['project_run_deleted:' + entries[1].source_id]
    errors.clear()
    original = module.ProjectRun_BackupLoad
    gui_thread = threading.get_ident(); calls = []
    def recover(*args):
        calls.append(threading.get_ident())
        return original(*args)
    monkeypatch.setattr(module, 'ProjectRun_BackupLoad', recover)
    window._ReplayRun_Restore(entries[1].result_id)
    assert window._active_worker is not None
    window._ReplayRun_Delete(entries[0].result_id)
    assert window._replay_store.Entry_Get(entries[0].result_id) is not None
    qtbot.waitUntil(lambda: window._active_worker is None, timeout=30000)
    assert len(calls) == 1 and calls[0] != gui_thread
    assert window._replay_store.ActiveSource_Get().available and window._project_dirty
    assert errors == ['another_background_task_is_running']
    window._Project_SetDirty(False); window.close()


@pytest.mark.parametrize('bad', ['traversal', 'identity', 'deleted_configuration'])
def test_hostile_recovery_history_is_rejected(tmp_path, small_runs, bad):
    opened, _ = small_runs
    document, store, entries = _Saved(tmp_path, small_runs)
    ProjectRun_Remove(document, store, entries[1].result_id)
    Project_Save(document, document.project_path, replay_store=store, dataset=opened.dataset)
    payload = json.loads(document.project_path.read_text())
    if bad == 'traversal':
        payload['removed_results'][entries[1].result_id]['backup']['artifact_reference']['path'] = '../escape/manifest.json'
    elif bad == 'identity':
        payload['run_identity_state']['limits']['pure_ins:what_if'] = 1
    else:
        entry = entries[1]
        payload['replay_configurations'][entry.result_id] = {
            'algorithm_id': entry.algorithm_id, 'algorithm_version': entry.algorithm_version,
            'mode': entry.mode.value, 'input_source': entry.input_source, 'actual_values': dict(entry.parameters),
            'parameter_schema_identity': entry.diagnostics['parameter_schema_identity'],
            'provenance': entry.diagnostics['config_source']}
    document.project_path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='artifact_path|run_identity|deleted_run_configuration'):
        Project_Load(document.project_path)
