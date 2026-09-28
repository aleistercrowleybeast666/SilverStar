from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.recovery import RecoveryReplay_Run
from silverstar_flp.core.comparison import Series_Compare
from silverstar_flp.core.math import (
    Quaternion_GeodesicErrorDeg,
    Quaternion_PropagateBodyIncrement,
)
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter, Kf6UpdateResult
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import StationaryFlight_Build


@pytest.fixture
def stationary_dataset(tmp_path: Path):
    path = StationaryFlight_Build(tmp_path / "SYNTHETIC_stationary.BIN")
    return Sslog0ParserPlugin().parse(path)


@pytest.mark.parametrize("source", ["recorded_inertial_increment", "corrected_imu"])
def test_pure_ins_stationary_replay_uses_software_quaternion_and_real_dt(
    stationary_dataset, source: str
) -> None:
    plugin = PureInsAlgorithmPlugin()
    result = plugin.run(
        stationary_dataset, ReplayRequest(mode=ReplayMode.OFFLINE, input_source=source)
    )
    assert result.fidelity.value == "APPROXIMATE"
    assert "host_golden_not_verified" in result.warnings
    assert result.diagnostics["software_quaternion_propagation"] is True
    assert result.diagnostics["output_count"] == 8
    assert np.allclose(
        result.channels["attitude.q_nb"].values,
        np.asarray((1.0, 0.0, 0.0, 0.0)),
        atol=2.0e-6,
    )
    assert np.max(np.abs(result.channels["navigation.velocity_enu"].values)) < 2.0e-6
    assert np.max(np.abs(result.channels["navigation.position_enu"].values)) < 2.0e-6
    timestamps = result.channels["navigation.position_enu"].timestamp_us
    assert np.all(np.diff(timestamps) == 20_000)


def test_replay_defaults_to_corrected_imu_while_increment_support_remains_internal(
    stationary_dataset,
) -> None:
    request = ReplayRequest(
        mode=ReplayMode.OFFLINE,
    )
    assert request.input_source == "corrected_imu"
    for plugin in (PureInsAlgorithmPlugin(), Kf6AlgorithmPlugin()):
        availability = plugin.availability(stationary_dataset)
        assert availability.available
        assert "corrected_imu" in availability.supported_input_sources
        assert "recorded_inertial_increment" in availability.supported_input_sources


def test_pure_ins_never_silently_falls_back_to_other_source(tmp_path: Path) -> None:
    path = StationaryFlight_Build(
        tmp_path / "SYNTHETIC_increment_only.BIN", include_corrected_imu=False
    )
    dataset = Sslog0ParserPlugin().parse(path)
    plugin = PureInsAlgorithmPlugin()
    availability = plugin.availability(dataset, "corrected_imu")
    assert not availability.available
    assert availability.fidelity.value == "UNAVAILABLE"
    assert "IMU_CORRECTED" in availability.missing_inputs
    with pytest.raises(ValueError, match="replay_unavailable"):
        plugin.run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE, input_source="corrected_imu"))


def test_quaternion_error_is_sign_invariant_and_propagation_is_right_multiplied() -> None:
    identity = np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float32)
    yaw = Quaternion_PropagateBodyIncrement(
        identity, np.asarray((0.0, 0.0, np.pi / 2), dtype=np.float32)
    )
    assert Quaternion_GeodesicErrorDeg(yaw, -yaw) < 1.0e-5
    assert np.allclose(yaw, (np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)), atol=2.0e-6)


def test_kf6_stationary_replay_has_finite_positive_covariance(stationary_dataset) -> None:
    plugin = Kf6AlgorithmPlugin()
    result = plugin.run(
        stationary_dataset,
        ReplayRequest(mode=ReplayMode.OFFLINE, input_source="recorded_inertial_increment"),
    )
    state = result.channels["kf6.state"].values
    diagonal = result.channels["kf6.covariance.diagonal"].values
    assert result.fidelity.value == "APPROXIMATE"
    assert "host_golden_not_verified" in result.warnings
    assert tuple(result.diagnostics["state_order"]) == (
        "pE",
        "pN",
        "pU",
        "vE",
        "vN",
        "vU",
    )
    assert np.all(np.isfinite(state))
    assert np.all(diagonal > 0.0)
    assert np.max(np.abs(state)) < 2.0e-6
    for channel_id, width in (
        ("kf6.measurement_r.position", 3),
        ("kf6.measurement_r.velocity", 3),
        ("kf6.measurement_r.baro", 1),
    ):
        series = result.channels[channel_id]
        values = np.asarray(series.values).reshape(series.count, -1)
        assert values.shape == (state.shape[0], width)
        assert np.all(np.isfinite(values))
        assert np.all(values >= 0.0)


def test_kf6_hard_nis_gate_rejects_outlier_without_moving_state() -> None:
    filter_instance = Kf6Filter.Kf6_Create(
        process_accel_std_mps2=np.asarray((1.5, 1.5, 2.0)),
        p0_diagonal=np.ones(6),
        initial_velocity_enu_mps=np.zeros(3),
        nis_soft_threshold=np.asarray((6.635, 9.210, 11.345)),
        nis_hard_threshold=np.asarray((10.828, 13.816, 16.266)),
        nis_max_r_scale=10.0,
    )
    before = filter_instance.state.copy()
    separated = filter_instance.Kf6_UpdateGnssPosition(
        np.asarray((1000.0, 1000.0, 1000.0)), np.ones(3)
    )
    assert separated.horizontal_result == Kf6UpdateResult.REJECTED_NIS
    assert separated.vertical_result == Kf6UpdateResult.REJECTED_NIS
    assert np.array_equal(filter_instance.state, before)


def test_recorded_and_recomputed_comparison_uses_geodesic_attitude_error(
    stationary_dataset,
) -> None:
    result = PureInsAlgorithmPlugin().run(
        stationary_dataset,
        ReplayRequest(mode=ReplayMode.OFFLINE, input_source="recorded_inertial_increment"),
    )
    comparison = Series_Compare(
        stationary_dataset.Series_Get("pure_ins.recorded.attitude.q_nb"),
        result.channels["attitude.q_nb"],
        quaternion=True,
    )
    assert comparison.unit == "deg"
    assert comparison.statistics.maximum_absolute_error < 1.0e-5


def test_what_if_is_labeled_and_does_not_mutate_recorded_dataset(stationary_dataset) -> None:
    recorded_before = stationary_dataset.Series_Get(
        "pure_ins.recorded.navigation.position_enu"
    ).values.copy()
    result = PureInsAlgorithmPlugin().run(
        stationary_dataset,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF,
            input_source="recorded_inertial_increment",
            parameters={"gravity_mps2": 9.7},
        ),
    )
    assert result.provenance == "What-if"
    assert result.parameters["gravity_mps2"] == 9.7
    assert np.array_equal(
        stationary_dataset.Series_Get("pure_ins.recorded.navigation.position_enu").values,
        recorded_before,
    )


def test_deploy_delay_replay_uses_mission_config(stationary_dataset) -> None:
    result = RecoveryReplay_Run(stationary_dataset)
    assert result.deploy.available
    assert result.deploy.replayed_timestamp_us == 1_100_000
    assert result.deploy.matched_mask == 0x04
    assert not result.landing.available
