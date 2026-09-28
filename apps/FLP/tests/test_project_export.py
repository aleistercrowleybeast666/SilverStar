from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.project import (
    Project_Load,
    Project_Save,
    ProjectDecoderProfile,
    ProjectDocument,
    _Reference_Encode,
)
from silverstar_flp.core.trajectory import TrajectoryPhaseSegments_Build, TrajectoryPhaseValues_Get
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_LANDING_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
)
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCacheReference
from silverstar_flp.export.plot_metadata import ChannelDisplayMetadata_Get
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportOptions,
    ExportTheme,
    FlightExporter,
    _PlotColor_Get,
)
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import AnalysisFlight_Build, StationaryFlight_Build


def _PlotBaseName_Get(path):
    return re.sub(r'_\d{6}\.\d{3}-\d{6}\.\d{3}(?=\.png$)', '', path.name)


def _DisplayDataset_Parse(path):
    dataset = Sslog0ParserPlugin().parse(path)
    series = dict(dataset.series)
    position = series.get("kf6.recorded.navigation.position_enu")
    if position is not None:
        series["kf6.recorded.attitude.q_nb"] = TimeSeries(
            position.timestamp_us, np.tile([1., 0., 0., 0.], (position.count, 1)),
            "1", "quaternion", "synthetic KF attitude", position.valid, ("W", "X", "Y", "Z"))
    return replace(dataset, series=series)


def _ProjectDocument_Build(
    log_path: Path,
    project_path: Path,
) -> ProjectDocument:
    package_hash = "2" * 64
    generation_hash = "3" * 64
    document = ProjectDocument(project_path=project_path)
    document.LogReference_Set(log_path)
    document.decoder_profile = ProjectDecoderProfile(
        source_reference=str(project_path.parent / "synthetic.ssdecoder"),
        cache_reference=DecoderProfileCacheReference(
            generation_profile_sha256=generation_hash,
            package_sha256=package_hash,
            relative_path=f"{generation_hash[:32]}/{package_hash}.ssdecoder",
        ),
        package_sha256=package_hash,
        generation_profile_sha256=generation_hash,
        record_catalog_sha256="4" * 64,
        record_catalog_hash_128="4" * 32,
        project_semantics_sha256="5" * 64,
        project_semantics_hash_128="5" * 32,
        container_plugin_id="silverstar.flight_log.container.0_0",
        container_plugin_version="0.0.0",
        exact_match_mode="exact_generation_profile",
    )
    return document


def test_project_contains_references_only_and_raw_log_remains_unchanged(tmp_path: Path) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_project_source.BIN")
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    project_path = tmp_path / "flight.ssflp"
    document = _ProjectDocument_Build(log_path, project_path)
    document.notes = "synthetic fixture"
    Project_Save(document, project_path)
    loaded = Project_Load(project_path)
    assert loaded.LogPath_Resolve() == log_path.resolve()
    assert loaded.decoder_profile is not None
    assert loaded.decoder_profile.exact_match_mode == "exact_generation_profile"
    project_text = project_path.read_text(encoding="utf-8")
    assert "SSLOG0" not in project_text
    assert '"log_reference"' in project_text
    assert '"log_references"' not in project_text
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before


def test_project_save_as_keeps_log_reference_resolvable(tmp_path: Path) -> None:
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    log_path = StationaryFlight_Build(source_folder / "SYNTHETIC_save_as_source.BIN")
    original_path = source_folder / "flight.ssflp"
    document = _ProjectDocument_Build(log_path, original_path)
    Project_Save(document, original_path)

    loaded = Project_Load(original_path)
    saved_as_path = tmp_path / "copy" / "flight_copy.ssflp"
    Project_Save(loaded, saved_as_path)

    saved_as = Project_Load(saved_as_path)
    assert saved_as.LogPath_Resolve() == log_path.resolve()
    assert Project_Load(original_path).LogPath_Resolve() == log_path.resolve()


