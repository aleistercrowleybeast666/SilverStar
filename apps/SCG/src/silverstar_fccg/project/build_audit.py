"""Post-link static authority for exact MCU memory and bounded C stack use."""

from __future__ import annotations

import re
import subprocess
import hashlib
import json
from datetime import datetime, timezone
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
    r"LENGTH\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)([KkMm]?)\s*$"
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
        name = match.group(1)
        if name in result:
            raise ValueError('Duplicate linker MEMORY region: ' + name)
        number = match.group(3)
        result[name] = (int(match.group(2), 16), int(number, 16 if number.startswith('0x') else 10) * scale)
    return result


def MemoryReport_Build(contract: dict, linker_source: str, section_source: str, map_source: str | None = None) -> dict:
    """Account ELF VMA allocations and LMA load bytes per physical bank.

    This does not prove stack depth. Reservation sections already contribute to
    used_bytes; unassigned physical banks are not advertised as linker space.
    """
    if contract.get('schema') != 'silverstar.memory-contract/1':
        raise ValueError('Unsupported memory contract')
    declared = contract.get('regions')
    if not isinstance(declared, list) or not declared:
        raise ValueError('Exact MCU memory regions are required')
    official = {}
    for region in declared:
        if (not isinstance(region, dict) or not isinstance(region.get('name'), str)
                or type(region.get('origin')) is not int or region['origin'] < 0
                or type(region.get('bytes')) is not int or region['bytes'] <= 0
                or region['name'] in official):
            raise ValueError('Invalid or duplicate physical memory region')
        official[region['name']] = (region['origin'], region['bytes'])
    physical = sorted((origin, origin + size, name) for name, (origin, size) in official.items())
    if any(left[1] > right[0] for left, right in zip(physical, physical[1:])):
        raise ValueError('Overlapping physical memory banks')
    linked = _LinkerRegions_Parse(linker_source)
    if not linked:
        raise ValueError('Linker MEMORY is unavailable')
    errors = []
    for name, (origin, capacity) in linked.items():
        exact = official.get(name)
        if exact is None or origin != exact[0] or capacity > exact[1]:
            errors.append('LINKER_MEMORY_EXCEEDS_EXACT_MCU:' + name)
    allocations = {name: [] for name in official}
    sections = _Sections_Parse(section_source)
    if not sections:
        raise ValueError('ELF has no readable sections')
    if map_source is not None:
        errors.extend(_MapConsistencyErrors_Get(sections, linked, map_source))
    for name, size, vma, lma, allocated, loaded in sections:
        if not allocated or not size:
            continue
        addresses = [(vma, 'run')]
        if loaded and lma != vma:
            addresses.append((lma, 'load'))
        for address, role in addresses:
            bank = next((key for key, (origin, capacity) in official.items()
                         if origin <= address < origin + capacity), None)
            if bank is None:
                errors.append('SECTION_OUTSIDE_EXACT_MCU:' + name + ':' + role)
                continue
            origin, capacity = official[bank]
            link_origin, link_capacity = linked.get(bank, (origin, 0))
            if address + size > origin + capacity:
                errors.append('MEMORY_REGION_OVERFLOW:' + bank + ':' + name)
            if address < link_origin or address + size > link_origin + link_capacity:
                errors.append('SECTION_OUTSIDE_LINKER_MEMORY:' + bank + ':' + name)
            allocations[bank].append({'section': name, 'address': address,
                                      'bytes': size, 'role': role})
    regions = []
    budgets = contract.get('review_budget_bytes', {})
    for name, (origin, capacity) in official.items():
        entries = sorted(allocations[name], key=lambda row: (row['address'], row['section']))
        used = 0
        end = origin
        for row in entries:
            if row['address'] < end:
                errors.append('OVERLAPPING_ALLOCATED_SECTIONS:' + name + ':' + row['section'])
            used += max(0, row['address'] + row['bytes'] - max(end, row['address']))
            end = max(end, row['address'] + row['bytes'])
        reserved = sum(row['bytes'] for row in entries if row['section'] in
                       ('._user_heap_stack', '.stack', '.heap', '.msp_stack'))
        budget = budgets.get(name)
        if budget is not None and (type(budget) is not int or not 0 < budget <= capacity):
            raise ValueError('Invalid memory review budget: ' + name)
        regions.append({
            'name': name, 'origin': origin, 'physical_capacity_bytes': capacity,
            'linker_capacity_bytes': linked.get(name, (origin, 0))[1],
            'used_bytes': used, 'allocated_span_bytes': end - origin,
            'reserved_bytes': reserved, 'reserved_included_in_used': True,
            'physical_free_bytes': capacity - used, 'used_percent': 100.0 * used / capacity,
            'free_percent': 100.0 * (capacity - used) / capacity,
            'linker_free_bytes': linked.get(name, (origin, 0))[1] - used,
            'review_budget_bytes': budget,
            'budget_free_bytes': None if budget is None else budget - used,
            'budget_used_percent': None if budget is None else 100.0 * used / budget,
            'sections': entries,
        })
    return {'schema': 'silverstar.memory-report/1', 'target': contract.get('target'),
            'mcu': contract.get('mcu_model'), 'target_profile': contract.get('target_profile'),
            'memory_layout': contract.get('memory_layout'),
            'generation_input_sha256': contract.get('generation_input_sha256'),
            'mcu_manifest_sha256': contract.get('mcu_manifest_sha256'),
            'mcu_flags': contract.get('mcu_flags'), 'regions': regions,
            'errors': list(dict.fromkeys(errors)), 'stack_proof': 'NOT_PROVEN',
            'map_consistency': 'checked' if map_source is not None else 'NOT_PROVEN'}


