from pathlib import Path
root=Path('D:/python_software/SilverStar/.work/ccdi')
p=root/'apps/SCG/src/silverstar_fccg/generator/native_runtime.py'
s=p.read_text(encoding='utf-8')
anchor="        runtime=runtime.replace('    /* Radio timeouts and PC transport errors',"
insert="""        runtime=runtime.replace('    s_state = NativeRuntimeState_Ready;',
            '    if (s_transport_fault != 0U) { return NativeRuntime_Abort(NativeRuntimeResult_PcFailure); }\\n'
            '    s_state = NativeRuntimeState_Ready;')
"""
assert s.count(anchor)==1;s=s.replace(anchor,insert+anchor,1)
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'apps/SCG/tools/validation/native_classic_cdc_compile.py'
s=p.read_text(encoding='utf-8')
old="for name in ('check_ground','check_native_ground')]"
new="for name in ('check_ground','check_native_ground','check_native_probe')]"
assert s.count(old)==1;s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Initialization cannot return success after a stored transport fault; runtime snapshot includes shared probe gate')
