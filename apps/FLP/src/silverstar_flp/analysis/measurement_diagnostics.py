"""Group-specific KF6 measurement variance and operation-time diagnostics."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from silverstar_flp.core.dataset import TimeSeries

_GROUPS = (
    ("position_en", "position_variance_m2", (0, 1), "position_measurement_timestamp_us", 0),
    ("position_u", "position_variance_m2", (2,), "position_measurement_timestamp_us", 1),
    ("velocity_en", "velocity_variance_m2ps2", (0, 1), "velocity_measurement_timestamp_us", 2),
    ("velocity_u", "velocity_variance_m2ps2", (2,), "velocity_measurement_timestamp_us", 3),
)


def _Series(rows: Sequence[Mapping[str, object]], key: str, *, unit: str,
            quantity: str, columns: tuple[str, ...]) -> TimeSeries:
    values = np.asarray([row[key] for row in rows], dtype=np.float64)
    valid = np.asarray([bool(row["valid"]) for row in rows], dtype=np.bool_)
    valid &= np.all(np.isfinite(values), axis=1) if values.ndim == 2 else np.isfinite(values)
    return TimeSeries(
        timestamp_us=np.asarray([int(row["timestamp_us"]) for row in rows], dtype=np.uint64),
        values=values, unit=unit, quantity=quantity, source="measurement_operation",
        valid=valid, columns=columns,
        metadata={"group_specific": True, "application_time_source": "operation_stream"},
    )


def _Rows_Channels(rows: Sequence[Mapping[str, object]], prefix: str,
                   group: str, axes: tuple[int, ...], variance_unit: str) -> dict[str, TimeSeries]:
    if not rows:
        return {}
    columns = tuple("ENU"[axis] for axis in axes) if group != "baro" else ("Baro",)
    result = {}
    for name, unit, quantity, selected_columns in (
        ("input_variance", variance_unit, "variance", columns),
        ("effective_variance", variance_unit, "variance", columns),
        ("receive_age", "ms", "receive_age", ()),
        ("fixed_lag_latency", "ms", "fixed_lag_latency", ()),
        ("r_scale", "1", "scale", ()),
    ):
        values = []
        for row in rows:
            if name in ("input_variance", "effective_variance"):
                values.append(row[name])
            else:
                values.append(row[name])
        shaped = [{"timestamp_us": row["timestamp_us"], "valid": row["valid"],
                   name: value} for row, value in zip(rows, values, strict=True)]
        result[f"{prefix}.measurement_{name}.{group}"] = _Series(
            shaped, name, unit=unit, quantity=quantity, columns=selected_columns
        )
    return result


def _Effective_Get(base: np.ndarray, nis: float, result: int,
                   parameters: Mapping[str, float], dimension: int) -> np.ndarray:
    """Return NaN when accepted post-weight variance is not reconstructible."""
    unknown = np.full(base.shape, np.nan, dtype=np.float64)
    if result not in (0, 1) or not np.all(np.isfinite(base)) or np.any(base <= 0):
        return unknown
    soft_key = f"nis_{dimension}d_soft"
    hard_key = f"nis_{dimension}d_hard"
    try:
        soft = float(parameters[soft_key])
        hard = float(parameters[hard_key])
        maximum = float(parameters["nis_max_r_scale"])
    except (KeyError, TypeError, ValueError):
        return unknown
    if not all(math.isfinite(value) for value in (soft, hard, maximum, nis)):
        return unknown
    if soft <= 0 or hard <= soft or maximum < 1 or nis >= hard:
        return unknown
    if result == 0 and nis <= soft:
        return base
    if result == 1 and soft < nis < hard:
        return base * min(nis / soft, maximum)
    return unknown


def RecordedMeasurementChannels_Build(
    records: Mapping[str, Sequence[object]], parameters: Mapping[str, float],
) -> dict[str, TimeSeries]:
    """Reconstruct only accepted, group-specific recorded effective R."""
    channels: dict[str, TimeSeries] = {}
    gnss = sorted(records.get("GNSS_MEASUREMENT", ()),
                  key=lambda row: (row.timestamp_us, row.record_sequence))
    for group, field, axes, measurement_key, index in _GROUPS:
        rows = []
        for record in gnss:
            payload = record.payload
            if not all(key in payload for key in (
                "valid_group_mask", field, "group_nis", "group_update_result",
                "receive_timestamp_us", measurement_key, "estimator_present_timestamp_us",
            )) or (len(payload["group_nis"]) <= index
                    or len(payload["group_update_result"]) <= index):
                continue
            base = np.asarray(payload[field], dtype=np.float64)[list(axes)]
            nis = float(payload["group_nis"][index])
            update = int(payload["group_update_result"][index])
            present = int(payload["estimator_present_timestamp_us"])
            receive = int(payload["receive_timestamp_us"])
            resolved = int(payload[measurement_key])
            valid = bool(int(payload["valid_group_mask"]) & (1 << index)) and (
                0 < receive <= present and 0 < resolved <= present
            ) and np.all(np.isfinite(base)) and np.all(base > 0)
            effective = _Effective_Get(base, nis, update, parameters, len(axes))
            rows.append({
                "timestamp_us": present, "valid": valid,
                "input_variance": base,
                "effective_variance": effective,
                "receive_age": (present - receive) * .001,
                "fixed_lag_latency": (present - resolved) * .001,
                "r_scale": (
                    float(effective[0] / base[0])
                    if np.all(np.isfinite(effective)) else math.nan
                ),
            })
        channels.update(_Rows_Channels(
            rows, "kf6.recorded", group, axes,
            "m^2/s^2" if "velocity" in group else "m^2",
        ))
    rows = []
    for record in sorted(records.get("BARO_MEASUREMENT", ()),
                         key=lambda row: (row.timestamp_us, row.record_sequence)):
        payload = record.payload
        if not all(key in payload for key in (
            "variance_m2", "nis", "update_result", "receive_timestamp_us",
            "measurement_timestamp_us", "estimator_present_timestamp_us",
        )):
            continue
        base = np.asarray([float(payload["variance_m2"])], dtype=np.float64)
        present = int(payload["estimator_present_timestamp_us"])
        receive = int(payload["receive_timestamp_us"])
        resolved = int(payload["measurement_timestamp_us"])
        valid = bool(int(payload.get("valid_mask", 1)) & 1) and (
            0 < receive <= present and 0 < resolved <= present
            and np.isfinite(base[0]) and base[0] > 0
        )
        effective = _Effective_Get(base, float(payload["nis"]),
                                   int(payload["update_result"]), parameters, 1)
        rows.append({"timestamp_us": present, "valid": valid,
                     "input_variance": base, "effective_variance": effective,
                     "receive_age": (present - receive) * .001,
                     "fixed_lag_latency": (present - resolved) * .001,
                     "r_scale": (
                         float(effective[0] / base[0])
                         if np.isfinite(effective[0]) else math.nan
                     )})
    channels.update(_Rows_Channels(rows, "kf6.recorded", "baro", (0,), "m^2"))
    return channels


def RecomputedMeasurementChannels_Build(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, TimeSeries]:
    channels: dict[str, TimeSeries] = {}
    for group, _, axes, _, _ in _GROUPS:
        group_rows = [row for row in rows if row["group"] == group]
        channels.update(_Rows_Channels(group_rows, "kf6", group, axes,
                                       "m^2/s^2" if "velocity" in group else "m^2"))
    baro_rows = [row for row in rows if row["group"] == "baro"]
    channels.update(_Rows_Channels(baro_rows, "kf6", "baro", (0,), "m^2"))
    return channels
