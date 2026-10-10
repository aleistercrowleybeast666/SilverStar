"""Run only the final generated timer Host fixtures; never target firmware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess

ROOT=Path('D:/python_software/SilverStar')
TEMP=Path('C:/Users/chdxm/AppData/Local/Temp/sscdc-native-final13d')
OUT=ROOT/'.work/ccdi-timer-host-fault13d.json'
assert not OUT.exists()
assert (ROOT/'.work/ccdi-native-final13d.exit').read_text().strip()=='0'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
for original in sorted(TEMP.rglob('original.exe')):
    directory=original.parent
    if not directory.name.startswith('test_actual_timer_init_irq_pre_'):continue
    logs=list(directory.glob('original-*.log'));assert len(logs)==1
    scenario=logs[0].stem.removeprefix('original-')
    assert scenario in ('div1','div2','bad-clock','bad-priority','base-fail','start-fail')
    for label in ('original','derived'):
        exe=directory/(label+'.exe');source=directory/(label+'.c')
        assert 'TimerRegisters timer_registers;' in source.read_text()
        command=[str(exe),scenario];started=datetime.now(timezone.utc).isoformat()
        run=subprocess.run(command,capture_output=True,text=True,timeout=15)
        expected_ok=label=='derived' or scenario in ('base-fail','start-fail')
        assert (run.returncode==0)==expected_ok,(command,run.returncode)
        records.append({'scope':'Host MMIO/HAL mocks, actual native function bodies',
            'command':command,'started_utc':started,'exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr,
            'expected':'success under unchanged safety expectations' if expected_ok else 'original missing IRQ/clock/priority contract assertion failure',
            'executable_sha256':sha(exe),'source':str(source),'source_sha256':sha(source),
            'compile_record':str(directory/(label+'-command.json'))})
ports=list(TEMP.rglob('timer-port.exe'));assert len(ports)==1
exe=ports[0];source=exe.with_suffix('.c')
assert 'TimerRegisters timer_registers={' in source.read_text()
run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15);assert run.returncode==0
records.append({'scope':'Host actual TIM1 port with fake MMIO, masking, pending update, stopped/misconfigured timer and unchanged output faults',
    'command':[str(exe)],'exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr,
    'executable_sha256':sha(exe),'source':str(source),'source_sha256':sha(source),
    'compile_record':str(exe.parent/'timer-port-command.json')})
assert len(records)==13
OUT.write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Dedicated Host fault execution, not hardware or Ground Host acceptance',
    'runs':records},indent=2))
print(json.dumps({'output':str(OUT),'runs':len(records),'expected_original_failures':sum(r['exit']!=0 for r in records)}))
