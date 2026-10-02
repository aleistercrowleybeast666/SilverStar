from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.math import (
    Quaternion_Normalize,
    Quaternion_PropagateBodyIncrement,
    Quaternion_RotateVector,
)
from silverstar_flp.core.mission import (
    MissionReplayBounds_Get,
    MissionReplayEndReason,
)
from silverstar_flp.plugins.algorithms.kf6.diagnostics import (
    DiagnosticMetadata_Get,
    DiagnosticSchedule_Apply,
    Kf6DiagnosticOptions,
    MeasurementWeights_Inspect,
)
from silverstar_flp.plugins.algorithms.kf6.filter import (
    Kf6Filter,
    Kf6GnssEpoch,
    Kf6GnssGroup,
    Kf6UpdateResult,
)
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement,
    InertialIncrement_BuildFromCorrectedImu,
    InertialIncrement_ReadRecorded,
    Mechanization_ConfigurationGet,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import (
    CURRENT_BUILD_ID,
    SOURCE_CORRECTED_IMU,
    SOURCE_RECORDED_INCREMENT,
)
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


@dataclass(frozen=True, slots=True)
class _ScheduledMeasurement:
    application_timestamp_us: int
    source_order: int
    kind: str
    record: DecodedRecord
    inferred: bool


@dataclass(frozen=True, slots=True)
class _ReplaySnapshot:
    timestamp_us: int
    q_nb: np.ndarray
    state: np.ndarray
    covariance: np.ndarray
    position_innovation: np.ndarray
    velocity_innovation: np.ndarray
    baro_innovation: float
    position_nis: float
    velocity_nis: float
    group_nis: np.ndarray
    group_result: np.ndarray
    baro_nis: float
    position_result: int
    velocity_result: int
    baro_result: int
    attempt_mask: int
    r_scale: np.ndarray
    position_measurement_variance: np.ndarray
    velocity_measurement_variance: np.ndarray
    baro_measurement_variance: float


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
        source="silverstar.algorithm.kf6",
        valid=np.ones(len(timestamps), dtype=np.bool_),
        columns=columns,
        metadata={"provenance": "Recomputed"},
    )


def _Result_Aggregate(first: Kf6UpdateResult, second: Kf6UpdateResult) -> int:
    for preferred in (
        Kf6UpdateResult.ACCEPTED,
        Kf6UpdateResult.SOFT_WEIGHTED,
        Kf6UpdateResult.REJECTED_NIS,
        Kf6UpdateResult.REJECTED_INVALID,
        Kf6UpdateResult.NUMERIC_ERROR,
    ):
        if preferred in (first, second):
            return int(preferred)
    return int(Kf6UpdateResult.NUMERIC_ERROR)


