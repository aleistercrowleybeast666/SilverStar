"""Tiny actual storage stages; no long log, timer progress or numerical replay loop."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_flp.core.context import TaskContext, TaskCancelledError
from silverstar_flp.core.project import Project_Save, Project_Load
from tests.test_project_artifact_boundaries import _SmallRun


@pytest.fixture(scope='module')
def small_input(tmp_path_factory):
    return _SmallRun(tmp_path_factory.mktemp('input'))


def _Copy(small_input, path):
    opened, original, store = small_input
    document = replace(original, replay_configurations=deepcopy(original.replay_configurations),
        removed_results={}, recovery_sources={}, result_artifact=None, parse_artifact=None)
    return opened, document, store


@pytest.mark.parametrize('save_data', [False, True])
def test_save_reports_real_stages_and_never_publishes_worker_complete(tmp_path, small_input, save_data):
    path = tmp_path/'saved.ssflp'
    opened, document, store = _Copy(small_input, path)
    document.save_data_and_results = save_data
    reports = []
    Project_Save(document, path, dataset=opened.dataset, replay_store=store,
        context=TaskContext(progress_callback=lambda value, code: reports.append((value, code))))
    assert len(reports) >= 3, 'Saving must report actual stages'
    assert all(0 <= value < 1 for value, _ in reports)
    assert [value for value, _ in reports] == sorted(value for value, _ in reports)
    assert any(code == 'progress.save.commit' for _, code in reports)
    assert Project_Load(path).save_data_and_results == save_data


def test_cancel_at_reported_commit_keeps_old_project(tmp_path, small_input):
    path = tmp_path/'saved.ssflp'
    opened, document, store = _Copy(small_input, path)
    document.save_data_and_results = False
    before = b'preserve old user project'
    path.write_bytes(before)
    context = TaskContext()
    context.progress_callback = lambda _, code: context.Cancel_Request() if code == 'progress.save.commit' else None
    with pytest.raises(TaskCancelledError):
        Project_Save(document, path, dataset=opened.dataset, replay_store=store, context=context)
    assert path.read_bytes() == before


def test_commit_failure_never_reports_complete(tmp_path, small_input, monkeypatch):
    import silverstar_flp.core.project as module
    path = tmp_path/'saved.ssflp'
    opened, document, store = _Copy(small_input, path)
    document.save_data_and_results = False
    before = b'preserve old user project'; path.write_bytes(before)
    original = module.os.replace
    def fail(source, target):
        if Path(target) == path.resolve(): raise OSError('injected disk full')
        return original(source, target)
    monkeypatch.setattr(module.os, 'replace', fail)
    reports = []
    with pytest.raises(OSError, match='disk full'):
        Project_Save(document, path, dataset=opened.dataset, replay_store=store,
            context=TaskContext(progress_callback=lambda value, code: reports.append(value)))
    assert path.read_bytes() == before and all(value < 1 for value in reports)


def test_cancel_after_atomic_commit_cannot_become_cancelled_save(tmp_path, small_input, monkeypatch):
    import silverstar_flp.core.project as module
    path = tmp_path/'saved.ssflp'
    opened, document, store = _Copy(small_input, path)
    document.save_data_and_results = False
    context = TaskContext(); reports = []
    original = module.os.replace
    def cancel_after(source, target):
        result = original(source, target)
        if Path(target) == path.resolve(): context.Cancel_Request()
        return result
    monkeypatch.setattr(module.os, 'replace', cancel_after)
    def progress(value, code):
        assert not context.cancellation_event.is_set(), 'No fallible progress after commit'
        reports.append((value, code))
    context.progress_callback = progress
    Project_Save(document, path, dataset=opened.dataset, replay_store=store, context=context)
    assert reports and document.project_path == path.resolve()
    assert not Project_Load(path).save_data_and_results
