"""Run the emitted PowerShell stream contract, including rejected mutations."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("tier,choice,emitted,passes", [
    ("full",True,1,True), ("full",False,0,True),
    ("standard",True,1,True), ("standard",False,0,True),
    ("compact",True,0,True), ("minimal",True,0,True),
    ("compact",True,1,False), ("minimal",False,1,False),
    ("full",True,0,False), ("standard",False,1,False),
])
def test_saved_choice_and_tier_projection(tmp_path,tier,choice,emitted,passes):
    _run(tmp_path,tier,choice,emitted,passes)


@pytest.mark.parametrize("mutation", ["cadence","decimation","duplicate","policy","tier","mixed_authority","profile"])
def test_stream_contract_rejects_mismatches(tmp_path,mutation):
    _run(tmp_path,"compact",True,0,False,mutation)


@pytest.mark.parametrize("tier",["full","standard","compact"])
def test_omitted_serialized_default_profile(tmp_path,tier):
    _run(tmp_path,tier,True,0 if tier == "compact" else 1,True,"default_profile")


def _run(root,tier,choice,emitted,passes,mutation=None):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable")
    owner = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_architecture.ps1"
    body = re.search(r"(?s)function Test-TelemetryDiagnosticLogSelection \{.*?\n}\n",owner.read_text(encoding="utf8"))[0]
    project = {"build":{"feature_tier":tier,"logging_profile":"sf6_minimal" if tier == "minimal" else "all_streams"},
               "logging":{"streams":[{"record":"FLIGHT_LOG_RECORD_TELEMETRY_DIAG","enabled":choice,"policy":"PERIODIC","decimation":1,"period_us":1000000}]}}
    if mutation == "tier": project["build"]["feature_tier"] = "unknown"
    if mutation == "mixed_authority": project["build"]["compact_mode"] = True
    if mutation == "profile": project["build"]["logging_profile"] = "sf6_minimal"
    if mutation == "default_profile": del project["build"]["logging_profile"]
    text = f"{{FLIGHT_LOG_RECORD_TELEMETRY_DIAG, {emitted}U, {2 if mutation == 'decimation' else 1}U, {500000 if mutation == 'cadence' else 1000000}UL, SSLOG_STREAM_POLICY_PERIODIC}}"
    if mutation == "duplicate": text += text
    if mutation == "policy": text = text.replace("POLICY_PERIODIC","POLICY_EVENT")
    (root / "project.json").write_text(json.dumps(project),encoding="utf8")
    (root / "configuration.c").write_text(text,encoding="utf8")
    script = root / "selection.ps1"
    script.write_text("$ErrorActionPreference='Stop'\n" + body + "\n$p=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'project.json') -Raw | ConvertFrom-Json\n$c=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configuration.c') -Raw\n$result=Test-TelemetryDiagnosticLogSelection -Project $p -Configuration $c\nWrite-Output ('CONTRACT_RESULT=' + $result)\nif ($result) { exit 0 } else { exit 1 }\n",encoding="utf8")
    result = subprocess.run([shell,"-NoProfile","-File",str(script)],capture_output=True,text=True,timeout=20)
    assert "CONTRACT_RESULT=" in result.stdout,result.stdout+result.stderr
    assert result.returncode == (0 if passes else 1),result.stdout+result.stderr
