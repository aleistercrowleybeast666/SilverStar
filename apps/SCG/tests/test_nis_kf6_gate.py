"""Actual owning C source; compile-time controls retain finite numeric thresholds."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import pytest
from silverstar_fccg.app.service import FccgService

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def gate_project(tmp_path_factory):
    project=tmp_path_factory.mktemp("kf6-gates")/"project"
    service=FccgService(ROOT/"apps/SCG")
    service.Project_Save(service.ReferenceProject_Create("nis_kf6_host"),project,confirm_dangerous=True)
    return project


@pytest.mark.parametrize("soft_enabled,hard_enabled",[(1,1),(0,1),(1,0),(0,0)])
def test_kf6_explicit_controls_and_invalid_input(gate_project,tmp_path,soft_enabled,hard_enabled):
    compiler=shutil.which("gcc")
    assert compiler, "Actual Host GCC required"
    project=gate_project
    runner=(project/"Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes=re.findall(r'"-I\$repoRoot\\([^"\n]+)"',runner)
    assert includes
    source=Path(os.environ.get("SILVERSTAR_NIS_KF6_BASELINE",project/"Algorithm/Estimator/KF6/Src/navigation_kf.c"))
    exe=tmp_path/"kf6-gate.exe"
    command=[compiler,"-std=c11","-O2","-Wall","-Wextra","-Werror","-pedantic",
        "-include",str(project/"Generated/Inc/project_flight_config.h"),
        f"-DSYSTEM_ESTIMATOR_NIS_SOFT_ENABLED={soft_enabled}",f"-DSYSTEM_ESTIMATOR_NIS_HARD_ENABLED={hard_enabled}"]
    command += ["-I"+str(project/x.replace("\\","/")) for x in includes]
    command += [str(source),str(project/"Common/Src/silverstar_assert.c"),
        str(ROOT/"apps/SCG/tests/fixtures/nis_kf6_gate.c"),"-lm","-o",str(exe)]
    environment=dict(os.environ,TEMP=str(tmp_path),TMP=str(tmp_path))
    built=subprocess.run(command,capture_output=True,text=True,env=environment,timeout=90)
    (tmp_path/"compile.json").write_text(json.dumps({"command":command,"exit":built.returncode,"output":built.stdout+built.stderr},indent=2),encoding="utf-8")
    assert built.returncode==0,built.stdout+built.stderr
    result=subprocess.run([str(exe)],capture_output=True,text=True,env=environment,timeout=30)
    (tmp_path/"run.log").write_text(result.stdout+result.stderr,encoding="utf-8")
    assert result.returncode==0,result.stdout+result.stderr
    equality,soft,outlier,invalid,position,velocity=map(int,result.stdout.split())
    # Original KF6 hard comparison remains >=: exact NIS=8 is rejected.
    assert equality == (2 if hard_enabled else 1 if soft_enabled else 0)
    assert soft == (1 if soft_enabled else 0)
    assert outlier == (2 if hard_enabled else 1 if soft_enabled else 0)
    assert invalid == 3
    assert position == velocity == 0  # Reserved df=3 is not used by either product update.
