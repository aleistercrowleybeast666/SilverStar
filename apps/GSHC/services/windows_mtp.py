"""Windows Shell MTP copy with independent local readback verification.

The helper never moves/deletes files. Shell copy is asynchronous: cancellation
ends our wait, and explicitly does not claim a submitted remote copy stopped.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Event
import time


class MtpOperationResult(Enum):
    Available = 'available'
    Selected = 'selected'
    Verified = 'verified'
    Cancelled = 'cancelled'
    Unsupported = 'unsupported'
    Failed = 'failed'
    Uncertain = 'uncertain'


@dataclass(frozen=True)
class MtpReply:
    result: MtpOperationResult
    detail: str = ''
    destination: str = ''
    diagnostics: dict | None = None


def MtpDestination_Validate(value):
    if (not isinstance(value, str) or len(value) > 4096
            or not value.lower().startswith('::{20d04fe0-3aea-1069-a2d8-08002b30309d}')
            or '{6ac27878-a6fa-4155-ba85-f98f491d4f33}' not in value.lower()
            or any(ord(c) < 32 for c in value)):
        raise ValueError('Select a Windows Portable Devices (MTP) folder, not a filesystem/archive folder')
    return value


def _Hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


class WindowsMtp:
    FILE_LIMIT = 128
    BYTE_LIMIT = 512 * 1024 * 1024

    def __init__(self, runner=None):
        self._runner = runner or self._process

    def capability(self, cancel=None):
        return self._runner({'operation': 'capability'}, cancel or Event())

    def choose(self, title, cancel):
        reply = self._runner({'operation': 'choose', 'title': str(title)[:256]}, cancel)
        if reply.result is MtpOperationResult.Selected:
            try:
                MtpDestination_Validate(reply.destination)
            except ValueError as exc:
                return MtpReply(MtpOperationResult.Failed, str(exc))
        return reply

    def copy(self, package, destination, cancel):
        """Copy a verified DeviceExport package, then hash every returned file."""
        try:
            MtpDestination_Validate(destination)
            package = Path(package).absolute()
            if package.is_symlink() or not package.is_dir():
                raise ValueError('MTP staging package must be a regular directory')
            manifest_path = package / 'manifest.json'
            if manifest_path.is_symlink() or manifest_path.stat().st_size > 65536:
                raise ValueError('Invalid staging manifest')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('format') != 'silverstar.session-export':
                raise ValueError('MTP requires a verified session-export package')
            names = [row['path'] for row in manifest['files']]
            if not 1 <= len(names) <= self.FILE_LIMIT or len(set(names)) != len(names):
                raise ValueError('MTP supports between1 and128 distinct files')
            files = []
            for row in manifest['files']:
                name = row['path']
                if not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', name) is None or name in ('.', '..', 'manifest.json'):
                    raise ValueError('Invalid staging filename')
                path = package / name
                if path.is_symlink() or not path.is_file() or path.stat().st_size != row['size_bytes'] or _Hash(path) != row['sha256']:
                    raise ValueError('Staging file changed before MTP copy')
                files.append(dict(name=name, size=row['size_bytes'], sha256=row['sha256']))
            files.append(dict(name='manifest.json', size=manifest_path.stat().st_size, sha256=_Hash(manifest_path)))
            if sum(row['size'] for row in files) > self.BYTE_LIMIT:
                raise ValueError('MTP package exceeds512MiB bound')
            if re.fullmatch(r'SilverStar_export_[A-Za-z0-9_]{1,80}', package.name) is None:
                raise ValueError('Invalid unique export package name')
            readback = package / 'mtp_readback'
            if cancel.is_set():
                return MtpReply(MtpOperationResult.Cancelled, 'Cancelled; source files retained')
            readback.mkdir(exist_ok=False)
            reply = self._runner(dict(operation='copy', destination=destination,
                package=str(package), name=package.name, readback=str(readback), files=files), cancel)
            helper_result = reply.result.value
            if reply.result is MtpOperationResult.Verified:
                if cancel.is_set():
                    reply = MtpReply(MtpOperationResult.Uncertain,
                        'MTP wait cancelled; submitted copy may continue. Source files retained.',
                        diagnostics=reply.diagnostics)
                else:
                    try:
                        for row in files:
                            path = readback / row['name']
                            if (path.is_symlink() or not path.is_file()
                                    or path.stat().st_size != row['size'] or _Hash(path) != row['sha256']):
                                raise ValueError('MTP readback differs; remote copy is not verified')
                    except (OSError, ValueError) as exc:
                        reply = MtpReply(MtpOperationResult.Failed, str(exc), diagnostics=reply.diagnostics)
            # Retain the phase/HRESULT alongside this unique local staging
            # package, including the final independent local verification.
            with (package / 'mtp_result.json').open('x', encoding='utf-8') as stream:
                json.dump(dict(result=reply.result.value, detail=reply.detail,
                               helper_result=helper_result, diagnostics=reply.diagnostics,
                               destination=destination, source_files_retained=True), stream,
                          ensure_ascii=False, indent=2)
            if reply.result is not MtpOperationResult.Verified:
                return reply
            return MtpReply(MtpOperationResult.Verified, 'MTP copy and every-file SHA-256 readback verified; source files retained',
                            destination + '\\' + package.name, reply.diagnostics)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return MtpReply(MtpOperationResult.Failed, str(exc))

    def _process(self, request, cancel):
        if cancel.is_set():
            return MtpReply(MtpOperationResult.Cancelled, 'Cancelled before Windows MTP operation')
        if os.name != 'nt':
            return MtpReply(MtpOperationResult.Unsupported, 'Windows Shell MTP requires Windows')
        executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        if not executable.is_file():
            return MtpReply(MtpOperationResult.Unsupported, 'Windows PowerShell is unavailable')
        # Fixed application source only; user paths remain JSON data on stdin.
        # Retain the existing encoded-command launch; do not change machine
        # execution policy or require the user to enable unsigned script files.
        script = Path(__file__).with_suffix('.ps1').read_text(encoding='utf-8')
        adapter = Path(__file__).with_name('windows_mtp_copy.cs').read_text(encoding='utf-8')
        script = script.replace("Add-Type -Path (Join-Path $PSScriptRoot 'windows_mtp_copy.cs')",
                                "Add-Type -TypeDefinition @'\n" + adapter + "\n'@")
        source = script.encode('utf-8')
        if len(source) > 65536:
            return MtpReply(MtpOperationResult.Failed, 'Windows MTP helper command exceeds its bound')
        # The fixed trusted helper travels on a bounded first stdin line, so its
        # size does not hit CreateProcess's command-line limit. Only that line is
        # executable; user data remains the subsequent JSON consumed by the helper.
        loader = ('[ScriptBlock]::Create([Text.Encoding]::UTF8.GetString('
                  '[Convert]::FromBase64String([Console]::In.ReadLine()))).Invoke()')
        encoded = base64.b64encode(loader.encode('utf-16-le')).decode('ascii')
        command = [str(executable), '-NoProfile', '-NonInteractive', '-Sta', '-EncodedCommand', encoded]
        timeout = {'capability': 15, 'choose': 180, 'copy': 900}[request['operation']]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        data = base64.b64encode(source) + b'\n' + json.dumps(request, ensure_ascii=True).encode('ascii')
        deadline = time.monotonic() + timeout
        while True:
            if cancel.is_set() or time.monotonic() >= deadline:
                try:
                    process.kill()
                    process.communicate(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    return MtpReply(MtpOperationResult.Uncertain, 'MTP helper termination unconfirmed; submitted copy may continue. Source files retained.')
                result = MtpOperationResult.Uncertain if request['operation'] == 'copy' else MtpOperationResult.Cancelled
                return MtpReply(result, 'MTP wait cancelled/timed out; submitted remote copy may continue. Source files retained.')
            try:
                stdout, stderr = process.communicate(input=data, timeout=.1)
                break
            except subprocess.TimeoutExpired:
                data = None
            except OSError as exc:
                # A helper/pipe failure is not proof that the phone disconnected.
                try:
                    process.kill()
                    _, stderr = process.communicate(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    stderr = b''
                result = MtpOperationResult.Uncertain if request['operation'] == 'copy' else MtpOperationResult.Failed
                return MtpReply(result, 'Windows MTP helper IPC failed: ' + str(exc) +
                    '; ' + stderr.decode('utf-8', errors='replace')[-2000:] + '; source files retained')
        if len(stdout) > 65536 or len(stderr) > 65536 or process.returncode:
            return MtpReply(MtpOperationResult.Failed, 'Windows MTP helper failed: ' + stderr.decode('utf-8', errors='replace')[-2000:])
        try:
            raw = json.loads(stdout.decode('utf-8-sig'))
            diagnostics = raw.get('diagnostics')
            if diagnostics is not None and not isinstance(diagnostics, dict):
                raise ValueError('Invalid MTP diagnostics')
            return MtpReply(MtpOperationResult(raw['status']), str(raw.get('detail', ''))[:4096],
                            str(raw.get('destination', ''))[:4096], diagnostics)
        except (ValueError, KeyError, TypeError):
            return MtpReply(MtpOperationResult.Failed, 'Invalid Windows MTP helper response')
