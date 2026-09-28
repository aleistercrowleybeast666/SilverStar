from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.project import Project_Load, Project_Save, ReplayConfiguration_Validate
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.replay import ReplayPage
from tests.parameter_fixtures import (
    FirmwareSets_Build,
    ParameterPackage_Open,
    SyntheticParameters_Attach,
)
from tests.sslog_synthetic import StationaryFlight_Build
from tests.test_decoder_profiles import (
    _Checksums_Refresh,
    _JsonBytes,
    _Package_Write,
    _PackageFiles_Build,
)
from tests.test_project_export import _ProjectDocument_Build

FIXTURES = Path(__file__).parent / "fixtures/parameter_contracts"


def test_fccg_ids_units_representations_defaults_match_audited_contract():
    for plugin in builtin_registry().algorithms:
        name = plugin.metadata.plugin_id.rsplit(".", 1)[-1]
        expected = json.loads((FIXTURES / f"{name}_fccg_1_2.json").read_text(encoding="utf8"))[
            "parameters"
        ]
        actual = {p.parameter_id: p for p in plugin.metadata.parameter_schema}
        assert set(actual) == {p["id"] for p in expected}
        for item in expected:
            spec = actual[item["id"]]
            assert (spec.default, spec.unit, spec.representation, spec.minimum, spec.maximum) == (
                item["default"],
                item["unit"],
                item["representation"],
                item["min"],
                item["max"],
            )
        assert not {
            "p0_scale",
            "gnss_position_r_scale",
            "gnss_velocity_r_scale",
            "baro_r_scale",
        } & set(actual)


def test_package_12_actual_values_are_immutable_and_separate_from_membership(tmp_path):
    opened = ParameterPackage_Open(tmp_path)
    assert opened.package.package_schema_minor == 2
    assert opened.package.semantics.schema_version == 0x10002
    context = opened.dataset.semantic_context
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    values = plugin.recorded_parameters(opened.dataset)
    assert values["p0_position_u"] == 9
    assert values["gravity_mps2"] == float(np.float32(9.78))
    with pytest.raises(TypeError):
        context.FirmwareParameters_Get(plugin.metadata.firmware_component_ids[0])["gravity_mps2"][
            "value"
        ] = 0
    absent = replace(opened.dataset, semantic_context=replace(context, firmware_algorithm_ids=()))
    assert not plugin.recorded_parameters(absent)
    assert not plugin.ConfigurationAvailability_Get(absent).recorded_available


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "unknown"),
        ("unit", "wrong"),
        ("representation", "variance"),
        ("value", True),
        ("value", "9.78"),
        ("value", -1.0),
        ("storage_type", "string"),
        ("storage_type", "int32"),
    ],
)
def test_package_rejects_parameter_contract_errors_before_cache(tmp_path, field, value):
    groups = FirmwareSets_Build()
    groups[0]["parameters"][0][field] = value
    with pytest.raises(DecoderProfileError):
        ParameterPackage_Open(tmp_path, groups)
    assert not list((tmp_path / "cache").rglob("*.ssdecoder"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "2", -1, 1001])
def test_request_rejects_invalid_actual_value(value):
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    with pytest.raises(ValueError):
        plugin.metadata.Parameters_Validate({"gnss_position_std_horizontal": value}, complete=False)


def test_package_11_rejected(tmp_path):
    files, _ = _PackageFiles_Build()
    manifest = json.loads(files["manifest.json"])
    manifest["package_schema"] = {
        "id": "silverstar.ssdecoder.package-schema/1.1",
        "major": 1,
        "minor": 1,
    }
    files["manifest.json"] = _JsonBytes(manifest)
    _Checksums_Refresh(files)
    path, _ = _Package_Write(tmp_path / "obsolete.ssdecoder", files=files)
    with pytest.raises(DecoderProfileError, match="version_unsupported"):
        DecoderProfilePackage.Load(path)


def test_missing_required_parameter_never_uses_offline_default(tmp_path):
    groups = FirmwareSets_Build()
    groups[0]["parameters"] = []
    opened = ParameterPackage_Open(tmp_path, groups)
    plugin = builtin_registry().algorithms[0]
    config = plugin.ConfigurationAvailability_Get(opened.dataset)
    assert config.firmware_member and not config.recorded_available
    assert "gravity_mps2" in config.missing_recorded_parameters
    with pytest.raises(ValueError, match="recorded_configuration_unavailable"):
        plugin.Parameters_Resolve(opened.dataset, ReplayRequest())
    with pytest.raises(ValueError, match="recorded_configuration_unavailable"):
        plugin.Parameters_Resolve(opened.dataset, ReplayRequest(mode=ReplayMode.WHAT_IF))


