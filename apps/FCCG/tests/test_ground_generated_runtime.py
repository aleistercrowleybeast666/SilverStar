"""Execute the actual fresh generated Ground adapter; no hardware claim."""
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import GroundFiles_Render
from silverstar_fccg.generator.render import AirLinkHeader_Render
from ground_radio_led_fixture import GroundMultiFixture_Create
from test_round2_targets import _GroundBoardProject_Get


def _GeneratedRuntime_Check(catalog, root, count, owner=0, led=False):
    gcc = shutil.which("gcc")
    assert gcc is not None, "Host GCC required for runtime readiness validation"
    model = (_GroundBoardProject_Get(catalog) if count == 1
             else GroundMultiFixture_Create(catalog, root, count, owner))
    if led:
        ground = model.ground_target
        resource = next(r for r in ground.hardware.resources
                        if r.kind == "gpio_output" and r.metadata.get("label") == "LED")
        model.ground_target = replace(ground, tx_led_resource=resource.resource_id,
                                      rx_led_resource=resource.resource_id)
    generated = GroundFiles_Render(model, catalog, WorkspacePolicy(root))
    output = root / "Ground_Station"
    for relative, content in generated.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if count == 1:
        assert generated["Generated/Inc/air_link_config.h"] == AirLinkHeader_Render(model, target="ground").encode()
    else:
        assert b"AIR_LINK_HAL_BUFFER_SIZE 260U" in generated["Generated/Inc/air_link_config.h"]
    assert b"#include <stddef.h>" in generated["Generated/Src/pc_byte_stream.c"]
    includes = ["Generated/Inc", "Common/Inc", "Ground/Core/Inc", "Platform/Inc", "Platform/STM32F1/Inc", "Interfaces/Inc",
                "Devices/Telemetry/SX1281/Inc", "Middlewares/Third_Party/SX1280lib"]
    fixture = Path(__file__).parent / "fixtures/ground_radio_runtime_host.c"
    executable = root / "generated-runtime.exe"
    compiled = subprocess.run([gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        *("-I" + str(output / p) for p in includes), str(fixture),
        str(output / "Common/Src/silverstar_assert.c"),
        str(output / "Ground/Radio/Src/ground_radio_activity.c"),
        str(output / "Ground/Radio/Src/ground_radio_sx1281.c"), "-o", str(executable)],
        capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    scenarios = ["routing", "quiet"]
    if count == 1:
        scenarios += ["init_error", "config_error", "role_error"]
    elif owner == 0:
        scenarios += ["transient", "init_error", "retire_error", "forward", "wrap", "cold_start_error"]
    if led: scenarios.append("led")
    for scenario in scenarios:
        result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, scenario + result.stdout + result.stderr
    return model, output, scenarios


@pytest.mark.parametrize("count,owner,led", [(1,0,False), (1,0,True), (2,0,False), (2,1,False), (2,0,True)])
def test_actual_fresh_generated_runtime(builtin_catalog, tmp_path, count, owner, led):
    _GeneratedRuntime_Check(builtin_catalog, tmp_path, count, owner, led)


def test_ground_board_pc13_has_verified_output_mapping(builtin_catalog, tmp_path):
    model = _GroundBoardProject_Get(builtin_catalog)
    led = next((r for r in model.ground_target.hardware.resources
                if r.kind == "gpio_output" and r.metadata.get("label") == "LED"), None)
    assert led is not None, "Ground PCB PC13 LED output is missing from GPIO choices"
    assert led.resource_id == "PLATFORM_GPIO_6"
    assert led.metadata["physical_pin"] == "PC13-TAMPER-RTC"
    assert led.metadata["fixed_logical_index"] == 6
    model.ground_target = replace(model.ground_target, tx_led_resource=led.resource_id,
                                  rx_led_resource=led.resource_id)
    output = GroundFiles_Render(model, builtin_catalog, WorkspacePolicy(tmp_path))
    assert b"[PLATFORM_GPIO_6] = {LED_GPIO_Port, LED_Pin, 0U}" in output["Generated/Src/platform_resources.c"]
    assert b"GROUND_ACTIVITY_TX_GPIO ((PlatformGpioId)6U)" in output["Generated/Inc/ground_radio_config.h"]
    assert b"GROUND_ACTIVITY_RX_GPIO ((PlatformGpioId)6U)" in output["Generated/Inc/ground_radio_config.h"]
    assert not _GroundBoardProject_Get(builtin_catalog).ground_target.tx_led_resource


@pytest.mark.parametrize("pin,labelled", [("PC13-TAMPER-RTC",True), ("PC13-TAMPER-RTC",False), ("PA8",False)])
def test_cubemx_multi_suffix_gpio_identity(pin, labelled):
    from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
    text = f"Mcu.Name=STM32F103C8Tx\n{pin}.Signal=GPIO_Output\n"
    if labelled: text += f"{pin}.GPIO_Label=LED\n"
    resources = CubeMxInventory_Parse(text).HardwareResources_Get()
    resource = next(r for r in resources if r.kind == "gpio_output")
    assert resource.metadata["physical_pin"] == pin
    assert resource.metadata["port"] == ("LED_GPIO_Port" if labelled else "GPIO" + pin[1])
    assert resource.metadata["pin"] == ("LED_Pin" if labelled else "GPIO_PIN_" + pin[2:].split("-")[0])


def test_secondary_ground_binding_errors_stop_before_generation(builtin_catalog, tmp_path):
    from silverstar_fccg.project.air_link import GroundTargetIssues_Get
    model = GroundMultiFixture_Create(builtin_catalog, tmp_path, 2)
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    bindings = dict(model.ground_target.resource_assignments)
    del bindings["radio1:radio_nss"]
    model.ground_target = replace(model.ground_target, resource_assignments=bindings)
    issues = GroundTargetIssues_Get(model, builtin_catalog)
    assert any(issue.code == "GROUND_RADIO_RESOURCE_UNBOUND" and "radio1 radio_nss" in issue.message for issue in issues)
    with pytest.raises(ValueError, match="radio1 radio_nss"):
        GroundFiles_Render(model, builtin_catalog, WorkspacePolicy(tmp_path))
    assert not (tmp_path / "Ground_Station/Makefile").exists()
    bindings["radio1:radio_nss"] = bindings["radio0:radio_nss"]
    model.ground_target = replace(model.ground_target, resource_assignments=bindings)
    assert "GROUND_RESOURCE_CONFLICT" in {issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)}
