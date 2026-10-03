"""Revision2 host/C and identity tests. Synthetic inputs are not flight proof."""

import ctypes
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.decoder_profiles.sf6_revision import COMPONENT, DELAY_IDS, Sf6Revision_Get
from silverstar_flp.plugins.algorithms.sf6.current_state import Sf6CurrentStateFilter
from silverstar_flp.plugins.algorithms.sf6.filter import NavigationSf6Result as Result
from silverstar_flp.plugins.algorithms.sf6.filter import Sf6Filter, Sf6Measurement
from silverstar_flp.plugins.algorithms.sf6.plugin import Sf6AlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import InertialIncrement_ReadRecorded, Mechanization_Run
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from tests.parameter_fixtures import FirmwareSets_Build, SyntheticParameters_Attach
from tests.sf6_c_bridge import CCore, CurrentContext, Library_Build
from tests.sslog_synthetic import START_TIMESTAMP_US, StationaryFlight_Build
from tests.test_decoder_profiles import _PackageFiles_Build, _Package_Write, _SemanticsDocument_Build
from tests.test_sf6_replay import _Measurement_Record


@pytest.fixture(scope="module")
def current_oracle(tmp_path_factory):
    return Library_Build(tmp_path_factory.mktemp("sf6_revision2_oracle"), revision=2)


def _Pair_Build(oracle, gain=(0.2,) * 6, velocity=(0, 0, 0), epoch=0):
    return Sf6CurrentStateFilter(gain, velocity, epoch), CCore(oracle, gain, velocity, epoch)


def _Update_Assert(python, c, item, expected=None):
    before = python.state
    result = python.Update(item)
    assert result == c.Update(item)
    if expected is not None:
        assert result[0] == expected
    np.testing.assert_array_equal(python.state, c.state)
    if result[0] != Result.OK:
        np.testing.assert_array_equal(python.state, before)
    return result


@pytest.mark.parametrize("gain", [0.0, 0.2, 1.0])
def test_current_state_c_parity_delayed_groups_order_duplicates_and_wrap(current_oracle, gain):
    python, c = _Pair_Build(current_oracle, (gain,) * 6, (1, -2, 3), 12345)
    rng = np.random.default_rng(1506)
    for step in range(1, 1201):
        now = 12345 + step * 1000
        dv = rng.uniform(-0.01, 0.01, 3).astype(np.float32)
        assert python.Predict(now, dv, 0.001) == c.Predict(now, dv, 0.001) == Result.OK
        if step % 5 == 0:
            for group in (4, 1, 3, 0, 2):
                age = min(step - 1, 100 if group in (2, 3) else 20)
                item = Sf6Measurement(now - age * 1000, now, step, group,
                                      tuple(rng.uniform(-10, 10, 2)))
                result, boundary = _Update_Assert(python, c, item)
                assert boundary == (now if result == Result.OK else None)
                if result == Result.OK:
                    _Update_Assert(python, c, item, Result.DUPLICATE)
        np.testing.assert_array_equal(python.state, c.state)
    python, c = _Pair_Build(current_oracle)
    assert python.Predict(10000, (0, 0, 0), 0.01) == c.Predict(10000, (0, 0, 0), 0.01)
    for item in (Sf6Measurement(1000, 2000, 2**32 - 1, 4, (10, 0)),
                 Sf6Measurement(1000, 2000, 7, 1, (-10, 0)),
                 Sf6Measurement(3000, 4000, 0, 4, (0, 0))):
        _Update_Assert(python, c, item, Result.OK)


def test_current_state_c_parity_epoch_age_and_transactional_numeric_guards(current_oracle):
    python, c = _Pair_Build(current_oracle, (1,) * 6, epoch=1000)
    for step in range(1, 61):
        now = 1000 + step * 10000
        assert python.Predict(now, (0, 0, 0), 0.01) == c.Predict(now, (0, 0, 0), 0.01)
    for item, expected in (
        (Sf6Measurement(999, now, 1, 0, (1, 2)), Result.STALE),
        (Sf6Measurement(now - 500001, now, 1, 0, (1, 2)), Result.STALE),
        (Sf6Measurement(now - 500000, now, 1, 0, (1, 2)), Result.OK),
        (Sf6Measurement(now + 1, now, 2, 0, (1, 2)), Result.INVALID_ARGUMENT),
        (Sf6Measurement(now, now, 2, 0, (float("nan"), 2)), Result.INVALID_ARGUMENT),
        (Sf6Measurement(now, now, 2, 4, (3e38, float("nan"))), Result.OK),
        (Sf6Measurement(now, now, 3, 4, (-3e38, 0)), Result.DUPLICATE),
    ):
        _Update_Assert(python, c, item, expected)
    assert python.Predict(now + 10000, (0, 0, 0), 0.01) == c.Predict(now + 10000, (0, 0, 0), 0.01)
    _Update_Assert(python, c, Sf6Measurement(now + 1, now + 1, 3, 4, (-3e38, 0)), Result.NUMERIC_ERROR)
    _Update_Assert(python, c, Sf6Measurement(now + 1, now + 1, 3, 4, (3e38, 0)), Result.OK)
    assert ctypes.sizeof(CurrentContext) == 192
    assert not hasattr(python, "history") and not hasattr(python, "events")


