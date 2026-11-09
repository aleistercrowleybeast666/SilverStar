from __future__ import annotations

import json
import os
import re
import importlib.util
import zipfile
import sys
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


def _AssemblyFixture_Extend(base, extra, connections=None, fixed_addresses=None):
    """Give historical callback fixtures a consistent ELF FUNC/address model.

    Their source/table mutation expectations remain unchanged. This is only a
    synthetic tool-output builder; actual ARM ELF validation is separate.
    """
    blocks = {}
    for text in (base, extra):
        name = None
        for line in text.splitlines():
            if match := re.match(r"^([0-9a-f]+) <([^>]+)>:", line):
                name = match[2]
                blocks[name] = []
            elif name and (match := re.match(r"\s*[0-9a-f]+:\s+((?:(?:[0-9a-f]{8}|[0-9a-f]{4})\s+)+)(\S+)\s*(.*)", line)):
                blocks[name].append((match[1].strip(), match[2], match[3]))
    addresses = {name: 0x08010000 + index * 0x100 for index, name in enumerate(blocks)}
    addresses.update(fixed_addresses or {})
    for name, target in (connections or {}).items():
        blocks[name].insert(0, ("f000 f000", "bl", f"0 <{target}>"))
    assembly, symbols = "Disassembly of section .text:\n", ""
    for name, rows in blocks.items():
        start = cursor = addresses[name]
        assembly += f"{start:08x} <{name}>:\n"
        # Literals are data after the return, not executed fake instructions.
        rows = [row for row in rows if not row[1].startswith(".")] + [row for row in rows if row[1].startswith(".")]
        for machine, op, args in rows:
            if target := re.search(r"([0-9a-f]+)\s+<([^>+]+)(?:\+([^>]+))?>", args):
                if target[2] in addresses:
                    args = args[:target.start()] + f"{addresses[target[2]] + (int(target[3], 0) if target[3] else 0):x} <{target[2]}>" + args[target.end():]
            assembly += f" {cursor:x}: {machine} {op} {args}\n"
            cursor += len(re.sub(r"\s", "", machine)) // 2
        symbols += f"{start:08x} g F .text {cursor - start:08x} {name}\n"
    return assembly, symbols, addresses


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
    addresses = {name: 0x08000000 + index * 0x100 for index, name in enumerate(names)}
    disassembly = "Disassembly of section .text:\n"
    symbol_table = ""
    for name in names:
        start = addresses[name]
        cursor = start
        disassembly += f"{start:08x} <{name}>:\n"
        if name in edges:
            disassembly += f" {cursor:x}: f000 f000 bl {addresses[edges[name]]:x} <{edges[name]}>\n"
            cursor += 4
        if name == "library":
            disassembly += f" {cursor:x}: e96d ce04 strd ip, lr, [sp, #-16]!\n"
            cursor += 4
        if name == "AppTask_Serial" and serial:
            instruction = serial.strip().split(":", 1)[1].strip()
            instruction = instruction.replace("8000000 <AppTask_Serial>", f"{start:x} <AppTask_Serial>")
            disassembly += f" {cursor:x}: {instruction}\n"
            machine = re.match(r"((?:[0-9a-f]{4,8}\s+)+)", instruction)[1]
            cursor += len(re.sub(r"\s", "", machine)) // 2
        disassembly += f" {cursor:x}: 4770 bx lr\n"
        symbol_table += f"{start:08x} g F .text {cursor + 2 - start:08x} {name}\n"
    (build / "test.su").write_text("".join(
        f"fixture.c:1:1:{name}\t{frame}\tstatic\n" for name in names if name != "library"
    ), encoding="utf-8")
    _DependencyFixture_Write(build / "test.d", "test.c", monkeypatch)
    nm = "".join(f"10000000 00001000 b {symbol}\n" for _, symbol in stacks.TASKS.values())
    def read(command, root):
        if "objdump" in command[0]:
            return symbol_table if "-t" in command else disassembly
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