def test_project_references_prefer_relative_paths_for_siblings_and_children(
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "Flight.ssflp"
    (tmp_path / "Logs").mkdir()
    log_path = StationaryFlight_Build(tmp_path / "Logs" / "SS0000.BIN")
    decoder_path = tmp_path / "Decoder" / "Flight.ssdecoder"
    decoder_path.parent.mkdir()
    decoder_path.write_bytes(b"decoder reference")
    document = _ProjectDocument_Build(log_path, project_path)
    assert document.decoder_profile is not None
    document.decoder_profile = replace(
        document.decoder_profile,
        source_reference=str(decoder_path),
    )
    Project_Save(document, project_path)
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    assert payload["log_reference"] == str(Path("Logs") / "SS0000.BIN")
    assert payload["decoder_profile"]["source_reference"] == str(
        Path("Decoder") / "Flight.ssdecoder"
    )


def test_project_reference_falls_back_to_absolute_when_not_relative(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "SS0000.BIN"
    project = tmp_path / "Flight.ssflp"
    original = Path.relative_to

    def fail_for_source(self, other, *args, **kwargs):
        if self == source.resolve():
            raise ValueError("different drive")
        return original(self, other, *args, **kwargs)

    monkeypatch.setattr(Path, "relative_to", fail_for_source)
    assert _Reference_Encode(source, project) == str(source.resolve())


def test_export_keeps_independent_channel_timestamps_and_language_suffix(
    tmp_path: Path,
) -> None:
    log_path = StationaryFlight_Build(tmp_path / "SYNTHETIC_export_source.BIN")
    dataset = _DisplayDataset_Parse(log_path)
    before = hashlib.sha256(log_path.read_bytes()).hexdigest()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "exported",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert manifest.files
    assert all("_EN" in path.name or "CSV_EN" in str(path.parent) for path in manifest.files)
    csv_files = [path for path in manifest.files if path.suffix.lower() == ".csv"]
    assert csv_files
    inertial_csv = next(path for path in csv_files if "inertial.increment.dt" in path.name)
    rows = inertial_csv.read_text(encoding="utf-8-sig").splitlines()
    assert "timestamp_us" in rows[1]
    assert len(rows) == 10  # metadata + header + eight real-rate samples
    assert hashlib.sha256(log_path.read_bytes()).hexdigest() == before


def test_follow_ui_exports_standard_plot_set_segmented_trajectory_and_combined_gif(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_export_analysis.BIN")
    )
    progress_updates: list[tuple[float, str]] = []
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "analysis_export",
        options=ExportOptions(
            language=ExportLanguage.FOLLOW_UI,
            ui_language="zh_CN",
            theme=ExportTheme.DARK,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=True,
            include_trajectory_3d=True,
            include_attitude_gif=True,
        ),
        context=TaskContext(
            progress_callback=lambda progress, code: progress_updates.append(
                (progress, code)
            )
        ),
    )
    assert manifest.language == ExportLanguage.ZH
    assert manifest.theme == ExportTheme.DARK
    assert not manifest.failures
    names = {_PlotBaseName_Get(path) for path in manifest.files}
    assert {
        "Flight_Velocity_ENU_ZH.png",
        "Flight_Position_ENU_ZH.png",
        "Flight_Acceleration_XYZ_ZH.png",
        "Flight_Angular_Rate_XYZ_ZH.png",
        "Flight_Attitude_ZH.png",
        "KF6_Recorded_Position_Std_1Sigma_ZH.png",
        "KF6_Recorded_Velocity_Std_1Sigma_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Position_EN_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Position_U_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Velocity_EN_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Velocity_U_ZH.png",
        "KF6_Recorded_Innovation_Barometer_ZH.png",
        "KF6_Recorded_NIS_GNSS_Position_EN_ZH.png",
        "KF6_Recorded_NIS_GNSS_Position_U_ZH.png",
        "KF6_Recorded_NIS_GNSS_Velocity_EN_ZH.png",
        "KF6_Recorded_NIS_GNSS_Velocity_U_ZH.png",
        "KF6_Recorded_NIS_Barometer_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Position_EN_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Position_U_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Velocity_EN_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Velocity_U_ZH.png",
        "KF6_Recorded_Measurement_Std_Barometer_ZH.png",
        "KF6_Recorded_Measurement_Update_ZH.png",
        "Trajectory_3D_ZH.png",
        "Flight_Replay_ZH.gif",
        "Export_Manifest_ZH.json",
    } <= names
    start = dataset.start_timestamp_us
    assert start is not None
    landing = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload["event_id"]) == 0x2A
    )
    mission_duration_us = landing - start
    main_frame_count = int(np.ceil(mission_duration_us * 30 / 1_000_000.0))
    gif_path = next(path for path in manifest.files if path.name == "Flight_Replay_ZH.gif")
    with Image.open(gif_path) as image:
        assert image.n_frames == main_frame_count + 30
        durations_ms: list[int] = []
        hold_frames: list[bytes] = []
        terminal_frame: bytes | None = None
        for frame_index in range(image.n_frames):
            image.seek(frame_index)
            durations_ms.append(int(image.info["duration"]))
            rendered = image.convert("RGB").tobytes()
            if frame_index == 0:
                assert image.convert("RGB").getpixel((0, 0)) == (11, 18, 32)
            if frame_index == main_frame_count:
                terminal_frame = rendered
            if frame_index >= main_frame_count:
                hold_frames.append(rendered)
        assert terminal_frame is not None
        assert len(hold_frames) == 30
        assert all(frame == terminal_frame for frame in hold_frames)
        expected_mission_ms = max(
            main_frame_count,
            int(round(mission_duration_us / 10_000.0)),
        ) * 10
        assert sum(durations_ms[:main_frame_count]) == expected_mission_ms
        assert sum(durations_ms[main_frame_count:]) == 1_000
    export_progress = [
        progress
        for progress, code in progress_updates
        if code == "export.running"
    ]
    assert export_progress
    assert np.isclose(export_progress[-1], 1.0)
    unit_steps = np.diff(np.asarray((0.0, *export_progress)))
    assert np.allclose(unit_steps, unit_steps[0])
    manifest_payload = json.loads(
        (tmp_path / "analysis_export" / "Export_Manifest_ZH.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest_payload["language"] == "zh_CN"
    assert manifest_payload["theme"] == "dark"
    assert manifest_payload["generated"]
    assert "skipped" in manifest_payload
    assert manifest_payload["failed"] == []
    assert manifest_payload["failures"] == []

    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    assert position is not None
    deploy = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload["event_id"]) == 0x29
    )
    segments = TrajectoryPhaseSegments_Build(position, (deploy,))
    pre, post = (TrajectoryPhaseValues_Get(segments, phase) for phase in (0, 1))
    assert pre.size > 0
    assert post.size > 0
    assert FlightExporter._Position_At(position, landing) is None
    assert np.allclose(
        FlightExporter._Position_NearEvent(position, landing),
        position.values[-1],
    )


