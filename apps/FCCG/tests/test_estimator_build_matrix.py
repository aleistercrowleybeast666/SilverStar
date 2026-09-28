from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


def _Make_Run(
    make: str, project: Path, name: str, *targets: str
) -> str:
    report_root = project / "build/FCCG/Matrix"
    report_root.mkdir(parents=True, exist_ok=True)
    temp_root = report_root / "Temp"
    temp_root.mkdir(exist_ok=True)
    log = report_root / f"{name}.log"
    env = dict(os.environ, TEMP=str(temp_root), TMP=str(temp_root),
               TMPDIR=str(temp_root), PYTHONDONTWRITEBYTECODE="1")
    command = [make, "-j4", "SHELL=cmd.exe", *targets]
    with log.open("w", encoding="utf-8", errors="replace") as output:
        result = subprocess.run(
            command, cwd=project, env=env, stdout=output,
            stderr=subprocess.STDOUT, check=False,
        )
    text = log.read_text(encoding="utf-8", errors="replace")
    assert result.returncode == 0, f"{name}: {text[-6000:]}"
    return text


@pytest.mark.parametrize("estimator_enabled", [True, False], ids=["KF6", "PureINS"])
def test_estimator_release_debug_build_and_quality_matrix(
    tmp_path: Path, workspace_root: Path, estimator_enabled: bool
) -> None:
    make = shutil.which("mingw32-make") or r"D:\msys64\ucrt64\bin\mingw32-make.exe"
    if os.name != "nt" or not Path(make).is_file() or not shutil.which("arm-none-eabi-gcc"):
        pytest.skip("Windows Arm GNU/MinGW build toolchain unavailable")

    service = FccgService(workspace_root)
    name = "KF6LoggingMatrix" if estimator_enabled else "PureINSLoggingMatrix"
    model = service.ReferenceProject_Create(name)
    if not estimator_enabled:
        model.strategies["estimator"] = None
        model = service.ProjectConfiguration_Reconcile(model).model
    assert model.protocols["logging"] is not None
    graph = SourceGraph_Resolve(model, service.catalog)
    project = tmp_path / name
    service.Project_Save(model, project, confirm_dangerous=True)
    reloaded = service.Project_Open(project)
    assert reloaded.strategies["estimator"] == model.strategies["estimator"]
    assert SourceGraph_Resolve(reloaded, service.catalog).defines == graph.defines

    expected_fusion = "SYSTEM_FUSION_KF6" if estimator_enabled else "SYSTEM_FUSION_NONE"
    assert f"SYSTEM_BUILD_FUSION_ALGORITHM={expected_fusion}" in graph.defines
    assert f"SYSTEM_BUILD_ESTIMATOR_ENABLED={int(estimator_enabled)}U" in graph.defines
    assert "SYSTEM_BUILD_LANDING_MODE=SYSTEM_LANDING_MODE_BARO_IMU_WINDOW" in graph.defines
    sources = [source for source in graph.sources if "Algorithm/Estimator/KF6" in source]
    assert len(sources) == (3 if estimator_enabled else 0)
    for config in ("Release", "Debug"):
        build = _Make_Run(
            make, project, f"{config.lower()}-build",
            f"CONFIG={config}", "all", "stack-report",
            "memory-report", "artifact-check",
        )
        include = "-IAlgorithm/Estimator/KF6/Inc"
        assert (include in build) == estimator_enabled
        assert ("Algorithm/Estimator/KF6/Src/navigation_kf.c" in build) == estimator_enabled
        assert ("Algorithm/Estimator/KF6/Src/navigation_kf_replay.c" in build) == estimator_enabled
        assert ("Algorithm/Estimator/KF6/Src/navigation_integrity.c" in build) == estimator_enabled

    quality = _Make_Run(
        make, project, "quality", "CONFIG=Release",
        "architecture-check", "power10-check",
    )
    assert "architecture check passed:" in quality
    assert "Power of Ten check passed:" in quality
    host = _Make_Run(make, project, "host", "CONFIG=Release", "host-tests")
    assert "All SilverStar host tests passed." in host
