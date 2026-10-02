from pathlib import Path
import hashlib,json,os,struct,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
out=repo/'.work/m0_golden';out.mkdir(exist_ok=False)
fixture=Path(__file__).with_name('m0_golden_host.c')
records=[];outputs={}
for label,project in [('old',repo/'.work/fs_counter/Flight_Controller'),('new',repo/'.work/m0_final/Flight_Controller')]:
 command=[r'D:\msys64\ucrt64\bin\gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-include',str(project/'Generated/Inc/project_flight_config.h')]
 includes=[p for p in project.rglob('Inc') if 'build' not in p.parts]+[project/'Tests/Host',project/'System/User']
 for p in includes:command+=['-I',str(p)]
 exe=out/(label+'.exe');command += [str(fixture),str(project/'Protocol/Src/air_protocol.c'),str(project/'Common/Src/silverstar_assert.c'),'-lm','-o',str(exe)]
 for name,cmd in [('compile_'+label,command),('golden_'+label,[str(exe)])]:
  result=subprocess.run(cmd,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=90)
  log=out/(name+'.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
  records.append({'name':name,'command':cmd,'cwd':str(project),'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
  print(name,result.returncode,result.stdout+result.stderr,flush=True)
  if result.returncode:
   (out/'results.json').write_text(json.dumps(records,indent=2),encoding='utf8');sys.exit(1)
  if name.startswith('golden_'):outputs[label]=[bytes.fromhex(l) for l in result.stdout.splitlines() if l and all(c in '0123456789abcdef' for c in l)]
assert outputs['old']==outputs['new'] and len(outputs['new'])==8
prefix=lambda typ:struct.pack('<BBIhhhhhhhhhh',typ,42,0x12345678,100,-200,300,-400,500,-600,32767,0,0,0)
expected=[prefix(16)+struct.pack('<ffffff',1.25,-2.5,3.75,4.,-5.,6.),prefix(17),bytes.fromhex('122a0001070f10d007'),bytes.fromhex('132a03241503337f00'),bytes.fromhex('142a050100ff000001'),bytes.fromhex('202a03785634120100'),bytes.fromhex('302a01c33c5aa50000'),bytes.fromhex('402a0b010078563412')]
# Alignment state occupies low nibble; diagnostic high nibble is zero.
expected[3]=bytes.fromhex('132a03241503037f00')
assert outputs['new']==expected,[[b.hex() for b in outputs['new']],[b.hex() for b in expected]]
sys.path.insert(0,str(repo/'apps/GSHC'))
from protocol.air import parse_air_frame,build_air_cmd
for frame in outputs['new']:
 raw,message=parse_air_frame(frame);assert raw.raw==frame
assert build_air_cmd(42,1,0xA55A3CC3)==expected[6]
(out/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
(out/'golden.json').write_text(json.dumps({'types':[f'{b[0]:02x}' for b in expected],'wire_hex':[b.hex() for b in expected],'old_new_byte_equal':True,'independent_struct_vectors_equal':True,'gshc_parsed_all8':True},indent=2)+'\n',encoding='utf8')
print('ALL8 old/new/independent vectors byte identical; actual GSHC parse all8',flush=True)
