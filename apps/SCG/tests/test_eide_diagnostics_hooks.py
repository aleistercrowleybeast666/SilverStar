"""Host-only EIDE lifecycle tests; no hardware or firmware execution."""
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from silverstar_diagnostics.eide import EideHooks_Create, EideHooks_Merge, EideDiagnostics_Bind
from silverstar_diagnostics.contract import DiagnosticError
from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Create


def test_macro_paths_are_quoted_before_native_eide_expansion():
    hooks = EideHooks_Create(["C:/Program Files/SCG/SCG.exe"])
    before = hooks["beforeBuildTasks"][0]
    after = hooks["afterBuildTasks"][0]
    assert '"${ProjectRoot}/Flight.ssdiag"' in before["command"]
    assert '"${OutDir}/${ProjectName}.elf"' in after["command"]
    assert before["abortAfterFailed"] and after["abortAfterFailed"]
    assert '"--diagnostics-eide" "bind"' in after["command"]
    assert "Flash" not in after["command"]


def test_merge_preserves_user_tasks_flags_and_is_idempotent():
    old = {"c/cpp-compiler": {"C_FLAGS": "-DUSER_FLAG=1"},
           "beforeBuildTasks": [{"name": "user before", "command": "echo user"}],
           "afterBuildTasks": [{"name": "user after", "command": "echo done"}]}
    unchanged = deepcopy(old)
    hooks = EideHooks_Create(["SCG.exe"])
    changed = EideHooks_Merge(old, hooks)
    assert old == unchanged
    assert EideHooks_Merge(changed, hooks) == changed
    assert changed["c/cpp-compiler"] == old["c/cpp-compiler"]
    assert changed["beforeBuildTasks"][1:] == old["beforeBuildTasks"]
    assert changed["afterBuildTasks"][:-1] == old["afterBuildTasks"]


def test_fresh_generated_flight_has_native_hooks_and_no_copied_runtime(builtin_catalog, tmp_path):
    from silverstar_fccg.generator.assembler import ProjectAssembler
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.project.reference import ReferenceProject_Create
    assembler = ProjectAssembler(WorkspacePolicy(tmp_path), builtin_catalog)
    model = ReferenceProject_Create("EIDE Space Name", catalog=builtin_catalog)
    root = tmp_path / "Flight"
    plan = assembler.Plan(model, root)
    assert plan.valid
    assembler.Apply(model, plan)
    first = (root / ".eide/eide.yml").read_bytes()
    value = yaml.safe_load(first)
    for target in ("Release", "Debug"):
        options = value["targets"][target]["toolchainConfigMap"]["GCC"]["options"]
        assert options["beforeBuildTasks"] == EideHooks_Create()["beforeBuildTasks"]
        assert options["afterBuildTasks"] == EideHooks_Create()["afterBuildTasks"]
    source = root / "Devices/IMU/JY901B/Src/jy901b_device.c"
    source.write_bytes(source.read_bytes() + b"\n/* preserved user input */\n")
    retained = source.read_bytes()
    from silverstar_fccg.project.model import ProjectModel_Load
    reopened = ProjectModel_Load(root / "SilverStar.ssproject")
    assembler.Apply(reopened, assembler.Plan(reopened, root))
    assert (root / ".eide/eide.yml").read_bytes() == first
    assert source.read_bytes() == retained
    assert not (root / "Refresh_EIDE_Diagnostics.py").exists()
    assert not (root / "ssdiag_runtime").exists()


@pytest.mark.parametrize("case", ["missing", "outside", "missing_hex", "invalid_elf"])
def test_failed_postbuild_leaves_pending_and_returns_failure(tmp_path, case):
    root = tmp_path / "Flight"
    root.mkdir()
    descriptor = root / "Flight.ssdiag"
    descriptor.write_text(json.dumps(ProjectDescriptor_Create("Test", "STM32F407VET6")))
    elf = (tmp_path if case == "outside" else root) / "test.elf"
    if case != "missing":
        elf.write_bytes(b"not an ELF")
    if case == "invalid_elf":
        elf.with_suffix(".hex").write_text(":00000001FF\n")
    with pytest.raises((DiagnosticError, OSError)):
        EideDiagnostics_Bind(descriptor, elf)
    assert json.loads(descriptor.read_text())["state"] == "pending_build"


def test_host_cli_runs_without_gui_and_reports_failed_bind(tmp_path):
    descriptor = tmp_path / "Flight.ssdiag"
    descriptor.write_text(json.dumps(ProjectDescriptor_Create("Test", "STM32F407VET6")))
    entry = Path(__file__).resolve().parents[1] / "main.py"
    command = [sys.executable, "-X", "utf8", "-B", str(entry), "--diagnostics-eide"]
    begin = subprocess.run([*command, "begin", "--project", str(descriptor)],
                           capture_output=True, text=True, timeout=20)
    assert begin.returncode == 0, begin.stderr
    assert json.loads(begin.stdout)["diagnostics"] == "pending_build"
    bind = subprocess.run([*command, "bind", "--project", str(descriptor),
                           "--elf", str(tmp_path / "missing.elf")],
                          capture_output=True, text=True, timeout=20)
    assert bind.returncode == 1 and "ELF missing" in bind.stderr
    assert json.loads(descriptor.read_text())["state"] == "pending_build"
