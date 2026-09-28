from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.render import (
    GeneratedFiles_Render,
    MetadataFiles_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.hardware.cubemx import CubeMxImportResult
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.hardware.platform import PlatformMatchError
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    DeviceInstance,
    HardwareConfiguration,
    HardwareResource,
    ProjectModelError,
    ProjectModel_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    ResourceAssignments_Resolve,
)
from silverstar_fccg.project.validation import Project_Validate


STORAGE_PLUGIN = "silverstar.device.storage.sd_sdio_fatfs"
BOARD_PLUGIN = "silverstar.board.silverstar_0_5"
MCU_PLUGIN = "silverstar.mcu.stm32f407vet6"


def _TimebaseSource_Get(
    instance: str = "TIM1",
    handle: str = "htim1",
    irq: str = "TIM1_UP_TIM10_IRQn",
    *,
    counter_frequency_hz: int = 1_000_000,
    tick_frequency_hz: int = 1_000,
    start_interrupt: bool = True,
    enable_irq: bool = True,
) -> str:
    start = (
        f"HAL_TIM_Base_Start_IT(&{handle});"
        if start_interrupt
        else f"HAL_TIM_Base_Start(&{handle});"
    )
    irq_enable = f"HAL_NVIC_EnableIRQ({irq});" if enable_irq else ""
    return f"""
TIM_HandleTypeDef {handle};
HAL_StatusTypeDef HAL_InitTick(uint32_t TickPriority)
{{
    uint32_t uwTimclock = 0U;
    uint32_t uwPrescalerValue =
        (uint32_t)((uwTimclock / {counter_frequency_hz}U) - 1U);
    (void)TickPriority;
    (void)uwPrescalerValue;
    {handle}.Instance = {instance};
    {handle}.Init.Period =
        ({counter_frequency_hz}U / {tick_frequency_hz}U) - 1U;
    {start}
    {irq_enable}
    return HAL_OK;
}}
"""


def _TimebaseIoc_Get(
    instance: str = "TIM1", irq: str = "TIM1_UP_TIM10_IRQn"
) -> str:
    return "\n".join(
        (
            "Mcu.CPN=STM32F407VET6",
            "Mcu.Family=STM32F4",
            "Mcu.Package=LQFP100",
            "Mcu.IP0=NVIC",
            "Mcu.IP1=RCC",
            "Mcu.IP2=SYS",
            f"NVIC.{irq}=true:15:0",
            f"NVIC.TimeBase={irq}",
            f"NVIC.TimeBaseIP={instance}",
        )
    )


@pytest.mark.parametrize(
    ("instance", "handle", "irq"),
    (
        ("TIM1", "htim1", "TIM1_UP_TIM10_IRQn"),
        ("TIM6", "htim6", "TIM6_DAC_IRQn"),
    ),
)
def test_tim_hal_timebase_is_read_from_cubemx_without_fixed_timer(
    instance: str, handle: str, irq: str
) -> None:
    inventory = CubeMxInventory_Parse(
        _TimebaseIoc_Get(instance, irq),
        generated_files={
            "Core/Src/stm32f4xx_hal_timebase_tim.c": (
                _TimebaseSource_Get(instance, handle, irq)
            )
        },
    )
    assert inventory.timebase.valid
    assert inventory.timebase.instance == instance
    assert inventory.timebase.handle == handle
    assert inventory.timebase.irq == irq
    assert inventory.timebase.counter_frequency_hz == 1_000_000
    assert inventory.timebase.period_counts == 1_000
    time_resource = next(
        item
        for item in inventory.HardwareResources_Get()
        if item.kind == "time"
    )
    assert time_resource.metadata["handle"] == handle
    assert time_resource.metadata["handle_type"] == "TIM_HandleTypeDef"
    assert time_resource.metadata["timer_instance"] == instance


