"""Strict ARM compile and Host execution of the fresh generated facade."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.generator.render import GeneratedFiles_Render


@pytest.mark.parametrize("telemetry", [False, True])
def test_fresh_facade_control_without_and_with_telemetry(workspace_root, tmp_path, telemetry):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("FacadeControl")
    if not telemetry:
        model.device_instances = [item for item in model.device_instances
                                  if item.plugin != "silverstar.device.telemetry.sx1281"]
        model = service.ProjectConfiguration_Reconcile(model).model
        assert model.protocols["telemetry"] is None
    root = tmp_path / "project"
    # Match the sensor-matrix source-generation boundary: AIR validation
    # currently requires a radio, while the reusable facade supports zero.
    catalog = service.catalog.ProjectView_Get(model)
    graph = SourceGraph_Resolve(model, catalog)
    for component_id in model.ComponentIds_Get():
        component = catalog.Component_Get(component_id)
        for original in component.PayloadFiles_Get():
            target = root / original.relative_to(component.payload_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
    for relative, content in GeneratedFiles_Render(model, catalog, graph).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    includes = ["-I" + str(root / p) for p in graph.include_dirs]
    defines = ["-D" + value for value in graph.defines]
    forced = [argument for path in graph.forced_includes for argument in ("-include",str(root/path))]
    arm = os.environ.get("FCCG_TEST_ARM_GCC") or shutil.which("arm-none-eabi-gcc")
    host = shutil.which("gcc")
    assert arm and host, "Actual ARM and Host GCC are required"
    source = root / "Generated/Src/project_device_instances.c"
    command = [arm, *graph.mcu_flags, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
               *includes, *defines, *forced, "-c", str(source), "-o", str(tmp_path/"facade-arm.o")]
    result = subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/"arm.log").write_text(result.stdout+result.stderr,encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    harness = tmp_path / "control.c"
    harness.write_text("""
#include <assert.h>
#include "project_device_instances.h"
static unsigned calls;
SystemDeviceResult Sx1281TelemetryInstance_SendControl(uint8_t source_instance,
    const uint8_t *data, uint16_t length, uint32_t *transaction_id)
{
    assert(source_instance == 0U && data != 0 && data[0] == 41U && length == 1U);
    assert(transaction_id != 0); calls++; *transaction_id = 777U;
    return SYSTEM_DEVICE_OK;
}
int main(void)
{
    const uint8_t data = 41U;
    uint32_t transaction = 123U;
    assert(ProjectTelemetryInstance_SendControl(0U, 0, 1U, &transaction) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    assert(ProjectTelemetryInstance_SendControl(0U, &data, 0U, &transaction) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    assert(transaction == 123U && calls == 0U);
    assert(ProjectTelemetryInstance_SendControl(255U, &data, 1U, &transaction) == SYSTEM_DEVICE_NOT_PRESENT);
    assert(transaction == 123U && calls == 0U);
    if (TEST_TELEMETRY != 0)
    {
        assert(ProjectTelemetryInstance_SendControl(0U, &data, 1U, &transaction) == SYSTEM_DEVICE_OK);
        assert(transaction == 777U && calls == 1U);
    }
    else
    {
        assert(ProjectTelemetryInstance_SendControl(0U, &data, 1U, &transaction) == SYSTEM_DEVICE_NOT_PRESENT);
        assert(ProjectTelemetryInstance_SendControl(0U, &data, 1U, 0) == SYSTEM_DEVICE_NOT_PRESENT);
        assert(transaction == 123U && calls == 0U);
    }
    return 0;
}
""",encoding="utf8")
    # Compile the entire generated translation unit with strict Host warnings.
    options = [host, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               *includes, *defines, *forced]
    result = subprocess.run([*options, "-c", str(source), "-o", str(tmp_path/"facade-host.o")],
                            capture_output=True, text=True, timeout=60)
    (tmp_path/"host-compile.log").write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    # MinGW retains unrelated externally visible facade functions during PE
    # linking. Execute this function's verbatim generated body separately.
    generated = source.read_text(encoding="utf8")
    start = generated.index("SystemDeviceResult ProjectTelemetryInstance_SendControl(")
    opening = generated.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (generated[end] == "{") - (generated[end] == "}")
        end += 1
    control = tmp_path / "control-facade.c"
    generated_includes = "\n".join(line for line in generated.splitlines()
                                   if line.startswith("#include "))
    control.write_text(generated_includes + "\n" + generated[start:end] + "\n", encoding="utf8")
    executable = tmp_path / "facade-host.exe"
    command = [*options, "-DTEST_TELEMETRY="+str(int(telemetry)), str(control),
               str(harness), "-o", str(executable)]
    result = subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/"host-link.log").write_text(result.stdout+result.stderr,encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
