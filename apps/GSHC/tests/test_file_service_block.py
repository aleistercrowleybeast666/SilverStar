import struct
import unittest
import zlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError
from services.file_service_client import RemoteLog
from unittest.mock import patch
from test_file_service_client import MockTransport

from services.file_service_block import (
    BLOCK_SIZE, HEADER, RAW_LIMIT, WIRE_LIMIT, Block_Decode, BlockIntegrityError,
)


def Cobs_Encode(raw):
    output = bytearray([0])
    code_at = 0
    code = 1
    for value in raw:
        if value == 0:
            output[code_at] = code
            code_at = len(output)
            output.append(0)
            code = 1
        else:
            output.append(value)
            code += 1
            if code == 255:
                output[code_at] = code
                code_at = len(output)
                output.append(0)
                code = 1
    output[code_at] = code
    return bytes(output)


def Frame(data, *, transfer=0x1122334455667788, rid=3, sequence=0,
          file_id=1, whole=None, size=None, offset=0, flags=None, reserved=0):
    size = len(data) if size is None else size
    whole = zlib.crc32(data) if whole is None else whole
    flags = int(offset + len(data) == size) if flags is None else flags
    raw = HEADER.pack(b'SLB1', 1, 1, flags, transfer, rid, sequence, file_id,
                      whole, size, offset, len(data), reserved) + data
    return Cobs_Encode(raw + struct.pack('<I', zlib.crc32(raw)))


class BlockCodecTests(unittest.TestCase):
    def test_boundaries_and_binary_bytes(self):
        self.assertEqual((HEADER.size, RAW_LIMIT, WIRE_LIMIT), (44, 560, 565))
        for length in (0, 1, 255, 511, 512):
            with self.subTest(length=length):
                data = bytes(index % 256 for index in range(length))
                frame = Frame(data)
                block = Block_Decode(frame)
                self.assertEqual(block.data, data)
                self.assertTrue(block.eof)
                self.assertLessEqual(len(frame) + 2, WIRE_LIMIT)

    def test_non_eof_full_block(self):
        block = Block_Decode(Frame(b'\0' * BLOCK_SIZE, size=513))
        self.assertFalse(block.eof)

    def test_crc_and_incomplete_cobs_fail(self):
        frame = bytearray(Frame(b'123456789'))
        frame[-1] ^= 1
        for invalid in (bytes(frame), b'\x08a', b'', b'\0', b'\x01' * 566):
            with self.subTest(invalid=invalid[:8]):
                with self.assertRaises(BlockIntegrityError):
                    Block_Decode(invalid)

    def test_valid_crc_invalid_contract_is_not_retryable(self):
        for args in ({'transfer': 0}, {'rid': 0}, {'offset': 10, 'size': 9},
                     {'size': 513}, {'flags': 0}, {'flags': 3}, {'reserved': 1}):
            with self.subTest(args=args):
                with self.assertRaises(ValueError) as caught:
                    Block_Decode(Frame(b'123456789', **args))
                self.assertNotIsInstance(caught.exception, BlockIntegrityError)


class BlockTransport(MockTransport):
    def __init__(self, data=bytes(range(256)) * 5):
        super().__init__(data)
        self.polls = []
        self.completions = []
        self.frame_mutate = lambda frame, _fields: frame

    def exchange(self, command, timeout, cancel):
        reply = super().exchange(command, timeout, cancel)
        if command == 'LOGFILE CAPS':
            reply += ' block_version=1 max_block=512 block_encoding=COBS block_window=1'
        return reply

    def block_poll(self, rid, timeout, cancel):
        self.polls.append(rid)
        fields = self.pending
        offset = int(fields[4])
        args = dict(transfer=int(fields[5], 16), rid=rid, sequence=int(fields[6]),
                    file_id=int(fields[2]), whole=zlib.crc32(self.data), size=len(self.data), offset=offset)
        frame = Frame(self.data[offset:offset+512], **args)
        return self.frame_mutate(frame, args)

    def block_complete(self, rid):
        self.completions.append(rid)


class BlockClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_download_and_progress_use_three_exact_blocks(self):
        wire = BlockTransport()
        progress = []
        output = FileServiceClient(wire).download(1, self.root, byte_progress=lambda *args: progress.append(args))
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual([int(cmd.split()[4]) for cmd in wire.commands if cmd.startswith('LOGFILE BLOCK ')], [0, 512, 1024])
        self.assertEqual(len(wire.completions), 3)
        self.assertEqual([p[0] for p in progress if p[2] == 'receiving' and p[0]], [512, 1024, 1280])

    def test_complete_crc_failures_replay_same_request_without_duplicate_write(self):
        wire = BlockTransport(b'123456789')
        def mutate(frame, _args):
            return frame[:-1] + bytes([frame[-1] ^ 1]) if len(wire.polls) <= 2 else frame
        wire.frame_mutate = mutate
        output = FileServiceClient(wire).download(1, self.root)
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual(len(set(wire.polls)), 1)
        self.assertEqual(len(wire.polls), 3)
        self.assertEqual(len(wire.completions), 1)

    def test_three_corrupt_completions_stop_before_any_write(self):
        wire = BlockTransport()
        wire.frame_mutate = lambda frame, _args: frame[:-1] + bytes([frame[-1] ^ 1])
        with self.assertRaisesRegex(FileServiceError, 'replay'):
            FileServiceClient(wire).download(1, self.root)
        self.assertEqual(len(wire.polls), 3)
        self.assertEqual(next(self.root.glob('*.partial')).stat().st_size, 0)
        self.assertFalse(list(self.root.glob('*.sslog')))

    def test_valid_crc_stale_identity_is_rejected_without_retry(self):
        for key in ('transfer', 'rid', 'sequence', 'file_id', 'whole', 'offset'):
            with self.subTest(key=key), TemporaryDirectory(dir=self.root) as folder:
                wire = BlockTransport()
                def mutate(_frame, args):
                    args[key] += 1
                    return Frame(wire.data[args['offset']:args['offset']+512], **args)
                wire.frame_mutate = mutate
                with self.assertRaises(FileServiceError):
                    FileServiceClient(wire).download(1, Path(folder))
                self.assertEqual(len(wire.polls), 1)
                self.assertEqual(next(Path(folder).glob('*.partial')).stat().st_size, 0)

    def test_cancel_preserves_partial_new_attempt_has_new_nonce_and_starts_zero(self):
        wire = BlockTransport()
        event = Event()
        client = FileServiceClient(wire, cancel=event)
        with self.assertRaises(ExportCancelled):
            client.download(1, self.root, progress=lambda *_: event.set())
        partial = next(self.root.glob('*.partial'))
        self.assertEqual(partial.stat().st_size, 512)
        checkpoint = json.loads(partial.with_name(partial.name+'.json').read_text())
        self.assertFalse(checkpoint['resume_allowed'])
        old_nonce = client._block_transfer
        client.cancel_remote()
        event.clear()
        wire.commands.clear()
        output = client.download(1, self.root)
        self.assertNotEqual(client._block_transfer, old_nonce)
        self.assertEqual(next(cmd.split()[4] for cmd in wire.commands if cmd.startswith('LOGFILE BLOCK ')), '0')
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual(partial.stat().st_size, 512)

    def test_timeout_is_not_automatically_retried(self):
        wire = BlockTransport()
        def fail(_frame, _args):
            raise TimeoutError('incomplete frame')
        wire.frame_mutate = fail
        with self.assertRaises(TimeoutError):
            FileServiceClient(wire).download(1, self.root)
        self.assertEqual(len(wire.polls), 1)
        self.assertFalse(wire.completions)

    def test_complete_but_late_block_is_not_accepted_and_invalidates_link(self):
        wire = BlockTransport(b'123456789')
        clock = [0.0]
        invalid = []
        wire.block_invalidate = lambda: invalid.append(True)
        def late(frame, _args):
            clock[0] = 31.0
            return frame
        wire.frame_mutate = late
        client = FileServiceClient(wire)
        client._block_transfer = 1
        with patch('services.file_service_client.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(TimeoutError):
                client._Block_Read(RemoteLog(1, wire.token, 9, zlib.crc32(wire.data)), 0)
        self.assertEqual(invalid, [True])
        self.assertFalse(wire.completions)

    def test_old_caps_and_line_only_transport_use_legacy_read(self):
        for wire in (MockTransport(), BlockTransport()):
            with self.subTest(wire=type(wire).__name__), TemporaryDirectory(dir=self.root) as folder:
                if isinstance(wire, BlockTransport):
                    wire.block_complete = None
                output = FileServiceClient(wire).download(1, Path(folder))
                self.assertEqual(output.read_bytes(), wire.data)
                self.assertTrue(any(cmd.startswith('LOGFILE READ ') for cmd in wire.commands))
                self.assertFalse(any(cmd.startswith('LOGFILE BLOCK ') for cmd in wire.commands))

    def test_incomplete_or_unknown_block_caps_fail_closed(self):
        for suffix in (' block_version=1', ' block_version=2 max_block=512 block_encoding=COBS block_window=1'):
            wire = MockTransport()
            exchange = wire.exchange
            wire.exchange = lambda command, timeout, cancel: exchange(command, timeout, cancel) + (suffix if command == 'LOGFILE CAPS' else '')
            with self.subTest(suffix=suffix), self.assertRaises(FileServiceError):
                FileServiceClient(wire).negotiate()
