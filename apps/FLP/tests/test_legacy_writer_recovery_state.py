"""Actual original writer compatibility; no metadata is stripped to fabricate v3."""
from copy import deepcopy
import json
import subprocess
import sys
from types import ModuleType

import pytest

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load
from tests.test_audit_block_artifacts import _Fingerprint
from tests.test_project_artifact_boundaries import _SmallRun
from tests.test_project_artifacts import _Document_Build

WRITER_COMMIT = '1b0b1650d5270a5c904ca31b09ab5b54e0d2b73e'


@pytest.fixture(scope='module')
def legacy_writer():
    source = subprocess.check_output(['git', 'show', WRITER_COMMIT+
        ':apps/FLP/src/silverstar_flp/core/project.py'], encoding='utf-8')
    name = 'silverstar_flp.core._legacy_writer_1b_fixture'
    module = ModuleType(name); sys.modules[name] = module
    try:
        exec(compile(source, '<exact-1b-project-module>', 'exec'), module.__dict__)
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.fixture(scope='module')
def small_input(tmp_path_factory):
    opened, _, store = _SmallRun(tmp_path_factory.mktemp('legacy-writer-input'))
    return opened, store.Entries_Get()[0].result


def _LegacyWrite(tmp_path, legacy_writer, small_input, count=1):
    opened, result = small_input
    current = _Document_Build(opened, tmp_path/'old.ssflp')
    old = legacy_writer.ProjectDocument(log_reference=current.log_reference,
        decoder_profile=current.decoder_profile, project_path=current.project_path,
        notes='real old-writer notes')
    store = ReplayResultStore()
    for _ in range(count): store.Result_Add(result)
    assert old.replay_configurations == {}
    legacy_writer.Project_Save(old, old.project_path, replay_store=store, dataset=opened.dataset)
    payload = json.loads(old.project_path.read_text(encoding='utf-8'))
    assert payload['version'] == 3 and payload['replay_configurations'] == {}
    assert not {'run_identity_state', 'removed_results', 'recovery_sources'} & payload.keys()
    return opened, Project_Load(old.project_path), store


@pytest.mark.parametrize('save_data', [False, True])
def test_exact_old_writer_strict_load_can_save_with_or_without_data(tmp_path, legacy_writer, small_input, save_data):
    opened, document, original = _LegacyWrite(tmp_path, legacy_writer, small_input)
    old_path = document.project_path
    committed = old_path.read_bytes()
    store = ProjectResults_Load(document)
    entry = store.Entries_Get()[0]
    assert entry.result_id == 'pure_ins:what_if:1'
    assert store.IdentityState_Get()['limits'] == {'pure_ins:what_if': 1}
    assert _Fingerprint(entry.result) == _Fingerprint(original.Entries_Get()[0].result)
    document.save_data_and_results = save_data
    target = tmp_path/'new.ssflp'
    Project_Save(document, target, replay_store=store, dataset=opened.dataset)
    assert document.run_identity_state == store.IdentityState_Get()
    reloaded = Project_Load(target)
    assert reloaded.notes == 'real old-writer notes'
    assert reloaded.run_identity_state['limits'] == {'pure_ins:what_if': 1}
    restored = ProjectResults_Load(reloaded)
    if save_data:
        assert _Fingerprint(restored.Entries_Get()[0].result) == _Fingerprint(entry.result)
    else:
        assert restored.Entries_Get() == () and reloaded.result_artifact is None
    assert old_path.read_bytes() == committed


@pytest.mark.parametrize('fault', ['late_result', 'merged_admission', 'saved_ids_allocation'])
def test_failed_strict_load_does_not_publish_reservations_or_sources(tmp_path, legacy_writer, small_input, monkeypatch, fault):
    _, document, _ = _LegacyWrite(tmp_path, legacy_writer, small_input, count=2)
    before = (deepcopy(document.run_identity_state), deepcopy(document.recovery_sources), document.saved_result_ids)
    committed = document.project_path.read_bytes()
    if fault == 'late_result':
        import silverstar_flp.core.artifacts as artifacts
        original_read = artifacts.Artifact_Read
        def corrupt_late(*args, **kwargs):
            items = original_read(*args, **kwargs)
            changed = dict(items[1]); changed['source_id'] = 'wrong-source'
            return (items[0], changed)
        monkeypatch.setattr(artifacts, 'Artifact_Read', corrupt_late)
        expected = 'result_identity_mismatch'
    elif fault == 'merged_admission':
        import silverstar_flp.core.run_history as history
        original_validate = history.RunHistory_Validate
        def reject_pending(candidate):
            if candidate.recovery_sources:
                raise ValueError('project_run_recovery_sources_invalid')
            original_validate(candidate)
        monkeypatch.setattr(history, 'RunHistory_Validate', reject_pending)
        expected = 'recovery_sources_invalid'
    else:
        import builtins
        import silverstar_flp.core.project as module
        class TupleGate(type):
            def __instancecheck__(cls, value): return isinstance(value, builtins.tuple)
        class AllocationFailureTuple(builtins.tuple, metaclass=TupleGate):
            def __new__(cls, value=()):
                if isinstance(value, dict): raise MemoryError('saved_ids_allocation_failed')
                return builtins.tuple(value)
        monkeypatch.setattr(module, 'tuple', AllocationFailureTuple, raising=False)
        expected = 'saved_ids_allocation_failed'
    error = MemoryError if fault == 'saved_ids_allocation' else ValueError
    with pytest.raises(error, match=expected): ProjectResults_Load(document)
    assert (document.run_identity_state, document.recovery_sources, document.saved_result_ids) == before
    assert document.project_path.read_bytes() == committed
