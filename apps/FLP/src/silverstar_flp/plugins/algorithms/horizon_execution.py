"""Product-side delayed-primary execution from exact recorded initialization.

Package identity and parameter admission are checked by the owning plugin before
calling here. No file is opened, decoder selected or metadata synthesized here.
"""

from types import SimpleNamespace

import numpy as np

from silverstar_flp.decoder_profiles.fusion_horizon_records import FusionHorizonRecords_Validate
from silverstar_flp.plugins.algorithms.eskf15.horizon import DelayedHorizon
from silverstar_flp.plugins.algorithms.horizon_bodies import (
    EskfHorizonBodies_Build,
    KfHorizon_RecordedInitialize,
    KfHorizonBodies_Build,
)
from silverstar_flp.plugins.algorithms.horizon_result import HorizonAlgorithmResult_Build
from silverstar_flp.plugins.algorithms.horizon_timeline import HorizonTimeline_Run
from silverstar_flp.plugins.api.algorithm import ReplayMode

_DELAYS = {
    "gnss_position_measurement_delay_ms": (0, 1),
    "gnss_velocity_measurement_delay_ms": (2, 3),
    "baro_measurement_delay_ms": (4,),
}


def _MissionEvidence_Get(dataset, algorithm, recorded_horizon_us, begin_us, end_us):
    def records_get(name):
        return tuple(
            record
            for record in dataset.Records_Get(name)
            if begin_us <= record.timestamp_us <= end_us
        )

    evidence = FusionHorizonRecords_Validate(
        SimpleNamespace(Records_Get=records_get),
        algorithm_id=algorithm,
        horizon_us=recorded_horizon_us,
    )
    if evidence.replay_blockers:
        raise ValueError("replay_unavailable:" + ",".join(evidence.replay_blockers))
    identities = {
        (row.payload["epoch"], row.payload["source_id"], row.payload["calibration_generation"])
        for row in evidence.statuses
    }
    if len(identities) != 1:
        raise ValueError("fusion_horizon_mission_identity_ambiguous")
    return evidence, next(iter(identities))


def _Overrides_Resolve(plugin, dataset, request, parameters):
    baseline = plugin.recorded_parameters(dataset)
    delays = {}
    if request.mode == ReplayMode.RECORDED_CONFIGURATION:
        return delays
    blocked = []
    for name in parameters:
        if parameters[name] == baseline.get(name):
            continue
        if name in _DELAYS:
            for group in _DELAYS[name]:
                delays[group] = parameters[name]
        elif name.startswith("gnss_") or name == "baro_std_m":
            blocked.append(name)
    if blocked:
        # Prepared R and receipt certificates cannot be inverted to recover
        # native uncertainty or a different receiver/quality policy.
        raise ValueError(
            "fusion_horizon_receive_or_noise_recompute_unavailable:" + ",".join(sorted(blocked))
        )
    if request.quality_policy_revision not in (None, 3):
        raise ValueError("fusion_horizon_quality_policy_recompute_unavailable")
    return delays


def _FallbackTimes_Validate(evidence, recorded_parameters):
    for record in evidence.requests:
        p = record.payload
        if p["timing_flags"] & 8:
            parameter = next(name for name, groups in _DELAYS.items() if p["group"] in groups)
            value = recorded_parameters.get(parameter)
            if type(value) is not int or value < 0:
                raise ValueError("fusion_horizon_recorded_delay_actual_missing")
            expected = p["receive_timestamp_us"] - value * 1000
            if expected <= 0 or p["measurement_timestamp_us"] != expected:
                raise ValueError("fusion_horizon_recorded_fallback_time_mismatch")


