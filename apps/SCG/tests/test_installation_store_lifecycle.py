"""Actual C coordinator with explicitly supplied I/O outcomes; no hardware.

Full FatFs/SSOB red/green evidence is separate. This small regression exercises
every cancellable phase and the confirmed-commit publication boundary.
"""
import ctypes as c
import hashlib
import importlib.util
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "plugins/builtin"
CORE = BUILTIN / "silverstar_core_0_1_0/payload"
PAYLOAD = BUILTIN / "silverstar_installation_capture/payload"
EXPERIMENT = ROOT / "experiments/installation_capture_stream_0_1_3/implementation_v1"
spec = importlib.util.spec_from_file_location("installation_store_c_binding", EXPERIMENT / "c_binding.py")
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)
u8, u16, u32, u64 = c.c_uint8, c.c_uint16, c.c_uint32, c.c_uint64


class Work(c.Structure):
    _fields_ = [("action", c.c_int)] + [(name, u32) for name in
        ("request_id", "token", "expected_generation", "total_bytes", "offset")] + [
        ("object_sha256", u8 * 32), ("binding_sha256", u8 * 32), ("data", u8 * 64),
        ("length", u16), ("final_blob", u8)]


class Status(c.Structure):
    _fields_ = [(name, u32) for name in ("request_id", "completed_bytes", "total_bytes", "generation")] + [
        ("result", c.c_int), ("cleanup_complete", u8), ("candidate_only", u8)]


