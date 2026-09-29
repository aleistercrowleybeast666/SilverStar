"""Conservative fixed-priority response-time calculation for qualified budgets.

All durations are integer microseconds. Callers must provide reviewed upper
bounds, including algorithm work at its actual event rate, before treating a
result as a target qualification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskTimingBudget:
    name: str
    priority: int
    period_us: int
    deadline_us: int
    execution_us: int
    blocking_us: int = 0


@dataclass(frozen=True, slots=True)
class IsrTimingBudget:
    name: str
    minimum_interarrival_us: int
    execution_us: int


@dataclass(frozen=True, slots=True)
class TaskResponse:
    name: str
    response_us: int
    deadline_us: int
    schedulable: bool


def ResponseTime_Analyze(
    tasks: tuple[TaskTimingBudget, ...],
    isrs: tuple[IsrTimingBudget, ...],
) -> tuple[TaskResponse, ...]:
    """Bound a task by all higher/equal-priority peers and all declared ISRs.

    Equal-priority peers are counted as interference regardless of queue order.
    This over-approximates FreeRTOS time slicing and avoids assuming favorable
    release phasing. A deadline crossing terminates the iteration immediately.
    """
    if len({task.name for task in tasks}) != len(tasks):
        raise ValueError("Task timing names must be unique")
    if any(
        task.period_us <= 0 or task.deadline_us <= 0
        or task.deadline_us > task.period_us
        or task.execution_us <= 0 or task.blocking_us < 0
        for task in tasks
    ) or any(
        isr.minimum_interarrival_us <= 0 or isr.execution_us < 0
        for isr in isrs
    ):
        raise ValueError("Timing budgets must be finite and positive")
    results: list[TaskResponse] = []
    for task in tasks:
        peers = (
            other for other in tasks
            if other.name != task.name and other.priority >= task.priority
        )
        interference = tuple(peers)
        response = task.execution_us + task.blocking_us
        for _iteration in range(128):
            if response > task.deadline_us:
                break
            candidate = task.execution_us + task.blocking_us
            candidate += sum(
                math.ceil(response / other.period_us) * other.execution_us
                for other in interference
            )
            candidate += sum(
                math.ceil(response / isr.minimum_interarrival_us)
                * isr.execution_us for isr in isrs
            )
            if candidate == response:
                break
            if candidate < response:
                raise ValueError("Response-time iteration was not monotonic")
            response = candidate
        else:
            raise ValueError("Response-time analysis exceeded bounded iteration limit")
        results.append(TaskResponse(
            task.name, response, task.deadline_us,
            response <= task.deadline_us,
        ))
    return tuple(results)