@pytest.mark.parametrize(
    ("ioc", "files", "message"),
    (
        (
            "Mcu.CPN=STM32F407VET6\nMcu.IP0=SYS",
            {},
            "must use one TIM",
        ),
        (
            _TimebaseIoc_Get(),
            {},
            "Exactly one generated",
        ),
        (
            _TimebaseIoc_Get(),
            {
                "Core/Src/stm32f4xx_hal_timebase_tim.c": (
                    _TimebaseSource_Get("TIM6", "htim6", "TIM1_UP_TIM10_IRQn")
                )
            },
            "does not match .ioc",
        ),
        (
            _TimebaseIoc_Get(),
            {
                "Core/Src/stm32f4xx_hal_timebase_tim.c": (
                    _TimebaseSource_Get(counter_frequency_hz=2_000_000)
                )
            },
            "1 MHz counter",
        ),
        (
            _TimebaseIoc_Get(),
            {
                "Core/Src/stm32f4xx_hal_timebase_tim.c": (
                    _TimebaseSource_Get(enable_irq=False)
                )
            },
            "IRQ is missing",
        ),
        (
            _TimebaseIoc_Get(),
            {
                "Core/Src/stm32f4xx_hal_timebase_tim.c": (
                    _TimebaseSource_Get(start_interrupt=False)
                )
            },
            "not started in interrupt mode",
        ),
    ),
)
def test_invalid_hal_timebase_contracts_fail_early(
    ioc: str, files: dict[str, str], message: str
) -> None:
    inventory = CubeMxInventory_Parse(ioc, generated_files=files)
    assert not inventory.timebase.valid
    assert any(message in error for error in inventory.timebase.errors)


def test_timebase_timer_is_removed_from_pwm_candidates() -> None:
    ioc = _TimebaseIoc_Get("TIM6", "TIM6_DAC_IRQn") + "\n" + "\n".join(
        (
            "Mcu.IP3=TIM6",
            "PA0.Signal=TIM6_CH1",
            "SH.S_TIM6_CH1.0=TIM6_CH1,PWM Generation1 CH1",
            "TIM6.Prescaler=83",
            "TIM6.Period=999",
            "RCC.APB1Freq_Value=42000000",
        )
    )
    inventory = CubeMxInventory_Parse(
        ioc,
        generated_files={
            "Core/Src/stm32f4xx_hal_timebase_tim.c": _TimebaseSource_Get(
                "TIM6", "htim6", "TIM6_DAC_IRQn"
            ),
            "Core/Src/tim.c": """
TIM_HandleTypeDef htim6;
void MX_TIM6_Init(void)
{
    TIM_OC_InitTypeDef config = {0};
    htim6.Instance = TIM6;
    htim6.Init.CounterMode = TIM_COUNTERMODE_UP;
    config.OCMode = TIM_OCMODE_PWM1;
    config.OCPolarity = TIM_OCPOLARITY_HIGH;
    HAL_TIM_PWM_ConfigChannel(&htim6, &config, TIM_CHANNEL_1);
}
""",
        },
    )
    assert inventory.pwms == ()
    assert any(
        issue.startswith("inventory.timebase_pwm_conflict")
        for issue in inventory.issues
    )


def test_unlabelled_cubemx_gpio_uses_physical_hal_expressions() -> None:
    inventory = CubeMxInventory_Parse(
        _TimebaseIoc_Get() + "\n" + "\n".join(
            (
                "PC7.Signal=GPIO_Output",
                "PC7.GPIO_Mode=GPIO_MODE_OUTPUT_PP",
                "PC7.PinState=GPIO_PIN_RESET",
            )
        ),
        generated_files={
            "Core/Src/stm32f4xx_hal_timebase_tim.c": _TimebaseSource_Get()
        },
    )
    gpio = next(
        resource
        for resource in inventory.HardwareResources_Get()
        if resource.resource_id == "PC7"
    )
    assert gpio.metadata["port"] == "GPIOC"
    assert gpio.metadata["pin"] == "GPIO_PIN_7"


def test_labelled_cubemx_gpio_keeps_generated_label_macros() -> None:
    inventory = CubeMxInventory_Parse(
        _TimebaseIoc_Get() + "\n" + "\n".join(
            (
                "PE7.Signal=GPXTI7",
                "PE7.GPIO_Label=RADIO_DIO1",
                "PE7.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_RISING",
            )
        ),
        generated_files={
            "Core/Src/stm32f4xx_hal_timebase_tim.c": _TimebaseSource_Get()
        },
    )
    gpio = next(
        resource
        for resource in inventory.HardwareResources_Get()
        if resource.resource_id == "RADIO_DIO1"
    )
    assert gpio.metadata["port"] == "RADIO_DIO1_GPIO_Port"
    assert gpio.metadata["pin"] == "RADIO_DIO1_Pin"


