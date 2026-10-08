"""Authorized bounded Flight-only stages; no active-run halt or calibration."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess
import sys

out = Path(__file__).resolve().parent
stage = sys.argv[1]
assert stage in ('preflight', 'program', 'startup', 'post')
dest = out / ('hardware_' + stage)
dest.mkdir(exist_ok=False)
project = out / 'project/Flight_Controller'
image = project / 'build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin'
for name in ('architecture', 'power10', 'release', 'stack', 'analyzer', 'host'):
    assert json.loads((out / (name + '_result.json')).read_text())['exit_code'] == 0, name
assert json.loads((out / 'pytest_normal_v2_result.json').read_text())['exit_code'] == 0
assert hashlib.sha256(image.read_bytes()).hexdigest() == 'cf1a359c9212354b63b4af8b83f0db4008897eb333d35d220d8eec4a2f33da4c'
owner = Path('apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload')
for relative in ['APP/Src/estimator_task.c', 'Tools/check_task_stacks.py']:
    assert (owner / relative).read_text() == (project / relative).read_text(), relative
layout = json.loads((out / 'diagnostic_layout.json').read_text())
elf = Path(layout['elf'])
assert hashlib.sha256(elf.read_bytes()).hexdigest() == layout['elf_sha256']
script = ['init',
          'set id [lindex [read_memory 0xE0042000 32 1] 0]; set size [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($size != 512)} {error {Target mismatch; stop}}',
          'echo "TARGET_ID=$id FLASH_KIB=$size"',
          'echo "UID=[read_memory 0x1FFF7A10 32 3]"',
          'echo "CORE_BEFORE=[read_memory 0xE000EDF0 32 1]"']
if stage == 'preflight':
    script += ['echo "OLD_LIFECYCLE=[read_memory 0x2001a214 8 1]"',
               'dump_image {' + (dest / 'before_fullflash.bin').as_posix() + '} 0x08000000 524288']
elif stage == 'program':
    preflight = json.loads((out / 'hardware_preflight/result.json').read_text())
    assert preflight['old_image_verified'] and preflight['old_lifecycle'] == 2 and preflight['exit_code'] == 0
    expected_uid = ' '.join(str(value) for value in preflight['uid_words'])
    script += ['set uid [read_memory 0x1FFF7A10 32 3]; if {$uid ne {' + expected_uid + '}} {error {Device UID changed; no flash}}',
               'set phase [lindex [read_memory 0x2001a214 8 1] 0]; if {$phase != 2} {error {Expected old verified PREFLIGHT; no flash}}',
               'program {' + image.as_posix() + '} 0x08000000 verify reset',
               'dump_image {' + (dest / 'readback.bin').as_posix() + '} 0x08000000 ' + str(image.stat().st_size),
               'dump_image {' + (dest / 'sector7.bin').as_posix() + '} 0x08060000 131072']
else:
    assert json.loads((out / 'hardware_program/result.json').read_text())['readback_verified']
    for key, field in layout['fields'].items():
        script.append('echo "FIELD_' + key + '=[read_memory ' + hex(field['address']) + ' 8 ' + str(field['bytes']) + ']"')
script += ['echo "CORE_AFTER=[read_memory 0xE000EDF0 32 1]"', 'shutdown']
argv = ['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe', '-s',
        'D:/OpenOCD-20250710-0.12.0/share/openocd/scripts', '-f', 'interface/cmsis-dap.cfg',
        '-c', 'adapter serial 132765403520', '-c', 'transport select swd',
        '-f', 'target/stm32f4x.cfg', '-c', 'reset_config none',
        '-c', 'stm32f4x.cpu configure -event examine-end {}',
        '-c', 'gdb_port disabled; tcl_port disabled; telnet_port disabled', '-c', '; '.join(script)]
record = dict(stage=stage, argv=argv, utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(), elf_sha256=layout['elf_sha256'],
              flash=stage == 'program', reset=stage == 'program', halt=stage == 'program',
              active_mission_halt=False, calibration_command=False, ground_flash=False,
              mass_erase=False, options=False, timeout_s=60)
(dest / 'command.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
result = subprocess.run(argv, capture_output=True, timeout=60)
raw = result.stdout + b'\n--- STDERR ---\n' + result.stderr
(dest / 'openocd.log').write_bytes(raw)
record.update(exit_code=result.returncode, utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              log_sha256=hashlib.sha256(raw).hexdigest())
if result.returncode == 0:
    text = raw.decode(errors='replace')
    record['uid_words'] = [int(value) for value in re.search(r'UID=(\d+(?: \d+)*)', text)[1].split()]
    assert len(record['uid_words']) == 3
    cores = [int(value) for value in re.findall(r'CORE_(?:BEFORE|AFTER)=(\d+)', text)]
    record['core_values'] = cores
    record['running_after'] = bool(cores and not (cores[-1] & (1 << 17)))
    if stage == 'preflight':
        before = (dest / 'before_fullflash.bin').read_bytes()
        old = Path('.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin').read_bytes()
        assert hashlib.sha256(old).hexdigest() == '5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3'
        assert len(before) == 524288
        record.update(old_image_verified=before[:len(old)] == old,
                      old_lifecycle=int(re.search(r'OLD_LIFECYCLE=(\d+)', text)[1]),
                      old_lifecycle_scope='Address from the prior ELF-matched final_state record; applicable only after old prefix identity check',
                      fullflash_sha256=hashlib.sha256(before).hexdigest())
    elif stage == 'program':
        readback = (dest / 'readback.bin').read_bytes()
        before = (out / 'hardware_preflight/before_fullflash.bin').read_bytes()
        record.update(readback_verified=readback == image.read_bytes(),
                      readback_sha256=hashlib.sha256(readback).hexdigest(),
                      untouched_sector7=(dest / 'sector7.bin').read_bytes() == before[393216:])
    else:
        fields = {}
        for key, values in re.findall(r'FIELD_(\w+)=(\d+(?: \d+)*)', text):
            data = bytes(int(value) for value in values.split())
            assert len(data) == layout['fields'][key]['bytes'], key
            fields[key] = dict(hex=data.hex(), value=int.from_bytes(data, 'little'))
        assert len(fields) == len(layout['fields'])
        fields['path']['text'] = bytes.fromhex(fields['path']['hex']).split(b'\0')[0].decode('ascii')
        record['fields'] = fields
(dest / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
assert result.returncode == 0 and record.get('running_after'), record
if stage == 'preflight': assert record['old_image_verified']
if stage == 'program': assert record['readback_verified'] and record['untouched_sector7']
print(json.dumps({key: value for key, value in record.items() if key not in ('argv','fields')}, indent=2))
