from pathlib import Path
import sys, time, json
from dataclasses import asdict
from datetime import datetime, timezone
import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.work/FieldBenchHarness_20261003'))
from field_bench import Bench

out = Path(__file__).resolve().parent / 'passive_initial'
out.mkdir(exist_ok=False)
ports = list(list_ports.comports())
matches = [p for p in ports if p.device == 'COM3' and p.vid == 0x1A86 and p.pid == 0x7523 and p.location == '1-1']
if len(matches) != 1:
    raise SystemExit('Confirmed historical Ground UART identity missing or ambiguous; no port opened')
b = Bench('COM3', out)
summary = {'started_utc': datetime.now(timezone.utc).isoformat(), 'port': 'COM3', 'baud':230400, 'transmitted_bytes':0, 'dtr':False, 'rts':False, 'duration_s':30, 'serial_identity':matches[0].hwid}
ser = serial.Serial(port=None, baudrate=230400, timeout=0.05, write_timeout=0.5, rtscts=False, dsrdtr=False)
ser.dtr = False
ser.rts = False
ser.port = 'COM3'
try:
    with (out/'raw_rx.bin').open('xb') as raw, (out/'events.jsonl').open('x',encoding='utf-8') as events:
        b.raw, b.events, b.ser = raw, events, ser
        ser.open()
        b.record('session', **summary)
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            b.receive()
        summary.update(capability=asdict(b.capability) if b.capability else None, preflight=asdict(b.preflight) if b.preflight else None, gs_status=asdict(b.gs_status) if b.gs_status else None, flight_frames=b.flight_count, gsp_diagnostics=asdict(b.parser.diagnostics()), exit_code=0)
        b.record('passive_summary', **summary)
except Exception as exc:
    summary.update(exit_code=1,error=repr(exc))
finally:
    ser.close()
    summary['finished_utc']=datetime.now(timezone.utc).isoformat()
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
raise SystemExit(summary['exit_code'])
