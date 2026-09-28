"""Conservative, reproducible stack budgets from GCC .su and the linked Arm ELF.

No LTO is used by the generated Make project. Inline frames are already in .su.
All direct calls and cross-function branches are conservatively nested, including
tail calls (overestimates). Linked library frames without .su use the sum of all
constant stack decrements/pushes in disassembly, also an overestimate. Unknown
indirect calls, dynamic frames, recursion and unaccounted SP writes fail closed.
This is a worst-known static budget, not a hardware high-water measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


TASKS = {
    "Device": ("AppTask_Device", "s_device_stack"),
    "INS": ("AppTask_Ins", "s_ins_stack"),
    "Estimator": ("AppTask_Estimator", "s_estimator_stack"),
    "Flight": ("AppTask_Flight", "s_flight_stack"),
    "Logger": ("AppTask_Logger", "s_logger_stack"),
    "Serial": ("AppTask_Serial", "s_serial_stack"),
    "Telemetry": ("AppTask_Telemetry", "s_telemetry_stack"),
    "Idle": ("prvIdleTask", "s_idle_task_stack"),
}
# FatFs diskio.c calls the single CubeMX SD_Driver table. Verify this binding
# below before adding the edges; no arbitrary plugin callback is assumed safe.
DISK_CALLBACKS = {
    "disk_initialize": "SD_initialize", "disk_status": "SD_status",
    "disk_read": "SD_read", "disk_write": "SD_write", "disk_ioctl": "SD_ioctl",
}
# Cortex-M4F: hardware core + FP exception frame (104), software r4-r11/lr
# and s16-s31 (100), worst alignment padding (4), rounded up to 256 bytes.
# Nested ISR frames use MSP, whose separate linker reservation is audited too.
CONTEXT_BYTES = 256
MIN_MARGIN_BYTES = 256


def Command_Read(command: list[str], root: Path) -> str:
    return subprocess.run(command, cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="strict").stdout


def RegisterBytes_Get(registers: str, width: int) -> int:
    total = 0
    for item in registers.strip("{}").split(","):
        item = item.strip()
        if "-" in item:
            first, last = item.split("-")
            total += int(re.search(r"\d+", last)[0]) - int(re.search(r"\d+", first)[0]) + 1
        elif item:
            total += 1
    return total * width


def StackReport_Build(root: Path, config: str, prefix: str) -> dict:
    target = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf-8"))["build"]["target_profile"]
    build = (root / "build/FCCG" / target / config).resolve()
    build.relative_to(root.resolve())
    elfs = list(build.glob("*.elf"))
    if len(elfs) != 1:
        raise ValueError("Expected exactly one linked ELF in the selected configuration")
    elf = elfs[0]
    disassembly = Command_Read([prefix + "objdump", "-d", str(elf)], root)
    nm = Command_Read([prefix + "nm", "-S", "--defined-only", str(elf)], root)
    sizes = {parts[3]: int(parts[1], 16) for line in nm.splitlines()
             if len(parts := line.split()) == 4}
    frames: dict[str, int] = {}
    unbounded: set[str] = set()
    # Consume the resolved generator graph, not stale objects left by an earlier
    # configuration. Every compiled C source must supply GCC's own frame report;
    # disassembly fallback is reserved for linked assembly/runtime libraries.
    manifest = (root / "Generated/project_sources.mk").read_text(encoding="utf-8")
    block = re.search(r"(?ms)^C_SOURCES \+= \\\n(.*?)(?:\n\n|\Z)", manifest)
    if block is None:
        raise ValueError("Missing resolved C source graph")
    sources = [line.strip().removesuffix("\\").strip() for line in block[1].splitlines()]
    su_paths = [build / Path(source).with_suffix(".su") for source in sources]
    for source, path in zip(sources, su_paths):
        path.resolve().relative_to(build)
        if not source.endswith(".c") or not path.is_file():
            raise ValueError("Missing source stack report; rebuild: " + source)
    for path in su_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            location, count, kind = line.split("\t")
            name = location.rsplit(":", 1)[1]
            frames[name] = max(frames.get(name, 0), int(count))
            if kind not in ("static", "dynamic,bounded"):
                unbounded.add(name)
    instructions: dict[str, list[tuple[str, str]]] = {}
    for line in disassembly.splitlines():
        if match := re.match(r"^[0-9a-f]+ <([^>]+)>:", line):
            name = match[1]
            instructions[name] = []
        elif match := re.match(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{4,8}\s+)+(\S+)\s*(.*)", line):
            instructions[name].append((match[1], match[2]))

    edges: dict[str, set[str]] = {}
    indirect: set[str] = set()
    library_frames: dict[str, int] = {}
    for name, rows in instructions.items():
        edges[name] = set()
        frame = 0
        for op, args in rows:
            if (op.startswith("b") or op in ("cbz", "cbnz")) and (match := re.search(r"<([^>+]+)(?:\+[^>]+)?>", args)):
                if (match[1] != name or op in ("bl", "bl.w", "blx")) and match[1] in instructions:
                    edges[name].add(match[1])
            if (op == "blx" and "<" not in args) or (op.startswith("bx") and args.strip() != "lr"):
                indirect.add(name)
            if name in frames:
                continue
            if op.startswith(("push", "stmdb")) and "{" in args:
                frame += RegisterBytes_Get(args[args.index("{"):], 4)
            elif op.startswith("vpush"):
                frame += RegisterBytes_Get(args, 8 if "d" in args else 4)
            elif op.startswith("sub") and re.match(r"sp,\s*(?:sp,\s*)?#", args):
                frame += int(re.search(r"#(0x[0-9a-f]+|\d+)", args)[1], 0)
            elif re.search(r"\[sp,\s*#-(0x[0-9a-f]+|\d+)\]!", args):
                frame += int(re.search(r"#-(0x[0-9a-f]+|\d+)", args)[1], 0)
            elif re.search(r"\[sp[^\]]*\]!", args):
                unbounded.add(name)
            elif re.match(r"sp,", args) and op.startswith(("sub", "mov", "bic")):
                unbounded.add(name)
        if name not in frames:
            frames[name] = frame
            library_frames[name] = frame

    sd_source = root / "HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c"
    if not sd_source.exists():
        sd_source = root / "FATFS/Target/sd_diskio.c"
    if sd_source.exists():
        source = sd_source.read_text(encoding="utf-8")
        table = re.search(r"const\s+Diskio_drvTypeDef\s+SD_Driver\s*=\s*\{(.*?)\};", source, re.S)
        fatfs = next(iter(root.glob("HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c")), root / "FATFS/App/fatfs.c")
        if not table or not fatfs.exists() or not re.search(r"FATFS_LinkDriver\(&SD_Driver,", fatfs.read_text(encoding="utf-8")):
            raise ValueError("Cannot verify the single SD_Driver callback binding")
        for caller, callee in DISK_CALLBACKS.items():
            if caller in indirect and callee in instructions and re.search(rf"\b{callee}\b", table[1]):
                edges[caller].add(callee)
                indirect.remove(caller)

    def Closure_Get(name: str) -> set[str]:
        seen: set[str] = set()
        pending = [name]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(edges.get(node, ()))
        return seen

    memo: dict[str, tuple[int, list[str]]] = {}
    def Budget_Get(name: str, visiting: tuple[str, ...] = ()) -> tuple[int, list[str]]:
        if name in visiting:
            raise ValueError("Recursive stack path: " + " -> ".join((*visiting, name)))
        if name in indirect or name in unbounded:
            raise ValueError("Unresolved stack usage: " + name)
        if name not in memo:
            children = [Budget_Get(child, (*visiting, name)) for child in sorted(edges.get(name, ()))]
            count, path = max(children, default=(0, []), key=lambda item: item[0])
            memo[name] = (frames[name] + count, [name, *path])
        return memo[name]

    tasks = []
    for label, (entry, stack) in TASKS.items():
        if entry not in instructions:
            if stack in sizes:
                raise ValueError("Task stack exists without entry: " + label)
            continue
        if stack not in sizes:
            raise ValueError("Missing configured stack symbol: " + stack)
        count, chain = Budget_Get(entry)
        estimate = count + CONTEXT_BYTES
        tasks.append({"task": label, "configured_bytes": sizes[stack],
                      "call_chain_bytes": count, "context_bytes": CONTEXT_BYTES,
                      "worst_known_bytes": estimate, "margin_bytes": sizes[stack] - estimate,
                      "chain": [{"function": node, "frame_bytes": frames[node]} for node in chain],
                      "passes": sizes[stack] - estimate >= MIN_MARGIN_BYTES})
    init_closure = Closure_Get("AppTasks_Init")
    align_closure = Closure_Get("SystemAlignment_Start")
    checks = {
        "indicator_in_production_init": "SystemIndicator_Init" in init_closure and "AppTasks_Init" in Closure_Get("main"),
        "alignment_start_deferred": "SystemAlignment_Process" not in align_closure,
        "flight_processes_alignment": "SystemAlignment_Process" in Closure_Get("AppTask_Flight"),
        "communication_does_not_process_alignment": all(
            "SystemAlignment_Process" not in Closure_Get(entry)
            for entry in ("AppTask_Telemetry", "AppTask_Serial")),
        "all_enabled_tasks_budgeted": {
            name for name in instructions if name.startswith("AppTask_") or name in ("prvIdleTask", "prvTimerTask")
        } == {TASKS[row["task"]][0] for row in tasks},
    }
    reachable = set().union(*(Closure_Get(TASKS[row["task"]][0]) for row in tasks))
    return {"schema": "silverstar.stack-budget/1", "configuration": config,
            "elf": str(elf.relative_to(root)), "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
            "compiler": Command_Read([prefix + "gcc", "--version"], root).splitlines()[0],
            "su_files": len(su_paths), "minimum_margin_bytes": MIN_MARGIN_BYTES,
            "method": __doc__, "checks": checks, "tasks": tasks,
            "library_frames": {name: count for name, count in sorted(library_frames.items()) if name in reachable},
            "hardware_high_water_marks": "not measured; use normal stack snapshot on SS0.5",
            "passes": all(checks.values()) and all(row["passes"] for row in tasks)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", choices=("Release", "Debug"), default="Release")
    parser.add_argument("--prefix", default="arm-none-eabi-")
    arguments = parser.parse_args()
    root = arguments.project.resolve(strict=True)
    print("FCCG_PROGRESS|STACK_REPORT|PLAN|1", flush=True)
    print("FCCG_PROGRESS|STACK_REPORT|BEGIN|1|1|ELF and stack budget", flush=True)
    report = StackReport_Build(root, arguments.config, arguments.prefix)
    destination = root / Path(report["elf"]).parent / "stack-budget.json"
    destination.resolve().relative_to(root)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["tasks"]:
        print(f"{row['task']}: configured={row['configured_bytes']} estimate={row['worst_known_bytes']} margin={row['margin_bytes']}")
    print(json.dumps(report["checks"], indent=2))
    if report["passes"]:
        print("FCCG_PROGRESS|STACK_REPORT|DONE|1|1|ELF and stack budget")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
