from pathlib import Path
import subprocess,json,re
out=Path(__file__).resolve().parent
repo=out.parents[1]
elf=repo/'.work/bench08b_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf'
objects={'timing':'s_estimator_task_timing','navigation':'s_published_snapshot','task':'s_tasks[0]','assert_fault':'s_assert_fault','radio_stats':"'sx1281_device.c'::s_contexts[0].stats",'radio_bus':'s_bus_status[0]','health':"'system_health.c'::s_health"}
objects['alignment_retry']="'flight_task.c'::s_alignment_log"
objects.update({'lifecycle':'s_lifecycle_state','logger':"'logger_task.c'::s_diagnostics",'logger_runtime':"'logger_task.c'::s_logger",'logger_bus':"'logger_bus.c'::s_diagnostics",'logger_request':"'logger_bus.c'::s_request",'storage':"'storage_service.c'::s_health",'file_open':"'storage_service.c'::s_file_open",'mission_id':"'storage_service.c'::s_mission_id",'sink':"'log_sink_service.c'::s_sink.health",'file_path':"'log_sink_service.c'::s_sink.path",'first_mount':"'storage_service.c'::s_first_mount_fresult",'normal_queue':"'logger_bus.c'::s_logger_queue",'estimator_queue':"'logger_bus.c'::s_estimator_logger_queue"})
objects.update({'stack_'+name:'s_'+symbol+'_stack' for name,symbol in [('Device','device'),('INS','ins'),('Estimator','estimator'),('Flight','flight'),('Logger','logger'),('Serial','serial'),('Telemetry','telemetry')]})
commands=['set pagination off','set print pretty on','file '+elf.as_posix()]
for name,expr in objects.items():
    commands += ['echo LAYOUT_'+name+'\\n','printf "ADDR=0x%x SIZE=%u\\n",(unsigned)&('+expr+'),(unsigned)sizeof('+expr+')','ptype /o '+expr]
commands+=['quit']
(out/'gdb_layout.commands').write_text('\n'.join(commands)+'\n',encoding='utf-8')
r=subprocess.run(['D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gdb.exe','-nx','-batch','-x',str(out/'gdb_layout.commands')],capture_output=True,timeout=20)
text=r.stdout.decode('utf-8',errors='replace')
(out/'gdb_layout.log').write_bytes(r.stdout+b'\n--- STDERR ---\n'+r.stderr)
result={}
for chunk in re.split(r'LAYOUT_',text)[1:]:
    name=chunk.splitlines()[0]
    addr=re.search(r'ADDR=(0x[0-9a-fA-F]+) SIZE=(\d+)',chunk)
    if not addr: raise RuntimeError('Missing layout: '+chunk)
    fields=[]
    for offset,size,decl in re.findall(r'/\*\s*(\d+)\s*\|\s*(\d+)\s*\*/\s*([^\n;]+);',chunk):
        match=re.search(r'([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]+\])?$',decl)
        if match: fields.append({'name':match[1],'offset':int(offset),'bytes':int(size),'declaration':decl.strip()})
    result[name]={'expression':objects[name],'address':int(addr[1],16),'bytes':int(addr[2]),'fields':fields}
assert result['timing']['bytes']==80 and result['task']['bytes']==16
(out/'diagnostic_layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({n:{'address':hex(o['address']),'bytes':o['bytes'],'fields':len(o['fields'])} for n,o in result.items()},indent=2))