def test_light_replay_gif_keeps_mission_time_and_equal_csv_frame_units(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_light_replay.BIN")
    )
    progress_updates: list[tuple[float, str]] = []
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "light_replay_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            theme=ExportTheme.LIGHT,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=True,
            selected_channels=("inertial.increment.dt",),
        ),
        context=TaskContext(
            progress_callback=lambda progress, code: progress_updates.append(
                (progress, code)
            )
        ),
    )
    assert not manifest.failures
    gif_path = tmp_path / "light_replay_export" / "GIF" / "Flight_Replay_EN.gif"
    with Image.open(gif_path) as image:
        frame_count = image.n_frames
        assert frame_count > 30
        image.seek(0)
        assert min(image.convert("RGB").getpixel((0, 0))) >= 250
    assert (
        tmp_path
        / "light_replay_export"
        / "CSV_EN"
        / "inertial.increment.dt_EN.csv"
    ).is_file()
    export_progress = [
        progress
        for progress, code in progress_updates
        if code == "export.running"
    ]
    assert len(export_progress) == frame_count + 3
    assert np.allclose(
        np.diff(np.asarray((0.0, *export_progress))),
        1.0 / len(export_progress),
    )


def test_plot_metadata_has_language_specific_titles(tmp_path: Path) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_plot_metadata.BIN")
    )
    series = dataset.Series_Get("kf6.recorded.navigation.velocity_enu")
    assert series is not None
    metadata = ChannelDisplayMetadata_Get("navigation.velocity_enu", series)
    assert metadata.Title_Get("zh_CN") == "飞行速度（ENU）"
    assert metadata.Title_Get("en_US") == "Flight Velocity (ENU)"
    assert "Flight" not in metadata.Title_Get("zh_CN")
    assert "飞行" not in metadata.Title_Get("en_US")
    low_level = dataset.Series_Get("inertial.increment.dt")
    assert low_level is not None
    generic = ChannelDisplayMetadata_Get("inertial.increment.dt", low_level)
    assert generic.Title_Get("zh_CN") == "时间（数据通道）"
    assert generic.Title_Get("en_US") == "Time (Data Channel)"
    assert "inertial" not in generic.Title_Get("zh_CN")


