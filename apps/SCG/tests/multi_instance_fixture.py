from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.capabilities import (
    CapabilitySourceOverrides_Reconcile,
)
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.model import DeviceInstance, HardwareConfiguration, ProjectModel
from silverstar_fccg.project.reference import REFERENCE_COMPONENT_IDS, ReferenceProject_Create
from silverstar_fccg.project.resources import ResourceAssignments_Resolve


MULTI_INSTANCE_BOARD_ID = "fixture.board.f407_multi_instance"


def _WorkspaceTestRoot_Require(workspace_root: Path, destination: Path) -> Path:
    tests_root = (workspace_root / "tests").resolve()
    resolved = destination.resolve()
    try:
        resolved.relative_to(tests_root)
    except ValueError as error:
        raise ValueError("Multi-instance fixture output must remain below tests/") from error
    return resolved


def _Provision_Create(
    resource_id: str, kind: str, c_id: str, header: str = ""
) -> dict[str, object]:
    metadata = {"c_id": c_id}
    if header:
        metadata["header"] = header
    return {"id": resource_id, "kind": kind, "metadata": metadata}


def _Role_Create(
    key: str, kind: str, resource_id: str, *, fixed: bool = True
) -> dict[str, object]:
    return {
        "key": key,
        "kind": kind,
        "default": resource_id,
        "candidates": [resource_id],
        "fixed": fixed,
    }


