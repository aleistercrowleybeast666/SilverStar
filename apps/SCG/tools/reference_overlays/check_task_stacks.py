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
STARTUP_CALLBACK_SOURCES = (
    "Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c",
    "Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c",
)
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


def FunctionBody_Get(source: str, name: str) -> str:
    """Canonical reviewed binding body; comments/formatting earn no exception."""
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", source)
    if match is None:
        raise ValueError("Missing callback binding body: " + name)
    depth = 1
    for end in range(match.end(), len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return re.sub(r"\s+", "", source[match.start():end + 1])
    raise ValueError("Unclosed callback binding body: " + name)


def MpuCallbackBindings_Resolve(root, sources, instructions, edges, indirect, nm, prefix, elf):
    """Resolve a reviewed immutable MPU profile and its concrete I2C bus.

    Source body fingerprints preserve the reviewed provenance, not merely
    function names. The selected graph, actual linked read-only profile bytes,
    profile getter literal and direct initialization callers must agree. Any
    extra indirect instruction, caller or changed binding requires review.
    """
    optional = {"SensorImu_Verify", "SensorImu_ProcessConfigure", "SensorImu_Read"}
    if not optional.intersection(indirect):
        return []
    project = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf-8"))
    imus = {device["plugin"] for device in project["components"]["devices"]
            if device["plugin"].startswith("silverstar.device.imu.")}
    if imus != {"silverstar.device.imu.mpu6050"}:
        raise ValueError("Unreviewed SensorImu selected profile binding")
    imu = "Devices/SensorBus/Src/sensor_imu.c"
    bus = "Devices/SensorBus/Src/sensor_register_bus.c"
    adapter = "Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c"
    instance = "Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c"
    profile = "Devices/IMU/MPU6050/Src/mpu6050_device.c"
    # Each body was reviewed as part of the binding proof. They establish
    # immutable profile assignment and read/write targets, and guarded optional
    # calls. This deliberately fails after a semantic change until re-reviewed.
    reviewed = {
        imu: {
            "SensorImu_Init": "da3bd34fc08e65fb32e5a72b68f60a0f2a08eafd2c630a92914621c949878453",
            "SensorImu_Verify": "8b6786ccf36eec5eddabb1878139eb463d345eefa88a573e34c7ddf8bf7a3a04",
            "SensorImu_ProcessConfigure": "6eb4ee07a620e1c9a2ea532046a25bd3f1c4595ac90461fd9e17f76e02dd71d2",
            "SensorImu_Read": "f97d205c95377a02e4d1a4283d7018688f67caef15d10942bb5bd8aa7843c579",
        },
        bus: {
            "SensorRegister_Read": "29b0b73fcbc3f3f3d248d790bab51870a564852c4eec5a4b1d265be19af3f971",
            "SensorRegister_Write": "b08b754cf52dc6558f9d3af40ea3db36a09331df7774ba3a96987f62bfd82929",
        },
        adapter: {
            "SensorImuAdapter_PrepareI2c": "652772579357ed30ad767d5d49a6888a691e30ea07b5addd7f12a89b76b4c1a4",
        },
        instance: {
            "Mpu6050ImuInstance_Init": "4776cec45657cafb0e67926917d05f1cf0b553fbe650ef81fbfcf0b0b322c614",
        },
    }
    proofs = []
    for path, bodies in reviewed.items():
        if path not in sources:
            raise ValueError("Missing selected callback binding source: " + path)
        text = (root / path).read_text(encoding="utf-8")
        for name, expected in bodies.items():
            actual = hashlib.sha256(FunctionBody_Get(text, name).encode()).hexdigest()
            if actual != expected:
                raise ValueError("Changed reviewed callback binding body: " + name)
        proofs.append({"source": path, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    if profile not in sources:
        raise ValueError("Missing selected MPU profile source")
    text = (root / profile).read_text(encoding="utf-8")
    if FunctionBody_Get(text, "Mpu6050_ProfileGet") != "Mpu6050_ProfileGet(void){return&s_profile;}":
        raise ValueError("Changed immutable MPU profile getter")
    table = re.search(r"static\s+const\s+SensorImuProfile\s+s_profile\s*=\s*\{(.*?)\n};", text, re.DOTALL)
    if table is None or re.search(r"\.(prepare|frame_read|extra_verify)\s*=", table[1]):
        raise ValueError("Unreviewed MPU optional profile callbacks")
    # ARM AAPCS32 layout: five byte fields follow the name pointer, then float,
    # then the three callbacks at 16/20/24. Reject a changed prefix/type layout.
    header = re.sub(r"/\*.*?\*/", "", (root / "Devices/SensorBus/Inc/sensor_imu.h").read_text(encoding="utf-8"), flags=re.DOTALL)
    layout = ("constchar*name;uint8_tregister_width;uint8_ti2c_dummy_bytes;"
              "uint8_tauxiliary_address_7bit;uint8_tspi_dummy_bytes;"
              "uint8_tauxiliary_spi_dummy_bytes;floataccel_full_scale_g;"
              "SensorImuPrepareprepare;SensorImuFrameReadframe_read;SensorImuExtraVerifyextra_verify;")
    if layout not in re.sub(r"\s+", "", header):
        raise ValueError("Changed MPU profile callback layout")
    symbols = [parts for line in nm.splitlines() if len(parts := line.split()) == 4 and parts[3] == "s_profile"]
    if len(symbols) != 1 or symbols[0][2].lower() != "r" or int(symbols[0][1], 16) < 28:
        raise ValueError("MPU profile is not one linked read-only object")
    address = int(symbols[0][0], 16)
    data = Command_Read([prefix + "objdump", "-s", "--start-address=" + hex(address),
                         "--stop-address=" + hex(address + 28), str(elf)], root)
    if "file format elf32-littlearm" not in data:
        raise ValueError("Unreviewed MPU profile ELF ABI")
    bytes_by_address = {}
    for line in data.splitlines():
        if match := re.match(r"\s*([0-9a-f]+)\s+((?:[0-9a-f]{8}\s*){1,4})", line):
            start = int(match[1], 16)
            for offset, byte in enumerate(bytes.fromhex(match[2])):
                bytes_by_address[start + offset] = byte
    if any(bytes_by_address.get(address + offset) != 0 for offset in range(16, 28)):
        raise ValueError("Linked MPU optional callbacks are not NULL")
    getter_words = {int(args, 16) for op, args in instructions.get("Mpu6050_ProfileGet", []) if op == ".word"}
    if address not in getter_words:
        raise ValueError("Linked MPU getter does not bind the reviewed profile")
    init_callers = {name for name, calls in edges.items() if "SensorImu_Init" in calls}
    prepare_callers = {name for name, calls in edges.items() if "SensorImuAdapter_PrepareI2c" in calls}
    if init_callers != {"SensorImuAdapter_PrepareI2c"} or prepare_callers != {"Mpu6050ImuInstance_Init"}:
        raise ValueError("Unreviewed linked SensorImu initialization provenance")
    resolved = {"SensorRegister_Read": "SensorImuAdapter_ReadRegister",
                "SensorRegister_Write": "SensorImuAdapter_WriteRegister"}
    for name in optional | set(resolved):
        if name not in indirect:
            continue
        calls = [op for op, args in instructions[name]
                 if (op == "blx" and "<" not in args) or (op.startswith("bx") and args.strip() != "lr")]
        if len(calls) != 1:
            raise ValueError("Extra indirect MPU callback instruction: " + name)
        if name in resolved:
            callee = resolved[name]
            if callee not in instructions:
                raise ValueError("Missing concrete MPU register callback: " + callee)
            edges[name].add(callee)
        indirect.remove(name)
    return [{"kind": "immutable_mpu6050_i2c", "profile_address": hex(address),
             "null_callbacks": ["prepare", "frame_read", "extra_verify"],
             "bus_edges": resolved, "reviewed_sources": proofs}]


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
            if (
                (op.startswith("b") or op in ("cbz", "cbnz"))
                and (match := re.search(r"<([^>+]+)(?:\+[^>]+)?>", args))
                and (match[1] != name or op in ("bl", "bl.w", "blx"))
                and match[1] in instructions
            ):
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
            elif re.search(r"\[sp[^\]]*\]!", args) or re.match(r"sp,", args) and op.startswith(("sub", "mov", "bic")):
                unbounded.add(name)
        if name not in frames:
            frames[name] = frame
            library_frames[name] = frame

    sd_sources = [source for source in sources if source.endswith("/sd_diskio.c") or
                  source == "Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c"]
    if len(sd_sources) > 1:
        raise ValueError("Multiple selected SD_Driver providers")
    if sd_sources:
        sd_source = root / sd_sources[0]
        source = sd_source.read_text(encoding="utf-8")
        table = re.search(r"(?:const\s+)?Diskio_drvTypeDef\s+SD_Driver\s*=\s*\{(.*?)\};", source, re.DOTALL)
        fatfs = next(iter(root.glob("HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c")), root / "FATFS/App/fatfs.c")
        if not table or not fatfs.exists() or not re.search(r"FATFS_LinkDriver\(&SD_Driver,", fatfs.read_text(encoding="utf-8")):
            raise ValueError("Cannot verify the single SD_Driver callback binding")
        # F1's R0.11 ABI declares the table non-const. This is a fixed selected
        # provider, not permission for another registration/callback registry.
        table_code = re.sub(r"/\*.*?\*/|//[^\n]*", "", table[1], flags=re.DOTALL)
        # Existing F4 glue conditionally declares the write/ioctl ABI slots.
        # Admit only those exact guards, with their targets actually linked.
        for macro, callback in (("_USE_WRITE", "SD_write"), ("_USE_IOCTL", "SD_ioctl")):
            guard = rf"#if\s+{macro}\s*==\s*1\s*\n\s*{callback},\s*\n#endif"
            if re.search(guard, table_code):
                if callback not in instructions:
                    raise ValueError("Missing linked conditional SD callback: " + callback)
                table_code = re.sub(guard, callback + ",", table_code)
        entries = re.findall(r"\b[A-Za-z]\w*\b", table_code)
        if entries != list(DISK_CALLBACKS.values()):
            raise ValueError("Unreviewed selected SD_Driver callback table")
        registrations = {caller for caller, callees in edges.items() if "FATFS_LinkDriver" in callees}
        if registrations != {"MX_FATFS_Init"}:
            raise ValueError("Unreviewed SD_Driver registration caller")
        if any(re.search(r"\bSD_Driver\s*\.\s*\w+\s*=", (root / path).read_text(encoding="utf-8")) for path in sources):
            raise ValueError("Mutable SD_Driver callback assignment")
        if sd_sources[0] == "Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c":
            # R0.11's writable table cannot earn an immutable-object claim.
            # Freeze the reviewed registration/dispatch implementation and all
            # source references, then verify initialized callback pointers in
            # the actual ELF. This does not prove freedom from RAM corruption.
            reviewed_fatfs = {
                "Middlewares/Third_Party/FatFs/src/ff_gen_drv.c":
                    "36679af13a80db6a2fe0fb27918a2e420ad662e28f9491e59c91c2931e75e609",
                "Middlewares/Third_Party/FatFs/src/diskio.c":
                    "b70fbf239fe462cb5f1918f77d04b7d68cf8f71eadf3d9778e7e55abecb75fc7",
            }
            for path, expected in reviewed_fatfs.items():
                if path not in sources:
                    raise ValueError("Missing selected F1 FatFs binding source")
                canonical = re.sub(r"/\*.*?\*/|//[^\n]*", "", (root / path).read_text(encoding="utf-8"), flags=re.DOTALL)
                if hashlib.sha256(re.sub(r"\s+", "", canonical).encode()).hexdigest() != expected:
                    raise ValueError("Changed reviewed F1 FatFs binding source: " + path)
            if FunctionBody_Get(fatfs.read_text(encoding="utf-8"), "MX_FATFS_Init") != "MX_FATFS_Init(void){retSD=FATFS_LinkDriver(&SD_Driver,SDPath);}":
                raise ValueError("Changed reviewed F1 SD registration")
            allowed_refs = {sd_sources[0], fatfs.relative_to(root).as_posix()}
            for path in sources:
                code = re.sub(r"/\*.*?\*/|//[^\n]*", "", (root / path).read_text(encoding="utf-8"), flags=re.DOTALL)
                refs = len(re.findall(r"\bSD_Driver\b", code))
                if refs != (1 if path in allowed_refs else 0):
                    raise ValueError("Unreviewed F1 SD_Driver source reference: " + path)
            extended_callers = {caller for caller, callees in edges.items() if "FATFS_LinkDriverEx" in callees}
            expected_extended = {"FATFS_LinkDriver"} if "FATFS_LinkDriverEx" in instructions else set()
            if extended_callers != expected_extended:
                raise ValueError("Unreviewed F1 extended SD registration caller")
            symbols = {parts[3]: parts for line in nm.splitlines() if len(parts := line.split()) == 4}
            if "SD_Driver" not in symbols or symbols["SD_Driver"][2] != "D" or int(symbols["SD_Driver"][1], 16) != 20:
                raise ValueError("Changed linked F1 SD_Driver table ABI")
            address = int(symbols["SD_Driver"][0], 16)
            data = Command_Read([prefix + "objdump", "-s", "--start-address=" + hex(address),
                                 "--stop-address=" + hex(address + 20), str(elf)], root)
            raw = b"".join(bytes.fromhex(match[1]) for line in data.splitlines()
                if (match := re.match(r"\s*[0-9a-f]+\s+((?:[0-9a-f]{8}\s*){1,4})", line)))
            expected = b"".join((int(symbols[entry][0], 16) | 1).to_bytes(4, "little") for entry in entries if entry in symbols)
            if "file format elf32-littlearm" not in data or len(expected) != 20 or raw != expected:
                raise ValueError("Linked F1 SD callback pointers differ from reviewed table")
        for caller, callee in DISK_CALLBACKS.items():
            if caller in indirect and callee in instructions and re.search(rf"\b{callee}\b", table[1]):
                edges[caller].add(callee)
                indirect.remove(caller)

    # SystemDeviceStartup has one immutable operations table per linked device.
    # Resolve every callback to the selected tables, taking the deeper
    # branch. Refuse new callers or tables until their binding is reviewed.
    if "SystemDeviceStartup_Tick" in instructions:
        startup_callers = {caller for caller, callees in edges.items()
                           if "SystemDeviceStartup_Init" in callees}
        selected_startup_sources = [source for source in STARTUP_CALLBACK_SOURCES if source in sources]
        if not selected_startup_sources:
            raise ValueError("Missing reviewed startup callback sources in the selected graph")
        expected_callers = set()
        if STARTUP_CALLBACK_SOURCES[0] in selected_startup_sources:
            expected_callers.add("Jy901bStartup_Init")
        if STARTUP_CALLBACK_SOURCES[1] in selected_startup_sources:
            expected_callers.add("NeoM9nStartup_Init")
        # The reviewed M9N recovery reuses controller.config, including the
        # original immutable operations table. O2 inlines RecoveryBegin into
        # Tick; Debug retains its separate frame. Admit exactly one of these
        # known caller sets; keep unknown callers/tables fatal.
        reviewed_callers = (expected_callers,)
        if STARTUP_CALLBACK_SOURCES[1] in selected_startup_sources:
            reviewed_callers = (
                expected_callers | {"NeoM9nStartup_Tick"},
                expected_callers | {"NeoM9nStartup_RecoveryBegin"},
            )
        if startup_callers not in reviewed_callers:
            raise ValueError("Unreviewed device startup operation binding: " +
                             repr(sorted(startup_callers)))
        callbacks: set[str] = set()
        for source_name in selected_startup_sources:
            source_text = (root / source_name).read_text(encoding="utf-8")
            tables = re.findall(
                r"static\s+const\s+SystemDeviceStartupOperations\s+s_operations\s*=\s*\{(.*?)\};",
                source_text, re.DOTALL)
            if len(tables) != 1 or len(entries := re.findall(r"\b[A-Za-z]\w*\b", tables[0])) != 7:
                raise ValueError("Unreviewed device startup operation table: " + source_name)
            if not re.search(r"config\.operations\s*=\s*&s_operations\s*;", source_text):
                raise ValueError("Unbound device startup operation table: " + source_name)
            if not all(entry in instructions for entry in entries):
                raise ValueError("Missing linked device startup callback: " + source_name)
            if source_name.endswith("neo_m9n_startup.c"):
                recovery = re.search(
                    r"static void NeoM9nStartup_RecoveryBegin\(.*?\n}\s*",
                    source_text, re.DOTALL)
                if (not recovery or
                        len(re.findall(r"config\s*=\s*context->controller\.config\s*;",
                                       recovery[0])) != 1 or
                        re.search(r"config\.operations\s*=", recovery[0])):
                    raise ValueError("Unreviewed M9N recovery operation binding")
            callbacks.update(entries)
        for caller in ("SystemDeviceStartup_ProbeTick", "SystemDeviceStartup_ReadTick",
                       "SystemDeviceStartup_ApplyTick", "SystemDeviceStartup_Tick"):
            if caller in indirect:
                edges[caller].update(callbacks)
                indirect.remove(caller)

    callback_bindings = MpuCallbackBindings_Resolve(
        root, sources, instructions, edges, indirect, nm, prefix, elf)

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
            "callback_bindings": callback_bindings,
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
