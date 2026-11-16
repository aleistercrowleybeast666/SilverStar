"""Actual M4 CRT bytes preserve weak-call and initializer rejection rules."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

SCG = Path(__file__).resolve().parents[1]
TOOLS = SCG / "plugins/builtin/silverstar_core_0_1_0/payload/Tools"
SPEC = importlib.util.spec_from_file_location("crt_runtime_test", TOOLS / "stack_runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


@pytest.fixture
def machine(tmp_path):
    data = json.loads((SCG / "tests/fixtures/stack_crt_m4_20261117.json").read_bytes())
    entries = data["function_entries"]
    for entry in entries.values():
        entry["rows"] = [tuple(row) for row in entry["rows"]]
        entry["memory"] = {int(key): value for key, value in entry["memory"].items()}
    proofs = data["assembly_proofs"]
    for proof in proofs.values():
        proof["successors"] = {int(key): value for key, value in proof["successors"].items()}
        proof["indirect"] = [tuple(row) for row in proof["indirect"]]
    elf = tmp_path / "size-bound-only.elf"
    elf.write_bytes(bytes(256))  # Only table-length bound; instructions/tables are actual recorded ELF bytes.
    graph = {"function_entries": entries, "assembly_proofs": proofs, "nm": data["nm"],
             "elf": elf, "indirect": {"deregister_tm_clones", "register_tm_clones", "__libc_init_array"},
             "edges": {name: set() for name in entries}}

    def read(_root, _prefix, _elf, start, size):
        result = bytes.fromhex(data["tables"][str(start)])
        assert len(result) == size
        return result

    return graph, read


def test_complete_original_m4_crt_proof_and_exact_targets(machine):
    graph, read = machine
    result = runtime.CrtCallbacks_Resolve(Path("."), graph, "", read)
    assert not graph["indirect"]
    assert len(result) == 4
    assert graph["edges"]["__libc_init_array"] == {"frame_dummy"}
    assert all(row["linked_weak_pointer"] == 0 for row in result[:2])


@pytest.mark.parametrize("mutation", ["pointer", "literal_missing", "guard_opcode", "guard_register",
                                     "guard_return", "bypass_load", "bypass_guard", "call_opcode",
                                     "call_register", "extra_call", "initializer_loop", "array_target"])
def test_complete_original_m4_crt_rejects_real_boundary_mutations(machine, mutation):
    graph, read = machine
    entry = graph["function_entries"]["deregister_tm_clones"]
    proof = graph["assembly_proofs"]["deregister_tm_clones"]
    index = next(i for i, row in enumerate(entry["rows"]) if row[0] == proof["indirect"][0][0])
    literal = entry["rows"][index - 2]
    offset = int(re.search(r"#(\d+)", literal[3])[1])
    pointer = ((literal[0] + 4) & ~3) + offset
    address, size, opcode, arguments = entry["rows"][index - 1]
    if mutation == "pointer":
        entry["memory"][pointer] = 1
    elif mutation == "literal_missing":
        del entry["memory"][pointer]
    elif mutation == "guard_opcode":
        entry["rows"][index - 1] = (address, size, "cbnz", arguments)
    elif mutation == "guard_register":
        entry["rows"][index - 1] = (address, size, opcode, arguments.replace("r3,", "r2,"))
    elif mutation == "guard_return":
        entry["rows"][index - 1] = (address, size, opcode, "r3, 0 <not_a_return>")
    elif mutation == "bypass_load":
        proof["successors"][0] = [entry["rows"][index][0]]
    elif mutation == "bypass_guard":
        proof["successors"][0] = [address]
    elif mutation == "call_opcode":
        site = proof["indirect"][0]
        proof["indirect"][0] = (site[0], "blx", site[2])
    elif mutation == "call_register":
        site = proof["indirect"][0]
        proof["indirect"][0] = (site[0], site[1], "r2")
    elif mutation == "extra_call":
        proof["indirect"].append(proof["indirect"][0])
    elif mutation == "initializer_loop":
        init = graph["function_entries"]["__libc_init_array"]
        row = init["rows"][19]
        init["rows"][19] = (row[0], row[1], row[2], "r6, #2")
    else:
        read = lambda *_args: b"\x01\x00\x00\x00"
    with pytest.raises(ValueError):
        runtime.CrtCallbacks_Resolve(Path("."), graph, "", read)


def test_helper_only_preserves_initializer_for_its_architecture_owner(machine):
    graph, _ = machine
    result = runtime.CrtWeakCallbacks_Resolve(graph)
    assert len(result) == 2
    assert graph["indirect"] == {"__libc_init_array"}
    assert not graph["edges"]["__libc_init_array"]
