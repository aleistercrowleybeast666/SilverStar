"""The optional logging contract fails closed on inconsistent generated facts."""
from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply


@pytest.fixture(scope="module")
def logging_disabled_project(workspace_root: Path, tmp_path_factory):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("ArchitectureLoggingDisabled")
    previous = deepcopy(model)
    model.protocols["logging"] = None
    LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
    model = service.ProjectConfiguration_Reconcile(model).model
    project = tmp_path_factory.mktemp("logging_architecture")
    service.Project_Save(model, project, confirm_dangerous=True)
    return project


def _Architecture_Run(project: Path, case: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                             str(project / "Tools/check_architecture.ps1")], cwd=project,
                            text=True, capture_output=True, encoding="utf-8", errors="replace")
    (project / f"architecture-{case}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def test_disabled_logging_architecture_accepts_consistent_absence(logging_disabled_project):
    result = _Architecture_Run(logging_disabled_project, "valid")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SSLOG and decoder payload/source absence is verified" in result.stdout


def test_enabled_logging_keeps_complete_codec_gate(workspace_root, tmp_path):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("ArchitectureLoggingEnabled")
    previous = deepcopy(model)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.eskf15"
    LoggingProfile_AvailabilityTransitionApply(previous, model, service.catalog)
    model = service.ProjectConfiguration_Reconcile(model).model
    service.Project_Save(model, tmp_path, confirm_dangerous=True)
    result = _Architecture_Run(tmp_path, "enabled")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Record Catalog, decoder profile" in result.stdout


@pytest.mark.parametrize("relative", [
    "Generated/unreviewed_audit.py",
    "Generated/__pycache__/memory_audit.pyc",
])
def test_generated_audit_exception_does_not_hide_other_files(logging_disabled_project, relative):
    project = logging_disabled_project
    unexpected = project / relative
    assert not unexpected.exists()
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"unreviewed fixture")
    try:
        result = _Architecture_Run(project, "unexpected_audit_" + unexpected.suffix)
        assert result.returncode != 0
        assert "outside the reviewed thin-glue set" in result.stdout
    finally:
        unexpected.unlink()


def test_exact_auto_link_recipe_does_not_allow_another_python_generator(logging_disabled_project):
    project = logging_disabled_project
    makefile = project / "Makefile"
    original = makefile.read_bytes()
    try:
        with makefile.open("a") as stream:
            stream.write("\nunreviewed-generator:\n\tpython Tools/unreviewed_generator.py\n")
        result = _Architecture_Run(project, "unexpected_generator")
        assert result.returncode != 0
        assert "invokes a generator" in result.stdout
    finally:
        makefile.write_bytes(original)


@pytest.mark.parametrize("case", [
    "missing", "invalid", "duplicate", "literal_mismatch", "semantics_mismatch",
    "semantics_missing", "selected_source", "decoder_payload", "decoder_package",
])
def test_disabled_logging_architecture_rejects_inconsistent_facts(logging_disabled_project, case):
    project = logging_disabled_project
    header = project / "Generated/Inc/project_flight_config.h"
    semantics = project / "Generated/project_semantics.json"
    graph = project / "Generated/project_sources.mk"
    original = {path: path.read_bytes() for path in (header, semantics, graph)}
    added = []
    try:
        if case in {"missing", "invalid", "duplicate", "literal_mismatch"}:
            text = header.read_text(encoding="utf-8")
            declaration = next(line for line in text.splitlines()
                               if line.startswith("#define SILVERSTAR_PROTOCOL_LOGGING_ENABLED"))
            replacement = {"missing": "", "invalid": declaration.replace("0U", "2U"),
                           "duplicate": declaration + "\n" + declaration,
                           "literal_mismatch": declaration.replace("0U", "1U")}[case]
            header.write_text(text.replace(declaration, replacement), encoding="utf-8")
        elif case in {"semantics_mismatch", "semantics_missing"}:
            value = json.loads(semantics.read_text(encoding="utf-8"))
            if case == "semantics_missing":
                del value["protocols"]["logging"]
            else:
                value["protocols"]["logging"] = {"component": "silverstar.protocol.logging.sslog0"}
            semantics.write_text(json.dumps(value), encoding="utf-8")
        else:
            relative = ("unexpected.ssdecoder" if case == "decoder_package"
                        else "Generated/Src/project_log_decoder_profile.c")
            payload = project / relative
            assert not payload.exists()
            payload.write_text("/* deliberately invalid negative fixture */\n", encoding="utf-8")
            added.append(payload)
            if case == "selected_source":
                with graph.open("a", encoding="utf-8") as stream:
                    stream.write("\nC_SOURCES += " + relative + "\n")
        result = _Architecture_Run(project, case)
        assert result.returncode != 0, result.stdout + result.stderr
        expected = ("exactly one literal" if case in {"missing", "invalid", "duplicate"}
                    else "protocol selection" if case in {"literal_mismatch", "semantics_mismatch"}
                    else "explicitly declare" if case == "semantics_missing"
                    else "authoritative graph" if case == "selected_source"
                    else "decoder package" if case == "decoder_package" else "decoder payload")
        assert expected in result.stdout, result.stdout + result.stderr
    finally:
        for path, data in original.items():
            path.write_bytes(data)
        for path in added:
            path.unlink()
