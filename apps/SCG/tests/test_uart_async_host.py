"""Compile the real F4 platform source; HAL doubles record bytes and inject failures."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.fixture(scope='module')
def uart_async_executable(tmp_path_factory):
    gcc=shutil.which('gcc')
    if not gcc: pytest.skip('Host GCC unavailable')
    root=Path(__file__).resolve().parents[1]
    builtin=root/'plugins/builtin'
    core=builtin/'silverstar_core_0_1_0/payload'
    f4=builtin/'silverstar_mcu_family_stm32f4/payload/Platform/STM32F4'
    source=Path(os.environ.get('SILVERSTAR_UART_TEST_SOURCE',str(f4/'Src')))
    exe=tmp_path_factory.mktemp('uart-async')/'async.exe'
    command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic']
    for p in [root/'tests/fixtures/uart_recovery',source,f4/'Inc',builtin/'silverstar_platform_api/payload/Platform/Inc',core/'Common/Inc']:
        command+=['-I',str(p)]
    command += [str(root/'tests/fixtures/uart_async_host.c'),str(core/'Common/Src/common_ringbuf.c'),str(core/'Common/Src/silverstar_assert.c'),'-o',str(exe)]
    r=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=60)
    assert r.returncode==0,r.stdout+r.stderr
    return exe

@pytest.mark.parametrize('slot',range(6))
def test_uart_async_real_backend(uart_async_executable,slot):
    r=subprocess.run([str(uart_async_executable),str(slot)],cwd=uart_async_executable.parent,capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr


def test_sensor_commands_reach_real_f4_hal(tmp_path,workspace_root):
    from silverstar_fccg.app.service import FccgService
    gcc=shutil.which('gcc')
    if not gcc: pytest.skip('Host GCC unavailable')
    configured=os.environ.get('SILVERSTAR_UART_TEST_PROJECT')
    if configured:
        project=Path(configured)
    else:
        service=FccgService(workspace_root)
        project=tmp_path/'sensor-project'
        service.Project_Save(service.ReferenceProject_Create('UartSensorTx'),project,confirm_dangerous=True)
    builtin=workspace_root/'plugins/builtin'
    core=builtin/'silverstar_core_0_1_0/payload'
    f4=builtin/'silverstar_mcu_family_stm32f4/payload/Platform/STM32F4'
    source=Path(os.environ.get('SILVERSTAR_UART_TEST_SOURCE',str(project/'Platform/STM32F4/Src')))
    exe=tmp_path/'sensor-tx.exe'
    command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-DUART_SENSOR_TEST','-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
    for path in [project/'Generated/Inc',workspace_root/'tests/fixtures/uart_recovery',source,f4/'Inc',project/'Platform/Inc',project/'Common/Inc',project/'Generated/Inc',project/'System/Inc',project/'Interfaces/Inc',project/'Devices/IMU/JY901B/Inc',project/'Devices/IMU/JY901B/Adapter/Inc',project/'Devices/GNSS/NEO_M9N/Inc']:
        command+=['-I',str(path)]
    command+=[str(workspace_root/'tests/fixtures/uart_async_host.c'),str(core/'Common/Src/common_ringbuf.c'),str(core/'Common/Src/silverstar_assert.c'),str(project/'Devices/IMU/JY901B/Src/jy901b_device.c'),str(project/'Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c'),str(project/'Generated/Src/project_resources.c'),'-lm','-o',str(exe)]
    r=subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=60)
    assert r.returncode==0,r.stdout+r.stderr
    r=subprocess.run([str(exe)],cwd=project,capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr
from types import SimpleNamespace

@pytest.mark.parametrize('custom',[False,True])
def test_uart_buffer_sizes_follow_logical_bindings(monkeypatch,custom):
    import silverstar_fccg.generator.render as render
    model=SimpleNamespace(hardware=SimpleNamespace(mode='custom' if custom else 'board'),board='board',device_instances=[SimpleNamespace(instance_id='console0',plugin='silverstar.device.console.uart')])
    assignment=SimpleNamespace(component_id='console0',provision=SimpleNamespace(kind='uart',resource_id='console'))
    resolution=SimpleNamespace(assignments=[assignment])
    entries={'uarts':[{'id':'console','logical_index':1,'handle':'huart6'}, {'id':'sensor','logical_index':5,'handle':'huart4'}]}
    monkeypatch.setattr(render,'ResourceAssignments_Resolve',lambda *a,**k:resolution)
    monkeypatch.setattr(render,'_CustomPlatformResources_Get',lambda *a:entries)
    monkeypatch.setattr(render,'_BoardPlatformResources_Get',lambda *a:entries)
    catalog=SimpleNamespace(Component_Get=lambda *a:None)
    text=render._PlatformUartConfigDefines_Render(model,catalog)
    assert '#define PROJECT_PLATFORM_UART_2_TX_RING_SIZE 2048U' in text
    assert '#define PROJECT_PLATFORM_UART_2_TX_PRIORITY_SIZE 1024U' in text
    assert '#define PROJECT_PLATFORM_UART_6_TX_RING_SIZE 192U' in text
    assert '#define PROJECT_PLATFORM_UART_6_TX_PRIORITY_SIZE 192U' in text
    assert '#define PROJECT_PLATFORM_UART_1_TX_RING_SIZE 1U' in text
