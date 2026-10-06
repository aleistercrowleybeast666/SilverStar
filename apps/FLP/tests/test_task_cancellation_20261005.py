from types import SimpleNamespace
from unittest.mock import Mock
from threading import Event
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt

from silverstar_flp.core.context import TaskCancelledError
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement, Mechanization_Run,
)
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker
from silverstar_flp.plugins.registry import builtin_registry


@pytest.mark.parametrize("scenario", ["dialog_rejected", "directory_changed", "queued_result_cancelled"])
def test_folder_discovery_publication_respects_gui_request_lifetime(qtbot, tmp_path, monkeypatch, scenario):
    window = MainWindow(builtin_registry())
    qtbot.addWidget(window)
    path_a, path_b = tmp_path / "a", tmp_path / "b"
    path_a.mkdir()
    path_b.mkdir()
    started, release, emitted = Event(), Event(), Event()
    published, errors = [], []
    old_dataset = object()
    window._dataset = old_dataset
    old_project = window._project
    window._pending_new_project_path = tmp_path / "pending.ssflp"
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    monkeypatch.setattr(window, "_FolderSearch_Set", published.append)

    def scan(path):
        started.set()
        assert release.wait(10), "test scan gate expired"
        return SimpleNamespace(selected_path=Path(path), pairs=(), diagnostics=())

    monkeypatch.setattr(type(window._log_open_coordinator), "PairDiscovery_Run",
                        lambda _coordinator, path: scan(path))
    window.import_dialog.Folder_Set(path_a)
    if scenario != "queued_result_cancelled":
        window.import_dialog.show()
    try:
        window._FolderSearch_Start(path_a)
        qtbot.waitUntil(started.is_set)
        worker = window._active_worker
        if scenario == "dialog_rejected":
            window.import_dialog.reject()
        elif scenario == "directory_changed":
            window.import_dialog.Folder_Set(path_b)
            window._FolderSearch_Start(path_b)
        else:
            worker.signals.result.connect(lambda _result: emitted.set(), Qt.ConnectionType.DirectConnection)
            release.set()
            assert emitted.wait(10), "worker result did not reach the queue"
            window._Task_Cancel()
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=10000)
        assert published == []
        assert window._dataset is old_dataset and window._project is old_project
        if scenario == "directory_changed":
            assert window.import_dialog.folder_path_edit.text() == str(path_b)
            assert window.import_dialog.candidate_combo.count() == 0
        else:
            assert not window.import_dialog.isVisible()
        if scenario == "dialog_rejected":
            assert window._pending_new_project_path is None
    finally:
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=10000)
        window._project_dirty = False
        window.import_dialog.reject()
        window.close()


def test_cancelled_discovery_result_is_not_published():
    results, cancelled, finished = [], [], []

    def discovery(context):
        def scan(_path):
            context.Cancel_Request()
            return "discovery_result"
        window = SimpleNamespace(_log_open_coordinator=SimpleNamespace(PairDiscovery_Run=scan))
        return MainWindow._FolderSearch_Run(window, "test_folder", context)

    worker = FunctionWorker(discovery)
    worker.signals.result.connect(results.append)
    worker.signals.cancelled.connect(lambda: cancelled.append(True))
    worker.signals.finished.connect(lambda: finished.append(True))
    worker.run()
    assert not results and cancelled == [True] and finished == [True]


def test_declining_close_does_not_cancel_active_task():
    worker, event = Mock(), Mock()
    window = SimpleNamespace(_active_worker=worker, _ProjectChanges_Confirm=lambda: False)
    MainWindow.closeEvent(window, event)
    worker.Worker_Cancel.assert_not_called()
    event.ignore.assert_called_once()
    event.accept.assert_not_called()


def test_cancellation_updates_local_and_global_status():
    local = Mock()
    global_status = Mock()
    window = SimpleNamespace(
        _translator=SimpleNamespace(Text_Get=lambda key: "cancelled"),
        status_label=global_status, _worker_cancel_callback=local,
        _worker_cancelled_published=False,
    )
    # Exercise the extracted status publisher; the signal dispatcher now requires
    # a live QObject sender belonging to the active task.
    MainWindow._TaskCancellation_Publish(window)
    global_status.setText.assert_called_once_with("cancelled")
    local.assert_called_once_with("cancelled")


def test_mechanization_observes_cancellation_between_intervals():
    increment = InertialIncrement(
        0, 10000, 1, 1, np.float32(0.01),
        np.zeros(3, dtype=np.float32), np.array([0, 0, 0.0980665], dtype=np.float32),
    )
    checks = []

    def check():
        checks.append(True)
        if len(checks) == 3:
            raise TaskCancelledError("task_cancelled")

    context = SimpleNamespace(Cancel_RaiseIfRequested=check)
    with pytest.raises(TaskCancelledError):
        Mechanization_Run((increment,) * 100,
                          initial_q_nb=np.array([1, 0, 0, 0], dtype=np.float32),
                          gravity_mps2=9.80665, context=context)
    assert len(checks) == 3
