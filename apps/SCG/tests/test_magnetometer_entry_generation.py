"""Optional magnetic capture generation; synthetic compilation, no hardware."""
from copy import deepcopy
from dataclasses import replace
import json
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.render import (
    AlgorithmParametersHeader_Render,
    _DeviceBuildCapabilitiesHeader_Render,
    _DeviceDescriptorEntries_Get,
    _DeviceInstancesSource_Render,
    _FlightConfigHeader_Render,
    _InstanceResourcesSource_Render,
)
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.release_policy import ReleaseCompatibilityIssues_Get
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


MAG = "SYSTEM_DEVICE_CLASS_MAGNETOMETER"
JY = "silverstar.device.imu.jy901b"
PROFILE = "jy901b_mag_capture"


def _Model_Create(catalog, *, capture=False, devices=()):
    model = ReferenceProject_Create("OptionalMagCapture", catalog=catalog)
    if capture:
        model.device_instances = [replace(item, profile=PROFILE)
                                  if item.plugin == JY else item
                                  for item in model.device_instances]
    model.device_instances.extend(devices)
    return model


def _Compile_Run(model, catalog, tmp_path, rate, enabled, jy_capture, *, overrides=()):
    # Isolate rate/descriptor header compilation from the maintenance UART.
    # This fixture does not instantiate magnetic hardware; full validation of
    # unassigned magnetic resources remains a separate negative check.
    model = deepcopy(model)
    model.protocols['maintenance'] = None
    tmp_path.mkdir(exist_ok=True)
    view = catalog.ProjectView_Get(model)
    generated = {
        "project_device_build_capabilities.h": _DeviceBuildCapabilitiesHeader_Render(model, view),
        "project_flight_config.h": _FlightConfigHeader_Render(model, view),
        "project_algorithm_parameters.h": AlgorithmParametersHeader_Render(model, view),
    }
    for name, source in generated.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    # Only JY's compile-time RSW constants need this include; no resource driver
    # is linked or substituted into firmware by this compile-only fixture.
    (tmp_path / "project_resources.h").write_text("/* compile fixture */\n", encoding="utf-8")
    code = ['#include "project_flight_config.h"', '#include "system_user_config.h"',
            '#include "jy901b_config.h"',
            f'_Static_assert(SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ == {rate}U, "exact MAG rate");',
            f'_Static_assert(SYSTEM_USER_MAGNETOMETER_ENABLE == {enabled}U, "explicit endpoint");',
            f'_Static_assert(JY901B_MAGNETOMETER_ADAPTER_ENABLE == {jy_capture}U, "explicit JY frames");',
            f'_Static_assert(JY901B_RSW_OPTIONAL_MAG_MASK == {16 if jy_capture else 0}U, "actual RSW bit");',
            '_Static_assert(SYSTEM_SELECTED_MAGNETOMETER_ABSOLUTE_VECTOR_QUALIFIED == 0U, "capture is unqualified");',
            'int main(void) { return 0; }']
    (tmp_path / "facts.c").write_text("\n".join(code) + "\n", encoding="utf-8")
    includes = [tmp_path]
    for component in model.ComponentIds_Get():
        manifest = view.Component_Get(component)
        includes.extend(manifest.payload_root / item for item in manifest.build.include_dirs)
    gcc = shutil.which("gcc")
    assert gcc is not None, "Host GCC required; never download dependencies"
    command = [gcc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
               *overrides, *["-I" + str(path) for path in includes],
               "-c", str(tmp_path / "facts.c"), "-o", str(tmp_path / "facts.o")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (tmp_path / "compile.json").write_text(json.dumps(dict(
        command=command, exit_code=result.returncode, stdout=result.stdout,
        stderr=result.stderr), indent=2) + "\n", encoding="utf-8")
    return result


def test_default_has_no_mag_endpoint_and_preserves_200hz(builtin_catalog, tmp_path):
    model = _Model_Create(builtin_catalog)
    assert not [item for item in _DeviceDescriptorEntries_Get(model, builtin_catalog)
                if item["class"] == MAG]
    result = _Compile_Run(model, builtin_catalog, tmp_path, 200, 0, 0)
    assert result.returncode == 0, result.stderr


def test_missing_magnetic_resource_bindings_still_block_full_generation(builtin_catalog):
    model = _Model_Create(builtin_catalog, devices=[DeviceInstance(
        'mag0', 'silverstar.device.magnetometer.lis3mdl', 'i2c', 'uhp_20_hz_4g')])
    result = Project_Validate(model, builtin_catalog)
    assert not result.valid
    assert any('mag0:data' in issue.message for issue in result.issues)
    with pytest.raises(ValueError, match='Unassigned resource requirement: mag0:data'):
        _FlightConfigHeader_Render(model, builtin_catalog)


@pytest.mark.parametrize("chip,profile", [("lis3mdl", "uhp_20_hz_4g"),
                                         ("mmc5983ma", "oneshot_20_hz_8g")])
@pytest.mark.parametrize("interface", ["i2c", "spi"])
def test_dedicated_mag_restores_dispatch_and_20hz_without_jy_frames(
        builtin_catalog, tmp_path, chip, profile, interface):
    model = _Model_Create(builtin_catalog, devices=[DeviceInstance(
        "mag0", "silverstar.device.magnetometer." + chip, interface, profile)])
    before = model.Dictionary_Get()
    assert not ReleaseCompatibilityIssues_Get(model)
    entries = [item for item in _DeviceDescriptorEntries_Get(model, builtin_catalog)
               if item["class"] == MAG]
    assert len(entries) == 1 and entries[0]["_source_instance_id"] == "mag0"
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    prefix = ("Lis3mdl" if chip == "lis3mdl" else "Mmc5983ma") + interface.capitalize()
    assert prefix + "MagnetometerInstance_Process(0U)" in source
    result = _Compile_Run(model, builtin_catalog, tmp_path, 20, 1, 0)
    assert result.returncode == 0, result.stderr
    assert model.Dictionary_Get() == before


def test_explicit_jy_profile_keeps_module_identity_and_unqualified_capture(builtin_catalog, tmp_path):
    model = _Model_Create(builtin_catalog, capture=True)
    view = builtin_catalog.ProjectView_Get(model)
    entries = [item for item in _DeviceDescriptorEntries_Get(model, view) if item["class"] == MAG]
    assert len(entries) == 1 and entries[0]["_source_instance_id"] == "imu0"
    assert "Jy901bMagnetometerInstance_Process(0U)" in _DeviceInstancesSource_Render(model, view)
    manifest = view.InstanceIdComponent_Get("imu0")
    assert {"magnetometer.field", "magnetometer.physical_unit"} <= set(manifest.provides)
    assert "magnetometer.absolute_vector_qualified" not in manifest.provides
    assert ".module_variant = 0U" in _InstanceResourcesSource_Render(model, view)
    result = _Compile_Run(model, view, tmp_path, 200, 1, 1)
    assert result.returncode == 0, result.stderr


def test_two_explicit_jy_instances_remain_separate(builtin_catalog):
    model = _Model_Create(builtin_catalog, capture=True, devices=[
        DeviceInstance("imu1", JY, "uart", PROFILE)])
    entries = [item for item in _DeviceDescriptorEntries_Get(model, builtin_catalog) if item["class"] == MAG]
    assert len(entries) == 2
    assert entries[0]["physical_device_id"] != entries[1]["physical_device_id"]
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    assert "Jy901bMagnetometerInstance_Process(0U)" in source
    assert "Jy901bMagnetometerInstance_Process(1U)" in source


def test_explicit_jy_capture_has_valid_project_and_unchanged_source_ownership(builtin_catalog):
    default = _Model_Create(builtin_catalog)
    capture = _Model_Create(builtin_catalog, capture=True)
    ordinary_graph = SourceGraph_Resolve(default, builtin_catalog)
    capture_graph = SourceGraph_Resolve(capture, builtin_catalog)
    assert ordinary_graph.sources == capture_graph.sources
    assert ordinary_graph.include_dirs == capture_graph.include_dirs
    assert ordinary_graph.defines == capture_graph.defines
    assert capture.strategies == default.strategies and capture.alignment == default.alignment
    reconciled = ProjectConfiguration_Reconcile(capture, builtin_catalog).model
    assert not Project_Validate(reconciled, builtin_catalog).issues


def test_dedicated_descriptor_cannot_silently_replace_20hz_with_200hz(builtin_catalog, monkeypatch):
    model = _Model_Create(builtin_catalog, devices=[DeviceInstance(
        "mag0", "silverstar.device.magnetometer.lis3mdl", "i2c", "uhp_20_hz_4g")])
    view = builtin_catalog.ProjectView_Get(model)
    original = view.InstanceIdComponent_Get("mag0")
    metadata = deepcopy(original.metadata)
    metadata["runtime_defaults"][MAG]["SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ"] = 200
    monkeypatch.setitem(view._instance_components, "mag0", replace(original, metadata=metadata))
    with pytest.raises(ValueError, match="MAG descriptor and runtime output rate disagree"):
        _FlightConfigHeader_Render(model, view)


def test_mixed_jy_opt_in_is_rejected_instead_of_enabling_every_module(builtin_catalog):
    model = _Model_Create(builtin_catalog, capture=True, devices=[
        DeviceInstance("imu1", JY, "uart", "jy901b")])
    with pytest.raises(ValueError, match="JY901B.*all.*explicit"):
        _FlightConfigHeader_Render(model, builtin_catalog)


def test_mixed_200hz_and_20hz_mag_instances_are_rejected(builtin_catalog):
    model = _Model_Create(builtin_catalog, capture=True, devices=[DeviceInstance(
        "mag0", "silverstar.device.magnetometer.lis3mdl", "i2c", "uhp_20_hz_4g")])
    with pytest.raises(ValueError, match="MAG.*shared output rate"):
        _FlightConfigHeader_Render(model, builtin_catalog)


@pytest.mark.parametrize("fault", ["missing_field", "missing_unit", "bad_default"])
def test_invalid_capture_declarations_reject_generation(builtin_catalog, monkeypatch, fault):
    model = _Model_Create(builtin_catalog, capture=True)
    view = builtin_catalog.ProjectView_Get(model)
    original = view.InstanceIdComponent_Get("imu0")
    if fault == "bad_default":
        metadata = deepcopy(original.metadata)
        metadata["runtime_defaults"][MAG]["SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ"] = 20
        changed = replace(original, metadata=metadata)
    else:
        capability = "magnetometer.field" if fault == "missing_field" else "magnetometer.physical_unit"
        changed = replace(original, provides=tuple(item for item in original.provides if item != capability))
    monkeypatch.setitem(view._instance_components, "imu0", changed)
    with pytest.raises(ValueError, match="[Mm]agnetometer|MAG"):
        _FlightConfigHeader_Render(model, view)


def test_two_20hz_devices_are_supported(builtin_catalog, tmp_path):
    model = _Model_Create(builtin_catalog, devices=[
        DeviceInstance("mag0", "silverstar.device.magnetometer.lis3mdl", "i2c", "uhp_20_hz_4g"),
        DeviceInstance("mag1", "silverstar.device.magnetometer.mmc5983ma", "spi", "oneshot_20_hz_8g")])
    assert len([item for item in _DeviceDescriptorEntries_Get(model, builtin_catalog)
                if item["class"] == MAG]) == 2
    result = _Compile_Run(model, builtin_catalog, tmp_path, 20, 1, 0)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("override", ["SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ=200U",
                                     "JY901B_MAGNETOMETER_ADAPTER_ENABLE=1U"])
def test_inconsistent_build_overrides_fail_compilation(builtin_catalog, tmp_path, override):
    model = _Model_Create(builtin_catalog, devices=[DeviceInstance(
        "mag0", "silverstar.device.magnetometer.lis3mdl", "i2c", "uhp_20_hz_4g")])
    result = _Compile_Run(model, builtin_catalog, tmp_path, 20, 1, 0,
                          overrides=["-D" + override])
    assert result.returncode != 0
    assert "explicit magnetic" in result.stderr


def test_jy_rate_override_must_match_actual_imu_rate(builtin_catalog, tmp_path):
    model = _Model_Create(builtin_catalog, capture=True)
    result = _Compile_Run(model, builtin_catalog, tmp_path, 200, 1, 1,
                          overrides=["-DSYSTEM_IMU_OUTPUT_RATE_HZ=100U"])
    assert result.returncode != 0
    assert "JY rate override conflicts with explicit magnetic" in result.stderr


def test_unsupported_imu_does_not_acquire_mag(builtin_catalog):
    model = _Model_Create(builtin_catalog)
    model.device_instances = [replace(item, plugin="silverstar.device.imu.mpu9250",
                                      interface="", profile="") if item.plugin == JY else item
                              for item in model.device_instances]
    assert not [item for item in _DeviceDescriptorEntries_Get(model, builtin_catalog)
                if item["class"] == MAG]

