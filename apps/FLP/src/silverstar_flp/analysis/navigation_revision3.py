"""Revision-3 native quality weighting for KF6, distinct from legacy veto rules."""

from __future__ import annotations

from dataclasses import asdict, replace

import numpy as np

from silverstar_flp.analysis.geodesy import GeoLocal_ToEnu
from silverstar_flp.analysis.navigation_policy import (
    FusionSupervisor,
    GnssQuality_VarianceScale,
    StaggeredWindows,
)
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.plugins.algorithms.eskf15.plugin import Native_PhysicalMask


def QualitySchedule_Apply(dataset, schedule, parameters):
    initial = dataset.initial_state.payload
    if not int(initial.get("origin_valid_flags", 0)) & 1:
        raise ValueError("gnss_origin_unavailable")
    origin = tuple(
        int(initial[name])
        for name in ("gnss_origin_latitude_e7", "gnss_origin_longitude_e7", "gnss_origin_height_mm")
    )
    native = dataset.Records_Get("GNSS_NATIVE")
    if not native:
        raise ValueError("gnss_integrity_native_evidence_missing")
    quality_records = {
        (int(r.payload["native_sequence"]), int(r.payload["receive_us"])): r.payload
        for r in dataset.Records_Get("NAV_QUALITY")
    }
    windows = StaggeredWindows(
        max_gap_us=int(parameters["gnss_integrity_max_gap_ms"]) * 1000,
        threshold_m=float(parameters["gnss_integrity_error_threshold_m"]),
        maximum_scale=float(parameters["gnss_integrity_position_r_scale"]),
    )
    evidence, decisions = [], {}
    native_time_unavailable = False
    for record in native:
        p = record.payload
        key = (int(p["sequence"]), int(p["receive_timestamp_us"]))
        logged = quality_records.get(key)
        epoch = int(logged["native_epoch_us"]) if logged else int(p["sample_timestamp_us"])
        native_time_unavailable |= not bool(logged or p.get("measurement_timestamp_trusted"))
        position = GeoLocal_ToEnu(
            np.asarray([p["latitude_e7"]]),
            np.asarray([p["longitude_e7"]]),
            np.asarray([p["ellipsoid_height_mm"]]),
            origin,
        )[0]
        velocity = np.asarray(p["velocity_enu_mps"], dtype=float)
        mask = Native_PhysicalMask(p)
        accuracy = np.asarray(
            [p["horizontal_accuracy_m"], p["vertical_accuracy_m"], p["speed_accuracy_mps"]],
            dtype=float,
        )
        for group, index in enumerate((0, 1, 2, 2)):
            if not np.isfinite(accuracy[index]) or accuracy[index] < 0:
                mask &= ~(1 << group)
        valid_fields = int(p.get("supported_fields", 0)) & int(p.get("valid_fields", 0))
        quality = GnssQuality_VarianceScale(int(p["satellite_count"])) if valid_fields & 4 else 1.0
        completed = windows.Sample_Receive(
            epoch,
            position,
            velocity,
            position_valid=bool(mask & 1),
            velocity_valid=bool(mask & 4),
            source=int(p.get("instance_id", 0)),
            generation=int(logged["calibration_generation"]) if logged else 0,
            sequence=key[0],
        )
        for item in completed:
            detail = asdict(item)
            if logged:
                detail["evaluation_us"] = int(logged["evaluation_us"]) - (epoch - item.end_us)
            evidence.append(detail)
        consistency = (
            windows.VarianceScale_Get(epoch) if parameters["gnss_integrity_enable"] else 1.0
        )
        position_r = np.square(
            np.maximum(
                accuracy[[0, 0, 1]] * 1.25,
                [parameters["gnss_position_std_horizontal"]] * 2
                + [parameters["gnss_position_std_vertical"]],
            )
        ) + np.square(np.asarray(initial["gnss_origin_position_std_m"], dtype=float))
        position_r *= quality
        position_r[:2] *= consistency
        velocity_std = np.full(3, max(accuracy[2] * 1.25, parameters["gnss_velocity_std"]))
        velocity_std[2] *= parameters.get("gnss_velocity_vertical_scale", 1.0)
        decisions[key] = (
            mask,
            position_r,
            velocity_std**2 * quality,
            int(logged["source_id"]) if logged else None,
            (quality * consistency, quality, quality, quality),
        )
    output = []
    for item in schedule:
        if item.kind != "gnss":
            output.append(item)
            continue
        payload = dict(item.record.payload)
        key = (int(payload["sequence"]), int(payload["receive_timestamp_us"]))
        if key not in decisions:
            raise ValueError("gnss_integrity_native_evidence_missing")
        mask, position_r, velocity_r, source_id, variance_scales = decisions[key]
        payload["_quality_variance_scales"] = variance_scales
        payload["valid_group_mask"] = mask
        payload["_integrity_native_valid_group_mask"] = mask
        payload["position_variance_m2"] = tuple(position_r)
        payload["velocity_variance_m2ps2"] = tuple(velocity_r)
        if source_id is not None:
            payload["_quality_source_id"] = source_id
        output.append(replace(item, record=replace(item.record, payload=payload)))
    return tuple(output), {
        "revision": 3,
        "window_evidence": evidence,
        "position_disabled_count": 0,
        "native_epoch_unavailable": native_time_unavailable,
        "window_reset_count": windows.reset_count,
        "consistency_role": "bounded_position_en_variance_only",
        "position_operation_missing_count": sum(
            bool(item.record.payload.get("valid_group_mask", 0) & 3)
            and item.record.payload.get("position_operation_sequence") == 0
            for item in output
            if item.kind == "gnss"
        ),
    }


