"""Offline KF6 experiments. Immutable inputs; no firmware timing compensation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayMode, ReplayRequest


def VelocitySchedule_Shift(schedule: tuple, shift_ms: int) -> tuple:
    """Positive shift delays velocity; interpolate on unchanged GNSS epoch grid.

    Position/barometer, IMU and source timestamps remain immutable. Only velocity
    and its receiver-derived variance are resampled. All offsets use the common
    interior window; no extrapolation or interpolation across missing epochs.
    """
    if type(shift_ms) is not int or not -500 <= shift_ms <= 500:
        raise ValueError("velocity_shift_out_of_range")
    gnss = [item for item in schedule if item.kind == "gnss"]
    valid = [
        item
        for item in gnss
        if item.record.valid_flags & 2
        and item.record.payload.get("fusion_allowed")
        and int(item.record.payload["velocity_valid_mask"]) & 3 == 3
    ]
    if len(valid) < 3:
        raise ValueError("velocity_sweep_insufficient_samples")
    times = np.array([item.record.payload["sample_timestamp_us"] for item in valid], dtype=np.int64)
    if np.any(np.diff(times) <= 0) or times[-1] - times[0] <= 1000000:
        raise ValueError("velocity_sweep_insufficient_monotonic_coverage")
    max_gap = 2.5 * float(np.median(np.diff(times)))
    output = []
    for item in schedule:
        if item.kind != "gnss":
            output.append(item)
            continue
        record = item.record
        payload = dict(record.payload)
        timestamp = int(payload["sample_timestamp_us"])
        query = timestamp - shift_ms * 1000
        upper = int(np.searchsorted(times, query))
        lower = upper if upper < len(times) and times[upper] == query else upper - 1
        usable = times[0] + 500000 <= timestamp <= times[-1] - 500000 and 0 <= lower <= upper < len(
            times
        )
        if usable:
            usable = times[upper] - times[lower] <= max_gap
        if usable:
            left, right = valid[lower].record.payload, valid[upper].record.payload
            fraction = np.float32(
                0 if lower == upper else (query - times[lower]) / (times[upper] - times[lower])
            )
            for name in ("velocity_enu_mps", "velocity_variance_m2ps2"):
                a, b = (
                    np.asarray(left[name], dtype=np.float32),
                    np.asarray(right[name], dtype=np.float32),
                )
                payload[name] = tuple(a + fraction * (b - a))
            payload["velocity_valid_mask"] = int(left["velocity_valid_mask"]) & int(
                right["velocity_valid_mask"]
            )
        else:
            payload["velocity_valid_mask"] = 0
        if 'valid_group_mask' in payload:
            velocity_groups = (
                (int(left["valid_group_mask"]) & int(right["valid_group_mask"]) & 12)
                if usable
                else 0
            )
            payload['valid_group_mask'] = (int(payload['valid_group_mask']) & 3) | velocity_groups
        flags = record.valid_flags if usable else record.valid_flags & ~2
        output.append(replace(item, record=replace(record, payload=payload, valid_flags=flags)))
    return tuple(output)


def _Residual_Get(series: TimeSeries, reference: TimeSeries | None) -> dict[str, Any] | None:
    if reference is None:
        return None
    _, a, b = np.intersect1d(series.timestamp_us, reference.timestamp_us, return_indices=True)
    valid = series.valid[a] & reference.valid[b]
    delta = series.values[a][valid] - reference.values[b][valid]
    delta = delta[np.isfinite(delta).all(axis=1)]
    if not len(delta):
        return {"exact_matches": 0}
    return {
        "exact_matches": len(delta),
        "rmse": np.sqrt(np.mean(delta * delta, axis=0)).tolist(),
        "last_residual": delta[-1].tolist(),
        "max_absolute": np.max(abs(delta), axis=0).tolist(),
    }


def ResultSummary_Get(
    result: AlgorithmResult,
    dataset: FlightDataset,
    stationary_interval_us: tuple[int, int] | None = None,
    reference_velocity: TimeSeries | None = None,
) -> dict[str, Any]:
    position = result.channels["navigation.position_enu"]
    velocity = result.channels["navigation.velocity_enu"]
    covariance = result.channels.get("kf6.covariance.diagonal")
    stationary = None
    if stationary_interval_us is not None:
        start, end = stationary_interval_us
        mask = velocity.valid & (velocity.timestamp_us >= start) & (velocity.timestamp_us <= end)
        samples = velocity.values[mask]
        samples = samples[np.isfinite(samples).all(axis=1)]
        if len(samples):
            stationary = np.sqrt(np.mean(samples * samples, axis=0)).tolist()
    return {
        "final_position_m": position.values[-1].tolist(),
        "final_velocity_mps": velocity.values[-1].tolist(),
        "covariance_diagonal_peak": None
        if covariance is None
        else covariance.values.max(axis=0).tolist(),
        "recorded_position_residual": _Residual_Get(
            position, dataset.Series_Get("kf6.recorded.navigation.position_enu")
        ),
        "recorded_velocity_residual": _Residual_Get(
            velocity, dataset.Series_Get("kf6.recorded.navigation.velocity_enu")
        ),
        "pure_ins_position_residual": _Residual_Get(
            position, dataset.Series_Get("pure_ins.recorded.navigation.position_enu")
        ),
        "reference_velocity_error": _Residual_Get(velocity, reference_velocity),
        "stationary_velocity_rmse": stationary,
        "stationary_interval_us": stationary_interval_us,
        "diagnostics": dict(result.diagnostics),
    }


def LatencySweep_Run(
    dataset: FlightDataset,
    request: ReplayRequest,
    *,
    context: TaskContext | None = None,
    stationary_interval_us: tuple[int, int] | None = None,
    analysis_options=None,
) -> dict[str, Any]:
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin

    plugin = Kf6AlgorithmPlugin()
    task = context or TaskContext()
    runs = {}

    def evaluate(shift):
        task.Cancel_RaiseIfRequested()
        result = plugin.run(
            dataset,
            request,
            velocity_shift_ms=shift,
            analysis_options=analysis_options,
            context=TaskContext(cancellation_event=task.cancellation_event),
        )
        summary = ResultSummary_Get(result, dataset, stationary_interval_us)
        groups = result.diagnostics["gnss_group_nis"]
        counts = result.diagnostics["gnss_group_results"]
        if any(groups[i]["count"] == 0 for i in (2, 3)):
            score = None
        else:
            # Diagnostic ranking only. A small NIS is not proof of physical accuracy.
            score = sum(
                groups[i]["p50_p90_p95_p99"][2] / threshold + counts[i][2] / groups[i]["count"]
                for i, threshold in (
                    (2, result.parameters["nis_2d_hard"]),
                    (3, result.parameters["nis_1d_hard"]),
                )
            )
        runs[shift] = {"shift_ms": shift, "score": score, **summary}

    for index, shift in enumerate(range(-500, 501, 20)):
        evaluate(shift)
        task.Progress_Report((index + 1) / 60, "replay.kf6")
    eligible = [item for item in runs.values() if item["score"] is not None]
    if not eligible:
        raise ValueError("velocity_sweep_no_qualified_vertical_and_horizontal_samples")
    best = min(eligible, key=lambda item: (item["score"], abs(item["shift_ms"])))
    for shift in range(max(-500, best["shift_ms"] - 20), min(500, best["shift_ms"] + 20) + 1, 5):
        if shift not in runs:
            evaluate(shift)
    best = min(
        (item for item in runs.values() if item["score"] is not None),
        key=lambda item: (item["score"], abs(item["shift_ms"])),
    )
    zero = runs[0]["score"]
    near = [
        item["shift_ms"]
        for item in runs.values()
        if item["score"] is not None and item["score"] <= best["score"] * 1.05
    ]
    task.Progress_Report(1.0, "replay.complete")
    return {
        "score_zero_ms": zero,
        "score_best": best["score"],
        "improvement_percent": 100 * (1 - best["score"] / zero) if zero else None,
        "sampled_minimum_width_ms": max(near) - min(near),
        "sampled_5percent_interval_ms": [min(near), max(near)],
        "confidence": "diagnostic_association_not_fixed_firmware_delay",
        "offline_diagnostics": runs[best["shift_ms"]]["diagnostics"].get("offline_diagnostics"),
        "method": (
            "velocity and receiver variance resampled on common interior GNSS epoch grid; "
            "positive shift delays velocity"
        ),
        "best_shift_ms": best["shift_ms"],
        "firmware_compensation_authorized": False,
        "runs": [runs[key] for key in sorted(runs)],
    }


def FieldSweep_Run(
    dataset: FlightDataset,
    *,
    include_latency: bool = True,
    stationary_interval_us: tuple[int, int] | None = None,
) -> dict[str, Any]:
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin

    plugin = Kf6AlgorithmPlugin()
    mode = (
        ReplayMode.RECORDED_CONFIGURATION
        if plugin.FirmwareMember_Is(dataset)
        else ReplayMode.OFFLINE
    )
    request = ReplayRequest(mode=mode)

    def run(parameters=None, legacy=False):
        changed = (
            ReplayRequest(mode=ReplayMode.WHAT_IF, parameters=parameters or {})
            if parameters
            else request
        )
        result = plugin.run(
            dataset,
            changed,
            analysis_legacy_reacquisition=legacy,
            analysis_frozen_initial=bool(parameters),
        )
        return ResultSummary_Get(result, dataset, stationary_interval_us)

    report = {"baseline": run(), "old_rejection_gate_comparison": run(legacy=True), "sweeps": {}}
    pure = PureInsAlgorithmPlugin().run(dataset, ReplayRequest(mode=mode))
    report["pure_ins"] = ResultSummary_Get(pure, dataset, stationary_interval_us)
    candidates = {
        "gnss_reacquire_outage_ms": [160, 200, 250, 300, 500],
        "gnss_position_std_vertical": [2.5, 3, 4, 5, 6],
        "baro_std_m": [1.5, 2, 3, 5],
        "gnss_velocity_vertical_scale": [1, 1.25, 1.5, 2],
    }
    for name, values in candidates.items():
        results = []
        for value in values:
            try:
                results.append({"value": value, "result": run({name: value})})
            except ValueError as error:
                results.append({"value": value, "unavailable": str(error)})
        report["sweeps"][name] = results
    if include_latency:
        try:
            report["latency"] = LatencySweep_Run(
                dataset, request, stationary_interval_us=stationary_interval_us
            )
        except ValueError as error:
            report["latency"] = {"unavailable": str(error)}
    return report
