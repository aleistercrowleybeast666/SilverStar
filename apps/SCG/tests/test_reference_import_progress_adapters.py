from __future__ import annotations

import re
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from tools.import_reference_components import (
    _ArchitectureChecker_Adapt,
    _ArtifactChecker_Adapt,
    _HostTestRunner_Adapt,
    _PowerTenChecker_Adapt,
)


def _ProgressLines_Remove(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if "FCCG_PROGRESS|" not in line
    ) + "\n"


def _PowerProgress_Remove(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not any(
            token in line
            for token in (
                "FCCG_PROGRESS|",
                "$progressTotal =",
                "$progressCurrent =",
                "$progressCurrent++",
                "$progressSubject =",
            )
        )
    ) + "\n"


def _HostProgress_Remove(text: str) -> str:
    text = text.replace("$script:collectHostJobs = $true\n", "", 1)
    text = text.replace(
        "$script:hostJobs = [System.Collections.Generic.List[object]]::new()\n",
        "",
        1,
    )
    text = text.replace("$script:progressCompleted = @{}\n", "", 1)
    text = text.replace("$script:progressTotals = @{}\n", "", 1)
    detail_start = text.index("$detailLogPath = Join-Path $outputDir")
    detail_end = text.index("\n\n", detail_start) + 2
    text = text[:detail_start] + text[detail_end:]
    helper_start = text.index("function Write-FccgProgressBegin")
    helper_end = text.index("function Invoke-HostTest", helper_start)
    text = text[:helper_start] + text[helper_end:]
    text = re.sub(
        r"    if \(\$script:collectHostJobs\) \{.*?"
        r"    Write-FccgProgressBegin[^\n]*\n\n",
        "",
        text,
        count=3,
        flags=re.DOTALL,
    )
    text = re.sub(r"    Write-FccgProgressDone[^\n]*\n", "", text)
    diagnostic_start = text.index("    $diagnosticLine = $compileResult.Output")
    diagnostic_end_marker = (
        "    Write-HostTestDetail -Text ([string]$diagnostic)\n"
        "    }\n"
    )
    diagnostic_end = text.index(diagnostic_end_marker, diagnostic_start) + len(
        diagnostic_end_marker
    )
    text = (
        text[:diagnostic_start]
        + "    $script:expectedCompileFailureCount++\n"
        + '    Write-Output "Expected host compile failure passed: $Name"\n'
        + text[diagnostic_end:]
    )
    replay_start = text.index("$script:collectHostJobs = $false\n")
    replay_end = text.index("$alignmentRuntimeFiles = @(\n", replay_start)
    return text[:replay_start] + text[replay_end:]


def test_reference_import_reapplies_progress_to_pristine_scripts(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    policy = WorkspacePolicy(tmp_path)
    cases = (
        (
            "plugins/builtin/silverstar_core_0_1_0/payload/Tools/"
            "check_architecture.ps1",
            _ArchitectureChecker_Adapt,
            "FCCG_PROGRESS|ARCHITECTURE|PLAN|6",
            _ProgressLines_Remove,
        ),
        (
            "plugins/builtin/silverstar_core_0_1_0/payload/Tools/"
            "check_power_of_ten.ps1",
            _PowerTenChecker_Adapt,
            "FCCG_PROGRESS|POWER10|PLAN|$progressTotal",
            _PowerProgress_Remove,
        ),
        (
            "plugins/builtin/silverstar_core_0_1_0/payload/Tools/"
            "check_firmware_artifact.ps1",
            _ArtifactChecker_Adapt,
            "FCCG_PROGRESS|ARTIFACT|PLAN|8",
            _ProgressLines_Remove,
        ),
        (
            "plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/"
            "run_tests.ps1",
            _HostTestRunner_Adapt,
            "FCCG_PROGRESS|$taskKind|PLAN|$total",
            _HostProgress_Remove,
        ),
    )
    for index, (relative, adapter, marker, progress_remove) in enumerate(cases):
        target = tmp_path / f"adapter-{index}.ps1"
        source = (workspace_root / relative).read_text(encoding="utf-8")
        target.write_text(
            progress_remove(source),
            encoding="utf-8",
            newline="\n",
        )

        adapter(target, policy)
        first = target.read_text(encoding="utf-8")
        assert marker in first

        adapter(target, policy)
        assert target.read_text(encoding="utf-8") == first

    host = (tmp_path / "adapter-3.ps1").read_text(encoding="utf-8")
    assert "FCCG_EXPECTED_REJECTION|$Name" in host
    assert "static assertion failed|#error" in host
    assert "host-tests-detail.log" in host
    assert "SILVERSTAR_GOLDEN_OUTPUT" in host
    assert "generate_golden_sample.c" in host

    architecture = (tmp_path / "adapter-0.ps1").read_text(encoding="utf-8")
    assert (
        "Get-Content -Raw -Encoding UTF8 -LiteralPath $sslogSchemaPath"
        in architecture
    )
    assert (
        "Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $repoRoot"
        in architecture
    )
