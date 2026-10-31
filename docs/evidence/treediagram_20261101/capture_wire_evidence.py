"""Retain actual C timing traces, C/Python bytes, and contract-derived offsets."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SCG = ROOT / 'apps/SCG'
OUT = Path(__file__).resolve().parent / 'ss-tm-wire-v1'
WORK = ROOT / '.work/0.1.3-treediagram-20261101/silverstar/wire-v1'
OUT.mkdir(exist_ok=False)
WORK.mkdir(exist_ok=False)
sys.path.insert(0, str(SCG / 'src'))
from silverstar_telemetry.codec import Frame_Encode, Frame_Decode


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


commands = []
def Run(name, command):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    (OUT / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    commands.append(dict(name=name, command=list(map(str, command)), exit_code=result.returncode))
    (OUT / 'commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


build = ROOT / '.work/0.1.3-treediagram-20261101/silverstar/scg-runtime-v2/tm_scheduler_build0'
receipt = json.loads((build / 'compiler-receipt.json').read_text(encoding='utf-8'))
project = Path(receipt['project'])
assert receipt['exit'] == 0
assert Hash(build / 'ss_tm_scheduler_host.c') == receipt['harness_sha256']
assert all(Hash(project / name) == sha for name, sha in receipt['generated_sources_sha256'].items())
shutil.copyfile(build / 'compiler-receipt.json', OUT / 'scheduler-compiler-receipt.json')
executable = build / 'tm_scheduler.exe'
timing = []
for scenario in ('normal', 'burst', 'landed', 'ack', 'observations', 'local_start', 'long',
                 'lost_start_ack', 'preflight', 'start_order', 'start_ack_backlog', 'start_event_full',
                 'stage_event', 'stage_scope', 'sx1278_airtime_events', 'sx1278_no_samples'):
    text = Run(scenario, [executable, scenario])
    assert '0 failures' in text
    timing.append(dict(scenario=scenario, measurements=[line for line in text.splitlines()
        if line.startswith(('TX_DONE', 'ordinary event', 'SX1278 PHY', 'TM profile', 'preflight'))]))
(OUT / 'scheduler-measurements.json').write_text(json.dumps(timing, indent=2), encoding='utf-8')

native = SCG / 'plugins/builtin/silverstar_protocol_telemetry_ss_tm/payload/Protocol/SS_TM'
core = SCG / 'plugins/builtin/silverstar_core_0_1_0/payload'
sources = [native / 'Legacy/ss_tm_legacy.c', native / 'Src/ss_tm_protocol.c', SCG / 'tests/fixtures/ss_tm_codec_host.c']
binary = WORK / 'ss_tm_codec.exe'
Run('codec-compile', ['D:/msys64/ucrt64/bin/gcc.exe', '-std=c11', '-Wall', '-Wextra', '-Werror',
    '-Wconversion', '-Wsign-conversion', '-Wshadow', '-Wvla', '-fanalyzer',
    *['-I' + str(path) for path in (core / 'Modules/Inc', native / 'Inc', native / 'Legacy', core / 'Common/Inc')],
    *sources, '-lm', '-o', binary])
actual = Run('codec-c-vectors', [binary]).splitlines()
values = [
    ('POSITION', dict(latitude_e7=0, longitude_e7=1799999999, ellipsoid_height_mm=-12000,
        sample_age_ms=12345, horizontal_accuracy_cm=65534, position_flags=15, satellite_count=12)),
    ('HEALTH', dict(battery_mv=0, battery_age_ds=65534, known_mask=0x7FF, fault_mask=0x42)),
    ('ACK', dict(acked_sequence=0xBEEF, command_id=1, result=0, time_ms=123456)),
    ('EVENT', dict(event_id=0x10203040, occurred_us=123456789, event_code=0x100,
        stage_id=0x11223344, instance_id=2, transaction_id=65534, arg0=7, arg1=9))]
vectors = []
for profile in ('S', 'H'):
    for sequence, (name, fields) in enumerate(values):
        frame = Frame_Encode(profile, name, sequence, 0x12345678, fields)
        assert Frame_Decode(frame).values == fields
        vectors.append(dict(profile=profile, scope='current active' if profile == 'S' else 'historical read compatibility',
            message=name, sequence=sequence, boot_session=0x12345678, fields=fields, hex=frame.hex()))
assert actual == [row['hex'] for row in vectors]
(OUT / 'golden-vectors.json').write_text(json.dumps(vectors, indent=2), encoding='utf-8')

contract_file = ROOT / 'contracts/ss_tm_v0_1.json'
contract = json.loads(contract_file.read_text(encoding='utf-8'))
shutil.copyfile(contract_file, OUT / 'ss_tm_v0_1.json')
sizes = {'u8':1, 'i8':1, 'u16':2, 'i16':2, 'u32':4, 'i32':4, 'u64':8, 'i64':8, 'f32':4}
lines = ['# SS-TM-S 当前逐字节定义', '',
    '来源：`contracts/ss_tm_v0_1.json`。所有多字节量 little-endian，float 为 IEEE-754 binary32。偏移从完整帧第 0 字节起算；无应用层 CRC，链路硬件 CRC 仍启用。最大帧 61 B。S 是当前唯一生成配置；bit7=1 的 H 只保留历史解码/迁移语义。', '',
    '## 公共头（8 B）', '', '| offset | bytes | type | field | meaning |', '|---:|---:|---|---|---|']
offset = 0
for field in contract['header']:
    size = sizes[field['type']]
    lines.append(f"| {offset} | {size} | {field['type']} | {field['name']} | {field['unit']} |")
    offset += size
assert offset == 8
for name, message in contract['messages'].items():
    lines += ['', f"## {name} (type 0x{message['type']:02X}, total {message['length']} B)", '',
              '| offset | bytes | type | field | unit / meaning |', '|---:|---:|---|---|---|']
    offset = 8
    for field in message['fields']:
        match = re.fullmatch(r'(\w+)(?:\[(\d+)\])?', field['type'])
        size = sizes[match[1]] * int(match[2] or 1)
        lines.append(f"| {offset} | {size} | {field['type']} | {field['name']} | {field.get('unit', '')} |")
        offset += size
    assert offset == message['length'], (name, offset)
for key in ('position_flags', 'invalid', 'events', 'queue', 'phy_baseline'):
    lines += ['', '## ' + key, '', '| name | value |', '|---|---|']
    lines += [f'| {name} | {value} |' for name, value in contract[key].items()]
lines += ['', '## HEALTH known/fault bit indices', '', '| bit | meaning |', '|---:|---|']
lines += [f'| {index} | {name} |' for index, name in enumerate(contract['health_bits'])]
(OUT / 'WIRE_BYTES_ZH.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
(OUT / 'provenance.json').write_text(json.dumps(dict(
    scheduler_binary_sha256=Hash(executable), codec_binary_sha256=Hash(binary),
    source_hashes={str(path.relative_to(ROOT)): Hash(path) for path in [contract_file, *sources]},
    scope='Actual generated telemetry service/codec with actual SX1281 driver and Host ports; simulated TX_DONE from PHY airtime, not measured RF. SX1278 scenarios use capacity-one transport facade plus SX1278 exact PHY ToA, not driver/hardware timing proof.',
    expected_c_python_vectors=8, mismatches=0), indent=2), encoding='utf-8')
print('16 scheduler scenarios and 8 exact C/Python vectors passed; contract offsets checked')
