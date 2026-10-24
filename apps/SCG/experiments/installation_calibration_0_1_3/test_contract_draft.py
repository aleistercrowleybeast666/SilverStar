"""Contract closeout: explicit partitions, replay and complete SSIC dependencies."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import zlib

import numpy as np
import pytest

from .capture import Archive_Import, BoundedCollector, CaptureResult, WindowTag
from .protocol import Request_Decode, Request_Encode, Response_Encode
from .prototype import FACES, ImuSixFace_Fit, InstallationSession, Policy, _digest
from .session import OfflineSession
from .ssic_draft import (Bundle_Build, Bundle_Decode, Bundle_VerifyContext, HEADER, MAX_BUNDLE,
                        Record_Decode)
from .test_capture_session import SID, action, collector, completed_math_archive, fixture, owner, samples

RESULTS = {}


@pytest.fixture(scope="module", autouse=True)
def evidence():
    yield
    target = os.environ.get("INSTALL_CAL_EVIDENCE")
    if target:
        root = Path(target).resolve(); allowed = Path(__file__).resolve().parents[4]/".work/dev013_installation_calibration_20261018"
        assert root.is_relative_to(allowed.resolve())
        prefix = os.environ.get("INSTALL_CAL_PREFIX", "")
        (root/(prefix+"contract_cases.json")).write_text(json.dumps(RESULTS, indent=2, allow_nan=False)+"\n", encoding="utf-8")


@pytest.fixture(scope="module")
def built():
    case, capture, imu, mag = completed_math_archive()
    session = InstallationSession(capture.StaticRecords(), case.session.convention)
    policy = Policy(starts=48)
    report = session.Solve(case.accel, case.mag, policy)
    target = OfflineSession("boot1", imu, mag, case.accel, case.mag, policy=capture.policy,
        math_convention=session.convention, config_u32=0x12345678)
    target.Handle(f"INSTALL BEGIN {SID} 1 {target.binding}".encode(), 0)
    target.collector, target.state = capture, "SOLVE"
    data = Bundle_Build(session, report, case.accel, case.mag, (imu, mag), target.binding_digest,
        config_u32=target.config_u32, archive_digest=_digest(capture.ArchiveExport()), commit_rid=2, policy=policy)
    return case, capture, session, report, target, data


@pytest.mark.parametrize("body", [
    f"INSTALL WINDOW {SID} 4294967295 SIX_FACE:XP:HOLDOUT:{'w'*16}:{'p'*16}:65535".encode(),
    f"INSTALL WINDOW {SID} 2 MAG_ROTATE:NA:TRAIN:mag:motion:1".encode(),
    f"INSTALL WINDOW {SID} 3 SUPPLEMENT:ZN:TRAIN:w2:p2:2".encode(),
    f"INSTALL UPLOAD {SID} 4294967295 5140:FFFFFFFF:{'f'*64}".encode(),
    f"INSTALL DO {SID} 4 CAPTURE_DONE".encode(), f"INSTALL DO {SID} 5 WINDOW_CANCEL".encode()])
def test_explicit_contract_golden_stays_in_maintenance_budgets(body):
    assert Request_Encode(Request_Decode(body)) == body+b"\r\n"
    assert len(body) <= 191 and len(body.split()) <= 5
    RESULTS.setdefault("request_golden", []).append({"text": body.decode(), "bytes": len(body)})


@pytest.mark.parametrize("spec", ["SIX_FACE:XP:HOLDOUT:w:p:0", "SIX_FACE:XP:HOLDOUT:w:p:65536",
    "SIX_FACE:XP:TEST:w:p:1", "MAG_ROTATE:XP:TRAIN:w:p:1", "SIX_FACE:XP:TRAIN:"+"w"*17+":p:1",
    "SIX_FACE:XP:TRAIN:w:p:1:extra"])
def test_bad_window_declaration_is_rejected_before_state_mutation(spec):
    value, _, _ = owner(); before = value.state, value.sequence
    with pytest.raises(ValueError): value.Handle(f"INSTALL WINDOW {SID} 2 {spec}".encode(), 0)
    assert (value.state, value.sequence) == before


def test_wire_windows_keep_holdout_separate_and_finish_explicitly():
    value, imu, mag = owner(); n, rid = 0, 2
    def window(stage, face, split, name):
        nonlocal n, rid
        body = f"INSTALL WINDOW {SID} {rid} {stage}:{face}:{split}:{name}:{face if face!='NA' else 'motion'}:1".encode()
        first = value.Handle(body, value.now); assert first.status == "OK"
        assert value.Handle(body, value.now) == first and len(value.collector.windows) <= 64
        rid += 1
        for _ in range(3):
            n += 1; a, m = samples(imu, mag, n)
            value.Feed(a, n*1000+300); value.Feed(m, n*1000+300)
        assert action(value, rid, "WINDOW_STOP").status == "OK"; rid += 1
    window("MAG_ROTATE", "NA", "TRAIN", "m1")
    assert action(value, rid, "SIX_START").status == "OK"; rid += 1
    window("SIX_FACE", "XP", "HOLDOUT", "h0")
    assert value.face_mask == 0
    for face in FACES: window("SIX_FACE", face, "TRAIN", "t"+face)
    assert value.face_mask == 63 and value.state == "FACE_WAIT"
    assert action(value, rid, "CAPTURE_DONE").Field("reason") == "TRAIN_SIX_AND_HOLDOUT_REQUIRED"; rid += 1
    window("SIX_FACE", "XN", "HOLDOUT", "h1"); window("SIX_FACE", "YP", "HOLDOUT", "h2")
    assert action(value, rid, "CAPTURE_DONE").Field("state") == "SOLVE"
    replay = Archive_Import(value.collector.ArchiveExport())
    assert len([r for r in replay.static_records if r.split == "TRAIN"]) == 18
    assert len([r for r in replay.static_records if r.split == "HOLDOUT"]) == 9
    assert len(replay.MagTrainingSamples()) == 3
    RESULTS["wire_partition"] = {"train": 18, "holdout": 9, "rotation_train": 3, "face_mask": value.face_mask,
                                  "archive_digest": replay.archive_digest, "apply": False}


def test_window_cancel_is_local_and_same_face_supplement_returns_for_explicit_solve():
    value, imu, mag = owner(); value.state = "NEED_SAMPLES"; value.face_mask = 63
    body = f"INSTALL WINDOW {SID} 2 SUPPLEMENT:XP:TRAIN:s1:heading2:2".encode()
    assert value.Handle(body, 0).status == "OK"
    value.Feed(samples(imu, mag)[0], 1300)
    assert action(value, 3, "WINDOW_CANCEL").Field("state") == "NEED_SAMPLES"
    assert value.gate.owner == SID and not value.collector.StaticRecords()
    assert value.collector.outcomes["s1"] == "CANCELLED"
    assert value.Handle(f"INSTALL WINDOW {SID} 4 SUPPLEMENT:XP:HOLDOUT:s2:heading2:3".encode(), 1300).status == "OK"
    for n in range(2,5):
        a, m = samples(imu, mag, n); value.Feed(a,n*1000+300); value.Feed(m,n*1000+300)
    assert action(value,5,"WINDOW_STOP").Field("state") == "NEED_SAMPLES"
    assert len(value.collector.archive) == 7


def test_archive_roundtrip_preserves_raw_and_checks_completeness_and_partitions(built):
    _, capture, session, _, _, _ = built
    raw = capture.ArchiveExport(); archive = Archive_Import(raw)
    assert archive.static_records == session.records and archive.archive_digest == _digest(raw)
    raw["records"][0]["sample"]["values"] = (999.,)*6
    assert json.loads(archive.payload_json)["records"][0]["sample"]["values"][0] != 999
    for mutation in ("pair", "gap", "split", "counts"):
        data = capture.ArchiveExport()
        if mutation == "pair": data["pairs"][0]["imu"] = 2
        if mutation == "gap": data["records"][0]["sample"]["flags"] = ("GAP",)
        if mutation == "split": data["records"][0]["tag"]["split"] = "HOLDOUT"
        if mutation == "counts": data["records"].pop()
        with pytest.raises((ValueError, IndexError)): Archive_Import(data)


def test_complete_ssic_ten_records_roundtrip_dependencies_and_raw_replacement(built):
    case, capture, session, _, target, data = built
    bundle = Bundle_Decode(data)
    assert len(bundle.records) == 10 and len(data) <= MAX_BUNDLE
    assert all(len(r) <= 512 for r in bundle.records)
    assert bundle.ParentsMatch(case.accel, case.mag) and not bundle.apply_allowed
    assert Bundle_VerifyContext(bundle, session, (target.sources["IMU"], target.sources["MAG"]),
        target.binding_digest, 0, case.accel, case.mag, _digest(capture.ArchiveExport()),config_u32=target.config_u32)
    raw = session.records[0].magnetic
    np.testing.assert_allclose(bundle.CorrectFromRaw("MAG", raw), case.mag.Correct(raw))
    assert not np.allclose(bundle.CorrectFromRaw("MAG", raw), case.mag.Correct(case.mag.Correct(raw)))
    with pytest.raises(ValueError): bundle.CorrectFromRaw("MAG", raw, "ALREADY_CORRECTED")
    assert not bundle.ParentsMatch(replace(case.accel, generation=8), case.mag)
    np.testing.assert_allclose(bundle.MagToGyro(), np.array(session.convention.R_GA) @ bundle.R_AM)
    RESULTS["ssic"] = {"bundle_bytes": len(data), "record_bytes": [len(r) for r in bundle.records],
        "sha256": hashlib.sha256(data).hexdigest(), "kind_order": [Record_Decode(r)[0][2] for r in bundle.records],
        "archive_digest": bundle.archive_digest, "fit_raw_digest": bundle.fit_raw_digest, "apply_allowed": False}


def test_holdout_changes_do_not_change_intrinsic_fit_or_mag_fit_inputs(built):
    case, capture, session, _, _, _ = built
    before = ImuSixFace_Fit(session,case.accel)
    changed = InstallationSession([replace(r,accel=(1000.,)*3,magnetic=(1000.,)*3) if r.split=="HOLDOUT" else r
                                  for r in session.records],session.convention)
    after = ImuSixFace_Fit(changed,case.accel)
    assert before == after
    _,imu,mag = fixture(); value = BoundedCollector(SID,"boot1",imu,mag)
    n = 0
    for split in ("TRAIN","HOLDOUT"):
        value.Start(WindowTag("MAG_ROTATE","NA",split,split,split),n*1000+400 if n else 0)
        for _ in range(3):
            n+=1; a,m=samples(imu,mag,n); value.Feed(a,n*1000+300); value.Feed(m,n*1000+300)
        value.Stop(n*1000+400)
    raw=value.ArchiveExport(); original=Archive_Import(raw)
    for row in raw["records"]:
        if row["tag"]["split"]=="HOLDOUT" and row["descriptor"]==mag.Digest():
            row["sample"]["values"]=(999.,)*3
    amended=Archive_Import(raw)
    assert original.MagTrainingSamples()==amended.MagTrainingSamples() and len(original.MagTrainingSamples())==3
    assert original.archive_digest!=amended.archive_digest


@pytest.mark.parametrize("mutation", ["truncate", "trailing", "schema", "reserved", "child", "length", "manifest_order"])
def test_ssic_corruption_never_partially_publishes(built, mutation):
    packet = bytearray(built[-1])
    if mutation == "truncate": packet = packet[:-1]
    elif mutation == "trailing": packet += b"x"
    elif mutation == "schema": packet[2+4] = 2
    elif mutation == "reserved": packet[2+13] = 1
    elif mutation == "child": packet[-1] ^= 1
    elif mutation == "length": packet[0:2] = b"\xff\xff"
    elif mutation == "manifest_order": packet[2+32+93] ^= 1
    with pytest.raises(ValueError): Bundle_Decode(bytes(packet))


def test_parent_archive_generation_and_coordinate_assumptions_invalidate_bundle(built):
    case, capture, session, report, target, data = built; bundle = Bundle_Decode(data)
    for binding, base, archive in (("f"*64,0,bundle.archive_digest),(target.binding_digest,1,bundle.archive_digest),
                                   (target.binding_digest,0,"0"*64)):
        with pytest.raises(ValueError): Bundle_VerifyContext(bundle, session, tuple(target.sources.values()), binding, base,
            case.accel, case.mag, archive,config_u32=target.config_u32)
    with pytest.raises(ValueError): Bundle_VerifyContext(bundle,session,tuple(target.sources.values()),target.binding_digest,0,
        case.accel,case.mag,bundle.archive_digest,config_u32=target.config_u32+1)
    unknown = InstallationSession(session.records, replace(session.convention,R_GA=None,gyro_axis_evidence="UNPROVEN"))
    from .prototype import Candidate
    unknown_report = replace(report, context_digest=unknown.ContextDigest(case.accel,case.mag,bundle.policy),
        candidates=(replace(report.candidates[0],R_GM=None),))
    data = Bundle_Build(unknown,unknown_report,case.accel,case.mag,tuple(target.sources.values()),target.binding_digest,
        config_u32=target.config_u32,archive_digest=bundle.archive_digest,policy=bundle.policy)
    assert Bundle_Decode(data).MagToGyro() is None
    with pytest.raises(ValueError): Bundle_Build(session,report,case.accel,case.mag,tuple(target.sources.values()),target.binding_digest,
        config_u32=target.config_u32,archive_digest=bundle.archive_digest,base_generation=2**32-1,policy=bundle.policy)


def test_formal_upload_declared_in_band_reads_complete_ssic_but_never_applies(built):
    case, capture, math_session, _, old_target, _ = built
    value = OfflineSession("boot1",*tuple(old_target.sources.values()),case.accel,case.mag,policy=capture.policy,
        math_convention=math_session.convention,config_u32=old_target.config_u32)
    value.Handle(f"INSTALL BEGIN {SID} 1 {value.binding}".encode(),0)
    value.collector,value.state = capture,"SOLVE"
    packet = built[-1]
    declaration = f"INSTALL UPLOAD {SID} 2 {len(packet)}:{zlib.crc32(packet):08X}:{hashlib.sha256(packet).hexdigest()}".encode()
    first = value.Handle(declaration,0); assert first.status == "OK" and value.Handle(declaration,0) == first
    rid = 3
    for offset in range(0,len(packet),48):
        response = value.Handle(f"INSTALL PUT {SID} {rid} {offset}:{packet[offset:offset+48].hex().upper()}".encode(),0)
        assert response.status == "OK"; rid += 1
    assert value.staged_bundle is not None and value.state == "CANDIDATE_ONLY"
    view = value.Handle(f"INSTALL STATUS {SID} CANDIDATE:0".encode(),0)
    assert view.Field("format") == "SSIC_DRAFT"
    read = bytearray()
    for offset in range(0,len(packet),48):
        page = value.Handle(f"INSTALL READ {SID} {view.Field('snapshot')} {offset}".encode(),0)
        assert len(Response_Encode(page)[:-2]) <= 511
        read.extend(bytes.fromhex(page.Field("data")))
    assert bytes(read) == packet
    for name in ("VALIDATE","APPLY","SAVE"):
        assert action(value,rid,name).Field("code") == "NOT_PROVEN"; rid += 1
    assert action(value,rid,"UPLOAD_CANCEL").Field("cleanup_complete") == "1"
    assert value.staged_bundle is None and len(value.upload) == 0 and value.gate.owner == SID


@pytest.mark.parametrize("phase", ["IDLE","MAG_FIT","FACE_WAIT","SOLVE","NEED_SAMPLES","CANDIDATE_ONLY","UNKNOWN"])
def test_every_noncommit_phase_cancel_disconnect_cleanup_is_bounded(phase):
    value,_,_ = owner(); value.state = phase
    assert action(value,2,"CANCEL").status == "PENDING"
    value.Disconnect(); assert value.state == "CANCEL_PENDING"
    value.Tick(500000)
    assert value.state == "CANCELLED" and value.gate.owner is None
    value.Reconnect()
    assert value.Handle(f"INSTALL POLL {SID} 2".encode(),500000).Field("cleanup_complete") == "1"
