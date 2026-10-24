"""Real backend export/independent check plus TF-object fault lifecycle, no I/O devices."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from services.installation_calibration_backend import InstallationBackend,InstallationResult
from services.installation_calibration_candidate import (Candidate_Decode,Candidate_Encode,
    InstallationCandidateResult,InstallationCandidateStore,OfflineTfObjects)
from services.installation_calibration_fit import FACES,Policy
from services.installation_calibration_worker import InstallationWorker
from test_installation_calibration_backend import MockInstallationOwner,run_job


@pytest.fixture(scope='module')
def exported(tmp_path_factory):
    root=tmp_path_factory.mktemp('installation_export')
    provider=MockInstallationOwner();backend=InstallationBackend(provider,allow_simulated=True)
    provider.info['runtime_imu']={'bias_radps':None,'scale':None,'generation':1,'mode':0,'ready':False}
    from services.installation_calibration_fit import _digest
    provider.binding_digest=_digest({key:value for key,value in provider.info.items() if key!='binding_digest'})
    provider.info['binding_digest']=provider.binding_digest;provider.binding='B-'+provider.binding_digest[:30]
    provider.payload=json.dumps(provider.info,sort_keys=True,separators=(',',':')).encode()
    worker=InstallationWorker(backend);raw=root/'raw.jsonl';destination=root/'candidate.ssic'
    try:
        assert run_job(worker,'begin',archive_path=raw).result==InstallationResult.Ok
        for face in FACES:assert run_job(worker,'face',face=face,attempt=1).result==InstallationResult.Ok
        assert run_job(worker,'fit',policy=Policy(starts=16)).result==InstallationResult.CandidateOnly
        outcome=run_job(worker,'export',path=destination)
        assert outcome.result==InstallationResult.CandidateOnly,outcome.reason
        packet=destination.read_bytes();result,value=Candidate_Decode(packet)
        assert result==InstallationCandidateResult.Ok
        assert value['raw_archive_sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
        assert value['validation']['selects_solution'] is False
        assert len(value['validation']['windows'])==6
        assert not provider.busy and backend.cleanup_confirmed
        assert not any(command.operation in ('UPLOAD','PUT') for command in provider.commands)
        yield packet,value
    finally:assert worker.Close().result==InstallationResult.Ok


def test_full_export_is_immutable_candidate_not_target_acceptance(exported,tmp_path):
    packet,value=exported
    assert value['hardware_acceptance']=='NOT_PROVEN'
    assert value['solution']['gyro_scale_status']=='NOT_ESTIMATED_STATIC_SIX_FACE'
    assert value['binding']['sources']['IMU']['identity']==value['solution']['accel_candidate']['identity']
    assert not value['apply_allowed'] and not value['save_allowed']
    changed=copy.deepcopy(value);changed['apply_allowed']=True
    with pytest.raises(ValueError):Candidate_Encode(changed)
    damaged=bytearray(packet);damaged[-1]^=1
    with pytest.raises(ValueError):Candidate_Decode(bytes(damaged))
    image=OfflineTfObjects(tmp_path/'invalid-tf')
    assert InstallationCandidateStore(image).Save(bytes(damaged),value['binding'])[0]==InstallationCandidateResult.Invalid
    assert image.Read('head') is None


def test_tf_image_idempotence_old_data_and_dependency_invalidation(exported,tmp_path):
    packet,value=exported;objects=OfflineTfObjects(tmp_path/'tf-image');store=InstallationCandidateStore(objects)
    result,first=store.Save(packet,value['binding']);assert result==InstallationCandidateResult.Ok
    assert first['generation']==1
    assert store.Save(packet,value['binding'])==store.Load(value['binding'])
    changed=copy.deepcopy(value['binding']);changed['configuration_u32']+=1
    assert store.Load(changed)[0]==InstallationCandidateResult.Stale
    assert store.Save(packet,changed)[0]==InstallationCandidateResult.Stale
    assert store.Load(value['binding'])[1]['generation']==1
    assert len(list((tmp_path/'tf-image').glob('*.ssic')))==1


@pytest.mark.parametrize('fault',('object_write','readback','commit','torn_head','uncertain_commit'))
def test_failed_save_never_reports_success_or_deletes_old_candidate(exported,tmp_path,fault):
    packet,value=exported;objects=OfflineTfObjects(tmp_path/'tf');store=InstallationCandidateStore(objects)
    assert store.Save(packet,value['binding'])[0]==InstallationCandidateResult.Ok
    original=objects.Read('head');old_object=json.loads(original)['object']
    changed=copy.deepcopy(value);changed['raw_archive_sha256']='a'*64
    newer=Candidate_Encode(changed)
    class Faults:
        def Read(self,key):
            if fault=='readback' and key.startswith('candidate-') and key!=old_object:
                data=objects.Read(key);return None if data is None else data[:-1]
            return objects.Read(key)
        def Create(self,key,data):
            if fault=='object_write':raise OSError('TF unavailable')
            return objects.Create(key,data)
        def Commit(self,expected,data):
            if fault=='torn_head':
                (objects.root/'head-0000000002.json').write_bytes(b'{torn')
                return False
            if fault=='uncertain_commit':objects.Commit(expected,data);return False
            return False if fault=='commit' else objects.Commit(expected,data)
    assert InstallationCandidateStore(Faults()).Save(newer,value['binding'])[0]==InstallationCandidateResult.StorageError
    assert objects.Read(old_object)==packet
    recovered=store.Load(value['binding']);assert recovered[0]==InstallationCandidateResult.Ok
    assert recovered[1]['generation']==(2 if fault=='uncertain_commit' else 1)
    # A complete commit with a lost ACK is uncertain in RAM; restart may select
    # it. It must never be called a guaranteed rollback or target acceptance.
    assert recovered[1]['candidate']['hardware_acceptance']=='NOT_PROVEN'
