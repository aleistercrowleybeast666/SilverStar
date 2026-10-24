"""Synthetic ordered UART faults; no device enumeration or real serial access."""
import json
import zlib
from threading import Event
from unittest.mock import patch

import pytest

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError, RemoteLog
from test_file_service_batch import BatchSerial, BatchTransport
from test_file_service_block import Frame
from transport.file_service_backend import FileServiceSerialTransport


class RecoverySerial(BatchSerial):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = BatchTransport(bytes(range(256)) * 25)
        self.fault = 'tail92'
        self.failed = 0
        self.batch_offsets = []
        self.nonces = []
        self.cancel_count = 0
        self.probe_count = 0
        self.metadata_cached = False
        self.late = b''
        self.on_cancel = lambda: None
        self.on_probe = lambda: None
        self.on_recovery = lambda: None
        self.fragment = 128

    def write(self, payload):
        self.writes.append(payload)
        command = payload.decode('ascii').strip()
        if command == 'LOGFILE CANCEL':
            self.cancel_count += 1
            self.metadata_cached = False  # Owning firmware LogFile_Abort revokes this.
            self.on_cancel()
            self.buffer.extend(self.late)
            self.late = b''
            self.buffer.extend(b'OK LOGFILE CANCEL cancelled=1 cleanup_complete=0\r\n')
            return len(payload)
        if command == 'SYSTEM INFO':
            self.probe_count += 1
            self.on_probe()
            if self.fault != 'late_after_probe':
                self.buffer.extend(self.late)
            self.buffer.extend(b'OK SYSTEM INFO project=SYNTHETIC version=0.1.3\r\n')
            if self.fault == 'late_after_probe':
                self.buffer.extend(self.late)
            self.late = b''
            return len(payload)
        response = self.server.exchange(command, 1, Event())
        self.buffer.extend((response + '\r\n').encode('ascii'))
        if command.startswith('LOGFILE POLL ') and self.server.pending[1] == 'META':
            self.metadata_cached = True
        if not command.startswith('LOGFILE BATCH '):
            return len(payload)
        offset = int(command.split()[4])
        self.batch_offsets.append(offset)
        self.nonces.append(command.split()[5])
        recovering = self.batch_offsets.count(offset) > 1
        if recovering:
            self.on_recovery()
            if self.fault == 'busy':
                self.buffer.extend(b'ERR LOGFILE BATCH request_id=0 code=BUSY\r\n')
                return len(payload)
        if not self.metadata_cached:
            self.buffer.extend(
                f'ERR LOGFILE BATCH request_id={self.server.request_id} code=STALE\r\n'.encode())
            return len(payload)
        for index in range(min(4, (len(self.server.data) - offset + 511) // 512)):
            frame = self.server.batch_receive(self.server.request_id, 1, Event())
            full = b'\0' + frame + b'\0'
            if offset == 2048 and index == 3 and (self.failed == 0 or self.fault == 'persistent'):
                self.failed += 1
                self.buffer.extend(full[:-1] if self.fault == 'delimiter' else full[:-92])
                if self.fault in ('late', 'late_after_probe'):
                    self.late = full[-92:] + full  # Late suffix, then a duplicate old record.
                break
            if recovering and index == 0 and self.fault == 'wrong_offset':
                args = dict(transfer=int(command.split()[5], 16), rid=self.server.request_id,
                            sequence=offset // 512 + 1, file_id=1, whole=zlib.crc32(self.server.data),
                            size=len(self.server.data), offset=offset + 512)
                full = b'\0' + Frame(self.server.data[offset+512:offset+1024], **args) + b'\0'
            if recovering and index == 0 and self.fault == 'stale_nonce':
                args = dict(transfer=int(self.nonces[-2], 16), rid=self.server.request_id,
                            sequence=offset // 512, file_id=1, whole=zlib.crc32(self.server.data),
                            size=len(self.server.data), offset=offset)
                self.buffer.extend(b'\0' + Frame(self.server.data[offset:offset+512], **args) + b'\0')
            self.buffer.extend(full)
            if recovering and index == 1 and self.fault == 'duplicate':
                self.buffer.extend(full)
        return len(payload)


def client_wire():
    wire = FileServiceSerialTransport('SYNTHETIC', 921600, serial_factory=RecoverySerial)
    wire._needs_sync = False
    return FileServiceClient(wire, timeout=.1), wire


@pytest.mark.parametrize('fault', ['tail92', 'delimiter', 'late', 'late_after_probe', 'duplicate', 'stale_nonce'])
def test_recovers_only_uncommitted_window_preserves_verified_prefix(tmp_path, fault):
    client, wire = client_wire()
    wire._serial.fault = fault
    original = wire._serial.server.data
    progress = []
    output = client.download(1, tmp_path, byte_progress=lambda *row: progress.append(row))
    assert output.read_bytes() == original
    assert wire._serial.server.data == original
    assert wire._serial.batch_offsets == [0, 2048, 2048, 4096, 6144]
    assert wire._serial.nonces[1] != wire._serial.nonces[2]
    assert [n for n, _, stage in progress if stage == 'receiving'] == [0, 2048, 4096, 6144, 6400]
    assert wire._serial.cancel_count == 0
    assert wire._serial.probe_count == 1 and wire._serial.metadata_cached
    assert client.transfer_diagnostics['batch_replays'] == 1
    assert client.transfer_diagnostics['recovered_batches'] == 1
    assert not wire.requires_reconnect and not wire._requests
    assert not list(tmp_path.glob('*.partial'))
    assert sum(c == 'LOGFILE META 1' for c in wire._serial.server.commands) == 2
    wire.close()


def test_wrong_offset_with_valid_crc_fails_closed_after_recovery(tmp_path):
    client, wire = client_wire()
    wire._serial.fault = 'wrong_offset'
    with pytest.raises((FileServiceError, ValueError), match='identity|offset'):
        client.download(1, tmp_path)
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire._serial.server.data[:2048]
    assert not list(tmp_path.glob('*.sslog')) and wire.requires_reconnect
    assert wire._serial.batch_offsets == [0, 2048, 2048]
    wire.close()


def test_persistent_tail_loss_stops_at_two_replays(tmp_path):
    client, wire = client_wire()
    wire._serial.fault = 'persistent'
    with pytest.raises(TimeoutError):
        client.download(1, tmp_path)
    assert wire._serial.batch_offsets == [0, 2048, 2048, 2048]
    assert client.transfer_diagnostics['batch_replays'] == 2
    assert client.transfer_diagnostics['resync_completed'] == 2
    assert client.transfer_diagnostics['recovered_batches'] == 0
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire._serial.server.data[:2048]
    assert not list(tmp_path.glob('*.sslog')) and wire.requires_reconnect
    wire.close()


def test_cancel_in_recovery_does_not_restart_or_publish(tmp_path):
    client, wire = client_wire()
    wire._serial.on_probe = client.cancel.set
    with pytest.raises(ExportCancelled):
        client.download(1, tmp_path)
    assert wire._serial.batch_offsets == [0, 2048]
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire._serial.server.data[:2048]
    assert not list(tmp_path.glob('*.sslog'))
    wire.close()


def test_recovery_does_not_extend_original_batch_deadline(tmp_path):
    client, wire = client_wire()
    # Real read timeout gets us into recovery; jump beyond the same absolute
    # deadline only when the replacement request is submitted.
    import time
    original = time.monotonic
    clock_offset = [0.]
    wire._serial.on_recovery = lambda: clock_offset.__setitem__(0, 31.)
    with patch('time.monotonic', side_effect=lambda: original() + clock_offset[0]):
        with pytest.raises(TimeoutError):
            client.download(1, tmp_path)
    assert wire._serial.batch_offsets == [0, 2048, 2048]
    assert next(tmp_path.glob('*.partial')).stat().st_size == 2048
    assert not list(tmp_path.glob('*.sslog')) and wire.requires_reconnect
    wire.close()


def test_whole_download_stops_after_sixteen_window_replays(tmp_path):
    wire = BatchTransport(bytes(range(256)) * (18 * 8))
    corrupted_offsets = set()
    def corrupt_once(frame, args):
        if args['offset'] % 2048 == 0 and args['offset'] not in corrupted_offsets:
            corrupted_offsets.add(args['offset'])
            return frame[:-1] + bytes([frame[-1] ^ 1])
        return frame
    wire.on_frame = corrupt_once
    client = FileServiceClient(wire)
    with pytest.raises(FileServiceError, match='whole-download replay limit'):
        client.download(1, tmp_path)
    assert client.transfer_diagnostics['batch_replays'] == 16
    assert client.transfer_diagnostics['crc_batches'] == 17
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire.data[:16 * 2048]
    assert not list(tmp_path.glob('*.sslog'))
    assert wire.invalidated


def test_outer_budget_timeout_does_not_trigger_recovery(tmp_path):
    wire = BatchTransport()
    def expired(*args):
        raise TimeoutError('Storage transaction deadline exceeded')
    wire.batch_receive = expired
    recoveries = []
    wire.batch_recover = lambda *args: recoveries.append(args)
    client = FileServiceClient(wire)
    with pytest.raises(TimeoutError, match='Storage transaction'):
        client.download(1, tmp_path)
    assert recoveries == [] and client.transfer_diagnostics['batch_replays'] == 0
    assert next(tmp_path.glob('*.partial')).stat().st_size == 0


def test_matching_nonce_without_crc_cannot_clear_taint():
    client, wire = client_wire()
    wire._requests['7'] = 'BATCH'
    wire._sync_failed = True
    payload = b'x' * 512
    nonce = 1234
    raw = Frame(payload, transfer=nonce, rid=8, size=512, whole=zlib.crc32(payload))
    wire._buffer.extend(b'\0' + raw[:-1] + bytes([raw[-1] ^ 1]) + b'\0')
    import time
    record = dict(discarded_candidates=0, received_bytes=0)
    with pytest.raises(TimeoutError):
        wire._Recovery_FirstFrame((nonce, 0, 1, zlib.crc32(payload), 512, 0),
                                  7, time.monotonic() + .02, Event(), record)
    assert wire.requires_reconnect and wire._requests == {'7': 'BATCH'}
    wire.close()


def test_duplicate_flood_has_finite_record_bound():
    wire = BatchTransport()
    original = wire.batch_receive
    first = [None]
    def repeat(rid, timeout, cancel):
        if first[0] is None:
            first[0] = original(rid, timeout, cancel)
        return first[0]
    wire.batch_receive = repeat
    client = FileServiceClient(wire)
    client._block_transfer = 1
    with pytest.raises(FileServiceError, match='duplicate limit'):
        client._Batch_Read(RemoteLog(1, wire.token, len(wire.data), zlib.crc32(wire.data)), 0)
    assert client.transfer_diagnostics['duplicate_records'] == 5
    assert wire.invalidated and not wire.completions


@pytest.mark.parametrize('fault', ['busy', 'cache_revoked'])
def test_text_ack_and_quiet_do_not_authorize_a_recovery(tmp_path, fault):
    client, wire = client_wire()
    wire._serial.fault = fault
    if fault == 'cache_revoked':
        wire._serial.on_probe = lambda: setattr(wire._serial, 'metadata_cached', False)
    with pytest.raises(TimeoutError):
        client.download(1, tmp_path)
    assert wire._serial.batch_offsets == [0, 2048, 2048]
    assert client.transfer_diagnostics['resync_completed'] == 0
    assert wire.requires_reconnect and wire._serial.cancel_count >= 1
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire._serial.server.data[:2048]
    assert not list(tmp_path.glob('*.sslog'))
    wire.close()
