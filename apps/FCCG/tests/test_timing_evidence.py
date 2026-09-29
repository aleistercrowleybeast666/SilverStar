from __future__ import annotations

from silverstar_fccg.project.response_time import (
    IsrTimingBudget, TaskTimingBudget,
)
from silverstar_fccg.project.timing_evidence import (
    REQUIRED_STRUCTURE_CHECKS, TimingEvidence_Assess,
    TimingEvidenceStatus,
)


def test_missing_wcet_is_explicit_and_not_zero() -> None:
    checks = dict.fromkeys(REQUIRED_STRUCTURE_CHECKS, True)
    result = TimingEvidence_Assess(checks, source_fingerprint="source-a")
    assert result.structure_status == TimingEvidenceStatus.STRUCTURALLY_BOUNDED
    assert result.qualification_status == TimingEvidenceStatus.MEASUREMENT_PENDING
    assert result.responses == ()
    assert len(result.missing_measurement) == 2


def test_unbounded_or_stale_source_never_qualifies() -> None:
    checks = dict.fromkeys(REQUIRED_STRUCTURE_CHECKS, True)
    checks["queue_work"] = False
    assert TimingEvidence_Assess(
        checks, source_fingerprint="source-a"
    ).qualification_status == TimingEvidenceStatus.INVALID
    checks["queue_work"] = True
    assert TimingEvidence_Assess(
        checks, source_fingerprint="source-b",
        reviewed_source_fingerprint="source-a",
    ).qualification_status == TimingEvidenceStatus.STALE


def test_reviewed_matching_budgets_are_the_only_rta_input() -> None:
    checks = dict.fromkeys(REQUIRED_STRUCTURE_CHECKS, True)
    result = TimingEvidence_Assess(
        checks, source_fingerprint="source-a",
        reviewed_source_fingerprint="source-a",
        task_budgets=(TaskTimingBudget("Ground", 1, 1000, 1000, 100),),
        isr_budgets=(IsrTimingBudget("UART", 1000, 20),),
    )
    assert result.qualification_status == TimingEvidenceStatus.QUALIFIED_STATIC
    assert result.responses[0].response_us == 120
