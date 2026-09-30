"""Fault-test the checker against real linked artifacts supplied explicitly.

Set SILVERSTAR_ARTIFACT_ENABLED / SILVERSTAR_ARTIFACT_DISABLED to independent
Flight_Controller Release build roots. Inputs are copied, never mutated.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


@pytest.fixture(params=("ENABLED", "DISABLED"))
def artifact_case(request, tmp_path, workspace_root):
    source = os.environ.get("SILVERSTAR_ARTIFACT_" + request.param)
    if source is None:
        pytest.skip("Explicit real ARM Release artifact fixture required")
    source = Path(source)
    root = tmp_path / "artifact"
    relative = Path("build/FCCG/SilverStar_F407/Release")
    (root / relative).mkdir(parents=True)
    for suffix in ("elf", "map", "bin", "hex"):
        shutil.copy2(source / relative / ("SilverStar_0_1_0." + suffix), root / relative)
    shutil.copy2(source / "STM32F407XX_FLASH.ld", root)
    config = root / "Generated/Inc/project_flight_config.h"
    config.parent.mkdir(parents=True)
    shutil.copy2(source / "Generated/Inc/project_flight_config.h", config)
    checker = root / "Tools/check_firmware_artifact.ps1"
    checker.parent.mkdir()
    shutil.copy2(workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_firmware_artifact.ps1", checker)
    return checker, config, request.param == "ENABLED"


def run_check(checker):
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(checker), "-Config", "Release"],
                            capture_output=True, text=True, errors="replace", timeout=60)
    checker.with_name("check.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return result.returncode, result.stdout + result.stderr


def test_real_artifact_matches_maintenance_selection(artifact_case):
    checker, _, _ = artifact_case
    code, output = run_check(checker)
    assert code == 0, output


def test_real_artifact_rejects_opposite_maintenance_selection(artifact_case):
    checker, config, enabled = artifact_case
    text = config.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^(#define\s+SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED\s+)[01]U\s*$",
                          lambda m: m[1] + ("0U" if enabled else "1U"), text)
    assert count == 1
    config.write_text(text, encoding="utf-8")
    code, output = run_check(checker)
    assert code == 1, output
    assert ("must not allocate task stack s_serial_stack" if enabled else
            "Required symbol is missing: s_serial_stack") in output


@pytest.mark.parametrize("fault", ("missing", "duplicate", "invalid"))
def test_real_artifact_rejects_ambiguous_selection(artifact_case, fault):
    checker, config, _ = artifact_case
    text = config.read_text(encoding="utf-8")
    pattern = r"(?m)^#define\s+SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED\s+[01]U\s*$"
    line = re.search(pattern, text)
    assert line is not None
    replacement = {"missing": "", "duplicate": line[0] + "\n" + line[0],
                   "invalid": "#define SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED 2U"}[fault]
    config.write_text(re.sub(pattern, lambda _: replacement, text), encoding="utf-8")
    code, output = run_check(checker)
    assert code == 1, output
    assert "Generated MAINTENANCE selection must have exactly one literal 0/1 definition" in output
