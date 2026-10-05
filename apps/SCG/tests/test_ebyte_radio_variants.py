from dataclasses import replace
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from silverstar_fccg.project.radio_variants import (
    EBYTE_VARIANTS, RADIO_PLUGIN, RadioVariant_Get, FlightRadioConfiguration_Get, FlightRadioConfiguration_Apply,
)
from silverstar_fccg.generator.ground_radio import GroundRadioAirHeader_Render
from silverstar_fccg.generator.render import AirLinkHeader_Render, _ResourceHeader_Render, _InstanceResourcesSource_Render
from silverstar_fccg.project.model import (
    DeviceInstance, HardwareResource, GroundRadioConfiguration, GroundRadioSelection_Apply, ProjectModel_Parse,
)
from silverstar_fccg.project.air_link import AirLinkIssues_Get, GroundTargetIssues_Get
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create


@pytest.mark.parametrize("module", EBYTE_VARIANTS)
def test_documented_capability_and_both_power_renderers(builtin_catalog, module):
    cap = EBYTE_VARIANTS[module]
    manifest = builtin_catalog.Component_Get(RADIO_PLUGIN)
    declared = manifest.metadata["radio_variant_capabilities"][module]
    assert declared["chip_drive_dbm"] == cap.chip_drive_dbm
    assert declared["external_frontend"] == cap.external_frontend
    assert declared["maximum_spi_clock_hz"] == 10_000_000
    assert manifest.radio.modules[module]["supported_tx_powers_dbm"] == [cap.nominal_output_dbm]
    assert cap.hardware_status == declared["hardware_status"]
    model = ReferenceProject_Create("EbytePower", catalog=builtin_catalog)
    index = next(i for i, item in enumerate(model.device_instances) if item.plugin == RADIO_PLUGIN)
    model.device_instances[index] = replace(model.device_instances[index], module_variant=module, tx_power_dbm=cap.nominal_output_dbm)
    from test_round2_targets import _GroundBoardProject_Get
    model.ground_target = replace(_GroundBoardProject_Get(builtin_catalog).ground_target,
        module_variant=module, tx_power_dbm=cap.nominal_output_dbm)
    flight = AirLinkHeader_Render(model)
    ground = GroundRadioAirHeader_Render(model.ground_target, AirLinkHeader_Render(model, target="ground"))
    for token in ("FREQUENCY_HZ", "SPREADING_FACTOR", "BANDWIDTH_HZ", "CODING_RATE_DENOMINATOR", "SX128X_PREAMBLE_ENCODED", "PACKET_MTU"):
        assert re.search(rf"#define AIR_LINK_{token} (.+)", flight)[1] == re.search(rf"#define AIR_LINK_{token} (.+)", ground)[1]
    if module != "e28_2g4m12sx":
        expected = f"#define AIR_LINK_INSTANCE_CHIP_TX_POWER_DBM(instance) {cap.chip_drive_dbm}"
        assert expected in flight and expected in ground
    assert not AirLinkIssues_Get(model, builtin_catalog)
    restored = ProjectModel_Parse(model.Dictionary_Get())
    assert restored.Dictionary_Get() == model.Dictionary_Get()
    assert restored.format_version == 16
    with pytest.raises(ValueError): RadioVariant_Get(module, cap.nominal_output_dbm - 1)


def test_original_serialization_and_resource_contract(builtin_catalog):
    model = ReferenceProject_Create("OriginalM12", catalog=builtin_catalog)
    instance = model.DeviceInstance_Get(model.air_link.flight_radio_instance)
    assert FlightRadioConfiguration_Get(model, instance) == ("e28_2g4m12sx", 12)
    assert model.Dictionary_Get()["format_version"] == 14
    entry = next(entry for entry in model.Dictionary_Get()["components"]["devices"] if entry["instance_id"] == instance.instance_id)
    assert set(entry) == {"instance_id", "plugin", "interface", "profile"}
    header = _ResourceHeader_Render(model, builtin_catalog)
    source = _InstanceResourcesSource_Render(model, builtin_catalog)
    assert ".rx_en = (PlatformGpioId)PLATFORM_GPIO_COUNT" in source
    assert ".tx_en = (PlatformGpioId)PLATFORM_GPIO_COUNT" in source
    assert "RF_FRONTEND" not in header
    assert "INSTANCE_CHIP_TX_POWER" not in AirLinkHeader_Render(model)
    assert not AirLinkIssues_Get(model, builtin_catalog)


def test_undocumented_models_and_nominal_only_power(builtin_catalog):
    assert not any("28" in key.removeprefix("e28_") for key in EBYTE_VARIANTS)
    for power in (False, 19, 12, -2, "20"):
        with pytest.raises(ValueError): RadioVariant_Get("e28_2g4m20s", power)
    with pytest.raises(ValueError): RadioVariant_Get("e28_2g4m28sx", 28)
    model = ReferenceProject_Create("UnsupportedPower", catalog=builtin_catalog)
    model.flight_tx_power_dbm = 10
    assert any(issue.code == "AIR_LINK_TX_POWER_UNSUPPORTED" for issue in AirLinkIssues_Get(model, builtin_catalog))


