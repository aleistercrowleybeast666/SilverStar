"""Numerical project history and transactional rejection, using small real engines."""
from dataclasses import replace
from pathlib import Path
import json

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Write, FileHash_Get
from silverstar_flp.core.context import TaskContext, TaskCancelledError
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_project_export import _ProjectDocument_Build


def _Assert_Result(first, second):
    assert first.algorithm_id == second.algorithm_id
    assert first.algorithm_version == second.algorithm_version
    assert first.parameters == second.parameters
    assert first.fidelity == second.fidelity
    assert first.provenance == second.provenance
    assert first.warnings == second.warnings
    assert first.missing_inputs == second.missing_inputs
    assert set(first.channels) == set(second.channels)
    for channel, a in first.channels.items():
        b = second.channels[channel]
        for field in ('timestamp_us', 'values', 'valid'):
            av, bv = getattr(a, field), getattr(b, field)
            assert av.dtype == bv.dtype and av.shape == bv.shape
            np.testing.assert_array_equal(av, bv)
            assert not bv.flags.writeable
        assert (a.unit, a.quantity, a.source, a.columns) == (b.unit, b.quantity, b.source, b.columns)
        assert dict(a.metadata) == dict(b.metadata)
    # Codec round-trip of audit data preserves tuple/list/float/array types too.
    assert repr(first.diagnostics) == repr(second.diagnostics)


def test_four_completed_algorithms_and_two_distinct_runs_roundtrip(tmp_path, monkeypatch):
    opened = NavigationPair_Open(tmp_path / 'pair', flight_samples=41)
    store = ReplayResultStore()
    registry = builtin_registry()
    for plugin in registry.algorithms:
        request = ReplayRequest(mode=ReplayMode.WHAT_IF,
                                process_model_revision=2 if plugin.metadata.plugin_id.endswith('kf6') else None)
        result = plugin.run(opened.dataset, request)
        assert result.channels and not result.missing_inputs
        store.Result_Add(result, algorithm_name=plugin.metadata.display_name)
    plugin = registry.Algorithm_Get('silverstar.algorithm.pure_ins')
    store.Result_Add(plugin.run(opened.dataset, ReplayRequest(mode=ReplayMode.WHAT_IF,
                                                            parameters={'gravity_mps2':9.81})))
    path = tmp_path / 'project.ssflp'
    document = _ProjectDocument_Build(opened.dataset.source_path, path)
    document.notes = 'Keep history'
    document.ui_state = {'analysis_source': store.Entries_Get()[3].source_id,
                         'secondary_source': store.Entries_Get()[0].source_id}
    Project_Save(document, path, replay_store=store, dataset=opened.dataset)
    for cls in {type(plugin) for plugin in registry.algorithms}:
        monkeypatch.setattr(cls, 'run', lambda *args: pytest.fail('Reopen must not recompute'))
    loaded = Project_Load(path)
    restored = ProjectResults_Load(loaded)
    assert len(restored.Entries_Get()) == 5
    assert loaded.ui_state == document.ui_state and loaded.notes == 'Keep history'
    for a, b in zip(store.Entries_Get(), restored.Entries_Get()):
        assert (a.result_id, a.source_id, a.run_index) == (b.result_id, b.source_id, b.run_index)
        _Assert_Result(a.result, b.result)
    copied = tmp_path / 'copy' / 'other.ssflp'
    Project_Save(loaded, copied)
    moved = tmp_path / 'moved'
    copied.parent.rename(moved)
    again = ProjectResults_Load(Project_Load(moved / copied.name))
    assert len(again.Entries_Get()) == 5


