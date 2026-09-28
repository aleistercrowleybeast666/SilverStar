from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import IntEnum

import numpy as np
from numpy.typing import NDArray

P_DIAGONAL_MIN = np.float32(1.0e-8)
MATRIX_EPSILON = np.float32(1.0e-9)
PREDICTION_DT_MAX_S = np.float32(0.10)


class Kf6UpdateResult(IntEnum):
    ACCEPTED = 0
    SOFT_WEIGHTED = 1
    REJECTED_NIS = 2
    REJECTED_INVALID = 3
    NUMERIC_ERROR = 4


class Kf6GnssGroup(IntEnum):
    POSITION_HORIZONTAL = 0
    POSITION_VERTICAL = 1
    VELOCITY_HORIZONTAL = 2
    VELOCITY_VERTICAL = 3


@dataclass(frozen=True, slots=True)
class Kf6SeparatedResult:
    horizontal_result: Kf6UpdateResult
    vertical_result: Kf6UpdateResult
    vertical_attempted: bool = True


@dataclass(frozen=True, slots=True)
class Kf6GnssEpoch:
    timestamp_us: int
    position_enu_m: NDArray[np.float32]
    velocity_enu_mps: NDArray[np.float32]
    position_std_m: NDArray[np.float32]
    velocity_std_mps: NDArray[np.float32]
    valid_group_mask: int


@dataclass(slots=True)
class _ReacquireGroupState:
    consistency_start_us: int = 0
    generation: int = 0
    availability_timestamp_us: int = 0
    outage: bool = False
    loss_latched: bool = False
    reject_streak: int = 0
    consistent_count: int = 0
    accepted_streak: int = 0
    inflation_attempt_count: int = 0
    epochs_since_inflation: int = 0
    last_inflation_factor: float = 1.0
    active: bool = False


