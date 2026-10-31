"""Fresh normal source-graph/ARM/gate evidence for research control interfaces."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[4]
SCG = REPO / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))


def ControlValidation_Run(revision: str) -> int:
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.tuning_bundle import TuningBundle_Read, TuningBundle_ControlCoreAttach
    if not revision.isalnum():
        raise ValueError("revision must be alphanumeric")
    work = REPO / ".work/0.1.3-treediagram-20261101" / ("control-core-" + revision)
    evidence = REPO / "docs/evidence/treediagram_algorithms_20261101" / revision
    work.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    compiler, host, make = (shutil.which(name) for name in ("arm-none-eabi-gcc", "gcc", "mingw32-make"))
    if not all((compiler, host, make)):
        raise RuntimeError("ARM GCC, Host GCC and mingw32-make are required")
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(Path(compiler).parent), str(Path(host).parent), environment["PATH"]))
    commands = []
    def Run(name, command, cwd=REPO):
        started = time.monotonic()
        with (evidence / (name + ".log")).open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        commands.append({"name": name, "command": command, "cwd": str(cwd),
            "exit_code": result.returncode, "seconds": time.monotonic() - started})
        (evidence / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
        print(name, result.returncode, flush=True)
        return result.returncode
    for tool in (compiler, host):
        Run(Path(tool).stem + "-version", [tool, "--version"])
    service = FccgService(SCG)
    inputs = []
    for kind in ("pid", "lqr"):
        fixture = SCG / f"tests/fixtures/tuning_bundle_v1/kf6-{kind}.sstuning.json"
        bundle = TuningBundle_Read(fixture)
        model = TuningBundle_ControlCoreAttach(ReferenceProject_Create("ControlCore_" + kind,
            catalog=service.catalog), service.catalog, bundle)
        destination = work / kind
        result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        inputs.append({"kind": kind, "bundle_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "model": model.Dictionary_Get(), "generation_result": str(result)})
        (evidence / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
        project = destination / "Flight_Controller"
        # Compile and execute the actual freshly generated project accessor and core.
        consumer = work / (kind + "-consumer.c")
        if kind == "pid":
            body = "ControlPidConfig c; ControlPidContext s; float y; if(ControlPid_ProjectConfigGet(&c)!=CONTROL_PID_OK || ControlPid_Start(&s,&c)!=CONTROL_PID_OK || ControlPid_Step(&s,&c,0.01f,0.0f,c.sample_period_s,&y)!=CONTROL_PID_OK) return 1; printf(\"%.9g %.9g\\n\",(double)c.kp,(double)y); return fabsf(y-0.03252f)<1e-6f?0:2;"
        else:
            gains = bundle["control_research"]["parameters"]
            expected = -gains["k_angle"] * .01 - gains["k_rate"] * .02
            body = f"ControlLqrConfig c; float x[2]={{0.01f,0.02f}},y; if(ControlLqr_ProjectConfigGet(&c)!=CONTROL_LQR_OK || ControlLqr_Step(&c,x,&y)!=CONTROL_LQR_OK) return 1; printf(\"%.9g %.9g\\n\",(double)c.gain[0],(double)y); return fabsf(y-({expected:.9e}f))<1e-6f?0:2;"
        consumer.write_text(f'#include <math.h>\n#include <stdio.h>\n#include "control_{kind}_project.h"\nint main(void){{{body}}}\n', encoding="utf-8")
        core = project / f"Algorithm/Control/{kind.upper()}"
        binary = work / (kind + "-consumer.exe")
        command = [host, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-fanalyzer",
            "-I" + str(core / "Inc"), "-I" + str(project / "Generated/Inc"),
            str(core / f"Src/control_{kind}.c"), str(core / f"Src/control_{kind}_project.c"),
            str(consumer), "-lm", "-o", str(binary)]
        if Run(kind + "-generated-consumer-compile", command) == 0:
            Run(kind + "-generated-consumer-execute", [str(binary)])
        for task in ("all", "architecture-check", "power10-check", "static-analysis", "artifact-check", "stack-report"):
            Run(kind + "-" + task, [make, "-C", str(project), "-j2", "CONFIG=Release",
                "GCC_PATH=" + str(Path(compiler).parent), "HOST_CC=" + host,
                "PYTHON=" + sys.executable, task])
    artifacts = []
    for path in work.rglob("*"):
        if path.is_file():
            artifacts.append({"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "owner": "algorithm_sdk",
                "purpose": "fresh generated validation; not a user flight candidate"})
    (evidence / "inventory.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] for row in commands))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="v1")
    raise SystemExit(ControlValidation_Run(parser.parse_args().revision))
