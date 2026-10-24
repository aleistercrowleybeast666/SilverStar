"""Bounded batch faults use synthetic files and UART bytes only."""
import json
import zlib
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError, RemoteLog
from services.file_service_block import Block_Decode
from test_file_service_block import BlockTransport, Frame
from test_file_service_backend import SerialBytes
from transport.file_service_backend import FileServiceSerialTransport


class BatchTransport(BlockTransport):
    def __init__(self, data=bytes(range(256)) * 17):
        super().__init__(data)
        self.received = []
        self.batch_index = 0
        self.invalidated = False
        self.on_frame = lambda frame, args: frame

    def exchange(self, command, timeout, cancel):
        reply = super().exchange(command, timeout, cancel)
        if command == 'LOGFILE CAPS':
            reply += ' batch_version=1 batch_count=4'
        if command.startswith('LOGFILE BATCH '):
            self.batch_index = 0
        return reply

    def batch_receive(self, rid, timeout, cancel):
        fields = self.pending
        offset = int(fields[4]) + self.batch_index * 512
        self.batch_index += 1
        self.received.append((rid, offset))
        args = dict(transfer=int(fields[5], 16), rid=rid, sequence=offset // 512,
                    file_id=int(fields[2]), whole=zlib.crc32(self.data), size=len(self.data), offset=offset)
        return self.on_frame(Frame(self.data[offset:offset+512], **args), args)

    def batch_complete(self, rid):
        self.completions.append(rid)

    def block_invalidate(self):
        self.invalidated = True


@pytest.mark.parametrize('size', [1, 511, 512, 513, 2047, 2048, 2049, 4352])
def test_batch_download_exact_boundaries_and_fresh_meta(tmp_path, size):
    wire = BatchTransport(bytes(i % 256 for i in range(size)))
    output = FileServiceClient(wire).download(1, tmp_path)
    assert output.read_bytes() == wire.data
    assert len(wire.completions) == (size + 2047) // 2048
    assert not wire.polls and not any(c.startswith(('LOGFILE BLOCK ', 'LOGFILE READ ', 'LOGFILE DELETE')) for c in wire.commands)
    assert sum(c == 'LOGFILE META 1' for c in wire.commands) == 2
    assert not list(tmp_path.glob('*.partial'))


def test_two_crc_retries_drain_each_batch_before_any_write(tmp_path):
    wire = BatchTransport(bytes(range(256)) * 8)
    def corrupt(frame, args):
        if len(wire.completions) < 2 and args['offset'] == 512:
            return frame[:-1] + bytes([frame[-1] ^ 1])
        return frame
    wire.on_frame = corrupt
    progress = []
    output = FileServiceClient(wire).download(1, tmp_path, byte_progress=lambda *p: progress.append(p))
    assert output.read_bytes() == wire.data
    assert len(wire.received) == 12 and len(set(wire.completions)) == 3
    assert [p[0] for p in progress if p[2] == 'receiving'] == [0, 2048]
    assert [offset for _, offset in wire.received] == [0, 512, 1024, 1536] * 3


def test_third_crc_failure_invalidates_without_publishing(tmp_path):
    wire = BatchTransport()
    wire.on_frame = lambda frame, args: frame[:-1] + bytes([frame[-1] ^ 1])
    with pytest.raises(FileServiceError, match='replay'):
        FileServiceClient(wire).download(1, tmp_path)
    assert wire.invalidated and len(wire.received) == 12
    assert next(tmp_path.glob('*.partial')).stat().st_size == 0
    assert not list(tmp_path.glob('*.sslog'))


@pytest.mark.parametrize('field', ['transfer', 'rid', 'sequence', 'file_id', 'whole', 'offset'])
def test_valid_crc_wrong_identity_never_retries_or_writes(tmp_path, field):
    wire = BatchTransport()
    def wrong(frame, args):
        args[field] += 1
        return Frame(wire.data[args['offset']:args['offset']+512], **args)
    wire.on_frame = wrong
    with pytest.raises(FileServiceError):
        FileServiceClient(wire).download(1, tmp_path)
    assert wire.invalidated and len(wire.received) == 1 and not wire.completions
    assert next(tmp_path.glob('*.partial')).stat().st_size == 0


def test_cancel_during_batch_preserves_source_and_no_partial_batch(tmp_path):
    wire = BatchTransport()
    original = wire.data
    cancel = Event()
    def stop(frame, args):
        if args['offset'] == 512:
            cancel.set()
        return frame
    wire.on_frame = stop
    with pytest.raises(ExportCancelled):
        FileServiceClient(wire, cancel=cancel).download(1, tmp_path)
    partial = next(tmp_path.glob('*.partial'))
    assert wire.invalidated and partial.stat().st_size == 0 and wire.data == original
    assert not json.loads(partial.with_name(partial.name+'.json').read_text())['resume_allowed']


