from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.mission import (
    EstimatedLandingOnset_Get,
    FlightDisplayBounds_Get,
    MissionReplayBounds_Get,
    MissionReplayEndReason,
)
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.ui.pages.charts import FlightPage


def Dataset_Build(tmp_path: Path, with_complete=True):
    source = tmp_path / "landing.bin"
    source.write_bytes(b"synthetic")
    times = np.arange(14, dtype=np.uint64) * 1_000_000
    valid = np.ones(len(times), dtype=bool)
    event_start = DecodedRecord(
        1, "EVENT", 1, 0, 1, 0, 0,
        {"event_id": 0x03, "event_name": "START", "arg0": 0, "arg1": 0}, 0,
    )
    event_landing = DecodedRecord(
        1, "EVENT", 1, 0, 2, 13_000_000, 0,
        {"event_id": 0x2A, "event_name": "LANDING", "arg0": 0, "arg1": 0}, 0,
    )
    diagnostic = DecodedRecord(
        2, "LANDING_DIAGNOSTIC", 1, 0, 3, 13_000_000, 0,
        {"transition": 3, "candidate_start_timestamp_us": 10_000_000,
         "evaluation_timestamp_us": 13_000_000}, 0,
    )
    return FlightDataset(
        source, source.stat().st_size, {}, ParserDiagnostics(),
        {"EVENT": (event_start, event_landing),
         "LANDING_DIAGNOSTIC": (diagnostic,) if with_complete else ()},
        {
            "kf6.recorded.navigation.position_enu": TimeSeries(
                times, np.column_stack((times.astype(float) * 1e-6,
                                        np.zeros(len(times)), np.zeros(len(times)))),
                "m", "position", "test", valid, ("E", "N", "U")),
            "kf6.recorded.navigation.velocity_enu": TimeSeries(
                times, np.tile((1., 0., 0.), (len(times), 1)),
                "m/s", "velocity", "test", valid, ("E", "N", "U")),
            "kf6.recorded.attitude.q_nb": TimeSeries(
                times, np.tile((1., 0., 0., 0.), (len(times), 1)),
                "1", "quaternion", "test", valid, ("W", "X", "Y", "Z")),
        },
    )


def test_candidate_onset_is_visual_only_and_falls_back(tmp_path):
    dataset = Dataset_Build(tmp_path)
    mission = MissionReplayBounds_Get(dataset)
    flight = FlightDisplayBounds_Get(dataset, mission)
    assert EstimatedLandingOnset_Get(dataset) == 10_000_000
    assert mission.end_timestamp_us == 13_000_000
    assert flight.end_timestamp_us == 10_000_000
    assert dataset.Records_Get("EVENT")[-1].timestamp_us == 13_000_000
    assert dataset.Series_Get("kf6.recorded.navigation.position_enu").count == 14
    without_complete = Dataset_Build(tmp_path, with_complete=False)
    assert EstimatedLandingOnset_Get(without_complete) == 13_000_000
    bounds = FlightDisplayBounds_Get(
        without_complete, MissionReplayBounds_Get(without_complete)
    )
    assert bounds.end_timestamp_us == 13_000_000


def test_flight_page_and_export_use_onset_while_state_retains_confirmed(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None
    dataset = Dataset_Build(tmp_path)
    resolver = ChannelResolver(dataset, ReplayResultStore())
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    assert page._mission_bounds.end_timestamp_us == 10_000_000
    assert page._trajectory_phase_segments[-1].timestamp_us[-1] <= 10_000_000
    page.TimeRange_Set(0, 13_000_000)
    assert page._end_timestamp_us == 10_000_000
    assert resolver.MissionReplayBounds_Get().end_timestamp_us == 13_000_000
    page.close()
    seen = {}
    def gif(_dataset, _attitude, _position, path, *_args, **kwargs):
        bounds = kwargs["mission_bounds"]
        seen["gif"] = (bounds.start_timestamp_us, bounds.end_timestamp_us,
                       bounds.end_reason)
        path.write_bytes(b"GIF89a;")
    def trajectory(_dataset, _position, path, *_args, **kwargs):
        seen["trajectory"] = kwargs["mission_bounds"].end_timestamp_us
        path.write_bytes(b"PNG")
    exporter = FlightExporter()
    with patch.object(exporter, "_FlightReplayGif_Write", side_effect=gif), patch.object(
        exporter, "_Trajectory_Write", side_effect=trajectory
    ):
        manifest = exporter.export(
            dataset, tmp_path / "export",
            options=ExportOptions(include_overview=False, include_diagnostics=False,
                                  include_events=False, include_csv=False,
                                  include_full_covariance_keyframes=False,
                                  include_plots=False, include_trajectory_3d=True,
                                  include_attitude_gif=True),
        )
    assert not manifest.failures
    assert seen == {
        "gif": (0, 10_000_000, MissionReplayEndReason.SOURCE_END),
        "trajectory": 10_000_000,
    }


def test_gif_current_view_after_onset_shifts_inside_flight(tmp_path):
    dataset = Dataset_Build(tmp_path)
    seen = {}

    def gif(_dataset, _attitude, _position, path, *_args, **kwargs):
        seen["bounds"] = kwargs["mission_bounds"]
        path.write_bytes(b"GIF89a;")

    exporter = FlightExporter()
    with patch.object(exporter, "_FlightReplayGif_Write", side_effect=gif):
        manifest = exporter.export(
            dataset, tmp_path / "late_view_export",
            options=ExportOptions(
                include_overview=False, include_diagnostics=False,
                include_events=False, include_csv=False,
                include_full_covariance_keyframes=False,
                include_plots=False, include_trajectory_3d=False,
                include_attitude_gif=True, current_range=(11, 13),
            ),
        )
    assert not manifest.failures
    bounds = seen["bounds"]
    assert bounds.start_timestamp_us == 8_000_000
    assert bounds.end_timestamp_us == 10_000_000
    assert bounds.end_reason == MissionReplayEndReason.SOURCE_END
