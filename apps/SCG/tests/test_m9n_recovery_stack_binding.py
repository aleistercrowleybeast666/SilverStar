"""Synthetic ELF negatives for reviewed recovery bindings; real ARM evidence is separate."""
from pathlib import Path
import re

import pytest
from test_stack_budget import stacks, _ElfFixture_Create, _DependencyFixture_Write


def _StartupFixture(root, monkeypatch, *, separate=False, mutation=None, gnss_only=False):
    root = _ElfFixture_Create(root, monkeypatch)
    original_read = stacks.Command_Read
    builtin = Path(__file__).resolve().parents[1] / "plugins/builtin"
    owner = {
        stacks.STARTUP_CALLBACK_SOURCES[0]: builtin / "silverstar_device_imu_jy901b/payload",
        stacks.STARTUP_CALLBACK_SOURCES[1]: builtin / "silverstar_device_gnss_neo_m9n/payload",
    }
    core = builtin / "silverstar_core_0_1_0/payload"
    for path in ("System/Src/system_device_startup.c", "System/Inc/system_device_startup.h"):
        target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((core / path).read_text(encoding="utf8"), encoding="utf8")
    callbacks = []
    tables = {}
    build = root / "build/FCCG/SilverStar_F407/Release"
    selected = stacks.STARTUP_CALLBACK_SOURCES[1:] if gnss_only else stacks.STARTUP_CALLBACK_SOURCES
    for source in selected:
        text = (owner[source] / source).read_text(encoding="utf8")
        if source.endswith("neo_m9n_startup.c"):
            if mutation == "init_overwrite":
                text = text.replace("config.operations = &s_operations;", "config.operations = &s_operations; config.operations = &other;")
            elif mutation == "operations":
                text = text.replace("config = context->controller.config;",
                    "config = context->controller.config;\n    config.operations = replacement;")
            elif mutation == "provenance":
                text = text.replace("config = context->controller.config;", "config = arbitrary;")
            elif mutation == "table":
                text = text.replace("    NeoM9nStartup_SamplePoll\n", "    NeoM9nStartup_SamplePoll,\n    UnknownCallback\n")
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf8")
        su = build / Path(source).with_suffix(".su")
        su.parent.mkdir(parents=True, exist_ok=True)
        su.write_text("", encoding="utf8")
        _DependencyFixture_Write(su.with_suffix(".d"), source, monkeypatch)
        table = re.search(r"static\s+const\s+SystemDeviceStartupOperations\s+s_operations\s*=\s*\{(.*?)\};", text, re.DOTALL)
        entries = re.findall(r"\b[A-Za-z]\w*\b", table[1])
        callbacks.extend(entries)
        tables["NeoM9nStartup_Init" if "neo_m9n" in source else "Jy901bStartup_Init"] = entries
    selected = list(selected) + ["System/Src/system_device_startup.c"]
    (build / "System/Src").mkdir(parents=True, exist_ok=True)
    (build / "System/Src/system_device_startup.su").write_text("")
    _DependencyFixture_Write(build / "System/Src/system_device_startup.d", "System/Src/system_device_startup.c", monkeypatch)
    manifest = root / "Generated/project_sources.mk"
    manifest.write_text("C_SOURCES += \\\n  test.c \\\n  " + " \\\n  ".join(selected) + "\n\n", encoding="utf8")
    edges = {
        "SystemDeviceStartup_Init": [],
        "SystemDeviceStartup_Tick": [],
        "Jy901bStartup_Init": ["SystemDeviceStartup_Init"],
        "NeoM9nStartup_Init": ["SystemDeviceStartup_Init"],
        "NeoM9nStartup_Tick": ["SystemDeviceStartup_Tick"],
    }
    if gnss_only:
        del edges["Jy901bStartup_Init"]
    caller = "NeoM9nStartup_RecoveryBegin" if separate else "NeoM9nStartup_Tick"
    edges.setdefault(caller, []).append("SystemDeviceStartup_Init")
    if separate:
        edges["NeoM9nStartup_Tick"].append(caller)
    if mutation == "caller":
        edges["UnreviewedStartup"] = ["SystemDeviceStartup_Init"]
    if mutation == "recursion":
        edges["SystemDeviceStartup_Init"].append("NeoM9nStartup_Tick")
    for name in callbacks:
        edges[name] = []
    edges["NeoM9nStartup_SamplePoll"] = ["GnssNeoM9n_Process"]
    edges["GnssNeoM9n_Process"] = []
    addresses = {name: 0x08002000 + index * 16 for index, name in enumerate(callbacks)}
    table_addresses = {name: 0x08001000 + index * 0x100 for index, name in enumerate(tables)}
    extra = ""
    for name, callees in edges.items():
        extra += "08000000 <" + name + ">:\n"
        for callee in callees:
            extra += " 8000000: f000 f000 bl 8000000 <" + callee + ">\n"
        if name == "SystemDeviceStartup_Tick" or (name == caller and mutation == "indirect"):
            for slot in ([4,0,8,12,16,20,24] if name == "SystemDeviceStartup_Tick" else [0]):
                extra += f" 8000002: 680b ldr r3, [r2, #{slot}]\n 8000004: 4798 blx r3\n"
            if mutation == "extra_tick_indirect" and name == "SystemDeviceStartup_Tick":
                extra += " 8000006: 4798 blx r3\n"
        if name in table_addresses:
            extra += f" 8000008: {table_addresses[name]:08x} .word 0x{table_addresses[name]:08x}\n"
        extra += " 8000008: 4770 bx lr\n"
    su = build / "test.su"
    with su.open("a", encoding="utf8") as stream:
        frames = {"NeoM9nStartup_SamplePoll": 112, "GnssNeoM9n_Process": 344}
        stream.write("".join("fixture.c:1:1:" + name + "\t" + str(frames.get(name,16)) + "\tstatic\n" for name in edges))
    def read(command, cwd):
        if "objdump" in command[0] and "-s" in command:
            address = int(next(arg.split("=")[1] for arg in command if arg.startswith("--start-address=")),16)
            name = next(name for name, value in table_addresses.items() if value == address)
            raw = b"".join((addresses[entry] | 1).to_bytes(4,"little") for entry in tables[name])
            if mutation == "table_pointers": raw = b"\0" * 28
            return "file format elf32-littlearm\n" + "\n".join(f" {address+i:x} " + " ".join(raw[j:j+4].hex() for j in range(i,min(i+16,len(raw)),4)) for i in range(0,len(raw),16))
        text = original_read(command, cwd)
        if "nm" in command[0]:
            return text + "".join(f"{address:08x} 0000001c r s_operations\n" for address in table_addresses.values()) + "".join(f"{address:08x} 00000020 t {name}\n" for name,address in addresses.items())
        if "objdump" in command[0]:
            text = text.replace("08000000 <AppTask_Device>:\n",
                "08000000 <AppTask_Device>:\n 8000000: f000 f000 bl 8000000 <NeoM9nStartup_Tick>\n")
            return text + extra
        return text
    monkeypatch.setattr(stacks, "Command_Read", read)
    return root


