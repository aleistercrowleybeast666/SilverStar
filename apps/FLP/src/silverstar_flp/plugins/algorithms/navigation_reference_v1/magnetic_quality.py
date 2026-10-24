"""Recorded JY quality evidence, not a claim of a hardware sample clock.

The host keeps bounded raw stationary samples and computes two-pass covariance.
Firmware uses online scatter. Independent NumPy/analytic tests are separate from
the consistency replay; neither validates physical timing or white-noise truth.
"""
import math
import numpy as np

CONFIG,PROXY,COMPENSATED,TIME,TRANSPORT,DUPLICATE,SEQUENCE,MOTION,FIELD,WARMUP,COVARIANCE,NUMERIC,CALIBRATION,INPUT,UNVERIFIED,SKIPPED=(1<<i for i in range(16))
UINT32_MAX=2**32-1
CONFIG_INTS=('minimum_samples','minimum_duration_us','maximum_gap_us','maximum_sequence_step')
CONFIG_FLOATS=('variance_floor_uT2','maximum_std_uT','maximum_span_uT','gyro_max_radps',
    'accel_tolerance_mps2','accel_span_mps2','gravity_mps2','field_reference_uT','field_min_ratio','field_max_ratio')
CONFIG_TIMING=('delay_us','uncertainty_us','maximum_time_uncertainty_us','maximum_queue_bytes','delay_bound_verified')
PARAMETERS=(
    'magnetic_noise_min_samples','magnetic_noise_duration_us','magnetic_noise_maximum_gap_us','magnetic_noise_maximum_sequence_step',
    'magnetic_noise_variance_floor_ut2','magnetic_noise_maximum_std_ut','magnetic_noise_maximum_span_ut',
    'magnetic_stationary_gyro_max_radps','magnetic_stationary_accel_tolerance_mps2','magnetic_stationary_accel_span_mps2',
    'gravity_mps2','magnetic_reference_ut','magnetic_min_norm_ratio','magnetic_max_norm_ratio',
    'magnetic_time_delay_us','magnetic_time_uncertainty_us','magnetic_time_maximum_uncertainty_us',
    'magnetic_time_maximum_queue_bytes','magnetic_time_bound_verified')

def configuration_from_values(values):
    try:return dict(zip(CONFIG_INTS+CONFIG_FLOATS+CONFIG_TIMING,(values[name] for name in PARAMETERS)))
    except KeyError as exc:raise ValueError('magnetic_quality_policy_manifest_unsupported') from exc

def config_valid(c):
    return (all(math.isfinite(c[k]) and c[k]>0 for k in CONFIG_FLOATS)
        and 16<=c['minimum_samples']<=256 and 1000<=c['minimum_duration_us']<=5000000
        and 0<c['maximum_gap_us']<=1000000 and 0<c['maximum_sequence_step']<=256
        and c['field_max_ratio']>c['field_min_ratio'] and 0<=c['delay_us']<=1000000
        and 0<=c['uncertainty_us']<=1000000 and 0<=c['maximum_time_uncertainty_us']<=1000000
        and 0<=c['maximum_queue_bytes']<=4096 and c['delay_bound_verified'] in (0,1))

def _norm(vector):
    return math.sqrt(sum(float(v)*float(v) for v in vector))

def _covariance_positive(covariance):
    try:
        matrix=np.asarray(covariance,dtype=float)
        if matrix.shape!=(3,3) or not np.isfinite(matrix).all() or not np.array_equal(matrix,matrix.T):return False
        np.linalg.cholesky(matrix)
        return True
    except (TypeError,ValueError,np.linalg.LinAlgError):return False


