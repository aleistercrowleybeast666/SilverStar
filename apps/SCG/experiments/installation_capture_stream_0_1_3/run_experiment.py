"""Offline ARM layout/encoder and finite stream model. Never opens a port."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
RUN = sys.argv[1] if len(sys.argv) == 2 else 'v2'
if re.fullmatch(r'v[1-9][0-9]{0,2}', RUN) is None:
    raise ValueError('Run must be a fresh bounded v<number> suffix')
OUT = ROOT / ('.work/dev013_installation_stream_20261019_' + RUN)
PROTECTED = Path('D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01')
OWNER = 'installation_stream_resource_experiment_20261019_' + RUN
COMMANDS = []


def fingerprint(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def run(label, args, *, success=True):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True,
                            timeout=120, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    (OUT / f'{label}.stdout').write_bytes(result.stdout)
    (OUT / f'{label}.stderr').write_bytes(result.stderr)
    COMMANDS.append({'name': label, 'args': [str(a) for a in args], 'exit': result.returncode,
                     'expected_success': success})
    (OUT / 'commands.json').write_text(json.dumps(COMMANDS, indent=2), encoding='utf-8')
    if (result.returncode == 0) != success:
        raise RuntimeError(f'{label}: unexpected exit {result.returncode}; complete logs retained')
    return result.stdout


def sections(path):
    data = path.read_bytes()
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    assert header[0][:6] == b'\x7fELF\x01\x01'
    entries = [struct.unpack_from('<10I', data, header[6] + i * header[11])
               for i in range(header[12])]
    names_record = entries[header[13]]
    names = data[names_record[4]:names_record[4] + names_record[5]]
    return {names[e[0]:].split(b'\0', 1)[0].decode():
            {'address': e[3], 'size': e[5], 'data': data[e[4]:e[4] + e[5]], 'type': e[1]}
            for e in entries}


class StreamModel:
    """Sequential bounded publication model; does not prove RTOS concurrency."""
    def __init__(self, initial=0):
        self.queue = [[i, 0] for i in range(initial)]
        self.next_pair = initial
        self.failed = False
        self.cancelled = False
        self.sent = []

    def produce(self):
        if self.failed or self.cancelled:
            return False
        if len(self.queue) == 2:
            self.failed = True
            return False
        self.queue.append([self.next_pair, 0])
        self.next_pair += 1
        return True

    def send(self, accepted=True):
        if self.failed or self.cancelled or not self.queue or not accepted:
            return
        pair, part = self.queue[0]
        self.sent.append((pair, part))
        self.queue[0][1] += 1
        if self.queue[0][1] == 2:
            self.queue.pop(0)

    def cancel(self):
        self.cancelled = True
        # No later producer/publication is permitted. Production needs a real
        # acknowledgement of the consumer lease before these slots are recycled.


def model_tests():
    checks = []
    m = StreamModel()
    for millisecond in range(6400):
        if millisecond % 200 == 0:
            assert m.produce()
        if millisecond % 50 == 0:
            m.send()
    assert not m.failed and not m.queue and len(m.sent) == 64
    checks.append('32 pairs at exactly 5 Hz; one part service/50 ms; exact complete order')
    assert m.sent == [(p, k) for p in range(32) for k in range(2)]
    assert [p for p, k in m.sent if k == 0 and p < 16] == list(range(16))
    assert [p for p, k in m.sent if k == 0 and p >= 16] == list(range(16, 32))
    checks.append('TRAIN/HOLDOUT disjoint fixed pair boundary; original order retained')
    m = StreamModel(); assert m.produce(); m.send(); m.send(False)
    assert m.queue == [[0, 1]] and m.sent == [(0, 0)]
    m.send(); assert not m.queue and m.sent == [(0, 0), (0, 1)]
    checks.append('second-part TX rejection retains slot/cursor; accepted first part not duplicated')
    for initial in range(3):
        m = StreamModel(initial)
        for _ in range(2 - initial):
            assert m.produce()
        assert not m.produce() and m.failed
        assert not m.produce()
    checks.append('initial occupancy 0/1/2: first over-capacity arrival fails entire face')
    for partial in range(2):
        m = StreamModel(); assert m.produce()
        if partial: m.send()
        before = list(m.sent); m.cancel(); m.send(); assert not m.produce()
        assert m.sent == before
    checks.append('cancel before either part: no new sample/part publication after model acknowledgement')
    for start in range(0, 200, 10):
        m = StreamModel()
        for t in range(1400):
            if t % 200 == 0 and not m.failed: m.produce()
            if t % 50 == 0 and not start <= t < start + 500: m.send()
        assert m.failed
    checks.append('500 ms service blackout at every 10 ms phase: overflow is visible failure')
    m = StreamModel(); assert m.produce(); assert m.produce(); assert not m.produce()
    checks.append('three-pair burst rejected, not silently downsampled')
    return checks


def calculations():
    sid, binding = 'f' * 32, 'B-' + 'a' * 30
    base = f'INSTALL FACE sid={sid} rid=4294967295 binding={binding}'
    replies = {
        'progress': f'PENDING {base} state=COLLECTING train_count=64 holdout_count=64\r\n',
        'complete': f'OK {base} state=COMPLETE train_count=64 holdout_count=64\r\n',
        'failed': f'ERR {base} state=FAILED code=SOURCE_FAULT reason=SOURCE_TIMEOUT\r\n',
        'cancel': f'OK INSTALL DO sid={sid} rid=4294967295 cleanup_complete=1\r\n',
    }
    assert max(map(len, replies.values())) <= 192
    poll = f'INSTALL POLL {sid} 4294967295\r\n'
    cancel = f'INSTALL DO {sid} 4294967295 CANCEL\r\n'
    sys.path.insert(0, str(ROOT / 'apps/GSHC'))
    from services.installation_calibration_protocol import Response_Decode, Request_Decode
    for line in replies.values():
        Response_Decode(line.encode().removesuffix(b'\r\n'))
    Request_Decode(poll.encode().removesuffix(b'\r\n'))
    rates = []
    for hz in (2, 5, 10, 20):
        rates.append({'pairs_per_s': hz, 'hex_sample_bytes_per_s': hz * 876,
                      'poll_192_cap_bytes_per_s': 20 * 192,
                      'downstream_bits_per_s': (hz * 876 + 20 * 192) * 10,
                      'upstream_poll_bits_per_s': 20 * len(poll) * 10,
                      'at_115200': (hz * 876 + 20 * 192) * 10 / 115200,
                      'at_230400': (hz * 876 + 20 * 192) * 10 / 230400})
    return {'replies': {k: {'line': v, 'bytes': len(v)} for k, v in replies.items()},
            'existing_codec_checks': 'four replies and POLL request accepted',
            'poll_request_bytes': len(poll), 'cancel_request_bytes': len(cancel),
            'reply_cap': 192, 'rates': rates,
            'optional_base64_pair_bytes': 676, 'optional_base64_implemented': False,
            'face_example_s': {'settle': 2, 'capture_16_plus_16_at_5hz': 6.4,
                               'conditional_drain': 0.5, 'total': 8.9},
            'worst_existing_normal_backlog_4095B_plus_192B_at_115200_ms': (4095 + 192) * 10 / 115200 * 1000,
            'worst_add_priority1023B_at_115200_ms': (4095 + 192 + 1023) * 10 / 115200 * 1000,
            'exclusions': 'other writers, HAL/DMA delay, scheduling/interrupt latency, RX command parse, host disk stalls'}


def main():
    if OUT.exists():
        raise RuntimeError('Fresh output directory required; never overwrite earlier experiment evidence')
    OUT.mkdir(parents=True)
    original = json.loads((ROOT / '.work/dev013_installation_capture_gate_20261019_v1/audit.json').read_text(encoding='utf-8'))
    protected_before = {p: fingerprint(PROTECTED / p) for p in original['candidate_before']}
    assert protected_before == original['candidate_before']
    source_snapshot = {str(p.relative_to(ROOT)): {'hex': p.read_bytes().hex(), **fingerprint(p)}
                       for p in sorted(SOURCE.iterdir()) if p.is_file()}
    (OUT / 'source_snapshot.json').write_text(json.dumps(source_snapshot, indent=2), encoding='utf-8')
    arm, host = shutil.which('arm-none-eabi-gcc'), shutil.which('gcc')
    assert arm and host
    versions = {'arm': run('arm_version', [arm, '--version']).decode(),
                'host': run('host_version', [host, '--version']).decode(), 'python': sys.version}
    common = ['-std=c11', '-Wall', '-Wextra', '-Wconversion', '-Wshadow', '-Wstrict-prototypes', '-Werror']
    target = ['-mcpu=cortex-m4', '-mthumb', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard']
    source = SOURCE / 'layout_probe.c'
    run('arm_compile', [arm, *common, *target, '-Os', '-ffreestanding', '-fno-builtin',
        '-ffunction-sections', '-fdata-sections', '-fstack-usage', '-c', source, '-o', OUT / 'layout.o'])
    run('arm_analyzer', [arm, *common, *target, '-O0', '-ffreestanding', '-fno-builtin', '-fanalyzer',
        '-c', source, '-o', OUT / 'analyzer.o'])
    run('arm_link', [arm, *target, '-nostdlib', '-Wl,--gc-sections', f'-Wl,-Map={OUT / "layout.map"}',
        '-T', SOURCE / 'experiment.ld', OUT / 'layout.o', '-lgcc', '-o', OUT / 'layout.elf'])
    run('host_compile', [host, *common, '-O2', '-DEXPERIMENT_HOST', source, '-o', OUT / 'encoder.exe'])
    encoded = run('host_encoder', [OUT / 'encoder.exe'])
    body = bytes(range(154))
    expected = (f'EVENT INSTALL IMU sid={"f"*32} pair=4294967295 ctx=B-{"ab"*15} '
                f'data={body.hex().upper()} crc32={zlib.crc32(body):08X}\r\n').encode()
    assert encoded == expected and len(encoded) == 438
    sec = sections(OUT / 'layout.elf')
    layout = struct.unpack('<14I', sec['.layout']['data'])
    assert layout[0] == sec['.capture_ccm']['size'] <= 2048
    assert sec['.capture_ccm']['address'] == 0x1000F5B8
    assert all(sec.get(k, {}).get('size', 0) == 0 for k in ('.data', '.bss'))
    # Original proposed memory amount deliberately fails the same isolated free-region link.
    counter = OUT / 'old_budget_counter.c'
    counter.write_text('static volatile unsigned char state[6208] __attribute__((used,section(".capture_ccm")));\nvoid Experiment_Entry(void) {state[0]=1;}\n', encoding='ascii')
    run('old_budget_compile', [arm, *common, *target, '-Os', '-ffreestanding', '-c', counter, '-o', OUT / 'old_budget.o'])
    run('old_budget_link_expected_failure', [arm, *target, '-nostdlib', '-T', SOURCE / 'experiment.ld',
        OUT / 'old_budget.o', '-o', OUT / 'old_budget.elf'], success=False)
    protected_after = {p: fingerprint(PROTECTED / p) for p in protected_before}
    assert protected_after == protected_before
    for p, entry in source_snapshot.items():
        assert fingerprint(ROOT / p)['sha256'] == entry['sha256']
    checks = model_tests()
    report = {'owner': OWNER, 'purpose': 'isolated ABI/link/encoder/finite-stream-model only; never flash',
              'versions': versions, 'commands': COMMANDS,
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'layout_fields': ['state', 'pair_slot', 'pending_source', 'frozen_fields', 'frozen_reservation',
                  'transaction_fields', 'transaction_reservation', 'sha_offset', 'state_alignment',
                  'pending_offset', 'frozen_offset', 'transaction_offset', 'encoder_offset', 'owner_offset'],
              'layout_values': layout,
              'new_ccm_actual': layout[0], 'new_ccm_budget': 2048, 'new_main_sram': 0,
              'remaining_ccm_after_actual': 2632 - layout[0], 'remaining_ccm_after_budget': 2632 - 2048,
              'function_frames': (OUT / 'layout.su').read_text(encoding='utf-8'),
              'stream_checks': checks, 'calculations': calculations(),
              'protected_before': protected_before, 'protected_after': protected_after,
              'production_readiness': 'NOT_PROVEN_SOURCE_TIME_IDENTITY_CANONICAL_INFO_OWNERSHIP_STACK_WCET',
              'not_implemented': ['source taps/acquisition', 'canonical INFO/SHA', 'RTOS/ISR cross-owner synchronization',
                  'UART/HAL integration', 'new firmware generation', 'whole-firmware linking/stack/power10',
                  'GUI/live serial integration', 'APPLY/SAVE/UPLOAD'],
              'cleanup_authorized': False}
    (OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    inventory = {'owner': OWNER, 'purpose': report['purpose'], 'cleanup_authorized': False,
                 'files': [{'path': str(p.relative_to(ROOT)), **fingerprint(p)} for p in sorted(OUT.iterdir()) if p.is_file()]}
    (OUT / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    print(json.dumps({'ccm_actual': layout[0], 'main_new': 0, 'ccm_remaining': 2632 - layout[0],
                      'model_checks': len(checks), 'encoder': 'exact 438-byte golden PASS',
                      'production_readiness': report['production_readiness']}))


if __name__ == '__main__':
    main()
