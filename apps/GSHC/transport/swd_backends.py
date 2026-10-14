"""Fixed read-only backend selection; no plugins, scripts or debugger commands."""
from enum import Enum
import re
from typing import Protocol
from transport.probe_inventory import HostProbe
from transport.swd_session import SwdError, SwdResult as R


class SwdBackendKind(Enum):
    CmsisDap = 'cmsis-dap'
    Stlink = 'stlink-experimental'
    OpenOcd = 'openocd-disabled'


# Exact installed pyOCD 0.45.1 USB map; excludes V1 and DFU personalities.
STLINK_PIDS = (0x3748, 0x374A, 0x374B, 0x374E, 0x374F,
               0x3752, 0x3753, 0x3754, 0x3755, 0x3757)


class ReadOnlyMemoryBackend(Protocol):
    def configure(self, profile): ...
    def open(self, selected): ...
    def read(self, address: int, length: int) -> bytes: ...
    def close(self): ...


def ProbeKind_Get(probe):
    if not isinstance(probe, HostProbe) or not probe.identity or len(probe.identity) > 512:
        raise SwdError(R.InvalidRequest, 'An explicit host probe identity is required')
    if probe.identity_kind != 'USB serial' or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', probe.serial):
        raise SwdError(R.Unsupported, 'A stable USB serial identity is required')
    usb = probe.usb_id.upper()
    if not re.fullmatch(r'[0-9A-F]{4}:[0-9A-F]{4}', usb):
        raise SwdError(R.InvalidRequest, 'Invalid USB VID/PID')
    vid, pid = (int(x,16) for x in usb.split(':'))
    if probe.family == 'CMSIS-DAP' and (vid,pid) == (0xFAED,0x4870):
        kind = SwdBackendKind.CmsisDap
    elif probe.family == 'ST-Link' and vid == 0x0483 and pid in STLINK_PIDS:
        kind = SwdBackendKind.Stlink
    else:
        raise SwdError(R.Unsupported, 'No reviewed read-only backend for this probe; OpenOCD/config scripts remain disabled')
    expected = rf'USB\VID_{vid:04X}&PID_{pid:04X}\{probe.serial}'
    if probe.identity.upper() != expected.upper():
        raise SwdError(R.InvalidRequest, 'Probe serial does not match selected USB identity')
    return kind


def ProbeBackend_Create(probe, cancel):
    kind = ProbeKind_Get(probe)
    if kind == SwdBackendKind.CmsisDap:
        from transport._swd_pyocd import PyOcdMemAp
        return PyOcdMemAp(cancel)
    if kind == SwdBackendKind.Stlink:
        from transport._swd_stlink import StlinkMemAp
        return StlinkMemAp(cancel)
    raise SwdError(R.SafetyNotProven, 'OpenOCD is reserved and disabled; no configuration is executed')
