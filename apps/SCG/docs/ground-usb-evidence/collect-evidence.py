"""Collect linked artifact and compiler stack evidence without hardware access."""
from pathlib import Path
import hashlib, json, re, subprocess, sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
bin_dir = Path("D:/Arm GNU Toolchain/14.3 rel1/bin")
results = []
for name in ("f103-usb", "f103-uart", "f407-usb"):
    target = root / ("generated-" + name) / "Ground_Station"
    elf = target / "build/ground.elf"
    graph = json.loads((target / "Generated/ground_source_graph.json").read_text())
    size = subprocess.check_output([str(bin_dir / "arm-none-eabi-size.exe"), str(elf)], text=True)
    text_size, data_size, bss_size = map(int, size.splitlines()[1].split()[:3])
    symbols = subprocess.check_output([str(bin_dir / "arm-none-eabi-nm.exe"), "-S", "--size-sort", str(elf)], text=True)
    (root / (name + "-symbols.txt")).write_text(symbols, encoding="utf8")
    disasm = subprocess.check_output([str(bin_dir / "arm-none-eabi-objdump.exe"), "-d", str(elf)], text=True)
    (root / (name + "-disassembly.txt")).write_text(disasm, encoding="utf8")
    frames = {}
    for file in (target / "build").rglob("*.su"):
        if "analysis" in file.parts:
            continue
        for line in file.read_text().splitlines():
            source, usage, kind = line.split("\t")
            function = source.rsplit(":", 1)[-1]
            frames[function] = {"bytes": int(usage), "kind": kind, "source": source}
    calls = {}; current = None; opaque = set()
    for line in disasm.splitlines():
        entry = re.match(r"[0-9a-f]+ <([^>]+)>:", line)
        if entry:
            current = entry[1]; calls.setdefault(current, set())
        if current:
            call = re.search(r"\bbl(?:\.w|x)?\s+[0-9a-f]+\s+<([^>]+)>", line)
            if call: calls[current].add(call[1])
            if re.search(r"\bblx\s+r", line): opaque.add(current)
    def path_sample(function, seen=frozenset()):
        if function in seen: return (0, [function + " (cycle)"])
        suffix = max((path_sample(child, seen | {function}) for child in calls.get(function, ())), default=(0, []), key=lambda item: item[0])
        return (frames.get(function, {}).get("bytes", 0) + suffix[0], [function] + suffix[1])
    selected = ["main", "GroundBridge_Process", "PcByteStream_Write", "PcByteStream_Read", "PcByteStream_OnUsbReceive", "USB_LP_CAN1_RX0_IRQHandler", "OTG_FS_IRQHandler"]
    known_paths = {entry: {"known_frame_sum": path_sample(entry)[0], "path": path_sample(entry)[1]} for entry in selected if entry in calls}
    reserved_stack = 2048
    item = {"case": name, "sources": len(graph["sources"]), "asm_sources": graph["asm_sources"], "linker_script": graph["linker_script"],
        "artifact_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in (elf, target / "build/ground.bin", target / "Generated/ground_source_graph.json")},
        "text": text_size, "data": data_size, "bss_including_linker_reserved_stack": bss_size,
        "reserved_stack": reserved_stack, "reserved_heap": 0,
        "ram_unallocated": (20480 if name.startswith("f103") else 131072) - data_size - bss_size,
        "first_party_critical_frames": {entry: frames[entry] for entry in selected if entry in frames},
        "all_frames": frames, "known_direct_call_path_samples": known_paths,
        "indirect_call_functions": sorted(opaque),
        "stack_status": "NOT PROVEN: frame sums are partial observations, not upper bounds; vendor callbacks, library functions without .su, tail calls and nested IRQs require complete review and hardware high-water measurement"}
    results.append(item)
(root / "linked-evidence.json").write_text(json.dumps(results, indent=2), encoding="utf8")
for item in results:
    print(item["case"], "text/data/bss", item["text"], item["data"], item["bss_including_linker_reserved_stack"], "unallocatedRAM", item["ram_unallocated"])
    print("partial direct call paths", item["known_direct_call_path_samples"])
