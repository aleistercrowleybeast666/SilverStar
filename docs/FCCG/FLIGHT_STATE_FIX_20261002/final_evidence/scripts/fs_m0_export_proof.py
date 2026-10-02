from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
out=repo/'.work/m0_c_frames_export';out.mkdir(exist_ok=False)
sys.path.insert(0,str(repo/'apps/GSHC'))
from protocol.gsp_min import build_gsp_frame
from protocol.receive_pipeline import ReceivePipeline,protocol_event_log_records
from processing.flight_log_processor import FlightLogProcessor
from services.preferences import ResolvedExportOptions,ExportItem,Theme
from services.i18n import Language
log=repo/'.work/m0_final_v2_evidence/counter_contended.log'
flight=[bytes.fromhex(line.split()[1]) for line in log.read_text(encoding='utf8').splitlines() if line.startswith('FLIGHT_HEX ')]
assert len(flight)==61
golden=json.loads((repo/'.work/m0_golden_v2/golden.json').read_text(encoding='utf8'))
capability=bytes.fromhex(next(h for h in golden['wire_hex'] if h.startswith('12')))
pipeline=ReceivePipeline();records=[]
for index,wire in enumerate([capability]+flight):
 for event in pipeline.feed(build_gsp_frame(2,bytes((186,20,len(wire)))+wire),1000000000+index*200000000):
  records.extend(protocol_event_log_records(event))
source=out/'HOST_GENERATED_C_NOT_HARDWARE.jsonl'
source.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in records)+'\n',encoding='utf8')
before=hashlib.sha256(source.read_bytes()).hexdigest()
options=ResolvedExportOptions(language=Language.EN_US,theme=Theme.LIGHT,items=frozenset({ExportItem.PROCESSED_DATA,ExportItem.SUMMARY,ExportItem.SESSION_INFO}))
processor=FlightLogProcessor(output_root=out/'export',export_options=options)
result=processor.process_file(source)
after=hashlib.sha256(source.read_bytes()).hexdigest();assert before==after
assert not processor.last_export_errors
proof={'C_counter_log':str(log),'C_counter_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'C_flight_frames':len(flight),'actual_receive_pipeline_records':len(records),'source_log':str(source),'source_before':before,'source_after':after,'export_path':str(result),'last_export_errors':processor.last_export_errors,'files':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()},'scope':'Host C scheduler frame/export proof; no hardware mission. Missing MISSION_START uses existing first-FLIGHT start fallback; no source log fabrication of a mission-start event.'}
(out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8');print(json.dumps(proof,indent=2),flush=True)
