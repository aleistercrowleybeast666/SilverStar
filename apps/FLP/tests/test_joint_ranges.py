import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.time_range import DisplayIndices_Get, TimeRangeController
from silverstar_flp.export.ranges import ExportPages_Get, GifMetadata_Get, PlotDirectory
from silverstar_flp.export.service import FlightExporter
from silverstar_flp.ui.time_range import TimeRangeBar


def test_range_defaults_clamping_restore():
    c = TimeRangeController()
    assert c.Mission_Set(10).preset == "Full"
    assert c.Mission_Set(300).duration == 30
    c.Range_Set(290, 300)
    assert c.Duration_Set(60).start == 240
    c.Range_Set(11.125, 42.5)
    state = c.model.State_Get()
    assert state['preset'] == 'Custom'
    c.Mission_Set(300)
    assert c.State_Restore(state).start == 11.125
    assert c.Preset_Set('Full').duration == 300
    with pytest.raises(ValueError):
        c.Duration_Set(float('nan'))


@pytest.mark.parametrize('language', ['en_US', 'zh_CN'])
def test_controls_synchronize_without_recursion(language):
    app = QApplication.instance() or QApplication([])
    bar = TimeRangeBar(Translator(language))
    bar.Mission_Set(300)
    signals = []
    bar.rangeChanged.connect(signals.append)
    bar.slider.rangeChanged.emit(230, 250)
    assert bar.start.value() == 230 and bar.duration.value() == 20
    assert bar.preset.currentData() == 'Custom'
    bar.duration.setValue(120)
    assert bar.start.value() == 180 and bar.end.value() == 300
    assert bar.preset.currentData() == '120'
    assert len(signals) == 2
    bar.resize(700, 110)
    bar.show()
    app.processEvents()
    assert bar.minimumSizeHint().width() <= 700
    bar.close()


def test_three_handle_drag_shift_buttons_and_touch_hitbox():
    app = QApplication.instance() or QApplication([])
    bar = TimeRangeBar(Translator("en_US"))
    bar.Mission_Set(120)
    bar.controller.Range_Set(30, 60)
    bar._Changed(bar.controller.model)
    bar.resize(700, 115)
    bar.show()
    app.processEvents()
    slider = bar.slider
    slider.resize(520, 44)
    left = round(slider._Position_Get(30))
    right = round(slider._Position_Get(60))
    center = (left + right) // 2
    y = slider.height() // 2
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=QPoint(left + 17, y))
    assert slider._handle == 0
    slider._Move(slider._Position_Get(20))
    assert bar.controller.model.start == pytest.approx(20)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=QPoint(left + 17, y))
    QTest.mousePress(slider, Qt.MouseButton.LeftButton,
                     pos=QPoint(round(slider._Position_Get(60)), y))
    assert slider._handle == 1
    slider._Move(slider._Position_Get(70))
    assert bar.controller.model.end == pytest.approx(70)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton)
    duration = bar.controller.model.duration
    midpoint = (bar.controller.model.start + bar.controller.model.end) / 2
    center = round(slider._Position_Get(midpoint))
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=QPoint(center, y))
    assert slider._handle == 2
    slider._Move(center + 40)
    assert bar.controller.model.duration == pytest.approx(duration)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton)
    bar.controller.Range_Set(30, 60)
    bar._Changed(bar.controller.model)
    bar.shift_right.click()
    assert (bar.start.value(), bar.end.value()) == (60, 90)
    bar.shift_right.click()
    assert (bar.start.value(), bar.end.value()) == (90, 120)
    bar.shift_right.click()
    assert (bar.start.value(), bar.end.value()) == (90, 120)
    bar.shift_left.click()
    assert (bar.start.value(), bar.end.value()) == (60, 90)
    bar.Mission_Set(20)
    bar.shift_right.click()
    assert (bar.start.value(), bar.end.value()) == (0, 20)
    bar.close()


def test_peak_and_gap_boundaries_are_retained():
    time = np.arange(100000, dtype=np.uint64) * 5000
    values = np.zeros((len(time), 3))
    values[517, 0] = 999
    values[718, 1] = -999
    valid = np.ones(len(time), dtype=bool)
    valid[30100:31000] = False
    indices = DisplayIndices_Get(time, values, valid, 6000)
    assert {517, 718, 30099, 30100, 30999, 31000} <= set(indices)
    assert len(indices) < 6500
    assert values[517, 0] == 999  # No mutation.


def test_export_pages_and_category(tmp_path):
    assert ExportPages_Get(61) == ((0, 30), (30, 60), (60, 61))
    assert ExportPages_Get(61, 'Current View', current=(7, 12)) == ((7, 12),)
    assert ExportPages_Get(61, 'Full') == ((0, 61),)
    assert (
        PlotDirectory(tmp_path, 30, 60) / "Flight_Velocity_ENU_EN.png"
    ).parent.name == "Velocity"


