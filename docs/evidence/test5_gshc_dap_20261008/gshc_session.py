from pathlib import Path
import sys, json, time, datetime, traceback

repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'apps/GSHC'))
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from serial.tools import list_ports
import app as production
from protocol.common import AirCalibrationMode

version=sys.argv[1]
assert version in ['test5','current','current_diag']
out=Path(__file__).resolve().parent/version
out.mkdir(exist_ok=False)
production.USER_DATA_ROOT=out/'userdata'
application=QApplication([])
application.setOrganizationName('SilverStarBoundedAcceptance')
application.setApplicationName('GshcComparison20261008_'+version)
window=production.MainWindow()
controller=production.Controller(window)
window.show()
ports=[p for p in list_ports.comports() if p.device=='COM3']
assert len(ports)==1 and (ports[0].vid,ports[0].pid,ports[0].location)==(0x1a86,0x7523,'1-1')
window.port_combo.setCurrentText('COM3')
window.baud_combo.setCurrentText('230400')
record={'version':version,'scope':'Actual GSHC MainWindow/Controller/SerialWorker/ProtocolWorker; Qt-driven production operations, no mouse/manual UI claim','utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'start_calls':0,'operations':[],'errors':[],'gui_input_tool':'unavailable','timeout_ack_ms':production.AIR_CMD_ACK_TIMEOUT_MS,'max_retries':production.AIR_CMD_MAX_RETRIES,'halt_instrumented':version=='current_diag'}
timeline=(out/'observations.jsonl').open('x',encoding='utf-8')
raw_rx=(out/'raw_rx.bin').open('xb')
started=time.monotonic();stage='connect';stage_at=started;mission_at=None;last=None;finishing=False

def note(kind,**fields):
    row={'kind':kind,'monotonic_ns':time.monotonic_ns(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields}
    timeline.write(json.dumps(row,ensure_ascii=False,default=str)+'\n');timeline.flush()

def act(name,fn):
    record['operations'].append(name);note('operation',name=name);fn()
    if name=='CONNECT_COM3' and controller.worker is not None:
        controller.worker.bytes_chunk_received.connect(raw_rx.write,Qt.DirectConnection)
        record['raw_capture_connected_monotonic_ns']=time.monotonic_ns()

def change(next_stage):
    global stage,stage_at
    stage=next_stage;stage_at=time.monotonic();note('stage',stage=stage)

def finish(success,reason):
    global finishing
    if finishing:return
    finishing=True;timer.stop()
    note('finish',success=success,reason=reason)
    window.grab().save(str(out/'final_window.png'))
    record.update(success=success,reason=reason,elapsed_s=time.monotonic()-started,log_path=str(controller.logger.path),mission_started=controller.state.mission_started,mission_start_source=controller.state.mission_start_source,last_start_failure_result=controller.state.last_start_failure_result,logger_error=controller.logger.last_error)
    try:controller.shutdown()
    except Exception as exc:record['errors'].append(repr(exc));record['success']=False
    record.update(serial_closed=controller.worker is None,protocol_closed=controller.protocol_worker is None,utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/'result.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    raw_rx.close();timeline.close();window.close();application.quit()

def tick():
    global last,mission_at
    try:
        s=controller.state
        value={'stage':stage,'connected':s.connected,'capability_acked':s.capability_acked,'capability':None if s.capability is None else {'profile':s.capability.air_profile_id,'mask':s.capability.calibration_mode_mask,'policy':s.capability.command_policy},'lifecycle':s.lifecycle_state,'calibration_ready':s.calibration.ready,'alignment_ready':s.alignment.ready,'system_ready':s.system_ready,'unlocked':s.start_unlocked,'block_reason':s.start_block_reason,'pending':s.pending_command_name,'mission_started':s.mission_started,'mission_source':s.mission_start_source,'start_failed':s.last_start_failure_result,'start_timed_out':s.start_transaction_timed_out,'pending_attempts':[(p.cmd_id,p.sent_count) for p in controller.pending_air_cmds.values()]}
        if value!=last:note('state',**value);last=value
        now=time.monotonic()
        if now-started>65:return finish(False,'bounded total timeout; no additional command')
        if stage!='observe' and now-stage_at>18:return finish(False,'stage timeout '+stage+'; no additional command')
        if s.start_transaction_timed_out:return finish(False,'production START timeout')
        if s.last_start_failure_result is not None:return finish(False,'production START failure '+str(s.last_start_failure_result))
        if stage=='connect':
            if not (s.connected and s.capability_acked and s.capability is not None):return
            expected=1 if version=='test5' else 3
            if s.capability.air_profile_id!=0 or s.capability.calibration_mode_mask!=expected or s.capability.command_policy!=1:return finish(False,'unexpected capability; business commands blocked')
            if s.calibration.ready:change('alignment')
            elif version=='test5':return
            else:act('CAL_START_ONE_FACE',lambda:controller.send_cal_start(int(AirCalibrationMode.ONE_FACE)));change('calibration')
        elif stage=='calibration':
            if s.calibration.ready and not controller.pending_air_cmds:change('alignment')
        elif stage=='alignment':
            if controller.pending_air_cmds:return
            if s.alignment.ready:change('unlock')
            else:act('ALIGN_START',controller.send_align_start);change('align_wait')
        elif stage=='align_wait':
            if s.alignment.ready and not controller.pending_air_cmds:change('unlock')
        elif stage=='unlock':
            if controller.pending_air_cmds:return
            if s.start_unlocked:change('start')
            else:act('UNLOCK',controller.send_unlock);change('unlock_wait')
        elif stage=='unlock_wait':
            if s.start_ready():change('start')
        elif stage=='start':
            if not s.start_ready():return
            assert record['start_calls']==0
            record['start_calls']+=1;act('START_MISSION',controller.send_start);change('start_wait')
        elif stage=='start_wait':
            if s.mission_started:mission_at=now;change('observe')
        elif stage=='observe':
            duration=6 if version=='test5' else (22 if version=='current_diag' else 20)
            if now-mission_at>=duration:return finish(True,'finite observation complete; TEST5 landing not induced' if version=='test5' else 'finite observation complete; inspect persisted events for lifecycle results')
    except Exception as exc:
        record['errors'].append(traceback.format_exc());finish(False,repr(exc))

timer=QTimer();timer.setInterval(50);timer.timeout.connect(tick)
QTimer.singleShot(0,lambda:act('CONNECT_COM3',controller.connect))
timer.start();application.exec()
print(json.dumps(record,ensure_ascii=True,indent=2),flush=True)
raise SystemExit(0 if record.get('success') and record.get('serial_closed') and record.get('protocol_closed') else 1)
