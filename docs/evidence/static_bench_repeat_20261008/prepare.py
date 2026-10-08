from pathlib import Path
import json, shutil, subprocess, re, hashlib
out=Path(__file__).resolve().parent
repo=out.parents[1]
prior=repo/'docs/evidence/static_bench_authorized_20261008'
for name in ['read_diagnostics.py','diagnostic_layout.json']:
    target=out/name
    if target.exists():raise SystemExit('Refuse overwrite: '+name)
    target.write_bytes((prior/name).read_bytes())
layout=json.loads((out/'diagnostic_layout.json').read_text(encoding='utf-8'))
layout={k:v for k,v in layout.items() if not k.startswith('stack_')}
extra={'accepting':"'logger_bus.c'::s_accepting_records",'logger_initialized':"'logger_bus.c'::s_initialized",'boot_disabled':"'logger_bus.c'::s_boot_disabled",'finalization':"'logger_bus.c'::s_finalization_state",'finalization_deadline':"'logger_bus.c'::s_finalization_deadline_us"}
elf=repo/'.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf'
commands=['set pagination off','file '+elf.as_posix()]
for k,e in extra.items():commands+=['printf "'+k+'=%u,%u\\n", (unsigned)&('+e+'), (unsigned)sizeof('+e+')']
commands+=['quit']
(out/'layout_extra.commands').write_text('\n'.join(commands)+'\n',encoding='utf-8')
r=subprocess.run(['D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gdb.exe','-nx','-batch','-x',str(out/'layout_extra.commands')],capture_output=True,timeout=20)
(out/'layout_extra.log').write_bytes(r.stdout+b'\n'+r.stderr)
assert r.returncode==0
for k,e in extra.items():
    m=re.search(k+r'=(\d+),(\d+)',r.stdout.decode('ascii',errors='replace'))
    assert m,k
    layout[k]={'expression':e,'address':int(m[1]),'bytes':int(m[2]),'fields':[]}
(out/'diagnostic_layout.json').write_text(json.dumps(layout,indent=2),encoding='utf-8')
t=(out/'read_diagnostics.py').read_text(encoding='utf-8')
# No halt or stack dump options allowed in this repeat recorder.
t=t.replace("freeze='--freeze' in sys.argv","freeze=False\nassert '--freeze' not in sys.argv and '--stacks' not in sys.argv, 'Live-only repeat sampling'")
(out/'read_diagnostics.py').write_text(t,encoding='utf-8')
plan={'source_commit':'cac7bd29bf6f6aec5297715ea14893b4b7684953','documents_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip(),'probe':'132765403520','port':'COM3','condition':'User confirms stationary +Y and all actuators disconnected, TF inserted. No physical changes requested.','flash_count':0,'start_max':1,'reset_max':1,'reset_condition':'Only if exact flashed BIN matches, current LANDED, file closed/finalized, no CPU/assert fault. LANDED START locked by current source.','samples':['pre-reset identity and finalized state','preSTART after authoritative calibration/alignment','active after actual flight transition','first received LANDING (may already be draining; record observed phase)','LANDING receive +1.4s','LANDING receive +4s or finite final deadline'],'sampling':'Live SWD reads only, no halt, no firmware or parameter mutation; all multi-field live snapshots have coherence limits. Counters are boot cumulative and reset once, compare phase deltas.','elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest()}
(out/'sampling_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
print(json.dumps({'prepared':True,'extra_layout':{k:layout[k] for k in extra}},indent=2))
