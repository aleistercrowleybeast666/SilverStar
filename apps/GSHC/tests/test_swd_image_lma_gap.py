"""Review regression: ELF symbols use VMA even when gap comparison uses LMA."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_swd_image_contract import image,load_v2,DiagnosticError,Contract_Get


@pytest.mark.parametrize('symbol',[False,True])
def test_ram_load_gap_symbol_is_mapped_from_vma_before_erased_expectation(image,symbol):
    folder=image.parent
    (folder/'gap.c').write_text('volatile unsigned ram_head __attribute__((section(".head")))=0x12345678;\nvolatile unsigned ram_tail[4] __attribute__((section(".tail"),aligned(16)))={1,2,3,4};\n')
    (folder/'gap.ld').write_text('ENTRY(_start)\nMEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K\nRAM (rw) : ORIGIN = 0x20000000, LENGTH = 20K\nCCM (rw) : ORIGIN = 0x10000000, LENGTH = 64K }\nSECTIONS { .text : { *(.isr_vector) *(.text*) *(.rodata*) } > FLASH\n.datahead 0x20000000 : AT(0x08001000) { *(.head) } > RAM\n.datatail 0x20000010 : AT(0x08001010) { *(.tail) } > RAM\n.data 0x20000020 : AT(0x08001020) { *(.data*) } > RAM\n.bss (NOLOAD) : { *(.bss*) } > RAM\n.ccm_bss (NOLOAD) : { *(.ccm_bss) } > CCM }\n')
    commands=[]
    def run(command):
        result=subprocess.run(command,cwd=folder,capture_output=True,text=True,timeout=30)
        commands.append(dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
        (folder/'gap_commands.json').write_text(json.dumps(commands,indent=2))
        assert result.returncode==0,result.stderr
    run([shutil.which('arm-none-eabi-gcc'),'-mcpu=cortex-m4','-mthumb','-g','-gdwarf-4','-O0','-Wall','-Wextra','-Werror','-nostdlib',
         '-Wl,--build-id=none','-Tgap.ld',*[s['source'] for s in Contract_Get()['entries']],'start.c','gap.c','-o','gap.elf'])
    elf=folder/'gap.elf'
    if symbol:
        run([shutil.which('arm-none-eabi-objcopy'),'--add-symbol','phantom=.datahead:8,global,object','gap.elf','gap_symbol.elf'])
        elf=folder/'gap_symbol.elf'
    run([shutil.which('arm-none-eabi-objcopy'),'-O','ihex',str(elf),str(elf.with_suffix('.hex'))])
    if symbol:
        with pytest.raises(DiagnosticError):load_v2(elf)
    else:
        firmware=load_v2(elf)
        assert any(g['address']==0x08001004 and g['size']==12 for g in firmware.image_identity['erased_gaps'])
