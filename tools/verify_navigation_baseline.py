"""Reproducible offline checks; artifacts stay in a fresh repository .work path."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "root": (".", ["tests/integration/test_product_version_metadata.py",
        "tests/integration/test_desktop_version_inventory.py", "tests/integration/test_monorepo_baseline.py"]),
    "scg": ("apps/SCG", ["tests/test_navigation_v1.py", "tests/test_project_schema_current.py",
        "tests/test_product_patch_identity.py", "tests/test_firmware_identity_gate.py"]),
    "flp": ("apps/FLP", ["tests/test_navigation_plugins.py", "tests/test_navigation_body_inputs.py",
        "tests/test_navigation_c_journal.py",
        "tests/test_navigation_firmware_configuration.py", "tests/test_magnetometer_decoder_routes.py",
        "tests/test_kf6_process_model_identity.py",
        "tests/test_actual_parameters.py", "tests/test_project_artifacts.py",
        "tests/test_decoder_profiles.py::test_log_open_coordinator_builds_immutable_semantics_and_none_calibration"]),
    "gshc": ("apps/GSHC", ["tests/test_navigation_readiness.py", "tests/test_start_ack_state.py"]),
    "host": ("apps/SCG", ["tests/test_navigation_delayed_health.py",
        "tests/test_navigation_integrity_host.py", "tests/test_navigation_augmented_host.py"]),
    "math": ("apps/SCG/experiments/navigation_0_1_3", []),
}


def Baseline_Main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=GROUPS, action="append")
    parser.add_argument("--output", type=Path, help="Fresh directory inside .work; use a short Windows path")
    args = parser.parse_args()
    output = (args.output or ROOT / ".work" / datetime.now(timezone.utc).strftime("nav013_%Y%m%d_%H%M%S")).resolve()
    output.relative_to((ROOT / ".work").resolve())
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
               SILVERSTAR_GSHC_DATA_ROOT=str(output / "gshc-data"))
    report = {"schema": "silverstar.offline-navigation-checks/1", "hardware_tested": False,
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True),
              "python": sys.version, "groups": [], "sources": {}}
    patterns = ["apps/SCG/plugins/builtin/silverstar_algorithm_augmented_common",
                "apps/FLP/src/silverstar_flp/plugins/algorithms/navigation_reference_v1", "contracts"]
    for folder in patterns:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in (".c", ".h", ".py", ".json"):
                report["sources"][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    failed = False
    for group in args.group or GROUPS:
        directory = output / group
        directory.mkdir()
        cwd, tests = GROUPS[group]
        if group == "math":
            tests = [p.name for p in sorted((ROOT / cwd).glob("test_*.py"))]
        command = [sys.executable, "-B", "-m", "pytest", "-q", *tests, "-o", "addopts=",
                   "-o", "cache_dir=" + str(directory / "cache"), "-o", "faulthandler_timeout=60",
                   "--basetemp=" + str(directory / "tmp"), "--junitxml=" + str(directory / "junit.xml")]
        started = time.monotonic()
        log_path = directory / "stdout.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT / cwd, env=env, stdout=log,
                                       stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, timeout=10, check=False)
                else:
                    process.kill()
                process.wait(timeout=10)
                code = 124
        report["groups"].append({"group": group, "cwd": cwd, "command": command,
            "exit_code": code, "seconds": round(time.monotonic()-started, 3),
            "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest()})
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(group + ": " + "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-4:]), flush=True)
        failed |= code != 0
    print("Evidence: " + str(output / "summary.json"))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(Baseline_Main())
