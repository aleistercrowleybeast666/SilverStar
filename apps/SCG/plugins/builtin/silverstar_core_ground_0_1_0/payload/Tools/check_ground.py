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


def ResourceIndex_Get(root: Path, expression: str, kind: str) -> int:
    """Resolve only generated enum names or exact typed unsigned constants."""
    type_name = {'spi': 'PlatformSpiId', 'gpio': 'PlatformGpioId', 'time': 'PlatformTimeId'}[kind]
    header = (root / f'Platform/Inc/platform_{kind}.h').read_text(encoding='utf-8')
    declaration = re.search(r'typedef\s+enum\s*\{([^{}]+)\}\s*' + type_name + r'\s*;', header)
    if declaration is None:
        raise ValueError('Resource enum declaration missing: ' + kind)
    values = {}; value = -1
    for entry in declaration[1].split(','):
        match = re.fullmatch(r'\s*(\w+)\s*(?:=\s*(\d+)U?)?\s*', entry)
        if match is None:
            raise ValueError('Unsupported resource enum declaration: ' + kind)
        value = int(match[2]) if match[2] is not None else value + 1
        values[match[1]] = value
    expression = expression.strip()
    typed = re.fullmatch(r'\(\(\s*' + type_name + r'\s*\)\s*(\d+)U\s*\)', expression)
    if expression in values and expression != 'PLATFORM_' + kind.upper() + '_COUNT':
        index = values[expression]
    elif typed is not None:
        index = int(typed[1])
    else:
        raise ValueError('Unsupported resource binding expression: ' + expression)
    if not 0 <= index < values['PLATFORM_' + kind.upper() + '_COUNT']:
        raise ValueError('Resource binding outside enum capacity: ' + expression)
    platform = (root / 'Generated/Src/platform_resources.c').read_text(encoding='utf-8')
    table_name = {'spi': 's_spi_handles', 'gpio': 's_gpio_resources', 'time': 's_time_resources'}[kind]
    table = re.search(r'\b' + table_name + r'\s*\[[^\]]+\]\s*=\s*\{(.*?)\n\};', platform, re.S)
    if table is None:
        raise ValueError('Generated resource table missing: ' + kind)
    selectors = re.findall(r'\[\s*(\w+)\s*\]\s*=', table[1])
    configured = {int(token[:-1]) if re.fullmatch(r'\d+U', token) else values.get(token, -1) for token in selectors}
    if index not in configured:
        raise ValueError('Resource binding has no configured platform row: ' + expression)
    return index


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
    family = metadata.get('radio_family')
    adapters = {'sx128x': 'Ground/Radio/Src/ground_radio_sx1281.c',
                'nrf24': 'Ground/Radio/Src/ground_radio_nrf24.c'}
    if family not in adapters or adapters[family] not in graph['sources']:
        raise ValueError('selected backend adapter missing')
    for other, path in adapters.items():
        if other != family and (path in graph['sources'] or (root / path).exists()):
            raise ValueError('unselected backend adapter present')
    air = (root / 'Generated/Inc/air_link_config.h').read_text(encoding='utf-8')
    resource = (root / 'Generated/Inc/project_resources.h').read_text(encoding='utf-8')
    if family == 'nrf24':
        required = ('Devices/Telemetry/NRF24L01P/Src/nrf24_device.c',
                    'Devices/Telemetry/NRF24L01P/Src/nrf24_fragment.c')
        if any(path not in graph['sources'] for path in required):
            raise ValueError('NRF backend implementation missing')
        if any('/SX128' in path for path in graph['sources']):
            raise ValueError('SX implementation in NRF graph')
        if 'AIR_LINK_NRF24_CHANNEL' not in air or 'AIR_LINK_SX128' in air:
            raise ValueError('NRF backend header mismatch')
        for macro in ('PROJECT_NRF24_INSTANCE_COUNT', 'PROJECT_NRF24_INSTANCE_COUNT_MAX'):
            if not re.search(r'#define\s+' + macro + r'\s+1U\b', resource):
                raise ValueError('NRF instance bound mismatch')
        if any(' ' + field + ';' not in resource for field in ('spi', 'csn', 'ce', 'time')):
            raise ValueError('NRF resource binding missing')
        bindings = (root / 'Generated/Src/project_resources.c').read_text(encoding='utf-8')
        rows = re.findall(r'\{\s*\.spi\s*=\s*([^,{}]+)\s*,\s*\.csn\s*=\s*([^,{}]+)\s*,\s*\.ce\s*=\s*([^,{}]+)\s*,\s*\.time\s*=\s*([^,{}]+)\s*\}', bindings)
        if len(rows) != 1:
            raise ValueError('NRF resource ownership collision or missing row')
        indices = [ResourceIndex_Get(root, expression, kind) for expression, kind in zip(rows[0], ('spi', 'gpio', 'gpio', 'time'))]
        if indices[1] == indices[2]:
            raise ValueError('NRF resource ownership collision or missing row')
        ground_header = (root / 'Generated/Inc/ground_radio_config.h').read_text(encoding='utf-8')
        if not re.search(r'#define\s+GROUND_RADIO_BACKEND_NRF24\s+1U\b', ground_header):
            raise ValueError('NRF metric capability dispatch missing')
    else:
        if 'AIR_LINK_NRF24' in air or any('/NRF24' in path for path in graph['sources']):
            raise ValueError('NRF implementation in SX graph')
    print(f'PASS Ground declared source graph ({len(sources)} sources), ownership and startup')
    print('Critical-contract manual review, call graph, stack and MCU timing: NOT PROVEN')
    return graph


def Host_Check(root: Path, compiler: str) -> None:
    # Execute generated bridge sources with bounded RX and PC busy/error injection.
    build = root / 'build/ground-host'
    build.mkdir(parents=True, exist_ok=True)
    tests = root / 'Tests/Host'
    includes = [build, root / 'Ground/Core/Inc', root / 'Ground/Protocol/Inc', root / 'Common/Inc', root / 'Generated/Inc', root / 'Platform/Inc']
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
