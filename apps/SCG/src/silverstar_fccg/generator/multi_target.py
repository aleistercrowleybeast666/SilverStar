from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from silverstar_fccg.app.version import __version__
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import GenerationProgressCallback, ProjectAssembler
from silverstar_fccg.generator.ground_environment import GroundEnvironmentFiles_Render
from silverstar_fccg.generator.eide_ownership import EideOwnedFields_Merge, EideOwnedFields_Normalize
from silverstar_fccg.generator.ground_radio import GroundRadioConfig_Render, GroundRadioAirHeader_Render
from silverstar_fccg.generator.render import (
    AirLinkHeader_Render,
    _InstanceResourcesSource_Render,
    _PlatformResources_Render,
    _ResourceHeader_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.folder_contract import (
    FLIGHT_DIRECTORY,
    GROUND_DIRECTORY,
    PROJECT_FILENAME,
    ProjectRoot_Save,
)
from silverstar_fccg.project.model import (
    DeviceInstance,
    ProjectModel,
    ProjectModel_Load,
    GroundRadioConfigurations_Get,
)

GROUND_CORE_ID = "silverstar.core.ground.0_1_0"
GROUND_OWNERSHIP_FILE = ".silverstar-ground-ownership.json"


class TargetScope(StrEnum):
    FLIGHT = "flight"
    GROUND = "ground"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class TargetGenerationResult:
    project_root: Path
    targets: tuple[str, ...]
    file_hashes: dict[str, str]


def _PayloadFiles_Add(files: dict[str, bytes], manifest, *, skip_adapter: bool = False) -> None:
    for source in manifest.PayloadFiles_Get():
        relative = source.relative_to(manifest.payload_root).as_posix()
        if skip_adapter and relative.startswith("Devices/Telemetry/") and "/Adapter/" in relative:
            continue
        content = source.read_bytes()
        previous = files.setdefault(relative, content)
        if previous != content:
            raise ValueError(f"Ground source collision: {relative}")


def _GroundModel_Get(model: ProjectModel, catalog: PluginCatalog) -> ProjectModel:
    ground = model.ground_target
    mcu_family = str(
        catalog.Component_Get(ground.mcu).metadata.get("platform_family_id", "")
    )
    if not mcu_family:
        raise ValueError("Ground exact MCU does not declare a family backend")
    return replace(
        model, core=GROUND_CORE_ID, mcu_family=mcu_family,
        mcu=ground.mcu, board=ground.board, os="",
        device_instances=[DeviceInstance(radio.instance_id, radio.plugin,
                          module_variant=radio.module_variant, tx_power_dbm=radio.tx_power_dbm)
                          for radio in GroundRadioConfigurations_Get(ground)],
        base_components=[], strategies={}, modes={}, protocols={
            "telemetry": None, "maintenance": None, "logging": None,
        }, development_environment="", hardware=ground.hardware,
        resource_assignments=dict(ground.resource_assignments),
        capability_source_overrides={}, logging_streams=[],
        build=ground.build,
    )


def _UserSection_Insert(source: str, section: str, insertion: str, *, empty: bool) -> str:
    start = f"/* USER CODE BEGIN {section} */"
    end = f"/* USER CODE END {section} */"
    pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)
    match = pattern.search(source)
    if match is None:
        raise ValueError(f"CubeMX main.c lacks USER CODE section {section}")
    if empty and match.group(1).strip():
        raise ValueError(f"Ground CubeMX main.c USER CODE {section} already owns application code")
    existing = match.group(1).strip("\r\n") if not empty else ""
    body = "\n".join(part for part in (existing, insertion) if part)
    return source[:match.start()] + start + "\n" + body + "\n" + end + source[match.end():]


