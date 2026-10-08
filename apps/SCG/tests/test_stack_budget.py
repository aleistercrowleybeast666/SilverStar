from __future__ import annotations

import json
import os
import importlib.util
from pathlib import Path

import pytest

_tool = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py"
_tool = Path(os.environ.get("SILVERSTAR_STACK_CHECKER_SOURCE", str(_tool)))
_spec = importlib.util.spec_from_file_location("check_task_stacks", _tool)
stacks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stacks)


def _DependencyFixture_Write(path, source, monkeypatch):
    path.write_text("fixture.o: " + source + "\n", encoding="utf8")
    if hasattr(stacks, "BINDING_DEPENDENCIES_V2"):
        import hashlib
        monkeypatch.setitem(stacks.BINDING_DEPENDENCIES_V2, source, [hashlib.sha256(source.encode()).hexdigest()])


def _ElfFixture_Create(tmp_path: Path, monkeypatch, *, serial="", frame=64):
    (tmp_path / "test.c").write_text("", encoding="utf8")
    # Explicit fixture-only reviewed empty source, not a production exemption.
    monkeypatch.setitem(stacks.BINDING_SOURCE_V2, "test.c", [stacks.BindingSourceHash_Get("")])
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
    _DependencyFixture_Write(build / "test.d", "test.c", monkeypatch)
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


@pytest.mark.parametrize("layout", ["auto", "eskf_window_sram"])
def test_stack_budget_reads_selected_layout_elf_and_frames(tmp_path, monkeypatch, layout):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    build = root / "build/FCCG/SilverStar_F407/Release"
    selected = build / layout
    selected.mkdir()
    (build / "test.elf").rename(selected / "test.elf")
    (build / "test.su").rename(selected / "test.su")
    (build / "test.d").rename(selected / "test.d")
    (build / "test.elf").write_bytes(b"different legacy ELF")
    with pytest.raises(ValueError, match="Missing source stack report"):
        stacks.StackReport_Build(root, "Release", "unused-")
    report = stacks.StackReport_Build(root, "Release", "unused-", layout)
    assert report["passes"] and Path(report["elf"]).parent.name == layout
    import hashlib
    assert report["elf_sha256"] == hashlib.sha256((selected / "test.elf").read_bytes()).hexdigest()


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

@pytest.mark.parametrize("mutation", ["unknown_source", "missing_dependency", "changed_dependencies"])
def test_complete_compilation_input_contract_fails_closed(tmp_path, monkeypatch, mutation):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    dependency = root / "build/FCCG/SilverStar_F407/Release/test.d"
    if mutation == "unknown_source":
        (root / "test.c").write_text("void mutate(void) { *(unsigned *)0x20000000 = 0; }", encoding="utf8")
    elif mutation == "missing_dependency":
        dependency.unlink()
    else:
        dependency.write_text("fixture.o: test.c unknown_header.h\n", encoding="utf8")
    with pytest.raises(ValueError):
        stacks.StackReport_Build(root, "Release", "fixture-")


@pytest.mark.parametrize("mutation", ["changed_inc", "missing_inc", "emptied_source"])
def test_reviewed_compilation_inputs_reject_non_header_and_empty_mutations(tmp_path, monkeypatch, mutation):
    """Exercise the public source verifier; no ARM or linked-code claim."""
    source = "Devices/SensorBus/Src/sensor_bmi088_sync.c"
    included = "Devices/SensorBus/Src/bmi088_sync_image.inc"
    payload = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_sensor_register_bus/payload"
    build = tmp_path / "build"
    for name in (source, included):
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((payload / name).read_bytes())
    dependencies = [source, included]
    import hashlib
    monkeypatch.setitem(stacks.BINDING_DEPENDENCIES_V2, source,
                        [hashlib.sha256("\n".join(dependencies).encode()).hexdigest()])
    report = build / Path(source).with_suffix(".d")
    report.parent.mkdir(parents=True)
    report.write_text("fixture.o: " + " ".join(dependencies) + "\n", encoding="utf8")
    assert stacks.BindingSources_Verify(tmp_path, [source], build)
    if mutation == "changed_inc":
        original = (tmp_path / included).read_text(encoding="utf8")
        changed = original.replace("0xc8", "0xc9", 1)
        assert changed != original
        (tmp_path / included).write_text(changed, encoding="utf8")
    elif mutation == "missing_inc":
        (tmp_path / included).unlink()
    else:
        (tmp_path / source).write_text("", encoding="utf8")
    with pytest.raises(ValueError):
        stacks.BindingSources_Verify(tmp_path, [source], build)


def test_unknown_empty_source_is_not_reviewed(tmp_path):
    (tmp_path / "unknown.c").write_text("", encoding="utf8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "unknown.d").write_text("fixture.o: unknown.c\n", encoding="utf8")
    with pytest.raises(ValueError):
        stacks.BindingSources_Verify(tmp_path, ["unknown.c"], build)


@pytest.mark.parametrize('mutation', ['patch', 'runtime'])
def test_product_patch_binding_accepts_only_authorized_complete_header(tmp_path, mutation):
    payload = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload'
    relative = 'System/User/system_user_config.h'
    text = (payload / relative).read_text(encoding='utf-8')
    assert stacks.BindingSourceHash_Get(text) == 'ffb28f9bf8e08e73c80a16c1121e8c37954f7bb7ade95f2aa47a5226787cc840'
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text(text, encoding='utf-8')
    stacks.BindingHeader_Verify(tmp_path, relative)
    changed = (text.replace('SILVERSTAR_VERSION_PATCH     2', 'SILVERSTAR_VERSION_PATCH     3')
               if mutation == 'patch' else text.replace('SYSTEM_LOCAL_GRAVITY_MPS2       9.78f',
                                                       'SYSTEM_LOCAL_GRAVITY_MPS2       9.79f'))
    assert changed != text
    target.write_text(changed, encoding='utf-8')
    with pytest.raises(ValueError, match='Changed or missing reviewed callback compilation input'):
        stacks.BindingHeader_Verify(tmp_path, relative)
