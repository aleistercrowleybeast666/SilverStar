import os
import re
import subprocess

from silverstar_fccg.app.service import FccgService


def test_generated_fixed_lag_replay(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("FixedLagReplay")
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    output = project / "build/FCCG/Host/Tests"
    output.mkdir(parents=True, exist_ok=True)
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra",
               "-Werror", "-pedantic", "-O2", "-include",
               str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    sources = ["Algorithm/Estimator/KF6/Src/navigation_kf.c",
               "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
               "System/Src/system_time.c", "Common/Src/silverstar_assert.c"]
    fixture = workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_navigation_kf_replay.c"
    command += [str(project / p) for p in sources]
    command += [str(fixture), "-lm", "-o", str(output / "replay.exe")]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    (output / "replay-compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(output / "replay.exe")], env=env, capture_output=True, text=True)
    (output / "replay-result.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr
    assert "0 failures" in result.stdout
