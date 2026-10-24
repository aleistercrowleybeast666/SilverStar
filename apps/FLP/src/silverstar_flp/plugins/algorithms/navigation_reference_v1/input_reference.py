"""Isolated host input adapter. No FLP registration, hardware, or implicit replay.

This revision deliberately rejects delayed data instead of fusing it at a wrong
time. The retained adverse corpus exposes that incomplete capability explicitly.
"""
from dataclasses import dataclass, replace
from enum import IntEnum
import math
import numpy as np

from . import eskf20_reference as eskf
from . import inekf15_reference as inv15
from . import inekf20_reference as inv20


class Result(IntEnum):
    OK=0
    INVALID=1
    IDENTITY=2
    UNTRUSTED_TIME=3
    FUTURE=4
    DELAYED_UNSUPPORTED=5
    DUPLICATE=6
    OUT_OF_ORDER=7
    NUMERIC=8
    WRONG_STAGE=9
    FIELD_REJECTED=10


@dataclass(frozen=True)
class Identity:
    epoch:int
    source:int
    calibration:int


@dataclass(frozen=True)
class Event:
    identity:Identity
    sample_us:int
    receive_us:int
    sequence:int
    trusted:int


def unsigned(value,bits):
    return type(value) is int and 0 <= value < 2**bits


class Ledger:
    def __init__(self,identity):
        if not isinstance(identity,Identity) or not all(unsigned(v,32) for v in vars(identity).values()):
            raise ValueError('identity')
        self.identity=identity
        self.last_sequence=None
        self.last_sample_us=0

    def check(self,event,state_us):
        if (not isinstance(event,Event) or not isinstance(event.identity,Identity)
            or not unsigned(state_us,64) or not unsigned(event.sample_us,64)
            or not unsigned(event.receive_us,64) or not unsigned(event.sequence,32)
            or type(event.trusted) is not int or event.trusted not in (0,1)
            or not all(unsigned(v,32) for v in vars(event.identity).values())):
            return Result.INVALID
        if event.identity != self.identity: return Result.IDENTITY
        if not event.trusted: return Result.UNTRUSTED_TIME
        if event.sample_us>event.receive_us or self.last_sample_us>state_us: return Result.INVALID
        if event.sample_us>state_us: return Result.FUTURE
        if event.sample_us<state_us: return Result.DELAYED_UNSUPPORTED
        if self.last_sequence is not None:
            delta=(event.sequence-self.last_sequence) % 2**32
            if delta==0: return Result.DUPLICATE
            if delta>=2**31 or event.sample_us<=self.last_sample_us: return Result.OUT_OF_ORDER
        return Result.OK

    def consume(self,event,state_us):
        result=self.check(event,state_us)
        if result is Result.OK:
            self.last_sequence,self.last_sample_us=event.sequence,event.sample_us
        return result


def magnetic_prepare(sensor_uT,covariance_uT2,stage,bias,soft,reference,ratio_bounds):
    if stage!=1: return Result.WRONG_STAGE,None
    try:
        raw=np.asarray(sensor_uT,dtype=np.float64)
        noise=np.asarray(covariance_uT2,dtype=np.float64)
        bias=np.asarray(bias,dtype=np.float64)
        soft=np.asarray(soft,dtype=np.float64)
        if raw.shape!=(3,) or noise.shape!=(3,3) or bias.shape!=(3,) or soft.shape!=(3,3):
            return Result.INVALID,None
        if not all(np.isfinite(v).all() for v in (raw,noise,bias,soft)): return Result.INVALID,None
        if not np.array_equal(noise,noise.T) or not np.array_equal(soft,soft.T): return Result.INVALID,None
        np.linalg.cholesky(noise);np.linalg.cholesky(soft)
        lo,hi=ratio_bounds
        if not all(type(x) in (int,float) and math.isfinite(x) for x in (reference,lo,hi)):
            return Result.INVALID,None
        if reference<=0 or not 0<lo<hi: return Result.INVALID,None
        corrected=soft@(raw-bias)
        transformed=soft@noise@soft.T
        if not np.isfinite(corrected).all() or not np.isfinite(transformed).all(): return Result.NUMERIC,None
        if not lo<=np.linalg.norm(corrected)/reference<=hi: return Result.FIELD_REJECTED,None
        return Result.OK,(corrected,transformed)
    except (ValueError,TypeError,OverflowError,np.linalg.LinAlgError):
        return Result.INVALID,None


