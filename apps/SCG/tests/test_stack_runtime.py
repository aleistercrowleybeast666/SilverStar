"""Runtime stack proof counterexamples; no synthetic MCU acceptance."""
import importlib.util
from pathlib import Path

import pytest


def test_readelf_binary_constant_bytes_do_not_hide_or_corrupt_abi_text(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from test_stack_budget import stacks
    raw = b'DW_AT_const_value: \xf3}m\xb8_@\xe9\nDW_AT_data_member_location: 60\n'
    monkeypatch.setattr(stacks.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=raw))
    text = stacks.Command_Read(['arm-none-eabi-readelf', '--debug-dump=info', 'firmware.elf'], tmp_path)
    assert text.encode('latin1') == raw
    assert 'DW_AT_data_member_location: 60' in text
    with pytest.raises(UnicodeDecodeError):
        stacks.Command_Read(['arm-none-eabi-nm', 'firmware.elf'], tmp_path)

_path = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/stack_runtime.py"
_spec = importlib.util.spec_from_file_location("stack_runtime_unit", _path)
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def test_hal_callback_scanner_without_manual_object_contract_cannot_accept_any_null_assignment(tmp_path):
    # A NULL write in an unrelated/unlinked function is not evidence that an
    # actual interrupt handle was initialized, or that no aggregate copy exists.
    with pytest.raises(ValueError, match="reviewed HAL handle/object contract"):
        runtime.HalCallbacks_Resolve(tmp_path, {"indirect": {"HAL_DMA_IRQHandler"}}, "unused-", None, None)


def test_source_functions_accept_nested_callback_parameters_and_attributes():
    text = """
__attribute__((naked)) void Handler(void) { __asm("nop"); }
int Register(void (*callback)(int value)) { if (callback) { callback(1); } return 0; }
static const int values[] = {1, 2, 3};
"""
    functions = runtime.SourceFunctions_Get(text)
    assert set(functions) == {"Handler", "Register"}
    assert "callback(1)" in functions["Register"]


def test_dwarf_callback_offsets_must_agree_across_compilation_units():
    first = """
 <1><10>: Abbrev Number: 1 (DW_TAG_structure_type)
 <11> DW_AT_name : __DMA_HandleTypeDef
 <2><20>: Abbrev Number: 1 (DW_TAG_member)
 <21> DW_AT_name : XferCpltCallback
 <22> DW_AT_data_member_location: 60
 <1><30>: Abbrev Number: 1 (DW_TAG_base_type)
"""
    assert runtime.DwarfMembers_Get(first, {"__DMA_HandleTypeDef"}) == {"__DMA_HandleTypeDef": {"XferCpltCallback": 60}}
    with pytest.raises(ValueError, match="inconsistent linked callback ABI"):
        runtime.DwarfMembers_Get(first + first.replace("location: 60", "location: 64"), {"__DMA_HandleTypeDef"})


def test_dwarf_constant_member_location_expression_is_checked_against_actual_bytes():
    assert runtime.DwarfLocation_Read('2 byte block: 23 3c (DW_OP_plus_uconst: 60)') == 60
    assert runtime.DwarfLocation_Read('3 byte block: 23 80 1 (DW_OP_plus_uconst: 128)') == 128
    for value in ('2 byte block: 23 3c (DW_OP_plus_uconst: 64)',
                  '2 byte block: 23 bc (DW_OP_plus_uconst: 60)',
                  '3 byte block: 23 3c 0 (DW_OP_plus_uconst: 60)',
                  '2 byte block: 22 3c (DW_OP_plus_uconst: 60)'):
        with pytest.raises(ValueError, match='DWARF member location'):
            runtime.DwarfLocation_Read(value)


def _HalGraph_Create(bypass=False):
    rows = [(0, 2, "ldr", "r3, [r0, #60]"), (2, 2, "cmp", "r3, #0"),
            (4, 2, "beq.n", "8 <Handler+0x8>"), (6, 2, "bx", "r3"), (8, 2, "bx", "lr")]
    successors = {0: [2], 2: [4], 4: [6, 8], 6: [], 8: []}
    if bypass:
        rows.insert(0, (-2, 2, "cbz", "r0, 6 <Handler+0x6>"))
        successors[-2] = [0, 6]
    return {"function_entries": {"Handler": {"rows": rows}},
            "assembly_proofs": {"Handler": {"successors": successors}}}


def test_hal_slot_requires_every_path_to_load_callback_value():
    graph = _HalGraph_Create()
    assert runtime.HalSlots_Get(graph, "Handler", 3) == [60]
    with pytest.raises(ValueError, match="bypassed from function entry"):
        runtime.HalSlots_Get(_HalGraph_Create(True), "Handler", 4)


def test_hal_slot_does_not_treat_compare_as_register_write():
    assert runtime.HalSlots_Get(_HalGraph_Create(), "Handler", 3) == [60]
