"""Authorized bench: exact Horco, two bounded read-only sessions, no run control."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).absolute().parents[2]
task = Path(__file__).absolute().parent
if len(sys.argv) > 1:
    assert sys.argv[1] in ('bench02','cli03')
    task = task/sys.argv[1]
    task.mkdir(exist_ok=False)
sys.path.insert(0, str(root/'apps/GSHC'))
from transport.probe_inventory import ProbeInventory_Read, ProbeInventoryResult
from transport.swd_session import SwdSession, SwdResult, SwdError
from transport import _swd_pyocd as adapter
from threading import Event


def json_value(value):
    if isinstance(value, bytes): return value.hex()
    return value.value


def save(name, value):
    (task/name).write_text(json.dumps(value, default=json_value, indent=2), encoding='utf-8')


def check_packet(data, select):
    # Explicitly exclude DAP_ResetTarget and DAP_SWJ_Pins (NRST). Only the
    # commands used by this audited path are allowed. SWJ sequence resets the
    # wire protocol, not the CPU. All AP writes must address CSW/TAR on AP0.
    command = data[0]
    if command not in (0, 1, 2, 3, 4, 5, 6, 0x11, 0x12, 0x13):
        raise SwdError(SwdResult.SafetyNotProven, f'Unexpected CMSIS-DAP command {command:#x}')
    def check_write(request, value, current):
        register = request & 0xC
        if request & 1:
            if current >> 24 or (current & 0xF0 | register) not in (0, 4):
                raise SwdError(SwdResult.SafetyNotProven, 'Target-data/AP control write forbidden')
        elif register == 8:
            if value >> 24: raise SwdError(SwdResult.SafetyNotProven, 'Only AP0 permitted')
            current = value
        elif register not in (0, 4) or register == 4 and value & 0x04000000:
            raise SwdError(SwdResult.SafetyNotProven, 'Unexpected DP write/debug reset request')
        return current
    if command == 6:
        request = data[4]
        if request & 0xF0:
            raise SwdError(SwdResult.SafetyNotProven, 'Unexpected block transfer flags')
        if not request & 2:
            for index in range(data[2] | data[3] << 8):
                value = int.from_bytes(bytes(data[5+index*4:9+index*4]), 'little')
                select = check_write(request, value, select)
    if command == 5:
        cursor = 3
        for _ in range(data[2]):
            request = data[cursor]; cursor += 1
            if request & 0xF0:
                raise SwdError(SwdResult.SafetyNotProven, 'Unexpected transfer flags')
            if request & 2: continue
            value = int.from_bytes(bytes(data[cursor:cursor+4]), 'little'); cursor += 4
            select = check_write(request, value, select)
    return select


def main():
    names = ['openocd.exe','pyocd.exe','ST-LINK_gdbserver.exe','STM32_Programmer_CLI.exe',
        'STM32CubeProgrammer.exe','JLink.exe','JLinkGDBServer.exe','JLinkGDBServerCL.exe',
        'Ozone.exe','UV4.exe','gdb.exe','arm-none-eabi-gdb.exe']
    ps = "$names=@(" + ','.join("'"+name+"'" for name in names) + "); @(Get-CimInstance Win32_Process | Where-Object { $names -contains $_.Name } | Select-Object Name,ProcessId) | ConvertTo-Json -Compress"
    check = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],
        capture_output=True,text=True,timeout=20)
    save('bench_process_check.json', {'checked_utc':datetime.now(timezone.utc).isoformat(),
        'names':names,'exit':check.returncode,'stdout':check.stdout,'stderr':check.stderr})
    if check.returncode or check.stdout.strip() not in ('','[]','null'):
        raise SystemExit('Common debugger process present/inspection failed: no USB open')
    inventory = ProbeInventory_Read(Event())
    save('bench_inventory.json', asdict(inventory))
    identity = r'USB\VID_FAED&PID_4870\132765403520'
    matches = [p for p in inventory.probes if p.identity == identity]
    if inventory.result != ProbeInventoryResult.Ready or len(matches) != 1 or matches[0].host_status != 'OK':
        raise SystemExit('Specified connected Horco absent/ambiguous/unhealthy: no USB open')
    source = ['apps/GSHC/transport/_swd_pyocd.py','apps/GSHC/transport/swd_session.py','apps/GSHC/swd_cli.py']
    save('bench_sources.json', {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source})
    original = adapter._BulkInterface
    packet_log = (task/'bench_packets.jsonl').open('x', encoding='utf-8')
    def audited(api, device, guard):
        interface = original(api, device, guard)
        write = interface.write
        select = 0
        def checked_write(data):
            nonlocal select
            row = {'utc':datetime.now(timezone.utc).isoformat(), 'tx':bytes(data).hex()}
            try:
                select = check_packet(data, select)
                row['allowed'] = True
            except Exception as exc:
                row.update(allowed=False, reason=str(exc))
                packet_log.write(json.dumps(row)+'\n'); packet_log.flush()
                raise
            packet_log.write(json.dumps(row)+'\n')
            packet_log.flush()
            return write(data)
        interface.write = checked_write
        return interface
    adapter._BulkInterface = audited
    results = []
    try:
        if task.name == 'cli03':
            from swd_cli import SwdCli_Run
            return SwdCli_Run(['read','--probe',identity,'--address','0x20000000','--length','16'])
        for cycle in range(2):
            session = SwdSession()
            record = {'cycle':cycle,'utc':datetime.now(timezone.utc).isoformat()}
            try:
                reply = session.Swd_Attach(matches[0])
                record['attach'] = asdict(reply)
                if reply.result == SwdResult.Ok:
                    backend = session._backend
                    record['backend'] = {'pyocd':'0.45.1', 'interface':'CMSIS-DAPv2 bulk MI00',
                        'protocol_version':backend._link.protocol_version,
                        'firmware_version':backend._link.firmware_version,
                        'dpidr':backend._ap.dp.dpidr.idr, 'ap_idr':backend._ap.idr,
                        'clock_hz':1000000, 'board_constructed':backend._session.board is not None}
                if reply.result == SwdResult.Ok and cycle == 0:
                    time.sleep(.12)
                    record['ram'] = asdict(session.Swd_ReadMemory(0x20000000, 16))
                    if record['ram']['result'] == SwdResult.Ok:
                        time.sleep(.12)
                        record['after_read'] = asdict(session.Swd_Snapshot())
            finally:
                record['release'] = asdict(session.Swd_Detach())
                record['library_owner_released'] = not adapter._LibraryOwner.locked()
                results.append(record)
                save('bench_result.json', results)
            print(json.dumps(record, default=json_value), flush=True)
            if any(item['result'] != SwdResult.Ok for item in record.values() if isinstance(item,dict) and 'result' in item):
                return 2  # No retry/takeover after a failed hardware operation.
        return 0
    finally:
        packet_log.close()
        adapter._BulkInterface = original


if __name__ == '__main__':
    raise SystemExit(main())
