from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError


def ArtifactMemoryReportSummary_Encode(output: str, expected_root: Path, target: str = 'flight') -> str:
    """Freeze the verified report's bank figures in the target's quality record."""
    paths = re.findall(r'^FIRMWARE_MEMORY_REPORT\|(.+)$', output, re.MULTILINE)
    if len(paths) != 1:
        return ''
    try:
        path = Path(paths[0].strip())
        policy = WorkspacePolicy(expected_root)
        if not path.is_absolute() or policy.Path_Resolve(path, allow_root=False) != path.absolute():
            return ''
        if path.stat().st_size > 2 * 1024 * 1024:
            return ''
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('schema') != 'silverstar.memory-report/1' or report['target'] != target:
            return ''
        artifacts = report['artifacts']
        for name in ('elf', 'map', 'linker', 'contract'):
            artifact = artifacts[name]
            artifact_path = Path(artifact['path'])
            if not artifact_path.is_absolute() or policy.Path_Resolve(artifact_path, allow_root=False) != artifact_path.absolute():
                return ''
            with artifact_path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != artifact['sha256']:
                    return ''
        fields = ('name', 'physical_capacity_bytes', 'used_bytes', 'physical_free_bytes',
                  'allocated_span_bytes', 'reserved_bytes', 'review_budget_bytes',
                  'budget_free_bytes', 'linker_capacity_bytes', 'linker_free_bytes')
        value = {key: report[key] for key in ('target', 'mcu', 'generation_input_sha256', 'errors', 'stack_proof')}
        value['regions'] = [{key: region[key] for key in fields} for region in report['regions']]
        value['report_path'] = str(path.resolve())
        value['report_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        value['artifacts'] = artifacts
        # Generated builds place an optional memory-layout directory after the
        # configuration. Bind identity to the verified ELF below this project,
        # not an arbitrary ancestor called Release or the current UI selection.
        elf_parts = Path(artifacts['elf']['path']).resolve().relative_to(expected_root.resolve()).parts
        value['configuration'] = (elf_parts[3] if len(elf_parts) in (5, 6) and
            elf_parts[:2] == ('build', 'FCCG') and elf_parts[3] in ('Release', 'Debug') else '')
        summary = 'artifact_memory_v1=' + json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        return summary if ArtifactMemoryReportSummary_Decode(summary) else ''
    except (OSError, ValueError, KeyError, TypeError, WorkspacePolicyError):
        return ''


def ArtifactMemoryReportSummary_Decode(summary: str) -> dict | None:
    if not summary.startswith('artifact_memory_v1=') or len(summary) > 65536:
        return None
    try:
        value = json.loads(summary.partition('=')[2])
        if value['target'] not in ('flight', 'ground') or not isinstance(value['mcu'], str):
            return None
        if value.get('configuration', '') not in ('', 'Release', 'Debug'):
            return None
        if not re.fullmatch(r'[0-9a-f]{64}', value['generation_input_sha256']):
            return None
        if type(value['errors']) is not list or not all(type(item) is str for item in value['errors']):
            return None
        if type(value['regions']) is not list or not 1 <= len(value['regions']) <= 32:
            return None
        names = set()
        for region in value['regions']:
            name = region['name']
            if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', name) or name in names:
                return None
            names.add(name)
            for key in ('physical_capacity_bytes', 'used_bytes',
                        'allocated_span_bytes', 'reserved_bytes', 'linker_capacity_bytes'):
                if type(region[key]) is not int or region[key] < 0:
                    return None
            if any(type(region[key]) is not int for key in ('physical_free_bytes', 'linker_free_bytes')):
                return None
            capacity, used = region['physical_capacity_bytes'], region['used_bytes']
            if capacity <= 0 or region['physical_free_bytes'] != capacity - used:
                return None
            budget = region['review_budget_bytes']
            if budget is not None and (type(budget) is not int or budget <= 0 or
                                      region['budget_free_bytes'] != budget - used):
                return None
            if budget is None and region['budget_free_bytes'] is not None:
                return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


def ArtifactMemoryMarginLevel_Get(remaining: int, capacity: int) -> str:
    if capacity <= 0 or remaining < 0 or remaining > capacity:
        raise ValueError("Invalid memory region")
    return "error" if remaining * 100 < capacity * 10 else "warning" if remaining * 100 <= capacity * 20 else "success"


def ArtifactMemorySummary_Encode(output: str) -> str:
    values = []
    for name in ("FLASH", "main SRAM", "CCMRAM"):
        matches = re.findall(re.escape(name) + r"\s+used=(\d+)\s+remaining=(\d+)\s+capacity=(\d+)", output)
        if len(matches) != 1:
            return ""
        used, remaining, capacity = map(int, matches[0])
        if capacity <= 0 or remaining != max(0, capacity - used):
            return ""
        values.extend((used, remaining, capacity))
    return "artifact_memory=" + "/".join(map(str, values))


def ArtifactMemorySummary_Decode(summary: str) -> tuple[tuple[int, int, int], ...]:
    if re.fullmatch(r"artifact_memory=\d+(?:/\d+){8}", summary) is None:
        return ()
    values = tuple(map(int, summary.partition("=")[2].split("/")))
    regions = tuple(values[i:i+3] for i in (0, 3, 6))
    if any(capacity <= 0 or remaining != max(0, capacity-used)
           for used, remaining, capacity in regions):
        return ()
    return regions
