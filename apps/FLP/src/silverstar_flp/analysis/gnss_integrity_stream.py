"""Revision-2 receiver-native horizontal position/velocity closure.

The stream consumes one GNSS solution epoch at a time. Only its returned traces
retain history for desktop display; the state machine itself has constant memory.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from silverstar_flp.analysis.geodesy import GeoLocal_ToEnu
from silverstar_flp.core.dataset import FlightDataset

DEFAULT_PARAMETERS = {
    "gnss_integrity_enable": 1,
    "gnss_integrity_max_gap_ms": 120,
    "gnss_integrity_error_threshold_m": 10.0,
    "gnss_integrity_recovery_threshold_m": 4.0,
    "gnss_integrity_suspect_duration_ms": 2000,
    "gnss_integrity_reject_duration_ms": 5000,
    "gnss_integrity_recovery_duration_ms": 8000,
    "gnss_integrity_position_r_scale": 4.0,
    "gnss_integrity_hacc_max_m": 6.0,
    "gnss_integrity_sacc_max_mps": 1.2,
}


@dataclass(frozen=True, slots=True)
class IntegrityDecision:
    timestamp_us: int
    sequence: int
    state: int
    previous_state: int
    reason: int
    admitted_mask: int
    position_r_scale: float
    evidence_valid: bool
    chain_reset: bool
    position_displacement_en: tuple[float, float]
    integrated_velocity_en: tuple[float, float]
    closure_en: tuple[float, float]
    closure_norm_m: float


@dataclass(frozen=True, slots=True)
class IntegrityTrace:
    timestamp_us: np.ndarray
    position_displacement_en: np.ndarray
    integrated_velocity_en: np.ndarray
    closure_en: np.ndarray
    closure_norm_m: np.ndarray
    evidence_valid: np.ndarray
    chain_reset: np.ndarray
    state: np.ndarray
    quality: np.ndarray
    by_measurement: Mapping[tuple[int, int], IntegrityDecision]
    decisions: tuple[IntegrityDecision, ...]


class IntegrityStream:
    def __init__(self, parameters: Mapping[str, float | int]):
        self.config = {**DEFAULT_PARAMETERS, **parameters}
        if (self.config["gnss_integrity_recovery_threshold_m"] >=
                self.config["gnss_integrity_error_threshold_m"]):
            raise ValueError("gnss_integrity_threshold_order_invalid")
        self.state = 0
        self.last_timestamp_us = 0
        self.last_epoch = 0
        self.last_sequence = 0
        self.last_source = 0
        self.chain_valid = False
        self.anchor_valid = False
        self.anchor_trusted = False
        self.anchor_timestamp_us = 0
        self.last_velocity = np.zeros(2, dtype=np.float32)
        self.integral = np.zeros(2, dtype=np.float32)
        self.anchor_position = np.zeros(2, dtype=np.float32)
        self.abnormal_us = 0
        self.reject_us = 0
        self.healthy_us = 0

    def _ChainReset(self):
        self.chain_valid = False
        self.anchor_valid = False
        self.anchor_trusted = False
        self.abnormal_us = self.reject_us = self.healthy_us = 0
        self.integral.fill(0)

    def _AnchorSet(self, timestamp_us, position):
        self.anchor_valid = True
        self.anchor_trusted = self.state == 0
        self.anchor_timestamp_us = timestamp_us
        self.anchor_position = position.copy()
        self.integral.fill(0)

    def _StateAdvance(self, closure: float, delta_us: int):
        if not math.isfinite(closure):
            self.abnormal_us = self.reject_us = self.healthy_us = 0
            return
        if closure > self.config["gnss_integrity_error_threshold_m"]:
            self.healthy_us = 0
            if self.state == 0:
                self.abnormal_us = min(0xFFFFFFFF, self.abnormal_us + delta_us)
                if self.abnormal_us >= self.config["gnss_integrity_suspect_duration_ms"] * 1000:
                    self.state = 1
                    self.reject_us = 0
            elif self.state == 1:
                self.reject_us = min(0xFFFFFFFF, self.reject_us + delta_us)
                if self.reject_us >= self.config["gnss_integrity_reject_duration_ms"] * 1000:
                    self.state = 2
            return
        self.abnormal_us = self.reject_us = 0
        if (closure >= self.config["gnss_integrity_recovery_threshold_m"] or
                not self.anchor_trusted):
            self.healthy_us = 0
            return
        if self.state != 0:
            self.healthy_us = min(0xFFFFFFFF, self.healthy_us + delta_us)
            if self.healthy_us >= self.config["gnss_integrity_recovery_duration_ms"] * 1000:
                self.state = 1 if self.state == 2 else 0
                self.healthy_us = 0

    def Receive(self, *, timestamp_us: int, epoch: int, sequence: int,
                source: int, mask: int, position: np.ndarray, velocity: np.ndarray,
                hacc: float, sacc: float) -> IntegrityDecision:
        if timestamp_us <= 0 or not 0 <= mask <= 15:
            raise ValueError("gnss_integrity_input_invalid")
        if (self.last_timestamp_us and epoch == self.last_epoch and
                source == self.last_source and sequence == self.last_sequence):
            raise ValueError("gnss_integrity_duplicate")
        previous = self.state
        reason = 0
        reset = False
        closure = math.nan
        pos = np.asarray(position[:2], dtype=np.float32)
        vel = np.asarray(velocity[:2], dtype=np.float32)
        position_good = bool(mask & 1 and math.isfinite(hacc) and 0 < hacc <=
                             self.config["gnss_integrity_hacc_max_m"] and
                             np.isfinite(pos).all())
        velocity_good = bool(mask & 4 and math.isfinite(sacc) and 0 < sacc <=
                             self.config["gnss_integrity_sacc_max_mps"] and
                             np.isfinite(vel).all())
        delta_us = 0
        if self.config["gnss_integrity_enable"]:
            if self.last_timestamp_us:
                if source != self.last_source or epoch != self.last_epoch:
                    reason = 6
                elif sequence != (self.last_sequence + 1) & 0xFFFFFFFF:
                    reason = 5
                elif (timestamp_us <= self.last_timestamp_us or
                      timestamp_us - self.last_timestamp_us >
                      self.config["gnss_integrity_max_gap_ms"] * 1000):
                    reason = 4
                else:
                    delta_us = timestamp_us - self.last_timestamp_us
            if not velocity_good:
                reason = 3 if not mask & 4 else 7
            if not velocity_good or (self.last_timestamp_us and delta_us == 0):
                self._ChainReset()
                reset = True
            if velocity_good:
                if not self.chain_valid:
                    self.chain_valid = True
                    self.last_velocity = vel.copy()
                    if position_good:
                        self._AnchorSet(timestamp_us, pos)
                    if reason == 0:
                        reason = 1
                else:
                    dt = np.float32(delta_us * 1e-6)
                    self.integral += (np.float32(0.5) *
                                      (self.last_velocity + vel) * dt).astype(np.float32)
                    self.last_velocity = vel.copy()
                    if not np.isfinite(self.integral).all():
                        self._ChainReset()
                        reset = True
                        reason = 7
                        self.chain_valid = True
                        self.last_velocity = vel.copy()
                        if position_good:
                            self._AnchorSet(timestamp_us, pos)
                    elif not self.anchor_valid and position_good:
                        self._AnchorSet(timestamp_us, pos)
                        reason = 1
                    elif self.anchor_valid and position_good:
                        residual = (pos - self.anchor_position) - self.integral
                        closure = float(np.hypot(residual[0], residual[1]))
                        if closure > self.config["gnss_integrity_error_threshold_m"]:
                            reason = 8
            if not position_good and reason == 0:
                reason = 2 if not mask & 1 else 7
            self._StateAdvance(closure, delta_us)
            self.last_timestamp_us = timestamp_us
            self.last_epoch = epoch
            self.last_sequence = sequence
            self.last_source = source
        displacement = (pos - self.anchor_position) if self.anchor_valid and position_good \
            else np.full(2, np.nan, dtype=np.float32)
        velocity_delta = self.integral.copy() if self.anchor_valid else np.full(
            2, np.nan, dtype=np.float32)
        residual = displacement - velocity_delta
        admitted = mask & ~1 if self.state == 2 else mask
        scale = self.config["gnss_integrity_position_r_scale"] if self.state == 1 else 1.0
        return IntegrityDecision(timestamp_us, sequence, self.state, previous, reason,
            admitted, float(scale), math.isfinite(closure), reset,
            tuple(float(x) for x in displacement),
            tuple(float(x) for x in velocity_delta),
            tuple(float(x) for x in residual), closure)


def GnssIntegrityStream_Build(dataset: FlightDataset,
    parameters: Mapping[str, float | int] | None = None, *,
    consumed_only: bool = False) -> IntegrityTrace:
    initial = dataset.initial_state
    if initial is None or not int(initial.payload.get("origin_valid_flags", 0)) & 1:
        raise ValueError("gnss_origin_unavailable")
    fields = ("gnss_origin_latitude_e7", "gnss_origin_longitude_e7",
              "gnss_origin_height_mm")
    origin = tuple(int(initial.payload[name]) for name in fields)
    measurements = {
        (int(r.payload["sequence"]), int(r.payload["receive_timestamp_us"])): r
        for r in dataset.Records_Get("GNSS_MEASUREMENT")
    }
    natives = tuple(dataset.Records_Get("GNSS_NATIVE"))
    if consumed_only:
        natives = tuple(r for r in natives if (
            int(r.payload["sequence"]), int(r.payload["receive_timestamp_us"])
        ) in measurements)
    if not natives:
        raise ValueError("gnss_native_unavailable")
    stream = IntegrityStream(parameters or {})
    decisions = []
    quality = []
    by_measurement = {}
    for record in natives:
        p = record.payload
        sample = int(p.get("sample_timestamp_us", record.timestamp_us))
        key = (int(p["sequence"]), int(p.get("receive_timestamp_us", sample)))
        lat = np.asarray([int(p["latitude_e7"])], dtype=np.int64)
        lon = np.asarray([int(p["longitude_e7"])], dtype=np.int64)
        height = np.asarray([int(p["ellipsoid_height_mm"])], dtype=np.int64)
        pos = GeoLocal_ToEnu(lat, lon, height, origin)[0]
        mask = int(p.get("valid_group_mask", (
            (3 if p.get("position_usable") else 0) |
            (4 if int(p.get("velocity_valid_mask", 0)) & 3 == 3 else 0)
        )))
        receive = key[1]
        timestamp = sample if (p.get("measurement_timestamp_trusted", 0) and
                               0 < sample <= receive) else receive
        measured = measurements.get(key)
        epoch = int(measured.payload.get("replay_epoch", 0)) if measured else 0
        if timestamp <= 0:
            continue
        decision = stream.Receive(timestamp_us=timestamp, epoch=epoch,
            sequence=key[0], source=int(p.get("instance_id", 0)), mask=mask,
            position=pos, velocity=np.asarray(p["velocity_enu_mps"], dtype=np.float32),
            hacc=float(p.get("horizontal_accuracy_m", math.nan)),
            sacc=float(p.get("speed_accuracy_mps", math.nan)))
        decisions.append(decision)
        quality.append((float(p.get("horizontal_accuracy_m", math.nan)),
            float(p.get("vertical_accuracy_m", math.nan)),
            float(p.get("speed_accuracy_mps", math.nan)),
            float(p.get("satellite_count", math.nan))))
        if measured:
            if key in by_measurement:
                raise ValueError("gnss_integrity_native_ambiguous")
            by_measurement[key] = decision
    return IntegrityTrace(
        np.asarray([d.timestamp_us for d in decisions], dtype=np.int64),
        np.asarray([d.position_displacement_en for d in decisions], dtype=np.float64),
        np.asarray([d.integrated_velocity_en for d in decisions], dtype=np.float64),
        np.asarray([d.closure_en for d in decisions], dtype=np.float64),
        np.asarray([d.closure_norm_m for d in decisions], dtype=np.float64),
        np.asarray([d.evidence_valid for d in decisions], dtype=bool),
        np.asarray([d.chain_reset for d in decisions], dtype=bool),
        np.asarray([d.state for d in decisions], dtype=np.uint8),
        np.asarray(quality, dtype=np.float64), by_measurement, tuple(decisions),
    )
