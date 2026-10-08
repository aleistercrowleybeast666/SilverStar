from pathlib import Path
import json

out = Path(__file__).resolve().parent
previous = Path('.work/test5_gshc_dap_20261008_v1/gshc_session.py')
text = previous.read_text(encoding='utf-8')
text = text.replace("assert version in ['test5','current','current_diag']", "assert version == 'health_fixed'")
text = text.replace("elif version=='test5':return", "else:return  # No TF calibration command; require existing READY.")
text = text.replace("            else:act('CAL_START_ONE_FACE',lambda:controller.send_cal_start(int(AirCalibrationMode.ONE_FACE)));change('calibration')", '')
text = text.replace("'halt_instrumented':version=='current_diag'", "'halt_instrumented':False,'calibration_commands_allowed':False")
assert 'send_cal_start(' not in text
compile(text, 'gshc_session.py', 'exec')
(out / 'gshc_session.py').write_text(text, encoding='utf-8')
(out / 'hardware_plan.json').write_text(json.dumps(dict(
    permission='Parent user transcript: 允许 exact estimator source proof and previously authorized Flight static retest',
    precondition='All original software gate exits zero; exact BIN/ELF/source/decoder/config identity',
    flight_probe_serial='132765403520', flight_id='0x10076413', flash_kib=512,
    ground_serial={'port':'COM3','vid':'0x1a86','pid':'0x7523','location':'1-1'},
    actuator_state='User confirmed disconnected, +Y stationary, TF inserted',
    allowed='Flight program verify readback; one production GSHC START, existing READY/ALIGN/UNLOCK; read-only startup/post-finalization RAM',
    prohibited=['Ground flash','mass erase','options','CAL_START','TF calibration writes','halt during active mission','breakpoints'],
    mission_identity='Read exact current logger snapshot ID with ELF-derived field layout; never infer sequential IDs',
    acceptance_boundary='RAM finalization/counters and radio lifecycle; actual TF file tail/header/snapshot requires user extraction'), indent=2), encoding='utf-8')
print('Prepared GSHC production harness; no calibration call and exactly one public START')