def _BoardManifest_Create(source: dict[str, object]) -> dict[str, object]:
    manifest = deepcopy(source)
    manifest["id"] = MULTI_INSTANCE_BOARD_ID
    manifest["name"] = "F407 Multi-instance Compile Fixture"
    manifest["version"] = "1.0.0"
    manifest["description"] = (
        "Test-only compile fixture with independent logical resources for two "
        "JY901B, NEO-M9N and SX1281 instances; it is not an electrically "
        "verified PCB declaration."
    )

    uart_resources = [
        ("MULTI_UART_IMU_0", "PLATFORM_UART_1"),
        ("MULTI_UART_GNSS_0", "PLATFORM_UART_2"),
        ("MULTI_UART_CONSOLE_0", "PLATFORM_UART_3"),
        ("MULTI_UART_IMU_1", "((PlatformUartId)3U)"),
        ("MULTI_UART_GNSS_1", "((PlatformUartId)4U)"),
    ]
    spi_resources = [
        ("MULTI_SPI_RADIO_0", "PLATFORM_SPI_1"),
        ("MULTI_SPI_RADIO_1", "((PlatformSpiId)1U)"),
    ]
    gpio_resources = [
        ("MULTI_GPIO_RADIO_0_NSS", "gpio_output", "PLATFORM_GPIO_0"),
        ("MULTI_GPIO_RADIO_0_RESET", "gpio_output", "PLATFORM_GPIO_1"),
        ("MULTI_GPIO_RADIO_0_BUSY", "gpio_input", "PLATFORM_GPIO_2"),
        ("MULTI_GPIO_RADIO_0_DIO1", "gpio_interrupt", "PLATFORM_GPIO_3"),
        ("MULTI_GPIO_LAUNCH", "gpio_output", "PLATFORM_GPIO_4"),
        ("MULTI_GPIO_PARACHUTE", "gpio_output", "PLATFORM_GPIO_5"),
        ("MULTI_GPIO_SYSTEM_LED", "gpio_output", "PLATFORM_GPIO_6"),
        ("MULTI_GPIO_GNSS_0_RESET", "gpio_output", "PLATFORM_GPIO_7"),
        ("MULTI_GPIO_GNSS_0_TIMEPULSE", "gpio_interrupt", "PLATFORM_GPIO_8"),
        ("MULTI_GPIO_GNSS_1_RESET", "gpio_output", "((PlatformGpioId)9U)"),
        (
            "MULTI_GPIO_GNSS_1_TIMEPULSE",
            "gpio_interrupt",
            "((PlatformGpioId)10U)",
        ),
        ("MULTI_GPIO_RADIO_1_NSS", "gpio_output", "((PlatformGpioId)11U)"),
        ("MULTI_GPIO_RADIO_1_RESET", "gpio_output", "((PlatformGpioId)12U)"),
        ("MULTI_GPIO_RADIO_1_BUSY", "gpio_input", "((PlatformGpioId)13U)"),
        (
            "MULTI_GPIO_RADIO_1_DIO1",
            "gpio_interrupt",
            "((PlatformGpioId)14U)",
        ),
    ]
    provisions = [
        *(
            _Provision_Create(resource_id, "uart", c_id, "platform_uart.h")
            for resource_id, c_id in uart_resources
        ),
        *(
            _Provision_Create(resource_id, "spi", c_id, "platform_spi.h")
            for resource_id, c_id in spi_resources
        ),
        *(
            _Provision_Create(resource_id, kind, c_id, "platform_gpio.h")
            for resource_id, kind, c_id in gpio_resources
        ),
        _Provision_Create(
            "MULTI_ADC_INPUT_VOLTAGE", "adc", "PLATFORM_ADC_1", "platform_adc.h"
        ),
        {
            **_Provision_Create(
                "MULTI_SDIO_STORAGE", "sdio", "PLATFORM_SDIO_1", "sdio.h"
            ),
            "metadata": {
                "c_id": "PLATFORM_SDIO_1",
                "header": "sdio.h",
                "fatfs": {
                    "enabled": True,
                    "object_symbol": "SDFatFS",
                    "path_symbol": "SDPath",
                    "driver_symbol": "SD_Driver",
                    "errors": [],
                },
            },
        },
        _Provision_Create(
            "MULTI_TIME", "time", "((PlatformTimeId)0U)", "platform_time.h"
        ),
    ]
    roles = [
        _Role_Create("imu0:data", "uart", "MULTI_UART_IMU_0"),
        _Role_Create("imu0:time", "time", "MULTI_TIME"),
        _Role_Create("imu1:data", "uart", "MULTI_UART_IMU_1"),
        _Role_Create("imu1:time", "time", "MULTI_TIME"),
        _Role_Create("gnss0:data", "uart", "MULTI_UART_GNSS_0"),
        _Role_Create("gnss0:reset", "gpio_output", "MULTI_GPIO_GNSS_0_RESET"),
        _Role_Create(
            "gnss0:timepulse", "gpio_interrupt", "MULTI_GPIO_GNSS_0_TIMEPULSE"
        ),
        _Role_Create("gnss0:time", "time", "MULTI_TIME"),
        _Role_Create("gnss1:data", "uart", "MULTI_UART_GNSS_1"),
        _Role_Create("gnss1:reset", "gpio_output", "MULTI_GPIO_GNSS_1_RESET"),
        _Role_Create(
            "gnss1:timepulse", "gpio_interrupt", "MULTI_GPIO_GNSS_1_TIMEPULSE"
        ),
        _Role_Create("gnss1:time", "time", "MULTI_TIME"),
        _Role_Create("telemetry0:radio_bus", "spi", "MULTI_SPI_RADIO_0"),
        _Role_Create(
            "telemetry0:radio_nss", "gpio_output", "MULTI_GPIO_RADIO_0_NSS"
        ),
        _Role_Create(
            "telemetry0:radio_reset", "gpio_output", "MULTI_GPIO_RADIO_0_RESET"
        ),
        _Role_Create(
            "telemetry0:radio_busy", "gpio_input", "MULTI_GPIO_RADIO_0_BUSY"
        ),
        _Role_Create(
            "telemetry0:radio_dio1", "gpio_interrupt", "MULTI_GPIO_RADIO_0_DIO1"
        ),
        _Role_Create("telemetry0:time", "time", "MULTI_TIME"),
        _Role_Create("telemetry1:radio_bus", "spi", "MULTI_SPI_RADIO_1"),
        _Role_Create(
            "telemetry1:radio_nss", "gpio_output", "MULTI_GPIO_RADIO_1_NSS"
        ),
        _Role_Create(
            "telemetry1:radio_reset", "gpio_output", "MULTI_GPIO_RADIO_1_RESET"
        ),
        _Role_Create(
            "telemetry1:radio_busy", "gpio_input", "MULTI_GPIO_RADIO_1_BUSY"
        ),
        _Role_Create(
            "telemetry1:radio_dio1", "gpio_interrupt", "MULTI_GPIO_RADIO_1_DIO1"
        ),
        _Role_Create("telemetry1:time", "time", "MULTI_TIME"),
        _Role_Create("maintenance0:console", "uart", "MULTI_UART_CONSOLE_0"),
        _Role_Create(
            "launch_ignition0:output", "gpio_output", "MULTI_GPIO_LAUNCH"
        ),
        _Role_Create("launch_ignition0:time", "time", "MULTI_TIME"),
        _Role_Create(
            "parachute_pyro0:output", "gpio_output", "MULTI_GPIO_PARACHUTE"
        ),
        _Role_Create("parachute_pyro0:time", "time", "MULTI_TIME"),
        _Role_Create(
            "system_indicator0:output", "gpio_output", "MULTI_GPIO_SYSTEM_LED"
        ),
        _Role_Create(
            "voltage_monitor0:input_voltage", "adc", "MULTI_ADC_INPUT_VOLTAGE"
        ),
        _Role_Create("voltage_monitor0:time", "time", "MULTI_TIME"),
        _Role_Create("storage0:storage", "sdio", "MULTI_SDIO_STORAGE"),
        _Role_Create("storage0:time", "time", "MULTI_TIME"),
    ]
    manifest["resources"] = {
        "provides": provisions,
        "roles": roles,
        "conflicts": [],
    }
    metadata = manifest["metadata"]
    assert isinstance(metadata, dict)
    metadata["display_names"] = {
        "zh_CN": "F407 多实例编译夹具",
        "en_US": "F407 Multi-instance Compile Fixture",
    }
    metadata["descriptions"] = {
        "zh_CN": "仅用于自动化生成与编译测试，不代表已验证PCB或电气映射。",
        "en_US": (
            "Automation-only generation and compile fixture; not a verified "
            "PCB or electrical mapping."
        ),
    }
    metadata["platform_resources"] = {
        "uarts": [
            {"id": resource_id, "logical_index": index, "handle": handle}
            for index, (resource_id, handle) in enumerate(
                (
                    ("MULTI_UART_IMU_0", "huart1"),
                    ("MULTI_UART_GNSS_0", "huart2"),
                    ("MULTI_UART_CONSOLE_0", "huart3"),
                    ("MULTI_UART_IMU_1", "huart1"),
                    ("MULTI_UART_GNSS_1", "huart2"),
                )
            )
        ],
        "spis": [
            {"id": resource_id, "logical_index": index, "handle": "hspi1"}
            for index, resource_id in enumerate(
                ("MULTI_SPI_RADIO_0", "MULTI_SPI_RADIO_1")
            )
        ],
        "adcs": [
            {
                "id": "MULTI_ADC_INPUT_VOLTAGE",
                "logical_index": 0,
                "handle": "hadc1",
            }
        ],
        "gpios": [
            {
                "id": resource_id,
                "logical_index": index,
                "port": port,
                "pin": pin,
                "irq_enabled": irq_enabled,
            }
            for index, (resource_id, port, pin, irq_enabled) in enumerate(
                (
                    (
                        "MULTI_GPIO_RADIO_0_NSS",
                        "RADIO_NSS_GPIO_Port",
                        "RADIO_NSS_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_0_RESET",
                        "RADIO_RST_GPIO_Port",
                        "RADIO_RST_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_0_BUSY",
                        "RADIO_BUSY_GPIO_Port",
                        "RADIO_BUSY_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_0_DIO1",
                        "RADIO_DIO1_GPIO_Port",
                        "RADIO_DIO1_Pin",
                        1,
                    ),
                    (
                        "MULTI_GPIO_LAUNCH",
                        "P_CONTROL2_GPIO_Port",
                        "P_CONTROL2_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_PARACHUTE",
                        "P_CONTROL1_GPIO_Port",
                        "P_CONTROL1_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_SYSTEM_LED",
                        "IMU_CAL_LED_GPIO_Port",
                        "IMU_CAL_LED_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_GNSS_0_RESET",
                        "GNSS_RST_GPIO_Port",
                        "GNSS_RST_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_GNSS_0_TIMEPULSE",
                        "GNSS_TIMEPULSE_GPIO_Port",
                        "GNSS_TIMEPULSE_Pin",
                        1,
                    ),
                    (
                        "MULTI_GPIO_GNSS_1_RESET",
                        "GNSS_RST_GPIO_Port",
                        "GNSS_RST_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_GNSS_1_TIMEPULSE",
                        "GNSS_TIMEPULSE_GPIO_Port",
                        "GNSS_TIMEPULSE_Pin",
                        1,
                    ),
                    (
                        "MULTI_GPIO_RADIO_1_NSS",
                        "RADIO_NSS_GPIO_Port",
                        "RADIO_NSS_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_1_RESET",
                        "RADIO_RST_GPIO_Port",
                        "RADIO_RST_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_1_BUSY",
                        "RADIO_BUSY_GPIO_Port",
                        "RADIO_BUSY_Pin",
                        0,
                    ),
                    (
                        "MULTI_GPIO_RADIO_1_DIO1",
                        "RADIO_DIO1_GPIO_Port",
                        "RADIO_DIO1_Pin",
                        1,
                    ),
                )
            )
        ],
        "i2cs": [],
        "cans": [],
        "pwms": [],
        "timebases": [
            {
                "id": "MULTI_TIME",
                "logical_index": 0,
                "handle": "htim1",
                "handle_type": "TIM_HandleTypeDef",
                "counter_frequency_hz": 1_000_000,
                "period_counts": 1_000,
                "tick_frequency_hz": 1_000,
            }
        ],
    }
    board = manifest["board"]
    assert isinstance(board, dict)
    board.clear()
    board.update(
        {
            "source_kind": "third_party",
            "compatible_mcus": ["silverstar.mcu.stm32f407vet6"],
            "vendor": "STM32",
            "provider": "silverstar.hardware_provider.stm32_cubemx",
            "verified": False,
            "hardware_root": "Core",
        }
    )
    return manifest


