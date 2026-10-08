"""One authorized repeated static lifecycle; live diagnostic reads only."""
from pathlib import Path
import importlib.util, sys, json, time, subprocess, threading, traceback
from dataclasses import asdict
out=Path(__file__).resolve().parent
repo=out.parents[1]
spec=importlib.util.spec_from_file_location('bench_primitives',repo/'.work/FieldBenchHarness_20261003/field_bench.py')
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b)

def capture(tag):
    with (out/(tag+'_runner.log')).open('xb') as f:
        r=subprocess.run([sys.executable,str(out/'read_diagnostics.py'),tag],stdout=f,stderr=subprocess.STDOUT,timeout=25)
    if r.returncode:raise RuntimeError('Live diagnostic failed: '+tag)
    return json.loads((out/('diag_'+tag)/'result.json').read_text(encoding='utf-8'))

def ready(s):
    return (s.lifecycle_state==int(b.AirLifecycleState.READY) and s.start_block_reason==0
        and all([s.selftest_passed,s.capability_acked,s.calibration_ready,s.alignment_ready,s.system_ready,s.start_unlocked]))

class ReportingBench(b.Bench):
    def wait_for(self,label,seconds,predicate):
        print('WAIT',label,flush=True)
        x=super().wait_for(label,seconds,predicate)
        print('PASS',label,flush=True)
        return x

