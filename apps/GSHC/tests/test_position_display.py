from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pytest
from processing.flight_log_processor import FlightData, TimedVector
from processing.flight_plotter import FlightPlotter
from processing.horizontal_trajectory import HorizontalTrajectory_Build
from processing.position_display import (
    POSITION_DISPLAY_MAX_ABS_M,
    PositionDisplay_Build,
    PositionDisplay_History,
    PositionDisplay_PointAt,
)


def samples_build(points, times=None):
    if times is None:
        times = np.arange(len(points)) * .2
    return [TimedVector(float(t), tuple(p), round(t * 1000)) for t, p in zip(times, points)]


def data_build(samples, deploy=.5):
    data = FlightData(0, None, None if deploy is None else round(deploy * 1000),
                      1400, Path("input.jsonl"))
    data.pos = samples
    return data


@pytest.mark.parametrize("axis", range(3))
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf, 2e15, -2e15])
def test_invalid_coordinate_excluded_without_bridging_or_rewriting(axis, invalid):
    points = np.column_stack((np.arange(8), np.arange(8) * 2, np.arange(8) * 3)).astype(float)
    points[3, axis] = invalid
    samples = samples_build(points)
    display = PositionDisplay_Build(samples)
    assert display.valid.tolist() == [True, True, True, False, True, True, True, True]
    assert np.isnan(display.points_enu[3]).all()
    assert not display.joins[2] and not display.joins[3]
    assert PositionDisplay_PointAt(display, .5) is None
    assert PositionDisplay_PointAt(display, .6) is None
    assert PositionDisplay_PointAt(display, .7) is None
    trajectory = HorizontalTrajectory_Build(
        display.times_s, display.points_enu, valid=display.valid,
        gap_threshold_s=display.gap_threshold_s, deploy_time_s=.5,
    )
    assert trajectory.deploy_enu is None
    assert trajectory.edges_enu.shape == (5, 2, 3)
    before, after, current = PositionDisplay_History(display, 1.4, .5)
    assert np.isnan(after).any() and current is not None
    for path in (before, after):
        finite_pairs = np.isfinite(path[:-1]).all(axis=1) & np.isfinite(path[1:]).all(axis=1)
        assert np.all(np.abs(np.diff(path, axis=0)[finite_pairs, 0]) <= 1.000001)
    np.testing.assert_array_equal([s.values for s in samples], points)


@pytest.mark.parametrize("gap,marker", [(.598, True), (.599, False), (1.001, False)])
def test_air_tick_quantization_accepts_boundary_but_keeps_real_gaps(gap, marker):
    times = np.array([69., 69.239, 69.478, 69.717,
                      69.717 + gap, 69.956 + gap, 70.195 + gap])
    samples = samples_build(np.column_stack((times, times * 2, times * 3)), times)
    display = PositionDisplay_Build(samples)
    assert display.gap_threshold_s == pytest.approx(.598, abs=1e-12)
    trajectory = HorizontalTrajectory_Build(
        display.times_s, display.points_enu, valid=display.valid,
        gap_threshold_s=display.gap_threshold_s, deploy_time_s=69.8,
    )
    assert (trajectory.deploy_enu is not None) is marker
    point = PositionDisplay_PointAt(display, 69.8)
    assert (point is not None) is marker
    if marker:
        np.testing.assert_allclose(point, [69.8, 139.6, 209.4])
        np.testing.assert_allclose(trajectory.deploy_enu, point)


def test_explicit_threshold_and_one_second_cap_are_preserved():
    samples = samples_build([(0, 0, 0), (1, 2, 3), (2, 4, 6)], [0, 1.001, 2.002])
    display = PositionDisplay_Build(samples)
    assert display.gap_threshold_s == pytest.approx(1.0)
    assert not display.joins.any()
    display = PositionDisplay_Build(samples, .25)
    assert display.gap_threshold_s == pytest.approx(.25)
    assert not display.joins.any()


