"""Build numerical SSLOG fixtures from a materialized FCCG project."""
import os
import re
import subprocess
from pathlib import Path


def NavigationGolden_Generate(project: Path, output: Path, scenario: str = "normal") -> Path:
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    sources = (
        "Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c",
        "Algorithm/Common/Src/attitude_frame.c",
        "Algorithm/Estimator/KF6/Src/navigation_kf.c",
        "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
        "Algorithm/Estimator/KF6/Src/navigation_integrity.c",
        "Protocol/SSLOG/Src/sslog_protocol.c",
        "Protocol/SSLOG/Src/sslog_records.c",
        "Generated/Src/project_log_decoder_profile.c",
        "Generated/Src/project_log_config.c",
        "Common/Src/silverstar_assert.c",
    )
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / path.replace("\\", "/")) for path in includes]
    command += [str(project / path) for path in sources]
    executable = output / "joint-navigation.exe"
    command += [str(root / "tests/fixtures/joint_navigation_golden.c"), "-lm", "-o", str(executable)]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    (output / "compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    log = output / "navigation.sslog"
    subprocess.run([str(executable), str(log), scenario], env=env, check=True)
    return log
