"""Synthetic ELF negatives for reviewed recovery bindings; real ARM evidence is separate."""
from pathlib import Path
import re

import pytest
from test_stack_budget import stacks, _ElfFixture_Create


def _StartupFixture(root, monkeypatch, *, separate=False, mutation=None):
    root = _ElfFixture_Create(root, monkeypatch)
    original_read = stacks.Command_Read
    builtin = Path(__file__).resolve().parents[1] / "plugins/builtin"
    owner = {
        stacks.STARTUP_CALLBACK_SOURCES[0]: builtin / "silverstar_device_imu_jy901b/payload",
        stacks.STARTUP_CALLBACK_SOURCES[1]: builtin / "silverstar_device_gnss_neo_m9n/payload",
    }
    callbacks = []
    build = root / "build/FCCG/SilverStar_F407/Release"
    for source in stacks.STARTUP_CALLBACK_SOURCES:
        text = (owner[source] / source).read_text(encoding="utf8")
        if source.endswith("neo_m9n_startup.c"):
            if mutation == "operations":
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
        table = re.search(r"static\s+const\s+SystemDeviceStartupOperations\s+s_operations\s*=\s*\{(.*?)\};", text, re.DOTALL)
        callbacks.extend(re.findall(r"\b[A-Za-z]\w*\b", table[1]))
    manifest = root / "Generated/project_sources.mk"
    manifest.write_text("C_SOURCES += \\\n  test.c \\\n  " + " \\\n  ".join(stacks.STARTUP_CALLBACK_SOURCES) + "\n\n", encoding="utf8")
    edges = {
        "SystemDeviceStartup_Init": [],
        "SystemDeviceStartup_Tick": [],
        "Jy901bStartup_Init": ["SystemDeviceStartup_Init"],
        "NeoM9nStartup_Init": ["SystemDeviceStartup_Init"],
        "NeoM9nStartup_Tick": ["SystemDeviceStartup_Tick"],
    }
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
    extra = ""
    for name, callees in edges.items():
        extra += "08000000 <" + name + ">:\n"
        for callee in callees:
            extra += " 8000000: f000 f000 bl 8000000 <" + callee + ">\n"
        if name == "SystemDeviceStartup_Tick" or (name == caller and mutation == "indirect"):
            extra += " 8000004: 4798 blx r3\n"
        extra += " 8000008: 4770 bx lr\n"
    su = build / "test.su"
    with su.open("a", encoding="utf8") as stream:
        stream.write("".join("fixture.c:1:1:" + name + "\t16\tstatic\n" for name in edges))
    def read(command, cwd):
        text = original_read(command, cwd)
        if "objdump" in command[0]:
            text = text.replace("08000000 <AppTask_Device>:\n",
                "08000000 <AppTask_Device>:\n 8000000: f000 f000 bl 8000000 <NeoM9nStartup_Tick>\n")
            return text + extra
        return text
    monkeypatch.setattr(stacks, "Command_Read", read)
    return root


@pytest.mark.parametrize("separate", [False, True])
def test_reviewed_inlined_and_separate_recovery_binding(tmp_path, monkeypatch, separate):
    root = _StartupFixture(tmp_path, monkeypatch, separate=separate)
    report = stacks.StackReport_Build(root, "Release", "fixture-")
    assert report["passes"]


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
