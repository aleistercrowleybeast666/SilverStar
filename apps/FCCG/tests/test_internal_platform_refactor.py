from __future__ import annotations

import hashlib
import io
import inspect
import json
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.render import (
    LogDecoderProfile_Render,
    _PlatformBinding_Render,
    _PlatformResources_Render,
)
from silverstar_fccg.generator.source_graph import (
    SourceGraphError,
    SourceGraph_Resolve,
)
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import I2cPullupEvidenceView
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.hardware.platform import (
    DetectedMcuFacts,
    PlatformCompatibilityErrors_Get,
    PlatformMatchError,
    PlatformMatch_Resolve,
)
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import (
    PlatformResourceBinding,
    PluginManifestError,
    PluginManifest_Load,
)
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.generation_state import (
    ProjectGenerationFingerprint_Get,
)
from silverstar_fccg.project.model import (
    DeviceInstance,
    HardwareConfiguration,
    PROJECT_FORMAT_VERSION,
    ProjectModel_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.pages.components import BoardHardwarePage
from silverstar_fccg.ui.widgets import StandardCheckBox


def _Device_Write(
    installed_root: Path,
    component_id: str,
    kind: str,
    constraints: dict,
    platform_capabilities: list[str],
) -> None:
    package = installed_root / component_id / "1.0.0"
    (package / "payload" / "Fixture").mkdir(parents=True)
    manifest = {
        "schema_version": 0,
        "id": component_id,
        "name": component_id.rsplit(".", 1)[-1],
        "type": "device",
        "class": "fixture_sensor",
        "instance_policy": {
            "plugin_max": 4,
            "class_max": 8,
            "same_plugin_multiple": True,
            "multi_instance_ready": True,
        },
        "physical_device": {
            "vendor": "Fixture",
            "model": component_id,
            "chipset": "fixture",
            "driver": "fixture",
        },
        "version": "1.0.0",
        "description": "Test-only declarative platform resource consumer.",
        "requires": {
            "components": [
                {"id": "silverstar.core.0_1_0", "optional": False}
            ],
            "resources": [
                {
                    "name": "bus",
                    "kind": kind,
                    "required": True,
                    "mode": "shared",
                    "platform_capabilities": platform_capabilities,
                    "constraints": constraints,
                    "display_names": {"en_US": "Fixture bus"},
                }
            ],
            "capabilities": [],
        },
        "resources": {"provides": [], "roles": [], "conflicts": []},
        "provides": [],
        "build": {
            "sources": [],
            "asm_sources": [],
            "include_dirs": [],
            "defines": [],
        },
        "payload": {"roots": ["Fixture"]},
        "metadata": {
            "declarative": True,
            "device_category": "sensor.temperature",
        },
    }
    (package / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _Catalog_Create(workspace_root: Path, installed_root: Path) -> PluginCatalog:
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", installed_root)
    catalog.Scan()
    return catalog


def _Inventory_Create() -> object:
    return CubeMxInventory_Parse(
        "\n".join(
            (
                "Mcu.CPN=STM32F407VET6",
                "Mcu.Name=STM32F407V(E-G)Tx",
                "Mcu.Family=STM32F4",
                "Mcu.Package=LQFP100",
                "Mcu.Core=ARM Cortex-M4",
                "MxCube.Version=6.15.0",
                "ProjectManager.FirmwarePackage=STM32Cube FW_F4 V1.28.3",
                "Mcu.IP0=I2C1",
                "Mcu.IP1=CAN1",
                "Mcu.IP2=TIM3",
                "PB6.Signal=I2C1_SCL",
                "PB6.GPIO_PuPd=GPIO_PULLUP",
                "PB6.GPIO_OutputType=GPIO_MODE_AF_OD",
                "PB7.Signal=I2C1_SDA",
                "PB7.GPIO_PuPd=GPIO_PULLUP",
                "PB7.GPIO_OutputType=GPIO_MODE_AF_OD",
                "PB8.Signal=CAN1_RX",
                "PB9.Signal=CAN1_TX",
                "PA6.Signal=TIM3_CH1",
                "PA7.Signal=TIM3_CH2",
                "SH.S_TIM3_CH1.0=TIM3_CH1,PWM Generation1 CH1",
                "SH.S_TIM3_CH2.0=TIM3_CH2,PWM Generation2 CH2",
                "I2C1.ClockSpeed=400000",
                "I2C1.AddressingMode=I2C_ADDRESSINGMODE_7BIT",
                "CAN1.Prescaler=6",
                "CAN1.TimeSeg1=CAN_BS1_11TQ",
                "CAN1.TimeSeg2=CAN_BS2_2TQ",
                "CAN1.Mode=CAN_MODE_NORMAL",
                "TIM3.Prescaler=83",
                "TIM3.Period=19999",
                "RCC.APB1Freq_Value=42000000",
            )
        ),
        generated_sources=(
            """
TIM_HandleTypeDef htim3;
void MX_TIM3_Init(void)
{
    TIM_OC_InitTypeDef sConfigOC = {0};
    htim3.Instance = TIM3;
    htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1);
    sConfigOC.OCMode = TIM_OCMODE_PWM2;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_LOW;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_2);
}
""",
        ),
    )


def _CustomModel_Create(catalog: PluginCatalog, devices: list[DeviceInstance]):
    inventory = _Inventory_Create()
    model = ReferenceProject_Create("OptionalPlatform", catalog=catalog)
    model.board = ""
    model.device_instances = devices
    model.resource_assignments = {}
    model.hardware = HardwareConfiguration(
        mode="custom",
        source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx",
        snapshot_id="a" * 64,
        source_digest="a" * 64,
        mcu="STM32F407VET6",
        platform_component="silverstar.mcu.stm32f407vet6",
        platform_version=catalog.Component_Get(
            "silverstar.mcu.stm32f407vet6"
        ).version,
        platform_manifest_sha256=catalog.Component_Get(
            "silverstar.mcu.stm32f407vet6"
        ).ManifestSha256_Get(),
        cubemx_version=inventory.cubemx_version,
        firmware_package=inventory.firmware_package,
        hal_cmsis_source_policy="plugin_payload_authoritative",
        capabilities=tuple(
            sorted(
                {
                    f"peripheral.{resource.kind}"
                    for resource in inventory.HardwareResources_Get()
                }
            )
        ),
        inventory=inventory.Dictionary_Get(),
        resources=inventory.HardwareResources_Get(),
        build_sources=(
            "HardwareGenerated/STM32CubeMX/Core/Src/main.c",
        ),
        include_dirs=(
            "HardwareGenerated/STM32CubeMX/Core/Inc",
        ),
    )
    return model


def test_default_reference_does_not_select_optional_platform_backends(
    builtin_catalog: PluginCatalog,
) -> None:
    graph = SourceGraph_Resolve(
        ReferenceProject_Create("DefaultNoOptional", catalog=builtin_catalog),
        builtin_catalog,
    )
    optional_tokens = (
        "platform_i2c_stm32f4.c",
        "platform_can_stm32f4.c",
        "platform_pwm_stm32f4.c",
        "stm32f4xx_hal_i2c.c",
        "stm32f4xx_hal_i2c_ex.c",
        "stm32f4xx_hal_can.c",
    )
    assert not any(
        source.endswith(optional_tokens) for source in graph.sources
    )
    assert all(
        any(excluded.endswith(token) for excluded in graph.exclude_sources)
        for token in optional_tokens
    )


def test_cubemx_modules_keep_hal_providers_without_device_backends(
    builtin_catalog: PluginCatalog,
) -> None:
    model = _CustomModel_Create(builtin_catalog, [])
    graph = SourceGraph_Resolve(model, builtin_catalog)
    for provider_source in (
        "stm32f4xx_hal_i2c.c",
        "stm32f4xx_hal_i2c_ex.c",
        "stm32f4xx_hal_can.c",
        "stm32f4xx_hal_tim.c",
        "stm32f4xx_hal_tim_ex.c",
    ):
        assert any(
            source.endswith(provider_source) for source in graph.sources
        )
    for backend_source in (
        "platform_i2c_stm32f4.c",
        "platform_can_stm32f4.c",
        "platform_pwm_stm32f4.c",
    ):
        assert not any(
            source.endswith(backend_source) for source in graph.sources
        )
    assert any(
        source.endswith("stm32f4xx_hal_mmc.c")
        for source in graph.exclude_sources
    )


def test_unknown_cubemx_module_has_no_implicit_compile_all_fallback(
    builtin_catalog: PluginCatalog,
) -> None:
    model = _CustomModel_Create(builtin_catalog, [])
    model.hardware = replace(
        model.hardware,
        inventory={
            **model.hardware.inventory,
            "peripherals": [
                *model.hardware.inventory["peripherals"],
                "CRYP",
            ],
        },
    )
    with pytest.raises(SourceGraphError, match="no declarative Platform provider"):
        SourceGraph_Resolve(model, builtin_catalog)


def test_hardware_inventory_json_has_case_insensitive_unique_keys(
    builtin_catalog: PluginCatalog,
) -> None:
    inventory = ReferenceProject_Create(
        "PowerShellCompatibleInventory", catalog=builtin_catalog
    ).hardware.inventory

    def keys_validate(value: object) -> None:
        if isinstance(value, dict):
            folded = [str(key).casefold() for key in value]
            assert len(folded) == len(set(folded))
            for child in value.values():
                keys_validate(child)
        elif isinstance(value, list):
            for child in value:
                keys_validate(child)

    keys_validate(inventory)
    spi_settings = inventory["spis"][0]["settings"]
    assert spi_settings["mode"] == "master"
    assert spi_settings["cubemx_Mode"] == "SPI_MODE_MASTER"


def test_i2c_inventory_assignment_glue_and_conditional_sources(
    tmp_path: Path, workspace_root: Path
) -> None:
    installed = tmp_path / "installed"
    _Device_Write(
        installed,
        "fixture.device.i2c_temperature",
        "i2c",
        {
            "i2c": {
                "maximum_bus_frequency_hz": 400000,
                "address_mode": "7bit",
                "address_7bit": 0x48,
                "required_pullup": True,
            }
        },
        ["i2c.master_blocking"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [DeviceInstance("temperature0", "fixture.device.i2c_temperature")],
    )
    model.resource_assignments["temperature0:bus"] = "I2C1"
    assert ResourceAssignments_Resolve(model, catalog).valid
    graph = SourceGraph_Resolve(model, catalog)
    assert "Platform/STM32F4/Src/platform_i2c_stm32f4.c" in graph.sources
    assert any(source.endswith("stm32f4xx_hal_i2c.c") for source in graph.sources)
    assert any(source.endswith("stm32f4xx_hal_i2c_ex.c") for source in graph.sources)
    # The CubeMX fixture enables CAN1, so its generated init source must retain
    # the HAL provider even though no CAN Device may consume the reserved backend.
    assert any(source.endswith("stm32f4xx_hal_can.c") for source in graph.sources)
    assert "Platform/STM32F4/Src/platform_can_stm32f4.c" not in graph.sources
    glue = _PlatformResources_Render(model, catalog)
    assert '#include "i2c.h"' in glue
    assert "&hi2c1" in glue


def test_i2c_address_conflict_and_repeated_start_capability_fail_early(
    tmp_path: Path, workspace_root: Path
) -> None:
    installed = tmp_path / "installed"
    _Device_Write(
        installed,
        "fixture.device.i2c_shared",
        "i2c",
        {"i2c": {"address_7bit": 0x68, "address_mode": "7bit"}},
        ["i2c.master_blocking"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [
            DeviceInstance("sensor0", "fixture.device.i2c_shared"),
            DeviceInstance("sensor1", "fixture.device.i2c_shared"),
        ],
    )
    model.resource_assignments.update(
        {"sensor0:bus": "I2C1", "sensor1:bus": "I2C1"}
    )
    result = ResourceAssignments_Resolve(model, catalog)
    assert any("I2C address conflict" in error for error in result.errors)

    repeated_root = tmp_path / "repeated"
    _Device_Write(
        repeated_root,
        "fixture.device.i2c_repeated",
        "i2c",
        {
            "i2c": {
                "address_7bit": 0x69,
                "address_mode": "7bit",
                "requires_repeated_start": True,
            }
        },
        ["i2c.master_blocking"],
    )
    repeated_catalog = _Catalog_Create(workspace_root, repeated_root)
    repeated_model = _CustomModel_Create(
        repeated_catalog,
        [DeviceInstance("sensor0", "fixture.device.i2c_repeated")],
    )
    repeated_model.resource_assignments["sensor0:bus"] = "I2C1"
    repeated = ResourceAssignments_Resolve(repeated_model, repeated_catalog)
    assert any("i2c.repeated_start" in error for error in repeated.errors)


def test_i2c_shared_address_requires_one_explicit_composite_device(
    tmp_path: Path, workspace_root: Path
) -> None:
    installed = tmp_path / "installed"
    component_id = "fixture.device.i2c_composite"
    _Device_Write(
        installed,
        component_id,
        "i2c",
        {"i2c": {"address_7bit": 0x68, "address_mode": "7bit"}},
        ["i2c.master_blocking"],
    )
    manifest_path = installed / component_id / "1.0.0" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    second = json.loads(json.dumps(data["requires"]["resources"][0]))
    second["name"] = "auxiliary"
    data["requires"]["resources"].append(second)
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog, [DeviceInstance("sensor0", component_id)]
    )
    model.resource_assignments.update(
        {"sensor0:bus": "I2C1", "sensor0:auxiliary": "I2C1"}
    )
    conflict = ResourceAssignments_Resolve(model, catalog)
    assert any("matching composite_device" in error for error in conflict.errors)

    for requirement in data["requires"]["resources"]:
        requirement["constraints"]["i2c"]["composite_device"] = "imu.package"
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog, [DeviceInstance("sensor0", component_id)]
    )
    model.resource_assignments.update(
        {"sensor0:bus": "I2C1", "sensor0:auxiliary": "I2C1"}
    )
    assert ResourceAssignments_Resolve(model, catalog).valid


def test_typed_optional_backend_requires_declared_platform_capability(
    tmp_path: Path
) -> None:
    installed = tmp_path / "installed"
    component_id = "fixture.device.i2c_without_backend_contract"
    _Device_Write(
        installed,
        component_id,
        "i2c",
        {"i2c": {"address_7bit": 0x69}},
        [],
    )
    manifest_path = installed / component_id / "1.0.0" / "plugin.json"
    with pytest.raises(PluginManifestError, match="platform_capabilities"):
        PluginManifest_Load(manifest_path, source="installed")


def test_protocol_extensions_require_namespaced_object_values(
    tmp_path: Path, workspace_root: Path
) -> None:
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_protocol_telemetry_air_m0"
    )
    package = tmp_path / "protocol"
    shutil.copytree(source, package)
    manifest_path = package / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["protocol"]["extensions"] = {"example.vendor": ["unsafe-shape"]}
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(PluginManifestError, match="object values"):
        PluginManifest_Load(manifest_path, source="installed")


def test_classic_can_single_owner_and_fdcan_do_not_cross_match(
    tmp_path: Path, workspace_root: Path
) -> None:
    installed = tmp_path / "installed"
    _Device_Write(
        installed,
        "fixture.device.classic_can",
        "can_classic",
        {
            "can": {
                "allowed_nominal_bitrates": [500000],
                "frame_format": "classic",
                "mode": "normal",
            }
        },
        ["can.classic_bxcan"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [DeviceInstance("can0", "fixture.device.classic_can")],
    )
    model.resource_assignments["can0:bus"] = "CAN1"
    reserved = ResourceAssignments_Resolve(model, catalog)
    assert any("backend reserved" in error for error in reserved.errors)

    model.device_instances.append(
        DeviceInstance("can1", "fixture.device.classic_can")
    )
    model.resource_assignments["can1:bus"] = "CAN1"
    conflict = ResourceAssignments_Resolve(model, catalog)
    assert any("backend reserved" in error for error in conflict.errors)

    fdcan = CubeMxInventory_Parse(
        "\n".join(
            (
                "Mcu.CPN=STM32H743ZIT6",
                "Mcu.Family=STM32H7",
                "Mcu.IP0=FDCAN1",
                "PB8.Signal=FDCAN1_RX",
                "PB9.Signal=FDCAN1_TX",
            )
        )
    )
    assert fdcan.cans[0].kind == "can_fd"
    assert all(resource.kind != "can_classic" for resource in fdcan.HardwareResources_Get())


def test_pwm_channel_identity_shared_timer_and_frequency_conflict(
    tmp_path: Path, workspace_root: Path
) -> None:
    installed = tmp_path / "installed"
    _Device_Write(
        installed,
        "fixture.device.pwm_50hz",
        "pwm",
        {
            "pwm": {
                "frequency_hz": 50,
                "minimum_resolution_bits": 12,
                "safe_state": "inactive",
            }
        },
        ["pwm.output_fixed_frequency"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [
            DeviceInstance("pwm0", "fixture.device.pwm_50hz"),
            DeviceInstance("pwm1", "fixture.device.pwm_50hz"),
        ],
    )
    model.resource_assignments.update(
        {"pwm0:bus": "TIM3_CH1", "pwm1:bus": "TIM3_CH2"}
    )
    assert ResourceAssignments_Resolve(model, catalog).valid
    glue = _PlatformResources_Render(model, catalog)
    assert "&htim3, TIM_CHANNEL_1" in glue
    assert "&htim3, TIM_CHANNEL_2" in glue
    assert "Platform/STM32F4/Src/platform_pwm_stm32f4.c" in SourceGraph_Resolve(
        model, catalog
    ).sources

    _Device_Write(
        installed,
        "fixture.device.pwm_100hz",
        "pwm",
        {"pwm": {"frequency_hz": 100}},
        ["pwm.output_fixed_frequency"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model.device_instances[1] = DeviceInstance(
        "pwm1", "fixture.device.pwm_100hz"
    )
    conflict = ResourceAssignments_Resolve(model, catalog)
    assert any("shared-timer frequency conflict" in error for error in conflict.errors)


def test_platform_matching_reports_zero_and_tied_candidates(
    builtin_catalog: PluginCatalog,
) -> None:
    with pytest.raises(PlatformMatchError, match="no compatible"):
        PlatformMatch_Resolve(
            DetectedMcuFacts(
                vendor="STM32",
                part="STM32H743ZIT6",
                family="STM32H7",
                package="LQFP144",
                core="ARM Cortex-M7",
                provider="stm32_cubemx",
            ),
            builtin_catalog,
        )
    official = builtin_catalog.Component_Get("silverstar.mcu.stm32f407vet6")
    assert official.platform is not None

    class MatchCatalog:
        def __init__(self, manifests):
            self.manifests = manifests

        def Type_Get(self, component_type: str):
            return self.manifests if component_type == "mcu" else ()

    duplicate = replace(
        official,
        component_id="fixture.mcu.stm32f407vet6_duplicate",
        name="Duplicate F407",
    )
    facts = DetectedMcuFacts(
        vendor="STM32",
        part="STM32F407VET6",
        family="STM32F4",
        package="LQFP100",
        core="ARM Cortex-M4",
        provider="stm32_cubemx",
    )
    with pytest.raises(PlatformMatchError, match="ambiguous"):
        PlatformMatch_Resolve(facts, MatchCatalog((official, duplicate)))

    family_rule = replace(
        official.platform.match_rules[0],
        exact_part="",
        priority=9999,
        specificity=9999,
    )
    family = replace(
        official,
        component_id="fixture.mcu.stm32f4_family",
        name="Generic F4",
        platform=replace(official.platform, match_rules=(family_rule,)),
    )
    matched = PlatformMatch_Resolve(facts, MatchCatalog((family, official)))
    assert matched.selected.component_id == official.component_id


def test_renderer_uses_virtual_non_f4_platform_binding_without_fixed_symbols() -> None:
    binding = PlatformResourceBinding(
        kind="uart",
        collection="uarts",
        include_header="fixture_h7_uart.h",
        entry_kind="handle",
        id_type="FixtureH7UartId",
        count_symbol="FIXTURE_H7_UART_COUNT",
        table_symbol="s_fixture_h7_uart_handles",
        getter="FixtureH7Resource_UartHandleGet",
    )
    rendered = _PlatformBinding_Render(
        binding,
        [{"c_id": "FIXTURE_H7_UART_4", "handle": "huart4"}],
    )
    assert "FixtureH7Resource_UartHandleGet" in rendered
    assert "FixtureH7UartId" in rendered
    assert "&huart4" in rendered
    assert "Stm32f4" not in rendered
    assert "stm32f4" not in inspect.getsource(_PlatformResources_Render).casefold()


def test_cubemx_import_keeps_vendor_hal_out_of_source_graph(
    tmp_path: Path, workspace_root: Path
) -> None:
    fixture = tmp_path / "cubemx_optional_backends"
    shutil.copytree(workspace_root / "tests" / "fixtures" / "cubemx_minimal", fixture)
    ioc = fixture / "MockFlightController.ioc"
    ioc.write_text(
        ioc.read_text(encoding="utf-8")
        + "\n".join(
            (
                "",
                "Mcu.IP8=I2C1",
                "Mcu.IP9=CAN1",
                "Mcu.IP10=TIM3",
                "PB6.Signal=I2C1_SCL",
                "PB7.Signal=I2C1_SDA",
                "PB8.Signal=CAN1_RX",
                "PB9.Signal=CAN1_TX",
                "PC6.Signal=TIM3_CH1",
                "SH.S_TIM3_CH1.0=TIM3_CH1,PWM Generation1 CH1",
                "I2C1.ClockSpeed=400000",
                "CAN1.Mode=CAN_MODE_NORMAL",
                "TIM3.Prescaler=83",
                "TIM3.Period=19999",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    hal_source = fixture / "Drivers" / "STM32F4xx_HAL_Driver" / "Src"
    hal_source.mkdir(parents=True)
    for name in (
        "stm32f4xx_hal_i2c.c",
        "stm32f4xx_hal_i2c_ex.c",
        "stm32f4xx_hal_can.c",
        "stm32f4xx_hal_tim.c",
    ):
        (hal_source / name).write_text("/* CubeMX fixture. */\n", encoding="utf-8")
    (fixture / "Core" / "Src" / "tim.c").write_text(
        """
TIM_HandleTypeDef htim3;
void MX_TIM3_Init(void)
{
    TIM_OC_InitTypeDef sConfigOC = {0};
    htim3.Instance = TIM3;
    htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1);
}
""",
        encoding="utf-8",
    )

    imported = CubeMxImporter(WorkspacePolicy(tmp_path)).Project_Import(fixture)
    assert {item.kind for item in imported.inventory.i2cs} == {"i2c"}
    assert {item.kind for item in imported.inventory.cans} == {"can_classic"}
    assert imported.inventory.pwms[0].instance == "TIM3_CH1"
    assert not any(
        "/Drivers/" in source for source in imported.hardware.build_sources
    )
    assert imported.hardware.include_dirs == (
        "HardwareGenerated/STM32CubeMX/Core/Inc",
    )


def test_platform_lock_is_saved_and_legacy_missing_lock_reconciles(
    builtin_catalog: PluginCatalog,
) -> None:
    current = ReferenceProject_Create("PlatformLock", catalog=builtin_catalog)
    platform = builtin_catalog.Component_Get(current.mcu)
    assert current.hardware.platform_component == current.mcu
    assert current.hardware.platform_version == platform.version
    assert current.hardware.platform_manifest_sha256 == platform.ManifestSha256_Get()

    legacy = replace(
        current.hardware,
        platform_component="",
        platform_version="",
        platform_manifest_sha256="",
    )
    current.hardware = legacy
    validation = Project_Validate(current, builtin_catalog)
    assert validation.valid
    assert any(issue.code == "platform_lock" for issue in validation.issues)
    reconciled = ProjectConfiguration_Reconcile(current, builtin_catalog).model
    assert reconciled.hardware.platform_component == reconciled.mcu
    assert reconciled.hardware.platform_manifest_sha256 == (
        builtin_catalog.Component_Get(reconciled.mcu).ManifestSha256_Get()
    )


def test_protocol_split_preserves_reference_source_hashes(
    workspace_root: Path,
) -> None:
    provenance = json.loads(
        (workspace_root / "plugins" / "builtin" / "reference_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {
        "Protocol/Src/air_protocol.c": (
            "silverstar_protocol_telemetry_air_m0/payload/Protocol/Src/air_protocol.c"
        ),
        "System/Src/system_console.c": (
            "silverstar_core_0_1_0/payload/System/Src/system_console.c"
        ),
        "Protocol/SSLOG/Src/sslog_protocol.c": (
            "silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Src/sslog_protocol.c"
        ),
        "Protocol/SSLOG/Src/sslog_records.c": (
            "silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Src/sslog_records.c"
        ),
    }
    for source, target in targets.items():
        actual = hashlib.sha256(
            (workspace_root / "plugins" / "builtin" / target).read_bytes()
        ).hexdigest()
        assert actual == provenance.get("fccg_protocol_source_sha256", {}).get(
            source, provenance["protocol_source_sha256"][source]
        )


def test_decoder_profile_records_hardware_resources_and_three_protocol_locks(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("DecoderHardware", catalog=builtin_catalog)
    package = LogDecoderProfile_Render(model, builtin_catalog).content
    manifest = LogDecoderPackage_Verify(package)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        semantics = json.loads(archive.read("project_semantics.json"))
    assert set(manifest["protocols"]) == {"telemetry", "maintenance", "logging"}
    assert semantics["protocols"] == manifest["protocols"]
    assert semantics["hardware"]["matched_mcu_platform"] == model.mcu
    assert semantics["hardware"]["detected_mcu"] == "STM32F407VET6"
    assert semantics["algorithms"]
    assert any(
        assignment["requirement"] == "imu0:data"
        and assignment["logical_resource"] == "PLATFORM_UART_1"
        for assignment in semantics["resource_assignments"]
    )


def _I2cPullupModel_Create(
    tmp_path: Path, workspace_root: Path
) -> tuple[PluginCatalog, object]:
    installed = tmp_path / "installed_pullup"
    component_id = "fixture.device.i2c_pullup_required"
    _Device_Write(
        installed,
        component_id,
        "i2c",
        {
            "i2c": {
                "maximum_bus_frequency_hz": 400000,
                "address_mode": "7bit",
                "address_7bit": 0x48,
                "required_pullup": True,
            }
        },
        ["i2c.master_blocking"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [DeviceInstance("temperature0", component_id)],
    )
    resources = []
    for resource in model.hardware.resources:
        if resource.resource_id != "I2C1":
            resources.append(resource)
            continue
        pin_electrical = {
            role: {**electrical, "pull": "none"}
            for role, electrical in resource.metadata["pin_electrical"].items()
        }
        resources.append(
            replace(
                resource,
                metadata={
                    **resource.metadata,
                    "pin_electrical": pin_electrical,
                },
            )
        )
    model.hardware = replace(model.hardware, resources=tuple(resources))
    model.resource_assignments["temperature0:bus"] = "I2C1"
    return catalog, model


def test_custom_i2c_external_pullup_evidence_is_snapshot_bound_and_not_generated(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    catalog, model = _I2cPullupModel_Create(tmp_path, workspace_root)
    missing = ResourceAssignments_Resolve(model, catalog)
    assert any(
        "snapshot-bound custom external pull-up confirmation" in error
        and "SCL=PB6" in error
        and "SDA=PB7" in error
        for error in missing.errors
    )

    service = FccgService(workspace_root)
    service.catalog = catalog
    evidence = service.I2cPullupEvidenceViews_Get(model)
    assert len(evidence) == 1
    assert evidence[0].resource_id == "I2C1"
    assert evidence[0].physical_resource == "I2C1"
    assert not evidence[0].confirmed

    generation_fingerprint = ProjectGenerationFingerprint_Get(model)
    model.hardware = replace(
        model.hardware,
        i2c_external_pullup_confirmations={
            "I2C1": {
                "source_digest": model.hardware.source_digest,
                "snapshot_id": model.hardware.snapshot_id,
            }
        },
    )
    assert ProjectGenerationFingerprint_Get(model) == generation_fingerprint
    assert ResourceAssignments_Resolve(model, catalog).valid
    assert service.I2cPullupEvidenceViews_Get(model)[0].confirmed

    stale = replace(model.hardware, source_digest="b" * 64)
    model.hardware = stale
    stale_result = ResourceAssignments_Resolve(model, catalog)
    assert any("snapshot-bound" in error for error in stale_result.errors)
    assert not service.I2cPullupEvidenceViews_Get(model)[0].confirmed


def test_i2c_pullup_gui_is_visible_only_when_confirmation_is_required(
    qapp,
) -> None:
    page = BoardHardwarePage(Translator("zh_CN"))
    evidence = I2cPullupEvidenceView(
        resource_id="I2C1",
        physical_resource="I2C1",
        pins_text="SCL=PB6, SDA=PB7",
        confirmed=False,
    )
    page.I2cPullupEvidence_Set((evidence,))
    assert not page.i2c_pullup_group.isHidden()
    checks = page.i2c_pullup_checks_widget.findChildren(StandardCheckBox)
    assert len(checks) == 1
    assert "I2C1" in checks[0].text()
    assert "SCL=PB6" in checks[0].text()
    page.I2cPullupEvidence_Set(())
    assert page.i2c_pullup_group.isHidden()


def test_project_v8_migrates_compatibility_facts_and_pullup_evidence(
    builtin_catalog: PluginCatalog,
) -> None:
    data = ReferenceProject_Create(
        "CompatibilityMigration", catalog=builtin_catalog
    ).Dictionary_Get()
    data["format_version"] = 8
    for key in (
        "cubemx_version",
        "firmware_package",
        "hal_cmsis_source_policy",
        "i2c_external_pullup_confirmations",
    ):
        data["hardware"].pop(key)
    migrated = ProjectModel_Parse(data)
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.hardware.cubemx_version == "6.15.0"
    assert migrated.hardware.firmware_package == "STM32Cube FW_F4 V1.28.3"
    assert migrated.hardware.hal_cmsis_source_policy == ""
    assert migrated.hardware.i2c_external_pullup_confirmations == {}


def test_platform_compatibility_is_exact_and_reported_in_hardware_gui(
    qapp,
    workspace_root: Path,
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("Compatibility", catalog=builtin_catalog)
    platform = builtin_catalog.Component_Get(model.mcu)
    assert PlatformCompatibilityErrors_Get(
        platform,
        cubemx_version="6.15.0",
        firmware_package="STM32Cube FW_F4 V1.28.3",
        source_policy="plugin_payload_authoritative",
    ) == ()
    mismatch = PlatformCompatibilityErrors_Get(
        platform,
        cubemx_version="6.14.0",
        firmware_package="STM32Cube FW_F4 V1.28.2",
        source_policy="imported_tree_authoritative",
    )
    assert len(mismatch) == 3
    model.hardware = replace(model.hardware, cubemx_version="6.14.0")
    validation = Project_Validate(model, builtin_catalog)
    assert any(issue.code == "platform_compatibility" for issue in validation.issues)

    service = FccgService(workspace_root)
    current = ReferenceProject_Create("CompatibilityGui", catalog=service.catalog)
    view = service.PlatformMatchView_Get(current)
    assert view.cubemx_version == "6.15.0"
    assert view.firmware_package == "STM32Cube FW_F4 V1.28.3"
    assert view.source_policy == "plugin_payload_authoritative"
    page = BoardHardwarePage(Translator("zh_CN"))
    page.Platform_Set(view)
    assert page.platform_values["cubemx"].text() == "6.15.0"
    assert "V1.28.3" in page.platform_values["firmware_package"].text()
    assert page.platform_values["source_policy"].text() == (
        "plugin_payload_authoritative"
    )


@pytest.mark.parametrize(
    ("shared_declaration", "counter_mode", "extra_ioc", "expected_issue"),
    (
        ("TIM3_CH1,Input Capture direct mode", "TIM_COUNTERMODE_UP", "", "not a supported"),
        ("TIM3_CH1,Output Compare1 CH1", "TIM_COUNTERMODE_UP", "", "not a supported"),
        ("TIM3_CH1,PWM Generation1 CH1", "TIM_COUNTERMODE_UP", "TIM3.OnePulseMode=TIM_OPMODE_SINGLE", "advanced/combined"),
        ("TIM3_CH1N,PWM Generation1 CH1N", "TIM_COUNTERMODE_UP", "", "complementary"),
        ("TIM3_CH1,PWM Generation1 CH1", "TIM_COUNTERMODE_CENTERALIGNED1", "", "edge-aligned"),
    ),
)
def test_pwm_inventory_rejects_nonportable_timer_modes(
    shared_declaration: str,
    counter_mode: str,
    extra_ioc: str,
    expected_issue: str,
) -> None:
    channel = "TIM3_CH1N" if shared_declaration.startswith("TIM3_CH1N") else "TIM3_CH1"
    ioc_lines = (
        "Mcu.CPN=STM32F407VET6",
        "Mcu.IP0=TIM3",
        f"PA6.Signal={channel}",
        f"SH.S_TIM3_CH1.0={shared_declaration}",
        "TIM3.Prescaler=83",
        "TIM3.Period=19999",
        "RCC.APB1Freq_Value=42000000",
    ) + ((extra_ioc,) if extra_ioc else ())
    source = f"""
TIM_HandleTypeDef htim3;
void MX_TIM3_Init(void)
{{
    TIM_OC_InitTypeDef sConfigOC = {{0}};
    htim3.Instance = TIM3;
    htim3.Init.CounterMode = {counter_mode};
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1);
}}
"""
    inventory = CubeMxInventory_Parse(
        "\n".join(ioc_lines), generated_sources=(source,)
    )
    assert inventory.pwms == ()
    assert any(expected_issue in issue for issue in inventory.issues)


def test_pwm_inventory_requires_both_cubemx_and_generated_code_evidence() -> None:
    base = "\n".join(
        (
            "Mcu.CPN=STM32F407VET6",
            "Mcu.IP0=TIM3",
            "PA6.Signal=TIM3_CH1",
            "TIM3.Prescaler=83",
            "TIM3.Period=19999",
        )
    )
    generated = """
TIM_HandleTypeDef htim3;
void MX_TIM3_Init(void)
{
    TIM_OC_InitTypeDef sConfigOC = {0};
    htim3.Instance = TIM3;
    htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1);
}
"""
    pin_only = CubeMxInventory_Parse(base, generated_sources=(generated,))
    assert pin_only.pwms == ()
    declaration_only = CubeMxInventory_Parse(
        base + "\nSH.S_TIM3_CH1.0=TIM3_CH1,PWM Generation1 CH1"
    )
    assert declaration_only.pwms == ()
    complete = CubeMxInventory_Parse(
        base + "\nSH.S_TIM3_CH1.0=TIM3_CH1,PWM Generation1 CH1",
        generated_sources=(generated,),
    )
    assert complete.pwms[0].settings["pwm_mode"] == "pwm1"
    assert complete.pwms[0].settings["period_counts"] == 20000
    assert complete.pwms[0].settings["safe_inactive_behavior"] == (
        "forced_inactive_then_stop"
    )


def test_pwm_requirement_rejects_logical_polarity_field(
    tmp_path: Path,
) -> None:
    installed = tmp_path / "pwm_polarity"
    component_id = "fixture.device.pwm_polarity"
    _Device_Write(
        installed,
        component_id,
        "pwm",
        {"pwm": {"frequency_hz": 50, "polarity": "active_high"}},
        ["pwm.output_fixed_frequency"],
    )
    with pytest.raises(PluginManifestError, match="unknown fields"):
        PluginManifest_Load(
            installed / component_id / "1.0.0" / "plugin.json",
            source="installed",
        )


def test_i2c_pullup_evidence_accepts_board_metadata_but_never_push_pull(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    catalog, model = _I2cPullupModel_Create(tmp_path, workspace_root)
    resources = []
    for resource in model.hardware.resources:
        if resource.resource_id == "I2C1":
            resource = replace(
                resource,
                metadata={
                    **resource.metadata,
                    "external_pullup_verified": True,
                },
            )
        resources.append(resource)
    model.hardware = replace(model.hardware, resources=tuple(resources))
    assert ResourceAssignments_Resolve(model, catalog).valid

    push_pull_resources = []
    for resource in model.hardware.resources:
        if resource.resource_id == "I2C1":
            resource = replace(
                resource,
                metadata={
                    **resource.metadata,
                    "pin_electrical": {
                        role: {**electrical, "output_type": "push_pull"}
                        for role, electrical in resource.metadata[
                            "pin_electrical"
                        ].items()
                    },
                },
            )
        push_pull_resources.append(resource)
    model.hardware = replace(
        model.hardware,
        resources=tuple(push_pull_resources),
        i2c_external_pullup_confirmations={
            "I2C1": {
                "source_digest": model.hardware.source_digest,
                "snapshot_id": model.hardware.snapshot_id,
            }
        },
    )
    invalid = ResourceAssignments_Resolve(model, catalog)
    assert any("SCL/SDA must both be open-drain" in error for error in invalid.errors)


def test_i2c_public_abi_has_no_hal_constants_or_generic_write_read(
    workspace_root: Path,
) -> None:
    overlay = workspace_root / "tools" / "reference_overlays" / "platform"
    builtin = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_platform_api"
        / "payload"
        / "Platform"
    )
    public_header = (overlay / "platform_i2c.h").read_text(encoding="utf-8")
    assert "PlatformI2cMemoryAddressSize" in public_header
    assert "PLATFORM_I2C_MEMORY_ADDRESS_8_BIT" in public_header
    assert "PLATFORM_I2C_MEMORY_ADDRESS_16_BIT" in public_header
    assert "I2C_MEMADD_SIZE" not in public_header
    assert "PlatformI2c_WriteRead" not in public_header
    assert public_header == (
        builtin / "Inc" / "platform_i2c.h"
    ).read_text(encoding="utf-8")
    for manifest in (workspace_root / "plugins" / "builtin").glob(
        "silverstar_device_*/plugin.json"
    ):
        package_text = "\n".join(
            path.read_text(encoding="utf-8", errors="strict")
            for path in manifest.parent.rglob("*")
            if path.is_file() and path.suffix.casefold() in {".c", ".h"}
        )
        assert "I2C_MEMADD_SIZE" not in package_text


def test_builtin_catalog_contains_no_fake_can_device(
    builtin_catalog: PluginCatalog,
) -> None:
    for manifest in builtin_catalog.Type_Get("device"):
        assert "can bus" not in manifest.name.casefold()
        assert not any(
            requirement.kind in {"can_classic", "can_fd"}
            for requirement in manifest.resource_requirements
        )


def test_custom_i2c_source_graph_uses_one_plugin_hal_tree_only(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    installed = tmp_path / "installed_graph"
    _Device_Write(
        installed,
        "fixture.device.i2c_graph",
        "i2c",
        {"i2c": {"address_7bit": 0x48, "address_mode": "7bit"}},
        ["i2c.master_blocking"],
    )
    catalog = _Catalog_Create(workspace_root, installed)
    model = _CustomModel_Create(
        catalog,
        [DeviceInstance("sensor0", "fixture.device.i2c_graph")],
    )
    model.resource_assignments["sensor0:bus"] = "I2C1"
    model.hardware = replace(
        model.hardware,
        build_sources=(
            "HardwareGenerated/STM32CubeMX/Core/Src/main.c",
            "HardwareGenerated/STM32CubeMX/Core/Src/i2c.c",
        ),
    )
    graph = SourceGraph_Resolve(model, catalog)
    assert len(graph.sources) == len(set(graph.sources))
    assert graph.sources.count(
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c"
    ) == 1
    assert graph.sources.count(
        "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c"
    ) == 1
    assert not any(
        source.startswith("HardwareGenerated/STM32CubeMX/Drivers/")
        for source in graph.sources
    )
    assert not any(
        source.startswith("HardwareGenerated/STM32CubeMX/")
        and (source.casefold().endswith(".s") or source.casefold().endswith(".ld"))
        for source in (*graph.sources, *graph.asm_sources, graph.linker_script)
    )


def test_compatibility_facts_persist_and_participate_in_fingerprint(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("CompatibilityPersistence", catalog=builtin_catalog)
    serialized = model.Dictionary_Get()
    loaded = ProjectModel_Parse(json.loads(json.dumps(serialized)))
    assert loaded.hardware.cubemx_version == model.hardware.cubemx_version
    assert loaded.hardware.firmware_package == model.hardware.firmware_package
    assert loaded.hardware.hal_cmsis_source_policy == (
        model.hardware.hal_cmsis_source_policy
    )
    before = ProjectGenerationFingerprint_Get(model)
    loaded.hardware = replace(loaded.hardware, firmware_package="STM32Cube FW_F4 V1.28.2")
    assert ProjectGenerationFingerprint_Get(loaded) != before