class Kf6AlgorithmPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        what_if_quality_revisions=(3,),
        plugin_id="silverstar.algorithm.kf6",
        version="0.2.0-firmware-SILV0008",
        display_name="KF_6",
        description="Firmware-order 6-state [pE,pN,pU,vE,vN,vU] navigation filter",
        required_records=("INITIAL_STATE", "SYSTEM_CONFIG"),
        optional_records=(
            "GNSS_MEASUREMENT",
            "BARO_MEASUREMENT",
            "KF6_STATE",
            "KF6_DIAGNOSTIC",
            "KF6_FULL_P",
        ),
        required_channels=(),
        optional_channels=("kf6.recorded.navigation.position_enu",),
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
            ParameterSpec(
                "p0_position_e",
                "float",
                4.0,
                0.001,
                1000000.0,
                "m^2",
                representation="covariance_diagonal",
                precision=6,
                order=1,
                step=0.01,
                label_key="parameter.p0_position_e",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_position_e",
            ),
            ParameterSpec(
                "p0_position_n",
                "float",
                4.0,
                0.001,
                1000000.0,
                "m^2",
                representation="covariance_diagonal",
                precision=6,
                order=2,
                step=0.01,
                label_key="parameter.p0_position_n",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_position_n",
            ),
            ParameterSpec(
                "p0_position_u",
                "float",
                9.0,
                0.001,
                1000000.0,
                "m^2",
                representation="covariance_diagonal",
                precision=6,
                order=3,
                step=0.01,
                label_key="parameter.p0_position_u",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_position_u",
            ),
            ParameterSpec(
                "p0_velocity_e",
                "float",
                0.25,
                0.001,
                1000000.0,
                "m^2/s^2",
                representation="covariance_diagonal",
                precision=6,
                order=4,
                step=0.01,
                label_key="parameter.p0_velocity_e",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_velocity_e",
            ),
            ParameterSpec(
                "p0_velocity_n",
                "float",
                0.25,
                0.001,
                1000000.0,
                "m^2/s^2",
                representation="covariance_diagonal",
                precision=6,
                order=5,
                step=0.01,
                label_key="parameter.p0_velocity_n",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_velocity_n",
            ),
            ParameterSpec(
                "p0_velocity_u",
                "float",
                0.25,
                0.001,
                1000000.0,
                "m^2/s^2",
                representation="covariance_diagonal",
                precision=6,
                order=6,
                step=0.01,
                label_key="parameter.p0_velocity_u",
                group_key="parameter_group.initial_covariance",
                tooltip_key="parameter.tooltip.p0_velocity_u",
            ),
            ParameterSpec(
                "process_accel_std_e",
                "float",
                1.5,
                0.001,
                100.0,
                "m/s^2",
                representation="sigma",
                precision=6,
                order=7,
                step=0.01,
                label_key="parameter.process_accel_std_e",
                group_key="parameter_group.process_model",
                tooltip_key="parameter.tooltip.process_accel_std_e",
            ),
            ParameterSpec(
                "process_accel_std_n",
                "float",
                1.5,
                0.001,
                100.0,
                "m/s^2",
                representation="sigma",
                precision=6,
                order=8,
                step=0.01,
                label_key="parameter.process_accel_std_n",
                group_key="parameter_group.process_model",
                tooltip_key="parameter.tooltip.process_accel_std_n",
            ),
            ParameterSpec(
                "process_accel_std_u",
                "float",
                2.0,
                0.001,
                100.0,
                "m/s^2",
                representation="sigma",
                precision=6,
                order=9,
                step=0.01,
                label_key="parameter.process_accel_std_u",
                group_key="parameter_group.process_model",
                tooltip_key="parameter.tooltip.process_accel_std_u",
            ),
            ParameterSpec(
                "gnss_position_std_horizontal",
                "float",
                1.5,
                0.001,
                1000.0,
                "m",
                representation="sigma",
                precision=6,
                order=10,
                step=0.01,
                label_key="parameter.gnss_position_std_horizontal",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_position_std_horizontal",
            ),
            ParameterSpec(
                "gnss_position_std_vertical",
                "float",
                2.5,
                0.001,
                1000.0,
                "m",
                representation="sigma",
                precision=6,
                order=11,
                step=0.01,
                label_key="parameter.gnss_position_std_vertical",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_position_std_vertical",
            ),
            ParameterSpec(
                "gnss_velocity_std",
                "float",
                0.15,
                0.001,
                1000.0,
                "m/s",
                representation="sigma",
                precision=6,
                order=12,
                step=0.01,
                label_key="parameter.gnss_velocity_std",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_velocity_std",
            ),
            ParameterSpec(
                "gnss_velocity_vertical_scale",
                "float",
                1.0,
                1.0,
                10.0,
                "1",
                representation="value",
                precision=3,
                order=22,
                step=0.05,
                label_key="parameter.gnss_velocity_vertical_scale",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_velocity_vertical_scale",
                required=False,
            ),
            ParameterSpec(
                "gnss_reacquire_outage_ms",
                "int",
                300,
                100,
                10000,
                "ms",
                representation="value",
                precision=0,
                order=23,
                step=10,
                label_key="parameter.gnss_reacquire_outage_ms",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.gnss_reacquire_outage_ms",
                required=False,
            ),
            ParameterSpec(
                "baro_std_m",
                "float",
                5.0,
                1.5,
                1000.0,
                "m",
                representation="sigma",
                precision=6,
                order=13,
                step=0.01,
                label_key="parameter.baro_std_m",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.baro_std_m",
            ),
            ParameterSpec(
                "nis_1d_soft",
                "float",
                6.635,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=14,
                step=0.01,
                label_key="parameter.nis_1d_soft",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_1d_soft",
            ),
            ParameterSpec(
                "nis_1d_hard",
                "float",
                10.828,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=15,
                step=0.01,
                label_key="parameter.nis_1d_hard",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_1d_hard",
                greater_than="nis_1d_soft",
            ),
            ParameterSpec(
                "nis_2d_soft",
                "float",
                9.21,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=16,
                step=0.01,
                label_key="parameter.nis_2d_soft",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_2d_soft",
            ),
            ParameterSpec(
                "nis_2d_hard",
                "float",
                13.816,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=17,
                step=0.01,
                label_key="parameter.nis_2d_hard",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_2d_hard",
                greater_than="nis_2d_soft",
            ),
            ParameterSpec(
                "nis_3d_soft",
                "float",
                11.345,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=18,
                step=0.01,
                label_key="parameter.nis_3d_soft",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_3d_soft",
            ),
            ParameterSpec(
                "nis_3d_hard",
                "float",
                16.266,
                0.001,
                10000.0,
                "1",
                representation="value",
                precision=6,
                order=19,
                step=0.01,
                label_key="parameter.nis_3d_hard",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_3d_hard",
                greater_than="nis_3d_soft",
            ),
            ParameterSpec(
                "nis_max_r_scale",
                "float",
                10.0,
                1.0,
                1000.0,
                "1",
                representation="value",
                precision=6,
                order=20,
                step=0.01,
                label_key="parameter.nis_max_r_scale",
                group_key="parameter_group.consistency_gating",
                tooltip_key="parameter.tooltip.nis_max_r_scale",
            ),
            ParameterSpec(
                "gnss_position_measurement_delay_ms",
                "int",
                0,
                0,
                550,
                "ms",
                representation="value",
                precision=0,
                order=24,
                step=5,
                label_key="parameter.gnss_position_measurement_delay_ms",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_position_measurement_delay_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_velocity_measurement_delay_ms",
                "int",
                270,
                0,
                550,
                "ms",
                representation="value",
                precision=0,
                order=25,
                step=5,
                label_key="parameter.gnss_velocity_measurement_delay_ms",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.gnss_velocity_measurement_delay_ms",
                required=False,
            ),
            ParameterSpec(
                "baro_measurement_delay_ms",
                "int",
                0,
                0,
                550,
                "ms",
                representation="value",
                precision=0,
                order=26,
                step=5,
                label_key="parameter.baro_measurement_delay_ms",
                group_key="parameter_group.measurement_noise",
                tooltip_key="parameter.tooltip.baro_measurement_delay_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_enable",
                "int",
                1,
                0,
                1,
                "1",
                representation="value",
                precision=0,
                order=27,
                step=1,
                label_key="parameter.gnss_integrity_enable",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_enable",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_max_gap_ms",
                "int",
                120,
                40,
                1200,
                "ms",
                representation="value",
                precision=0,
                order=28,
                step=1,
                label_key="parameter.gnss_integrity_max_gap_ms",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_max_gap_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_error_threshold_m",
                "float",
                10.0,
                0.1,
                200.0,
                "m",
                representation="value",
                precision=3,
                order=29,
                step=0.01,
                label_key="parameter.gnss_integrity_error_threshold_m",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_error_threshold_m",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_recovery_threshold_m",
                "float",
                4.0,
                0.1,
                100.0,
                "m",
                representation="value",
                precision=3,
                order=30,
                step=0.01,
                label_key="parameter.gnss_integrity_recovery_threshold_m",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_recovery_threshold_m",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_suspect_duration_ms",
                "int",
                2000,
                100,
                30000,
                "ms",
                representation="value",
                precision=0,
                order=31,
                step=1,
                label_key="parameter.gnss_integrity_suspect_duration_ms",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_suspect_duration_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_reject_duration_ms",
                "int",
                5000,
                100,
                30000,
                "ms",
                representation="value",
                precision=0,
                order=32,
                step=1,
                label_key="parameter.gnss_integrity_reject_duration_ms",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_reject_duration_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_recovery_duration_ms",
                "int",
                8000,
                100,
                30000,
                "ms",
                representation="value",
                precision=0,
                order=33,
                step=1,
                label_key="parameter.gnss_integrity_recovery_duration_ms",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_recovery_duration_ms",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_position_r_scale",
                "float",
                4.0,
                1.0,
                100.0,
                "1",
                representation="value",
                precision=3,
                order=34,
                step=0.01,
                label_key="parameter.gnss_integrity_position_r_scale",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_position_r_scale",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_hacc_max_m",
                "float",
                6.0,
                0.1,
                100.0,
                "m",
                representation="value",
                precision=3,
                order=35,
                step=0.01,
                label_key="parameter.gnss_integrity_hacc_max_m",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_hacc_max_m",
                required=False,
            ),
            ParameterSpec(
                "gnss_integrity_sacc_max_mps",
                "float",
                1.2,
                0.01,
                20.0,
                "m/s",
                representation="value",
                precision=3,
                order=36,
                step=0.01,
                label_key="parameter.gnss_integrity_sacc_max_mps",
                group_key="parameter_group.gnss_integrity",
                tooltip_key="parameter.tooltip.gnss_integrity_sacc_max_mps",
                required=False,
            ),
        ),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        ),
        diagnostic_outputs=(
            "kf6.state",
            "kf6.covariance.diagonal",
            "kf6.covariance.upper_triangle",
            "kf6.innovation.position",
            "kf6.innovation.velocity",
            "kf6.innovation.baro",
            "kf6.nis.position",
            "kf6.nis.velocity",
            "kf6.nis.baro",
            "kf6.update_result",
            "kf6.measurement_attempt_mask",
            "kf6.measurement_r_scale",
            "kf6.measurement_r.position",
            "kf6.measurement_r.velocity",
            "kf6.measurement_r.baro",
        ),
        firmware_component_ids=("silverstar.algorithm.estimator.kf6",),
        recorded_output_roles=(
            "kf6.recorded.attitude.q_nb",
            "kf6.recorded.navigation.velocity_enu",
            "kf6.recorded.navigation.position_enu",
            "kf6.recorded.covariance.diagonal",
        ),
        required_semantic_roles=(
            "imu.corrected.accel_b",
            "imu.corrected.gyro_b",
        ),
        optional_semantic_roles=(
            "gnss.measurement.position_enu",
            "gnss.measurement.velocity_enu",
            "baro.measurement.relative_altitude",
            "kf6.recorded.navigation.position_enu",
        ),
        cadence_contract={
            "prediction": "recorded IMU/inertial-increment timestamps",
            "measurements": "event-driven; GNSS may legally have zero samples",
            "state_output": "one output per accepted prediction interval",
        },
        gap_tolerance_contract={
            "interpolation": "forbidden",
            "corrected_imu": "reset three-sample coning/sculling history",
            "measurements": "missing optional measurements do not block prediction",
        },
        parameter_source_contract={
            "recorded_configuration": "Firmware build configuration from .ssdecoder",
            "offline": "plugin defaults or explicit what-if values",
        },
        coordinate_frame_contract={
            "quaternion_order": "WXYZ",
            "quaternion_convention": "Hamilton body-to-ENU",
            "state_order": "pE,pN,pU,vE,vN,vU",
            "navigation_frame": "ENU",
        },
        estimator_visualization=EstimatorVisualizationSpec(
            navigation_health_channel="kf6.navigation_health",
            state_groups=(
                StateGroupSpec(
                    "position",
                    "state.position",
                    ("E", "N", "U"),
                    "m",
                    "kf6.covariance.diagonal",
                    (0, 1, 2),
                    file_stem="Position",
                ),
                StateGroupSpec(
                    "velocity",
                    "state.velocity",
                    ("E", "N", "U"),
                    "m/s",
                    "kf6.covariance.diagonal",
                    (3, 4, 5),
                    file_stem="Velocity",
                ),
            ),
            measurement_groups=(
                *(
                    MeasurementGroupSpec(
                        group_id,
                        label_key,
                        dimension,
                        components,
                        innovation,
                        f"kf6.nis.{group_id.removeprefix('gnss_')}",
                        f"kf6.update_result.{group_id.removeprefix('gnss_')}",
                        f"kf6.measurement_r_scale.{group_id.removeprefix('gnss_')}",
                        measurement_age_channel=f"kf6.measurement_receive_age.{group_id.removeprefix('gnss_')}",
                        fixed_lag_latency_channel=f"kf6.measurement_fixed_lag_latency.{group_id.removeprefix('gnss_')}",
                        measurement_uncertainty_channel=f"kf6.measurement_input_variance.{group_id.removeprefix('gnss_')}",
                        effective_r_channel=f"kf6.measurement_effective_variance.{group_id.removeprefix('gnss_')}",
                        r_scale_index=0,
                        attempt_mask_channel="",
                        attempt_mask_bit=0,
                        soft_threshold_parameter_id=soft,
                        hard_threshold_parameter_id=hard,
                        unit=unit,
                        file_stem=stem,
                        configuration_fields=("configured_gnss_rate_hz",),
                        measurement_record_names=("GNSS_MEASUREMENT",),
                        measurement_validity_channel=validity,
                    )
                    for (
                        group_id,
                        label_key,
                        dimension,
                        components,
                        innovation,
                        scale_index,
                        soft,
                        hard,
                        unit,
                        stem,
                        validity,
                    ) in (
                        (
                            "gnss_position_en",
                            "measurement.gnss_position_en",
                            2,
                            ("E", "N"),
                            "kf6.innovation.position_en",
                            0,
                            "nis_2d_soft",
                            "nis_2d_hard",
                            "m",
                            "GNSS_Position_EN",
                            "gnss.measurement.position_enu",
                        ),
                        (
                            "gnss_position_u",
                            "measurement.gnss_position_u",
                            1,
                            ("U",),
                            "kf6.innovation.position_u",
                            0,
                            "nis_1d_soft",
                            "nis_1d_hard",
                            "m",
                            "GNSS_Position_U",
                            "gnss.measurement.position_enu",
                        ),
                        (
                            "gnss_velocity_en",
                            "measurement.gnss_velocity_en",
                            2,
                            ("E", "N"),
                            "kf6.innovation.velocity_en",
                            1,
                            "nis_2d_soft",
                            "nis_2d_hard",
                            "m/s",
                            "GNSS_Velocity_EN",
                            "gnss.measurement.velocity_enu",
                        ),
                        (
                            "gnss_velocity_u",
                            "measurement.gnss_velocity_u",
                            1,
                            ("U",),
                            "kf6.innovation.velocity_u",
                            1,
                            "nis_1d_soft",
                            "nis_1d_hard",
                            "m/s",
                            "GNSS_Velocity_U",
                            "gnss.measurement.velocity_enu",
                        ),
                    )
                ),
                MeasurementGroupSpec(
                    "barometric_altitude",
                    "measurement.barometric_altitude",
                    1,
                    ("Baro",),
                    "kf6.innovation.baro",
                    "kf6.nis.baro",
                    "kf6.update_result",
                    "kf6.measurement_r_scale.baro",
                    measurement_age_channel="kf6.measurement_receive_age.baro",
                    fixed_lag_latency_channel="kf6.measurement_fixed_lag_latency.baro",
                    measurement_uncertainty_channel="kf6.measurement_input_variance.baro",
                    effective_r_channel="kf6.measurement_effective_variance.baro",
                    update_result_index=2,
                    r_scale_index=0,
                    attempt_mask_channel="kf6.measurement_attempt_mask",
                    attempt_mask_bit=0x04,
                    soft_threshold_parameter_id="nis_1d_soft",
                    hard_threshold_parameter_id="nis_1d_hard",
                    unit="m",
                    file_stem="Barometer",
                    configuration_fields=("configured_barometer_rate_hz",),
                    measurement_record_names=("BARO_MEASUREMENT",),
                    measurement_validity_channel="baro.measurement.relative_altitude",
                ),
            ),
            full_covariance=FullCovarianceSpec(
                channel_id="kf6.covariance.upper_triangle",
                file_stem="KF6_Full_P_Keyframes",
                state_symbols=("pE", "pN", "pU", "vE", "vN", "vU"),
                state_units=("m", "m", "m", "m/s", "m/s", "m/s"),
                initial_record_name="INITIAL_STATE",
                initial_diagonal_field="p0_diagonal",
            ),
        ),
    )

    def ParameterSchemaCompatible_Is(self, identity: str) -> bool:
        if super().ParameterSchemaCompatible_Is(identity):
            return True
        legacy = replace(
            self.metadata,
            parameter_schema=tuple(
                spec
                for spec in self.metadata.parameter_schema
                if spec.parameter_id
                not in {"gnss_reacquire_outage_ms", "gnss_velocity_vertical_scale"}
            ),
        )
        return identity == legacy.ParameterSchemaIdentity_Get()

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
        if not dataset.Records_Get("SYSTEM_CONFIG"):
            missing.append("SYSTEM_CONFIG")
        if source == SOURCE_RECORDED_INCREMENT:
            if not dataset.Records_Get("INERTIAL_INCREMENT"):
                missing.append("INERTIAL_INCREMENT")
            if config["inertial_increment_decimation"] not in (None, 1):
                missing.append("INERTIAL_INCREMENT(decimation=1)")
        elif source == SOURCE_CORRECTED_IMU:
            if not dataset.Records_Get("IMU_CORRECTED"):
                missing.append("IMU_CORRECTED")
            if config["imu_corrected_decimation"] not in (None, 1):
                missing.append("IMU_CORRECTED(decimation=1)")
        else:
            missing.append(f"unsupported_input_source:{source}")
        if config["subsample_count"] != 2:
            missing.append("mechanization_subsample_count=2")
        if (
            dataset.semantic_context is not None
            and dataset.semantic_context.FirmwareVersion_Get() == "0.0.10"
        ):
            if not dataset.Records_Get("ESTIMATOR_STEP"):
                missing.append("ESTIMATOR_STEP")
            if not dataset.Records_Get("INERTIAL_INCREMENT"):
                missing.append("INERTIAL_INCREMENT")
        if missing:
            return AlgorithmAvailability(
                False,
                ReplayFidelity.UNAVAILABLE,
                tuple(missing),
                tuple(warnings),
                tuple(supported),
            )
        fidelity = ReplayFidelity.EXACT
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
        if dataset.data_quality is not None and (dataset.data_quality.status.value == "warnings"):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("source_log_has_integrity_or_sequence_gaps")
        return AlgorithmAvailability(True, fidelity, (), tuple(warnings), tuple(supported))

    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
        *,
        velocity_shift_ms: int | None = None,
        analysis_legacy_reacquisition: bool = False,
        analysis_frozen_initial: bool = False,
        analysis_options: Kf6DiagnosticOptions | None = None,
    ) -> AlgorithmResult:
        if analysis_options is not None:
            if not isinstance(analysis_options, Kf6DiagnosticOptions):
                raise TypeError("kf6_diagnostic_options_invalid")
            analysis_frozen_initial = True
            if velocity_shift_ms is None and analysis_options.velocity_shift_ms:
                velocity_shift_ms = analysis_options.velocity_shift_ms
        task_context = context or TaskContext()
        if request.quality_policy_revision not in (None, *self.metadata.what_if_quality_revisions):
            raise ValueError("quality_policy_revision_unsupported")
        availability = self.availability(dataset, request.input_source)
        if not availability.available:
            raise ValueError("replay_unavailable:" + ",".join(availability.missing_inputs))
        initial = dataset.initial_state
        if initial is None:
            raise ValueError("replay_initial_state_missing")
        system_config = dataset.RecordAtOrBefore_Get(
            "SYSTEM_CONFIG",
            dataset.start_timestamp_us or initial.timestamp_us,
        )
        if system_config is None:
            raise ValueError("replay_system_config_missing")
        start_timestamp = dataset.start_timestamp_us or initial.timestamp_us
        mechanism_config = Mechanization_ConfigurationGet(dataset)
        mission_bounds = MissionReplayBounds_Get(dataset)
        replay_input_end = (
            mission_bounds.end_timestamp_us
            if mission_bounds.end_reason == MissionReplayEndReason.LANDING
            else None
        )
        if request.input_source == SOURCE_CORRECTED_IMU:
            increments, build_diagnostics = InertialIncrement_BuildFromCorrectedImu(
                dataset.Records_Get("IMU_CORRECTED"),
                start_timestamp_us=start_timestamp,
                end_timestamp_us=replay_input_end,
                minimum_sample_rate_hz=mechanism_config["minimum_sample_rate_hz"],
                maximum_sample_rate_hz=mechanism_config["maximum_sample_rate_hz"],
            )
            source_diagnostics: dict[str, Any] = {
                "invalid_sample_count": build_diagnostics.invalid_sample_count,
                "sample_gap_count": build_diagnostics.sample_gap_count,
            }
        else:
            increments = InertialIncrement_ReadRecorded(
                dataset.Records_Get("INERTIAL_INCREMENT"),
                start_timestamp_us=start_timestamp,
                end_timestamp_us=replay_input_end,
            )
            source_diagnostics = {}
        if dataset.Records_Get("ESTIMATOR_STEP"):
            from silverstar_flp.plugins.algorithms.kf6.mechanization_verification import (
                Mechanization_Verify,
            )

            source_diagnostics["mechanization_verification"] = Mechanization_Verify(
                dataset, start_timestamp, replay_input_end
            )
            increments = InertialIncrement_ReadRecorded(
                dataset.Records_Get("INERTIAL_INCREMENT"),
                start_timestamp_us=start_timestamp,
                end_timestamp_us=replay_input_end,
            )
        if not increments:
            raise ValueError("replay_no_valid_inertial_increment")
        if mission_bounds.end_reason == MissionReplayEndReason.SOURCE_END:
            mission_bounds = MissionReplayBounds_Get(
                dataset,
                source_end_timestamp_us=increments[-1].interval_end_timestamp_us,
            )
        parameters = self._Parameters_Resolve(dataset, request)
        filter_instance = Kf6Filter.Kf6_Create(
            gnss_reacquire_outage_ms=parameters.get("gnss_reacquire_outage_ms", 300),
            process_accel_std_mps2=np.asarray(
                (
                    parameters["process_accel_std_e"],
                    parameters["process_accel_std_n"],
                    parameters["process_accel_std_u"],
                ),
                dtype=np.float32,
            ),
            p0_diagonal=self._P0_Resolve(dataset, parameters),
            initial_velocity_enu_mps=np.asarray(
                initial.payload["initial_velocity_enu_mps"], dtype=np.float32
            ),
            nis_soft_threshold=np.asarray(
                (
                    parameters["nis_1d_soft"],
                    parameters["nis_2d_soft"],
                    parameters["nis_3d_soft"],
                ),
                dtype=np.float32,
            ),
            nis_hard_threshold=np.asarray(
                (
                    parameters["nis_1d_hard"],
                    parameters["nis_2d_hard"],
                    parameters["nis_3d_hard"],
                ),
                dtype=np.float32,
            ),
            nis_max_r_scale=parameters["nis_max_r_scale"],
        )
        q_nb = Quaternion_Normalize(np.asarray(initial.payload["q_nb"], dtype=np.float32))
        schedule, schedule_inferred = self._MeasurementSchedule_Build(dataset, increments)
        filter_instance.outage_required = not analysis_legacy_reacquisition
        schedule = self._MeasurementParameters_Apply(
            dataset, schedule, parameters, frozen_initial=analysis_frozen_initial
        )
        metadata = dataset.semantic_context.raw_metadata if dataset.semantic_context else {}
        quality_revision = (
            metadata.get("metadata_declarations", {})
            .get("navigation_replay", {})
            .get("gnss_integrity_revision", 0)
        )
        if request.quality_policy_revision is not None:
            quality_revision = request.quality_policy_revision
        filter_instance.require_effective_gain = quality_revision == 3
        source_diagnostics["quality_policy_revision"] = quality_revision
        source_diagnostics["quality_policy_override"] = request.quality_policy_revision
        if request.quality_policy_revision is not None:
            source_diagnostics["counterfactual_timing_scope"] = (
                "recorded operations and resolved times retained; absent old operations "
                "cannot be recovered from logs and are not fabricated"
            )
        if parameters.get("gnss_integrity_enable", 0) or quality_revision == 3:
            schedule, integrity_diagnostics = self._IntegritySchedule_Apply(
                dataset, schedule, parameters, revision_override=quality_revision
            )
            source_diagnostics["gnss_integrity"] = integrity_diagnostics
            if quality_revision == 3:
                source_diagnostics["window_evidence"] = integrity_diagnostics["window_evidence"]
        firmware_schedule = schedule
        schedule = DiagnosticSchedule_Apply(schedule, analysis_options)
        filter_instance.analysis_position_vertical_disabled = bool(
            analysis_options and analysis_options.gnss_position_vertical_disabled
        )
        if velocity_shift_ms is not None:
            from silverstar_flp.plugins.algorithms.kf6.field_analysis import VelocitySchedule_Shift

            schedule = VelocitySchedule_Shift(schedule, velocity_shift_ms)
        weights = MeasurementWeights_Inspect(
            dataset, parameters, firmware_schedule, schedule, analysis_options
        )
        diagnostic_metadata = DiagnosticMetadata_Get(dataset, parameters, analysis_options, weights)
        if (
            velocity_shift_ms is not None
            or analysis_legacy_reacquisition
            or analysis_frozen_initial
        ):
            diagnostic_metadata["mode"] = "analysis_only"
            diagnostic_metadata["analysis_only_overrides"]["velocity_shift_ms"] = (
                velocity_shift_ms or 0
            )
            diagnostic_metadata["legacy_velocity_shift_ms"] = velocity_shift_ms
            diagnostic_metadata["legacy_reacquisition"] = analysis_legacy_reacquisition
            diagnostic_metadata["initial_state_frozen"] = analysis_frozen_initial
        task_context.Progress_Report(0.08, "replay.inputs")
        if dataset.Records_Get("ESTIMATOR_STEP"):
            from silverstar_flp.plugins.algorithms.kf6.fixed_lag import Faithful_Run
            from silverstar_flp.plugins.algorithms.kf6.measurement_time import (
                MeasurementDelays_Apply,
            )

            schedule = MeasurementDelays_Apply(
                dataset, schedule, parameters, self.recorded_parameters(dataset)
            )
            replaced_records = dict(dataset.records)
            for kind in ("GNSS_MEASUREMENT", "BARO_MEASUREMENT"):
                replaced_records[kind] = tuple(
                    item.record for item in schedule if item.record.record_name == kind
                )
            replay_dataset = replace(dataset, records=replaced_records)
            snapshots, filter_instance, timing_diagnostics = Faithful_Run(
                replay_dataset,
                filter_instance,
                q_nb,
                increments,
                parameters,
                task_context,
            )
            source_diagnostics.update(timing_diagnostics)
        else:
            measurement_events: list[dict[str, object]] = []
            snapshots = self._Replay_Run(
                filter_instance,
                q_nb,
                increments,
                schedule,
                parameters,
                task_context,
                measurement_events,
            )
            source_diagnostics["measurement_events"] = measurement_events
        if not snapshots:
            raise ValueError("replay_no_valid_kf6_output")
        warnings = list(availability.warnings)
        if source_diagnostics.get("gnss_integrity", {}).get("gnss_available") is False:
            warnings.append("gnss_unavailable")
        fidelity = availability.fidelity
        if quality_revision == 3:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("revision3_cross_validation_scope_limited")
        state_decimation = tuple(system_config.payload.get("log_decimation", ()))
        if schedule_inferred:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("measurement_application_time_inferred")
        elif len(state_decimation) > 7 and int(state_decimation[7]) != 1 and schedule:
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("kf6_state_timing_reference_is_decimated")
        if source_diagnostics.get("sample_gap_count", 0):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("input_sample_gaps_detected")
        if (
            velocity_shift_ms is not None
            or analysis_legacy_reacquisition
            or analysis_frozen_initial
        ):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("kf6_offline_field_analysis")
        if "gnss_reacquire_outage_ms" not in parameters and dataset.Records_Get("GNSS_MEASUREMENT"):
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("kf6_reacquisition_policy_changed")
        channels = self._Channels_Build(snapshots)
        from silverstar_flp.analysis.measurement_diagnostics import (
            RecomputedMeasurementChannels_Build,
        )

        channels.update(
            RecomputedMeasurementChannels_Build(source_diagnostics.get("measurement_events", ()))
        )
        if quality_revision == 3:
            from silverstar_flp.analysis.navigation_revision3 import Revision3Health_Build

            channels["kf6.navigation_health"], health_diagnostics = Revision3Health_Build(
                channels["navigation.position_enu"].timestamp_us,
                source_diagnostics.get("gnss_group_updates", ()),
                source_diagnostics.get("measurement_events", ()),
                start_timestamp,
            )
            source_diagnostics.update(health_diagnostics)
        for channel_id in ("navigation.position_enu", "navigation.velocity_enu"):
            series = channels[channel_id]
            channels[channel_id] = replace(
                series,
                metadata={
                    **series.metadata,
                    "discontinuity_timestamps_us": source_diagnostics.get(
                        "reanchor_timestamps_us", ()
                    ),
                },
            )
        task_context.Progress_Report(1.0, "replay.complete")
        if dataset.Records_Get("ESTIMATOR_STEP"):
            # Numerical Golden coverage is reported explicitly, not inferred from version.
            fidelity = ReplayFidelity.APPROXIMATE
            warnings.append("fixed_lag_cross_validation_scope_limited")
        return AlgorithmResult(
            algorithm_id=self.metadata.plugin_id,
            algorithm_version=self.metadata.version,
            input_source=(
                SOURCE_RECORDED_INCREMENT
                if dataset.Records_Get("ESTIMATOR_STEP")
                else request.input_source
            ),
            parameters=parameters,
            fidelity=fidelity,
            missing_inputs=(),
            warnings=tuple(dict.fromkeys(warnings)),
            channels=channels,
            diagnostics={
                **self.ParameterAudit_Get(dataset, request),
                "offline_diagnostics": diagnostic_metadata,
                "state_order": ("pE", "pN", "pU", "vE", "vN", "vU"),
                "input_increment_count": len(increments),
                "measurement_count": len(schedule),
                "output_count": len(snapshots),
                "mission_end_timestamp_us": mission_bounds.end_timestamp_us,
                "mission_end_reason": mission_bounds.end_reason.value,
                "predict_count": filter_instance.predict_count,
                "health_flags": filter_instance.health_flags,
                "gnss_group_results": filter_instance.gnss_result_counts,
                "gnss_group_nis": [
                    {
                        "count": len(values),
                        "max": max(values) if values else None,
                        "p50_p90_p95_p99": np.percentile(values, [50, 90, 95, 99]).tolist()
                        if values
                        else None,
                    }
                    for values in filter_instance.gnss_nis_samples
                ],
                "inflation_counts": filter_instance.inflation_counts,
                "velocity_shift_ms": velocity_shift_ms,
                "analysis_legacy_reacquisition": analysis_legacy_reacquisition,
                "analysis_frozen_initial": analysis_frozen_initial,
                "compatibility_defaults": {
                    name: value
                    for name, value in (
                        ("gnss_reacquire_outage_ms", 300),
                        ("gnss_velocity_vertical_scale", 1.0),
                    )
                    if name not in parameters
                },
                "reacquire_count": filter_instance.reacquire_count,
                "reacquire_active_mask": filter_instance.reacquire_active_mask,
                "last_inflation_group": filter_instance.last_inflation_group,
                "last_inflation_factor": filter_instance.last_inflation_factor,
                **filter_instance.counters,
                **source_diagnostics,
            },
            provenance=(
                "Analysis-only"
                if diagnostic_metadata["mode"] == "analysis_only"
                else "What-if"
                if request.mode == ReplayMode.WHAT_IF
                else (
                    "Offline"
                    if request.mode == ReplayMode.OFFLINE
                    else "Recomputed from recorded configuration"
                )
            ),
        )

    def recorded_parameters(self, dataset: FlightDataset) -> Mapping[str, Any]:
        metadata = dataset.semantic_context.raw_metadata if dataset.semantic_context else {}
        revision = (
            metadata.get("metadata_declarations", {})
            .get("navigation_replay", {})
            .get("gnss_integrity_revision", 0)
        )
        if revision != 0:
            return super().recorded_parameters(dataset)
        if dataset.semantic_context is None or not self.FirmwareMember_Is(dataset):
            return {}
        records = dataset.semantic_context.FirmwareParameters_Get(
            self.metadata.firmware_component_ids[0]
        )
        if records is None:
            return {}
        specs = {spec.parameter_id: spec for spec in self.metadata.parameter_schema}
        values = {}
        for name, item in records.items():
            if name.startswith("gnss_integrity_"):
                continue
            if name not in specs:
                raise ValueError(f"parameter_unknown:{name}")
            spec = specs[name]
            if item["unit"] != spec.unit or item["representation"] != spec.representation:
                raise ValueError(f"parameter_contract_mismatch:{name}")
            spec.Value_Validate(item["value"])
            values[name] = item["value"]
        return values

    def _Parameters_Resolve(
        self, dataset: FlightDataset, request: ReplayRequest
    ) -> dict[str, float]:
        parameters = self.Parameters_Resolve(dataset, request)
        metadata = (
            dataset.semantic_context.raw_metadata if dataset.semantic_context is not None else {}
        )
        revision = (
            metadata.get("metadata_declarations", {})
            .get("navigation_replay", {})
            .get("gnss_integrity_revision", 0)
        )
        if revision == 1:
            raise ValueError("gnss_integrity_revision_1_legacy_candidate_unsupported")
        if revision not in (0, 2, 3):
            raise ValueError("gnss_integrity_revision_unsupported")
        revision = request.quality_policy_revision or revision
        if revision == 3:
            for name, value in self.OfflineParameters_Get().items():
                if name.startswith("gnss_integrity_"):
                    parameters.setdefault(name, value)
            runtime = {p.parameter_id: p for p in self.RuntimeParameterSchema_Get(dataset, 3)}
            baseline = {**self.OfflineParameters_Get(), **self.recorded_parameters(dataset)}
            for name, value in request.parameters.items():
                if name not in runtime and value != baseline.get(name):
                    raise ValueError(f"parameter_retired_revision3:{name}")
            for name, spec in runtime.items():
                spec.Value_Validate(parameters[name])
        if revision == 0:
            for name, default in self.OfflineParameters_Get().items():
                if name.startswith("gnss_integrity_"):
                    parameters.setdefault(name, default)
            if "gnss_integrity_enable" not in request.parameters:
                parameters["gnss_integrity_enable"] = 0
        if revision != 3 and (
            parameters["gnss_integrity_recovery_threshold_m"]
            >= parameters["gnss_integrity_error_threshold_m"]
        ):
            raise ValueError("gnss_integrity_threshold_order_invalid")
        for dimension in ("1d", "2d", "3d"):
            if parameters[f"nis_{dimension}_hard"] <= parameters[f"nis_{dimension}_soft"]:
                raise ValueError("nis_threshold_order_invalid")
        return parameters

    def RuntimeParameterSchema_Get(self, dataset, quality_policy_revision=None):
        from dataclasses import replace

        metadata = (
            dataset.semantic_context.raw_metadata if dataset and dataset.semantic_context else {}
        )
        revision = quality_policy_revision or metadata.get("metadata_declarations", {}).get(
            "navigation_replay", {}
        ).get("gnss_integrity_revision", 0)
        if revision != 3:
            return self.metadata.parameter_schema
        retired = {
            "gnss_integrity_" + suffix
            for suffix in (
                "recovery_threshold_m",
                "suspect_duration_ms",
                "reject_duration_ms",
                "recovery_duration_ms",
                "hacc_max_m",
                "sacc_max_mps",
            )
        }
        return tuple(
            replace(p, maximum=4.0) if p.parameter_id == "gnss_integrity_position_r_scale" else p
            for p in self.metadata.parameter_schema
            if p.parameter_id not in retired
        )

    def ParameterAudit_Get(self, dataset, request):
        audit = super().ParameterAudit_Get(dataset, request)
        runtime = self.RuntimeParameterSchema_Get(dataset, request.quality_policy_revision)
        active = {p.parameter_id for p in runtime}
        audit["retired_parameter_ids"] = [
            p.parameter_id for p in self.metadata.parameter_schema if p.parameter_id not in active
        ]
        audit["actual_effective_parameter_ids"] = sorted(active)
        return audit

    def _P0_Resolve(self, dataset: FlightDataset, parameters: Mapping[str, float]) -> np.ndarray:
        recorded = self.recorded_parameters(dataset)
        baseline = recorded or self.OfflineParameters_Get()
        initial = np.asarray(dataset.initial_state.payload["p0_diagonal"], dtype=np.float32)
        names = tuple(f"p0_{group}_{axis}" for group in ("position", "velocity") for axis in "enu")
        result = initial.copy()
        for index, name in enumerate(names):
            before, after = (
                np.float32(baseline.get(name, self.OfflineParameters_Get()[name])),
                np.float32(parameters[name]),
            )
            if before == after:
                continue
            if not int(dataset.initial_state.payload.get("origin_valid_flags", 0)) & 1:
                result[index] = after
            else:
                if after < before and initial[index] <= before:
                    raise ValueError(f"parameter_dynamic_uncertainty_missing:{name}")
                result[index] = max(initial[index], after)
        return result

    def _IntegritySchedule_Apply(
        self,
        dataset: FlightDataset,
        schedule: tuple[_ScheduledMeasurement, ...],
        parameters: Mapping[str, float],
        *,
        revision_override: int | None = None,
    ) -> tuple[tuple[_ScheduledMeasurement, ...], dict[str, object]]:
        from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build

        metadata = dataset.semantic_context.raw_metadata if dataset.semantic_context else {}
        revision = (
            metadata.get("metadata_declarations", {})
            .get("navigation_replay", {})
            .get("gnss_integrity_revision", 0)
        )
        if revision_override is not None:
            revision = revision_override
        if revision == 3:
            from silverstar_flp.analysis.navigation_revision3 import QualitySchedule_Apply

            return QualitySchedule_Apply(dataset, schedule, parameters)
        from silverstar_flp.analysis.gnss_replay_availability import GnssUnavailableSchedule_Get

        unavailable = GnssUnavailableSchedule_Get(dataset, schedule, revision)
        if unavailable is not None:
            return unavailable
        selected = GnssIntegrityStream_Build(dataset, parameters, consumed_only=True)
        recorded_parameters = self.recorded_parameters(dataset)
        baseline = recorded_parameters or self.OfflineParameters_Get()
        old = (
            GnssIntegrityStream_Build(dataset, baseline, consumed_only=True)
            if revision == 2
            else None
        )
        noise_recomputed = any(
            np.float32(parameters[name]) != np.float32(baseline.get(name, parameters[name]))
            for name in ("gnss_position_std_horizontal", "gnss_position_std_vertical")
        )
        changed = []
        native_by_key = {
            (int(r.payload["sequence"]), int(r.payload["receive_timestamp_us"])): r
            for r in dataset.Records_Get("GNSS_NATIVE")
        }
        mask_mismatches = 0
        r_mismatches = 0
        position_disabled_count = 0
        for item in schedule:
            if item.kind != "gnss":
                changed.append(item)
                continue
            payload = dict(item.record.payload)
            key = (int(payload["sequence"]), int(payload["receive_timestamp_us"]))
            decision = selected.by_measurement.get(key)
            if decision is None:
                raise ValueError("gnss_integrity_native_evidence_missing")
            logged_mask = int(payload["valid_group_mask"])
            baseline_decision = old.by_measurement.get(key) if old else None
            native_mask = baseline_decision.admitted_mask if baseline_decision else logged_mask
            # The receiver's raw four-group mask is restored from GNSS_NATIVE below.
            native_record = native_by_key.get(key)
            if native_record is None:
                raise ValueError("gnss_integrity_native_evidence_missing")
            native_mask = int(native_record.payload.get("valid_group_mask", native_mask))
            base = np.asarray(payload["position_variance_m2"], dtype=np.float32).copy()
            if baseline_decision and not noise_recomputed:
                base[:2] /= np.float32(baseline_decision.position_r_scale)
            if revision == 2 and baseline_decision:
                if logged_mask != baseline_decision.admitted_mask:
                    mask_mismatches += 1
                expected = base[:2] * np.float32(baseline_decision.position_r_scale)
                recorded = np.asarray(payload["position_variance_m2"][:2], dtype=np.float32)
                if not np.allclose(expected, recorded, rtol=1e-5, atol=1e-5):
                    r_mismatches += 1
            base[:2] *= np.float32(decision.position_r_scale)
            payload["position_variance_m2"] = tuple(float(x) for x in base)
            payload["_integrity_native_valid_group_mask"] = native_mask
            payload["valid_group_mask"] = decision.admitted_mask & native_mask
            if (native_mask & 1) and not (decision.admitted_mask & 1):
                position_disabled_count += 1
            payload["_integrity_state"] = decision.state
            changed.append(replace(item, record=replace(item.record, payload=payload)))
        diagnostics = {
            "revision": 2,
            "state_counts": tuple(
                sum(d.state == state for d in selected.decisions) for state in range(3)
            ),
            "transitions": tuple(
                (d.timestamp_us, d.previous_state, d.state, d.reason, d.sequence)
                for d in selected.decisions
                if d.state != d.previous_state
            ),
            "position_disabled_count": position_disabled_count,
            "recorded_mask_mismatches": mask_mismatches,
            "recorded_r_mismatches": r_mismatches,
        }
        return tuple(changed), diagnostics

    def _MeasurementParameters_Apply(
        self,
        dataset: FlightDataset,
        schedule: tuple[_ScheduledMeasurement, ...],
        parameters: Mapping[str, float],
        *,
        frozen_initial: bool = False,
    ) -> tuple[_ScheduledMeasurement, ...]:
        baseline = self.recorded_parameters(dataset) or self.OfflineParameters_Get()
        changed = {
            name
            for name in parameters
            if np.float32(parameters[name])
            != np.float32(baseline.get(name, self.OfflineParameters_Get()[name]))
        }
        position_names = {"gnss_position_std_horizontal", "gnss_position_std_vertical"}
        gnss_names = position_names | {"gnss_velocity_std", "gnss_velocity_vertical_scale"}
        if not changed & (gnss_names | {"baro_std_m"}):
            return schedule
        initial = dataset.initial_state.payload
        if (
            not frozen_initial
            and changed & gnss_names
            and int(initial.get("origin_valid_flags", 0)) & 1
        ):
            # Frozen GNSS initialization has already used the selected floors. The
            # logged aggregate is insufficient to repeat its pre-START averaging.
            raise ValueError("parameter_dynamic_uncertainty_missing:GNSS_initialization")
        native_records = {}
        for kind in ("GNSS_NATIVE", "BARO_NATIVE"):
            context = dataset.semantic_context
            capability = "barometer.altitude" if kind == "BARO_NATIVE" else "gnss.position"
            if kind == "GNSS_NATIVE" and not changed & position_names:
                capability = "gnss.velocity"
            route = context.CanonicalRoute_Get("canonical:" + capability) if context else None
            endpoints = route.get("endpoint_descriptor_ids", ()) if route else ()
            if len(endpoints) != 1:
                continue
            endpoint = context.CapabilityEndpoint_Get(endpoints[0])
            for record in dataset.Records_Get(kind):
                if record.payload.get("source_descriptor_id") != endpoints[0]:
                    continue
                if endpoint and record.payload.get("instance_id") != endpoint.get("instance_id"):
                    continue
                key = (
                    kind,
                    record.payload.get("sample_timestamp_us"),
                    record.payload.get("sequence"),
                )
                native_records.setdefault(key, []).append(record)
        result = []
        for item in schedule:
            record = item.record
            is_gnss = record.record_name == "GNSS_MEASUREMENT"
            relevant = gnss_names if is_gnss else {"baro_std_m"}
            if not changed & relevant:
                result.append(item)
                continue
            kind = "GNSS_NATIVE" if is_gnss else "BARO_NATIVE"
            key = (kind, record.payload.get("sample_timestamp_us"), record.payload.get("sequence"))
            matches = native_records.get(key, ())
            if len(matches) != 1:
                raise ValueError(f"parameter_dynamic_uncertainty_missing:{kind}")
            native = matches[0].payload
            payload = dict(record.payload)
            try:
                if is_gnss:
                    if changed & position_names:
                        origin = np.asarray(initial["gnss_origin_position_std_m"], dtype=np.float32)
                        sigma = np.asarray(
                            (
                                native["horizontal_accuracy_m"],
                                native["horizontal_accuracy_m"],
                                native["vertical_accuracy_m"],
                            ),
                            dtype=np.float32,
                        )
                        floors = np.asarray(
                            (
                                parameters["gnss_position_std_horizontal"],
                                parameters["gnss_position_std_horizontal"],
                                parameters["gnss_position_std_vertical"],
                            ),
                            dtype=np.float32,
                        )
                        sigma = np.maximum(sigma * np.float32(1.25), floors)
                        payload["position_variance_m2"] = tuple(sigma * sigma + origin * origin)
                    if changed & {"gnss_velocity_std", "gnss_velocity_vertical_scale"}:
                        sigma = np.sqrt(
                            np.maximum(
                                np.asarray(native["velocity_variance_m2ps2"], dtype=np.float32), 0
                            )
                        )
                        sigma = np.maximum(
                            sigma * np.float32(1.25), np.float32(parameters["gnss_velocity_std"])
                        )
                        sigma[2] *= np.float32(parameters.get("gnss_velocity_vertical_scale", 1.0))
                        payload["velocity_variance_m2ps2"] = tuple(sigma * sigma)
                else:
                    sigma = np.float32(parameters["baro_std_m"])
                    origin = np.float32(initial["barometer_origin_std_m"])
                    payload["variance_m2"] = float(
                        max(np.float32(native["altitude_variance_m2"]), sigma * sigma)
                        + origin * origin
                    )
                numeric = (
                    (payload["position_variance_m2"], payload["velocity_variance_m2ps2"])
                    if is_gnss
                    else (payload["variance_m2"],)
                )
                if any(
                    not np.isfinite(value).all() or np.any(np.asarray(value) < 0)
                    for value in numeric
                ):
                    raise ValueError("invalid uncertainty")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"parameter_dynamic_uncertainty_missing:{kind}") from exc
            # Only the R inputs change: sample/application time, order, measurements,
            # validity and source identity are preserved in immutable copies.
            result.append(replace(item, record=replace(record, payload=payload)))
        return tuple(result)

    @staticmethod
    def _MeasurementSchedule_Build(
        dataset: FlightDataset, increments: tuple[InertialIncrement, ...]
    ) -> tuple[tuple[_ScheduledMeasurement, ...], bool]:
        if not increments:
            return (), False
        if dataset.Records_Get("ESTIMATOR_STEP"):
            exact = tuple(
                _ScheduledMeasurement(
                    int(record.payload["estimator_present_timestamp_us"]),
                    int(
                        record.payload[
                            "receive_operation_sequence" if kind == "gnss" else "operation_sequence"
                        ]
                    ),
                    kind,
                    record,
                    False,
                )
                for kind, name in (("gnss", "GNSS_MEASUREMENT"), ("baro", "BARO_MEASUREMENT"))
                for record in dataset.Records_Get(name)
                if int(record.payload["estimator_present_timestamp_us"])
                <= increments[-1].interval_end_timestamp_us
            )
            return tuple(sorted(exact, key=lambda item: item.source_order)), False
        increment_timestamps = [item.interval_end_timestamp_us for item in increments]
        scheduled: list[_ScheduledMeasurement] = []
        for kind, records in (
            ("gnss", dataset.Records_Get("GNSS_MEASUREMENT")),
            ("baro", dataset.Records_Get("BARO_MEASUREMENT")),
        ):
            for record in records:
                # The adapters preserve device sample and host receive time. A sample
                # cannot be used before receipt, nor before its sample time (the
                # firmware rejects future samples). ESTIMATOR is a decimated snapshot,
                # not evidence that a referenced sequence was first applied there.
                available_timestamp = max(
                    int(record.payload["sample_timestamp_us"]),
                    int(record.payload["receive_timestamp_us"]),
                )
                index = bisect_left(increment_timestamps, available_timestamp)
                if index >= len(increment_timestamps):
                    continue
                scheduled.append(
                    _ScheduledMeasurement(
                        application_timestamp_us=increment_timestamps[index],
                        source_order=record.record_sequence,
                        kind=kind,
                        record=record,
                        inferred=True,
                    )
                )
        scheduled.sort(
            key=lambda item: (
                item.application_timestamp_us,
                0 if item.kind == "gnss" else 1,
                item.source_order,
            )
        )
        return tuple(scheduled), bool(scheduled)

    def _Replay_Run(
        self,
        filter_instance: Kf6Filter,
        initial_q_nb: np.ndarray,
        increments: tuple[InertialIncrement, ...],
        schedule: tuple[_ScheduledMeasurement, ...],
        parameters: dict[str, float],
        context: TaskContext,
        measurement_events: list[dict[str, object]] | None = None,
    ) -> tuple[_ReplaySnapshot, ...]:
        q_nb = initial_q_nb.copy()
        measurement_index = 0
        snapshots: list[_ReplaySnapshot] = []
        for increment_index, increment in enumerate(increments):
            context.Cancel_RaiseIfRequested()
            dt = np.float32(increment.dt_s)
            rotated = Quaternion_RotateVector(q_nb, increment.delta_velocity_b)
            delta_velocity_enu = rotated.copy()
            delta_velocity_enu[2] -= np.float32(parameters["gravity_mps2"]) * dt
            q_nb = Quaternion_PropagateBodyIncrement(q_nb, increment.delta_theta_b)
            if not filter_instance.Kf6_Predict(delta_velocity_enu, float(dt)):
                continue
            position_result = int(Kf6UpdateResult.REJECTED_INVALID)
            velocity_result = int(Kf6UpdateResult.REJECTED_INVALID)
            baro_result = int(Kf6UpdateResult.REJECTED_INVALID)
            attempt_mask = 0
            filter_instance.last_group_result.fill(5)
            r_scale = np.ones(3, dtype=np.float32)
            while (
                measurement_index < len(schedule)
                and schedule[measurement_index].application_timestamp_us
                <= increment.interval_end_timestamp_us
            ):
                measurement = schedule[measurement_index]
                measurement_index += 1
                if measurement.kind == "gnss":
                    result = self._Gnss_Apply(
                        filter_instance,
                        measurement.record,
                    )
                    position_result, velocity_result, mask, scales = result
                    attempt_mask |= mask
                    r_scale[0:2] = scales
                    if measurement_events is not None:
                        self._MeasurementEvents_Append(
                            measurement_events,
                            filter_instance,
                            measurement,
                            increment.interval_end_timestamp_us,
                        )
                else:
                    result, scale, mask = self._Baro_Apply(
                        filter_instance,
                        measurement.record,
                    )
                    baro_result = result
                    r_scale[2] = scale
                    attempt_mask |= mask
                    if measurement_events is not None:
                        self._MeasurementEvents_Append(
                            measurement_events,
                            filter_instance,
                            measurement,
                            increment.interval_end_timestamp_us,
                            baro_result,
                        )
            snapshots.append(
                _ReplaySnapshot(
                    timestamp_us=increment.interval_end_timestamp_us,
                    q_nb=q_nb.copy(),
                    state=filter_instance.state.copy(),
                    covariance=filter_instance.covariance.copy(),
                    position_innovation=filter_instance.last_position_innovation.copy(),
                    velocity_innovation=filter_instance.last_velocity_innovation.copy(),
                    baro_innovation=float(filter_instance.last_baro_innovation),
                    position_nis=float(filter_instance.last_position_nis),
                    velocity_nis=float(filter_instance.last_velocity_nis),
                    group_nis=filter_instance.last_group_nis.copy(),
                    group_result=filter_instance.last_group_result.copy(),
                    baro_nis=float(filter_instance.last_baro_nis),
                    position_result=position_result,
                    velocity_result=velocity_result,
                    baro_result=baro_result,
                    attempt_mask=attempt_mask,
                    r_scale=r_scale,
                    position_measurement_variance=(
                        filter_instance.last_position_effective_variance.copy()
                    ),
                    velocity_measurement_variance=(
                        filter_instance.last_velocity_effective_variance.copy()
                    ),
                    baro_measurement_variance=float(filter_instance.last_baro_effective_variance),
                )
            )
            if increment_index % 256 == 0:
                context.Progress_Report(
                    0.1 + 0.82 * increment_index / max(len(increments), 1),
                    "replay.kf6",
                )
        return tuple(snapshots)

    @staticmethod
    def _MeasurementEvents_Append(
        output: list[dict[str, object]],
        filter_instance: Kf6Filter,
        measurement: _ScheduledMeasurement,
        present: int,
        baro_result: int | None = None,
    ) -> None:
        payload = measurement.record.payload
        receive = int(payload.get("receive_timestamp_us", 0))
        if measurement.kind == "baro":
            groups = (("baro", (0,), "variance_m2", "measurement_timestamp_us", 0),)
        else:
            groups = (
                (
                    "position_en",
                    (0, 1),
                    "position_variance_m2",
                    "position_measurement_timestamp_us",
                    0,
                ),
                (
                    "position_u",
                    (2,),
                    "position_variance_m2",
                    "position_measurement_timestamp_us",
                    1,
                ),
                (
                    "velocity_en",
                    (0, 1),
                    "velocity_variance_m2ps2",
                    "velocity_measurement_timestamp_us",
                    2,
                ),
                (
                    "velocity_u",
                    (2,),
                    "velocity_variance_m2ps2",
                    "velocity_measurement_timestamp_us",
                    3,
                ),
            )
        for group, axes, variance_key, time_key, index in groups:
            resolved = int(payload.get(time_key, payload.get("sample_timestamp_us", 0)))
            raw = payload.get(variance_key)
            if raw is None:
                continue
            variance = np.asarray(raw, dtype=np.float64).reshape(-1)
            if max(axes) >= variance.size:
                continue
            base = variance[list(axes)]
            if group == "baro":
                effective = np.asarray(
                    [filter_instance.last_baro_effective_variance], dtype=np.float64
                )
                result = int(baro_result) if baro_result is not None else 3
                group_valid = bool(int(payload.get("valid_mask", 1)) & 1)
            else:
                effective_source = (
                    filter_instance.last_position_effective_variance
                    if index < 2
                    else filter_instance.last_velocity_effective_variance
                )
                effective = np.asarray(effective_source, dtype=np.float64)[list(axes)]
                result = int(filter_instance.last_group_result[index])
                group_valid = bool(int(payload.get("valid_group_mask", 0)) & (1 << index))
            accepted = result in (0, 1)
            valid = group_valid and 0 < receive <= present and 0 < resolved <= present
            output.append(
                dict(
                    group=group,
                    timestamp_us=present,
                    receive_timestamp_us=receive,
                    source_id=payload.get("_quality_source_id"),
                    resolved_measurement_timestamp_us=resolved,
                    operation_sequence=measurement.source_order,
                    valid=valid,
                    result=result,
                    variance_scale=(
                        (float(payload.get("_quality_variance_scales", (1.0,) * 4)[index])
                         if group != "baro" else 1.0)
                        * (float(effective[0] / base[0]) if result == 1 and base[0] > 0 else 1.0)
                    ),
                    input_variance=tuple(float(value) for value in base),
                    effective_variance=tuple(
                        float(value)
                        for value in (effective if accepted else np.full(base.shape, np.nan))
                    ),
                    receive_age=(present - receive) * 0.001,
                    fixed_lag_latency=(present - resolved) * 0.001,
                    r_scale=float(effective[0] / base[0]) if accepted and base[0] > 0 else np.nan,
                )
            )

    @staticmethod
    def _Gnss_Apply(
        filter_instance: Kf6Filter,
        record: DecodedRecord,
    ) -> tuple[int, int, int, np.ndarray]:
        payload = record.payload
        if "_integrity_native_valid_group_mask" in payload:
            return Kf6AlgorithmPlugin._GnssIntegrity_Apply(filter_instance, record)
        mask = int(record.valid_flags) & 0x03
        if not bool(payload.get("fusion_allowed", 0)):
            return 3, 3, 0, np.ones(2, dtype=np.float32)
        position = np.asarray(payload["position_enu_m"], dtype=np.float32)
        velocity = np.asarray(payload["velocity_enu_mps"], dtype=np.float32)
        position_variance = np.asarray(payload["position_variance_m2"], dtype=np.float32)
        velocity_variance = np.asarray(payload["velocity_variance_m2ps2"], dtype=np.float32)
        velocity_mask = int(payload["velocity_valid_mask"])
        epoch_mask = 0
        if mask & 0x01:
            epoch_mask |= (1 << int(Kf6GnssGroup.POSITION_HORIZONTAL)) | (
                1 << int(Kf6GnssGroup.POSITION_VERTICAL)
            )
        if mask & 0x02 and (velocity_mask & 0x03) == 0x03:
            epoch_mask |= 1 << int(Kf6GnssGroup.VELOCITY_HORIZONTAL)
            if velocity_mask & 0x04:
                epoch_mask |= 1 << int(Kf6GnssGroup.VELOCITY_VERTICAL)
        if filter_instance.analysis_position_vertical_disabled:
            epoch_mask &= ~(1 << int(Kf6GnssGroup.POSITION_VERTICAL))
        filter_instance.Kf6_GnssEpochTrack(
            Kf6GnssEpoch(
                timestamp_us=int(payload["sample_timestamp_us"]),
                position_enu_m=position,
                velocity_enu_mps=velocity,
                position_std_m=np.sqrt(np.maximum(position_variance, 0.0)).astype(np.float32),
                velocity_std_mps=np.sqrt(np.maximum(velocity_variance, 0.0)).astype(np.float32),
                valid_group_mask=epoch_mask,
            )
        )
        position_result = int(Kf6UpdateResult.REJECTED_INVALID)
        velocity_result = int(Kf6UpdateResult.REJECTED_INVALID)
        position_scale_applied = np.float32(1.0)
        velocity_scale_applied = np.float32(1.0)
        if mask & 0x01:
            base = position_variance
            separated = filter_instance.Kf6_UpdateGnssPosition(position, base)
            position_result = (
                _Result_Aggregate(separated.horizontal_result, separated.vertical_result)
                if separated.vertical_attempted
                else int(separated.horizontal_result)
            )
            filter_instance.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.POSITION_HORIZONTAL, separated.horizontal_result
            )
            if separated.vertical_attempted:
                filter_instance.Kf6_GnssGroupResultProcess(
                    Kf6GnssGroup.POSITION_VERTICAL, separated.vertical_result
                )
            ratios = np.divide(
                filter_instance.last_position_effective_variance,
                base,
                out=np.ones(3, dtype=np.float32),
                where=base > 0.0,
            )
            position_scale_applied = np.max(ratios)
        if mask & 0x02 and (velocity_mask & 0x03) == 0x03:
            base = velocity_variance
            separated = filter_instance.Kf6_UpdateGnssVelocity(
                velocity, base, vertical_valid=bool(velocity_mask & 0x04)
            )
            velocity_result = (
                _Result_Aggregate(separated.horizontal_result, separated.vertical_result)
                if separated.vertical_attempted
                else int(separated.horizontal_result)
            )
            filter_instance.Kf6_GnssGroupResultProcess(
                Kf6GnssGroup.VELOCITY_HORIZONTAL, separated.horizontal_result
            )
            if separated.vertical_attempted:
                filter_instance.Kf6_GnssGroupResultProcess(
                    Kf6GnssGroup.VELOCITY_VERTICAL, separated.vertical_result
                )
            ratios = np.divide(
                filter_instance.last_velocity_effective_variance,
                base,
                out=np.ones(3, dtype=np.float32),
                where=base > 0.0,
            )
            velocity_scale_applied = np.max(ratios[: 3 if velocity_mask & 0x04 else 2])
        return (
            position_result,
            velocity_result,
            mask,
            np.asarray((position_scale_applied, velocity_scale_applied), dtype=np.float32),
        )

    @staticmethod
    def _GnssIntegrity_Apply(
        filter_instance: Kf6Filter,
        record: DecodedRecord,
    ) -> tuple[int, int, int, np.ndarray]:
        payload = record.payload
        if not bool(payload.get("fusion_allowed", 0)):
            return 3, 3, 0, np.ones(2, dtype=np.float32)
        position = np.asarray(payload["position_enu_m"], dtype=np.float32)
        velocity = np.asarray(payload["velocity_enu_mps"], dtype=np.float32)
        position_variance = np.asarray(payload["position_variance_m2"], dtype=np.float32)
        velocity_variance = np.asarray(payload["velocity_variance_m2ps2"], dtype=np.float32)
        native_mask = int(payload["_integrity_native_valid_group_mask"])
        admitted = int(payload["valid_group_mask"])
        if filter_instance.analysis_position_vertical_disabled:
            admitted &= ~2
        filter_instance.Kf6_GnssEpochTrack(
            Kf6GnssEpoch(
                timestamp_us=int(payload["sample_timestamp_us"]),
                position_enu_m=position,
                velocity_enu_mps=velocity,
                position_std_m=np.sqrt(np.maximum(position_variance, 0.0)),
                velocity_std_mps=np.sqrt(np.maximum(velocity_variance, 0.0)),
                valid_group_mask=native_mask,
            )
        )
        results = [Kf6UpdateResult.REJECTED_INVALID] * 4
        for group in range(4):
            if not admitted & (1 << group):
                continue
            selected = Kf6GnssGroup(group)
            value = position if group < 2 else velocity
            variance = position_variance if group < 2 else velocity_variance
            result = filter_instance.Kf6_GroupUpdate(selected, value, variance)
            result = filter_instance.Kf6_GroupRecover(
                selected, result, value, variance, int(payload["receive_timestamp_us"])
            )
            results[group] = result
        filter_instance.last_position_nis = np.max(filter_instance.last_group_nis[:2])
        filter_instance.last_velocity_nis = np.max(filter_instance.last_group_nis[2:])
        if admitted & 3:
            filter_instance._Counter_Update(
                "position",
                Kf6UpdateResult(
                    _Result_Aggregate(results[0], results[1])
                    if admitted & 3 == 3
                    else int(results[0] if admitted & 1 else results[1])
                ),
            )
        if admitted & 12:
            filter_instance._Counter_Update(
                "velocity",
                Kf6UpdateResult(
                    _Result_Aggregate(results[2], results[3])
                    if admitted & 12 == 12
                    else int(results[2] if admitted & 4 else results[3])
                ),
            )
        position_result = (
            _Result_Aggregate(results[0], results[1])
            if admitted & 3 == 3
            else int(results[0] if admitted & 1 else results[1])
        )
        velocity_result = (
            _Result_Aggregate(results[2], results[3])
            if admitted & 12 == 12
            else int(results[2] if admitted & 4 else results[3])
        )
        ratios = np.ones(2, dtype=np.float32)
        if admitted & 1 and position_variance[0] > 0:
            ratios[0] = filter_instance.last_position_effective_variance[0] / position_variance[0]
        if admitted & 4 and velocity_variance[0] > 0:
            ratios[1] = filter_instance.last_velocity_effective_variance[0] / velocity_variance[0]
        attempt_mask = int(bool(admitted & 3)) | (int(bool(admitted & 12)) << 1)
        return int(position_result), int(velocity_result), attempt_mask, ratios

    @staticmethod
    def _Baro_Apply(filter_instance: Kf6Filter, record: DecodedRecord) -> tuple[int, float, int]:
        if (int(record.valid_flags) & 0x04) == 0 or not int(record.payload.get("valid_mask", 0)):
            return int(Kf6UpdateResult.REJECTED_INVALID), 1.0, 0
        base_variance = float(record.payload["variance_m2"])
        result = filter_instance.Kf6_UpdateBaro(
            float(record.payload["relative_altitude_m"]), base_variance
        )
        scale = (
            float(filter_instance.last_baro_effective_variance) / base_variance
            if base_variance > 0.0
            else 1.0
        )
        return int(result), scale, 0x04

    @staticmethod
    def _Channels_Build(snapshots: tuple[_ReplaySnapshot, ...]) -> dict[str, TimeSeries]:
        timestamps = np.asarray([item.timestamp_us for item in snapshots], dtype=np.uint64)
        state = np.asarray([item.state for item in snapshots])
        covariance = np.asarray([item.covariance for item in snapshots])
        diagonal = np.asarray([np.diag(item) for item in covariance])
        upper = np.asarray(
            [
                [matrix[row, column] for row in range(6) for column in range(row, 6)]
                for matrix in covariance
            ]
        )
        channels = {
            "attitude.q_nb": _Series_Create(
                timestamps,
                np.asarray([item.q_nb for item in snapshots]),
                unit="1",
                quantity="quaternion",
                columns=("W", "X", "Y", "Z"),
            ),
            "navigation.position_enu": _Series_Create(
                timestamps, state[:, 0:3], unit="m", quantity="position", columns=("E", "N", "U")
            ),
            "navigation.velocity_enu": _Series_Create(
                timestamps, state[:, 3:6], unit="m/s", quantity="velocity", columns=("E", "N", "U")
            ),
            "kf6.state": _Series_Create(
                timestamps,
                state,
                unit="mixed",
                quantity="state",
                columns=("pE", "pN", "pU", "vE", "vN", "vU"),
            ),
            "kf6.covariance.diagonal": _Series_Create(
                timestamps,
                diagonal,
                unit="mixed",
                quantity="covariance",
                columns=("PpE", "PpN", "PpU", "PvE", "PvN", "PvU"),
            ),
            "kf6.covariance.upper_triangle": _Series_Create(
                timestamps,
                upper,
                unit="mixed",
                quantity="covariance",
                columns=tuple(f"P{row}{column}" for row in range(6) for column in range(row, 6)),
            ),
            "kf6.innovation.position": _Series_Create(
                timestamps,
                np.asarray([item.position_innovation for item in snapshots]),
                unit="m",
                quantity="innovation",
                columns=("E", "N", "U"),
            ),
            "kf6.innovation.velocity": _Series_Create(
                timestamps,
                np.asarray([item.velocity_innovation for item in snapshots]),
                unit="m/s",
                quantity="innovation",
                columns=("E", "N", "U"),
            ),
            "kf6.innovation.baro": _Series_Create(
                timestamps,
                np.asarray([item.baro_innovation for item in snapshots]),
                unit="m",
                quantity="innovation",
            ),
            "kf6.nis.position": _Series_Create(
                timestamps,
                np.asarray([item.position_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.nis.velocity": _Series_Create(
                timestamps,
                np.asarray([item.velocity_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.nis.baro": _Series_Create(
                timestamps,
                np.asarray([item.baro_nis for item in snapshots]),
                unit="1",
                quantity="nis",
            ),
            "kf6.update_result": _Series_Create(
                timestamps,
                np.asarray(
                    [
                        (item.position_result, item.velocity_result, item.baro_result)
                        for item in snapshots
                    ]
                ),
                unit="enum",
                quantity="update_result",
                columns=("GNSS position", "GNSS velocity", "Barometer"),
            ),
            "kf6.measurement_attempt_mask": _Series_Create(
                timestamps,
                np.asarray([item.attempt_mask for item in snapshots]),
                unit="bitmask",
                quantity="status",
            ),
            "kf6.measurement_r_scale": _Series_Create(
                timestamps,
                np.asarray([item.r_scale for item in snapshots]),
                unit="1",
                quantity="scale",
                columns=("GNSS position", "GNSS velocity", "Barometer"),
            ),
            "kf6.measurement_r.position": _Series_Create(
                timestamps,
                np.asarray([item.position_measurement_variance for item in snapshots]),
                unit="m^2",
                quantity="variance",
                columns=("E", "N", "U"),
            ),
            "kf6.measurement_r.velocity": _Series_Create(
                timestamps,
                np.asarray([item.velocity_measurement_variance for item in snapshots]),
                unit="m^2/s^2",
                quantity="variance",
                columns=("E", "N", "U"),
            ),
            "kf6.measurement_r.baro": _Series_Create(
                timestamps,
                np.asarray([item.baro_measurement_variance for item in snapshots]),
                unit="m^2",
                quantity="variance",
            ),
        }
        group_nis = np.asarray([item.group_nis for item in snapshots], dtype=np.float64)
        group_result = np.asarray([item.group_result for item in snapshots], dtype=np.float64)
        for index, name in enumerate(("position_en", "position_u", "velocity_en", "velocity_u")):
            attempted = group_result[:, index] != 5
            nis_valid = attempted & np.isin(group_result[:, index], (0, 1, 2))
            channels[f"kf6.nis.{name}"] = replace(
                _Series_Create(timestamps, group_nis[:, index], unit="1", quantity="nis"),
                valid=nis_valid,
            )
            channels[f"kf6.update_result.{name}"] = replace(
                _Series_Create(
                    timestamps, group_result[:, index], unit="enum", quantity="update_result"
                ),
                valid=attempted,
            )
            base = (
                np.asarray([item.position_innovation for item in snapshots])
                if index < 2
                else np.asarray([item.velocity_innovation for item in snapshots])
            )
            selected = base[:, :2] if index % 2 == 0 else base[:, 2:3]
            channels[f"kf6.innovation.{name}"] = replace(
                _Series_Create(
                    timestamps,
                    selected,
                    unit="m" if index < 2 else "m/s",
                    quantity="innovation",
                    columns=("E", "N") if index % 2 == 0 else ("U",),
                ),
                valid=attempted,
            )
        return channels
