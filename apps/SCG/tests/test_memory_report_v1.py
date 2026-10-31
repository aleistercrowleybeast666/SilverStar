"""ELF section accounting fault cases; synthetic parser evidence, not MCU tests."""
from copy import deepcopy

from silverstar_fccg.project.build_audit import MemoryReport_Build


CONTRACT = {'schema': 'silverstar.memory-contract/1', 'mcu_model': 'STM32F103RFT6',
            'regions': [{'name': 'FLASH', 'origin': 0x08000000, 'bytes': 786432},
                        {'name': 'RAM', 'origin': 0x20000000, 'bytes': 98304}]}
LINKER = '''FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 768K
RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 96K
'''


def _Section(name, size, vma, lma, flags='ALLOC, LOAD'):
    return f'  0 {name} {size:08x} {vma:08x} {lma:08x} 00000000 2**2\n {flags}\n'


def test_f103rf_600k_is_valid_and_data_is_counted_in_both_banks():
    sections = (_Section('.text', 600 * 1024, 0x08000000, 0x08000000)
                + _Section('.custom_initialized', 16, 0x20000000, 0x08096000)
                + _Section('.bss', 1024, 0x20000010, 0x20000010, 'ALLOC'))
    report = MemoryReport_Build(CONTRACT, LINKER, sections)
    assert report['errors'] == []
    flash, ram = report['regions']
    assert flash['used_bytes'] == 600 * 1024 + 16
    assert flash['physical_capacity_bytes'] == 786432
    assert ram['used_bytes'] == 1040
    assert report['stack_proof'] == 'NOT_PROVEN'


def test_single_bank_overflow_cannot_borrow_other_banks():
    report = MemoryReport_Build(CONTRACT, LINKER, _Section('.bss', 100000, 0x20000000, 0x20000000, 'ALLOC'))
    assert 'MEMORY_REGION_OVERFLOW:RAM:.bss' in report['errors']
    assert report['regions'][1]['physical_free_bytes'] < 0


def test_unknown_allocated_section_is_not_ignored():
    report = MemoryReport_Build(CONTRACT, LINKER, _Section('.unowned', 64, 0x30000000, 0x30000000, 'ALLOC'))
    assert 'SECTION_OUTSIDE_EXACT_MCU:.unowned:run' in report['errors']


def test_reserved_memory_is_not_double_counted_or_confused_with_image_span():
    sections = (_Section('.bss', 100, 0x20000000, 0x20000000, 'ALLOC')
                + _Section('._user_heap_stack', 2048, 0x20017000, 0x20017000, 'ALLOC'))
    report = MemoryReport_Build(CONTRACT, LINKER, sections)
    ram = report['regions'][1]
    assert ram['used_bytes'] == 2148
    assert ram['allocated_span_bytes'] == 0x17800
    assert ram['reserved_bytes'] == 2048 and ram['reserved_included_in_used']


def test_h7_unassigned_physical_bank_is_not_immediately_linker_available():
    contract = deepcopy(CONTRACT)
    contract['regions'].append({'name': 'RAM_D2', 'origin': 0x30000000, 'bytes': 294912})
    report = MemoryReport_Build(contract, LINKER, _Section('.text', 100, 0x08000000, 0x08000000))
    assert not report['errors']
    bank = report['regions'][2]
    assert bank['physical_free_bytes'] == 294912
    assert bank['linker_capacity_bytes'] == bank['linker_free_bytes'] == 0


def test_overlaps_and_wrong_linker_capacity_are_rejected():
    sections = (_Section('.text', 100, 0x08000000, 0x08000000)
                + _Section('.bad_overlap', 100, 0x08000030, 0x08000030))
    report = MemoryReport_Build(CONTRACT, LINKER.replace('768K', '1024K'), sections)
    assert 'LINKER_MEMORY_EXCEEDS_EXACT_MCU:FLASH' in report['errors']
    assert 'OVERLAPPING_ALLOCATED_SECTIONS:FLASH:.bad_overlap' in report['errors']


def test_map_must_match_elf_sections_and_selected_linker():
    sections = _Section('.text', 100, 0x08000000, 0x08000000)
    map_source = ('Memory Configuration\n\nName Origin Length Attributes\n'
                  'FLASH 0x08000000 0x000c0000 xr\nRAM 0x20000000 0x00018000 xrw\n'
                  '\nLinker script and memory map\n\n.text 0x08000000 0x64\n')
    assert not MemoryReport_Build(CONTRACT, LINKER, sections, map_source)['errors']
    stale = map_source.replace('.text 0x08000000 0x64', '.text 0x08000000 0x63')
    assert 'ELF_MAP_SECTION_MISMATCH:.text' in MemoryReport_Build(CONTRACT, LINKER, sections, stale)['errors']
    stale = map_source.replace('FLASH 0x08000000 0x000c0000', 'FLASH 0x08000000 0x00080000')
    assert 'LINKER_MAP_MEMORY_MISMATCH' in MemoryReport_Build(CONTRACT, LINKER, sections, stale)['errors']