@pytest.mark.parametrize('diagnostic,frame,expected',[(False,64,2),(False,2000,1),(True,64,2)])
def test_machine_report_marker_only_names_written_budget(tmp_path,monkeypatch,capsys,diagnostic,frame,expected):
    root=_ElfFixture_Create(tmp_path,monkeypatch,frame=frame)
    monkeypatch.setattr(sys,'argv',['check_task_stacks.py','--project',str(root),'--prefix','unused-']+
        (['--diagnostic'] if diagnostic else []))
    assert stacks.main()==expected
    lines=capsys.readouterr().out.splitlines()
    markers=[line for line in lines if line.startswith('FIRMWARE_STACK_REPORT|')]
    if diagnostic:
        assert markers==[]
    else:
        assert len(markers)==1
        path=Path(markers[0].split('|',1)[1])
        assert path.is_absolute() and path.name=='stack-budget.json'
        report=json.loads(path.read_text(encoding='utf8'))
        # This legacy fixture proves task-only arithmetic. Its unchanged
        # positive task result cannot grant strict MSP/ISR acceptance.
        assert report['passes'] is (frame==64)
        assert report['whole_program_stack_acceptance'].startswith('NOT PROVEN')


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


@pytest.mark.parametrize("instruction", [
    " 8000004: 4798 blxne r3\n",
    " 8000004: 469f mov pc, r3\n",
    " 8000004: f8d3 f000 ldr.w pc, [r3]\n",
])
def test_stack_budget_rejects_all_register_indirect_call_forms(tmp_path, monkeypatch, instruction):
    root = _ElfFixture_Create(tmp_path, monkeypatch, serial=instruction)
    with pytest.raises(ValueError, match="Unresolved stack usage"):
        stacks.StackReport_Build(root, "Release", "unused-")


def test_returning_tail_call_in_initializer_does_not_hide_task_business_loop(tmp_path, monkeypatch):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    original = stacks.Command_Read
    base = original(["objdump", "-d"], root)
    base = re.sub(r"(<AppTask_Ins>:\n)", r"\1 8000000: f000 f000 bl 0 <LoopWork>\n", base)
    extra = ("08000000 <Initialize>:\n 8000000: f000 b800 b.w 0 <library>\n"
             "08000000 <LoopWork>:\n 8000000: 4770 bx lr\n")
    assembly, symbols, _ = _AssemblyFixture_Extend(base, extra, {"AppTask_Ins": "Initialize"})
    su = root / "build/FCCG/SilverStar_F407/Release/test.su"
    with su.open("a", encoding="utf8") as stream:
        stream.write("fixture.c:1:1:Initialize\t16\tstatic\nfixture.c:1:1:LoopWork\t512\tstatic\n")
    def Read(command, cwd):
        if "objdump" in command[0]:
            return symbols if "-t" in command else assembly
        return original(command, cwd)
    monkeypatch.setattr(stacks, "Command_Read", Read)
    report = stacks.StackReport_Build(root, "Release", "fixture-")
    task = next(row for row in report["tasks"] if row["task"] == "INS")
    assert task["call_chain_bytes"] == 64 + 512
    assert task["chain"][-1]["function"] == "LoopWork"


def test_diagnostic_never_grants_acceptance_even_with_closed_direct_paths(tmp_path, monkeypatch):
    root = _ElfFixture_Create(tmp_path, monkeypatch)
    report = stacks.StackDiagnostic_Build(root, "Release", "unused-")
    assert report["schema"] == "silverstar.stack-diagnostic/1"
    assert not report["passes"]
    assert all(row["direct_graph_closed"] for row in report["tasks"])
    assert all("margin_bytes" not in row for row in report["tasks"])
    assert report["whole_program_stack_acceptance"].startswith("NOT PROVEN")


@pytest.mark.parametrize("instruction,boundary", [
    (" 8000004: 4798 blx r3\n", "AppTask_Serial"),
    (" 8000004: f000 f000 bl 8000000 <AppTask_Serial>\n", "recursion:AppTask_Serial"),
])
def test_diagnostic_reports_unknown_boundary_without_synthesizing_a_margin(tmp_path, monkeypatch, instruction, boundary):
    root = _ElfFixture_Create(tmp_path, monkeypatch, serial=instruction)
    report = stacks.StackDiagnostic_Build(root, "Release", "unused-")
    serial = next(row for row in report["tasks"] if row["task"] == "Serial")
    assert boundary in serial["unresolved_boundaries"]
    assert not serial["direct_graph_closed"]
    assert not report["passes"]

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
    relative = 'System/User/system_user_config.h'
    # Keep the exact historical V28 review bytes after active owners evolve.
    with zipfile.ZipFile(Path(__file__).parent / 'fixtures/stack_review_20261025.zip') as archive:
        text = archive.read(relative).decode('utf8')
    # V28 reviews these complete source bytes, without granting a compiled
    # dependency closure or weakening either forbidden mutation below.
    # Both original forbidden mutations below remain rejected.
    assert stacks.BindingSourceHash_Get(text) == '4baa9ee7f7292e12b2f81608614d9b2e08c0b21bcaac7c1db971306235e52bf2'
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


