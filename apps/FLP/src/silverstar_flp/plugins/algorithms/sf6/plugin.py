from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.mission import MissionReplayBounds_Get, MissionReplayEndReason
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_BuildFromCorrectedImu,
    InertialIncrement_ReadRecorded,
    Mechanization_ConfigurationGet,
    Mechanization_Run,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.algorithms.sf6.filter import (
    NavigationSf6Result,
    Sf6Filter,
    Sf6Measurement,
)
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    ParameterSpec,
    ReplayFidelity,
    ReplayMode,
)

GAIN_IDS = tuple("gain_" + name for name in ("ve", "vn", "vu", "pe", "pn", "pu"))
DELAY_IDS = (
    "gnss_position_measurement_delay_ms",
    "gnss_velocity_measurement_delay_ms",
    "baro_measurement_delay_ms",
)
STATE_ORDER = ("vE", "vN", "vU", "pE", "pN", "pU")


def Sf6MeasurementTime_Resolve(receive_us, sample_us, trusted, delay_ms):
    """system_time.c: receive-only fallback also applies when delay is zero."""
    if receive_us <= 0 or trusted not in (0, 1) or not 0 <= delay_ms <= 550:
        raise ValueError("sf6_measurement_time_invalid")
    if trusted:
        if not 0 < sample_us <= receive_us:
            raise ValueError("sf6_measurement_time_invalid")
        return int(sample_us)
    timestamp = int(receive_us) - int(delay_ms) * 1000
    if timestamp < 0:
        raise ValueError("sf6_measurement_time_invalid")
    return timestamp


@dataclass(frozen=True, slots=True)
class _Observation:
    evaluation_us: int
    order: int
    measurement: Sf6Measurement
    physical: bool
    source: str


