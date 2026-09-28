import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create


@pytest.mark.parametrize("device,qualified", [
    ("bmi088", 0), ("bmi323", 1), ("icm42688p", 1), ("icm45686", 1),
    ("lsm6dsv32x", 1), ("mpu6050", 1),
])
def test_single_new_imu_compiles_without_legacy_headers(builtin_catalog, tmp_path: Path, device, qualified):
    from test_internal_platform_refactor import _CustomModel_Create

    from silverstar_fccg.generator.render import (
        AlgorithmParametersHeader_Render,
        _DeviceBuildCapabilitiesHeader_Render,
        _FlightConfigHeader_Render,
    )
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile

    model = _CustomModel_Create(builtin_catalog, [DeviceInstance("imu0", "silverstar.device.imu." + device)])
    model.strategies = {}
    model.modes = {}
    model.protocols = {}
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    for name, content in {
        "project_device_build_capabilities.h": _DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog),
        "project_flight_config.h": _FlightConfigHeader_Render(model, builtin_catalog),
        "project_algorithm_parameters.h": AlgorithmParametersHeader_Render(model, builtin_catalog),
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    source = tmp_path / "facts.c"
    source.write_text(
        '#include "project_flight_config.h"\n#include "target_system_config.h"\n'
        '_Static_assert(SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE == 1U, "raw acceleration");\n'
        f'_Static_assert(SYSTEM_SELECTED_IMU_SOFTWARE_PROPAGATION_QUALIFIED == {qualified}U, "actual qualification");\n'
        '_Static_assert(SYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE == 0U, "no JY noise fallback");\n'
        '_Static_assert(SYSTEM_SELECTED_GNSS_POSITION_AVAILABLE == 0U, "no M9 fallback");\n'
        '_Static_assert(SYSTEM_SELECTED_BAROMETER_DIRECT_ALTITUDE_AVAILABLE == 0U, "no JY baro fallback");\n'
        '_Static_assert(SYSTEM_SELECTED_HARDWARE_QUATERNION_OUTPUT_AVAILABLE == 0U, "no JY quaternion fallback");\n'
        'int main(void) { return 0; }\n', encoding="utf-8")
    includes = [tmp_path]
    for component in model.ComponentIds_Get():
        manifest = builtin_catalog.Component_Get(component)
        includes.extend(manifest.payload_root / value for value in manifest.build.include_dirs)
    assert not any("JY901B" in str(path) or "NEO_M9N" in str(path) for path in includes)
    compiler = shutil.which("gcc")
    assert compiler
    result = subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                             "-o", str(tmp_path / "facts.o")] + ["-I" + str(path) for path in includes],
                            cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_reference_and_mixed_primary_capabilities_follow_provider(builtin_catalog):
    from silverstar_fccg.generator.render import _DeviceBuildCapabilitiesHeader_Render

    model = ReferenceProject_Create("ProviderFacts", catalog=builtin_catalog)
    header = _DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog)
    assert "SYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE 1U" in header
    assert "SYSTEM_SELECTED_BAROMETER_ALIGNMENT_ORIGIN_QUALIFIED 1U" in header
    assert "SYSTEM_SELECTED_GNSS_RECOMMENDED_VELOCITY_STD_FLOOR_MPS 0.15f" in header
    model.device_instances.insert(0, DeviceInstance("raw0", "silverstar.device.imu.bmi088"))
    model.strategies = {}
    model.modes = {}
    model.capability_source_overrides.clear()
    header = _DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog)
    assert "SYSTEM_SELECTED_IMU_SOFTWARE_PROPAGATION_QUALIFIED 0U" in header
    assert "SYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE 0U" in header
    assert "SYSTEM_SELECTED_BAROMETER_DIRECT_ALTITUDE_AVAILABLE 1U" in header


@pytest.mark.parametrize("selection", ["selected", "absent", "missing", "invalid"])
def test_indicator_requires_explicit_boolean_project_binding(builtin_catalog, tmp_path, selection):
    from silverstar_fccg.generator.render import (
        AlgorithmParametersHeader_Render,
        _DeviceBuildCapabilitiesHeader_Render,
        _FlightConfigHeader_Render,
    )
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile

    model = ReferenceProject_Create("IndicatorBinding", catalog=builtin_catalog)
    if selection == "absent":
        model.device_instances = [device for device in model.device_instances
                                  if device.plugin != "silverstar.device.indicator.system_status"]
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    for name, content in {
        "project_device_build_capabilities.h": _DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog),
        "project_flight_config.h": _FlightConfigHeader_Render(model, builtin_catalog),
        "project_algorithm_parameters.h": AlgorithmParametersHeader_Render(model, builtin_catalog),
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    lines = ['#include "project_flight_config.h"']
    if selection in {"missing", "invalid"}:
        lines.append("#undef SYSTEM_INDICATOR_SYSTEM_ENABLE")
    if selection == "invalid":
        lines.append("#define SYSTEM_INDICATOR_SYSTEM_ENABLE 2U")
    lines.append('#include "system_user_config.h"')
    if selection in {"selected", "absent"}:
        expected = 1 if selection == "selected" else 0
        lines.append(f'_Static_assert(SYSTEM_INDICATOR_SYSTEM_ENABLE == {expected}U, "actual device selection");')
    source = tmp_path / "indicator_binding.c"
    source.write_text("\n".join(lines), encoding="utf-8")
    includes = [tmp_path]
    for component in model.ComponentIds_Get():
        manifest = builtin_catalog.Component_Get(component)
        includes.extend(manifest.payload_root / value for value in manifest.build.include_dirs)
    compiler = shutil.which("gcc")
    assert compiler
    result = subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                             "-o", str(tmp_path / "indicator_binding.o")] + ["-I" + str(path) for path in includes],
                            cwd=tmp_path, text=True, capture_output=True)
    if selection in {"selected", "absent"}:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
        expected = "must be bound by project_flight_config.h" if selection == "missing" else "must be 0 or 1"
        assert expected in result.stderr