def test_export_3d_uses_unique_colors_rocket_mesh_and_mission_relative_points(
    tmp_path: Path,
) -> None:
    colors = [_PlotColor_Get(index) for index in range(32)]
    assert len(colors) == len(set(colors))

    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_export_3d_rules.BIN")
    )
    position = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    assert position is not None
    raw_before = np.asarray(position.values).copy()
    start = dataset.start_timestamp_us
    assert start is not None
    origin = FlightExporter._TrajectoryOrigin_Get(position, start)

    FlightExporter._Matplotlib_Configure()
    from matplotlib import pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    exporter = FlightExporter()
    trajectory_figure = plt.figure()
    trajectory_axis = trajectory_figure.add_subplot(111, projection="3d")
    exporter._Trajectory_AxisDraw(
        trajectory_axis,
        dataset,
        position,
        ExportLanguage.EN,
        ExportTheme.LIGHT,
    )
    labels = {artist.get_label() for artist in trajectory_axis.collections}
    assert "Mission Start" not in labels
    assert {"Deploy", "Landing"} <= labels
    assert "Current Position" not in labels
    ground_plane = next(
        artist
        for artist in trajectory_axis.collections
        if artist.get_gid() == "trajectory_ground_plane"
    )
    assert isinstance(ground_plane, Poly3DCollection)
    assert ground_plane.get_alpha() == 0.30
    deploy_collection = next(
        artist for artist in trajectory_axis.collections if artist.get_label() == "Deploy"
    )
    landing_collection = next(
        artist
        for artist in trajectory_axis.collections
        if artist.get_label() == "Landing"
    )
    from matplotlib.colors import to_rgba

    assert np.allclose(
        ground_plane.get_facecolor()[0],
        to_rgba("#75B5D8", alpha=0.30),
    )
    assert np.allclose(
        ground_plane.get_edgecolor()[0],
        to_rgba("#3F86AE"),
    )
    assert np.allclose(deploy_collection.get_facecolor()[0], to_rgba(TRAJECTORY_DEPLOY_COLOR))
    assert np.allclose(deploy_collection.get_edgecolor()[0], to_rgba(TRAJECTORY_DEPLOY_COLOR))
    assert isinstance(deploy_collection, Poly3DCollection)
    assert deploy_collection.get_alpha() == 1.0
    assert np.allclose(
        landing_collection.get_facecolor()[0],
        to_rgba(TRAJECTORY_LANDING_COLOR),
    )
    assert isinstance(landing_collection, Poly3DCollection)
    assert landing_collection.get_alpha() == 1.0
    assert trajectory_axis.lines[0].get_color() == TRAJECTORY_PRE_DEPLOY_COLOR
    assert trajectory_axis.lines[1].get_color() == TRAJECTORY_POST_DEPLOY_COLOR
    assert not trajectory_axis.texts
    first_pre = np.asarray(trajectory_axis.lines[0].get_data_3d()).T[0]
    assert np.allclose(first_pre, np.zeros(3), atol=1.0e-6)
    post_start = np.flatnonzero(
        position.valid & (position.timestamp_us >= np.uint64(start))
    )
    assert post_start.size
    assert np.allclose(origin, position.values[post_start[0]])
    assert np.array_equal(position.values, raw_before)
    plt.close(trajectory_figure)

    active_figure = plt.figure()
    active_axis = active_figure.add_subplot(111, projection="3d")
    exporter._Trajectory_AxisDraw(
        active_axis,
        dataset,
        position,
        ExportLanguage.EN,
        ExportTheme.LIGHT,
        current_timestamp_us=start + 130_000,
    )
    active_labels = {artist.get_label() for artist in active_axis.collections}
    assert "Current Position" in active_labels
    assert "Landing" not in active_labels
    current_collection = next(
        artist
        for artist in active_axis.collections
        if artist.get_label() == "Current Position"
    )
    assert np.allclose(
        current_collection.get_facecolor()[0],
        to_rgba(TRAJECTORY_POST_DEPLOY_COLOR),
    )
    plt.close(active_figure)

    attitude_figure = plt.figure()
    attitude_axis = attitude_figure.add_subplot(111, projection="3d")
    exporter._Attitude_AxisDraw(
        attitude_axis,
        np.asarray((1.0, 0.0, 0.0, 0.0)),
        ExportLanguage.EN,
        ExportTheme.DARK,
    )
    rocket_collection = next(
        collection
        for collection in attitude_axis.collections
        if isinstance(collection, Poly3DCollection)
    )
    actual_face_colors = {
        tuple(np.round(color, 6)) for color in rocket_collection.get_facecolor()
    }
    expected_face_colors = {
        tuple(np.round(to_rgba(color), 6)) for color in RocketFaceColors_Get("dark")
    }
    assert actual_face_colors == expected_face_colors
    assert np.allclose(attitude_axis.get_xlim3d(), (-2.5, 2.5))
    assert np.allclose(attitude_axis.get_ylim3d(), (-2.5, 2.5))
    assert np.allclose(attitude_axis.get_zlim3d(), (-2.5, 2.5))
    assert attitude_axis.elev == 18.0
    assert attitude_axis.azim == 35.0
    assert not attitude_axis.texts
    assert attitude_axis.get_legend() is None
    rotated_vertices = exporter._RocketVertices_Rotate(
        np.asarray((np.sqrt(0.5), 0.0, np.sqrt(0.5), 0.0))
    )
    assert np.allclose(np.mean(rotated_vertices[:4], axis=0), np.zeros(3))
    assert np.isclose(np.linalg.norm(rotated_vertices[4]), 2.2)
    plt.close(attitude_figure)

    dark_ground_figure = plt.figure()
    dark_ground_axis = dark_ground_figure.add_subplot(111, projection="3d")
    dark_ground = exporter._TrajectoryGroundPlane_Add(
        dark_ground_axis,
        (-2.0, 2.0, -3.0, 3.0),
        ExportTheme.DARK,
    )
    assert np.allclose(
        dark_ground.get_facecolor()[0],
        to_rgba("#4F86A6", alpha=0.30),
    )
    assert np.allclose(
        dark_ground.get_edgecolor()[0],
        to_rgba("#79B8D8"),
    )
    plt.close(dark_ground_figure)


