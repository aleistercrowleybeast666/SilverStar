import json
import os
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.core.project import Project_Load, Project_Save, ReplayConfiguration_Validate
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_ReadRecorded,
    Mechanization_Run,
)
from silverstar_flp.plugins.algorithms.sf6.filter import NavigationSf6Result as Result
from silverstar_flp.plugins.algorithms.sf6.filter import Sf6Filter, Sf6Measurement
from silverstar_flp.plugins.algorithms.sf6.plugin import (
    Sf6AlgorithmPlugin,
    Sf6MeasurementTime_Resolve,
)
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from tests.parameter_fixtures import SyntheticParameters_Attach
from tests.sf6_c_bridge import CCore, Library_Build
from tests.sslog_synthetic import START_TIMESTAMP_US, StationaryFlight_Build
from tests.test_project_export import _ProjectDocument_Build


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    path = os.environ.get("SILVERSTAR_SF6_ORACLE_EVIDENCE") or tmp_path_factory.mktemp("sf6_oracle")
    return Library_Build(path)


def _Assert_StateMatches(python, c):
    np.testing.assert_array_equal(python.state, c.state)
    assert len(python.history) == c.context.count
    assert len(python.events) == c.context.event_count


@pytest.mark.parametrize("gain", [0.0, 0.2, 1.0])
def test_c_oracle_fixed_lag_groups_duplicates_stale_and_window(oracle, gain):
    gains = (gain, gain, gain, gain, gain, gain)
    python, c = Sf6Filter(gains, (1, -2, 3), 12345), CCore(oracle, gains, (1, -2, 3), 12345)
    rng = np.random.default_rng(802)
    for step in range(1, 901):
        now = 12345 + step * 1000
        dv = rng.uniform(-0.01, 0.01, 3).astype(np.float32)
        assert python.Predict(now, dv, 0.001) == c.Predict(now, dv, 0.001) == Result.OK
        if step % 5 == 0:
            # Interleaved delivery includes a delayed event from a different group.
            for group in (4, 1, 3, 0, 2):
                age = min(step - 1, 100 if group in (2, 3) else 20)
                measurement = Sf6Measurement(
                    now - age * 1000, now, step, group, tuple(rng.uniform(-10, 10, 2))
                )
                assert python.Update(measurement) == c.Update(measurement)
                _Assert_StateMatches(python, c)
                before = python.state
                assert (
                    python.Update(measurement) == c.Update(measurement) == (Result.DUPLICATE, None)
                )
                np.testing.assert_array_equal(python.state, before)
        _Assert_StateMatches(python, c)
    # Capacity, independently of the 600ms age, drops old boundaries at 1kHz.
    assert len(python.history) == 256
    expired = Sf6Measurement(12345, now, 1000, 0, (0, 0))
    assert python.Update(expired) == c.Update(expired) == (Result.STALE, None)
    bad_future = Sf6Measurement(now + 1, now, 1001, 1, (1, 0))
    assert python.Update(bad_future) == c.Update(bad_future) == (Result.INVALID_ARGUMENT, None)


def test_c_oracle_600ms_event_capacity_zero_gain_and_failed_commit(oracle):
    python, c = Sf6Filter((0,) * 6), CCore(oracle, (0,) * 6)
    for step in range(1, 101):
        assert python.Predict(step * 10000, (0, 0, 0), 0.01) == c.Predict(
            step * 10000, (0, 0, 0), 0.01
        )
    assert len(python.history) == 61  # Closed 600ms window.
    for sequence in range(1, 257):
        item = Sf6Measurement(400000 + sequence, 400000 + sequence, sequence, 4, (42, 0))
        assert python.Update(item) == c.Update(item) == (Result.OK, 400000)
    assert len(python.events) == 256  # Gain-zero observations still consume capacity.
    item = Sf6Measurement(500000, 500000, 257, 4, (13, 0))
    assert python.Update(item) == c.Update(item) == (Result.FULL, None)
    _Assert_StateMatches(python, c)
    python, c = Sf6Filter((1,) * 6), CCore(oracle, (1,) * 6)
    assert python.Predict(10000, (0, 0, 0), 0.01) == c.Predict(10000, (0, 0, 0), 0.01)
    for item, expected in (
        (Sf6Measurement(1, 1, 1, 4, (3e38, 0)), Result.OK),
        (Sf6Measurement(2, 2, 2, 4, (-3e38, 0)), Result.NUMERIC_ERROR),
        (Sf6Measurement(2, 2, 2, 4, (3e38, 0)), Result.OK),
    ):
        assert python.Update(item) == c.Update(item)
        assert python.last[4].sequence == (1 if expected == Result.NUMERIC_ERROR else item.sequence)
        _Assert_StateMatches(python, c)