@pytest.fixture(scope="module")
def dll(tmp_path_factory):
    gcc = shutil.which("gcc")
    assert gcc, "Host GCC is required for actual C lifecycle regressions"
    output = tmp_path_factory.mktemp("installation-store") / "coordinator.dll"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-Wswitch-enum", "-shared",
               "-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1", "-DRYU_ONLY_64_BIT_OPS"]
    code = PAYLOAD / "Modules/InstallationCapture"
    for directory in [ROOT / "tests/fixtures/installation_store", code / "Inc", code / "Src", PAYLOAD / "ThirdParty/InstallationCapture", EXPERIMENT,
                      EXPERIMENT / "fixtures", CORE / "Common/Inc", CORE / "Interfaces/Inc",
                      CORE / "System/Inc"]:
        command += ["-I", str(directory)]
    sources = [EXPERIMENT / name for name in ("capture_test_access.c", "capture_port_host.c", "integration_stubs.c")]
    sources += [code / "Src" / name for name in ("capture_info.c", "capture_primitives.c", "installation_lease.c", "installation_store.c")]
    sources += [PAYLOAD / "ThirdParty/InstallationCapture/ryu/d2s.c", ROOT / "tests/fixtures/installation_store_host.c"]
    result = subprocess.run([*command, *map(str, sources), "-o", str(output)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return output


class Session:
    def __init__(self, dll):
        self.capture = binding.Library(str(dll))
        self.capture.configure()
        self.capture.begin()
        assert self.capture.Cancel(self.capture.sid, 2, 0) == 10
        assert self.capture.ProducerStopped() == 12
        assert self.capture.Release() == 0
        self.dll = self.capture.dll
        ptr = c.POINTER
        for name, args in {
            "Begin": [ptr(u8), u32, u32, u32, ptr(u8), ptr(u8), u64],
            "Write": [ptr(u8), u32, u32, ptr(u8), u16, u64], "Verify": [ptr(u8), u32, u64],
            "Cancel": [ptr(u8), u32, u64], "Status": [ptr(u8), u32, u64, ptr(Status)],
            "WorkTake": [u64, ptr(Work)], "WorkComplete": [ptr(Work), c.c_int, u32, u32, u64],
        }.items():
            function = getattr(self.dll, "SystemInstallationStore_" + name)
            function.argtypes, function.restype = args, c.c_int
            setattr(self, name, function)
        body = b'{"candidate_only":true,"validation":"mock_io_outcomes"}'
        header = bytearray(40)
        header[:8] = b"SSIC" + bytes((1, 2, 1, 2))
        struct.pack_into("<HHB", header, 8, 1, 1, 0)
        struct.pack_into("<I", header, 16, 0x12345678)
        struct.pack_into("<II", header, 32, len(body), zlib.crc32(body))
        self.payload = bytes(header) + body
        self.rid, self.now = 10, 10
        digest = (u8 * 32).from_buffer_copy(hashlib.sha256(self.payload).digest())
        frozen = (u8 * 32).from_buffer_copy(bytes(self.capture.status().binding))
        assert self.Begin(self.capture.sid, self.rid, 0, len(self.payload), digest, frozen, self.now) == 1

    def take(self):
        self.now += 1
        work = Work()
        assert self.WorkTake(self.now, c.byref(work)) == 1
        return work

    def complete(self, work, result=0):
        progress, generation = 0, 0
        if work.action == 2:
            progress = work.offset + work.length
        elif work.action == 3:
            work.data[:work.length] = self.payload[work.offset:work.offset + work.length]
        elif work.action == 5:
            generation = 1
        self.now += 1
        assert self.WorkComplete(c.byref(work), result, progress, generation, self.now) == 0

    def phase(self, action):
        self.complete(self.take())  # Open.
        if action == 1:
            raise AssertionError("Open must be taken before preparation")
        for offset in range(0, len(self.payload), 64):
            data = self.payload[offset:offset + 64]
            self.rid += 1
            assert self.Write(self.capture.sid, self.rid, offset, (u8 * len(data)).from_buffer_copy(data), len(data), self.now) == 1
            work = self.take()
            if action == 2:
                return work
            self.complete(work)
        self.rid += 1
        assert self.Verify(self.capture.sid, self.rid, self.now) == 1
        for _ in range(1024):
            work = self.take()
            if work.action == action:
                return work
            self.complete(work)
        raise AssertionError("bounded phase progression failed")

    def status(self):
        value = Status()
        result = self.Status(self.capture.sid, self.rid, self.now, c.byref(value))
        return result, value


@pytest.mark.parametrize("phase", range(1, 6))
@pytest.mark.parametrize("event", ("cancel", "timeout"))
def test_late_cancel_or_timeout_reports_actual_publication(dll, phase, event):
    session = Session(dll)
    work = session.take() if phase == 1 else session.phase(phase)
    if event == "cancel":
        session.rid += 1
        assert session.Cancel(session.capture.sid, session.rid, session.now) == 1
    else:
        session.now += 30000000
    session.complete(work)
    result, status = session.status()
    assert result == (10 if phase == 5 else 9)
    assert status.generation == (1 if phase == 5 else 0)
    assert status.candidate_only == 1 and status.cleanup_complete == 1
    assert session.capture.status().resource_owner == 0
    token = u32()
    assert session.capture.ResourceClaim(2, c.byref(token)) == 0
    assert session.WorkComplete(c.byref(work), 0, 0, 1, session.now) == 4
    assert session.capture.status().resource_owner == 2


def test_unconfirmed_commit_retains_owner_even_after_cancel(dll):
    session = Session(dll)
    work = session.phase(5)
    session.rid += 1
    assert session.Cancel(session.capture.sid, session.rid, session.now) == 1
    session.complete(work, result=8)
    assert session.status()[0] == 8
    assert session.capture.status().resource_owner == 11
    assert session.WorkComplete(c.byref(work), 0, 0, 1, session.now) == 4
    assert session.capture.status().resource_owner == 11


def test_queued_store_data_is_a_copy_of_the_callers_buffer(dll):
    session = Session(dll)
    session.complete(session.take())
    data = session.payload[:64]
    source = (u8 * len(data)).from_buffer_copy(data)
    session.rid += 1
    assert session.Write(session.capture.sid, session.rid, 0, source, len(data), session.now) == 1
    source[:] = b"\xff" * len(data)
    work = session.take()
    assert work.action == 2 and bytes(work.data[:work.length]) == data


@pytest.mark.parametrize("fault", ("previous_session_time", "previous_epoch"))
def test_late_native_data_cannot_enter_the_new_capture(dll, fault):
    capture = binding.Library(str(dll))
    capture.configure()
    capture.begin()
    assert capture.face() == 10
    old = capture.sample(0, 0, 0)
    assert capture.Cancel(capture.sid, 3, 500) == 10
    assert capture.ProducerStopped() == 12 and capture.Release() == 0
    capture.sid = (u8 * 16).from_buffer_copy(bytes.fromhex("2" * 32))
    frozen = (u8 * 15).from_buffer_copy(bytes(capture.status().binding[:15]))
    assert capture.Begin(capture.sid, 1, frozen, 100000) == 0
    assert capture.face(now=100000) == 10
    if fault == "previous_epoch":
        old.sample_us, old.receive_us = 100100, 100300
        old.epoch += 1  # Wrong provenance, even with a newly received timestamp.
    assert capture.SourcePush(0, c.byref(old), 100300) == 8
    assert capture.status().train_count == 0
