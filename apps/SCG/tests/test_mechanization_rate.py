from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.rate_plan import InertialRatePlan_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate


def test_rate_plan_uses_physical_odr_and_bounded_replay(builtin_catalog) -> None:
    model = ReferenceProject_Create("RatePlan", catalog=builtin_catalog)
    owner = "silverstar.algorithm.ins.coning2_sculling2"
    plan = InertialRatePlan_Resolve(model, builtin_catalog)
    assert (plan.raw_imu_odr_hz, plan.aggregation) == (200, 2)
    assert plan.effective_propagation_rate_hz == 100
    assert plan.maximum_replay_steps == 27
    assert not plan.issues

    model.algorithm_parameters[owner]["mechanization_aggregation"] = 1
    plan = InertialRatePlan_Resolve(model, builtin_catalog)
    assert plan.effective_propagation_rate_hz == 200
    assert plan.maximum_replay_steps == 54
    assert plan.required_history_steps == 121
    assert not plan.issues

    model.device_instances[0] = DeviceInstance(
        "imu0", "silverstar.device.imu.bmi088", "i2c", "bosch_sync_400_hz"
    )
    plan = InertialRatePlan_Resolve(model, builtin_catalog)
    assert plan.raw_imu_odr_hz == 400
    assert plan.effective_propagation_rate_hz == 400
    assert plan.maximum_replay_steps == 108
    assert any(issue.code == "REPLAY_HISTORY_INSUFFICIENT" for issue in plan.issues)
    assert any(
        issue.code == "REPLAY_HISTORY_INSUFFICIENT"
        for issue in Project_Validate(model, builtin_catalog).issues
    )


def test_eskf15_on_cortex_m3_is_timing_unqualified(builtin_catalog) -> None:
    model = ReferenceProject_Create("M3Timing", catalog=builtin_catalog)
    model.mcu = "silverstar.mcu.stm32f103c8t6"
    model.strategies["estimator"] = "silverstar.algorithm.estimator.eskf15"
    # This isolates the qualified arithmetic/timing decision from PCB bindings.
    plan = InertialRatePlan_Resolve(model, builtin_catalog)
    assert plan.cpu_profile == "cortex_m3_softfp"
    assert plan.arithmetic_requirements == ("fp32",)
    assert any(issue.code == "TIMING_PROFILE_UNQUALIFIED" for issue in plan.issues)


def test_one_real_imu_interval_propagates_once(
    tmp_path: Path, workspace_root: Path,
) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("host GCC unavailable")
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("OneInterval")
    owner = "silverstar.algorithm.ins.coning2_sculling2"
    model.algorithm_parameters[owner]["mechanization_aggregation"] = 1
    project = tmp_path / "project"
    service.Project_Save(model, project, confirm_dangerous=True)
    header = (project / "Generated/Inc/project_algorithm_parameters.h").read_text(
        encoding="utf-8"
    )
    assert "#define SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT 1" in header
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    sources = (
        "Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
        "Algorithm/Common/Src/attitude_frame.c",
        "Common/Src/silverstar_assert.c",
    )
    executable = tmp_path / "one_interval.exe"
    command = [
        compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-include", str(project / "Generated/Inc/project_flight_config.h"),
        *("-I" + str(project / path.replace("\\", "/")) for path in includes),
        *(str(project / source) for source in sources),
        str(workspace_root / "tests/fixtures/inertial_rate_one.c"),
        "-lm", "-o", str(executable),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
