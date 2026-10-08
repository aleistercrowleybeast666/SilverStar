from pathlib import Path
import os,sys,json,hashlib,zipfile,datetime,time,dataclasses,collections,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
repo=Path(__file__).resolve().parents[2];root=Path(__file__).resolve().parent
sys.path.insert(0,str(repo/'apps/FLP/src'))
import numpy as np
from silverstar_flp.log_open import LogOpenCoordinator,LogOpenRequest
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.analysis.overview import FlightSummary_Build

def js(v):
 if dataclasses.is_dataclass(v):return {f.name:js(getattr(v,f.name)) for f in dataclasses.fields(v)}
 if isinstance(v,dict) or hasattr(v,'items'):return {str(k):js(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [js(x) for x in v]
 if isinstance(v,bytes):return v.hex()
 if isinstance(v,Path):return str(v)
 if isinstance(v,np.ndarray):return v.tolist()
 if isinstance(v,np.generic):return v.item()
 return v
def write(p,v):p.write_text(json.dumps(js(v),indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
source=Path('D:/stm32_project/missions.zip')
source_sha=sha(source);source_stat=source.stat()
decoder=repo/'.work/bench08c_f407/KF6_Static_20261008_f045d8c.ssdecoder'
assert sha(decoder)=='46b449244dcfde73baa5faaa795ac496d34f097bd095824959f53210067fafe2'
inventory=[]
with zipfile.ZipFile(source) as z:
 infos=z.infolist()
 for mission in [44,45]:
  prefix=f'missions/{mission:06}/'
  selected=[i for i in infos if i.filename.startswith(prefix) and not i.is_dir()]
  names=[i.filename for i in selected]
  assert len(names)==len(set(names)), 'Duplicate selected source member'
  required={prefix+n for n in ['manifest','flight.sslog']+[f'snap{i:02}.0' for i in range(8)]}
  assert required.issubset(set(names)), sorted(required-set(names))
  for i in selected:
   rel=Path(i.filename);assert len(rel.parts)==3 and '..' not in rel.parts and not rel.is_absolute()
   assert i.file_size<=16000000
   data=z.read(i);p=root/'input'/rel
   p.parent.mkdir(parents=True,exist_ok=True)
   assert not p.exists(),'Never overwrite input snapshot'
   p.write_bytes(data)
   inventory.append({'source_member':i.filename,'snapshot_path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'zip_crc32':f'{i.CRC:08x}','zip_crc_verified':True,'zip_timestamp':i.date_time})
write(root/'input_inventory.json',{'archive':str(source),'archive_sha256':source_sha,'archive_bytes':source_stat.st_size,'archive_mtime_utc':datetime.datetime.fromtimestamp(source_stat.st_mtime,datetime.timezone.utc).isoformat(),'member_timestamps':'1980 values not acquisition UTC evidence','unrelated_archive_member_crc_scan':'NOT_RUN','members':inventory,'decoder':{'path':str(decoder),'sha256':sha(decoder)},'repository_HEAD':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip()})
for mission in [44,45]:
 dest=root/f'm{mission}';dest.mkdir(exist_ok=False)
 coordinator=LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(dest/'cache'))
 start=time.monotonic()
 try:opened=coordinator.Open(LogOpenRequest(root/'input'/f'missions/{mission:06}/flight.sslog',decoder))
 except Exception as e:
  write(dest/'failure.json',{'error':repr(e),'traceback':traceback.format_exc()});raise
 ds=opened.dataset
 summary={'mission':mission,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seconds':time.monotonic()-start,'match_mode':opened.match_mode,'descriptor':opened.descriptor,'package_sha256':opened.package.package_sha256,'header':ds.header,'diagnostics':opened.parse_diagnostics.to_dict(),'data_quality':opened.data_quality,'overview':FlightSummary_Build(ds),'metadata':ds.metadata,'record_counts':{k:len(v) for k,v in ds.records.items()}}
 write(dest/'parse_summary.json',summary)
 write(dest/'record_samples.json',{k:{'count':len(v),'first':js(v[0]),'last':js(v[-1])} for k,v in ds.records.items() if v})
 write(dest/'critical_records.json',{k:[js(r) for r in v] for k,v in ds.records.items() if k in {'EVENT','INITIAL_STATE','CALIBRATION_RESULT','ALIGNMENT_RESULT','ALIGNMENT_EVIDENCE','MISSION_SNAPSHOT_IDENTITY','MAG_CALIBRATION_IDENTITY','STATS','SYSTEM_CONFIG','DECODER_PROFILE_DESCRIPTOR','DEPLOY_DETAIL','LANDING_DIAGNOSTIC'}})
 health={}
 for k,v in ds.records.items():
  if k not in {'ESTIMATOR','ESTIMATOR_STEP','BARO_MEASUREMENT','HEALTH','STATS','TELEMETRY_DIAGNOSTIC','IMU_CORRECTED','INERTIAL_INCREMENT','GNSS_NATIVE','BARO_NATIVE'} or not v:continue
  items=[js(r) for r in v];payloads=[r['payload'] for r in items]
  timestamps=np.array([r['timestamp_us'] for r in items],dtype=np.int64)
  seqs=[r['record_sequence'] for r in items]
  fields={}
  for name in payloads[0]:
   values=[r[name] for r in payloads if name in r]
   if not values or not all(isinstance(x,(int,float)) for x in values):continue
   fields[name]={'min':min(values),'max':max(values),'first':values[0],'last':values[-1],'finite':all(np.isfinite(x) for x in values),'distinct':sorted(set(values))[:24]}
  delta=np.diff(timestamps)
  health[k]={'count':len(v),'first_timestamp_us':int(timestamps[0]),'last_timestamp_us':int(timestamps[-1]),'min_interval_us':int(delta.min()) if len(delta) else None,'max_interval_us':int(delta.max()) if len(delta) else None,'nonpositive_interval_count':int(np.sum(delta<=0)),'fields':fields}
 write(dest/'health_field_summary.json',health)
 print(json.dumps({'mission':mission,'seconds':summary['seconds'],'diagnostics':summary['diagnostics'],'record_counts':summary['record_counts'],'log_sha256':next(x['sha256'] for x in inventory if x['source_member']==f'missions/{mission:06}/flight.sslog')},default=str),flush=True)
assert sha(source)==source_sha and source.stat().st_size==source_stat.st_size
print('Original source archive and exact decoder preserved',flush=True)
