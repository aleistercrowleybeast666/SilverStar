from pathlib import Path

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from silverstar_flp.core.horizontal_trajectory import (
    LABEL_IDS,
    HorizontalTrajectory_Build,
    HorizontalTrajectory_Draw,
)
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.mission import FlightDisplayBounds_Get, MissionReplayBounds_Get
from silverstar_flp.export.service import ExportLanguage, ExportTheme, FlightExporter
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse


def test_both_apps_ship_identical_standalone_geometry_and_renderer():
    flp = Path(__file__).parents[1] / "src/silverstar_flp/core/horizontal_trajectory.py"
    gshc = Path(__file__).parents[2] / "GSHC/processing/horizontal_trajectory.py"
    assert flp.read_bytes() == gshc.read_bytes()


def test_invalid_duplicate_long_gap_and_reanchor_never_bridge():
    times = [0, 0.1, 0.2, 0.2, 0.3, 5, 5.1, 5.2, 5.3]
    points = np.array([[i, 2 * i, i - 4] for i in range(len(times))], dtype=float)
    points[6] = np.nan
    result = HorizontalTrajectory_Build(times, points, breaks_s=(5.3,), deploy_time_s=3)
    assert result.deploy_enu is None
    assert result.edges_enu.shape == (3, 2, 3)
    np.testing.assert_array_equal(result.edges_enu[:, 0, 0], [0, 1, 3])
    np.testing.assert_array_equal(result.edge_height_m, [-3.5, -2.5, -0.5])
    assert not result.points_enu.flags.writeable


def test_clipped_samples_keep_mission_origin_and_event_is_only_local_interpolation():
    times = np.arange(11) / 10
    points = np.column_stack((times * 20 + 100, times * 30 - 10, times * 40 - 50))
    result = HorizontalTrajectory_Build(
        times, points, origin_enu=points[0], time_range=(0.25, 0.75), deploy_time_s=0.45
    )
    np.testing.assert_allclose(result.points_enu[0], [6, 9, 12])
    np.testing.assert_allclose(result.deploy_enu, [9, 13.5, 18])
    assert result.start_clipped and result.end_clipped
    assert result.edges_enu.shape == (4, 2, 3)
    full = HorizontalTrajectory_Build(times, points, origin_enu=points[0], deploy_time_s=2)
    assert not full.start_clipped and not full.end_clipped and full.deploy_enu is None


def test_preflight_samples_are_not_mission_start_and_range_does_not_interpolate_endpoints():
    result = HorizontalTrajectory_Build(
        [0, 0.1, 0.2, 0.3],
        [[0, 0, -1], [1, 1, 0], [2, 2, 1], [3, 3, 2]],
        mission_range=(0.1, 0.3),
        time_range=(0.1, 0.3),
    )
    assert not result.start_clipped and not result.end_clipped
    cropped = HorizontalTrajectory_Build([0, 0.1], [[0, 0, 0], [1, 1, 1]], time_range=(0.05, 0.08))
    assert len(cropped.points_enu) == 0


@pytest.mark.parametrize("points", [[], [[1, 2, -5]], [[1, 2, 7], [2, 3, 7]]])
@pytest.mark.parametrize("language", ["en_US", "zh_CN"])
def test_renderer_empty_short_constant_height_equal_metric_axes(points, language, tmp_path):
    result = HorizontalTrajectory_Build(np.arange(len(points)) * 0.1, points)
    translator = Translator(language)
    labels = {key: translator.Text_Get("horizontal." + key) for key in LABEL_IDS}
    figure = Figure(figsize=(8, 6))
    FigureCanvasAgg(figure)
    axis = HorizontalTrajectory_Draw(figure, result, labels)
    figure.canvas.draw()
    assert axis.get_aspect() == 1
    if points:
        delta = axis.transData.transform([1, 1]) - axis.transData.transform([0, 0])
        assert abs(delta[0] - delta[1]) < 1e-9
        assert figure.axes[1].get_ylabel() == labels["height"]
        assert len(figure.axes[1].get_yticks()) == 1
        assert axis.get_legend().get_bbox_to_anchor().y1 < axis.get_window_extent().y0
    else:
        assert axis.texts[0].get_text() == labels["empty"]
    figure.savefig(tmp_path / "horizontal.png")


def test_flp_export_draws_same_geometry_and_keeps_equal_axes(tmp_path, monkeypatch):
    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC_horizontal.BIN"))
    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    bounds = FlightDisplayBounds_Get(dataset, MissionReplayBounds_Get(dataset))
    observed = []
    from silverstar_flp.export import service

    draw = service.HorizontalTrajectory_Draw

    def capture(figure, trajectory, labels, **kwargs):
        observed.append(trajectory)
        return draw(figure, trajectory, labels, **kwargs)

    monkeypatch.setattr(service, "HorizontalTrajectory_Draw", capture)
    path = tmp_path / "Horizontal_EN.png"
    FlightExporter()._HorizontalTrajectory_Write(
        dataset, position, path, ExportLanguage.EN, ExportTheme.DARK, bounds, (0.04, 0.08)
    )
    assert path.exists() and path.stat().st_size > 10000
    assert len(observed) == 1 and observed[0].start_clipped and observed[0].end_clipped


def test_wide_pane_keeps_metric_square_centred_with_external_colourbar():
    trajectory = HorizontalTrajectory_Build([0, .2], [(0, 0, 0), (1, 100, 20)])
    translator = Translator("en_US")
    labels = {key: translator.Text_Get("horizontal." + key) for key in LABEL_IDS}
    figure = Figure(figsize=(14, 5))
    FigureCanvasAgg(figure)
    axis = HorizontalTrajectory_Draw(figure, trajectory, labels)
    figure.canvas.draw()
    allocated, actual = axis.get_position(original=True), axis.get_position()
    assert abs((actual.x0 + actual.x1) - (allocated.x0 + allocated.x1)) < 1e-9
    pixels = axis.get_window_extent()
    assert abs(pixels.width - pixels.height) < 1e-9
    assert figure.axes[1].get_position().x0 > actual.x1