@dataclass(slots=True)
class Kf6Filter:
    process_accel_std_mps2: NDArray[np.float32]
    nis_soft_threshold: NDArray[np.float32]
    nis_hard_threshold: NDArray[np.float32]
    nis_max_r_scale: np.float32
    state: NDArray[np.float32] = field(default_factory=lambda: np.zeros(6, dtype=np.float32))
    covariance: NDArray[np.float32] = field(
        default_factory=lambda: np.diag(
            np.asarray((4.0, 4.0, 9.0, 0.25, 0.25, 0.25), dtype=np.float32)
        )
    )
    last_position_nis: np.float32 = np.float32(0.0)
    last_velocity_nis: np.float32 = np.float32(0.0)
    last_baro_nis: np.float32 = np.float32(0.0)
    last_position_innovation: NDArray[np.float32] = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )
    last_velocity_innovation: NDArray[np.float32] = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )
    last_position_effective_variance: NDArray[np.float32] = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )
    last_velocity_effective_variance: NDArray[np.float32] = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )
    last_baro_innovation: np.float32 = np.float32(0.0)
    last_baro_effective_variance: np.float32 = np.float32(0.0)
    last_group_nis: NDArray[np.float32] = field(
        default_factory=lambda: np.zeros(4, dtype=np.float32)
    )
    last_group_result: NDArray[np.int32] = field(
        default_factory=lambda: np.full(4, 5, dtype=np.int32)
    )
    predict_count: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    health_flags: int = 0
    _previous_epoch: Kf6GnssEpoch | None = None
    _reacquire_groups: list[_ReacquireGroupState] = field(
        default_factory=lambda: [_ReacquireGroupState() for _ in range(4)]
    )
    analysis_position_vertical_disabled: bool = False
    outage_required: bool = True
    # Old revisions retain their original arithmetic/admission semantics.
    require_effective_gain: bool = False
    inflation_counts: list[int] = field(default_factory=lambda: [0] * 4)
    gnss_nis_samples: list[list[float]] = field(default_factory=lambda: [[] for _ in range(4)])
    gnss_result_counts: list[list[int]] = field(default_factory=lambda: [[0] * 5 for _ in range(4)])
    gnss_reacquire_outage_ms: int = 300
    reanchor_counts: list[int] = field(default_factory=lambda: [0] * 4)
    reacquire_count: int = 0
    reacquire_active_mask: int = 0
    last_inflation_group: int = -1
    last_inflation_factor: float = 1.0

    @classmethod
    def Kf6_Create(
        cls,
        *,
        process_accel_std_mps2: NDArray[np.floating],
        p0_diagonal: NDArray[np.floating],
        initial_velocity_enu_mps: NDArray[np.floating],
        nis_soft_threshold: NDArray[np.floating],
        nis_hard_threshold: NDArray[np.floating],
        nis_max_r_scale: float,
        gnss_reacquire_outage_ms: int = 300,
    ) -> Kf6Filter:
        process = np.asarray(process_accel_std_mps2, dtype=np.float32)
        p0 = np.asarray(p0_diagonal, dtype=np.float32)
        velocity = np.asarray(initial_velocity_enu_mps, dtype=np.float32)
        soft = np.asarray(nis_soft_threshold, dtype=np.float32)
        hard = np.asarray(nis_hard_threshold, dtype=np.float32)
        if (
            process.shape != (3,)
            or p0.shape != (6,)
            or velocity.shape != (3,)
            or soft.shape != (3,)
            or hard.shape != (3,)
            or np.any(process <= 0.0)
            or np.any(p0 < 0.0)
            or np.any(soft <= 0.0)
            or np.any(hard <= soft)
            or not 100 <= gnss_reacquire_outage_ms <= 10000
            or nis_max_r_scale < 1.0
        ):
            raise ValueError("kf6_configuration_invalid")
        instance = cls(
            process_accel_std_mps2=process.copy(),
            nis_soft_threshold=soft.copy(),
            nis_hard_threshold=hard.copy(),
            nis_max_r_scale=np.float32(nis_max_r_scale),
            gnss_reacquire_outage_ms=gnss_reacquire_outage_ms,
        )
        instance.covariance = np.diag(np.maximum(p0, P_DIAGONAL_MIN)).astype(np.float32)
        instance.state[3:6] = velocity
        return instance

    def Kf6_Predict(self, delta_velocity_enu_mps: NDArray[np.floating], dt_s: float) -> bool:
        delta_velocity = np.asarray(delta_velocity_enu_mps, dtype=np.float32)
        dt = np.float32(dt_s)
        if (
            delta_velocity.shape != (3,)
            or not np.all(np.isfinite(delta_velocity))
            or not np.isfinite(dt)
            or dt <= 0.0
            or dt > PREDICTION_DT_MAX_S
        ):
            self.health_flags |= 1
            return False
        covariance_previous = self.covariance.copy()
        velocity_previous = self.state[3:6].copy()
        for axis in range(3):
            self.state[axis] += (
                velocity_previous[axis] * dt + np.float32(0.5) * delta_velocity[axis] * dt
            )
            self.state[axis + 3] += delta_velocity[axis]
        delta_velocity_variance = (self.process_accel_std_mps2 * dt) ** np.float32(2.0)
        covariance_new = np.empty((6, 6), dtype=np.float32)
        for row in range(6):
            row_axis = row % 3
            row_position = row < 3
            row_noise_gain = np.float32(0.5) * dt if row_position else np.float32(1.0)
            for column in range(6):
                column_axis = column % 3
                column_position = column < 3
                column_noise_gain = np.float32(0.5) * dt if column_position else np.float32(1.0)
                value = covariance_previous[row, column]
                if row_position:
                    value += dt * covariance_previous[row + 3, column]
                if column_position:
                    value += dt * covariance_previous[row, column + 3]
                if row_position and column_position:
                    value += dt * dt * covariance_previous[row + 3, column + 3]
                if row_axis == column_axis:
                    value += row_noise_gain * column_noise_gain * delta_velocity_variance[row_axis]
                covariance_new[row, column] = value
        self.covariance = covariance_new
        if not self._Covariance_Repair():
            self.health_flags |= 4
            return False
        self.predict_count += 1
        return True

    def Kf6_UpdateGnssPosition(
        self,
        position_enu_m: NDArray[np.floating],
        variance_m2: NDArray[np.floating],
    ) -> Kf6SeparatedResult:
        horizontal = self._Vector_Update(
            position_enu_m,
            variance_m2,
            dimension=2,
            state_offset=0,
            group=Kf6GnssGroup.POSITION_HORIZONTAL,
            innovation_target=self.last_position_innovation,
            variance_target=self.last_position_effective_variance,
        )
        if self.analysis_position_vertical_disabled:
            self.last_position_nis = self.last_group_nis[0]
            self._Counter_Update("position", horizontal)
            return Kf6SeparatedResult(horizontal, Kf6UpdateResult.REJECTED_INVALID, False)
        position = np.asarray(position_enu_m, dtype=np.float32)
        variance = np.asarray(variance_m2, dtype=np.float32)
        vertical = self._Vector_Update(
            position[2:3],
            variance[2:3],
            dimension=1,
            state_offset=2,
            group=Kf6GnssGroup.POSITION_VERTICAL,
            innovation_target=self.last_position_innovation[2:3],
            variance_target=self.last_position_effective_variance[2:3],
        )
        self.last_position_nis = np.max(self.last_group_nis[0:2])
        self._Counter_Update("position", self._Separated_Aggregate(horizontal, vertical))
        return Kf6SeparatedResult(horizontal, vertical)

    def Kf6_UpdateGnssVelocity(
        self,
        velocity_enu_mps: NDArray[np.floating],
        variance_m2ps2: NDArray[np.floating],
        *,
        vertical_valid: bool,
    ) -> Kf6SeparatedResult:
        horizontal = self._Vector_Update(
            velocity_enu_mps,
            variance_m2ps2,
            dimension=2,
            state_offset=3,
            group=Kf6GnssGroup.VELOCITY_HORIZONTAL,
            innovation_target=self.last_velocity_innovation,
            variance_target=self.last_velocity_effective_variance,
        )
        vertical = Kf6UpdateResult.REJECTED_INVALID
        if vertical_valid:
            velocity = np.asarray(velocity_enu_mps, dtype=np.float32)
            variance = np.asarray(variance_m2ps2, dtype=np.float32)
            vertical = self._Vector_Update(
                velocity[2:3],
                variance[2:3],
                dimension=1,
                state_offset=5,
                group=Kf6GnssGroup.VELOCITY_VERTICAL,
                innovation_target=self.last_velocity_innovation[2:3],
                variance_target=self.last_velocity_effective_variance[2:3],
            )
        self.last_velocity_nis = max(
            self.last_group_nis[2],
            self.last_group_nis[3] if vertical_valid else np.float32(0.0),
        )
        self._Counter_Update(
            "velocity",
            self._Separated_Aggregate(horizontal, vertical) if vertical_valid else horizontal,
        )
        return Kf6SeparatedResult(horizontal, vertical, vertical_valid)

    def Kf6_UpdateBaro(self, altitude_up_m: float, variance_m2: float) -> Kf6UpdateResult:
        observation = np.float32(altitude_up_m)
        variance = np.float32(variance_m2)
        if not np.isfinite(observation) or not np.isfinite(variance) or variance <= MATRIX_EPSILON:
            self.health_flags |= 1
            result = Kf6UpdateResult.REJECTED_INVALID
            self._Counter_Update("baro", result)
            return result
        innovation = np.float32(observation - self.state[2])
        innovation_variance = np.float32(self.covariance[2, 2] + variance)
        if not np.isfinite(innovation_variance) or innovation_variance <= MATRIX_EPSILON:
            result = Kf6UpdateResult.NUMERIC_ERROR
            self._Counter_Update("baro", result)
            return result
        nis = np.float32(innovation * innovation / innovation_variance)
        self.last_baro_nis = nis
        self.last_baro_innovation = innovation
        if nis >= self.nis_hard_threshold[0]:
            result = Kf6UpdateResult.REJECTED_NIS
            self._Counter_Update("baro", result)
            return result
        scale = np.float32(1.0)
        result = Kf6UpdateResult.ACCEPTED
        if nis > self.nis_soft_threshold[0]:
            scale = min(np.float32(nis / self.nis_soft_threshold[0]), self.nis_max_r_scale)
            result = Kf6UpdateResult.SOFT_WEIGHTED
        effective_variance = np.float32(variance * scale)
        self.last_baro_effective_variance = effective_variance
        covariance_previous = self.covariance.copy()
        innovation_variance = np.float32(covariance_previous[2, 2] + effective_variance)
        gain = np.asarray(covariance_previous[:, 2] / innovation_variance, dtype=np.float32)
        if not self._Gain_IsEffective(gain):
            result = Kf6UpdateResult.NUMERIC_ERROR
            self._Counter_Update("baro", result)
            return result
        self.state = np.asarray(self.state + gain * innovation, dtype=np.float32)
        identity_minus_kh = np.eye(6, dtype=np.float32)
        identity_minus_kh[:, 2] -= gain
        self.covariance = np.asarray(
            identity_minus_kh @ covariance_previous @ identity_minus_kh.T
            + np.outer(gain, gain) * effective_variance,
            dtype=np.float32,
        )
        if not self._Covariance_Repair():
            result = Kf6UpdateResult.NUMERIC_ERROR
        self._Counter_Update("baro", result)
        return result

    def Kf6_GnssEpochTrack(self, epoch: Kf6GnssEpoch) -> None:
        if epoch.timestamp_us <= 0:
            self.health_flags |= 1
            if self._previous_epoch is not None:
                self._previous_epoch = replace(self._previous_epoch, valid_group_mask=0)
            return
        current_mask = int(epoch.valid_group_mask) & 0x0F
        for group in Kf6GnssGroup:
            indices = (0, 1) if int(group) % 2 == 0 else (2,)
            values, std = (
                (epoch.position_enu_m, epoch.position_std_m)
                if int(group) < 2
                else (epoch.velocity_enu_mps, epoch.velocity_std_mps)
            )
            if not all(
                np.isfinite(values[i]) and np.isfinite(std[i]) and std[i] > 0 for i in indices
            ):
                current_mask &= ~(1 << int(group))
        epoch = replace(epoch, valid_group_mask=current_mask)
        previous = self._previous_epoch
        if previous is not None and epoch.timestamp_us <= previous.timestamp_us:
            self._reacquire_groups = [
                _ReacquireGroupState(generation=g.generation + 1) for g in self._reacquire_groups
            ]
            self.reacquire_active_mask = 0
            self._previous_epoch = replace(epoch, valid_group_mask=0)
            return
        for group in Kf6GnssGroup:
            bit = 1 << int(group)
            state = self._reacquire_groups[int(group)]
            anchor = state.availability_timestamp_us
            if anchor == 0:
                state.availability_timestamp_us = epoch.timestamp_us
            elif (
                epoch.timestamp_us - anchor > self.gnss_reacquire_outage_ms * 1000
                and not state.loss_latched
            ):
                state = _ReacquireGroupState(
                    availability_timestamp_us=anchor,
                    outage=True,
                    loss_latched=True,
                    generation=state.generation + 1,
                )
                self._reacquire_groups[int(group)] = state
                self.reacquire_active_mask &= ~bit
            if current_mask & bit:
                state.loss_latched = False
                state.availability_timestamp_us = epoch.timestamp_us
            else:
                state.reject_streak = state.accepted_streak = state.consistent_count = 0
                state.consistency_start_us = 0
        if previous is None:
            for state in self._reacquire_groups:
                state.consistent_count = 0
                state.consistency_start_us = 0
            self._previous_epoch = epoch
            return
        dt_s = (epoch.timestamp_us - previous.timestamp_us) * 1.0e-6
        if dt_s < 0.010 or dt_s > 1.0:
            for state in self._reacquire_groups:
                state.consistent_count = 0
                state.consistency_start_us = 0
            self._previous_epoch = epoch
            return
        for group in Kf6GnssGroup:
            bit = 1 << int(group)
            required = bit
            if group == Kf6GnssGroup.POSITION_HORIZONTAL:
                required |= 1 << int(Kf6GnssGroup.VELOCITY_HORIZONTAL)
            elif group == Kf6GnssGroup.POSITION_VERTICAL:
                required |= 1 << int(Kf6GnssGroup.VELOCITY_VERTICAL)
            consistent = False
            if (current_mask & required) == required and (
                previous.valid_group_mask & required
            ) == required:
                consistent = self._EpochGroup_IsConsistent(previous, epoch, group, dt_s)
            state = self._reacquire_groups[int(group)]
            if consistent and state.consistent_count == 0:
                state.consistency_start_us = previous.timestamp_us
            if not consistent:
                state.consistency_start_us = 0
            state.consistent_count = state.consistent_count + 1 if consistent else 0
        self._previous_epoch = epoch

    def Kf6_GnssGroupResultProcess(self, group: Kf6GnssGroup, result: Kf6UpdateResult) -> None:
        self.last_group_result[int(group)] = int(result)
        state = self._reacquire_groups[int(group)]
        bit = 1 << int(group)
        if self._previous_epoch is None or not self._previous_epoch.valid_group_mask & bit:
            state.reject_streak = state.accepted_streak = 0
            return
        self.gnss_result_counts[int(group)][int(result)] += 1
        if result in (
            Kf6UpdateResult.ACCEPTED,
            Kf6UpdateResult.SOFT_WEIGHTED,
            Kf6UpdateResult.REJECTED_NIS,
        ):
            self.gnss_nis_samples[int(group)].append(float(self.last_group_nis[int(group)]))
        if result == Kf6UpdateResult.REJECTED_NIS:
            state.reject_streak += 1
            state.accepted_streak = 0
            if state.active:
                state.epochs_since_inflation += 1
            if (
                (state.outage or not self.outage_required)
                and state.reject_streak >= 5
                and state.consistent_count >= 3
            ):
                if not state.active:
                    state.active = True
                    state.inflation_attempt_count = 0
                    state.epochs_since_inflation = 5
                    self.reacquire_active_mask |= bit
                    self.reacquire_count += 1
                if state.inflation_attempt_count < 8 and state.epochs_since_inflation >= 5:
                    factor = self._Covariance_Inflate(group)
                    if factor is not None:
                        self.inflation_counts[int(group)] += 1
                        state.inflation_attempt_count += 1
                        state.epochs_since_inflation = 0
                        state.last_inflation_factor = factor
                        self.last_inflation_group = int(group)
                        self.last_inflation_factor = factor
            return
        if result in (Kf6UpdateResult.ACCEPTED, Kf6UpdateResult.SOFT_WEIGHTED):
            state.reject_streak = 0
            if not state.active:
                state.outage = False
            if state.active:
                state.accepted_streak += 1
                if state.accepted_streak >= 3:
                    state.active = False
                    state.outage = False
                    state.accepted_streak = 0
                    self.reacquire_active_mask &= ~bit
            return
        state.reject_streak = 0
        state.accepted_streak = 0

    def Kf6_GroupUpdate(self, group: Kf6GnssGroup, observation, variance) -> Kf6UpdateResult:
        """One independently qualified group; unrelated NaNs never reject it."""
        g = int(group)
        vertical = g % 2 == 1
        axis = 2 if vertical else 0
        offset = axis + (3 if g >= 2 else 0)
        innovation = self.last_position_innovation if g < 2 else self.last_velocity_innovation
        effective = (
            self.last_position_effective_variance
            if g < 2
            else self.last_velocity_effective_variance
        )
        return self._Vector_Update(np.asarray(observation)[axis:], np.asarray(variance)[axis:],
            dimension=1 if vertical else 2, state_offset=offset, group=group,
            innovation_target=innovation[axis:], variance_target=effective[axis:])

    def Kf6_GroupRecover(self, group, result, observation, variance, receive_us):
        self.Kf6_GnssGroupResultProcess(group, result)
        state = self._reacquire_groups[int(group)]
        if not (result == Kf6UpdateResult.REJECTED_NIS and state.outage and state.active
                and not state.loss_latched and state.consistency_start_us > 0
                and receive_us - state.consistency_start_us >= 1_000_000
                and state.consistent_count >= 3 and state.inflation_attempt_count >= 8
                and state.epochs_since_inflation >= 5):
            return result
        g = int(group)
        indices = ((0, 1), (2,), (3, 4), (5,))[g]
        if not np.isfinite(self.state).all() or not np.isfinite(self.covariance).all():
            return Kf6UpdateResult.NUMERIC_ERROR
        if not np.array_equal(self.covariance, self.covariance.T):
            return Kf6UpdateResult.NUMERIC_ERROR
        try:
            np.linalg.cholesky(self.covariance)
        except np.linalg.LinAlgError:
            return Kf6UpdateResult.NUMERIC_ERROR
        for index in indices:
            axis = index % 3
            if (
                not np.isfinite(observation[axis])
                or not np.isfinite(variance[axis])
                or variance[axis] <= 0
            ):
                return Kf6UpdateResult.NUMERIC_ERROR
        for index in indices:
            self.state[index] = observation[index % 3]
            self.covariance[index, :] = 0
            self.covariance[:, index] = 0
            self.covariance[index, index] = max(variance[index % 3], P_DIAGONAL_MIN)
        self.reanchor_counts[g] += 1
        state.active = state.outage = False
        state.reject_streak = state.accepted_streak = 0
        self.reacquire_active_mask &= ~(1 << g)
        return Kf6UpdateResult.ACCEPTED

    def _Vector_Update(
        self,
        observation: NDArray[np.floating],
        variance: NDArray[np.floating],
        *,
        dimension: int,
        state_offset: int,
        group: Kf6GnssGroup,
        innovation_target: NDArray[np.float32],
        variance_target: NDArray[np.float32],
    ) -> Kf6UpdateResult:
        observed = np.asarray(observation, dtype=np.float32)[:dimension]
        measurement_variance = np.asarray(variance, dtype=np.float32)[:dimension]
        if (
            observed.size != dimension
            or measurement_variance.size != dimension
            or not np.all(np.isfinite(observed))
            or not np.all(np.isfinite(measurement_variance))
            or np.any(measurement_variance <= MATRIX_EPSILON)
        ):
            self.health_flags |= 1
            return Kf6UpdateResult.REJECTED_INVALID
        covariance_previous = self.covariance.copy()
        innovation = np.asarray(
            observed - self.state[state_offset : state_offset + dimension],
            dtype=np.float32,
        )
        innovation_target[:dimension] = innovation
        effective_variance = measurement_variance.copy()
        variance_target[:dimension] = effective_variance
        innovation_covariance = covariance_previous[
            state_offset : state_offset + dimension,
            state_offset : state_offset + dimension,
        ].copy()
        innovation_covariance[np.diag_indices(dimension)] += measurement_variance
        inverse = self._Cholesky_Inverse(innovation_covariance)
        if inverse is None:
            self.health_flags |= 2 | 4 | 8
            return Kf6UpdateResult.NUMERIC_ERROR
        nis = np.float32(innovation @ inverse @ innovation)
        self.last_group_nis[int(group)] = nis
        if not np.isfinite(nis) or nis < 0.0:
            self.health_flags |= 4
            return Kf6UpdateResult.NUMERIC_ERROR
        if nis >= self.nis_hard_threshold[dimension - 1]:
            return Kf6UpdateResult.REJECTED_NIS
        result = Kf6UpdateResult.ACCEPTED
        if nis > self.nis_soft_threshold[dimension - 1]:
            scale = min(
                np.float32(nis / self.nis_soft_threshold[dimension - 1]),
                self.nis_max_r_scale,
            )
            effective_variance = np.asarray(measurement_variance * scale, dtype=np.float32)
            variance_target[:dimension] = effective_variance
            innovation_covariance = covariance_previous[
                state_offset : state_offset + dimension,
                state_offset : state_offset + dimension,
            ].copy()
            innovation_covariance[np.diag_indices(dimension)] += effective_variance
            inverse = self._Cholesky_Inverse(innovation_covariance)
            if inverse is None:
                self.health_flags |= 2 | 4 | 8
                return Kf6UpdateResult.NUMERIC_ERROR
            result = Kf6UpdateResult.SOFT_WEIGHTED
        cross_covariance = covariance_previous[:, state_offset : state_offset + dimension]
        gain = np.asarray(cross_covariance @ inverse, dtype=np.float32)
        if not self._Gain_IsEffective(gain):
            return Kf6UpdateResult.NUMERIC_ERROR
        self.state = np.asarray(self.state + gain @ innovation, dtype=np.float32)
        identity_minus_kh = np.eye(6, dtype=np.float32)
        identity_minus_kh[:, state_offset : state_offset + dimension] -= gain
        self.covariance = np.asarray(
            identity_minus_kh @ covariance_previous @ identity_minus_kh.T
            + gain @ np.diag(effective_variance) @ gain.T,
            dtype=np.float32,
        )
        if not self._Covariance_Repair():
            self.health_flags |= 4 | 8
            return Kf6UpdateResult.NUMERIC_ERROR
        return result

    def _Gain_IsEffective(self, gain: NDArray[np.float32]) -> bool:
        # Do not square K: a nonzero float32 gain can have K squared == 0.
        if self.require_effective_gain and (
            not np.isfinite(gain).all() or not np.any(gain != np.float32(0.0))
        ):
            self.health_flags |= 4 | 8
            self.counters["numeric_error_count"] = self.counters.get("numeric_error_count", 0) + 1
            return False
        return True

    @staticmethod
    def _Cholesky_Inverse(matrix: NDArray[np.float32]) -> NDArray[np.float32] | None:
        dimension = matrix.shape[0]
        lower = np.zeros((dimension, dimension), dtype=np.float32)
        try:
            for row in range(dimension):
                for column in range(row + 1):
                    value = np.float32(matrix[row, column])
                    for inner in range(column):
                        value -= lower[row, inner] * lower[column, inner]
                    if row == column:
                        if not np.isfinite(value) or value <= MATRIX_EPSILON:
                            return None
                        lower[row, column] = np.float32(math.sqrt(float(value)))
                    else:
                        if lower[column, column] <= MATRIX_EPSILON:
                            return None
                        lower[row, column] = value / lower[column, column]
            inverse = np.zeros((dimension, dimension), dtype=np.float32)
            for column in range(dimension):
                forward = np.zeros(dimension, dtype=np.float32)
                solution = np.zeros(dimension, dtype=np.float32)
                for row in range(dimension):
                    value = np.float32(1.0 if row == column else 0.0)
                    for inner in range(row):
                        value -= lower[row, inner] * forward[inner]
                    forward[row] = value / lower[row, row]
                for row in range(dimension - 1, -1, -1):
                    value = forward[row]
                    for inner in range(row + 1, dimension):
                        value -= lower[inner, row] * solution[inner]
                    solution[row] = value / lower[row, row]
                inverse[:, column] = solution
            return inverse
        except (FloatingPointError, ValueError, ZeroDivisionError):
            return None

    def _Covariance_Repair(self) -> bool:
        if not np.all(np.isfinite(self.state)) or not np.all(np.isfinite(self.covariance)):
            return False
        self.covariance = np.asarray(
            np.float32(0.5) * (self.covariance + self.covariance.T), dtype=np.float32
        )
        diagonal = np.diag(self.covariance).copy()
        if np.any(diagonal < 0.0):
            return False
        np.fill_diagonal(self.covariance, np.maximum(diagonal, P_DIAGONAL_MIN))
        return True

    def _Covariance_Inflate(self, group: Kf6GnssGroup) -> float | None:
        if group == Kf6GnssGroup.POSITION_HORIZONTAL:
            indices, cap = (0, 1), 1_000_000.0
        elif group == Kf6GnssGroup.POSITION_VERTICAL:
            indices, cap = (2,), 1_000_000.0
        elif group == Kf6GnssGroup.VELOCITY_HORIZONTAL:
            indices, cap = (3, 4), 10_000.0
        else:
            indices, cap = (5,), 10_000.0
        factor = 2.0
        for index in indices:
            diagonal = float(self.covariance[index, index])
            if not math.isfinite(diagonal) or diagonal < float(P_DIAGONAL_MIN):
                return None
            factor = min(factor, math.sqrt(cap / diagonal))
        factor = max(1.0, factor)
        scales = np.ones(6, dtype=np.float32)
        scales[list(indices)] = np.float32(factor)
        self.covariance = np.asarray(self.covariance * np.outer(scales, scales), dtype=np.float32)
        return factor if self._Covariance_Repair() else None

    @staticmethod
    def _Separated_Aggregate(
        horizontal: Kf6UpdateResult, vertical: Kf6UpdateResult
    ) -> Kf6UpdateResult:
        values = (horizontal, vertical)
        for preferred in (
            Kf6UpdateResult.ACCEPTED,
            Kf6UpdateResult.SOFT_WEIGHTED,
            Kf6UpdateResult.REJECTED_NIS,
            Kf6UpdateResult.REJECTED_INVALID,
        ):
            if preferred in values:
                return preferred
        return Kf6UpdateResult.NUMERIC_ERROR

    def _Counter_Update(self, source: str, result: Kf6UpdateResult) -> None:
        if result == Kf6UpdateResult.ACCEPTED:
            suffix = "accept"
        elif result == Kf6UpdateResult.SOFT_WEIGHTED:
            suffix = "soft"
        else:
            suffix = "reject"
        key = f"{source}_{suffix}_count"
        self.counters[key] = self.counters.get(key, 0) + 1

    @staticmethod
    def _EpochGroup_IsConsistent(
        previous: Kf6GnssEpoch,
        current: Kf6GnssEpoch,
        group: Kf6GnssGroup,
        dt_s: float,
    ) -> bool:
        if group in (
            Kf6GnssGroup.POSITION_HORIZONTAL,
            Kf6GnssGroup.POSITION_VERTICAL,
        ):
            if group == Kf6GnssGroup.POSITION_HORIZONTAL:
                axes = slice(0, 2)
                floor = 3.0
            else:
                axes = slice(2, 3)
                floor = 5.0
            residual = (
                current.position_enu_m[axes]
                - previous.position_enu_m[axes]
                - 0.5 * (previous.velocity_enu_mps[axes] + current.velocity_enu_mps[axes]) * dt_s
            )
            position_variance = np.sum(previous.position_std_m[axes] ** 2) + np.sum(
                current.position_std_m[axes] ** 2
            )
            velocity_variance = np.sum(previous.velocity_std_mps[axes] ** 2) + np.sum(
                current.velocity_std_mps[axes] ** 2
            )
            uncertainty = math.sqrt(
                float(position_variance + 0.25 * dt_s * dt_s * velocity_variance)
            )
            return float(np.linalg.norm(residual)) <= max(floor, 2.0 * uncertainty)
        axes = slice(0, 2) if group == Kf6GnssGroup.VELOCITY_HORIZONTAL else slice(2, 3)
        delta = current.velocity_enu_mps[axes] - previous.velocity_enu_mps[axes]
        uncertainty = math.sqrt(
            float(
                np.sum(previous.velocity_std_mps[axes] ** 2)
                + np.sum(current.velocity_std_mps[axes] ** 2)
            )
        )
        return float(np.linalg.norm(delta)) <= 60.0 * dt_s + 2.0 * uncertainty
