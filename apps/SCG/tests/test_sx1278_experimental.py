"""The SX1278 experiment is isolated from the existing SX1281/E28 defaults."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.sx1278 import (
    SX1278_PLUGIN, Sx1278Header_Render, Sx1278Link_Validate, Sx1278Module_Validate,
)

STRICT_WARNINGS = ["-Wall", "-Wextra", "-Werror", "-Wpedantic", "-Wconversion",
    "-Wsign-conversion", "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion",
    "-Wcast-align", "-Wcast-qual", "-Wstrict-prototypes", "-Wmissing-prototypes",
    "-Wswitch-enum", "-Wvla"]


def Sx1278Model_Get(catalog):
    model = ReferenceProject_Create("Sx1278Experiment", catalog=catalog)
    model.device_instances = [replace(item, plugin=SX1278_PLUGIN,
        module_variant="e32_400m20s", tx_power_dbm=17)
        if item.instance_id == model.air_link.flight_radio_instance else item
        for item in model.device_instances]
    model.air_link = replace(model.air_link, radio_family="sx127x", frequency_hz=433000000,
        bandwidth_hz=125000, spreading_factor=7, packet_mtu=61)
    return model


def test_sx1278_catalog_and_explicit_profile(builtin_catalog):
    manifest = builtin_catalog.Component_Get(SX1278_PLUGIN)
    assert manifest.physical_device.chipset == "SX1278"
    assert manifest.radio.family == "sx127x" and manifest.radio.maximum_payload == 61
    requirements = {item.name: item for item in manifest.resource_requirements}
    assert set(requirements) == {"radio_bus", "radio_nss", "radio_reset", "radio_dio0",
                                 "radio_rx_en", "radio_tx_en", "time"}
    assert requirements["radio_rx_en"].required and requirements["radio_tx_en"].required
    header = Sx1278Header_Render(Sx1278Model_Get(builtin_catalog))
    assert "AIR_LINK_FREQUENCY_HZ 433000000UL" in header
    assert "AIR_LINK_TX_POWER_DBM 17" in header and "SX128" not in header
    assert not any("Middlewares" in source for source in manifest.build.sources)
    legacy = ReferenceProject_Create("Legacy", catalog=builtin_catalog)
    assert legacy.air_link.radio_family == "sx128x"
    assert legacy.device_instances[2].plugin != SX1278_PLUGIN


@pytest.mark.parametrize("field,value", [("frequency_hz", 470000000), ("frequency_hz", True),
    ("spreading_factor", 12), ("bandwidth_hz", 250000), ("coding_rate", "4/8"),
    ("preamble_symbols", 8), ("crc_enabled", False), ("crc_enabled", 1),
    ("header_mode", "implicit"), ("iq_mode", "inverted"), ("packet_mtu", 62),
    ("radio_family", "sx128x"), ("nrf24", {})])
def test_sx1278_rejects_unadmitted_phy(builtin_catalog, field, value):
    model = Sx1278Model_Get(builtin_catalog)
    with pytest.raises(ValueError):
        Sx1278Link_Validate(replace(model.air_link, **{field: value}))


@pytest.mark.parametrize("module,power", [("", 17), ("e32_400m30s", 17),
    ("e32_400m20s", 20), ("e32_400m20s", True), ("e32_900m20s", 17)])
def test_sx1278_rejects_implicit_or_other_modules(module, power):
    with pytest.raises(ValueError): Sx1278Module_Validate(module, power)


@pytest.fixture(scope="module")
def sx1278_host(tmp_path_factory, builtin_catalog):
    root = Path(__file__).resolve().parents[1]
    work = tmp_path_factory.mktemp("sx1278-host")
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    radio = root / "plugins/builtin/silverstar_device_telemetry_sx1278/payload/Devices/Telemetry/SX1278"
    (work / "air_link_config.h").write_text(Sx1278Header_Render(Sx1278Model_Get(builtin_catalog)), encoding="utf8")
    (work / "project_resources.h").write_text('''#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H
#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_SX1278_INSTANCE_COUNT 1U
#define PROJECT_SX1278_INSTANCE_COUNT_MAX 1U
typedef struct {
    PlatformSpiId spi; PlatformGpioId nss; PlatformGpioId reset;
    PlatformGpioId dio0; PlatformTimeId time; PlatformGpioId rx_en; PlatformGpioId tx_en;
} ProjectSx1278Resources;
SystemDeviceResult ProjectSx1278Resources_Get(uint8_t instance, ProjectSx1278Resources *resources);
#endif
''', encoding="utf8")
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC required for this driver experiment"
    includes = [work, radio/"Inc", radio/"Src", radio/"Adapter/Inc", core/"Common/Inc", core/"Interfaces/Inc",
        root/"plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
        root/"plugins/builtin/silverstar_core_ground_0_1_0/payload/Ground/Core/Inc",
        root/"plugins/builtin/silverstar_core_ground_0_1_0/payload/Ground/Protocol/Inc"]
    (work/"ground_radio_config.h").write_text('#include "platform_gpio.h"\n#define GROUND_ACTIVITY_ENABLED 0U\n#define GROUND_ACTIVITY_TX_GPIO PLATFORM_GPIO_COUNT\n#define GROUND_ACTIVITY_RX_GPIO PLATFORM_GPIO_COUNT\n#define GROUND_ACTIVITY_TX_ACTIVE_HIGH 0U\n#define GROUND_ACTIVITY_RX_ACTIVE_HIGH 0U\n#define GROUND_ACTIVITY_PULSE_MS 40U\n', encoding="utf8")
    command = [compiler, "-std=c11", "-O2", *STRICT_WARNINGS,
        *("-I"+str(p) for p in includes), str(root/"tests/fixtures/sx1278_host/host.c"),
        str(radio/"Src/sx1278_chip.c"), str(radio/"Adapter/Src/sx1278_telemetry_adapter.c"),
        str(radio.parents[2]/"Ground/Radio/Src/ground_radio_sx1278.c"),
        str(root/"plugins/builtin/silverstar_core_ground_0_1_0/payload/Ground/Radio/Src/ground_radio_activity.c"),
        "-o", str(work/"host.exe")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (work/"compile.json").write_text(json.dumps({"command": command, "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr}, indent=2), encoding="utf8")
    assert result.returncode == 0, result.stdout+result.stderr
    return work/"host.exe", work, includes, radio


@pytest.mark.parametrize("scenario", ["tx", "rx", "timeout", "absent", "readback", "boundaries",
    "gpio_fault", "resources", "wrap", "adapter", "queue_corrupt", "state_corrupt",
    "queue_expiry", "continuous_rx", "conflicting_irq", "chip_bounds", "ground_adapter", "crc_race", "deadline_during_spi",
    "stop_restart", "stop_during_config", "stop_receive", "stop_gpio_error", "ignored_standby",
    "ignored_rx_entry", "ignored_tx_entry", "reset_timing", "rx_window_clock", "queue_nonterminal_irq",
    "wanted_corrupt", "lifecycle_corrupt", "stop_during_tx_done",
    "unexpected_reset_rx", "unexpected_mode_tx", "health_time_epoch", "autonomous_tx_done",
    "negative_state_corrupt", "receipt_corrupt", "rx_length_corrupt", "tx_length_corrupt", "adapter_stop_pending",
    "adapter_stop_before_start", "stop_status_error"])
def test_sx1278_host_scenarios(sx1278_host, scenario):
    executable, work, _, _ = sx1278_host
    result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=10)
    (work/(scenario+".log")).write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == (90 if scenario.endswith("corrupt") else 0), result.stdout+result.stderr


@pytest.mark.parametrize("nth", range(1, 17))
@pytest.mark.parametrize("timeout", [0, 1])
def test_sx1278_spi_failure_at_every_rx_transaction(sx1278_host, nth, timeout):
    executable, work, _, _ = sx1278_host
    result = subprocess.run([str(executable), "spi_fault", str(nth), str(timeout)],
        capture_output=True, text=True, timeout=10)
    (work/f"spi-{nth}-{timeout}.log").write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout+result.stderr


@pytest.mark.parametrize("nth", range(1, 12))
@pytest.mark.parametrize("timeout", [0, 1])
def test_sx1278_spi_failure_at_every_tx_start_transaction(sx1278_host, nth, timeout):
    executable, work, _, _ = sx1278_host
    result = subprocess.run([str(executable), "tx_spi_fault", str(nth), str(timeout)], capture_output=True, text=True, timeout=10)
    (work/f"tx-spi-{nth}-{timeout}.log").write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout+result.stderr


@pytest.mark.parametrize("nth", range(1, 65))
def test_sx1278_spi_failure_at_every_initialization_transaction(sx1278_host, nth):
    executable, work, _, _ = sx1278_host
    result = subprocess.run([str(executable), "init_spi_fault", str(nth)], capture_output=True, text=True, timeout=10)
    (work/f"init-spi-{nth}.log").write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout+result.stderr


@pytest.mark.parametrize("nth", range(1, 20))
def test_sx1278_spi_failure_across_rx_to_tx_transition(sx1278_host, nth):
    executable, work, _, _ = sx1278_host
    result = subprocess.run([str(executable), "rx_tx_spi_fault", str(nth)], capture_output=True, text=True, timeout=10)
    (work/f"rx-tx-spi-{nth}.log").write_text(result.stdout+result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout+result.stderr


def test_sx1278_actual_gcc_analyzer_and_arm_compilation(sx1278_host):
    _, work, includes, radio = sx1278_host
    commands=[]
    for compiler, flags, prefix in [(shutil.which("gcc"), ["-fanalyzer"], "analyzer"),
        (shutil.which("arm-none-eabi-gcc"), ["-mcpu=cortex-m4", "-mthumb", "-fstack-usage"], "arm")]:
        assert compiler, "Real GCC analyzer and ARM compiler are required"
        for source in [radio/"Src/sx1278_chip.c", radio/"Src/sx1278_device.c", radio/"Adapter/Src/sx1278_telemetry_adapter.c",
                       radio.parents[2]/"Ground/Radio/Src/ground_radio_sx1278.c"]:
            command=[compiler, "-std=c11", "-O2", *STRICT_WARNINGS, *flags,
                *("-I"+str(p) for p in includes), "-c", str(source), "-o", str(work/f"{prefix}-{source.stem}.o")]
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            commands.append({"command":command,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
            (work/"analysis-arm.json").write_text(json.dumps(commands,indent=2),encoding="utf8")
            assert result.returncode==0,result.stdout+result.stderr
    arm=shutil.which("arm-none-eabi-gcc")
    for target, sources in [("flight", ["sx1278_chip", "sx1278_device", "sx1278_telemetry_adapter"]),
                            ("ground", ["sx1278_chip", "sx1278_device", "sx1278_telemetry_adapter", "ground_radio_sx1278"])]:
        # Both are IO-failing ABI fixtures, not whole-firmware/HAL/RTOS proof.
        stub=Path(__file__).parent/"fixtures/sx1278_host/arm_link.c"
        stub_text=stub.read_text(encoding="utf8")
        if target=="flight":
            stub_text=stub_text.replace('    if (GroundRadio_Init() != GROUND_RADIO_OK) { return 2; }\n    GroundRadio_Process(); GroundRadio_StatsGet(&stats);', '    (void)stats;')
        stub_copy=work/f"{target}-arm-link.c"
        stub_copy.write_text(stub_text,encoding="utf8")
        command=[arm,"-std=c11","-O2",*STRICT_WARNINGS,"-mcpu=cortex-m4","-mthumb",
            "-nostartfiles","--specs=nosys.specs","-Wl,-e,main","-Wl,-Ttext=0x08000000",
            "-Wl,-Map="+str(work/f"{target}.map"),*("-I"+str(p) for p in includes),str(stub_copy),
            *(str(work/f"arm-{name}.o") for name in sources),"-o",str(work/f"{target}.elf")]
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        commands.append({"command":command,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
        (work/"analysis-arm.json").write_text(json.dumps(commands,indent=2),encoding="utf8")
        assert result.returncode==0,result.stdout+result.stderr
