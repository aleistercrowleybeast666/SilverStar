"""Current owned C sources, independent oracles, and bounded replay semantics."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

APP = Path(__file__).resolve().parents[1]
OWNER = APP / "plugins/builtin/silverstar_algorithm_augmented_common/payload/Algorithm/Estimator/Augmented"


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_current_bounded_c_independent_math_and_reference_parity(tmp_path, optimization):
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC is required for the offline navigation baseline"
    source = OWNER / "Src/navigation_bounded.c"
    library = tmp_path / ("bounded.dll" if sys.platform == "win32" else "bounded.so")
    command = [compiler, "-std=c11", "-" + optimization, "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-shared", "-fPIC", "-I" + str(OWNER / "Inc"),
               str(source), "-lm", "-o", str(library)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    checked = subprocess.run([
        sys.executable, "-B", str(APP / "tests/fixtures/navigation_bounded_oracle.py"),
        "--library", str(library), "--output", str(tmp_path),
        "--reference", str(APP / "experiments/navigation_0_1_3"), "--label", optimization,
    ], capture_output=True, text=True, timeout=180)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    report = json.loads((tmp_path / "verification_results.json").read_text(encoding="utf-8"))
    assert report["passed"] == 41
    assert sum(row.startswith("independent/") for row in report["tests"]) == 33
    report["compile_command"] = command
    report["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    report["header_sha256"] = hashlib.sha256((OWNER / "Inc/navigation_bounded.h").read_bytes()).hexdigest()
    (tmp_path / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.parametrize("module", ["bounded", "input", "session", "replay", "journal", "mag_quality"])
def test_m7_navigation_objects_strict_analyzer_without_board(tmp_path, module):
    compiler = os.environ.get("SILVERSTAR_ARM_GCC") or shutil.which("arm-none-eabi-gcc")
    if not compiler:
        pytest.skip("ARM compiler unavailable; M7 object preparation remains untested")
    source = OWNER / "Src" / ("navigation_" + module + ".c")
    sslog = APP / "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Inc"
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16", "-mfloat-abi=hard",
        "-fanalyzer", "-fstack-usage", "-ffunction-sections", "-fdata-sections",
        "-I" + str(OWNER / "Inc"), "-I" + str(sslog),
        "-I" + str(APP / "tests/fixtures/navigation_augmented_host"),
        "-c", str(source), "-o", str(tmp_path / (module + ".o"))]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (tmp_path / "evidence.json").write_text(json.dumps({"command": command,
        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
        "scope": "Cortex-M7 objects with test logger boundary; no board startup/link/RTOS execution",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / (module + ".su")).is_file()
