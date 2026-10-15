"""Local JSON CLI; no listening service. python swd_cli.py --help"""
import argparse
from dataclasses import asdict
from enum import Enum
import json
import time
from threading import Event

from transport.probe_inventory import ProbeInventory_Read, ProbeInventoryResult
from transport.swd_session import SwdSession, SwdReply, SwdResult


def _JsonValue(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(type(value).__name__)


def SwdCli_Run(argv=None, *, _inventory=ProbeInventory_Read, _session=SwdSession):
    parser = argparse.ArgumentParser(description='Bounded SWD read-only JSON API; Horco CMSIS-DAPv2 / pyOCD 0.45.1')
    parser.add_argument('operation', choices=('inventory', 'targets', 'inspect', 'catalog', 'snapshot', 'read', 'diagnostics', 'watch', 'summary'))
    parser.add_argument('--probe', help='Exact USB identity from inventory; never selects the first probe')
    parser.add_argument('--address', type=lambda value: int(value, 0))
    parser.add_argument('--length', type=int)
    parser.add_argument('--target', help='Explicit target from targets; descriptor provides its target automatically')
    parser.add_argument('--elf')
    parser.add_argument('--descriptor')
    parser.add_argument('--watch', action='append', default=[], help='Exact ID from the offline ELF catalog; repeat up to 16')
    args = parser.parse_args(argv)
    offline = args.operation in ('inventory','targets','inspect','catalog')
    if args.watch and args.operation not in ('watch','summary'):
        parser.error('--watch is only valid for watch/summary')
    if not offline and not args.probe:
        parser.error('--probe is required')
    if args.operation == 'read' and (args.address is None or args.length is None):
        parser.error('read requires --address and --length')
    if args.operation != 'read' and (args.address is not None or args.length is not None):
        parser.error('--address and --length are only valid for read')
    firmware = None
    if args.operation == 'targets':
        from transport.swd_firmware import Targets_List
        print(json.dumps(dict(targets=Targets_List(),capability='single-core little-endian ADIv5/AP0 internal-memory reads',
                              hardware_verified='Horco + F407 only'),ensure_ascii=False))
        return 0
    if args.elf or args.descriptor:
        from transport.swd_firmware import Firmware_Import, DiagnosticResult
        imported = Firmware_Import([p for p in (args.descriptor,args.elf) if p],target=args.target)
        if imported.result != DiagnosticResult.Ok:
            print(json.dumps(dict(result=imported.result.value,detail=imported.detail)))
            return 2
        firmware = imported.firmware
    if args.operation in ('inspect','catalog','diagnostics','watch','summary') and firmware is None:
        parser.error('This operation requires --descriptor or --elf with --target')
    if args.operation in ('watch','summary'):
        available={item.id for item in firmware.watches if not item.unavailable}
        if len(args.watch)>16 or len(set(args.watch))!=len(args.watch) or any(item not in available for item in args.watch):
            parser.error('Select at most 16 unique available IDs from catalog; no address expressions')
        if args.operation=='watch' and not args.watch:
            parser.error('watch requires at least one --watch catalog ID')
    if args.operation == 'catalog':
        print(json.dumps(dict(format='silverstar.swd-watch-catalog',version=1,elf_sha256=firmware.sha256,
            target=firmware.target.name,firmware_status='unmatched',dwarf=firmware.dwarf,
            reason='' if firmware.dwarf else 'DWARF unavailable; variable types cannot be inferred',
            entries=[asdict(item) for item in firmware.watches]),ensure_ascii=False))
        return 0
    if args.operation == 'inspect':
        print(json.dumps(dict(result='ok',firmware=firmware.descriptor,dwarf=firmware.dwarf,
                              target_status='selected_not_connected',firmware_status='unmatched'),ensure_ascii=False))
        return 0
    inventory = _inventory(Event())
    if args.operation == 'inventory':
        print(json.dumps(asdict(inventory), default=_JsonValue, ensure_ascii=False))
        return 0 if inventory.result in (ProbeInventoryResult.Ready, ProbeInventoryResult.Empty) else 2
    matches = [probe for probe in inventory.probes if probe.identity == args.probe]
    if inventory.result != ProbeInventoryResult.Ready or len(matches) != 1:
        reply = SwdReply(SwdResult.InvalidRequest, 'Exact probe identity is absent or ambiguous; refresh inventory')
        print(json.dumps(asdict(reply), default=_JsonValue))
        return 2
    options = {}
    if args.target: options['target'] = args.target
    if firmware: options['firmware'] = firmware
    session = _session(**options)
    try:
        reply = session.Swd_Attach(matches[0])
        if reply.result == SwdResult.Ok and args.operation == 'read':
            time.sleep(.1)  # Respect the API rate limit after the identity sample.
            reply = session.Swd_ReadMemory(args.address, args.length)
        if reply.result == SwdResult.Ok and args.operation in ('diagnostics','watch','summary'):
            time.sleep(.1)
            reply = session.Swd_VerifyFirmware()
            if reply.result == SwdResult.Ok:
                time.sleep(1.0 if args.operation == 'watch' or args.watch else .1)
                reply = (session.Swd_ReadWatches(args.watch) if args.operation == 'watch' else
                         session.Swd_Inspect(args.watch) if args.operation == 'summary' else session.Swd_Diagnostics())
    finally:
        released = session.Swd_Detach()
    from services.swd_summary import Snapshot_Document
    output = Snapshot_Document(reply)
    output['release'] = asdict(released)
    if reply.snapshot:
        output['snapshot']['age_ms'] = reply.snapshot.age_ms
    if reply.received_ns is not None:
        output['age_ms'] = max(0.0, (time.monotonic_ns()-reply.received_ns)/1e6)
    print(json.dumps(output, default=_JsonValue, ensure_ascii=False))
    return 0 if reply.result == released.result == SwdResult.Ok else 2


if __name__ == '__main__':
    raise SystemExit(SwdCli_Run())
