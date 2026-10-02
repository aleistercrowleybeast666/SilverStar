from pathlib import Path
import datetime,gzip,hashlib,json,shutil,subprocess,sys,time,zipfile
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
firmware=repo/'.work/m0_final_v2_evidence';gshc=repo/'.work/gshc_final_evidence'
deadline=time.monotonic()+1800
while time.monotonic()<deadline:
 records=json.loads((gshc/'results.json').read_text(encoding='utf8')) if (gshc/'results.json').exists() else []
 final=next((r for r in records if r['name']=='GSHC_full'),None)
 if final is not None:
  if final['exit']!=0:raise RuntimeError('GSHC full gate failed; do not freeze')
  break
 time.sleep(1)
else:raise TimeoutError('Full GSHC pending; do not freeze')
firmware_records=json.loads((firmware/'results.json').read_text(encoding='utf8'))
assert len(firmware_records)==15 and all(r['exit']==0 for r in firmware_records)
assert len(records)==3 and all(r['exit']==0 for r in records)
git=['git','-c','core.longpaths=true','-c','safe.directory='+repo.as_posix(),'-C',str(repo)]
source_commit=subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()
assert source_commit.startswith('494dcf5'),source_commit
assert not subprocess.check_output(git+['status','--porcelain'],text=True).strip()
out=repo/'docs/FCCG/FLIGHT_STATE_FIX_20261002/final_evidence'
freeze=repo/'.work/M0TelemetryFreeze_20261002'
for p in [out,freeze]:
 if p.exists():raise FileExistsError('Preserve existing evidence/freeze: '+str(p))
