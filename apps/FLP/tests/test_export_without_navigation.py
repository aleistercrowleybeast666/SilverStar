"""Export real available data without inventing a Recorded navigation solution."""

import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.decoder_profiles import DecoderProfileCache
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import Event_Payload, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    DESCRIPTOR_RECORD_TYPE,
    IMU_RECORD_TYPE,
    START_TIMESTAMP_US,
    _CalibrationNonePayload_Build,
    _DescriptorPayload_Build,
    _ImuPayload_Build,
    _Package_Write,
)


def options(**changes):
    return replace(
        ExportOptions(
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        **changes,
    )


@pytest.fixture
def raw_dataset(tmp_path):
    package, hashes = _Package_Write(tmp_path / "raw.ssdecoder")
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3
    )
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 1, (1.0, 2.0, 3.0)),
        START_TIMESTAMP_US + 1,
    )
    log = builder.File_Write(tmp_path / "raw.sslog")
    before = {p: sha256(p.read_bytes()).hexdigest() for p in (log, package)}
    result = LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(tmp_path / "cache")
    ).Open(LogOpenRequest(log_path=log, decoder_package_path=package))
    assert result.match_mode == "exact_generation_profile"
    assert not ChannelResolver(result.dataset, ReplayResultStore()).Source_Get().available
    yield result.dataset
    assert all(sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())


@pytest.mark.parametrize("csv", (False, True))
def test_exact_raw_log_allows_audit_and_selected_real_csv(raw_dataset, tmp_path, csv):
    channel = "IMU_NATIVE:1:0.accel_b_mps2"
    original = raw_dataset.Series_Get(channel)
    manifest = FlightExporter().export(
        raw_dataset,
        tmp_path / "export",
        options=options(include_csv=csv, selected_channels=(channel,)),
    )
    assert not manifest.failures
    audit = json.loads(manifest.ManifestPath_Get().read_text())
    assert audit["resolved_source_id"] == "recorded"
    assert audit["active_recorded_solution"] is None
    assert audit["active_source_available"] is False
    assert audit["shared_recorded_data_only"] is True
    assert audit["decoder_profile"]["match_mode"] == "exact_generation_profile"
    generated = [row.item_id for row in manifest.generated]
    assert ("csv:" + channel in generated) == csv
    assert raw_dataset.Series_Get(channel) is original
    assert not any(".recorded.navigation." in name for name in raw_dataset.series)


def test_missing_navigation_products_are_skipped_without_calling_writers(
    raw_dataset, tmp_path, monkeypatch
):
    exporter = FlightExporter()

    def forbidden(*args, **kwargs):
        pytest.fail("Missing trajectory must not be drawn or fabricated")

    monkeypatch.setattr(exporter, "_Trajectory_Write", forbidden)
    monkeypatch.setattr(exporter, "_FlightReplayGif_Write", forbidden)
    monkeypatch.setattr(exporter, "_HorizontalTrajectory_Write", forbidden)
    manifest = exporter.export(
        raw_dataset,
        tmp_path / "missing-nav",
        options=options(include_plots=True, include_trajectory_3d=True, include_attitude_gif=True),
    )
    assert not manifest.failures
    skipped = {row.item_id: row.skipped_reason for row in manifest.skipped}
    assert (
        skipped["trajectory_3d"]
        == skipped["flight_replay_gif"]
        == "navigation_solution_unavailable"
    )
    assert any(
        key.startswith("horizontal_trajectory:") and value == "navigation_solution_unavailable"
        for key, value in skipped.items()
    )
    assert not any(p.suffix in (".gif",) or "Trajectory" in str(p) for p in manifest.files)


@pytest.mark.parametrize("source", ("replay:deleted", "recorded:eskf15", "recorded:unknown"))
def test_unavailable_explicit_source_is_not_replaced(raw_dataset, tmp_path, source):
    output = tmp_path / "unavailable"
    with pytest.raises(ValueError, match="export_source_unavailable"):
        FlightExporter().export(
            raw_dataset, output, options=options(source_mode="explicit", source_id=source)
        )
    assert not output.exists()


