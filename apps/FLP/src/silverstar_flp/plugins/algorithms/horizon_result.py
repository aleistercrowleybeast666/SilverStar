"""Present independent primary/output epochs and real completed numerical work."""

import numpy as np

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.plugins.algorithms.pure_ins.plugin import SOURCE_RECORDED_INCREMENT
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity, ReplayMode


def _Series(times, values, source, unit, quantity, *, columns=(), valid=None, metadata=None):
    count = len(times)
    return TimeSeries(
        np.asarray(times, dtype=np.uint64),
        np.asarray(values, dtype=float),
        unit,
        quantity,
        source,
        np.ones(count, dtype=bool) if valid is None else np.asarray(valid, dtype=bool),
        tuple(columns),
        {"provenance": "Recomputed", **(metadata or {})},
    )


def HorizonChannels_Build(timeline, algorithm_id, *, quaternions=None):
    if algorithm_id not in (1, 2) or not timeline.samples:
        raise ValueError("fusion_horizon_no_valid_output")
    prefix = "kf6" if algorithm_id == 1 else "eskf15"
    source = "silverstar.algorithm." + prefix
    samples = timeline.samples
    times = [sample.timestamp_us for sample in samples]
    state_size = 6 if algorithm_id == 1 else 15
    channels = {}
    for phase in ("output", "primary"):
        states = [getattr(sample, phase) for sample in samples]
        phase_times = (
            times if phase == "output" else [sample.primary_timestamp_us for sample in samples]
        )
        position = [state.state[:3] if algorithm_id == 1 else state.p for state in states]
        velocity = [state.state[3:] if algorithm_id == 1 else state.v for state in states]
        name = "" if phase == "output" else prefix + ".horizon.primary."
        channels[name + "navigation.position_enu"] = _Series(
            phase_times, position, source, "m", "position", columns=("E", "N", "U")
        )
        channels[name + "navigation.velocity_enu"] = _Series(
            phase_times, velocity, source, "m/s", "velocity", columns=("E", "N", "U")
        )
        covariance_prefix = prefix + "." if phase == "output" else prefix + ".horizon.primary."
        channels[covariance_prefix + "covariance.diagonal"] = _Series(
            phase_times,
            [np.diag(state.covariance) for state in states],
            source,
            "mixed",
            "covariance",
        )
        channels[covariance_prefix + "covariance.upper_triangle"] = _Series(
            phase_times,
            [state.covariance[np.triu_indices(state_size)] for state in states],
            source,
            "mixed",
            "covariance",
            columns=tuple(
                f"P{row}_{column}" for row in range(state_size) for column in range(row, state_size)
            ),
        )
        if algorithm_id == 2:
            for attribute, label, unit in (
                ("q", "attitude.q_nb", "1"),
                ("bg", "gyro_bias", "rad/s"),
                ("ba", "accel_bias", "m/s2"),
            ):
                target = (
                    label if phase == "output" and attribute == "q" else covariance_prefix + label
                )
                channels[target] = _Series(
                    phase_times,
                    [getattr(state, attribute) for state in states],
                    source,
                    unit,
                    "quaternion" if attribute == "q" else "bias",
                )
    if algorithm_id == 1:
        if quaternions is None or any(time not in quaternions for time in times):
            raise ValueError("fusion_horizon_attitude_epoch_missing")
        channels["attitude.q_nb"] = _Series(
            times,
            [quaternions[time] for time in times],
            source,
            "1",
            "quaternion",
            columns=("W", "X", "Y", "Z"),
        )
        channels["kf6.state"] = _Series(
            times,
            [sample.output.state for sample in samples],
            source,
            "mixed",
            "state",
            columns=("pE", "pN", "pU", "vE", "vN", "vU"),
        )
    for name, values, unit in (
        ("primary_timestamp_us", [sample.primary_timestamp_us for sample in samples], "us"),
        (
            "output_covariance_timestamp_us",
            [sample.output_covariance_timestamp_us for sample in samples],
            "us",
        ),
        ("warmup", [int(sample.warmup) for sample in samples], "bool"),
        ("work_count", [sample.work_count for sample in samples], "1"),
    ):
        channels[prefix + ".horizon." + name] = _Series(times, values, source, unit, name)
    # Numerical completions alone cannot reconstruct source-selection/liveness
    # barriers. Preserve the unknown health explicitly; never manufacture READY.
    channels[prefix + ".navigation_health"] = _Series(
        times,
        np.zeros(len(times)),
        source,
        "enum",
        "status",
        valid=np.zeros(len(times), dtype=bool),
        metadata={
            "unavailable_reason": "fusion_horizon_source_selection_health_evidence_unavailable"
        },
    )
    names = ("position_en", "position_u", "velocity_en", "velocity_u", "baro")
    for group, name in enumerate(names):
        entries = [
            (time, event, outcome)
            for time, event, outcome in timeline.completions
            if event.group == group
        ]
        if not entries:
            continue
        stamps = [entry[0] for entry in entries]
        dimension = 2 if group in (0, 2) else 1
        variance = [entry[1].prepared_variance[:dimension] for entry in entries]
        effective = [
            (entry[2].effective_variance if algorithm_id == 1 else entry[2].effective_r)[:dimension]
            for entry in entries
        ]
        definitions = {
            "innovation": (
                [entry[2].innovation[:dimension] for entry in entries],
                "m/s" if group in (2, 3) else "m",
            ),
            "nis": ([entry[2].nis for entry in entries], "1"),
            "update_result": ([int(entry[2].result) for entry in entries], "enum"),
            "physically_valid": ([int(entry[1].physically_valid) for entry in entries], "bool"),
            "admitted": ([1] * len(entries), "bool"),
            "effective_update": (
                [
                    int(entry[2].effective_update)
                    if algorithm_id == 1
                    else int(int(entry[2].result) in (0, 1) and entry[2].gain_norm > 0)
                    for entry in entries
                ],
                "bool",
            ),
            "input_variance": (variance, "mixed"),
            "effective_variance": (effective, "mixed"),
            "r_scale": (
                [
                    float(np.max(np.asarray(r) / np.asarray(base)))
                    for r, base in zip(effective, variance, strict=True)
                ],
                "1",
            ),
            "receive_age": (
                [(time - event.receive_us) * 0.001 for time, event, _ in entries],
                "ms",
            ),
            "latency": ([(time - event.timestamp_us) * 0.001 for time, event, _ in entries], "ms"),
            "source_timestamp_us": ([event.timestamp_us for _, event, _ in entries], "us"),
            "application_timestamp_us": ([event.timestamp_us for _, event, _ in entries], "us"),
            "fusion_timing_mode": ([2] * len(entries), "enum"),
            "execution_result": ([0] * len(entries), "enum"),
        }
        for quantity, (values, unit) in definitions.items():
            target = quantity
            if algorithm_id == 1 and quantity not in ("innovation", "nis", "update_result"):
                target = "measurement_" + (
                    "fixed_lag_latency" if quantity == "latency" else quantity
                )
            valid = (
                [int(entry[2].result) in (0, 1, 2) for entry in entries]
                if quantity in ("nis", "innovation", "effective_variance", "r_scale")
                else None
            )
            channels[f"{prefix}.{target}.{name}"] = _Series(
                stamps,
                values,
                source,
                unit,
                quantity,
                valid=valid,
                metadata={
                    "input_variance_basis": "prepared_R_includes_quality_and_consistency",
                    "r_scale_basis": "effective_over_prepared",
                },
            )
    return channels