@pytest.mark.parametrize(
    "duration,frames,speed",
    [(10, 300, 1), (30, 900, 1), (31, 900, 31 / 30), (60, 900, 2), (300, 900, 10)],
)
def test_gif_is_linear_complete_and_bounded(duration, frames, speed):
    times = np.array([0, duration * 1_000_000], dtype=np.uint64)
    position = TimeSeries(times, np.zeros((2,3)), 'm', 'position', 'test', np.ones(2,bool))
    attitude = TimeSeries(times, np.array([[1,0,0,0]]*2), '1', 'attitude', 'test', np.ones(2,bool))
    plain = FlightExporter._ReplayFrameTimestamps_Get(attitude, position, 0)
    events = FlightExporter._ReplayFrameTimestamps_Get(attitude, position, 0,
                                                       key_event_timestamps=(123456,))
    np.testing.assert_array_equal(plain, events)
    assert len(plain) == frames
    assert np.max(np.diff(plain)) - np.min(np.diff(plain)) <= 1
    assert plain[-1] >= duration * 1e6 * (1-1/frames) - 1
    delays = FlightExporter._ReplayFrameDurations_Get(frames, duration * 1000000)
    assert len(delays) == frames + 30
    assert sum(delays) == min(duration, 30) * 1000 + 1000
    metadata = GifMetadata_Get(0, duration)
    assert metadata['speed_factor'] == speed
    assert metadata['final_hold_frames'] == 30


def test_real_61_second_png_pages_and_unmodified_csv(tmp_path):
    from dataclasses import replace

    from PIL import Image

    from silverstar_flp.export.service import ExportLanguage, ExportOptions
    from tests.sslog_synthetic import AnalysisFlight_Build
    from tests.test_project_export import _DisplayDataset_Parse
    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / 'synthetic.bin'))
    origin = dataset.start_timestamp_us
    ending = next(
        r.timestamp_us for r in dataset.Records_Get("EVENT") if r.payload["event_id"] == 0x2A
    )
    scale = 61_000_000 / (ending-origin)
    def time_map(value):
        return origin + np.rint((np.asarray(value, dtype=np.int64)-origin)*scale).astype(np.int64)

    dataset = replace(
        dataset,
        records={
            name: tuple(
                replace(record, timestamp_us=int(time_map(record.timestamp_us)))
                for record in records
            )
            for name, records in dataset.records.items()
        },
        series={
            name: replace(series, timestamp_us=time_map(series.timestamp_us))
            for name, series in dataset.series.items()
        },
    )
    before = dataset.Series_Get('kf6.recorded.navigation.velocity_enu').values.copy()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            selected_channels=("kf6.recorded.navigation.velocity_enu",),
            include_plots=True,
            include_full_covariance_keyframes=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert not manifest.failures
    velocity = sorted(p for p in manifest.files if p.name.startswith('Flight_Velocity_ENU_'))
    assert len(velocity) == 3
    assert [p.name.rsplit('_', 1)[1] for p in velocity] == [
        '000000.000-000030.000.png', '000030.000-000060.000.png', '000060.000-000061.000.png']
    assert all(p.parent.name == 'Velocity' for p in velocity)
    assert len({Image.open(p).size for p in velocity}) == 1
    csv = next(p for p in manifest.files if p.suffix=='.csv')
    assert len(csv.read_text(encoding='utf-8-sig').splitlines()) == len(before)+2
    np.testing.assert_array_equal(
        dataset.Series_Get("kf6.recorded.navigation.velocity_enu").values, before
    )


def test_export_cancel_propagates_instead_of_becoming_item_failure(tmp_path):
    from silverstar_flp.core.context import TaskCancelledError, TaskContext
    from silverstar_flp.export.service import ExportOptions
    from tests.sslog_synthetic import AnalysisFlight_Build
    from tests.test_project_export import _DisplayDataset_Parse
    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path/'synthetic.bin'))
    context = TaskContext()
    context.Cancel_Request()
    with pytest.raises(TaskCancelledError):
        FlightExporter().export(
            dataset, tmp_path / "export", options=ExportOptions(), context=context
        )


def test_display_never_connects_reanchor_or_invalid_gap():
    from silverstar_flp.core.time_range import PlotArrays_Get
    time, values = PlotArrays_Get(np.arange(10), np.arange(10), breaks=[5])
    assert np.isnan(values).sum() == 1
    assert 5 in values and 4 in values
    x, y = PlotArrays_Get([0,1,2,10,11], [0,1,2,10,11])
    assert np.isnan(y).sum() == 1
    assert 10 in y