def test_export_records_individual_failure_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = _DisplayDataset_Parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_partial_export.BIN")
    )
    exporter = FlightExporter()
    original = exporter._SeriesCsv_Write
    selected = (
        "inertial.increment.dt",
        "pure_ins.recorded.navigation.position_enu",
    )

    def selectively_fail(dataset_arg, channel_id, series, path):
        if channel_id == selected[0]:
            raise RuntimeError("intentional_csv_failure")
        original(dataset_arg, channel_id, series, path)

    monkeypatch.setattr(exporter, "_SeriesCsv_Write", selectively_fail)
    manifest = exporter.export(
        dataset,
        tmp_path / "partial_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
            selected_channels=selected,
        ),
    )
    assert len(manifest.failures) == 1
    assert manifest.failures[0].item == f"csv:{selected[0]}"
    assert any(selected[1] in path.name for path in manifest.files)
    payload = json.loads(
        (tmp_path / "partial_export" / "Export_Manifest_EN.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["failures"][0]["item_id"] == f"csv:{selected[0]}"
    assert payload["failures"][0]["localized_name"].startswith("CSV Data")
    assert payload["failures"][0]["exception_type"] == "RuntimeError"
    assert payload["failures"][0]["exception_message"] == "intentional_csv_failure"
    failure_report = (
        tmp_path / "partial_export" / "Export_Failures_EN.txt"
    )
    assert failure_report in manifest.files
    failure_text = failure_report.read_text(encoding="utf-8")
    assert f"csv:{selected[0]}" in failure_text
    assert "Type: RuntimeError" in failure_text
    assert "Message: intentional_csv_failure" in failure_text


def test_manifest_failure_still_writes_plain_text_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_failure_fallback.BIN")
    )
    exporter = FlightExporter()

    def gif_fail(*_args, **_kwargs) -> None:
        raise OSError("intentional_gif_failure")

    def manifest_fail(*_args, **_kwargs) -> None:
        raise RuntimeError("intentional_manifest_failure")

    monkeypatch.setattr(exporter, "_FlightReplayGif_Write", gif_fail)
    monkeypatch.setattr(exporter, "_Manifest_Write", manifest_fail)
    manifest = exporter.export(
        dataset,
        tmp_path / "failure_fallback_export",
        options=ExportOptions(
            language="en_US",
            theme="light",
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=True,
        ),
    )

    assert manifest.language == ExportLanguage.EN
    assert manifest.theme == ExportTheme.LIGHT
    assert {failure.item_id for failure in manifest.failures} == {
        "flight_replay_gif",
        "manifest",
    }
    assert manifest.ManifestPath_Get() is None
    report_path = (
        tmp_path
        / "failure_fallback_export"
        / "Export_Failures_EN.txt"
    )
    assert manifest.FailureReportPath_Get() == report_path
    text = report_path.read_text(encoding="utf-8")
    assert "flight_replay_gif" in text
    assert "Item: 3D Flight Replay GIF" in text
    assert "Type: OSError" in text
    assert "Message: intentional_gif_failure" in text
    assert "manifest" in text
    assert "Item: Export Manifest" in text
    assert "Type: RuntimeError" in text
    assert "Message: intentional_manifest_failure" in text


def test_bulk_export_keeps_selected_channel_csv_without_channel_png(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_pre_start_plot.BIN")
    )
    channel_id = "alignment.result.q_nb"
    series = dataset.Series_Get(channel_id)
    assert series is not None
    assert dataset.start_timestamp_us is not None
    assert int(series.timestamp_us[-1]) < dataset.start_timestamp_us

    manifest = FlightExporter().export(
        dataset,
        tmp_path / "pre_start_plot_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_plots=True,
            include_trajectory_3d=False,
            include_attitude_gif=False,
            selected_channels=(channel_id,),
        ),
    )

    assert not manifest.failures
    channel_plot = (
        tmp_path
        / "pre_start_plot_export"
        / "Plots_EN"
        / "Channel_alignment.result.q_nb_EN.png"
    )
    channel_csv = (
        tmp_path
        / "pre_start_plot_export"
        / "CSV_EN"
        / "alignment.result.q_nb_EN.csv"
    )
    assert channel_plot not in manifest.files
    assert not channel_plot.exists()
    assert channel_csv in manifest.files
    assert channel_csv.exists()


