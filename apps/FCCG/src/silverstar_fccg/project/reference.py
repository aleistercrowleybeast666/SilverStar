from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from silverstar_fccg.app.version import SILVERSTAR_CORE_COMPONENT_ID
from silverstar_fccg.hardware.platform import (
    DetectedMcuFacts_FromInventory,
    PlatformMatch_Resolve,
)
from silverstar_fccg.plugins.manifest import PluginManifest_Load
from silverstar_fccg.project.logging import (
    LoggingProfile_Reconcile,
    ProtocolLogDefinitions_Load,
    ProtocolLogMetadataPath_Get,
)
from silverstar_fccg.project.model import (
    BuildOptions,
    DeviceInstance,
    HardwareConfiguration,
    LogStreamConfig,
    ProjectIdentity,
    ProjectModel,
    ProtocolSelection,
)
from silverstar_fccg.project.resources import BoardHardwareInventory_Get

if TYPE_CHECKING:
    from silverstar_fccg.plugins.catalog import PluginCatalog


REFERENCE_COMPONENT_IDS = {
    "core": SILVERSTAR_CORE_COMPONENT_ID,
    "board": "silverstar.board.silverstar_0_5",
    "os": "silverstar.os.freertos_11_3_0",
    "jy901b": "silverstar.device.imu.jy901b",
    "neo_m9n": "silverstar.device.gnss.neo_m9n",
    "sx1281": "silverstar.device.telemetry.sx1281",
    "console": "silverstar.device.console.uart",
    "storage": "silverstar.device.storage.sd_sdio_fatfs",
    "input_voltage": "silverstar.device.sensor.input_voltage",
    "launch_ignition": "silverstar.device.actuator.launch_ignition",
    "parachute_pyro": "silverstar.device.actuator.parachute_pyro",
    "system_indicator": "silverstar.device.indicator.system_status",
    "gnss_indicator": "silverstar.device.indicator.gnss_status",
    "mission_action_service": (
        "silverstar.flight_logic.mission_action.gpio_output_service"
    ),
    "indicator_service": (
        "silverstar.flight_logic.indicator.gpio_status_service"
    ),
    "algorithm_common": "silverstar.algorithm.common",
    "alignment_common": "silverstar.algorithm.alignment.common",
    "alignment": "silverstar.algorithm.alignment.gravity_known_yaw",
    "calibration": "silverstar.algorithm.calibration",
    "ins": "silverstar.algorithm.ins.coning2_sculling2",
    "kf6": "silverstar.algorithm.estimator.kf6",
    "flight_cycle": "silverstar.flight_logic.cycle.reference",
    "deployment": "silverstar.flight_logic.deployment.multi_trigger",
    "landing_common": "silverstar.flight_logic.landing.baro_imu_window",
    "landing": "silverstar.flight_logic.landing.baro_imu_window_strategy",
    "protocol_telemetry": "silverstar.protocol.telemetry.air_m0",
    "protocol_maintenance": "silverstar.protocol.maintenance.serial_0_0",
    "protocol_logging": "silverstar.protocol.logging.sslog_0_0",
    "environment": "silverstar.environment.vscode_eide_gcc",
    "hardware_provider": "silverstar.hardware_provider.stm32_cubemx",
}


def ProtocolDefaultStreams_Get() -> list[LogStreamConfig]:
    """Load new-project defaults from Protocol-owned metadata.

    Each record starts with its Protocol-declared default. Existing projects
    retain their serialized choices when they are opened.
    """
    repository_root = Path(__file__).resolve().parents[3]
    manifest = PluginManifest_Load(
        repository_root
        / "plugins"
        / "builtin"
        / "silverstar_protocol_logging_sslog_0_0"
        / "plugin.json"
    )
    return [
        LogStreamConfig(
            definition.record,
            definition.default_stream.enabled,
            definition.default_stream.policy,
            definition.default_stream.decimation,
            definition.default_stream.period_us,
        )
        for definition in ProtocolLogDefinitions_Load(
            ProtocolLogMetadataPath_Get(manifest)
        )
    ]


def ReferenceResourceAssignments_Get() -> dict[str, str]:
    return {
        "imu0:data": "PLATFORM_UART_1",
        "imu0:time": "PLATFORM_TIME_1",
        "gnss0:data": "PLATFORM_UART_2",
        "gnss0:reset": "PLATFORM_GPIO_7",
        "gnss0:timepulse": "PLATFORM_GPIO_8",
        "gnss0:time": "PLATFORM_TIME_1",
        "telemetry0:radio_bus": "PLATFORM_SPI_1",
        "telemetry0:radio_nss": "PLATFORM_GPIO_0",
        "telemetry0:radio_reset": "PLATFORM_GPIO_1",
        "telemetry0:radio_busy": "PLATFORM_GPIO_2",
        "telemetry0:radio_dio1": "PLATFORM_GPIO_3",
        "telemetry0:time": "PLATFORM_TIME_1",
        "maintenance0:console": "PLATFORM_UART_3",
        "launch_ignition0:output": "PLATFORM_GPIO_4",
        "launch_ignition0:time": "PLATFORM_TIME_1",
        "parachute_pyro0:output": "PLATFORM_GPIO_5",
        "parachute_pyro0:time": "PLATFORM_TIME_1",
        "system_indicator0:output": "PLATFORM_GPIO_6",
        "voltage_monitor0:input_voltage": "PLATFORM_ADC_1",
        "voltage_monitor0:time": "PLATFORM_TIME_1",
        "storage0:storage": "PLATFORM_SDIO_1",
        "storage0:time": "PLATFORM_TIME_1",
    }


