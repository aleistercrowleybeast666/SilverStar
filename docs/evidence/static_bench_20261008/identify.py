from pathlib import Path
import subprocess, json, hashlib, datetime, time
out=Path(__file__).resolve().parent
dest=out/'current_F407_before_test_fullflash.bin'
if dest.exists() or (out/'identify_result.json').exists():
    raise SystemExit('Refuse duplicate target inspection evidence')
command=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port disabled; tcl_port disabled; telnet_port disabled']
action='init; set actual_id [lindex [read_memory 0xE0042000 32 1] 0]; set actual_flash [lindex [read_memory 0x1FFF7A22 16 1] 0]; echo [format "TARGET_ID=0x%08x" $actual_id]; echo [format "FLASH_KIB=%u" $actual_flash]; if {($actual_id != 0x10076413) || ($actual_flash != 512)} {error "Target identity mismatch"}; dump_image {'+dest.as_posix()+'} 0x08000000 0x80000; shutdown'
command+=['-c',action]
record={'command':command,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_head':'0a2ceb54d5b536997b1464f7c740fa3349f5d595','probe':'132765403520','timeout_s':60,'no_halt_reset_flash_protection_change':True}
(out/'identify_command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
t=time.monotonic()
try:
    r=subprocess.run(command,capture_output=True,timeout=60)
    log=r.stdout+b'\n--- STDERR ---\n'+r.stderr
    record.update(exit_code=r.returncode,timed_out=False)
except subprocess.TimeoutExpired as exc:
    log=(exc.stdout or b'')+b'\n--- STDERR ---\n'+(exc.stderr or b'')
    record.update(exit_code=None,timed_out=True)
record.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=time.monotonic()-t,log_sha256=hashlib.sha256(log).hexdigest())
(out/'identify.log').write_bytes(log)
if dest.exists():
    raw=dest.read_bytes()
    record.update(flash_bytes=len(raw),flash_sha256=hashlib.sha256(raw).hexdigest(),known_image_matches={})
    for name,p in [('28b168f',Path('D:/python_software/SilverStar/.work/Q2F407_7fa06c4/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin')),('recovery_20261004',Path('D:/stm32_project/SS_0_5_RELEASE_KF6_RECOVERY/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin'))]:
        if p.exists():
            data=p.read_bytes()
            record['known_image_matches'][name]={'bin':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'exact_flash_prefix_match':raw[:len(data)]==data}
(out/'identify_result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(log.decode('utf-8',errors='replace'))
print(json.dumps(record,indent=2))
raise SystemExit(0 if record['exit_code']==0 and record.get('flash_bytes')==524288 else 1)
