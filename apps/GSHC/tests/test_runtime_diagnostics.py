from dataclasses import replace
from threading import Event
import unittest
from services.file_service_client import FileServiceError
from services.runtime_diagnostics import RuntimeDiagnosticsClient, DiagnosticEntry_Parse

def entry(identifier='thread.new_sensor', state='OBSERVED', **extra):
    return dict(version='1', id=identifier, group='thread', name='New_sensor', state=state,
        reason='completed', source='NewTask', age_ms='100', readonly='1', **extra)


class DiagnosticTests(unittest.TestCase):
    def test_bad_cycle_is_never_published(self):
        caps = 'OK SYSTEM DIAG version=1 maintenance=0.1 compatible=0.0 entries=2 max_entries=16 max_line=511 polling_ms=1000'
        first = 'OK SYSTEM DIAG ' + ' '.join(f'{k}={v}' for k,v in entry('thread.same', next_cursor='1', end='0').items())
        for reply in (first, first.replace('next_cursor=1', 'next_cursor=17'),
                      first.replace('next_cursor=1', 'next_cursor=2'),
                      'OK SYSTEM DIAG version=1 end=1 next_cursor=0'):
            class Wire:
                def __init__(self): self.responses=iter((caps,first,reply))
                def exchange(self, *_): return next(self.responses)
            client = RuntimeDiagnosticsClient(Wire(), Event())
            self.assertIsNone(client.step())
            self.assertIsNone(client.step())
            with self.assertRaises(FileServiceError): client.step()

    def test_incompatible_caps_and_oversized_lines_fail(self):
        caps = 'OK SYSTEM DIAG version=1 maintenance=0.1 compatible=0.0 entries=2 max_entries=16 max_line=511 polling_ms=1000'
        for response in (caps.replace('version=1','version=2'), caps.replace('max_entries=16','max_entries=17'),
                         caps.replace('entries=2','entries=17'), caps + ' ' + 'x'*512,
                         caps + ' entries=2', caps.replace('compatible=0.0','compatible=0.2')):
            class Wire:
                def exchange(self, *_): return response
            with self.assertRaises(FileServiceError): RuntimeDiagnosticsClient(Wire(), Event()).step()

    def test_known_new_entry_and_unknown_optional_field(self):
        parsed = DiagnosticEntry_Parse(entry(counter='2', unit='samples', future_option='ignored'))
        self.assertEqual(parsed.id, 'thread.new_sensor')
        self.assertEqual(parsed.fields, {'counter':'2','unit':'samples'})
        self.assertEqual(DiagnosticEntry_Parse(entry(state='FUTURE_STATE')).state, 'UNKNOWN')

    def test_incompatible_and_bad_bounds_fail_explicitly(self):
        for key, value in [('version','2'),('readonly','0'),('age_ms','-1'),('counter','4294967296'),('id','bad id')]:
            fields = entry()
            fields[key] = value
            with self.assertRaises(FileServiceError): DiagnosticEntry_Parse(fields)
        with self.assertRaises(FileServiceError): DiagnosticEntry_Parse(entry(progress_done='2', progress_total='1'))

    def test_paged_cycle_one_exchange_per_step_and_rate_limited(self):
        class Wire:
            def __init__(self): self.commands=[]
            def exchange(self, command, *_):
                self.commands.append(command)
                if command == 'SYSTEM DIAG':
                    return 'OK SYSTEM DIAG version=1 maintenance=0.1 compatible=0.0 entries=2 max_entries=16 max_line=511 polling_ms=1000'
                if command == 'SYSTEM DIAG 2': return 'OK SYSTEM DIAG version=1 end=1 next_cursor=0'
                n = int(command.rsplit(' ',1)[1])
                fields = entry('thread.' + str(n), next_cursor=str(n+1), end='0')
                return 'OK SYSTEM DIAG ' + ' '.join(f'{k}={v}' for k,v in fields.items())
        wire = Wire()
        client = RuntimeDiagnosticsClient(wire, Event())
        self.assertIsNone(client.step())
        self.assertIsNone(client.step())
        self.assertIsNone(client.step())
        rows = client.step()
        self.assertEqual(len(rows), 2)
        self.assertEqual(wire.commands, ['SYSTEM DIAG','SYSTEM DIAG 0','SYSTEM DIAG 1','SYSTEM DIAG 2'])
        self.assertIsNone(client.step())
        self.assertEqual(len(wire.commands), 4)

    def test_unknown_entry_renders_without_gui_code_for_its_id(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from services.i18n import I18n
        from ui.maintenance_page import MaintenancePage
        app = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as temporary:
            page = MaintenancePage(I18n(QSettings(str(Path(temporary)/'ui.ini'), QSettings.IniFormat)))
            page.set_diagnostics([DiagnosticEntry_Parse(entry(state='NEW_UNKNOWN'))])
            group = page.diagnostic_tree.topLevelItem(0)
            self.assertIn('thread.new_sensor', group.child(0).text(0))
            self.assertIn('UNKNOWN', group.child(0).text(1))
            page.set_diagnostics(None, 'Disconnected')
            self.assertEqual(page.diagnostic_tree.topLevelItemCount(),0)
            page.close()
            page.deleteLater()
            app.processEvents()
