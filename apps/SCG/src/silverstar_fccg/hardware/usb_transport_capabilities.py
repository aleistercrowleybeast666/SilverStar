"""Conservative, nonexecuting inventory for the experimental USB transport.

This checks a literal CubeMX Make inventory, not arbitrary build semantics.
Unresolved configuration is rejected, never interpreted as a disabled feature.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import json
import re


def UsbCode_Read(body: bytes) -> str:
    text = body.decode("utf-8-sig", errors="strict")
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.S)


def _InventoryInputs_Inspect(files: dict[str, bytes], build: dict) -> list[str]:
    reasons = []
    for key in ("sources", "asm_sources", "linker_script", "include_dirs"):
        tokens = build.get(key, [])
        if len(set(token.casefold() for token in tokens)) != len(tokens):
            reasons.append("BUILD_DUPLICATE:" + key)
        for token in tokens:
            path = token[2:] if key == "include_dirs" and token.startswith("-I") else token
            if (not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or
                    any(part in {"", ".", ".."} for part in path.split("/"))):
                reasons.append("UNSAFE_BUILD_PATH:" + token)
            elif key == "include_dirs":
                if not token.startswith("-I") or not any(p.startswith(path + "/") for p in files):
                    reasons.append("MISSING_BUILD_INCLUDE:" + token)
            elif path not in files or not files[path].strip():
                reasons.append("MISSING_OR_EMPTY_BUILD_INPUT:" + token)
    if len(build.get("asm_sources", [])) != 1 or len(build.get("linker_script", [])) != 1:
        reasons.append("ONE_STARTUP_AND_LINKER_REQUIRED")
    return reasons


def _Manifest_Inspect(files: dict[str, bytes]) -> tuple[dict, list[str]]:
    try:
        data = json.loads(files["scg-usb-build.json"].decode("utf-8-sig"))
        fields = {"format", "version", "sources", "asm_sources", "include_dirs", "defines", "cpu", "linker_script"}
        if (set(data) != fields or data["format"] != "silverstar.usb.native-build" or data["version"] != 1):
            raise ValueError("unrecognized fields/version")
        for key in ("sources", "asm_sources", "include_dirs", "defines"):
            if not isinstance(data[key], list) or not data[key] or not all(isinstance(v, str) for v in data[key]):
                raise ValueError("nonempty string list required: " + key)
        if not isinstance(data["cpu"], str) or not re.fullmatch(r"[A-Za-z0-9_-]+", data["cpu"]):
            raise ValueError("literal CPU required")
        if not isinstance(data["linker_script"], str):
            raise ValueError("literal linker path required")
        if any(not re.fullmatch(r"[A-Za-z_]\w*(?:=[A-Za-z0-9_]+)?", v) for v in data["defines"]):
            raise ValueError("literal preprocessor definitions required")
        build = {key: data[key] for key in ("sources", "asm_sources")}
        build.update(include_dirs=["-I" + p for p in data["include_dirs"]],
            defines=["-D" + p for p in data["defines"]], cpu=["-mcpu=" + data["cpu"]],
            linker_script=[data["linker_script"]], inventory_owner="scg-usb-build.json")
        return build, _InventoryInputs_Inspect(files, build)
    except (ValueError, TypeError, UnicodeError) as error:
        return {}, ["INVALID_DECLARATIVE_BUILD_INVENTORY:" + str(error)]


def UsbBuild_Inspect(files: dict[str, bytes]) -> tuple[dict, list[str]]:
    reasons = []
    if "scg-usb-build.json" in files:
        if "Makefile" in files:
            return {}, ["AMBIGUOUS_BUILD_INVENTORY: choose Makefile or scg-usb-build.json"]
        return _Manifest_Inspect(files)
    if "Makefile" not in files:
        return {}, ["LITERAL_CUBEMX_MAKE_INVENTORY_REQUIRED"]
    text = re.sub(r"\\\r?\n", " ", files["Makefile"].decode("utf-8-sig"))
    build = {}
    for field, key in (("C_SOURCES", "sources"), ("ASM_SOURCES", "asm_sources"),
                       ("C_INCLUDES", "include_dirs"), ("C_DEFS", "defines"),
                       ("LDSCRIPT", "linker_script"), ("CPU", "cpu")):
        matches = re.findall(r"(?m)^[ \t]*" + field + r"[ \t]*([:+?]?=)[ \t]*([^\r\n]*)", text)
        if len(matches) != 1 or matches[0][0] != "=" or not matches[0][1].strip():
            reasons.append("LITERAL_BUILD_FIELD_REQUIRED:" + field)
            continue
        tokens = matches[0][1].split()
        if any(re.search(r"[$#;|&`\"'(){}\\]", token) for token in tokens):
            reasons.append("BUILD_EXPRESSION_UNSUPPORTED:" + field)
            continue
        if len(set(token.casefold() for token in tokens)) != len(tokens):
            reasons.append("BUILD_DUPLICATE:" + field)
        build[key] = tokens
    reasons.extend(_InventoryInputs_Inspect(files, build))
    # Additional definitions in CFLAGS/includes cannot silently override the inventory.
    other_lines = re.sub(r"(?m)^\s*C_DEFS\s*=.*$", "", text)
    # CubeMX's generated dependency include is not a source/configuration owner.
    other_lines = re.sub(r"(?m)^-include \$\(wildcard \$\(BUILD_DIR\)/\*\.d\)[ \t\r]*$", "", other_lines)
    if re.search(r"(?m)^[ \t]*(?:include|-include|sinclude|override|export)\b|\$\(eval\b", other_lines):
        reasons.append("BUILD_CONFIGURATION_REQUIRES_REVIEW")
    if re.search(r"(?m)^[^#\r\n]*\s-D[A-Za-z_]", other_lines):
        reasons.append("EXTRA_BUILD_DEFINITIONS_UNSUPPORTED")
    if re.search(r"(?m)^[ \t]*(?:ASMM_SOURCES|ASMMC_SOURCE)[ \t]*[:+?]?=[ \t]*[^\s#]", text):
        reasons.append("ADDITIONAL_ASSEMBLY_UNSUPPORTED")
    return build, reasons


def UsbCapabilities_Inspect(files: dict[str, bytes], owners: dict[str, str]) -> tuple[dict, list[str]]:
    build, reasons = UsbBuild_Inspect(files)
    try:
        code = {p: UsbCode_Read(b) for p, b in files.items() if p.endswith((".c", ".h"))}
    except UnicodeError:
        return {"build": build}, reasons + ["SOURCE_ENCODING_UNSUPPORTED"]
    sources = build.get("sources", [])
    for name, path in owners.items():
        if name.endswith(".c") and path not in sources:
            reasons.append("OWNER_NOT_IN_BUILD:" + name)
    required_functions = {
        "usbd_core.c": ("USBD_Init", "USBD_SetClassConfig", "USBD_ClrClassConfig"),
        "usbd_cdc.c": ("USBD_CDC_Init", "USBD_CDC_DeInit", "USBD_CDC_DataIn", "USBD_CDC_DataOut"),
        "usbd_cdc_if.c": ("CDC_Init_FS", "CDC_DeInit_FS", "CDC_Receive_FS", "CDC_Transmit_FS"),
        "usb_device.c": ("MX_USB_DEVICE_Init",),
        "usbd_conf.c": ("USBD_LL_Transmit", "USBD_LL_PrepareReceive", "USBD_LL_CloseEP"),
        "main.c": ("main", "SystemClock_Config"),
    }
    for owner, names in required_functions.items():
        body = code.get(owners.get(owner, ""), "")
        for name in names:
            if len(re.findall(r"\b" + name + r"\s*\([^;{}]*\)\s*\{", body)) != 1:
                reasons.append("FUNCTION_OWNER_UNPROVEN:" + name)
    compiled = "\n".join(code.get(p, "") for p in sources)
    application = "\n".join(code.get(p, "") for p in sources if not
        any(part.casefold() in {"drivers", "middlewares"} for part in PurePosixPath(p).parts))
    definitions = "\n".join(code.values()) + "\n" + " ".join(build.get("defines", []))
    if (re.search(r"(?im)^\s*#\s*define\s+USE_USBD_COMPOSITE\b", definitions) or
            any(d.startswith("-DUSE_USBD_COMPOSITE") for d in build.get("defines", []))):
        reasons.append("COMPOSITE_OR_RTOS_OWNER_UNSUPPORTED")
    if (any(re.search(r"(?i)freertos|threadx|cmsis[_-]?rtos|usb.*host|class/(?!cdc/)", p) for p in sources) or
            re.search(r"\b(?:vTaskStartScheduler|osKernelStart|tx_kernel_enter)\s*\(", compiled)):
        reasons.append("COMPOSITE_OR_RTOS_OWNER_UNSUPPORTED")
    for value in re.findall(r"\bdma_enable\s*=(?!=)\s*([^;]+);", application):
        if not re.fullmatch(r"\(*\s*(?:DISABLE|0[Uu]?)\s*\)*", value.strip()):
            reasons.append("DMA_OR_DATA_CACHE_UNSUPPORTED")
    if re.search(r"\bSCB_EnableDCache\s*\(|\bSCB_CCR_DC_Msk\b", compiled):
        reasons.append("DMA_OR_DATA_CACHE_UNSUPPORTED")
    conf = code.get(owners.get("usbd_conf.c", ""), "")
    config = code.get(owners.get("usbd_conf.h", ""), "")
    if (re.search(r"\b(?:malloc|calloc|realloc|pvPortMalloc|tx_byte_allocate)\s*\(", application) or
            not re.search(r"#\s*define\s+USBD_malloc\s+(?:\((?:void|uint32_t)\s*\*\))?USBD_static_malloc\b", config) or
            not re.search(r"\bUSBD_static_malloc\s*\([^;{}]*\)\s*\{", conf)):
        reasons.append("STATIC_CLASS_ALLOCATOR_UNPROVEN")
    if not re.search(r"\.speed\s*=\s*PCD_SPEED_FULL\s*;", conf):
        reasons.append("FULL_SPEED_CONTROLLER_UNPROVEN")
    for field in ("low_power_enable", "lpm_enable"):
        for value in re.findall(r"\b" + field + r"\s*=\s*([^;]+);", conf):
            if value.strip() not in {"DISABLE", "0", "0U"}:
                reasons.append("LOW_POWER_LIFECYCLE_UNSUPPORTED")
    app = code.get(owners.get("usb_device.c", ""), "")
    if not re.search(r"USBD_RegisterClass\s*\(\s*&hUsbDeviceFS\s*,\s*&USBD_CDC\s*\)", app):
        reasons.append("SINGLE_CDC_INSTANCE_UNPROVEN")
    if not re.search(r"\bMX_USB_DEVICE_Init\s*\(\s*\)\s*;", code.get(owners.get("main.c", ""), "")):
        reasons.append("NATIVE_USB_INIT_CALL_UNPROVEN")
    return {"build": build, "scope": "DECLARED_BUILD_AND_SOURCE_CHECKS_ONLY",
            "clock_irq_memory_runtime": "NOT_PROVEN",
            "controller": "FS", "scheduler": "single_main_plus_usb_irq"}, list(dict.fromkeys(reasons))
