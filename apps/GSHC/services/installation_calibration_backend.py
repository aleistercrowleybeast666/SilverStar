"""GSHC installation backend over an injected exclusive owner; no port opens/UI.

The current firmware does not implement this optional contract. This service
never falls back to legacy MAG/CAL/ALIGN controls or uploads/applies/saves fits.
"""
from dataclasses import asdict, dataclass, field, fields as DataclassFields, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from services.installation_calibration_contract import InstallationContract_Load
from services.installation_calibration_capture_contract import (CaptureProofResult, CaptureProvenance_Audit, CaptureQualification,
    InfoSnapshot_Decode)
from services.installation_calibration_data import CapturedPair, CapturePolicy, SourceDescriptor, SourceSample, WindowTag
from services.installation_calibration_fit import (CandidateResult, Convention, InstallationSession, Intrinsic,
    IntrinsicFitResult,ImuSixFace_Fit,Policy, SensorIdentity, _digest,_uint)
from services.installation_calibration_plan import FaceTransaction, InstallationDataset, InstallationPlanResult
from services.installation_calibration_protocol import (PairAssembler, Request, Request_Encode,
    Response_Decode, SamplePart_Decode)


class InstallationResult(str,Enum):
    Ok="OK"
    CandidateOnly="CANDIDATE_ONLY"
    Unsupported="UNSUPPORTED"
    Unknown="UNKNOWN"
    Busy="BUSY"
    Invalid="INVALID"
    Timeout="TIMEOUT"
    Cancelled="CANCELLED"
    Failed="FAILED"
    NeedSamples="NEED_SAMPLES"
    NeedFreshValidation="NEED_FRESH_VALIDATION"
    ApplyDisabled="APPLY_SAVE_DISABLED"


@dataclass(frozen=True)
class InstallationOutcome:
    result: InstallationResult
    reason: str
    detail: object=None
    apply_allowed: bool=field(default=False,init=False)
    save_allowed: bool=field(default=False,init=False)


@dataclass(frozen=True)
class InstallationCapabilities:
    outcome: InstallationOutcome
    train_pairs: int=0
    holdout_pairs: int=0
    pair_capacity: int=0
    simulated: bool=False


def InstallationCapabilities_Parse(line,*,allow_simulated=False):
    contract=InstallationContract_Load().Read()
    if line.decode("ascii",errors="replace") in contract["unsupported"]:
        return InstallationCapabilities(InstallationOutcome(InstallationResult.Unsupported,"CAPABILITY"))
    try:
        reply=Response_Decode(line,"CAPS")
        if reply.status!="OK": raise ValueError("capability response")
        if reply.Field("supported")=="0":
            return InstallationCapabilities(InstallationOutcome(InstallationResult.Unsupported,"CAPABILITY"))
        for key,value in contract["capability_required"].items():
            if reply.Field(key)!=value:
                return InstallationCapabilities(InstallationOutcome(InstallationResult.Unsupported,"AUTOMATIC_FACE_CONTRACT_REQUIRED"))
        values={}
        for key,(low,high) in contract["capability_numeric"].items():
            value=reply.Field(key)
            if value is None or not value.isascii() or not value.isdecimal() or len(value)>10: raise ValueError("capability range")
            values[key]=int(value)
            if not low<=values[key]<=high: raise ValueError("capability range")
        simulated=reply.Field("offline")=="1"
        if reply.Field("offline") not in ("0","1") or (simulated and not allow_simulated):
            return InstallationCapabilities(InstallationOutcome(InstallationResult.Unsupported,"SIMULATION_NOT_AUTHORIZED"))
        if values["train_pairs"]+values["holdout_pairs"]>values["pair_capacity"]: raise ValueError("logical face record budget")
        return InstallationCapabilities(InstallationOutcome(InstallationResult.Ok,"EXPLICIT_CAPABILITY"),
            values["train_pairs"],values["holdout_pairs"],values["pair_capacity"],simulated)
    except (ValueError,TypeError):
        return InstallationCapabilities(InstallationOutcome(InstallationResult.Unknown,"BAD_CAPABILITY_RESPONSE"))


@dataclass(frozen=True)
class InstallationBinding:
    raw_json: bytes
    binding: str
    digest: str
    boot: str
    sources: tuple
    accel: Intrinsic
    mag: Intrinsic
    convention: Convention
    capture_policy: CapturePolicy
    capture_qualification: CaptureQualification


