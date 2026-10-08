from pathlib import Path
import sys,json,subprocess,datetime,time,hashlib,re,struct
out=Path(__file__).resolve().parent
tag=sys.argv[1]
if not re.fullmatch(r'[a-zA-Z0-9_]+',tag): raise SystemExit('Unsafe diagnostic tag')
stacks='--stacks' in sys.argv
freeze=False
assert '--freeze' not in sys.argv and '--stacks' not in sys.argv, 'Live-only repeat sampling'
dest=out/('diag_'+tag)
dest.mkdir(exist_ok=False)
layout=json.loads((out/'diagnostic_layout.json').read_text())
blocks={n:o for n,o in layout.items() if not n.startswith('stack_')}
blocks['task']=dict(blocks['task'],bytes=blocks['task']['bytes']*7)
script=['init', 'set id [lindex [read_memory 0xE0042000 32 1] 0]; set flash [lindex [read_memory 0x1FFF7A22 16 1] 0]; if {($id != 0x10076413) || ($flash != 512)} {error {Target mismatch}}']
if freeze:script+=['halt 1000','echo "CORE_REGS=[get_reg -force {pc msp psp xpsr}]"']
ta=layout['timing']['address']
def bracket_read(label):
 return 'echo "'+label+'=[read_memory '+hex(layout['lifecycle']['address'])+' 8 1] [read_memory '+hex(layout['accepting']['address'])+' 8 1] [read_memory '+hex(layout['finalization']['address'])+' 8 1] [read_memory '+hex(layout['logger_bus']['address']+16)+' 32 1]"'
