"""Generated gates must accept both release identities and reject mismatches."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("version,target,success", [
    ("0.1.0", "SilverStar_0_1_0", True),
    ("0.1.1", "SilverStar_0_1_1", True),
    ("0.1.1", "SilverStar_0_1_0", False),
    ("0.1.0", "SilverStar_0_1_1", False),
    ("../escape", "SilverStar_0_1_1", False),
    (None, "SilverStar_0_1_1", False),
])
def test_firmware_identity_contract(tmp_path, version, target, success):
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell unavailable")
    helper = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/read_firmware_identity.ps1"
    shutil.copy2(helper, tmp_path / "identity.ps1")
    (tmp_path / "SilverStar.ssproject").write_text(json.dumps({"project": {
        "firmware_version": version, "build_target": target}}), encoding="utf-8")
    script = tmp_path / "check.ps1"
    script.write_text("$ErrorActionPreference='Stop'\n. (Join-Path $PSScriptRoot 'identity.ps1')\n"
                      "(FirmwareIdentity_Read -ProjectRoot $PSScriptRoot).build_target\n", encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                            capture_output=True, text=True, timeout=15)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    if success:
        assert result.stdout.strip() == target
    else:
        assert "Project firmware identity is missing or invalid" in result.stderr or "Project build target does not match" in result.stderr