def _complete(value, cls):
    if type(value) is not dict or set(value) != {item.name for item in DataclassFields(cls)}:
        raise ValueError("INFO_COMPLETE_FIELDS_REQUIRED")


def InstallationBinding_Parse(payload,binding,caps):
    rules=InstallationContract_Load().Read()["info_snapshot"]
    data=InfoSnapshot_Decode(payload,rules)
    _uint(data["base_generation"],32); _uint(data["configuration_u32"],32)
    if type(data["sources"]) is not dict or set(data["sources"])!={"IMU","MAG"}:
        raise ValueError("INFO_EXACT_SOURCE_ROLES")
    sources=[]
    for role in ("IMU","MAG"):
        _complete(data["sources"][role],SourceDescriptor)
        _complete(data["sources"][role]["identity"],SensorIdentity)
        fields=dict(data["sources"][role]); fields["identity"]=SensorIdentity(**fields["identity"])
        source=SourceDescriptor(**fields)
        if source.role!=role or source.boot!=data["boot"]: raise ValueError("INFO source/boot")
        if (source.boot=="UNKNOWN" or source.clock_provenance=="UNKNOWN" or source.frame_provenance=="UNKNOWN"
                or source.clock=="PC_RECEIVE_PROXY"): raise ValueError("INFO provenance unproven")
        sources.append(source)
    intrinsics=[]
    for name,source in zip(("accel","mag"),sources):
        _complete(data[name],Intrinsic); _complete(data[name]["identity"],SensorIdentity)
        fields=dict(data[name]); fields["identity"]=SensorIdentity(**fields["identity"])
        intrinsic=Intrinsic(**fields)
        if intrinsic.identity!=source.identity: raise ValueError("INFO parent identity")
        intrinsics.append(intrinsic)
    _complete(data["convention"],Convention); _complete(data["capture_policy"],CapturePolicy)
    convention=Convention(**data["convention"]); capture=CapturePolicy(**data["capture_policy"])
    if ((intrinsics[0].unit,intrinsics[1].unit)!=("m/s2","uT")
            or (intrinsics[0].output_frame,intrinsics[1].output_frame)!=(convention.accel_frame,convention.mag_frame)
            or any((s.intrinsic_id,s.intrinsic_generation)!=(i.calibration_id,i.generation) for s,i in zip(sources,intrinsics))):
        raise ValueError("INFO correction provenance changed")
    canonical={key:data[key] for key in (*rules["canonical_binding_fields"],
        *(key for key in rules.get('optional_binding_fields',[]) if key in data))}
    digest=_digest(canonical)
    if digest!=data["binding_digest"] or binding!="B-"+digest[:30]: raise ValueError("full binding digest")
    plan=data["face_plan"]
    if plan.get("automatic") is not True or plan!={"train_pairs":caps.train_pairs,"holdout_pairs":caps.holdout_pairs,"automatic":True}:
        raise ValueError("INFO/CAPS plan changed")
    if sources[0].clock!=sources[1].clock: raise ValueError("source clocks differ")
    qualification=CaptureProvenance_Audit(data["capture_provenance"],sources,capture,simulated=caps.simulated)
    if qualification.result!=CaptureProofResult.Qualified: raise ValueError(qualification.reason)
    return InstallationBinding(bytes(payload),binding,digest,data["boot"],tuple(sources),*intrinsics,convention,capture,qualification)