@pytest.mark.parametrize("separate", [False, True])
@pytest.mark.parametrize("gnss_only", [False, True])
def test_reviewed_inlined_and_separate_recovery_binding(tmp_path, monkeypatch, separate, gnss_only):
    root = _StartupFixture(tmp_path, monkeypatch, separate=separate, gnss_only=gnss_only)
    report = stacks.StackReport_Build(root, "Release", "fixture-")
    assert report["passes"]
    device = next(row for row in report["tasks"] if row["task"] == "Device")
    assert device["call_chain_bytes"] >= 64 + 16 + 16 + 112 + 344
    assert [row["function"] for row in device["chain"]][-2:] == ["NeoM9nStartup_SamplePoll", "GnssNeoM9n_Process"]


@pytest.mark.parametrize("mutation,message", [
    ("caller", "Unreviewed device startup operation binding"),
    ("operations", "Unreviewed M9N recovery operation binding"),
    ("provenance", "Unreviewed M9N recovery operation binding"),
    ("table", "Unreviewed device startup operation table"),
    ("recursion", "Recursive stack path"),
    ("indirect", "Unresolved stack usage"),
])
def test_recovery_binding_fails_closed(tmp_path, monkeypatch, mutation, message):
    root = _StartupFixture(tmp_path, monkeypatch, mutation=mutation)
    with pytest.raises(ValueError, match=message):
        stacks.StackReport_Build(root, "Release", "fixture-")

@pytest.mark.parametrize("mutation", ["init_overwrite", "extra_tick_indirect", "table_pointers"])
def test_startup_parent_counterexamples_rejected(tmp_path, monkeypatch, mutation):
    with pytest.raises(ValueError):
        stacks.StackReport_Build(_StartupFixture(tmp_path, monkeypatch, mutation=mutation), "Release", "fixture-")