@pytest.mark.parametrize('fault', ['cancel', 'disk_full', 'array_corrupt', 'manifest_corrupt', 'path_escape'])
def test_artifact_failures_leave_committed_project_intact(tmp_path, monkeypatch, fault):
    source = tmp_path / 'log.sslog'; source.write_bytes(b'immutable source')
    document = _ProjectDocument_Build(source, tmp_path / 'flight.ssflp')
    Project_Save(document, document.project_path, replay_store=ReplayResultStore())
    before = document.project_path.read_bytes()
    loaded = Project_Load(document.project_path)
    if fault == 'cancel':
        context = TaskContext(); context.Cancel_Request()
        with pytest.raises(TaskCancelledError):
            Project_Save(document, document.project_path, replay_store=ReplayResultStore(), context=context)
    elif fault == 'disk_full':
        monkeypatch.setattr(np, 'save', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(OSError, match='disk full'):
            Artifact_Write(document.project_path, np.arange(3), {'test':1})
    elif fault == 'path_escape':
        loaded.result_artifact['path'] = '../untrusted/manifest.json'
        with pytest.raises(ValueError, match='artifact_path'):
            ProjectResults_Load(loaded)
    else:
        reference = Artifact_Write(document.project_path, np.arange(3), {'test':1})
        manifest = document.project_path.parent / reference['path']
        path = manifest if fault == 'manifest_corrupt' else next(manifest.parent.glob('*.npy'))
        path.write_bytes(b'broken')
        with pytest.raises((ValueError, OSError)):
            Artifact_Read(document.project_path, reference, {'test':1})
    assert document.project_path.read_bytes() == before
    assert source.read_bytes() == b'immutable source'


@pytest.mark.parametrize('change', ['log', 'decoder', 'engine', 'parameters'])
def test_numerical_identity_mismatch_does_not_recompute(tmp_path, monkeypatch, change):
    opened = NavigationPair_Open(tmp_path / 'pair', flight_samples=21)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.pure_ins')
    result = plugin.run(opened.dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    store = ReplayResultStore(); entry = store.Result_Add(result)
    document = _ProjectDocument_Build(opened.dataset.source_path, tmp_path / 'project.ssflp')
    document.replay_configurations[entry.result_id] = {
        'algorithm_id':result.algorithm_id, 'algorithm_version':result.algorithm_version,
        'mode':entry.mode.value, 'input_source':result.input_source,
        'actual_values':dict(result.parameters),
        'parameter_schema_identity':result.diagnostics['parameter_schema_identity'],
        'provenance':result.diagnostics['config_source']}
    Project_Save(document, document.project_path, replay_store=store)
    if change == 'log':
        with opened.dataset.source_path.open('ab') as target: target.write(b'changed')
    elif change == 'decoder':
        document.decoder_profile = replace(document.decoder_profile, package_sha256='a'*64)
    elif change == 'engine':
        monkeypatch.setattr('silverstar_flp.core.artifacts.EngineIdentity_Get', lambda:'b'*64)
    else:
        document.replay_configurations[entry.result_id]['actual_values']['gravity_mps2'] = 9.81
    monkeypatch.setattr(type(plugin), 'run', lambda *args: pytest.fail('Must not recompute'))
    with pytest.raises(ValueError, match='identity_mismatch|configuration_mismatch'):
        ProjectResults_Load(document)


def test_object_arrays_and_hostile_npy_shape_are_rejected_before_allocation(tmp_path):
    path = tmp_path / 'project.ssflp'
    with pytest.raises(ValueError, match='array_invalid'):
        Artifact_Write(path, np.asarray([object()], dtype=object), {})
    reference = Artifact_Write(path, np.arange(3), {})
    manifest_path = tmp_path / reference['path']
    manifest = json.loads(manifest_path.read_text())
    name = next(iter(manifest['arrays']))
    array_path = manifest_path.parent / name
    with array_path.open('wb') as target:
        np.lib.format.write_array_header_1_0(target, {'descr':'<i8','fortran_order':False,
                                                     'shape':(2**50,)})
    sha = FileHash_Get(array_path)
    spec = manifest['arrays'].pop(name)
    spec['sha256'] = sha; spec['bytes'] = array_path.stat().st_size
    new_name = sha + '.npy'; array_path.rename(manifest_path.parent / new_name)
    manifest['arrays'][new_name] = spec; manifest['payload']['array'] = new_name
    manifest_path.write_text(json.dumps(manifest))
    reference['sha256'] = FileHash_Get(manifest_path)
    with pytest.raises(ValueError, match='header_invalid'):
        Artifact_Read(path, reference, {})


def test_gui_reopen_restores_every_run_and_two_sources_without_replay(qtbot, tmp_path, monkeypatch):
    from silverstar_flp.core.project import ProjectDocument
    from silverstar_flp.ui.main_window import MainWindow
    opened = NavigationPair_Open(tmp_path / 'pair', flight_samples=41)
    registry = builtin_registry()
    first = MainWindow(registry); qtbot.addWidget(first)
    errors = []; monkeypatch.setattr(first, '_Error_Show', errors.append)
    first._LogOpenResult_Set(opened, ProjectDocument())
    for plugin in registry.algorithms:
        request = ReplayRequest(mode=ReplayMode.WHAT_IF,
            process_model_revision=2 if plugin.metadata.plugin_id.endswith('kf6') else None)
        first._replay_store.Result_Add(plugin.run(opened.dataset, request),
                                      algorithm_name=plugin.metadata.display_name)
    entries = first._replay_store.Entries_Get()
    first._AnalysisSource_Set(entries[3].source_id)
    first._SecondarySource_Set(entries[0].source_id)
    path = tmp_path / 'flight.ssflp'
    first._Project_Write(path)
    assert not errors and path.is_file()
    first._project_dirty = False; first.close()
    for cls in {type(plugin) for plugin in registry.algorithms}:
        monkeypatch.setattr(cls, 'run', lambda *args: pytest.fail('GUI reopen must not replay'))
    second = MainWindow(registry); qtbot.addWidget(second)
    monkeypatch.setattr(second, '_Error_Show', errors.append)
    second._Project_Open(path)
    qtbot.waitUntil(lambda: second._active_worker is None, timeout=15000)
    assert not errors
    assert tuple(e.result_id for e in second._replay_store.Entries_Get()) == tuple(e.result_id for e in entries)
    assert second._replay_store.ActiveSource_Get().source_id == entries[3].source_id
    assert second._secondary_source_id == entries[0].source_id
    second._project_dirty = False; second.close()
