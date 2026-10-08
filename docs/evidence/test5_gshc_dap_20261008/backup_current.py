from pathlib import Path
import datetime, hashlib, json, subprocess, time

out = Path(__file__).resolve().parent
assert not (out / 'backup_result.json').exists(), 'Preserve prior attempt'
layout = json.loads(Path('docs/evidence/static_bench_repeat_20261008/diagnostic_layout.json').read_text(encoding='utf-8'))
script = [
    'init',
    'set id [lindex [read_memory 0xE0042000 32 1] 0]; set size [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($size != 512)} {error {Target mismatch; stop}}',
    'echo "TARGET_ID=$id FLASH_KIB=$size"',
    'echo "CORE_BEFORE=[read_memory 0xE000EDF0 32 1]"',
]
for name in ['lifecycle','accepting','finalization','logger_bus','logger_runtime','assert_fault']:
    item = layout[name]
    script.append('echo "STATE_'+name+'=[read_memory '+hex(item['address'])+' 8 '+str(item['bytes'])+']"')
for name in ['current_fullflash.bin','current_fullflash_confirm.bin']:
    script.append('dump_image {'+(out/name).as_posix()+'} 0x08000000 524288')
script += ['echo "CORE_AFTER=[read_memory 0xE000EDF0 32 1]"','shutdown']
command = ['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port disabled; tcl_port disabled; telnet_port disabled','-c','; '.join(script)]
record = {'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'timeout_s':60,'flash':False,'halt':False,'reset':False,'scope':'Flight main flash double read plus live RAM; no option bytes, mass erase, Ground or calibration commands'}
(out/'backup_command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
begin=time.monotonic()
try:
    result=subprocess.run(command,capture_output=True,timeout=60)
    raw=result.stdout+b'\n--- STDERR ---\n'+result.stderr
    record['exit_code']=result.returncode
except subprocess.TimeoutExpired as exc:
    raw=(exc.stdout or b'')+b'\n--- STDERR ---\n'+(exc.stderr or b'')
    record.update(exit_code=None,timed_out=True)
(out/'backup_openocd.log').write_bytes(raw)
record.update(elapsed_s=time.monotonic()-begin,utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),log_sha256=hashlib.sha256(raw).hexdigest())
if record['exit_code']==0:
    first=(out/'current_fullflash.bin').read_bytes();second=(out/'current_fullflash_confirm.bin').read_bytes()
    assert len(first)==len(second)==524288 and first==second, 'Backup mismatch'
    candidate=Path('.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin').read_bytes()
    record.update(double_read_match=True,fullflash_sha256=hashlib.sha256(first).hexdigest(),current_candidate_prefix_match=first[:len(candidate)]==candidate,candidate_bytes=len(candidate),candidate_sha256=hashlib.sha256(candidate).hexdigest())
    record['regions']={}
    for name,start,length in [('application_sector_extent',0,393216),('untouched_sector7',393216,131072)]:
        data=first[start:start+length];(out/(name+'.bin')).write_bytes(data)
        record['regions'][name]={'start':hex(0x08000000+start),'bytes':length,'sha256':hashlib.sha256(data).hexdigest()}
(out/'backup_result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='command'},indent=2),flush=True)
raise SystemExit(0 if record['exit_code']==0 and record.get('current_candidate_prefix_match') else 1)
