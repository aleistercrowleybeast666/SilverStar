import json
import shutil
import subprocess

from replay_compliance_support import (
    barometer_operation_run,
    estimator_trace_run,
    replay_trace_run,
    replay_work_limit_run,
)

from silverstar_fccg.app.service import FccgService


def test_replay_recovery_contract_and_app_order(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    project = tmp_path / "generated"
    model = service.ReferenceProject_Create("ComplianceTrace")
    model.algorithm_parameters["silverstar.algorithm.estimator.kf6"][
        "gnss_integrity_enable"] = 0
    service.Project_Save(model, project, confirm_dangerous=True)
    actual = replay_trace_run(project, project / "build/FCCG/Host/Trace",
                              project / "Tests/Host/test_navigation_kf_replay.c")
    # Group isolation and controlled re-anchor intentionally supersede the old
    # math-preserving refactor baseline, which remains historical evidence.
    # The C fixture also checks independent direct/on-time x/P references, SPD,
    # no-outage rejection, and the wrong-current-state negative control.
    expected = json.loads((workspace_root / "tests/fixtures/navigation_recovery_trace.json").read_text())
    assert actual == expected["traces"], "KF/history/outcome operation trace changed"
    replay_work_limit_run(project, project / "build/FCCG/Host/WorkLimit",
                          workspace_root / "tests/fixtures/replay_work_limit.c")
    app = estimator_trace_run(project, project / "build/FCCG/Host/AppTrace",
                               workspace_root / "tests/fixtures/estimator_replay_trace.c")
    assert app == expected["app_traces"], "App packet ordering/outcome trace changed"
    barometer_operation_run(project, project / "build/FCCG/Host/BaroTiming",
                            workspace_root / "tests/fixtures/barometer_operation_timing.c")


def test_architecture_runtime_tokens_and_raw_boundaries(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    project = tmp_path / "generated"
    service.Project_Save(service.ReferenceProject_Create("ArchitectureFixture"), project,
                         confirm_dangerous=True)
    command = [shutil.which("powershell") or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               "Tools/check_architecture.ps1"]
    fixture = project / "Algorithm/Estimator/KF6/Src/architecture_fixture.h"
    def check(text, name):
        fixture.write_text(text, encoding="utf-8")
        result = subprocess.run(command, cwd=project, capture_output=True, text=True, check=False)
        (project / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        return result

    ignored = '/* provider\nExampleProviderOps */\n// RegisterCallback provider\nconst char *s = "provider Radio.foo \\" DioIrqHandler";\n'
    clean = check(ignored, "comments-literals")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    tokens = ["FooProviderOps x;", "ExampleProviderOps y;", "RegisterCallback();",
              "DioIrqHandler();", "Radio.foo();", "provider_runtime_identifier();", "provider();"]
    runtime = check(ignored + "\n".join(tokens) + "\n", "runtime-tokens")
    assert runtime.returncode != 0
    assert "Legacy Provider/VTable/callback" in runtime.stdout
    for line, token in enumerate(tokens, 5):
        assert f"architecture_fixture.h:{line}: {token}" in runtime.stdout

    boundary = check('#include "stm32f4xx_hal.h"\n', "raw-include")
    assert boundary.returncode != 0
    assert "stm32f4xx_hal.h" in boundary.stdout
    assert "Legacy Provider/VTable/callback" not in boundary.stdout
