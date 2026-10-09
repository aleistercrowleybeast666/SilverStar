"""Target routing, evidence identity and failure semantics; no MCU operations."""
from dataclasses import replace
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_scg_ui_metadata_hotfix import window
from silverstar_fccg.build.quality_batch import QualityBatch_Run
from silverstar_fccg.build.runner import BuildAction, BuildProgress, BuildResult, BuildRunner
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.task import TaskContext, TaskCancelledError
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel_Save
from silverstar_fccg.project.quality_inputs import QualityInputHash_Get
from silverstar_fccg.project.quality_results import QualityResult_Save, QualityResults_Load
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.pages.build import BuildPage


def _Inputs_Create(tmp_path):
    model = ReferenceProject_Create("CheckRouting")
    inputs = []
    for target, directory in (("flight", "Flight_Controller"), ("ground", "Ground_Station")):
        root = tmp_path / directory
        root.mkdir()
        marker = ("# SilverStar authoritative build entry" if target == "flight" else
                  "# Generated Ground target; source graph is Generated/ground_source_graph.json.")
        (root / "Makefile").write_text(marker + "\n" + "\n".join(
            task + ":\n\t@echo checked" for task in
            ("host-tests", "architecture-check", "power10-check", "static-analysis", "artifact-check")), encoding="utf-8")
        if target == "flight":
            ProjectModel_Save(model, root / "SilverStar.ssproject", WorkspacePolicy(root))
        else:
            generated = root / "Generated"
            generated.mkdir()
            (generated / "ground_source_graph.json").write_text(json.dumps(dict(
                sources=["sample.c"], asm_sources=[], include_dirs=[], defines=[], linker_script="sample.ld")), encoding="utf-8")
            (generated / "ground_target_metadata.json").write_text('{"target_role":"ground_station"}', encoding="utf-8")
        (root / "sample.c").write_text("int input_value = 1;\n", encoding="utf-8")
        (root / "sample.ld").write_text("/* synthetic linker input */\n", encoding="utf-8")
        inputs.append((target, root, model))
    return tuple(inputs)


def _Runner_Fake(monkeypatch, *, failed="", mutation="", cancel=False, power10=False):
    calls = []
    def run(self, model, root, action, token, *, line_callback, progress_callback, target_kind="flight"):
        calls.append((target_kind, root, action))
        progress_callback(BuildProgress("PLAN", 0, 2))
        progress_callback(BuildProgress("ANALYZE", 1, 2, "sample.c", 1, 2))
        output = ("POWER10_RULE5|Ground|eligible_assertions=2|functions=1\n"
                  "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending\n" if power10 else "PASS bounded checks\n")
        if failed == target_kind:
            output += "FAIL injected target fault\n"
        line_callback(output)
        if mutation == target_kind:
            (root / "sample.c").write_text("int input_value = 2;\n", encoding="utf-8")
        if cancel:
            token.Cancel_Request()
        return BuildResult(action, self.Command_Get(model, action),
                           1 if failed == target_kind else 0, output, live_streamed=True)
    monkeypatch.setattr(BuildRunner, "Run", run)
    return calls


@pytest.mark.parametrize("selection", [("flight",), ("ground",), ("flight", "ground"), ()])
def test_batch_only_runs_selected_targets(tmp_path, monkeypatch, selection):
    inputs = _Inputs_Create(tmp_path)
    calls = _Runner_Fake(monkeypatch)
    lines = []
    batch = QualityBatch_Run(tuple(item for item in inputs if item[0] in selection),
                            BuildAction.ARCHITECTURE_CHECK, TaskContext(line_callback=lines.append))
    assert tuple(call[0] for call in calls) == selection
    assert batch.succeeded == bool(selection)
    assert all(item.input_sha256 for item in batch.targets)
    events = [json.loads(line.partition("|")[2]) for line in lines]
    assert {event["target"] for event in events} == set(selection)
    for target in selection:
        progress = [event for event in events if event["target"] == target and event["kind"] == "progress"]
        assert progress[0]["fraction"] is None
        assert progress[1]["fraction"] == 0.5


