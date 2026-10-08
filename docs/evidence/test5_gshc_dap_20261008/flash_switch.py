from pathlib import Path
import datetime,hashlib,json,subprocess,sys,time

out=Path(__file__).resolve().parent
stage=sys.argv[1]
assert stage in ['test5','current','restore']
dest=out/('flash_'+stage);dest.mkdir(exist_ok=False)
backup=json.loads((out/'backup_result.json').read_text(encoding='utf-8'))
assert backup['double_read_match'] and backup['current_candidate_prefix_match']
if stage=='test5':
    image=Path('D:/stm32_project/SS_0_5_TEST_5/Flight_Controller/build/FCCG/SilverStar_F407/EIDE/Release/SS_0_5_TEST_5.hex')
    assert hashlib.sha256(image.read_bytes()).hexdigest()=='95f5c58e0c8e99b6d3a181a6eef26e0a157c51480a6f6b4ebd258b4ba35f2b4d'
    expected={};upper=0
    for line in image.read_text().splitlines():
        row=bytes.fromhex(line[1:]);assert sum(row)%256==0
        count=row[0];address=int.from_bytes(row[1:3],'big');kind=row[3];data=row[4:4+count]
        if kind==4:upper=int.from_bytes(data,'big')<<16
        if kind==0:
            for i,v in enumerate(data):expected[upper+address+i]=v
    assert min(expected)==0x08000000 and max(expected)<0x08060000
    end=max(expected)+1
    program='program {'+image.as_posix()+'} verify reset'
else:
    image=Path('.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin').resolve()
    payload=image.read_bytes();assert hashlib.sha256(payload).hexdigest()=='5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3'
    expected=dict(enumerate(payload,0x08000000));end=0x08000000+len(payload)
    program='program {'+image.as_posix()+'} 0x08000000 verify reset'
script=['init','set id [lindex [read_memory 0xE0042000 32 1] 0]; set size [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($size != 512)} {error {Target mismatch; no flash}}',program,'dump_image {'+(dest/'application_readback.bin').as_posix()+'} 0x08000000 '+str(end-0x08000000),'dump_image {'+(dest/'untouched_sector7.bin').as_posix()+'} 0x08060000 131072','shutdown']
command=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port disabled; tcl_port disabled; telnet_port disabled','-c','; '.join(script)]
record={'stage':stage,'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'image':str(image),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'expected_bytes':len(expected),'span_bytes':end-0x08000000,'ground_flash':False,'mass_erase':False,'option_bytes':False,'timeout_s':60}
(dest/'command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
start=time.monotonic()
try:
    r=subprocess.run(command,capture_output=True,timeout=60);raw=r.stdout+b'\n--- STDERR ---\n'+r.stderr;record['exit_code']=r.returncode
except subprocess.TimeoutExpired as e:
    raw=(e.stdout or b'')+b'\n--- STDERR ---\n'+(e.stderr or b'');record.update(exit_code=None,timed_out=True)
(dest/'openocd.log').write_bytes(raw)
record.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=time.monotonic()-start,log_sha256=hashlib.sha256(raw).hexdigest())
if record['exit_code']==0:
    data=(dest/'application_readback.bin').read_bytes();tail=(dest/'untouched_sector7.bin').read_bytes()
    record.update(readback_verified=all(data[a-0x08000000]==v for a,v in expected.items()),readback_sha256=hashlib.sha256(data).hexdigest(),untouched_sector7_verified=tail==(out/'untouched_sector7.bin').read_bytes())
(dest/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='command'},indent=2),flush=True)
raise SystemExit(0 if record['exit_code']==0 and record.get('readback_verified') and record.get('untouched_sector7_verified') else 1)
