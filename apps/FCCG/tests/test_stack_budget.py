from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.reference_overlays import check_task_stacks as stacks


def _ElfFixture_Create(tmp_path: Path, monkeypatch, *, serial="", frame=64):
    (tmp_path / "SilverStar.ssproject").write_text(
        json.dumps({"build": {"target_profile": "SilverStar_F407"}}), encoding="utf-8")
    build = tmp_path / "build/FCCG/SilverStar_F407/Release"
    build.mkdir(parents=True)
    (tmp_path / "Generated").mkdir()
    (tmp_path / "Generated/project_sources.mk").write_text(
        "C_SOURCES += \\\n  test.c\n\n", encoding="utf-8")
    (build / "test.elf").write_bytes(b"fixture ELF, tool output injected")
    names = [entry for entry, _ in stacks.TASKS.values()]
    names += ["main", "AppTasks_Init", "SystemIndicator_Init", "SystemAlignment_Start",
              "SystemAlignment_Process", "library"]
    edges = {"main": "AppTasks_Init", "AppTasks_Init": "SystemIndicator_Init",
             "AppTask_Flight": "SystemAlignment_Process", "AppTask_Serial": "library"}
    disassembly = ""
    for name in names:
        disassembly += f"08000000 <{name}>:\n"
        if name in edges:
            disassembly += f" 8000000: f000 f000 bl 8000000 <{edges[name]}>\n"
        if name == "library":
            disassembly += " 8000004: e96d ce04 strd ip, lr, [sp, #-16]!\n"
        if name == "AppTask_Serial":
            disassembly += serial
        disassembly += " 8000008: 4770 bx lr\n"
    (build / "test.su").write_text("".join(
        f"fixture.c:1:1:{name}\t{frame}\tstatic\n" for name in names if name != "library"
    ), encoding="utf-8")
    nm = "".join(f"10000000 00001000 b {symbol}\n" for _, symbol in stacks.TASKS.values())
    def read(command, root):
        if "objdump" in command[0]:
            return disassembly
        if "nm" in command[0]:
            return nm
        return "Arm GNU test fixture"
    monkeypatch.setattr(stacks, "Command_Read", read)
    return tmp_path


def test_stack_budget_includes_library_preindexed_sp_and_context(tmp_path, monkeypatch):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    report = stacks.StackReport_Build(root, "Release", "unused-")
    assert report["passes"]
    assert len(report["tasks"]) == 8
    serial = next(row for row in report["tasks"] if row["task"] == "Serial")
    assert serial["worst_known_bytes"] == 64 + 16 + 256
    assert serial["chain"][-1] == {"function": "library", "frame_bytes": 16}


def test_stack_budget_fails_insufficient_margin(tmp_path, monkeypatch):
    root = _ElfFixture_Create(tmp_path, monkeypatch, frame=4000)
    report = stacks.StackReport_Build(root, "Release", "unused-")
    assert not report["passes"]
    assert all(not row["passes"] for row in report["tasks"])


def test_stack_budget_rejects_missing_source_frame_report(tmp_path, monkeypatch):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    (root / "Generated/project_sources.mk").write_text(
        "C_SOURCES += \\\n  test.c \\\n  missing.c\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing source stack report; rebuild: missing.c"):
        stacks.StackReport_Build(root, "Release", "unused-")


@pytest.mark.parametrize("instruction, error", (
    (" 8000004: 4798 blx r3\n", "Unresolved stack usage"),
    (" 8000004: f000 f000 bl 8000000 <AppTask_Serial>\n", "Recursive stack path"),
))
def test_stack_budget_rejects_unknown_indirect_and_recursion(tmp_path, monkeypatch, instruction, error):
    root = _ElfFixture_Create(tmp_path, monkeypatch, serial=instruction)
    with pytest.raises(ValueError, match=error):
        stacks.StackReport_Build(root, "Release", "unused-")