def _Main_Integrate(content: bytes, *, usb: bool = False) -> bytes:
    source = content.decode("utf-8-sig")
    source = _UserSection_Insert(source, "Includes", '#include "ground_bridge.h"', empty=True)
    if usb:
        source = _UserSection_Insert(source, "Includes", '#include "pc_byte_stream.h"', empty=False)
    source = _UserSection_Insert(
        source, "2", "  if (GroundBridge_Init() != GROUND_BRIDGE_OK) { Error_Handler(); }",
        empty=True,
    )
    section = re.search(
        r"/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/",
        source, re.DOTALL,
    )
    if section is None or section.group(1).strip() != "}":
        raise ValueError("Ground CubeMX main.c USER CODE 3 has unsupported application code")
    source = source.replace(
        "/* USER CODE BEGIN 3 */",
        "/* USER CODE BEGIN 3 */\n    (void)GroundBridge_Process(HAL_GetTick());",
        1,
    )
    return source.encode("utf-8")


def _VerifiedBoardMain_Prepare(content: bytes, board) -> bytes:
    if (
        board.source == "builtin"
        and board.board is not None
        and board.board.verified
        and board.metadata.get("ground_entry") == "clean_cubemx_main"
    ):
        return content
    if board.component_id != "silverstar.board.silverstar_0_5":
        raise ValueError("Ground board application entry is not verified for this board")
    source = content.decode("utf-8-sig")
    expected = (
        "SystemStartup_Run()", "AppTasks_Init()", "vTaskStartScheduler()",
        "/* USER CODE BEGIN 2 */", "/* USER CODE BEGIN Includes */",
    )
    if not all(token in source for token in expected):
        raise ValueError("Verified board main.c differs from the reviewed Flight entry")
    for section in ("Includes", "2"):
        source = _UserSection_Insert(source, section, "", empty=False)
        section_pattern = re.compile(
            re.escape(f"/* USER CODE BEGIN {section} */") + r".*?" +
            re.escape(f"/* USER CODE END {section} */"), re.DOTALL,
        )
        source = section_pattern.sub(
            f"/* USER CODE BEGIN {section} */\n/* USER CODE END {section} */",
            source, count=1,
        )
    task_block = re.compile(
        r"  /\* Initialize the statically allocated SilverStar tasks.*?"
        r"  /\* Infinite loop \*/", re.DOTALL,
    )
    if len(task_block.findall(source)) != 1:
        raise ValueError("Verified board Flight task entry was not found exactly once")
    source = task_block.sub("  /* Infinite loop */", source, count=1)
    if '#include "fatfs.h"' not in source or "MX_FATFS_Init();" not in source:
        raise ValueError("Verified board FATFS initialization differs from reviewed source")
    source = re.sub(r'(?m)^#include "fatfs\.h"\r?\n', "", source, count=1)
    source = re.sub(r"(?m)^  MX_FATFS_Init\(\);\r?\n", "", source, count=1)
    return source.encode("utf-8")


def _UsbCallback_Integrate(content: bytes) -> bytes:
    source = content.decode("utf-8-sig")
    source = _UserSection_Insert(
        source, "INCLUDES", '#include "pc_byte_stream.h"', empty=False
    ) if "/* USER CODE BEGIN INCLUDES */" in source else source.replace(
        '#include "usbd_cdc_if.h"', '#include "usbd_cdc_if.h"\n#include "pc_byte_stream.h"', 1
    )
    marker = "/* USER CODE BEGIN 6 */"
    if marker not in source or "CDC_Receive_FS" not in source:
        raise ValueError("CubeMX USB CDC callback lacks a supported receive hook")
    source = source.replace(marker, marker + "\n  PcByteStream_OnUsbReceive(Buf, (uint16_t)*Len);", 1)
    for section in ("3", "4"):
        # Init/DeInit exist in both old and new classic CDC templates. Refuse
        # an unfamiliar template instead of silently losing lifecycle handling.
        if f"/* USER CODE BEGIN {section} */" not in source:
            raise ValueError("CubeMX USB CDC callback lacks a supported Init/DeInit hook")
        marker = f"/* USER CODE BEGIN {section} */"
        source = source.replace(marker, marker + "\n  PcByteStream_OnUsbReset();", 1)
    return source.encode("utf-8")


