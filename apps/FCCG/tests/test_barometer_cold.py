from pathlib import Path

from silverstar_fccg.generator.render import _DeviceInstancesHeader_Render
from silverstar_fccg.app.service import FccgService
from test_joint_sensor_library import _Command_Run, _Compiler_Get

BUILTIN = Path(__file__).resolve().parents[1] / "plugins/builtin"


def test_actual_cold_controller_and_pressure_datum(tmp_path, builtin_catalog):
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    reference_model = FccgService(BUILTIN.parents[1]).ReferenceProject_Create("cold_host")
    (tmp_path / "project_device_instances.h").write_text(
        _DeviceInstancesHeader_Render(reference_model, builtin_catalog), encoding="utf-8")
    includes = [tmp_path, core / "System/Inc", core / "Interfaces/Inc", core / "Common/Inc",
                BUILTIN / "silverstar_platform_api/payload/Platform/Inc"]
    sources = [core / "System/Src/system_barometer_cold.c", core / "System/Src/system_barometer.c",
               core / "Tests/Host/test_barometer_cold.c"]
    flags = [_Compiler_Get(), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fanalyzer",
             "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla",
             "-DSYSTEM_BUILD_BAROMETER_COLD_ENABLED=1U"]
    binary = tmp_path / "cold.exe"
    _Command_Run(flags + ["-I" + str(path) for path in includes] + [str(p) for p in sources]
                 + ["-lm", "-o", str(binary)], tmp_path, "compile_cold")
    output = _Command_Run([str(binary)], tmp_path, "run_cold")
    assert "cold barometer order/cache/stop/start/exhaustion/wrap/pressure datum PASS" in output
