"""Exercise fixed-slot boundaries and terminal traps on a generated project."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def run(project: Path, compiler: str, output: Path) -> int:
    project = project.resolve()
    output.mkdir(parents=True, exist_ok=True)
    host = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"', host)
    sources = ["Tests/Host/test_compact_log_slots.c", "Common/Src/common_spsc_queue.c",
               "Tests/Host/compact_assert_trap.c", "System/Src/system_log_policy.c",
               "System/Src/system_profile.c", "System/Src/system_navigation_profile.c",
               "System/Src/system_estimator_profile.c", "Generated/Src/project_metadata.c",
               "Generated/Src/project_log_config.c", "Generated/Src/project_log_decoder_profile.c",
               "Protocol/SSLOG/Src/sslog_records.c", "Protocol/SSLOG/Src/sslog_protocol.c"]
    binary = output / "compact_log_slots.exe"
    command = [compiler, "-std=c11", "-O2", "-fno-inline", "-Wall", "-Wextra", "-Werror",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               "-include",
               str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    target = json.loads((project / "SilverStar.ssproject").read_text(encoding="utf-8"))["build"]["target_profile"]
    command += ["-I" + str(project / "Targets" / target / "Inc")]
    command += [str(project / p) for p in sources] + ["-lm", "-o", str(binary)]
    print(subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, timeout=180)
    return subprocess.run([str(binary)], timeout=30).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    raise SystemExit(run(args.project, args.compiler, args.output))
