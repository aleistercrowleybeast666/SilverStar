"""Read host PnP metadata only. Never open USB interfaces, COM ports or a target."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Lock
import time


class ProbeInventoryResult(Enum):
    Ready = 'ready'
    Empty = 'empty'
    MissingDependency = 'missing_dependency'
    Failed = 'failed'
    Cancelled = 'cancelled'


@dataclass(frozen=True)
class HostProbe:
    identity: str
    name: str
    family: str
    usb_id: str
    serial: str
    identity_kind: str
    interfaces: tuple[str, ...]
    host_status: str

    @property
    def label(self):
        return f'{self.name} | {self.usb_id} | {self.serial or self.identity}'


@dataclass(frozen=True)
class ProbeInventory:
    result: ProbeInventoryResult
    probes: tuple[HostProbe, ...] = ()
    detail: str = ''


# Fixed script, no returned device strings are ever evaluated as commands.
_PNP_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    if (!(Get-Command Get-CimInstance -ErrorAction SilentlyContinue) -or
        !(Get-Command Invoke-CimMethod -ErrorAction SilentlyContinue)) {
        @{state='missing_dependency'; detail='Windows CIM cmdlets unavailable'} | ConvertTo-Json -Compress
        exit 0
    }
    $nodes = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter "(PNPDeviceID LIKE 'USB%' OR PNPDeviceID LIKE 'HID%') AND Present = TRUE")
    if ($nodes.Count -gt 512) { throw 'PnP inventory exceeds the 512-node limit' }
    $rows = @($nodes | ForEach-Object {
        $device = $_
        $props = Invoke-CimMethod -InputObject $device -MethodName GetDeviceProperties -Arguments @{devicePropertyKeys=@('DEVPKEY_Device_Parent','DEVPKEY_Device_BusReportedDeviceDesc')}
        if ($props.ReturnValue -ne 0) { throw 'Cannot read PnP identity properties; retry inventory' }
        $values = @{}
        foreach ($prop in $props.deviceProperties) { if ($prop.Type -eq 18) { $values[$prop.KeyName] = [string]$prop.Data } }
        @{id=[string]$device.PNPDeviceID; name=[string]$device.Name; class=[string]$device.PNPClass;
          status=[string]$device.Status; parent=$values['DEVPKEY_Device_Parent'];
          description=$values['DEVPKEY_Device_BusReportedDeviceDesc'];
          service=[string]$device.Service}
    })
    @{state='ready'; nodes=$rows} | ConvertTo-Json -Compress -Depth 4
} catch {
    @{state='failed'; detail=$_.Exception.Message} | ConvertTo-Json -Compress
}
'''


def _text(value, limit=512):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid host PnP text')
    return value.strip()


def ProbeInventory_Parse(document) -> ProbeInventory:
    if not isinstance(document, dict):
        raise ValueError('Invalid host inventory document')
    if document.get('state') in ('failed', 'missing_dependency'):
        return ProbeInventory(ProbeInventoryResult(document['state']), detail=_text(document.get('detail')))
    nodes = document.get('nodes')
    if document.get('state') != 'ready' or not isinstance(nodes, list) or len(nodes) > 512:
        raise ValueError('Invalid or unbounded PnP inventory')
    records = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError('Invalid PnP node')
        record = {key: _text(node.get(key)) for key in ('id','name','class','status','parent','description','service')}
        key = record['id'].upper()
        if not key or key in records:
            raise ValueError('Missing or duplicate PnP identity')
        records[key] = record
    groups = {}
    for key, node in records.items():
        # A VCP alone is never a debug probe interface.
        if node['class'].lower() == 'ports':
            continue
        name = node['description'] or node['name']
        family = next((label for pattern,label in ((r'cmsis[- _]?dap|daplink','CMSIS-DAP'),
            (r'st[- _]?link','ST-Link'), (r'j[- _]?link','J-Link'))
            if re.search(pattern, node['name']+' '+node['description'], re.I)), None)
        if family is None:
            continue
        physical = key
        seen = set()
        for _ in range(8):
            if physical in seen:
                raise ValueError('Cyclic PnP parent identity')
            seen.add(physical)
            if physical.startswith('USB\\VID_') and '&MI_' not in physical:
                break
            parent = records[physical]['parent'].upper()
            if parent not in records:
                break
            physical = parent
        if not physical.startswith('USB\\VID_') or '&MI_' in physical:
            raise ValueError('Incomplete probe parent identity; retry inventory')
        usb = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', physical)
        if not usb:
            continue
        identity = physical
        serial = physical.rsplit('\\',1)[-1] if '&MI_' not in physical else ''
        kind = 'USB serial' if serial and '&' not in serial else 'USB instance/location'
        # Group composite HID/WinUSB interfaces by their actual OS parent.
        group = groups.setdefault(identity, dict(name=name, family=family, usb_id=usb[1]+':'+usb[2],
            serial=serial, kind=kind, interfaces=set(), statuses=set()))
        group['interfaces'].add(f"{node['class']} / {node['service'] or '?'} / {key}")
        group['statuses'].add(node['status'] or 'Unknown')
    if len(groups) > 32:
        raise ValueError('Probe count exceeds the 32-probe limit')
    probes = tuple(HostProbe(key, value['name'], value['family'], value['usb_id'], value['serial'],
        value['kind'], tuple(sorted(value['interfaces'])), ', '.join(sorted(value['statuses'])))
        for key,value in sorted(groups.items()))
    return ProbeInventory(ProbeInventoryResult.Ready if probes else ProbeInventoryResult.Empty, probes)


_Inventory_Lock = Lock()
_Inventory_PendingProcess = None


def _ProbeHelper_Stop(process):
    """Only reap our helper, with a finite cleanup budget and no pipe drain."""
    try:
        if process.poll() is not None:
            return True
        process.kill()
        process.wait(timeout=1.0)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ProbeInventory_Query(cancel, executable, timeout):
    global _Inventory_PendingProcess
    if _Inventory_PendingProcess is not None:
        if _Inventory_PendingProcess.poll() is None:
            return ProbeInventory(ProbeInventoryResult.Failed, detail='Previous host inventory helper is still exiting; retry later')
        _Inventory_PendingProcess = None
    command = [executable,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',
        base64.b64encode(_PNP_SCRIPT.encode('utf-16le')).decode('ascii')]
    deadline = time.monotonic() + timeout
    # Files avoid communicate()'s pipe-reader threads and unbounded drain after
    # kill. Read only after exit and cap the bytes admitted to the JSON parser.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while True:
                if cancel.is_set():
                    return ProbeInventory(ProbeInventoryResult.Cancelled)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ProbeInventory(ProbeInventoryResult.Failed, detail='Host enumeration timed out; retry is available')
                if process.poll() is not None:
                    break
                cancel.wait(min(0.1, remaining))
            output.seek(0); errors.seek(0)
            stdout, stderr = output.read(1024*1024+1), errors.read(300)
            if cancel.is_set():
                return ProbeInventory(ProbeInventoryResult.Cancelled)
            if process.returncode or len(stdout) > 1024*1024:
                return ProbeInventory(ProbeInventoryResult.Failed, detail='Host enumeration failed: '+stderr.decode('utf-8',errors='replace'))
            return ProbeInventory_Parse(json.loads(stdout.decode('utf-8-sig')))
        finally:
            if not _ProbeHelper_Stop(process):
                # Do not accumulate helpers if the OS has not confirmed exit.
                _Inventory_PendingProcess = process


def ProbeInventory_Read(cancel, *, timeout=20.0) -> ProbeInventory:
    if cancel.is_set():
        return ProbeInventory(ProbeInventoryResult.Cancelled)
    executable = (shutil.which('pwsh.exe') or shutil.which('powershell.exe')) if sys.platform == 'win32' else None
    if not executable:
        return ProbeInventory(ProbeInventoryResult.MissingDependency, detail='Windows PowerShell/CIM is required; no driver or package was installed')
    if not _Inventory_Lock.acquire(blocking=False):
        return ProbeInventory(ProbeInventoryResult.Failed, detail='Host inventory is already running')
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError('Host enumeration requires a finite nonnegative timeout')
        return _ProbeInventory_Query(cancel, executable, timeout)
    except (OSError, TypeError, ValueError) as exc:
        return ProbeInventory(ProbeInventoryResult.Failed, detail=str(exc)[:300])
    finally:
        _Inventory_Lock.release()


class ProbeSelection:
    def __init__(self):
        self.probes = ()
        self.identity = ''
        self.require_choice = False

    def apply(self, inventory):
        probes = inventory.probes if inventory.result == ProbeInventoryResult.Ready else ()
        lost = bool(self.identity and self.identity not in {p.identity for p in probes})
        if lost:
            self.identity, self.require_choice = '', True
        self.probes = probes
        if len(probes) == 1 and not self.identity and not self.require_choice:
            self.identity = probes[0].identity
        return lost

    def select(self, identity):
        if identity and identity not in {p.identity for p in self.probes}:
            return False
        self.identity = identity
        self.require_choice = not bool(identity)
        return True
