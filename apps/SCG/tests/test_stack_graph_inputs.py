"""Shared graph construction is data-only; target adapters own full coverage."""
import json

import pytest
from test_stack_budget import stacks


def test_flight_keeps_complete_manifest_and_selected_configuration(tmp_path, monkeypatch):
    (tmp_path / "SilverStar.ssproject").write_text(json.dumps({"build": {"target_profile": "Known"}}))
    generated = tmp_path / "Generated"
    generated.mkdir()
    (generated / "project_sources.mk").write_text("C_SOURCES += \\\n  first.c \\\n  nested/second.c\n\n")
    observed = []
    monkeypatch.setattr(stacks, "StackGraph_LoadInputs", lambda *args: observed.append(args) or {})
    stacks.StackGraph_Load(tmp_path, "Debug", "arm-", "auto")
    assert observed == [(tmp_path, tmp_path / "build/FCCG/Known/Debug/auto", "arm-",
                         ["first.c", "nested/second.c"])]


@pytest.mark.parametrize("mutation", ["outside-build", "missing-su",
                                     "missing-source", "duplicate", "traversal", "absolute", "empty"])
def test_graph_input_boundary_rejects_invalid_inputs_before_tools(tmp_path, monkeypatch, mutation):
    build = tmp_path / "build/Release"
    build.mkdir(parents=True)
    (build / "firmware.elf").write_bytes(b"not executed")
    (tmp_path / "first.c").write_text("void First(void) {}\n")
    (build / "first.su").write_text("first.c:1:1:First\t0\tstatic\n")
    sources = ["first.c"]
    if mutation == "outside-build":
        build = tmp_path
    elif mutation == "missing-su":
        (build / "first.su").unlink()
    elif mutation == "missing-source":
        (tmp_path / "first.c").unlink()
    elif mutation == "duplicate":
        sources *= 2
    elif mutation == "traversal":
        sources = ["nested/../first.c"]
    elif mutation == "absolute":
        sources = [str(tmp_path / "first.c")]
    else:
        sources = []
    def unexpected(*args):
        pytest.fail("Invalid inputs must be rejected before invoking objdump")
    monkeypatch.setattr(stacks, "Command_Read", unexpected)
    with pytest.raises(ValueError):
        stacks.StackGraph_LoadInputs(tmp_path, build, "arm-", sources)


def test_bare_metal_build_root_is_valid_graph_input_not_proof(tmp_path, monkeypatch):
    build = tmp_path / "build"
    build.mkdir()
    (build / "firmware.elf").write_bytes(b"synthetic tool input")
    (tmp_path / "first.c").write_text("void First(void) {}\n")
    (build / "first.su").write_text("first.c:1:1:First\t8\tstatic\n")
    def command_read(command, root):
        if "-t" in command:
            return "08000000 g F .text 00000002 First\n"
        if "-d" in command:
            return "Disassembly of section .text:\n08000000 <First>:\n 8000000: 4770 bx lr\n"
        return "08000000 00000002 T First\n"
    monkeypatch.setattr(stacks, "Command_Read", command_read)
    graph = stacks.StackGraph_LoadInputs(tmp_path, build, "arm-", ["first.c"])
    assert graph["build"] == build and graph["sources"] == ["first.c"]
    assert graph["frames"]["First"] == 8
    assert "passes" not in graph
