from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

import silverstar_fccg.core.workspace as workspace_module
from silverstar_fccg.core.workspace import (
    PortablePath_Normalize,
    PortableRelativePath_Validate,
    WorkspacePolicy,
    WorkspacePolicyError,
)
from silverstar_fccg.plugins.manifest import (
    PluginManifestError,
    PluginManifest_Load,
)


@pytest.mark.skipif(os.name != "nt", reason="Real Windows CopyFile2 path boundary")
def test_windows_overlong_copy_rejected_before_io_and_preserves_boundary(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.bin"
    source.write_bytes(bytes(range(256)) * 3)
    policy = WorkspacePolicy(tmp_path / "owned")
    destination = policy.root / ("nested_" + "x" * 65) / ("nested_" + "y" * 65) / ("nested_" + "z" * 65) / "output.bin"
    assert len(str(destination)) > 260
    calls = []
    monkeypatch.setattr(workspace_module.shutil, "copy2", lambda *args: calls.append(args))
    with pytest.raises(WorkspacePolicyError, match="WINDOWS_PATH_TOO_LONG.*shorten"):
        policy.File_Copy(source, destination)
    assert not destination.parent.exists()
    assert source.read_bytes() == bytes(range(256)) * 3
    with pytest.raises(WorkspacePolicyError, match="escapes"):
        policy.File_Copy(source, tmp_path / "outside" / destination.name)
    assert not calls


def test_copy_error_is_not_hidden_by_long_path_support(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.bin"
    source.write_bytes(b"input")
    policy = WorkspacePolicy(tmp_path / "owned")
    def denied(*args):
        raise PermissionError("fixture access denied")
    monkeypatch.setattr(workspace_module.shutil, "copy2", denied)
    with pytest.raises(PermissionError, match="access denied"):
        policy.File_Copy(source, policy.root / "output.bin")


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


@pytest.mark.skipif(os.name != "nt", reason="Windows inherited staging access")
def test_windows_staging_inherits_access_without_acl_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden_private_temp(*args, **kwargs):
        raise AssertionError("Windows staging must not create a mode0700 directory")
    monkeypatch.setattr(workspace_module.tempfile, "mkdtemp", forbidden_private_temp)
    policy = WorkspacePolicy(tmp_path)
    staging = policy.StagingDirectory_Create("test-")
    assert staging.parent == (tmp_path / ".staging").resolve()
    policy.Text_AtomicWrite(staging / "state.txt", "verified")
    assert (staging / "state.txt").read_text(encoding="utf-8") == "verified"
    assert list(staging.iterdir()) == [staging / "state.txt"]


@pytest.mark.skipif(os.name != "nt", reason="Windows staging failure handling")
def test_windows_staging_collision_is_bounded_and_preserves_existing_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(workspace_module.secrets, "token_hex", lambda _size: "collision")
    policy = WorkspacePolicy(tmp_path)
    existing = policy.Directory_Ensure(".staging/test-collision")
    (existing / "input.bin").write_bytes(b"user input")
    with pytest.raises(WorkspacePolicyError, match="unique staging"):
        policy.StagingDirectory_Create("test-")
    assert (existing / "input.bin").read_bytes() == b"user input"


@pytest.mark.skipif(os.name != "nt", reason="Windows staging failure handling")
def test_windows_staging_access_denial_propagates_without_permission_repair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = Path.mkdir
    def denied(path, *args, **kwargs):
        if path.parent.name == ".staging":
            raise PermissionError("fixture creation denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(PermissionError, match="creation denied"):
        WorkspacePolicy(tmp_path).StagingDirectory_Create()
    assert list((tmp_path / ".staging").iterdir()) == []


@pytest.mark.parametrize("prefix", ["../escape-", "nested/path-", "nested\\path-", "C:/escape-", "/escape-"])
def test_staging_prefix_cannot_escape_or_create_nested_directories(tmp_path, prefix):
    with pytest.raises(WorkspacePolicyError):
        WorkspacePolicy(tmp_path).StagingDirectory_Create(prefix)
    assert not (tmp_path / ".staging").exists()