def test_c_oracle_equal_time_group_order_and_sequence_wrap(oracle):
    python, c = Sf6Filter((0.2,) * 6), CCore(oracle, (0.2,) * 6)
    assert python.Predict(10000, (0, 0, 0), 0.01) == c.Predict(10000, (0, 0, 0), 0.01)
    for item in (
        Sf6Measurement(1000, 2000, 2**32 - 1, 4, (10, 0)),
        Sf6Measurement(1000, 2000, 7, 1, (-10, 0)),
        Sf6Measurement(3000, 4000, 0, 4, (0, 0)),
    ):
        assert python.Update(item) == c.Update(item)
        _Assert_StateMatches(python, c)
    assert [(e.measurement_us, e.group) for e in python.events] == [(1000, 1), (1000, 4), (3000, 4)]


@pytest.mark.parametrize(
    "receive,sample,trusted,delay,expected",
    [
        (1_000_000, 700_000, 1, 270, 700_000),
        (1_000_000, 700_000, 0, 270, 730_000),
        (1_000_000, 700_000, 0, 0, 1_000_000),
        (550000, 0, 0, 550, 0),
    ],
)
def test_timestamp_resolution_matches_sf6_backend(receive, sample, trusted, delay, expected):
    assert Sf6MeasurementTime_Resolve(receive, sample, trusted, delay) == expected


@pytest.mark.parametrize(
    "args", [(0, 0, 0, 0), (10, 11, 1, 0), (10, 0, 1, 0), (10, 0, 0, 550), (10, 1, 2, 0)]
)
def test_timestamp_invalid_conditions(args):
    with pytest.raises(ValueError):
        Sf6MeasurementTime_Resolve(*args)


@pytest.fixture
def dataset(tmp_path):
    return Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_sf6.BIN"))


def test_plugin_order_optional_gnss_no_covariance_and_cross_algorithm_what_if(dataset):
    registry = builtin_registry()
    assert [p.metadata.display_name for p in registry.algorithms] == [
        "Pure INS",
        "SF6",
        "KF_6",
        "ESKF_15",
    ]
    plugin = Sf6AlgorithmPlugin()
    assert not plugin.ConfigurationAvailability_Get(dataset).recorded_available
    with pytest.raises(ValueError, match="recorded_configuration_unavailable"):
        plugin.run(dataset, ReplayRequest())
    result = plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF))
    assert result.provenance == "What-if" and result.fidelity.value == "APPROXIMATE"
    assert "sf6_gnss_optional_missing" in result.warnings
    assert not result.diagnostics["has_covariance"] and not result.diagnostics["uses_magnetometer"]
    assert not any("covariance" in key or "nis" in key for key in result.channels)
    assert tuple(result.channels["sf6.state"].columns) == ("vE", "vN", "vU", "pE", "pN", "pU")
    assert max(abs(result.channels["navigation.position_enu"].values).flat) < 1e-5


def test_recorded_configuration_joins_shared_ins_gravity_and_preserves_source(dataset, tmp_path):
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    plugin = Sf6AlgorithmPlugin()
    assert plugin.ConfigurationAvailability_Get(dataset).recorded_available
    assert plugin.recorded_parameters(dataset)["gravity_mps2"] == float(np.float32(9.78))
    original = dataset.Records_Get("INITIAL_STATE")[0]
    before = dict(original.payload)
    result = plugin.run(dataset, ReplayRequest())
    assert result.provenance == "Recomputed from recorded configuration"
    assert dict(original.payload) == before
    with pytest.raises(ValueError, match="recorded_configuration_override_forbidden"):
        plugin.run(dataset, ReplayRequest(parameters={"gain_pu": 1}))


