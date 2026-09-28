from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.mission import (
    MissionReplayBounds_Get,
    MissionReplayEndReason,
)
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_BuildFromCorrectedImu,
    InertialIncrement_ReadRecorded,
    Mechanization_ConfigurationGet,
    Mechanization_Run,
)
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    ParameterSpec,
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
)

SOURCE_CORRECTED_IMU = "corrected_imu"
SOURCE_RECORDED_INCREMENT = "recorded_inertial_increment"
CURRENT_BUILD_ID = "SILV0008"


def _Series_Create(
    timestamps: np.ndarray,
    values: np.ndarray,
    *,
    unit: str,
    quantity: str,
    columns: tuple[str, ...] = (),
) -> TimeSeries:
    return TimeSeries(
        timestamp_us=np.asarray(timestamps, dtype=np.uint64),
        values=np.asarray(values, dtype=np.float64),
        unit=unit,
        quantity=quantity,
        source="silverstar.algorithm.pure_ins",
        valid=np.ones(len(timestamps), dtype=np.bool_),
        columns=columns,
        metadata={"provenance": "Recomputed"},
    )


class PureInsAlgorithmPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id="silverstar.algorithm.pure_ins",
        version="0.2.0-firmware-SILV0008",
        display_name="Pure INS",
        description="Full WXYZ/Hamilton/ENU software attitude and inertial mechanization",
        required_records=("INITIAL_STATE",),
        optional_records=("SYSTEM_CONFIG", "PURE_INS"),
        required_channels=(),
        optional_channels=("pure_ins.recorded.attitude.q_nb",),
        parameter_schema=(
            ParameterSpec(
                "gravity_mps2",
                "float",
                9.78,
                1.0,
                20.0,
                "m/s^2",
                representation="value",
                precision=6,
                order=0,
                step=0.01,
                label_key="parameter.gravity_mps2",
                group_key="parameter_group.process_model",
                tooltip_key="parameter.tooltip.gravity_mps2",
            ),
        ),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
            "navigation.specific_force_enu",
            "navigation.linear_accel_enu",
        ),
        diagnostic_outputs=(
            "mechanization.delta_theta_b",
            "mechanization.delta_velocity_b",
            "mechanization.dt",
        ),
        firmware_component_ids=("silverstar.algorithm.ins.coning2_sculling2",),
        recorded_output_roles=(
            "pure_ins.recorded.attitude.q_nb",
            "pure_ins.recorded.navigation.velocity_enu",
            "pure_ins.recorded.navigation.position_enu",
        ),
        required_semantic_roles=(
            "imu.corrected.accel_b",
            "imu.corrected.gyro_b",
        ),
        optional_semantic_roles=(
            "inertial.increment.delta_theta_b",
            "inertial.increment.delta_velocity_b",
            "pure_ins.recorded.attitude.q_nb",
        ),
        cadence_contract={
            "corrected_imu": "recorded sample timestamps within SYSTEM_CONFIG bounds",
            "recorded_inertial_increment": "recorded interval timestamps",
            "mechanization_subsample_count": 2,
        },
        gap_tolerance_contract={
            "interpolation": "forbidden",
            "corrected_imu": "reset three-sample coning/sculling history",
            "recorded_inertial_increment": "preserve recorded intervals",
        },
        parameter_source_contract={
            "recorded_configuration": "Firmware build configuration from .ssdecoder",
            "offline": "plugin defaults or explicit what-if values",
        },
        coordinate_frame_contract={
            "quaternion_order": "WXYZ",
            "quaternion_convention": "Hamilton body-to-ENU",
            "navigation_frame": "ENU",
        },
    )

    def availability(
        self, dataset: FlightDataset, input_source: str | None = None
    ) -> AlgorithmAvailability:
        source = input_source or SOURCE_CORRECTED_IMU
        missing: list[str] = []
        warnings: list[str] = []
        supported: list[str] = []
        config = Mechanization_ConfigurationGet(dataset)

        if dataset.Records_Get("INERTIAL_INCREMENT"):
            supported.append(SOURCE_RECORDED_INCREMENT)
        if dataset.Records_Get("IMU_CORRECTED"):
            supported.append(SOURCE_CORRECTED_IMU)
        if not dataset.Records_Get("INITIAL_STATE"):
            missing.append("INITIAL_STATE")
        if source == SOURCE_RECORDED_INCREMENT:
            if not dataset.Records_Get("INERTIAL_INCREMENT"):
                missing.append("INERTIAL_INCREMENT")
            decimation = config["inertial_increment_decimation"]
            if decimation not in (None, 1):
                missing.append("INERTIAL_INCREMENT(decimation=1)")
        elif source == SOURCE_CORRECTED_IMU:
            if not dataset.Records_Get("IMU_CORRECTED"):
                missing.append("IMU_CORRECTED")
            decimation = config["imu_corrected_decimation"]
            if decimation not in (None, 1):
                missing.append("IMU_CORRECTED(decimation=1)")
        else:
            missing.append(f"unsupported_input_source:{source}")
        if config["subsample_count"] != 2:
            missing.append("mechanization_subsample_count=2")
        if missing:
            return AlgorithmAvailability(
                False,
                ReplayFidelity.UNAVAILABLE,
                tuple(missing),
                tuple(warnings),
                tuple(supported),
            )

        fidelity = ReplayFidelity.EXACT
        if not dataset.Records_Get("SYSTEM_CONFIG"):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("system_config_missing_current_firmware_bounds_used")
        if str(dataset.header.get("build_id", "")) != CURRENT_BUILD_ID:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("firmware_build_differs_from_reimplementation")
        firmware_version = (
            dataset.semantic_context.FirmwareVersion_Get()
            if dataset.semantic_context is not None
            else ""
        )
        if firmware_version == "0.0.10":
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("fccg_0_0_10_host_golden_not_verified")
        elif not self.metadata.exact_validation_reference:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("host_golden_not_verified")
        if dataset.data_quality is not None and (
            dataset.data_quality.status.value == "warnings"
        ):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("source_log_has_integrity_or_sequence_gaps")
        return AlgorithmAvailability(
            True,
            fidelity,
            (),
            tuple(warnings),
            tuple(supported),
        )

    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
    ) -> AlgorithmResult:
        task_context = context or TaskContext()
        availability = self.availability(dataset, request.input_source)
        if not availability.available:
            raise ValueError("replay_unavailable:" + ",".join(availability.missing_inputs))
        initial_record = dataset.initial_state
        if initial_record is None:
            raise ValueError("replay_initial_state_missing")
        start_timestamp = dataset.start_timestamp_us or initial_record.timestamp_us
        initial_q = np.asarray(initial_record.payload["q_nb"], dtype=np.float32)
        config = Mechanization_ConfigurationGet(dataset)
        mission_bounds = MissionReplayBounds_Get(dataset)
        replay_input_end = (
            mission_bounds.end_timestamp_us
            if mission_bounds.end_reason == MissionReplayEndReason.LANDING
            else None
        )
        task_context.Progress_Report(0.05, "replay.inputs")
        source_diagnostics: Mapping[str, Any] = {}
        if request.input_source == SOURCE_CORRECTED_IMU:
            increments, build_diagnostics = InertialIncrement_BuildFromCorrectedImu(
                dataset.Records_Get("IMU_CORRECTED"),
                start_timestamp_us=start_timestamp,
                end_timestamp_us=replay_input_end,
                minimum_sample_rate_hz=config["minimum_sample_rate_hz"],
                maximum_sample_rate_hz=config["maximum_sample_rate_hz"],
            )
            source_diagnostics = {
                "invalid_sample_count": build_diagnostics.invalid_sample_count,
                "sample_gap_count": build_diagnostics.sample_gap_count,
            }
        else:
            increments = InertialIncrement_ReadRecorded(
                dataset.Records_Get("INERTIAL_INCREMENT"),
                start_timestamp_us=start_timestamp,
                end_timestamp_us=replay_input_end,
            )
        if mission_bounds.end_reason == MissionReplayEndReason.SOURCE_END:
            mission_bounds = MissionReplayBounds_Get(
                dataset,
                source_end_timestamp_us=(
                    increments[-1].interval_end_timestamp_us if increments else start_timestamp
                ),
            )
        task_context.Cancel_RaiseIfRequested()
        parameters = self.Parameters_Resolve(dataset, request)
        gravity = parameters["gravity_mps2"]
        outputs = Mechanization_Run(
            increments,
            initial_q_nb=initial_q,
            gravity_mps2=gravity,
        )
        task_context.Progress_Report(0.75, "replay.mechanization")
        if not outputs:
            raise ValueError("replay_no_valid_mechanization_output")

        timestamps = np.asarray([item.timestamp_us for item in outputs], dtype=np.uint64)
        channels = {
            "attitude.q_nb": _Series_Create(
                timestamps,
                np.asarray([item.q_nb for item in outputs]),
                unit="1",
                quantity="quaternion",
                columns=("W", "X", "Y", "Z"),
            ),
            "navigation.velocity_enu": _Series_Create(
                timestamps,
                np.asarray([item.velocity_enu_mps for item in outputs]),
                unit="m/s",
                quantity="velocity",
                columns=("E", "N", "U"),
            ),
            "navigation.position_enu": _Series_Create(
                timestamps,
                np.asarray([item.position_enu_m for item in outputs]),
                unit="m",
                quantity="position",
                columns=("E", "N", "U"),
            ),
            "navigation.specific_force_enu": _Series_Create(
                timestamps,
                np.asarray([item.specific_force_enu_mps2 for item in outputs]),
                unit="m/s^2",
                quantity="specific_force",
                columns=("E", "N", "U"),
            ),
            "navigation.linear_accel_enu": _Series_Create(
                timestamps,
                np.asarray([item.linear_accel_enu_mps2 for item in outputs]),
                unit="m/s^2",
                quantity="acceleration",
                columns=("E", "N", "U"),
            ),
            "mechanization.delta_theta_b": _Series_Create(
                timestamps,
                np.asarray([item.delta_theta_b for item in outputs]),
                unit="rad",
                quantity="angle",
                columns=("X", "Y", "Z"),
            ),
            "mechanization.delta_velocity_b": _Series_Create(
                timestamps,
                np.asarray([item.delta_velocity_b for item in outputs]),
                unit="m/s",
                quantity="velocity_increment",
                columns=("X", "Y", "Z"),
            ),
            "mechanization.dt": _Series_Create(
                timestamps,
                np.asarray([item.dt_s for item in outputs]),
                unit="s",
                quantity="time",
            ),
        }
        warnings = list(availability.warnings)
        fidelity = availability.fidelity
        if source_diagnostics.get("sample_gap_count", 0):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("input_sample_gaps_detected")
        task_context.Progress_Report(1.0, "replay.complete")
        return AlgorithmResult(
            algorithm_id=self.metadata.plugin_id,
            algorithm_version=self.metadata.version,
            input_source=request.input_source,
            parameters=parameters,
            fidelity=fidelity,
            missing_inputs=availability.missing_inputs,
            warnings=tuple(dict.fromkeys(warnings)),
            channels=channels,
            diagnostics={
                **self.ParameterAudit_Get(dataset, request),
                "input_increment_count": len(increments),
                "output_count": len(outputs),
                "start_timestamp_us": start_timestamp,
                "mission_end_timestamp_us": mission_bounds.end_timestamp_us,
                "mission_end_reason": mission_bounds.end_reason.value,
                "software_quaternion_propagation": True,
                "initial_velocity_policy": "zero_matches_firmware_pure_ins",
                **dict(source_diagnostics),
            },
            provenance=(
                "What-if"
                if request.mode == ReplayMode.WHAT_IF
                else (
                    "Offline"
                    if request.mode == ReplayMode.OFFLINE
                    else "Recomputed from recorded configuration"
                )
            ),
        )