def _CustomStorageModel_Get(catalog, *, mutate: str = ""):
    model = ReferenceProject_Create("StorageContract", catalog=catalog)
    board = catalog.Component_Get(BOARD_PLUGIN)
    inventory = BoardHardwareInventory_Get(board)
    assert inventory is not None
    resources = list(inventory.HardwareResources_Get())
    changed: list[HardwareResource] = []
    for resource in resources:
        if resource.kind != "sdio":
            changed.append(resource)
            continue
        metadata = deepcopy(resource.metadata)
        if mutate == "fatfs":
            metadata["fatfs"]["errors"] = ["fixture invalid FatFs"]
        elif mutate == "dma_rx":
            metadata["dma"] = [
                item
                for item in metadata["dma"]
                if not str(item.get("request", "")).endswith("_RX")
            ]
        elif mutate == "dma_tx":
            metadata["dma"] = [
                item
                for item in metadata["dma"]
                if not str(item.get("request", "")).endswith("_TX")
            ]
        elif mutate == "irq":
            metadata["irq"]["enabled"] = False
        elif mutate == "sdmmc":
            metadata["peripheral"] = "SDMMC1"
        changed.append(HardwareResource(resource.resource_id, resource.kind, metadata))
    if mutate == "sdio":
        changed = [item for item in changed if item.kind != "sdio"]
    platform = catalog.Component_Get(MCU_PLUGIN)
    model.board = ""
    model.device_instances = [DeviceInstance("storage0", STORAGE_PLUGIN)]
    model.resource_assignments = {
        "storage0:storage": "SDIO",
        "storage0:time": "SYSTEM_TIME",
    }
    model.hardware = HardwareConfiguration(
        mode="custom",
        source_kind="manual_import",
        provider="silverstar.hardware_provider.stm32_cubemx",
        snapshot_id="a" * 64,
        ioc_file="Flight_Controller0.5.ioc",
        mcu=inventory.mcu_part,
        platform_component=platform.component_id,
        platform_version=platform.version,
        platform_manifest_sha256=platform.ManifestSha256_Get(),
        cubemx_version=inventory.cubemx_version,
        firmware_package=inventory.firmware_package,
        hal_cmsis_source_policy="plugin_payload_authoritative",
        inventory=inventory.Dictionary_Get(),
        resources=tuple(changed),
        build_sources=(
            "HardwareGenerated/STM32CubeMX/Core/Src/main.c",
            "HardwareGenerated/STM32CubeMX/Core/Src/sdio.c",
            "HardwareGenerated/STM32CubeMX/Core/Src/stm32f4xx_hal_timebase_tim.c",
            "HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c",
            "HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c",
        ),
        include_dirs=(
            "HardwareGenerated/STM32CubeMX/Core/Inc",
            "HardwareGenerated/STM32CubeMX/FATFS/App",
            "HardwareGenerated/STM32CubeMX/FATFS/Target",
        ),
        source_digest="b" * 64,
        risk_acknowledged=True,
    )
    return model


