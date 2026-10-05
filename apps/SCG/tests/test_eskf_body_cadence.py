"""400 Hz device timing traverses actual APP pairing before ESKF history."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply


@pytest.mark.parametrize("aggregation", (1, 2))
def test_actual_app_samples_produce_200hz_body(
    aggregation: int, tmp_path: Path, workspace_root: Path,
):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("BodyCadence400")
    previous = deepcopy(model)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.eskf15"
    LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
    model = service.ProjectConfiguration_Reconcile(model).model
    model.algorithm_parameters[
        "silverstar.algorithm.ins.coning2_sculling2"
    ]["mechanization_aggregation"] = aggregation
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    output = project / "build/FCCG/Host/BodyCadence"
    output.mkdir(parents=True)
    environment = dict(os.environ, TEMP=str(output), TMP=str(output))
    compiler = shutil.which("gcc")
    assert compiler is not None, "Real Host GCC is required for BODY cadence acceptance"
    runner = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', runner)
    command = [
        compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-flto", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
        "-include", str(project / "Generated/Inc/project_flight_config.h"),
        "-DSYSTEM_BUILD_ESTIMATOR_ENABLED=0U", "-DSYSTEM_BUILD_ESKF15_ENABLED=1U",
        "-DSYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_ESKF15",
        "-I" + str(project / "APP/Src"),
        "-I" + str(project / "Algorithm/Estimator/ESKF15/Inc"),
    ]
    command += ["-I" + str(project / path.replace("\\", "/")) for path in includes]
    command += [str(project / path) for path in (
        "Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
        "Algorithm/Common/Src/attitude_frame.c", "Common/Src/silverstar_assert.c",
        "System/Calibration/Src/system_calibration.c",
        "System/Calibration/Src/system_calibration_correction.c", "Tests/Host/host_platform_mock.c",
        "Algorithm/Estimator/ESKF15/Src/navigation_eskf.c",
        "Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c",
    )]
    executable = output / "body_cadence.exe"
    command += [str(workspace_root / "tests/fixtures/eskf_body_cadence.c"), "-lm", "-o", str(executable)]
    compiled = subprocess.run(command, env=environment, capture_output=True, text=True)
    (output / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(executable)], env=environment, capture_output=True, text=True)
    (output / "run.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
