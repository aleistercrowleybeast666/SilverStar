"""Cross-check Java fixtures with byte-preserved frozen PC protocol/reader.
Only optional GUI/plotting/preference imports are stubbed; protocol and log
reader functions execute verbatim. No rendering/export claim is made.
"""
import dataclasses
import importlib
import json
import math
import os
from pathlib import Path
import sys
import types
sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'reference/v0.1.2/apps/GSHC'
sys.path.insert(0,str(REF))
def module(name, **values):
    m=types.ModuleType(name)
    m.__dict__.update(values)
    sys.modules[name]=m
    return m
module('config',STANDARD_GRAVITY_MPS2=9.80665)
module('services.i18n',Language=types.SimpleNamespace(EN_US='en',ZH_CN='zh'))
module('services.preferences',ALL_EXPORT_ITEMS=(),ExportItem=object,ExportTheme=object,ResolvedExportOptions=object,Theme=object)
module('processing.flight_plotter',FlightPlotter=object,PlotterConfig=object)
module('processing.time_ranges',GifPlan_Build=None,PageName_Build=None,Pages_Build=None)
from protocol.gsp_min import GspParser,parse_gsp_frame
from protocol.air import parse_air_frame
from processing.flight_log_processor import FlightLogProcessor
BUILD=Path(os.environ.get('SILVERSTAR_ANDROID_BUILD_ROOT',str(ROOT/'build')))
fixture=BUILD/'core-tests/simulation-session.jsonl'
records=[json.loads(line) for line in fixture.read_text(encoding='utf-8').splitlines()]
frames=0
for i,r in enumerate(records):
    if r.get('layer')!='GSP':continue
    parser=GspParser(); parsed=parser.feed(bytes.fromhex(r['raw_hex']))
    assert len(parsed)==1 and parser.crc_errors==0
    envelope=parse_gsp_frame(parsed[0]); assert envelope is not None
    _,air=parse_air_frame(envelope.air_frame)
    raw,typed=records[i+1:i+3]
    assert raw['air_hex']==envelope.air_frame.hex()
    assert raw['radio_backend']==envelope.radio_backend
    assert raw['rssi_dbm']==envelope.rssi_dbm and raw['snr_db']==envelope.snr_db
    for field,value in dataclasses.asdict(air).items():
        actual=typed[field]
        if isinstance(value,tuple):
            assert len(actual)==len(value)
            assert all(math.isclose(a,b,abs_tol=1e-12) for a,b in zip(actual,value)),(field,actual,value)
        else:assert actual==value,(field,actual,value)
    frames+=1
reader=FlightLogProcessor.__new__(FlightLogProcessor)
reader.gap_threshold_s=None;reader.pos_z_is_height=True
loaded=reader._read_jsonl(fixture)
full=reader._extract_flight_data(loaded,fixture)
raw_only=[r for r in loaded if r.get('layer') in ('GSP','SESSION')]
raw_data=reader._extract_flight_data(raw_only,fixture)
assert full.simulated and raw_data.simulated
assert full.mission_start_ms==raw_data.mission_start_ms==6000
assert full.end_ms==raw_data.end_ms==12000
assert len(full.pos)==len(raw_data.pos)==31
assert full.pos==raw_data.pos
assert full.accel==raw_data.accel
print(f'PASS: frozen v0.1.2 Python decoded {frames} Java GSP/AIR frames field-for-field; PC JSONL reader full/raw-only both yielded 31 flight samples and simulated=True. GUI/plotting imports stubbed; no rendering or hardware validation.')