def test_late_batch_is_not_accepted_or_retried():
    wire = BatchTransport()
    clock = [0.0]
    def late(frame, args):
        clock[0] = 31.0
        return frame
    wire.on_frame = late
    client = FileServiceClient(wire)
    client._block_transfer = 1
    with patch('services.file_service_client.time.monotonic', side_effect=lambda: clock[0]):
        with pytest.raises(TimeoutError):
            client._Batch_Read(RemoteLog(1, wire.token, len(wire.data), zlib.crc32(wire.data)), 0)
    assert wire.invalidated and len(wire.received) == 1 and not wire.completions


def test_fresh_meta_mismatch_preserves_unpublished_full_partial(tmp_path):
    wire = BatchTransport()
    wire.mutate = lambda reply: reply.replace('size=4352', 'size=4353') if len(wire.completions) == 3 else reply
    with pytest.raises(FileServiceError):
        FileServiceClient(wire).download(1, tmp_path)
    assert not list(tmp_path.glob('*.sslog'))
    assert next(tmp_path.glob('*.partial')).read_bytes() == wire.data


@pytest.mark.parametrize('suffix', [' batch_version=1', ' batch_version=2 batch_count=4', ' batch_version=1 batch_count=99'])
def test_malformed_batch_caps_fail_closed(suffix):
    wire = BlockTransport()
    original = wire.exchange
    wire.exchange = lambda cmd, timeout, cancel: original(cmd, timeout, cancel) + (suffix if cmd == 'LOGFILE CAPS' else '')
    with pytest.raises(FileServiceError, match='batch'):
        FileServiceClient(wire).negotiate()


def test_host_without_batch_transport_retains_block_protocol(tmp_path):
    wire = BatchTransport()
    wire.batch_receive = None
    output = FileServiceClient(wire).download(1, tmp_path)
    assert output.read_bytes() == wire.data and wire.polls
    assert not any(c.startswith('LOGFILE BATCH ') for c in wire.commands)


class BatchSerial(SerialBytes):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = BatchTransport()
        self.fragment = 128
        self.truncate = False

    def write(self, payload):
        self.writes.append(payload)
        command = payload.decode('ascii').strip()
        if command == 'SYSTEM INFO':
            self.buffer.extend(b'OK SYSTEM INFO project=SYNTHETIC version=0.1.3\r\n')
            return len(payload)
        response = self.server.exchange(command, 1, Event())
        self.buffer.extend((response + '\r\n').encode('ascii'))
        if command.startswith('LOGFILE BATCH '):
            offset = int(command.split()[4])
            for _ in range(min(4, (len(self.server.data)-offset+511)//512)):
                frame = self.server.batch_receive(self.server.request_id, 1, Event())
                self.buffer.extend(b'\0'+frame+(b'' if self.truncate else b'\0'))
                if self.truncate:
                    break
        return len(payload)


@pytest.mark.parametrize('fragment', [1, 7, 128, 565])
def test_real_transport_batch_fragments_without_poll_or_extra_empty_read(tmp_path, fragment):
    wire = FileServiceSerialTransport('SYNTHETIC', 921600, serial_factory=BatchSerial)
    wire._needs_sync = False
    wire._serial.fragment = fragment
    output = FileServiceClient(wire).download(1, tmp_path)
    assert output.read_bytes() == wire._serial.server.data
    requests = wire._serial.writes
    assert sum(x.startswith(b'LOGFILE BATCH ') for x in requests) == 3
    assert sum(x.startswith(b'LOGFILE POLL ') for x in requests) == 2  # META only
    assert not wire.requires_reconnect and not wire._requests
    wire.close()


def test_truncated_recovery_first_frame_stops_without_publish(tmp_path):
    wire = FileServiceSerialTransport('SYNTHETIC', 921600, serial_factory=BatchSerial)
    wire._needs_sync = False
    wire._serial.truncate = True
    client = FileServiceClient(wire, timeout=.01)
    with pytest.raises(TimeoutError):
        client.download(1, tmp_path)
    assert wire.requires_reconnect
    assert sum(x.startswith(b'LOGFILE BATCH ') for x in wire._serial.writes) == 2
    assert client.transfer_diagnostics['batch_replays'] == 1
    assert client.transfer_diagnostics['recovery_failures'] == 1
    assert next(tmp_path.glob('*.partial')).stat().st_size == 0
    assert not list(tmp_path.glob('*.sslog'))
    wire.close()
