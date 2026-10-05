"""Bounded, deterministic link-time placement of audited CPU-only BSS.

No probe link enlarges physical memory. Every candidate uses the target's actual
MEMORY declaration, original startup intervals and original stack reservation.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path
import re
import subprocess
import importlib.util
import sys
import traceback


def AuditModule_Get():
    """Generated copy of the existing FCCG resource audit; one parser owner."""
    generated = Path(__file__).resolve().parents[1] / "Generated/memory_audit.py"
    if generated.is_file():
        spec = importlib.util.spec_from_file_location("silverstar_memory_audit", generated)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        # The generated directory is an audited source inventory. Loading the
        # shared parser must not create an unowned __pycache__ there.
        exec(compile(generated.read_bytes(), str(generated), "exec"), module.__dict__)
        return module
    # Repository tests import the tool directly, before project generation.
    # Standalone generated projects cannot silently invent a replacement audit.
    from silverstar_fccg.project import build_audit
    return build_audit


PREFIX = ".bss.silverstar_auto_"
# Exact object suffix, exact private symbol; no general CPU/DMA classification.
GROUPS = {
    "eskf_work": ("Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.o", "s_work"),
    "eskf_history": ("Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.o", "s_history"),
    "eskf_window": ("Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.o", "s_eskf_window"),
    "kf_replay": ("APP/Src/estimator_task.o", "s_replay_storage"),
    "nav_health": ("System/Src/system_navigation_health.o", "s_groups"),
}
MAX_CANDIDATES = 32


def Tool_Run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(f"Tool failed ({result.returncode}): {command}\n{result.stdout}{result.stderr}")
    return result.stdout


def Regions_Parse(script: str) -> dict[str, tuple[int, int]]:
    declared = AuditModule_Get()._LinkerRegions_Parse(script)
    regions = {name: region for name, region in declared.items() if name in ("RAM", "CCMRAM")}
    declarations = re.findall(r"^\s*(RAM|CCMRAM)\s*\([^)]*\)\s*:\s*ORIGIN", script, re.MULTILINE)
    if len(declarations) != len(regions) or any(size <= 0 for _, size in regions.values()):
        raise ValueError("Invalid, unreadable or repeated physical memory region")
    if "RAM" not in regions:
        raise ValueError("Auto requires a literal RAM MEMORY region; unsupported target syntax")
    if "CCMRAM" in regions:
        a, b = regions["RAM"], regions["CCMRAM"]
        if max(a[0], b[0]) < min(a[0] + a[1], b[0] + b[1]):
            raise ValueError("Overlapping RAM regions")
        # Only the reviewed F407 independent physical banks are enabled. A
        # disjoint CPU address range does not prove independent storage (F413).
        if a[0] != 0x20000000 or a[1] > 128 * 1024 or b[0] != 0x10000000 or b[1] > 64 * 1024:
            raise ValueError("Unreviewed CCM physical layout or alias; dual-region auto supports F407 only")
    names = set(re.findall(r"^\s*(\w+)\s*\([^)]*\)\s*:\s*ORIGIN", script, re.MULTILINE))
    if names - {"RAM", "CCMRAM", "FLASH"}:
        raise ValueError("Additional regions/aliases require a reviewed physical-memory model")
    return regions


def Groups_Inspect(objdump: str, objects: list[str]) -> dict[str, dict]:
    groups = {}
    # Inspect only possible owners plus all other objects for illegal auto tags.
    for obj in objects:
        dump = Tool_Run([objdump, "-h", "-t", obj])
        sections = re.findall(
            r"^\s*\d+\s+(\S+)\s+([\da-fA-F]+)\s+[\da-fA-F]+\s+[\da-fA-F]+\s+[\da-fA-F]+\s+2\*\*(\d+)\s*\n([^\n]*)",
            dump, re.MULTILINE,
        )
        for section, size_hex, alignment, flags in sections:
            if not section.startswith(PREFIX):
                continue
            group = section[len(PREFIX):]
            if group not in GROUPS:
                raise ValueError(f"Unapproved auto section: {section}")
            owner, symbol = GROUPS[group]
            normalized = Path(obj).as_posix()
            if not normalized.endswith("/" + owner) or group in groups:
                raise ValueError(f"Auto group {group} has a wrong or duplicate owner: {obj}")
            entries = re.findall(
                r"^([\da-fA-F]+)\s+l\s+O\s+" + re.escape(section) + r"\s+([\da-fA-F]+)\s+(\S+)\s*$",
                dump, re.MULTILINE,
            )
            size = int(size_hex, 16)
            if entries != [("00000000", size_hex, symbol)] or size <= 0 or int(alignment) < 3:
                raise ValueError(f"Auto group {group} must contain exactly its aligned private BSS object")
            if "CONTENTS" in flags or "ALLOC" not in flags:
                raise ValueError(f"Auto group {group} is not zero-initialized BSS; data moves are unsupported")
            groups[group] = {"object": normalized, "symbol": symbol, "size": size, "alignment": 2 ** int(alignment)}
        for group, (owner, symbol) in GROUPS.items():
            if Path(obj).as_posix().endswith("/" + owner) and re.search(r"\s+l\s+O\s+\S+\s+[\da-fA-F]+\s+" + symbol + r"\s*$", dump, re.MULTILINE):
                if group not in groups:
                    raise ValueError(f"Preserved payload lacks auto marker for {symbol}; use a fresh project")
    return dict(sorted(groups.items()))


def Script_Render(script: str, assignment: dict[str, str], regions: dict) -> str:
    if "CCMRAM" not in regions:
        # Generic .bss.* is covered by the target's unchanged normal clear loop.
        if (any(region != "RAM" for region in assignment.values()) or "*(.bss*)" not in script or
                re.search(r">\s*CCMRAM\b", script)):
            raise ValueError("No-CCM target must cover auto BSS with its ordinary .bss wildcard")
        return script
    for region, marker in (("CCMRAM", "/* SILVERSTAR_AUTO_CCM_BSS */"),
                           ("RAM", "/* SILVERSTAR_AUTO_RAM_BSS */")):
        if script.count(marker) != 1:
            raise ValueError("Preserved linker lacks audited auto BSS hooks; use a fresh project")
        entries = "\n    ".join(f"*({PREFIX}{group})" for group, target in sorted(assignment.items()) if target == region)
        script = script.replace(marker, marker + "\n    " + entries)
    return script


def SourceOwners_Check(project: Path, groups: dict, linker: Path | None = None) -> None:
    """A preserved user edit cannot inherit a CPU-only proof from a symbol name."""
    identity = json.loads((project / "SilverStar.ssproject").read_text(encoding="utf-8"))
    provenance = identity.get("component_provenance", {})
    # Include the algorithm kernels/helpers and core interfaces called by the
    # private owners. A user-modified callee could otherwise start using DMA.
    for component, entry in provenance.items():
        if (component not in ("silverstar.core.0_1_0", "silverstar.platform.api") and
                not component.startswith(("silverstar.algorithm.", "silverstar.mcu."))):
            continue
        for relative, expected in entry.get("files", {}).items():
            if Path(relative).suffix.lower() not in (".c", ".h", ".s", ".ld"):
                continue
            source = (project / relative).resolve()
            if not source.is_relative_to(project.resolve()):
                raise ValueError(f"CPU-only source proof path escapes project: {relative}")
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError(f"CPU-only source proof does not cover preserved/edited helper {relative}; use audited fresh payload or legacy")
    if linker is not None:
        # Bind the actual linker argument, not only an unused canonical file.
        # An alternate no-CCM script must not invent capacity for an F407 model.
        relative = linker.resolve().relative_to(project.resolve()).as_posix()
        mcu = identity.get("components", {}).get("mcu")
        expected = provenance.get(mcu, {}).get("files", {}).get(relative)
        if not mcu or not expected or hashlib.sha256(linker.read_bytes()).hexdigest() != expected:
            raise ValueError("Actual linker lacks selected-MCU source proof; use audited fresh payload or legacy")
    for group, info in groups.items():
        relative = GROUPS[group][0][:-2] + ".c"
        owner = "silverstar.algorithm.estimator.eskf15" if group.startswith("eskf_") else "silverstar.core.0_1_0"
        expected = provenance.get(owner, {}).get("files", {}).get(relative)
        source = project / relative
        if not expected or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"CPU-only source proof does not cover preserved/edited {relative}; use audited fresh payload or legacy")
        info["source_sha256"] = expected


def Usage_Read(objdump: str, elf: Path, regions: dict) -> dict[str, int]:
    dump = Tool_Run([objdump, "-h", str(elf)])
    usage = {name: 0 for name in regions}
    for _, size, address, _, allocated, _ in AuditModule_Get()._Sections_Parse(dump):
        if size == 0 or not allocated:
            continue
        for name, (origin, capacity) in regions.items():
            if origin <= address < origin + capacity:
                if address + size > origin + capacity:
                    raise ValueError(f"Linked section exceeds {name}")
                usage[name] = max(usage[name], address + size - origin)
    return usage


def Score_Get(usage: dict[str, int], regions: dict, assignment: dict) -> tuple:
    used = [Fraction(usage[name], capacity) for name, (_, capacity) in sorted(regions.items())]
    # Physical feasibility is provided by GNU ld. Minimize worst utilization,
    # then spread; ties prefer fewer moves from legacy CCM, then sorted names.
    return max(used), max(used) - min(used), sum(value == "RAM" for value in assignment.values()), tuple(assignment.items())


def LinkedGroups_Check(objdump: str, elf: Path, groups: dict, assignment: dict, regions: dict) -> None:
    dump = Tool_Run([objdump, "-t", str(elf)])
    symbols = {}
    for address, section, size, name in re.findall(
        r"^([\da-fA-F]+)\s+.*?\s+(\.\S+|\*ABS\*)\s+([\da-fA-F]+)\s+(\S+)\s*$", dump, re.MULTILINE,
    ):
        symbols.setdefault(name, []).append((int(address, 16), int(size, 16), section))
    for group, info in groups.items():
        entries = symbols.get(info["symbol"], [])
        if len(entries) != 1:
            raise ValueError(f"Linked whitelist symbol missing or ambiguous: {info['symbol']}")
        address, size, section = entries[0]
        region = assignment[group]
        start, capacity = regions[region]
        bounds = ("_sccmram_bss", "_eccmram_bss") if region == "CCMRAM" else ("_sbss", "_ebss")
        if any(len(symbols.get(bound, [])) != 1 for bound in bounds):
            raise ValueError(f"Missing startup zero bounds for {group}")
        if not (size == info["size"] and address % info["alignment"] == 0 and
                start <= address and address + size <= start + capacity and
                symbols[bounds[0]][0][0] <= address and address + size <= symbols[bounds[1]][0][0]):
            raise ValueError(f"Placement, size, alignment or startup zero bounds failed: {group}")
        info.update(address=address, region=region, output_section=section, zero_bounds=bounds)


def LayoutCandidates_Link(args: argparse.Namespace) -> None:
    output = Path(args.output)
    directory = output.parent / "memory_layout"
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "decision.json"
    # Never let a failed relink leave a prior successful artifact/report behind.
    for old in (output, report_path):
        old.unlink(missing_ok=True)
    script = Path(args.linker).read_text(encoding="utf-8")
    regions = Regions_Parse(script)
    objects = [value for value in args.command if value.endswith(".o")]
    if not objects or any(value.startswith("-T") or value == "-o" for value in args.command):
        raise ValueError("Auto requires explicit objects and owns the linker/output options")
    groups = Groups_Inspect(args.objdump, objects)
    SourceOwners_Check(Path(getattr(args, "project", ".")), groups, Path(args.linker))
    names = sorted(groups)
    choices = ("CCMRAM", "RAM") if "CCMRAM" in regions else ("RAM",)
    attempts, successful = [], []
    if len(choices) ** len(names) > MAX_CANDIDATES:
        raise ValueError("Auto candidate bound exceeded")
    print(f"MEMORY_LAYOUT:auto groups={len(names)} max_candidates={len(choices) ** len(names)}", flush=True)
    if "CCMRAM" not in regions:
        print("MEMORY_LAYOUT: target has no CCM; all CPU-only objects use ordinary SRAM", flush=True)
    for index, values in enumerate(product(choices, repeat=len(names))):
        if index >= MAX_CANDIDATES:
            raise ValueError("Auto candidate bound exceeded")
        assignment = dict(zip(names, values))
        candidate = directory / f"candidate_{index:02d}.ld"
        candidate.write_text(Script_Render(script, assignment, regions), encoding="utf-8")
        command = [args.compiler, *args.command, "-T" + candidate.as_posix(), "-o", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (directory / f"candidate_{index:02d}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        record = {"index": index, "assignment": assignment, "exit_code": result.returncode, "command": command}
        if result.returncode == 0:
            usage = Usage_Read(args.objdump, output, regions)
            record["usage"] = usage
            successful.append((Score_Get(usage, regions, assignment), index, assignment, candidate))
        attempts.append(record)
    report = {"version": 1, "policy": "physical-fit/minimax-utilization/spread/legacy-tie", "max_candidates": MAX_CANDIDATES,
              "regions": regions, "groups": groups, "attempts": attempts,
              "linker_sha256": hashlib.sha256(Path(args.linker).read_bytes()).hexdigest(),
              "object_sha256": {obj: hashlib.sha256(Path(obj).read_bytes()).hexdigest() for obj in objects}}
    if not successful:
        output.unlink(missing_ok=True)
        report["status"] = "failed-no-physical-fit"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise ValueError(f"No candidate linked within physical RAM; see {directory} (real ld failures retained)")
    _, index, assignment, candidate = min(successful)
    # One final real link ensures ELF and map belong to the selected assignment.
    Tool_Run([args.compiler, *args.command, "-T" + candidate.as_posix(), "-o", str(output)])
    LinkedGroups_Check(args.objdump, output, groups, assignment, regions)
    usage = Usage_Read(args.objdump, output, regions)
    report.update(status="linked", selected=index, assignment=assignment, usage=usage,
                  elf_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  selected_linker_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"MEMORY_LAYOUT:auto selected={index} attempts={len(attempts)} decision={report_path}", flush=True)
    for group, info in groups.items():
        print(f"MEMORY_LAYOUT: {group} {info['symbol']} bytes={info['size']} address=0x{info['address']:08x} -> {info['region']}", flush=True)
    for name, (_, capacity) in sorted(regions.items()):
        remaining = capacity - usage[name]
        color = "red" if remaining * 100 < capacity * 10 else "yellow" if remaining * 100 <= capacity * 20 else "green"
        print(f"MEMORY_LAYOUT: region={name} occupied={usage[name]} spare={remaining} capacity={capacity} margin={color}", flush=True)
        if color != "green":
            print(f"WARNING: {name} margin <=20%; aim for green. Spare bytes are not a stack/timing proof.", flush=True)


def Layout_Link(args: argparse.Namespace) -> None:
    """Publish no successful artifact when any link/audit/report step fails."""
    try:
        LayoutCandidates_Link(args)
    except BaseException:
        output = Path(args.output)
        directory = output.parent / "memory_layout"
        failure = traceback.format_exc()
        output.unlink(missing_ok=True)
        (directory / "decision.json").unlink(missing_ok=True)
        # Keep all candidate linker scripts/logs, and record late audit or
        # report-write failures even when GNU ld itself returned success.
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "failure.log").write_text(failure, encoding="utf-8")
        raise


def Main_Run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linker", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--objdump", required=True)
    parser.add_argument("--project", default=".")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command.pop(0)
    try:
        Layout_Link(args)
    except (ValueError, OSError, ImportError, subprocess.TimeoutExpired) as error:
        Path(args.output).unlink(missing_ok=True)
        print(f"MEMORY_LAYOUT:auto FAIL: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(Main_Run())
