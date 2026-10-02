"""Invalid numeric input must not become a valid increment or navigation commit."""
import json
import os
import re
import shutil
import subprocess

import pytest

from silverstar_fccg.app.service import FccgService


@pytest.mark.parametrize("aggregation", (1, 2))
def test_inertial_numeric_rejection_is_atomic(tmp_path, workspace_root, aggregation):
    compiler = shutil.which("gcc")
    assert compiler is not None, "Real host compiler required for numeric fault injection"
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("NumericRejection")
    model.algorithm_parameters["silverstar.algorithm.ins.coning2_sculling2"]["mechanization_aggregation"] = aggregation
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    output = tmp_path / "numeric_rejection.exe"
    runner = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', runner)
    sources = ("Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
               "Algorithm/Common/Src/attitude_frame.c", "Common/Src/silverstar_assert.c")
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-include", str(project / "Generated/Inc/project_flight_config.h"),
               *("-I" + str(project / p.replace("\\", "/")) for p in includes),
               *(str(project / p) for p in sources),
               str(workspace_root / "tests/fixtures/inertial_numeric_rejection.c"),
               "-lm", "-o", str(output)]
    (tmp_path / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    compiled = subprocess.run(command, env=environment, capture_output=True, text=True)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    executed = subprocess.run([str(output)], env=environment, capture_output=True, text=True)
    (tmp_path / "run.log").write_text(executed.stdout + executed.stderr, encoding="utf-8")
    assert executed.returncode == 0, executed.stdout + executed.stderr
