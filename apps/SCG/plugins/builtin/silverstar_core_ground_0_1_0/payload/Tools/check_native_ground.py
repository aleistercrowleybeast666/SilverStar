"""Private native Ground source/ownership gate; critical acceptance NOT PROVEN.

Legacy check_ground.py retains its existing implementation and thresholds.
This gate follows real native owners instead of inventing legacy backend tables.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from native_machine_contract import NativeArmAttributes_Validate, NativeIndependentVectors_Validate


def Architecture_Check(root: Path) -> dict:
    root = root.resolve()
    graph = json.loads((root/'Generated/ground_source_graph.json').read_text())
    contract = json.loads((root/'Generated/native_ground_contract.json').read_text())
    if graph.get('native_complete_classic_cdc') is not True:
        raise ValueError('Native candidate source graph marker missing')
    make = (root/'Makefile').read_text().replace('\\\n',' ')
    for key, variable in (('sources','C_SOURCES'),('asm_sources','ASM_SOURCES')):
        match = re.search(r'^'+variable+r' := (.*)$',make,re.M)
        if match is None or match[1].split() != graph[key] or len(set(graph[key])) != len(graph[key]):
            raise ValueError('Native Make/source graph disagreement: '+key)
    compiled = graph['sources']+graph['asm_sources']
    for path in compiled+graph['include_dirs']+[graph['linker_script']]:
        actual = (root/path).resolve()
        if not actual.is_relative_to(root) or not actual.exists():
            raise ValueError('Native source graph escapes or lacks a path: '+path)
    owned = ('Common/','Devices/','Generated/','Ground/','Platform/')
    vendor = ('HardwareGenerated/','Middlewares/')
    for path in graph['sources']:
        if not path.startswith(owned+vendor) or any(token in path for token in ('FreeRTOS','FatFs','FATFS','/Adapter/')):
            raise ValueError('Native Ground source ownership/role conflict: '+path)
        if path.startswith('Platform/') or path.endswith('/sysmem.c'):
            raise ValueError('Native candidate must use its typed native port and rejecting heap ABI')
    native_prefix = 'HardwareGenerated/NativeClassicCdc/'
    for path, digest in contract['original_sha256'].items():
        actual = (root/native_prefix/path).resolve()
        if not actual.is_relative_to(root) or hashlib.sha256(actual.read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen native original changed: '+path)
    for original, derived in contract['source_replacements'].items():
        if original in compiled or derived not in compiled or original.removeprefix(native_prefix) not in contract['original_sha256']:
            raise ValueError('Native replacement has duplicate or missing compiled owner')
    for path, digest in contract['compiled_owned_sha256'].items():
        if path not in graph['sources'] or hashlib.sha256((root/path).read_bytes()).hexdigest() != digest:
            raise ValueError('Native generated/derived owner changed: '+path)
    for entry in contract.get('payload_derivatives',[]):
        if (entry['original'] in compiled or entry['derived'] not in compiled or
                hashlib.sha256((root/entry['original']).read_bytes()).hexdigest()!=entry['original_sha256'] or
                hashlib.sha256((root/entry['derived']).read_bytes()).hexdigest()!=entry['derived_sha256']):
            raise ValueError('Native payload derivative has changed or duplicate ownership')
    mains = [path for path in graph['sources'] if path.endswith('/main.c')]
    if len(mains) != 1 or mains[0] != contract['source_replacements'][native_prefix+'Core/Src/main.c']:
        raise ValueError('Native main does not have one reviewed replacement owner')
    main = (root/mains[0]).read_text()
    if (main.count('NativeRuntime_Init()') != 1 or main.count('NativeRuntime_Process()') != 1 or
            any(token in main for token in ('AppTasks_Init','SystemStartup_Run','MX_FATFS_Init'))):
        raise ValueError('Native runtime startup/owner loop is not bound')
    required = ('Generated/Src/native_runtime.c','Generated/Src/native_platform.c',
        'Generated/Src/native_clock.c','Generated/Src/native_clock_port.c',
        'Generated/Src/native_critical.c','Generated/Src/native_no_heap.c',
        'Generated/Src/native_usb_state.c','Generated/Src/pc_byte_stream.c',
        'Generated/Src/project_resources.c','Ground/Core/Src/ground_bridge.c',
        'Ground/Radio/Src/ground_radio_sx1281.c')
    if any(path not in graph['sources'] for path in required):
        raise ValueError('Native Ground runtime owner is missing')
    if graph['required_link_symbols'] != ['_sbrk'] or '-Wl,-u,_sbrk' not in make:
        raise ValueError('Native no-heap ABI is not retained by the linker')
    if '-T'+graph['linker_script'] not in make or not graph['linker_script'].startswith(native_prefix):
        raise ValueError('Native linker ownership differs from the original contract')
    if any('/NRF24' in path for path in compiled) or (root/'Ground/Radio/Src/ground_radio_nrf24.c').exists():
        raise ValueError('Unselected radio backend present')
    for flag in graph['mcu_flags']:
        if flag not in make:
            raise ValueError('Native machine flag missing from Make')
    print('PASS private native source graph, immutable originals, unique replacement owners and runtime binding')
    print('Critical-contract manual review, EP0 admission, call graph, stack and MCU timing: NOT PROVEN')
    return graph


def Host_Check(root: Path, compiler: str) -> None:
    from check_ground import Host_Check as LegacyHost_Check
    build=root/'build/native-host';build.mkdir(parents=True,exist_ok=True)
    ready_fixture=build/'ready_transport_fixture.c'
    ready_fixture.write_text('''#include "native_runtime.h"
#include "native_clock.h"
#include <assert.h>
extern uint32_t usb_test_mask;
/* Existing transport regression cases are scoped to an already-ready runtime.
 * Initialization/fault lifecycle is exercised separately with the real runtime. */
uint8_t NativeRuntime_ReadyGet(void) { return 1U; }
uint8_t NativeClock_ContextAllowedGet(void) { return usb_test_mask == 0U ? 1U : 0U; }
NativeClockResult NativeClock_DelayUs(uint32_t delay)
{ assert(delay == 1U && usb_test_mask == 0U); return NativeClockResult_Ok; }
''')
    LegacyHost_Check(root,compiler,extra_usb_sources=(str(ready_fixture),))


def NativeLinkedLibraries_Inspect(map_text: str, regions: list[dict]) -> list[dict]:
    # Loaded archive members and linker wildcard selectors are not necessarily
    # retained. Inventory only positive-size sections in real physical memory.
    marker = 'Linker script and memory map'
    if map_text.count(marker) != 1:
        raise ValueError('Native linked library inventory lacks one memory map')
    retained = set()
    pattern = (r'(?m)^[ \t]+(?:\S+[ \t]+)?(0x[\da-fA-F]+)[ \t]+(0x[\da-fA-F]+)[ \t]+'
        r'([^\r\n]+\.a)\(([^()]+\.o)\)[ \t]*\r?$')
    for address, size, archive, member in re.findall(pattern, map_text.split(marker, 1)[1]):
        start, length = int(address, 16), int(size, 16)
        if length > 0 and any(r['origin'] <= start and start + length <= r['origin'] + r['length'] for r in regions):
            retained.add((archive, member))
    if not retained:
        raise ValueError('Native linked library inventory found no retained members')
    records = []
    for archive, member in sorted(retained):
        path = Path(archive).resolve()
        if not path.is_file():
            raise ValueError('Native retained archive path is missing: '+archive)
        records.append({'archive':archive,'object':member,
            'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return records


def Artifact_Check(root: Path, prefix: str, *, architecture_check=None) -> None:
    graph = (Architecture_Check if architecture_check is None else architecture_check)(root)
    receipt = json.loads((root/'receipt.json').read_text())
    if (receipt['status'] != 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED' or
            receipt['failure'] is not None or receipt['warning_diagnostics'] or
            not receipt['commands'] or any(item['exit'] != 0 for item in receipt['commands']) or
            receipt['graph'] != graph):
        raise ValueError('Native recorded compile/analyzer scope is incomplete or disagrees with source graph')
    for inventory in ('experimental_files_sha256','output_artifact_sha256'):
        for path, digest in receipt[inventory].items():
            actual = (root/path).resolve()
            if not actual.is_relative_to(root.resolve()) or hashlib.sha256(actual.read_bytes()).hexdigest()!=digest:
                raise ValueError('Native recorded file/artifact identity differs: '+path)
    facts = receipt['facts']; reports = []
    def run(command):
        print('COMMAND '+json.dumps(command))
        result = subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=30)
        if result.returncode != 0:
            raise ValueError('Native artifact tool failed: '+result.stdout+result.stderr)
        return result.stdout
    for build in ('build','build/analysis'):
        for path in [*graph['sources'],*graph['asm_sources']]:
            obj = root/build/Path(path).with_suffix('.o')
            NativeArmAttributes_Validate(run([prefix+'readelf','-A',str(obj)]),
                core=facts['core'],fpu=facts['fpu'],hard_float='-mfloat-abi=hard' in graph['mcu_flags'],
                assembly=path in graph['asm_sources'])
        elf = root/build/'native.elf'
        NativeArmAttributes_Validate(run([prefix+'readelf','-A',str(elf)]),core=facts['core'],
            fpu=facts['fpu'],hard_float='-mfloat-abi=hard' in graph['mcu_flags'])
        symbols = run([prefix+'nm','-n',str(elf)])
        if len(re.findall(r'(?m)^[0-9a-fA-F]+\s+T\s+_sbrk$',symbols))!=1:
            raise ValueError('Rejecting heap ABI is not one strong linked owner')
        if re.search(r'(?m)^[0-9a-fA-F]+\s+\w\s+(malloc|calloc|realloc|free|_malloc_r|_calloc_r|_realloc_r|_free_r|pvPortMalloc|vPortFree)$',symbols):
            raise ValueError('Dynamic allocator unexpectedly linked')
        vector = root/build/'native-artifact-vectors.bin'
        run([prefix+'objcopy','--dump-section','.isr_vector='+str(vector),str(elf)])
        NativeIndependentVectors_Validate(vector.read_bytes(),symbols,receipt['contract']['independent_irq_slots'])
        sections = run([prefix+'objdump','-h',str(elf)])
        allocated = 0
        for item in re.finditer(r'^\s*\d+\s+(\S+)\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s+([\da-fA-F]+).*\n\s*([^\n]+)',sections,re.M):
            name,size,vma,lma,flags=item.groups()
            if 'ALLOC' not in flags or int(size,16)==0:continue
            allocated+=1
            for address in [int(vma,16)]+([int(lma,16)] if 'LOAD' in flags else []):
                if not any(region['origin']<=address and address+int(size,16)<=region['origin']+region['length'] for region in facts['regions']):
                    raise ValueError('Native linked section exceeds independently recorded memory: '+name)
        if allocated==0:raise ValueError('No allocated ARM sections parsed')
        map_text=(root/build/'native.map').read_text()
        libraries=NativeLinkedLibraries_Inspect(map_text, facts['regions'])
        stack_files=sorted((root/build).rglob('*.su'))
        reports.append({'build':build,'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
            'linked_libraries':libraries,
            'stack_usage_files':len(stack_files),
            'dynamic_frames':[str(p.relative_to(root)) for p in stack_files if '\tdynamic' in p.read_text()],
            'limits':'NOT PROVEN: library/indirect call graph, whole-program task/MSP/ISR nesting stack and MCU WCET'})
    (root/'build/native-artifact-report.json').write_text(json.dumps(reports,indent=2))
    print('PASS current artifact hashes, real object/ELF ARM attributes, independent IRQ positions, rejecting heap ABI and physical region bounds')
    print('EP0/full async lifecycle, semantic critical-contract review, actual stack margin, MCU timing and hardware: NOT PROVEN')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['architecture','host','artifact'],default='architecture',nargs='?')
    parser.add_argument('--host-cc',default='gcc')
    parser.add_argument('--prefix',default='arm-none-eabi-')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.mode=='architecture':
        Architecture_Check(root)
    elif args.mode=='host':
        Host_Check(root,args.host_cc)
    else:
        Artifact_Check(root,args.prefix)
