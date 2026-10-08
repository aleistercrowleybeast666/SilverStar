"""Offline audit only. Never opens COM or DAP. Run from repository root."""
from pathlib import Path
import sys,json,hashlib,dataclasses,collections

sys.path.insert(0,str(Path('apps/GSHC').resolve()))
from protocol.receive_pipeline import ReceivePipeline
from protocol.gsp_min import GspParser

root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
output={}
for name in ['test5','current','current_diag']:
    folder=root/name
    log=next((folder/'userdata/logs').glob('*.jsonl'))
    rows=[json.loads(s) for s in log.read_text(encoding='utf-8').splitlines()]
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    tx=[r for r in rows if r['kind']=='CMD' and r.get('cmd_id')==1]
    first=tx[0]
    ack=[r for r in rows if r['kind']=='ACK' and r.get('ack_cmd_id')==1 and r.get('ack_seq')==first['seq']]
    resolved=[r for r in rows if r['kind']=='AIR_COMMAND_TRANSACTION_RESOLVED' and r.get('command_id')==1]
    flight=[r for r in rows if r['kind']=='FLIGHT_STATE']
    status=[r for r in rows if r['kind']=='STATUS']
    gsp_rows=[r for r in rows if r['kind']=='GSP_FRAME']
    valid_parser=GspParser()
    for row in gsp_rows:
        assert len(valid_parser.feed(bytes.fromhex(row['raw_hex'])))==1
    assert valid_parser.crc_errors==valid_parser.resyncs==valid_parser.buffer_size==0
    item={'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'log_rows':len(rows),
          'kinds':dict(collections.Counter(r['kind'] for r in rows)),
          'public_start_calls':result['start_calls'],'start_wire_attempts':len(tx),
          'start_retry_interval_ms':[(b['host_monotonic_ns']-a['host_monotonic_ns'])/1e6 for a,b in zip(tx,tx[1:])],
          'resolution':resolved,'start_ack_count':len(ack),
          'start_first_tx_to_ack_rx_ms':[(r['host_rx_monotonic_ns']-first['host_monotonic_ns'])/1e6 for r in ack],
          'ack_rx_to_protocol_ms':[r['processing_lag_ms'] for r in ack],
          'start_first_tx_to_first_flight_rx_ms':(flight[0]['host_rx_monotonic_ns']-first['host_monotonic_ns'])/1e6,
          'statuses':dict(collections.Counter(r['status_name'] for r in status)),
          'status_mcu_times_ms':{key:sorted({r['time_ms'] for r in status if r['status_name']==key}) for key in ['MISSION_START','PARACHUTE_DEPLOY','LANDING']},
          'flight_packets':len(flight),'flight_time_range_ms':[flight[0]['time_ms'],flight[-1]['time_ms']],
          'max_flight_mcu_gap_ms':max(b['time_ms']-a['time_ms'] for a,b in zip(flight,flight[1:])),
          'max_flight_host_rx_gap_ms':max((b['host_rx_monotonic_ns']-a['host_rx_monotonic_ns'])/1e6 for a,b in zip(flight,flight[1:])),
          'nonmonotonic_flight_time_count':sum(bool(r['time_non_monotonic']) for r in flight),
          'estimated_loss_last':{key:flight[-1][key] for key in ['estimated_lost_packets','expected_flight_packets','packet_loss_rate']},
          'valid_logged_gsp_frames':len(gsp_rows),'valid_logged_frame_scope':'Already accepted GSP frames only; rejected/unobserved bytes are not proven absent.',
          'serial_closed':result['serial_closed'],'protocol_closed':result['protocol_closed'],
          'logger_error':result['logger_error'],'instrumented':name=='current_diag'}
    raw=folder/'raw_rx.bin'
    if raw.exists() and raw.stat().st_size:
        data=raw.read_bytes();pipeline=ReceivePipeline();events=[]
        for offset in range(0,len(data),137):events.extend(pipeline.feed(data[offset:offset+137]))
        item['raw_capture']={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'diagnostics':dataclasses.asdict(pipeline.diagnostics()),'parsed_frames_equal_logged_frames':[e.gsp_frame.raw.hex() for e in events]==[r['raw_hex'] for r in gsp_rows],'scope':'Passive worker signal capture from recorded attachment time; offline reparse, not a live acceptance replay.'}
    else:item['raw_capture']={'scope':'NOT_RUN; original TEST5 run has accepted-frame JSONL but no complete byte-stream observer.'}
    assert result['success'] and result['start_calls']==1 and result['serial_closed'] and result['protocol_closed'] and not result['errors'] and not result['logger_error']
    assert resolved[0]['resolved_by']=='FLIGHT_STATE' and ack[0]['result']==0
    output[name]=item
(root/'session_audit.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps(output,indent=2))
