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
    irq_handlers: tuple[str, ...]


def GroundCubeInputs_Get(root: Path, mcu: str) -> GroundCubeInputs:
    profiles = {
        "STM32F103C8T6": ("STM32F103xB", ("-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft")),
        "STM32F407VET6": ("STM32F407xx", ("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard")),
    }
    if mcu not in profiles:
        raise ValueError("Ground CubeMX import supports UART on F103C8T6 and F407VET6")
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
    if any(Path(name).name.lower() in {'usbd_cdc.c', 'usbd_cdc_if.c'} for name in source_values):
        from silverstar_fccg.project.retired_cdc import MIGRATION_NOTICE
        raise ValueError(MIGRATION_NOTICE)
    allowed = ('Core/Src/',)
    for value in source_values:
        family = {"STM32F103C8T6": "STM32F1xx", "STM32F407VET6": "STM32F4xx"}[mcu]
        hal = re.fullmatch(r"Drivers/" + family + r"_HAL_Driver/Src/[A-Za-z0-9_]+\.c", value)
        if not value.endswith(".c") or not (value.startswith(allowed) or hal):
            raise ValueError(f"Unsupported Ground CubeMX source: {value}; expected the Ground UART peripheral and HAL sources")
    sources = tuple(path(value) for value in source_values if not value.endswith(("/sysmem.c", "/freertos.c")))
    if not any(value.endswith("/Core/Src/main.c") for value in sources):
        raise ValueError("Ground CubeMX Makefile does not compile Core/Src/main.c")
    assembly_values = values("ASM_SOURCES")
    startup = {"STM32F103C8T6": "startup_stm32f103xb.s", "STM32F407VET6": "startup_stm32f407xx.s"}[mcu]
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
    if any(not value[2:].startswith(("Core/Inc", "Drivers/")) for value in includes):
        raise ValueError("CubeMX Ground include directories are outside the supported hardware tree")
    defines = values("C_DEFS")
    if any(not re.fullmatch(r"-D[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_]+)?", value) for value in defines):
        raise ValueError("CubeMX C_DEFS contains unsupported definitions")
    expected_define, flags = profiles[mcu]
    if "-D" + expected_define not in defines or "-DUSE_HAL_DRIVER" not in defines:
        raise ValueError("CubeMX Makefile MCU definitions do not match its .ioc")
    if set(defines) != {"-D" + expected_define, "-DUSE_HAL_DRIVER"}:
        raise ValueError("Ground C_DEFS supports only the exact MCU and USE_HAL_DRIVER; conflicting/custom macro overrides are unsupported")
    family = {"STM32F103C8T6": "stm32f1xx", "STM32F407VET6": "stm32f4xx"}[mcu]
    irq_path = "Core/Src/" + family + "_it.c"
    if irq_path not in source_values:
        raise ValueError("Ground requires its generated IRQ source in C_SOURCES: " + irq_path)
    irq_handlers = _IrqHandlers_Get(root, source_values)
    irq_text = (root / irq_path).read_text(encoding="utf-8-sig")
    for handler in irq_handlers:
        if not re.search(r"\bvoid\s+" + handler + r"\s*\(\s*void\s*\)\s*\{", irq_text):
            raise ValueError("Ground compiled IRQ source is missing handler: " + handler)
    from silverstar_fccg.hardware.ground_dependencies import GroundDependencyDirectives_Validate
    GroundDependencyDirectives_Validate(root)
    if values("CPU") != (flags[0],):
        raise ValueError("CubeMX compiler CPU does not match its .ioc")
    if mcu == "STM32F407VET6" and (values("FPU") != (flags[2],) or values("FLOAT-ABI") != (flags[3],)):
        raise ValueError("CubeMX FPU/ABI does not match STM32F407")
    return GroundCubeInputs(sources, tuple(path(value) for value in assembly_values),
                            tuple(path(value[2:], directory=True) for value in includes),
                            tuple(value[2:] for value in defines), path(linker_values[0]), flags, irq_handlers)


def _IrqHandlers_Get(root: Path, sources: tuple[str, ...]) -> tuple[str, ...]:
    iocs = tuple(root.glob("*.ioc"))
    if len(iocs) != 1:
        raise ValueError("Ground IRQ inventory requires exactly one IOC")
    fields = dict(line.split("=", 1) for line in iocs[0].read_text(encoding="utf-8-sig").splitlines() if "=" in line)
    timer_timebase = fields.get("NVIC.TimeBaseIP", "").startswith("TIM")
    handlers = [] if timer_timebase else ["SysTick_Handler"]
    if not timer_timebase and not fields.get("NVIC.SysTick_IRQn", "").startswith("true"):
        raise ValueError("Ground SysTick timebase requires its enabled interrupt")
    if timer_timebase:
        family = "stm32f1xx" if fields.get("Mcu.Family") == "STM32F1" else "stm32f4xx"
        if "Core/Src/" + family + "_hal_timebase_tim.c" not in sources:
            raise ValueError("Ground timer timebase source is missing from its build inventory")
        if not fields.get("NVIC." + fields.get("NVIC.TimeBase", ""), "").startswith("true"):
            raise ValueError("Ground timer timebase needs its enabled interrupt")
    for key, value in fields.items():
        if key.startswith("NVIC.") and key.endswith("_IRQn") and value.startswith("true"):
            name = key[5:].removesuffix("_IRQn")
            if name not in {"NonMaskableInt", "HardFault", "MemoryManagement", "BusFault", "UsageFault", "SVCall", "DebugMonitor", "PendSV", "SysTick"}:
                handlers.append(name + "_IRQHandler")
    return tuple(dict.fromkeys(handlers))


def GroundEffectiveDefinitions_Validate(defines: tuple[str, ...], mcu: str) -> None:
    expected = {"STM32F103C8T6": "STM32F103xB", "STM32F407VET6": "STM32F407xx"}[mcu]
    if expected not in defines:
        raise ValueError("Ground effective MCU definition is missing: " + expected)
    for item in defines:
        name = item.split("=", 1)[0]
        if name == "HSE_VALUE" or (re.fullmatch(r"STM32[FC][0-9]{3}[A-Za-z0-9_]+", name) and item != expected):
            raise ValueError("Ground effective macro contradicts its imported MCU/clock contract: " + item)
