import hashlib
import json
import struct
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from services.device_export import DeviceExport, ExportCancelled
from services.logger import AsyncJsonlLogger


class DeviceExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.logs = self.root / "logs"
        self.target = self.root / "target"
        self.logs.mkdir()
        self.target.mkdir()
        self.source = self.logs / "fc_session_test.jsonl"
        self.source.write_bytes(b'{"raw_hex":"00ff"}\r\n')

    def tearDown(self):
        self.temp.cleanup()

    def exporter(self, **kwargs):
        return DeviceExport([self.source], self.target, managed_root=self.logs,
                            is_active=kwargs.pop("is_active", lambda _: False), **kwargs)

    def test_copy_preserves_bytes_and_schema_valid_manifest(self):
        job = self.exporter()
        output = job.copy()
        self.assertEqual(self.source.read_bytes(), (output / self.source.name).read_bytes())
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["files"][0]["format_version"], "legacy-unversioned")
        self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        import jsonschema
        schema = Path(__file__).resolve().parents[3] / "contracts/session_export_v1.schema.json"
        jsonschema.validate(manifest, json.loads(schema.read_text(encoding="utf-8")))

    def test_cut_rejected_before_creating_destination(self):
        original = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, 'copy-only'):
            self.exporter().copy(cut=True)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_copy_cannot_be_reinterpreted_as_cut(self):
        job = self.exporter()
        output = job.copy()
        for confirmed in (False, True):
            if confirmed:
                with self.assertRaisesRegex(ValueError, 'copy-only'):
                    job.delete_verified_sources(confirmed=confirmed)
            else:
                job.delete_verified_sources(confirmed=confirmed)
        self.assertEqual(self.source.read_bytes(), (output / self.source.name).read_bytes())

    def test_copy_target_readback_failure_preserves_source(self):
        job = self.exporter()
        original = self.source.read_bytes()
        with patch.object(job, '_hash', return_value='incorrect digest'):
            with self.assertRaisesRegex(OSError, 'readback failed'):
                job.copy()
        self.assertFalse(job.ready)
        self.assertFalse((job.output / 'manifest.json').exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_source_change_during_copy_is_rejected(self):
        job = self.exporter()
        def change(progress):
            if progress.stage == 'verifying':
                self.source.write_bytes(b'new recording bytes')
        with self.assertRaisesRegex(OSError, 'Source changed'):
            job.copy(byte_progress=change)
        self.assertFalse(job.ready)
        self.assertEqual(self.source.read_bytes(), b'new recording bytes')

    def test_cancel_during_copy_preserves_source_and_does_not_publish_manifest(self):
        cancel = Event()
        job = self.exporter(cancel=cancel)
        original = self.source.read_bytes()
        def stop(progress):
            if progress.stage == 'receiving' and progress.received:
                cancel.set()
        with self.assertRaises(ExportCancelled):
            job.copy(byte_progress=stop)
        self.assertFalse(job.ready)
        self.assertFalse((job.output / 'manifest.json').exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_delete_rejected_even_when_completed_copy_is_tampered(self):
        job = self.exporter()
        original = self.source.read_bytes()
        output = job.copy()
        (output / 'manifest.json').write_bytes(b'{}')
        (output / self.source.name).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'copy-only'):
            job.delete_verified_sources(confirmed=True)
        self.assertEqual(self.source.read_bytes(), original)

    def test_external_cut_and_active_copy_are_rejected(self):
        external = self.target / "fc_session_external.jsonl"
        external.write_bytes(b"sample")
        job = DeviceExport([external], self.target, managed_root=self.logs, is_active=lambda _: False)
        with self.assertRaises(ValueError):
            job.copy(cut=True)
        with self.assertRaises(ValueError):
            self.exporter(is_active=lambda _: True).copy()

    def test_unicode_source_maps_to_safe_manifest_path(self):
        renamed = self.logs / "飞行 日志.jsonl"
        self.source.rename(renamed)
        job = DeviceExport([renamed], self.target, managed_root=self.logs, is_active=lambda _: False)
        output = job.copy()
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["files"][0]["path"], "file_0000.bin")

    def test_new_logger_version_preserves_raw_record(self):
        logger = AsyncJsonlLogger(self.logs)
        path = logger.path
        logger.write({"raw_hex": "00ff", "layer": "GSP"})
        logger.close()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(records[0]["log_format_version"], 1)
        self.assertEqual(records[1]["raw_hex"], "00ff")

    def test_sslog_label_requires_actual_valid_header(self):
        header = bytearray(64)
        header[:8] = b"SSLOG0\x00\x00"
        struct.pack_into("<HHH", header, 8, 0, 64, 24)
        struct.pack_into("<H", header, 44, 4)
        struct.pack_into("<I", header, 60, zlib.crc32(header[:60]))
        source = self.logs / "flight.sslog"
        source.write_bytes(header)
        self.assertEqual(DeviceExport._format(source)["format_version"], "0.0")
        source.write_bytes(b"not a SSLOG header")
        self.assertEqual(DeviceExport._format(source)["format"], "opaque")


if __name__ == "__main__":
    unittest.main()
