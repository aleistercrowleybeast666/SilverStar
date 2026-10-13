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
    parser = argparse.ArgumentParser(description='Bounded SWD read-only JSON API; live admission may be blocked')
    parser.add_argument('operation', choices=('inventory', 'snapshot', 'read'))
    parser.add_argument('--probe', help='Exact USB identity from inventory; never selects the first probe')
    parser.add_argument('--address', type=lambda value: int(value, 0))
    parser.add_argument('--length', type=int)
    args = parser.parse_args(argv)
    if args.operation != 'inventory' and not args.probe:
        parser.error('--probe is required')
    if args.operation == 'read' and (args.address is None or args.length is None):
        parser.error('read requires --address and --length')
    if args.operation != 'read' and (args.address is not None or args.length is not None):
        parser.error('--address and --length are only valid for read')
    inventory = _inventory(Event())
    if args.operation == 'inventory':
        print(json.dumps(asdict(inventory), default=_JsonValue, ensure_ascii=False))
        return 0 if inventory.result in (ProbeInventoryResult.Ready, ProbeInventoryResult.Empty) else 2
    matches = [probe for probe in inventory.probes if probe.identity == args.probe]
    if inventory.result != ProbeInventoryResult.Ready or len(matches) != 1:
        reply = SwdReply(SwdResult.InvalidRequest, 'Exact probe identity is absent or ambiguous; refresh inventory')
        print(json.dumps(asdict(reply), default=_JsonValue))
        return 2
    session = _session()
    try:
        reply = session.Swd_Attach(matches[0])
        if reply.result == SwdResult.Ok and args.operation == 'read':
            time.sleep(.1)  # Respect the API rate limit after the identity sample.
            reply = session.Swd_ReadMemory(args.address, args.length)
    finally:
        released = session.Swd_Detach()
    output = asdict(reply)
    output['release'] = asdict(released)
    if reply.snapshot:
        output['snapshot']['age_ms'] = reply.snapshot.age_ms
    if reply.received_ns is not None:
        output['age_ms'] = max(0.0, (time.monotonic_ns()-reply.received_ns)/1e6)
    print(json.dumps(output, default=_JsonValue, ensure_ascii=False))
    return 0 if reply.result == released.result == SwdResult.Ok else 2


if __name__ == '__main__':
    raise SystemExit(SwdCli_Run())
