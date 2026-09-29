"""Separate static work bounds from target-specific execution-time evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from silverstar_fccg.project.response_time import (
    IsrTimingBudget, ResponseTime_Analyze, TaskResponse, TaskTimingBudget,
)


class TimingEvidenceStatus(StrEnum):
    QUALIFIED_STATIC = "QUALIFIED_STATIC"
    STRUCTURALLY_BOUNDED = "STRUCTURALLY_BOUNDED"
    MEASUREMENT_PENDING = "MEASUREMENT_PENDING"
    STALE = "STALE"
    INVALID = "INVALID"


REQUIRED_STRUCTURE_CHECKS = frozenset((
    "event_rate", "loop_count", "batch", "queue_work", "replay",
    "parser", "retry", "isr_work", "critical_section",
))


@dataclass(frozen=True, slots=True)
class TimingEvidence:
    structure_status: TimingEvidenceStatus
    qualification_status: TimingEvidenceStatus
    missing_structure: tuple[str, ...]
    missing_measurement: tuple[str, ...]
    responses: tuple[TaskResponse, ...]


def TimingEvidence_Assess(
    structural_checks: Mapping[str, bool], *,
    source_fingerprint: str,
    reviewed_source_fingerprint: str = "",
    task_budgets: tuple[TaskTimingBudget, ...] = (),
    isr_budgets: tuple[IsrTimingBudget, ...] = (),
) -> TimingEvidence:
    """Fail closed on missing work bounds; never replace absent WCET with zero."""
    missing = tuple(sorted(
        name for name in REQUIRED_STRUCTURE_CHECKS
        if structural_checks.get(name) is not True
    ))
    if missing or not source_fingerprint:
        return TimingEvidence(
            TimingEvidenceStatus.INVALID, TimingEvidenceStatus.INVALID,
            missing, (), (),
        )
    if reviewed_source_fingerprint and (
        reviewed_source_fingerprint != source_fingerprint
    ):
        return TimingEvidence(
            TimingEvidenceStatus.STRUCTURALLY_BOUNDED,
            TimingEvidenceStatus.STALE, (), (), (),
        )
    if not task_budgets or not isr_budgets:
        missing_measurement = []
        if not task_budgets:
            missing_measurement.append("task execution/blocking upper bounds")
        if not isr_budgets:
            missing_measurement.append("ISR execution/interarrival upper bounds")
        return TimingEvidence(
            TimingEvidenceStatus.STRUCTURALLY_BOUNDED,
            TimingEvidenceStatus.MEASUREMENT_PENDING, (),
            tuple(missing_measurement), (),
        )
    if not reviewed_source_fingerprint:
        return TimingEvidence(
            TimingEvidenceStatus.STRUCTURALLY_BOUNDED,
            TimingEvidenceStatus.MEASUREMENT_PENDING, (),
            ("reviewed source/compiler/CPU fingerprint",), (),
        )
    try:
        responses = ResponseTime_Analyze(task_budgets, isr_budgets)
    except ValueError:
        return TimingEvidence(
            TimingEvidenceStatus.STRUCTURALLY_BOUNDED,
            TimingEvidenceStatus.INVALID, (), (), (),
        )
    return TimingEvidence(
        TimingEvidenceStatus.STRUCTURALLY_BOUNDED,
        TimingEvidenceStatus.QUALIFIED_STATIC if all(
            result.schedulable for result in responses
        ) else TimingEvidenceStatus.INVALID,
        (), (), responses,
    )
