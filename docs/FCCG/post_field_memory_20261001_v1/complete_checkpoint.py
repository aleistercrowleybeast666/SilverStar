"""Finish the checkpoint with the final template and supported Ground gates."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).parent / "checkpoint_final"
PROJECTS = ROOT / ".work/PostFieldMemory_d410f4a_20261001_v3"
sys.path.insert(0, str(ROOT / "apps/FCCG/src"))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.project.build_audit import BuildAudit_Run
from silverstar_fccg.project.model import ProjectModel_Load

EVIDENCE.mkdir(exist_ok=False)
make = shutil.which("mingw32-make")
results = []


def run(name, cwd, command, timeout=600):
    print("BEGIN " + name, flush=True)
    start = time.monotonic()
    log = EVIDENCE / (name + ".log")
    with log.open("wb") as output:
        try:
            process = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
    results.append({"name": name, "command": command, "cwd": str(cwd), "exit_code": code,
                    "seconds": time.monotonic() - start, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    (EVIDENCE / "commands.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"END {name} exit={code}", flush=True)
    if code != 0:
        raise SystemExit(f"Checkpoint blocked by {name}; inspect its complete log")


service = FccgService(ROOT / "apps/FCCG")
for kind in ("kf6", "eskf"):
    project = PROJECTS / kind / "Flight_Controller"
    model = ProjectModel_Load(project / "SilverStar.ssproject")
    assembler = ProjectAssembler(WorkspacePolicy(project.parent), service.catalog)
    plan = assembler.Plan(model, project)
    if not plan.valid:
        raise SystemExit("Final template regeneration is invalid")
    # Only generated build metadata may change. No payload replacement and no
    # compiled C/header/assembler change can be inferred from a metadata rerun.
    altered = [operation.target for operation in plan.operations if operation.operation in ("MODIFY", "DELETE")]
    if any(path.endswith((".c", ".h", ".s")) for path in altered):
        raise SystemExit("Compiler inputs changed; a broader new validation run is required")
    (EVIDENCE / (kind + "_regeneration.json")).write_text(json.dumps(altered, indent=2) + "\n", encoding="utf-8")
    assembler.Apply(model, plan, confirm_dangerous=True)
    run(kind + "_arm_final_legacy", project, [make, "-j6", "CONFIG=Release", "artifact-check"])
    if kind == "eskf":
        run("eskf_arm_final_window_sram", project, [make, "-j6", "CONFIG=Release", "MEMORY_LAYOUT=eskf_window_sram", "artifact-check"])
    detail = project / "build/FCCG/Host/Tests/host-tests-detail.log"
    if detail.is_file():
        shutil.copy2(detail, EVIDENCE / (kind + "_host_detail.log"))

ground = PROJECTS / "kf6/Ground_Station"
run("ground_arm_all", ground, [make, "-j6", "all"])
audit = BuildAudit_Run(ground / "build/ground.elf", ground / "build/ground.map",
                       ground / "STM32F103XX_FLASH.ld", ground / "build",
                       dict(service.catalog.Component_Get("silverstar.mcu.stm32f103c8t6").metadata))
(EVIDENCE / "ground_build_audit.json").write_text(json.dumps(asdict(audit), indent=2) + "\n", encoding="utf-8")
if audit.errors:
    raise SystemExit("Ground linked artifact audit failed: " + repr(audit.errors))

patch = subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)
(EVIDENCE / "source_delta.patch").write_bytes(patch)
artifacts = {}
for path in PROJECTS.rglob("*"):
    if path.is_file() and path.suffix in (".elf", ".map", ".bin", ".hex", ".su", ".ssproject", ".ssdecoder"):
        artifacts[path.relative_to(PROJECTS).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
(EVIDENCE / "artifact_sha256.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
print("Checkpoint final builds complete", flush=True)