def test_high_dynamic_points_and_display_envelope_boundary_are_retained():
    points = [(0, 0, 0), (1e5, -2e5, 3e5),
              (POSITION_DISPLAY_MAX_ABS_M, -POSITION_DISPLAY_MAX_ABS_M, 0)]
    samples = samples_build(points)
    display = PositionDisplay_Build(samples)
    assert display.valid.all() and display.joins.all()
    np.testing.assert_allclose(PositionDisplay_PointAt(display, .1), [5e4, -1e5, 1.5e5])
    np.testing.assert_array_equal([s.values for s in samples], points)


@pytest.mark.parametrize("points", [[], [(np.nan, 0, 0)], [(np.inf, 0, 0)],
                                  [(0, 0, 2e15)]])
def test_empty_or_all_invalid_positions_have_safe_axes_and_no_marker(points, tmp_path):
    data = data_build(samples_build(points))
    plotter = FlightPlotter()
    assert np.isfinite(plotter._trajectory_limits(data)).all()
    assert plotter._get_chute_point(data) is None
    renderer = plotter._GifRenderer_Create(data)
    try:
        frame = plotter._GifFrame_Render(renderer, data, .5)
        frame.close()
        assert len(renderer["current"].get_data_3d()[0]) == 0
        plotter.plot_horizontal_trajectory(tmp_path / "horizontal.png", data)
    finally:
        plt.close(renderer["figure"])


def test_invalid_boundary_and_timestamp_do_not_create_interpolation():
    samples = [
        TimedVector(0, (np.nan, 0, 0), 0), TimedVector(.2, (1, 2, 3), 200),
        TimedVector(np.nan, (2, 4, 6), 400), TimedVector(.6, (0, 0, 2e15), 600),
    ]
    display = PositionDisplay_Build(samples)
    assert not display.joins.any()
    assert PositionDisplay_PointAt(display, 0) is None
    assert PositionDisplay_PointAt(display, .1) is None
    assert PositionDisplay_PointAt(display, .7, hold_end=True) is None
    before, after, current = PositionDisplay_History(display, .7, .5)
    assert np.isnan(before).any() and np.isnan(after).all() and current is None


def test_static_and_animation_use_same_broken_paths_and_event_point(tmp_path):
    points = np.column_stack((np.arange(8), np.arange(8), np.arange(8))).astype(float)
    points[3, 2] = 2e15
    data = data_build(samples_build(points), .95)
    plotter = FlightPlotter()
    renderer = plotter._GifRenderer_Create(data)
    try:
        for t in [0, .2, .5, .6, .7, .8, .95, 1.4]:
            frame = plotter._GifFrame_Render(renderer, data, t)
            frame.close()
            if t in [.5, .6, .7]:
                assert len(renderer["current"].get_data_3d()[0]) == 0
        animation_paths = [np.column_stack(renderer[key].get_data_3d())
                           for key in ["before", "after"]]
        with patch.object(plotter, "_save_figure") as save:
            plotter._draw_gif_frame(tmp_path / "static.png", data, 1.4, (1, 0, 0, 0),
                                    (2e15, 2e15, 2e15), plotter._trajectory_limits(data))
            figure = save.call_args.args[0]
            static_paths = [np.column_stack(line.get_data_3d())
                            for line in figure.axes[1].lines]
            for animation, static in zip(animation_paths, static_paths):
                np.testing.assert_array_equal(animation, static)
            assert np.isnan(static_paths[0]).any()
            plt.close(figure)
        np.testing.assert_allclose(plotter._get_chute_point(data), [4.75] * 3)
    finally:
        plt.close(renderer["figure"])


