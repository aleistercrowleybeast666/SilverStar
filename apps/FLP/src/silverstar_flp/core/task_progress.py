"""Monotone stage ranges, sharing cancellation; no timers or duration estimates."""
from __future__ import annotations

import math

from silverstar_flp.core.context import TaskContext


class TaskProgress:
    def __init__(self, context: TaskContext | None):
        self.context = context if context is not None else TaskContext()
        self.value = 0.0

    def Progress_Report(self, value: float, code: str) -> None:
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('task_progress_range_invalid')
        self.value = max(self.value, value)
        self.context.Progress_Report(self.value, code)

    def Context_Build(self, start: float, end: float) -> TaskContext:
        if not 0 <= start <= end <= 1:
            raise ValueError('task_progress_range_invalid')
        def report(value, code):
            self.Progress_Report(start + (end-start)*value, code)
        return TaskContext(cancellation_event=self.context.cancellation_event,
                           progress_callback=report)
