"""Finite orchestration regression; real core/replay, mocked hardware boundary."""
import os
import importlib.util
from pathlib import Path

import pytest

from estimator_health_support import health_run
from silverstar_fccg.app.service import FccgService


def test_kf6_health_and_fault_publication(tmp_path, workspace_root):
    if os.name != "nt" or not Path("D:/msys64/ucrt64/bin/gcc.exe").is_file():
        pytest.skip("Configured Windows Host GCC unavailable")
    selected = os.environ.get("SCG_ESTIMATOR_HEALTH_PROJECT")
    if selected:
        project = Path(selected)
    else:
        service = FccgService(workspace_root)
        model = service.ReferenceProject_Create("KF6HealthHost")
        project = tmp_path / "project"
        service.Project_Save(model, project, confirm_dangerous=True)
    evidence = health_run(project, tmp_path / "health",
                          Path(__file__).parent / "fixtures/estimator_health.c")
    assert evidence["compile_exit"] == 0, (tmp_path / "health/compile.log").read_text()
    assert len(evidence["cases"]) == 23
    failures = [case for case in evidence["cases"] if case["exit"] != 0]
    assert not failures, failures


@pytest.mark.parametrize("source", ["estimator_task.c", "ins_task.c", "diagnostic_log.c"])
def test_health_stack_binding_rejects_unreviewed_source(tmp_path, workspace_root, source):
    payload = workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload"
    spec = importlib.util.spec_from_file_location("health_stack_checker",
                                               payload / "Tools/check_task_stacks.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    relative = "APP/Src/" + source
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((payload / relative).read_bytes())
    checker.BindingHeader_Verify(tmp_path, relative)
    target.write_text(target.read_text() + "\n/* unreviewed mutation */\n")
    with pytest.raises(ValueError, match="Changed or missing"):
        checker.BindingHeader_Verify(tmp_path, relative)