def _UsbConf_Integrate(content: bytes) -> bytes:
    source = content.decode("utf-8-sig")
    source = _UserSection_Insert(source, "Includes", '#include "pc_byte_stream.h"', empty=False)
    for event in ("Reset", "DevDisconnected"):
        pattern = r"(?m)^([ \t]*USBD_LL_" + event + r"\([^\n]+\);)[ \t]*\r?$"
        source, count = re.subn(pattern, r"\1\n  PcByteStream_OnUsbReset();", source)
        if count != 1:
            raise ValueError(f"CubeMX USB configuration lacks one classic {event} lifecycle call")
    return source.encode("utf-8")


def _PcAdapter_Render(model: ProjectModel, family=None) -> str:
    ground = model.ground_target
    if ground.pc_interface == "uart":
        resources = {resource.resource_id: resource for resource in ground.hardware.resources}
        handle = str(resources[ground.pc_resource].metadata.get("handle", ""))
        if re.fullmatch(r"huart[0-9]+", handle) is None:
            raise ValueError("Ground UART handle is unavailable from CubeMX inventory")
        dma = resources[ground.pc_resource].metadata.get("dma", ())
        dma_directions = {
            str(item.get("direction", ""))
            for item in dma if isinstance(item, dict)
        }
        if (
            family is not None
            and family.metadata.get("pc_uart_dma_adapter") == "stm32_hal_receive_to_idle"
            and {"DMA_PERIPH_TO_MEMORY", "DMA_MEMORY_TO_PERIPH"}.issubset(dma_directions)
        ):
            from silverstar_fccg.generator.ground_pc_uart_dma import PcUartDma_Render
            from silverstar_fccg.generator.ground_pc_session_uart import PcUartSession_Render
            return PcUartDma_Render(handle) + PcUartSession_Render()
        from silverstar_fccg.generator.ground_pc_session_uart import PcUartSession_Render
        return f"""#include "pc_byte_stream.h"
#include "main.h"
#include <stddef.h>

extern UART_HandleTypeDef {handle};

PcByteStreamInitResult PcByteStream_Init(void)
{{
    return PC_BYTE_STREAM_INIT_OK;
}}

uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{{
    if ((buffer == NULL) || (capacity == 0U)) {{ return 0U; }}
    return (HAL_UART_Receive(&{handle}, buffer, 1U, 0U) == HAL_OK) ? 1U : 0U;
}}

PcByteStreamWriteResult PcByteStream_Write(const uint8_t *data,
                                          uint16_t length)
{{
    HAL_StatusTypeDef result;
    if ((data == NULL) || (length == 0U))
    {{ return PC_BYTE_STREAM_WRITE_ERROR; }}
    result = HAL_UART_Transmit(&{handle},
        (uint8_t *)(uintptr_t)data, length, 100U);
    if (result == HAL_BUSY) {{ return PC_BYTE_STREAM_WRITE_BUSY; }}
    return (result == HAL_OK) ? PC_BYTE_STREAM_WRITE_OK :
        PC_BYTE_STREAM_WRITE_ERROR;
}}

uint32_t PcByteStream_OverflowCount_Get(void)
{{
    return 0U;
}}
""" + PcUartSession_Render()
    from silverstar_fccg.generator.ground_pc_usb_cdc import PcUsbCdc_Render
    return PcUsbCdc_Render()