class MagneticQuality:
    def __init__(self):
        self.previous=None
        self.window_reset()

    def window_reset(self):
        self.rows=[];self.start=0;self.anchor=None;self.covariance=None

    def reset(self):
        self.previous=None;self.window_reset()

    def process(self,c,x):
        y=dict(sample_us=0,flags=0,uncertainty_us=UINT32_MAX,sample_count=0,
            calibration_generation=x['calibration_generation'],covariance_valid=0,time_admitted=0,covariance=np.zeros((3,3)))
        if not config_valid(c):
            self.window_reset();y['flags']=CONFIG;return 2,y
        if self.covariance is not None and (len(self.rows)<c['minimum_samples'] or not _covariance_positive(self.covariance)):
            self.reset();y['flags']=NUMERIC;return 4,y
        if (not all(np.isfinite(x[k]).all() for k in ('sensor','corrected','accel','gyro'))
                or x['transport_valid'] not in (0,1) or x['imu_valid'] not in (0,1)):
            self.reset();y['flags']=INPUT;return 3,y
        y['flags']=PROXY;y['sample_us']=x['decode_us']
        if (x['decode_us']<c['delay_us'] or x['decode_us']==0 or x['now_us']<x['decode_us']
                or x['now_us']-x['decode_us']>c['maximum_gap_us'] or x['transport_valid']!=1
                or x['queue_bytes']>c['maximum_queue_bytes']):
            y['flags']|=TIME
        else:
            y['sample_us']=x['decode_us']-c['delay_us'];y['flags']|=COMPENSATED
            if c['delay_bound_verified']!=1 or not c['uncertainty_us'] or not c['maximum_time_uncertainty_us']:
                y['flags']|=UNVERIFIED
            else:
                y['uncertainty_us']=min(UINT32_MAX,c['uncertainty_us']+x['decode_span_us'])
                if c['uncertainty_us']+x['decode_span_us']>c['maximum_time_uncertainty_us']:y['flags']|=TIME
                else:y['time_admitted']=1
        if self.previous is not None:
            old=self.previous
            if (old['calibration_generation'],old['transport_epoch'])!=(x['calibration_generation'],x['transport_epoch']):
                y['flags']|=CALIBRATION if old['calibration_generation']!=x['calibration_generation'] else TRANSPORT
                self.window_reset();self.previous=None
        if self.previous is not None:
            if (x['sequence'],x['decode_us'])==(self.previous['sequence'],self.previous['decode_us']):
                y['flags']|=DUPLICATE;y['sample_count']=len(self.rows);return 1,y
            step=(x['sequence']-self.previous['sequence'])%2**32
            if (step==0 or step>c['maximum_sequence_step'] or x['decode_us']<=self.previous['decode_us']
                    or x['decode_us']-self.previous['decode_us']>c['maximum_gap_us']):
                self.window_reset();y['flags']|=SEQUENCE|TIME;y['time_admitted']=0
            elif step>1:y['flags']|=SKIPPED
        self.previous={k:x[k] for k in ('sequence','decode_us','calibration_generation','transport_epoch')}
        norm=_norm(x['corrected'])
        if (x['transport_valid']!=1 or x['queue_bytes']>c['maximum_queue_bytes'] or x['decode_span_us']>c['maximum_gap_us'] or not x['decode_us']
                or x['now_us']<x['decode_us'] or x['now_us']-x['decode_us']>c['maximum_gap_us']
                or norm<c['field_reference_uT']*c['field_min_ratio'] or norm>c['field_reference_uT']*c['field_max_ratio']):
            self.window_reset();y['flags']|=TRANSPORT|FIELD;y['time_admitted']=0;return 0,y
        if y['flags']&SEQUENCE:return 0,y
        stationary=(x['imu_valid']==1 and x['accel_decode_us']>0 and x['gyro_decode_us']>0
            and x['accel_decode_us']<=x['decode_us'] and x['gyro_decode_us']<=x['decode_us']
            and x['decode_us']-x['accel_decode_us']<=c['maximum_gap_us']
            and x['decode_us']-x['gyro_decode_us']<=c['maximum_gap_us']
            and sum(float(v)*float(v) for v in x['gyro'])<=c['gyro_max_radps']**2
            and abs(_norm(x['accel'])-c['gravity_mps2'])<=c['accel_tolerance_mps2']
            and (not self.rows or np.max(abs(x['accel']-self.anchor))<=c['accel_span_mps2']))
        if not stationary:
            y['flags']|=MOTION
            if self.covariance is None:self.window_reset()
        elif self.covariance is None:
            if not self.rows:self.start=x['decode_us'];self.anchor=x['accel'].copy()
            failed=len(self.rows)>=256
            if not failed:
                self.rows.append(x['sensor'].copy());data=np.asarray(self.rows)
                failed=bool(np.any(data.max(axis=0)-data.min(axis=0)>c['maximum_span_uT']))
            if not failed and len(self.rows)>=c['minimum_samples'] and x['decode_us']-self.start>=c['minimum_duration_us']:
                covariance=np.cov(data,rowvar=False,ddof=1)
                failed=bool(np.any(np.diag(covariance)<0) or np.any(np.diag(covariance)>c['maximum_std_uT']**2))
                if not failed:
                    self.covariance=(covariance+c['variance_floor_uT2']*np.eye(3)).astype(np.float32).astype(float)
                    try:np.linalg.cholesky(self.covariance)
                    except np.linalg.LinAlgError:failed=True
                    if not np.isfinite(self.covariance).all():failed=True
            if failed:
                self.window_reset();y['flags']|=FIELD|NUMERIC
        y['sample_count']=len(self.rows)
        if self.covariance is not None:
            y['flags']|=COVARIANCE;y['covariance_valid']=1;y['covariance']=self.covariance.copy()
        else:y['flags']|=WARMUP
        return 0,y

