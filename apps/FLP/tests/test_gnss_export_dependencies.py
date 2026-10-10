"""Ordinary export regressions for independent GNSS diagnostic inputs."""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_gnss_integrity import CurrentDataset_Build

HORIZONTAL = "GNSS_Horizontal_Consistency_Error"
VERTICAL = "GNSS_Vertical_Consistency_Error"
RECEIVER = "GNSS_Receiver_Information"


@pytest.fixture
def dataset(tmp_path):
    parsed = Sslog0ParserPlugin().parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC.BIN"))
    current = CurrentDataset_Build()
    origin = parsed.start_timestamp_us
    records = dict(parsed.records)
    for name in ("GNSS_NATIVE", "NAV_QUALITY"):
        rows = []
        for record in current.Records_Get(name):
            timestamp = origin + record.timestamp_us
            payload = {**record.payload}
            if name == "GNSS_NATIVE":
                payload["sample_timestamp_us"] = timestamp
                payload["receive_timestamp_us"] = timestamp
            else:
                payload["evaluation_us"] = timestamp
            rows.append(replace(record, timestamp_us=timestamp, payload=payload))
        records[name] = tuple(rows)
    initial = parsed.initial_state
    records["INITIAL_STATE"] = (replace(initial, payload={
        **initial.payload, **current.initial_state.payload,
    }),)
    # Complete this explicitly synthetic display dataset's selected solution.
    series = {**parsed.series, "kf6.recorded.attitude.q_nb":
              parsed.series["pure_ins.recorded.attitude.q_nb"]}
    return replace(parsed, records=records, series=series)


def Export_Run(dataset, tmp_path, *, store=None, source_id="recorded:kf6"):
    return FlightExporter().export(dataset, tmp_path / "ordinary", replay_store=store,
        options=ExportOptions(language=ExportLanguage.EN, include_overview=False,
            include_diagnostics=False, include_events=False, include_csv=False,
            include_full_covariance_keyframes=False, include_attitude_gif=False,
            include_trajectory_3d=False, page_mode="Full", source_mode="explicit",
            source_id=source_id))


def GnssProducts_Get(manifest):
    prefix = "gnss_integrity:"
    generated = {item.item_id.split(":")[1]: item.path for item in manifest.generated
                 if item.item_id.startswith(prefix)}
    skipped = {item.item_id.split(":")[1]: item.skipped_reason for item in manifest.skipped
               if item.item_id.startswith(prefix)}
    assert not manifest.failures
    assert all(path.stat().st_size > 1000 for path in generated.values())
    assert set(generated).isdisjoint(skipped)
    return generated, skipped


@pytest.mark.parametrize("quality,native", [(True, False), (False, True),
                                          (False, False), (True, True)])
def test_ordinary_export_records_each_independent_input(dataset, tmp_path, quality, native):
    removed = ({"NAV_QUALITY"} if not quality else set()) | (
        {"GNSS_NATIVE"} if not native else set())
    isolated = replace(dataset, records={k: v for k, v in dataset.records.items()
                                        if k not in removed})
    generated, skipped = GnssProducts_Get(Export_Run(isolated, tmp_path))
    assert (HORIZONTAL in generated) == quality
    assert (VERTICAL in generated) == native
    assert (RECEIVER in generated) == native
    if not quality:
        assert skipped[HORIZONTAL] == "recorded_revision3_nav_quality_unavailable"
    if not native:
        assert skipped[VERTICAL] == skipped[RECEIVER] == "gnss_native_unavailable"


@pytest.mark.parametrize("mapped_evidence", [True, False])
def test_ordinary_recomputed_export_uses_selected_evidence_without_native(
        dataset, tmp_path, monkeypatch, mapped_evidence):
    isolated = replace(dataset, records={k: v for k, v in dataset.records.items()
                                        if k != "GNSS_NATIVE"})
    evidence = [dict(evaluation_us=dataset.start_timestamp_us + 10_000,
                     end_us=486_114_000_000, valid=True, closure_en=(6., 8.),
                     variance_scale=1.7)] if mapped_evidence else []
    channels = {name.replace(".recorded.", "."): series
                for name, series in dataset.series.items() if name.startswith("kf6.recorded.")}
    channels.update({name: dataset.series["kf6.recorded." + name] for name in (
        "attitude.q_nb", "navigation.position_enu", "navigation.velocity_enu")})
    result = AlgorithmResult("silverstar.algorithm.kf6", "synthetic-display-input",
        "corrected_imu", {"gnss_integrity_enable": True}, ReplayFidelity.APPROXIMATE,
        (), (), channels, {"window_evidence": evidence}, "Offline")
    store = ReplayResultStore()
    entry = store.Result_Add(result)
    captured = []
    original = FlightExporter._GnssIntegrityPlot_Write

    def capture(self, dataset, trace, kind, *args, **kwargs):
        if kind == HORIZONTAL:
            captured.append(trace)
        return original(self, dataset, trace, kind, *args, **kwargs)

    monkeypatch.setattr(FlightExporter, "_GnssIntegrityPlot_Write", capture)
    generated, skipped = GnssProducts_Get(Export_Run(
        isolated, tmp_path, store=store, source_id=entry.source_id))
    assert skipped[VERTICAL] == skipped[RECEIVER] == "gnss_native_unavailable"
    if mapped_evidence:
        assert HORIZONTAL in generated and len(captured) == 1
        assert captured[0].source_kind == "recomputed"
        np.testing.assert_array_equal(captured[0].timestamp_us,
                                      [dataset.start_timestamp_us + 10_000])
        np.testing.assert_array_equal(captured[0].closure_norm_m, [10.])
        np.testing.assert_array_equal(captured[0].variance_scale, [1.7])
    else:
        assert not captured and HORIZONTAL not in generated
        assert skipped[HORIZONTAL] == "recomputed_window_evidence_unavailable"


def test_ordinary_vertical_missing_origin_does_not_suppress_other_gnss_plots(dataset, tmp_path):
    invalid = replace(dataset.initial_state, payload={
        **dataset.initial_state.payload, "origin_valid_flags": 0,
    })
    isolated = replace(dataset, records={**dataset.records, "INITIAL_STATE": (invalid,)})
    generated, skipped = GnssProducts_Get(Export_Run(isolated, tmp_path))
    assert set(generated) == {HORIZONTAL, RECEIVER}
    assert skipped == {VERTICAL: "gnss_vertical_input_unavailable:gnss_origin_unavailable"}