def _Measurement_Record(group, value, sequence=1, receive=None, epoch=None):
    receive = receive or START_TIMESTAMP_US + 10000
    return DecodedRecord(
        0x35,
        "SF6_MEASUREMENT",
        0,
        0,
        sequence,
        receive,
        1,
        {
            "sample_timestamp_us": receive,
            "receive_timestamp_us": receive,
            "measurement_timestamp_us": epoch or receive,
            "evaluation_timestamp_us": receive,
            "sequence": sequence,
            "group": group,
            "physically_valid": 1,
            "observation": (value, value),
            "result": 0,
        },
        0,
    )


def test_recorded_groups_share_pu_gain_and_zero_one_edges(dataset, tmp_path):
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    records = dict(dataset.records)
    records["SF6_MEASUREMENT"] = (_Measurement_Record(1, -10), _Measurement_Record(4, 20))
    dataset = replace(dataset, records=records)
    plugin = Sf6AlgorithmPlugin()
    for gain, expected in ((0, 0), (0.2, 2.4), (1, 20)):
        result = plugin.run(
            dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"gain_pu": gain})
        )
        np.testing.assert_allclose(
            result.channels["navigation.position_enu"].values[0, 2], expected, atol=2e-6
        )
        assert [e["group"] for e in result.diagnostics["measurement_events"]] == [1, 4]
        assert all(e["result"] == 0 for e in result.diagnostics["measurement_events"])
    with pytest.raises(ValueError, match="measurement_timestamp_trust_evidence_missing"):
        plugin.run(
            dataset,
            ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"baro_measurement_delay_ms": 1}),
        )


def test_save_restore_sf6_settings_and_export_audit(dataset, tmp_path):
    plugin = Sf6AlgorithmPlugin()
    result = plugin.run(
        dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"gain_ve": 0.4})
    )
    project = _ProjectDocument_Build(dataset.source_path, tmp_path / "sf6.ssflp")
    project.replay_configurations = {
        plugin.metadata.plugin_id: {
            "algorithm_id": plugin.metadata.plugin_id,
            "algorithm_version": plugin.metadata.version,
            "mode": "what_if",
            "input_source": "corrected_imu",
            "actual_values": dict(result.parameters),
            "provenance": "Algorithm Plugin actual defaults",
            "parameter_schema_identity": plugin.metadata.ParameterSchemaIdentity_Get(),
        }
    }
    Project_Save(project, project.project_path)
    loaded = Project_Load(project.project_path)
    ReplayConfiguration_Validate(loaded.replay_configurations[plugin.metadata.plugin_id])
    assert (
        loaded.replay_configurations[plugin.metadata.plugin_id]["actual_values"]["gain_ve"] == 0.4
    )
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "export",
        algorithm_results={"SF6": result},
        options=ExportOptions(
            language="en_US",
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
            include_full_covariance_keyframes=False,
        ),
    )
    assert not manifest.failures
    audit = next((tmp_path / "export").rglob("SF6_*_Replay_Audit_EN.json"))
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert payload["fidelity"] == "APPROXIMATE" and payload["mode"] == "what_if"
    assert payload["diagnostics"]["has_covariance"] is False