def test_source_only_review_cannot_grant_a_compiled_dependency_closure(tmp_path, monkeypatch):
    # Exercise the historical source-only grant, not a later logger revision
    # which must first fail the separate whole-source identity check.
    payload = Path(__file__).parent / 'fixtures/stack_logger_review_20261101'
    relative = 'APP/Src/logger_bus.c'
    destination = tmp_path / relative
    destination.parent.mkdir(parents=True)
    destination.write_bytes((payload / relative).read_bytes())
    build = tmp_path / 'build'
    (build / 'APP/Src').mkdir(parents=True)
    (build / 'APP/Src/logger_bus.d').write_text('fixture.o: ' + relative + '\n', encoding='utf8')
    import hashlib
    monkeypatch.setitem(stacks.BINDING_DEPENDENCIES_V2, relative, [hashlib.sha256(relative.encode()).hexdigest()])
    with pytest.raises(ValueError, match='paired source/compiler input closure'):
        stacks.BindingSources_Verify(tmp_path, [relative], build)


@pytest.mark.parametrize("fault", ["placement", "missing_header", "compiled_graph"])
def test_navigation_review_still_binds_real_complete_compiler_inputs(tmp_path, fault):
    archive_path = Path(__file__).resolve().parents[3] / "docs/evidence/algorithm_stack_binding_20261015/inputs_v2.zip"
    with zipfile.ZipFile(archive_path) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name in archive.namelist():
            if not name.startswith("compiler_fixture/"):
                continue
            target = tmp_path / name.removeprefix("compiler_fixture/")
            assert target.resolve().is_relative_to(tmp_path.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    source = "APP/Src/estimator_bus.c"
    build = tmp_path / "build"
    dependency = build / "APP/Src/estimator_bus.d"
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes((tmp_path / "estimator_bus.d").read_bytes())
    assert stacks.BindingSources_Verify(tmp_path, [source], build)
    if fault == "placement":
        path = tmp_path / source
        text = path.read_text(encoding="utf-8")
        assert "static PLATFORM_CPU_FAST_BSS SystemInertialIncrement" in text
        path.write_text(text.replace("static PLATFORM_CPU_FAST_BSS SystemInertialIncrement",
                                     "static SystemInertialIncrement"), encoding="utf-8")
    elif fault == "missing_header":
        (tmp_path / "Platform/Inc/platform_memory.h").unlink()
    else:
        text = dependency.read_text(encoding="utf-8")
        assert "Platform/Inc/platform_memory.h" in text
        dependency.write_text(text.replace("Platform/Inc/platform_memory.h", ""), encoding="utf-8")
    with pytest.raises(ValueError):
        stacks.BindingSources_Verify(tmp_path, [source], build)


@pytest.mark.parametrize('mutation', ['digest', 'function'])
def test_product_metadata_binding_accepts_only_authorized_complete_source(mutation):
    # v13 approves archived complete bytes. Rendering an old model with a new
    # product/catalog changes its identity and cannot reproduce that review.
    source = Path(__file__).resolve().parents[3] / 'docs/evidence/scg_decoder_binding_20261008/evidence.zip'
    relative = 'Generated/Src/project_metadata.c'
    with zipfile.ZipFile(source) as archive:
        text = archive.read('.work/DecoderBindingApproval_20261008/project/Flight_Controller/' + relative).decode('utf8').replace('\r\n', '\n')
    approved = 'bba3aed1cc73043a10cfd126a7759728a10de53e3769e2563fb209a4b12feadf'
    assert stacks.BindingSourceHash_Get(text) == approved
    assert approved in stacks.BindingSourceVersions_Get(relative)
    changed = (text.replace('0x42A4C1C6UL', '0x42A4C1C7UL') if mutation == 'digest'
               else text.replace('return SILVERSTAR_PROJECT_CONFIG_DIGEST;', 'return 0U;'))
    assert changed != text
    assert stacks.BindingSourceHash_Get(changed) not in stacks.BindingSourceVersions_Get(relative)


@pytest.mark.parametrize('mutation', ['digest', 'function'])
def test_product_decoder_binding_accepts_only_authorized_complete_source(mutation):
    # v14 approves exact archived bytes, not every later renderer's identity.
    source = Path(__file__).resolve().parents[3] / 'docs/evidence/scg_decoder_binding_20261008/evidence.zip'
    relative = 'Generated/Src/project_log_decoder_profile.c'
    with zipfile.ZipFile(source) as archive:
        text = archive.read('.work/DecoderBindingApproval_20261008/project/Flight_Controller/' + relative).decode('utf8').replace('\r\n', '\n')
    approved = 'ee5baec0a73077cdafee252ba8715045db8ee39e4b894c6846be3cd059392616'
    assert stacks.BindingSourceHash_Get(text) == approved
    assert approved in stacks.BindingSourceVersions_Get(relative)
    changed = (text.replace('0xAEU, 0x60U', '0xAFU, 0x60U') if mutation == 'digest'
               else text.replace('profile->package_schema_major = 1U;', 'profile->package_schema_major = 2U;'))
    assert changed != text
    assert stacks.BindingSourceHash_Get(changed) not in stacks.BindingSourceVersions_Get(relative)


INTEGRATION_IDENTITIES = {
    'Generated/Src/project_metadata.c': '7b76da5ac6c0e615a2c76dabf8bf2a8e674b00ca0c3e4d1b81ecc60a1eaf4d00',
    'Generated/Src/project_log_decoder_profile.c': 'ec50f2e5db9a0de82b53c77811f99838bb3ecf2b0f7f6dd94ccb632961b09c51',
}


@pytest.mark.parametrize('relative', [
    'APP/Inc/logger_bus.h', 'APP/Src/logger_bus.c', 'APP/Src/logger_task.c',
    'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c',
    'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c',
    'Generated/Src/project_log_decoder_profile.c', 'Generated/Src/project_metadata.c',
    'System/Inc/system_lifecycle.h', 'System/Inc/system_log_file.h',
    'System/Src/system_console.c', 'System/Src/system_log_file.c'])
def test_uart_review_accepts_exact_owner_and_rejects_changed_complete_input(tmp_path, relative):
    base = Path(__file__).resolve().parents[1]
    if relative.startswith('Generated/'):
        owner = base / 'tests/fixtures/stack_uart_identity_20261013'
    elif relative.startswith('Devices/'):
        owner = base / 'plugins/builtin/silverstar_device_storage_sd_sdio_fatfs/payload'
    elif relative.startswith('FlightLogic/'):
        owner = base / 'plugins/builtin/silverstar_flight_logic_cycle_reference/payload'
    else:
        owner = base / 'plugins/builtin/silverstar_core_0_1_0/payload'
    if relative in ('APP/Inc/logger_bus.h', 'APP/Src/logger_bus.c'):
        text = (base / 'tests/fixtures/stack_logger_review_20261101' / relative).read_text(encoding='utf8')
    elif relative in ('FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c',
                    'System/Src/system_console.c'):
        with zipfile.ZipFile(base / 'tests/fixtures/stack_review_20261025.zip') as archive:
            text = archive.read(relative).decode('utf8')
    else:
        text = (owner / relative).read_text(encoding='utf8')
    assert stacks.BindingSourceHash_Get(text) in stacks.BindingSourceVersions_Get(relative)
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding='utf8')
    stacks.BindingHeader_Verify(tmp_path, relative)
    path.write_text(text + '\nint Unreviewed_Callback(void) { return 1; }\n', encoding='utf8')
    with pytest.raises(ValueError, match='Changed or missing reviewed callback compilation input'):
        stacks.BindingHeader_Verify(tmp_path, relative)


