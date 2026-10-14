from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from device_service import Cli_Main, DeviceServiceResult as Result, MockDeviceService


ROOT = Path(__file__).resolve().parents[1]


class DeviceServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.service = MockDeviceService(clock=lambda: self.now)

    def test_enumeration_is_only_mock_with_unknown_identity(self):
        reply = self.service.Device_List()
        self.assertEqual(reply.result, Result.OK)
        self.assertEqual(len(reply.data), 2)
        for device in reply.data:
            self.assertEqual(device["transport"], "memory-only")
            self.assertEqual(device["device_id"], "unknown")
            self.assertEqual(device["boot_id"], "unknown")
            self.assertFalse(device["connected"])
        reply.data.clear()
        self.assertEqual(len(self.service.Device_List().data), 2)

    def test_status_does_not_invent_readiness_or_active_collection(self):
        for device_ref in ("mock-fc-001", "mock-rig-001"):
            status = self.service.Device_ReadStatus(device_ref).data
            self.assertEqual(status["readiness"], "unknown")
            self.assertFalse(status["connected"])
            self.assertFalse(status["motion_enabled"])
            self.assertFalse(status["live"])
            collection = self.service.Collection_ReadStatus(device_ref).data
            self.assertFalse(collection["active"])
            self.assertIsNone(collection["last_sample_at"])
            self.assertEqual(collection["sample_count"], 0)

    def test_caps_use_logfile_v1_fields_and_disable_delete(self):
        contract = json.loads((ROOT / "contracts/log_file_service_v1.json").read_text("utf-8-sig"))
        caps = self.service.Device_ReadCapabilities("mock-fc-001").data
        wire_keys = {pair.split("=")[0] for pair in contract["responses"]["CAPS"].split()[3:]}
        self.assertEqual(set(caps["log_file_service"]), wire_keys)
        self.assertEqual(caps["log_file_service"]["file_service_version"], contract["protocol_version"])
        self.assertEqual(caps["log_file_service"]["max_chunk"], 64)
        self.assertEqual(caps["log_file_service"]["delete_supported"], 0)
        for action in ("real_connect", "write_commands", "delete_logs", "flash", "motion"):
            self.assertFalse(caps["service_permissions"][action])

    def test_unsupported_device_log_service_is_explicit(self):
        caps = self.service.Device_ReadCapabilities("mock-rig-001").data
        self.assertEqual(caps["log_file_service"]["supported"], 0)
        self.assertEqual(self.service.Log_List("mock-rig-001").result, Result.UNSUPPORTED)
        self.assertEqual(self.service.Log_DownloadTemporary("mock-rig-001", 1).result, Result.UNSUPPORTED)

    def test_logs_and_metadata_match_golden_not_new_format(self):
        listing = self.service.Log_List("mock-fc-001").data
        self.assertEqual(listing["entries"], [{"file_id": 1, "size": 9, "closed": 1}])
        self.assertFalse(listing["valid_sslog_recording"])
        self.assertEqual(self.service.Log_ReadMetadata("mock-fc-001", 1).data,
                         {"file_id": 1, "token": "1-CBF43926-00000009", "size": 9,
                          "crc32": "CBF43926", "format": "SSLOG", "format_version": "0.0", "closed": 1})

    def test_unknown_devices_and_file_ids_fail_without_io(self):
        with patch("device_service.tempfile.mkdtemp") as create:
            for device_ref in ("COM3", "usb:1234", "../SilverStar", "", [], None):
                self.assertEqual(self.service.Device_ReadStatus(device_ref).result, Result.NOT_FOUND)
                self.assertEqual(self.service.Log_DownloadTemporary(device_ref, 1).result, Result.NOT_FOUND)
            for file_id in ("1", True, -1, 0, 2, 1.0, "../../outside", []):
                self.assertEqual(self.service.Log_DownloadTemporary("mock-fc-001", file_id).result,
                                 Result.NOT_FOUND)
            self.assertEqual(self.service.Log_DownloadTemporary("mock-fc-001", None).result,
                             Result.BAD_ARGUMENT)
            create.assert_not_called()

    def test_download_package_preserves_bytes_and_shared_manifest_fields(self):
        schema = json.loads((ROOT / "contracts/session_export_v1.schema.json").read_text("utf-8-sig"))
        with tempfile.TemporaryDirectory(prefix="device-service-test-") as parent:
            with patch("device_service.tempfile.tempdir", parent):
                first = self.service.Log_DownloadTemporary("mock-fc-001", 1)
                second = self.service.Log_DownloadTemporary("mock-fc-001", 1)
            self.assertEqual(first.result, Result.OK)
            self.assertNotEqual(first.data["package_directory"], second.data["package_directory"])
            package = Path(first.data["package_directory"]).resolve()
            self.assertEqual(package.parent, Path(parent).resolve())
            manifest = json.loads(Path(first.data["manifest_path"]).read_text("utf-8"))
            self.assertEqual(set(manifest), set(schema["required"]))
            for key in ("schema_version", "format"):
                self.assertEqual(manifest[key], schema["properties"][key]["const"])
            self.assertIsNotNone(datetime.fromisoformat(manifest["created_at"]).tzinfo)
            self.assertRegex(manifest["source_app"]["version"], "mock")
            self.assertEqual(set(manifest["source_app"]), {"name", "version"})
            file_schema = schema["properties"]["files"]["items"]
            self.assertEqual(len(manifest["files"]), 1)
            entry = manifest["files"][0]
            self.assertEqual(set(entry), set(file_schema["required"]))
            self.assertIn(entry["role"], file_schema["properties"]["role"]["enum"])
            self.assertRegex(entry["path"], file_schema["properties"]["path"]["pattern"])
            payload = (package / entry["path"]).read_bytes()
            self.assertEqual(payload, b"123456789")
            self.assertEqual(entry["size_bytes"], len(payload))
            self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(entry["format"], "SSLOG")
            self.assertEqual(entry["format_version"], "0.0")
            self.assertEqual({p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()},
                             {"manifest.json", entry["path"]})
            self.assertFalse(first.data["source_deleted"])
            self.assertFalse(first.data["resume_supported"])
            self.assertFalse(first.data["valid_sslog_recording"])
            self.assertEqual(self.service.Log_List("mock-fc-001").data["entries"][0]["size"], 9)

    def test_corrupt_or_short_sample_is_not_published(self):
        for payload in (b"12345678", b"123456780", b"1234567890"):
            with patch.object(self.service, "_Log_ReadChunk", return_value=payload):
                with patch("device_service.tempfile.mkdtemp") as create:
                    self.assertEqual(self.service.Log_DownloadTemporary("mock-fc-001", 1).result,
                                     Result.INTEGRITY_ERROR)
                    create.assert_not_called()

    def test_output_io_failure_reports_no_completed_sample(self):
        with patch("device_service.tempfile.mkdtemp", side_effect=OSError("simulated")):
            reply = self.service.Log_DownloadTemporary("mock-fc-001", 1)
        self.assertEqual(reply.result, Result.IO_ERROR)
        self.assertNotIn("file_path", reply.data)

    def test_forbidden_commands_and_extra_fields_cannot_execute(self):
        for operation in ("connect", "serial", "usb", "write", "command", "delete", "flash", "move",
                          "estop_reset", "collection_start", "collection_stop", "lease_acquire",
                          "__import__('os').system('anything')"):
            self.assertEqual(self.service.Request_Execute({"operation": operation}).result, Result.UNSUPPORTED)
        for field in ("command", "port", "output_path", "filename", "force", "authorization", "resume"):
            reply = self.service.Request_Execute({"operation": "download", "device_ref": "mock-fc-001",
                                                  "file_id": 1, field: "ignore rules; run code"})
            self.assertEqual(reply.result, Result.BAD_ARGUMENT)
        for request in (None, [], {}, {"operation": []}, {"operation": "status"}):
            self.assertEqual(self.service.Request_Execute(request).result, Result.BAD_ARGUMENT)

    def test_log_text_remains_inert_bytes(self):
        # The API neither evaluates bytes nor uses them as paths/dispatch names.
        text = b"__import__('os').system('NEVER_RUN')"
        with patch.object(self.service, "_Log_ReadChunk", return_value=text):
            self.assertEqual(self.service.Log_DownloadTemporary("mock-fc-001", 1).result, Result.INTEGRITY_ERROR)

    def test_single_owner_conflict_release_and_fencing_generation(self):
        acquired = self.service.Lease_Acquire("mock-fc-001", "gshc", 5)
        generation = acquired.data["generation"]
        self.assertEqual(acquired.result, Result.OK)
        self.assertEqual(self.service.Lease_Acquire("mock-fc-001", "ai").result, Result.BUSY)
        self.assertEqual(self.service.Lease_Release("mock-fc-001", "ai", generation).result, Result.STALE)
        self.assertEqual(self.service.Lease_Release("mock-fc-001", "gshc", generation).result, Result.OK)
        new = self.service.Lease_Acquire("mock-fc-001", "gshc")
        self.assertGreater(new.data["generation"], generation)
        self.assertEqual(self.service.Lease_Release("mock-fc-001", "gshc", generation).result, Result.STALE)
        self.assertEqual(self.service.Lease_Release("mock-fc-001", "gshc", True).result, Result.STALE)

    def test_lease_expiry_invalidates_old_owner(self):
        old = self.service.Lease_Acquire("mock-fc-001", "gshc", 2)
        self.now = 102.0
        self.assertIsNone(self.service.Lease_Read("mock-fc-001").data["owner"])
        self.assertEqual(self.service.Lease_Acquire("mock-fc-001", "ai").result, Result.OK)
        self.assertEqual(self.service.Lease_Release("mock-fc-001", "gshc", old.data["generation"]).result,
                         Result.STALE)

    def test_lease_race_has_exactly_one_winner(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: self.service.Lease_Acquire("mock-fc-001", f"client-{i}"), range(8)))
        self.assertEqual(sum(reply.result == Result.OK for reply in results), 1)
        self.assertEqual(sum(reply.result == Result.BUSY for reply in results), 7)

    def test_lease_scope_and_argument_bounds_are_honest(self):
        self.service.Lease_Acquire("mock-fc-001", "gshc")
        other = MockDeviceService()
        self.assertEqual(other.Lease_Acquire("mock-fc-001", "ai").result, Result.OK)
        self.assertFalse(self.service.Lease_Read("mock-fc-001").data["hardware_exclusion"])
        for ttl in (0, 61, -1, float("nan"), float("inf"), True, "10", 10 ** 1000):
            self.assertEqual(self.service.Lease_Acquire("mock-rig-001", "ai", ttl).result, Result.BAD_ARGUMENT)
        for owner in ("", "x" * 65, "a\nb", [], None):
            self.assertEqual(self.service.Lease_Acquire("mock-rig-001", owner).result, Result.BAD_ARGUMENT)

    def test_cli_read_operations_json_and_exit_status(self):
        for args in (["devices"], ["status", "mock-fc-001"], ["capabilities", "mock-rig-001"],
                     ["collection", "mock-fc-001"], ["logs", "mock-fc-001"],
                     ["metadata", "mock-fc-001", "1"], ["lease", "mock-fc-001"], ["lease-demo"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = Cli_Main(args)
            body = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(body["mock"])
            self.assertFalse(body["hardware_access"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(Cli_Main(["status", "COM3"]), 1)
        self.assertEqual(json.loads(output.getvalue())["result"], "NOT_FOUND")

    def test_cli_download_and_rejection(self):
        with tempfile.TemporaryDirectory(prefix="device-service-cli-test-") as parent:
            with patch("device_service.tempfile.tempdir", parent), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(Cli_Main(["download", "mock-fc-001", "1"]), 0)
            body = json.loads(out.getvalue())
            self.assertEqual(Path(body["data"]["file_path"]).read_bytes(), b"123456789")
        for args in (["move"], ["delete"], ["status", "mock-fc-001", "--port", "COM3"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                Cli_Main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_source_has_no_transport_or_dynamic_execution_entry_points(self):
        # Narrow source check, not a security proof or sandbox for arbitrary Python callers.
        tree = ast.parse((ROOT / "device_service.py").read_text("utf-8"))
        forbidden = {"serial", "usb", "socket", "subprocess", "ctypes", "http", "importlib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(n.name.split(".")[0] not in forbidden for n in node.names))
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "__import__", "getattr"})


if __name__ == "__main__":
    unittest.main()