def ReferenceProject_Create(
    name: str = "SilverStar_F407_Reference_Generated",
    *,
    reference_provenance: dict | None = None,
    catalog: PluginCatalog | None = None,
) -> ProjectModel:
    ids = REFERENCE_COMPONENT_IDS
    if catalog is None:
        from silverstar_fccg.plugins.catalog import PluginCatalog

        repository_root = Path(__file__).resolve().parents[3]
        catalog = PluginCatalog(
            repository_root / "plugins" / "builtin",
            repository_root / "plugins" / "installed",
        )
        catalog.Scan()

    protocol_components = {
        "telemetry": ids["protocol_telemetry"],
        "maintenance": ids["protocol_maintenance"],
        "logging": ids["protocol_logging"],
    }
    protocols = {
        category: ProtocolSelection(
            component=component_id,
            version=catalog.Component_Get(component_id).version,
            profile={
                "telemetry": "air.m0",
                "maintenance": "maintenance.serial.0_0",
                "logging": "flight_log.0_0",
            }[category],
            manifest_sha256=(
                catalog.Component_Get(component_id).ManifestSha256_Get()
            ),
        )
        for category, component_id in protocol_components.items()
    }
    board_manifest = catalog.Component_Get(ids["board"])
    inventory = BoardHardwareInventory_Get(board_manifest)
    if inventory is None or board_manifest.board is None:
        raise ValueError("Reference Board has no CubeMX hardware inventory")
    provider_manifest = catalog.Component_Get(board_manifest.board.provider)
    provider = provider_manifest.hardware_provider
    if provider is None:
        raise ValueError("Reference Board has no hardware provider contract")
    platform_match = PlatformMatch_Resolve(
        DetectedMcuFacts_FromInventory(
            inventory,
            vendor=provider.vendor,
            provider=provider.handler,
        ),
        catalog,
    )
    platform_manifest = catalog.Component_Get(
        platform_match.selected.component_id
    )
    model = ProjectModel(
        identity=ProjectIdentity(name=name),
        core=ids["core"],
        mcu=platform_match.selected.component_id,
        board=ids["board"],
        os=ids["os"],
        device_instances=[
            DeviceInstance("imu0", ids["jy901b"]),
            DeviceInstance("gnss0", ids["neo_m9n"]),
            DeviceInstance("telemetry0", ids["sx1281"]),
            DeviceInstance("maintenance0", ids["console"]),
            DeviceInstance("storage0", ids["storage"]),
            DeviceInstance("voltage_monitor0", ids["input_voltage"]),
            DeviceInstance("launch_ignition0", ids["launch_ignition"]),
            DeviceInstance("parachute_pyro0", ids["parachute_pyro"]),
            DeviceInstance("system_indicator0", ids["system_indicator"]),
        ],
        base_components=[
            ids["algorithm_common"],
            ids["alignment_common"],
            ids["calibration"],
            ids["flight_cycle"],
            ids["deployment"],
            ids["landing_common"],
            ids["mission_action_service"],
            ids["indicator_service"],
        ],
        strategies={
            "alignment": ids["alignment"],
            "ins": ids["ins"],
            "estimator": ids["kf6"],
            "landing": ids["landing"],
        },
        modes={
            "calibration": [],
            "deployment": ["ApogeeVerticalVelocity", "Tilt"],
        },
        protocols=protocols,
        development_environment=ids["environment"],
        hardware=HardwareConfiguration(
            mode="board_plugin",
            source_kind="verified_builtin",
            provider=board_manifest.board.provider,
            ioc_file=board_manifest.board.ioc_file,
            mcu=inventory.mcu_part,
            platform_component=platform_manifest.component_id,
            platform_version=platform_manifest.version,
            platform_manifest_sha256=platform_manifest.ManifestSha256_Get(),
            cubemx_version=inventory.cubemx_version,
            firmware_package=inventory.firmware_package,
            hal_cmsis_source_policy=(
                platform_manifest.platform.compatibility.source_policy
                if platform_manifest.platform is not None
                else ""
            ),
            capabilities=tuple(
                sorted(
                    {
                        f"peripheral.{resource.kind}"
                        for resource in inventory.HardwareResources_Get()
                    }
                )
            ),
            inventory=inventory.Dictionary_Get(),
            source_label=board_manifest.name,
        ),
        resource_assignments=ReferenceResourceAssignments_Get(),
        logging_streams=ProtocolDefaultStreams_Get(),
        build=BuildOptions(
            target_profile=(
                platform_manifest.platform.build_target_profile
                if platform_manifest.platform is not None
                else ""
            )
        ),
        reference_provenance=dict(reference_provenance or {}),
    )
    LoggingProfile_Reconcile(model, catalog)
    from silverstar_fccg.project.algorithm_parameters import (
        AlgorithmParameters_Reconcile,
    )
    AlgorithmParameters_Reconcile(model, catalog)
    return model
