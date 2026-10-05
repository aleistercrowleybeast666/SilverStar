"""Generate an isolated selected navigation project and run its software gates.

No serial, debug probe, flash, deployment, or actuator access is performed.
All output, compiler temporary files and evidence stay below this repository's tests/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from silverstar_fccg.app.service import FccgService  # noqa: E402
from silverstar_fccg.project.logging import (  # noqa: E402
    LoggingProfile_AvailabilityTransitionApply,
    LoggingProfile_SelectAllAvailable,
)

VARIANTS = {
    "kf6_flight": ("silverstar.algorithm.estimator.kf6", "flight"),
    "kf6_test": ("silverstar.algorithm.estimator.kf6", "test"),
    "eskf15_flight": ("silverstar.algorithm.estimator.eskf15", "flight"),
    "eskf15_test": ("silverstar.algorithm.estimator.eskf15", "test"),
    "eskf15_no_logging": ("silverstar.algorithm.estimator.eskf15", "off"),
    "pure_ins": (None, "flight"),
}


def Project_Generate(variant: str, output: Path) -> None:
    """Use the same service and reconcile pipeline as the product GUI."""
    if not output.is_relative_to(ROOT / "tests") or output == ROOT / "tests":
        raise ValueError("Acceptance output must be below this repository's tests/")
    if output.exists():
        raise FileExistsError("Use a fresh output directory; sources are project-owned")
    service = FccgService(ROOT)
    algorithm, logging = VARIANTS[variant]
    model = service.ReferenceProject_Create("Joint_" + variant)
    previous = deepcopy(model)
    model.strategies["estimator"] = algorithm
    LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
    model = service.ProjectConfiguration_Reconcile(model).model
    if logging == "test":
        LoggingProfile_SelectAllAvailable(model, service.catalog)
    elif logging == "off":
        previous = deepcopy(model)
        model.protocols["logging"] = None
        LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
    model = service.ProjectConfiguration_Reconcile(model).model
    service.Project_Save(model, output, confirm_dangerous=True)


def Gates_Run(project: Path, host: bool, *, report_name: str = "JointAcceptance",
              keep_going: bool = False) -> int:
    if not report_name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                              for character in report_name):
        raise ValueError("Gate report name must be one local directory name")
    report = project / "build/FCCG" / report_name
    report.mkdir(parents=True, exist_ok=True)
    temporary = report / "Temp"
    temporary.mkdir(exist_ok=True)
    environment = dict(os.environ, TEMP=str(temporary), TMP=str(temporary),
                       TMPDIR=str(temporary), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    # Local toolchain discovery does not modify the machine or user PATH.
    candidates = (Path("D:/Arm GNU Toolchain/14.3 rel1/bin"), Path("D:/msys64/ucrt64/bin"))
    environment["PATH"] = os.pathsep.join(str(path) for path in candidates if path.is_dir()) + os.pathsep + environment["PATH"]
    make = shutil.which("mingw32-make", path=environment["PATH"])
    if make is None or shutil.which("arm-none-eabi-gcc", path=environment["PATH"]) is None:
        raise RuntimeError("The Windows Arm GNU and MinGW toolchains must be available")
    plan = []
    for configuration in ("Release", "Debug"):
        plan.extend((
            (configuration + "-build", configuration, ["all", "stack-report", "memory-report", "artifact-check"]),
            (configuration + "-quality", configuration, ["architecture-check", "power10-check", "static-analysis"]),
        ))
    if host:
        plan.append(("Host", "Release", ["host-tests"]))
    results = []
    for name, configuration, targets in plan:
        log = report / (name + ".log")
        command = [make, "-j4", "SHELL=cmd.exe", "CONFIG=" + configuration, *targets]
        with log.open("w", encoding="utf-8") as stream:
            run = subprocess.run(command, cwd=project, env=environment,
                                 stdout=stream, stderr=subprocess.STDOUT, check=False)
        row = {"gate": name, "command": command, "exit": run.returncode,
               "log": log.relative_to(ROOT).as_posix(),
               "sha256": hashlib.sha256(log.read_bytes()).hexdigest()}
        results.append(row)
        (report / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row), flush=True)
        if run.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-7000:], flush=True)
            if not keep_going:
                return run.returncode
    return int(any(row["exit"] != 0 for row in results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=VARIANTS)
    parser.add_argument("output", type=Path)
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--no-host", action="store_true", help="Only ARM gates; no Host pass is claimed")
    options = parser.parse_args()
    project = options.output.resolve()
    Project_Generate(options.variant, project)
    print(json.dumps({"variant": options.variant, "project": str(project), "generated": True}), flush=True)
    return 0 if options.generate_only else Gates_Run(project, not options.no_host)


if __name__ == "__main__":
    raise SystemExit(main())
