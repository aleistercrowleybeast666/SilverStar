from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.clean_workspace import WorkspaceClean_Apply, WorkspaceClean_Plan, WorkspaceCleanResult


def _Repository_Create(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    return root


def _File_Write(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("preserve-or-clean", encoding="utf8")
    return path


def test_cleanup_dry_run_apply_and_protected_inputs(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "build/report.png")
    cache = _File_Write(root, "src/pkg/__pycache__/module.pyc")
    protected = [
        _File_Write(root, name)
        for name in (
            "build/flight.BIN",
            "build/profile.ssdecoder",
            "build/project.ssflp",
            "build/raw.sslog",
            "tests/fixtures/result.png",
            "docs/figure.png",
            "src/change.py",
            "build/unknown.xyz",
            "build/keep.json",
            "build/user_project.ssproject",
            "build/user_archive.zip",
            "src/pkg/__pycache__/user_project.ssproject",
            "src/pkg/__pycache__/user_archive.zip",
            "main.zip",
        )
    ]
    subprocess.run(["git", "-C", str(root), "add", "build/keep.json"], check=True)
    targets = WorkspaceClean_Plan(root)
    assert generated in targets and cache in targets
    assert generated.exists() and cache.exists()  # dry run never writes
    result, removed = WorkspaceClean_Apply(root, targets)
    assert result == WorkspaceCleanResult.APPLIED
    assert generated in removed and not generated.exists()
    assert cache in removed and not cache.exists() and cache.parent.exists()
    assert all(path.exists() for path in protected)


def test_apply_rechecks_index_and_rejects_outside_target(tmp_path):
    root = _Repository_Create(tmp_path)
    path = _File_Write(root, "dist/keep.png")
    targets = WorkspaceClean_Plan(root)
    subprocess.run(["git", "-C", str(root), "add", "dist/keep.png"], check=True)
    outside = _File_Write(tmp_path, "outside.png")
    result, _ = WorkspaceClean_Apply(root, (*targets, outside))
    assert result == WorkspaceCleanResult.REFUSED
    assert path.exists() and outside.exists()


def test_symlink_escape_and_replaced_parent_are_refused(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "build/report.png")
    targets = WorkspaceClean_Plan(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = _File_Write(outside, "report.png")
    generated.unlink()
    generated.parent.rmdir()
    try:
        generated.parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"symlink permission unavailable: {exc}")
        # Directory junctions exercise Windows reparse-point escape without admin rights.
        import _winapi

        _winapi.CreateJunction(str(outside), str(generated.parent))
    assert not WorkspaceClean_Plan(root)
    result, removed = WorkspaceClean_Apply(root, targets)
    assert result == WorkspaceCleanResult.REFUSED and not removed
    assert sentinel.exists()


def test_gitignore_does_not_hide_sources_or_fixtures(tmp_path):
    root = _Repository_Create(tmp_path)
    source_root = Path(__file__).resolve().parents[3]
    (root / ".gitignore").write_bytes((source_root / ".gitignore").read_bytes())
    for path in (
        ".work/pytest/a.json",
        ".acceptance/export.png",
        "apps/FLP/.work/export.png",
        "apps/FLP/tests/.tmp_release/full/report.json",
        "apps/FLP/tests/.pytest-full/basetemp/result.csv",
        "apps/FLP/tests/artifacts/result.json",
        "apps/FLP/tests/joint_rework_20260927/work/report.json",
        "apps/FLP/tests/joint_rework_20260927/compile_cache/result.pyc",
        "build/a.png",
        "src/pkg/__pycache__/a.pyc",
    ):
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", path]).returncode == 0
    for path in (
        "apps/FLP/tests/fixtures/golden.png",
        "apps/FLP/tests/joint_rework_20260927/evidence_final/report.json",
        "docs/plot.png",
        "src/change.py",
        "flight.BIN",
        "profile.ssdecoder",
        "project.ssflp",
        "tests/source.py",
        "unknown.json",
    ):
        assert subprocess.run(["git", "-C", str(root), "check-ignore", "-q", path]).returncode == 1


def test_test_workspaces_clean_only_generated_files_and_keep_evidence(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "tests/.tmp_full/basetemp/export.csv")
    synthetic_input = _File_Write(root, "tests/.tmp_full/basetemp/input.BIN")
    summary = _File_Write(root, "tests/.tmp_full/basetemp/summary.json")
    acceptance_csv = _File_Write(root, ".acceptance/run/final_export/events.csv")
    acceptance_summary = _File_Write(root, ".acceptance/run/summary.json")
    acceptance_gif = _File_Write(root, ".acceptance/run/Flight_Replay.gif")
    gui_screenshot = _File_Write(root, ".acceptance/dialogs_gui/about_en_US_dark.png")
    targets = WorkspaceClean_Plan(root)
    assert generated in targets and acceptance_csv in targets
    assert all(
        path not in targets
        for path in (synthetic_input, summary, acceptance_summary, acceptance_gif, gui_screenshot)
    )
    result, removed = WorkspaceClean_Apply(root, targets)
    assert result == WorkspaceCleanResult.APPLIED
    assert generated in removed and acceptance_csv in removed
    assert all(
        path.exists()
        for path in (
            synthetic_input, summary, acceptance_summary,
            acceptance_gif, gui_screenshot,
        )
    )


def test_explicit_retirement_removes_tracked_test_outputs_only(tmp_path):
    from tools.clean_workspace import WorkspaceClean_RetireTests
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, ".codex_pytest_old/test_case/SYNTHETIC_run.BIN")
    source = _File_Write(root, "tests/fixtures/reference.BIN")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    assert generated not in WorkspaceClean_Plan(root)
    result, count = WorkspaceClean_RetireTests(root, (".codex_pytest_old",))
    assert result == WorkspaceCleanResult.APPLIED and count == 3
    assert source.exists() and not generated.exists()
    result, _ = WorkspaceClean_RetireTests(root, ("tests",))
    assert result == WorkspaceCleanResult.REFUSED and source.exists()


def test_retirement_refuses_junction_before_removing_any_run_file(tmp_path):
    from tools.clean_workspace import WorkspaceClean_RetireTests
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, ".codex_pytest_old/test_case/generated.png")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = _File_Write(outside, "actual.BIN")
    link = generated.parent / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink not available")
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    result, count = WorkspaceClean_RetireTests(root, (".codex_pytest_old",))
    assert result == WorkspaceCleanResult.REFUSED and count == 0
    assert generated.exists() and sentinel.exists()


