"""Receiver-native vertical consistency for offline inspection only.

This diagnostic never feeds firmware admission, KF6 gating, or NIS decisions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from silverstar_flp.analysis.geodesy import GeoLocal_ToEnu
from silverstar_flp.core.dataset import FlightDataset


@dataclass(frozen=True, slots=True)
class VerticalConsistencyTrace:
    timestamp_us: np.ndarray
    error_m: np.ndarray
    chain_reset: np.ndarray
    position_valid: np.ndarray
    velocity_valid: np.ndarray


def GnssVerticalConsistency_Build(
    dataset: FlightDataset, *, max_gap_ms: int = 120,
) -> VerticalConsistencyTrace:
    """Compare native height change with the independent native velocity-U integral."""
    initial = dataset.initial_state
    if initial is None or not int(initial.payload.get("origin_valid_flags", 0)) & 1:
        raise ValueError("gnss_origin_unavailable")
    origin = tuple(int(initial.payload[name]) for name in (
        "gnss_origin_latitude_e7", "gnss_origin_longitude_e7", "gnss_origin_height_mm",
    ))
    measurements = {
        (int(record.payload["sequence"]), int(record.payload["receive_timestamp_us"])):
        record for record in dataset.Records_Get("GNSS_MEASUREMENT")
    }
    timestamps: list[int] = []
    errors: list[float] = []
    resets: list[bool] = []
    positions: list[bool] = []
    velocities: list[bool] = []
    last_timestamp = 0
    last_sequence = -1
    last_source = -1
    last_epoch = -1
    last_velocity: float | None = None
    integral = 0.0
    reference_position: float | None = None
    reference_integral = 0.0
    for record in dataset.Records_Get("GNSS_NATIVE"):
        payload = record.payload
        sample = int(payload.get("sample_timestamp_us", record.timestamp_us))
        receive = int(payload.get("receive_timestamp_us", sample))
        timestamp = sample if (payload.get("measurement_timestamp_trusted", 0)
                               and 0 < sample <= receive) else receive
        if timestamp <= 0:
            continue
        sequence = int(payload["sequence"])
        source = int(payload.get("instance_id", 0))
        matched = measurements.get((sequence, receive))
        epoch = int(matched.payload.get("replay_epoch", 0)) if matched else 0
        velocity_vector = np.asarray(payload["velocity_enu_mps"], dtype=np.float64)
        mask = int(payload.get("valid_group_mask", (
            (3 if payload.get("position_usable") else 0) |
            (4 if int(payload.get("velocity_valid_mask", 0)) & 3 == 3 else 0) |
            (8 if int(payload.get("velocity_valid_mask", 0)) & 4 else 0)
        )))
        position_valid = bool(mask & 2)
        velocity_valid = bool(mask & 8 and velocity_vector.size >= 3
                              and math.isfinite(float(velocity_vector[2])))
        height_mm = int(payload["ellipsoid_height_mm"])
        position_u = float(GeoLocal_ToEnu(
            np.asarray([int(payload["latitude_e7"])], dtype=np.int64),
            np.asarray([int(payload["longitude_e7"])], dtype=np.int64),
            np.asarray([height_mm], dtype=np.int64), origin,
        )[0, 2])
        position_valid = position_valid and math.isfinite(position_u)
        delta_us = timestamp - last_timestamp if last_timestamp else 0
        broken = (not velocity_valid or last_timestamp == 0 or
                  source != last_source or epoch != last_epoch or
                  sequence != ((last_sequence + 1) & 0xFFFFFFFF) or
                  delta_us <= 0 or delta_us > max_gap_ms * 1000)
        if broken:
            integral = 0.0
            reference_position = None
            reference_integral = 0.0
            last_velocity = None
        if velocity_valid:
            current_velocity = float(velocity_vector[2])
            if last_velocity is not None:
                integral += 0.5 * (last_velocity + current_velocity) * delta_us * 1e-6
            last_velocity = current_velocity
            if reference_position is None and position_valid:
                reference_position = position_u
                reference_integral = integral
        error = (position_u - reference_position - (integral - reference_integral)
                 if position_valid and reference_position is not None else math.nan)
        timestamps.append(timestamp)
        errors.append(error)
        resets.append(broken)
        positions.append(position_valid)
        velocities.append(velocity_valid)
        last_timestamp = timestamp
        last_sequence = sequence
        last_source = source
        last_epoch = epoch
    return VerticalConsistencyTrace(
        np.asarray(timestamps, dtype=np.int64),
        np.asarray(errors, dtype=np.float64),
        np.asarray(resets, dtype=bool),
        np.asarray(positions, dtype=bool),
        np.asarray(velocities, dtype=bool),
    )
