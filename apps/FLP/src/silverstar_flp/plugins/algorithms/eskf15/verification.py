"""Recorded revision-1 parity gate with explicit first divergent operation."""

from __future__ import annotations

import numpy as np


def RecordedParity_Verify(dataset, channels):
    policy = (
        dataset.semantic_context.LoggingStream_Get("ESKF15_FULL_P_PART")
        if dataset.semantic_context is not None
        else None
    )
    periodic_p_optional = policy is not None and policy.get("enabled") is False
    has_p_fragments = bool(dataset.Records_Get("ESKF15_FULL_P_PART"))
    compare_cross_covariance = not periodic_p_optional or has_p_fragments
    required = (
        "navigation.position_enu",
        "navigation.velocity_enu",
        "attitude.q_nb",
        "eskf15.gyro_bias",
        "eskf15.accel_bias",
        "eskf15.covariance.diagonal",
        *(("eskf15.covariance.upper_triangle",) if compare_cross_covariance else ()),
    )
    candidates = (
        *required,
        *(
            name
            for name in channels
            if any(
                name.startswith("eskf15." + quantity + ".")
                for quantity in (
                    "update_result",
                    "physically_valid",
                    "admitted",
                    "nis",
                    "innovation",
                    "effective_variance",
                )
            )
        ),
    )
    maximum, missing, first_difference, unavailable = {}, [], None, {}
    if dataset.metadata.get("eskf15_covariance_diagnostics"):
        missing.append("covariance_fragment_assembly_failed")
    for name in candidates:
        recorded = dataset.Series_Get("eskf15.recorded." + name.removeprefix("eskf15."))
        if recorded is None:
            missing.append(name)
            continue
        replayed = channels[name]
        indexes = np.searchsorted(replayed.timestamp_us, recorded.timestamp_us)
        matched = indexes < replayed.count
        matched[matched] &= (
            replayed.timestamp_us[indexes[matched]] == recorded.timestamp_us[matched]
        )
        matched &= recorded.valid
        if not np.all(matched):
            missing.append(name + ":timestamp_or_validity")
            continue
        observed, expected = replayed.values[indexes], recorded.values
        # Preserve deterministic quaternion sign, not merely equivalent attitude.
        exact = any(key in name for key in ("update_result", "physically_valid", "admitted"))
        tolerance = (0, 0) if exact else (2e-4, 3e-4)
        equal = np.isclose(observed, expected, atol=tolerance[0], rtol=tolerance[1], equal_nan=True)
        finite = np.isfinite(observed) & np.isfinite(expected)
        if any(
            name.startswith("eskf15." + key + ".")
            for key in ("nis", "innovation", "effective_variance")
        ):
            group = name.rsplit(".", 1)[1]
            not_attempted = np.ones(recorded.count, dtype=bool)
            for quantity in ("admitted", "update_result"):
                reference = dataset.Series_Get(f"eskf15.recorded.{quantity}.{group}")
                actual = channels.get(f"eskf15.{quantity}.{group}")
                if reference is None or actual is None:
                    not_attempted[:] = False
                    break
                if not (
                    np.array_equal(reference.timestamp_us, recorded.timestamp_us)
                    and np.array_equal(actual.timestamp_us, replayed.timestamp_us)
                ):
                    not_attempted[:] = False
                    break
                not_attempted &= reference.values == actual.values[indexes]
                if quantity == "admitted":
                    not_attempted &= reference.values == 0
            unavailable[name] = int(np.count_nonzero(not_attempted))
            # An unattempted update has no innovation/NIS/effective R. The C wire
            # leaves these slots zero; Python uses NaN. Admission and result are
            # still compared exactly above; attempted diagnostics never bypass.
            equal[not_attempted] = True
            finite[not_attempted] = False
        maximum[name] = (
            float(np.max(np.abs(observed[finite] - expected[finite]))) if np.any(finite) else 0.0
        )
        if not np.all(equal):
            location = tuple(int(i) for i in np.argwhere(~equal)[0])
            item = {
                "channel": name,
                "timestamp_us": int(recorded.timestamp_us[location[0]]),
                "recorded": float(expected[location]),
                "recomputed": float(observed[location]),
                "component": list(location[1:]),
            }
            if first_difference is None or item["timestamp_us"] < first_difference["timestamp_us"]:
                first_difference = item
    diagnostics = dataset.diagnostics
    stream_intact = not (
        diagnostics.record_crc_failures
        or diagnostics.sequence_gap_count
        or diagnostics.truncated_tail
    )
    return {
        "passed": not missing and first_difference is None and stream_intact,
        "scope": (
            "recorded revision 1 float32/float64 parity; "
            "absolute 2e-4, relative 3e-4; results exact"
        ),
        "missing_evidence": missing,
        "stream_intact": stream_intact,
        "first_difference": first_difference,
        "maximum_absolute_error": maximum,
        "unattempted_diagnostic_rows_unavailable": unavailable,
        "cross_covariance_comparison": (
            "compared"
            if compare_cross_covariance
            else "unavailable: periodic full P explicitly disabled in exact decoder"
        ),
    }
