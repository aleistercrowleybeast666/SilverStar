from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event


class TaskCancelledError(RuntimeError):
    """Raised cooperatively when a background task receives cancellation."""


class TaskProgressState(StrEnum):
    PLAN = "PLAN"
    BEGIN = "BEGIN"
    DONE = "DONE"


@dataclass(frozen=True, slots=True)
class TaskProgressEvent:
    task: str
    state: TaskProgressState
    current: int = 0
    total: int = 0
    subject: str = ""

    def Line_Get(self) -> str:
        if self.state == TaskProgressState.PLAN:
            return f"FCCG_PROGRESS|{self.task}|PLAN|{self.total}"
        return (
            f"FCCG_PROGRESS|{self.task}|{self.state.value}|"
            f"{self.current}|{self.total}|{self.subject}"
        )


def TaskProgressEvent_Parse(line: str) -> TaskProgressEvent | None:
    normalized = line.strip()
    if (
        len(normalized) >= 2
        and normalized.startswith('"')
        and normalized.endswith('"')
    ):
        normalized = normalized[1:-1]
    if not normalized.startswith("FCCG_PROGRESS|"):
        return None
    fields = normalized.split("|", 5)
    if len(fields) < 4:
        return None
    _prefix, task, state_text = fields[:3]
    if not task:
        return None
    try:
        state = TaskProgressState(state_text)
    except ValueError:
        return None
    try:
        if state == TaskProgressState.PLAN:
            total = int(fields[3])
            return (
                TaskProgressEvent(task, state, total=total)
                if total > 0
                else None
            )
        if len(fields) != 6:
            return None
        current = int(fields[3])
        total = int(fields[4])
    except ValueError:
        return None
    if total < 1 or not 1 <= current <= total:
        return None
    return TaskProgressEvent(task, state, current, total, fields[5])


@dataclass(slots=True)
class TaskContext:
    cancellation_event: Event = field(default_factory=Event)
    progress_callback: Callable[[float, str], None] | None = None
    line_callback: Callable[[str], None] | None = None

    def Progress_Report(self, progress: float, code: str) -> None:
        self.Cancel_RaiseIfRequested()
        if self.progress_callback is not None:
            bounded_progress = max(0.0, min(1.0, float(progress)))
            self.progress_callback(bounded_progress, code)

    def Cancel_RaiseIfRequested(self) -> None:
        if self.cancellation_event.is_set():
            raise TaskCancelledError("task_cancelled")

    def Line_Report(self, line: str) -> None:
        self.Cancel_RaiseIfRequested()
        if self.line_callback is not None:
            self.line_callback(line)

    def ProgressEvent_Report(
        self,
        task: str,
        state: TaskProgressState,
        *,
        current: int = 0,
        total: int,
        subject: str = "",
        code: str = "status.task_running",
        check_cancellation: bool = True,
    ) -> None:
        if check_cancellation:
            self.Cancel_RaiseIfRequested()
        if total < 1:
            raise ValueError("task progress total must be positive")
        if state == TaskProgressState.PLAN:
            completed = 0
        elif state == TaskProgressState.BEGIN:
            if not 1 <= current <= total:
                raise ValueError("task progress current is outside the plan")
            completed = current - 1
        else:
            if not 1 <= current <= total:
                raise ValueError("task progress current is outside the plan")
            completed = current
        event = TaskProgressEvent(task, state, current, total, subject)
        if self.progress_callback is not None:
            self.progress_callback(completed / total, code)
        if self.line_callback is not None:
            self.line_callback(event.Line_Get())

    def Cancel_Request(self) -> None:
        self.cancellation_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancellation_event.is_set()
