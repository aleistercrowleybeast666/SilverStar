"""Post-link static authority for exact MCU memory and bounded C stack use."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


_SECTION = re.compile(
    r"^\s*\d+\s+(\S+)\s+([0-9a-fA-F]+)\s+"
    r"([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+"
)
_MEMORY = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*\([^)]*\)\s*:\s*"
    r"ORIGIN\s*=\s*(0x[0-9A-Fa-f]+)\s*,\s*"
    r"LENGTH\s*=\s*([0-9]+)([KkMm]?)\s*$"
)
_FORBIDDEN_HEAP = frozenset(("malloc", "calloc", "realloc", "free", "alloca"))


@dataclass(frozen=True, slots=True)
class MemoryRegionAudit:
    name: str
    official_bytes: int
    linker_bytes: int
    occupied_bytes: int


@dataclass(frozen=True, slots=True)
class BuildAudit:
    regions: tuple[MemoryRegionAudit, ...]
    text_bytes: int
    data_bytes: int
    bss_bytes: int
    stack_files: int
    largest_function_stack_bytes: int
    errors: tuple[str, ...]


def _LinkerRegions_Parse(source: str) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for line in source.splitlines():
        match = _MEMORY.fullmatch(line)
        if match is None:
            continue
        scale = {"": 1, "K": 1024, "M": 1048576}[match.group(4).upper()]
        result[match.group(1)] = (int(match.group(2), 16), int(match.group(3)) * scale)
    return result


def _Sections_Parse(source: str) -> tuple[tuple[str, int, int, int, bool, bool], ...]:
    lines = source.splitlines()
    result: list[tuple[str, int, int, int, bool, bool]] = []
    for index, line in enumerate(lines[:-1]):
        match = _SECTION.match(line)
        if match is None:
            continue
        flags = set(lines[index + 1].strip().split(", "))
        result.append((
            match.group(1), int(match.group(2), 16),
            int(match.group(3), 16), int(match.group(4), 16),
            "ALLOC" in flags, "LOAD" in flags,
        ))
    return tuple(result)


def _Tool_Run(
    tool: str, *args: str, environment: Mapping[str, str] | None = None,
) -> str:
    result = subprocess.run(
        [tool, *args], check=True, capture_output=True, text=True,
        env=environment,
    )
    return result.stdout


def BuildAudit_Run(
    elf: Path, map_file: Path, linker: Path, stack_root: Path,
    exact_metadata: dict, *, toolchain_prefix: str = "arm-none-eabi-",
    environment: Mapping[str, str] | None = None,
) -> BuildAudit:
    errors: list[str] = []
    if not elf.is_file() or not map_file.is_file() or not linker.is_file():
        raise ValueError("ELF, MAP and selected linker script are required")
    declared = exact_metadata.get("memory_regions", ())
    official = {
        item["name"]: (item["origin"], item["bytes"])
        for item in declared if isinstance(item, dict)
    }
    if not official:
        raise ValueError("Exact MCU has no official memory-region contract")
    linked = _LinkerRegions_Parse(linker.read_text(encoding="utf-8"))
    if not linked:
        raise ValueError("Selected linker script has no readable MEMORY regions")
    occupied = {name: 0 for name in official}
    for name, (origin, capacity) in linked.items():
        expected = official.get(name)
        if expected is None or origin != expected[0] or capacity > expected[1]:
            errors.append(f"LINKER_MEMORY_EXCEEDS_EXACT_MCU:{name}")
    for name in official:
        if name not in linked:
            errors.append(f"LINKER_MEMORY_REGION_MISSING:{name}")
    sections = _Sections_Parse(_Tool_Run(
        toolchain_prefix + "objdump", "-h", str(elf), environment=environment,
    ))
    for section_name, size, vma, lma, allocated, loaded in sections:
        if size == 0 or not allocated:
            continue
        found = False
        for address in (vma, lma) if loaded and lma != vma else (vma,):
            region_name = next(
                (name for name, (origin, capacity) in official.items()
                 if origin <= address < origin + capacity), None,
            )
            if region_name is None:
                errors.append(f"SECTION_OUTSIDE_EXACT_MCU:{section_name}")
                continue
            origin, capacity = official[region_name]
            occupied[region_name] = max(
                occupied[region_name], address + size - origin,
            )
            if occupied[region_name] > capacity:
                errors.append(f"MEMORY_REGION_OVERFLOW:{region_name}")
            found = True
        if not found:
            errors.append(f"SECTION_UNMAPPED:{section_name}")
    size_lines = _Tool_Run(
        toolchain_prefix + "size", str(elf), environment=environment,
    ).splitlines()
    if len(size_lines) < 2:
        raise ValueError("arm-none-eabi-size returned no section totals")
    totals = size_lines[1].split()
    text_bytes, data_bytes, bss_bytes = map(int, totals[:3])
    symbols = _Tool_Run(
        toolchain_prefix + "nm", str(elf), environment=environment,
    )
    for line in symbols.splitlines():
        name = line.split()[-1] if line.split() else ""
        if name in _FORBIDDEN_HEAP:
            errors.append(f"DYNAMIC_ALLOCATION_LINKED:{name}")
    stack_files = list(stack_root.rglob("*.su"))
    if not stack_files:
        errors.append("STACK_USAGE_MISSING")
    for object_file in stack_root.rglob("*.o"):
        if (
            not object_file.name.startswith("startup_")
            and not object_file.with_suffix(".su").is_file()
        ):
            errors.append(f"STACK_USAGE_MISSING:{object_file.name}")
    largest_stack = 0
    for path in stack_files:
        for row in path.read_text(encoding="utf-8", errors="replace").splitlines():
            fields = row.split("\t")
            if len(fields) < 3:
                errors.append(f"STACK_USAGE_UNREADABLE:{path.name}")
                continue
            if "dynamic" in fields[2]:
                errors.append(f"DYNAMIC_STACK_USAGE:{path.name}:{fields[0]}")
            try:
                largest_stack = max(largest_stack, int(fields[1]))
            except ValueError:
                errors.append(f"STACK_USAGE_UNREADABLE:{path.name}")
    return BuildAudit(
        regions=tuple(
            MemoryRegionAudit(name, capacity, linked.get(name, (0, 0))[1],
                              occupied[name])
            for name, (_origin, capacity) in official.items()
        ),
        text_bytes=text_bytes,
        data_bytes=data_bytes,
        bss_bytes=bss_bytes,
        stack_files=len(stack_files),
        largest_function_stack_bytes=largest_stack,
        errors=tuple(dict.fromkeys(errors)),
    )