def KfHorizon_Run(
    plugin,
    dataset,
    request,
    parameters,
    timing_audit,
    template,
    increments,
    context,
    bounds,
    *,
    recorded_horizon_us,
    diagnostics=None,
):
    if (
        request.mode == ReplayMode.RECORDED_CONFIGURATION
        and parameters["fusion_horizon_ms"] * 1000 != recorded_horizon_us
    ):
        raise ValueError("fusion_horizon_recorded_lag_mismatch")
    if template.algorithm_revision != 2 or not increments:
        raise ValueError("fusion_horizon_kf6_original_interval_revision_required")
    evidence, (epoch, source, calibration) = _MissionEvidence_Get(
        dataset, 1, recorded_horizon_us, bounds.start_timestamp_us, bounds.end_timestamp_us
    )
    steps = tuple(
        row
        for row in dataset.Records_Get("ESTIMATOR_STEP")
        if bounds.start_timestamp_us <= row.timestamp_us <= bounds.end_timestamp_us
    )
    keys = {
        (row.payload["source_sequence"], row.payload["interval_end_timestamp_us"]) for row in steps
    }
    selected = tuple(
        row for row in increments if (row.source_sequence, row.interval_end_timestamp_us) in keys
    )
    if not selected:
        raise ValueError("fusion_horizon_admitted_body_missing")
    first_us = selected[0].interval_start_timestamp_us
    baseline = plugin.recorded_parameters(dataset)
    _FallbackTimes_Validate(evidence, baseline)
    delays = _Overrides_Resolve(plugin, dataset, request, parameters)
    p0 = {name: parameters[name] for name in request.parameters if name.startswith("p0_")}
    if request.mode == ReplayMode.RECORDED_CONFIGURATION:
        p0 = {}
    engine, initial_q = KfHorizon_RecordedInitialize(
        dataset,
        template,
        epoch=epoch,
        source=source,
        calibration_generation=calibration,
        start_us=first_us,
        horizon_us=parameters["fusion_horizon_ms"] * 1000,
        p0_overrides=p0,
    )
    body = KfHorizonBodies_Build(
        selected,
        steps,
        evidence,
        epoch=epoch,
        source=source,
        calibration_generation=calibration,
        initial_q_nb=initial_q,
        gravity_mps2=parameters["gravity_mps2"],
    )
    timeline = HorizonTimeline_Run(
        engine,
        1,
        body.bodies,
        evidence,
        strict_recorded=request.mode == ReplayMode.RECORDED_CONFIGURATION,
        context=context,
        changed_delays_ms=delays if delays else None,
    )
    return HorizonAlgorithmResult_Build(
        plugin,
        dataset,
        request,
        parameters,
        timing_audit,
        timeline,
        1,
        quaternions=body.quaternions,
        diagnostics={
            **(diagnostics or {}),
            "body_input_source": "INERTIAL_INCREMENT+ESTIMATOR_STEP",
            "unconsumed_recorded_increment_count": len(increments) - len(selected),
            "recorded_initial_state": True,
            "recorded_horizon_us": recorded_horizon_us,
            "selected_horizon_us": engine.horizon_us,
            "epoch": epoch,
            "calibration_generation": calibration,
        },
    )


def EskfHorizon_Run(
    plugin,
    dataset,
    request,
    parameters,
    timing_audit,
    kernel,
    initial_snapshot,
    context,
    bounds,
    *,
    recorded_horizon_us,
):
    if (
        request.mode == ReplayMode.RECORDED_CONFIGURATION
        and parameters["fusion_horizon_ms"] * 1000 != recorded_horizon_us
    ):
        raise ValueError("fusion_horizon_recorded_lag_mismatch")
    evidence, (epoch, source, calibration) = _MissionEvidence_Get(
        dataset, 2, recorded_horizon_us, bounds.start_timestamp_us, bounds.end_timestamp_us
    )
    if initial_snapshot is None or (
        initial_snapshot.payload["epoch"],
        initial_snapshot.payload["source_id"],
        initial_snapshot.payload["calibration_generation"],
    ) != (epoch, source, calibration):
        raise ValueError("fusion_horizon_initial_snapshot_identity_mismatch")
    baseline = plugin.recorded_parameters(dataset)
    _FallbackTimes_Validate(evidence, baseline)
    delays = _Overrides_Resolve(plugin, dataset, request, parameters)
    records = tuple(
        row
        for row in dataset.Records_Get("ESKF15_BODY_INPUT")
        if bounds.start_timestamp_us <= row.payload["interval_start_timestamp_us"]
        and row.payload["interval_end_timestamp_us"] <= bounds.end_timestamp_us
    )
    bodies = EskfHorizonBodies_Build(records, source=source, calibration_generation=calibration)
    engine = DelayedHorizon(
        kernel,
        bodies[0].start_us,
        epoch=epoch,
        source=source,
        generation=calibration,
        horizon_us=parameters["fusion_horizon_ms"] * 1000,
        soft=(parameters["nis_1d_soft"], parameters["nis_2d_soft"]),
        hard=(parameters["nis_1d_hard"], parameters["nis_2d_hard"]),
        max_r_scale=parameters["nis_max_r_scale"],
        soft_enabled=bool(parameters.get("nis_soft_enabled", 1)),
        hard_enabled=bool(parameters.get("nis_hard_enabled", 1)),
        lever_arm=np.array([parameters["lever_arm_body_" + axis + "_m"] for axis in "xyz"]),
    )
    timeline = HorizonTimeline_Run(
        engine,
        2,
        bodies,
        evidence,
        strict_recorded=request.mode == ReplayMode.RECORDED_CONFIGURATION,
        context=context,
        changed_delays_ms=delays if delays else None,
    )
    return HorizonAlgorithmResult_Build(
        plugin,
        dataset,
        request,
        parameters,
        timing_audit,
        timeline,
        2,
        diagnostics={
            "body_input_source": "ESKF15_BODY_INPUT",
            "recorded_initial_state": True,
            "recorded_horizon_us": recorded_horizon_us,
            "selected_horizon_us": engine.horizon_us,
            "epoch": epoch,
            "calibration_generation": calibration,
            "recovery_policy": "ordinary_updates_only",
        },
    )
