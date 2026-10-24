"""Validate real saved projects with the published standalone JSON Schema."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import zipfile

import pytest
from jsonschema import Draft202012Validator

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.source_export import SourcePackage_Export
from silverstar_fccg.core.nis_probability import NisInput_Create
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.model import (
    GroundRadioConfiguration, ProjectModel_Parse, ProjectModelError,
    PROJECT_FORMAT_VERSION, PROJECT_GROUND_RADIOS_FORMAT_VERSION,
    PROJECT_RADIO_VARIANTS_FORMAT_VERSION, PROJECT_FEATURE_TIERS_FORMAT_VERSION,
    PROJECT_NIS_INPUT_FORMAT_VERSION, PROJECT_NATIVE_USB_FORMAT_VERSION,
    PROJECT_SENSOR_INSTALLATION_FORMAT_VERSION, PROJECT_OPTIONAL_RESOURCES_FORMAT_VERSION, RAW_IMU_MOUNT_PLUGINS,
)
from silverstar_fccg.project.native_usb import NativeUsbReference
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.sensor_installation import SensorInstallationConfiguration, SensorPosition
from silverstar_fccg.project.validation import Project_Validate
from test_f103_ground_reference import _GroundF103Model_Get


@pytest.fixture(scope="module")
def schema():
    document = json.loads((Path(__file__).resolve().parents[1] / "schemas/project.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(document)
    return document


@pytest.fixture(scope="module")
def validator(schema):
    return Draft202012Validator(schema)


def _Document_Get(version, catalog):
    model = ReferenceProject_Create("SchemaCompatibility", catalog=catalog)
    model.format_version = version
    if version in (15, 20):
        model.ground_target = _GroundF103Model_Get(catalog).ground_target
        ground = model.ground_target
        model.ground_target = replace(ground, radio_instances=(GroundRadioConfiguration(
            "radio0", ground.radio_plugin, ground.module_variant, ground.tx_power_dbm),))
    if version in (16, 20):
        radio = catalog.Component_Get("silverstar.device.telemetry.sx1281").radio
        module = next(iter(radio.modules))
        power = radio.modules[module]["supported_tx_powers_dbm"][0]
        model.device_instances = [replace(item, module_variant=module, tx_power_dbm=power)
                                  if item.instance_id == "telemetry0" else item for item in model.device_instances]
    if version in (17, 20):
        model.build = replace(model.build, feature_tier="standard")
    if version in (18, 20):
        owner = catalog.Component_Get(model.strategies["estimator"])
        parameter = next(item for item in owner.algorithm_parameters if item.nis_df)
        model.algorithm_parameters[owner.component_id][parameter.parameter_id] = NisInput_Create(0.95, parameter.nis_df)
    if version in (19, 20):
        model.native_usb = NativeUsbReference("D:/native-reference", "a" * 64)
    if version == 20:
        model.sensor_installation = SensorInstallationConfiguration("CAD datum O; +X flange mark; +Y right hand; +Z nose")
        model.device_instances = [replace(item, position_body_m=SensorPosition(0.01, -0.02, 1.5))
                                  if item.instance_id in ("imu0", "gnss0") else item for item in model.device_instances]
        preset = model.Dictionary_Get()
        preset["build"].pop("feature_tier")
        model.feature_tier_presets["full"] = preset
    document = model.Dictionary_Get()
    assert document["format_version"] == version
    # The public schema describes JSON, including list-normalized inventory
    # metadata, rather than Python tuple-backed in-memory board snapshots.
    return json.loads(json.dumps(document))


def test_published_schema_tracks_supported_versions_and_shared_installation_contract(schema):
    assert schema["properties"]["format_version"]["enum"] == [
        PROJECT_FORMAT_VERSION, PROJECT_GROUND_RADIOS_FORMAT_VERSION,
        PROJECT_RADIO_VARIANTS_FORMAT_VERSION, PROJECT_FEATURE_TIERS_FORMAT_VERSION,
        PROJECT_NIS_INPUT_FORMAT_VERSION, PROJECT_NATIVE_USB_FORMAT_VERSION,
        PROJECT_SENSOR_INSTALLATION_FORMAT_VERSION,
        PROJECT_OPTIONAL_RESOURCES_FORMAT_VERSION,
    ] == list(range(14, 22))
    assert {"alignment", "flight_tx_power_dbm", "ground_target"} <= set(schema["required"])
    hardware = schema["properties"]["hardware"]
    assert set(hardware["required"]) <= set(hardware["properties"])
    assert "cubemx_version" not in schema["properties"]["log_decoder_profile"]["properties"]
    contract = json.loads((Path(__file__).resolve().parents[3] / "contracts/sensor_installation_v1.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["position"] == contract["$defs"]["position"]
    assert schema["$defs"]["coordinate"] == contract["$defs"]["coordinate"]
    device = schema["$defs"]["deviceInstance"]
    assert set(device["allOf"][1]["then"]["properties"]["plugin"]["enum"]) == RAW_IMU_MOUNT_PLUGINS


@pytest.mark.parametrize("version", range(14, 21))
def test_real_serializer_outputs_pass_schema_and_parser(version, validator, builtin_catalog):
    document = _Document_Get(version, builtin_catalog)
    validator.validate(document)
    assert ProjectModel_Parse(deepcopy(document)).Dictionary_Get() == document


@pytest.mark.parametrize("version", range(14, 20))
def test_installation_cannot_be_smuggled_into_earlier_format(version, validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    document["format_version"] = version
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)


@pytest.mark.parametrize("current,older", [(16, 14), (18, 17), (19, 18)])
def test_existing_extension_version_gates_are_preserved(current, older, validator, builtin_catalog):
    document = _Document_Get(current, builtin_catalog)
    document["format_version"] = older
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)


@pytest.mark.parametrize("patch", [
    {"position_body_m": {"x": True, "y": 0, "z": 0}},
    {"position_body_m": {"x": "1", "y": 0, "z": 0}},
    {"position_body_m": {"x": 0, "y": 0}},
    {"position_body_m": {"x": 0, "y": 0, "z": 0, "w": 1}},
    {"position_body_m": {"x": 1000001, "y": 0, "z": 0}},
    {"position_body_m": None},
])
def test_position_shape_type_and_range_rejected_by_both(patch, validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    document["components"]["devices"][0].update(patch)
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)


@pytest.mark.parametrize("field,value", [("unit", "mm"), ("frame", "ENU"), ("origin_kind", "primary_imu"), ("origin_description", "bad\nreference"), ("runtime_applied", True)])
def test_installation_frame_and_reference_rejected_by_both(field, value, validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    document["sensor_installation"][field] = value
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)


def test_positions_require_explicit_reference_but_unknown_positions_remain_absent(validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    document.pop("sensor_installation")
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)
    legacy = _Document_Get(14, builtin_catalog)
    assert "sensor_installation" not in legacy
    assert all("position_body_m" not in item for item in legacy["components"]["devices"])
    validator.validate(legacy)


def test_schema_rejects_recursive_or_wrong_tier_preset(validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    nested = document["feature_tier_presets"]["full"]
    nested["feature_tier_presets"] = {}
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)
    nested.pop("feature_tier_presets")
    nested["build"]["feature_tier"] = "standard"
    assert not validator.is_valid(document)
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(document)


def test_empty_origin_is_a_valid_draft_but_not_generation_acceptance(validator, builtin_catalog):
    document = _Document_Get(20, builtin_catalog)
    document["sensor_installation"]["origin_description"] = ""
    validator.validate(document)
    model = ProjectModel_Parse(document)
    validation = Project_Validate(model, builtin_catalog)
    assert not validation.valid
    assert any(item.code == "INSTALLATION_ORIGIN_UNDEFINED" and item.level == "error"
               for item in validation.issues)
    with pytest.raises(ValueError, match="fixed structural origin"):
        GeneratedFiles_Render(model, builtin_catalog, SourceGraph_Resolve(model, builtin_catalog))


def test_source_export_carries_self_contained_schema_that_accepts_format20(tmp_path, schema, builtin_catalog):
    # Exercise the production exporter with only two small synthetic files,
    # avoiding a copy/export of the repository or SDK.
    source = tmp_path / "minimal-source"
    (source / "schemas").mkdir(parents=True)
    (source / "schemas/project.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    document = _Document_Get(20, builtin_catalog)
    (source / "sample.ssproject").write_text(json.dumps(document), encoding="utf-8")
    destination = tmp_path / "minimal-source.zip"
    result = SourcePackage_Export(source, destination)
    assert result.file_count == 2
    with zipfile.ZipFile(destination) as package:
        exported_schema = json.loads(package.read("SilverStar_SCG/schemas/project.schema.json"))
        exported_project = json.loads(package.read("SilverStar_SCG/sample.ssproject"))
    assert exported_project == document
    Draft202012Validator(exported_schema).validate(exported_project)


def test_production_open_save_and_generation_use_parser_and_no_compensation_claim(
    tmp_path, workspace_root, builtin_catalog, validator, monkeypatch,
):
    service = FccgService(workspace_root)
    model = ProjectModel_Parse(_Document_Get(20, builtin_catalog))
    read_text = Path.read_text
    schema_path = workspace_root / "schemas/project.schema.json"
    def read_without_schema(path, *args, **kwargs):
        assert path.resolve() != schema_path.resolve(), "Production unexpectedly reads documentary JSON Schema"
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_without_schema)
    root = ProjectRoot_Save(model, tmp_path / "production-roundtrip")
    loaded = service.Project_Open(root)
    assert loaded.Dictionary_Get() == model.Dictionary_Get()
    validator.validate(loaded.Dictionary_Get())
    validation = Project_Validate(loaded, service.catalog)
    codes = {issue.code for issue in validation.issues}
    assert "INSTALLATION_CONFIGURATION_ONLY" in codes
    assert "INSTALLATION_NONZERO_UNCOMPENSATED" in codes
    generated = GeneratedFiles_Render(loaded, service.catalog, SourceGraph_Resolve(loaded, service.catalog))
    snapshot = json.loads(generated["Generated/project_sensor_installation.json"])
    assert snapshot["runtime_applied"] is False
    assert snapshot["compensation_status"] == "configuration_only_not_applied"
    assert b"PROJECT_SENSOR_INSTALLATION_RUNTIME_APPLIED 0U" in generated["Generated/Inc/project_sensor_installation.h"]
    snapshot_schema = json.loads((workspace_root.parents[1] / "contracts/sensor_installation_v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(snapshot_schema)
    Draft202012Validator(snapshot_schema).validate(snapshot)
    invalid = loaded.Dictionary_Get()
    invalid["sensor_installation"]["unit"] = "mm"
    (root / "SilverStar.ssproject").write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ProjectModelError):
        service.Project_Open(root)
