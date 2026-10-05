from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from silverstar_flp.core.context import TaskCancelledError
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement, Mechanization_Run,
)
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker


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
    )
    MainWindow._Task_Cancelled(window)
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
