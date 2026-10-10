from pathlib import Path
root=Path('D:/python_software/SilverStar/.work/ccdi')
p=root/'apps/SCG/tests/test_native_runtime.py'
s=p.read_text(encoding='utf-8')
old='def test_native_lifecycle_prevents_early_and_faulted_publication(tmp_path, scenario):\n'
new='''@pytest.mark.parametrize('transport_fault', [False, True])
def test_native_lifecycle_prevents_early_and_faulted_publication(tmp_path, scenario, transport_fault):
    _ExerciseLifecycle(tmp_path,scenario,transport_fault=transport_fault)


@pytest.mark.parametrize('scenario',['transport-before-init','transport-during-init',
    'transport-before-process','transport-during-process'])
def test_stored_transport_fault_cancels_successful_initialization_and_publication(tmp_path,scenario):
    _ExerciseLifecycle(tmp_path,scenario,transport_fault=True)


def _ExerciseLifecycle(tmp_path, scenario, *, transport_fault=False):
'''
assert s.count(old)==1;s=s.replace(old,new,1)
s=s.replace('NativeRuntime_FilesRender().items()', 'NativeRuntime_FilesRender(transport_fault=transport_fault).items()',1)
anchor="    (tmp_path/'test.c').write_text(harness,encoding='utf-8')"
injection='''    if transport_fault:
        harness=harness.replace('static uint8_t radio_not_initialized,radio_unverified;',
            'static uint8_t radio_not_initialized,radio_unverified;\\nstatic uint8_t transport_bad_init,transport_bad_process;')
        harness=harness.replace('    return bridge_init;',
            '    if (transport_bad_init!=0U) { NativeRuntime_TransportFaultRecord(); }\\n    return bridge_init;')
        harness=harness.replace('    if (clock_bad_process!=0U)',
            '    if (transport_bad_process!=0U) { NativeRuntime_TransportFaultRecord(); }\\n    if (clock_bad_process!=0U)')
        harness=harness.replace('    NativeRuntimeResult init=NativeRuntime_Init();',
            '    if (strcmp(argv[1],"transport-before-init")==0) { NativeRuntime_TransportFaultRecord(); }\\n'
            '    if (strcmp(argv[1],"transport-during-init")==0) { transport_bad_init=1U; }\\n'
            '    NativeRuntimeResult init=NativeRuntime_Init();\\n'
            '    if (strncmp(argv[1],"transport-",10U)==0 && strstr(argv[1],"init")!=NULL) { assert(init==NativeRuntimeResult_PcFailure); }')
        harness=harness.replace('    NativeRuntimeResult result=NativeRuntime_Process();',
            '    if (strcmp(argv[1],"transport-before-process")==0) { NativeRuntime_TransportFaultRecord();assert(NativeRuntime_ReadyGet()==0U); }\\n'
            '    if (strcmp(argv[1],"transport-during-process")==0) { transport_bad_process=1U; }\\n'
            '    NativeRuntimeResult result=NativeRuntime_Process();\\n'
            '    if (strncmp(argv[1],"transport-",10U)==0)\\n'
            '    { assert(result==NativeRuntimeResult_PcFailure && NativeRuntime_ReadyGet()==0U);\\n'
            '      assert(retired==1U && quiesced==1U && pc_reset==1U && bridge_reset==1U);\\n'
            '      uint32_t before=process_calls;assert(NativeRuntime_Process()==result && process_calls==before);return 0; }')
'''
assert s.count(anchor)==1;s=s.replace(anchor,injection+anchor,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Added ordinary stored-fault lifecycle regression; no USB packets or EP0 exercised')
