"""Local non-reference is not proof of ownership of an artifact generation."""
from copy import deepcopy

import pytest

from silverstar_flp.core.analysis_source import ReplayResultChangeResult
from silverstar_flp.core.artifacts import FileHash_Get
from silverstar_flp.core.project import Project_Load, Project_Save
from silverstar_flp.core.project_cache import ProjectCache_Inspect, ProjectCache_UnusedRemove
from silverstar_flp.core.run_history import ProjectRun_BackupLoad, ProjectRun_Remove, ProjectRun_Restore
from tests.test_project_artifact_boundaries import _SmallRun
from tests.test_project_artifacts import _Assert_Result


def test_config_only_save_as_dependency_survives_origin_restore_and_local_purge(tmp_path):
    origin = tmp_path/'origin'; origin.mkdir()
    opened, document, store = _SmallRun(origin)
    entry = store.Entries_Get()[0]
    Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    original_path = document.project_path
    old_reference = deepcopy(document.result_artifact)
    generation_path = (origin/old_reference['path']).parent
    before = {file.name: FileHash_Get(file) for file in generation_path.iterdir()}
    assert ProjectRun_Remove(document, store, entry.result_id) == ReplayResultChangeResult.REMOVED
    original = deepcopy(document)
    document.save_data_and_results = False
    target = tmp_path/'copy'/'config-only.ssflp'
    Project_Save(document, target, replay_store=store, dataset=opened.dataset)
    dependent = Project_Load(target)
    assert dependent.removed_results[entry.result_id]['backup']['project_reference'] is not None
    _Assert_Result(entry.result, ProjectRun_BackupLoad(dependent, entry.result_id).result)
    assert ProjectRun_Restore(original, store, entry) == ReplayResultChangeResult.RESTORED
    Project_Save(original, original_path, dataset=opened.dataset, replay_store=store)
    inventory = ProjectCache_Inspect(original_path)
    old = next(item for item in inventory['generations'] if item['generation'] == generation_path.name)
    assert old['role'] == 'unreferenced'
    with pytest.raises(ValueError, match='generation_ownership_unproven'):
        ProjectCache_UnusedRemove(original_path, generation_path.name)
    assert {file.name: FileHash_Get(file) for file in generation_path.iterdir()} == before
    _Assert_Result(entry.result, ProjectRun_BackupLoad(Project_Load(target), entry.result_id).result)
