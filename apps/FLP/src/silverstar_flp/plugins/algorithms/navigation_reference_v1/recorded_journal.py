"""Trusted host interpretation of the exact declarative NAVIGATION_OPERATION_PART.

This is not a fallback container parser. LogOpenCoordinator first validates the
SSLOG container, exact Descriptor/Catalog/package, and immutable dataset. The
versioned operation contract is interpreted only by this installed algorithm.
Recorded configuration completeness does not establish target numerical fidelity.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import struct
import zlib
import numpy as np

from .buffered_replay import BufferedSession, result_code
from .firmware_configuration import _Parameters_Read, _QuaternionRotation, _Plain
from .input_reference import Event, Identity

SCHEMA = "silverstar.navigation-operation-journal/2"
RECORD = "NAVIGATION_OPERATION_PART"
MAX_OPERATIONS = 1000000
_HEADERS = {"epoch", "operation", "transaction_crc32", "total_size", "part_index",
            "part_count", "kind", "algorithm_id", "revision", "data"}
_MODELS = {"eskf20": (1, 4, 20), "inekf15": (2, 5, 15), "inekf20": (3, 6, 20)}


def _uint(value, bits):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= value < 2**bits:
        raise ValueError("navigation_journal_integer")
    return int(value)


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def get(self, fmt):
        size = struct.calcsize('<'+fmt)
        if self.offset+size > len(self.data):
            raise ValueError("navigation_journal_truncated_operation")
        values = struct.unpack_from('<'+fmt, self.data, self.offset)
        self.offset += size
        return values[0] if len(values) == 1 else values

    def identity(self):
        return Identity(*self.get('III'))

    def array(self, count, fmt='d'):
        return np.asarray(self.get(str(count)+fmt), dtype=float)

    def finish(self):
        if self.offset != len(self.data):
            raise ValueError("navigation_journal_extra_operation_bytes")


def _transactions(dataset, model):
    records = dataset.Records_Get(RECORD)
    if not records:
        raise ValueError("navigation_complete_journal_missing")
    if len(records) > MAX_OPERATIONS*26:
        raise ValueError("navigation_journal_operation_limit")
    # The legacy 144-byte INITIAL_STATE has NO epoch field. Choose exactly one
    # explicitly initialized journal in the selected mission, never infer an
    # epoch from calibration generation or a default zero.
    from silverstar_flp.core.mission import MissionReplayBounds_Get
    if dataset.initial_state is None or dataset.start_timestamp_us is None:
        raise ValueError("navigation_recorded_initial_state_missing")
    bounds=MissionReplayBounds_Get(dataset,source_end_timestamp_us=max(r.timestamp_us for r in records))
    last_by_epoch={}
    for record in records:
        epoch_key=_uint(record.payload.get('epoch'),32)
        last_by_epoch[epoch_key]=max(last_by_epoch.get(epoch_key,0),record.timestamp_us)
    starts=[record for record in records if record.payload.get('kind')==0
            and record.payload.get('part_index')==0 and record.timestamp_us<=bounds.end_timestamp_us
            and last_by_epoch[_uint(record.payload.get('epoch'),32)]>=bounds.start_timestamp_us]
    if len(starts)!=1:
        raise ValueError("navigation_journal_mission_epoch_missing_or_ambiguous")
    epoch = _uint(starts[0].payload.get('epoch'),32)
    selected = [record for record in records if _uint(record.payload.get('epoch'), 32) == epoch]
    if not selected:
        raise ValueError("navigation_journal_epoch_missing")
    if any(record.record_version!=1 or record.payload_length!=180 for record in selected):
        raise ValueError("navigation_journal_record_layout")
    output, index, revision = [], 0, None
    while index < len(selected):
        first = selected[index].payload
        if set(first) != _HEADERS:
            raise ValueError("navigation_journal_fields")
        header = {k: _uint(first[k], 8 if k in {'part_index','part_count','kind','algorithm_id'}
                         else 16 if k in {'revision','total_size'} else 32) for k in _HEADERS-{'data'}}
        if (header['operation'] != len(output) or header['revision'] not in (1,2)
                or header['algorithm_id'] != _MODELS[model][1]
                or not 0 < header['total_size'] <= 4096 or header['kind'] > (4 if header['revision']==2 else 3)
                or header['part_index'] != 0
                or header['part_count'] != (header['total_size']+159)//160):
            raise ValueError("navigation_journal_header_or_sequence")
        if revision is not None and header['revision']!=revision:
            raise ValueError("navigation_journal_mixed_revision")
        revision=header['revision']
        payload = bytearray()
        for part_index in range(header['part_count']):
            if index >= len(selected):
                raise ValueError("navigation_journal_missing_part")
            part = selected[index].payload
            if set(part) != _HEADERS or any(part[key] != value for key,value in header.items() if key!='part_index') or part['part_index'] != part_index:
                raise ValueError("navigation_journal_conflicting_part")
            raw = part['data']
            if not isinstance(raw, (tuple,list,bytes,bytearray,np.ndarray)) or len(raw) != 160:
                raise ValueError("navigation_journal_part_size")
            payload.extend(_uint(value,8) for value in raw)
            index += 1
        if any(payload[header['total_size']:]):
            raise ValueError("navigation_journal_nonzero_padding")
        payload = bytes(payload[:header['total_size']])
        if zlib.crc32(payload) != header['transaction_crc32']:
            raise ValueError("navigation_journal_transaction_crc")
        sizes={0:464+_MODELS[model][2]**2*8,1:128,3:16,4:288}
        if header['kind'] in sizes and len(payload)!=sizes[header['kind']]:
            raise ValueError("navigation_journal_operation_size")
        if header['kind']==2:
            if len(payload)<4:
                raise ValueError("navigation_journal_operation_size")
            group=struct.unpack_from('<I',payload)[0]
            if group>2 or len(payload)!=(184 if group==2 else 168):
                raise ValueError("navigation_journal_operation_size")
        output.append((header['kind'], payload))
        if len(output) > MAX_OPERATIONS:
            raise ValueError("navigation_journal_operation_limit")
    if len(output)<3 or output[0][0]!=0 or output[-1][0]!=3 or any(kind in (0,3) for kind,_ in output[1:-1]):
        raise ValueError("navigation_journal_unsealed_or_reinitialized")
    return epoch, output,starts[0].timestamp_us,revision


def _initial(model, data):
    from .plugin import _State_Build
    reader = Reader(data)
    if reader.get('I') != _MODELS[model][0]:
        raise ValueError("navigation_journal_model")
    origin, imu = reader.get('Q'), reader.identity()
    identities = {kind: reader.identity() for kind in ('position','velocity','magnetic')}
    maximum_delay = reader.get('Q')
    geodetic=reader.get('iii')
    magnetic_physical,magnetic_descriptor,magnetic_bound=reader.get('H'),reader.get('H'),reader.get('I')
    bindings=dict(origin_geodetic=list(geodetic),magnetic_physical=magnetic_physical,
        magnetic_descriptor=magnetic_descriptor,magnetic_bound=magnetic_bound)
    gravity, density = reader.array(3), reader.array(12)
    initial = dict(rotation=reader.array(9).reshape(3,3),position=reader.array(3),
        velocity=reader.array(3),gyro_bias=reader.array(3),accel_bias=reader.array(3))
    installation, inclination, declination = reader.array(9).reshape(3,3), reader.get('d'), reader.get('d')
    dimension = _MODELS[model][2]
    initial['covariance'] = reader.array(dimension*dimension).reshape(dimension,dimension)
    if model != 'inekf15':
        initial.update(installation=installation,inclination=inclination,declination=declination)
    reader.finish()
    if any(identity.epoch != imu.epoch for identity in identities.values()):
        raise ValueError("navigation_journal_initial_identity")
    return BufferedSession(model,_State_Build(model,initial),origin,identities,gravity,density,maximum_delay,magnetic_native_float32=True), imu,bindings


def _parameter_binding(dataset, model, session,bindings):
    context = dataset.semantic_context
    component = 'silverstar.algorithm.estimator.'+model
    if context is None or component not in context.firmware_algorithm_ids:
        raise ValueError("navigation_journal_firmware_membership")
    groups = [group for group in context.FirmwareParameterSets_Get() if group['component']==component]
    if len(groups)!=1:
        raise ValueError("navigation_journal_actual_parameter_set")
    values, contract, group = _Parameters_Read(model,groups[0])
    state = session.state
    position=state.position if model=='eskf20' else state.group[:3,4]
    velocity=state.velocity if model=='eskf20' else state.group[:3,3]
    adopted=dataset.initial_state.payload
    if (not np.array_equal(position,np.zeros(3)) or
            list(bindings['origin_geodetic'])!=[adopted[name] for name in (
                'gnss_origin_latitude_e7','gnss_origin_longitude_e7','gnss_origin_height_mm')] or
            not np.array_equal(velocity,adopted['initial_velocity_enu_mps'])):
        raise ValueError("navigation_journal_geodetic_or_velocity_origin_mismatch")
    gnss=session.current.ledgers['position'].identity
    if (gnss!=session.current.ledgers['velocity'].identity or gnss.calibration!=0 or
            not any(endpoint['device_class']=='SYSTEM_DEVICE_CLASS_GNSS' and endpoint['instance_id']==gnss.source
                    for endpoint in context.capability_endpoints)):
        raise ValueError("navigation_journal_gnss_endpoint_mismatch")
    magnetic=session.current.ledgers['magnetic'].identity
    if bindings['magnetic_bound'] not in (0,1) or (model=='inekf15' and bindings['magnetic_bound']):
        raise ValueError("navigation_journal_magnetic_binding")
    if bindings['magnetic_bound']:
        endpoint=context.CapabilityEndpoint_Get(bindings['magnetic_descriptor'])
        if (endpoint is None or endpoint['device_class']!='SYSTEM_DEVICE_CLASS_MAGNETOMETER' or
                endpoint['physical_device_id']!=bindings['magnetic_physical'] or
                endpoint['instance_id']!=values['magnetic_instance'] or
                magnetic.source!=(bindings['magnetic_physical']<<8)|values['magnetic_instance']):
            raise ValueError("navigation_journal_magnetic_endpoint_mismatch")
    elif (bindings['magnetic_physical']!=0 or bindings['magnetic_descriptor']!=0 or magnetic.source!=0 or magnetic.calibration!=0):
        raise ValueError("navigation_journal_unbound_magnetic_identity")
    if not np.array_equal(state.covariance,np.diag([values['initial_variance_'+str(i)] for i in range(contract['dimension'])])):
        raise ValueError("navigation_journal_initial_covariance_parameter_mismatch")
    for field, prefix in [('gyro_bias','initial_gyro_bias_'),('accel_bias','initial_accel_bias_')]:
        if not np.array_equal(getattr(state,field),[values[prefix+axis] for axis in 'xyz']):
            raise ValueError("navigation_journal_initial_bias_parameter_mismatch")
    expected_density = [values[prefix+'_density_'+axis] for prefix in ('gyro','accel','gyro_bias_rw','accel_bias_rw') for axis in 'xyz']
    if not np.array_equal(session.gravity,[0.,0.,-values['gravity_mps2']]) or not np.array_equal(session.density,expected_density):
        raise ValueError("navigation_journal_process_parameter_mismatch")
    if model!='inekf15':
        rotation = _QuaternionRotation([values['installation_q_'+str(i)] for i in range(4)])
        if (not np.allclose(state.installation,rotation,rtol=0,atol=2e-15)
                or state.inclination != values['inclination_rad'] or state.declination != values['declination_rad']):
            raise ValueError("navigation_journal_magnetic_prior_parameter_mismatch")
    if model!='inekf15':
        candidates=[endpoint for endpoint in context.capability_endpoints
            if endpoint['device_class']=='SYSTEM_DEVICE_CLASS_MAGNETOMETER' and endpoint['instance_id']==values['magnetic_instance']]
        bindings['magnetic_endpoint']=_Plain(candidates[0]) if len(candidates)==1 else None
    return _Plain(group)


@dataclass
class RecordedJournal:
    epoch: int
    operations: list
    session: BufferedSession
    imu: Identity
    parameter_group: dict
    sha256: str
    bindings: dict
    revision: int


def RecordedJournal_Read(dataset, model):
    if dataset.semantic_context is None or not dataset.metadata.get('parse_identity') or not dataset.metadata.get('source_log_sha256'):
        raise ValueError("navigation_journal_exact_log_open_required")
    epoch, transactions,initial_timestamp,revision = _transactions(dataset,model)
    session, imu,bindings = _initial(model,transactions[0][1])
    if imu.epoch != epoch or session.state_us!=initial_timestamp:
        raise ValueError("navigation_journal_epoch_mismatch")
    calibration=dataset.semantic_context.calibration
    if (not calibration.ready or not calibration.correction_valid
            or imu.source!=calibration.source_id or imu.calibration!=calibration.start_sequence):
        raise ValueError("navigation_journal_imu_calibration_mismatch")
    from scipy.spatial.transform import Rotation
    recorded_rotation=Rotation.from_quat(dataset.initial_state.payload['q_nb'],scalar_first=True).as_matrix()
    actual_rotation=session.state.rotation if model=='eskf20' else session.state.group[:3,:3]
    if not np.allclose(recorded_rotation,actual_rotation,rtol=0,atol=1e-7):
        raise ValueError("navigation_journal_initial_attitude_mismatch")
    group = _parameter_binding(dataset,model,session,bindings)
    digest = hashlib.sha256(b''.join(bytes([kind])+data for kind,data in transactions)).hexdigest()
    return RecordedJournal(epoch,transactions,session,imu,group,digest,bindings,revision)


def _observation(reader):
    kind, admission = reader.get('I'),reader.get('I')
    if kind>2 or admission not in (0,1,2,9):
        raise ValueError("navigation_journal_observation_kind_or_admission")
    identity = reader.identity()
    sample, receive, sequence, trusted = reader.get('Q'),reader.get('Q'),reader.get('I'),reader.get('I')
    event, gate = Event(identity,sample,receive,sequence,trusted),reader.get('d')
    if kind<2:
        args = (reader.array(3),reader.array(9).reshape(3,3),gate)
    else:
        sensor,covariance=reader.array(3,'f'),reader.array(9,'f').reshape(3,3)
        bias,soft=reader.array(3,'f'),reader.array(9,'f').reshape(3,3)
        reference,lo,hi=reader.get('f'),reader.get('f'),reader.get('f')
        stage=reader.get('I');args=(sensor,covariance,stage,bias,soft,reference,(lo,hi),gate)
    expected,nis,evaluation=reader.get('I'),reader.get('d'),reader.get('Q')
    if expected>16 or (expected in (0,12,13) and (not math.isfinite(nis) or nis<0)) or (expected not in (0,12,13) and not math.isnan(nis)):
        raise ValueError("navigation_journal_result_or_nis")
    reader.finish()
    return kind,admission,event,args,expected,nis,evaluation


def RecordedJournal_Execute(journal, context):
    session=journal.session
    values={row['id']:row['value'] for row in journal.parameter_group['parameters']}
    magnetic_signature=None
    from .magnetic_quality import MagneticQuality,read_evidence,bind_observation
    quality_estimator=MagneticQuality();pending_quality=None
    histories,times,outcomes=[session.state],[session.state_us],[]
    for operation,(kind,data) in enumerate(journal.operations[1:],1):
        context.Cancel_RaiseIfRequested()
        reader=Reader(data)
        if pending_quality is not None and kind!=2:
            raise ValueError("magnetic_quality_observation_missing")
        if kind==1:
            start,end=reader.get('Q'),reader.get('Q');imu=reader.identity()
            gyro,force=reader.array(6).reshape(2,3),reader.array(6).reshape(2,3)
            expected=reader.get('I');reader.finish()
            actual=2 if imu!=journal.imu else session.predict_pair(start,end,gyro,force,session.gravity,session.density)
            if actual!=expected:
                raise ValueError("navigation_recorded_prediction_result_mismatch:"+str(operation))
            if actual==0:
                histories.append(session.state);times.append(session.state_us)
        elif kind==2:
            group,admission,event,args,expected,nis,evaluation=_observation(reader)
            if group==2 and session.current.model=='inekf15':
                raise ValueError("navigation_journal_15d_magnetic_operation")
            if args[-1]!=values[('position','velocity','magnetic')[group]+'_nis_gate']:
                raise ValueError("navigation_journal_gate_parameter_mismatch")
            if group==2 and (not admission or pending_quality is not None and pending_quality['mode']==1):
                if not journal.bindings['magnetic_bound']:
                    raise ValueError("navigation_journal_magnetic_operation_without_binding")
                if args[5]!=values['magnetic_reference_ut'] or tuple(args[6])!=(values['magnetic_min_norm_ratio'],values['magnetic_max_norm_ratio']):
                    raise ValueError("navigation_journal_magnetic_field_parameter_mismatch")
                signature=np.r_[np.ravel(args[3]),np.ravel(args[4]),args[5],args[6]].astype(np.float32).tobytes()
                if magnetic_signature is not None and signature!=magnetic_signature:
                    raise ValueError("navigation_journal_frozen_magnetic_correction_changed")
                magnetic_signature=signature
            if pending_quality is not None:
                if group!=2 or pending_quality['evaluation_us']!=evaluation:
                    raise ValueError("magnetic_quality_operation_order")
                bind_observation(pending_quality,event,args,admission,journal.bindings)
                pending_quality=None
            elif group==2 and journal.revision>=2 and (journal.bindings.get('magnetic_endpoint') or {}).get('plugin')=='silverstar.device.imu.jy901b':
                raise ValueError("magnetic_quality_evidence_required")
            if evaluation!=session.state_us:
                raise ValueError("navigation_recorded_evaluation_time_mismatch")
            if admission:
                actual=admission
            elif group==2:
                actual=session.update_magnetic(event,*args)
            else:
                actual=session.update_vector(event,('position','velocity')[group],*args)
            if actual!=expected:
                raise ValueError("navigation_recorded_observation_result_mismatch:"+str(operation))
            histories[-1]=session.state
            outcomes.append(dict(operation=operation,kind=('position','velocity','magnetic')[group],
                sample_us=event.sample_us,receive_us=event.receive_us,evaluation_us=evaluation,
                result=actual,admission=admission,recorded_nis=nis if math.isfinite(nis) else None,
                nis_equivalence='NOT_PROVEN',provenance='recorded operation journal'))
        elif kind==4:
            if journal.revision!=2 or session.current.model=='inekf15':
                raise ValueError("magnetic_quality_operation_unsupported")
            pending_quality=read_evidence(reader,values,quality_estimator)
            q=pending_quality['output'];x=pending_quality['input']
            outcomes.append(dict(operation=operation,kind='magnetic_quality',mode=pending_quality['mode'],
                native_clock_trusted=pending_quality['native_trusted'],decode_us=x['decode_us'],
                processing_us=x['now_us'],evaluation_us=pending_quality['evaluation_us'],sample_us=q['sample_us'],
                flags=q['flags'],uncertainty_bound_us=q['uncertainty_us'],sample_count=q['sample_count'],
                covariance_valid=q['covariance_valid'],time_admitted=q['time_admitted'],
                covariance_sensor_uT2=q['covariance'].tolist(),sensor_uT=x['sensor'].tolist(),
                calibration_generation=q['calibration_generation'],queue_bytes=x['queue_bytes'],decode_span_us=x['decode_span_us']))
        elif kind==3:
            final_us,reason,count=reader.get('Q'),reader.get('I'),reader.get('I');reader.finish()
            if final_us!=session.state_us or count!=operation:
                raise ValueError("navigation_journal_final_marker_mismatch")
            outcomes.append(dict(operation=operation,kind='end',reason=reason))
        else:
            raise ValueError("navigation_journal_operation_kind")
        context.Progress_Report(operation/(len(journal.operations)-1),'navigation_recorded.replay')
    return times,histories,outcomes
