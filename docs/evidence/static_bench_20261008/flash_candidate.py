"""Default: print the exact reviewable flash plan. --execute performs one flash."""
from pathlib import Path
import sys,json,hashlib,subprocess,datetime,time
out=Path(__file__).resolve().parent
repo=out.parents[1]
project=repo/'.work/bench08b_f407/Flight_Controller'
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo).strip()
generated=json.loads((out/'generation_b_result.json').read_text(encoding='utf-8'))
assert generated['source_head']==head and generated['configuration_keys_unchanged'] and generated['resources_unchanged']
for name in ['architecture','power10','release','analyzer','host']:
    r=json.loads((out/(name+'_result.json')).read_text())
    assert r['exit_code']==0 and r['source_commit']==head
    assert hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()==r['log_sha256']
artifacts={}
paths={'elf':project/'build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf',
       'bin':project/'build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin',
       'generated_semantics':project/'Generated/project_semantics.json',
       'configuration':project.parent/'SilverStar.ssproject'}
decoders=list(project.parent.glob('*.ssdecoder'))
assert len(decoders)==1
paths['decoder']=decoders[0]
for name,p in paths.items():
    artifacts[name]={'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
assert artifacts['bin']['bytes']<512*1024
backup=out/'current_F407_before_test_fullflash.bin'
assert hashlib.sha256(backup.read_bytes()).hexdigest()=='e72caaa5adbb92d69854d824ce05ee086a2a1deb83f2e79a3d70ed01aebe8aa1'
readback=out/'flashed_image_readback.bin'
record={'source_commit':head,'probe':'132765403520','expected_id':'0x10076413','expected_flash_kib':512,
        'board_configuration':'SS0.5/F407VET6; actual silicon ID identifies F407 family/revision and size, not package suffix',
        'configuration':'Full KF6 / JY901B vertical ORIENT / M9N / SX1281 / SD_SDIO / OneFace / Delay10; actuators physically disconnected by user',
        'artifacts':artifacts,'prior_image_backup':str(backup),'ground_reflash':False,
        'safety_scope':'Software gate exits passed. Manual critical-contract review, whole-stack/WCET and flight qualification remain NOT PROVEN.',
        'flash_operation':'One program+verify+reset of Flight main image; no option-byte/protection/mass erase or Ground operation.'}
(out/'flash_plan.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2),flush=True)
if '--execute' not in sys.argv:raise SystemExit(0)
if readback.exists() or (out/'flash_result.json').exists():raise SystemExit('Refuse repeated flash')
command=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts',
         '-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd',
         '-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}',
         '-c','gdb_port disabled; tcl_port disabled; telnet_port disabled']
action='init; set id [lindex [read_memory 0xE0042000 32 1] 0]; set flash [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($flash != 512)} {error {Target mismatch; no flash}}; program {'+paths['bin'].as_posix()+'} 0x08000000 verify reset; dump_image {'+readback.as_posix()+'} 0x08000000 '+str(artifacts['bin']['bytes'])+'; shutdown'
command+=['-c',action]
record.update(command=command,utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),timeout_s=90)
(out/'flash_command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
start=time.monotonic()
try:
    r=subprocess.run(command,capture_output=True,timeout=90)
    raw=r.stdout+b'\n--- STDERR ---\n'+r.stderr
    record['exit_code']=r.returncode
except subprocess.TimeoutExpired as e:
    raw=(e.stdout or b'')+b'\n--- STDERR ---\n'+(e.stderr or b'')
    record.update(exit_code=None,error='Flash completion NOT PROVEN; no automatic retry')
(out/'flash.log').write_bytes(raw)
record.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=time.monotonic()-start,
              log_sha256=hashlib.sha256(raw).hexdigest(),exact_readback_match=readback.exists() and readback.read_bytes()==paths['bin'].read_bytes())
if readback.exists():record['readback_sha256']=hashlib.sha256(readback.read_bytes()).hexdigest()
(out/'flash_result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(raw.decode('utf-8',errors='replace'),flush=True)
print(json.dumps(record,indent=2),flush=True)
raise SystemExit(0 if record['exit_code']==0 and record['exact_readback_match'] else 1)
