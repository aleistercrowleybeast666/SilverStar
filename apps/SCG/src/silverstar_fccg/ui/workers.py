from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from silverstar_fccg.core.task import TaskCancelledError, TaskContext


class WorkerSignals(QObject):
    progress = Signal(float, str)
    line = Signal(str)
    result = Signal(object)
    error = Signal(object, str)
    cancelled = Signal()
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[[TaskContext], Any]) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self.context = TaskContext(
            progress_callback=self.signals.progress.emit,
            line_callback=self.signals.line.emit,
        )
        self._function = function
        # The main window releases the runnable after its queued ``finished``
        # signal returns.  QThreadPool auto-deletion can otherwise invalidate
        # the Python wrapper while the final Qt callbacks are still dispatching.
        self.setAutoDelete(False)

    @Slot()
    def run(self) -> None:
        try:
            result = self._function(self.context)
        except TaskCancelledError:
            self.signals.cancelled.emit()
        except Exception as exc:  # Worker boundary keeps Qt's event loop alive.
            self.signals.error.emit(exc, traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()

    def Worker_Cancel(self) -> None:
        self.context.Cancel_Request()
