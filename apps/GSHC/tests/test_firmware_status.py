"""RAM status, maintenance admission and stale display; no physical ports."""
import time
import unittest
from dataclasses import replace
from tempfile import TemporaryDirectory
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from services.file_service_client import FileServiceClient, FileServiceError
from services.i18n import I18n
from ui.maintenance_page import MaintenancePage
from test_file_service_client import MockTransport


class FirmwareStatusTests(unittest.TestCase):
    def test_status_is_read_only_and_has_real_source(self):
        wire = MockTransport()
        snapshot = FileServiceClient(wire).status()
        self.assertEqual(wire.commands, ['LOGFILE CAPS', 'LOGFILE STATUS'])
        self.assertEqual(snapshot.firmware, '0.1.3')
        self.assertEqual(snapshot.maintenance, 0)
        self.assertLess(abs(time.monotonic_ns() - snapshot.received_ns), 1000000000)

    def test_acceptance_does_not_bypass_writer_cleanup(self):
        for field in ('writer_open=1', 'cleanup_pending=1', 'age_ms=4000',
                      'healthy=0', 'finalization=2', 'log_fault=1', 'maintenance=3'):
            with self.subTest(field=field):
                wire = MockTransport()
                key = field.split('=')[0]
                import re
                wire.mutate = lambda text: re.sub(r'\b' + key + r'=\d+', field, text)
                with self.assertRaises(FileServiceError):
                    FileServiceClient(wire).enter_maintenance()
                self.assertFalse(any(c.startswith('LOGFILE LIST') for c in wire.commands))

    def test_ready_snapshot_allows_maintenance(self):
        wire = MockTransport()
        FileServiceClient(wire).enter_maintenance()
        self.assertEqual(wire.commands, ['LOGFILE CAPS', 'LOGFILE ENTER', 'LOGFILE STATUS'])

    def test_old_capabilities_are_explicitly_unsupported(self):
        client = FileServiceClient(MockTransport())
        client.capabilities = {'file_service_version': '1'}
        with self.assertRaises(FileServiceError):
            client.status()
        with self.assertRaises(FileServiceError):
            client.enter_maintenance()
        self.assertEqual(client.transport.commands, [])

    def test_malformed_status_is_not_accepted(self):
        for change in (lambda t: t.replace('lifecycle=2', 'lifecycle=99'),
                       lambda t: t.replace('source=FC_DEBUG_RAM', 'source=AIR'),
                       lambda t: t + ' sequence=2'):
            wire = MockTransport()
            wire.mutate = change
            with self.assertRaises(FileServiceError):
                FileServiceClient(wire).status()

    def test_view_expires_and_clears_disconnected_snapshot(self):
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temporary:
            settings = QSettings(str(Path(temporary) / 'settings.ini'), QSettings.IniFormat)
            page = MaintenancePage(I18n(settings))
            snapshot = FileServiceClient(MockTransport()).status()
            page.set_firmware_status(replace(snapshot, age_ms=4000))
            self.assertIn(page.i18n.tr('maintenance.stale'), page.firmware_summary.text())
            page.set_firmware_status(None, 'Disconnected / invalidated')
            self.assertIsNone(page.firmware_snapshot)
            self.assertNotIn('mounted=', page.firmware_summary.text())
            self.assertIn('invalidated', page.firmware_summary.text())
            page.close()
            page.deleteLater()
            app.processEvents()

    def test_legacy_view_uses_receive_age_and_clears_unknown_storage(self):
        from services.legacy_firmware_status import LegacyFirmwareStatusClient
        from test_legacy_firmware_status import LegacyWire
        from threading import Event
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temporary:
            page = MaintenancePage(I18n(QSettings(str(Path(temporary) / 'legacy.ini'), QSettings.IniFormat)))
            snapshot = LegacyFirmwareStatusClient(LegacyWire(), cancel=Event()).status()
            page.set_firmware_status(replace(snapshot, received_ns=time.monotonic_ns() - 5_000_000_000))
            self.assertIn(page.i18n.tr('maintenance.stale'), page.firmware_summary.text())
            self.assertIn(page.i18n.tr('maintenance.legacy_age'), page.firmware_summary.text())
            page.set_firmware_status(replace(snapshot, storage=None, storage_detail='Unavailable'))
            self.assertNotIn('mounted=', page.firmware_summary.text())
            page.set_firmware_status(None, 'Disconnected / invalidated')
            self.assertIsNone(page.firmware_snapshot)
            page.close()
            page.deleteLater()
            app.processEvents()


if __name__ == '__main__':
    unittest.main()