def test_integration_registration_is_exactly_two_complete_sources():
    assert stacks.BINDING_SOURCE_INTEGRATION_IDENTITIES_V15 == {
        name: [digest] for name, digest in INTEGRATION_IDENTITIES.items()}
    assert '414271a0f6546b0b8d251a98b4d0611546fa2f5d572a5c9ba5192a79c43154af' not in stacks.BindingSourceVersions_Get('Generated/Src/project_log_decoder_profile.c')


@pytest.mark.parametrize('relative', INTEGRATION_IDENTITIES)
@pytest.mark.parametrize('mutation', ['identity', 'function', 'unknown_path'])
def test_integration_identity_binding_accepts_exact_sources_and_rejects_changes(tmp_path, monkeypatch, relative, mutation):
    fixture = Path(__file__).parent / 'fixtures/stack_integration_identity_20261009' / relative
    text = fixture.read_text(encoding='utf8')
    assert stacks.BindingSourceHash_Get(text) == INTEGRATION_IDENTITIES[relative]
    target = tmp_path / relative; target.parent.mkdir(parents=True)
    target.write_text(text, encoding='utf8')
    dependency = tmp_path / 'build' / Path(relative).with_suffix('.d')
    dependency.parent.mkdir(parents=True)
    _DependencyFixture_Write(dependency, relative, monkeypatch)
    assert len(stacks.BindingSources_Verify(tmp_path, [relative], tmp_path / 'build')) == 1
    if mutation == 'unknown_path':
        relative = 'Generated/Src/unreviewed_identity.c'
        target = tmp_path / relative
        changed = text
    elif 'metadata' in relative:
        changed = text.replace('0x871692B0UL', '0x871692B1UL') if mutation == 'identity' else text.replace('return SILVERSTAR_PROJECT_CONFIG_DIGEST;', 'return 0U;')
    else:
        changed = text.replace('0x9EU, 0xCAU', '0x9FU, 0xCAU') if mutation == 'identity' else text.replace('profile->package_schema_major = 1U;', 'profile->package_schema_major = 2U;')
    assert mutation == 'unknown_path' or changed != text
    target.write_text(changed, encoding='utf8')
    with pytest.raises(ValueError, match='Changed or unknown complete callback binding source'):
        stacks.BindingSources_Verify(tmp_path, [relative], tmp_path / 'build')


