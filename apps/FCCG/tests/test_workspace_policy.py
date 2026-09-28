from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import silverstar_fccg.core.workspace as workspace_module
from silverstar_fccg.core.workspace import (
    PortablePath_Normalize,
    PortableRelativePath_Validate,
    WorkspacePolicy,
    WorkspacePolicyError,
    _WindowsDirectoryInheritance_Enable,
)
from silverstar_fccg.plugins.manifest import (
    PluginManifestError,
    PluginManifest_Load,
)


def test_workspace_policy_rejects_escape_and_unsafe_portable_paths(tmp_path: Path) -> None:
    policy = WorkspacePolicy(tmp_path)
    assert policy.Path_Resolve("inside/file.txt") == (tmp_path / "inside/file.txt").resolve()
    with pytest.raises(WorkspacePolicyError):
        policy.Path_Resolve("../outside.txt")
    with pytest.raises(WorkspacePolicyError):
        policy.Path_Resolve(tmp_path.parent / "outside.txt")
    for value in (
        "../escape",
        "/absolute",
        "C:/drive",
        "a\\b",
        "NUL.txt",
        "trailing.",
        "control\nname",
        "alternate:stream",
        "a/./b",
        "a//b",
    ):
        with pytest.raises(WorkspacePolicyError):
            policy.RelativePath_Validate(value)


@pytest.mark.parametrize(
    "value",
    (
        "/absolute",
        "//server/share",
        "C:/drive",
        "C:\\drive",
        "\\\\server\\share",
        "../escape",
        "a/../b",
        "a/./b",
        "a//b",
        "a\\b",
        "NUL",
        "nul.txt",
        "folder/COM1.log",
        "trailing.",
        "trailing ",
        "control\nname",
        "delete\x7fname",
        "alternate:stream",
    ),
)
def test_pure_portable_relative_path_validator_keeps_illegal_corpus(
    value: str,
) -> None:
    with pytest.raises(WorkspacePolicyError):
        PortableRelativePath_Validate(value)


def test_pure_relative_path_validation_and_manifest_load_ignore_root_cwd(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
) -> None:
    filesystem_root = Path(workspace_root.anchor)
    monkeypatch.chdir(filesystem_root)

    assert PortableRelativePath_Validate(
        "nested/component/source.c"
    ).as_posix() == "nested/component/source.c"
    assert PortablePath_Normalize("nested/component/source.c") == (
        "nested/component/source.c"
    )
    manifest = PluginManifest_Load(
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_algorithm_calibration"
        / "plugin.json"
    )
    assert manifest.component_id == "silverstar.algorithm.calibration"


def test_manifest_path_error_reports_field_and_value(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_algorithm_calibration"
    )
    package = tmp_path / "invalid_manifest_path"
    shutil.copytree(source, package)
    manifest_path = package / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["build"]["sources"][0] = "../escape.c"
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        PluginManifestError,
        match=r"build\.sources.*'\.\./escape\.c'",
    ):
        PluginManifest_Load(manifest_path, source="installed")


def test_workspace_policy_still_rejects_filesystem_root_authorization(
    workspace_root: Path,
) -> None:
    with pytest.raises(WorkspacePolicyError, match="filesystem root"):
        WorkspacePolicy(Path(workspace_root.anchor))


def test_workspace_staging_and_atomic_write_remain_inside_root(tmp_path: Path) -> None:
    policy = WorkspacePolicy(tmp_path)
    staging = policy.StagingDirectory_Create("test-")
    assert staging.is_relative_to(tmp_path.resolve())
    path = policy.Text_AtomicWrite("state/value.txt", "stable\n")
    assert path.read_text(encoding="utf-8") == "stable\n"


def test_workspace_replace_retries_a_transient_windows_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    policy = WorkspacePolicy(tmp_path)
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "value.txt").write_text("stable\n", encoding="utf-8")
    original_replace = workspace_module.os.replace
    calls = 0

    def transient_replace(source_path: Path, target_path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError(13, "transient directory lock")
        original_replace(source_path, target_path)

    monkeypatch.setattr(workspace_module.os, "replace", transient_replace)
    monkeypatch.setattr(workspace_module.time, "sleep", lambda _seconds: None)

    replaced = policy.Path_Replace(source, target)

    assert calls == 2
    assert replaced == target.resolve()
    assert (target / "value.txt").read_text(encoding="utf-8") == "stable\n"


def test_windows_staging_permission_fix_enables_parent_inheritance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def run_stub(
        arguments: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        captured["arguments"] = arguments
        captured["options"] = options
        return subprocess.CompletedProcess(arguments, 0, "processed", "")

    monkeypatch.setattr(workspace_module.subprocess, "run", run_stub)
    staging = tmp_path / "staging"
    _WindowsDirectoryInheritance_Enable(staging)

    assert captured["arguments"] == [
        "icacls",
        str(staging),
        "/inheritance:e",
    ]
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["check"] is False
    assert options["capture_output"] is True


def test_windows_staging_permission_fix_reports_icacls_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run_stub(
        arguments: list[str], **_options: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 5, "", "access denied")

    monkeypatch.setattr(workspace_module.subprocess, "run", run_stub)
    with pytest.raises(WorkspacePolicyError, match="access denied"):
        _WindowsDirectoryInheritance_Enable(tmp_path / "staging")