def test_reference_storage_device_has_unique_ownership_and_decoder_semantics(
    builtin_catalog,
) -> None:
    storage = builtin_catalog.Component_Get(STORAGE_PLUGIN)
    board = builtin_catalog.Component_Get(BOARD_PLUGIN)
    assert storage.component_type == "device"
    assert storage.metadata["device_category"].startswith("storage.")
    assert storage.instance_policy.plugin_max == 1
    assert "service.storage" in storage.provides
    assert "service.log_sink" in storage.provides
    assert "transport.sequential_file_sink" in storage.provides
    assert "service.storage" not in board.provides
    assert "service.log_sink" not in board.provides
    assert not board.transports

    model = ReferenceProject_Create("StorageRc", catalog=builtin_catalog)
    assert sum(instance.plugin == STORAGE_PLUGIN for instance in model.device_instances) == 1
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid
    graph = SourceGraph_Resolve(model, builtin_catalog)
    for source in (
        "Devices/Storage/SdSdioFatFs/Src/storage_service.c",
        "Devices/Storage/SdSdioFatFs/Src/log_sink_service.c",
        "Middlewares/Third_Party/FatFs/src/ff.c",
        "Middlewares/Third_Party/FatFs/src/diskio.c",
        "Middlewares/Third_Party/FatFs/src/ff_gen_drv.c",
    ):
        assert graph.sources.count(source) == 1
    assert not any("stm32f4xx_hal_mmc.c" in source for source in graph.sources)

    generated = GeneratedFiles_Render(model, builtin_catalog, graph)
    storage_binding = generated[
        "Generated/Inc/project_storage_binding.h"
    ].decode("utf-8")
    assert "PROJECT_STORAGE_FATFS_OBJECT SDFatFS" in storage_binding
    assert "PROJECT_STORAGE_FATFS_PATH   SDPath" in storage_binding
    assert "PROJECT_STORAGE_FATFS_DRIVER SD_Driver" in storage_binding
    platform_resources = generated[
        "Generated/Src/platform_resources.c"
    ].decode("utf-8")
    assert "extern TIM_HandleTypeDef htim1;" in platform_resources
    assert "&htim1" in platform_resources
    project_resources = generated[
        "Generated/Inc/project_resources.h"
    ].decode("utf-8")
    assert '#include "sdio.h"' not in project_resources
    assert "PROJECT_RESOURCE_STORAGE_SDIO" not in project_resources

    first = MetadataFiles_Render(model, builtin_catalog, graph)["StorageRc.ssdecoder"]
    second = MetadataFiles_Render(model, builtin_catalog, graph)["StorageRc.ssdecoder"]
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as package:
        assert all(
            not name.casefold().endswith(
                (".py", ".pyc", ".pyd", ".dll", ".exe", ".bat", ".ps1")
            )
            for name in package.namelist()
        )
        semantics = json.loads(package.read("project_semantics.json"))
    storage_device = next(
        item
        for item in semantics["physical_devices"]
        if item["instance_id"] == "storage0"
    )
    assert storage_device["plugin"] == STORAGE_PLUGIN
    logging_binding = next(
        item
        for item in semantics["protocol_bindings"]
        if item["service"] == "flight_log_service"
    )
    assert logging_binding["physical_device_instance"] == "storage0"
    storage_lock = next(
        item
        for item in semantics["component_locks"]
        if item["component"] == STORAGE_PLUGIN
    )
    assert storage_lock["version"] == storage.version
    assert storage_lock["manifest_sha256"] == storage.ManifestSha256_Get()


def test_host_tests_use_generated_component_features_with_override_guards(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("HostFeatureConfig", catalog=builtin_catalog)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    flight_config = GeneratedFiles_Render(model, builtin_catalog, graph)[
        "Generated/Inc/project_flight_config.h"
    ].decode("utf-8")
    assert "#ifndef SYSTEM_USER_MISSION_ACTION_ENABLE" in flight_config
    assert "#ifndef MISSION_ACTION_OUTPUT_BUILD_START_ACTION_AVAILABLE" in flight_config

    core = builtin_catalog.Component_Get("silverstar.core.0_1_0")
    host_runner = (
        core.payload_root / "Tests" / "Host" / "run_tests.ps1"
    ).read_text(encoding="utf-8")
    assert "Generated\\Inc\\project_flight_config.h" in host_runner
    assert host_runner.count(
        "-DSYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK=SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ"
    ) >= 2


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("sdio", "Unknown resource SDIO"),
        ("fatfs", "unique CubeMX FatFs"),
        ("dma_rx", "SDIO RX DMA"),
        ("dma_tx", "SDIO TX DMA"),
        ("irq", "enabled SDIO IRQ"),
        ("sdmmc", "storage.sdio_only"),
    ),
)
def test_storage_device_rejects_incomplete_hardware_contracts(
    builtin_catalog, mutation: str, message: str
) -> None:
    model = _CustomStorageModel_Get(builtin_catalog, mutate=mutation)
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert not resolution.valid
    assert any(message in error for error in resolution.errors)
    service = FccgService(Path(__file__).resolve().parents[1])
    availability = service.DeviceSelectionAvailabilities_Get(model)[STORAGE_PLUGIN]
    assert not availability.available
    assert availability.reason_code == "selection.unavailable.hardware_contract"