@pytest.mark.parametrize("source", ["corrected_imu", "recorded_inertial_increment"])
def test_actual_default_replay_equals_frozen_legacy_multiplier_one(tmp_path, source):
    ds = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_defaults.BIN"))
    ds = SyntheticParameters_Attach(ds, tmp_path / "package")
    with np.load(FIXTURES / "legacy_default_outputs.npz") as baseline:
        for plugin in builtin_registry().algorithms:
            if not any(key.startswith(plugin.metadata.plugin_id + ".") for key in baseline.files):
                continue  # Frozen outputs cover only algorithms that existed in that firmware.
            result = plugin.run(ds, ReplayRequest(input_source=source))
            for key, value in plugin.recorded_parameters(ds).items():
                assert result.parameters[key] == value
            if plugin.metadata.plugin_id.endswith("kf6"):
                assert result.parameters["gnss_integrity_enable"] == 0
            prefix = plugin.metadata.plugin_id + "." + source + "."
            for key in baseline.files:
                if not key.startswith(prefix):
                    continue
                name = key.removeprefix(prefix)
                assert name in result.channels
                np.testing.assert_array_equal(result.channels[name].values, baseline[key])
            assert (
                result.diagnostics["config_source"]
                == "Firmware build configuration from .ssdecoder"
            )


def test_recorded_replay_uses_exact_package_value_instead_of_header(tmp_path):
    ds = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_actual.BIN"))
    ds = SyntheticParameters_Attach(ds, tmp_path / "package", {"pure_ins": {"gravity_mps2": 9.7}})
    plugin = builtin_registry().algorithms[0]
    result = plugin.run(ds, ReplayRequest())
    assert result.parameters["gravity_mps2"] == float(np.float32(9.7))
    assert result.parameters["gravity_mps2"] != ds.header["gravity_mps2"]
    assert np.max(np.abs(result.channels["navigation.velocity_enu"].values)) > 0.001
    with pytest.raises(ValueError, match="override_forbidden"):
        plugin.run(ds, ReplayRequest(parameters={"gravity_mps2": 9.8}))


@pytest.mark.parametrize("firmware", [True, False])
def test_what_if_edit_reset_project_roundtrip_and_exact_baseline(tmp_path, firmware):
    app = QApplication.instance() or QApplication([])
    ds = Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path / "SYNTHETIC_UI.BIN"))
    if firmware:
        ds = SyntheticParameters_Attach(
            ds, tmp_path / "package", {"pure_ins": {"gravity_mps2": 9.7654321}}
        )
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(ds)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    plugin = builtin_registry().algorithms[0]
    baseline = dict(plugin.recorded_parameters(ds) if firmware else plugin.OfflineParameters_Get())
    assert page.Configuration_Get()["actual_values"] == baseline
    assert page.parameter_reset_button.text() == (
        "Restore firmware configuration" if firmware else "Restore algorithm defaults"
    )
    page._parameter_widgets["gravity_mps2"].setValue(9.6)
    page.Language_Apply(Translator("zh_CN"))
    assert page._parameter_widgets["gravity_mps2"].value() == 9.6
    doc = _ProjectDocument_Build(ds.source_path, tmp_path / "actual.ssflp")
    doc.replay_configurations["draft"] = page.Configuration_Get()
    Project_Save(doc, doc.project_path)
    loaded = Project_Load(doc.project_path)
    assert json.loads(doc.project_path.read_text())["version"] == 3
    page._Parameters_Reset()
    assert page.Configuration_Get()["actual_values"] == baseline
    page.Configuration_Set(loaded.replay_configurations["draft"])
    assert page._parameter_widgets["gravity_mps2"].value() == 9.6
    for field in ("algorithm_version", "parameter_schema_identity"):
        bad = copy.deepcopy(loaded.replay_configurations["draft"])
        bad[field] = "old"
        with pytest.raises(ValueError, match="schema_mismatch"):
            ReplayConfiguration_Validate(bad)
    old_mode = copy.deepcopy(loaded.replay_configurations["draft"])
    old_mode["mode"] = "integrity_assisted"
    with pytest.raises(ValueError, match="legacy_integrity_assistance_unsupported"):
        ReplayConfiguration_Validate(old_mode)
    old = json.loads(doc.project_path.read_text())
    old["version"] = 2
    doc.project_path.write_text(json.dumps(old))
    with pytest.raises(ValueError, match="version_unsupported"):
        Project_Load(doc.project_path)
    app.processEvents()
    page.close()