def read_evidence(reader,values,estimator):
    revision,mode=reader.get('I'),reader.get('I');evaluation_us=reader.get('Q');identity=reader.identity();native_trusted=reader.get('I')
    if revision!=1 or mode not in (1,2) or native_trusted>1:raise ValueError('magnetic_quality_revision_or_mode')
    names=('imu_valid','transport_valid','queue_bytes','transport_epoch','calibration_generation','sequence','decode_span_us')
    x={name:reader.get('I') for name in names}
    x.update({name:reader.get('Q') for name in ('decode_us','now_us','accel_decode_us','gyro_decode_us')})
    x.update({name:reader.array(3,'f') for name in ('sensor','corrected','accel','gyro')})
    c={name:reader.get('I') for name in CONFIG_INTS}
    c.update({name:reader.get('f') for name in CONFIG_FLOATS});c.update({name:reader.get('I') for name in CONFIG_TIMING})
    y=dict(sample_us=reader.get('Q'))
    y.update({name:reader.get('I') for name in ('flags','uncertainty_us','sample_count','calibration_generation','covariance_valid','time_admitted')})
    y['covariance']=reader.array(9,'f').reshape(3,3);expected=reader.get('I');reader.finish()
    if c!=configuration_from_values(values):raise ValueError('magnetic_quality_actual_policy_mismatch')
    if mode==1:
        if native_trusted!=0:raise ValueError('jy_native_clock_claim_forbidden')
        result,actual=estimator.process(c,x)
    else:
        estimator.reset();result=0
        if y['flags'] not in (CALIBRATION,INPUT):raise ValueError('magnetic_quality_reset_reason')
        actual=dict(sample_us=x['decode_us'],flags=y['flags'],uncertainty_us=UINT32_MAX,sample_count=0,
            calibration_generation=x['calibration_generation'],covariance_valid=0,time_admitted=0,covariance=np.zeros((3,3)))
    if result!=expected or any(y[name]!=actual[name] for name in y if name!='covariance'):
        raise ValueError('magnetic_quality_result_mismatch')
    if not np.allclose(y['covariance'],actual['covariance'],rtol=2e-6,atol=2e-9,equal_nan=False):
        raise ValueError('magnetic_quality_covariance_mismatch')
    return dict(identity=identity,mode=mode,input=x,output=y,native_trusted=native_trusted,evaluation_us=evaluation_us)

def bind_observation(evidence,event,args,admission,bindings):
    x,y=evidence['input'],evidence['output'];endpoint=bindings.get('magnetic_endpoint')
    if (endpoint is None or endpoint['plugin']!='silverstar.device.imu.jy901b'
            or event.identity!=evidence['identity'] or event.sequence!=x['sequence']
            or event.identity.source!=(endpoint['physical_device_id']<<8)|endpoint['instance_id']
            or event.sample_us!=y['sample_us'] or event.receive_us!=x['decode_us']
            or event.trusted!=y['time_admitted'] or not np.array_equal(args[0],x['sensor'])
            or not np.array_equal(args[1],y['covariance'])):
        raise ValueError('magnetic_quality_observation_binding')
    if evidence['mode']==1:
        corrected=np.asarray(args[4],dtype=np.float32)@(np.asarray(args[0],dtype=np.float32)-np.asarray(args[3],dtype=np.float32))
        expected_admission=1 if y['time_admitted'] and not y['covariance_valid'] else 0
        if (admission!=expected_admission or not bindings['magnetic_bound'] or x['calibration_generation']!=event.identity.calibration
                or not np.allclose(corrected,x['corrected'],rtol=2e-6,atol=1e-5)):
            raise ValueError('magnetic_quality_calibration_binding')
