"""Machine-code counterexamples for stack bounds, independent of source seals."""
import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/stack_arm.py"
_spec = importlib.util.spec_from_file_location("stack_arm_unit", _path)
arm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arm)


def Analyze(assembly, symbols, name="entry"):
    entries = arm.Assembly_Parse("Disassembly of section .text:\n" + assembly, symbols)
    return entries, arm.Function_Analyze(name, entries[name], entries)


def test_notype_startup_loop_labels_do_not_hide_main_call():
    entries, proof = Analyze("""
08000000 <entry>:
 8000000: e000 b.n 8000004 <Loop>
08000002 <Copy>:
 8000002: 3004 adds r0, #4
08000004 <Loop>:
 8000004: 4288 cmp r0, r1
 8000006: d3fc bcc.n 8000002 <Copy>
 8000008: f000 f000 bl 8000020 <main>
 800000c: 4770 bx lr
08000020 <main>:
 8000020: b510 push {r4, lr}
 8000022: bd10 pop {r4, pc}
""", """
08000000 g F .text 0000000e entry
08000002 l .text 00000000 Copy
08000004 l .text 00000000 Loop
08000020 g F .text 00000004 main
""")
    assert set(entries) == {"entry", "main"}
    assert proof["edges"] == {"main"}
    assert proof["indirect"] == []


def test_overlapping_libgcc_entry_includes_shared_suffix_stack_frame():
    entries, proof = Analyze("""
08000000 <entry>:
 8000000: 4048 eors r0, r1
08000002 <shared>:
 8000002: b530 push {r4, r5, lr}
 8000004: bd30 pop {r4, r5, pc}
""", "08000000 g F .text 00000006 entry\n08000002 g F .text 00000004 shared\n")
    assert proof["frame_bytes"] == 12
    assert arm.Function_Analyze("shared", entries["shared"], entries)["frame_bytes"] == 12


def test_positive_stack_growth_cycle_has_no_finite_one_push_bound():
    with pytest.raises(ValueError, match="Unbounded stack-growth instruction cycle"):
        Analyze(" 8000000: b401 push {r0}\n 8000002: e7fd b.n 8000000 <entry>\n",
                "08000000 g F .text 00000004 entry\n")


def test_balanced_loop_has_finite_stack_peak():
    _, proof = Analyze(" 8000000: b401 push {r0}\n 8000002: bc01 pop {r0}\n 8000004: e7fc b.n 8000000 <entry>\n",
                       "08000000 g F .text 00000006 entry\n")
    assert proof["frame_bytes"] == 4


def test_local_link_subroutine_is_not_function_entry_recursion():
    _, proof = Analyze("""
 8000000: b500 push {lr}
 8000002: f000 f000 bl 8000010 <entry+0x10>
 8000006: b084 sub sp, #16
 8000008: b004 add sp, #16
 800000a: bd00 pop {pc}
 8000010: b401 push {r0}
 8000012: bc01 pop {r0}
 8000014: 4770 bx lr
""", "08000000 g F .text 00000016 entry\n")
    assert proof["edges"] == set()
    assert proof["frame_bytes"] == 20


def test_recursive_local_link_subroutine_is_rejected_even_with_zero_frame():
    with pytest.raises(ValueError, match="Recursive local linked subroutine"):
        Analyze("""
 8000000: f000 f000 bl 8000010 <entry+0x10>
 8000004: 4770 bx lr
 8000010: f000 f000 bl 8000010 <entry+0x10>
 8000014: 4770 bx lr
""", "08000000 g F .text 00000016 entry\n")


def test_tail_branch_to_returning_function_cannot_prove_noreturn():
    _, proof = Analyze(" 8000000: f000 b800 b.w 8000010 <callee>\n 8000010: 4770 bx lr\n",
                       "08000000 g F .text 00000004 entry\n08000010 g F .text 00000002 callee\n")
    assert proof["tail_returns"] == ["callee"]


