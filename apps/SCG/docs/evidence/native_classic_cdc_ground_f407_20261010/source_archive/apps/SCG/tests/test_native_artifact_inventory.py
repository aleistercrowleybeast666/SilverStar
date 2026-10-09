"""Retained library inventory must distinguish loading from GC retention."""
from pathlib import Path
import importlib.util
import hashlib
import pytest
from silverstar_fccg.hardware import native_machine_contract


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.setitem(__import__('sys').modules,'native_machine_contract',native_machine_contract)
    path=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools/check_native_ground.py'
    spec=importlib.util.spec_from_file_location('native_gate_inventory_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_only_retained_members_have_full_space_containing_archive_paths(gate,tmp_path):
    archive=tmp_path/'tool chain'/'libc_nano.a';archive.parent.mkdir();archive.write_bytes(b'reviewed archive identity')
    memory='''Archive member included to satisfy reference by file (symbol)
{archive}(libc_a-mallocr.o)
Discarded input sections
 .text._malloc_r 0x00000000 0x80 {archive}(libc_a-mallocr.o)
Linker script and memory map
 *libc.a(*)
 .text.memcpy
                0x08000020 0x30 {archive}(libc_a-memcpy.o)
 .debug_info    0x00000000 0x90 {archive}(libc_a-mallocr.o)
 .text.zero     0x08000060 0x0 {archive}(libc_a-mallocr.o)
 .text.outside  0x09000000 0x40 {archive}(libc_a-mallocr.o)
 .text.memcpy   0x08000020 0x30 {archive}(libc_a-memcpy.o)
 .bss.filler    0x20000000 0x0
 .bss.__sf      0x20000100 0x138 {archive}(libc_a-findfp.o)
'''.format(archive=archive.as_posix())
    result=gate.NativeLinkedLibraries_Inspect(memory,[{'origin':0x08000000,'length':65536},
        {'origin':0x20000000,'length':20480}])
    assert len(result)==2 and {item['object'] for item in result}=={'libc_a-memcpy.o','libc_a-findfp.o'}
    assert all(item['archive']==archive.as_posix() and item['archive_sha256']==
        hashlib.sha256(archive.read_bytes()).hexdigest() for item in result)


def test_incomplete_or_missing_archive_inventory_cannot_pass(gate,tmp_path):
    regions=[{'origin':0x08000000,'length':65536}]
    with pytest.raises(ValueError,match='one memory map'):
        gate.NativeLinkedLibraries_Inspect('LOAD libc.a',regions)
    with pytest.raises(ValueError,match='no retained members'):
        gate.NativeLinkedLibraries_Inspect('Linker script and memory map\n *libc.a(*)\n',regions)
    with pytest.raises(ValueError,match='archive path is missing'):
        gate.NativeLinkedLibraries_Inspect('Linker script and memory map\n .text.x 0x08000020 0x20 '+
            (tmp_path/'missing lib.a').as_posix()+'(x.o)\n',regions)