def test_one_side_failure_does_not_hide_other_side_or_claim_batch_success(tmp_path, monkeypatch):
    inputs = _Inputs_Create(tmp_path)
    calls = _Runner_Fake(monkeypatch, failed="flight")
    batch = QualityBatch_Run(inputs, BuildAction.ARCHITECTURE_CHECK, TaskContext())
    assert len(calls) == 2 and not batch.succeeded
    assert not batch.targets[0].succeeded and batch.targets[1].succeeded
    assert "injected target fault" in batch.targets[0].result.output


def test_input_changes_during_check_block_current_result(tmp_path, monkeypatch):
    inputs = _Inputs_Create(tmp_path)
    _Runner_Fake(monkeypatch, mutation="ground")
    batch = QualityBatch_Run(inputs[1:], BuildAction.ARCHITECTURE_CHECK, TaskContext())
    assert not batch.succeeded and batch.targets[0].input_sha256 == ""
    assert "NOT PROVEN" in batch.targets[0].error


def test_cancel_stops_following_target(tmp_path, monkeypatch):
    inputs = _Inputs_Create(tmp_path)
    calls = _Runner_Fake(monkeypatch, cancel=True)
    with pytest.raises(TaskCancelledError):
        QualityBatch_Run(inputs, BuildAction.ARCHITECTURE_CHECK, TaskContext())
    assert len(calls) == 1


def test_missing_input_does_not_run_or_save_anything(tmp_path, monkeypatch):
    inputs = _Inputs_Create(tmp_path)
    # Occupied but incomplete target: do not generate or alter it.
    ground = tmp_path / "MissingGround"
    ground.mkdir()
    before = tuple(ground.iterdir())
    calls = _Runner_Fake(monkeypatch)
    batch = QualityBatch_Run((("ground", ground, inputs[0][2]),),
                            BuildAction.ARCHITECTURE_CHECK, TaskContext())
    assert not calls and not batch.succeeded
    assert batch.targets[0].result is None and batch.targets[0].error
    assert tuple(ground.iterdir()) == before


def test_ground_runner_uses_real_make_target_without_flight_descriptor(tmp_path, monkeypatch):
    _, (_, root, model) = _Inputs_Create(tmp_path)
    commands = []
    def process(command, actual_root, environment, token, line_callback=None):
        commands.append((command, actual_root))
        if line_callback:
            line_callback("PASS Ground declared source graph\nCritical-contract review NOT PROVEN\n")
        return 0, ["PASS Ground declared source graph\nCritical-contract review NOT PROVEN\n"]
    monkeypatch.setattr(BuildRunner, "_Process_Run", staticmethod(process))
    runner = BuildRunner(WorkspacePolicy(root))
    result = runner.Run(model, root, BuildAction.ARCHITECTURE_CHECK, target_kind="ground")
    assert result.succeeded and commands[0][0][-1] == "architecture-check"
    assert commands[0][1] == root and "NOT PROVEN" in result.output
    with pytest.raises(Exception, match="Not an FCCG project"):
        runner.Run(model, root, BuildAction.ARCHITECTURE_CHECK)


