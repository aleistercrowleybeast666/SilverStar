"""Product ESKF15 replay plugin; old firmware runs are explicitly What-if."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from silverstar_flp.analysis.geodesy import GeoLocal_ToEnu
from silverstar_flp.analysis.navigation_policy import (
    FusionSupervisor,
    GnssQuality_VarianceScale,
    StaggeredWindows,
    WindowEvidence,
)
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.mission import MissionReplayBounds_Get
from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfNoise, EskfState
from silverstar_flp.plugins.algorithms.eskf15.inputs import BodySteps_Build
from silverstar_flp.plugins.algorithms.eskf15.replay import DelayedReplay, Measurement
from silverstar_flp.plugins.algorithms.eskf15.verification import RecordedParity_Verify
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    EstimatorVisualizationSpec,
    FullCovarianceSpec,
    MeasurementGroupSpec,
    ParameterSpec,
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
    StateGroupSpec,
)

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[7] / "contracts/navigation_v1.json").read_text(
        encoding="utf8"
    )
)
ALGORITHM_ID = CONTRACT["eskf15"]["component_id"]
GROUPS = ("position_en", "position_u", "velocity_en", "velocity_u", "baro")


def _Parameters_Build() -> tuple[ParameterSpec, ...]:
    return tuple(
        ParameterSpec(
            name,
            "int" if item.get("type") == "integer" else "float",
            item["default"],
            item["min"],
            item["max"],
            item["unit"],
            representation=item["representation"],
            order=index,
            label_key="parameter." + name,
            group_key="parameter_group.process_model",
            tooltip_key="parameter.tooltip." + name,
        )
        for index, (name, item) in enumerate(CONTRACT["eskf15"]["parameters"].items())
    )


def _Visualization_Build() -> EstimatorVisualizationSpec:
    state = tuple(
        StateGroupSpec(
            name,
            "state." + name,
            axes,
            unit,
            "eskf15.covariance.diagonal",
            tuple(range(i, i + 3)),
            file_stem=name.title(),
            estimate_channel="eskf15." + name if name in ("gyro_bias", "accel_bias") else "",
        )
        for name, axes, unit, i in (
            ("position", ("E", "N", "U"), "m", 0),
            ("velocity", ("E", "N", "U"), "m/s", 3),
            ("attitude_error", ("X", "Y", "Z"), "rad", 6),
            ("gyro_bias", ("X", "Y", "Z"), "rad/s", 9),
            ("accel_bias", ("X", "Y", "Z"), "m/s²", 12),
        )
    )
    groups = []
    for index, name in enumerate(GROUPS):
        axes = ("E", "N") if index in (0, 2) else ("U",)
        dimension = len(axes)
        prefix = "eskf15."
        groups.append(
            MeasurementGroupSpec(
                "gnss_" + name if index < 4 else "barometric_altitude",
                "measurement.gnss_" + name if index < 4 else "measurement.barometric_altitude",
                dimension,
                axes,
                prefix + "innovation." + name,
                prefix + "nis." + name,
                prefix + "update_result." + name,
                prefix + "r_scale." + name,
                measurement_age_channel=prefix + "receive_age." + name,
                fixed_lag_latency_channel=prefix + "latency." + name,
                measurement_uncertainty_channel=prefix + "input_variance." + name,
                effective_r_channel=prefix + "effective_variance." + name,
                soft_threshold_parameter_id=f"nis_{dimension}d_soft",
                hard_threshold_parameter_id=f"nis_{dimension}d_hard",
                unit="m/s" if index in (2, 3) else "m",
                file_stem="ESKF15_" + name,
                measurement_record_names=("GNSS_MEASUREMENT" if index < 4 else "BARO_MEASUREMENT",),
            )
        )
    return EstimatorVisualizationSpec(
        state,
        tuple(groups),
        FullCovarianceSpec(
            "eskf15.covariance.upper_triangle",
            "ESKF15_Full_P_Keyframes",
            tuple(CONTRACT["eskf15"]["error_order"]),
            ("m",) * 3 + ("m/s",) * 3 + ("rad",) * 3 + ("rad/s",) * 3 + ("m/s²",) * 3,
            initial_record_name="ESKF15_INITIAL_STATE",
            initial_diagonal_field="p0_diagonal",
        ),
        navigation_health_channel="eskf15.navigation_health",
    )


def _Series_Create(timestamps, values, unit, quantity, columns=(), valid=None) -> TimeSeries:
    return TimeSeries(
        np.asarray(timestamps, dtype=np.uint64),
        np.asarray(values),
        unit,
        quantity,
        ALGORITHM_ID,
        np.ones(len(timestamps), dtype=bool) if valid is None else valid,
        columns,
        {"algorithm_revision": 1, "quality_policy_revision": 3},
    )


def Native_PhysicalMask(payload) -> int:
    """Re-evaluate only audited protocol fields, never old policy-filtered mask."""
    fields = int(payload.get("supported_fields", 0)) & int(payload.get("valid_fields", 0))
    if fields & 3 != 3 or not payload.get("online") or not payload.get("fix_ok"):
        return 0
    if int(payload.get("fix_type", 0)) not in (3, 4):
        return 0  # 2D receiver semantics are not certified by this contract.
    mask = 0
    for group, required in enumerate((8 | 32, 16 | 64, 128 | 512, 256 | 512)):
        if fields & required == required:
            mask |= 1 << group
    for group, key in enumerate(
        ("horizontal_accuracy_m", "vertical_accuracy_m", "speed_accuracy_mps", "speed_accuracy_mps")
    ):
        sigma = float(payload.get(key, np.nan))
        if not np.isfinite(sigma) or sigma < 0:
            mask &= ~(1 << group)
    velocity = int(payload.get("velocity_valid_mask", 0))
    if velocity & 3 != 3:
        mask &= ~4
    if not velocity & 4:
        mask &= ~8
    return mask


class Eskf15AlgorithmPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id=ALGORITHM_ID,
        version="1.0.0",
        display_name="ESKF_15",
        description="ENU 15-dimensional right-error inertial navigation with residual biases",
        required_records=("INITIAL_STATE", "IMU_CORRECTED"),
        optional_records=("GNSS_NATIVE", "GNSS_MEASUREMENT", "BARO_MEASUREMENT", "ESKF15_STATE"),
        required_channels=(),
        optional_channels=(),
        parameter_schema=_Parameters_Build(),
        standard_outputs=("attitude.q_nb", "navigation.position_enu", "navigation.velocity_enu"),
        diagnostic_outputs=("eskf15.covariance.diagonal", "eskf15.gyro_bias", "eskf15.accel_bias"),
        estimator_visualization=_Visualization_Build(),
        firmware_component_ids=(ALGORITHM_ID,),
        recorded_output_roles=("eskf15.recorded.navigation.position_enu",),
        required_semantic_roles=("imu.corrected.accel_b", "imu.corrected.gyro_b"),
        coordinate_frame_contract={
            "navigation_frame": "ENU",
            "quaternion_order": "WXYZ",
            "quaternion_convention": "Hamilton body-to-ENU; right error",
        },
        parameter_source_contract={
            "recorded_configuration": ".ssdecoder firmware parameters",
            "offline": "navigation_v1.json contract",
        },
    )

    def availability(self, dataset, input_source=None):
        missing = [
            name for name in ("INITIAL_STATE", "IMU_CORRECTED") if not dataset.Records_Get(name)
        ]
        if dataset.Records_Get("ESKF15_BODY_INPUT") and "IMU_CORRECTED" in missing:
            missing.remove("IMU_CORRECTED")
        if (
            self.FirmwareMember_Is(dataset)
            and dataset.Records_Get("ESKF15_INITIAL_STATE")
            and "INITIAL_STATE" in missing
        ):
            missing.remove("INITIAL_STATE")
        if input_source not in (None, "corrected_imu"):
            missing.append("corrected_imu_required")
        return AlgorithmAvailability(
            not missing,
            ReplayFidelity.APPROXIMATE if not missing else ReplayFidelity.UNAVAILABLE,
            tuple(missing),
            ("eskf15_host_parity_scope_limited",),
            ("corrected_imu",),
        )

    def _Measurements_Build(self, dataset, parameters, start_us, end_us, request):
        if dataset.Records_Get("ESKF15_MEASUREMENT"):
            events = []
            for record in dataset.Records_Get("ESKF15_MEASUREMENT"):
                p = record.payload
                evaluation = int(p["evaluation_timestamp_us"])
                if not start_us <= evaluation <= end_us:
                    continue
                group = int(p["group"])
                if group not in range(5):
                    raise ValueError("eskf15_measurement_group_unsupported")
                dimension = 2 if group in (0, 2) else 1
                variance = np.asarray(p["base_variance"])[:dimension]
                measurement_time = int(p["measurement_timestamp_us"])
                if request.mode != ReplayMode.RECORDED_CONFIGURATION:
                    receive = int(p["receive_timestamp_us"])
                    native = next(
                        (
                            r.payload
                            for r in dataset.Records_Get("GNSS_NATIVE")
                            if int(r.payload["receive_timestamp_us"]) == receive
                        ),
                        None,
                    )
                    floor_key = (
                        "gnss_position_std_horizontal"
                        if group == 0
                        else "gnss_position_std_vertical"
                        if group == 1
                        else "gnss_velocity_std"
                        if group in (2, 3)
                        else "baro_std_m"
                    )
                    if floor_key in request.parameters:
                        if group == 4:
                            variance = np.array([parameters[floor_key] ** 2])
                        elif native is None:
                            raise ValueError("eskf15_what_if_receiver_sigma_evidence_missing")
                        else:
                            sigma_key = (
                                "horizontal_accuracy_m"
                                if group == 0
                                else "vertical_accuracy_m"
                                if group == 1
                                else "speed_accuracy_mps"
                            )
                            variance = np.full(
                                dimension, max(float(native[sigma_key]), parameters[floor_key]) ** 2
                            )
                    delay_key = (
                        "gnss_position_measurement_delay_ms"
                        if group < 2
                        else "gnss_velocity_measurement_delay_ms"
                        if group < 4
                        else "baro_measurement_delay_ms"
                    )
                    if delay_key in request.parameters:
                        if group < 4 and native is None:
                            raise ValueError("eskf15_what_if_timestamp_trust_evidence_missing")
                        trusted = group == 4 or native.get("measurement_timestamp_trusted")
                        measurement_time = (
                            int(p["sample_timestamp_us"])
                            if trusted
                            else receive - int(parameters[delay_key]) * 1000
                        )
                        if group == 4:
                            measurement_time -= int(parameters[delay_key]) * 1000
                item = Measurement(
                    (int(p["operation_sequence"]), group),
                    measurement_time,
                    int(p["receive_timestamp_us"]),
                    group,
                    np.asarray(p["observation"])[:dimension],
                    variance,
                    bool(p["physically_valid"]),
                    float(p["quality_scale"]),
                    float(p["consistency_scale"]),
                    int(p["source_id"]),
                    int(p["calibration_generation"]),
                )
                events.append((evaluation, record.record_sequence, item))
            evidence, seen = [], set()
            for quality in dataset.Records_Get("NAV_QUALITY"):
                q = quality.payload
                key = (q["source_id"], q["calibration_generation"], q["window_end_us"])
                if q["quality_revision"] != 3 or not q["evidence_valid"] or key in seen:
                    continue
                seen.add(key)
                duration = int(q["window_end_us"]) - int(q["window_start_us"])
                if duration <= 0:
                    raise ValueError("navigation_window_evidence_duration_invalid")
                evidence.append(
                    WindowEvidence(
                        int(q["window_index"]),
                        int(q["window_start_us"]),
                        int(q["window_end_us"]),
                        True,
                        "recorded_complete",
                        tuple(q["closure_en_m"]),
                        float(q["covered_us"]) / duration,
                        float(q["variance_scale"]),
                        max(0, int(q["evaluation_us"]) - int(q["evidence_age_us"])),
                    )
                )
            return sorted(events, key=lambda e: (e[0], e[1])), evidence, set()
        initial = dataset.initial_state.payload
        origin_valid = bool(int(initial.get("origin_valid_flags", 0)) & 1)
        origin = tuple(
            int(initial.get(name, 0))
            for name in (
                "gnss_origin_latitude_e7",
                "gnss_origin_longitude_e7",
                "gnss_origin_height_mm",
            )
        )
        natives = {
            (int(r.payload["sequence"]), int(r.payload["receive_timestamp_us"])): r
            for r in dataset.Records_Get("GNSS_NATIVE")
        }
        windows = StaggeredWindows()
        events, evidence = [], []
        warnings = set()
        for record in dataset.Records_Get("GNSS_MEASUREMENT"):
            p = record.payload
            receive = int(p["receive_timestamp_us"])
            evaluation = int(p.get("estimator_present_timestamp_us", receive))
            if evaluation < start_us or evaluation > end_us:
                continue
            native = natives.get((int(p["sequence"]), receive))
            position, velocity = np.asarray(p["position_enu_m"]), np.asarray(p["velocity_enu_mps"])
            scale, consistency = 1.0, 1.0
            mask = int(p.get("valid_group_mask", 0)) if p.get("fusion_allowed") else 0
            r_pos, r_vel = (
                np.asarray(p["position_variance_m2"]),
                np.asarray(p["velocity_variance_m2ps2"]),
            )
            if native and origin_valid:
                n = native.payload
                mask = Native_PhysicalMask(n)
                position = GeoLocal_ToEnu(
                    np.array([n["latitude_e7"]]),
                    np.array([n["longitude_e7"]]),
                    np.array([n["ellipsoid_height_mm"]]),
                    origin,
                )[0]
                velocity = np.asarray(n["velocity_enu_mps"])
                hacc, vacc, sacc = (
                    float(n.get(key, np.nan))
                    for key in (
                        "horizontal_accuracy_m",
                        "vertical_accuracy_m",
                        "speed_accuracy_mps",
                    )
                )
                r_pos = np.square(
                    np.maximum(
                        np.array((hacc, hacc, vacc)),
                        (
                            parameters["gnss_position_std_horizontal"],
                            parameters["gnss_position_std_horizontal"],
                            parameters["gnss_position_std_vertical"],
                        ),
                    )
                )
                r_vel = np.full(3, max(sacc, parameters["gnss_velocity_std"]) ** 2)
                fields = int(n.get("supported_fields", 0)) & int(n.get("valid_fields", 0))
                scale = GnssQuality_VarianceScale(int(n["satellite_count"])) if fields & 4 else 1.0
                # Old M9N logs provide receive time, not receiver iTOW. Keep the
                # approximation visible; never call it native-epoch evidence.
                epoch = int(n["sample_timestamp_us"])
                if not n.get("measurement_timestamp_trusted"):
                    warnings.add("eskf15_native_epoch_unavailable")
                try:
                    evidence.extend(
                        windows.Sample_Receive(
                            epoch,
                            position,
                            velocity,
                            position_valid=bool(mask & 1),
                            velocity_valid=bool(mask & 4),
                            source=int(n.get("instance_id", 0)),
                            generation=int(p.get("replay_epoch", 0)),
                            sequence=int(n["sequence"]),
                        )
                    )
                except ValueError:
                    warnings.add("eskf15_gnss_epoch_discontinuity")
                consistency = windows.VarianceScale_Get(epoch)
            else:
                warnings.add("eskf15_raw_quality_evidence_missing")
            if not origin_valid:
                mask = 0
                warnings.add("eskf15_origin_unavailable")
            for group, axes in enumerate(((0, 1), (2,), (0, 1), (2,))):
                is_position = group < 2
                # These are new-policy What-if operations, not the old KF6
                # admitted schedule. Trusted MCU sample epochs bypass delay;
                # otherwise delay is applied once to actual receive time.
                trusted = native is not None and bool(
                    native.payload.get("measurement_timestamp_trusted")
                )
                delay_key = (
                    "gnss_position_measurement_delay_ms"
                    if is_position
                    else "gnss_velocity_measurement_delay_ms"
                )
                timestamp = (
                    int(native.payload["sample_timestamp_us"])
                    if trusted
                    else receive - int(parameters[delay_key]) * 1000
                )
                value, variance = (position, r_pos) if is_position else (velocity, r_vel)
                item = Measurement(
                    (record.record_sequence, group),
                    timestamp,
                    receive,
                    group,
                    value[list(axes)],
                    variance[list(axes)],
                    bool(mask & (1 << group)),
                    scale,
                    consistency if group == 0 else 1.0,
                    generation=int(p.get("replay_epoch", 0)),
                )
                events.append((evaluation, record.record_sequence, item))
        for record in dataset.Records_Get("BARO_MEASUREMENT"):
            p = record.payload
            receive = int(p["receive_timestamp_us"])
            evaluation = int(p.get("estimator_present_timestamp_us", receive))
            if not start_us <= evaluation <= end_us:
                continue
            item = Measurement(
                (record.record_sequence, 4),
                int(p["sample_timestamp_us"]) - int(parameters["baro_measurement_delay_ms"]) * 1000,
                receive,
                4,
                np.array([p["relative_altitude_m"]]),
                np.array([parameters["baro_std_m"] ** 2]),
                bool(int(p.get("valid_mask", 0)) & 1) and 0 <= evaluation - receive <= 500_000,
            )
            events.append((evaluation, record.record_sequence, item))
        return sorted(events, key=lambda e: (e[0], e[1], e[2].group)), evidence, warnings

    def run(
        self, dataset: FlightDataset, request: ReplayRequest, context: TaskContext | None = None
    ) -> AlgorithmResult:
        context = context or TaskContext()
        available = self.availability(dataset, request.input_source)
        if not available.available:
            raise ValueError("replay_unavailable:" + ",".join(available.missing_inputs))
        if request.mode == ReplayMode.RECORDED_CONFIGURATION and not self.FirmwareMember_Is(
            dataset
        ):
            raise ValueError("eskf15_not_recorded_use_what_if")
        parameters = self.Parameters_Resolve(dataset, request)
        bounds = MissionReplayBounds_Get(dataset)
        steps, input_failure, exact_body = BodySteps_Build(dataset, bounds)
        if not steps:
            raise ValueError("eskf15_body_history_insufficient")
        start = steps[0].start_us
        p0 = [
            parameters["p0_" + name]
            for name in (
                "position_e",
                "position_n",
                "position_u",
                "velocity_e",
                "velocity_n",
                "velocity_u",
                "theta_x",
                "theta_y",
                "theta_z",
                "gyro_bias_x",
                "gyro_bias_y",
                "gyro_bias_z",
                "accel_bias_x",
                "accel_bias_y",
                "accel_bias_z",
            )
        ]
        if self.FirmwareMember_Is(dataset):
            snapshot = dataset.RecordAtOrBefore_Get("ESKF15_INITIAL_STATE", start)
            initial_p = dataset.Series_Get("eskf15.initial.covariance.upper_triangle")
            if snapshot is None or initial_p is None or not exact_body:
                raise ValueError("eskf15_recorded_initialization_evidence_missing")
            if (
                snapshot.payload["algorithm_id"] != 2
                or snapshot.payload["algorithm_revision"] != 1
                or snapshot.payload["quality_revision"] != 3
            ):
                raise ValueError("eskf15_revision_unsupported")
            eligible = np.flatnonzero(
                initial_p.valid & (initial_p.timestamp_us == snapshot.timestamp_us)
            )
            if len(eligible) != 1:
                raise ValueError("eskf15_initial_covariance_incomplete_or_ambiguous")
            identity = initial_p.metadata["snapshot_identities"][int(eligible[0])]
            expected_identity = (
                snapshot.timestamp_us,
                snapshot.payload["snapshot_id"],
                2,
                snapshot.payload["epoch"],
                snapshot.payload["source_id"],
                snapshot.payload["calibration_generation"],
                0,
            )
            if tuple(identity) != expected_identity:
                raise ValueError("eskf15_initial_covariance_identity_mismatch")
            if any(
                step.generation != snapshot.payload["calibration_generation"]
                or step.source != snapshot.payload["source_id"]
                for step in steps
            ):
                raise ValueError("eskf15_body_calibration_or_source_identity_mismatch")
            if any(
                int(record.payload["epoch"]) != int(snapshot.payload["epoch"])
                or int(record.payload["calibration_generation"])
                != int(snapshot.payload["calibration_generation"])
                for record in dataset.Records_Get("ESKF15_MEASUREMENT")
                if start
                <= int(record.payload["evaluation_timestamp_us"])
                <= bounds.end_timestamp_us
            ):
                raise ValueError("eskf15_measurement_epoch_or_calibration_identity_mismatch")
            matrix = np.zeros((15, 15))
            rows, columns = np.triu_indices(15)
            matrix[rows, columns] = initial_p.values[eligible[0]]
            matrix[columns, rows] = matrix[rows, columns]
            p = snapshot.payload
            state = EskfState(
                np.asarray(p["position_enu_m"]),
                np.asarray(p["velocity_enu_mps"]),
                np.asarray(p["q_nb"]),
                np.asarray(p["gyro_bias_radps"]),
                np.asarray(p["accel_bias_mps2"]),
                matrix,
            )
            if request.mode != ReplayMode.RECORDED_CONFIGURATION:
                # Explicit What-if P0 edits replace only requested diagonal
                # entries; preserve recorded correlations and enforce SPD.
                for name in CONTRACT["eskf15"]["parameters"]:
                    if name.startswith("p0_") and name in request.parameters:
                        p0_names = [
                            key for key in CONTRACT["eskf15"]["parameters"] if key.startswith("p0_")
                        ]
                        diagonal = p0_names.index(name)
                        state.covariance[diagonal, diagonal] = parameters[name]
        else:
            initial = dataset.initial_state.payload
            state = EskfState(
                q=np.asarray(initial["q_nb"], dtype=float),
                v=np.asarray(initial["initial_velocity_enu_mps"], dtype=float),
                covariance=np.diag(p0),
            )
        kernel = Eskf15Filter(
            state,
            gravity=parameters["gravity_mps2"],
            noise=EskfNoise(
                parameters["gyro_noise_density"],
                parameters["accel_noise_density"],
                parameters["gyro_bias_rw"],
                parameters["accel_bias_rw"],
            ),
        )
        replay = DelayedReplay(
            kernel,
            start,
            soft=(parameters["nis_1d_soft"], parameters["nis_2d_soft"]),
            hard=(parameters["nis_1d_hard"], parameters["nis_2d_hard"]),
            max_r_scale=parameters["nis_max_r_scale"],
            lever_arm=np.array([parameters["lever_arm_body_" + axis + "_m"] for axis in "xyz"]),
        )
        supervisor = FusionSupervisor(start)
        events, window_evidence, warnings = self._Measurements_Build(
            dataset, parameters, start, bounds.end_timestamp_us, request
        )
        if not self.FirmwareMember_Is(dataset):
            warnings.add("eskf15_legacy_log_what_if")
        warnings.update(available.warnings)
        histories, timestamps, health = [], [], []
        measurements = [[] for _ in range(5)]
        event_index = 0
        failure = input_failure
        for index, step in enumerate(steps):
            context.Cancel_RaiseIfRequested()
            if index % 200 == 0:
                context.Progress_Report(index / len(steps), "replay.running")
            try:
                replay.Body_Receive(step)
                while event_index < len(events) and events[event_index][0] <= replay.present_us:
                    evaluation, _, item = events[event_index]
                    result = replay.Measurement_Receive(item)
                    supervisor.Decision_Record(
                        item.group,
                        item.receive_us,
                        physically_valid=item.physically_valid,
                        result=int(result.result),
                        nis=result.nis,
                        gain_norm=result.gain_norm,
                        variance_scale=(
                            float(np.max(result.effective_r / item.variance))
                            if int(result.result) == 1
                            else item.quality_scale * item.consistency_scale
                        ),
                        evaluation_us=evaluation,
                        source=item.source,
                    )
                    measurements[item.group].append((evaluation, item, result))
                    event_index += 1
            except ValueError as exc:
                failure = {"timestamp_us": step.end_us, "reason": str(exc)}
                break
            timestamps.append(replay.present_us)
            histories.append(kernel.state.State_Clone())
            current_health = int(supervisor.Health_Get(replay.present_us))
            if (step.quality_flags or 0) & 0x05:
                current_health = max(2, current_health)
            health.append(current_health)
        if failure:
            warnings.add("eskf15_replay_stopped_invalid_input")
        if not histories:
            raise ValueError("eskf15_no_valid_output:" + str(failure))
        channels = {}
        for channel, attribute, unit, quantity, columns in (
            ("navigation.position_enu", "p", "m", "position", ("E", "N", "U")),
            ("navigation.velocity_enu", "v", "m/s", "velocity", ("E", "N", "U")),
            ("attitude.q_nb", "q", "1", "quaternion", ("W", "X", "Y", "Z")),
            ("eskf15.gyro_bias", "bg", "rad/s", "bias", ("X", "Y", "Z")),
            ("eskf15.accel_bias", "ba", "m/s²", "bias", ("X", "Y", "Z")),
        ):
            channels[channel] = _Series_Create(
                timestamps, [getattr(s, attribute) for s in histories], unit, quantity, columns
            )
        channels["eskf15.covariance.diagonal"] = _Series_Create(
            timestamps,
            [np.diag(s.covariance) for s in histories],
            "mixed",
            "covariance",
            tuple(CONTRACT["eskf15"]["error_order"]),
        )
        channels["eskf15.covariance.upper_triangle"] = _Series_Create(
            timestamps,
            [s.covariance[np.triu_indices(15)] for s in histories],
            "mixed",
            "covariance",
            tuple(f"P{r}_{c}" for r in range(15) for c in range(r, 15)),
        )
        channels["eskf15.navigation_health"] = _Series_Create(timestamps, health, "enum", "status")
        for group, entries in enumerate(measurements):
            if not entries:
                continue
            t = [e[0] for e in entries]
            name = GROUPS[group]
            definitions = {
                "innovation": (
                    [e[2].innovation for e in entries],
                    "m/s" if group in (2, 3) else "m",
                ),
                "nis": ([e[2].nis for e in entries], "1"),
                "update_result": ([int(e[2].result) for e in entries], "enum"),
                "physically_valid": ([int(e[1].physically_valid) for e in entries], "bool"),
                "admitted": (
                    [int(e[1].physically_valid and int(e[2].result) < 16) for e in entries],
                    "bool",
                ),
                "input_variance": ([e[1].variance for e in entries], "mixed"),
                "effective_variance": ([e[2].effective_r for e in entries], "mixed"),
                "r_scale": (
                    [float(np.max(e[2].effective_r / e[1].variance)) for e in entries],
                    "1",
                ),
                "receive_age": ([(e[0] - e[1].receive_us) * 0.001 for e in entries], "ms"),
                "latency": ([(e[0] - e[1].timestamp_us) * 0.001 for e in entries], "ms"),
            }
            for quantity, (values, unit) in definitions.items():
                channels[f"eskf15.{quantity}.{name}"] = _Series_Create(t, values, unit, quantity)
        diagnostics = {
            **self.ParameterAudit_Get(dataset, request),
            "algorithm_revision": 1,
            "quality_policy_revision": 3,
            "fusion_groups": [asdict(g) for g in supervisor.groups],
            "model_mismatch_latched": supervisor.model_mismatch_latched,
            "window_evidence": [asdict(e) for e in window_evidence],
            "history_misses": replay.history_misses,
            "history_overflows": replay.overflows,
            "maximum_history_steps": replay.maximum_history,
            "replay_steps": replay.replay_steps,
            "maximum_replay_steps": replay.maximum_replay_steps,
            "failure": failure,
            "initial_covariance_diagonal": p0,
            "origin_preserved": True,
            "body_input_source": "ESKF15_BODY_INPUT"
            if exact_body
            else "IMU_CORRECTED_reconstruction",
            "imu_quality_evidence": "recorded" if exact_body else "unavailable_in_legacy_log",
            "recovery_count": 0,
            "fusion_timeout_policy": "degrade_then_invalid_without_independent_reset_evidence",
        }
        fidelity = ReplayFidelity.APPROXIMATE
        if request.mode == ReplayMode.RECORDED_CONFIGURATION and exact_body and not failure:
            parity = RecordedParity_Verify(dataset, channels)
            diagnostics["recorded_parity"] = parity
            if parity["passed"]:
                fidelity = ReplayFidelity.EXACT
                warnings.discard("eskf15_host_parity_scope_limited")
                diagnostics["replay_claim"] = "FAITHFUL"
            else:
                warnings.add("eskf15_recorded_parity_failed_or_incomplete")
        diagnostics.setdefault(
            "replay_claim", "WHAT_IF" if request.mode == ReplayMode.WHAT_IF else "APPROXIMATE"
        )
        context.Progress_Report(1.0, "replay.complete")
        return AlgorithmResult(
            ALGORITHM_ID,
            self.metadata.version,
            "corrected_imu",
            parameters,
            fidelity,
            ("eskf15_replay_stopped:" + failure["reason"],) if failure else (),
            tuple(sorted(warnings)),
            channels,
            diagnostics,
            "What-if"
            if request.mode == ReplayMode.WHAT_IF
            else "Offline"
            if request.mode == ReplayMode.OFFLINE
            else "Recomputed",
        )