def test_storage_selection_is_available_until_custom_hardware_is_prepared(
    workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create("PendingStorageHardware")

    availability = service.DeviceSelectionAvailabilities_Get(model)[STORAGE_PLUGIN]
    assert model.hardware.mode == "custom"
    assert not model.hardware.snapshot_id
    assert availability.available
    assert not availability.reason_code

    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != STORAGE_PLUGIN
    ]
    availability = service.DeviceSelectionAvailabilities_Get(model)[STORAGE_PLUGIN]
    assert availability.available
    assert not availability.reason_code


def test_fatfs_symbol_ambiguity_and_missing_target_are_detected(
    builtin_catalog,
) -> None:
    board = builtin_catalog.Component_Get(BOARD_PLUGIN)
    assert board.board is not None
    ioc_path = board.package_root.joinpath(*board.board.ioc_file.split("/"))
    generated_files = {
        path.relative_to(ioc_path.parent).as_posix(): path.read_text(
            encoding="utf-8-sig"
        )
        for relative_root in ("Core/Src", "Core/Inc", "FATFS/App", "FATFS/Target")
        for directory in (ioc_path.parent.joinpath(*relative_root.split("/")),)
        if directory.is_dir()
        for path in directory.glob("*")
        if path.is_file() and path.suffix.casefold() in {".c", ".h"}
    }
    ambiguous = dict(generated_files)
    ambiguous["FATFS/App/fatfs.h"] += "\nextern FATFS OtherFatFs;\n"
    inventory = CubeMxInventory_Parse(
        ioc_path.read_text(encoding="utf-8-sig"),
        generated_files=ambiguous,
    )
    assert not inventory.fatfs.valid
    assert any("ambiguous" in error for error in inventory.fatfs.errors)

    missing_target = {
        path: text
        for path, text in generated_files.items()
        if "/fatfs/target/" not in ("/" + path.casefold())
    }
    inventory = CubeMxInventory_Parse(
        ioc_path.read_text(encoding="utf-8-sig"),
        generated_files=missing_target,
    )
    assert not inventory.fatfs.valid
    assert any("Target glue is missing" in error for error in inventory.fatfs.errors)


