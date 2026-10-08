"""One finite authorized static mission; no command retries or actuator commands."""
from pathlib import Path
import importlib.util, sys, json, time, subprocess, threading, traceback
from dataclasses import asdict
from datetime import datetime, timezone
out = Path(__file__).resolve().parent
repo = out.parents[1]
spec = importlib.util.spec_from_file_location('bench_primitives', repo/'.work/FieldBenchHarness_20261003/field_bench.py')
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)

def snapshot(tag, freeze=False):
    args = [sys.executable, str(out/'read_diagnostics.py'), tag]
    if freeze:
        args += ['--stacks', '--freeze']
    with (out/(tag+'_runner.log')).open('xb') as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
    if result.returncode:
        raise RuntimeError('Diagnostic read failed: '+tag)
    return json.loads((out/('diag_'+tag)/'result.json').read_text(encoding='utf-8'))

def ready(s):
    return (s.lifecycle_state == int(b.AirLifecycleState.READY)
            and all((s.selftest_passed, s.capability_acked, s.calibration_ready,
                     s.alignment_ready, s.system_ready, s.start_unlocked))
            and s.start_block_reason == 0)

class ReportingBench(b.Bench):
    def wait_for(self,label,seconds,predicate):
        print('WAIT',label,flush=True)
        result=super().wait_for(label,seconds,predicate)
        print('PASS',label,flush=True)
        return result

