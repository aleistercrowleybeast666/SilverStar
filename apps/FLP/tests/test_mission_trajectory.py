from __future__ import annotations

from math import atan, radians, sin, tan
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.mission import (
    MissionReplayBounds,
    MissionReplayBounds_Get,
    MissionReplayEndReason,
)
from silverstar_flp.core.trajectory import (
    TrajectoryBounds_Calculate,
    TrajectoryCameraDistance_Get,
    TrajectoryPosition_NearEvent,
)
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import START_TIMESTAMP_US, AnalysisFlight_Build


@pytest.mark.parametrize(
    "plugin_type",
    (PureInsAlgorithmPlugin, Kf6AlgorithmPlugin),
)
def test_replay_stops_at_landing_and_preserves_post_landing_raw_data(
    tmp_path: Path,
    plugin_type: type[PureInsAlgorithmPlugin] | type[Kf6AlgorithmPlugin],
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / f"SYNTHETIC_{plugin_type.__name__}_post_landing.BIN",
            update_count=10,
            landing_after_update_count=6,
        )
    )
    landing = START_TIMESTAMP_US + 120_100
    raw = dataset.Series_Get("imu.corrected.accel_b")
    assert raw is not None
    raw_before = raw.values.copy()
    assert int(raw.timestamp_us[-1]) > landing

    result = plugin_type().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    position = result.channels["navigation.position_enu"]

    assert int(position.timestamp_us[-1]) == START_TIMESTAMP_US + 120_000
    assert int(position.timestamp_us[-1]) <= landing
    assert result.diagnostics["mission_end_timestamp_us"] == landing
    assert result.diagnostics["mission_end_reason"] == "landing"
    assert np.array_equal(raw.values, raw_before)
    assert int(raw.timestamp_us[-1]) > landing


@pytest.mark.parametrize(
    "plugin_type",
    (PureInsAlgorithmPlugin, Kf6AlgorithmPlugin),
)
def test_post_landing_inputs_do_not_change_pre_landing_replay(
    tmp_path: Path,
    plugin_type: type[PureInsAlgorithmPlugin] | type[Kf6AlgorithmPlugin],
) -> None:
    parser = Sslog0ParserPlugin()
    reference = parser.parse(
        AnalysisFlight_Build(
            tmp_path / f"SYNTHETIC_{plugin_type.__name__}_reference.BIN",
            update_count=6,
        )
    )
    extended = parser.parse(
        AnalysisFlight_Build(
            tmp_path / f"SYNTHETIC_{plugin_type.__name__}_extended.BIN",
            update_count=10,
            landing_after_update_count=6,
        )
    )

    reference_result = plugin_type().run(
        reference,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    extended_result = plugin_type().run(
        extended,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )

    for channel_id in (
        "attitude.q_nb",
        "navigation.velocity_enu",
        "navigation.position_enu",
    ):
        reference_series = reference_result.channels[channel_id]
        extended_series = extended_result.channels[channel_id]
        assert np.array_equal(reference_series.timestamp_us, extended_series.timestamp_us)
        assert np.allclose(reference_series.values, extended_series.values, atol=1.0e-7)


@pytest.mark.parametrize(
    "plugin_type",
    (PureInsAlgorithmPlugin, Kf6AlgorithmPlugin),
)
def test_replay_without_landing_runs_to_valid_input_end(
    tmp_path: Path,
    plugin_type: type[PureInsAlgorithmPlugin] | type[Kf6AlgorithmPlugin],
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / f"SYNTHETIC_{plugin_type.__name__}_no_landing.BIN",
            include_landing_event=False,
            update_count=10,
        )
    )
    result = plugin_type().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    position = result.channels["navigation.position_enu"]

    assert int(position.timestamp_us[-1]) == START_TIMESTAMP_US + 200_000
    assert result.diagnostics["mission_end_timestamp_us"] == START_TIMESTAMP_US + 200_000
    assert result.diagnostics["mission_end_reason"] == "source_end"


