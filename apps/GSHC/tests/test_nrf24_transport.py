from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import sys
import json
import pytest
from protocol.gsp_min import GspFrame, GsToPcAirFrame, GspParser, build_gsp_frame, parse_gsp_frame
from protocol.receive_pipeline import ReceivePipeline, protocol_event_log_records
from test_receive_pipeline import capability_frame, flight_frame, air_rx_gsp
from processing.flight_log_processor import FlightLogProcessor
from processing.flight_plotter import FlightPlotter, PlotterConfig
from transport.protocol_worker import ProtocolBatch

def nrf(air):
    return build_gsp_frame(5, bytes([1,0,len(air)])+air)

@pytest.mark.parametrize("payload", [b"",b"\x01\x00\x00",b"\x02\x00\x01x",b"\x01\x01\x01x",b"\x01\x00\x02x",bytes([1,0,62])+b"x"*62])
def test_typed_envelope_rejects_incomplete_unknown(payload):
    assert parse_gsp_frame(GspFrame(5,payload)) is None

def test_metric_capability_and_legacy_negative_value():
    legacy=parse_gsp_frame(GspParser().feed(air_rx_gsp(flight_frame(1,1000),-128,-128))[0])
    assert (legacy.rssi_dbm,legacy.snr_db,legacy.metrics_supported)==(-128,-32.0,True)
    current=parse_gsp_frame(GspParser().feed(nrf(flight_frame(1,1000)))[0])
    assert current.air_frame==legacy.air_frame
    assert (current.rssi_dbm,current.snr_db,current.radio_backend,current.metrics_supported)==(None,None,"nrf24l01p",False)

def test_controller_clears_sx_metrics_and_rejects_stale_session():
    from app import Controller
    state=SimpleNamespace(rssi_dbm=-70,snr_db=5,radio_backend="sx128x",radio_metrics_supported=True,touch=lambda:None)
    owner=SimpleNamespace(state=state,_connection_generation=7,_handle_air_message=lambda *args:None)
    events=ReceivePipeline().feed(nrf(capability_frame()))
    Controller.on_protocol_batch(owner,ProtocolBatch(6,tuple(events)))
    assert state.rssi_dbm==-70
    Controller.on_protocol_batch(owner,ProtocolBatch(7,tuple(events)))
    assert (state.rssi_dbm,state.snr_db,state.radio_backend,state.radio_metrics_supported)==(None,None,"nrf24l01p",False)

def test_pipeline_parsed_and_raw_export_has_no_fake_measurements(tmp_path):
    pipeline=ReceivePipeline()
    wire=nrf(capability_frame())+nrf(flight_frame(1,1000))+nrf(flight_frame(2,1200))
    records=[r for event in pipeline.feed(wire) for r in protocol_event_log_records(event)]
    air_records=[r for r in records if r.get("layer") in {"AIR_RAW","AIR_PARSED"}]
    assert air_records and all(r.get("rssi_dbm") is None and r.get("snr_db") is None for r in air_records)
    assert all(r["radio_backend"]=="nrf24l01p" and r["radio_metrics_supported"] is False for r in air_records)
    processor=FlightLogProcessor()
    parsed=processor._extract_flight_data(records,tmp_path/'in.jsonl')
    raw=processor._extract_flight_data([r for r in records if r.get("layer")=="GSP"],tmp_path/'in.jsonl')
    assert len(parsed.pos)==len(raw.pos)==2 and parsed.link==raw.link==[]
    target=tmp_path/'processed.txt';processor._write_processed_data(parsed,target)
    text=target.read_text(encoding='utf8');link=text.split('[link_quality]')[1].strip().splitlines()
    assert len(link)==1 and 'rssi_dbm' in link[0] and 'snr_db' in link[0]
    plotter=FlightPlotter(PlotterConfig());figures=[]
    with patch.object(plotter,'_save_figure',side_effect=lambda fig,*args,**kw:figures.append(fig)):
        plotter.plot_link_quality(tmp_path/'link.png',parsed.link)
    assert len(figures)==1 and len(figures[0].axes)==2 and all(len(ax.lines)==0 for ax in figures[0].axes)

def test_old_actual_parser_ignores_new_type(tmp_path):
    repo=Path(__file__).resolve().parents[3]
    package=tmp_path/'legacy';package.mkdir();(package/'__init__.py').write_text('')
    for name in ('common.py','gsp_min.py'):
        r=subprocess.run(['git','-c','safe.directory='+str(repo), 'show','0bb06c94cf40dac9c18f04807938a1aef963d5f2:apps/GSHC/protocol/'+name],cwd=repo,capture_output=True,check=True)
        (package/name).write_bytes(r.stdout)
    command=[sys.executable,'-c',"from legacy.gsp_min import GspParser,parse_gsp_frame; import sys; frames=GspParser().feed(bytes.fromhex(sys.argv[1])); assert len(frames)==1 and parse_gsp_frame(frames[0]) is None",nrf(capability_frame()).hex()]
    result=subprocess.run(command,cwd=tmp_path,capture_output=True,text=True)
    (tmp_path/'old_parser.json').write_text(json.dumps({'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}),encoding='utf8')
    assert result.returncode==0,result.stderr


def test_parsed_unsupported_flag_suppresses_numeric_placeholder(tmp_path):
    records=[r for event in ReceivePipeline().feed(nrf(capability_frame())+nrf(flight_frame(1,1000))) for r in protocol_event_log_records(event)]
    for record in records:
        if record.get('layer')=='AIR_PARSED' and record.get('kind')=='FLIGHT_STATE':
            record['rssi_dbm']=0;record['snr_db']=127
            assert record['radio_metrics_supported'] is False
    data=FlightLogProcessor()._extract_flight_data(records,tmp_path/'input.jsonl')
    assert data.link==[]
