"""Offline B1/B2 normal/fault tests; synthetic clocks and sources only."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import zlib

import pytest

from .capture import (BoundedCollector, CapturePolicy, CaptureResult, CapturedPair,
                     SourceDescriptor, SourceSample, WindowTag)
from .protocol import (LineFramer, PairAssembler, ProtocolError, ProtocolResult, Request,
    Request_Decode, Request_Encode, Response, Response_Decode, Response_Encode,
    SamplePart_Decode, SamplePart_Encode)
from .prototype import CandidateReport, CandidateResult, FACES, InstallationSession, Policy
from .session import (CandidateAttachResult, Capability_Decode, CapabilityResult, OfflineSession,
                     ResourceGate, State_Decode, UploadSpec)
from .synthetic_cases import Case_Build

SID, OTHER = "1"*32, "2"*32
CONTEXT = "B-"+"3"*30
EVIDENCE = {}
ARCHIVE = {}


@pytest.fixture(scope="module", autouse=True)
def evidence():
    yield
    destination = os.environ.get("INSTALL_CAL_EVIDENCE")
    if destination:
        target = Path(destination).resolve()
        prefix = os.environ.get("INSTALL_CAL_PREFIX", "")
        assert target.is_relative_to((Path(__file__).resolve().parents[4]/".work/dev013_installation_calibration_20261018").resolve())
        (target/(prefix+"capture_session_cases.json")).write_text(json.dumps(EVIDENCE, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if ARCHIVE:
            (target/(prefix+"capture_archive.json")).write_text(json.dumps(ARCHIVE, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def fixture():
    case = Case_Build()
    imu = SourceDescriptor("IMU", case.accel.identity, ("m/s2", "rad/s"), "SYNTHETIC_TRUTH",
        "BOOT_MONOTONIC", "SYNTHETIC_SHARED_CLOCK", case.accel.calibration_id, case.accel.generation, 3, boot="boot1")
    mag = SourceDescriptor("MAG", case.mag.identity, ("uT",), "SYNTHETIC_TRUTH",
        "BOOT_MONOTONIC", "SYNTHETIC_SHARED_CLOCK", case.mag.calibration_id, case.mag.generation, 4, boot="boot1")
    return case, imu, mag


def samples(imu, mag, n=1, case_row=None):
    t = n*1000
    av = (*case_row.accel, *case_row.gyro) if case_row else (9.7, -.08, .06, .003, -.005, .002)
    mv = case_row.magnetic if case_row else (20., 30., 40.)
    return (SourceSample(imu, n, t, t+200, 10**12+t, 20, av, temperature_c=25., raw_counts=(1, 2, 3, 4, 5, 6)),
            SourceSample(mag, n, t+100, t+300, 2*10**12+t, 30, mv, raw_counts=(7, 8, 9)))


def collector(policy=CapturePolicy()):
    _, imu, mag = fixture()
    value = BoundedCollector(SID, "boot1", imu, mag, policy)
    assert value.Start(WindowTag("SIX_FACE", "XP", "w1", "p1", "TRAIN"), 0) == CaptureResult.Accepted
    return value, imu, mag


def feed_pairs(value, imu, mag, start=1, count=3):
    for n in range(start, start+count):
        a, m = samples(imu, mag, n)
        assert value.Feed(a, n*1000+300) == CaptureResult.Accepted
        assert value.Feed(m, n*1000+300) == CaptureResult.Paired


def owner(gate=None, upload=None):
    case, imu, mag = fixture()
    value = OfflineSession("boot1", imu, mag, case.accel, case.mag, gate, upload=upload)
    result = value.Handle(f"INSTALL BEGIN {SID} 1 {value.binding}".encode(), 0)
    assert result.status == "OK"
    return value, imu, mag


def action(value, rid, name, now=None):
    return value.Handle(f"INSTALL DO {SID} {rid} {name}".encode(), value.now if now is None else now)


def test_bounded_capture_preserves_raw_counts_units_clock_and_completed_windows():
    value, imu, mag = collector(); feed_pairs(value, imu, mag)
    assert value.Stop(3400) == CaptureResult.Complete
    rows = value.StaticRecords(); assert len(rows) == 3
    assert rows[0].imu_us == 1000 and rows[0].mag_us == 1100
    assert rows[0].time_uncertainty_us == 50 and rows[0].clock == "BOOT_MONOTONIC"
    assert rows[0].acquisition_intrinsic_generations == (7, 11)
    assert value.archive[0][1].pc_receive_us != value.archive[0][1].receive_us
    assert value.pairs[0].imu.raw_counts == (1, 2, 3, 4, 5, 6)
    assert value.pairs[0].imu.descriptor.units == ("m/s2", "rad/s")
    assert value.Snapshot()["outcomes"] == (("w1", "COMPLETE"),)
    EVIDENCE["completed_window"] = {k: v for k, v in value.Snapshot().items() if k not in ("archive", "records")}


@pytest.mark.parametrize("change,reason", [
    ({"sequence": 3}, "SOURCE_SEQUENCE_GAP_OR_REORDER"),
    ({"sequence": 1}, "SOURCE_SEQUENCE_GAP_OR_REORDER"),
    ({"sample_us": 900}, "SOURCE_SEQUENCE_GAP_OR_REORDER"),
    ({"flags": ("GAP",)}, "SOURCE_QUALITY_OR_TIME_UNCERTAIN"),
    ({"uncertainty_us": 1001}, "SOURCE_QUALITY_OR_TIME_UNCERTAIN"),
    ({"receive_us": 0}, "SOURCE_QUALITY_OR_TIME_UNCERTAIN"),
])
def test_source_faults_fail_window_and_keep_offending_record(change, reason):
    value, imu, mag = collector(); feed_pairs(value, imu, mag, count=1)
    a, _ = samples(imu, mag, 2)
    assert value.Feed(replace(a, **change), 2300) == CaptureResult.Failed
    assert value.reason == reason and len(value.archive) == 3
    assert not value.StaticRecords()  # Earlier good pairs from failed window are excluded.
    EVIDENCE[reason] = value.reason


@pytest.mark.parametrize("change", [{"clock": "PC_RECEIVE_PROXY"}, {"clock_provenance": "UNKNOWN"},
                                  {"frame_provenance": "UNKNOWN"}, {"boot": "UNKNOWN"}])
def test_missing_source_evidence_cannot_start(change):
    _, imu, mag = fixture(); imu = replace(imu, **change)
    value = BoundedCollector(SID, "boot1", imu, mag)
    assert value.Start(WindowTag("SIX_FACE", "XP", "w", "p", "TRAIN"), 0) == CaptureResult.Failed


def test_explicit_sequence_stride_and_uint32_wrap_are_not_timestamp_wrap():
    _, imu, mag = fixture(); imu = replace(imu, sequence_stride=2); mag = replace(mag, sequence_stride=2)
    value = BoundedCollector(SID, "boot1", imu, mag)
    value.Start(WindowTag("SIX_FACE", "XP", "w", "p", "TRAIN"), 0)
    for n, seq in ((1, 2**32-2), (2, 0), (3, 2)):
        a, m = samples(imu, mag, n)
        assert value.Feed(replace(a, sequence=seq), n*1000+300) == CaptureResult.Accepted
        assert value.Feed(replace(m, sequence=seq), n*1000+300) == CaptureResult.Paired
    assert value.Stop(3400) == CaptureResult.Complete


def test_saturating_timestamp_epoch_parent_changes_and_wrong_units():
    value, imu, mag = collector()
    with pytest.raises(ValueError): replace(imu, units=("g", "deg/s"))
    with pytest.raises(ValueError): replace(imu, axis_mapping_applied=(-1, 2, 3))
    with pytest.raises(ValueError): replace(imu, handedness="LEFT")
    a, _ = samples(imu, mag)
    assert value.Feed(replace(a, descriptor=replace(imu, epoch=4)), 1300) == CaptureResult.Failed
    _, imu, mag = fixture(); imu = replace(imu, sample_time_bits=32, timestamp_saturates=True)
    value = BoundedCollector(SID, "boot1", imu, mag)
    value.Start(WindowTag("SIX_FACE", "XP", "w", "p", "TRAIN"), 2**32-200)
    a, _ = samples(imu, mag)
    a = replace(a, sample_us=2**32-1, receive_us=2**32)
    assert value.Feed(a, 2**32) == CaptureResult.Failed and value.reason == "SAMPLE_TIME_SATURATED"


def test_source_pair_archive_overflow_never_silently_drops_or_wraps():
    for policy, reason in ((CapturePolicy(source_capacity=1), "SOURCE_BUFFER_FULL"),
                           (CapturePolicy(pair_capacity=3), "PAIR_BUFFER_FULL"),
                           (CapturePolicy(archive_capacity=1), "ARCHIVE_BUFFER_FULL")):
        value, imu, mag = collector(policy)
        if reason == "SOURCE_BUFFER_FULL":
            value.Feed(samples(imu, mag, 1)[0], 1300)
            result = value.Feed(samples(imu, mag, 2)[0], 2300)
        elif reason == "ARCHIVE_BUFFER_FULL":
            value.Feed(samples(imu, mag, 1)[0], 1300)
            result = value.Feed(samples(imu, mag, 1)[1], 1300)
        else:
            feed_pairs(value, imu, mag)
            value.Feed(samples(imu, mag, 4)[0], 4300)
            result = value.Feed(samples(imu, mag, 4)[1], 4300)
        assert result == CaptureResult.Failed and value.reason == reason
        assert value.overflow_count == 1 and len(value.pairs) <= policy.pair_capacity
        assert len(value.archive) <= policy.archive_capacity and not value.StaticRecords()
        EVIDENCE[reason] = {"overflow_count": value.overflow_count, "archive": len(value.archive), "pairs": len(value.pairs)}


def test_skew_missing_source_window_deadline_and_cancel():
    value, imu, mag = collector(); a, m = samples(imu, mag)
    value.Feed(a, 4300)
    assert value.Feed(replace(m, sample_us=4000, receive_us=4300), 4300) == CaptureResult.Failed
    assert value.reason == "PAIR_SKEW_OR_UNCERTAINTY"
    value, imu, mag = collector()
    value.Feed(samples(imu, mag)[0], 1300)
    assert value.Poll(250000) == CaptureResult.Failed and value.reason == "SOURCE_TIMEOUT"
    value, _, _ = collector(CapturePolicy(source_timeout_us=100, window_timeout_us=200))
    assert value.Poll(200) == CaptureResult.Failed and value.reason == "WINDOW_TIMEOUT"
    value, imu, mag = collector(); feed_pairs(value, imu, mag, count=1)
    before = value.Snapshot()["archive"]
    assert value.Cancel() == CaptureResult.Cancelled
    assert value.Feed(samples(imu, mag, 2)[0], 2300) == CaptureResult.Rejected
    assert value.Snapshot()["archive"] == before and not value.StaticRecords()


def test_bad_next_window_start_preserves_completed_window_history():
    value, imu, mag = collector(); feed_pairs(value, imu, mag)
    value.Stop(3400); before = value.StaticRecords()
    assert value.Start(WindowTag("SIX_FACE", "XN", "w2", "p2", "TRAIN"), 3000) == CaptureResult.Failed
    assert value.StaticRecords() == before and value.outcomes["w1"] == "COMPLETE"


@pytest.mark.parametrize("body", [b"INSTALL CAPS", b"INSTALL INFO 0:255 0",
    f"INSTALL BEGIN {SID} 4294967295 {CONTEXT}".encode(),
    f"INSTALL DO {SID} 2 FACE_ZN".encode(), f"INSTALL POLL {SID} 2".encode(),
    f"INSTALL STATUS {SID} CANDIDATE:0".encode(), f"INSTALL STATUS {CONTEXT} SAVED:0".encode(),
    f'INSTALL READ {SID} S-{"4"*30} 48'.encode(),
    f'INSTALL PUT {SID} 4294967295 4294967295:{"FF"*48}'.encode()])
def test_command_golden_roundtrip_and_191_byte_five_token_budget(body):
    parsed = Request_Decode(body)
    assert Request_Encode(parsed) == body+b"\r\n"
    assert len(body) <= 191 and len(body.split()) <= 5
    EVIDENCE.setdefault("request_golden", []).append(body.decode())


@pytest.mark.parametrize("body", [b"INSTALL CAPS EXTRA", b"INSTALL DO x 0 APPLY", b"INSTALL INFO 256:0 0",
    f"INSTALL DO {SID} 01 APPLY".encode(), f"INSTALL DO {SID} 1 UNKNOWN".encode(),
    f"INSTALL PUT {SID} 1 0:ff".encode(), f"INSTALL PUT {SID} 1 0:ABC".encode(),
    f"INSTALL STATUS {CONTEXT} STATE:0".encode(), b"INSTALL CAPS\x00", b"X"*192])
def test_malformed_commands_never_reach_state_machine(body):
    with pytest.raises(ProtocolError): Request_Decode(body)


def test_line_framing_discontinuity_overlong_echo_and_complete_response_match():
    framer = LineFramer(191)
    assert framer.Feed(b"INSTALL CA") == ()
    framer.Discontinuity()
    assert framer.Feed(b"PS\r\nINSTALL CAPS\r\n") == (b"INSTALL CAPS",)
    result = framer.Feed(b"X"*192+b"\r\nINSTALL CAPS\n")
    assert isinstance(result[0], ProtocolError) and result[1] == b"INSTALL CAPS"
    with pytest.raises(ProtocolError): framer.Feed(b"X"*257)
    response = Response("PENDING", "DO", (("sid", SID), ("rid", "3"), ("action", "CANCEL")))
    line = Response_Encode(response)[:-2]
    assert Response_Decode(line, "DO", SID, 3) == response
    for args in (("POLL", SID, 3), ("DO", OTHER, 3), ("DO", SID, 4)):
        with pytest.raises(ProtocolError): Response_Decode(line, *args)
    for bad in (line+b" rid=3", b"OK INSTALL STATUS state=", b"LOG random", b"OK INSTALL CAPS\x00"):
        with pytest.raises(ProtocolError): Response_Decode(bad)


def test_sample_parts_preserve_all_fields_crc_and_binding_without_latest_substitution():
    value, imu, mag = collector(); feed_pairs(value, imu, mag, count=1)
    pair = value.pairs[0]; a, m = (SamplePart_Encode(pair, x, CONTEXT)[:-2] for x in ("IMU", "MAG"))
    assert max(len(a), len(m)) <= 511
    assembly = PairAssembler(SID, CONTEXT, "boot1", {"IMU": imu, "MAG": mag})
    assert assembly.Feed(m, 0) is None and assembly.Feed(m, 1) is None
    expected=replace(pair,imu=replace(pair.imu,pc_receive_us=0),mag=replace(pair.mag,pc_receive_us=0))
    assert assembly.Feed(a, 2) == expected  # Host clock is stamped by the GSHC reader, never supplied by firmware.
    assert assembly.Feed(a, 3) is None
    broken = a.replace(b"data=", b"data=FF", 1)
    with pytest.raises(ProtocolError): SamplePart_Decode(broken, SID, CONTEXT, assembly.descriptors)
    with pytest.raises(ProtocolError): SamplePart_Decode(a, OTHER, CONTEXT, assembly.descriptors)
    EVIDENCE["sample_golden"] = {"imu": a.decode(), "mag": m.decode(), "max_line_bytes": max(len(a), len(m)),
        "imu_descriptor": asdict(imu), "mag_descriptor": asdict(mag)}


def test_assembly_missing_parts_timeout_conflicts_overflow_and_sequence_gap():
    value, imu, mag = collector(); feed_pairs(value, imu, mag)
    sources = {"IMU": imu, "MAG": mag}
    a = SamplePart_Encode(value.pairs[0], "IMU", CONTEXT)[:-2]
    assembly = PairAssembler(SID, CONTEXT, "boot1", sources, capacity=1, timeout_us=100)
    assembly.Feed(a, 0)
    with pytest.raises(ProtocolError) as error: assembly.Poll(100)
    assert error.value.code == ProtocolResult.Timeout and assembly.requires_resample
    with pytest.raises(ProtocolError): assembly.Feed(a, 101)
    assembly = PairAssembler(SID, CONTEXT, "boot1", sources, capacity=1)
    assembly.Feed(a, 0)
    changed = replace(value.pairs[0], imu=replace(value.pairs[0].imu, values=(1.,)*6))
    with pytest.raises(ProtocolError) as error: assembly.Feed(SamplePart_Encode(changed, "IMU", CONTEXT)[:-2], 1)
    assert error.value.code == ProtocolResult.Conflict
    assembly = PairAssembler(SID, CONTEXT, "boot1", sources, capacity=1)
    assembly.Feed(a, 0)
    with pytest.raises(ProtocolError) as error: assembly.Feed(SamplePart_Encode(value.pairs[1], "MAG", CONTEXT)[:-2], 2)
    assert error.value.code == ProtocolResult.Overflow
    assembly = PairAssembler(SID, CONTEXT, "boot1", sources)
    assembly.Feed(SamplePart_Encode(value.pairs[1], "IMU", CONTEXT)[:-2], 0)
    with pytest.raises(ProtocolError) as error: assembly.Feed(SamplePart_Encode(value.pairs[1], "MAG", CONTEXT)[:-2], 1)
    assert error.value.code == ProtocolResult.Stale and assembly.requires_resample


def test_sample_maxima_fit_one_line_and_mag_motion_cannot_be_static_gravity():
    _, imu, mag = fixture()
    tag = WindowTag("MAG_ROTATE", "NA", "w"*16, "p"*16, "HOLDOUT", 65535)
    a, m = samples(imu, mag)
    a = replace(a, sequence=2**32-1, sample_us=2**64-1, receive_us=2**64-1, pc_receive_us=2**64-1, uncertainty_us=2**32-1)
    pair = CapturedPair(SID, "boot1", 2**32-1, tag, a, m)
    for role in ("IMU", "MAG"):
        line = SamplePart_Encode(pair, role, CONTEXT)[:-2]
        assert len(line) <= 511
        assert SamplePart_Decode(line, SID, CONTEXT, {"IMU": imu, "MAG": mag})[3] == replace(getattr(pair,role.lower()),pc_receive_us=0)
    with pytest.raises(ValueError): pair.RawPair()


def test_reassembled_samples_cannot_bypass_source_quality_or_declared_sequence_stride():
    value, imu, mag = collector(); feed_pairs(value, imu, mag, count=2)
    for change in ("GAP_FLAG", "SEQUENCE_GAP"):
        assembly = PairAssembler(SID, CONTEXT, "boot1", {"IMU": imu, "MAG": mag})
        first = value.pairs[0]
        assembly.Feed(SamplePart_Encode(first, "IMU", CONTEXT)[:-2], 0)
        assert assembly.Feed(SamplePart_Encode(first, "MAG", CONTEXT)[:-2], 1) == replace(first,
            imu=replace(first.imu,pc_receive_us=0),mag=replace(first.mag,pc_receive_us=0))
        second = value.pairs[1]
        altered = replace(second.imu, flags=("GAP",)) if change == "GAP_FLAG" else replace(second.imu, sequence=3)
        second = replace(second, imu=altered)
        assembly.Feed(SamplePart_Encode(second, "IMU", CONTEXT)[:-2], 2)
        with pytest.raises(ProtocolError): assembly.Feed(SamplePart_Encode(second, "MAG", CONTEXT)[:-2], 3)
        assert assembly.requires_resample


def test_capability_probe_never_infers_install_from_maintenance_or_timeout():
    value, _, _ = owner()
    line = Response_Encode(value.Handle(b"INSTALL CAPS", 0))[:-2]
    assert Capability_Decode(line) == CapabilityResult.Supported
    assert Capability_Decode(b"ERR INSTALL CAPS code=BAD_MODULE reason=UNKNOWN") == CapabilityResult.Unsupported
    assert Capability_Decode(b"ERR INSTALL CAPS code=UNSUPPORTED reason=CAPABILITY") == CapabilityResult.Unsupported
    for body in (b"", b"OK SYSTEM DIAG maintenance=0.1", b"OK INSTALL CAPS supported=1",
                 line.replace(b"apply=0", b"apply=1"), line.replace(b"pair_capacity=32 ", b"")):
        assert Capability_Decode(body) == CapabilityResult.Unknown
    EVIDENCE["caps_golden"] = line.decode()


def test_state_reply_requires_complete_matched_fields_and_never_implies_ready():
    value, _, _ = owner()
    line = Response_Encode(value.Handle(f"INSTALL STATUS {SID} STATE:0".encode(), 0))[:-2]
    state = State_Decode(line, SID)
    assert state.phase == "IDLE" and state.face_mask == 0 and not state.cleanup_complete
    assert State_Decode(line.replace(b"state=IDLE", b"state=FUTURE_PHASE"), SID).phase == "UNKNOWN"
    for bad in (line.replace(b"apply=0", b"apply=1"), line.replace(b"face_mask=0 ", b""),
                line.replace(b"face_mask=0", b"face_mask=64"), line.replace(SID.encode(), OTHER.encode())):
        with pytest.raises(ValueError): State_Decode(bad, SID)


def test_repeat_commands_conflict_stale_rid_wrap_and_cancel_cleanup_are_distinct():
    value, imu, mag = owner(); request = f"INSTALL DO {SID} 2 MAG_START".encode()
    first = value.Handle(request, 0); assert first.status == "OK"
    assert value.Handle(request, 1) == first and len(value.collector.windows) == 1
    assert action(value, 2, "MAG_STOP").Field("code") == "CONFLICT"
    pending = action(value, 3, "CANCEL")
    assert pending.status == "PENDING" and pending.Field("cleanup_complete") == "0"
    assert value.gate.owner == SID and value.collector.state == "CANCELLED"
    assert value.Handle(f"INSTALL POLL {SID} 3".encode(), 2) == pending
    assert action(value, 4, "MAG_START").Field("code") == "BUSY"
    value.Process(3)
    terminal = value.Handle(f"INSTALL POLL {SID} 3".encode(), 3)
    assert terminal.operation == "DO" and terminal.status == "OK" and terminal.Field("cleanup_complete") == "1"
    assert value.gate.owner is None and action(value, 3, "CANCEL") == terminal
    assert value.Handle(request, 4).Field("code") == "STALE"
    value, _, _ = owner()
    assert action(value, 2**32-1, "APPLY").Field("code") == "NOT_PROVEN"
    assert action(value, 2, "SAVE").Field("code") == "STALE"


def test_no_quality_boolean_can_enable_validate_apply_or_save():
    value, _, _ = owner()
    for rid, name in enumerate(("VALIDATE", "APPLY", "SAVE"), 2):
        response = action(value, rid, name)
        assert response.status == "ERR" and response.Field("code") == "NOT_PROVEN"
        assert response.Field("apply") == "0" and response.Field("saved") == "0"
    assert value.state == "IDLE"
    EVIDENCE["application_gate"] = "ALWAYS_DISABLED_OFFLINE_INCLUDING_NUMERIC_PASS"


def test_disconnect_no_auto_resume_lease_timeout_restart_and_parent_change():
    value, imu, mag = owner(); action(value, 2, "MAG_START")
    value.Disconnect(); value.Reconnect()
    assert value.state == "UNKNOWN" and action(value, 3, "MAG_START").Field("code") == "UNKNOWN"
    assert value.Feed(samples(imu, mag)[0], 1300) == CaptureResult.Rejected
    value.Tick(30000000)
    assert value.state == "FAILED" and value.reason == "SESSION_TIMEOUT" and value.gate.owner is None
    case, imu, mag = fixture()
    restarted = OfflineSession("boot2", replace(imu, boot="boot2"), replace(mag, boot="boot2"), case.accel, case.mag)
    assert restarted.Handle(f"INSTALL POLL {SID} 2".encode(), 0).Field("code") == "SESSION_UNKNOWN"
    value, _, _ = owner(); value.candidate = object()
    old = value.binding; value.ParentsUpdate(replace(value.accel, generation=8), value.mag)
    assert value.candidate is None and value.state == "FAILED" and value.binding != old
    assert action(value, 2, "CANCEL").status == "PENDING"
    value.Process(1); assert value.gate.owner is None


def test_tf_and_configuration_owner_exclusion_export_latch_survives_cancel():
    gate = ResourceGate(); value, _, _ = owner(gate)
    assert gate.TransferEnter() == "CONFIG_ACTION"
    assert gate.Acquire("AIR_START") == "CONFIG_ACTION"
    action(value, 2, "CANCEL"); value.Process(1)
    assert gate.TransferEnter() is None
    case, imu, mag = fixture(); other = OfflineSession("boot1", imu, mag, case.accel, case.mag, gate)
    body = f"INSTALL BEGIN {OTHER} 1 {other.binding}".encode()
    assert other.Handle(body, 0).Field("reason") == "TF_TRANSFER"
    gate.TransferCancel()
    assert other.Handle(body, 1).Field("reason") == "REBOOT_REQUIRED"


def test_opaque_upload_exact_retries_crc_hash_and_no_partial_publication():
    payload = bytes(range(100)); spec = UploadSpec(100, hashlib.sha256(payload).hexdigest(), f"{zlib.crc32(payload):08X}")
    value, _, _ = owner(upload=spec)
    for rid, offset in enumerate(range(0, len(payload), 48), 2):
        body = f"INSTALL PUT {SID} {rid} {offset}:{payload[offset:offset+48].hex().upper()}".encode()
        response = value.Handle(body, rid)
        assert response.status == "OK" and value.Handle(body, rid) == response
    assert bytes(value.upload) == payload and all(value.written)
    assert value.Handle(f"INSTALL PUT {SID} 5 0:FF".encode(), 5).Field("code") == "CONFLICT"
    assert action(value, 6, "VALIDATE").Field("code") == "NOT_PROVEN"
    value, _, _ = owner(upload=spec)
    for rid, offset in ((2, 0), (3, 48)):
        value.Handle(f"INSTALL PUT {SID} {rid} {offset}:{payload[offset:offset+48].hex().upper()}".encode(), rid)
    before = bytes(value.upload), bytes(value.written)
    bad = value.Handle(f"INSTALL PUT {SID} 4 96:FFFFFFFF".encode(), 4)
    assert bad.Field("code") == "VERIFY_FAILED" and (bytes(value.upload), bytes(value.written)) == before
    assert action(value, 5, "VALIDATE").Field("reason") == "INCOMPLETE_OBJECT"
    plain, _, _ = owner()
    assert plain.Handle(f"INSTALL PUT {SID} 2 0:AA".encode(), 0).Field("reason") == "UPLOAD_REQUIRED"


def test_info_bound_pages_stale_binding_and_missing_persistence_are_explicit():
    case, imu, mag = fixture(); value = OfflineSession("boot1", imu, mag, case.accel, case.mag)
    data, cursor, binding = bytearray(), 0, None
    while True:
        response = value.Handle(f"INSTALL INFO 0:0 {cursor}".encode(), 0)
        assert response.status == "OK"
        binding = binding or response.Field("binding")
        assert response.Field("binding") == binding
        assert len(Response_Encode(response)[:-2]) <= 511
        data.extend(bytes.fromhex(response.Field("data"))); cursor = int(response.Field("next"))
        if response.Field("end") == "1": break
    assert hashlib.sha256(data).hexdigest() == response.Field("sha256")
    assert json.loads(data)["sources"]["IMU"]["units"] == ["m/s2", "rad/s"]
    assert value.Handle(f"INSTALL BEGIN {SID} 1 {binding}".encode(), 5000000).Field("code") == "STALE"
    assert value.Handle(f"INSTALL STATUS {binding} SAVED:0".encode(), 5000000).Field("reason") == "NO_PERSISTENCE_MODEL"


def completed_math_archive():
    case, imu, mag = fixture()
    value = BoundedCollector(SID, "boot1", imu, mag, CapturePolicy(pair_capacity=128, archive_capacity=256))
    n = 0
    for face in FACES:
        for split in ("TRAIN", "HOLDOUT"):
            index = FACES.index(face)*10+(0 if split == "TRAIN" else 5)
            value.Start(WindowTag("SIX_FACE", face, face+"-"+split, face, split), n*1000+400 if n else 0)
            for row in case.session.records[index:index+5]:
                n += 1; a, m = samples(imu, mag, n, row)
                assert value.Feed(a, n*1000+300) == CaptureResult.Accepted
                assert value.Feed(m, n*1000+300) == CaptureResult.Paired
            assert value.Stop(n*1000+400) == CaptureResult.Complete
    return case, value, imu, mag


def test_collection_event_reassembly_math_context_and_frozen_candidate_readback():
    case, capture, imu, mag = completed_math_archive()
    assembler = PairAssembler(SID, CONTEXT, "boot1", {"IMU": imu, "MAG": mag})
    rebuilt = []
    for pair in capture.pairs:
        assert assembler.Feed(SamplePart_Encode(pair, "MAG", CONTEXT)[:-2], pair.pair_id*2) is None
        rebuilt.append(assembler.Feed(SamplePart_Encode(pair, "IMU", CONTEXT)[:-2], pair.pair_id*2+1).RawPair())
    assert tuple(rebuilt) == capture.StaticRecords()
    mathematical = InstallationSession(rebuilt, case.session.convention)
    policy = Policy(starts=48)
    report = mathematical.Solve(case.accel, case.mag, policy)
    assert report.result == CandidateResult.Candidate and not report.apply_allowed
    value, _, _ = owner(); value.collector = capture; value.state = "SOLVE"
    changed = InstallationSession(rebuilt[:-1], case.session.convention)
    assert value.CandidateAttach(report, changed, policy) == CandidateAttachResult.ContextMismatch
    assert value.CandidateAttach(report, mathematical, replace(policy, starts=8)) == CandidateAttachResult.ContextMismatch
    assert value.CandidateAttach(report, mathematical, policy) == CandidateAttachResult.Accepted
    response = value.Handle(f"INSTALL STATUS {SID} CANDIDATE:0".encode(), 0)
    assert response.status == "OK"
    token, length = response.Field("snapshot"), int(response.Field("length"))
    contents = bytearray()
    for offset in range(0, length, 48):
        page = value.Handle(f"INSTALL READ {SID} {token} {offset}".encode(), 0)
        assert page.status == "OK" and len(Response_Encode(page)[:-2]) <= 511
        part = bytes.fromhex(page.Field("data"))
        assert f"{zlib.crc32(part):08X}" == page.Field("crc32")
        contents.extend(part)
    assert hashlib.sha256(contents).hexdigest() == response.Field("sha256")
    assert json.loads(contents)["report"]["apply_allowed"] is False
    assert json.loads(contents)["context"]["convention"] == json.loads(json.dumps(asdict(mathematical.convention)))
    assert json.loads(contents)["context"]["policy"] == asdict(policy)
    for rid, name in enumerate(("VALIDATE", "APPLY", "SAVE"), 2):
        assert action(value, rid, name).Field("code") == "NOT_PROVEN"
    value.ParentsUpdate(replace(value.accel, generation=8), value.mag)
    assert value.candidate is None
    assert value.Handle(f"INSTALL READ {SID} {token} 0".encode(), 0).Field("code") == "STALE"
    ARCHIVE.update(capture.ArchiveExport())
    assert len(ARCHIVE["records"]) == 120 and not ARCHIVE["apply_allowed"]
    exported = capture.ArchiveExport(); exported["records"][0]["sample"]["sequence"] = 999
    assert capture.archive[0][1].sequence == 1  # Export is an owned copy.
    EVIDENCE["end_to_end_offline"] = {"pairs": len(rebuilt), "math_result": report.result,
        "raw_digest": mathematical.raw_digest, "context_digest": report.context_digest,
        "snapshot_bytes": length, "apply_allowed": report.apply_allowed, "global_uniqueness": report.gates["global_uniqueness"]}


def test_boot_binding_cannot_be_bypassed_by_reassembly_or_direct_pair_input():
    value, imu, mag = collector(); feed_pairs(value, imu, mag, count=1)
    with pytest.raises(ValueError): replace(value.pairs[0], boot="other-boot")
    _, imu, mag = fixture()
    imu, mag = replace(imu, clock="PC_RECEIVE_PROXY"), replace(mag, clock="PC_RECEIVE_PROXY")
    value = BoundedCollector(SID, "boot1", imu, mag)
    assert value.Start(WindowTag("SIX_FACE", "XP", "w", "p", "TRAIN"), 0) == CaptureResult.Failed


def test_six_face_command_progress_is_acquisition_only():
    value, imu, mag = owner()
    rid, n = 2, 0
    assert action(value, rid, "MAG_START").status == "OK"; rid += 1
    for n in range(1, 4):
        a, m = samples(imu, mag, n)
        value.Feed(a, n*1000+300); value.Feed(m, n*1000+300)
    assert action(value, rid, "MAG_STOP").Field("state") == "MAG_FIT"; rid += 1
    assert action(value, rid, "SIX_START").Field("state") == "FACE_WAIT"; rid += 1
    for face in FACES:
        assert action(value, rid, "FACE_"+face).Field("state") == "FACE_COLLECT"; rid += 1
        for _ in range(3):
            n += 1; a, m = samples(imu, mag, n)
            value.Feed(a, n*1000+300); value.Feed(m, n*1000+300)
        assert action(value, rid, "FACE_STOP").status == "OK"; rid += 1
    status = value.Handle(f"INSTALL STATUS {SID} STATE:0".encode(), value.now)
    assert status.Field("face_mask") == "63" and status.Field("state") == "SOLVE"
    assert status.Field("imu_ready") == status.Field("extrinsic_validated") == status.Field("apply") == "0"
