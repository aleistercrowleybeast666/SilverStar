from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event


class TaskCancelledError(RuntimeError):
    pass


@dataclass(slots=True)
class TaskContext:
    cancellation_event: Event = field(default_factory=Event)
    progress_callback: Callable[[float, str], None] | None = None

    def Progress_Report(self, progress: float, code: str) -> None:
        self.Cancel_RaiseIfRequested()
        if self.progress_callback is not None:
            self.progress_callback(max(0.0, min(1.0, float(progress))), code)

    def Cancel_RaiseIfRequested(self) -> None:
        if self.cancellation_event.is_set():
            raise TaskCancelledError("task_cancelled")

    def Cancel_Request(self) -> None:
        self.cancellation_event.set()