def test_revision2_updates_latest_boundary_without_replaying_velocity_history(current_oracle):
    python, c = _Pair_Build(current_oracle, (1,) * 6, (1, 0, 0))
    legacy = Sf6Filter((1,) * 6, (1, 0, 0))
    for step in range(1, 11):
        for core in (python, c, legacy):
            assert core.Predict(step * 10000, (0, 0, 0), 0.01) == Result.OK
    item = Sf6Measurement(10000, 100000, 1, 2, (3, 0))
    assert _Update_Assert(python, c, item) == (Result.OK, 100000)
    assert legacy.Update(item) == (Result.OK, 10000)
    assert python.state[3] == np.float32(0.09999999)
    assert legacy.state[3] > python.state[3]


def _CurrentDataset_Build(tmp_path):
    dataset = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_current.BIN"))
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    metadata = dict(dataset.semantic_context.raw_metadata)
    metadata["firmware_algorithm_parameters"] = [
        {**group, "parameters": [item for item in group["parameters"]
         if group["component"] != COMPONENT or item["id"] not in DELAY_IDS]}
        for group in metadata["firmware_algorithm_parameters"]]
    metadata["metadata_declarations"] = {"sf6": {"revision": 2}}
    metadata["component_locks"] = [{"component": COMPONENT, "version": "0.2.0"}]
    return replace(dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata))


def test_revision2_plugin_current_boundary_no_replay_metrics_and_retired_knob_rejection(tmp_path, current_oracle):
    dataset = _CurrentDataset_Build(tmp_path)
    receive = START_TIMESTAMP_US + 30000
    records = dict(dataset.records)
    records["SF6_MEASUREMENT"] = (
        _Measurement_Record(4, 20, receive=receive, epoch=receive - 20000),
        _Measurement_Record(1, -10, receive=receive, epoch=receive - 10000),)
    dataset = replace(dataset, records=records)
    plugin = Sf6AlgorithmPlugin()
    result = plugin.run(dataset, ReplayRequest(input_source="recorded_inertial_increment"))
    assert result.algorithm_version == "0.2.0-c-core-revision2"
    assert result.diagnostics["algorithm_revision"] == 2
    assert result.diagnostics["fusion_semantics"] == "current-state-no-history-replay"
    assert all(key not in result.diagnostics for key in ("history_window_us", "history_capacity", "event_capacity"))
    assert not set(DELAY_IDS) & set(result.parameters)
    for event in result.diagnostics["measurement_events"]:
        assert event["result"] == 0
        assert event["boundary_timestamp_us"] == event["timestamp_us"]
    increments = InertialIncrement_ReadRecorded(dataset.Records_Get("INERTIAL_INCREMENT"),
                                               start_timestamp_us=dataset.start_timestamp_us)
    outputs = Mechanization_Run(increments, initial_q_nb=dataset.initial_state.payload["q_nb"],
                                gravity_mps2=result.parameters["gravity_mps2"])
    c = CCore(current_oracle, (0.2,) * 6, dataset.initial_state.payload["initial_velocity_enu_mps"],
              increments[0].interval_start_timestamp_us)
    expected = []
    for output in outputs:
        assert c.Predict(output.timestamp_us, output.delta_velocity_enu_mps, output.dt_s) == Result.OK
        for event in result.diagnostics["measurement_events"]:
            if event["timestamp_us"] == output.timestamp_us:
                item = Sf6Measurement(event["measurement_timestamp_us"], event["receive_timestamp_us"],
                                      event["sequence"], event["group"], tuple(event["observation"]))
                assert c.Update(item) == (event["result"], event["boundary_timestamp_us"])
        expected.append(c.state)
    np.testing.assert_array_equal(result.channels["sf6.state"].values, expected)
    for delay in DELAY_IDS:
        with pytest.raises(ValueError, match="sf6_revision2_delay_parameters_forbidden"):
            plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={delay: 1}))


