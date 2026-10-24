"""Software-only automatic-face/worker/archive regressions; no serial adapter."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from threading import Event, current_thread, main_thread
import time
import sys
import struct
import zlib

import numpy as np
import pytest

from services.installation_calibration_backend import (InstallationBackend, InstallationCapabilities_Parse,
    InstallationBinding_Parse,InstallationOutcome, InstallationResult)
from services.installation_calibration_contract import InstallationContract_Load
from services.installation_calibration_data import (BoundedCollector,CapturePolicy,CaptureResult,SourceDescriptor,SourceSample,WindowTag)
from services.installation_calibration_fit import (Convention,FACES,FACE_AXES,Intrinsic,Policy,SensorIdentity,_digest)
from services.installation_calibration_plan import InstallationDataset, InstallationPlanResult
from services.installation_calibration_protocol import (Request_Decode,Response,Response_Encode,SamplePart_Encode,SamplePart_Decode)
from services.installation_calibration_replay import InstallationReplay_Load
from services.installation_calibration_worker import InstallationJob,InstallationWorker


def response(status,op,**fields):
    return Response_Encode(Response(status,op,tuple((k,str(v)) for k,v in fields.items())))[:-2]


class MockInstallationOwner:
    """Exclusive-owner stand-in and target reference, not a firmware implementation."""
    def __init__(self,*,unsupported=False,old_face=False,fault=None):
        self.unsupported,self.old_face,self.fault=unsupported,old_face,fault
        self.busy=False; self.commands=[]; self.thread_ids=[]; self.release_failed=False; self.releases=0
        imu_id=SensorIdentity("SYNTHETIC",1,1,0,"mock.imu","fixture","cfg-a","A0")
        mag_id=SensorIdentity("SYNTHETIC",2,2,0,"mock.mag","fixture","cfg-m","M0")
        identity=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
        self.accel=Intrinsic(imu_id,1,"accel-1",(0.,0.,0.),identity,"m/s2","A")
        self.mag=Intrinsic(mag_id,1,"mag-1",(3.,-2.,1.),identity,"uT","M")
        self.sources=(SourceDescriptor("IMU",imu_id,("m/s2","rad/s"),"TEST_FIXTURE","BOOT_CLOCK",
            "SYNTHETIC_SHARED_CLOCK","accel-1",1,3,boot="test-boot"),
            SourceDescriptor("MAG",mag_id,("uT",),"TEST_FIXTURE","BOOT_CLOCK","SYNTHETIC_SHARED_CLOCK",
                             "mag-1",1,4,boot="test-boot"))
        self.policy=CapturePolicy(pair_capacity=4096,archive_capacity=8192)
        self.info={"boot":"test-boot","sources":{s.role:asdict(s) for s in self.sources},
            "accel":asdict(self.accel),"mag":asdict(self.mag),"convention":asdict(Convention()),
            "base_generation":0,"configuration_u32":0x12345678,"capture_policy":asdict(self.policy),
            "face_plan":{"train_pairs":5,"holdout_pairs":5,"automatic":True}}
        self.info["capture_provenance"]={
            "sources":{role:{"identity_scope":"SYNTHETIC_ENDPOINT","hardware_identity":None,
                "hardware_identity_provenance":"UNKNOWN","sample_time_basis":"SYNTHETIC_MEASUREMENT",
                "sample_time_provenance":"TEST_FIXTURE","measurement_uncertainty_bound_us":bound,
                "epoch_provenance":"TEST_FIXTURE","native_sequence_provenance":"TEST_FIXTURE"}
                for role,bound in (("IMU",20),("MAG",30))},
            "selection":{"kind":"FIXED_NATIVE_SEQUENCE_STRIDE","phase":{"IMU":0,"MAG":0},
                "nominal_output_millihz":20000,"native_rate_unchanged":True,"value_dependent":False},
            "native_health_timeout_us":250000,"selected_interval_max_us":100000}
        self.binding_digest=_digest(self.info); self.info["binding_digest"]=self.binding_digest
        self.binding="B-"+self.binding_digest[:30]
        self.payload=json.dumps(self.info,sort_keys=True,separators=(",",":")).encode()
        vector=np.array([.13,-.09,.11]); angle=np.linalg.norm(vector); axis=vector/angle
        k=np.array([[0.,-axis[2],axis[1]],[axis[2],0.,-axis[0]],[-axis[1],axis[0],0.]])
        self.rotation=np.eye(3)+np.sin(angle)*k+(1-np.cos(angle))*(k@k)
        self.sid=None; self.n=0; self.batch=[]; self.latest=None

    def Acquire(self,name):
        assert name=="installation"
        if self.busy: return None
        self.busy=True; return self

    def Release(self):
        self.releases+=1
        if self.release_failed: return False
        self.busy=False; return True

    def _capture(self,rid,mode,stage,face,attempt):
        a=np.array(FACE_AXES[face]); angle=[.13,.87,1.2,2.6,-.45,1.7][FACES.index(face)]
        basis=np.eye(3)[int(np.argmin(abs(a)))]; tangent=np.cos(angle)*basis+np.sin(angle)*np.cross(a,basis)
        field=.45*a+np.sqrt(1-.45**2)*tangent
        train=5 if mode=="FIT_CHECK" else 0; events={"TRAIN":[],"HOLDOUT":[]}
        for role,count in (("TRAIN",train),("HOLDOUT",5)):
            if not count: continue
            window=f"{rid:08X}"+("T" if role=="TRAIN" else "V")
            tag=WindowTag(stage,face,window,f"P{rid:08X}",role,attempt)
            assert self.collector.Start(tag,self.n*50000+300)==CaptureResult.Accepted
            for i in range(count):
                self.n+=1; t=self.n*50000
                imu=SourceSample(self.sources[0],self.n,t,t+200,0,20,tuple(a*9.80665)+(0.,0.,0.))
                mag=SourceSample(self.sources[1],self.n,t+100,t+300,0,30,tuple(self.rotation.T@field*48+np.array([3.,-2.,1.])))
                assert self.collector.Feed(imu,t+300)==CaptureResult.Accepted
                assert self.collector.Feed(mag,t+300)==CaptureResult.Paired
                pair=self.collector.pairs[-1]
                events[role].append(SamplePart_Encode(pair,"IMU",self.binding)[:-2])
                if not (self.fault=="drop" and role=="HOLDOUT" and i==1):
                    events[role].append(SamplePart_Encode(pair,"MAG",self.binding)[:-2])
            assert self.collector.Stop(self.n*50000+300)==CaptureResult.Complete
        base={"sid":self.sid,"rid":rid,"binding":self.binding}
        self.batch=[]
        if train: self.batch.append(tuple(events["TRAIN"]+[response("PENDING","FACE",**base,state="HOLDOUT")]))
        self.batch.append(tuple(events["HOLDOUT"]+[response("OK","FACE",**base,state="COMPLETE",
            train_count=train,holdout_count=4 if self.fault=="count" else 5)]))

    def Request(self,data,*,deadline,cancel):
        assert current_thread() is not main_thread() and time.monotonic()<deadline
        if cancel.is_set(): raise InterruptedError("mock cancelled")
        request=Request_Decode(data[:-2]); self.commands.append(request); self.thread_ids.append(current_thread().ident)
        op,args=request.operation,request.arguments
        if op=="CAPS":
            if self.unsupported: return (b"ERR INSTALL CAPS code=BAD_MODULE reason=UNKNOWN",)
            return (response("OK",op,maintenance="0.1",supported=1,install_contract=1,face_auto=0 if self.old_face else 1,
                check_only=1,sample_format=1,max_request=191,max_line=511,train_pairs=5,holdout_pairs=5,pair_capacity=4096,offline=1),)
        if op=="INFO":
            if args[0]!="0:0": return (response("ERR",op,code="WRONG_DEVICE",reason="ENDPOINT"),)
            offset=int(args[1]); chunk=self.payload[offset:offset+48]
            return (response("OK",op,binding=self.binding,cursor=offset,next=offset+len(chunk),end=int(offset+len(chunk)==len(self.payload)),
                length=len(self.payload),sha256=hashlib.sha256(self.payload).hexdigest(),data=chunk.hex().upper()),)
        if op=="BEGIN":
            self.sid=args[0]; self.collector=BoundedCollector(self.sid,"test-boot",*self.sources,self.policy)
            return (response("OK",op,sid=self.sid,rid=args[1],state="FACE_WAIT"),)
        if op=="FACE":
            mode,stage,face,attempt=args[2].split(":"); self._capture(int(args[1]),mode,stage,face,int(attempt))
            self.latest=("FACE",int(args[1]))
            return (response("PENDING",op,sid=self.sid,rid=args[1],binding=self.binding,state="TRAIN"),)
        if op=="POLL":
            if self.latest and self.latest[0]=="DO": return (response("OK","DO",sid=self.sid,rid=args[1],cleanup_complete=1),)
            if self.fault=="timeout": raise TimeoutError("mock timeout")
            return self.batch.pop(0)
        if op=="DO" and args[2]=="CANCEL":
            self.latest=("DO",int(args[1])); self.collector.Cancel()
            return (response("PENDING",op,sid=self.sid,rid=args[1],cleanup_complete=0),)
        raise AssertionError("Unexpected/unsafe command: "+op)


def run_job(worker,action,**kwargs):
    result=worker.Submit(InstallationJob(action,tuple(kwargs.items())))
    assert result.result==InstallationResult.Ok,result
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=worker.TakeResult()
        if result is not None: return result
        time.sleep(.005)
    raise AssertionError("worker did not finish")


@pytest.fixture
def running(tmp_path):
    provider=MockInstallationOwner(); backend=InstallationBackend(provider,allow_simulated=True)
    worker=InstallationWorker(backend); path=tmp_path/"source.jsonl"
    assert run_job(worker,"begin",archive_path=path).result==InstallationResult.Ok
    yield provider,backend,worker,path
    assert worker.Close().result==InstallationResult.Ok


def test_contract_requires_auto_segmentation_and_keeps_maintenance_versions():
    contract=InstallationContract_Load().Read()
    assert contract["versions"]=={"maintenance":"0.1","air":"M0","sslog":"0.0","sample_format":1}
    assert contract["face_plan"]["default"]=="one-transaction-train-then-holdout-per-face"
    for line in (b"ERR INSTALL CAPS code=BAD_MODULE reason=UNKNOWN",b"OK INSTALL CAPS supported=0"):
        assert InstallationCapabilities_Parse(line).outcome.result==InstallationResult.Unsupported
    assert InstallationCapabilities_Parse(b"garbage").outcome.result==InstallationResult.Unknown
    bad=response("OK","CAPS",supported=1,maintenance="0.1",face_auto=0)
    assert InstallationCapabilities_Parse(bad).outcome.result==InstallationResult.Unsupported


@pytest.mark.parametrize("unsupported,old_face",[(True,False),(False,True)])
def test_legacy_firmware_disables_new_flow_and_never_falls_back(tmp_path,unsupported,old_face):
    provider=MockInstallationOwner(unsupported=unsupported,old_face=old_face)
    backend=InstallationBackend(provider,allow_simulated=True); worker=InstallationWorker(backend)
    try:
        result=run_job(worker,"begin",archive_path=tmp_path/"never.jsonl")
        assert result.result==InstallationResult.Unsupported and not provider.busy
        assert [r.operation for r in provider.commands]==["CAPS"]
        assert not (tmp_path/"never.jsonl").exists()
    finally: worker.Close()


def test_each_face_is_one_command_and_target_automatically_splits_nonoverlap(running):
    provider,backend,worker,path=running
    for face in FACES:
        result=run_job(worker,"face",face=face,attempt=1)
        assert result.result==InstallationResult.Ok,result
    faces=[r for r in provider.commands if r.operation=="FACE"]
    assert len(faces)==6 and all(r.arguments[2].startswith("FIT_CHECK:") for r in faces)
    assert not any(r.operation in ("WINDOW","PUT","UPLOAD") for r in provider.commands)
    assert len(backend.dataset.FittingRecords())==30 and len(backend.dataset.FreshHoldout())==30
    assert {r.window for r in backend.dataset.FittingRecords()}.isdisjoint(r.window for r in backend.dataset.FreshHoldout())
    assert all(len(list(group))==5 for group in ([r for r in backend.dataset.records if r.window==w] for w in {r.window for r in backend.dataset.records}))
    fit=run_job(worker,"fit",policy=Policy(starts=16))
    assert fit.result==InstallationResult.CandidateOnly,fit.reason
    assert fit.detail.candidates[0].R_GM is None and not fit.apply_allowed
    snapshot=run_job(worker,"snapshot").detail
    assert snapshot["accel_candidate"]["generation"]==backend.binding.accel.generation+1
    assert snapshot["gyro_scale_status"]=="NOT_ESTIMATED_STATIC_SIX_FACE"
    assert backend.Apply().result==backend.Save().result==InstallationResult.ApplyDisabled
    assert worker.Submit(InstallationJob("apply")).result==InstallationResult.ApplyDisabled
    run_job(worker,"close")
    replay=InstallationReplay_Load(path)
    assert replay.dataset.records==backend.dataset.records and replay.complete_faces==6
    assert len(replay.dataset.Snapshot()["observed_windows"])==6
    replay_result=run_job(worker,"replay",path=path)
    assert replay_result.reason=="REPLAYED_NOT_REVALIDATED"
    assert not any(r.operation=="DO" and r.arguments[-1] in ("APPLY","SAVE") for r in provider.commands)
    assert len(set(provider.thread_ids))==1


def test_adaptation_retires_used_holdout_and_never_relabels_history(running):
    _,backend,worker,path=running
    for face in FACES: assert run_job(worker,"face",face=face,attempt=1).result==InstallationResult.Ok
    assert run_job(worker,"fit",policy=Policy(starts=16)).result==InstallationResult.CandidateOnly
    original={r.window for r in backend.dataset.FreshHoldout()}
    assert run_job(worker,"face",face="XP",attempt=2,stage="SUPPLEMENT").result==InstallationResult.Ok
    assert original<=backend.dataset.retired_windows
    assert run_job(worker,"fit",policy=Policy(starts=16)).result==InstallationResult.NeedFreshValidation
    assert all(r.split=="HOLDOUT" for r in backend.dataset.records if r.window in original)
    train_before=backend.dataset.FittingRecords()
    for face in FACES[1:]:
        assert run_job(worker,"face",face=face,attempt=2,stage="SUPPLEMENT",mode="CHECK_ONLY").result==InstallationResult.Ok
    assert backend.dataset.FittingRecords()==train_before
    result=run_job(worker,"fit",policy=Policy(starts=16))
    assert result.result in (InstallationResult.CandidateOnly,InstallationResult.NeedSamples)
    assert len(backend.dataset.FreshHoldout())==30 and not result.apply_allowed
    run_job(worker,"close")
    replay=InstallationReplay_Load(path)
    assert replay.dataset.retired_windows==backend.dataset.retired_windows
    assert replay.dataset.FittingRecords()==backend.dataset.FittingRecords()


@pytest.mark.parametrize("fault",["drop","count","timeout"])
def test_source_failure_preserves_partial_raw_but_cannot_publish_success(tmp_path,fault):
    provider=MockInstallationOwner(fault=fault); backend=InstallationBackend(provider,allow_simulated=True)
    worker=InstallationWorker(backend); path=tmp_path/"fault.jsonl"
    try:
        assert run_job(worker,"begin",archive_path=path).result==InstallationResult.Ok
        result=run_job(worker,"face",face="XP",attempt=1)
        assert result.result in (InstallationResult.Failed,InstallationResult.Timeout)
        assert not backend.dataset.records and not provider.busy
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        assert any(row["kind"]=="source_part" for row in rows) if fault!="timeout" else True
        assert rows[-1]["kind"]=="face_end" and rows[-1]["result"]=="UNCONFIRMED"
        replay=InstallationReplay_Load(path)
        assert replay.unconfirmed_faces==1 and not replay.dataset.records
    finally: assert worker.Close().result==InstallationResult.Ok


def test_existing_raw_file_never_overwritten_and_worker_admission_is_bounded(tmp_path):
    path=tmp_path/"original.jsonl"; path.write_bytes(b"original user data")
    provider=MockInstallationOwner(); backend=InstallationBackend(provider,allow_simulated=True); worker=InstallationWorker(backend)
    try:
        result=worker.Submit(InstallationJob("begin",(("archive_path",path),)))
        assert result.result==InstallationResult.Ok
        assert worker.Submit(InstallationJob("face",(("face","XP"),("attempt",1)))).result==InstallationResult.Busy
        deadline=time.monotonic()+5
        while worker.TakeResult() is None and time.monotonic()<deadline: time.sleep(.005)
        assert path.read_bytes()==b"original user data" and not provider.busy
        assert worker.Submit(InstallationJob("face",(("cancel",Event()),))).result==InstallationResult.Invalid
    finally: worker.Close()


def test_no_registered_live_provider_and_simulation_never_imply_support(tmp_path):
    worker=InstallationWorker(InstallationBackend())
    try: assert run_job(worker,"begin",archive_path=tmp_path/"none").result==InstallationResult.Unsupported
    finally: worker.Close()
    owner=MockInstallationOwner(); worker=InstallationWorker(InstallationBackend(owner))
    try: assert run_job(worker,"begin",archive_path=tmp_path/"sim").result==InstallationResult.Unsupported
    finally: worker.Close()


def test_replay_rejects_changed_source_and_truncated_records(running,tmp_path):
    _,backend,worker,path=running
    assert run_job(worker,"face",face="XP",attempt=1).result==InstallationResult.Ok
    run_job(worker,"close")
    before=path.read_bytes(); rows=before.splitlines()
    for i,line in enumerate(rows):
        row=json.loads(line)
        if row["kind"]=="pair":
            row["imu"]["values"][0]+=1; rows[i]=json.dumps(row).encode(); break
    altered=tmp_path/"altered.jsonl"; altered.write_bytes(b"\n".join(rows)+b"\n")
    with pytest.raises(ValueError,match="RAW_SOURCE_PART_MISMATCH"): InstallationReplay_Load(altered)
    partial=tmp_path/"partial.jsonl"; partial.write_bytes(before[:-5])
    with pytest.raises(ValueError,match="TRUNCATED"): InstallationReplay_Load(partial)


@pytest.mark.parametrize("cancel_after",[1,6])
def test_cancel_during_either_segment_never_publishes_completed_face(running,cancel_after):
    _,backend,worker,path=running
    original=worker._emit_progress
    def cancel_progress(role,train,hold):
        original(role,train,hold)
        if train+hold>=cancel_after: worker.Cancel()
    worker._emit_progress=cancel_progress
    result=run_job(worker,"face",face="XP",attempt=1)
    assert result.result==InstallationResult.Cancelled and not backend.dataset.records
    assert backend.cleanup_confirmed and path.exists()
    replay=InstallationReplay_Load(path)
    assert replay.unconfirmed_faces==1 and not replay.dataset.records


def test_optional_fit_dependency_missing_is_explicit_and_raw_is_preserved(running,monkeypatch):
    _,backend,worker,path=running
    for face in FACES: assert run_job(worker,"face",face=face,attempt=1).result==InstallationResult.Ok
    with monkeypatch.context() as context:
        context.setitem(sys.modules,"scipy.optimize",None)
        result=run_job(worker,"fit",policy=Policy(starts=8))
        assert result.result==InstallationResult.Unsupported and "FIT_DEPENDENCY_UNAVAILABLE" in result.reason
    assert path.stat().st_size>0 and not result.apply_allowed and len(backend.dataset.records)==60


def test_target_cannot_fabricate_pc_receive_clock(running):
    provider,_,_,_=running
    provider._capture(2,"FIT_CHECK","SIX_FACE","XP",1)
    line=provider.batch[0][0]; parts=line.decode().split(); values=dict(x.split("=",1) for x in parts[3:])
    payload=bytearray.fromhex(values["data"]); struct.pack_into("<Q",payload,24,12345)
    bad=(f"EVENT INSTALL IMU sid={provider.sid} pair=1 ctx={provider.binding} data={payload.hex().upper()} "
         f"crc32={zlib.crc32(payload):08X}").encode()
    with pytest.raises(ValueError): SamplePart_Decode(bad,provider.sid,provider.binding,{s.role:s for s in provider.sources})


def test_release_failure_remains_unknown_and_blocks_second_owner(tmp_path):
    provider=MockInstallationOwner(); backend=InstallationBackend(provider,allow_simulated=True); worker=InstallationWorker(backend)
    try:
        assert run_job(worker,"begin",archive_path=tmp_path/"release.jsonl").result==InstallationResult.Ok
        provider.release_failed=True
        assert run_job(worker,"close").result==InstallationResult.Unknown
        assert provider.busy and backend.lease is provider
        assert run_job(worker,"begin",archive_path=tmp_path/"second.jsonl").result==InstallationResult.Busy
        provider.release_failed=False
        assert run_job(worker,"close").result==InstallationResult.Ok
    finally: worker.Close()


@pytest.mark.parametrize("field,value",[("base_generation",-1),("configuration_u32",2**32),("base_generation",True)])
def test_invalid_info_generation_never_becomes_a_binding(field,value):
    provider=MockInstallationOwner(); data=dict(provider.info); data[field]=value
    context={k:v for k,v in data.items() if k!="binding_digest"}
    data["binding_digest"]=_digest(context)
    caps=InstallationCapabilities_Parse(response("OK","CAPS",maintenance="0.1",supported=1,install_contract=1,
        face_auto=1,check_only=1,sample_format=1,max_request=191,max_line=511,train_pairs=5,holdout_pairs=5,
        pair_capacity=4096,offline=1),allow_simulated=True)
    with pytest.raises(ValueError, match="unsigned integer range"):
        InstallationBinding_Parse(json.dumps(data,sort_keys=True,separators=(",",":")).encode(),"B-"+data["binding_digest"][:30],caps)
