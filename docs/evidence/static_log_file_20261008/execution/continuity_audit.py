from pathlib import Path
import os, sys, json, hashlib, datetime
os.environ['OPENBLAS_NUM_THREADS']='1'
root=Path(__file__).resolve().parent; repo=root.parents[1]
sys.path.insert(0,str(repo/'apps/FLP/src'))
import numpy as np
from silverstar_flp.log_open import LogOpenCoordinator,LogOpenRequest
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.plugins.registry import builtin_registry
decoder=repo/'.work/bench08c_f407/KF6_Static_20261008_f045d8c.ssdecoder'

def stats(values):
    a=np.asarray(values,dtype=np.int64)
    return {'count':len(a),'min':int(a.min()) if len(a) else None,
            'max':int(a.max()) if len(a) else None,
            'nonpositive':int(np.sum(a<=0)),
            'distinct':np.unique(a).tolist()[:32]}

for mission in (44,45):
    folder=root/f'm{mission}'
    ds=LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(folder/'continuity_cache')).Open(
        LogOpenRequest(root/'input'/f'missions/{mission:06}/flight.sslog',decoder)).dataset
    streams={}
    for name,field in [('IMU_CORRECTED','sequence'),('INERTIAL_INCREMENT','sequence'),
                       ('ESTIMATOR_STEP','source_sequence')]:
        rows=ds.records[name]
        sequence=[r.payload[field] for r in rows]
        delta=np.diff(sequence)
        timestamps=[r.timestamp_us for r in rows]
        streams[name]={'count':len(rows),'first_sequence':sequence[0],
            'last_sequence':sequence[-1], 'sequence_delta':stats(delta),
            'first_timestamp_us':timestamps[0], 'last_timestamp_us':timestamps[-1],
            'timestamp_delta_us':stats(np.diff(timestamps))}
        assert np.all(delta==1), (name,'Source sample/step sequence gap')
        assert np.all(np.diff(timestamps)>0), (name,'Nonpositive timestamp step')
    increments=ds.records['INERTIAL_INCREMENT'];steps=ds.records['ESTIMATOR_STEP']
    increment_pairs=[(r.payload['sequence'],r.payload['interval_end_timestamp_us']) for r in increments]
    step_pairs=[(r.payload['source_sequence'],r.payload['interval_end_timestamp_us']) for r in steps]
    assert increment_pairs==step_pairs
    continuity=[b.payload['interval_start_timestamp_us']-a.payload['interval_end_timestamp_us']
                for a,b in zip(increments,increments[1:])]
    operation=[r.payload['operation_sequence'] for r in steps]
    assert np.all(np.diff(operation)>0)
    telemetry=[{'timestamp_us':r.timestamp_us,**dict(r.payload)} for r in ds.records['TELEMETRY_DIAG']]
    nav=ds.records['ESTIMATOR']
    report={'mission':mission,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'streams':streams,'increment_step_one_to_one':True,
        'increment_boundary_delta_us':stats(continuity),
        'operation_sequence_delta':stats(np.diff(operation)),
        'replay_epochs':sorted({r.payload['replay_epoch'] for r in steps}),
        'navigation_gnss_position_result_flags':sorted({r.payload['measurement_result_flags'] for r in nav}),
        'gnss_origin_valid_values':sorted({r.payload['gnss_origin_valid'] for r in nav}),
        'gnss_sequence_values':sorted({r.payload['gnss_sequence'] for r in nav}),
        'estimator_prediction_overflow_values':sorted({r.payload['prediction_queue_overflow_count'] for r in nav}),
        'telemetry_records':telemetry,
        'limitations':['Accepted-record continuity does not identify calls rejected before admission.',
            'TELEMETRY_DIAG receive_error includes rx_timeout/rx_error/rx_dropped; not the raw radio rx_error field.',
            'Source timing during recorded mission does not attribute boot-wide historical maximum or establish WCET.',
            'No external navigation truth or end-to-end radio delivery proof.']}
    (folder/'continuity_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('telemetry_records','limitations')},indent=2),flush=True)
