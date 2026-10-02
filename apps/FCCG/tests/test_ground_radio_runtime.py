from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace, make_dataclass, fields

import pytest

from silverstar_fccg.generator.ground_radio import GroundRadioConfig_Render, GroundRadioAirHeader_Render
from silverstar_fccg.project.model import GroundRadioConfiguration, GroundTargetConfiguration, HardwareResource


def config(count=1, initial=0, tx="", rx="", tx_high=False, rx_high=False):
    radios = tuple(GroundRadioConfiguration(instance_id=f"radio{i}",
        plugin="silverstar.device.telemetry.sx1281", module_variant="e28_2g4m12sx") for i in range(count))
    return SimpleNamespace(radio_instances=radios, active_radio_instance=f"radio{initial}",
        tx_led_resource=tx, rx_led_resource=rx, tx_led_active_high=tx_high,
        rx_led_active_high=rx_high, activity_led_pulse_ms=40,
        hardware=SimpleNamespace(resources=(
            HardwareResource("led_a", "gpio_output", {"fixed_logical_index": 8, "logical_index": 4}),
            HardwareResource("led_b", "gpio_output", {"logical_index": 9}),
        )))


@pytest.fixture(scope="module")
def runtime_executables(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
    ground = root / "plugins/builtin/silverstar_core_ground_0_1_0/payload/Ground"
    radio = root / "plugins/builtin/silverstar_device_telemetry_sx1281/payload"
    result = {}
    for name, cfg in {"single": config(), "multi": config(2),
        "owner": config(3, 1), "shared_led": config(tx="led_a", rx="led_a"),
        "separate_led": config(tx="led_a", rx="led_b", rx_high=True)}.items():
        work = tmp_path_factory.mktemp(name)
        (work / "ground_radio_config.h").write_text(GroundRadioConfig_Render(cfg), encoding="utf-8")
        (work / "project_resources.h").write_text(f"#define PROJECT_SX1281_INSTANCE_COUNT {len(cfg.radio_instances)}U\n", encoding="utf-8")
        includes = [work, core / "Inc", ground / "Core/Inc",
            root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
            radio / "Devices/Telemetry/SX1281/Inc", radio / "Middlewares/Third_Party/SX1280lib"]
        executable = work / "runtime.exe"
        command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            *("-I" + str(path) for path in includes),
            str(root / "tests/fixtures/ground_radio_runtime_host.c"),
            str(core / "Src/silverstar_assert.c"), str(ground / "Radio/Src/ground_radio_activity.c"),
            str(ground / "Radio/Src/ground_radio_sx1281.c"), "-o", str(executable)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        result[name] = executable
    return result


@pytest.mark.parametrize("name,scenario", [
    ("single", "routing"), ("single", "quiet"), ("single", "init_error"),
    ("single", "config_error"), ("single", "role_error"),
    ("multi", "routing"), ("multi", "quiet"), ("multi", "transient"),
    ("multi", "init_error"), ("multi", "retire_error"), ("multi", "forward"), ("multi", "wrap"),
    ("multi", "cold_start_error"),
    ("owner", "routing"), ("owner", "forward"),
    ("shared_led", "led"), ("separate_led", "led"),
])
def test_runtime(runtime_executables, name, scenario):
    result = subprocess.run([str(runtime_executables[name]), scenario], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_header_and_fixed_led_index():
    original = "original AIR M0 header\n"
    assert GroundRadioAirHeader_Render(config(), original) == original
    assert "((PlatformGpioId)8U)" in GroundRadioConfig_Render(config(tx="led_a"))
    assert "GROUND_ACTIVITY_ENABLED 0U" in GroundRadioConfig_Render(config())


@pytest.mark.parametrize("fault", ["missing", "polarity", "pulse", "duplicate", "owner", "capacity", "power_type", "power", "variant"])
def test_render_rejects_invalid_configuration(fault):
    cfg = config()
    if fault == "missing": cfg.tx_led_resource = "unknown"
    elif fault == "polarity":
        cfg.tx_led_resource = cfg.rx_led_resource = "led_a"
        cfg.rx_led_active_high = True
    elif fault == "pulse": cfg.activity_led_pulse_ms = 201
    elif fault == "duplicate": cfg.radio_instances = (cfg.radio_instances[0],) * 2
    elif fault == "owner": cfg.active_radio_instance = "absent"
    elif fault == "capacity": cfg = config(5)
    elif fault == "power_type": cfg.radio_instances = (replace(cfg.radio_instances[0], tx_power_dbm="12;"),)
    elif fault == "power": cfg.radio_instances = (replace(cfg.radio_instances[0], tx_power_dbm=13),)
    elif fault == "variant": cfg.radio_instances = (replace(cfg.radio_instances[0], module_variant="unvalidated"),)
    with pytest.raises(ValueError): GroundRadioConfig_Render(cfg)


def test_ready_metadata_and_configurable_led_generated_source(builtin_catalog, tmp_path):
    from ground_radio_led_fixture import GroundMultiFixture_Create
    from silverstar_fccg.generator.multi_target import GroundFiles_Render
    from silverstar_fccg.core.workspace import WorkspacePolicy
    core = builtin_catalog.Component_Get("silverstar.core.ground.0_1_0")
    assert core.metadata["ground_activity_leds_ready"] is True
    model = GroundMultiFixture_Create(builtin_catalog, tmp_path, 1, activity_led=True)
    ground = model.ground_target
    led = next(item for item in ground.hardware.resources if item.metadata.get("label") == "ACTIVITY_LED")
    led_type = make_dataclass("LedGround", [("tx_led_resource",str,""), ("tx_led_active_high",bool,False),
        ("rx_led_resource",str,""), ("rx_led_active_high",bool,False), ("activity_led_pulse_ms",int,40)],
        bases=(GroundTargetConfiguration,), frozen=True)
    values = {field.name: getattr(ground, field.name) for field in fields(ground)}
    values.update(tx_led_resource=led.resource_id, rx_led_resource=led.resource_id,
                  tx_led_active_high=False, rx_led_active_high=False, activity_led_pulse_ms=40)
    model.ground_target = led_type(**values)
    generated = GroundFiles_Render(model, builtin_catalog, WorkspacePolicy(tmp_path))
    source = "Ground/Radio/Src/ground_radio_activity.c"
    assert generated[source] == (core.payload_root / source).read_bytes()
    assert source.encode() in generated["Makefile"]
    assert b"GROUND_ACTIVITY_ENABLED 1U" in generated["Generated/Inc/ground_radio_config.h"]
    assert b"AIR_LINK_HAL_BUFFER_SIZE" not in generated["Generated/Inc/air_link_config.h"]
    assert b"HAL_Delay" not in generated[source]
