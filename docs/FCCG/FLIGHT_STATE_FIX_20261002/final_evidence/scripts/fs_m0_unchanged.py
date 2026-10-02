from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
out=repo/'.work/m0_final_evidence';old=repo/'.work/fs_counter';new=repo/'.work/m0_final'
records=[]
for target in ['Flight_Controller','Ground_Station']:
 before=old/target;after=new/target
 for p in before.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in {'.c','.h'} or 'build' in p.parts:continue
  relative=p.relative_to(before);q=after/relative
  a=hashlib.sha256(p.read_bytes()).hexdigest();b=hashlib.sha256(q.read_bytes()).hexdigest() if q.exists() else None
  records.append({'target':target,'file':relative.as_posix(),'old':a,'new':b,'byte_equal':a==b})
changed=[r for r in records if not r['byte_equal']]
(out/'generated_source_equivalence.json').write_text(json.dumps({'sources':len(records),'changed':changed,'records':records},indent=2)+'\n',encoding='utf8')
config0=json.loads((repo/'.work/fs_counter_evidence/Input.ssproject').read_text(encoding='utf8'));config1=json.loads((out/'Input.ssproject').read_text(encoding='utf8'))
name0=config0['project'].pop('name');name1=config1['project'].pop('name');assert config0==config1
(out/'config_equivalence.json').write_text(json.dumps({'old_name':name0,'new_name':name1,'all_other_configuration_equal':True,'frequency_hz':config1['air_link']['frequency_hz'] if 'air_link' in config1 else None},indent=2)+'\n',encoding='utf8')
print(json.dumps({'source_count':len(records),'changed':changed,'config_except_name_equal':True},indent=2),flush=True)
