"""Actual linked Cortex-M0+ code, including libgcc; no name-based call grants."""
import importlib.util
import json
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "stack_arm_thumb1", _root / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/stack_arm.py")
arm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arm)


def Fixture_Load(configuration):
    path = Path(__file__).parent / "fixtures/stack_thumb1_20261116" / (configuration + ".json")
    data = json.loads(path.read_text(encoding="utf8"))
    memory = {address + index: byte for address, raw in data["memory_segments"]
              for index, byte in enumerate(bytes.fromhex(raw))}
    for entry in data["entries"].values():
        entry["memory"] = memory
    return data["entries"]


@pytest.mark.parametrize("configuration,name", [
    ("Release", "GspMinParser_InputByte"),
    ("Release", "HAL_RCC_ClockConfig"),
    ("Release", "SX1280GetPacketStatus"),
    ("Release", "SX1280SetModulationParams"),
    ("Release", "SX1280SetPacketParams"),
    ("Release", "UART_SetConfig"),
    ("Release", "__aeabi_ddiv"),
    ("Debug", "GspMinParser_InputByte"),
    ("Debug", "SX1280GetPacketStatus"),
    ("Debug", "SX1280SetModulationParams"),
    ("Debug", "SX1280SetPacketParams"),
    ("Debug", "__aeabi_ddiv"),
    ("Debug", "Lora_BusReadSucceeded"),
])
def test_actual_thumb1_switches_and_saved_lr_have_bounded_graph(configuration, name):
    entries = Fixture_Load(configuration)
    proof = arm.Function_Analyze(name, entries[name], entries)
    assert proof["indirect"] == []
    assert proof["unknown_sp"] == []
    assert proof["frame_bytes"] > 0
    assert proof["returns"]


@pytest.mark.parametrize("configuration", ["Release", "Debug"])
@pytest.mark.parametrize("mutation", ["guard", "wrong-index", "bypass", "table-byte", "table-target", "helper-or-base"])
def test_thumb1_switch_mutations_remain_unproved(configuration, mutation):
    entries = Fixture_Load(configuration)
    name = "GspMinParser_InputByte"
    entry = entries[name]
    rows = entry["rows"]
    switch = next(index for index, row in enumerate(rows)
                  if "<__gnu_thumb1_case_uqi>" in row[3] or row[2:4] == ["mov", "pc, r3"])
    targets, guard = arm.Thumb1SwitchTargets_Get(switch, rows, entry, entries)
    compare = next(row for row in rows if row[0] == guard[0])
    if mutation == "guard":
        compare[2] = "movs"
    elif mutation == "wrong-index":
        compare[3] = "r7, #5"
    elif mutation == "bypass":
        # Keep the original reachable entry but jump past the comparison.
        rows[0][2:4] = ["b.n", f"{guard[-1]:x} <{name}+0x0>"]
    elif mutation == "helper-or-base":
        if configuration == "Release":
            entries["__gnu_thumb1_case_uqi"]["rows"][2][3] = "r1, r1, #2"
        else:
            rows[switch - 1][3] = "r3, [r2, r1]"
    else:
        if configuration == "Release":
            base = rows[switch][0] + rows[switch][1]
        else:
            literal = rows[switch - 2]
            location = ((literal[0] + 4) & ~3) + 160
            base = int.from_bytes(bytes(entry["memory"][location + offset] for offset in range(4)), "little")
        if mutation == "table-byte":
            del entry["memory"][base]
        else:
            for offset in range(1 if configuration == "Release" else 4):
                entry["memory"][base + offset] = 0xFF
    assert targets
    proof = arm.Function_Analyze(name, entry, entries)
    assert any(row[1] == "unresolved-switch" for row in proof["indirect"])


@pytest.mark.parametrize("mutation", ["wrong-slot", "register-write", "bypass", "slot-store", "unknown-sp"])
def test_saved_link_return_requires_actual_slot_and_unbroken_restore(mutation):
    entries = Fixture_Load("Debug")
    name = "Lora_BusReadSucceeded"
    rows = entries[name]["rows"]
    index = next(i for i, row in enumerate(rows) if row[2:4] == ["pop", "{r3}"])
    if mutation == "wrong-slot":
        rows[index - 1][3] = "{r4}"
    elif mutation == "register-write":
        rows[index + 1][2:4] = ["movs", "r3, #0"]
    elif mutation == "bypass":
        rows[3][2:4] = ["b.n", f"{rows[index + 2][0]:x} <{name}+0x4e>"]
    elif mutation == "slot-store":
        rows[4][3] = "r1, [sp, #76]"
    else:
        rows[2][3] = "sp, r0"
    proof = arm.Function_Analyze(name, entries[name], entries)
    assert not proof["saved_link_returns"]
    assert any(row[1] == "bx" for row in proof["indirect"])


@pytest.mark.parametrize("mutation", ["none", "writable", "missing-byte", "wrong-extent"])
def test_absolute_table_memory_requires_complete_readonly_elf_section(mutation):
    contents = "Contents of section .rodata:\n 8001000 01020304 050607                      .......\n"
    headers = "  2 .rodata 00000007 08001000 08001000 00001000 2**2\n                  CONTENTS, ALLOC, LOAD, READONLY, DATA\n"
    if mutation == "writable":
        headers = headers.replace(", READONLY", "")
    elif mutation == "missing-byte":
        contents = contents.replace("050607", "0506  ")
    elif mutation == "wrong-extent":
        headers = headers.replace("00000007", "00000008")
    if mutation == "none":
        assert arm.ReadOnlyData_Parse(contents, headers) == {0x8001000 + i: i + 1 for i in range(7)}
    else:
        with pytest.raises(ValueError):
            arm.ReadOnlyData_Parse(contents, headers)