def test_full_p_keyframes_replace_upper_triangle_plot_and_keep_csv(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_full_p_keyframes.BIN",
            include_full_p=True,
        )
    )
    channel_id = "kf6.recorded.covariance.upper_triangle"
    covariance = dataset.Series_Get(channel_id)
    assert covariance is not None
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "full_p_keyframes_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_plots=True,
            include_trajectory_3d=False,
            include_attitude_gif=False,
            selected_channels=(channel_id,),
        ),
    )

    assert not manifest.failures
    full_p_path = (
        tmp_path
        / "full_p_keyframes_export"
        / "KF6_Full_P_Keyframes_EN.txt"
    )
    csv_path = (
        tmp_path
        / "full_p_keyframes_export"
        / "CSV_EN"
        / "kf6.recorded.covariance.upper_triangle_EN.csv"
    )
    upper_triangle_plot = (
        tmp_path
        / "full_p_keyframes_export"
        / "Plots_EN"
        / "Channel_kf6.recorded.covariance.upper_triangle_EN.png"
    )
    assert full_p_path in manifest.files
    assert csv_path in manifest.files
    assert upper_triangle_plot not in manifest.files
    assert not upper_triangle_plot.exists()

    deploy_timestamp = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload["event_id"]) == 0x29
    )
    eligible = np.flatnonzero(
        covariance.valid
        & (covariance.timestamp_us <= np.uint64(deploy_timestamp))
        & np.all(np.isfinite(covariance.values), axis=1)
    )
    assert eligible.size
    selected_timestamp = int(covariance.timestamp_us[eligible[-1]])
    text = full_p_path.read_text(encoding="utf-8")
    assert "State vector order and physical units" in text
    assert "0: pE [m]" in text
    assert "5: vU [m/s]" in text
    assert f"Event timestamp [us]: {deploy_timestamp}" in text
    assert f"Selected P timestamp [us]: {selected_timestamp}" in text
    assert selected_timestamp <= deploy_timestamp
    assert "Full P matrix (6 x 6):" in text
    assert "[START]" in text
    assert (
        "START uses the diagonal P0 reconstructed from "
        "INITIAL_STATE.p0_diagonal"
    ) in text
    assert f"Selected P timestamp [us]: {dataset.start_timestamp_us}" in text
    assert "4.00000000000000000e+00" in text
    assert "9.00000000000000000e+00" in text