def test_sigma_and_p0_actual_edits_preserve_timing_and_input_arrays(tmp_path):
    ds = Sslog0ParserPlugin().parse(
        StationaryFlight_Build(tmp_path / "SYNTHETIC_parameter_effect.BIN")
    )
    ds = SyntheticParameters_Attach(ds, tmp_path / "package")
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    original = plugin.run(ds, ReplayRequest())
    changed = plugin.run(
        ds,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF, parameters={"p0_position_e": 20, "process_accel_std_e": 3}
        ),
    )
    np.testing.assert_array_equal(
        original.channels["kf6.state"].timestamp_us, changed.channels["kf6.state"].timestamp_us
    )
    assert (
        changed.channels["kf6.covariance.diagonal"].values[-1, 0]
        > original.channels["kf6.covariance.diagonal"].values[-1, 0]
    )
    assert ds.initial_state.payload["p0_diagonal"][0] == 4


def test_matching_dynamic_package_replay_and_actual_baro_export(tmp_path):
    from silverstar_flp.export.service import ExportOptions, FlightExporter
    from tests.synthetic_parameter_navigation import NavigationPair_Open

    opened = NavigationPair_Open(tmp_path / "dynamic")
    dataset = opened.dataset
    before = dataset.source_path.read_bytes()
    results = {}
    with np.load(FIXTURES / "legacy_dynamic_outputs.npz") as baseline:
        for plugin in builtin_registry().algorithms:
            name = plugin.metadata.plugin_id.rsplit(".", 1)[-1]
            if not plugin.FirmwareMember_Is(dataset):
                continue
            result = plugin.run(dataset, ReplayRequest())
            results[name] = result
            if name == 'pure_ins':
                for channel, series in result.channels.items():
                    np.testing.assert_array_equal(series.values, baseline[name + '.' + channel])
            else:
                # The former KF baseline guessed arrival times. The new numerical
                # authority is the separately tested generated C golden.
                assert result.diagnostics['measurement_timing_inferred'] is False
                assert result.diagnostics['mechanization_verification']['passed']
                assert all(
                    np.isfinite(channel.values).all() for channel in result.channels.values()
                )
    kf = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    changed = kf.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"baro_std_m": 6}))
    np.testing.assert_array_equal(
        changed.channels["kf6.state"].timestamp_us,
        results["kf6"].channels["kf6.state"].timestamp_us,
    )
    assert not np.array_equal(
        changed.channels["kf6.state"].values, results["kf6"].channels["kf6.state"].values
    )
    assert dataset.source_path.read_bytes() == before
    assert dataset.Records_Get("BARO_MEASUREMENT")[0].payload["variance_m2"] == float(
        np.float32(25.04)
    )
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "export",
        algorithm_results=results,
        options=ExportOptions(
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_full_covariance_keyframes=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert not manifest.failures
    audit = json.loads(manifest.ManifestPath_Get().read_text(encoding="utf8"))
    assert audit["firmware"]["algorithm_parameters"]
    for replay in audit["replay_results"]:
        assert replay["actual_parameters"]
        assert replay["parameter_schema_identity"]
        assert replay["config_source"] == "Firmware build configuration from .ssdecoder"
        assert replay["parameter_metadata"]["gravity_mps2"]["representation"] == "value"


def test_baro_floor_edit_without_native_uncertainty_is_refused(tmp_path):
    from tests.synthetic_parameter_navigation import NavigationPair_Open

    opened = NavigationPair_Open(tmp_path / "missing_native")
    ds = opened.dataset
    records = dict(ds.records)
    records.pop("BARO_NATIVE")
    ds = replace(ds, records=records)
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    with pytest.raises(ValueError, match="dynamic_uncertainty_missing:BARO_NATIVE"):
        plugin.run(ds, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"baro_std_m": 6}))


def test_uncertainty_edit_never_uses_a_different_device_with_matching_timestamp(tmp_path):
    from tests.synthetic_parameter_navigation import NavigationPair_Open

    ds = NavigationPair_Open(tmp_path / "device_identity").dataset
    records = dict(ds.records)
    records["BARO_NATIVE"] = tuple(
        replace(record, payload={**record.payload, "source_descriptor_id": 99})
        for record in records["BARO_NATIVE"]
    )
    ds = replace(ds, records=records)
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    with pytest.raises(ValueError, match="dynamic_uncertainty_missing:BARO_NATIVE"):
        plugin.run(ds, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={"baro_std_m": 6}))
