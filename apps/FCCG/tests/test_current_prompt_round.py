from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from pathlib import Path

from silverstar_fccg.app.source_export import SourcePackage_Export
from silverstar_fccg.build.runner import BuildAction, BuildRunner
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.generation_state import (
    ProjectGenerationFingerprint_Get,
)
from silverstar_fccg.project.protocols import ProtocolResolution_Resolve
from silverstar_fccg.project.quality_results import (
    QualityResult_Save,
    QualityResults_Load,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate

from tools import clean_all


def test_protocol_profiles_resolve_four_layers_and_selected_source_graph(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("ProtocolLayers", catalog=builtin_catalog)
    resolution = ProtocolResolution_Resolve(model, builtin_catalog)
    assert resolution.valid
    assert {
        (
            binding.service,
            binding.slot,
            binding.profile_id,
            binding.transport_capability,
            binding.provider_instance,
        )
        for binding in resolution.bindings
    } == {
        (
            "telemetry_service",
            "telemetry_protocol",
            "air.m0",
            "transport.packet",
            "telemetry0",
        ),
        (
            "maintenance_service",
            "maintenance_protocol",
            "maintenance.serial.0_0",
            "transport.byte_stream",
            "maintenance0",
        ),
        (
            "flight_log_service",
            "log_format",
                "flight_log.0_0",
                "transport.sequential_file_sink",
                "storage0",
            ),
    }
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "Protocol/Src/air_protocol.c" in graph.sources
    assert "Protocol/SSLOG/Src/sslog_records.c" in graph.sources


def test_protocol_transport_constraints_are_enforced(
    builtin_catalog, monkeypatch
) -> None:
    model = ReferenceProject_Create("TransportMismatch", catalog=builtin_catalog)
    telemetry = builtin_catalog.Component_Get(
        "silverstar.device.telemetry.sx1281"
    )
    monkeypatch.setitem(
        builtin_catalog._components,
        telemetry.component_id,
        replace(
            telemetry,
            transports=(replace(telemetry.transports[0], mtu=16),),
        ),
    )
    validation = Project_Validate(model, builtin_catalog)
    assert not validation.valid
    assert any(issue.code == "protocol_transport" for issue in validation.issues)


def test_quality_results_are_project_local_and_not_generation_state(
    tmp_path: Path, builtin_catalog
) -> None:
    root = tmp_path / "QualityProject"
    root.mkdir()
    model = ReferenceProject_Create("QualityProject", catalog=builtin_catalog)
    before = ProjectGenerationFingerprint_Get(model)
    saved = QualityResult_Save(
        root,
        task="host_tests",
        succeeded=True,
        duration=1.25,
        summary="checks=9307",
    )
    assert saved.result == "passed"
    assert QualityResults_Load(root) == (saved,)
    assert ProjectGenerationFingerprint_Get(model) == before
    document = json.loads(
        (root / ".fccg" / "quality-results.json").read_text(encoding="utf-8")
    )
    assert set(document["results"]["host_tests"]) == {
        "task",
        "result",
        "timestamp",
        "duration",
        "summary",
    }


def test_source_package_is_deterministic_and_keeps_real_test_sources(
    tmp_path: Path, workspace_root: Path
) -> None:
    first = SourcePackage_Export(workspace_root, tmp_path / "first.zip")
    second = SourcePackage_Export(workspace_root, tmp_path / "second.zip")
    assert first.file_count == second.file_count
    assert first.destination.read_bytes() == second.destination.read_bytes()
    with zipfile.ZipFile(first.destination) as archive:
        names = set(archive.namelist())
    assert "SilverStar_FCCG/tests/test_project_domain.py" in names
    assert (
        "SilverStar_FCCG/plugins/builtin/silverstar_core_0_1_0/"
        "payload/Tests/Host/test_interfaces.c"
    ) in names
    assert "SilverStar_FCCG/src/silverstar_fccg/build/runner.py" in names
    assert not any("/build/FCCG/" in name for name in names)
    assert not any(name.endswith((".o", ".d", ".lst", ".elf", ".bin", ".hex", ".map")) for name in names)


def test_source_package_omits_disposable_workspaces(tmp_path: Path) -> None:
    root = tmp_path / "Source"
    root.mkdir()
    (root / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    scratch = root / ".work" / "generated"
    scratch.mkdir(parents=True)
    (scratch / "generated.py").write_text("VALUE = 2\n", encoding="utf-8")
    nested_scratch = root / "nested" / ".work"
    nested_scratch.mkdir(parents=True)
    (nested_scratch / "generated.py").write_text("VALUE = 3\n", encoding="utf-8")
    result = SourcePackage_Export(root, tmp_path / "source.zip")
    with zipfile.ZipFile(result.destination) as archive:
        assert archive.namelist() == ["SilverStar_FCCG/source.py"]


def test_non_build_tasks_have_one_task_step_and_host_compiler_is_absolute(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Runner"
    root.mkdir()
    (root / "SilverStar.ssproject").write_text("{}", encoding="utf-8")
    (root / "Makefile").write_text(
        "# SilverStar authoritative build entry\n"
        ".PHONY: host-tests\n"
        "host-tests:\n\t@echo ok\n",
        encoding="utf-8",
    )
    model = ReferenceProject_Create("Runner")
    compiler = tmp_path / "Host GCC" / "gcc.exe"
    compiler.parent.mkdir()
    compiler.write_bytes(b"")
    model.build = replace(
        model.build,
        tool_paths={"host_gcc": str(compiler), "make": "mingw32-make"},
    )
    runner = BuildRunner(WorkspacePolicy(root))
    plan = runner.Plan_Get(model, root, BuildAction.HOST_TESTS)
    command = runner.Command_Get(model, BuildAction.HOST_TESTS)
    assert plan.total_steps == 1
    assert plan.compile_steps == 0
    host_argument = next(value for value in command if value.startswith("HOST_CC="))
    assert host_argument == f"HOST_CC={compiler.resolve().as_posix()}"
    assert '"' not in host_argument


def test_clean_all_stays_inside_workspace_and_preserves_test_sources(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "fccg"
    (root / ".git").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    removable = (
        root / "build" / "FCCG" / "target.o",
        root / "tests" / "generated_projects" / "project" / "firmware.elf",
        root / "tests" / ".cache-history" / "cache.bin",
        root / "tests" / ".inspect-history.ini",
        root / "src" / "package" / "__pycache__" / "module.pyc",
    )
    for path in removable:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"artifact")
    test_source = root / "tests" / "test_kept.py"
    test_source.parent.mkdir(parents=True, exist_ok=True)
    test_source.write_text("def test_kept(): pass\n", encoding="utf-8")
    host_source = root / "plugins" / "builtin" / "payload" / "Tests" / "Host" / "test_host.c"
    host_source.parent.mkdir(parents=True, exist_ok=True)
    host_source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

    monkeypatch.setattr(clean_all, "_WorkspaceRoot_Get", lambda: root.resolve())
    dry_count, dry_bytes = clean_all.WorkspaceArtifacts_Clean(dry_run=True)
    assert dry_count >= 4
    assert dry_bytes == 0
    assert all(path.exists() for path in removable)

    removed_count, removed_bytes = clean_all.WorkspaceArtifacts_Clean()
    assert removed_count == dry_count
    assert removed_bytes == 0
    assert all(not path.exists() for path in removable)
    assert test_source.is_file()
    assert host_source.is_file()


def test_clean_all_retries_a_transient_windows_tree_failure(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "retry-tree"
    target.mkdir()
    (target / "artifact.o").write_bytes(b"artifact")
    original = clean_all.shutil.rmtree
    calls = 0

    def transient_failure(path, *args, **kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(145, "directory not empty")
        original(path, *args, **kwargs)

    monkeypatch.setattr(clean_all.shutil, "rmtree", transient_failure)
    monkeypatch.setattr(clean_all.time, "sleep", lambda _seconds: None)
    clean_all._Path_Remove(target)
    assert calls == 2
    assert not target.exists()


def test_generated_architecture_check_treats_plugin_docs_as_import_audit() -> None:
    checker = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
        / "Tools"
        / "check_architecture.ps1"
    ).read_text(encoding="utf-8")
    assert "$fccgMaintenanceDocumentationPath" in checker
    assert "maintenance Markdown was audited during reference import" in checker