def test_full_p_keyframes_use_analysis_end_when_landing_is_absent(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_full_p_without_landing.BIN",
            include_full_p=True,
            include_landing_event=False,
        )
    )
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "full_p_without_landing_export",
        options=ExportOptions(
            language=ExportLanguage.ZH,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )

    assert not manifest.failures
    full_p_path = (
        tmp_path
        / "full_p_without_landing_export"
        / "KF6_Full_P_Keyframes_ZH.txt"
    )
    text = full_p_path.read_text(encoding="utf-8")
    assert "完整协方差矩阵 P 关键帧" in text
    assert "未找到 LANDING；事件时刻使用分析结束时刻" in text
    assert "数据源: 飞控记录（Recorded）" in text
    assert "实际采用的 P 时间戳 [us]: 1160000" in text


def test_gif_uses_constant_speed_without_key_event_time_warp() -> None:
    timestamps = np.asarray(
        [1_000_000 + index * index * 1_000 for index in range(100)],
        dtype=np.uint64,
    )
    attitude = TimeSeries(
        timestamp_us=timestamps,
        values=np.tile(np.asarray((1.0, 0.0, 0.0, 0.0)), (timestamps.size, 1)),
        unit="1",
        quantity="quaternion",
        source="synthetic",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=("W", "X", "Y", "Z"),
    )
    position = TimeSeries(
        timestamp_us=timestamps,
        values=np.column_stack(
            (
                np.linspace(0.0, 1.0, timestamps.size),
                np.linspace(0.0, 2.0, timestamps.size),
                np.linspace(0.0, 3.0, timestamps.size),
            )
        ),
        unit="m",
        quantity="position",
        source="synthetic",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=("E", "N", "U"),
    )
    targets = FlightExporter._ReplayFrameTimestamps_Get(
        attitude,
        position,
        1_000_000,
    )
    expected_count = int(
        np.ceil((int(timestamps[-1]) - 1_000_000) * 30 / 1_000_000.0)
    )
    assert targets.size == expected_count
    assert targets[0] == timestamps[0]
    assert targets[-1] < timestamps[-1]
    intervals = np.diff(targets.astype(np.int64))
    assert int(intervals.max() - intervals.min()) <= 1
    cropped_targets = FlightExporter._ReplayFrameTimestamps_Get(
        attitude,
        position,
        1_000_000,
        end_timestamp_us=int(timestamps[50]),
    )
    cropped_duration_us = int(timestamps[50]) - 1_000_000
    assert cropped_targets.size == int(
        np.ceil(cropped_duration_us * 30 / 1_000_000.0)
    )
    assert cropped_targets[-1] < timestamps[50]

    deploy_timestamp = int(timestamps[37])
    keyed_targets = FlightExporter._ReplayFrameTimestamps_Get(
        attitude,
        position,
        1_000_000,
        end_timestamp_us=int(timestamps[-1]),
        key_event_timestamps=(1_000_000, deploy_timestamp, int(timestamps[-1])),
    )
    assert keyed_targets.size == expected_count
    np.testing.assert_array_equal(keyed_targets, targets)
    render_targets = np.append(keyed_targets, timestamps[-1])
    event_indices = FlightExporter._ReplayEventFrameIndices_Get(
        render_targets,
        {
            "deploy": deploy_timestamp,
            "landing": int(timestamps[-1]),
        },
    )
    samples = FlightExporter()._ReplayFrameSamples_Precompute(
        attitude,
        timestamps,
        np.asarray(position.values, dtype=np.float64),
        render_targets,
        deploy_timestamp,
        int(timestamps[-1]),
        event_indices,
    )
    deploy_frame = event_indices["deploy"]
    assert samples[deploy_frame].deploy_visible
    if deploy_frame > 0:
        assert not samples[deploy_frame - 1].deploy_visible
    assert samples[deploy_frame].current_color == TRAJECTORY_POST_DEPLOY_COLOR
    assert samples[-1].landing_visible

    mission_duration_us = int(timestamps[-1]) - 1_000_000
    durations_ms = FlightExporter._ReplayFrameDurations_Get(
        keyed_targets.size,
        mission_duration_us,
    )
    assert len(durations_ms) == keyed_targets.size + 30
    expected_mission_ms = max(
        keyed_targets.size,
        int(round(mission_duration_us / 10_000.0)),
    ) * 10
    assert sum(durations_ms[: keyed_targets.size]) == expected_mission_ms
    assert sum(durations_ms[keyed_targets.size :]) == 1_000