def _positive_native32(matrix):
    if matrix.shape!=(3,3) or not np.isfinite(matrix).all() or not np.array_equal(matrix,matrix.T):return False
    lower=np.zeros((3,3),dtype=np.float32)
    for row in range(3):
        for column in range(row+1):
            value=matrix[row,column]
            for k in range(column):value=np.float32(value-np.float32(lower[row,k]*lower[column,k]))
            if not np.isfinite(value):return False
            if row==column:
                if value<=0:return False
                lower[row,column]=np.sqrt(value)
            else:
                lower[row,column]=np.float32(value/lower[column,column])
                if not np.isfinite(lower[row,column]):return False
    return True


def magnetic_prepare_native32(sensor_uT,covariance_uT2,stage,bias,soft,reference,ratio_bounds):
    """Materialize the firmware's binary32 physical-input boundary once.

    This is arithmetic-format compatibility, not an independent mathematical
    oracle. Generic What-if retains the float64 algebra above; independent
    NumPy S R S^T/closed-form tests validate the physical transform separately.
    """
    if stage!=1:return Result.WRONG_STAGE,None
    try:
        with np.errstate(over='ignore',invalid='ignore'):
            raw=np.asarray(sensor_uT,dtype=np.float32);noise=np.asarray(covariance_uT2,dtype=np.float32)
            bias=np.asarray(bias,dtype=np.float32);soft=np.asarray(soft,dtype=np.float32)
            reference=np.float32(reference);lo,hi=(np.float32(x) for x in ratio_bounds)
    except (TypeError,ValueError,OverflowError):return Result.INVALID,None
    if (raw.shape!=(3,) or bias.shape!=(3,) or not np.isfinite(raw).all() or not np.isfinite(bias).all()
            or not all(np.isfinite(v) for v in (reference,lo,hi)) or not reference>0 or not 0<lo<hi):return Result.INVALID,None
    with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
        if not _positive_native32(soft) or not _positive_native32(noise):return Result.INVALID,None
        corrected=np.zeros(3,dtype=np.float32);transformed=np.zeros((3,3),dtype=np.float32)
        norm2=np.float32(0)
        for row in range(3):
            value=np.float32(0)
            for column in range(3):
                product=np.float32(soft[row,column]*np.float32(raw[column]-bias[column]))
                value=np.float32(value+product)
            corrected[row]=value;norm2=np.float32(norm2+np.float32(value*value))
        ratio=np.float32(np.sqrt(norm2)/np.float32(reference))
        if not np.isfinite(corrected).all() or not np.isfinite(ratio):return Result.NUMERIC,None
        if not lo<=ratio<=hi:return Result.FIELD_REJECTED,None
        for row in range(3):
            for column in range(row+1):
                value=np.float32(0)
                for i in range(3):
                    for j in range(3):
                        product=np.float32(np.float32(soft[row,i]*noise[i,j])*soft[column,j])
                        value=np.float32(value+product)
                transformed[row,column]=value;transformed[column,row]=value
        if not np.isfinite(transformed).all():return Result.NUMERIC,None
        if not _positive_native32(transformed):return Result.NUMERIC,None
        return Result.OK,(corrected.astype(float),transformed.astype(float))