def test_position_chart_masks_whole_bad_row_but_keeps_raw_values(tmp_path):
    samples = samples_build([(0, 0, 0), (1, 2e15, 2), (3, 4, 5)])
    original = [s.values for s in samples]
    plotter = FlightPlotter()
    with patch.object(plotter, "_save_figure") as save:
        plotter.plot_vector_figure(tmp_path / "position.png", "Position", samples,
                                   ("E", "N", "U"), "m", position_samples=True)
        figure = save.call_args.args[0]
        for axis in figure.axes:
            assert np.isnan(axis.lines[0].get_ydata()[1])
            assert np.isfinite(axis.get_ylim()).all()
        plt.close(figure)
    assert [s.values for s in samples] == original


@pytest.mark.parametrize("duplicates,deploy,end_time,expected", [
    ([(1, 2, 3), (9, 9, 2e15)], .2, .4, None),
    ([(9, 9, 2e15), (1, 2, 3)], .2, .4, (1, 2, 3)),
    ([(1, 2, 3), (4, 5, 6)], .2, .4, (4, 5, 6)),
    ([(9, 9, 2e15), (8, 8, 2e15)], .2, .4, None),
    ([(1, 2, 3), (4, 5, 6)], .8, 1.4, None),
], ids=["valid-invalid", "invalid-valid", "both-valid", "both-invalid", "long-gap"])
def test_duplicate_epoch_deploy_is_consistent_across_exports(
    duplicates, deploy, end_time, expected, tmp_path,
):
    samples = samples_build([(0, 0, 0), *duplicates, (7, 8, 9)],
                            [0, .2, .2, end_time])
    original = [s.values for s in samples]
    data = data_build(samples, deploy)
    display = PositionDisplay_Build(samples)
    assert not display.joins[1]  # Duplicate epochs always split the path.
    for i in np.flatnonzero(~display.valid):
        if i:
            assert not display.joins[i - 1]
        if i < len(display.joins):
            assert not display.joins[i]
    plotter = FlightPlotter()
    with patch("processing.flight_plotter.HorizontalTrajectory_Draw") as draw:
        plotter.plot_horizontal_trajectory(tmp_path / "horizontal.png", data)
        trajectory = draw.call_args.args[1]
    if expected is None:
        assert trajectory.deploy_enu is None
        assert plotter._get_chute_point(data) is None
    else:
        np.testing.assert_array_equal(trajectory.deploy_enu, expected)
        np.testing.assert_array_equal(plotter._get_chute_point(data), expected)
    assert len(trajectory.edges_enu) == int(display.joins.sum())
    renderer = plotter._GifRenderer_Create(data)
    try:
        frame = plotter._GifFrame_Render(renderer, data, deploy)
        frame.close()
        if expected is None:
            assert renderer["chute"] is None
        else:
            np.testing.assert_array_equal(
                np.column_stack(renderer["chute"].get_data_3d())[0], expected,
            )
            assert renderer["chute"].get_visible()
        with patch.object(plotter, "_save_figure") as save:
            plotter._draw_gif_frame(tmp_path / "static.png", data, deploy,
                                    (1, 0, 0, 0), (0, 0, 0),
                                    plotter._trajectory_limits(data))
            figure = save.call_args.args[0]
            texts = figure.axes[1].texts
            assert bool(texts) is (expected is not None)
            if expected is not None:
                np.testing.assert_array_equal(texts[0].get_position_3d(), expected)
            plt.close(figure)
    finally:
        plt.close(renderer["figure"])
    np.testing.assert_array_equal([s.values for s in samples], original)


@pytest.mark.parametrize("page_range,deploy", [((0, .1), .2), ((.25, .4), .3)])
def test_2d_deploy_keeps_view_visibility_after_duplicate_resolution(
    page_range, deploy, tmp_path,
):
    data = data_build(samples_build([(0, 0, 0), (1, 2, 3), (4, 5, 6), (7, 8, 9)],
                                    [0, .2, .2, .4]), deploy)
    plotter = FlightPlotter()
    plotter.page_range = page_range
    with patch("processing.flight_plotter.HorizontalTrajectory_Draw") as draw:
        plotter.plot_horizontal_trajectory(tmp_path / "horizontal.png", data)
        assert draw.call_args.args[1].deploy_enu is None