def HorizonAlgorithmResult_Build(
    plugin,
    dataset,
    request,
    parameters,
    timing_audit,
    timeline,
    algorithm_id,
    *,
    quaternions=None,
    diagnostics=None,
):
    channels = HorizonChannels_Build(timeline, algorithm_id, quaternions=quaternions)
    effective = sum(
        int(outcome.effective_update)
        if algorithm_id == 1
        else int(int(outcome.result) in (0, 1) and outcome.gain_norm > 0)
        for _, _, outcome in timeline.completions
    )
    failure = timeline.failure
    return AlgorithmResult(
        algorithm_id=plugin.metadata.plugin_id,
        algorithm_version=plugin.metadata.version,
        input_source=SOURCE_RECORDED_INCREMENT if algorithm_id == 1 else "corrected_imu",
        parameters=parameters,
        fidelity=ReplayFidelity.APPROXIMATE,
        missing_inputs=(f"fusion_horizon_replay_stopped:{failure['phase']}:{failure['result']}",)
        if failure
        else (),
        warnings=(
            "fusion_horizon_cross_validation_scope_limited",
            "fusion_horizon_health_reconstruction_unavailable",
        ),
        channels=channels,
        diagnostics={
            **plugin.ParameterAudit_Get(dataset, request),
            **timing_audit,
            **(diagnostics or {}),
            "fusion_timing_mode": 2,
            "history_replay_count": 0,
            "output_feedback": False,
            "fusion_timing_operations": timeline.operations,
            "request_count": len(timeline.operations),
            "attempt_count": len(timeline.completions),
            "effective_update_count": effective,
            "pending_operations": timeline.pending_operations,
            "failure": failure,
            "replay_claim": "WHAT_IF"
            if request.mode != ReplayMode.RECORDED_CONFIGURATION
            else "APPROXIMATE",
        },
        provenance="What-if"
        if request.mode == ReplayMode.WHAT_IF
        else "Offline configuration"
        if request.mode == ReplayMode.OFFLINE
        else "Recomputed from recorded configuration",
    )
