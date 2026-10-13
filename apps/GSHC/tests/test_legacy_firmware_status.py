"""Exact FINAL console response shapes, exercised without opening hardware."""
from dataclasses import replace
from threading import Event
import time
import unittest
from services.device_export import ExportCancelled
from services.file_service_client import FileServiceError
from services.legacy_firmware_status import LegacyFirmwareStatusClient
from transport.file_service_backend import FileServiceSerialTransport

RESPONSES = {
    'SYSTEM INFO': 'OK SYSTEM INFO project=SilverStar version=0.1.2 profile=0x00000001',
    'SYSTEM CAPABILITIES': 'OK SYSTEM CAPABILITIES compiled=0x000000FF enabled=0x0000000F present=0x00000007 healthy=0x00000003',
    'SYSTEM STATUS': 'OK SYSTEM STATUS state=2 ready=0 block=0x00000004 warn=0x00000008 attitude=VALID',
    'LOG STATUS': 'OK LOG STATUS initialized=1 mounted=1 open=1 healthy=1 writes=123 syncs=4 errors=0',
}


class LegacyWire:
    def __init__(self):
        self.commands, self.closed = [], False
        self.responses = dict(RESPONSES)
    def exchange(self, command, timeout, cancel):
        if cancel.is_set():
            raise ExportCancelled()
        self.commands.append(command)
        if command == 'LOGFILE CAPS':
            return 'ERR CONSOLE PARSE code=BAD_MODULE reason=UNKNOWN'
        return self.responses[command]
    def check_alive(self): pass
    def close(self): self.closed = True


class LegacyStatusTests(unittest.TestCase):
    def test_reads_only_exact_status_commands_and_preserves_old_storage_meaning(self):
        wire = LegacyWire()
        client = LegacyFirmwareStatusClient(wire, cancel=Event())
        snapshot = client.status()
        self.assertEqual(wire.commands, list(RESPONSES))
        self.assertEqual(snapshot.firmware, '0.1.2')
        self.assertEqual(snapshot.lifecycle, 2)
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.blocking_mask, 4)
        self.assertEqual(snapshot.capabilities, (255, 15, 7, 3))
        self.assertTrue(snapshot.storage.writer_open)
        self.assertEqual(snapshot.storage.writes, 123)
        client.status()
        self.assertEqual(wire.commands[4:], ['SYSTEM STATUS', 'LOG STATUS'])
        with self.assertRaises(ValueError): client._query('SYSTEM START')
        self.assertNotIn('SYSTEM START', wire.commands)

    def test_storage_failure_keeps_system_status_without_invented_zeros(self):
        wire = LegacyWire()
        wire.responses['LOG STATUS'] = 'ERR LOG STATUS code=NOT_READY reason=DEVICE'
        snapshot = LegacyFirmwareStatusClient(wire, cancel=Event()).status()
        self.assertEqual(snapshot.lifecycle, 2)
        self.assertIsNone(snapshot.storage)
        self.assertIn('NOT_READY', snapshot.storage_detail)

    def test_malformed_system_status_never_publishes(self):
        for response in ('OK SYSTEM STATUS state=9 ready=1 block=0x00000000 warn=0x00000000 attitude=VALID',
                         RESPONSES['SYSTEM STATUS'] + ' ready=1',
                         RESPONSES['SYSTEM STATUS'].replace('block=0x00000004', 'block=4'),
                         'OK LOG STATUS state=2 ready=0'):
            wire = LegacyWire()
            wire.responses['SYSTEM STATUS'] = response
            with self.assertRaises(FileServiceError):
                LegacyFirmwareStatusClient(wire, cancel=Event()).status()

    def test_cancel_does_not_write_any_query(self):
        cancel = Event()
        cancel.set()
        wire = LegacyWire()
        with self.assertRaises(ExportCancelled):
            LegacyFirmwareStatusClient(wire, cancel=cancel).status()
        self.assertEqual(wire.commands, [])

    def test_transport_matches_legacy_command_not_late_caps_or_other_status(self):
        class Serial:
            def __init__(self, **kwargs):
                self.data = [b'OK LOGFILE CAPS supported=0\r\n', b'> SYSTEM STATUS\r\n',
                    b'OK LOG STATUS mounted=1\r\n', b'> OK SYSTEM STATUS state=2 ready=0 ',
                    b'block=0x00000004 warn=0x00000008 attitude=VALID\r\n']
            def write(self, payload): return len(payload)
            def read(self, count): return self.data.pop(0) if self.data else b''
        wire = FileServiceSerialTransport('MOCK', 230400, serial_factory=Serial)
        self.assertEqual(wire.exchange('SYSTEM STATUS', 1, Event()), RESPONSES['SYSTEM STATUS'])


if __name__ == '__main__':
    unittest.main()
