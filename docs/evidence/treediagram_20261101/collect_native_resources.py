"""Measure private native candidates from actual linked sections and linker regions.

This is retained evidence computation, not a replacement for the firmware gate.
No dynamic stack margin or MCU hardware qualification is inferred.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / 'native-resources'
BIN = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Measure(part, root):
    folder = OUT / part
    folder.mkdir(parents=True, exist_ok=True)
    elf, map_file = root / 'build/native.elf', root / 'build/native.map'
    commands = []
    outputs = {}
    for name, args in [('size', ['-A']), ('objdump', ['-h'])]:
        command = [str(BIN / ('arm-none-eabi-' + name + '.exe')), *args, str(elf)]
        run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (folder / (name + '.log')).write_text(run.stdout, encoding='utf-8')
        commands.append(dict(command=command, exit_code=run.returncode))
        assert run.returncode == 0
        outputs[name] = run.stdout
    # The map is the exact linker invocation's resolved MEMORY inventory.
    memory = map_file.read_text(encoding='utf-8').split('Memory Configuration', 1)[1].split('Linker script and memory map', 1)[0]
    regions = []
    for name, origin, length in re.findall(r'^([A-Za-z][\w]*)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)', memory, re.M):
        regions.append(dict(name=name, origin=int(origin, 16), capacity_bytes=int(length, 16), sections=[]))
    lines = outputs['objdump'].splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+', line)
        if not match or index + 1 == len(lines):
            continue
        name, size, vma, lma = match.groups()
        size, vma, lma = int(size, 16), int(vma, 16), int(lma, 16)
        flags = lines[index + 1]
        if not size or 'ALLOC' not in flags:
            continue
        locations = [(vma, 'run')]
        if lma != vma and 'LOAD' in flags:
            locations.append((lma, 'load'))
        for address, role in locations:
            owners = [region for region in regions if region['origin'] <= address and
                      address + size <= region['origin'] + region['capacity_bytes']]
            assert len(owners) == 1, (name, address, owners)
            owners[0]['sections'].append(dict(name=name, bytes=size, address=address, role=role))
    for region in regions:
        region['used_bytes'] = sum(section['bytes'] for section in region['sections'])
        region['allocated_span_bytes'] = max((section['address'] + section['bytes'] - region['origin']
                                              for section in region['sections']), default=0)
        region['unallocated_bytes_by_sum'] = region['capacity_bytes'] - region['used_bytes']
        region['tail_bytes_after_last_section'] = region['capacity_bytes'] - region['allocated_span_bytes']
    result = dict(part=part, status='linked private candidate; release gate remains blocked',
                  method='ARM objdump ALLOC VMA and LOAD LMA sections mapped to exact linked MEMORY regions; alignment span reported separately',
                  stack_status='NOT PROVEN; reserved linker bytes are included, not safe dynamic headroom',
                  artifacts={str(path.relative_to(root)): Hash(path) for path in (elf, map_file)},
                  regions=regions, commands=commands)
    shutil.copyfile(root / 'backend-receipt.json', folder / 'backend-receipt.json')
    shutil.copyfile(root / 'receipt.json', folder / 'compile-receipt.json')
    shutil.copyfile(map_file, folder / 'native.map')
    (folder / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    candidates = [('STM32C071FBP6', REPO / '.work/0.1.3-treediagram-20261101/silverstar/c071-v1/candidate')]
    for line in (Path(__file__).parent / 'native-build-v2-index.jsonl').read_text().splitlines():
        row = json.loads(line)
        candidates.append((row['part'], Path(row['output'])))
    results = [Measure(part, root) for part, root in candidates]
    (OUT / 'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps([dict(part=row['part'], regions=[{k:v for k,v in bank.items() if k != 'sections'}
                                                     for bank in row['regions']]) for row in results], indent=2))
