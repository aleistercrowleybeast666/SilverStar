from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from silverstar_fccg.app.version import __version__
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.render import (
    AirLinkHeader_Render,
    _InstanceResourcesSource_Render,
    _PlatformResources_Render,
    _ResourceHeader_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import DeviceInstance, ProjectModel, ProjectModel_Load
from silverstar_fccg.project.folder_contract import (
    FLIGHT_DIRECTORY, GROUND_DIRECTORY, PROJECT_FILENAME, ProjectRoot_Save,
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
        if skip_adapter and relative.startswith("Devices/Telemetry/SX1281/Adapter/"):
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
        device_instances=[DeviceInstance("radio0", ground.radio_plugin)],
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


def _Main_Integrate(content: bytes) -> bytes:
    source = content.decode("utf-8-sig")
    source = _UserSection_Insert(source, "Includes", '#include "ground_bridge.h"', empty=True)
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
    return source.encode("utf-8")


def _PcAdapter_Render(model: ProjectModel) -> str:
    ground = model.ground_target
    if ground.pc_interface == "uart":
        resources = {resource.resource_id: resource for resource in ground.hardware.resources}
        handle = str(resources[ground.pc_resource].metadata.get("handle", ""))
        if re.fullmatch(r"huart[0-9]+", handle) is None:
            raise ValueError("Ground UART handle is unavailable from CubeMX inventory")
        return f"""#include "pc_byte_stream.h"
#include "main.h"

extern UART_HandleTypeDef {handle};

uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{{
    if ((buffer == NULL) || (capacity == 0U)) {{ return 0U; }}
    return (HAL_UART_Receive(&{handle}, buffer, 1U, 0U) == HAL_OK) ? 1U : 0U;
}}

uint16_t PcByteStream_Write(const uint8_t *data, uint16_t length)
{{
    if ((data == NULL) || (length == 0U)) {{ return 0U; }}
    return (HAL_UART_Transmit(&{handle}, (uint8_t *)(uintptr_t)data, length, 100U)
            == HAL_OK) ? length : 0U;
}}

uint32_t PcByteStream_OverflowCount_Get(void)
{{
    return 0U;
}}
"""
    return """#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"

#define PC_USB_RX_CAPACITY 512U

static uint8_t s_rx_buffer[PC_USB_RX_CAPACITY];
static volatile uint16_t s_rx_head;
static volatile uint16_t s_rx_tail;
static volatile uint32_t s_rx_overflow_count;

void PcByteStream_OnUsbReceive(const uint8_t *data, uint16_t length)
{
    uint16_t index;
    if (data == NULL) { return; }
    for (index = 0U; index < length; index++)
    {
        uint16_t next = (uint16_t)((s_rx_head + 1U) % PC_USB_RX_CAPACITY);
        if (next == s_rx_tail)
        {
            s_rx_overflow_count += (uint32_t)(length - index);
            break;
        }
        s_rx_buffer[s_rx_head] = data[index];
        s_rx_head = next;
    }
}

uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{
    uint16_t count = 0U;
    if (buffer == NULL) { return 0U; }
    while ((count < capacity) && (s_rx_tail != s_rx_head))
    {
        buffer[count++] = s_rx_buffer[s_rx_tail];
        s_rx_tail = (uint16_t)((s_rx_tail + 1U) % PC_USB_RX_CAPACITY);
    }
    return count;
}

uint16_t PcByteStream_Write(const uint8_t *data, uint16_t length)
{
    uint8_t result;
    if ((data == NULL) || (length == 0U)) { return 0U; }
    result = CDC_Transmit_FS((uint8_t *)(uintptr_t)data, length);
    /* USBD_BUSY is transient: the bounded Ground PC queue retries this frame. */
    if (result == USBD_BUSY) { return 0U; }
    return (result == USBD_OK) ? length : 0U;
}

uint32_t PcByteStream_OverflowCount_Get(void)
{
    return s_rx_overflow_count;
}
"""


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
OBJCOPY := {toolchain_prefix}objcopy
SIZE := {toolchain_prefix}size
C_SOURCES := {source_lines}
ASM_SOURCES := {asm_lines}
OBJECTS := $(patsubst %.c,build/%.o,$(C_SOURCES)) $(patsubst %.s,build/%.o,$(ASM_SOURCES))
CFLAGS := -std=c11 -Os -ffunction-sections -fdata-sections -fstack-usage {flags} {include_flags} {define_flags}
LDFLAGS := {flags} -Wl,--gc-sections,-Map=build/ground.map -T{linker} -specs=nano.specs -lc -lm -lnosys

ifeq ($(OS),Windows_NT)
MKDIR_P = if not exist "$(dir $@)" mkdir "$(dir $@)"
else
MKDIR_P = mkdir -p "$(dir $@)"
endif

all: build/ground.elf build/ground.bin build/ground.size

build/ground.elf: $(OBJECTS)
\t$(CC) $(OBJECTS) $(LDFLAGS) -o $@

build/ground.bin: build/ground.elf
\t$(OBJCOPY) -O binary $< $@

build/ground.size: build/ground.elf
\t$(SIZE) $< > $@

build/%.o: %.c
\t@$(MKDIR_P)
\t$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

build/%.o: %.s
\t@$(MKDIR_P)
\t$(CC) $(CFLAGS) -x assembler-with-cpp -c $< -o $@

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
    core = catalog.Component_Get(GROUND_CORE_ID)
    radio = catalog.Component_Get(ground.radio_plugin)
    mcu = catalog.Component_Get(ground.mcu)
    files: dict[str, bytes] = {}
    _PayloadFiles_Add(files, core)
    _PayloadFiles_Add(files, radio, skip_adapter=True)
    family = catalog.Component_Get(ground_model.mcu_family)
    platform_api = catalog.Component_Get("silverstar.platform.api")
    for owner in (platform_api, family, mcu):
        for source in owner.PayloadFiles_Get():
            relative = source.relative_to(owner.payload_root).as_posix()
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
    files[main_path] = _Main_Integrate(files[main_path])
    if ground.pc_interface == "usb_cdc":
        callback_paths = [path for path in files if path.endswith("/usbd_cdc_if.c")]
        if len(callback_paths) != 1:
            raise ValueError("Ground CubeMX hardware has no unique usbd_cdc_if.c")
        files[callback_paths[0]] = _UsbCallback_Integrate(files[callback_paths[0]])

    files["Generated/Inc/project_resources.h"] = _ResourceHeader_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/project_resources.c"] = _InstanceResourcesSource_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Src/platform_resources.c"] = _PlatformResources_Render(
        ground_model, catalog
    ).encode("utf-8")
    files["Generated/Inc/air_link_config.h"] = AirLinkHeader_Render(model, target="ground").encode("utf-8")
    files["Generated/Src/pc_byte_stream.c"] = _PcAdapter_Render(model).encode("utf-8")

    base_graph = SourceGraph_Resolve(ground_model, catalog)
    sources = tuple(dict.fromkeys([
        *(source for source in base_graph.sources
          if not source.startswith(("Generated/", "FATFS/", "Middlewares/Third_Party/FatFs/"))
          and "/Adapter/" not in source),
        "Common/Src/silverstar_assert.c", "Generated/Src/project_resources.c",
        "Generated/Src/platform_resources.c", "Generated/Src/pc_byte_stream.c",
        main_path,
    ]))
    includes = tuple(dict.fromkeys([
        *base_graph.include_dirs,
        "Generated/Inc", "Common/Inc", "Interfaces/Inc", "Platform/Inc",
    ]))
    defines = tuple(dict.fromkeys([
        "SILVERSTAR_AIR_LINK_ENABLED=1", *base_graph.defines,
    ]))
    missing_sources = [source for source in sources if source not in files]
    if missing_sources:
        raise ValueError("Ground source graph has missing files: " + ", ".join(missing_sources))
    graph = {
        "sources": sources, "asm_sources": base_graph.asm_sources,
        "include_dirs": includes, "defines": defines,
        "linker_script": base_graph.linker_script,
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
    files["Generated/ground_target_metadata.json"] = (
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return files


def TargetGeneration_Apply(
    model: ProjectModel, catalog: PluginCatalog, internal_policy: WorkspacePolicy,
    project_root: Path, scope: TargetScope, *, confirm_dangerous: bool = False,
) -> TargetGenerationResult:
    output_policy = WorkspacePolicy(project_root)
    root = output_policy.root
    project_file = root / PROJECT_FILENAME
    if project_file.exists() and ProjectModel_Load(project_file).identity.name != model.identity.name:
        raise ValueError("Top-level project belongs to another SilverStar project")
    targets: list[str] = []
    ground_previous_hashes: dict[str, str] = {}
    ground_stale: list[str] = []
    if scope in (TargetScope.GROUND, TargetScope.ALL):
        if not model.ground_target.enabled:
            raise ValueError("Ground target is disabled")
        ground_files = GroundFiles_Render(model, catalog, internal_policy)
        ground_root = output_policy.Path_Resolve(root / GROUND_DIRECTORY, allow_root=False)
        ownership_file = ground_root / GROUND_OWNERSHIP_FILE
        if ownership_file.is_file():
            ownership = json.loads(ownership_file.read_text(encoding="utf-8"))
            if ownership.get("format_version") != 1 or not isinstance(ownership.get("files"), dict):
                raise ValueError("Ground output ownership metadata is invalid")
            ground_previous_hashes = ownership["files"]
        for relative, content in ground_files.items():
            destination = output_policy.Path_Resolve(
                ground_root.joinpath(*relative.split("/")), allow_root=False
            )
            if destination.exists():
                if not destination.is_file():
                    raise ValueError(f"Ground output is not a file: {destination}")
                current_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
                if current_hash != hashlib.sha256(content).hexdigest() and current_hash != ground_previous_hashes.get(relative):
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
        assembler.Apply(flight_model, plan, confirm_dangerous=confirm_dangerous)
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
                "files": {
                    relative: hashlib.sha256(content).hexdigest()
                    for relative, content in sorted(ground_files.items())
                },
            }, indent=2) + "\n",
        )
        targets.append(GROUND_DIRECTORY)
    ProjectRoot_Save(model, root)
    hashes = {
        relative: hashlib.sha256(content).hexdigest()
        for relative, content in (ground_files.items() if GROUND_DIRECTORY in targets else ())
    }
    return TargetGenerationResult(root, tuple(targets), hashes)
