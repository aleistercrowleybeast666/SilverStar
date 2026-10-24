"""Binary/text maintenance boundaries with a synthetic byte stream only."""
import unittest
from threading import Event

from services.file_service_block import Block_Decode
from transport.file_service_backend import FileServiceSerialTransport
from test_file_service_block import Frame


class SerialBytes:
    def __init__(self, *, port, baudrate, timeout, write_timeout):
        self.buffer = bytearray()
        self.writes = []
        self.fragment = 1
        self.reply = b''
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.buffer)

    def write(self, payload):
        self.writes.append(payload)
        if payload.startswith(b'LOGFILE BLOCK '):
            self.buffer.extend(b'PENDING LOGFILE BLOCK request_id=3\r\n')
        else:
            self.buffer.extend(self.reply)
        return len(payload)

    def read(self, size):
        size = min(size, self.fragment, len(self.buffer))
        raw = bytes(self.buffer[:size])
        del self.buffer[:size]
        return raw

    def close(self):
        self.closed = True


class BinaryTransportTests(unittest.TestCase):
    def wire(self):
        wire = FileServiceSerialTransport('HOST-ONLY', 230400, serial_factory=SerialBytes)
        wire._needs_sync = False  # Test fixture: never an actual port or startup claim.
        wire.exchange('LOGFILE BLOCK 1 1-00000000-00000200 0 1122334455667788 0', 1, Event())
        return wire

    def test_fragmented_maximum_binary_frame_keeps_embedded_newlines(self):
        for fragment in (1, 7, 127, 565):
            with self.subTest(fragment=fragment):
                wire = self.wire()
                wire._serial.fragment = fragment
                data = bytes(range(256)) * 2
                wire._serial.reply = b'\0' + Frame(data) + b'\0'
                self.assertEqual(Block_Decode(wire.block_poll(3, 1, Event())).data, data)
                self.assertFalse(wire.requires_reconnect)
                wire.block_complete(3)
                wire.close()

    def test_incomplete_frame_taints_and_prevents_further_requests(self):
        wire = self.wire()
        wire._serial.reply = b'\0' + Frame(b'123456789')[:-1]
        with self.assertRaises(TimeoutError):
            wire.block_poll(3, 0.01, Event())
        self.assertTrue(wire.requires_reconnect)
        count = len(wire._serial.writes)
        with self.assertRaises(OSError):
            wire.exchange('LOGFILE CANCEL', 1, Event())
        self.assertEqual(len(wire._serial.writes), count)
        wire.close()

    def test_delimited_corruption_can_replay_and_pending_is_correlated(self):
        wire = self.wire()
        wire._serial.reply = b'PENDING LOGFILE BLOCK request_id=3\r\n'
        self.assertTrue(wire.block_poll(3, 1, Event()).startswith('PENDING'))
        wire._serial.reply = b'\0\x02X\0'
        self.assertEqual(wire.block_poll(3, 1, Event()), b'\x02X')
        self.assertFalse(wire.requires_reconnect)
        self.assertEqual(wire._requests['3'], 'BLOCK')

    def test_delimited_late_duplicate_is_quarantined_before_next_text_reply(self):
        wire = self.wire()
        wire._serial.reply = b'\0' + Frame(b'123456789') + b'\0OK LOGFILE CAPS supported=1\r\n'
        self.assertEqual(wire.exchange('LOGFILE CAPS', 1, Event()), 'OK LOGFILE CAPS supported=1')

    def test_valid_stale_request_is_quarantined_before_current_binary_reply(self):
        wire = self.wire()
        wire._serial.reply = b'\0'+Frame(b'a', rid=2)+b'\0\0'+Frame(b'b', rid=3)+b'\0'
        self.assertEqual(Block_Decode(wire.block_poll(3, 1, Event())).data, b'b')

    def test_oversized_and_unframed_binary_fail_closed(self):
        for data in (b'\0'+b'x'*600, b'x\0'+Frame(b'a')+b'\0'):
            with self.subTest(data=data[:5]):
                wire = self.wire()
                wire._serial.reply = data
                with self.assertRaises(OSError):
                    wire.block_poll(3, 1, Event())
                self.assertTrue(wire.requires_reconnect)
