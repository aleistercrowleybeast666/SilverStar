from pathlib import Path
import datetime,json,subprocess,time,socket,hashlib

out=Path(__file__).resolve().parent
dest=out/'dap_reject';dest.mkdir(exist_ok=False)
elf=Path('.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf').resolve()
assert hashlib.sha256(elf.read_bytes()).hexdigest()=='14637f20ac2b83bc4b169b232a364d037013e494444aa23ad246070148ae4cfd'
gdb='D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gdb.exe'
address='0x080167e6'
commands=['set pagination off','set confirm off','set print elements 60','set remotetimeout 3','file '+elf.as_posix(),'target remote 127.0.0.1:3333','monitor reset halt','hbreak *'+address,'printf "DIAG_BREAKPOINT_ARMED\\n"','continue','printf "REJECTION_HIT\\n"','info registers pc lr sp r4 r6 r7','monitor reg primask','bt','info args','info locals',"p 'logger_bus.c'::s_initialized","p 'logger_bus.c'::s_accepting_records","p 'logger_bus.c'::s_boot_disabled","p 'logger_bus.c'::s_finalization_state","p 'logger_bus.c'::s_diagnostics","p 'silverstar_flight_cycle.c'::s_lifecycle_state",'p pxCurrentTCB','p *pxCurrentTCB','set $reject_payload = *(unsigned int *)($sp + 44)','printf "PAYLOAD_ADDRESS=%#x RECORD_TYPE=%u\\n", $reject_payload, $r4','x/32bx $reject_payload',"p 'system_log_policy.c'::s_streams","p 'estimator_task.c'::s_estimator.mission_running","p 'estimator_task.c'::s_snapshot.health_flags","p 'silverstar_assert.c'::s_assert_fault",'delete breakpoints','monitor resume','printf "DIAG_RESUMED\\n"','detach','quit']
script=dest/'capture.gdb';script.write_text('\n'.join(commands)+'\n',encoding='utf-8')
openocd=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port 3333; tcl_port disabled; telnet_port disabled','-c','init; set id [lindex [read_memory 0xE0042000 32 1] 0]; set size [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($size != 512)} {error {Target mismatch; stop}}']
record={'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'openocd_command':openocd,'gdb_command':[gdb,'-batch','-x',str(script)],'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'breakpoint':address,'scope':'One diagnostic reset/hardware breakpoint/halt/backtrace/resume. Excluded from latency and maximum-gap baseline. No firmware edits, flash writes or calibration commands.'}
(dest/'command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
server=None;debugger=None;session=None
with (dest/'openocd.log').open('xb') as server_log,(dest/'gdb.log').open('xb') as debugger_log,(dest/'gshc_runner.log').open('xb') as session_log:
    try:
        with socket.socket() as s:
            assert s.connect_ex(('127.0.0.1',3333))!=0,'Existing debug server; stop'
        server=subprocess.Popen(openocd,stdout=server_log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if server.poll() is not None:raise RuntimeError('OpenOCD startup failed')
            if 'Listening on port 3333' in (dest/'openocd.log').read_text(errors='replace'):break
            time.sleep(.1)
        else:raise TimeoutError('OpenOCD listening timeout')
        debugger=subprocess.Popen(record['gdb_command'],stdout=debugger_log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if 'DIAG_BREAKPOINT_ARMED' in (dest/'gdb.log').read_text(errors='replace'):break
            if debugger.poll() is not None:raise RuntimeError('GDB breakpoint setup failed')
            time.sleep(.1)
        else:raise TimeoutError('GDB arm timeout')
        session=subprocess.Popen([str(Path('.venv/Scripts/python.exe').resolve()),str(out/'gshc_session.py'),'current_diag'],stdout=session_log,stderr=subprocess.STDOUT)
        try:record['gshc_exit_code']=session.wait(timeout=80)
        except subprocess.TimeoutExpired:
            record['gshc_timeout']=True;session.terminate();session.wait(timeout=5)
        try:record['gdb_exit_code']=debugger.wait(timeout=2)
        except subprocess.TimeoutExpired:
            record['breakpoint_timeout']=True;debugger.terminate();debugger.wait(timeout=5)
    except Exception as exc:
        record['error']=repr(exc)
    finally:
        for process in [session,debugger]:
            if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        if server is not None and server.poll() is None:
            cleanup=[gdb,'-batch','-ex','target remote 127.0.0.1:3333','-ex','monitor rbp '+address,'-ex','monitor resume','-ex','detach']
            try:
                r=subprocess.run(cleanup,capture_output=True,timeout=10)
                (dest/'cleanup.log').write_bytes(r.stdout+b'\n--- STDERR ---\n'+r.stderr)
                record['cleanup_exit_code']=r.returncode
            except Exception as exc:record['cleanup_error']=repr(exc)
            server.terminate();server.wait(timeout=5)
record.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat())
text=(dest/'gdb.log').read_text(errors='replace')
record.update(rejection_hit='REJECTION_HIT' in text,resume_seen='DIAG_RESUMED' in text)
for p in dest.iterdir():
    if p.is_file() and p.name!='result.json':record.setdefault('files',{})[p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(dest/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k not in ['openocd_command','gdb_command','files']},indent=2),flush=True)
raise SystemExit(0 if record.get('rejection_hit') and record.get('resume_seen') and record.get('gshc_exit_code')==0 and record.get('cleanup_exit_code')==0 else 1)