def _Makefile_Render(
    sources: tuple[str, ...], asm_sources: tuple[str, ...],
    includes: tuple[str, ...], defines: tuple[str, ...], graph,
    toolchain_prefix: str,
) -> str:
    flags = " ".join(graph.mcu_flags)
    source_lines = " \\\n  ".join(sources)
    asm_lines = " \\\n  ".join(asm_sources)
    include_flags = " ".join(f"-I{path}" for path in includes)
    define_flags = " ".join(f"-D{value}" for value in defines)
    linker = graph.linker_script
    return f"""# Generated Ground target; source graph is Generated/ground_source_graph.json.
CC := {toolchain_prefix}gcc
unexport CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH DEPENDENCIES_OUTPUT SUNPRO_DEPENDENCIES
OBJCOPY := {toolchain_prefix}objcopy
SIZE := {toolchain_prefix}size
PYTHON ?= python
HOST_CC ?= gcc
ANALYZE ?= 0
BUILD_DIR := build
ifeq ($(ANALYZE),1)
BUILD_DIR := build/analysis
ANALYZER_FLAGS := -fanalyzer
endif
C_SOURCES := {source_lines}
ASM_SOURCES := {asm_lines}
FIRST_PARTY_C_SOURCES := $(filter Common/% Devices/% Generated/% Ground/% Platform/%,$(C_SOURCES))
VENDOR_C_SOURCES := $(filter Core/% Drivers/% HardwareGenerated/% Middlewares/%,$(C_SOURCES))
CLASSIFIED_C_SOURCES := $(FIRST_PARTY_C_SOURCES) $(VENDOR_C_SOURCES)
ifneq ($(words $(C_SOURCES)),$(words $(CLASSIFIED_C_SOURCES)))
$(error Ground compiler policy does not classify every C source)
endif
OBJECTS := $(patsubst %.c,$(BUILD_DIR)/%.o,$(C_SOURCES)) $(patsubst %.s,$(BUILD_DIR)/%.o,$(ASM_SOURCES))
FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror \\
  -Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 \\
  -Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes \\
  -Wmissing-prototypes -Wswitch-enum -Wvla $(ANALYZER_FLAGS)
VENDOR_WARNINGS := -Wall -Werror=implicit-function-declaration \\
  -Werror=incompatible-pointer-types -Werror=return-type
CFLAGS := -std=c11 -Os -ffunction-sections -fdata-sections -fstack-usage -Wvla -Werror=vla {flags} {include_flags} {define_flags}
LDFLAGS := {flags} -Wl,--gc-sections,-Map=$(BUILD_DIR)/ground.map -T{linker} -specs=nano.specs -lc -lm -lnosys

ifeq ($(OS),Windows_NT)
MKDIR_P = if not exist "$(dir $@)" mkdir "$(dir $@)"
else
MKDIR_P = mkdir -p "$(dir $@)"
endif

all: $(BUILD_DIR)/ground.elf $(BUILD_DIR)/ground.bin $(BUILD_DIR)/ground.size

.PHONY: all architecture-check host-tests artifact-check power10-check static-analysis

static-analysis:
\t$(MAKE) ANALYZE=1 all

architecture-check:
\t$(PYTHON) Tools/check_ground.py architecture

host-tests:
\t$(PYTHON) Tools/check_ground.py host --host-cc "$(HOST_CC)"

artifact-check: all
\t$(PYTHON) Tools/check_ground.py artifact --prefix "{toolchain_prefix}"

power10-check:
\tpowershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1 -TargetKind Ground

$(BUILD_DIR)/ground.elf: $(OBJECTS)
\t$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/ground.bin: $(BUILD_DIR)/ground.elf
\t$(OBJCOPY) -O binary $< $@

$(BUILD_DIR)/ground.size: $(BUILD_DIR)/ground.elf
\t$(SIZE) $< > $@

$(BUILD_DIR)/%.o: %.c
\t@$(MKDIR_P)
\t$(CC) $(CFLAGS) $(if $(filter $<,$(FIRST_PARTY_C_SOURCES)),$(FIRST_PARTY_WARNINGS),$(VENDOR_WARNINGS)) -MD -MP -c $< -o $@

$(BUILD_DIR)/%.o: %.s
\t@$(MKDIR_P)
\t$(CC) $(CFLAGS) -MD -MP -x assembler-with-cpp -c $< -o $@

-include $(OBJECTS:.o=.d)
"""