def _MapConsistencyErrors_Get(sections, linked, source: str) -> list[str]:
    """Match output sections, not indented input fragments, to the same ELF."""
    rows = re.findall(r'^(\.[^\s]+)[ \t]*(?:\r?\n[ \t]+)?(0x[0-9a-fA-F]+)[ \t]+(0x[0-9a-fA-F]+)(?:[ \t]+load address[ \t]+(0x[0-9a-fA-F]+))?', source, re.MULTILINE)
    outputs = {name: (int(vma, 16), int(size, 16), int(lma, 16) if lma else int(vma, 16))
               for name, vma, size, lma in rows}
    errors = []
    for name, size, vma, lma, allocated, loaded in sections:
        if not allocated or not size: continue
        row = outputs.get(name)
        if row is None or row[:2] != (vma, size) or (loaded and row[2] != lma):
            errors.append('ELF_MAP_SECTION_MISMATCH:' + name)
    memory = re.search(r'Memory Configuration\s*\n(.*?)\nLinker script and memory map', source, re.DOTALL)
    rows = [] if memory is None else re.findall(r'^([A-Za-z][A-Za-z0-9_]*)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', memory[1], re.MULTILINE)
    map_regions = {name: (int(origin, 16), int(size, 16)) for name, origin, size in rows}
    if map_regions != linked:
        errors.append('LINKER_MAP_MEMORY_MISMATCH')
    return errors


def MemoryReport_Run(elf: Path, map_file: Path, linker: Path, contract_path: Path,
                     *, toolchain_prefix: str = 'arm-none-eabi-') -> dict:
    for path in (elf, map_file, linker, contract_path):
        if not path.is_file():
            raise ValueError('Required current memory-report input missing: ' + str(path))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    report = MemoryReport_Build(contract, linker.read_text(encoding='utf-8'),
                               _Tool_Run(toolchain_prefix + 'objdump', '-h', str(elf)),
                               map_file.read_text(encoding='utf-8', errors='strict'))
    report['artifacts'] = {key: {'path': str(path.resolve()),
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                           for key, path in (('elf', elf), ('map', map_file),
                                             ('linker', linker), ('contract', contract_path))}
    report['compiler'] = _Tool_Run(toolchain_prefix + 'gcc', '--version').splitlines()[0]
    report['reported_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['elf_modified_at_utc'] = datetime.fromtimestamp(elf.stat().st_mtime, timezone.utc).isoformat()
    return report


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
    report = MemoryReport_Build(
        {'schema': 'silverstar.memory-contract/1', 'regions': list(declared)},
        linker.read_text(encoding='utf-8'),
        _Tool_Run(toolchain_prefix + 'objdump', '-h', str(elf), environment=environment),
        map_file.read_text(encoding='utf-8', errors='strict'))
    errors.extend(report['errors'])
    occupied = {row['name']: row['used_bytes'] for row in report['regions']}
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Exact MCU / linker / ELF memory accounting')
    for name in ('elf', 'map', 'linker', 'contract', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--prefix', default='arm-none-eabi-')
    arguments = parser.parse_args()
    try:
        result = MemoryReport_Run(arguments.elf, arguments.map, arguments.linker,
                                  arguments.contract, toolchain_prefix=arguments.prefix)
        arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print('FIRMWARE_MEMORY_REPORT|' + str(arguments.output.resolve()))
        for failure in result['errors']:
            print('FAIL: ' + failure)
        raise SystemExit(1 if result['errors'] else 0)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('FAIL: memory report unavailable: ' + str(error))
        raise SystemExit(1)