def test_bounds_are_cached_once_and_are_source_specific(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_bounds_cache.BIN",
            update_count=10,
            landing_after_update_count=6,
        )
    )
    store = ReplayResultStore()
    resolver = ChannelResolver(dataset, store)

    pure_bounds = resolver.TrajectoryBounds_Get("recorded", solution="pure_ins")
    kf6_bounds = resolver.TrajectoryBounds_Get("recorded", solution="kf6")
    assert pure_bounds is not None
    assert kf6_bounds is not None
    assert pure_bounds.sample_count == 6
    assert kf6_bounds.sample_count == 6
    assert pure_bounds.max_enu != kf6_bounds.max_enu
    assert resolver.TrajectoryBoundsCalculationCount_Get("recorded", solution="pure_ins") == 1
    assert resolver.TrajectoryBoundsCalculationCount_Get("recorded", solution="kf6") == 1
    assert resolver.TrajectoryBounds_Get("recorded", solution="pure_ins") is pure_bounds

    replay = PureInsAlgorithmPlugin().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    entry = store.Result_Add(replay, algorithm_name="Pure INS")
    assert resolver.TrajectoryBoundsCalculationCount_Get(entry.source_id) == 0
    replay_bounds = resolver.TrajectoryBounds_Get(entry.source_id)
    assert replay_bounds is not None
    assert replay_bounds.sample_count == 6
    assert resolver.TrajectoryBounds_Get(entry.source_id) is replay_bounds
    assert resolver.TrajectoryBoundsCalculationCount_Get(entry.source_id) == 1


@pytest.mark.parametrize(
    "values",
    (
        np.asarray(((0.0, 0.0, 0.0), (1000.0, 2.0, 1.0))),
        np.asarray(((0.0, 0.0, 0.0), (1.0, 2.0, 1000.0))),
        np.asarray(((0.0, 0.0, 0.0), (900.0, 700.0, 2.0))),
        np.asarray(((2.0, 3.0, 4.0),)),
    ),
)
def test_camera_fit_contains_vertical_horizontal_long_and_short_trajectories(
    values: np.ndarray,
) -> None:
    timestamps = np.arange(values.shape[0], dtype=np.uint64) + np.uint64(1_000_000)
    series = TimeSeries(
        timestamp_us=timestamps,
        values=values,
        unit="m",
        quantity="position",
        source="synthetic",
        valid=np.ones(values.shape[0], dtype=np.bool_),
        columns=("E", "N", "U"),
    )
    mission = MissionReplayBounds(
        start_timestamp_us=int(timestamps[0]),
        end_timestamp_us=int(timestamps[-1]),
        end_reason=MissionReplayEndReason.SOURCE_END,
    )
    bounds = TrajectoryBounds_Calculate(series, mission)
    aspect_ratio = 16.0 / 9.0
    horizontal_fov = 60.0
    distance = TrajectoryCameraDistance_Get(
        bounds,
        horizontal_fov_deg=horizontal_fov,
        aspect_ratio=aspect_ratio,
    )
    horizontal_half = radians(horizontal_fov * 0.5)
    vertical_half = atan(tan(horizontal_half) / aspect_ratio)
    limiting_half = min(horizontal_half, vertical_half)

    assert distance >= 8.0
    assert distance * sin(limiting_half) >= bounds.bounding_radius * 1.15 - 1.0e-9


def test_mission_bounds_and_landing_position_allow_normal_task_scheduling_gap(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_landing_gap.BIN")
    )
    bounds = MissionReplayBounds_Get(dataset, source_end_timestamp_us=9_999_999)
    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    assert position is not None

    assert bounds.end_reason == MissionReplayEndReason.LANDING
    assert bounds.end_timestamp_us == START_TIMESTAMP_US + 160_100
    assert TrajectoryPosition_NearEvent(position, bounds.end_timestamp_us) is not None
