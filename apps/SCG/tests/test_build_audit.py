from __future__ import annotations

from pathlib import Path

from silverstar_fccg.project import build_audit


def test_build_audit_rejects_inflated_linker_and_dynamic_stack(
    tmp_path: Path, monkeypatch,
) -> None:
    elf = tmp_path / "ground.elf"
    map_file = tmp_path / "ground.map"
    linker = tmp_path / "ground.ld"
    for path in (elf, map_file):
        path.write_bytes(b"fixture")
    linker.write_text(
        "MEMORY\n{\nRAM (xrw) : ORIGIN = 0x20000000, LENGTH = 24K\n"
        "FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "main.su").write_text(
        "main.c:1:1:main\t96\tdynamic,bounded\n", encoding="utf-8"
    )

    def tool_run(tool: str, *args: str, **_kwargs) -> str:
        if tool.endswith("objdump"):
            return (
                "Idx Name Size VMA LMA File off Algn\n"
                "  0 .text 00004000 08000000 08000000 00001000 2**2\n"
                "       CONTENTS, ALLOC, LOAD, READONLY, CODE\n"
                "  1 .bss 00002000 20000000 20000000 00005000 2**2\n"
                "       ALLOC\n"
            )
        if tool.endswith("size"):
            return "text data bss dec hex filename\n16384 0 8192 24576 6000 ground.elf\n"
        if tool.endswith("nm"):
            return "08000100 T malloc\n"
        raise AssertionError((tool, args))

    monkeypatch.setattr(build_audit, "_Tool_Run", tool_run)
    audit = build_audit.BuildAudit_Run(
        elf, map_file, linker, tmp_path,
        {"memory_regions": [
            {"name": "FLASH", "origin": 134217728, "bytes": 65536},
            {"name": "RAM", "origin": 536870912, "bytes": 20480},
        ]},
    )
    assert "LINKER_MEMORY_EXCEEDS_EXACT_MCU:RAM" in audit.errors
    assert "DYNAMIC_ALLOCATION_LINKED:malloc" in audit.errors
    assert any(error.startswith("DYNAMIC_STACK_USAGE:") for error in audit.errors)
    assert audit.largest_function_stack_bytes == 96
