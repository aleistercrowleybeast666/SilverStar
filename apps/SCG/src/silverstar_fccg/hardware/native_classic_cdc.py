"""Admission contract for complete native classic CDC projects.

This module never executes a native build recipe and never activates a runtime
adapter. Device facts are supplied by the trusted backend caller, independently
of the imported project. Import admission is not firmware acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from silverstar_fccg.hardware.cubemx import CubeMxImportError, CubeMxImporter, CubeMxImportResult
from silverstar_fccg.hardware.ground_dependencies import GroundDependencyDirectives_Validate
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.project.model import HardwareConfiguration, HardwareResource

NATIVE_CLASSIC_CDC_KEY = "native_complete_classic_cdc"
NATIVE_PREFIX = "HardwareGenerated/NativeClassicCdc/"


@dataclass(frozen=True, slots=True)
class NativeMemoryRegion:
    name: str
    origin: int
    length: int


@dataclass(frozen=True, slots=True)
class NativeDeviceFacts:
    """Reviewed independent facts, NOT a project-controlled sidecar assertion.

    The caller must establish trust in the descriptor source before calling
    this API. A URL/digest identifies evidence; it is not vendor authentication.
    More devices can supply this data without a handwritten MCU backend.
    """
    part: str
    core: str
    device_macro: str
    startup: str
    regions: tuple[NativeMemoryRegion, ...]
    evidence_source: str
    evidence_sha256: str
    fpu: str = ""

    def Facts_Validate(self) -> None:
        if not re.fullmatch(r"STM32[A-Z0-9]+", self.part):
            raise CubeMxImportError("Independent exact STM32 device facts are required")
        if self.core not in {"cortex-m0", "cortex-m0plus", "cortex-m3", "cortex-m4"}:
            raise CubeMxImportError("Unsupported single-core/cache-free CPU contract")
        if self.fpu not in {"", "fpv4-sp-d16"} or (self.fpu and self.core != "cortex-m4"):
            raise CubeMxImportError("Unsupported independent FPU facts")
        if not re.fullmatch(r"STM32[A-Za-z0-9]+", self.device_macro):
            raise CubeMxImportError("Invalid independent device macro")
        if not re.fullmatch(r"startup_stm32[a-z0-9]+\.s", self.startup):
            raise CubeMxImportError("Invalid independent startup identity")
        if not self.evidence_source or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_sha256):
            raise CubeMxImportError("Independent physical memory evidence is required; linker cannot self-prove it")
        if not self.regions or len({r.name for r in self.regions}) != len(self.regions):
            raise CubeMxImportError("Independent memory regions are missing or duplicated")
        for r in self.regions:
            if (not re.fullmatch(r"[A-Z][A-Z0-9_]*", r.name) or
                    type(r.origin) is not int or type(r.length) is not int or
                    r.origin < 0 or r.length <= 0 or r.origin + r.length > 0x100000000):
                raise CubeMxImportError("Invalid physical memory region")
        ranges = sorted((r.origin, r.origin + r.length) for r in self.regions)
        if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
            raise CubeMxImportError("Independent physical memory regions overlap")


def _Code_Get(text: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.S)


def _LiteralBuild_Get(root: Path, files: dict[str, bytes], facts: NativeDeviceFacts) -> dict:
    if "Makefile" not in files:
        raise CubeMxImportError("Complete classic CDC import requires its literal GNU Make inventory")
    logical = re.sub(r"\\\r?\n", " ", files["Makefile"].decode("utf-8-sig"))

    def values(name: str, *, optional: bool = False) -> tuple[str, ...]:
        assignments = re.findall(r"(?m)^[ \t]*(?:(?:override|export)[ \t]+)?" +
            re.escape(name) + r"[ \t]*([:+?]?=)", logical)
        matches = re.findall(r"(?m)^" + re.escape(name) + r"[ \t]*=[ \t]*([^\r\n]*)", logical)
        if not assignments and optional:
            return ()
        if assignments != ["="] or len(matches) != 1:
            raise CubeMxImportError("Native build needs one literal " + name)
        tokens = tuple(matches[0].split())
        if any(re.search(r"[$#;|&`\"'(){}]", t) for t in tokens) or len(set(tokens)) != len(tokens):
            raise CubeMxImportError("Native build has an expression or duplicate in " + name)
        return tokens

    def path(token: str, *, directory: bool = False) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", token) or any(p in {"", "..", "."} for p in token.split("/")):
            raise CubeMxImportError("Unsafe native build path: " + token)
        resolved = (root / token).resolve()
        if not resolved.is_relative_to(root) or not (resolved.is_dir() if directory else token in files):
            raise CubeMxImportError("Missing or escaping native build dependency: " + token)
        return token

    sources = tuple(path(p) for p in values("C_SOURCES"))
    allowed = ("Core/Src/", "USB_DEVICE/App/", "USB_DEVICE/Target/",
               "Middlewares/ST/STM32_USB_Device_Library/Core/Src/",
               "Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/")
    for source in sources:
        if not source.endswith(".c") or not (source.startswith(allowed) or
                re.fullmatch(r"Drivers/STM32[A-Z0-9a-z]+_HAL_Driver/Src/[A-Za-z0-9_]+\.c", source)):
            raise CubeMxImportError("Unknown native source/stack profile: " + source)
    if len({p.casefold() for p in sources}) != len(sources):
        raise CubeMxImportError("Native source aliases collide")
    assembly = tuple(path(p) for p in values("ASM_SOURCES"))
    if len(assembly) != 1 or Path(assembly[0]).name != facts.startup:
        raise CubeMxImportError("Native startup contradicts independent device facts")
    if len({str(Path(p).with_suffix('.o')).casefold() for p in (*sources, *assembly)}) != len(sources)+len(assembly):
        raise CubeMxImportError("Native C/assembler object paths collide")
    if values("ASMM_SOURCES", optional=True) or values("ASMMC_SOURCE", optional=True):
        raise CubeMxImportError("Unknown additional assembler source inventory")
    linker = values("LDSCRIPT")
    if len(linker) != 1 or not path(linker[0]).endswith(".ld"):
        raise CubeMxImportError("Native build needs one self-contained linker script")
    text = _Code_Get(files[linker[0]].decode("utf-8-sig"))
    memory_blocks = re.findall(r"\bMEMORY\s*\{([^{}]*)\}", text)
    region_pattern = r"(?m)^\s*(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*,\s*LENGTH\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*([KM]?)\s*$"
    if len(memory_blocks) != 1 or re.sub(region_pattern, "", memory_blocks[0]).strip():
        raise CubeMxImportError("Linker memory has unknown or nonliteral regions")
    regions = re.findall(region_pattern, memory_blocks[0])
    parsed = tuple(NativeMemoryRegion(n, int(o, 0), int(s, 0)*{"": 1, "K": 1024, "M": 1048576}[u]) for n, o, s, u in regions)
    if not parsed or {r.name: r for r in parsed} != {r.name: r for r in facts.regions} or len(parsed) != len(facts.regions):
        raise CubeMxImportError("Linker memory contradicts independent physical memory facts")
    cpu, fpu, abi = values("CPU"), values("FPU", optional=True), values("FLOAT-ABI", optional=True)
    if cpu != ("-mcpu=" + facts.core,):
        raise CubeMxImportError("Native CPU contradicts independent architecture facts")
    if facts.core == "cortex-m4":
        if (fpu, abi) not in {((), ()), ((), ("-mfloat-abi=soft",)),
                             (("-mfpu=fpv4-sp-d16",), ("-mfloat-abi=hard",)),
                             (("-mfpu=fpv4-sp-d16",), ("-mfloat-abi=softfp",))}:
            raise CubeMxImportError("Unsupported native M4 floating ABI")
        if fpu and fpu != ("-mfpu=" + facts.fpu,):
            raise CubeMxImportError("Native floating ABI contradicts independent FPU facts")
    elif fpu or abi not in {(), ("-mfloat-abi=soft",)}:
        raise CubeMxImportError("Native floating ABI contradicts its CPU")
    expected_mcu = {"$(CPU) -mthumb $(FPU) $(FLOAT-ABI)"}
    if not fpu and not abi:
        expected_mcu.add("$(CPU) -mthumb")
    if re.findall(r"(?m)^[ \t]*(?:(?:override|export)[ \t]+)?MCU[ \t]*([:+?]?=)", logical) != ["="]:
        raise CubeMxImportError("Native build needs one literal MCU flag expression")
    mcu_line = re.findall(r"(?m)^MCU\s*=\s*([^\r\n]+)", logical)
    if len(mcu_line) != 1 or mcu_line[0] not in expected_mcu:
        raise CubeMxImportError("Unknown native MCU flag expression")
    defs = values("C_DEFS")
    if set(defs) != {"-DUSE_HAL_DRIVER", "-D" + facts.device_macro} or values("AS_DEFS", optional=True):
        raise CubeMxImportError("Native effective definitions contradict device/adapter contract")
    inc = values("C_INCLUDES")
    if any(not v.startswith("-I") for v in inc):
        raise CubeMxImportError("Native include inventory must use literal -I paths")
    includes = tuple(path(v[2:], directory=True) for v in inc)
    if values("AS_INCLUDES", optional=True):
        raise CubeMxImportError("Unknown assembler include inventory")
    return {"sources": sources, "asm_sources": assembly, "include_dirs": includes,
            "defines": tuple(v[2:] for v in defs), "linker_script": linker[0],
            "mcu_flags": (*cpu, "-mthumb", *fpu, *(abi or ("-mfloat-abi=soft",)))}


def _CdcProfile_Validate(files: dict[str, bytes], sources: tuple[str, ...]) -> dict:
    required = {"main.c", "usb_device.c", "usbd_cdc_if.c", "usbd_desc.c", "usbd_conf.c",
                "usbd_core.c", "usbd_ctlreq.c", "usbd_ioreq.c", "usbd_cdc.c"}
    owners = {}
    for name in required:
        matches = [p for p in sources if Path(p).name == name]
        if len(matches) != 1:
            raise CubeMxImportError("Native CDC needs exactly one compiled owner: " + name)
        owners[name] = matches[0]
    code = {n: _Code_Get(files[p].decode("utf-8-sig")) for n, p in owners.items()}
    app = code["usb_device.c"]
    if (len(re.findall(r"\bUSBD_HandleTypeDef\s+hUsbDeviceFS\s*;", app)) != 1 or
            not re.search(r"USBD_RegisterClass\s*\(\s*&hUsbDeviceFS\s*,\s*&USBD_CDC\s*\)", app) or
            len(re.findall(r"USBD_Init\s*\(", app)) != 1):
        raise CubeMxImportError("Unknown classic CDC device instance/class ownership")
    callback = files[owners["usbd_cdc_if.c"]].decode("utf-8-sig")
    for name in ("CDC_Init_FS", "CDC_DeInit_FS", "CDC_Receive_FS", "CDC_Transmit_FS"):
        if len(re.findall(r"\b" + name + r"\s*\([^;{}]*\)\s*\{", code["usbd_cdc_if.c"])) != 1:
            raise CubeMxImportError("Unknown classic CDC callback shape: " + name)
    for section in ("3", "4", "6"):
        matches = re.findall(r"/\* USER CODE BEGIN " + section + r" \*/(.*?)/\* USER CODE END " + section + r" \*/", callback, re.S)
        if len(matches) != 1:
            raise CubeMxImportError("Unknown native CDC lifecycle/receive hook")
    for name in ("USBD_CDC_SetRxBuffer", "USBD_CDC_ReceivePacket", "USBD_CDC_SetTxBuffer", "USBD_CDC_TransmitPacket"):
        if name not in code["usbd_cdc_if.c"]:
            raise CubeMxImportError("Native CDC async ownership/rearm ABI missing: " + name)
    conf = code["usbd_conf.c"]
    for name in ("USBD_LL_Reset", "USBD_LL_DevDisconnected", "USBD_LL_Suspend", "USBD_LL_Resume"):
        if len(re.findall(r"\b" + name + r"\s*\(", conf)) != 1:
            raise CubeMxImportError("Unknown native CDC lifecycle owner: " + name)
    if re.search(r"\b(?:malloc|calloc|realloc|pvPortMalloc)\s*\(", conf):
        raise CubeMxImportError("Dynamic native USB allocation is unsupported")
    if "USBD_static_malloc" not in conf or "sizeof(USBD_CDC_HandleTypeDef)" not in conf.replace(" ", ""):
        raise CubeMxImportError("Unknown native static CDC allocator")
    if not re.search(r"\.speed\s*=\s*PCD_SPEED_FULL\s*;", conf):
        raise CubeMxImportError("Native controller is not a declared Full-Speed device")
    if re.search(r"(?:dma_enable|low_power_enable|lpm_enable)\s*=\s*ENABLE", conf):
        raise CubeMxImportError("DMA or sleep/tick coherency requires a separate adapter contract")
    return {"adapter_profile": "st_classic_fs_single_v1", "owners": owners,
            "device_symbol": "hUsbDeviceFS", "transmit_symbol": "CDC_Transmit_FS",
            "lifecycle_semantics": "NOT_PROVEN", "rearm_error_handling": "NOT_PROVEN",
            "tx_completion_zlp": "NOT_PROVEN", "control_request_semantics": "NOT_PROVEN"}


def _NativeClassicCdc_Inspect(root: Path, *, device_facts: NativeDeviceFacts,
                             spi_resource: str, gpio_resources: tuple[str, ...]) -> tuple[dict, object, dict[str, bytes]]:
    """Return a bounded, static admission inventory; no source edits or execution."""
    if not isinstance(device_facts, NativeDeviceFacts):
        raise CubeMxImportError("Trusted backend NativeDeviceFacts are required")
    device_facts.Facts_Validate()
    root = root.resolve()
    files: dict[str, bytes] = {}
    folded: set[str] = set()
    size = 0
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(root):
            raise CubeMxImportError("Native project alias/escape rejected: " + rel)
        if any(part.casefold() in CubeMxImporter._IGNORED_DIRECTORIES for part in p.relative_to(root).parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.casefold() not in CubeMxImporter._ALLOWED_SUFFIXES and rel not in {"Makefile", ".mxproject", ".project", ".gitignore"}:
            raise CubeMxImportError("Unfrozen native file kind: " + rel)
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", rel) or rel.casefold() in folded:
            raise CubeMxImportError("Unsafe/colliding native snapshot path: " + rel)
        folded.add(rel.casefold())
        remaining = CubeMxImporter.MAX_TOTAL_SIZE - size
        declared_size = p.stat().st_size
        if declared_size > remaining or len(files) >= CubeMxImporter.MAX_FILE_COUNT:
            raise CubeMxImportError("Native project exceeds bounded import limits")
        with p.open("rb") as stream:
            content = stream.read(declared_size + 1)
        if len(content) != declared_size:
            raise CubeMxImportError("Native input size changed while freezing: " + rel)
        size += len(content)
        if size > CubeMxImporter.MAX_TOTAL_SIZE or len(files) >= CubeMxImporter.MAX_FILE_COUNT:
            raise CubeMxImportError("Native project exceeds bounded import limits")
        files[rel] = content
    iocs = [p for p in files if p.endswith(".ioc") and "/" not in p]
    if len(iocs) != 1:
        raise CubeMxImportError("Native complete CDC needs exactly one root IOC")
    ioc = files[iocs[0]].decode("utf-8-sig")
    if CubeMxImporter._Mcu_Get(ioc) != device_facts.part:
        raise CubeMxImportError("Native IOC contradicts independent exact device facts")
    CubeMxImporter._RtosConflict_Validate(root, ioc)
    fields = dict(line.split("=", 1) for line in ioc.splitlines() if "=" in line)
    modules = {v for k, v in fields.items() if re.fullmatch(r"Mcu\.IP\d+", k)}
    if ("USB_DEVICE" not in modules or modules & {"USBX", "USB_OTG_HS", "USB_HOST"} or
            any(v not in {"Cdc", "Cdc_FS"} for k, v in fields.items() if k.startswith("USB_DEVICE.VirtualMode")) or
            not any(k.startswith("USB_DEVICE.VirtualMode") for k in fields)):
        raise CubeMxImportError("Only complete bare-metal single FS classic CDC is supported")
    GroundDependencyDirectives_Validate(root)
    build = _LiteralBuild_Get(root, files, device_facts)
    if any(re.search(r"(?i)(usbx|threadx|freertos|cmsis[_-]?rtos|usb.*hs|class/(?!cdc))", p) for p in build["sources"]):
        raise CubeMxImportError("Unsupported native stack/controller/scheduler")
    cdc = _CdcProfile_Validate(files, build["sources"])
    generated = {p: b.decode("utf-8-sig") for p, b in files.items() if p.endswith((".c", ".h")) and p.startswith(("Core/", "USB_DEVICE/"))}
    inventory = CubeMxInventory_Parse(ioc, generated_files=generated)
    resources = {r.resource_id: r for r in inventory.HardwareResources_Get()}
    spi = resources.get(spi_resource)
    if spi is None or spi.kind != "spi" or not re.fullmatch(r"hspi[0-9]+", str(spi.metadata.get("handle", ""))):
        raise CubeMxImportError("Native radio SPI handle/initialization inventory missing")
    spi_code = "\n".join(_Code_Get(generated.get(p, "")) for p in build["sources"] if p.startswith("Core/"))
    handle = spi.metadata["handle"]
    if (len(re.findall(r"\bSPI_HandleTypeDef\s+" + re.escape(handle) + r"\s*;", spi_code)) != 1 or
            not re.search(re.escape(handle) + r"\.Init\.Mode\s*=\s*SPI_MODE_MASTER\s*;", spi_code) or
            len(re.findall(r"HAL_SPI_Init\s*\(\s*&" + re.escape(handle) + r"\s*\)", spi_code)) != 1):
        raise CubeMxImportError("Native radio SPI has unknown/conflicting real type/init owner")
    spi_headers = [p for p in files if re.fullmatch(
        r"Drivers/STM32[A-Za-z0-9]+_HAL_Driver/Inc/stm32[a-z0-9]+_hal_spi\.h", p)]
    if len(spi_headers) != 1:
        raise CubeMxImportError("Native SPI needs one known HAL header owner")
    spi_header = _Code_Get(files[spi_headers[0]].decode("utf-8-sig"))
    qualifiers = []
    for name, tail in (("HAL_SPI_Transmit", ""),
                       ("HAL_SPI_TransmitReceive", r"uint8_t\s*\*\s*\w+\s*,\s*")):
        pattern = (r"\bHAL_StatusTypeDef\s+" + name +
                   r"\s*\(\s*SPI_HandleTypeDef\s*\*\s*\w+\s*,\s*(const\s+)?" +
                   r"uint8_t\s*\*\s*\w+\s*,\s*" + tail +
                   r"uint16_t\s+\w+\s*,\s*uint32_t\s+\w+\s*\)\s*;")
        signatures = re.findall(pattern, spi_header)
        if len(signatures) != 1:
            raise CubeMxImportError("Unknown native blocking SPI ABI: " + name)
        qualifiers.append(bool(signatures[0]))
    if qualifiers[0] != qualifiers[1]:
        raise CubeMxImportError("Inconsistent native SPI transmit buffer qualifiers")
    if not gpio_resources or len(set(gpio_resources)) != len(gpio_resources):
        raise CubeMxImportError("Native GPIO bindings missing or duplicated")
    pins = set()
    for key in gpio_resources:
        r = resources.get(key)
        if r is None or r.kind not in {"gpio_input", "gpio_output", "gpio_interrupt"} or not r.metadata.get("physical_pin"):
            raise CubeMxImportError("Native GPIO mode/pin inventory missing: " + key)
        pin = r.metadata["physical_pin"]
        if pin in pins:
            raise CubeMxImportError("Native GPIO owners conflict")
        pins.add(pin)
    if "HAL_IncTick" not in spi_code or "HAL_Init" not in spi_code:
        raise CubeMxImportError("Native HAL tick initialization/progression owner missing")
    startup = _Code_Get(files[build["asm_sources"][0]].decode("utf-8-sig"))
    if (len(re.findall(r"(?m)^\s*Reset_Handler:\s*$", startup)) != 1 or
            not re.search(r"(?m)^\s*\.type\s+Reset_Handler\s*,\s*%function\s*$", startup) or
            re.search(r"\.thumb_set\s+Reset_Handler\s*,", startup) or
            re.search(r"\bReset_Handler\s*\([^;{}]*\)\s*\{", spi_code)):
        raise CubeMxImportError("Unknown/conflicting native reset entry body/owner")
    vector = startup.split("g_pfnVectors:", 1)
    if len(vector) != 2:
        raise CubeMxImportError("Unknown native GNU vector table")
    exceptions = {"NonMaskableInt", "HardFault", "MemoryManagement", "BusFault", "UsageFault",
                  "SVCall", "DebugMonitor", "PendSV", "SysTick"}
    irq = [k[5:].removesuffix("_IRQn") + "_IRQHandler" for k, v in fields.items()
           if k.startswith("NVIC.") and k.endswith("_IRQn") and v.startswith("true")
           and k[5:].removesuffix("_IRQn") not in exceptions]
    if not fields.get("NVIC.TimeBaseIP", "").startswith("TIM"):
        if not fields.get("NVIC.SysTick_IRQn", "").startswith("true"):
            raise CubeMxImportError("Native SysTick is not enabled")
        irq.insert(0, "SysTick_Handler")
    for name in irq:
        if (len(re.findall(r"\bvoid\s+" + re.escape(name) + r"\s*\(\s*void\s*\)\s*\{", spi_code)) != 1 or
                len(re.findall(r"(?m)^\s*\.word\s+" + re.escape(name) + r"\s*$", vector[1])) != 1):
            raise CubeMxImportError("Native IRQ has no unique compiled/vector owner: " + name)
    proof = {"format_version": 1, "input_kind": NATIVE_CLASSIC_CDC_KEY, "ioc_file": iocs[0],
             "device_facts": asdict(device_facts), "build": build, "cdc": cdc,
             "bindings": {"spi": spi_resource, "gpio": gpio_resources}, "required_irq_handlers": irq,
             "spi_abi": {"tx_buffer_const": qualifiers[0], "header_owner": spi_headers[0],
                         "blocking_timeout_semantics": "NOT_PROVEN"},
             "static_contract": "VALIDATED_TEXT_SCOPE", "compiler_abi_closure": "NOT_PROVEN",
             "physical_hardware": "NOT_PROVEN", "runtime_adapter_enabled": False,
             "radio_us_delay": "NOT_PROVEN", "tick_liveness": "NOT_PROVEN",
             "native_files_sha256": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
    return json.loads(json.dumps(proof)), inventory, files


def NativeClassicCdc_Inspect(root: Path, *, device_facts: NativeDeviceFacts,
                             spi_resource: str, gpio_resources: tuple[str, ...]) -> tuple[dict, object, dict[str, bytes]]:
    try:
        return _NativeClassicCdc_Inspect(root, device_facts=device_facts,
            spi_resource=spi_resource, gpio_resources=gpio_resources)
    except (OSError, UnicodeError, ValueError) as error:
        raise CubeMxImportError("Cannot read strict native CDC source input: " + str(error)) from error


def NativeClassicCdc_Import(importer: CubeMxImporter, input_path: Path, *, device_facts: NativeDeviceFacts,
                            spi_resource: str, gpio_resources: tuple[str, ...],
                            risk_acknowledged: bool) -> CubeMxImportResult:
    root, _ioc = importer._Input_Resolve(input_path)
    proof, inventory, files = NativeClassicCdc_Inspect(root, device_facts=device_facts,
        spi_resource=spi_resource, gpio_resources=gpio_resources)
    encoded = json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    destination = importer.policy.Path_Resolve(importer.cache_root/digest/"NativeClassicCdc", allow_root=False)
    # A directory rename can succeed while making deeper children inaccessible
    # on a Windows host without long-path support. Reject before any publication.
    if os.name == "nt" and any(len(str(destination/p)) >= 248 for p in files):
        raise CubeMxImportError("Native snapshot paths exceed the portable Windows limit; select a shorter workspace path")
    if destination.exists():
        cached = set()
        for p in destination.rglob("*"):
            if p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(destination):
                raise CubeMxImportError("Immutable native snapshot contains an alias")
            if p.is_file():
                cached.add(p.relative_to(destination).as_posix())
        if cached != set(files):
            raise CubeMxImportError("Immutable native snapshot file inventory is modified")
        for p, content in files.items():
            candidate = importer.policy.Path_Resolve(destination/p, allow_root=False)
            if not candidate.is_file() or candidate.read_bytes() != content:
                raise CubeMxImportError("Immutable native snapshot is modified: " + p)
        if (destination.parent/"native-contract.json").read_bytes() != encoded:
            raise CubeMxImportError("Immutable native contract is modified")
    else:
        stage = importer.policy.StagingDirectory_Create("native-classic-cdc-")
        try:
            for p, b in files.items():
                target = stage/"NativeClassicCdc"/p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b)
            (stage/"native-contract.json").write_bytes(encoded)
            destination.parent.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.exists():
                raise CubeMxImportError("Native snapshot destination is occupied")
            importer.policy.Path_Replace(stage, destination.parent)
        finally:
            if stage.exists():
                importer.policy.Tree_Remove(stage)
    build = proof["build"]
    hardware = HardwareConfiguration(mode="custom", source_kind="manual_import", provider="silverstar.hardware_provider.stm32_cubemx",
        snapshot_id=digest, ioc_file=proof["ioc_file"], mcu=device_facts.part,
        cubemx_version=inventory.cubemx_version, firmware_package=inventory.firmware_package,
        hal_cmsis_source_policy="imported_tree_authoritative", capabilities=("usb.device", "usb.cdc"),
        inventory={**inventory.Dictionary_Get(), NATIVE_CLASSIC_CDC_KEY: proof},
        resources=tuple(HardwareResource(r.resource_id,r.kind,json.loads(json.dumps(r.metadata)))
                        for r in inventory.HardwareResources_Get()),
        build_sources=tuple(NATIVE_PREFIX+p for p in build["sources"]),
        asm_sources=tuple(NATIVE_PREFIX+p for p in build["asm_sources"]),
        include_dirs=tuple(NATIVE_PREFIX+p for p in build["include_dirs"]),
        defines=tuple(sorted(build["defines"])), linker_script=NATIVE_PREFIX+build["linker_script"],
        source_digest=digest, source_label=root.name, risk_acknowledged=risk_acknowledged)
    return CubeMxImportResult(hardware, destination, tuple(inventory.peripherals),
        ("Experimental static contract only; runtime hooks/closure/ABI/radio timing NOT PROVEN; normal firmware generation is blocked",), inventory)
