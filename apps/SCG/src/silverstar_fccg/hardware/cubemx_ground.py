"""Read the data-only build inventory of a copied CubeMX Ground project.

Never execute the imported Makefile. The first supported input is CubeMX's
GNU Makefile export with libraries copied inside the project.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GroundCubeInputs:
    sources: tuple[str, ...]
    assembly: tuple[str, ...]
    includes: tuple[str, ...]
    defines: tuple[str, ...]
    linker: str
    flags: tuple[str, ...]


def GroundCubeInputs_Get(root: Path, mcu: str) -> GroundCubeInputs:
    profiles = {
        "STM32F103C8T6": ("STM32F103xB", ("-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft")),
        "STM32F407VET6": ("STM32F407xx", ("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard")),
    }
    if mcu not in profiles:
        raise ValueError("Complete Ground CubeMX import currently supports STM32F103C8T6 and STM32F407VET6")
    makefile = root / "Makefile"
    if not makefile.is_file():
        raise ValueError("Ground CubeMX project needs its generated GNU Makefile; select Makefile and copy required libraries in CubeMX, then Generate Code")
    text = makefile.read_text(encoding="utf-8-sig")
    # Only direct assignments to the inventory fields are understood. Neither
    # make expansion nor shell commands are evaluated.
    logical = re.sub(r"\\\r?\n", " ", text)

    def values(name: str) -> tuple[str, ...]:
        matches = re.findall(r"(?m)^" + re.escape(name) + r"\s*=\s*([^\r\n]*)", logical)
        if len(matches) != 1:
            raise ValueError(f"CubeMX Makefile must contain one literal {name} assignment")
        result = tuple(matches[0].split())
        if any(any(char in token for char in "$#;|&`\"'") for token in result):
            raise ValueError(f"CubeMX {name} contains unsupported references or build expressions; copy dependencies into the project")
        if len(result) != len(set(result)):
            raise ValueError(f"CubeMX {name} contains duplicate inputs")
        return result

    def path(value: str, *, directory: bool = False) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", value) or any(part in {"..", ""} for part in value.split("/")):
            raise ValueError(f"CubeMX build path must be a safe project-relative path: {value}")
        resolved = (root / value).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"CubeMX dependency escapes project: {value}")
        if not (resolved.is_dir() if directory else resolved.is_file()):
            raise ValueError(f"CubeMX dependency missing: {value}; copy required libraries into the project")
        return "HardwareGenerated/STM32CubeMX/" + value

    source_values = values("C_SOURCES")
    allowed = ("Core/Src/", "USB_DEVICE/App/", "USB_DEVICE/Target/",
               "Middlewares/ST/STM32_USB_Device_Library/Core/Src/",
               "Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/")
    for value in source_values:
        family = "STM32F1xx" if mcu.startswith("STM32F103") else "STM32F4xx"
        hal = re.fullmatch(r"Drivers/" + family + r"_HAL_Driver/Src/[A-Za-z0-9_]+\.c", value)
        if not value.endswith(".c") or not (value.startswith(allowed) or hal):
            raise ValueError(f"Unsupported Ground CubeMX source: {value}; only bare-metal HAL and classic USB CDC are supported")
    sources = tuple(path(value) for value in source_values if not value.endswith(("/sysmem.c", "/freertos.c")))
    if not any(value.endswith("/Core/Src/main.c") for value in sources):
        raise ValueError("Ground CubeMX Makefile does not compile Core/Src/main.c")
    assembly_values = values("ASM_SOURCES")
    startup = "startup_stm32f103xb.s" if mcu.startswith("STM32F103") else "startup_stm32f407xx.s"
    if len(assembly_values) != 1 or assembly_values[0].split("/")[-1] != startup:
        raise ValueError("Ground CubeMX requires exactly one matching GNU startup assembler file")
    linker_values = values("LDSCRIPT")
    if len(linker_values) != 1 or not linker_values[0].endswith(".ld"):
        raise ValueError("Ground CubeMX requires exactly one GNU linker script")
    path(linker_values[0])
    linker_text = (root / linker_values[0]).read_text(encoding="utf-8-sig")
    regions = re.findall(r"(?m)^\s*(FLASH|RAM)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,\s*LENGTH\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*([KM]?)", linker_text)
    expected_regions = {"FLASH": (0x08000000, 65536 if mcu.startswith("STM32F103") else 524288),
                        "RAM": (0x20000000, 20480 if mcu.startswith("STM32F103") else 131072)}
    actual_regions = {name: (int(origin, 0), int(size, 0) * {"": 1, "K": 1024, "M": 1048576}[unit])
                      for name, origin, size, unit in regions}
    if len(regions) != 2 or actual_regions != expected_regions:
        raise ValueError("CubeMX linker FLASH/RAM regions do not match the exact MCU memory contract")
    includes = values("C_INCLUDES")
    if any(not value.startswith("-I") for value in includes):
        raise ValueError("CubeMX C_INCLUDES must contain literal -I paths")
    if any(not value[2:].startswith(("Core/Inc", "Drivers/", "USB_DEVICE/", "Middlewares/ST/STM32_USB_Device_Library/")) for value in includes):
        raise ValueError("CubeMX Ground include directories are outside the supported hardware/CDC tree")
    defines = values("C_DEFS")
    if any(not re.fullmatch(r"-D[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_]+)?", value) for value in defines):
        raise ValueError("CubeMX C_DEFS contains unsupported definitions")
    expected_define, flags = profiles[mcu]
    if "-D" + expected_define not in defines or "-DUSE_HAL_DRIVER" not in defines:
        raise ValueError("CubeMX Makefile MCU definitions do not match its .ioc")
    if values("CPU") != (flags[0],):
        raise ValueError("CubeMX compiler CPU does not match its .ioc")
    if mcu == "STM32F407VET6" and (values("FPU") != (flags[2],) or values("FLOAT-ABI") != (flags[3],)):
        raise ValueError("CubeMX FPU/ABI does not match STM32F407")
    # Classic ST headers use #if on optional switches omitted by some CubeMX
    # versions. Encode their normal zero default in the build inventory only
    # when the authoritative imported configuration does not define them.
    usb_conf = root / "USB_DEVICE/Target/usbd_conf.h"
    if usb_conf.is_file():
        config = usb_conf.read_text(encoding="utf-8-sig")
        for name in ("USBD_CLASS_BOS_ENABLED", "USBD_USER_REGISTER_CALLBACK"):
            if not re.search(r"(?m)^\s*#\s*define\s+" + name + r"\b", config):
                defines += ("-D" + name + "=0U",)
    return GroundCubeInputs(sources, tuple(path(value) for value in assembly_values),
                            tuple(path(value[2:], directory=True) for value in includes),
                            tuple(value[2:] for value in defines), path(linker_values[0]), flags)


def GroundUsbConfiguration_Validate(root: Path, ioc: str, mcu: str) -> None:
    """Validate documented FS CDC topology; electrical/clock accuracy needs hardware."""
    fields = dict(line.split("=", 1) for line in ioc.splitlines() if "=" in line)
    modules = {value for key, value in fields.items() if re.fullmatch(r"Mcu\.IP\d+", key)}
    if "USBX" in modules:
        raise ValueError("Ground USBX requires a separate adapter; the current supported stack is classic USB Device CDC")
    if "USB_DEVICE" not in modules:
        return
    classes = [value for key, value in fields.items() if key in {"USB_DEVICE.VirtualMode", "USB_DEVICE.VirtualModeFS"}]
    if not classes or any(value not in {"Cdc", "Cdc_FS"} for value in classes):
        raise ValueError("Ground supports a single classic full-speed CDC device, not composite, host or other classes")
    f1 = mcu == "STM32F103C8T6"
    prefix = "USB" if f1 else "USB_OTG_FS"
    if fields.get("PA11.Signal") != prefix + "_DM" or fields.get("PA12.Signal") != prefix + "_DP":
        raise ValueError("Ground USB FS needs CubeMX PA11/DM and PA12/DP")
    clock_key = "RCC.USBFreq_Value" if f1 else "RCC.48MHZClocksFreq_Value"
    if fields.get(clock_key) != "48000000":
        raise ValueError("Ground USB FS requires a declared 48000000 Hz clock in CubeMX")
    irq = "USB_LP_CAN1_RX0_IRQn" if f1 else "OTG_FS_IRQn"
    if not fields.get("NVIC." + irq, "").startswith("true"):
        raise ValueError("Ground USB needs its enabled CubeMX interrupt: " + irq)
    irq_source = (root / "Core/Src" / ("stm32f1xx_it.c" if f1 else "stm32f4xx_it.c")).read_text(encoding="utf-8-sig")
    handler = irq.removesuffix("IRQn") + "IRQHandler"
    match = re.search(r"void\s+" + handler + r"\s*\(void\)\s*\{([^}]+)\}", irq_source)
    if match is None or "HAL_PCD_IRQHandler" not in match[1]:
        raise ValueError("CubeMX USB interrupt does not dispatch to HAL_PCD_IRQHandler")
    conf = (root / "USB_DEVICE/Target/usbd_conf.c").read_text(encoding="utf-8-sig")
    hal_conf = (root / "Core/Inc" / ("stm32f1xx_hal_conf.h" if f1 else "stm32f4xx_hal_conf.h")).read_text(encoding="utf-8-sig")
    if not re.search(r"(?m)^\s*#define\s+HAL_PCD_MODULE_ENABLED\b", hal_conf):
        raise ValueError("CubeMX HAL configuration does not enable its PCD module")
    _UsbClock_Validate(root, hal_conf, f1)
    if "USBD_static_malloc" not in conf:
        raise ValueError("Ground CDC requires CubeMX's static USB class allocator")
    if f1:
        entries = re.findall(r"HAL_PCDEx_PMAConfig\([^,]+,\s*(0x[0-9A-Fa-f]+)\s*,\s*PCD_SNG_BUF\s*,\s*(0x[0-9A-Fa-f]+)\s*\)", conf)
        addresses = [(int(ep, 16), int(offset, 16)) for ep, offset in entries]
        if len(addresses) != 5 or {ep for ep, _ in addresses} != {0, 0x80, 0x81, 1, 0x82}:
            raise ValueError("Ground F103 requires the reviewed single CDC PMA endpoint layout")
        intervals = sorted((offset, offset + (8 if ep == 0x82 else 64)) for ep, offset in addresses)
        if any(start < 0x18 or start % 2 or end > 512 for start, end in intervals) or any(a[1] > b[0] for a, b in zip(intervals, intervals[1:])):
            raise ValueError("Ground F103 PMA endpoints overlap, are unaligned or exceed 512 bytes")
        main = (root / "Core/Src/main.c").read_text(encoding="utf-8-sig")
        if not re.search(r"UsbClockSelection\s*=\s*RCC_USBCLKSOURCE_PLL_DIV1_5\s*;", main):
            raise ValueError("Ground F103 profile requires generated PLL/1.5 USB clock selection")
    else:
        rx = re.findall(r"HAL_PCDEx_SetRxFiFo\([^,]+,\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*\)", conf)
        tx = re.findall(r"HAL_PCDEx_SetTxFiFo\([^,]+,\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*\)", conf)
        if len(rx) != 1 or len(tx) != 2 or {int(ep, 0) for ep, _ in tx} != {0, 1}:
            raise ValueError("Ground F407 requires the reviewed single CDC OTG FS FIFO layout")
        if int(rx[0], 0) < 47 or any(int(size, 0) < 16 for _, size in tx) or int(rx[0], 0) + sum(int(size, 0) for _, size in tx) > 320:
            raise ValueError("Ground F407 USB FIFO configuration exceeds capacity or lacks FS packet space")


def _UsbClock_Validate(root: Path, hal_conf: str, f1: bool) -> None:
    main = (root / "Core/Src/main.c").read_text(encoding="utf-8-sig")
    hse_values = re.findall(r"(?m)^\s*#define\s+HSE_VALUE\s+\(?([0-9]+)[uU]?\)?", hal_conf)
    if len(hse_values) != 1 or not re.search(r"PLLSource\s*=\s*RCC_PLLSOURCE_HSE\s*;", main):
        raise ValueError("Ground USB requires a literal HSE clock and generated HSE PLL source")
    hse = int(hse_values[0])
    if f1:
        mul = re.findall(r"PLLMUL\s*=\s*RCC_PLL_MUL([0-9]+)\s*;", main)
        div = re.findall(r"HSEPredivValue\s*=\s*RCC_HSE_PREDIV_DIV([0-9]+)\s*;", main)
        valid = len(mul) == len(div) == 1 and hse * int(mul[0]) * 2 == 48000000 * int(div[0]) * 3
    else:
        params = [re.findall(r"PLL" + name + r"\s*=\s*([0-9]+)\s*;", main) for name in ("M", "N", "Q")]
        valid = all(len(value) == 1 for value in params)
        if valid:
            m, n, q = (int(value[0]) for value in params)
            valid = m > 0 and q > 0 and hse * n == 48000000 * m * q
    if not valid:
        raise ValueError("Generated HSE/PLL configuration does not produce the required 48000000 Hz USB clock")
