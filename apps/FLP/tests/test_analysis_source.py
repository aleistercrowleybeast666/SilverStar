from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_flp.core.analysis_source import (
    AnalysisSourceKind,
    ChannelResolver,
    ReplayResultStore,
)
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import (
    ReplayFidelity,
    ReplayMode,
    ReplayRequest,
)
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import AnalysisFlight_Build, StationaryFlight_Build


def test_recomputed_and_what_if_results_coexist_and_resolve_independently(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_replay_store.BIN")
    )
    from tests.parameter_fixtures import SyntheticParameters_Attach
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "parameters")
    plugin = PureInsAlgorithmPlugin()
    recomputed = plugin.run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.RECORDED_CONFIGURATION,
            input_source="recorded_inertial_increment",
        ),
    )
    what_if = plugin.run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF,
            input_source="recorded_inertial_increment",
            parameters={"gravity_mps2": 9.7},
        ),
    )

    store = ReplayResultStore()
    with pytest.raises(ValueError, match="legacy_integrity_assistance_result_unsupported"):
        store.Result_Add(replace(recomputed, provenance="Integrity-assisted KF6"))
    recorded_entry = store.Result_Add(recomputed, algorithm_name="Pure INS")
    what_if_entry = store.Result_Add(what_if, algorithm_name="Pure INS")
    assert len(store.Entries_Get()) == 2
    assert recorded_entry.result_id == "pure_ins:recomputed:1"
    assert what_if_entry.result_id == "pure_ins:what_if:1"
    assert recorded_entry.channels is not what_if_entry.channels
    assert store.ActiveSource_Set(what_if_entry.source_id)
    assert store.ActiveSource_Get().kind == AnalysisSourceKind.WHAT_IF

    resolver = ChannelResolver(dataset, store)
    active_position = resolver.Series_Get("navigation.position_enu")
    assert active_position is what_if.channels["navigation.position_enu"]
    recorded_position = resolver.RecordedSeries_Get("navigation.position_enu")
    assert recorded_position is dataset.Series_Get("pure_ins.recorded.navigation.position_enu")
    explorer_names = resolver.ExplorerChannels_Get()
    assert any(
        name.endswith("/ navigation.position_enu") and "Pure INS / Recomputed #1" in name
        for name in explorer_names
    )
    assert any(
        name.endswith("/ navigation.position_enu") and "Pure INS / What-if #1" in name
        for name in explorer_names
    )

    export_directory = tmp_path / "active_source_export"
    FlightExporter().export(
        dataset,
        export_directory,
        options=ExportOptions(
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )
    manifest = json.loads(
        (export_directory / "Export_Manifest_ZH.json").read_text(encoding="utf-8")
    )
    assert manifest["active_analysis_source"] == what_if_entry.source_id
    assert manifest["active_source_kind"] == "what_if"

    recorded_export = tmp_path / "recorded_export"
    FlightExporter().export(
        dataset,
        recorded_export,
        options=ExportOptions(
            source_mode="explicit",
            source_id=ReplayResultStore.RECORDED_SOURCE_ID,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )
    recorded_manifest = json.loads(
        (recorded_export / "Export_Manifest_ZH.json").read_text(encoding="utf-8")
    )
    assert recorded_manifest["requested_source_mode"] == "explicit"
    assert recorded_manifest["resolved_source_id"] == "recorded"
    assert recorded_manifest["resolved_result_id"] is None
    assert recorded_manifest["replay_results"] == []
    assert recorded_manifest["requested_time_range"]["page_mode"] == "30"
    assert recorded_manifest["resolved_time_range"]["pages_s"]
    assert "manifest" in recorded_manifest["resolved_topics"]
    assert recorded_manifest["requested_topics"]["selected_channels"] == []
    assert store.ActiveSource_Get().source_id == what_if_entry.source_id

    selected_export = tmp_path / "selected_recompute_export"
    FlightExporter().export(
        dataset,
        selected_export,
        options=ExportOptions(
            source_mode="explicit",
            source_id=recorded_entry.source_id,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )
    selected_manifest = json.loads(
        (selected_export / "Export_Manifest_ZH.json").read_text(encoding="utf-8")
    )
    assert selected_manifest["resolved_source_id"] == recorded_entry.source_id
    assert selected_manifest["resolved_result_id"] == recorded_entry.result_id
    assert len(selected_manifest["replay_results"]) == 1
    assert store.ActiveSource_Get().source_id == what_if_entry.source_id


def test_recorded_navigation_resolver_prefers_kf6(tmp_path: Path) -> None:
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_resolver_kf6.BIN")
    )
    resolver = ChannelResolver(dataset, ReplayResultStore())
    assert resolver.RecordedNavigationSource_Get() == "KF_6"
    assert resolver.RecordedSeries_Get("navigation.position_enu") is dataset.Series_Get(
        "kf6.recorded.navigation.position_enu"
    )
    assert resolver.RecordedNavigationSources_Get() == ("Pure INS", "KF_6")
    layers = resolver.RecordedSolutionLayers_Get("navigation.position_enu")
    assert tuple(layer.solution_id for layer in layers) == ("pure_ins", "kf6")
    assert layers[0].series is dataset.Series_Get(
        "pure_ins.recorded.navigation.position_enu"
    )
    assert layers[1].series is dataset.Series_Get(
        "kf6.recorded.navigation.position_enu"
    )
    estimator_sources = resolver.EstimatorSources_Get()
    assert len(estimator_sources) == 1
    assert estimator_sources[0].algorithm_id == "silverstar.algorithm.kf6"


def test_only_complete_successful_replay_results_are_selectable(
    tmp_path: Path,
) -> None:
    dataset = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_source_readiness.BIN")
    )
    result = PureInsAlgorithmPlugin().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    store = ReplayResultStore()
    ready = store.Result_Add(result, algorithm_name="Pure INS")
    unavailable = store.Result_Add(
        replace(result, fidelity=ReplayFidelity.UNAVAILABLE),
        algorithm_name="Pure INS",
    )
    incomplete = store.Result_Add(
        replace(
            result,
            channels={"attitude.q_nb": result.channels["attitude.q_nb"]},
        ),
        algorithm_name="Pure INS",
    )
    missing = store.Result_Add(
        replace(result, missing_inputs=("IMU_CORRECTED",)),
        algorithm_name="Pure INS",
    )

    assert ready.analysis_ready
    assert not unavailable.analysis_ready
    assert not incomplete.analysis_ready
    assert not missing.analysis_ready
    sources = store.Sources_Get()
    assert sources[0].source_id == ReplayResultStore.RECORDED_SOURCE_ID
    assert tuple(source.source_id for source in sources[1:]) == (ready.source_id,)
    assert store.ActiveSource_Set(ready.source_id)
    assert not store.ActiveSource_Set(unavailable.source_id)
    assert not store.ActiveSource_Set(incomplete.source_id)
    assert not store.ActiveSource_Set(missing.source_id)
    assert store.ActiveSource_Set(ReplayResultStore.RECORDED_SOURCE_ID)