def test_plugin_adopted_initial_velocity_and_group_delivery_match_c_oracle(
    dataset, tmp_path, oracle
):
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "params")
    records = dict(dataset.records)
    initial = dataset.initial_state
    velocity = (1.25, -2.5, 3.0)
    records["INITIAL_STATE"] = (
        replace(initial, payload={**initial.payload, "initial_velocity_enu_mps": velocity}),
    )
    # First increment intentionally starts after the task START: only its real
    # end-dt boundary initializes the core, not a fictitious START-to-end dt.
    records["INERTIAL_INCREMENT"] = records["INERTIAL_INCREMENT"][1:]
    records["SF6_MEASUREMENT"] = (
        _Measurement_Record(4, 20, receive=START_TIMESTAMP_US + 30_000),
        _Measurement_Record(1, -10, receive=START_TIMESTAMP_US + 30_000),
        _Measurement_Record(2, 4, receive=START_TIMESTAMP_US + 50_000),
        _Measurement_Record(0, -7, receive=START_TIMESTAMP_US + 50_000),
    )
    dataset = replace(dataset, records=records)
    plugin = Sf6AlgorithmPlugin()
    request = ReplayRequest(mode=ReplayMode.WHAT_IF, input_source="recorded_inertial_increment")
    result = plugin.run(dataset, request)
    increments = InertialIncrement_ReadRecorded(
        records["INERTIAL_INCREMENT"], start_timestamp_us=dataset.start_timestamp_us
    )
    outputs = Mechanization_Run(
        increments,
        initial_q_nb=initial.payload["q_nb"],
        gravity_mps2=result.parameters["gravity_mps2"],
    )
    c = CCore(oracle, (0.2,) * 6, velocity, increments[0].interval_start_timestamp_us)
    events = iter(result.diagnostics["measurement_events"])
    event = next(events, None)
    expected = []
    for output in outputs:
        assert (
            c.Predict(output.timestamp_us, output.delta_velocity_enu_mps, output.dt_s) == Result.OK
        )
        while event is not None and event["timestamp_us"] == output.timestamp_us:
            update, boundary = c.Update(
                Sf6Measurement(
                    event["measurement_timestamp_us"],
                    event["receive_timestamp_us"],
                    event["sequence"],
                    event["group"],
                    tuple(event["observation"]),
                )
            )
            assert update == event["result"] and boundary == event["boundary_timestamp_us"]
            event = next(events, None)
        expected.append(c.state)
    np.testing.assert_array_equal(result.channels["sf6.state"].values, expected)
    assert len(expected) == len(increments)
    assert result.channels["sf6.state"].timestamp_us[0] == increments[0].interval_end_timestamp_us


def test_plugin_prediction_gap_rejected_and_input_unchanged(dataset):
    records = dict(dataset.records)
    records["INERTIAL_INCREMENT"] = (
        records["INERTIAL_INCREMENT"][:2] + records["INERTIAL_INCREMENT"][3:]
    )
    gapped = replace(dataset, records=records)
    with pytest.raises(ValueError, match="sf6_prediction_rejected:.*:STALE"):
        Sf6AlgorithmPlugin().run(
            gapped,
            ReplayRequest(mode=ReplayMode.WHAT_IF, input_source="recorded_inertial_increment"),
        )
    assert len(dataset.Records_Get("INERTIAL_INCREMENT")) == 8


def test_cross_algorithm_admission_is_independent_per_gnss_group(dataset):
    records = dict(dataset.records)
    receive = START_TIMESTAMP_US + 10_000
    records["INITIAL_STATE"] = (
        replace(
            dataset.initial_state,
            payload={**dataset.initial_state.payload, "origin_valid_flags": 3},
        ),
    )
    records["GNSS_MEASUREMENT"] = (
        replace(
            _Measurement_Record(0, 0),
            record_name="GNSS_MEASUREMENT",
            payload={
                "receive_timestamp_us": receive,
                "sample_timestamp_us": receive,
                "measurement_timestamp_trusted": 1,
                "sequence": 1,
                "fusion_allowed": 1,
                "valid_group_mask": 0b0101,
                "position_enu_m": (10, 20, 30),
                "velocity_enu_mps": (1, 2, 3),
            },
        ),
    )
    result = Sf6AlgorithmPlugin().run(
        replace(dataset, records=records), ReplayRequest(mode=ReplayMode.WHAT_IF)
    )
    assert [event["result"] for event in result.diagnostics["measurement_events"]] == [0, 1, 0, 1]
    assert result.channels["sf6.state"].values[0, 5] == 0


def test_sf6_parameter_form_starts_with_ordered_gains(dataset):
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.pages.replay import ReplayPage

    app = QApplication.instance() or QApplication([])
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset)
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.sf6"))
    app.processEvents()
    assert page.parameter_group_combo.currentData() == "parameter_group.sf6_gain"
    assert page.parameters_form.rowCount() == 6
    assert list(page._parameter_widgets)[:6] == [
        "gain_ve",
        "gain_vn",
        "gain_vu",
        "gain_pe",
        "gain_pn",
        "gain_pu",
    ]
    page.close()