def test_storage_absence_keeps_cubemx_fatfs_provider_but_fails_log_sink(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("NoStorage", catalog=builtin_catalog)
    model.device_instances = [
        instance
        for instance in model.device_instances
        if instance.plugin != STORAGE_PLUGIN
    ]
    model.resource_assignments = {
        key: value
        for key, value in model.resource_assignments.items()
        if not key.startswith("storage0:")
    }
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "Middlewares/Third_Party/FatFs/src/ff.c" in graph.sources
    assert "FATFS/App/fatfs.c" in graph.sources
    assert not any("storage_service.c" in source for source in graph.sources)
    assert not any("log_sink_service.c" in source for source in graph.sources)
    validation = Project_Validate(model, builtin_catalog)
    assert any(issue.code == "log_sink_cardinality" for issue in validation.issues)
    assert any(issue.code == "protocol_transport" for issue in validation.issues)


def test_two_physical_log_sinks_are_rejected(builtin_catalog) -> None:
    model = ReferenceProject_Create("TwoStorage", catalog=builtin_catalog)
    model.device_instances.append(DeviceInstance("storage1", STORAGE_PLUGIN))
    validation = Project_Validate(model, builtin_catalog)
    cardinality = [
        issue
        for issue in validation.issues
        if issue.code == "log_sink_cardinality"
    ]
    assert cardinality
    assert "storage0" in cardinality[0].message
    assert "storage1" in cardinality[0].message


def test_format9_storage_migration_is_deterministic_and_idempotent(
    builtin_catalog,
) -> None:
    data = ReferenceProject_Create("MigrateStorage", catalog=builtin_catalog).Dictionary_Get()
    data["format_version"] = 9
    data["components"]["devices"] = [
        item for item in data["components"]["devices"] if item["plugin"] != STORAGE_PLUGIN
    ]
    data["resources"].pop("storage0:storage")
    data["resources"].pop("storage0:time")
    data["resources"][f"{BOARD_PLUGIN}:storage"] = "PLATFORM_SDIO_1"
    data["generated_glue"].remove("project_storage_binding")

    migrated = ProjectModel_Parse(data)
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert [
        instance.instance_id
        for instance in migrated.device_instances
        if instance.plugin == STORAGE_PLUGIN
    ] == ["storage0"]
    assert migrated.resource_assignments["storage0:storage"] == "PLATFORM_SDIO_1"
    assert migrated.resource_assignments["storage0:time"] == "PLATFORM_TIME_1"
    assert "project_storage_binding" in migrated.generated_glue

    reparsed = ProjectModel_Parse(migrated.Dictionary_Get())
    assert reparsed.Dictionary_Get() == migrated.Dictionary_Get()
    unknown = migrated.Dictionary_Get()
    unknown["format_version"] = PROJECT_FORMAT_VERSION + 1
    with pytest.raises(ProjectModelError, match="Only project format_version"):
        ProjectModel_Parse(unknown)


def test_format9_generated_project_adds_device_owned_storage_without_board_collision(
    tmp_path: Path, builtin_catalog
) -> None:
    project_root = tmp_path / "StorageOwnershipMigration"
    assembler = ProjectAssembler(WorkspacePolicy(tmp_path), builtin_catalog)
    model = ReferenceProject_Create("StorageOwnershipMigration", catalog=builtin_catalog)
    assembler.Apply(model, assembler.Plan(model, project_root))

    ownership_path = project_root / ".fccg" / "ownership.json"
    ownership = json.loads(ownership_path.read_text(encoding="utf-8"))
    storage_provenance = ownership["components"].pop(STORAGE_PLUGIN)
    ownership["active_components"].remove(STORAGE_PLUGIN)
    board_provenance = ownership["components"][BOARD_PLUGIN]
    old_root = project_root / "Board" / "SilverStar_0_5" / "Services" / "Src"
    old_root.mkdir(parents=True, exist_ok=True)
    for name in ("storage_service.c", "log_sink_service.c"):
        new_relative = f"Devices/Storage/SdSdioFatFs/Src/{name}"
        new_path = project_root.joinpath(*new_relative.split("/"))
        old_path = old_root / name
        old_path.write_bytes(new_path.read_bytes())
        new_path.unlink()
        board_provenance["files"][
            f"Board/SilverStar_0_5/Services/Src/{name}"
        ] = storage_provenance["files"][new_relative]
    ownership_path.write_text(
        json.dumps(ownership, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    plan = assembler.Plan(model, project_root)
    assert plan.valid
    storage_operations = {
        operation.target: operation.operation
        for operation in plan.operations
        if operation.target.startswith("Devices/Storage/SdSdioFatFs/")
    }
    assert storage_operations == {
        "Devices/Storage/SdSdioFatFs/Src/log_sink_service.c": "ADD",
        "Devices/Storage/SdSdioFatFs/Src/storage_service.c": "ADD",
    }
    assert not any(
        operation.operation == "CONFLICT"
        and operation.target.startswith("Board/SilverStar_0_5/Services/")
        for operation in plan.operations
    )


class _CatalogOverlay:
    def __init__(self, base, manifests=()):
        self.base = base
        self.manifests = {manifest.component_id: manifest for manifest in manifests}

    def Component_Get(self, component_id: str):
        return self.manifests.get(component_id) or self.base.Component_Get(component_id)

    def Type_Get(self, component_type: str):
        overrides = tuple(
            manifest
            for manifest in self.manifests.values()
            if manifest.component_type == component_type
        )
        overridden_ids = {manifest.component_id for manifest in overrides}
        return (
            *overrides,
            *(
                manifest
                for manifest in self.base.Type_Get(component_type)
                if manifest.component_id not in overridden_ids
            ),
        )

    def __getattr__(self, name: str):
        return getattr(self.base, name)


class _FakeCubeMxImporter:
    def __init__(self, result: CubeMxImportResult):
        self.result = result
        self.keyword_arguments: dict[str, object] = {}

    def Project_Import(self, _path: Path, **keyword_arguments):
        self.keyword_arguments = dict(keyword_arguments)
        return self.result


def _ImportResultForPart_Get(builtin_catalog, part: str) -> CubeMxImportResult:
    board = builtin_catalog.Component_Get(BOARD_PLUGIN)
    inventory = BoardHardwareInventory_Get(board)
    assert inventory is not None
    if part.startswith("STM32H7"):
        inventory = replace(
            inventory,
            mcu_part=part,
            mcu_name="STM32H743ZITx",
            mcu_family="STM32H7",
            package="LQFP144",
            core="ARM Cortex-M7",
        )
    return CubeMxImportResult(
        hardware=HardwareConfiguration(),
        snapshot_root=Path("tests/.pytest-work/fake-cubemx"),
        peripherals=inventory.peripherals,
        warnings=(),
        inventory=inventory,
    )


def _H7Manifest_Get(builtin_catalog, component_id: str):
    official = builtin_catalog.Component_Get(MCU_PLUGIN)
    assert official.platform is not None
    rule = replace(
        official.platform.match_rules[0],
        exact_part="STM32H743ZIT6",
        family_pattern="",
        package_pattern="LQFP144",
        core_pattern="*M7*",
    )
    return replace(
        official,
        component_id=component_id,
        name="Fixture STM32H743ZIT6 Platform",
        metadata={
            **official.metadata,
            "mcu_model": "STM32H743ZIT6",
        },
        platform=replace(official.platform, match_rules=(rule,)),
    )


def test_custom_import_discovers_actual_mcu_before_platform_matching(
    workspace_root: Path, builtin_catalog
) -> None:
    service = FccgService(workspace_root)
    f407_importer = _FakeCubeMxImporter(
        _ImportResultForPart_Get(builtin_catalog, "STM32F407VET6")
    )
    service.hardware_importer = f407_importer
    service.CubeMxProject_Import(
        Path("unused-f407"),
        ReferenceProject_Create("HiddenDefault", catalog=builtin_catalog),
        risk_acknowledged=True,
    )
    assert "expected_mcu" not in f407_importer.keyword_arguments

    h7 = _H7Manifest_Get(builtin_catalog, "fixture.mcu.stm32h743zit6")
    service.catalog = _CatalogOverlay(builtin_catalog, (h7,))
    h7_importer = _FakeCubeMxImporter(
        _ImportResultForPart_Get(builtin_catalog, "STM32H743ZIT6")
    )
    service.hardware_importer = h7_importer
    result = service.CubeMxProject_Import(
        Path("unused-h7"),
        ReferenceProject_Create("StillDefaultsF407", catalog=builtin_catalog),
        risk_acknowledged=True,
    )
    assert result.inventory.mcu_part == "STM32H743ZIT6"
    assert "expected_mcu" not in h7_importer.keyword_arguments

    service.catalog = builtin_catalog
    with pytest.raises(PlatformMatchError, match="no compatible"):
        service.CubeMxProject_Import(
            Path("missing-h7-platform"),
            ReferenceProject_Create("MissingH7", catalog=builtin_catalog),
            risk_acknowledged=True,
        )

    duplicate = replace(
        h7,
        component_id="fixture.mcu.stm32h743zit6_duplicate",
        name="Duplicate H7 Platform",
    )
    service.catalog = _CatalogOverlay(builtin_catalog, (h7, duplicate))
    with pytest.raises(PlatformMatchError, match="ambiguous"):
        service.CubeMxProject_Import(
            Path("ambiguous-h7-platform"),
            ReferenceProject_Create("AmbiguousH7", catalog=builtin_catalog),
            risk_acknowledged=True,
        )


def test_known_board_still_enforces_compatible_mcu(builtin_catalog) -> None:
    board = builtin_catalog.Component_Get(BOARD_PLUGIN)
    assert board.board is not None
    incompatible_board = replace(
        board,
        board=replace(
            board.board,
            compatible_mcus=("fixture.mcu.stm32h743zit6",),
        ),
    )
    catalog = _CatalogOverlay(builtin_catalog, (incompatible_board,))
    model = ReferenceProject_Create("BoardMcuGuard", catalog=builtin_catalog)
    validation = Project_Validate(model, catalog)
    assert any(issue.code == "board_mcu" for issue in validation.issues)
