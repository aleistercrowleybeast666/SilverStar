from pathlib import Path
import json

root = Path(__file__).resolve().parent
path = root / 'hardware_plan.json'
record = json.loads(path.read_text())
record['allowed'] += '; one selected +Y OneFace RAM calibration required after reset'
record['prohibited'].remove('CAL_START')
record['ram_calibration_review'] = dict(
    source='System/Calibration/Src/system_calibration.c:SystemCalibration_OneFaceCorrectionApply',
    effect='RAM s_status bias/scales, generation, READY; no TF calibration-object writer. Ordinary new mission log/snapshot freezes runtime identity.',
    initial_guard_failure='Startup snapshot_ready=0 is not a product failure; production calibration/alignment/storage gates determine START readiness.')
path.write_text(json.dumps(record, indent=2), encoding='utf-8')
path = root / 'gshc_session.py'
text = path.read_text().replace("'calibration_commands_allowed':False", "'calibration_commands_allowed':'OneFace RAM only; TF calibration object writes forbidden'")
compile(text, 'gshc_session.py', 'exec')
path.write_text(text, encoding='utf-8')