out.mkdir(parents=True);freeze.mkdir(parents=True)
project=repo/'.work/m0_final_v2/Flight_Controller';build=project/'build/FCCG/SilverStar_F407/Release'
artifact={}
for extension in ['elf','bin','hex','map']:
 p=build/('SilverStar_0_1_1.'+extension);q=freeze/p.name;shutil.copy2(p,q)
 artifact[extension]={'path':str(q),'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()}
decoder=project/'SS_M0FlightStateRepair_20261002.ssdecoder';shutil.copy2(decoder,freeze/decoder.name)
shutil.copy2(firmware/'Input.ssproject',freeze/'Input.ssproject')
for name,folder in [('firmware',firmware),('gshc',gshc),('golden',repo/'.work/m0_final2_golden')]:
 target=out/name;target.mkdir()
 for p in folder.iterdir():
  if not p.is_file() or p.suffix.lower()=='.exe':continue
  if p.suffix=='.log':
   with p.open('rb') as source,gzip.open(target/(p.name+'.gz'),'wb') as dest:shutil.copyfileobj(source,dest)
  else:shutil.copy2(p,target/p.name)
failed=out/'failed_attempts';failed.mkdir()
for name in ['m0_final_evidence','gshc_retry_evidence','gshc_retry2_evidence','gshc_first_failed_inputs','host_gui_second_failed_inputs','m0_golden']:
 folder=repo/'.work'/name;target=failed/name;target.mkdir()
 for p in folder.iterdir():
  if not p.is_file() or p.suffix.lower()=='.exe':continue
  if p.suffix=='.log':
   with p.open('rb') as source,gzip.open(target/(p.name+'.gz'),'wb') as dest:shutil.copyfileobj(source,dest)
  else:shutil.copy2(p,target/p.name)
shutil.copytree(repo/'.work/m0_c_frames_export',out/'C_frames_export')
review=out/'review';shutil.copytree(repo/'.work/m0_review',review)
source=(review/'minimal_production.diff').read_text(encoding='utf8');offset=0;part=1
while offset<len(source):
 count=min(9000,len(source)-offset)
 if count==9000:count=source.rfind('\n',offset,offset+count)+1-offset
 (review/('minimal_production_part'+str(part)+'.diff')).write_text(source[offset:offset+count],encoding='utf8')
 offset+=count;part+=1
lines=(project/'Modules/Src/telemetry_service.c').read_text(encoding='utf8').splitlines()
for name in ['TelemetryService_StreamSend','TelemetryService_Process','TelemetryService_CommandDispatch']:
 start=next(i for i,l in enumerate(lines) if name+'(' in l and l.startswith(('static ','void ')))
 brace=start
 while '{' not in lines[brace]:brace+=1
 depth=0
 for end in range(brace,len(lines)):
  depth+=lines[end].count('{')-lines[end].count('}')
  if depth==0:break
 (review/(name+'.c')).write_text('\n'.join(lines[start:end+1])+'\n',encoding='utf8')
screens=out/'windows_gui';screens.mkdir()
for p in (repo/'apps/GSHC/.work/m0-release-gui').glob('windows_*.png'):shutil.copy2(p,screens/p.name)
assert len(list(screens.glob('*.png')))==8
tracked=subprocess.check_output(git+['ls-files','apps/GSHC'],text=True).splitlines();gshc_identity={}
with zipfile.ZipFile(freeze/'GSHC_source.zip','w',zipfile.ZIP_DEFLATED) as archive:
 for relative in tracked:
  p=repo/relative
  if p.is_file():
   archive.write(p,relative);gshc_identity[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
(out/'GSHC_identity.json').write_text(json.dumps({'source_commit':source_commit,'files':gshc_identity},indent=2)+'\n',encoding='utf8')
config=json.loads((firmware/'Input.ssproject').read_text(encoding='utf8'))
assert config['components']['strategies']['estimator']=='silverstar.algorithm.estimator.kf6'
assert config['modes']['deployment']==['Delay']
assert config['mode_parameters']['deployment']['Delay']['delay']==10.0
manifest={'source_commit':source_commit,'base_commit':'245bee70c3ee51291b4c875490a5479e8ec553b3','counter_checkpoint':'9931b397de9b7ce0d58f3a743d0d3ea5460e5b1d','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze':str(freeze),'generated_project':str(project),'artifacts':artifact,'decoder_sha256':hashlib.sha256(decoder.read_bytes()).hexdigest(),'GSHC_zip_sha256':hashlib.sha256((freeze/'GSHC_source.zip').read_bytes()).hexdigest(),'firmware_records':firmware_records,'GSHC_records':records,'hardware_qualification':'NOT_PROVEN; no COM/DAP/flash/mission by this task','critical_contract_review':'NOT_PROVEN: whole-firmware manual acceptance pending','config':{'estimator':'KF6','deployment':'Delay','delay_seconds':10.0,'air_link':config['air_link']},'code_changes':'Only three production owners, no algorithm/driver/board START admission change','GSHC_identity':'GSHC_identity.json','candidate_not_merged_or_pushed':True}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
shutil.copy2(out/'manifest.json',freeze/'manifest.json');shutil.copy2(out/'GSHC_identity.json',freeze/'GSHC_identity.json')
workspace=Path(__file__).parent;scripts=out/'scripts';scripts.mkdir()
for p in workspace.glob('fs_*.py'):shutil.copy2(p,scripts/p.name)
for name in ['m0_golden_host.c','m0_golden_host_v2.c','test_m0_release_gui.py','test_flight_state_scheduler_generated_host.py']:shutil.copy2(workspace/name,scripts/name)
README='''# M0 FLIGHT_STATE software candidate

Source commit {commit}; base245bee70. Candidate only, no hardware action/merge/push.

Final fresh generated firmware: all15 recorded commands exit0: C fixture compile and6 scenarios,30 FCCG radio/stream regressions, ARM Release compile/link, full75 Host executables4,401,516 checks0 failures,7 compile passes17 expected rejects/storage integrity; architecture335/0; PoT6058 text checks/108C/2636functions/752 recommendations; actual static-analyzer ARM compile/link, artifact and stack/memory reports. PoT critical-contract review remains NOT_PROVEN, not certification. Device2128/2560 INS2240/3072 Est3244/4096 Flight3600/4096 Logger2104/3072 Serial4944/6144 Telemetry2136/4096. Flash321964,SRAM102000,CCM55904,heap0. WCET/ISR/main-stack/indirect-path and flight qualification NOT_PROVEN.

Unchanged fixture against old code:14.005s FLIGHT0,NAV_HEALTH57,CAP12,PREP12;4 expected policy failures. New:61 FLIGHT, allthreeNAV0; queue normal<=2,total<=8. Missing IMU/estimator and non-mission states still reject stream. Actual C frames passed unchanged GSP/AIR receive pipeline and GSHC exporter,61 frames,zero export errors,source hash unchanged. Host stimulus only; no fabricated MISSION_START (existing first-FLIGHT export fallback recorded).

Eight M0 types10/11/12/13/14/20/30/40 old/new compiled C outputs byte identical, independent fixed vectors identical, actual GSHC parser accepts all8. 680 generated C/H proof retains algorithms, drivers, internal generation/health/logging/safety and all Ground C/H. Changes: telemetry owner, its Host test, project name metadata and decoder profile identity. Input configuration exact except candidate name; actual2473000000Hz/SF10/BW0800/CR4_5/CRC,Delay10/KF6 retained.

Final GSHC full suite is an actually executed complete suite, not stitched subset passes. Native Windows GUI4 cases also run separately with real M0 parse/controller/START mouse-click, mock serial only; English/Chinese and light/dark screenshots. Headless Qt backend is required for synthetic touch; it does not establish physical touch or OpenGL rendering qualification. All warnings and prior failed attempts retained.

Failures explained: first Host test incorrectly expected BAD_CMD before handshake; originalCAPABILITY_REQUIRED safety gate retained, BAD_CMD only after handshake. GUI fixture initially used wrong CAP_ACK command/invalid flags, then omitted required event. Fixed using valid actual parser/GSP event, no product API/READY relaxation. Two later offscreen English geometry failures were missing original9pt font fixture setup; strict1000x700 unchanged, production UI unchanged. Doc failure corrected by listing three retained legacy decode-only rows under postponed schema41, keeping current release table at8. No failing cases deleted/skipped. Earlier fairness proposal was removed from production before M0 restoration. All old evidence preserved.

Parent must review full minimal_production_part1..3 and original/new function text before hardware thread flashes. RF one-owner/handshake,M9/JY fixes, ESKF15/SF6 and internal preflight/TF/local logging preserved. Detailed NAV radio extension is postponed, decoder compatibility remains. This source candidate has not been integrated with any independent Baro/Radio work.
'''.format(commit=source_commit)
(out/'README.md').write_text(README,encoding='utf8')
file_hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
(out/'evidence_hashes.json').write_text(json.dumps(file_hashes,indent=2)+'\n',encoding='utf8')
subprocess.run(git+['add','docs/FCCG/FLIGHT_STATE_FIX_20261002/final_evidence'],check=True)
subprocess.run(git+['commit','-m','docs: freeze M0 flight telemetry candidate evidence'],check=True)
evidence_head=subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()
(freeze/'evidence_commit.txt').write_text(evidence_head+'\n',encoding='utf8')
print(json.dumps({'source_commit':source_commit,'evidence_head':evidence_head,'freeze':str(freeze),'artifacts':artifact,'gshc':records},indent=2),flush=True)