@pytest.mark.parametrize("op,args,expected", [
    ("blne", "8000000 <entry>", "bl"), ("bls.n", "8000000 <entry>", "b"),
    ("blxne", "r3", "blx"), ("bxne", "lr", "bx"),
])
def test_conditional_link_is_distinct_from_bls(op, args, expected):
    assert arm.BranchKind_Get(op) == expected


@pytest.mark.parametrize("instruction", ["add sp, r3", "mov sp, r3", "bic sp, sp, #7", "msr MSP, r0"])
def test_unknown_sp_write_never_acquires_zero_bound(instruction):
    _, proof = Analyze(f" 8000000: f000 f000 {instruction}\n 8000004: 4770 bx lr\n",
                       "08000000 g F .text 00000006 entry\n")
    assert proof["unknown_sp"] == [0x8000000]


def test_non_stack_stmdb_and_non_writeback_stack_load_do_not_change_sp():
    assert arm.StackDelta_Get("stmdb", "r0!, {r4-r11}") == 0
    assert arm.StackDelta_Get("stmia.w", "sp, {r0, r1}") == 0
    assert arm.StackDelta_Get("ldmia.w", "sp, {r0, r1}") == 0


def test_return_and_unreachable_literal_pool_padding_are_not_indirect_calls():
    _, proof = Analyze("""
 8000000: b500 push {lr}
 8000002: f85d fb04 ldr.w pc, [sp], #4
 8000006: bf00 nop
 8000008: deadbeef .word 0xdeadbeef
""", "08000000 g F .text 0000000c entry\n")
    assert proof["indirect"] == [] and proof["frame_bytes"] == 4


def test_same_named_local_symbols_keep_distinct_address_qualified_frames():
    assembly = "Disassembly of section .text:\n 8000000: 4770 bx lr\n 8000010: b530 push {r4, r5, lr}\n 8000012: bd30 pop {r4, r5, pc}\n"
    entries = arm.Assembly_Parse(assembly, "08000000 l F .text 00000002 entry\n08000010 l F .text 00000004 entry\n")
    assert set(entries) == {"entry@08000000", "entry@08000010"}
    assert arm.Function_Analyze("entry@08000000", entries["entry@08000000"], entries)["frame_bytes"] == 0
    assert arm.Function_Analyze("entry@08000010", entries["entry@08000010"], entries)["frame_bytes"] == 12


def test_same_name_and_address_with_conflicting_extents_is_rejected():
    with pytest.raises(ValueError, match="Conflicting ELF function extents"):
        Analyze("", "08000000 l F .text 00000004 entry\n08000000 l F .text 00000008 entry\n")


@pytest.mark.parametrize("mutation", ["none", "missing_guard", "out_of_function", "missing_bytes"])
def test_linked_thumb_switch_requires_bound_and_every_target(mutation):
    assembly = """
 8000000: 2801 cmp r0, #1
 8000002: d807 bhi.n 8000014 <entry+0x14>
 8000004: e8df f000 tbb [pc, r0]
 8000008: 0402 .short 0x0402
 800000c: b510 push {r4, lr}
 800000e: bd10 pop {r4, pc}
 8000010: b530 push {r4, r5, lr}
 8000012: bd30 pop {r4, r5, pc}
 8000014: 4770 bx lr
"""
    if mutation == "missing_guard":
        assembly = assembly.replace("cmp r0, #1", "mov r0, #1")
    elif mutation == "out_of_function":
        assembly = assembly.replace("0402 .short", "ff02 .short")
    elif mutation == "missing_bytes":
        assembly = assembly.replace(" 8000008: 0402 .short 0x0402", "")
    _, proof = Analyze(assembly, "08000000 g F .text 00000016 entry\n")
    if mutation == "none":
        assert proof["indirect"] == [] and proof["frame_bytes"] == 12
    else:
        assert any(row[1] == "unresolved-switch" for row in proof["indirect"])
