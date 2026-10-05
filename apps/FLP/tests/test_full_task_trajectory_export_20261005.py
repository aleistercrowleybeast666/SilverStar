import json
import numpy as np
import pytest
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.mission import FlightDisplayBounds_Get, MissionReplayBounds_Get
from silverstar_flp.core.trajectory import TrajectoryOrigin_Get
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse


@pytest.mark.parametrize('page_mode,expected_pages', [('30', 3), ('Full', 1), ('Current View', 1)])
def test_2d_is_one_full_task_picture_independent_of_time_pages(tmp_path, monkeypatch, page_mode, expected_pages):
    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / 'SYNTHETIC_long_trajectory.BIN', update_count=4000))
    bounds = FlightDisplayBounds_Get(dataset, MissionReplayBounds_Get(dataset))
    assert bounds.end_timestamp_us - bounds.start_timestamp_us > 60_000_000
    observed = []
    from silverstar_flp.export import service
    draw = service.HorizontalTrajectory_Draw
    def capture(figure, trajectory, labels, **kwargs):
        observed.append(trajectory)
        return draw(figure, trajectory, labels, **kwargs)
    monkeypatch.setattr(service, 'HorizontalTrajectory_Draw', capture)
    progress = []
    output = tmp_path / 'output'
    result = FlightExporter().export(dataset, output, options=ExportOptions(
        language=ExportLanguage.EN, include_overview=False, include_diagnostics=False,
        include_events=False, include_csv=False, include_plots=True,
        include_trajectory_3d=False, include_attitude_gif=False,
        page_mode=page_mode, current_range=(30, 45)),
        context=TaskContext(progress_callback=lambda value, code: progress.append((value, code))))
    assert not result.failures
    assert len(list(output.rglob('Horizontal_Trajectory*.png'))) == 1
    assert len(list(output.rglob('Flight_Position_ENU*.png'))) == expected_pages
    assert len(observed) == 1
    position = dataset.Series_Get('kf6.recorded.navigation.position_enu')
    keep = position.valid & (position.timestamp_us >= bounds.start_timestamp_us) & (position.timestamp_us <= bounds.end_timestamp_us)
    origin = TrajectoryOrigin_Get(position, bounds.start_timestamp_us)
    np.testing.assert_allclose(observed[0].points_enu[[0, -1]], position.values[keep][[0, -1]] - origin)
    assert observed[0].deploy_enu is not None
    assert not observed[0].start_clipped and not observed[0].end_clipped
    assert observed[0].edge_height_m.min() < observed[0].edge_height_m.max()
    manifest = json.loads(next(output.glob('Export_Manifest*.json')).read_text(encoding='utf-8'))
    assert len([item for item in manifest['resolved_topics'] if item.startswith('horizontal_trajectory:')]) == 1
    np.testing.assert_allclose(manifest['resolved_time_range']['horizontal_trajectory_s'],
                               [0.0, (bounds.end_timestamp_us - bounds.start_timestamp_us) * 1e-6])
    fractions = [value for value, code in progress if code == 'export.running']
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
