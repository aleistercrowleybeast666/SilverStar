from pathlib import Path
import json, math
root=Path(__file__).resolve().parent
for mission in (44,45):
    folder=root/f'm{mission}'
    c=json.loads((folder/'critical_records.json').read_text())
    s=json.loads((folder/'parse_summary.json').read_text())
    samples=json.loads((folder/'record_samples.json').read_text())
    initial=c['INITIAL_STATE'][0]
    alignment=c['ALIGNMENT_RESULT'][0]['payload']
    state=initial['payload']
    first=samples['ESTIMATOR']['first']['payload']
    assert len(c['INITIAL_STATE'])==1
    assert initial['timestamp_us']==s['overview']['mission_start_timestamp_us']
    assert alignment['ready']==1 and alignment['config_result']==0
    assert state['q_nb']==alignment['q_nb']==first['q_nb']
    assert state['alignment_algorithm']==alignment['attitude_source']
    assert state['p0_diagonal']==first['covariance_diagonal']
    assert all(math.isfinite(x) and x>0 for x in state['p0_diagonal'])
    assert state['origin_valid_flags']==2 and state['gnss_sample_count']==0
    report={'mission':mission,'initial_state_at_recorded_START':True,
        'alignment_ready_and_success':True,'initial_quaternion_matches_alignment_and_first_estimator':True,
        'initial_covariance_matches_first_estimator':True,
        'q_nb_norm':math.sqrt(sum(x*x for x in state['q_nb'])),
        'initial_state':state,'alignment_result':alignment,
        'barometer_origin_source':'INITIAL_STATE at START; earlier ALIGNMENT_RESULT origin may be unpopulated',
        'limitations':['OneFace readiness is not full six-face calibration or absolute heading proof.',
                       'Snapshot integrity does not verify physical mount or sensor accuracy.']}
    (folder/'initial_state_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('initial_state','alignment_result','limitations')}))