@pytest.mark.parametrize("selection", [("flight",), ("ground",), ("flight", "ground"), ()])
def test_gui_selection_routes_and_saves_per_target(window, tmp_path, monkeypatch, selection):
    _Inputs_Create(tmp_path)
    window._project_root = tmp_path
    window._model = ReferenceProject_Create("CheckRouting")
    calls = _Runner_Fake(monkeypatch)
    for target, checkbox in window.build_page.quality_target_checks.items():
        checkbox.setChecked(target in selection)
    def task(function, callback, error_callback=None, **kwargs):
        context = TaskContext(line_callback=kwargs["line_callback"])
        callback(function(context))
        return True
    monkeypatch.setattr(window, "Task_Run", task)
    if os.environ.get("SCG_CHECK_PRE3C"):
        source = subprocess.check_output(["git", "show", "3c8cf57:apps/SCG/src/silverstar_fccg/ui/main_window.py"],
                                         cwd=window._service.policy.root.parent.parent)
        path = tmp_path / "baseline_window.py"
        path.write_bytes(source)
        spec = importlib.util.spec_from_file_location("quality_baseline_window", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        window._Build_Request = module.MainWindow._Build_Request.__get__(window)
    monkeypatch.setattr(window, "_Project_SaveAs", lambda: pytest.fail("Check must not save project"))
    window._Build_Request("architecture_check")
    assert tuple(call[0] for call in calls) == selection
    for target, directory in (("flight", "Flight_Controller"), ("ground", "Ground_Station")):
        records = QualityResults_Load(tmp_path / directory)
        assert bool(records) == (target in selection)
        label = window.build_page.target_quality_labels[target]["architecture_check"]
        assert (label.property("statusLevel") == "success") == (target in selection)
        if records:
            assert records[0].input_sha256 and "PASS bounded" in records[0].details


def test_gui_old_result_invalidates_after_file_or_tool_change(window, tmp_path):
    inputs = _Inputs_Create(tmp_path)
    window._project_root = tmp_path
    window._model = inputs[0][2]
    target, root, model = inputs[0]
    command = BuildRunner(WorkspacePolicy(root)).Command_Get(model, BuildAction.ARCHITECTURE_CHECK)
    QualityResult_Save(root, task="architecture_check", succeeded=True, duration=0.1,
                       summary="completed", command=command,
                       input_sha256=QualityInputHash_Get(root, target, "architecture_check", command))
    window._TargetQualityResults_Refresh()
    label = window.build_page.quality_result_labels["architecture_check"]
    assert label.property("statusLevel") == "success"
    stored = (root / ".fccg/quality-results.json").read_bytes()
    (root / "sample.c").write_text("int input_value = 3;\n", encoding="utf-8")
    window._TargetQualityResults_Refresh()
    assert label.text() == window._translator.Text_Get("quality.target.stale")
    assert (root / ".fccg/quality-results.json").read_bytes() == stored
    (root / "sample.c").write_text("int input_value = 1;\n", encoding="utf-8")
    window._model.build = replace(model.build, tool_paths={"make": "changed-make.exe"})
    window._TargetQualityResults_Refresh()
    assert label.text() == window._translator.Text_Get("quality.target.stale")


def test_legacy_result_unbound_and_ground_result_not_inherited(window, tmp_path):
    inputs = _Inputs_Create(tmp_path)
    window._project_root = tmp_path
    window._model = inputs[0][2]
    root = inputs[0][1]
    QualityResult_Save(root, task="power10_check", succeeded=True, duration=0.1, summary="checks=10")
    before = (root / ".fccg/quality-results.json").read_bytes()
    window.build_page.quality_target_checks["ground"].setChecked(True)
    window._TargetQualityResults_Refresh()
    assert window.build_page.quality_result_labels["power10_check"].text() == window._translator.Text_Get("quality.target.stale")
    assert window.build_page.target_quality_labels["ground"]["power10_check"].text() == window._translator.Text_Get("quality.result.not_run")
    assert (root / ".fccg/quality-results.json").read_bytes() == before


def test_power10_manual_pending_and_critical_failure_are_per_target(qapp):
    page = BuildPage(Translator())
    page.quality_target_checks["ground"].setChecked(True)
    from silverstar_fccg.project.quality_results import QualityResultRecord
    record = QualityResultRecord("power10_check", "passed", "now", 1.0,
        "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending")
    page.TargetQualityResults_Set("ground", (record,))
    assert page.target_quality_labels["ground"]["power10_check"].property("statusLevel") == "success"
    assert page.target_quality_reviews["ground"].property("statusLevel") == "warning"
    page.TargetQualityResults_Set("flight", (replace(record, summary="POWER10_CONTRACT_REVIEW|FAIL|unchecked"),))
    assert page.quality_result_labels["power10_check"].property("statusLevel") == "error"
    assert page.power10_review_label.property("statusLevel") == "error"
    page.quality_target_checks["ground"].setChecked(False)
    assert page.target_quality_labels["ground"]["power10_check"].property("statusLevel") == "info"
    assert page.target_quality_progress["ground"].value() == 0
    page.Language_Apply(Translator("en_US"))
    assert "Not selected" in page.target_quality_labels["ground"]["power10_check"].text()


def test_progress_failure_unknown_and_cancel_never_claim_100(qapp):
    page = BuildPage(Translator())
    page.TargetQualityProgress_Set("flight", None, "unknown")
    assert page.target_quality_progress["flight"].maximum() == 0
    page.TargetQualityProgress_Set("flight", 1.0, "failed")
    assert page.target_quality_progress["flight"].value() == 999
    page.TargetQualityProgress_Set("flight", 1.0, "passed", succeeded=True)
    assert page.target_quality_progress["flight"].value() == 1000


def test_artifact_fingerprint_tracks_products_but_other_checks_ignore_build(tmp_path):
    inputs = _Inputs_Create(tmp_path)
    target, root, _ = inputs[1]
    source = QualityInputHash_Get(root, target, "architecture_check")
    artifact = QualityInputHash_Get(root, target, "artifact_check")
    (root / "build").mkdir()
    (root / "build/ground.elf").write_bytes(b"changed ELF")
    assert source == QualityInputHash_Get(root, target, "architecture_check")
    assert artifact != QualityInputHash_Get(root, target, "artifact_check")


def test_tool_binary_and_ownership_changes_invalidate_identity(tmp_path):
    inputs = _Inputs_Create(tmp_path)
    target, root, _ = inputs[0]
    executable = tmp_path / "fake-make.exe"
    executable.write_bytes(b"synthetic executable identity one")
    command = (str(executable), "architecture-check")
    before = QualityInputHash_Get(root, target, "architecture_check", command)
    executable.write_bytes(b"synthetic executable identity two")
    assert before != QualityInputHash_Get(root, target, "architecture_check", command)
    before = QualityInputHash_Get(root, target, "architecture_check", command)
    (root / ".fccg").mkdir()
    (root / ".fccg/ownership.json").write_text("{}", encoding="utf-8")
    assert before != QualityInputHash_Get(root, target, "architecture_check", command)


def test_gui_no_project_does_not_save_or_launch(window, monkeypatch):
    window._project_root = None
    monkeypatch.setattr(window, "_Project_SaveAs", lambda: pytest.fail("Implicit SaveAs"))
    monkeypatch.setattr(window, "Task_Run", lambda *args, **kwargs: pytest.fail("No input to run"))
    window._Build_Request("host_tests")
    assert window.build_page.quality_result_labels["host_tests"].property("statusLevel") == "info"


@pytest.mark.parametrize("target", ["flight", "ground"])
def test_corrupt_generated_identity_cannot_run_or_inherit_success(tmp_path, monkeypatch, target):
    inputs = _Inputs_Create(tmp_path)
    selected = inputs[0] if target == "flight" else inputs[1]
    path = selected[1] / ("SilverStar.ssproject" if target == "flight" else "Generated/ground_target_metadata.json")
    path.write_text("{}", encoding="utf-8")
    calls = _Runner_Fake(monkeypatch)
    batch = QualityBatch_Run((selected,), BuildAction.HOST_TESTS, TaskContext())
    assert not calls and not batch.succeeded and batch.targets[0].result is None


@pytest.mark.parametrize("failed", ["", "ground"])
def test_async_gui_terminal_uses_batch_outcome_and_keeps_other_target_result(qapp, window, tmp_path, monkeypatch, failed):
    from test_task_progress_busy import _Wait
    inputs = _Inputs_Create(tmp_path)
    window._project_root = tmp_path
    window._model = inputs[0][2]
    window.build_page.quality_target_checks["ground"].setChecked(True)
    _Runner_Fake(monkeypatch, failed=failed)
    window._Build_Request("architecture_check")
    _Wait(qapp, lambda: window._active_worker is None)
    assert window.progress_bar.property("taskState") == ("error" if failed else "success")
    assert (window.progress_bar.value() == 1000) == (not failed)
    assert window.build_page.quality_result_labels["architecture_check"].property("statusLevel") == "success"
    ground_label = window.build_page.target_quality_labels["ground"]["architecture_check"]
    assert ground_label.property("statusLevel") == ("error" if failed else "success")
    assert (window.build_page.target_quality_progress["ground"].value() == 1000) == (not failed)
    if failed:
        assert "injected target fault" in ground_label.toolTip()


def test_evidence_save_failure_cannot_leave_green(window, tmp_path, monkeypatch):
    import silverstar_fccg.ui.main_window as module
    inputs = _Inputs_Create(tmp_path)
    window._project_root = tmp_path
    window._model = inputs[0][2]
    _Runner_Fake(monkeypatch)
    batch = QualityBatch_Run(inputs[:1], BuildAction.ARCHITECTURE_CHECK, TaskContext())
    window._active_quality_action = "architecture_check"
    monkeypatch.setattr(module, "QualityResult_Save", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    window._QualityChecks_Complete(batch)
    assert not batch.succeeded
    assert window.build_page.quality_result_labels["architecture_check"].property("statusLevel") != "success"
    assert window.build_page.target_quality_progress["flight"].value() < 1000


def test_real_ground_architecture_gate_via_native_make(tmp_path, workspace_root, monkeypatch):
    from test_f103_ground_reference import _GroundF103Model_Get
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    make = shutil.which("mingw32-make") or shutil.which("make")
    assert make, "Native make unavailable; real gate has not run"
    service = FccgService(workspace_root)
    model = _GroundF103Model_Get(service.catalog)
    TargetGeneration_Apply(model, service.catalog, service.policy, tmp_path, TargetScope.GROUND)
    model.build = replace(model.ground_target.build, tool_paths={"make": make})
    monkeypatch.setenv("PYTHON", sys.executable)
    root = tmp_path / "Ground_Station"
    batch = QualityBatch_Run((("ground", root, model),), BuildAction.ARCHITECTURE_CHECK, TaskContext())
    assert batch.succeeded, batch.targets[0].error + str(batch.targets[0].result)
    output = batch.targets[0].result.output
    assert "PASS Ground declared source graph" in output and "NOT PROVEN" in output
    assert not (root / "build/ground.elf").exists()


@pytest.mark.parametrize("fail_gate", [False, True])
def test_native_ground_analysis_progress_counts_actual_jobs_and_gate(tmp_path, monkeypatch, fail_gate):
    # Real native host compilation of a tiny scheduler fixture, not ARM evidence.
    _, (_, root, model) = _Inputs_Create(tmp_path)
    make = shutil.which("mingw32-make") or shutil.which("make")
    gcc = shutil.which("gcc")
    assert make and gcc
    (root / "Makefile").write_text(
        "# Generated Ground target; source graph is Generated/ground_source_graph.json.\n"
        "static-analysis: build/app.elf\n\t" + ("exit 7" if fail_gate else "@echo PASS synthetic gate") + "\n"
        "build/a.o: sample.c\n\tif not exist build mkdir build\n\t" + gcc.replace("\\", "/") + " -fanalyzer -c sample.c -o build/a.o\n"
        "build/app.elf: build/a.o\n\t" + gcc.replace("\\", "/") + " -shared build/a.o -o build/app.elf\n", encoding="utf-8")
    model.build = replace(model.build, tool_paths={"make": make})
    progress = []
    result = BuildRunner(WorkspacePolicy(root)).Run(model, root, BuildAction.STATIC_ANALYSIS,
        target_kind="ground", progress_callback=progress.append)
    assert result.succeeded != fail_gate
    assert any(0 < item.completed_steps < item.total_steps for item in progress)
    assert result.plan.total_steps == 3
    assert result.completed_steps == (2 if fail_gate else 3)
    assert "--debug=j" in result.command