def GroundFiles_Render(
    model: ProjectModel, catalog: PluginCatalog, internal_policy: WorkspacePolicy,
) -> dict[str, bytes]:
    issues = GroundTargetIssues_Get(model, catalog)
    if issues:
        raise ValueError("; ".join(f"{issue.code}: {issue.message}" for issue in issues))
    ground = model.ground_target
    ground_model = _GroundModel_Get(model, catalog)
    catalog = catalog.ProjectView_Get(ground_model)
    core = catalog.Component_Get(GROUND_CORE_ID)
    radio = catalog.Component_Get(ground.radio_plugin)
    mcu = catalog.Component_Get(ground.mcu)
    files: dict[str, bytes] = {}
    _PayloadFiles_Add(files, core)
    nrf24 = model.air_link.radio_family == "nrf24"
    backend_adapters = core.metadata.get("ground_radio_backends", {})
    if set(backend_adapters) != {"sx128x", "nrf24"}:
        raise ValueError("Ground core must declare both supported backend adapters")
    for path in backend_adapters.values():
        if not isinstance(path, str) or not path.startswith("Ground/Radio/Src/") or ".." in path.split("/") or path not in files:
            raise ValueError("Ground backend adapter must be an owned declared payload")
    radio_adapter = backend_adapters[model.air_link.radio_family]
    for backend, path in backend_adapters.items():
        if backend != model.air_link.radio_family:
            files.pop(path)
    _PayloadFiles_Add(files, radio, skip_adapter=True)
    family = catalog.Component_Get(ground_model.mcu_family)
    platform_api = catalog.Component_Get("silverstar.platform.api")
    for owner in (platform_api, family, mcu):
        for source in owner.PayloadFiles_Get():
            relative = source.relative_to(owner.payload_root).as_posix()
            if (ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative"
                    and (relative.startswith(("Drivers/", "Middlewares/"))
                         or relative in {mcu.build.linker_script, *mcu.build.asm_sources})):
                continue
            if relative.startswith(("Middlewares/Third_Party/FatFs/", "FATFS/")):
                continue
            if relative.startswith(("Platform/", "Drivers/", "BuildSystem/", "Middlewares/")) or relative in {
                mcu.build.linker_script, *mcu.build.asm_sources,
            }:
                files[relative] = source.read_bytes()
    flight_core = catalog.Component_Get(model.core)
    for relative in (
        "Common/Inc/silverstar_assert.h", "Common/Inc/silverstar_compiler.h",
        "Common/Src/silverstar_assert.c", "Interfaces/Inc/system_device_types.h",
        "Tools/check_power_of_ten.ps1",
    ):
        files[relative] = (flight_core.payload_root / relative).read_bytes()
    if ground.hardware.mode == "board_plugin":
        board = catalog.Component_Get(ground.board)
        for source in board.PayloadFiles_Get():
            relative = source.relative_to(board.payload_root).as_posix()
            if not relative.startswith("FATFS/"):
                files[relative] = source.read_bytes()
    else:
        assembler = ProjectAssembler(internal_policy, catalog)
        files.update(assembler._HardwareFiles_Get(ground_model))

    main_path = "Core/Src/main.c" if ground.hardware.mode == "board_plugin" else \
        "HardwareGenerated/STM32CubeMX/Core/Src/main.c"
    if main_path not in files:
        raise ValueError("Ground CubeMX hardware has no generated Core/Src/main.c")
    if ground.hardware.mode == "board_plugin":
        files[main_path] = _VerifiedBoardMain_Prepare(
            files[main_path], catalog.Component_Get(ground.board)
        )
    files[main_path] = _Main_Integrate(files[main_path], usb=ground.pc_interface == "usb_cdc")
    if ground.pc_interface == "usb_cdc":
        callback_paths = [path for path in files if path.endswith("/usbd_cdc_if.c")]
        if len(callback_paths) != 1:
            raise ValueError("Ground CubeMX hardware has no unique usbd_cdc_if.c")
        files[callback_paths[0]] = _UsbCallback_Integrate(files[callback_paths[0]])
        conf_paths = [path for path in files if path.endswith("/usbd_conf.c")]
        if len(conf_paths) != 1:
            raise ValueError("Ground CubeMX hardware has no unique usbd_conf.c")
        files[conf_paths[0]] = _UsbConf_Integrate(files[conf_paths[0]])

    files["Generated/Inc/project_resources.h"] = _ResourceHeader_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/project_resources.c"] = _InstanceResourcesSource_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/platform_resources.c"] = _PlatformResources_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Inc/ground_radio_config.h"] = GroundRadioConfig_Render(ground).encode("utf-8")
    files["Generated/Inc/air_link_config.h"] = GroundRadioAirHeader_Render(
        ground, AirLinkHeader_Render(model, target="ground")).encode("utf-8")
    files["Generated/Src/pc_byte_stream.c"] = _PcAdapter_Render(model, family).encode("utf-8")

    base_graph = SourceGraph_Resolve(ground_model, catalog)
    sources = tuple(dict.fromkeys([
        *(source for source in base_graph.sources
          if not source.startswith(("Generated/", "FATFS/", "Middlewares/Third_Party/FatFs/"))
          and "/Adapter/" not in source and (not nrf24 or source != backend_adapters["sx128x"])),
        *([radio_adapter] if nrf24 else []),
        "Common/Src/silverstar_assert.c", "Generated/Src/project_resources.c",
        "Generated/Src/platform_resources.c", "Generated/Src/pc_byte_stream.c",
        main_path,
    ]))
    includes = tuple(dict.fromkeys([
        *(path for path in base_graph.include_dirs
          if "/Adapter/" not in path and not path.startswith(("FATFS/", "Middlewares/Third_Party/FatFs/"))),
        "Generated/Inc", "Common/Inc", "Interfaces/Inc", "Platform/Inc",
    ]))
    defines = tuple(dict.fromkeys([
        "SILVERSTAR_AIR_LINK_ENABLED=1", *base_graph.defines,
        # Ground transfers bounded AIR frames; the established HAL option still
        # accommodates a full 255-byte radio payload plus its command header.
        "AIR_LINK_HAL_BUFFER_SIZE=260",
    ]))
    if ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative":
        from silverstar_fccg.hardware.cubemx_ground import GroundEffectiveDefinitions_Validate
        GroundEffectiveDefinitions_Validate(defines, ground.hardware.mcu)
    missing_sources = [source for source in sources if source not in files]
    if missing_sources:
        raise ValueError("Ground source graph has missing files: " + ", ".join(missing_sources))
    required_irqs = ground.hardware.inventory.get("ground_cubemx_base", {}).get("required_irq_handlers", [])
    if ground.pc_interface == "usb_cdc":
        required_irqs = list(dict.fromkeys([*required_irqs,
            "USB_LP_CAN1_RX0_IRQHandler" if family.component_id.endswith("stm32f1") else "OTG_FS_IRQHandler"]))
    graph = {
        "sources": sources, "asm_sources": base_graph.asm_sources,
        "include_dirs": includes, "defines": defines,
        "linker_script": base_graph.linker_script,
        "required_irq_handlers": required_irqs,
        "mcu_flags": base_graph.mcu_flags,
        "complete_cube_import": ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative",
    }
    files["Generated/ground_source_graph.json"] = (
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    files["Makefile"] = _Makefile_Render(
        sources, base_graph.asm_sources, includes, defines, base_graph,
        ground.build.toolchain_prefix or base_graph.toolchain_prefix,
    ).encode("utf-8")
    files[f"{GROUND_DIRECTORY}.code-workspace"] = (
        json.dumps({
            "folders": [{"path": "."}],
            "settings": {},
            "tasks": {
                "version": "2.0.0",
                "tasks": [{
                    "label": "Build Ground Station",
                    "type": "shell",
                    "command": ground.build.make_command,
                    "args": [],
                    "group": "build",
                }],
            },
        }, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    files.update(GroundEnvironmentFiles_Render(ground_model, catalog, base_graph, sources, includes, defines))
    hardware_fingerprint = ground.hardware.snapshot_id or ground.hardware.source_digest
    if ground.hardware.mode == "board_plugin" and not hardware_fingerprint:
        board_reference = catalog.Component_Get(ground.board).metadata.get("reference", {})
        hardware_fingerprint = str(
            board_reference.get("snapshot_digest") or
            catalog.Component_Get(ground.board).ManifestSha256_Get()
        )
    metadata = {
        "silverstar_version": __version__,
        "firmware_version": model.identity.firmware_version,
        "target_role": "ground_station",
        "air_profile": model.air_link.protocol_profile,
        "radio_module": ground.module_variant,
        "radio_family": model.air_link.radio_family,
        "frequency_hz": model.air_link.frequency_hz,
        "phy": {
            "mode": model.air_link.phy_mode,
            "spreading_factor": model.air_link.spreading_factor,
            "bandwidth_hz": model.air_link.bandwidth_hz,
            "coding_rate": model.air_link.coding_rate,
        },
        "pc_interface": ground.pc_interface,
        "hardware_fingerprint": hardware_fingerprint,
    }
    if nrf24:
        metadata["phy"] = {"mode": "esb", **model.air_link.nrf24,
            "physical_mtu": 32, "logical_mtu": model.air_link.packet_mtu,
            "fragment_version": 1, "metrics_supported": False}
    files["Generated/ground_target_metadata.json"] = (
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return files


def TargetGeneration_Apply(
    model: ProjectModel, catalog: PluginCatalog, internal_policy: WorkspacePolicy,
    project_root: Path, scope: TargetScope, *, confirm_dangerous: bool = False,
    progress_callback: GenerationProgressCallback | None = None,
) -> TargetGenerationResult:
    output_policy = WorkspacePolicy(project_root)
    root = output_policy.root
    project_file = root / PROJECT_FILENAME
    if project_file.exists() and ProjectModel_Load(project_file).identity.name != model.identity.name:
        raise ValueError("Top-level project belongs to another SilverStar project")
    targets: list[str] = []
    ground_previous_hashes: dict[str, str] = {}
    ground_stale: list[str] = []
    total = (7 if scope in (TargetScope.FLIGHT, TargetScope.ALL) else 0) + (2 if scope in (TargetScope.GROUND, TargetScope.ALL) else 0) + 1
    offset = 0
    def report(current: int, subject: str, done: bool) -> None:
        if progress_callback is not None:
            progress_callback(current, total, subject, done)
    if scope in (TargetScope.GROUND, TargetScope.ALL):
        if not model.ground_target.enabled:
            raise ValueError("Ground target is disabled")
        report(1, "ground_environment", False)
        ground_files = GroundFiles_Render(model, catalog, internal_policy)
        ground_root = output_policy.Path_Resolve(root / GROUND_DIRECTORY, allow_root=False)
        ownership_file = ground_root / GROUND_OWNERSHIP_FILE
        ownership = {}
        if ownership_file.is_file():
            ownership = json.loads(ownership_file.read_text(encoding="utf-8"))
            if ownership.get("format_version") != 1 or not isinstance(ownership.get("files"), dict):
                raise ValueError("Ground output ownership metadata is invalid")
            ground_previous_hashes = ownership["files"]
        eide_path = ground_root / ".eide/eide.yml"
        if eide_path.is_file():
            current_eide = eide_path.read_text(encoding="utf8")
            desired_eide = ground_files[".eide/eide.yml"].decode("utf8")
            current_fields = EideOwnedFields_Normalize(current_eide)
            desired_fields = EideOwnedFields_Normalize(desired_eide)
            previous_fields = ownership.get("eide", {}).get("owned_fields", desired_fields)
            if current_fields != previous_fields:
                raise ValueError(f"Ground EIDE build-owned fields have local changes: {eide_path}")
            ground_files[".eide/eide.yml"] = (eide_path.read_bytes() if current_fields == desired_fields
                else EideOwnedFields_Merge(current_eide, desired_eide).encode("utf8"))
        for relative, content in ground_files.items():
            destination = output_policy.Path_Resolve(
                ground_root.joinpath(*relative.split("/")), allow_root=False
            )
            if destination.exists():
                if not destination.is_file():
                    raise ValueError(f"Ground output is not a file: {destination}")
                current_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
                if relative != ".eide/eide.yml" and current_hash != hashlib.sha256(content).hexdigest() and current_hash != ground_previous_hashes.get(relative):
                    raise ValueError(f"Ground output has local changes: {destination}")
        for relative, expected_hash in ground_previous_hashes.items():
            if relative in ground_files:
                continue
            destination = output_policy.Path_Resolve(
                ground_root.joinpath(*relative.split("/")), allow_root=False
            )
            if destination.is_file():
                if hashlib.sha256(destination.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError(f"Stale Ground output has local changes: {destination}")
                ground_stale.append(relative)
        report(1, "ground_environment", True)
        offset = 1
    if scope in (TargetScope.FLIGHT, TargetScope.ALL):
        flight_root = output_policy.Path_Resolve(root / FLIGHT_DIRECTORY, allow_root=False)
        assembler = ProjectAssembler(internal_policy, catalog, output_policy)
        flight_model = (
            replace(model, ground_target=replace(model.ground_target, enabled=False))
            if scope == TargetScope.FLIGHT
            and GroundTargetIssues_Get(model, catalog) else model
        )
        plan = assembler.Plan(flight_model, flight_root)
        if not plan.valid or (plan.dangerous and not confirm_dangerous):
            raise ValueError("Flight generation plan is invalid or needs user review")
        assembler.Apply(flight_model, plan, confirm_dangerous=confirm_dangerous,
            progress_callback=lambda current, _total, subject, done: report(offset + current, subject, done))
        offset += 7
        flight_descriptor = ProjectModel_Load(flight_root / PROJECT_FILENAME)
        model.log_decoder_profile = flight_descriptor.log_decoder_profile
        decoder = flight_root / f"{model.identity.name}.ssdecoder"
        root_decoder = root / decoder.name
        if decoder.is_file():
            output_policy.Bytes_AtomicWrite(root_decoder, decoder.read_bytes())
        elif root_decoder.is_file():
            root_decoder.unlink()
        targets.append(FLIGHT_DIRECTORY)
    if scope in (TargetScope.GROUND, TargetScope.ALL):
        report(offset + 1, "ground_files", False)
        for relative in ground_stale:
            output_policy.Path_Resolve(
                ground_root.joinpath(*relative.split("/")), allow_root=False
            ).unlink()
        for relative, content in sorted(ground_files.items()):
            destination = ground_root.joinpath(*relative.split("/"))
            if not destination.is_file() or destination.read_bytes() != content:
                output_policy.Bytes_AtomicWrite(destination, content)
        output_policy.Text_AtomicWrite(
            ground_root / GROUND_OWNERSHIP_FILE,
            json.dumps({
                "format_version": 1,
                "eide": {"owned_fields": EideOwnedFields_Normalize(ground_files[".eide/eide.yml"].decode("utf8"))},
                "files": {
                    relative: hashlib.sha256(content).hexdigest()
                    for relative, content in sorted(ground_files.items())
                },
            }, indent=2) + "\n",
        )
        targets.append(GROUND_DIRECTORY)
        report(offset + 1, "ground_files", True)
        offset += 1
    report(total, "project_descriptor", False)
    ProjectRoot_Save(model, root)
    report(total, "project_descriptor", True)
    hashes = {
        relative: hashlib.sha256(content).hexdigest()
        for relative, content in (ground_files.items() if GROUND_DIRECTORY in targets else ())
    }
    return TargetGenerationResult(root, tuple(targets), hashes)