class InstallationRawStore:
    """Exclusive append-only host archive. This is not SSLOG or a command log."""
    def __init__(self,path,header):
        self.path=Path(path); self.bytes=0; self.count=0; self.closed=False
        self.stream=self.path.open("xb")
        self.Write({"kind":"header","format":"silverstar.installation-raw","version":1,"info":header})

    def Write(self,record):
        data=(json.dumps(record,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
        if len(data)>16384 or self.bytes+len(data)>32*1024*1024: raise ValueError("RAW_ARCHIVE_FULL")
        if self.stream.write(data)!=len(data): raise OSError("short raw archive write")
        self.stream.flush(); self.bytes+=len(data); self.count+=1
        if self.count%16==0: os.fsync(self.stream.fileno())

    def Pair(self,pair):
        a,m=asdict(pair.imu),asdict(pair.mag); del a["descriptor"]; del m["descriptor"]
        self.Write({"kind":"pair","pair_id":pair.pair_id,"tag":asdict(pair.tag),"imu":a,"mag":m})

    def Close(self):
        if not self.closed:
            try: self.stream.flush(); os.fsync(self.stream.fileno())
            finally: self.stream.close(); self.closed=True


class InstallationBackend:
    """Provider.Acquire returns a bounded owner lease; Request never opens a port.

    Lease.Request(request_bytes, deadline=monotonic, cancel=Event) -> tuple[bytes]
    contains a bounded batch of complete event/reply bodies. Lease.Release() must
    release the same shared owner. No lease adapter is registered in the GUI.
    """
    def __init__(self,provider=None,*,allow_simulated=False,clock=time.monotonic):
        self.contract=InstallationContract_Load(); self.rules=self.contract.Read()
        self.provider,self.allow_simulated,self.clock=provider,allow_simulated,clock
        self.lease,self.binding,self.store=None,None,None
        self.capabilities=None; self.dataset=InstallationDataset(); self.sid=None
        self.rid=0; self.assembler=None; self.status="DISABLED"; self.cleanup_confirmed=True
        self._arrivals={}; self._evaluated_policy=None
        self._faces_started=0; self._evaluations=0
        self.proposed_accel=None; self.proposed_gyro_bias=None

    def _worker(self):
        if threading.current_thread() is threading.main_thread(): raise ValueError("WORKER_THREAD_REQUIRED")

    def _request(self,request,cancel,deadline):
        if cancel.is_set(): raise InterruptedError("CANCELLED")
        if self.clock()>=deadline: raise TimeoutError("JOB_DEADLINE")
        exchange_deadline=min(deadline,self.clock()+5)
        lines=self.lease.Request(Request_Encode(request),deadline=exchange_deadline,cancel=cancel)
        if self.clock()>=exchange_deadline: raise TimeoutError("REQUEST_RETURNED_AFTER_DEADLINE")
        if cancel.is_set(): raise InterruptedError("CANCELLED_DURING_REQUEST")
        if type(lines) is not tuple or len(lines)>self.rules["limits"]["event_lines_per_exchange"]:
            raise ValueError("BOUNDED_RESPONSE_BATCH_REQUIRED")
        if any(type(line) is not bytes or len(line)>511 for line in lines): raise ValueError("RESPONSE_LINE_BUDGET")
        return lines

    def _reply(self,lines,op,sid=None,rid=None):
        replies=[]
        for line in lines:
            if line.startswith(b"EVENT INSTALL "): continue
            replies.append(Response_Decode(line,op,sid,rid))
        if len(replies)!=1: raise ValueError("ONE_MATCHED_REPLY_REQUIRED")
        return replies[0]

    def Begin(self,archive_path,cancel,progress=lambda *_:None,*,imu_instance=0,mag_instance=0):
        self._worker()
        if self.lease is not None: return InstallationOutcome(InstallationResult.Busy,"SESSION_ACTIVE")
        if not self.cleanup_confirmed:
            return InstallationOutcome(InstallationResult.Unknown,"PREVIOUS_TARGET_CLEANUP_UNCONFIRMED")
        if self.provider is None: return InstallationOutcome(InstallationResult.Unsupported,"NO_SHARED_OWNER_PROVIDER")
        if any(type(x) is not int or not 0<=x<=255 for x in (imu_instance,mag_instance)):
            return InstallationOutcome(InstallationResult.Invalid,"ENDPOINT_SELECTION")
        self.lease=self.provider.Acquire("installation")
        if self.lease is None: return InstallationOutcome(InstallationResult.Busy,"MAINTENANCE_OWNER_BUSY")
        self.sid=None; self.binding=None; self.cleanup_confirmed=True
        deadline=self.clock()+self.rules["limits"]["job_timeout_s"]
        try:
            lines=self._request(Request("CAPS"),cancel,deadline)
            if len(lines)!=1: raise ValueError("ONE_CAPABILITY_REPLY_REQUIRED")
            self.capabilities=InstallationCapabilities_Parse(lines[0],allow_simulated=self.allow_simulated)
            if self.capabilities.outcome.result!=InstallationResult.Ok:
                outcome=self.capabilities.outcome; self._release(); return outcome
            payload=bytearray(); offset=0; digest=None; binding=None; total=None
            for _ in range(172):
                reply=self._reply(self._request(Request("INFO",(f"{imu_instance}:{mag_instance}",str(offset))),cancel,deadline),"INFO")
                if reply.status!="OK": raise ValueError("INFO_REJECTED")
                chunk=bytes.fromhex(reply.Field("data")); length=int(reply.Field("length"))
                current=(reply.Field("binding"),reply.Field("sha256"),length)
                if binding is None: binding,digest,total=current
                if current!=(binding,digest,total) or int(reply.Field("cursor"))!=offset or not 1<=len(chunk)<=48 or total>8192:
                    raise ValueError("INFO_SNAPSHOT_CHANGED")
                payload.extend(chunk); offset+=len(chunk)
                if int(reply.Field("next"))!=offset: raise ValueError("INFO_CURSOR")
                if reply.Field("end")=="1": break
            else: raise ValueError("INFO_PAGE_BUDGET")
            if len(payload)!=total or hashlib.sha256(payload).hexdigest()!=digest: raise ValueError("INFO_HASH")
            self.binding=InstallationBinding_Parse(bytes(payload),binding,self.capabilities)
            if tuple(s.identity.instance for s in self.binding.sources)!=(imu_instance,mag_instance):
                raise ValueError("INFO_SELECTED_ENDPOINT_CHANGED")
            self.sid=uuid4().hex; self.rid=1; self.dataset=InstallationDataset(); self.dataset.Bind(self.binding.digest)
            self._faces_started=0; self._evaluations=0; self._evaluated_policy=None
            reply=self._reply(self._request(Request("BEGIN",(self.sid,"1",binding)),cancel,deadline),"BEGIN",self.sid,1)
            if reply.status!="OK": raise ValueError("BEGIN_NOT_CONFIRMED")
            self.store=InstallationRawStore(archive_path,{"contract_sha256":self.contract.sha256,"sid":self.sid,
                "binding":json.loads(self.binding.raw_json),"simulated":self.capabilities.simulated,
                "pc_receive_provenance":"BACKEND_BATCH_DEQUEUE_MONOTONIC_NOT_HARDWARE_CAPTURE"})
            self.assembler=PairAssembler(self.sid,binding,self.binding.boot,{s.role:s for s in self.binding.sources},
                quality_policy=self.binding.capture_policy)
            self.status="FACE_WAIT"; self.cleanup_confirmed=False
            return InstallationOutcome(InstallationResult.Ok,"AUTOMATIC_FACE_AVAILABLE")
        except BaseException:
            self.status="UNKNOWN"; self.Cleanup(threading.Event()); raise

    def Face(self,face,attempt,cancel,progress=lambda *_:None,*,stage="SIX_FACE",mode="FIT_CHECK"):
        self._worker()
        if self.lease is None or self.binding is None: return InstallationOutcome(InstallationResult.Unsupported,"SESSION_UNAVAILABLE")
        if self.rid>=2**32-2: return InstallationOutcome(InstallationResult.Failed,"RID_EXHAUSTED")
        if self._faces_started>=self.rules["limits"]["face_transactions"]:
            return InstallationOutcome(InstallationResult.Failed,"FACE_TRANSACTION_LIMIT")
        if face not in self.rules["face_plan"]["faces"] or stage not in ("SIX_FACE","SUPPLEMENT") or mode not in ("FIT_CHECK","CHECK_ONLY"):
            return InstallationOutcome(InstallationResult.Invalid,"FACE_PLAN")
        if type(attempt) is not int or not 1<=attempt<=65535: return InstallationOutcome(InstallationResult.Invalid,"ATTEMPT")
        adaptation=mode=="FIT_CHECK" and (stage=="SUPPLEMENT" or bool(self.dataset.Snapshot()["observed_windows"]))
        if adaptation: self.dataset.BeginAdaptation()
        self.rid+=1
        plan=FaceTransaction(self.rid,stage,face,attempt,self.capabilities.train_pairs if mode=="FIT_CHECK" else 0,
                             self.capabilities.holdout_pairs,mode)
        request=Request("FACE",(self.sid,str(plan.rid),f"{mode}:{stage}:{face}:{attempt}"))
        deadline=self.clock()+self.rules["limits"]["job_timeout_s"]
        self._faces_started+=1
        self.store.Write({"kind":"face_begin","plan":asdict(plan),"adaptation":adaptation})
        staged=[]; train=hold=0; role="TRAIN" if plan.train_pairs else "HOLDOUT"
        self.status="COLLECTING"
        try:
            for poll in range(512):
                lines=self._request(request if poll==0 else Request("POLL",(self.sid,str(plan.rid))),cancel,deadline)
                for line in lines:
                    if not line.startswith(b"EVENT INSTALL "): continue
                    now_us=int(self.clock()*1000000)
                    self.store.Write({"kind":"source_part","line_hex":line.hex(),"pc_receive_us":now_us})
                    pid,part,tag,sample=SamplePart_Decode(line,self.sid,self.binding.binding,{s.role:s for s in self.binding.sources})
                    if self.binding.capture_qualification.Sample_Check(sample)!=CaptureProofResult.Qualified:
                        raise ValueError("SOURCE_TIME_BOUND_NOT_HONORED")
                    if len(self._arrivals)>8: raise ValueError("ARRIVAL_BUFFER_FULL")
                    self._arrivals.setdefault((pid,part),now_us)
                    pair=self.assembler.Feed(line,now_us)
                    if pair is None:
                        if pid<=self.assembler.highwater: self._arrivals.pop((pid,part),None)
                        continue
                    pair=replace(pair,imu=replace(pair.imu,pc_receive_us=self._arrivals.pop((pid,"IMU"))),
                                 mag=replace(pair.mag,pc_receive_us=self._arrivals.pop((pid,"MAG"))))
                    expected=plan.train_window if role=="TRAIN" else plan.holdout_window
                    if (tag.stage,tag.face,tag.attempt,tag.window,tag.pose,tag.split)!=(stage,face,attempt,expected,plan.pose,role):
                        raise ValueError("AUTOMATIC_SEGMENT_BOUNDARY")
                    self.store.Pair(pair); staged.append(pair.RawPair(self.binding.capture_policy))
                    if len(staged)>1:
                        previous=staged[-2]; current=staged[-1]
                        for source,key in zip(self.binding.sources,("imu_seq","mag_seq")):
                            if (getattr(current,key)-getattr(previous,key))%2**32!=source.sequence_stride:
                                raise ValueError("CONTINUOUS_FACE_SOURCE_GAP")
                    if len(staged)>plan.train_pairs+plan.holdout_pairs: raise ValueError("FACE_SAMPLE_OVERFLOW")
                    if role=="TRAIN":
                        train+=1
                        if train==plan.train_pairs: role="HOLDOUT"
                    else: hold+=1
                    progress(role,train,hold)
                reply=self._reply(lines,"FACE",self.sid,plan.rid)
                if cancel.is_set(): raise InterruptedError("CANCELLED_BEFORE_FACE_PUBLICATION")
                if reply.Field("binding")!=self.binding.binding: raise ValueError("SESSION_BINDING_CHANGED")
                if reply.status=="ERR": raise ValueError("FACE_REJECTED:"+str(reply.Field("reason")))
                if reply.status=="OK" and reply.Field("state")=="COMPLETE":
                    if train!=plan.train_pairs or hold!=plan.holdout_pairs or reply.Field("train_count")!=str(train) or reply.Field("holdout_count")!=str(hold):
                        raise ValueError("FACE_INCOMPLETE_OR_DROPPED")
                    result=self.dataset.AddTransaction(staged)
                    if result!=InstallationPlanResult.Accepted: raise ValueError(self.dataset.reason)
                    self.store.Write({"kind":"face_end","rid":plan.rid,"result":"COMPLETE","train":train,"holdout":hold})
                    self.status="FACE_WAIT"
                    return InstallationOutcome(InstallationResult.Ok,"FACE_CAPTURED_NOT_VALIDATED",self.dataset.Snapshot())
                if reply.status not in ("OK","PENDING"): raise ValueError("FACE_REPLY")
                if cancel.wait(self.rules["limits"]["poll_ms"]/1000): raise InterruptedError("CANCELLED")
            raise TimeoutError("POLL_BUDGET")
        except BaseException:
            self.store.Write({"kind":"face_end","rid":plan.rid,"result":"UNCONFIRMED","train":train,"holdout":hold})
            self.status="UNKNOWN"; self.dataset.Invalidate("FACE_UNCONFIRMED"); self.Cleanup(threading.Event()); raise

    def Fit(self,cancel,progress=lambda *_:None,*,policy=Policy()):
        self._worker()
        if self.binding is None: return InstallationOutcome(InstallationResult.Unsupported,"NO_BOUND_SOURCE")
        policy_digest=_digest(asdict(policy))
        if self._evaluated_policy is not None and self._evaluated_policy!=policy_digest:
            self.dataset.BeginAdaptation(); self._evaluated_policy=None
            if self.store: self.store.Write({"kind":"validation_retire","reason":"POLICY_CHANGED"})
        gate=self.dataset.ValidationGate()
        if gate!=InstallationPlanResult.Accepted:
            return InstallationOutcome(InstallationResult.NeedFreshValidation,self.dataset.reason,self.dataset.Snapshot())
        training=InstallationSession(self.dataset.FittingRecords(),self.binding.convention)
        status,accel,gyro_bias=ImuSixFace_Fit(training,self.binding.accel,gravity=policy.gravity)
        if status!=IntrinsicFitResult.Candidate:
            return InstallationOutcome(InstallationResult.NeedSamples,"TRAINING_IMU_INTRINSIC_REJECTED")
        self.proposed_accel,self.proposed_gyro_bias=accel,gyro_bias
        self._candidate_policy=policy
        mathematical=InstallationSession(self.dataset.EvaluationRecords(),self.binding.convention)
        if self._evaluations>=self.rules["limits"]["evaluations"]:
            return InstallationOutcome(InstallationResult.Failed,"EVALUATION_LIMIT")
        self._evaluations+=1
        if self.store:
            self.store.Write({"kind":"validation_use","policy":asdict(policy),"policy_digest":policy_digest,
                "windows":sorted({r.window for r in self.dataset.FreshHoldout()}),
                "accel_candidate":asdict(accel),"gyro_bias":gyro_bias,
                "context_digest":mathematical.ContextDigest(accel,self.binding.mag,policy)})
        self.dataset.MarkValidationObserved(); self._evaluated_policy=policy_digest
        report=mathematical.Solve(accel,self.binding.mag,policy,cancel=cancel.is_set,
                                  progress=lambda done,total:progress("SOLVE",done,total))
        self.dataset.candidate=report
        result=InstallationResult.CandidateOnly if report.result==CandidateResult.Candidate else InstallationResult.NeedSamples
        if report.result==CandidateResult.Cancelled: result=InstallationResult.Cancelled
        if "FIT_DEPENDENCY_UNAVAILABLE" in report.reasons: result=InstallationResult.Unsupported
        return InstallationOutcome(result,";".join(report.reasons) or "NUMERIC_CANDIDATE_ONLY",report)

    def Apply(self,*_): return InstallationOutcome(InstallationResult.ApplyDisabled,"EXPERIMENTAL_APPLY_DISABLED")
    def Save(self,*_): return InstallationOutcome(InstallationResult.ApplyDisabled,"EXPERIMENTAL_SAVE_DISABLED")

    def CandidateSnapshot(self):
        self._worker()
        report=self.dataset.candidate
        if report is None or self.proposed_accel is None: return None
        return {"binding_digest":self.binding.digest,"accel_candidate":asdict(self.proposed_accel),
                "gyro_bias":self.proposed_gyro_bias,"mag_parent":asdict(self.binding.mag),
                "convention":asdict(self.binding.convention),"report":asdict(report),
                "gyro_scale_status":"NOT_ESTIMATED_STATIC_SIX_FACE","apply_allowed":False,"save_allowed":False}

    def ExportCandidate(self,path):
        """Freeze/validate then close the remote session before immutable export.

        Reuses the captured raw records and fitted parents. No optimization,
        solution selection, relabelling, port opening or target apply occurs.
        """
        self._worker()
        from services.installation_calibration_candidate import Candidate_Encode
        solution=self.CandidateSnapshot();report=self.dataset.candidate
        if self.binding is None or 'runtime_imu' not in json.loads(self.binding.raw_json):
            return InstallationOutcome(InstallationResult.Unsupported,'COMPLETE_RUNTIME_IMU_SNAPSHOT_REQUIRED')
        if (solution is None or report.result!=CandidateResult.Candidate
                or self.dataset.ValidationGate()!=InstallationPlanResult.Accepted):
            return InstallationOutcome(InstallationResult.NeedFreshValidation,"NO_VALIDATED_SOFTWARE_CANDIDATE")
        policy=self._candidate_policy;chosen=report.candidates[0]
        rows,rejected=InstallationSession(self.dataset.EvaluationRecords(),self.binding.convention)._prepare(
            self.proposed_accel,self.binding.mag,policy)
        holdout=[row for row in rows if row[0].split=="HOLDOUT"]
        if rejected or {row[0].face for row in holdout}!={"XP","XN","YP","YN","ZP","ZN"}:
            return InstallationOutcome(InstallationResult.NeedFreshValidation,"INDEPENDENT_HOLDOUT_QUALITY")
        # Direct scalar implementation evaluates the training-selected R and s;
        # holdout never selects a solution or estimates inclination again.
        residual=[sum(float(a[i])*sum(float(chosen.R_AM[i][j])*float(m[j]) for j in range(3))
                      for i in range(3))-chosen.s for _,a,m in holdout]
        rms=(sum(x*x for x in residual)/len(residual))**.5;maximum=max(abs(x) for x in residual)
        if rms>policy.residual_rms or maximum>policy.residual_max:
            return InstallationOutcome(InstallationResult.NeedFreshValidation,"INDEPENDENT_HOLDOUT_REJECTED")
        validation={"result":"PASS_SOFTWARE_HOLDOUT","selects_solution":False,"rms":rms,"maximum":maximum,
                    "windows":sorted({row[0].window for row in holdout}),"context_digest":report.context_digest,
                    "solution_sha256":hashlib.sha256(json.dumps(asdict(chosen),sort_keys=True,
                        separators=(",",":"),allow_nan=False).encode()).hexdigest()}
        # Unknown remote cleanup cannot produce an export labelled complete.
        cleanup=self.Cleanup()
        if cleanup.result!=InstallationResult.Ok:return cleanup
        raw=self.store.path.read_bytes()
        packet=Candidate_Encode({"kind":"INSTALLATION_SOFTWARE_CANDIDATE","binding":json.loads(self.binding.raw_json),
            "solution":solution,"raw_archive_sha256":hashlib.sha256(raw).hexdigest(),"validation":validation,
            "hardware_acceptance":"NOT_PROVEN","apply_allowed":False,"save_allowed":False})
        destination=Path(path)
        with destination.open('xb') as stream:
            if stream.write(packet)!=len(packet):raise OSError("SHORT_CANDIDATE_WRITE")
            stream.flush();os.fsync(stream.fileno())
        return InstallationOutcome(InstallationResult.CandidateOnly,"EXPORTED_NOT_APPLIED",{
            "path":str(destination),"sha256":hashlib.sha256(packet).hexdigest(),"validation":validation})

    def Replay(self,path):
        self._worker()
        from services.installation_calibration_replay import InstallationReplay_Load
        replay=InstallationReplay_Load(path)
        return InstallationOutcome(InstallationResult.Ok,"REPLAYED_NOT_REVALIDATED",{
            "dataset":replay.dataset.Snapshot(),"complete_faces":replay.complete_faces,
            "unconfirmed_faces":replay.unconfirmed_faces,"sha256":replay.file_sha256})

    def _release(self):
        if self.lease is not None:
            lease=self.lease
            if lease.Release() is False: raise RuntimeError("SHARED_OWNER_RELEASE_UNCONFIRMED")
            self.lease=None

    def Cleanup(self,cancel=None):
        self._worker()
        confirmed=self.cleanup_confirmed if self.lease is None else self.sid is None
        try:
            if self.lease is not None and self.sid is not None and self.rid<2**32-1:
                self.rid+=1; rid=self.rid; deadline=self.clock()+1
                request=Request("DO",(self.sid,str(rid),"CANCEL"))
                for poll in range(8):
                    reply=self._reply(self._request(request if poll==0 else Request("POLL",(self.sid,str(rid))),
                        threading.Event(),deadline),"DO",self.sid,rid)
                    if reply.status=="OK" and reply.Field("cleanup_complete")=="1": confirmed=True; break
        except (OSError,ValueError,TimeoutError,InterruptedError):
            confirmed=False
        finally:
            try:
                if self.store is not None: self.store.Close()
            except (OSError,ValueError): confirmed=False
            try: self._release()
            except (OSError,ValueError,RuntimeError): confirmed=False
            self.cleanup_confirmed=confirmed
            self.status="CLOSED" if confirmed else "UNKNOWN"
        return InstallationOutcome(InstallationResult.Ok if confirmed else InstallationResult.Unknown,
                                   "CLEANUP_CONFIRMED" if confirmed else "REMOTE_CLEANUP_UNCONFIRMED")