script+=[bracket_read('STATE_BEFORE')]
script+=['echo "TIMING_SEQ_BEFORE=[read_memory '+hex(ta)+' 32 1]"']
for name,o in blocks.items():
    script+=['echo "BLOCK_'+name+'=[read_memory '+hex(o['address'])+(' 32 ' if o['bytes']%4==0 else ' 8 ')+str(o['bytes']//(4 if o['bytes']%4==0 else 1))+']"']
    if name=='timing':script+=['echo "TIMING_SEQ_AFTER=[read_memory '+hex(ta)+' 32 1]"']
script+=[bracket_read('STATE_AFTER')]
script+=['echo "SCB_FAULT=[read_memory 0xE000ED28 32 6]"','echo "ICSR_DHCSR=[read_memory 0xE000ED04 32 1] [read_memory 0xE000EDF0 32 1]"','echo "DWT_PCSR_SAMPLE=[read_memory 0xE000101C 32 1]"']
if stacks:
    for name,o in layout.items():
        if name.startswith('stack_'):script+=['dump_image {'+(dest/(name+'.bin')).as_posix()+'} '+hex(o['address'])+' '+str(o['bytes'])]
if freeze:
 active=layout['assert_fault']['address']+next(f['offset'] for f in layout['assert_fault']['fields'] if f['name']=='active')
 script+=['if {([lindex [read_memory '+hex(active)+' 8 1] 0] == 0) && ([lindex [read_memory 0xE000ED28 32 1] 0] == 0) && ([lindex [read_memory 0xE000ED2C 32 1] 0] == 0)} {resume; echo RESUMED_AFTER_COHERENT_CAPTURE} else {echo FAULT_CAPTURE_LEFT_HALTED}']
script+=['shutdown']
command=['D:/OpenOCD-20250710-0.12.0/bin/openocd.exe','-s','D:/OpenOCD-20250710-0.12.0/share/openocd/scripts','-f','interface/cmsis-dap.cfg','-c','adapter serial 132765403520','-c','transport select swd','-f','target/stm32f4x.cfg','-c','reset_config none','-c','stm32f4x.cpu configure -event examine-end {}','-c','gdb_port disabled; tcl_port disabled; telnet_port disabled','-c','; '.join(script)]
record={'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'tag':tag,'timeout_s':20,'halt_for_coherent_postmission_capture':freeze,'no_reset_flash':True,'intrusiveness':'Postmission halt/resume only when freeze enabled. A later interval after resume is instrumentation, not flight timing.'}
(dest/'command.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
t=time.monotonic()
try:
 r=subprocess.run(command,capture_output=True,timeout=20)
 raw=r.stdout+b'\n--- STDERR ---\n'+r.stderr
 record.update(exit_code=r.returncode,timed_out=False)
except subprocess.TimeoutExpired as e:
 raw=(e.stdout or b'')+b'\n--- STDERR ---\n'+(e.stderr or b'')
 record.update(exit_code=None,timed_out=True)
record.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=round(time.monotonic()-t,3),log_sha256=hashlib.sha256(raw).hexdigest())
(dest/'openocd.log').write_bytes(raw)
text=raw.decode('utf-8',errors='replace')
decoded={}
def fields(o,blob):
 result={}
 if not o['fields']:
  return {'value':int.from_bytes(blob,'little')} if len(blob) in [1,2,4,8] else {'text':blob.split(b'\0')[0].decode('ascii',errors='replace')}
 for f in o['fields']:
  piece=blob[f['offset']:f['offset']+f['bytes']]
  if len(piece)!=f['bytes']:raise RuntimeError('Short read')
  if 'char ' in f['declaration'] and '[' in f['declaration'] and f['bytes']>1:result[f['name']]=piece.split(b'\0')[0].decode('ascii',errors='replace')
  elif '[' not in f['declaration'] and f['bytes'] in [1,2,4,8]:
   result[f['name']]=struct.unpack('<f',piece)[0] if 'float ' in f['declaration'] else int.from_bytes(piece,'little')
 return result
if record['exit_code']==0:
 for name,o in blocks.items():
  m=re.search(r'BLOCK_'+name+r'=([^\r\n]+)',text)
  if not m:raise RuntimeError('Missing returned block '+name)
  blob=b''.join(int(v,0).to_bytes(4 if o['bytes']%4==0 else 1,'little') for v in m[1].split())
  assert len(blob)==o['bytes']
  (dest/(name+'.bin')).write_bytes(blob)
  decoded[name]=[fields(layout['task'],blob[i*16:(i+1)*16]) for i in range(7)] if name=='task' else fields(o,blob)
 seq=[int(re.search(r'TIMING_SEQ_'+n+r'=([^\r\n]+)',text)[1].strip(),0) for n in ['BEFORE','AFTER']]
 decoded['timing_coherent']=seq[0]==seq[1]==decoded['timing']['sequence'] and seq[0]%2==0
 decoded['timing_sequence_brackets']=seq
 for label in ['STATE_BEFORE','STATE_AFTER']:
  m=re.search(label+r'=([^\r\n]+)',text)
  decoded[label]=[int(v,0) for v in m[1].split()]
 decoded['state_brackets_unchanged']=decoded['STATE_BEFORE']==decoded['STATE_AFTER']
 for name in ['SCB_FAULT','ICSR_DHCSR','DWT_PCSR_SAMPLE']:
  m=re.search(name+r'=([^\r\n]+)',text);decoded[name]=[int(v,0) for v in m[1].split()]
 if stacks:
  decoded['stack_fill_observations']={}
  for name,o in layout.items():
   if name.startswith('stack_'):
    blob=(dest/(name+'.bin')).read_bytes();assert len(blob)==o['bytes']
    fill=0
    for byte in blob:
     if byte!=0xa5:break
     fill+=1
    decoded['stack_fill_observations'][name[6:]]={'allocation_bytes':o['bytes'],'untouched_low_fill_bytes':fill,'equivalent_words_floor':fill//4,'raw_sha256':hashlib.sha256(blob).hexdigest(),'scope':('Halted postmission FreeRTOS 0xA5 fill prefix' if freeze else 'Live sampled FreeRTOS 0xA5 fill prefix')+'; not scheduler API snapshot or safe stack proof'}
 decoded['concurrency_scope']='Timing only valid when same even sequence around block. Other fields are individual live observations; multi-field snapshots are NOT PROVEN coherent.'
record['decoded']=decoded
(dest/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({'tag':tag,'exit_code':record['exit_code'],'elapsed_s':record['elapsed_s'],'timing_coherent':decoded.get('timing_coherent'),'timing':decoded.get('timing'),'fault':decoded.get('assert_fault'),'SCB_FAULT':decoded.get('SCB_FAULT'),'stacks':decoded.get('stack_fill_observations')},indent=2),flush=True)
if record['exit_code']!=0:raise SystemExit(1)