def Revision3Health_Build(timestamps, group_updates, measurement_events, start_us):
    """Outer-operation health only; historical replay never feeds this supervisor."""
    names = {"Pos EN": 0, "Pos U": 1, "Vel EN": 2, "Vel U": 3}
    evidence = {(row["group"], row["timestamp_us"]): row for row in measurement_events}
    keys = ("position_en", "position_u", "velocity_en", "velocity_u")
    events = []
    for row in group_updates:
        group = names[row["group"]]
        result = int(row["result"])
        if result == 5:  # KF6 NOT_ATTEMPTED is not ESKF MODEL_MISMATCH.
            result = 3
        observed = evidence.get((keys[group], row["timestamp_us"]), {})
        events.append(
            (
                int(row["timestamp_us"]),
                group,
                int(observed.get("receive_timestamp_us", row["timestamp_us"])),
                bool(row["valid"]),
                result,
                float(row["nis"]),
                row.get("source_id"),
                float(observed.get("variance_scale", 1.0)),
            )
        )
    for row in measurement_events:
        if row["group"] != "baro":
            continue
        accepted = bool(row["valid"]) and np.isfinite(row["effective_variance"]).all()
        result = (1 if row["r_scale"] > 1.00001 else 0) if accepted else (2 if row["valid"] else 3)
        result = int(row.get("result", result))
        events.append(
            (
                int(row["timestamp_us"]),
                4,
                int(row["receive_timestamp_us"]),
                bool(row["valid"]),
                result,
                float("nan"),
                row.get("source_id"),
                float(row.get("variance_scale", row["r_scale"] if accepted else 1.0)),
            )
        )
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    supervisor = FusionSupervisor(start_us)
    index, values = 0, []
    for timestamp in timestamps:
        while index < len(events) and events[index][0] <= timestamp:
            (evaluated, group, received, physical, result, nis, source, variance_scale) = events[
                index
            ]
            supervisor.Decision_Record(
                group,
                received,
                physically_valid=physical,
                result=result,
                nis=nis,
                gain_norm=1 if result in (0, 1) else 0,
                variance_scale=variance_scale,
                evaluation_us=evaluated,
                source=0 if source is None else int(source),
            )
            index += 1
        values.append(int(supervisor.Health_Get(int(timestamp))))
    return TimeSeries(
        np.asarray(timestamps, dtype=np.uint64),
        np.asarray(values),
        "enum",
        "status",
        "revision3_live_operation_supervisor",
        np.ones(len(values), dtype=bool),
    ), {
        "fusion_groups": [asdict(group) for group in supervisor.groups],
        "fusion_timeout_policy": "2s degraded/dead reckoning; 10s required-group invalid",
        "health_scope": (
            "recorded outer operation evidence; no reset or covariance inflation inferred"
        ),
        "source_scope": (
            "logged NAV_QUALITY identities where available; otherwise "
            "single canonical source with unknown identity"
        ),
    }
