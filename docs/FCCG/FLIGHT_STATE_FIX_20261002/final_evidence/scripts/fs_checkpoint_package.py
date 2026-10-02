from pathlib import Path
import ast,collections,gzip,hashlib,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
old=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002\.work\imu_final\Flight_Controller')
hw=Path(r'D:\stm32_project\SilverStar_HardwareBaseline_20261001\FieldIntegration_DualBench_20261002_081145\IMUStartup_Validated_20261002_121336')
out=repo/'docs/FCCG/FLIGHT_STATE_FIX_20261002/old_counter'
out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(repo/'apps/GSHC'))
from protocol.air import parse_air_frame
readonly=repo/'.work/fs_readonly';shutil.copytree(readonly,out/'first_readonly')
records=json.loads((readonly/'runtime_counts.json').read_text(encoding='utf8'))
for r in records:
 counts=collections.Counter()
 for line in Path(r['file']).read_text(encoding='utf8').splitlines():
  row=json.loads(line)
  if row.get('kind')=='AIR_RAW':counts[type(parse_air_frame(bytes.fromhex(row['air_hex']))[1]).__name__]+=1
 r['actual_gshc_parser']=dict(counts)
(out/'runtime_counts_corrected.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
p=old/'APP/Src/estimator_task.c';lines=p.read_text(encoding='utf8').splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('uint8_t Estimator_GetLatestSnapshot('));brace=start
while '{' not in lines[brace]:brace+=1
depth=0
for end in range(brace,len(lines)):
 depth+=lines[end].count('{')-lines[end].count('}')
 if depth==0:break
(out/'Estimator_GetLatestSnapshot.c').write_text('\n'.join(lines[start:end+1])+'\n',encoding='utf8')
for relative,names in [('apps/GSHC/protocol/air.py',['parse_air_frame']),('apps/GSHC/app.py',['_handle_flight_state'])]:
 p=repo/relative;source=p.read_text(encoding='utf8');lines=source.splitlines();tree=ast.parse(source)
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
   (out/(node.name+'.py')).write_text('\n'.join(lines[node.lineno-1:node.end_lineno])+'\n',encoding='utf8')
shutil.copy2(hw/'PostFlight/Offline_decoded.json',out/'postflight_snapshot_readonly.json')
counter=repo/'.work/fs_counter_evidence';shutil.copytree(counter,out/'counter_attempts',ignore=shutil.ignore_patterns('*.exe'))
for name in ['fs_readonly_checkpoint.py','fs_counter_prepare.py','fs_counter_retry.py','fs_counter_retry3.py','fs_counter_retry4.py','fs_counter_cases.c','fs_counter_main.c']:
 shutil.copy2(Path(__file__).parent/name,out/name)
manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
(out/'README.md').write_text('''# FLIGHT_STATE old-code counter and source review

Base 245bee70c3ee51291b4c875490a5479e8ec553b3. No production change at this checkpoint.

Hardware immutable logs: 159 AIR_RAW frames, no type 0x10/length50 in either GSP radio payload or AIR layer. Actual GSHC parser accepts all159; corrected tuple payload classification is runtime_counts_corrected.json. The first readonly script incorrectly classified the returned tuple rather than its message; its original output is retained, and does not establish message classes. Existing export rejection is consistent with absent source frames, not evidence of GUI dropping FLIGHT_STATE.

Actual generated StreamSend: FLIGHT/RECOVERY, deadline, valid accel/gyro, and initialized published estimator. No GNSS-fix/origin gate. Postflight read snapshots show initialized=1,predict1402,published sequence1403,GNSS-origin=0,baro-origin=1. These are postflight non-atomic reads, not proof of the live telemetry call ordering or latest-IMU flags.

Valid counter v4 uses fresh actual generated TelemetryService, AIR builder, SX1281 transport and driver queues; hardware ports and unrelated subsystem endpoints are Host fixtures. Real normal capacity2,total8, SF10/BW0800/CR4_5,preamble0x18,CRC ON. Exact inherited config frequency2473000000Hz, not2395000000; no RF configuration was changed. Hardware mission cannot be quantitatively reproduced by this virtual IRQ timeline.

Old v4 contended 14005ms: FLIGHT0,NAV_HEALTH58,NAV_CAP12,NAV_PREP12, queued2,streamdeadline0:28187 checks,1 expected failure. NAV-disabled/no-GNSS control:3024/0,7 FLIGHT. No-estimator and no-IMU independent-process controls:3029/0 each,0 FLIGHT,6 NAV. All strict GCC flags including -Werror preserved.

v1/v2 compilation failures, and v3 wrong fixture endpoint/frequency/reset assumptions are retained. They are not evidence of the production defect. v4 corrects those assumptions without production edits. Post-fix expectations will remain unchanged.

Proposed narrow design: alternate preferred normal class after accepted enqueue; failed enqueue cannot count as accepted. Keep control priority, existing periods, queue capacities, format and GNSS-optional mission behavior. Keep missing IMU/estimator rejection. No hardware or COM/DAP access and no mission was performed by this software task. Full source in first_readonly/*.c plus Estimator_GetLatestSnapshot.c and Python parser/handler snapshots.
''',encoding='utf8')
cmd=['git','-c','core.longpaths=true','-c','safe.directory='+repo.as_posix(),'-C',str(repo)]
subprocess.run(cmd+['add','docs/FCCG/FLIGHT_STATE_FIX_20261002/old_counter'],check=True)
subprocess.run(cmd+['commit','-m','test: preserve generated FLIGHT_STATE starvation counter'],check=True)
print('CHECKPOINT',subprocess.check_output(cmd+['rev-parse','HEAD'],text=True).strip(),flush=True)
