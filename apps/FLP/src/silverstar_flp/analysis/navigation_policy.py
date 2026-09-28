"""Revision-3 causal quality and fusion supervision, independent of filter state.

Received samples never stand in for successful fusion. Internal consistency is
only evidence for bounded variance weighting, never an absolute-position veto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np


class NavigationHealth(IntEnum):
    WARMUP = 0
    HEALTHY = 1
    DEGRADED = 2
    DEAD_RECKONING = 3
    INVALID = 4


def GnssQuality_VarianceScale(
    satellites: int, *, recommended: int = 6, maximum: float = 4.0
) -> float:
    if satellites < 0 or recommended <= 0 or maximum < 1:
        raise ValueError("gnss_quality_configuration_invalid")
    return min(maximum, 1 + 0.5 * max(0, recommended - satellites) ** 2)


@dataclass(frozen=True, slots=True)
class WindowEvidence:
    window_id: int
    start_us: int
    end_us: int
    valid: bool
    reason: str
    closure_en: tuple[float, float]
    coverage: float
    variance_scale: float
    evaluation_us: int | None = None


@dataclass(slots=True)
class _Window:
    start_us: int
    start_position: np.ndarray | None = None
    integral: np.ndarray = field(default_factory=lambda: np.zeros(2))
    covered_us: int = 0
    valid: bool = True


class StaggeredWindows:
    """Two ten-second windows, staggered five seconds; constant streaming state."""

    def __init__(
        self,
        *,
        duration_us: int = 10_000_000,
        offset_us: int = 5_000_000,
        max_gap_us: int = 120_000,
        ttl_us: int = 6_000_000,
        threshold_m: float = 10.0,
        maximum_scale: float = 4.0,
    ):
        if (
            duration_us != 2 * offset_us
            or offset_us <= 0
            or max_gap_us <= 0
            or ttl_us <= 0
            or threshold_m <= 0
            or not np.isfinite(threshold_m)
            or not np.isfinite(maximum_scale)
            or not 1 <= maximum_scale <= 4
        ):
            raise ValueError("gnss_window_configuration_invalid")
        self.duration_us, self.offset_us = duration_us, offset_us
        self.max_gap_us, self.ttl_us = max_gap_us, ttl_us
        self.threshold_m, self.maximum_scale = threshold_m, maximum_scale
        self.windows: list[_Window] = []
        self.previous: tuple[int, np.ndarray, np.ndarray, bool, bool, int, int] | None = None
        self.last_evidence: WindowEvidence | None = None
        self.origin_us: int | None = None
        self.last_sequence: int | None = None
        self.reset_count = 0

    def Evidence_Get(self, timestamp_us: int) -> WindowEvidence | None:
        result = self.last_evidence
        if (
            result is None
            or timestamp_us < result.end_us
            or timestamp_us - result.end_us > self.ttl_us
        ):
            return None
        return result

    def VarianceScale_Get(self, timestamp_us: int) -> float:
        result = self.Evidence_Get(timestamp_us)
        return result.variance_scale if result and result.valid else 1.0

    def Sample_Receive(
        self,
        timestamp_us: int,
        position: np.ndarray,
        velocity: np.ndarray,
        *,
        position_valid: bool,
        velocity_valid: bool,
        source: int = 0,
        generation: int = 0,
        sequence: int | None = None,
    ) -> tuple[WindowEvidence, ...]:
        p, v = (
            np.asarray(position, dtype=np.float64)[:2],
            np.asarray(velocity, dtype=np.float64)[:2],
        )
        position_valid = position_valid and bool(np.isfinite(p).all())
        velocity_valid = velocity_valid and bool(np.isfinite(v).all())
        current = (
            timestamp_us,
            p.copy(),
            v.copy(),
            position_valid,
            velocity_valid,
            source,
            generation,
        )
        if self.previous is None:
            self.origin_us = timestamp_us
            self.windows = [
                _Window(timestamp_us, p.copy() if position_valid else None),
                _Window(timestamp_us + self.offset_us),
            ]
            self.previous = current
            self.last_sequence = sequence
            return ()
        old_t, old_p, old_v, old_p_valid, old_v_valid, old_source, old_generation = self.previous
        if (
            source == old_source
            and generation == old_generation
            and (timestamp_us <= old_t or sequence is not None and sequence == self.last_sequence)
        ):
            return ()
        continuous = (
            0 < timestamp_us - old_t <= self.max_gap_us
            and velocity_valid
            and old_v_valid
            and source == old_source
            and generation == old_generation
            and (
                sequence is None
                or self.last_sequence is None
                or sequence == (self.last_sequence + 1) & 0xFFFFFFFF
            )
        )
        if not continuous:
            self.previous = None
            self.last_evidence = None
            self.reset_count += 1
            return self.Sample_Receive(
                timestamp_us,
                p,
                v,
                position_valid=position_valid,
                velocity_valid=velocity_valid,
                source=source,
                generation=generation,
                sequence=sequence,
            )

        def position_at(time):
            if time == timestamp_us:
                return p.copy() if position_valid else None
            if time == old_t:
                return old_p.copy() if old_p_valid else None
            if not old_p_valid or not position_valid:
                return None
            return old_p + (time - old_t) / (timestamp_us - old_t) * (p - old_p)

        results = []
        for window in self.windows:
            end = window.start_us + self.duration_us
            begin_part, end_part = max(old_t, window.start_us), min(timestamp_us, end)
            if end_part <= begin_part:
                continue
            endpoint = position_at(end) if old_t <= end <= timestamp_us else None
            interpolate_p = endpoint is not None
            if window.start_position is None and old_t <= window.start_us <= timestamp_us:
                window.start_position = position_at(window.start_us)
            if continuous:
                left = old_v + (begin_part - old_t) / (timestamp_us - old_t) * (v - old_v)
                right = old_v + (end_part - old_t) / (timestamp_us - old_t) * (v - old_v)
                window.integral += 0.5 * (left + right) * (end_part - begin_part) * 1e-6
                window.covered_us += end_part - begin_part
            else:
                window.valid = False
            if timestamp_us >= end:
                valid = (
                    window.valid
                    and interpolate_p
                    and window.start_position is not None
                    and window.covered_us == self.duration_us
                )
                closure = np.full(2, np.nan)
                scale = 1.0
                if valid:
                    closure = endpoint - window.start_position - window.integral
                    scale = min(
                        self.maximum_scale,
                        max(1.0, float(np.linalg.norm(closure)) / self.threshold_m) ** 2,
                    )
                evidence = WindowEvidence(
                    (window.start_us - int(self.origin_us)) // self.offset_us,
                    window.start_us,
                    end,
                    bool(valid),
                    "complete" if valid else "gap_or_endpoint",
                    tuple(closure),
                    window.covered_us / self.duration_us,
                    scale,
                )
                results.append(evidence)
                if valid:
                    self.last_evidence = evidence
                window.start_us = end
                window.start_position = endpoint
                window.integral = np.zeros(2)
                window.covered_us = 0
                window.valid = continuous
                if continuous and timestamp_us > end:
                    left = old_v + (end - old_t) / (timestamp_us - old_t) * (v - old_v)
                    window.integral += 0.5 * (left + v) * (timestamp_us - end) * 1e-6
                    window.covered_us += timestamp_us - end
        self.previous = current
        self.last_sequence = sequence
        return tuple(results)


@dataclass(slots=True)
class FusionGroup:
    last_source: int | None = None
    last_receive_us: int = 0
    last_physically_valid_us: int = 0
    last_update_attempt_us: int = 0
    last_successful_fusion_us: int = 0
    last_recovery_us: int = 0
    received: int = 0
    attempted: int = 0
    accepted: int = 0
    soft_weighted: int = 0
    nis_rejected: int = 0
    invalid_rejected: int = 0
    longest_no_fusion_us: int = 0
    last_result: int = 3
    last_nis: float = np.nan
    last_physically_valid: bool | None = None
    last_variance_scale: float = 1.0


class FusionSupervisor:
    def __init__(
        self, start_us: int, *, degraded_us: int = 2_000_000, invalid_us: int = 10_000_000
    ):
        if not 0 < degraded_us < invalid_us:
            raise ValueError("fusion_timeout_configuration_invalid")
        self.start_us, self.degraded_us, self.invalid_us = start_us, degraded_us, invalid_us
        self.groups = [FusionGroup() for _ in range(5)]
        self.model_mismatch_latched = False

    def Decision_Record(
        self,
        group: int,
        receive_us: int,
        *,
        physically_valid: bool,
        result: int,
        nis: float,
        gain_norm: float,
        variance_scale: float = 1.0,
        evaluation_us: int | None = None,
        source: int = 0,
    ) -> bool:
        if not np.isfinite(variance_scale) or variance_scale < 1:
            return False
        state = self.groups[group]
        if source == state.last_source and receive_us <= state.last_receive_us:
            return False
        state.last_source = source
        state.last_receive_us = receive_us
        state.received += 1
        state.last_result, state.last_nis = result, nis
        state.last_physically_valid = physically_valid
        state.last_variance_scale = variance_scale
        if result == 5:
            self.model_mismatch_latched = True
        evaluated = receive_us if evaluation_us is None else evaluation_us
        if physically_valid:
            state.last_physically_valid_us = receive_us
        if physically_valid and result in (0, 1, 2, 4, 5):
            state.last_update_attempt_us = evaluated
            state.attempted += 1
        age = evaluated - (state.last_successful_fusion_us or self.start_us)
        state.longest_no_fusion_us = max(state.longest_no_fusion_us, age)
        if physically_valid and result in (0, 1) and np.isfinite(gain_norm) and gain_norm > 0:
            state.last_successful_fusion_us = evaluated
            state.accepted += 1
            state.soft_weighted += int(result == 1)
        elif result == 2:
            state.nis_rejected += 1
        else:
            state.invalid_rejected += 1
        return True

    def Health_Get(self, timestamp_us: int, required_mask: int = 15) -> NavigationHealth:
        if self.model_mismatch_latched:
            return NavigationHealth.INVALID
        ages = [
            timestamp_us - (g.last_successful_fusion_us or self.start_us)
            for index, g in enumerate(self.groups)
            if required_mask & (1 << index)
        ]
        if not ages:
            return NavigationHealth.DEAD_RECKONING
        if max(ages) >= self.invalid_us:
            return NavigationHealth.INVALID
        if min(ages) >= self.degraded_us:
            return NavigationHealth.DEAD_RECKONING
        if max(ages) >= self.degraded_us or any(
            g.received
            and (
                g.last_physically_valid is False or g.last_variance_scale > 1 or g.last_result == 1
            )
            for index, g in enumerate(self.groups)
            if required_mask & (1 << index)
        ):
            return NavigationHealth.DEGRADED
        if any(
            not g.last_successful_fusion_us
            for index, g in enumerate(self.groups)
            if required_mask & (1 << index)
        ):
            return NavigationHealth.WARMUP
        return NavigationHealth.HEALTHY
