"""Optional maintenance scopes remain bound to configuration and source graph."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from test_architecture_logging_selection import _Architecture_Run


@pytest.fixture(scope="module", params=[False, True])
def maintenance_project(request, workspace_root: Path, tmp_path_factory):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("MaintenanceArchitecture")
    if not request.param:
        model.protocols["maintenance"] = None
    model = service.ProjectConfiguration_Reconcile(model).model
    project = tmp_path_factory.mktemp("maintenance_architecture")
    service.Project_Save(model, project, confirm_dangerous=True)
    return project, request.param


def test_maintenance_architecture_accepts_complete_selected_contract(maintenance_project):
    project, enabled = maintenance_project
    result = _Architecture_Run(project, "valid")
    assert result.returncode == 0, result.stdout + result.stderr
    graph = (project / "Generated/project_sources.mk").read_text(encoding="utf-8")
    assert ("System/Src/system_console.c" in graph) is enabled


@pytest.mark.parametrize("case", [
    "missing", "invalid", "duplicate", "literal_mismatch", "semantics_mismatch",
    "semantics_missing", "saved_mismatch", "console_mismatch", "selected_source", "eide_exclusion",
])
def test_maintenance_architecture_rejects_inconsistent_contract(maintenance_project, case):
    project, enabled = maintenance_project
    header = project / "Generated/Inc/project_flight_config.h"
    semantics = project / "Generated/project_semantics.json"
    saved = project / "SilverStar.ssproject"
    graph = project / "Generated/project_sources.mk"
    eide = project / ".eide/eide.yml"
    original = {p: p.read_bytes() for p in (header, semantics, saved, graph, eide)}
    try:
        if case in {"missing", "invalid", "duplicate", "literal_mismatch", "console_mismatch"}:
            text = header.read_text(encoding="utf-8")
            name = "SYSTEM_USER_CONSOLE_ENABLE" if case == "console_mismatch" else "SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED"
            line = next(line for line in text.splitlines() if line.startswith("#define " + name + " "))
            replacement = ("" if case == "missing" else line.replace(f"{int(enabled)}U", "2U") if case == "invalid"
                           else line + "\n" + line if case == "duplicate"
                           else line.replace(f"{int(enabled)}U", f"{int(not enabled)}U"))
            header.write_text(text.replace(line, replacement), encoding="utf-8")
        elif case in {"semantics_mismatch", "semantics_missing", "saved_mismatch"}:
            path = saved if case == "saved_mismatch" else semantics
            value = json.loads(path.read_text(encoding="utf-8"))
            if case == "semantics_missing":
                del value["protocols"]["maintenance"]
            else:
                value["protocols"]["maintenance"] = None if enabled else {"component": "silverstar.protocol.maintenance.serial_0_0"}
            path.write_text(json.dumps(value), encoding="utf-8")
        elif case == "selected_source":
            if enabled:
                graph.write_text(graph.read_text(encoding="utf-8").replace("  System/Src/system_console.c", "  System/Src/missing_console.c"), encoding="utf-8")
            else:
                with graph.open("a", encoding="utf-8") as stream:
                    stream.write("\nC_SOURCES += System/Src/system_console.c\n")
        else:
            if enabled:
                text = eide.read_text(encoding="utf-8")
                text = text.replace("    excludeList:", "    excludeList:\n      - System/Src/system_console.c", 1)
            else:
                text = "\n".join(line for line in eide.read_text(encoding="utf-8").splitlines() if "system_console.c" not in line) + "\n"
            eide.write_text(text, encoding="utf-8")
        result = _Architecture_Run(project, case)
        assert result.returncode != 0, result.stdout + result.stderr
        expected = ("exactly one literal" if case in {"missing", "invalid", "duplicate"}
                    else "protocol selection" if case in {"literal_mismatch", "semantics_mismatch", "saved_mismatch"}
                    else "explicitly declare" if case == "semantics_missing"
                    else "Console transport literal" if case == "console_mismatch"
                    else "Maintenance source selection" if case == "selected_source"
                    else "EIDE C/assembly source graph differs")
        assert expected in result.stdout, result.stdout + result.stderr
    finally:
        for path, data in original.items():
            path.write_bytes(data)


@pytest.mark.parametrize("scope", ["Adapter", "Inc", "Src"])
def test_enabled_maintenance_missing_scope_still_fails(maintenance_project, scope):
    project, enabled = maintenance_project
    if not enabled:
        pytest.skip("missing-scope negative requires selected Console owner")
    source = project / "Devices/Console/UART" / scope
    detached = project / ("negative_detached_console_" + scope)
    assert source.resolve().is_relative_to(project.resolve())
    assert detached.resolve().is_relative_to(project.resolve())
    source.rename(detached)
    try:
        result = _Architecture_Run(project, "missing_" + scope)
        assert result.returncode != 0
        assert "Architecture scope is missing: Devices\\Console\\UART\\" + scope in result.stdout
    finally:
        detached.rename(source)


def test_disabled_present_console_files_are_still_scanned(maintenance_project):
    project, enabled = maintenance_project
    if enabled:
        pytest.skip("present-unselected-source negative requires disabled maintenance")
    path = project / "Devices/Console/UART/Inc/negative_dependency.h"
    path.parent.mkdir(parents=True)
    path.write_text('#include "system_health.h"\n', encoding="utf-8")
    try:
        result = _Architecture_Run(project, "present_optional_boundary")
        assert result.returncode != 0
        assert "Device core depends on a System interface" in result.stdout
    finally:
        path.unlink()
        for directory in (path.parent, path.parent.parent, path.parent.parent.parent):
            directory.rmdir()


def test_consistent_crlf_header_keeps_literal_contract(maintenance_project):
    project, _enabled = maintenance_project
    header = project / "Generated/Inc/project_flight_config.h"
    original = header.read_bytes()
    try:
        header.write_bytes(original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        result = _Architecture_Run(project, "valid_crlf")
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        header.write_bytes(original)
