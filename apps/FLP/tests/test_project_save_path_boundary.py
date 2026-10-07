"""Actual Windows artifact-path failure must retain a usable old project."""
from copy import deepcopy
import os

import pytest
from PySide6.QtWidgets import QMessageBox

from silverstar_flp.core.project import Project_Load, ProjectResults_Load
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from tests.test_project_artifact_boundaries import _SmallRun


@pytest.mark.skipif(os.name != 'nt', reason='Windows filesystem access boundary')
@pytest.mark.parametrize('background', [False, True])
def test_long_artifact_path_failure_is_actionable_and_preserves_old_project(
        qtbot, tmp_path, monkeypatch, background):
    opened, document, store = _SmallRun(tmp_path)
    window = MainWindow(builtin_registry())
    qtbot.addWidget(window)
    window.Language_Apply('zh_CN')
    window._LogOpenResult_Set(opened, document)
    entry = window._replay_store.Result_Add(store.Entries_Get()[0].result)
    messages = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: messages.append(args[2]))
    old = tmp_path/'old.ssflp'
    assert window._Project_Write(old, save_data=True)
    saved = window._project
    before = old.read_bytes()
    references = deepcopy((saved.parse_artifact, saved.result_artifact))
    source_bytes = opened.dataset.source_path.read_bytes()
    # A legal user-selected project directory/file can still produce an
    # overlong SHA256-named artifact. Do not alter the process/system policy.
    target_dir = tmp_path/('d' * max(5, 145-len(str(tmp_path))-1))
    target_dir.mkdir()
    target = target_dir/'retry.ssflp'
    window._Project_SetDirty(True)
    values = []
    window.progress_bar.valueChanged.connect(values.append)
    scheduled = window._Project_Write(target, background=background, save_data=True)
    if background:
        assert scheduled
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=15000)
    if not messages:
        window._Project_SetDirty(False)
        window.close()
        pytest.skip('Ordinary long paths are supported on this Windows host')
    assert window._project is saved and saved.project_path == old
    assert old.read_bytes() == before
    assert (saved.parse_artifact, saved.result_artifact) == references
    restored = ProjectResults_Load(Project_Load(old))
    assert len(restored.Entries_Get()) == 1
    assert restored.Entries_Get()[0].result_id == entry.result_id
    assert opened.dataset.source_path.read_bytes() == source_bytes
    assert not target.exists() and window._project_dirty
    assert window.progress_bar.value() < 1000
    assert all(value < 1000 for value in values)
    print('OLD_PROJECT_REOPEN_AND_SOURCE_IDENTITY_PRESERVED', background, flush=True)
    failure_status = window.status_label.text()
    print('SAVE_FAILURE_STATUS', failure_status, flush=True)
    window._Project_SetDirty(False)
    window.close()
    assert '缩短' in messages[0] and '未完成' in messages[0]
    assert failure_status == window._translator.Text_Get('status.failed')
    if not background:
        assert not scheduled