class ReferenceSession:
    """Single-owner co-timed adapter for the three already-defined host models.

    Integer microseconds are authoritative, relative to the supplied epoch origin.
    Constructor requires an explicitly initialized t=0 state. No prior is invented.
    """
    def __init__(self,model,state,origin_us,identities,magnetic_native_float32=False):
        expected={'eskf20':eskf.Eskf20State,'inekf15':inv15.InEkf15State,'inekf20':inv20.InEkf20State}
        if model not in expected or type(state) is not expected[model] or state.time_s!=0. or not unsigned(origin_us,64):
            raise ValueError('model_or_initial_time')
        self.model,self.state,self.origin_us,self.state_us=model,state,origin_us,origin_us
        self.ledgers={kind:Ledger(identity) for kind,identity in identities.items()}
        self.magnetic_native_float32=bool(magnetic_native_float32)

    def predict_pair(self,start_us,end_us,gyro_pair,force_pair,gravity,density):
        """Two equal-duration calibrated half means, committed as one interval.

        Odd microsecond intervals have a fractional half duration; do not round
        a midpoint or let a successful first half publish a partial state.
        """
        if (not unsigned(start_us,64) or not unsigned(end_us,64) or start_us!=self.state_us
            or not 0<end_us-start_us<=20000): return Result.INVALID
        try:
            density=np.asarray(density,dtype=np.float64)
            gyro_pair=np.asarray(gyro_pair,dtype=np.float64)
            force_pair=np.asarray(force_pair,dtype=np.float64)
            if (density.shape!=(12,) or gyro_pair.shape!=(2,3) or force_pair.shape!=(2,3)
                or not all(np.isfinite(x).all() for x in (density,gyro_pair,force_pair))
                or np.any(density<0)): return Result.INVALID
        except (TypeError,ValueError,OverflowError):
            return Result.INVALID
        if self.model=='eskf20': density=np.r_[density[3:6],density[:3],density[6:]]
        function={'eskf20':eskf.Eskf20_Predict,'inekf15':inv15.InEkf15_Predict,'inekf20':inv20.InEkf20_Predict}[self.model]
        candidate=self.state
        for half in range(2):
            step=function(candidate,gyro_pair[half],force_pair[half],gravity,density,(end_us-start_us)/2_000_000)
            if step.result.value!='ok': return step.result.value
            candidate=step.state
        self.state=replace(candidate,time_s=(end_us-self.origin_us)/1_000_000)
        self.state_us=end_us
        return Result.OK

    def predict(self,start_us,end_us,omega,force,gravity,density):
        """density order: gyro, accel, gyro-bias RW, accel-bias RW (3 axes each)."""
        if (not unsigned(start_us,64) or not unsigned(end_us,64) or start_us!=self.state_us
            or not 0<end_us-start_us<=20000): return Result.INVALID
        try:
            density=np.asarray(density,dtype=np.float64)
            if density.shape!=(12,) or not np.isfinite(density).all() or np.any(density<0):
                return Result.INVALID
        except (TypeError,ValueError,OverflowError):
            return Result.INVALID
        # Historical mathematical kernels differ in process-noise column order.
        if self.model=='eskf20': density=np.r_[density[3:6],density[:3],density[6:]]
        function={'eskf20':eskf.Eskf20_Predict,'inekf15':inv15.InEkf15_Predict,'inekf20':inv20.InEkf20_Predict}[self.model]
        step=function(self.state,omega,force,gravity,density,(end_us-start_us)*1e-6)
        if step.result.value!='ok': return step.result.value
        # Anchor to the verified integer endpoint; no epsilon or sample retiming.
        self.state=replace(step.state,time_s=(end_us-self.origin_us)/1_000_000)
        self.state_us=end_us
        return Result.OK

    def update_vector(self,event,kind,measured,covariance,gate):
        if kind not in ('position','velocity') or kind not in self.ledgers: return Result.INVALID
        if type(gate) not in (int,float) or not math.isfinite(gate) or gate<=0: return Result.INVALID
        ledger=self.ledgers[kind]
        classification=ledger.check(event,self.state_us)
        if classification is not Result.OK: return classification
        function={'eskf20':eskf.Eskf20_UpdateVector,'inekf15':inv15.InEkf15_Update,'inekf20':inv20.InEkf20_UpdateVector}[self.model]
        step=function(self.state,measured,covariance,kind,self.state.time_s,gate)
        if step.result.value in ('ok','rejected_nis','rejected_correction'):
            assert ledger.consume(event,self.state_us) is Result.OK
        if step.result.value=='ok': self.state=step.state
        return step.result.value

    def update_magnetic(self,event,sensor_uT,covariance_uT2,stage,bias,soft,reference_uT,ratio_bounds,gate):
        if self.model=='inekf15': return 'unsupported_observation'
        if type(gate) not in (int,float) or not math.isfinite(gate) or gate<=0: return Result.INVALID
        if 'magnetic' not in self.ledgers: return Result.IDENTITY
        ledger=self.ledgers['magnetic']
        classification=ledger.check(event,self.state_us)
        if classification is not Result.OK: return classification
        prepare=magnetic_prepare_native32 if self.magnetic_native_float32 else magnetic_prepare
        classification,prepared=prepare(sensor_uT,covariance_uT2,stage,bias,soft,reference_uT,ratio_bounds)
        if classification is Result.FIELD_REJECTED:
            assert ledger.consume(event,self.state_us) is Result.OK
        if classification is not Result.OK: return classification
        sample=eskf.MagneticSample(prepared[0],prepared[1],reference_uT,self.state.time_s,
                                  'magnetometer_sensor','hard_soft_iron_only')
        function=eskf.Eskf20_UpdateMagnetic if self.model=='eskf20' else inv20.InEkf20_UpdateMagnetic
        step=function(self.state,sample,gate)
        if step.result.value in ('ok','rejected_nis','rejected_correction'):
            assert ledger.consume(event,self.state_us) is Result.OK
        if step.result.value=='ok': self.state=step.state
        return step.result.value
