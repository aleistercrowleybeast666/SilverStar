"""Offline audit of captured production radio traffic and ELF-bound RAM."""
from pathlib import Path
import collections
import dataclasses
import hashlib
import json
import re
import sys

out = Path(__file__).resolve().parent
repo = out.parents[1]
sys.path.insert(0, str(repo / 'apps/GSHC'))
from protocol.receive_pipeline import ReceivePipeline

before = json.loads((out / 'hardware_startup/result.json').read_text())
after = json.loads((out / 'hardware_post/result.json').read_text())
gshc = json.loads((out / 'health_fixed/result.json').read_text(encoding='utf-8'))
ptypes = re.split(r'type = (?:volatile )?struct \{', (out / 'offline_layout.log').read_text())[1:]
decoded = {}
for phase, capture in [('startup', before), ('post', after)]:
    result = dict(fields={key:value['value'] for key,value in capture['fields'].items()
                          if value['value'].bit_length() <= 64},
                  path=capture['fields']['path']['text'])
    for name, block in zip(['bus', 'task', 'sink_health', 'assert_fault'], ptypes):
        data = bytes.fromhex(capture['fields'][name]['hex'])
        result[name] = {}
        for offset, size, field in re.findall(r'/\*\s*(\d+)\s*\|\s*(\d+)\s*\*/\s*[^;\n]*?\b(\w+)(?:\[\d+\])?;', block):
            offset, size = int(offset), int(size)
            assert offset + size <= len(data), field
            result[name][field] = int.from_bytes(data[offset:offset+size], 'little')
    decoded[phase] = result
log = next((out / 'health_fixed/userdata/logs').glob('*.jsonl'))
rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
tx = [row for row in rows if row['kind'] == 'CMD' and row.get('cmd_id') == 1]
acks = [row for row in rows if row['kind'] == 'ACK' and row.get('ack_cmd_id') == 1 and row.get('ack_seq') == tx[0]['seq']]
flight = [row for row in rows if row['kind'] == 'FLIGHT_STATE']
resolution = [row for row in rows if row['kind'] == 'AIR_COMMAND_TRANSACTION_RESOLVED' and row.get('command_id') == 1]
raw = (out / 'health_fixed/raw_rx.bin').read_bytes()
pipeline = ReceivePipeline()
events = []
for offset in range(0, len(raw), 137): events.extend(pipeline.feed(raw[offset:offset+137]))
record = dict(scope='One no-halt production GSHC static run; post-finalization live RAM read, not physical TF extraction',
              captures=decoded, public_start_calls=gshc['start_calls'], wire_attempts=len(tx),
              start_retry_interval_ms=[(b['host_monotonic_ns']-a['host_monotonic_ns'])/1e6 for a,b in zip(tx,tx[1:])],
              first_tx_to_ack_rx_ms=[(row['host_rx_monotonic_ns']-tx[0]['host_monotonic_ns'])/1e6 for row in acks],
              ack_processing_lag_ms=[row['processing_lag_ms'] for row in acks], transaction_resolution=resolution,
              lifecycle_statuses={key:sorted({row['time_ms'] for row in rows if row['kind']=='STATUS' and row['status_name']==key})
                                  for key in ['MISSION_START','PARACHUTE_DEPLOY','LANDING']},
              flight_packets=len(flight), flight_time_range_ms=[flight[0]['time_ms'],flight[-1]['time_ms']],
              nonmonotonic_times=sum(bool(row['time_non_monotonic']) for row in flight),
              last_loss_estimate={key:flight[-1][key] for key in ['estimated_lost_packets','expected_flight_packets','packet_loss_rate']},
              raw_capture_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest(),
              raw_diagnostics=dataclasses.asdict(pipeline.diagnostics()),
              raw_frames_equal_logged=[event.gsp_frame.raw.hex() for event in events]==[row['raw_hex'] for row in rows if row['kind']=='GSP_FRAME'],
              serial_closed=gshc['serial_closed'], protocol_closed=gshc['protocol_closed'],
              no_calibration_commands=not any('CAL_START' in name for name in gshc['operations']),
              ram_calibration_commands=[name for name in gshc['operations'] if 'CAL_START_ONE_FACE_RAM' == name],
              calibration_identity_interpretation='Initial snapshot_ready=0: its zero generation/hash are not a committed TF calibration identity. OneFace operates in RAM; final mission snapshot records generation 1 and the loaded magnetometer hash. Do not infer a TF calibration-object mutation from this before/after comparison.',
              tf_calibration_object_byte_equivalence='NOT_PROVEN; no calibration-object write command or code path was used, but media was not extracted',
              health_scope='Stored accepted fusion timestamps in the completed run plus unchanged timeout logic. AIR M0 does not expose fusion group health; no active-run halt/read was added.',
              event47_scope='Matched source guard + unchanged Host error contracts + finalized/counter/RAM observations. Full TF event inventory and other possible producers remain unproven until exact file extraction.',
              tf_file_acceptance='NOT_RUN')
pre, post = decoded['startup'], decoded['post']
record.update(mission_id=post['fields']['mission_id'], tf_path=post['path'],
              mission_identity_stable=pre['fields']['mission_id']==post['fields']['mission_id'] and pre['path']==post['path'],
              calibration_identity_stable=all(pre['fields'][key]==post['fields'][key] for key in ('calibration_generation','mag_hash')),
              post_health_ages_us={str(group):post['fields']['monotonic_end_us']-post['fields'][f'group{group}_last_successful_fusion_us']
                                  for group in range(5) if post['fields'][f'group{group}_has_success']})
record['post_health_age_interpretation'] = 'Only barometer group 4 has accepted fusion in this stationary no-GNSS run. Stored source state remains ACCEPTED; elapsed ages are derived offline from captured monotonic task time, not a target getter call. Existing GroupGet would age it according to unchanged 2 s/10 s rules. No blanket healthy claim.'
(out / 'hardware_audit.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({key:record[key] for key in ('mission_id','tf_path','mission_identity_stable','calibration_identity_stable',
                                           'public_start_calls','wire_attempts','first_tx_to_ack_rx_ms','lifecycle_statuses','raw_diagnostics')}, indent=2))