def main():
    import serial
    from serial.tools import list_ports
    flash = json.loads((out/'flash_result.json').read_text())
    assert flash['exit_code'] == 0 and flash['exact_readback_match']
    ports = [p for p in list_ports.comports() if p.device == 'COM3']
    assert len(ports) == 1 and (ports[0].vid, ports[0].pid, ports[0].location) == (0x1a86,0x7523,'1-1')
    dest = out/'mission_static_01'
    dest.mkdir(exist_ok=False)
    bench = ReportingBench('COM3', dest)
    rec = {'utc_start':b.utc_now(), 'firmware':flash['artifacts'], 'retries':0,
           'start_count_max':1, 'conditions':'User reports TF inserted, stationary +Y placement, all actuators disconnected.',
           'explicit_output_commands':0, 'cal_reset_save_or_multi_pose':False}
    thread = None
    running_results = []
    with (dest/'raw_rx.bin').open('xb') as raw, (dest/'events.jsonl').open('x',encoding='utf-8') as events:
        bench.raw, bench.events = raw, events
        ser = serial.Serial(port=None,baudrate=230400,timeout=.05,write_timeout=.5,rtscts=False,dsrdtr=False)
        ser.dtr = ser.rts = False
        ser.port = 'COM3'
        ser.open()
        bench.ser = ser
        try:
            cap = bench.wait_for('CAPABILITY',45.,lambda:bench.capability)
            if not cap.profile_supported or cap.calibration_mode_mask & 0xf8 or cap.command_policy != int(b.AirCommandPolicy.PREFLIGHT_ONLY):
                raise RuntimeError('Unexpected capability/configuration; stop')
            sent = bench.send_command(b.AirCmdId.CAPABILITY_ACK,0,cap.seq,cap.air_profile_id)
            bench.handshake_at = time.monotonic()
            status = bench.wait_for('selftest and capability',12.,lambda:bench.fresh_status(sent,lambda s:s.selftest_passed and s.capability_acked and s.lifecycle_state in (2,3)))
            if status.calibration_ready:
                bench.record('preserved_existing_calibration',status=asdict(status))
            else:
                if status.calibration_state != int(b.AirCalibrationState.IDLE):
                    raise RuntimeError('Existing non-idle calibration is preserved; user review needed')
                if not cap.calibration_mode_mask & (1 << int(b.AirCalibrationMode.ONE_FACE)):
                    raise RuntimeError('Static OneFace unavailable; user interaction needed')
                sent = bench.send_command(b.AirCmdId.CAL_START,b.TOKEN_CALIBRATION,int(b.AirCalibrationMode.ONE_FACE))
                status = bench.wait_for('OneFace authoritative READY',90.,lambda:bench.fresh_status(sent,lambda s:s.calibration_mode == int(b.AirCalibrationMode.ONE_FACE) and s.calibration_state == int(b.AirCalibrationState.READY) and s.calibration_ready))
            if not status.alignment_ready:
                if status.alignment_state != int(b.AirAlignmentState.IDLE):
                    raise RuntimeError('Existing non-idle alignment is preserved; user review needed')
                sent = bench.send_command(b.AirCmdId.ALIGN_START,b.TOKEN_ALIGNMENT)
                bench.wait_for('alignment authoritative READY',60.,lambda:bench.fresh_status(sent,lambda s:s.alignment_state == int(b.AirAlignmentState.READY) and s.alignment_ready))
            admission = snapshot('before_unlock')['decoded']
            rec['preparation_observation'] = admission
            if not (admission['storage']['mounted'] == 1 and admission['storage']['healthy'] == 1
                    and admission['file_open']['value'] == 1 and admission['sink']['session_active'] == 1
                    and admission['logger']['io_fault'] == 0 and admission['logger']['snapshot_ready'] == 1
                    and admission['logger_bus']['startup_state'] == 1 and admission['assert_fault']['active'] == 0
                    and admission['SCB_FAULT'][:2] == [0,0]):
                raise RuntimeError('TF/logger/fault admission failed; START blocked')
            sent = bench.send_command(b.AirCmdId.UNLOCK,b.TOKEN_UNLOCK)
            bench.wait_for('fresh authoritative READY after diagnostics',12.,lambda:bench.fresh_status(sent,ready))
            sent = bench.send_command(b.AirCmdId.START_MISSION,b.TOKEN_START_MISSION,timeout_s=15.)
            bench.wait_for('actual mission transition',12.,lambda:bench.last_flight_at if bench.last_flight_at > sent else None)
            def capture():
                try:
                    running_results.append(snapshot('after_start_live'))
                except Exception as error:
                    running_results.append({'error':repr(error)})
            thread = threading.Thread(target=capture,daemon=False)
            thread.start()
            end = time.monotonic()+45.
            while time.monotonic() < end:
                bench.receive()
                if bench.session_invalid:
                    raise RuntimeError('Unexpected BOOT/FAULT; stop without retry/reset')
            if not all(bench.mission_events[int(k)] for k in (b.AirStatusId.MISSION_START,b.AirStatusId.PARACHUTE_DEPLOY,b.AirStatusId.LANDING)):
                raise RuntimeError('Finite mission transition sequence not observed')
            if bench.max_flight_gap_s > 2.:
                raise RuntimeError('In-mission telemetry gap exceeded 2 seconds')
            rec['mission_result'] = 'COMPLETED_OBSERVED_SEQUENCE'
        except Exception as error:
            rec.update(mission_result='STOPPED',error=repr(error),traceback=traceback.format_exc())
            print('STOP WITHOUT RETRY/RESET',repr(error),flush=True)
        finally:
            ser.close()
            bench.record('serial_closed')
            if thread:
                thread.join(timeout=35.)
            rec.update(air_events=bench.mission_events,flight_frames=bench.flight_count,
                       max_flight_gap_s=bench.max_flight_gap_s,gsp_diagnostics=asdict(bench.parser.diagnostics()),
                       live_diagnostic_results=running_results,utc_end=b.utc_now())
            (dest/'result.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
    # Halt/resume only after a confirmed completed mission; failures remain live.
    final = snapshot('postmission' if rec['mission_result'].startswith('COMPLETED') else 'stopped_live',rec['mission_result'].startswith('COMPLETED'))
    rec['final_diagnostics'] = final
    d=final['decoded']
    rec['functional_checks']={
        'landed': d['lifecycle']['value']==6,
        'no_fault': d['assert_fault']['active']==0 and d['SCB_FAULT'][:2]==[0,0],
        'closed_finalized': d['file_open']['value']==0 and d['sink']['session_active']==0 and d['logger_runtime']['session_active']==0 and d['logger_runtime']['session_finalized']==1 and d['logger_runtime']['aggregate_length']==0,
        'start_snapshot_ack': d['logger_request']['is_start']==1 and d['logger_request']['generation']>0 and d['logger_request']['acknowledged_generation']==d['logger_request']['generation'] and d['logger_request']['phase']==0 and d['logger_request']['io_fault']==0,
        'queues_empty': all(d[k]['head']==d[k]['tail'] for k in ['normal_queue','estimator_queue']),
        'no_capacity_loss': d['logger_bus']['overflow_count']==0 and d['logger_bus']['capacity_reject_count']==0 and all(d[k]['overflow_count']==0 for k in ['normal_queue','estimator_queue']),
        'no_io_fault': d['logger']['io_fault']==0 and all(d['logger'][k]==0 for k in ['append_failure_count','flush_failure_count','serialize_failure_count','discarded_bytes','close_failure_count','final_status_write_failed']) and d['storage']['error_count']==0 and d['sink']['error_count']==0,
    }
    rec['persistent_TF_contents']='NOT_PROVEN; actual card files are required'
    rec['state_reject_review']='NOT_PROVEN' if d['logger_bus']['state_reject_count'] else 'NO_OBSERVED_REJECTION'
    (dest/'result.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
    print(json.dumps({k:rec[k] for k in ('mission_result','air_events','flight_frames','max_flight_gap_s','gsp_diagnostics')},indent=2),flush=True)
    if rec['mission_result']=='STOPPED' or any('error' in x for x in running_results) or not all(rec['functional_checks'].values()):
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
