"""Freeze only completed stages while the finite v6 driver continues."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/FCCG/src"))
from silverstar_fccg.project.build_audit import BuildAudit_Run

DOC = Path(__file__).parent
OUT = DOC / "checkpoint_resume"
OUT.mkdir(exist_ok=False)
(OUT / ".gitattributes").write_text("* -text\n")
live = json.loads((DOC / "evidence_v6/results.json").read_text())
prefix = "D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-"
metadata = json.loads((ROOT / "apps/FCCG/plugins/builtin/silverstar_mcu_stm32f407vet6/plugin.json").read_text())["metadata"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


report = {
    "utc": datetime.now(timezone.utc).isoformat(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "scope": "Completed v6 stages only; ongoing finite driver is not a completed suite. No hardware.",
    "driver_session": 91514,
    "driver_command": [str(Path(sys.executable)), "docs/FCCG/auto_memory_layout_20261002/run_checkpoint.py", "final"],
    "driver_environment": {"SILVERSTAR_RUN_VERSION": "v6"},
    "completed_stages": live["stages"],
    "fccg_source_sha256": live["source_sha256"],
    "fccg_source_unchanged_at_capture": all(digest(ROOT / name) == value for name, value in live["source_sha256"].items()),
    "resources": {}, "tools": {},
    "pending": "Remaining v6 four-algorithm builds, manual-layout build, Host, architecture, emitted PoT, real analyzer and selected-ELF stack reports. Read live evidence_v6/results.json for later completion; do not infer it from this snapshot.",
    "manual_acceptance": "NOT PROVEN: critical-contract semantic review, complete stack/WCET bounds and hardware/flight evidence remain outside text/tool passes.",
}
for key, command in {
    "python": [sys.executable, "--version"],
    "arm_gcc": [prefix + "gcc", "--version"],
    "arm_ld": [prefix + "ld", "--version"],
    "host_gcc": ["D:/msys64/ucrt64/bin/gcc.exe", "--version"],
    "make": ["D:/msys64/ucrt64/bin/mingw32-make.exe", "--version"],
}.items():
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    report["tools"][key] = {"command": command, "exit_code": result.returncode, "output": result.stdout + result.stderr}
archive = OUT / "completed_artifacts.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as packed:
    for stage in live["stages"]:
        log = DOC / "evidence_v6" / (stage["name"] + ".log")
        assert digest(log) == stage["log_sha256"]
        packed.write(log, "logs/" + log.name)
        if "_arm_" not in stage["name"] or stage["exit_code"] != 0:
            continue
        name, _, layout = stage["name"].partition("_arm_")
        project = Path(live["projects"][name]["directory"])
        build = project / "build/FCCG/SilverStar_F407/Release"
        if layout != "legacy":
            build = build / layout
        elf = next(build.glob("*.elf"))
        audit = BuildAudit_Run(elf, elf.with_suffix(".map"), project / "STM32F407XX_FLASH.ld", build,
                               metadata, toolchain_prefix=prefix)
        details = {"audit": asdict(audit), "artifact_sha256": {}, "stack_files_sha256": {}}
        for suffix in ("elf", "map", "bin", "hex"):
            path = elf.with_suffix("." + suffix)
            details["artifact_sha256"][suffix] = digest(path)
            packed.write(path, name + "/" + layout + "/" + path.name)
        for tool, args, label in (("objdump", ["-h"], "sections"), ("nm", ["-S", "--defined-only"], "symbols")):
            command = [prefix + tool, *args, str(elf)]
            result = subprocess.run(command, capture_output=True, timeout=20)
            assert result.returncode == 0
            packed.writestr(name + "/" + layout + "/" + label + ".txt", result.stdout)
        for path in build.rglob("*.su"):
            # Do not accidentally include the auto subtree when auditing legacy.
            if layout == "legacy" and "auto" in path.relative_to(build).parts:
                continue
            relative = path.relative_to(build).as_posix()
            details["stack_files_sha256"][relative] = digest(path)
            packed.write(path, name + "/" + layout + "/su/" + relative)
        decision = build / "memory_layout/decision.json"
        if decision.exists():
            details["decision"] = json.loads(decision.read_text())
            for path in decision.parent.iterdir():
                if path.is_file():
                    packed.write(path, name + "/" + layout + "/memory_layout/" + path.name)
        report["resources"][stage["name"]] = details
    for path in sorted(DOC.glob("tests_*.log")):
        packed.write(path, "regressions/" + path.name)
    for relative in ("catalog_fault_v1", "catalog_fault_v2"):
        for path in (DOC / relative).rglob("*"):
            if path.is_file():
                packed.write(path, path.relative_to(DOC).as_posix())
    for relative in ("review-critical.txt", "run_checkpoint.py", "run_catalog_probe.py", "capture_resume.py"):
        packed.write(DOC / relative, "review/" + relative)
    packed.write(DOC / "evidence_v5/results.json", "prior_v5/results.json")
    packed.write(DOC / "evidence_v5/driver_stop.json", "prior_v5/driver_stop.json")
    packed.write(DOC / "evidence_v5/ESKF15_host-tests.log", "prior_v5/ESKF15_host-tests.log")
    for name, project in live["projects"].items():
        path = Path(project["directory"]) / "SilverStar.ssproject"
        packed.write(path, "configurations/" + name + ".ssproject")
report["archive_sha256"] = digest(archive)
(OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"snapshot": str(OUT), "stages": [(s["name"], s["exit_code"]) for s in live["stages"]],
                  "sources_unchanged": report["fccg_source_unchanged_at_capture"], "archive_sha256": report["archive_sha256"]}, indent=2))