@pytest.mark.parametrize("declaration,version,expected", [
    (2, "0.1.0", "mismatch"), (3, "0.2.0", "unsupported"),
    (2, "0.3.0", "unsupported"), (None, None, "missing"),
])
def test_identity_unknown_and_mismatched_profiles_fail(tmp_path, declaration, version, expected):
    dataset = _CurrentDataset_Build(tmp_path)
    metadata = dict(dataset.semantic_context.raw_metadata)
    metadata["metadata_declarations"] = {} if declaration is None else {"sf6": {"revision": declaration}}
    metadata["component_locks"] = [] if version is None else [{"component": COMPONENT, "version": version}]
    dataset = replace(dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata))
    with pytest.raises(DecoderProfileError, match=expected):
        Sf6AlgorithmPlugin().run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))


def test_logged_revision_must_match_exact_decoder(tmp_path):
    dataset = _CurrentDataset_Build(tmp_path)
    record = replace(_Measurement_Record(0, 0), record_name="SF6_STATE", payload={"algorithm_revision": 1})
    dataset = replace(dataset, records={**dataset.records, "SF6_STATE": (record,)})
    with pytest.raises(DecoderProfileError, match="sf6_recorded_algorithm_revision_mismatch"):
        Sf6Revision_Get(dataset)


def test_exact_decoder_package_accepts_rev2_and_rejects_old_delay_contract(tmp_path):
    semantics = _SemanticsDocument_Build()
    groups = FirmwareSets_Build()
    semantics["algorithms"] = [g["component"] for g in groups]
    semantics["metadata_declarations"] = {"sf6": {"revision": 2}}
    semantics["component_locks"] = [{"component": COMPONENT, "version": "0.2.0"}]
    semantics["firmware_algorithm_parameters"] = groups
    files, _ = _PackageFiles_Build(semantics_document=semantics)
    package, _ = _Package_Write(tmp_path / "SYNTHETIC_wrong.ssdecoder", files=files)
    with pytest.raises(DecoderProfileError, match="sf6_revision2_delay_parameters_forbidden"):
        DecoderProfilePackage.Load(package)
    semantics["firmware_algorithm_parameters"] = [
        {**group, "parameters": [p for p in group["parameters"]
         if group["component"] != COMPONENT or p["id"] not in DELAY_IDS]}
        for group in groups]
    files, _ = _PackageFiles_Build(semantics_document=semantics)
    package, _ = _Package_Write(tmp_path / "SYNTHETIC_current.ssdecoder", files=files)
    DecoderProfilePackage.Load(package)


def test_historical_dataset_keeps_revision1_and_explicit_offline_selects_revision2(tmp_path):
    dataset = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_old.BIN"))
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    plugin = Sf6AlgorithmPlugin()
    old = plugin.run(dataset, ReplayRequest())
    new = plugin.run(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    assert old.algorithm_version == "0.1.0-c-core-revision1"
    assert old.diagnostics["algorithm_revision"] == 1
    assert old.diagnostics["history_capacity"] == 256
    assert new.algorithm_version == "0.2.0-c-core-revision2"
    assert new.diagnostics["algorithm_revision"] == 2
    assert new.provenance == "Offline" and not set(DELAY_IDS) & set(new.parameters)


def test_gui_and_saved_project_preserve_revision_specific_parameter_contract(tmp_path):
    from PySide6.QtWidgets import QApplication
    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.core.project import ReplayConfiguration_Validate
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.ui.pages.replay import ReplayPage

    dataset = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_ui.BIN"))
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    app = QApplication.instance() or QApplication([])
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset)
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.sf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    app.processEvents()
    legacy = page.Configuration_Get()
    assert legacy["algorithm_version"] == "0.1.0-c-core-revision1"
    assert set(DELAY_IDS) <= set(page._parameter_widgets)
    ReplayConfiguration_Validate(legacy)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.OFFLINE))
    app.processEvents()
    current = page.Configuration_Get()
    assert current["algorithm_version"] == "0.2.0-c-core-revision2"
    assert not set(DELAY_IDS) & set(page._parameter_widgets)
    ReplayConfiguration_Validate(current)
    with pytest.raises(ValueError, match="project_parameter_schema_mismatch"):
        ReplayConfiguration_Validate({**current,
            "parameter_schema_identity": legacy["parameter_schema_identity"]})
    page.Configuration_Set(legacy)
    assert page.Configuration_Get() == legacy
    with pytest.raises(ValueError, match="project_algorithm_semantics_mismatch"):
        page.Configuration_Set({**legacy, "mode": ReplayMode.OFFLINE.value})
    page.close()
