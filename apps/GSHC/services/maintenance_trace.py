"""Bounded append-only maintenance diagnostics, written by the serial owner.

Raw head and tail are diagnostic samples, not a complete recording. Existing
traces are never removed; reaching the directory quota disables new recording.
"""
from collections import deque
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4

_logger = logging.getLogger(__name__)


class MaintenanceTrace:
    def __init__(self, directory, port, baud, *, limit=262144):
        self.path = None
        self.error = ''
        self._stream = None
        self._limit = max(32768, min(262144, limit))
        self._written = self._raw_bytes = 0
        self._raw_records = 0
        self._started = self._flushed = time.monotonic()
        self._sampled = {}
        self._tail = deque(maxlen=8)
        self._last_exchanges = deque(maxlen=8)
        self._critical_tail = deque(maxlen=4)
        self._pending = deque(maxlen=32)
        self._pending_lock = Lock()
        self._accepting = True
        self._pending_dropped = self.critical_dropped = self.sampled_exchanges = 0
        self._status_signature = None
        self._priority_reserve = min(16384, self._limit//4)
        self.rx_bytes = self.tx_bytes = self.exchanges = 0
        self.truncated = False
        try:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            size = count = 0
            for entry in directory.glob('maintenance_*.jsonl'):
                size += entry.stat().st_size
                count += 1
                if size + self._limit > 8*1024*1024 or count >= 256:
                    raise OSError('Maintenance trace directory quota reached; existing evidence retained')
            path = directory/('maintenance_'+time.strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:12]+'.jsonl')
            self._stream = path.open('xb')
            self.path = path
            self.event('opened', port=port, baud=baud, raw_head_limit=32768, raw_head_records=256,
                       file_limit=self._limit, directory_limit=8*1024*1024)
        except OSError as exc:
            self._disable(exc)

    def _disable(self, exc):
        self.error = str(exc)
        _logger.warning('Maintenance diagnostics unavailable: %s', exc)
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass

    def Event_Post(self, kind, **fields):
        """Queue bounded GUI diagnostics; only the owner drains/writes them."""
        with self._pending_lock:
            if not self._accepting or self._stream is None:
                return False
            if len(self._pending) == self._pending.maxlen:
                self._pending_dropped += 1
            self._pending.append((kind, dict(requested_utc=datetime.now(timezone.utc).isoformat(), **fields)))
        return True

    def Pending_Flush(self):
        with self._pending_lock:
            pending = tuple(self._pending)
            self._pending.clear()
            dropped, self._pending_dropped = self._pending_dropped, 0
        if dropped:
            self.event('diagnostic_queue_overflow', dropped=dropped)
        for kind, fields in pending:
            self.event(kind, **fields)

    @staticmethod
    def _Critical_Summarize(row):
        keys = ('kind', 'utc', 'requested_utc', 'reason', 'request_sent', 'operation',
                'error', 'command', 'response', 'expected_uart_sha256', 'current_uart_sha256', 'dropped')
        return {key: value[:256] if isinstance(value, str) else value
                for key, value in row.items() if key in keys}

    def event(self, kind, *, final=False, **fields):
        if self._stream is None:
            return
        row = dict(kind=kind, elapsed_s=time.monotonic()-self._started,
                   utc=datetime.now(timezone.utc).isoformat(), **fields)
        critical = (kind in {'local_rejected', 'job_failed', 'owner_failed', 'diagnostic_queue_overflow'}
                    or bool(fields.get('error')) or str(fields.get('response', '')).startswith('ERR '))
        if critical:
            self._critical_tail.append(self._Critical_Summarize(row))
        payload = (json.dumps(row, ensure_ascii=False)+'\n').encode('utf-8')
        bound = self._limit if final else self._limit-16384-(0 if critical else self._priority_reserve)
        if final:
            # Keep the terminal counters even when Unicode tails need more bytes.
            for key in ('raw_tail', 'last_exchanges', 'critical_tail'):
                while self._written+len(payload) > bound and row.get(key):
                    row[key].pop(0)
                    row['terminal_tail_trimmed'] = row.get('terminal_tail_trimmed', 0)+1
                    payload = (json.dumps(row, ensure_ascii=False)+'\n').encode('utf-8')
        if self._written+len(payload) > bound:
            self.truncated = True
            if critical:self.critical_dropped += 1
            return
        try:
            if self._stream.write(payload) != len(payload):
                raise OSError('Incomplete maintenance diagnostic write')
            self._written += len(payload)
            if final or critical or time.monotonic()-self._flushed >= 1:
                self._stream.flush()
                self._flushed = time.monotonic()
        except OSError as exc:
            self._disable(exc)

    def raw(self, direction, payload):
        if direction == 'rx':
            self.rx_bytes += len(payload)
        else:
            self.tx_bytes += len(payload)
        self._tail.append(dict(direction=direction, bytes=len(payload), hex=payload[-128:].hex()))
        remaining = max(0,32768-self._raw_bytes)
        if remaining and self._raw_records<256:
            sample = payload[:remaining]
            self._raw_bytes += len(sample)
            self._raw_records += 1
            self.event('raw', direction=direction, bytes=len(payload), hex=sample.hex())

    def exchange(self, command, response, seconds, error=''):
        self.exchanges += 1
        self._last_exchanges.append(dict(command=command[:191],response=response[:511],
                                         seconds=seconds,error=error[:256]))
        key = 'pending' if response.startswith('PENDING ') else 'read' if command.startswith('LOGFILE READ ') else ''
        interval = 1
        changed = False
        if command == 'LOGFILE STATUS' and response.startswith('OK LOGFILE STATUS '):
            values = dict(word.split('=', 1) for word in response.split() if '=' in word)
            signature = tuple(values.get(name) for name in ('lifecycle', 'storage_valid', 'mounted',
                'healthy', 'writer_open', 'log_fault', 'finalization', 'maintenance', 'cleanup_pending', 'reboot_required'))
            changed = signature != self._status_signature
            self._status_signature = signature
            key, interval = 'status', 5
        elif command.startswith('SYSTEM DIAG ') and response.startswith('OK SYSTEM DIAG '):
            key, interval = 'diagnostics', 10
        now = time.monotonic()
        sample_key = (key,response.split(' request_id=')[0] if key=='pending' else '')
        if key and not changed and not error and not response.startswith('ERR ') and now-self._sampled.get(sample_key,-1e9) < interval:
            self.sampled_exchanges += 1
            return
        if key:
            # Only fixed operation keys are retained, never one entry per file block.
            self._sampled[sample_key] = now
            if len(self._sampled)>16:
                self._sampled.clear()
        self.event('exchange', command=command[:191], response=response[:511], seconds=seconds,
                   error=error[:1024], rx_bytes=self.rx_bytes, tx_bytes=self.tx_bytes)

    def close(self, detail=''):
        with self._pending_lock:
            self._accepting = False
        self.Pending_Flush()
        self.event('closed', final=True, detail=detail[:1024], rx_bytes=self.rx_bytes,
                   tx_bytes=self.tx_bytes, exchanges=self.exchanges, truncated=self.truncated,
                   sampled_exchanges=self.sampled_exchanges, critical_dropped=self.critical_dropped,
                   critical_tail=list(self._critical_tail),
                   raw_head_truncated=self.rx_bytes+self.tx_bytes>self._raw_bytes,
                   raw_tail=list(self._tail),last_exchanges=list(self._last_exchanges))
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except OSError as exc:
                self._disable(exc)
