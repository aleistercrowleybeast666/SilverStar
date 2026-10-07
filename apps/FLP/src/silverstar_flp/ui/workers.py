from __future__ import annotations

import traceback
from collections.abc import Callable
from enum import StrEnum
from threading import Event
from typing import Any
from weakref import ref
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from silverstar_flp.core.context import TaskCancelledError, TaskContext


class WorkerSignals(QObject):
    progress = Signal(float, str)
    result = Signal(object)
    error = Signal(str, str)
    cancelled = Signal()
    finished = Signal()


class WorkerRetireResult(StrEnum):
    RETIRED = "retired"
    ALREADY_RETIRED = "already_retired"
    RUNNING = "running"
    WRONG_THREAD = "wrong_thread"


def _ProgressEmitter_Build(signals):
    reference = ref(signals)
    last_detail = 0.0
    def _Progress_Emit(progress, code):
        nonlocal last_detail
        target = reference()
        if target is None:
            raise RuntimeError("worker_signals_unavailable")
        if code.startswith("progress.artifact.") and code != "progress.artifact.checked":
            now = monotonic()
            if now - last_detail < 0.1:
                return
            last_detail = now
        target.progress.emit(progress, code)
    return _Progress_Emit


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[[TaskContext], Any]) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self.context = TaskContext(progress_callback=_ProgressEmitter_Build(self.signals))
        self._function = function
        self.body_finished = Event()
        self._retired = False
        # The GUI controller owns this runnable until the pool confirms run()
        # has returned. Logical finished emission alone is not that boundary.
        self.setAutoDelete(False)

    @Slot()
    def run(self) -> None:
        try:
            result = self._function(self.context)
        except TaskCancelledError:
            self.signals.cancelled.emit()
        except Exception as exc:  # Worker boundary must keep Qt's event loop alive.
            self.signals.error.emit(str(exc), traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            try:
                self.signals.finished.emit()
            finally:
                self.body_finished.set()

    def Worker_Retire(self, pool) -> WorkerRetireResult:
        if self._retired:
            return WorkerRetireResult.ALREADY_RETIRED
        if QThread.currentThread() != self.signals.thread():
            return WorkerRetireResult.WRONG_THREAD
        if not self.body_finished.is_set() or not pool.waitForDone(0):
            return WorkerRetireResult.RUNNING
        self.context.progress_callback = None
        self._function = None
        self._retired = True
        self.signals.deleteLater()
        return WorkerRetireResult.RETIRED

    def Worker_Cancel(self) -> None:
        self.context.Cancel_Request()