def test_pa_requires_bindings_and_real_spi_limit(builtin_catalog):
    model = ReferenceProject_Create("UnboundPa", catalog=builtin_catalog)
    index = next(i for i, item in enumerate(model.device_instances) if item.plugin == RADIO_PLUGIN)
    model.device_instances[index] = replace(model.device_instances[index], module_variant="e28_2g4m20sx", tx_power_dbm=20)
    result = ResourceAssignments_Resolve(model, builtin_catalog)
    assert any("radio_rx_en" in error for error in result.errors)
    assert any("radio_tx_en" in error for error in result.errors)
    requirement = builtin_catalog.Component_Get(RADIO_PLUGIN).resource_requirements[0]
    assert requirement.constraints["spi"]["maximum_clock_hz"] == 10_000_000


def test_edit_copy_and_old_format_rejection(builtin_catalog):
    model = ReferenceProject_Create("VariantEdit", catalog=builtin_catalog)
    edited = FlightRadioConfiguration_Apply(model, "telemetry0", "e28_2g4m27sx", 27)
    assert model.DeviceInstance_Get("telemetry0").module_variant == ""
    assert edited.DeviceInstance_Get("telemetry0").tx_power_dbm == 27
    descriptor = edited.Dictionary_Get()
    descriptor["format_version"] = 14
    with pytest.raises(ValueError, match="format 16"): ProjectModel_Parse(descriptor)
    edited.resource_assignments["telemetry0:radio_rx_en"] = "extra"
    reverted = FlightRadioConfiguration_Apply(edited, "telemetry0", "e28_2g4m12sx", 12)
    assert "telemetry0:radio_rx_en" not in reverted.resource_assignments


def test_pa_pin_alias_and_peripheral_conflicts():
    from silverstar_fccg.project.resources import RadioFrontendConflicts_Get
    bindings = [("radio0:radio_rx_en", {"c_id": "gpio12", "physical_pin": "GPIOB8"}, "gpio12"),
                ("radio0:radio_tx_en", {"c_id": "gpio13", "physical_pin": "PB9"}, "gpio13"),
                ("radio0:radio_bus", {"c_id": "spi", "pins": {"sck": "PB8"}}, "spi")]
    assert RadioFrontendConflicts_Get(bindings)
    assert not RadioFrontendConflicts_Get(bindings[:2])
    assert RadioFrontendConflicts_Get([bindings[0], ("radio1:radio_tx_en", {"c_id": "gpio12"}, "alias")])


@pytest.mark.parametrize("chip,raw", [(12, 0x1E), (-2, 0x10), (0, 0x12)])
def test_real_register_encoder_frontend_lifecycle_and_faults(tmp_path, chip, raw):
    gcc = shutil.which("gcc")
    assert gcc is not None, "Host GCC required for radio safety evidence"
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    radio = root / "plugins/builtin/silverstar_device_telemetry_sx1281/payload"
    original = core / "Tests/Host/Fixtures/MultiInstance/Inc/project_resources.h"
    header = original.read_text(encoding="utf8")
    (tmp_path / "project_resources.h").write_text(header, encoding="utf8")
    includes = [tmp_path, core / "Tests/Host", core / "Common/Inc", core / "Interfaces/Inc",
        root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
        radio / "Devices/Telemetry/SX1281/Inc", radio / "Devices/Telemetry/SX1281/Src",
        radio / "Middlewares/Third_Party/SX1280lib"]
    flags = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-ffunction-sections", "-fdata-sections", *("-I" + str(path) for path in includes)]
    library = radio / "Middlewares/Third_Party/SX1280lib/sx1280.c"
    # Compile the exact production encoder body, unchanged, with a recording HAL.
    # COFF does not discard unresolved references from unused library sections.
    source = library.read_text(encoding="utf8")
    start = source.index("void SX1280SetTxParams(")
    end = source.index("void SX1280SetCadParams(", start)
    encoder = tmp_path / "actual_encoder.c"
    encoder.write_text('#include "sx1280.h"\n#include "sx1280-hal.h"\n' + source[start:end], encoding="utf8")
    obj = tmp_path / "chip.o"
    commands = [flags + ["-c", str(encoder), "-o", str(obj)],
        flags + [f"-DEXPECTED_POWER_REGISTER={raw}",
        f"-DAIR_LINK_INSTANCE_CHIP_TX_POWER_DBM(instance)={chip}",
        str(root / "tests/fixtures/ebyte_frontend_host.c"), str(core / "Common/Src/silverstar_assert.c"),
        str(obj), "-Wl,--gc-sections", "-lm", "-o", str(tmp_path / "frontend.exe")],
        [str(tmp_path / "frontend.exe")]]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
