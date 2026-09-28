"""Version-1 ESKF diagnostics and strict, bounded covariance-part assembly."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from silverstar_flp.core.dataset import TimeSeries


def NavigationWindows_Get(records):
    """Keep receiver-native boundaries and a distinct MCU plotting timestamp."""
    evidence, seen = [], set()
    for record in records:
        p = record.payload
        identity = (p["source_id"], p["calibration_generation"], p["window_end_us"])
        if p["quality_revision"] != 3 or not p["evidence_valid"] or identity in seen:
            continue
        duration = int(p["window_end_us"]) - int(p["window_start_us"])
        if duration <= 0:
            continue
        seen.add(identity)
        evidence.append(
            {
                "window_id": int(p["window_index"]),
                "start_us": int(p["window_start_us"]),
                "end_us": int(p["window_end_us"]),
                "valid": True,
                "reason": "recorded_complete",
                "closure_en": tuple(p["closure_en_m"]),
                "coverage": p["covered_us"] / duration,
                "variance_scale": float(p["variance_scale"]),
                "evaluation_us": max(0, int(p["evaluation_us"]) - int(p["evidence_age_us"])),
            }
        )
    return evidence


def Eskf15Records_Adapt(records):
    channels, diagnostics = {}, []
    for group in range(5):
        transitions = [
            r
            for r in records.get("EVENT", ())
            if int(r.payload.get("event_id", -1)) == 0x2F and int(r.payload["arg0"]) & 0xFF == group
        ]
        if transitions:
            times = np.asarray([r.timestamp_us for r in transitions], dtype=np.uint64)
            for name, values, unit in (
                ("state", [(int(r.payload["arg0"]) >> 8) & 0xFF for r in transitions], "enum"),
                ("reason", [(int(r.payload["arg0"]) >> 16) & 0xFF for r in transitions], "enum"),
                ("age", [int(r.payload["arg1"]) for r in transitions], "ms"),
            ):
                channels[f"navigation.fusion.group{group}.{name}"] = TimeSeries(
                    times,
                    np.asarray(values),
                    unit,
                    "live_supervisor_transition",
                    "EVENT",
                    np.ones(len(transitions), dtype=bool),
                )
    quality = records.get("NAV_QUALITY", ())
    if quality:
        timestamps = np.asarray([r.payload["evaluation_us"] for r in quality], dtype=np.uint64)
        for field, unit in (
            ("closure_en_m", "m"),
            ("closure_norm_m", "m"),
            ("variance_scale", "1"),
            ("physical_mask", "mask"),
            ("admitted_mask", "mask"),
            ("accepted_mask", "mask"),
            ("nav_output_valid", "bool"),
            ("health", "enum"),
            ("evidence_age_us", "us"),
            ("covered_us", "us"),
            ("position_epoch_count", "count"),
            ("velocity_epoch_count", "count"),
            ("window_reason", "enum"),
            ("quality_degraded_mask", "mask"),
            ("window_index", "enum"),
        ):
            evidence_field = field.startswith("closure")
            valid = np.asarray(
                [
                    int(r.payload["quality_revision"]) == 3
                    and (bool(r.payload["evidence_valid"]) if evidence_field else True)
                    for r in quality
                ]
            )
            channels[f"navigation.quality.{field}"] = TimeSeries(
                timestamps,
                np.asarray([r.payload[field] for r in quality]),
                unit,
                "navigation_quality",
                "NAV_QUALITY",
                valid,
                ("E", "N") if field == "closure_en_m" else (),
            )
    # Parts share timestamp, snapshot, algorithm, epoch, source, calibration and
    # phase. A CRC-discarded part cannot be replaced by another snapshot's part.
    for record_name, role in (
        ("ESKF15_FULL_P_PART", "eskf15.recorded.covariance.upper_triangle"),
        ("ESKF15_INITIAL_P_PART", "eskf15.initial.covariance.upper_triangle"),
    ):
        groups = defaultdict(list)
        for record in records.get(record_name, ()):
            p = record.payload
            key = (
                record.timestamp_us,
                *(
                    int(p[k])
                    for k in (
                        "snapshot_id",
                        "algorithm_id",
                        "epoch",
                        "source_id",
                        "calibration_generation",
                        "phase",
                    )
                ),
            )
            groups[key].append(record)
        timestamps, values, valid, identities = [], [], [], []
        for key, fragments in sorted(groups.items()):
            reason = ""
            expected_phase = int(record_name == "ESKF15_FULL_P_PART")
            if key[2] != 2 or key[-1] != expected_phase:
                reason = "identity_mismatch"
            indexes = [int(r.payload["part_index"]) for r in fragments]
            if len(fragments) != 4 or sorted(indexes) != [0, 1, 2, 3]:
                reason = "missing_or_duplicate_part"
            if any(
                int(r.payload["part_count"]) != 4
                or int(r.payload["count"]) != 30
                or int(r.payload["offset"]) != int(r.payload["part_index"]) * 30
                or len(r.payload["values"]) != 30
                for r in fragments
            ):
                reason = "part_layout_invalid"
            if reason:
                diagnostics.append({"key": key, "reason": reason, "record": record_name})
                continue
            upper = np.concatenate(
                [
                    r.payload["values"]
                    for r in sorted(fragments, key=lambda r: r.payload["part_index"])
                ]
            )
            covariance = np.zeros((15, 15))
            rows, columns = np.triu_indices(15)
            covariance[rows, columns] = upper
            covariance[columns, rows] = upper
            good = bool(np.isfinite(covariance).all())
            if good:
                good = bool(np.linalg.eigvalsh(covariance)[0] >= -1e-6)
            if not good:
                diagnostics.append(
                    {"key": key, "reason": "covariance_not_psd", "record": record_name}
                )
            timestamps.append(key[0])
            values.append(upper)
            valid.append(good)
            identities.append(key)
        if timestamps:
            channels[role] = TimeSeries(
                np.asarray(timestamps, dtype=np.uint64),
                np.asarray(values),
                "mixed",
                "covariance",
                record_name,
                np.asarray(valid),
                tuple(f"P{r}_{c}" for r in range(15) for c in range(r, 15)),
                {
                    "record_name": record_name,
                    "assembly": "four_complete_identity_matched_parts",
                    "snapshot_identities": tuple(identities),
                },
            )
    names = ("position_en", "position_u", "velocity_en", "velocity_u", "baro")
    for group, name in enumerate(names):
        selected = sorted(
            (r for r in records.get("ESKF15_MEASUREMENT", ()) if int(r.payload["group"]) == group),
            key=lambda r: (r.payload["evaluation_timestamp_us"], r.record_sequence),
        )
        if not selected:
            continue
        dimension = 2 if group in (0, 2) else 1
        timestamps = np.asarray(
            [r.payload["evaluation_timestamp_us"] for r in selected], dtype=np.uint64
        )
        for suffix, field, quantity in (
            ("innovation", "innovation", "innovation"),
            ("nis", "nis", "nis"),
            ("update_result", "update_result", "update_result"),
            ("physically_valid", "physically_valid", "status"),
            ("admitted", "admitted", "status"),
            ("input_variance", "base_variance", "variance"),
            ("effective_variance", "effective_variance", "variance"),
        ):
            values = np.asarray([r.payload[field] for r in selected])
            if values.ndim > 1:
                values = values[:, :dimension]
            role = f"eskf15.recorded.{suffix}.{name}"
            channels[role] = TimeSeries(
                timestamps,
                values,
                "mixed",
                quantity,
                "ESKF15_MEASUREMENT",
                np.ones(len(selected), dtype=bool),
            )
        for suffix, values, unit in (
            (
                "r_scale",
                [
                    r.payload["quality_scale"]
                    * r.payload["consistency_scale"]
                    * r.payload["robust_scale"]
                    for r in selected
                ],
                "1",
            ),
            (
                "receive_age",
                [
                    (r.payload["evaluation_timestamp_us"] - r.payload["receive_timestamp_us"])
                    * 0.001
                    for r in selected
                ],
                "ms",
            ),
            (
                "latency",
                [
                    (r.payload["evaluation_timestamp_us"] - r.payload["measurement_timestamp_us"])
                    * 0.001
                    for r in selected
                ],
                "ms",
            ),
        ):
            channels[f"eskf15.recorded.{suffix}.{name}"] = TimeSeries(
                timestamps,
                np.asarray(values),
                unit,
                "diagnostic",
                "ESKF15_MEASUREMENT",
                np.ones(len(selected), dtype=bool),
            )
    return channels, tuple(diagnostics)
