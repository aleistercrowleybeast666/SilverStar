"""JY901 wire masks and real parser-to-adapter magnetic publication (no hardware)."""
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.render import (
    _DeviceDescriptorEntries_Get, _FlightConfigHeader_Render,
    _InstanceResourcesSource_Render,
)
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.plugins.catalog import PluginCatalogError


JY = "silverstar.device.imu.jy901b"
MAG = "SYSTEM_DEVICE_CLASS_MAGNETOMETER"


@pytest.mark.parametrize("profile,capture,variant", [
    ("", False, 0),
    ("jy901b", False, 0), ("jy901s", False, 1),
    ("jy901b_mag_capture", True, 0), ("jy901s_mag_capture", True, 1),
])
def test_saved_profile_selects_only_requested_magnetic_frames(builtin_catalog, profile, capture, variant):
    model = ReferenceProject_Create("MagneticSelection", catalog=builtin_catalog)
    model.device_instances = [replace(item, profile=profile) if item.plugin == JY else item
                              for item in model.device_instances]
    # Exercise actual saved-project parsing as well as concrete variant lookup.
    model = ProjectModel_Parse(json.loads(json.dumps(model.Dictionary_Get())))
    view = builtin_catalog.ProjectView_Get(model)
    entries = _DeviceDescriptorEntries_Get(model, view)
    assert bool([item for item in entries if item["class"] == MAG]) is capture
    header = _FlightConfigHeader_Render(model, view)
    assert re.search(r"#define\s+JY901B_MAGNETOMETER_ADAPTER_ENABLE\s+" +
                     ("1U" if capture else "0U") + r"\b", header)
    assert f".module_variant = {variant}U" in _InstanceResourcesSource_Render(model, view)
    if variant == 1:
        assert not [item for item in entries if item["class"] == "SYSTEM_DEVICE_CLASS_BAROMETER"]


@pytest.mark.parametrize("profile", ["jy61p", "jy62"])
def test_six_axis_only_model_is_not_assumed_magnetic(builtin_catalog, profile):
    model = ReferenceProject_Create("UnsupportedMagneticModel", catalog=builtin_catalog)
    model.device_instances = [replace(item, profile=profile) if item.plugin == JY else item
                              for item in model.device_instances]
    with pytest.raises(PluginCatalogError, match="valid interface and profile"):
        builtin_catalog.ProjectView_Get(model)


@pytest.fixture(scope="module")
def magnetic_executable(request, tmp_path_factory):
    gcc = shutil.which("gcc")
    assert gcc, "Host GCC required for magnetic contracts"
    root = Path(__file__).resolve().parents[1]
    builtin = root / "plugins/builtin"
    core = builtin / "silverstar_core_0_1_0/payload"
    jy = builtin / "silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B"
    fixture = core / "Tests/Host/Fixtures/MultiInstance"
    output = tmp_path_factory.mktemp(f"jy-mag-{request.param}")
    # Unit fixture, not a target header: the full generated project is validated separately.
    (output / "system_user_config.h").write_text(
        "#define SYSTEM_IMU_OUTPUT_RATE_HZ 200U\n#define SYSTEM_LOCAL_GRAVITY_MPS2 9.78f\n",
        encoding="utf-8")
    includes = [output, fixture / "Inc", core / "System/Inc", core / "Interfaces/Inc",
                core / "Common/Inc", core / "Tests/Host", jy / "Inc", jy / "Adapter/Inc",
                builtin / "silverstar_platform_api/payload/Platform/Inc"]
    sources = [core / "Tests/Host/host_platform_mock.c", core / "Common/Src/silverstar_assert.c",
               fixture / "multi_instance_resources.c", core / "System/Src/system_device_startup.c",
               jy / "Src/jy901b_device.c", jy / "Adapter/Src/jy901b_startup.c",
               jy / "Adapter/Src/jy901b_sample_quality.c", jy / "Adapter/Src/jy901b_imu_adapter.c",
               jy / "Adapter/Src/jy901b_magnetometer_adapter.c",
               root / "tests/fixtures/jy901_magnetic_host.c"]
    exe = output / "mag.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               f"-DJY901B_MAGNETOMETER_ADAPTER_ENABLE={request.param}U",
               *["-I" + str(path) for path in includes], *map(str, sources), "-lm", "-o", str(exe)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / "compile.json").write_text(json.dumps(dict(command=command,
        exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2), encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return exe, request.param


@pytest.mark.parametrize("magnetic_executable,scenario", [
    (0, "mask"), (0, "disabled"), (1, "mask"), (1, "sample"),
    (1, "reserved_tail"), (1, "stale"),
    (1, "startup"), (1, "readback_rejected"),
], indirect=["magnetic_executable"], scope="module")
def test_parser_and_publication_contracts(magnetic_executable, scenario):
    exe, _enabled = magnetic_executable
    result = subprocess.run([str(exe), scenario], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