@pytest.mark.parametrize("new_record", ["source", "included_input"])
@pytest.mark.parametrize("revision", [24, 25, 26])
def test_logfile_review_rejects_mixing_individually_known_compiler_inputs(tmp_path, monkeypatch, new_record, revision):
    """New complete identities must still require their exact reviewed pairing."""
    import hashlib
    source = "binding.c"
    header = "binding.h"
    source_text = '#include "binding.h"\nint Binding_ValueGet(void) { return BINDING_VALUE; }\n'
    first = "#define BINDING_VALUE 1\n"
    second = "#define BINDING_VALUE 2\n"
    source_hash = stacks.BindingSourceHash_Get(source_text)
    first_hash = stacks.BindingSourceHash_Get(first)
    second_hash = stacks.BindingSourceHash_Get(second)
    reviewed_sources = (stacks.BINDING_SOURCE_LOGFILE_TRANSFER_V24 if revision == 24
                        else stacks.BINDING_SOURCE_BLOCK_TRANSFER_V25 if revision == 25
                        else stacks.BINDING_SOURCE_OPTIONAL_RESOURCES_V26)
    reviewed_pairs = (stacks.BINDING_COMPILED_INPUTS_LOGFILE_TRANSFER_V24 if revision == 24
                      else stacks.BINDING_COMPILED_INPUTS_BLOCK_TRANSFER_V25 if revision == 25
                      else stacks.BINDING_COMPILED_INPUTS_OPTIONAL_RESOURCES_V26)
    source_table = reviewed_sources if new_record == "source" else stacks.BINDING_SOURCE_V2
    input_table = reviewed_sources if new_record == "included_input" else stacks.BINDING_SOURCE_V2
    monkeypatch.setitem(source_table, source, [source_hash])
    monkeypatch.setitem(input_table, header, [first_hash, second_hash])
    dependencies = [source, header]
    monkeypatch.setitem(stacks.BINDING_DEPENDENCIES_V2, source, [hashlib.sha256("\n".join(dependencies).encode()).hexdigest()])
    closure = stacks.BindingClosureHash_Get(source, source_hash, [[source, source_hash], [header, first_hash]])
    monkeypatch.setitem(reviewed_pairs, source, [closure])
    (tmp_path / source).write_text(source_text, encoding="utf8")
    (tmp_path / header).write_text(first, encoding="utf8")
    build = tmp_path / "build"
    build.mkdir()
    (build / "binding.d").write_text("binding.o: " + " ".join(dependencies) + "\n", encoding="utf8")
    assert len(stacks.BindingSources_Verify(tmp_path, [source], build)) == 1
    (tmp_path / header).write_text(second, encoding="utf8")
    assert stacks.BindingHeader_Verify(tmp_path, header) == second_hash
    with pytest.raises(ValueError, match="Changed paired source/compiler input closure"):
        stacks.BindingSources_Verify(tmp_path, [source], build)
def test_strict_cli_refuses_task_only_pass_without_whole_program_proof(tmp_path, monkeypatch):
    import importlib.util
    import sys
    path = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py'
    spec = importlib.util.spec_from_file_location('strict_stack_cli_negative', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(sys, 'argv', ['checker', '--project', str(tmp_path)])
    monkeypatch.setattr(checker, 'StackReport_Build', lambda *args: {
        'elf': 'firmware.elf', 'tasks': [], 'checks': {'task_only': True}, 'passes': True,
        'whole_program_stack_acceptance': 'NOT PROVEN: missing MSP/ISR proof'})
    assert checker.main() == 2