def test_reviewed_plan_roundtrip_change_refusal_and_repeat(tmp_path):
    from tools.clean_workspace import WorkspaceClean_PlanLoad, WorkspaceClean_PlanSave

    root = _Repository_Create(tmp_path)
    path = _File_Write(root, "build/report.png")
    plan = WorkspaceClean_Plan(root, owner="synthetic image output")
    receipt = tmp_path / "plan.json"
    WorkspaceClean_PlanSave(plan, receipt)
    restored = WorkspaceClean_PlanLoad(root, receipt)
    path.write_text("changed", encoding="utf8")
    assert WorkspaceClean_Apply(root, restored) == (WorkspaceCleanResult.REFUSED, ())
    assert path.read_text() == "changed"
    fresh = WorkspaceClean_Plan(root)
    assert WorkspaceClean_Apply(root, fresh)[0] == WorkspaceCleanResult.APPLIED
    assert WorkspaceClean_Apply(root, fresh) == (WorkspaceCleanResult.APPLIED, ())
    assert WorkspaceClean_Apply(root, WorkspaceClean_Plan(root)) == (WorkspaceCleanResult.APPLIED, ())


def test_monorepo_scope_preserves_siblings_source_build_and_active_task(tmp_path):
    root = _Repository_Create(tmp_path)
    app = root / "apps/FLP"
    own = _File_Write(root, "apps/FLP/build/report.png")
    other = _File_Write(root, "apps/SCG/build/report.png")
    source = _File_Write(root, "apps/SCG/src/silverstar_fccg/build/runner.py")
    input_file = _File_Write(root, "apps/FLP/build/input.tdmotor.json")
    plan = WorkspaceClean_Plan(root, app)
    assert own in plan and other not in plan and source not in plan and input_file not in plan
    lock = _File_Write(root, "apps/FLP/.cleanup-active")
    assert WorkspaceClean_Apply(root, plan) == (WorkspaceCleanResult.REFUSED, ())
    assert own.exists() and not WorkspaceClean_Plan(root, app)
    lock.unlink()
    assert WorkspaceClean_Apply(root, plan)[0] == WorkspaceCleanResult.APPLIED
    assert all(path.exists() for path in (other, source, input_file))


@pytest.mark.parametrize("cwd_is_app", (False, True))
def test_cli_monorepo_default_preview_from_root_or_subdirectory(tmp_path, monkeypatch, capsys, cwd_is_app):
    import tools.clean_workspace as module

    root = _Repository_Create(tmp_path)
    own = _File_Write(root, "apps/FLP/build/report.png")
    _File_Write(root, "apps/SCG/build/other.png")
    script = root / "apps/FLP/tools/clean_workspace.py"
    script.parent.mkdir()
    monkeypatch.setattr(module, "__file__", str(script))
    monkeypatch.setattr("sys.argv", [str(script), "--dry-run"])
    monkeypatch.chdir(root / "apps/FLP" if cwd_is_app else root)
    assert module.WorkspaceClean_Main() == 0
    output = capsys.readouterr().out
    assert "apps/FLP/build/report.png" in output
    assert "apps/SCG" not in output and own.exists()


def test_scope_outside_repository_and_tampered_plan_refused(tmp_path):
    import json
    from tools.clean_workspace import WorkspaceClean_PlanLoad, WorkspaceClean_PlanSave

    root = _Repository_Create(tmp_path)
    _File_Write(root, "build/report.png")
    with pytest.raises(ValueError):
        WorkspaceClean_Plan(root, tmp_path)
    plan_file = tmp_path / "plan.json"
    WorkspaceClean_PlanSave(WorkspaceClean_Plan(root), plan_file)
    document = json.loads(plan_file.read_text())
    document["records"][0]["path"] = "../outside.png"
    plan_file.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="cleanup_plan_path_invalid"):
        WorkspaceClean_PlanLoad(root, plan_file)


def test_nested_repository_and_later_worktree_identity_are_protected(tmp_path):
    root = _Repository_Create(tmp_path)
    generated = _File_Write(root, "build/nested/build/report.png")
    plan = WorkspaceClean_Plan(root)
    nested = root / "build/nested"
    # A .git file also marks a worktree; no checkout beneath it belongs to this plan.
    (nested / ".git").write_text("gitdir: external-owner", encoding="utf8")
    assert generated not in WorkspaceClean_Plan(root)
    with pytest.raises(ValueError, match="cleanup_scope_is_nested_repository"):
        WorkspaceClean_Plan(root, nested / "build")
    assert WorkspaceClean_Apply(root, plan) == (WorkspaceCleanResult.REFUSED, ())
    assert generated.exists()
