"""Fresh four-algorithm layout checkpoint. No hardware and at most -j2."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "apps/FCCG/src")]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
from silverstar_fccg.project.reference import ReferenceProject_Create
import silverstar_fccg

assert Path(silverstar_fccg.__file__).is_relative_to(ROOT)
MODE = sys.argv[1] if len(sys.argv) > 1 else "matrix"
VERSION = os.environ.get("SILVERSTAR_RUN_VERSION", "v1")
EVIDENCE = Path(__file__).parent / (("evidence_gates_" if MODE == "gates" else "evidence_") + VERSION)
EVIDENCE.mkdir(exist_ok=True)
PROJECTS = ROOT / (".work/AutoMemoryCandidates_" + VERSION)
MAKE = "D:/msys64/ucrt64/bin/mingw32-make.exe"
os.environ["PATH"] = "D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;" + str(Path(sys.executable).parent) + ";" + os.environ["PATH"]
os.environ["PYTHONPATH"] = str(ROOT / "apps/FCCG/src")
manifest_path = EVIDENCE / "results.json"
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
    "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "utc": datetime.now(timezone.utc).isoformat(), "import_path": silverstar_fccg.__file__, "stages": [], "projects": {},
}
if MODE == "gates" and not manifest["projects"]:
    manifest["projects"] = json.loads((Path(__file__).parent / ("evidence_" + VERSION + "/results.json")).read_text())["projects"]


def save():
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run(name, directory, command, timeout=1500):
    if any(stage["name"] == name for stage in manifest["stages"]):
        return
    print("BEGIN " + name, flush=True)
    start = time.monotonic()
    log = EVIDENCE / (name + ".log")
    with log.open("wb") as stream:
        try:
            result = subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
    manifest["stages"].append({"name": name, "cwd": str(directory), "command": command, "exit_code": code,
                               "seconds": time.monotonic() - start, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    save()
    print(f"END {name} exit={code}", flush=True)


def generate():
    service = FccgService(ROOT / "apps/FCCG")
    for name, estimator in (("PureINS", None), ("KF6", "silverstar.algorithm.estimator.kf6"),
                            ("ESKF15", "silverstar.algorithm.estimator.eskf15"), ("SF6", "silverstar.algorithm.estimator.sf6")):
        if name in manifest["projects"]:
            continue
        model = ReferenceProject_Create("AutoMemory_" + name, catalog=service.catalog)
        previous = deepcopy(model)
        model.strategies["estimator"] = estimator
        model.build = replace(model.build, memory_layout="legacy")
        LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
        model = service.ProjectConfiguration_Reconcile(model).model
        directory = PROJECTS / name
        if directory.exists():
            raise RuntimeError("Unrecorded candidate directory already exists")
        ProjectRoot_Save(model, directory, create_new=True)
        result = TargetGeneration_Apply(model, service.catalog, service.policy, directory, TargetScope.FLIGHT, confirm_dangerous=True)
        (EVIDENCE / (name + ".ssproject")).write_text(json.dumps(model.Dictionary_Get(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["projects"][name] = {"directory": str(directory / "Flight_Controller"), "generated_files": len(result.file_hashes)}
        save()


generate()
snapshot = subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)
(EVIDENCE / "source_delta.patch").write_bytes(snapshot)
tracked = subprocess.check_output(["git", "ls-files", "apps/FCCG"], cwd=ROOT, text=True).splitlines()
tracked += subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "apps/FCCG"], cwd=ROOT, text=True).splitlines()
manifest["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in tracked}
save()
mode = MODE
if mode in ("matrix", "final"):
    for name in ("ESKF15", "KF6", "SF6", "PureINS"):
        directory = Path(manifest["projects"][name]["directory"])
        for layout in ("legacy", "auto"):
            run(name + "_arm_" + layout, directory, [MAKE, "-j2", "CONFIG=Release", "MEMORY_LAYOUT=" + layout,
                                                      "PYTHON=" + sys.executable.replace("\\", "/"), "artifact-check"])
    if mode == "final":
        directory = Path(manifest["projects"]["ESKF15"]["directory"])
        run("ESKF15_arm_eskf_window_sram", directory, [MAKE, "-j2", "CONFIG=Release", "MEMORY_LAYOUT=eskf_window_sram",
                                                         "PYTHON=" + sys.executable.replace("\\", "/"), "artifact-check", "stack-report"])
if mode in ("gates", "final"):
    for name in ("ESKF15", "KF6", "SF6", "PureINS"):
        directory = Path(manifest["projects"][name]["directory"])
        for gate in ("architecture-check", "power10-check", "host-tests"):
            run(name + "_" + gate, directory, [MAKE, "CONFIG=Release", gate])
        run(name + "_static_analysis", directory, [MAKE, "-j2", "CONFIG=Release", "MEMORY_LAYOUT=auto",
                                                      "PYTHON=" + sys.executable.replace("\\", "/"), "static-analysis"], timeout=2400)
        run(name + "_stack_report", directory, [MAKE, "CONFIG=Release", "MEMORY_LAYOUT=auto",
                                                   "PYTHON=" + sys.executable.replace("\\", "/"), "stack-report"])
if mode not in ("matrix", "gates", "final"):
    raise SystemExit("expected matrix, gates or final")
manifest["artifact_sha256"] = {str(path.relative_to(PROJECTS)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in PROJECTS.rglob("*") if path.is_file() and path.suffix in (".elf", ".map", ".hex", ".bin", ".ssdecoder", ".ssproject", ".su")}
manifest["source_unchanged_after"] = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                                          for name, digest in manifest["source_sha256"].items())
save()
