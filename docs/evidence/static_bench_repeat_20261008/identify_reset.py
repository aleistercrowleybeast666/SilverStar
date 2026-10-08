from pathlib import Path
import json, subprocess, hashlib, time, datetime, sys
from serial.tools import list_ports
out=Path(__file__).resolve().parent
repo=out.parents[1]
mode=sys.argv[1]
assert mode in ['identify','reset']
result=out/(mode+'_result.json')
assert not result.exists(),'No repeated identify/reset'
ports=[p for p in list_ports.comports() if p.device in ['COM3','COM9']]
com=[p for p in ports if p.device=='COM3']
dap=[p for p in ports if p.device=='COM9']
assert len(com)==len(dap)==1
assert (com[0].vid,com[0].pid,com[0].location)==(0x1a86,0x7523,'1-1')
assert (dap[0].vid,dap[0].pid,dap[0].serial_number)==(0xfaed,0x4870,'132765403520')
ports_record=[{'device':p.device,'vid':p.vid,'pid':p.pid,'location':p.location,'serial':p.serial_number} for p in ports]
candidate=repo/'.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(candidate)=='5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3'
base=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port disabled; tcl_port disabled; telnet_port disabled']
guard='init; set id [lindex [read_memory 0xE0042000 32 1] 0]; set flash [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($flash != 512)} {error {Target mismatch}}; '
if mode=='identify':
    dump=out/'current_image_readback.bin'
    assert not dump.exists()
    action='dump_image {'+dump.as_posix()+'} 0x08000000 '+str(candidate.stat().st_size)+'; shutdown'
else:
    i=json.loads((out/'identify_result.json').read_text(encoding='utf-8'))
    d=json.loads((out/'diag_pre_reset/result.json').read_text(encoding='utf-8'))['decoded']
    assert i['exit_code']==0 and i['exact_readback_match']
    assert d['lifecycle']['value']==6 and d['file_open']['value']==0
    assert d['logger_runtime']['session_finalized']==1 and d['logger_runtime']['session_active']==0 and d['logger_runtime']['aggregate_length']==0
    assert d['assert_fault']['active']==0 and d['SCB_FAULT'][:2]==[0,0]
    import serial
    serial_guard=serial.Serial(port=None,baudrate=230400,timeout=.05,write_timeout=.5,rtscts=False,dsrdtr=False)
    serial_guard.dtr=serial_guard.rts=False
    serial_guard.port='COM3'
    serial_guard.open()
    serial_guard.close()
    action='reset run; shutdown'
args=base+['-c',guard+action]
rec={'mode':mode,'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':args,'ports':ports_record,'timeout_s':45,'flashed':False,'reset_count':int(mode=='reset'),'reason':'LANDED cannot admit another START; one reset starts new independent static lifecycle' if mode=='reset' else 'Read exact current main image without halt/reset'}
(out/(mode+'_command.json')).write_text(json.dumps(rec,indent=2),encoding='utf-8')
t=time.monotonic()
r=subprocess.run(args,capture_output=True,timeout=45)
raw=r.stdout+b'\n--- STDERR ---\n'+r.stderr
(out/(mode+'.log')).write_bytes(raw)
rec.update(exit_code=r.returncode,utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=round(time.monotonic()-t,3),log_sha256=hashlib.sha256(raw).hexdigest())
if mode=='identify':rec.update(readback_sha256=sha(dump),exact_readback_match=dump.read_bytes()==candidate.read_bytes())
result.write_text(json.dumps(rec,indent=2),encoding='utf-8')
print(json.dumps(rec,indent=2))
raise SystemExit(0 if r.returncode==0 and (mode=='reset' or rec['exact_readback_match']) else 1)
