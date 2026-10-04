from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def test_gnss_outage_keeps_fresh_tilt_available(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = Path(os.environ.get("SILVERSTAR_GNSS_TILT_SOURCE",
        root / "plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/flight_task.c"))
    text = source.read_text(encoding="utf-8")
    start = text.index("static void FlightTask_RecoveryEstimatorInputApply(")
    end = text.index("\nstatic void FlightTask_RecoveryInitialInputApply(", start)
    extracted = tmp_path / "flight_task_recovery_extract.h"
    constants = "\n".join(line for line in text.splitlines()
                          if line.startswith("#define FLIGHT_TASK_RECOVERY_"))
    extracted.write_text(constants + "\n" + text[start:end], encoding="utf-8")

    configured = os.environ.get("SILVERSTAR_GNSS_TILT_GENERATED_PROJECT")
    if configured:
        project = Path(configured).resolve()
    else:
        from silverstar_fccg.app.service import FccgService

        service = FccgService(root)
        model = service.Project_Open(root / "tests/fixtures/radio_handshake.ssproject")
        project = tmp_path / "generated"
        service.Project_Save(model, project, confirm_dangerous=True)

    compiler = shutil.which("gcc")
    assert compiler is not None
    include_dirs = [tmp_path]
    include_dirs.extend(p for p in project.rglob("Inc") if "build" not in p.parts)
    include_dirs.extend(project / p for p in ("System/User", "Tests/Host"))
    args = [compiler, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
            "-include", str(project / "Generated/Inc/project_flight_config.h")]
    for directory in include_dirs:
        args.extend(("-I", str(directory)))
    args.extend((str(root / "tests/fixtures/gnss_tilt_recovery_host.c"),
                 str(project / "System/Src/system_navigation_health.c"),
                 str(project / "FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c"),
                 "-lm", "-o", str(tmp_path / "gnss_tilt_host.exe")))
    built = subprocess.run(args, capture_output=True, text=True, timeout=90)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(tmp_path / "gnss_tilt_host.exe")],
                         capture_output=True, text=True, timeout=30)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "0 failures" in ran.stdout
