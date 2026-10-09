"""Prove that UART session invalidation and TX ownership tests reject regressions."""
from pathlib import Path
import argparse,json,subprocess
from c071_uart_host import HEADER,TRANSPORT,SESSION

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('target',type=Path)
parser.add_argument('--host-cc',default='gcc')
args=parser.parse_args();root=args.target.resolve()
graph=json.loads((root/'Generated/ground_source_graph.json').read_text(encoding='utf-8'))
if graph.get('pc_interface')!='uart':raise ValueError('requires the UART alternative')
source=(root/'Generated/Src/pc_byte_stream.c').read_text(encoding='utf-8')
build=root/'build/c071-uart-negative';build.mkdir(parents=True,exist_ok=True)
(build/'main.h').write_text(HEADER,encoding='utf-8')
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-Wshadow','-Wvla']
flags += ['-I'+str(p) for p in (build,root/'Ground/Core/Inc',root/'Ground/Protocol/Inc',root/'Common/Inc')]
common=[root/'Common/Src/silverstar_assert.c']
bridge=[root/'Ground/Core/Src/ground_bridge.c',root/'Ground/Protocol/Src/gsp_min_protocol.c',root/'Ground/Protocol/Src/protocol_crc16.c']
callback='''void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart != &huart2) { return; }
    s_rx_armed = 0U;
    PcByteStream_OnUsbReset();
}'''
if source.count(callback)!=1:raise ValueError('unreviewed error callback')
busy='if ((s_rx_armed == 0U) || (s_tx_busy != 0U))'
if source.count(busy)!=1:raise ValueError('unreviewed TX ownership guard')
cases=[('lost-error-session',source.replace(callback,callback.replace('    PcByteStream_OnUsbReset();\n','')),SESSION,bridge,['read-reset'],'forwarded==0'),
       ('released-tx-too-early',source.replace(busy,'if (s_rx_armed == 0U)'),TRANSPORT,[],[],'tx_calls==calls')]
results=[]
for name,mutant,harness,extra,argv,predicate in cases:
    c=build/(name+'.c');c.write_text(mutant,encoding='utf-8')
    h=build/(name+'-test.c');h.write_text(harness,encoding='utf-8')
    exe=build/(name+'.exe')
    command=[args.host_cc,*flags,str(c),*map(str,common+extra),str(h),'-o',str(exe)]
    print('COMMAND',command,flush=True);subprocess.run(command,check=True)
    result=subprocess.run([str(exe),*argv],capture_output=True,text=True)
    if result.returncode==0 or predicate not in result.stderr:
        raise ValueError('negative did not fail at its expected safety predicate: '+name+' '+result.stderr)
    results.append({'case':name,'exit':result.returncode,'expected_predicate':predicate,'stderr':result.stderr})
    print('PASS regression rejected:',name,'exit',result.returncode,flush=True)
(build/'negative-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
