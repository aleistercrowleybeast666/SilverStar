"""Validate completed startup reports before any logger publication or indexing."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from silverstar_fccg.app.service import FccgService


@pytest.fixture(scope="module")
def logger_startup_executable(tmp_path_factory, workspace_root):
    build = tmp_path_factory.mktemp("logger-startup")
    selected = os.environ.get("SCG_CRITICAL_PROJECT")
    if selected:
        project = Path(selected).resolve(strict=True)
    else:
        service = FccgService(workspace_root)
        project = build / "project"
        service.Project_Save(service.ReferenceProject_Create("StartupContract"), project,
                             confirm_dangerous=True)
    source = Path(os.environ.get("SCG_CRITICAL_LOGGER_SOURCE", str(
        workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/logger_task.c")))
    # A single unchanged full translation unit is selected for pre/post evidence.
    (build / "logger_task.c").write_bytes(source.read_bytes())
    includes = re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"',
                         (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf8"))
    profile = json.loads((project / "SilverStar.ssproject").read_text(encoding="utf8"))["build"]["target_profile"]
    includes.insert(0, "Targets/" + profile + "/Inc")
    includes.append("Common/Src")
    compiler = shutil.which("gcc")
    assert compiler, "Actual Host GCC required"
    binary = build / "startup.exe"
    fixture = Path(__file__).parent / "fixtures/logger_startup_contract.c"
    sources = [project / "Protocol/SSLOG/Src/sslog_protocol.c",
               project / "Protocol/SSLOG/Src/sslog_records.c",
               project / "Generated/Src/project_log_decoder_profile.c"]
    command = [compiler, "-std=c11", "-O2", "-flto", "-Wall", "-Wextra", "-Werror", "-fanalyzer",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               "-I" + str(build), "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / name.replace("\\", "/")) for name in includes]
    command += [str(fixture), *map(str, sources), "-lm", "-o", str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    receipt = {"command": command, "exit": compiled.returncode,
               "stdout": compiled.stdout, "stderr": compiled.stderr,
               "inputs": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [source, fixture, *sources, project / "Common/Src/silverstar_assert.c"]},
               "scope": "Whole owning logger C, real SSLOG codec/assertion, explicit Host report/I/O ports; no MCU recovery"}
    (build / "compile-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return binary


@pytest.mark.parametrize("scenario", ["normal", "device-failure", "incomplete", "null",
                                      "io-failure", "oversized", "completed-domain", "passed-domain"])
def test_logger_startup_publication_contract(logger_startup_executable, scenario):
    result = subprocess.run([str(logger_startup_executable), scenario], capture_output=True,
                            text=True, timeout=10, check=False)
    print(result.stdout, end="")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