def main():
    import serial
    from serial.tools import list_ports
    assert json.loads((out/'reset_result.json').read_text(encoding='utf-8'))['exit_code']==0
    assert json.loads((out/'identify_result.json').read_text(encoding='utf-8'))['exact_readback_match']
    port=[p for p in list_ports.comports() if p.device=='COM3']
    assert len(port)==1 and (port[0].vid,port[0].pid,port[0].location)==(0x1a86,0x7523,'1-1')
    dest=out/'mission_repeat_01';dest.mkdir(exist_ok=False)
    bench=ReportingBench('COM3',dest)
    rec={'utc_start':b.utc_now(),'source_commit':'cac7bd29bf6f6aec5297715ea14893b4b7684953','firmware_bin_sha256':'5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3','flashes':0,'resets':1,'start_max':1,'command_retries':0,'explicit_output_commands':0,'samples':{}}
    pending=None
    sample_errors=[]
    def launch(tag):
        nonlocal pending
        assert pending is None or not pending.is_alive(), 'No parallel SWD readers'
        def worker():
            try:
                rec['samples'][tag]=capture(tag)
                print('LIVE SAMPLE',tag,'PASS',flush=True)
            except Exception as e:
                sample_errors.append({'tag':tag,'error':repr(e)})
                print('LIVE SAMPLE',tag,'FAIL',repr(e),flush=True)
        pending=threading.Thread(target=worker,daemon=False);pending.start()
    with (dest/'raw_rx.bin').open('xb') as raw,(dest/'events.jsonl').open('x',encoding='utf-8') as ev:
        bench.raw,bench.events=raw,ev
        ser=serial.Serial(port=None,baudrate=230400,timeout=.05,write_timeout=.5,rtscts=False,dsrdtr=False)
        ser.dtr=ser.rts=False;ser.port='COM3';ser.open();bench.ser=ser
        try:
            cap=bench.wait_for('CAPABILITY',45.,lambda:bench.capability)
            if not cap.profile_supported or cap.calibration_mode_mask & 0xf8 or cap.command_policy!=int(b.AirCommandPolicy.PREFLIGHT_ONLY):
                raise RuntimeError('Capability mismatch; no command')
            sent=bench.send_command(b.AirCmdId.CAPABILITY_ACK,0,cap.seq,cap.air_profile_id)
            bench.handshake_at=time.monotonic()
            status=bench.wait_for('authoritative selftest/capability',12.,lambda:bench.fresh_status(sent,lambda s:s.selftest_passed and s.capability_acked and s.lifecycle_state in (2,3)))
            if status.calibration_ready:bench.record('preserved_existing_calibration')
            else:
                if status.calibration_state!=int(b.AirCalibrationState.IDLE):raise RuntimeError('Preserve non-idle calibration; stop')
                if not cap.calibration_mode_mask & (1<<int(b.AirCalibrationMode.ONE_FACE)):raise RuntimeError('OneFace unavailable')
                sent=bench.send_command(b.AirCmdId.CAL_START,b.TOKEN_CALIBRATION,int(b.AirCalibrationMode.ONE_FACE))
                status=bench.wait_for('OneFace authoritative READY',90.,lambda:bench.fresh_status(sent,lambda s:s.calibration_mode==int(b.AirCalibrationMode.ONE_FACE) and s.calibration_state==int(b.AirCalibrationState.READY) and s.calibration_ready))
            if not status.alignment_ready:
                if status.alignment_state!=int(b.AirAlignmentState.IDLE):raise RuntimeError('Preserve non-idle alignment; stop')
                sent=bench.send_command(b.AirCmdId.ALIGN_START,b.TOKEN_ALIGNMENT)
                bench.wait_for('alignment authoritative READY',60.,lambda:bench.fresh_status(sent,lambda s:s.alignment_state==int(b.AirAlignmentState.READY) and s.alignment_ready))
            rec['samples']['pre_start']=capture('pre_start')
            d=rec['samples']['pre_start']['decoded']
            if not (d['storage']['mounted']==1 and d['storage']['healthy']==1 and d['file_open']['value']==1 and d['sink']['session_active']==1 and d['logger']['io_fault']==0 and d['logger']['snapshot_ready']==1 and d['logger_bus']['startup_state']==1 and d['assert_fault']['active']==0 and d['SCB_FAULT'][:2]==[0,0] and d['accepting']['value']==1 and d['finalization']['value']==0):
                raise RuntimeError('TF/logger/fault admission failed; no START')
            sent=bench.send_command(b.AirCmdId.UNLOCK,b.TOKEN_UNLOCK)
            bench.wait_for('fresh authoritative READY after live admission',12.,lambda:bench.fresh_status(sent,ready))
            sent=bench.send_command(b.AirCmdId.START_MISSION,b.TOKEN_START_MISSION,timeout_s=15.)
            bench.wait_for('actual flight transition',12.,lambda:bench.last_flight_at if bench.last_flight_at>sent else None)
            launch('active')
            sampled=set()
            end=time.monotonic()+45.
            while time.monotonic()<end:
                bench.receive()
                if bench.session_invalid:raise RuntimeError('Unexpected BOOT/FAULT; stop without retry')
                if sample_errors:raise RuntimeError('Diagnostic failed; stop commands')
                if bench.landing_at:
                    elapsed=time.monotonic()-bench.landing_at
                    for tag,delay in [('landing_receive',0.),('landing_plus_1_4s',1.4),('landing_plus_4s',4.)]:
                        if tag not in sampled and elapsed>=delay and (pending is None or not pending.is_alive()):
                            launch(tag);sampled.add(tag);break
                    if all(x in rec['samples'] for x in ['landing_receive','landing_plus_1_4s','landing_plus_4s']):
                        d=rec['samples']['landing_plus_4s']['decoded']
                        if d['file_open']['value']==0 and d['logger_runtime']['session_finalized']==1:
                            break
            if pending:pending.join(timeout=26.)
            if sample_errors:raise RuntimeError('Diagnostic sample failure')
            if not all(bench.mission_events[int(x)] for x in (b.AirStatusId.MISSION_START,b.AirStatusId.PARACHUTE_DEPLOY,b.AirStatusId.LANDING)):
                raise RuntimeError('Expected finite lifecycle not observed')
            if 'landing_plus_4s' not in rec['samples']:raise RuntimeError('Finalized sample not obtained')
            d=rec['samples']['landing_plus_4s']['decoded']
            rec['functional_checks']={'landed':d['lifecycle']['value']==6,'no_fault':d['assert_fault']['active']==0 and d['SCB_FAULT'][:2]==[0,0],'closed_finalized':d['file_open']['value']==0 and d['sink']['session_active']==0 and d['logger_runtime']['session_active']==0 and d['logger_runtime']['session_finalized']==1 and d['logger_runtime']['aggregate_length']==0,'start_snapshot_ack':d['logger_request']['is_start']==1 and d['logger_request']['generation']>0 and d['logger_request']['generation']==d['logger_request']['acknowledged_generation'] and d['logger_request']['io_fault']==0,'queues_empty':all(d[k]['head']==d[k]['tail'] for k in ['normal_queue','estimator_queue']),'no_capacity_loss':d['logger_bus']['capacity_reject_count']==0 and d['logger_bus']['overflow_count']==0 and all(d[k]['overflow_count']==0 for k in ['normal_queue','estimator_queue']),'no_io_fault':d['logger']['io_fault']==0 and all(d['logger'][k]==0 for k in ['append_failure_count','flush_failure_count','serialize_failure_count','discarded_bytes','close_failure_count','final_status_write_failed']) and d['storage']['error_count']==0 and d['sink']['error_count']==0,'max_flight_gap_within_2s':bench.max_flight_gap_s<=2.}
            if not all(rec['functional_checks'].values()):raise RuntimeError('Functional check failure')
            rec['mission_result']='COMPLETED_OBSERVED_SEQUENCE'
        except Exception as e:
            rec.update(mission_result='STOPPED',error=repr(e),traceback=traceback.format_exc())
            print('STOP WITHOUT RETRY/RESET',repr(e),flush=True)
        finally:
            ser.close();bench.record('serial_closed')
            if pending:pending.join(timeout=26.)
            rec.update(utc_end=b.utc_now(),air_events=bench.mission_events,air_event_rx_counts=bench.mission_event_rx_count,flight_frames=bench.flight_count,max_flight_gap_s=bench.max_flight_gap_s,gsp_diagnostics=asdict(bench.parser.diagnostics()),sample_errors=sample_errors,actual_TF_contents='NOT_PROVEN; full original mission directory required')
            (dest/'result.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
    print(json.dumps({k:rec.get(k) for k in ['mission_result','error','air_events','flight_frames','max_flight_gap_s','functional_checks']},indent=2),flush=True)
    return 0 if rec['mission_result']=='COMPLETED_OBSERVED_SEQUENCE' else 1

if __name__=='__main__':raise SystemExit(main())
