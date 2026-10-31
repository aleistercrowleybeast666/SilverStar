"""Numeric candidate serializer from a fully captured synthetic archive.
No production-provider qualification is inferred from these fixtures.
"""
from dataclasses import asdict, replace
import copy
import hashlib
import json
import pytest
from services.installation_calibration_active import ActivePacket_FromCandidate, ActivePacket_Check
from services.installation_calibration_backend import InstallationBackend, InstallationResult
from services.installation_calibration_candidate import Candidate_Decode, Candidate_Encode
from services.installation_calibration_fit import Convention, FACES, Policy, _digest
from services.installation_calibration_worker import InstallationWorker
from test_installation_calibration_backend import MockInstallationOwner, run_job

@pytest.fixture(scope='module')
def known_frame_candidate(tmp_path_factory):
    root=tmp_path_factory.mktemp('active_packet')
    provider=MockInstallationOwner()
    identity=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
    provider.mag=replace(provider.mag,calibration_id='mag-1-12345678')
    provider.sources=(provider.sources[0],replace(provider.sources[1],intrinsic_id=provider.mag.calibration_id))
    provider.info.update(mag=asdict(provider.mag),sources={s.role:asdict(s) for s in provider.sources},
        convention=asdict(Convention(R_GA=identity,gyro_axis_evidence='SYNTHETIC_IDENTICAL_AXES')),
        runtime_imu={'bias_radps':None,'scale':None,'generation':1,'mode':0,'ready':False})
    provider.binding_digest=_digest({k:v for k,v in provider.info.items() if k!='binding_digest'})
    provider.info['binding_digest']=provider.binding_digest
    provider.binding='B-'+provider.binding_digest[:30]
    provider.payload=json.dumps(provider.info,sort_keys=True,separators=(',',':')).encode()
    worker=InstallationWorker(InstallationBackend(provider,allow_simulated=True))
    archive=root/'raw.jsonl';candidate=root/'candidate.ssic'
    try:
        assert run_job(worker,'begin',archive_path=archive).result==InstallationResult.Ok
        for face in FACES: assert run_job(worker,'face',face=face,attempt=1).result==InstallationResult.Ok
        assert run_job(worker,'fit',policy=Policy(starts=16)).result==InstallationResult.CandidateOnly
        assert run_job(worker,'export',path=candidate).result==InstallationResult.CandidateOnly
        packet=candidate.read_bytes()
        _,snapshot=Candidate_Decode(packet)
        assert snapshot['raw_archive_sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
        return packet,snapshot
    finally: assert worker.Close().result==InstallationResult.Ok

def test_active_packet_matches_recorded_solution_without_changing_candidate(known_frame_candidate):
    packet,snapshot=known_frame_candidate
    before=hashlib.sha256(packet).hexdigest()
    active=ActivePacket_FromCandidate(packet);decoded=ActivePacket_Check(active)
    assert len(active)==228 and decoded['hardware_verified'] is False
    assert decoded['raw_archive_sha256']==snapshot['raw_archive_sha256']
    assert decoded['R_AM']==pytest.approx([v for row in snapshot['solution']['report']['candidates'][0]['R_AM'] for v in row])
    assert decoded['accel_bias_mps2']==pytest.approx(snapshot['solution']['accel_candidate']['bias'])
    assert decoded['gyro_bias_radps']==pytest.approx(snapshot['solution']['gyro_bias'])
    assert hashlib.sha256(packet).hexdigest()==before
    assert snapshot['apply_allowed'] is False and snapshot['save_allowed'] is False

def test_convention_cannot_be_replaced_after_capture(known_frame_candidate):
    _,snapshot=known_frame_candidate
    forged=copy.deepcopy(snapshot)
    forged['solution']['convention']['gyro_axis_evidence']='FORGED_DIFFERENT_SOURCE'
    packet=Candidate_Encode(forged)
    with pytest.raises(ValueError,match='SOURCE_FRAME_DEPENDENCY_MISMATCH'):
        ActivePacket_FromCandidate(packet)
