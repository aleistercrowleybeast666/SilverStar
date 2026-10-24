"""Per-face automatic plan and validation-use ledger. Raw labels never change."""
from dataclasses import dataclass, replace
from copy import copy
from enum import Enum

from services.installation_calibration_contract import InstallationContract_Load
from services.installation_calibration_fit import FACES, _digest


class InstallationPlanResult(str,Enum):
    Accepted="ACCEPTED"
    NeedTraining="NEED_TRAINING"
    NeedFreshValidation="NEED_FRESH_VALIDATION"
    Invalid="INVALID"
    Capacity="CAPACITY"


@dataclass(frozen=True)
class FaceTransaction:
    rid: int
    stage: str
    face: str
    attempt: int
    train_pairs: int
    holdout_pairs: int
    mode: str="FIT_CHECK"

    def __post_init__(self):
        if (type(self.rid) is not int or not 1<=self.rid<2**32 or self.stage not in ("SIX_FACE","SUPPLEMENT")
                or self.face not in FACES or type(self.attempt) is not int or not 1<=self.attempt<=65535
                or self.mode not in ("FIT_CHECK","CHECK_ONLY") or type(self.train_pairs) is not int
                or type(self.holdout_pairs) is not int or not 3<=self.holdout_pairs<=64
                or (self.mode=="FIT_CHECK" and not 3<=self.train_pairs<=64)
                or (self.mode=="CHECK_ONLY" and self.train_pairs!=0)):
            raise ValueError("bounded automatic face plan required")

    @property
    def train_window(self): return f"{self.rid:08X}T"
    @property
    def holdout_window(self): return f"{self.rid:08X}V"
    @property
    def pose(self): return f"P{self.rid:08X}"


class InstallationDataset:
    """Bounded records with a separate validation-use ledger, not relabelled data.

    Initial six-face TRAIN/HOLDOUT interleaving is supported. Once validation
    influences a decision, every older holdout is retired after new training.
    Fresh evidence must follow the last added training record.
    """
    def __init__(self):
        self.limit=InstallationContract_Load().Read()["limits"]["records"]
        self._records=[]; self._source_keys=set(); self._pair_ids=set()
        self._observed=set(); self._retired=set(); self._revision=0
        self._last_training_index=-1; self._adaptive=False
        self._context=None; self.candidate=None; self.reason="NO_DATA"

    @property
    def records(self): return tuple(self._records)
    @property
    def retired_windows(self): return frozenset(self._retired)
    @property
    def training_revision(self): return self._revision

    def Bind(self,context_digest):
        if self._context is not None and self._context!=context_digest:
            self.candidate=None; self.reason="CONTEXT_CHANGED"
            return InstallationPlanResult.Invalid
        self._context=context_digest
        return InstallationPlanResult.Accepted

    def Add(self,record):
        if len(self._records)>=self.limit:
            self.reason="DATASET_CAPACITY"; return InstallationPlanResult.Capacity
        keys=(("IMU",record.imu_epoch,record.imu_seq,record.imu_us),
              ("MAG",record.mag_epoch,record.mag_seq,record.mag_us))
        if record.pair_id in self._pair_ids or any(k in self._source_keys for k in keys):
            self.reason="OVERLAPPING_SOURCE_SAMPLES"; return InstallationPlanResult.Invalid
        if self._records:
            first=self._records[0]
            if (record.session,record.boot,record.imu,record.mag,record.imu_epoch,record.mag_epoch,record.clock,
                    record.acquisition_intrinsic_ids,record.acquisition_intrinsic_generations)!=(
                    first.session,first.boot,first.imu,first.mag,first.imu_epoch,first.mag_epoch,first.clock,
                    first.acquisition_intrinsic_ids,first.acquisition_intrinsic_generations):
                self.reason="SOURCE_CHANGED"; return InstallationPlanResult.Invalid
            last=self._records[-1]
            if record.imu_us<=last.imu_us or record.mag_us<=last.mag_us:
                self.reason="SOURCE_TIME_REVERSED"; return InstallationPlanResult.Invalid
        if record.split=="TRAIN":
            if self._observed:
                self._adaptive=True; self._revision+=1
                self._retired.update(r.window for r in self._records if r.split=="HOLDOUT")
                self._observed.clear()
            if self._adaptive:
                # A later supplementary training segment also invalidates any
                # holdout collected before this final new training segment.
                self._retired.update(r.window for r in self._records if r.split=="HOLDOUT")
            self._last_training_index=len(self._records)
            self.candidate=None
        self._records.append(record); self._pair_ids.add(record.pair_id); self._source_keys.update(keys)
        return InstallationPlanResult.Accepted

    def FittingRecords(self):
        return tuple(r for r in self._records if r.split=="TRAIN")

    def FreshHoldout(self):
        return tuple(r for i,r in enumerate(self._records) if r.split=="HOLDOUT" and r.window not in self._retired
                     and (not self._adaptive or i>self._last_training_index))

    def ValidationGate(self):
        if {r.face for r in self.FittingRecords()}!=set(FACES):
            self.reason="TRAIN_SIX_FACES_REQUIRED"; return InstallationPlanResult.NeedTraining
        if {r.face for r in self.FreshHoldout()}!=set(FACES):
            self.reason="FRESH_HOLDOUT_ALL_FACES_REQUIRED"; return InstallationPlanResult.NeedFreshValidation
        return InstallationPlanResult.Accepted

    def EvaluationRecords(self):
        fresh={r.window for r in self.FreshHoldout()}
        return tuple(r for r in self._records if r.split=="TRAIN" or r.window in fresh)

    def MarkValidationObserved(self):
        self._observed.update(r.window for r in self.FreshHoldout())

    def Invalidate(self,reason):
        self.candidate=None; self.reason=reason
        self._adaptive=True
        self._retired.update(r.window for r in self._records if r.split=="HOLDOUT")
        self._observed.clear()

    def BeginAdaptation(self):
        self.Invalidate("ADAPTATION_REQUIRES_FRESH_VALIDATION")
        self._revision+=1

    def AddTransaction(self,records):
        probe=copy(self)
        for name in ("_records",): setattr(probe,name,list(getattr(self,name)))
        for name in ("_source_keys","_pair_ids","_observed","_retired"):
            setattr(probe,name,set(getattr(self,name)))
        for record in records:
            result=probe.Add(record)
            if result!=InstallationPlanResult.Accepted:
                self.reason=probe.reason
                return result
        self.__dict__.update(probe.__dict__)
        return InstallationPlanResult.Accepted

    def Snapshot(self):
        return {"records":len(self._records),"training":len(self.FittingRecords()),"fresh_holdout":len(self.FreshHoldout()),
                "retired_windows":tuple(sorted(self._retired)),"observed_windows":tuple(sorted(self._observed)),
                "revision":self._revision,"reason":self.reason,"apply_allowed":False,"save_allowed":False}
