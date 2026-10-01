"""Bounded local builds and gates, with complete commands and output."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).parent / "validation_v3"
EVIDENCE.mkdir(exist_ok=False)
PROJECTS = ROOT / ".work/PostFieldMemory_d410f4a_20261001_v3"
make = shutil.which("mingw32-make")
if make is None:
    raise SystemExit("GNU Make unavailable")
snapshot = subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)
(EVIDENCE / "source_delta.patch").write_bytes(snapshot)
changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
changed += ["apps/FCCG/tests/test_static_memory_layout.py", "apps/FCCG/tests/test_firmware_identity_gate.py",
            "apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/read_firmware_identity.ps1"]
source = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in changed}
manifest = {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
            "utc": datetime.now(timezone.utc).isoformat(), "source_sha256": source,
            "source_delta_sha256": hashlib.sha256(snapshot).hexdigest(), "stages": []}


def run(name, cwd, command, timeout=600):
    print(f"BEGIN {name}", flush=True)
    start = time.monotonic()
    path = EVIDENCE / (name + ".log")
    with path.open("wb") as log:
        try:
            process = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
    manifest["stages"].append({"name": name, "cwd": str(cwd), "command": command, "exit_code": code,
                               "seconds": time.monotonic() - start, "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (EVIDENCE / "results.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"END {name} exit={code}", flush=True)
    return code


for compiler in ("arm-none-eabi-gcc", "gcc", "mingw32-make"):
    run("version_" + compiler, ROOT, [compiler, "--version"], 15)
for kind in ("kf6", "eskf"):
    project = PROJECTS / kind / "Flight_Controller"
    for gate in ("architecture-check", "power10-check", "host-tests"):
        run(kind + "_" + gate, project, [make, gate])
    run(kind + "_arm_legacy", project, [make, "-j6", "CONFIG=Release", "artifact-check"])
    if kind == "eskf":
        run("eskf_arm_window_sram", project, [make, "-j6", "CONFIG=Release", "MEMORY_LAYOUT=eskf_window_sram", "artifact-check"])
        run("eskf_static_analysis", project, [make, "-j6", "CONFIG=Release", "MEMORY_LAYOUT=eskf_window_sram", "static-analysis"], 900)
ground = PROJECTS / "kf6/Ground_Station"
for gate in ("architecture-check", "power10-check", "host-tests", "artifact-check"):
    run("ground_" + gate, ground, [make, "-j6", "CONFIG=Release", gate])

# A real legacy ELF at an experimental path must fail placement validation.
fault = PROJECTS / "wrong_layout_fault"
fault.mkdir(exist_ok=False)
eskf = PROJECTS / "eskf/Flight_Controller"
for name in ("Tools/check_firmware_artifact.ps1", "Tools/read_firmware_identity.ps1", "SilverStar.ssproject", "Generated/project_sources.mk",
             "Generated/Inc/project_flight_config.h", "STM32F407XX_FLASH.ld",
             "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c"):
    destination = fault / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(eskf / name, destination)
destination = fault / "build/FCCG/SilverStar_F407/Release/eskf_window_sram"
destination.mkdir(parents=True)
for suffix in ("elf", "map", "bin", "hex"):
    shutil.copy2(eskf / "build/FCCG/SilverStar_F407/Release" / ("SilverStar_0_1_1." + suffix), destination)
run("wrong_layout_fault", fault, ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                 "Tools/check_firmware_artifact.ps1", "-Config", "Release",
                                 "-MemoryLayout", "eskf_window_sram"])

artifacts = {}
for path in PROJECTS.rglob("*"):
    if path.is_file() and path.suffix in (".elf", ".map", ".bin", ".hex", ".ssproject", ".ssdecoder", ".su"):
        artifacts[path.relative_to(PROJECTS).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest["artifact_sha256"] = artifacts
manifest["source_unchanged_after"] = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                                          for name, digest in source.items())
(EVIDENCE / "results.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("COMPLETE; inspect every stage including expected fault failure", flush=True)
