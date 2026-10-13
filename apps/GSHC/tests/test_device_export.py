import hashlib
import json
import struct
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

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

    def test_cut_requires_confirmation_and_rechecks_target(self):
        job = self.exporter()
        output = job.copy(cut=True)
        job.delete_verified_sources(confirmed=False)
        self.assertTrue(self.source.exists())
        (output / self.source.name).write_bytes(b"corrupt")
        with self.assertRaises(OSError):
            job.delete_verified_sources(confirmed=True)
        self.assertTrue(self.source.exists())

    def test_copy_cannot_be_reinterpreted_as_cut(self):
        job = self.exporter()
        job.copy(cut=False)
        with self.assertRaises(ValueError):
            job.delete_verified_sources(confirmed=True)
        self.assertTrue(self.source.exists())

    def test_cut_manifest_corruption_preserves_source(self):
        job = self.exporter()
        output = job.copy(cut=True)
        (output / "manifest.json").write_bytes(b"{}")
        with self.assertRaises(OSError):
            job.delete_verified_sources(confirmed=True)
        self.assertTrue(self.source.exists())

    def test_cut_changed_or_active_source_is_preserved(self):
        active = [False]
        job = self.exporter(is_active=lambda _: active[0])
        job.copy(cut=True)
        active[0] = True
        with self.assertRaises(ValueError):
            job.delete_verified_sources(confirmed=True)
        active[0] = False
        self.source.write_bytes(b"changed")
        with self.assertRaises(OSError):
            job.delete_verified_sources(confirmed=True)
        self.assertTrue(self.source.exists())

    def test_cancel_before_delete_preserves_source(self):
        cancel = Event()
        job = self.exporter(cancel=cancel)
        job.copy(cut=True)
        cancel.set()
        with self.assertRaises(ExportCancelled):
            job.delete_verified_sources(confirmed=True)
        self.assertTrue(self.source.exists())

    def test_successful_cut_deletes_only_verified_temporary_source(self):
        job = self.exporter()
        output = job.copy(cut=True)
        job.delete_verified_sources(confirmed=True)
        self.assertFalse(self.source.exists())
        self.assertTrue((output / self.source.name).is_file())

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
