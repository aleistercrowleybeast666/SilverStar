import errno
import json
import os
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError
from transport.file_service_backend import FileServiceSerialTransport


class MockTransport:
    def __init__(self, data=b"123456789", *, known=False):
        self.data = data
        self.commands = []
        self.request_id = 0
        self.pending = None
        self.known = known
        self.mutate = lambda response: response
        self.closed = False
        self.maintenance = 0

    @property
    def token(self):
        return f"1-{zlib.crc32(self.data):08X}-{len(self.data):08X}"

    def close(self):
        self.closed = True

    def prepare_job(self):
        pass

    def check_alive(self):
        pass

    def exchange(self, command, timeout, cancel):
        if cancel.is_set():
            raise ExportCancelled()
        self.commands.append(command)
        parts = command.split()
        op = parts[1]
        if op == "CAPS":
            return "OK LOGFILE CAPS file_service_version=1 supported=1 max_chunk=64 delete_supported=" + ("1" if self.known else "0") + " telemetry_bulk=0 device_id=" + ("device-1 boot_id=boot-1" if self.known else "unknown boot_id=unknown") + " status_version=1 maintenance_required=1 firmware=0.1.3"
        if op == "ENTER":
            self.maintenance = 2
            return "OK LOGFILE ENTER accepted=1 maintenance=1 reboot_required=1"
        if op == "STATUS":
            return self.mutate(f"OK LOGFILE STATUS status_version=1 source=FC_DEBUG_RAM sequence=1 age_ms=0 lifecycle=2 storage_valid=1 mounted=1 healthy=1 writer_open=0 log_fault=0 finalization=3 maintenance={self.maintenance} cleanup_pending=0 reboot_required={int(self.maintenance != 0)}")
        if op == "CANCEL":
            return "OK LOGFILE CANCEL cancelled=1"
        if op != "POLL":
            self.request_id += 1
            self.pending = parts
            return f"PENDING LOGFILE {op} request_id={self.request_id}"
        parts = self.pending
        op = parts[1]
        prefix = f"OK LOGFILE {op} request_id={self.request_id}"
        if op == "LIST":
            response = prefix + (f" file_id=1 size={len(self.data)} closed=1 next_cursor=1 end=0" if parts[2] == "0" else " end=1 next_cursor=0")
        elif op == "META":
            response = prefix + f" file_id=1 token={self.token} size={len(self.data)} crc32={zlib.crc32(self.data):08X} format=SSLOG format_version=0.0 closed=1"
        elif op == "READ":
            offset = int(parts[4])
            data = self.data[offset:offset + 64]
            response = prefix + f" file_id=1 token={self.token} offset={offset} length={len(data)} crc32={zlib.crc32(data):08X} data={data.hex().upper() or '-'}"
        elif op == "DELETE":
            response = prefix + " file_id=1 deleted=1"
        else:
            raise AssertionError(command)
        return self.mutate(response)


class FileServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_golden_download_and_listing_never_delete(self):
        wire = MockTransport()
        client = FileServiceClient(wire)
        self.assertEqual(client.list_closed(), [1])
        output = client.download(1, self.root)
        self.assertEqual(output.read_bytes(), b"123456789")
        contract = json.loads((Path(__file__).resolve().parents[3] / "contracts/log_file_service_v1.json").read_text())
        self.assertEqual(wire.token, contract["golden"]["token"])
        self.assertIn(contract["golden"]["read_request"].strip(), wire.commands)
        self.assertFalse(any("DELETE" in command for command in wire.commands))

    def test_bad_chunk_crc_preserves_source_and_does_not_publish(self):
        wire = MockTransport()
        wire.mutate = lambda text: text.replace("crc32=CBF43926 data=", "crc32=00000000 data=")
        with self.assertRaises(FileServiceError):
            FileServiceClient(wire).download(1, self.root)
        self.assertFalse(list(self.root.glob("*.sslog")))
        self.assertEqual(wire.data, b"123456789")

    def test_stale_request_and_offset_are_rejected(self):
        for change in (lambda text: text.replace("request_id=", "request_id=99"),
                       lambda text: text.replace("offset=0", "offset=1")):
            wire = MockTransport()
            wire.mutate = change
            with self.assertRaises(FileServiceError):
                FileServiceClient(wire).download(1, self.root)

    def test_active_log_and_busy_device_are_rejected(self):
        wire = MockTransport()
        wire.mutate = lambda text: text.replace("closed=1", "closed=0")
        with self.assertRaises(FileServiceError):
            FileServiceClient(wire).download(1, self.root)
        wire.mutate = lambda text: "ERR LOGFILE META request_id=1 code=BUSY"
        with self.assertRaises(FileServiceError):
            FileServiceClient(wire).download(1, self.root)

    def test_cancel_retains_partial_unknown_identity_restarts_from_zero(self):
        wire = MockTransport(bytes(range(200)))
        cancel = Event()
        with self.assertRaises(ExportCancelled):
            FileServiceClient(wire, cancel=cancel).download(1, self.root, progress=lambda *_: cancel.set())
        old = next(self.root.glob("*.partial"))
        old_bytes = old.read_bytes()
        metadata = json.loads(old.with_name(old.name + ".json").read_text())
        self.assertEqual(metadata["bytes_written"], len(old_bytes))
        self.assertFalse(metadata["verified"])
        self.assertFalse(metadata["resume_allowed"])
        self.assertEqual(metadata["device_id"], "unknown")
        self.assertEqual(metadata["status"], "cancelled")
        wire.commands.clear()
        output = FileServiceClient(wire).download(1, self.root)
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertTrue(next(cmd for cmd in wire.commands if " READ " in cmd).endswith(" 0"))

    def test_v1_nonunknown_strings_still_restart_and_keep_old_partial(self):
        wire = MockTransport(bytes(range(200)), known=True)
        cancel = Event()
        with self.assertRaises(ExportCancelled):
            FileServiceClient(wire, cancel=cancel).download(1, self.root, progress=lambda *_: cancel.set())
        partial = next(self.root.glob("*.partial"))
        partial.write_bytes(b"old partial remains")
        output = FileServiceClient(wire).download(1, self.root)
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual(partial.read_bytes(), b"old partial remains")

    def test_v1_nonunknown_strings_never_reuse_changed_prefix(self):
        wire = MockTransport(bytes(range(200)), known=True)
        cancel = Event()
        with self.assertRaises(ExportCancelled):
            FileServiceClient(wire, cancel=cancel).download(1, self.root, progress=lambda *_: cancel.set())
        partial = next(self.root.glob("*.partial"))
        partial.write_bytes(b"corrupt")
        output = FileServiceClient(wire).download(1, self.root)
        self.assertEqual(partial.read_bytes(), b"corrupt")
        self.assertEqual(output.read_bytes(), wire.data)

    def test_unknown_identity_refuses_delete_even_if_advertised(self):
        wire = MockTransport()
        client = FileServiceClient(wire)
        with self.assertRaises(FileServiceError):
            client.prepare_delete(1)
        self.assertFalse(any("DELETE" in cmd for cmd in wire.commands))

    def test_v1_delete_refuses_unrecognized_identity_strings(self):
        wire = MockTransport(known=True)
        client = FileServiceClient(wire)
        with self.assertRaises(FileServiceError):
            client.prepare_delete(1)
        selected = client.metadata(1)
        with self.assertRaises(FileServiceError):
            client.delete(selected, confirmed_token=selected.token)
        self.assertFalse(any(" DELETE " in cmd for cmd in wire.commands))

    def test_timeout_does_not_publish(self):
        class TimeoutTransport(MockTransport):
            def exchange(self, command, timeout, cancel):
                raise TimeoutError("mock timeout")
        with self.assertRaises(TimeoutError):
            FileServiceClient(TimeoutTransport()).download(1, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_responsive_long_pending_has_no_whole_operation_timeout(self):
        class LongMetaTransport(MockTransport):
            simulated_elapsed = 0
            def exchange(self, command, timeout, cancel):
                if command.startswith("LOGFILE POLL") and self.pending[1] == "META" and self.simulated_elapsed < 120:
                    self.simulated_elapsed += 31
                    return f"PENDING LOGFILE META request_id={self.request_id}"
                return super().exchange(command, timeout, cancel)
        wire = LongMetaTransport()
        with patch("services.file_service_client.Event.wait", return_value=False):
            output = FileServiceClient(wire).download(1, self.root)
        self.assertGreater(wire.simulated_elapsed, 30)
        self.assertEqual(output.read_bytes(), wire.data)

    def test_existing_target_is_never_overwritten(self):
        wire = MockTransport()
        output = FileServiceClient(wire).download(1, self.root)
        with self.assertRaises(FileExistsError):
            FileServiceClient(wire).download(1, self.root)
        self.assertEqual(output.read_bytes(), wire.data)

    def test_unicode_space_directory_and_success_removes_only_own_checkpoint(self):
        destination = self.root / "下载 日志"
        destination.mkdir()
        retained = destination / "user.partial.json"
        retained.write_text("retain this user file")
        wire = MockTransport()
        output = FileServiceClient(wire).download(1, destination)
        self.assertEqual(output.read_bytes(), wire.data)
        self.assertEqual(retained.read_text(), "retain this user file")
        self.assertEqual(sorted(path.name for path in destination.iterdir()), sorted([output.name, retained.name]))

    def test_insufficient_space_stops_before_read_and_partial_creation(self):
        wire = MockTransport()
        with patch("services.file_service_client.shutil.disk_usage", return_value=SimpleNamespace(free=0)), self.assertRaises(OSError):
            FileServiceClient(wire).download(1, self.root)
        self.assertFalse(any(" READ " in command for command in wire.commands))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(wire.data, b"123456789")

    def test_revoked_permission_and_disk_full_write_preserve_remote_source(self):
        original_open = Path.open
        for revoke in (True, False):
            destination = self.root / str(revoke)
            destination.mkdir()
            wire = MockTransport()
            class FullDisk:
                def __init__(self, fp): self.fp = fp
                def __enter__(self): return self
                def __exit__(self, *args): self.fp.close()
                def __getattr__(self, name): return getattr(self.fp, name)
                def write(self, data): raise OSError(errno.ENOSPC, "mock disk full")
            def open_file(path, *args, revoked=revoke, **kwargs):
                if path.suffix == ".partial" and args and args[0] == "xb":
                    if revoked:
                        raise PermissionError("mock permission revoked")
                    return FullDisk(original_open(path, *args, **kwargs))
                return original_open(path, *args, **kwargs)
            with patch.object(Path, "open", open_file), self.assertRaises(OSError):
                FileServiceClient(wire).download(1, destination)
            self.assertFalse(list(destination.glob("*.sslog")))
            metadata = json.loads(next(destination.glob("*.partial.json")).read_text())
            self.assertFalse(metadata["verified"])
            self.assertFalse(metadata["resume_allowed"])
            self.assertEqual(metadata["bytes_written"], 0)
            self.assertEqual(wire.data, b"123456789")

    def test_final_data_fsync_failure_preserves_partial_with_unverified_metadata(self):
        wire = MockTransport()
        real_fsync = os.fsync
        calls = 0
        def fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError(errno.ENOSPC, "mock data fsync full")
            return real_fsync(fd)
        with patch("services.file_service_client.os.fsync", side_effect=fsync), self.assertRaises(OSError):
            FileServiceClient(wire).download(1, self.root)
        self.assertFalse(list(self.root.glob("*.sslog")))
        metadata = json.loads(next(self.root.glob("*.partial.json")).read_text())
        self.assertEqual(metadata["bytes_written"], len(wire.data))
        self.assertFalse(metadata["verified"])
        self.assertEqual(wire.data, b"123456789")

    def test_serial_adapter_is_bounded_and_checks_write(self):
        class FakeSerial:
            def __init__(self, **_):
                self.data = []
            def write(self, data):
                if data == b"SYSTEM INFO\r\n":
                    self.data = [b"OK SYSTEM INFO project=SilverStar version=0.0.12\r\n"]
                    return len(data)
                self.data = [b"> LOGFILE CAPS\r\n", b"OK LOGFILE CAPS supported=1\r\n"]
                return len(data)
            def read(self, count): return self.data.pop(0) if self.data else b""
            def close(self): pass
        transport = FileServiceSerialTransport("MOCK", 115200, serial_factory=FakeSerial)
        self.assertEqual(transport.exchange("LOGFILE CAPS", 1, Event()), "OK LOGFILE CAPS supported=1")
        with self.assertRaises(ValueError):
            transport.exchange("LOGFILE CAPS\nDELETE", 1, Event())


if __name__ == "__main__":
    unittest.main()