@pytest.mark.parametrize("source,allowed", (("recorded", True), ("replay:deleted", False)))
def test_gui_and_backend_share_source_admission(
    raw_dataset, tmp_path, monkeypatch, source, allowed
):
    import silverstar_flp.ui.main_window as window_module

    store = ReplayResultStore()
    errors = []
    completed = []
    monkeypatch.setattr(window_module, "FunctionWorker", lambda callback: callback)

    def start(callback, result, error, cancelled):
        from silverstar_flp.core.context import TaskContext

        completed.append(callback(TaskContext()))

    port = SimpleNamespace(
        _dataset=raw_dataset,
        _registry=builtin_registry(),
        _replay_store=store,
        _channel_resolver=ChannelResolver(raw_dataset, store),
        explorer_page=SimpleNamespace(ExportChannels_Get=lambda: ()),
        _theme="light",
        time_range=SimpleNamespace(
            controller=SimpleNamespace(model=SimpleNamespace(start=0.0, end=1.0))
        ),
        export_dialog=SimpleNamespace(Result_Error=errors.append),
        _Task_Start=start,
        _Export_ResultSet=lambda value: None,
    )
    window_module.MainWindow._Export_Start(
        port, tmp_path / "gui-export", options(source_mode="explicit", source_id=source)
    )
    assert bool(completed) == allowed
    assert bool(errors) != allowed
    if completed:
        assert not completed[0].failures and completed[0].ManifestPath_Get().is_file()


def test_gui_offers_raw_recorded_choice_without_changing_primary(raw_dataset, tmp_path):
    import silverstar_flp.ui.main_window as window_module
    from silverstar_flp.core.i18n import Translator

    store = ReplayResultStore()
    store.ActiveSource_Restore("replay:deleted")
    choices = []
    dialog = SimpleNamespace(
        OutputDirectory_Set=lambda path: None,
        Sources_Set=choices.extend,
        Result_Clear=lambda: None,
        Range_Set=lambda *args: None,
        open=lambda: None,
    )
    port = SimpleNamespace(
        _dataset=raw_dataset,
        _replay_store=store,
        _channel_resolver=ChannelResolver(raw_dataset, store),
        _translator=Translator("en_US"),
        export_dialog=dialog,
        _ExportDirectory_Default=lambda: tmp_path / "export",
        time_range=SimpleNamespace(
            controller=SimpleNamespace(
                model=SimpleNamespace(start=0.0, end=1.0, mission_duration=1.0)
            )
        ),
    )
    window_module.MainWindow._ExportDialog_Show(port)
    assert [source for source, _ in choices] == ["recorded"]
    assert store.ActiveSource_Get().source_id == "replay:deleted"


@pytest.mark.parametrize("empty", (False, True))
def test_empty_or_invalid_position_never_produces_a_trajectory(raw_dataset, tmp_path, empty):
    import numpy as np

    from silverstar_flp.core.dataset import TimeSeries

    count = 0 if empty else 1
    series = TimeSeries(
        np.full(count, START_TIMESTAMP_US, dtype=np.uint64),
        np.full((count, 3), np.nan),
        "m",
        "position",
        "explicit invalid test fixture",
        np.zeros(count, dtype=bool),
        ("E", "N", "U"),
    )
    dataset = replace(
        raw_dataset, series={**raw_dataset.series, "kf6.recorded.navigation.position_enu": series}
    )
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "invalid-position",
        options=options(include_trajectory_3d=True, include_attitude_gif=True),
    )
    assert not manifest.failures
    assert {row.item_id for row in manifest.skipped} == {"trajectory_3d", "flight_replay_gif"}
    assert all(row.skipped_reason == "navigation_solution_unavailable" for row in manifest.skipped)
    assert not any(p.suffix == ".gif" or "Trajectory" in str(p) for p in manifest.files)


def test_available_recorded_source_keeps_its_identity(tmp_path):
    from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
    from tests.sslog_synthetic import AnalysisFlight_Build

    dataset = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "available.BIN"))
    store = ReplayResultStore()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "available-export",
        replay_store=store,
        options=options(source_mode="explicit", source_id="recorded:kf6"),
    )
    audit = json.loads(manifest.ManifestPath_Get().read_text())
    assert not manifest.failures
    assert audit["resolved_source_id"] == "recorded:kf6"
    assert audit["active_source_available"] is True
    assert audit["shared_recorded_data_only"] is False
    assert store.ActiveSource_Get().source_id == "recorded"
