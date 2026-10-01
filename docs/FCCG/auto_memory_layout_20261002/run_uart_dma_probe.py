"""Real ARM links of synthetic UART4-6 symbols; no six-port hardware test."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DOC = Path(__file__).parent
VERSION = os.environ.get("SILVERSTAR_UART_PROBE_VERSION", "v1")
OUT = ROOT / (".work/UartDmaReview_" + VERSION)
EVIDENCE = DOC / ("uart_dma_review_" + VERSION)
OUT.mkdir(exist_ok=False)
EVIDENCE.mkdir(exist_ok=False)
base = ROOT / ".work/AutoMemoryCandidates_v8/KF6/Flight_Controller"
project = OUT / "Flight_Controller"
shutil.copytree(base, project)
prefix = "D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-"
os.environ["PATH"] = "D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;" + os.environ["PATH"]
decision = json.loads((project / "build/FCCG/SilverStar_F407/Release/auto/memory_layout/decision.json").read_text())
old_command = decision["attempts"][decision["selected"]]["command"]
objects = [item for item in old_command if item.endswith(".o")]
flags = [item for item in old_command[1:] if item not in objects and not item.startswith("-T") and item != "-o" and not item.endswith(".elf")]
names = [f"s_uart{number}_{suffix}" for number in range(4, 7) for suffix in ("rx_dma", "tx_ring", "tx_priority_ring")]
uart_object = next(project.glob("build/FCCG/SilverStar_F407/Release/auto/Platform/STM32F4/Src/platform_uart_stm32f4.o"))
# Even disabled native UART4-6 slots have linked one-byte placeholders. Rename
# those local symbols in this disposable synthetic fixture only, so added fault
# symbols cannot be hidden by duplicate nm names. Production objects are intact.
rename_command = [prefix + "objcopy", *["--redefine-sym=" + name + "=fixture_original_" + name for name in names], str(uart_object)]
subprocess.run(rename_command, check=True)
elf = Path("build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf")
report = {"scope": "synthetic linked UART4-6 symbol coverage, not hardware or real driver-instance enablement", "cases": [], "names": names, "fixture_symbol_rename_command": rename_command}
for case, section in (("valid_sram", ".dma_bss"), ("wrong_ccm", ".ccmram_bss")):
    source = project / "uart_fixture.c"
    source.write_text("\n".join(f'__attribute__((section("{section}"), aligned(8), used)) unsigned char {name}[16];' for name in names) + "\n")
    obj = project / "uart_fixture.o"
    compile_command = [prefix + "gcc", "-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard", "-Wall", "-Wextra", "-Werror", "-c", str(source), "-o", str(obj)]
    compiled = subprocess.run(compile_command, capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stderr
    link_command = [sys.executable, "Tools/auto_memory_layout.py", "--linker", "STM32F407XX_FLASH.ld", "--output", str(elf), "--compiler", prefix + "gcc", "--objdump", prefix + "objdump", "--", *objects, "uart_fixture.o", *flags,
                    *["-Wl,--undefined=" + name for name in names]]
    linked = subprocess.run(link_command, cwd=project, capture_output=True, text=True, timeout=180)
    assert linked.returncode == 0, linked.stdout + linked.stderr
    for suffix, format_name in (("hex", "ihex"), ("bin", "binary")):
        subprocess.run([prefix + "objcopy", "-O", format_name, str(project / elf), str((project / elf).with_suffix("." + suffix))], check=True)
    symbols = subprocess.check_output([prefix + "nm", "-S", "--defined-only", str(project / elf)], text=True)
    (EVIDENCE / (case + "_symbols.txt")).write_text(symbols)
    addresses = {}
    for line in symbols.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] in names:
            addresses[parts[3]] = int(parts[0], 16)
    assert len(addresses) == 9
    assert all((0x20000000 <= value < 0x20020000) if case == "valid_sram" else (0x10000000 <= value < 0x10010000) for value in addresses.values())
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "Tools/check_firmware_artifact.ps1", "-Config", "Release", "-MemoryLayout", "auto"]
    pre_fix_exit = None
    if case == "wrong_ccm":
        checker = project / "Tools/check_firmware_artifact.ps1"
        corrected = checker.read_bytes()
        baseline = ROOT / ".work/AutoMemoryCandidates_v6/KF6/Flight_Controller/Tools/check_firmware_artifact.ps1"
        try:
            checker.write_bytes(baseline.read_bytes())
            old = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=90)
            pre_fix_exit = old.returncode
            (EVIDENCE / "wrong_ccm_pre_fix.log").write_text(old.stdout + old.stderr)
            assert pre_fix_exit == 0, old.stdout + old.stderr
        finally:
            checker.write_bytes(corrected)
    result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=90)
    log = result.stdout + result.stderr
    expected = 0 if case == "valid_sram" else 1
    assert result.returncode == expected, log
    if case == "wrong_ccm":
        assert all("Symbol " + name + " is outside DMA-accessible main SRAM" in log for name in names)
    (EVIDENCE / (case + ".log")).write_text(compiled.stdout + compiled.stderr + linked.stdout + linked.stderr + log)
    report["cases"].append({"name": case, "compile_command": compile_command, "compile_exit": compiled.returncode,
        "link_command": link_command, "link_exit": linked.returncode, "artifact_command": command, "artifact_exit": result.returncode,
        "addresses": addresses, "pre_fix_artifact_exit": pre_fix_exit, "elf_sha256": hashlib.sha256((project / elf).read_bytes()).hexdigest()})
    print(case, result.returncode, addresses, flush=True)
(EVIDENCE / "results.json").write_text(json.dumps(report, indent=2) + "\n")