def MultiInstanceCatalog_Create(
    workspace_root: Path, runtime_root: Path
) -> PluginCatalog:
    runtime = _WorkspaceTestRoot_Require(workspace_root, runtime_root)
    package_root = runtime / "multi_instance_board"
    if runtime.exists():
        shutil.rmtree(runtime)
    package_root.mkdir(parents=True)
    source_root = workspace_root / "plugins" / "builtin" / "silverstar_board_silverstar_0_5"
    shutil.copytree(source_root / "payload", package_root / "payload")
    source_manifest = json.loads(
        (source_root / "plugin.json").read_text(encoding="utf-8")
    )
    (package_root / "plugin.json").write_text(
        json.dumps(
            _BoardManifest_Create(source_manifest),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    catalog = PluginCatalog(workspace_root / "plugins" / "builtin", runtime)
    catalog.Scan()
    return catalog


def MultiInstanceProject_Create(
    catalog: PluginCatalog, name: str = "SilverStar_Multi_Instance_Acceptance"
) -> ProjectModel:
    model = ReferenceProject_Create(name, catalog=catalog)
    model.board = MULTI_INSTANCE_BOARD_ID
    board = catalog.Component_Get(MULTI_INSTANCE_BOARD_ID)
    platform = catalog.Component_Get(model.mcu)
    assert board.board is not None and platform.platform is not None
    model.hardware = HardwareConfiguration(
        mode="board_plugin",
        source_kind="third_party",
        provider=board.board.provider,
        mcu=model.hardware.mcu,
        platform_component=platform.component_id,
        platform_version=platform.version,
        platform_manifest_sha256=platform.ManifestSha256_Get(),
        cubemx_version=model.hardware.cubemx_version,
        firmware_package=model.hardware.firmware_package,
        hal_cmsis_source_policy=platform.platform.compatibility.source_policy,
        capabilities=model.hardware.capabilities,
        inventory=deepcopy(model.hardware.inventory),
        source_label=board.name,
    )
    model.device_instances.extend(
        (
            DeviceInstance("imu1", REFERENCE_COMPONENT_IDS["jy901b"]),
            DeviceInstance("gnss1", REFERENCE_COMPONENT_IDS["neo_m9n"]),
            DeviceInstance("telemetry1", REFERENCE_COMPONENT_IDS["sx1281"]),
        )
    )
    model.resource_assignments = {}
    resources = ResourceAssignments_Resolve(model, catalog, auto_assign=True)
    if not resources.valid:
        raise ValueError("Multi-instance fixture resources failed: " + "; ".join(resources.errors))
    CapabilitySourceOverrides_Reconcile(model, catalog)
    LoggingProfile_Reconcile(model, catalog)
    return model
