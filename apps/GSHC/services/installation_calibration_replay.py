"""Bounded read-only replay of exact host source/role/validation-use archives."""
from dataclasses import asdict,dataclass, replace
import hashlib
import json
from pathlib import Path

from services.installation_calibration_backend import (InstallationBinding_Parse, InstallationCapabilities,
    InstallationOutcome, InstallationResult)
from services.installation_calibration_contract import InstallationContract_Load
from services.installation_calibration_capture_contract import CaptureProofResult
from services.installation_calibration_data import CapturedPair, SourceSample, WindowTag
from services.installation_calibration_fit import InstallationSession,IntrinsicFitResult,ImuSixFace_Fit, Policy, _digest
from services.installation_calibration_plan import FaceTransaction, InstallationDataset, InstallationPlanResult
from services.installation_calibration_protocol import PairAssembler, SamplePart_Decode


@dataclass(frozen=True)
class InstallationReplay:
    binding: object
    dataset: object
    complete_faces: int
    unconfirmed_faces: int
    file_sha256: str


def InstallationReplay_Load(path):
    contract=InstallationContract_Load(); rules=contract.Read(); dataset=InstallationDataset()
    header=None; binding=None; plan=None; staged=[]; complete=unconfirmed=0
    assembler=None; arrivals={}; raw_pairs=[]; source_error=False
    digest=hashlib.sha256(); size=0; count=0
    with Path(path).open("rb") as stream:
        for _ in range(1+3*rules["limits"]["records"]+2*rules["limits"]["face_transactions"]+2*rules["limits"]["evaluations"]):
            line=stream.readline(16385)
            if not line: break
            size+=len(line); digest.update(line); count+=1
            if len(line)>16384 or size>32*1024*1024 or not line.endswith(b"\n"): raise ValueError("ARCHIVE_TRUNCATED_OR_OVERSIZE")
            item=json.loads(line)
            if type(item) is not dict: raise ValueError("ARCHIVE_RECORD_OBJECT")
            if header is None:
                if item.get("kind")!="header" or item.get("format")!="silverstar.installation-raw" or item.get("version")!=1:
                    raise ValueError("ARCHIVE_HEADER")
                header=item["info"]
                if header["contract_sha256"]!=contract.sha256: raise ValueError("EXACT_RECORDED_CONTRACT_REQUIRED")
                info=header["binding"]; face=info["face_plan"]
                caps=InstallationCapabilities(InstallationOutcome(InstallationResult.Ok,"RECORDED"),
                    face["train_pairs"],face["holdout_pairs"],rules["limits"]["records"],header["simulated"])
                payload=json.dumps(info,separators=(",",":"),sort_keys=True).encode()
                binding=InstallationBinding_Parse(payload,"B-"+info["binding_digest"][:30],caps)
                dataset.Bind(binding.digest)
                assembler=PairAssembler(header["sid"],binding.binding,binding.boot,{s.role:s for s in binding.sources},
                    quality_policy=binding.capture_policy)
                continue
            kind=item.get("kind")
            if kind=="face_begin":
                if plan is not None: raise ValueError("OVERLAPPING_FACE_TRANSACTIONS")
                plan=FaceTransaction(**item["plan"]); staged=[]; raw_pairs=[]; source_error=False
                if item.get("adaptation") is True: dataset.BeginAdaptation()
            elif kind=="source_part":
                if plan is None: raise ValueError("SOURCE_WITHOUT_TRANSACTION")
                line=bytes.fromhex(item["line_hex"]); received=item["pc_receive_us"]
                if len(line)>511 or type(received) is not int or received<0: raise ValueError("SOURCE_PART_BUDGET")
                try:
                    pid,part,_,sample=SamplePart_Decode(line,header["sid"],binding.binding,{s.role:s for s in binding.sources})
                    if binding.capture_qualification.Sample_Check(sample)!=CaptureProofResult.Qualified:
                        raise ValueError("RECORDED_SOURCE_TIME_BOUND_NOT_HONORED")
                    arrivals.setdefault((pid,part),received)
                    pair=assembler.Feed(line,received)
                    if pair is not None:
                        pair=replace(pair,imu=replace(pair.imu,pc_receive_us=arrivals.pop((pid,"IMU"))),
                                     mag=replace(pair.mag,pc_receive_us=arrivals.pop((pid,"MAG"))))
                        raw_pairs.append(pair)
                    elif pid<=assembler.highwater: arrivals.pop((pid,part),None)
                    if len(raw_pairs)>128 or len(arrivals)>8: raise ValueError("RAW_PART_ASSEMBLY_BUDGET")
                except ValueError: source_error=True
            elif kind=="pair":
                if plan is None: raise ValueError("PAIR_WITHOUT_TRANSACTION")
                tag=WindowTag(**item["tag"])
                a=SourceSample(binding.sources[0],**item["imu"]); m=SourceSample(binding.sources[1],**item["mag"])
                pair=CapturedPair(header["sid"],binding.boot,item["pair_id"],tag,a,m)
                if not raw_pairs or pair!=raw_pairs.pop(0): raise ValueError("RAW_SOURCE_PART_MISMATCH")
                expected=plan.train_window if len(staged)<plan.train_pairs else plan.holdout_window
                split="TRAIN" if len(staged)<plan.train_pairs else "HOLDOUT"
                if (tag.window,tag.pose,tag.face,tag.attempt,tag.stage,tag.split)!=(expected,plan.pose,plan.face,plan.attempt,plan.stage,split):
                    raise ValueError("ARCHIVE_ROLE_BOUNDARY")
                staged.append(pair.RawPair(binding.capture_policy))
                if len(staged)>plan.train_pairs+plan.holdout_pairs: raise ValueError("ARCHIVE_FACE_CAPACITY")
            elif kind=="face_end":
                if plan is None or item["rid"]!=plan.rid: raise ValueError("ARCHIVE_TRANSACTION_END")
                if item["result"]=="COMPLETE":
                    if (source_error or raw_pairs or len(staged)!=plan.train_pairs+plan.holdout_pairs
                            or item["train"]!=plan.train_pairs or item["holdout"]!=plan.holdout_pairs):
                        raise ValueError("ARCHIVE_COMPLETE_COUNTS")
                    for previous,current in zip(staged,staged[1:]):
                        for source,key in zip(binding.sources,("imu_seq","mag_seq")):
                            if (getattr(current,key)-getattr(previous,key))%2**32!=source.sequence_stride:
                                raise ValueError("RECORDED_CONTINUOUS_FACE_GAP")
                    if dataset.AddTransaction(staged)!=InstallationPlanResult.Accepted: raise ValueError(dataset.reason)
                    complete+=1
                else: unconfirmed+=1; dataset.Invalidate("UNCONFIRMED_RECORDED_FACE")
                plan=None; staged=[]
            elif kind=="validation_retire": dataset.BeginAdaptation()
            elif kind=="validation_use":
                if plan is not None: raise ValueError("VALIDATION_DURING_CAPTURE")
                policy=Policy(**item["policy"])
                if _digest(item["policy"])!=item["policy_digest"] or dataset.ValidationGate()!=InstallationPlanResult.Accepted:
                    raise ValueError("RECORDED_VALIDATION_CONTEXT")
                windows=sorted({r.window for r in dataset.FreshHoldout()})
                mathematical=InstallationSession(dataset.EvaluationRecords(),binding.convention)
                training=InstallationSession(dataset.FittingRecords(),binding.convention)
                status,accel,gyro=ImuSixFace_Fit(training,binding.accel,gravity=policy.gravity)
                if (status!=IntrinsicFitResult.Candidate or _digest(item["accel_candidate"])!=_digest(asdict(accel))
                        or tuple(item["gyro_bias"])!=gyro): raise ValueError("RECORDED_TRAINING_FIT_CHANGED")
                if windows!=item["windows"] or mathematical.ContextDigest(accel,binding.mag,policy)!=item["context_digest"]:
                    raise ValueError("RECORDED_VALIDATION_LEAK_OR_CHANGE")
                dataset.MarkValidationObserved()
            else: raise ValueError("UNKNOWN_ARCHIVE_RECORD")
        else:
            if stream.read(1): raise ValueError("ARCHIVE_RECORD_COUNT")
    if header is None: raise ValueError("EMPTY_ARCHIVE")
    if plan is not None: unconfirmed+=1; dataset.Invalidate("PARTIAL_RECORDED_FACE")
    return InstallationReplay(binding,dataset,complete,unconfirmed,digest.hexdigest())
