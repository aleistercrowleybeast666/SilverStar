from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_radio import NativeRadioDevice_Derive


@pytest.fixture(scope='module')
def native_radio_executables(tmp_path_factory):
    compiler=shutil.which('gcc')
    if compiler is None:pytest.skip('Host GCC unavailable')
    root=Path(__file__).resolve().parents[1]
    core=root/'plugins/builtin/silverstar_core_0_1_0/payload'
    radio=root/'plugins/builtin/silverstar_device_telemetry_sx1281/payload'
    build=tmp_path_factory.mktemp('native-radio')
    source=radio/'Devices/Telemetry/SX1281/Src/sx1281_device.c'
    (build/'sx1281_device.c').write_bytes(NativeRadioDevice_Derive(source.read_bytes()))
    ports=(core/'Tests/Host/test_sx1281_device.c').read_text()
    changes={
        'uint32_t PlatformTime_Ms(void) { return s_tick_ms; }':
            'static uint32_t native_test_mask;\nuint32_t PlatformTime_Ms(void) { assert(native_test_mask==0U); return s_tick_ms; }',
        'uint64_t PlatformTime_Us(void) { return (uint64_t)s_tick_ms * 1000ULL; }':
            'uint64_t PlatformTime_Us(void) { assert(native_test_mask==0U);return (uint64_t)s_tick_ms * 1000ULL; }',
        'PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }':
            'PlatformCriticalState PlatformCritical_Enter(void) { uint32_t saved=native_test_mask;native_test_mask=1U;return saved; }',
        'void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }':
            'void PlatformCritical_Exit(PlatformCriticalState state) { native_test_mask=state; }',
    }
    for old,new in changes.items():
        assert ports.count(old)==1
        ports=ports.replace(old,new,1)
    (build/'test_sx1281_device.c').write_text('#include <assert.h>\n'+ports)
    (build/'contract.c').write_bytes((root/'tests/fixtures/sx1281_contract_host.c').read_bytes())
    includes=[build,core/'Tests/Host/Fixtures/MultiInstance/Inc',core/'Tests/Host',core/'Common/Inc',
        core/'Common/Src',core/'Interfaces/Inc',root/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc',
        radio/'Devices/Telemetry/SX1281/Inc',radio/'Middlewares/Third_Party/SX1280lib']
    common=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        *['-I'+str(p) for p in includes]]
    records=[]
    for name,files in (
        ('contract',[build/'contract.c',core/'Tests/Host/Fixtures/MultiInstance/multi_instance_resources.c']),
        ('owner',[build/'test_sx1281_device.c',build/'sx1281_device.c',core/'Common/Src/silverstar_assert.c',
                  core/'Tests/Host/Fixtures/MultiInstance/multi_instance_resources.c'])):
        command=[*common,*map(str,files),'-o',str(build/(name+'.exe'))]
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        records.append({'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        import json
        (build/'commands.json').write_text(json.dumps(records,indent=2))
        assert result.returncode==0,result.stdout+result.stderr
    return build


@pytest.mark.parametrize('scenario',['normal','reinit','deactivate'])
def test_real_driver_timestamps_are_sampled_before_irq_locks(native_radio_executables,scenario):
    result=subprocess.run([str(native_radio_executables/'contract.exe'),scenario],capture_output=True,text=True,timeout=15)
    (native_radio_executables/(scenario+'.log')).write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert '0 failures' in result.stdout


def test_actual_owner_diagnostics_controls_and_tx_rx_loops(native_radio_executables):
    result=subprocess.run([str(native_radio_executables/'owner.exe')],capture_output=True,text=True,timeout=15)
    (native_radio_executables/'owner.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert '0 failures' in result.stdout
