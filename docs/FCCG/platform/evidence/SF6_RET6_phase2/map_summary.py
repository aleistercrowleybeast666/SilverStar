"""Summarize failed-link map allocations; this does not validate an ELF."""
import json
import re
from collections import defaultdict
from pathlib import Path

root = Path.cwd()
maps = {
    "baseline": root / ".work/evidence/ret6_full_baseline_failed.map",
    "compact_queues_dma": root / ".work/generated_ret6/build/FCCG/SilverStar_F103RE/Release/SilverStar_0_1_1.map",
}
reports = {}
for name, path in maps.items():
    text = path.read_text()
    section = lambda label: int(re.search(r"^" + re.escape(label) + r"\s+0x[0-9a-f]+\s+0x([0-9a-f]+)", text, re.M)[1], 16)
    data, bss = section(".data"), section(".bss")
    stack_region = re.search(r"^\._user_heap_stack\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)", text, re.M)
    used = int(stack_region[1], 16) + int(stack_region[2], 16) - 0x20000000
    region = text[text.index("\n.data "):text.index("\n._user_heap_stack")]
    rows = [(int(m[3], 16), m[1], m[4]) for m in re.finditer(
        r"^ (\.(?:bss|data)\S*)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+([^\n]+\.o)", region, re.M)]
    groups = defaultdict(int)
    for size, symbol, owner in rows:
        if "_stack" in symbol:
            group = "static_task_stacks_in_bss"
        elif "APP/Src/logger_bus.o" in owner and "storage" in symbol or (
            "APP/Src/estimator_bus.o" in owner or "APP/Src/imu_sample_bus.o" in owner) and symbol == ".bss.s_queue":
            group = "sample_and_log_queues"
        elif "logger_" in owner or "/Protocol/SSLOG/" in owner:
            group = "other_logging"
        elif "/Algorithm/" in owner or "/APP/Src/estimator_task.o" in owner or "/APP/Src/ins_task.o" in owner:
            group = "algorithm_and_origin_state"
        elif "/Platform/" in owner or "/Drivers/" in owner or "/HardwareGenerated/" in owner or "/FreeRTOS" in owner:
            group = "platform_vendor_rtos"
        elif "/Devices/" in owner:
            group = "device_state"
        else:
            group = "other"
        groups[group] += size
    groups["alignment_fill_or_unparsed"] = used - 2048 - sum(groups.values())
    groups["main_msp_reservation"] = 2048
    reports[name] = {
        "status": "FAILED_LINK_NO_ELF",
        "data": data, "bss": bss, "main_msp_reserved": 2048,
        "ram_required": used, "ret6_ram_limit": 65536,
        "overflow": used - 65536, "twenty_percent_spare_target": 52428,
        "groups": {key: {"bytes": value, "percent_of_64k": round(value * 100 / 65536, 3)} for key, value in groups.items()},
        "largest_symbols": [{"bytes": size, "symbol": symbol, "object": owner} for size, symbol, owner in sorted(rows, reverse=True)[:24]],
    }
reports["ram_net_reduction"] = reports["baseline"]["ram_required"] - reports["compact_queues_dma"]["ram_required"]
output = root / ".work/evidence/map_symbol_distribution.json"
output.write_text(json.dumps(reports, indent=2) + "\n")
print(json.dumps({key: {k: v for k, v in report.items() if k not in ("groups", "largest_symbols")} if isinstance(report, dict) else report for key, report in reports.items()}, indent=2))
