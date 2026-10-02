"""Generated Ground software gates. No hardware or repository dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def Command_Run(command: list[str], root: Path) -> str:
    print('COMMAND ' + json.dumps(command), flush=True)
    result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120)
    print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError(f'command exit {result.returncode}')
    return result.stdout


def Architecture_Check(root: Path) -> dict:
    graph = json.loads((root / 'Generated/ground_source_graph.json').read_text(encoding='utf-8'))
    make = (root / 'Makefile').read_text(encoding='utf-8').replace('\\\n', ' ')
    for key, variable in [('sources', 'C_SOURCES'), ('asm_sources', 'ASM_SOURCES')]:
        match = re.search(rf'^{variable} := (.*)$', make, re.M)
        if match is None or match[1].split() != graph[key]:
            raise ValueError(f'{variable} differs from declared source graph')
        if len(graph[key]) != len(set(graph[key])):
            raise ValueError(f'duplicate {key}')
    sources = graph['sources'] + graph['asm_sources']
    for relative in sources + graph['include_dirs'] + [graph['linker_script']]:
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.exists():
            raise ValueError(f'missing or escaped source graph path: {relative}')
    owned = ('Common/', 'Devices/', 'Generated/', 'Ground/', 'Platform/')
    vendor = ('Core/', 'Drivers/', 'HardwareGenerated/', 'Middlewares/')
    for source in graph['sources']:
        if not source.startswith(owned + vendor):
            raise ValueError(f'unclassified source: {source}')
        if any(part in source for part in ('FreeRTOS', 'FatFs', 'FATFS', '/Adapter/')):
            raise ValueError(f'Flight-only source in Ground graph: {source}')
    mains = [source for source in graph['sources'] if source.endswith('/main.c')]
    if len(mains) != 1:
        raise ValueError('Ground must have exactly one main')
    main = (root / mains[0]).read_text(encoding='utf-8')
    if 'GroundBridge_Init' not in main or 'GroundBridge_Process' not in main:
        raise ValueError('Ground bridge integration missing')
    if any(name in main for name in ('AppTasks_Init', 'SystemStartup_Run', 'MX_FATFS_Init')):
        raise ValueError('Flight startup in Ground main')
    if '-T' + graph['linker_script'] not in make:
        raise ValueError('linker script differs from graph')
    metadata = json.loads((root / 'Generated/ground_target_metadata.json').read_text(encoding='utf-8'))
    if metadata['target_role'] != 'ground_station':
        raise ValueError('wrong target role')
    print(f'PASS Ground declared source graph ({len(sources)} sources), ownership and startup')
    print('Critical-contract manual review, call graph, stack and MCU timing: NOT PROVEN')
    return graph


def Host_Check(root: Path, compiler: str) -> None:
    # Execute generated bridge sources with bounded RX and PC busy/error injection.
    build = root / 'build/ground-host'
    build.mkdir(parents=True, exist_ok=True)
    tests = root / 'Tests/Host'
    includes = [build, root / 'Ground/Core/Inc', root / 'Ground/Protocol/Inc', root / 'Common/Inc']
    common = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wvla',
              *['-I' + str(path) for path in includes]]
    bridge = [str(root / path) for path in (
        'Ground/Core/Src/ground_bridge.c', 'Ground/Protocol/Src/gsp_min_protocol.c',
        'Ground/Protocol/Src/protocol_crc16.c', 'Common/Src/silverstar_assert.c')]
    cases = [('bridge_bounds', bridge, tests / 'ground_bridge_bounds.c')]
    adapter = root / 'Generated/Src/pc_byte_stream.c'
    text = adapter.read_text(encoding='utf-8')
    if 'HAL_UARTEx_ReceiveToIdle_DMA' in text:
        handle = re.search(r'extern UART_HandleTypeDef (\w+);', text)
        if handle is None:
            raise ValueError('UART DMA handle missing')
        (build / 'main.h').write_text((tests / 'uart_dma_main.h').read_text(encoding='utf-8'), encoding='utf-8')
        harness = build / 'uart_dma.c'
        harness.write_text((tests / 'uart_dma.c').read_text(encoding='utf-8').replace('huart1', handle[1]), encoding='utf-8')
        cases.append(('uart_dma', [str(adapter), str(root / 'Common/Src/silverstar_assert.c')], harness))
    elif 'CDC_Transmit_FS' in text:
        shutil.copyfile(tests / 'usb_cdc_if.h', build / 'usbd_cdc_if.h')
        cases.append(('usb_cdc', [str(adapter)], tests / 'usb_cdc.c'))
    else:
        raise ValueError('No host harness for selected PC transport; acceptance blocked')
    for name, sources, harness in cases:
        executable = build / (name + '.exe')
        Command_Run(common + sources + [str(harness), '-o', str(executable)], root)
        Command_Run([str(executable)], root)
        print('PASS host ' + name)
    print(f'PASS {len(cases)} generated-source host executables; HAL/radio are mocks, no MCU recovery proof')


def Artifact_Check(root: Path, prefix: str) -> None:
    graph = Architecture_Check(root)
    elf = root / 'build/ground.elf'
    binary = root / 'build/ground.bin'
    header = Command_Run([prefix + 'readelf', '-h', str(elf)], root)
    if not re.search(r'Machine:\s+ARM\b', header):
        raise ValueError('ELF is not ARM')
    symbols = Command_Run([prefix + 'nm', '-g', str(elf)], root)
    for symbol in ('Reset_Handler', 'main', 'GroundBridge_Init', 'GroundBridge_Process',
                   'PcByteStream_Init', 'GroundRadio_Process'):
        if not re.search(r'\b' + symbol + r'$', symbols, re.M):
            raise ValueError('linked required symbol missing: ' + symbol)
    if re.search(r'\b(?:pvPortMalloc|vTaskStartScheduler|SystemStartup_Run|malloc|calloc|realloc)$', symbols, re.M):
        raise ValueError('unexpected Flight scheduler or allocation symbol')
    memory = {}
    linker = (root / graph['linker_script']).read_text(encoding='utf-8')
    for name, origin, length, unit in re.findall(
            r'(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(0x[\da-fA-F]+)\s*,\s*LENGTH\s*=\s*(\d+)\s*([KM]?)', linker):
        memory[name] = (int(origin, 16), int(length) * {'': 1, 'K': 1024, 'M': 1048576}[unit])
    if 'FLASH' not in memory or 'RAM' not in memory:
        raise ValueError('unrecognized declared memory regions')
    sections = Command_Run([prefix + 'objdump', '-h', str(elf)], root)
    found = 0
    for match in re.finditer(r'^\s*\d+\s+(\S+)\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s+([\da-fA-F]+).*\n\s*([^\n]+)', sections, re.M):
        name, size, vma, lma, flags = match.groups()
        if 'ALLOC' not in flags or int(size, 16) == 0:
            continue
        found += 1
        addresses = [int(vma, 16)] + ([int(lma, 16)] if 'LOAD' in flags else [])
        for address in addresses:
            if not any(start <= address and address + int(size, 16) <= start + limit
                       for start, limit in memory.values()):
                raise ValueError('linked section outside declared regions: ' + name)
    if found == 0:
        raise ValueError('no allocated sections parsed')
    map_text = (root / 'build/ground.map').read_text(encoding='utf-8')
    for source in graph['sources'] + graph['asm_sources']:
        object_path = 'build/' + str(Path(source).with_suffix('.o')).replace('\\', '/')
        if object_path not in map_text or not (root / object_path).is_file():
            raise ValueError('declared object absent from link map: ' + object_path)
        if elf.stat().st_mtime_ns < (root / source).stat().st_mtime_ns:
            raise ValueError('ELF older than source: ' + source)
    reproduced = root / 'build/ground-artifact.bin'
    Command_Run([prefix + 'objcopy', '-O', 'binary', str(elf), str(reproduced)], root)
    if binary.read_bytes() != reproduced.read_bytes():
        raise ValueError('BIN does not match linked ELF')
    for path in (elf, binary):
        print('SHA256 ' + str(path) + ' ' + hashlib.sha256(path.read_bytes()).hexdigest())
    print('PASS ARM ELF/BIN identity, declared memory bounds, required symbols and linked source graph')
    print('Metadata version is configuration provenance; embedded product version NOT PROVEN')
    print('Actual task/ISR stack margin, radio timing and hardware qualification: NOT PROVEN')


def Main_Run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('gate', choices=('architecture', 'host', 'artifact'))
    parser.add_argument('--host-cc', default='gcc')
    parser.add_argument('--prefix', default='arm-none-eabi-')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.gate == 'architecture':
        Architecture_Check(root)
    elif args.gate == 'host':
        Host_Check(root, args.host_cc)
    else:
        Artifact_Check(root, args.prefix)


if __name__ == '__main__':
    Main_Run()