class Sf6AlgorithmPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id="silverstar.algorithm.sf6",
        version="0.1.0-c-core-revision1",
        display_name="SF6",
        description="Fixed-gain ENU fusion; no covariance or confidence",
        required_records=("INITIAL_STATE", "SYSTEM_CONFIG"),
        optional_records=("SF6_STATE", "SF6_MEASUREMENT", "GNSS_MEASUREMENT", "BARO_MEASUREMENT"),
        required_channels=(),
        optional_channels=(),
        parameter_schema=tuple(
            ParameterSpec(
                name,
                "float",
                0.2,
                0,
                1,
                "1",
                precision=6,
                order=i,
                step=0.01,
                label_key="parameter." + name,
                group_key="parameter_group.sf6_gain",
                tooltip_key="parameter.tooltip.sf6_gain",
            )
            for i, name in enumerate(GAIN_IDS)
        )
        + tuple(
            ParameterSpec(
                name,
                "int",
                default,
                0,
                550,
                "ms",
                order=i + 6,
                label_key="parameter." + name,
                group_key="parameter_group.measurement_delay",
            )
            for i, (name, default) in enumerate(zip(DELAY_IDS, (0, 270, 0), strict=True))
        )
        + (
            ParameterSpec(
                "gravity_mps2",
                "float",
                9.78,
                1,
                20,
                "m/s^2",
                order=9,
                label_key="parameter.gravity_mps2",
                group_key="parameter_group.process_model",
            ),
        ),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
            "navigation.specific_force_enu",
            "navigation.linear_accel_enu",
        ),
        diagnostic_outputs=("sf6.state", "sf6.gain"),
        firmware_component_ids=("silverstar.algorithm.estimator.sf6",),
        recorded_output_roles=("sf6.recorded.navigation.position_enu",),
        parameter_source_contract={
            "recorded_configuration": "exact decoder SF6 gains/delays + INS gravity",
            "offline": "explicit defaults, never recorded configuration",
        },
        coordinate_frame_contract={"navigation_frame": "ENU", "state_order": STATE_ORDER},
        cadence_contract={
            "max_dt_s": 0.02,
            "history_capacity": 256,
            "history_us": 600000,
            "event_capacity": 256,
        },
        gap_tolerance_contract={"interpolation": "forbidden", "prediction_gap": "reject replay"},
    )

    def recorded_parameters(self, dataset):
        values = dict(super().recorded_parameters(dataset))
        if self.FirmwareMember_Is(dataset):
            values.update(PureInsAlgorithmPlugin().recorded_parameters(dataset))
        return values

    def availability(self, dataset, input_source=None):
        base = PureInsAlgorithmPlugin().availability(dataset, input_source)
        missing = list(base.missing_inputs)
        if not dataset.Records_Get("SYSTEM_CONFIG"):
            missing.append("SYSTEM_CONFIG")
        warnings = [*base.warnings, "sf6_backend_schedule_not_exact", "sf6_defaults_not_tuned"]
        if not dataset.Records_Get("SF6_MEASUREMENT"):
            warnings.append("sf6_recorded_admission_reused")
        if not dataset.Records_Get("SF6_MEASUREMENT") and not dataset.Records_Get(
            "GNSS_MEASUREMENT"
        ):
            warnings.append("sf6_gnss_optional_missing")
        if not dataset.Records_Get("SF6_MEASUREMENT") and not dataset.Records_Get(
            "BARO_MEASUREMENT"
        ):
            warnings.append("sf6_baro_optional_missing")
        return AlgorithmAvailability(
            not missing,
            ReplayFidelity.UNAVAILABLE if missing else ReplayFidelity.APPROXIMATE,
            tuple(missing),
            tuple(dict.fromkeys(warnings)),
            base.supported_input_sources,
        )

    def _Observations_Build(self, dataset, parameters, recorded, warnings):
        observations = []
        native = {}
        for record in dataset.Records_Get("GNSS_NATIVE"):
            p = record.payload
            native.setdefault((p.get("sequence"), p.get("receive_timestamp_us")), []).append(p)
        origin_flags = int(dataset.initial_state.payload.get("origin_valid_flags", 0))
        sf6_records = dataset.Records_Get("SF6_MEASUREMENT")
        sources = (
            (("SF6_MEASUREMENT", sf6_records),)
            if sf6_records
            else (
                ("GNSS_MEASUREMENT", dataset.Records_Get("GNSS_MEASUREMENT")),
                ("BARO_MEASUREMENT", dataset.Records_Get("BARO_MEASUREMENT")),
            )
        )
        for name, records in sources:
            for record in records:
                p = record.payload
                receive = int(p["receive_timestamp_us"])
                sequence = int(p["sequence"])
                sample = int(p.get("sample_timestamp_us", 0))
                evidence = native.get((sequence, receive), [])
                trust = p.get("measurement_timestamp_trusted")
                if trust is None and len(evidence) == 1:
                    trust = evidence[0].get("measurement_timestamp_trusted")
                evaluation = int(
                    p.get(
                        "evaluation_timestamp_us", p.get("estimator_present_timestamp_us", receive)
                    )
                )
                if name == "SF6_MEASUREMENT":
                    groups = [
                        (int(p["group"]), tuple(p["observation"]), bool(p["physically_valid"]))
                    ]
                elif name == "BARO_MEASUREMENT":
                    groups = [
                        (
                            4,
                            (p["relative_altitude_m"], 0),
                            bool(
                                origin_flags & 2 and p.get("valid_mask", 0) and record.valid_flags
                            ),
                        )
                    ]
                else:
                    mask = int(p.get("valid_group_mask", 0))
                    if "valid_group_mask" not in p:
                        velocity_mask = int(p.get("velocity_valid_mask", 0))
                        mask = 3 if record.valid_flags & 1 and p.get("position_usable", 0) else 0
                        mask |= 4 if record.valid_flags & 2 and velocity_mask & 3 == 3 else 0
                        mask |= 8 if record.valid_flags & 2 and velocity_mask & 4 else 0
                    allowed = bool(origin_flags & 1 and p.get("fusion_allowed", 0))
                    position, velocity = p["position_enu_m"], p["velocity_enu_mps"]
                    groups = [
                        (0, tuple(position[:2]), allowed and bool(mask & 1)),
                        (1, (position[2], 0), allowed and bool(mask & 2)),
                        (2, tuple(velocity[:2]), allowed and bool(mask & 4)),
                        (3, (velocity[2], 0), allowed and bool(mask & 8)),
                    ]
                for group, observation, physical in groups:
                    if not 0 <= group < 5:
                        raise ValueError("sf6_measurement_group_invalid")
                    delay_id = DELAY_IDS[0 if group < 2 else 1 if group < 4 else 2]
                    # SF6 records carry the actual resolved epoch. Keep it unless the
                    # user changes the delay; that needs timestamp-trust evidence.
                    preserve = name == "SF6_MEASUREMENT" and parameters[delay_id] == recorded.get(
                        delay_id
                    )
                    if preserve:
                        epoch = int(p["measurement_timestamp_us"])
                    else:
                        if trust is None:
                            if name == "SF6_MEASUREMENT":
                                raise ValueError("measurement_timestamp_trust_evidence_missing")
                            warnings.append("sf6_timestamp_trust_missing_receive_only")
                        try:
                            epoch = Sf6MeasurementTime_Resolve(
                                receive, sample, trust or 0, parameters[delay_id]
                            )
                        except ValueError:
                            epoch, physical = 0, False
                    observations.append(
                        _Observation(
                            evaluation,
                            record.record_sequence,
                            Sf6Measurement(epoch, receive, sequence, group, observation),
                            physical,
                            name,
                        )
                    )
        return sorted(
            observations,
            key=lambda o: (o.evaluation_us, o.measurement.group == 4, o.order, o.measurement.group),
        )

    def run(self, dataset, request, context=None):
        task = context or TaskContext()
        availability = self.availability(dataset, request.input_source)
        if not availability.available:
            raise ValueError("replay_unavailable:" + ",".join(availability.missing_inputs))
        parameters = self.Parameters_Resolve(dataset, request)
        warnings = list(availability.warnings)
        initial = dataset.initial_state
        start = dataset.start_timestamp_us or initial.timestamp_us
        bounds = MissionReplayBounds_Get(dataset)
        end = (
            bounds.end_timestamp_us if bounds.end_reason == MissionReplayEndReason.LANDING else None
        )
        config = Mechanization_ConfigurationGet(dataset)
        if request.input_source == "corrected_imu":
            increments, diagnostics = InertialIncrement_BuildFromCorrectedImu(
                dataset.Records_Get("IMU_CORRECTED"),
                start_timestamp_us=start,
                end_timestamp_us=end,
                minimum_sample_rate_hz=config["minimum_sample_rate_hz"],
                maximum_sample_rate_hz=config["maximum_sample_rate_hz"],
            )
            if diagnostics.sample_gap_count:
                warnings.append("input_sample_gaps_detected")
        else:
            increments = InertialIncrement_ReadRecorded(
                dataset.Records_Get("INERTIAL_INCREMENT"),
                start_timestamp_us=start,
                end_timestamp_us=end,
            )
        if not increments:
            raise ValueError("replay_no_valid_mechanization_output")
        outputs = Mechanization_Run(
            increments,
            initial_q_nb=initial.payload["q_nb"],
            gravity_mps2=parameters["gravity_mps2"],
        )
        velocity = initial.payload["initial_velocity_enu_mps"]
        gain = [parameters[name] for name in GAIN_IDS]
        core = Sf6Filter(gain, velocity, increments[0].interval_start_timestamp_us)
        initial_epoch = core.history[0].timestamp_us
        observations = self._Observations_Build(
            dataset, parameters, self.recorded_parameters(dataset), warnings
        )
        if self.FirmwareMember_Is(dataset) and request.mode == ReplayMode.RECORDED_CONFIGURATION:
            for record in dataset.Records_Get("SF6_STATE"):
                if not np.array_equal(
                    np.asarray(record.payload["gain"], dtype=np.float32), core.gain
                ):
                    raise ValueError("sf6_recorded_gain_configuration_mismatch")
        cursor, states, events = 0, [], []
        for i, (increment, output) in enumerate(zip(increments, outputs, strict=True)):
            task.Cancel_RaiseIfRequested()
            result = core.Predict(
                output.timestamp_us, output.delta_velocity_enu_mps, increment.dt_s
            )
            if result != NavigationSf6Result.OK:
                raise ValueError(f"sf6_prediction_rejected:{output.timestamp_us}:{result.name}")
            while (
                cursor < len(observations)
                and observations[cursor].evaluation_us <= output.timestamp_us
            ):
                item = observations[cursor]
                cursor += 1
                if item.evaluation_us < initial_epoch:
                    continue  # Pre-START evidence is not a mission observation.
                result, boundary = (
                    core.Update(item.measurement)
                    if item.physical
                    else (NavigationSf6Result.INVALID_ARGUMENT, None)
                )
                events.append(
                    {
                        "timestamp_us": output.timestamp_us,
                        "group": item.measurement.group,
                        "receive_timestamp_us": item.measurement.receive_us,
                        "measurement_timestamp_us": item.measurement.measurement_us,
                        "boundary_timestamp_us": boundary,
                        "sequence": item.measurement.sequence,
                        "physically_valid": item.physical,
                        "result": int(result),
                        "observation": [
                            float(value) if np.isfinite(value) else None
                            for value in item.measurement.observation
                        ],
                        "source": item.source,
                    }
                )
            states.append(core.state)
            if i % 100 == 0:
                task.Progress_Report(0.1 + 0.85 * i / len(outputs), "replay.mechanization")
        timestamps = np.asarray([output.timestamp_us for output in outputs], dtype=np.uint64)
        states = np.asarray(states)
        provenance = (
            "What-if"
            if request.mode == ReplayMode.WHAT_IF
            else "Offline"
            if request.mode == ReplayMode.OFFLINE
            else "Recomputed from recorded configuration"
        )

        def series(values, unit, quantity, columns=()):
            return TimeSeries(
                timestamps,
                np.asarray(values),
                unit,
                quantity,
                self.metadata.plugin_id,
                np.ones(len(timestamps), dtype=bool),
                columns,
                {"provenance": provenance},
            )

        channels = {
            "attitude.q_nb": series(
                [o.q_nb for o in outputs], "1", "quaternion", ("W", "X", "Y", "Z")
            ),
            "navigation.velocity_enu": series(states[:, :3], "m/s", "velocity", ("E", "N", "U")),
            "navigation.position_enu": series(states[:, 3:], "m", "position", ("E", "N", "U")),
            "navigation.specific_force_enu": series(
                [o.specific_force_enu_mps2 for o in outputs],
                "m/s^2",
                "specific_force",
                ("E", "N", "U"),
            ),
            "navigation.linear_accel_enu": series(
                [o.delta_velocity_enu_mps / o.dt_s for o in outputs],
                "m/s^2",
                "acceleration",
                ("E", "N", "U"),
            ),
            "sf6.state": series(states, "mixed", "state", STATE_ORDER),
            "sf6.gain": series(np.tile(core.gain, (len(states), 1)), "1", "gain", STATE_ORDER),
        }
        task.Progress_Report(1, "replay.complete")
        return AlgorithmResult(
            self.metadata.plugin_id,
            self.metadata.version,
            request.input_source,
            parameters,
            ReplayFidelity.APPROXIMATE,
            (),
            tuple(dict.fromkeys(warnings)),
            channels,
            {
                **self.ParameterAudit_Get(dataset, request),
                "state_order": STATE_ORDER,
                "gain_order": STATE_ORDER,
                "has_covariance": False,
                "uses_magnetometer": False,
                "initial_velocity_policy": "INITIAL_STATE adopted velocity",
                "initial_position_policy": "zero",
                "history_window_us": 600000,
                "history_capacity": 256,
                "event_capacity": 256,
                "shared_pu_gain": "GNSS height and relative barometer altitude",
                "measurement_events": events,
                "output_count": len(outputs),
                "mission_end_timestamp_us": int(timestamps[-1]) if end is None else end,
                "mission_end_reason": bounds.end_reason.value,
                "critical_missing_conditions": [
                    "full backend/queue/quality timing not reproduced",
                    "no full-firmware exactness certification",
                ],
                "unapplied_observation_count": len(observations) - cursor,
            },
            provenance,
        )
