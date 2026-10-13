"""Bounded read-only grouped diagnostics; no arbitrary variables or commands."""
from dataclasses import dataclass
import re
import time
from services.file_service_client import FileServiceError, FileServiceResult, _uint

MAX_ENTRIES = 16
KNOWN_STATES = {'OBSERVED', 'WAIT', 'BUSY', 'FAULT', 'UNKNOWN'}


@dataclass(frozen=True)
class DiagnosticEntry:
    id: str
    group: str
    name: str
    state: str
    reason: str
    source: str
    age_ms: int | None
    received_ns: int
    fields: dict[str, str]


def DiagnosticEntry_Parse(fields):
    for key, limit in (('id', 64), ('group', 24), ('name', 64), ('state', 32), ('reason', 96), ('source', 64)):
        if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,' + str(limit) + '}', fields.get(key, '')):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, f'Invalid diagnostic {key}')
    if fields.get('readonly') != '1' or fields.get('version') != '1':
        raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Unsupported diagnostic schema/access')
    age = _uint(fields, 'age_ms')
    optional = {}
    for key in ('counter', 'work_age_ms', 'data_age_ms', 'sequence', 'errors', 'syncs', 'progress_done', 'progress_total'):
        if key in fields:
            optional[key] = str(_uint(fields, key))
    for key in ('unit', 'block', 'warn', 'phase', 'mounted', 'open', 'healthy', 'started', 'quaternion_valid', 'velocity_valid', 'position_valid'):
        if key in fields:
            if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,48}', fields[key]):
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Invalid diagnostic value')
            optional[key] = fields[key]
    if 'progress_done' in optional or 'progress_total' in optional:
        if (not {'progress_done','progress_total'} <= optional.keys() or
                int(optional['progress_total']) == 0 or int(optional['progress_done']) > int(optional['progress_total'])):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Invalid finite progress')
    state = fields['state'] if fields['state'] in KNOWN_STATES else 'UNKNOWN'
    reason = fields['reason'] if state == fields['state'] else 'unknown_state_' + fields['state']
    return DiagnosticEntry(fields['id'], fields['group'], fields['name'], state, reason,
        fields['source'], None if age == 0xFFFFFFFF else age, time.monotonic_ns(), optional)


class RuntimeDiagnosticsClient:
    def __init__(self, transport, cancel):
        self.transport, self.cancel = transport, cancel
        self.caps = None
        self.cursor = 0
        self.entries = []
        self.next_cycle = 0.0
        self.interval = 1.0

    def _query(self, cursor=None):
        command = 'SYSTEM DIAG' + ('' if cursor is None else f' {cursor}')
        line = self.transport.exchange(command, 2.0, self.cancel).strip()
        prefix = 'OK SYSTEM DIAG '
        if not line.isascii() or len(line) > 511 or not line.startswith(prefix):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Runtime diagnostics unavailable: ' + line[:100])
        fields = {}
        for token in line[len(prefix):].split():
            key, sep, value = token.partition('=')
            if not sep or not key or not value or key in fields:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Malformed diagnostic fields')
            fields[key] = value
        if fields.get('version') != '1':
            raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Unsupported diagnostic version')
        return fields

    def step(self):
        """At most one bounded exchange. File-job admission occurs between pages."""
        if time.monotonic() < self.next_cycle:
            return None
        if self.caps is None:
            caps = self._query()
            if (caps.get('maintenance') != '0.1' or caps.get('compatible') != '0.0' or
                _uint(caps, 'max_entries', MAX_ENTRIES) < _uint(caps, 'entries', MAX_ENTRIES) or
                _uint(caps, 'max_line', 511) < 64):
                raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Unsupported diagnostic bounds/version')
            self.interval = max(1.0, min(60.0, _uint(caps, 'polling_ms', 60000) / 1000))
            self.caps = caps
            return None
        fields = self._query(self.cursor)
        if _uint(fields, 'end', 1):
            if _uint(fields, 'next_cursor') != 0 or len(self.entries) != int(self.caps['entries']):
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Incomplete diagnostic cycle')
            result = self.entries
            self.entries, self.cursor = [], 0
            self.next_cycle = time.monotonic() + self.interval
            return result
        entry = DiagnosticEntry_Parse(fields)
        next_cursor = _uint(fields, 'next_cursor', MAX_ENTRIES)
        if len(self.entries) >= int(self.caps['entries']) or next_cursor <= self.cursor or any(e.id == entry.id for e in self.entries):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Duplicate/unbounded diagnostic cycle')
        self.entries.append(entry)
        self.cursor = next_cursor
        return None


def LegacyDiagnostics_FromSnapshot(snapshot):
    """Known legacy fields only; no claim of firmware-advertised entries."""
    rows = [DiagnosticEntry('legacy.system', 'task', 'Legacy_system', 'OBSERVED', 'not_start_authorization',
        'SYSTEM_STATUS', None, snapshot.received_ns, {'phase':str(snapshot.lifecycle),'block':f'0x{snapshot.blocking_mask:08X}','warn':f'0x{snapshot.warning_mask:08X}'}),
        DiagnosticEntry('legacy.thread', 'thread', 'Thread_work_health', 'UNKNOWN', 'completion_not_exported',
        'maintenance_0.0', None, snapshot.received_ns, {})]
    if snapshot.storage is not None:
        log = snapshot.storage
        rows.append(DiagnosticEntry('legacy.storage', 'storage', 'Legacy_TF', 'OBSERVED', 'write_attempts_not_completion',
            'LOG_STATUS', None, log.received_ns, {'mounted':str(int(log.mounted)),'open':str(int(log.writer_open)),
            'healthy':str(int(log.healthy)), 'counter':str(log.writes),'unit':'write_attempts','syncs':str(log.syncs),'errors':str(log.errors)}))
    return rows
