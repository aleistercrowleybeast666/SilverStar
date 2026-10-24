from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from silverstar_fccg.generator.maintenance_uart import (
    MaintenanceUart_Profile, MaintenanceUart_RuntimeGuard, CHECKER_SOURCE,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Create, ProjectDescriptor_Validate


def test_real_reference_uart_declaration_and_legacy_descriptor(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    profile = MaintenanceUart_Profile(model, builtin_catalog)
    assert profile['baudrate'] == 230400 and profile['block_size'] == 512
    assert profile['handle'] == 'huart3' and profile['peripheral'] == 'USART3'
    declaration = {k: v for k, v in profile.items() if k not in ('handle', 'peripheral')}
    old = ProjectDescriptor_Create('UART_test', 'STM32F407VET6', maintenance=dict(
        component='silverstar.protocol.maintenance.serial_0_0', package_version='0.1.1', profile='maintenance.serial.0_1'))
    ProjectDescriptor_Validate(old)
    new = deepcopy(old)
    new['maintenance']['uart'] = declaration
    ProjectDescriptor_Validate(new)
    new['maintenance']['uart']['block_size'] = 1024
    with pytest.raises(ValueError):
        ProjectDescriptor_Validate(new)


@pytest.mark.parametrize('baud', [1200, 123457, 230400, 250000, 460800, 921600, 1000000, 2000000])
def test_profile_comes_from_resolved_resource_not_ground_target(builtin_catalog, monkeypatch, baud):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    assignment = SimpleNamespace(requirement=SimpleNamespace(binding_macro='PROJECT_RESOURCE_CONSOLE_UART'),
        provision=SimpleNamespace(metadata=dict(baud_rate=baud, word_length=8, parity='none', stop_bits=1,
                                               handle='huart3', peripheral='USART3')))
    monkeypatch.setattr('silverstar_fccg.generator.maintenance_uart.ResourceAssignments_Resolve',
                        lambda *_: SimpleNamespace(valid=True, errors=(), assignments=[assignment]))
    profile = MaintenanceUart_Profile(model, builtin_catalog)
    assert profile['baudrate'] == baud
    assert profile['minimum_wire_ms'] == (8210000 + baud - 1) // baud
    assert profile['block_deadline_ms'] == 30000 and profile['block_size'] == 512


def test_actual_output_checker_rejects_ioc_or_c_mismatch_without_rewriting(tmp_path):
    (tmp_path / 'Tools').mkdir()
    (tmp_path / 'Core').mkdir()
    profile = dict(handle='huart3', peripheral='USART3', baudrate=460800)
    (tmp_path / 'Tools/maintenance_uart.json').write_text(json.dumps(profile), encoding='utf-8')
    script = tmp_path / 'Tools/check_maintenance_uart.ps1'
    script.write_text(CHECKER_SOURCE, encoding='utf-8')
    fields = dict(BaudRate='460800', WordLength='UART_WORDLENGTH_8B', Parity='UART_PARITY_NONE',
                  StopBits='UART_STOPBITS_1', HwFlowCtl='UART_HWCONTROL_NONE', Mode='UART_MODE_TX_RX')
    text = 'huart3.Instance = USART3;\n' + '\n'.join(f'huart3.Init.{key} = {value};' for key, value in fields.items())
    source = tmp_path / 'Core/usart.c'
    source.write_text(text, encoding='utf-8')
    ioc = tmp_path / 'target.ioc'
    ioc.write_text('USART3.BaudRate=460800\nRCC.APB1Freq_Value=42000000\n', encoding='utf-8')
    # Exit-status checks retain raw localized PowerShell output; decoding it
    # with Python's UTF-8 mode can raise in the subprocess reader thread.
    run = lambda: subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, timeout=10)
    assert run().returncode == 0
    ioc.write_text('USART3.BaudRate=230400\nRCC.APB1Freq_Value=42000000\n', encoding='utf-8')
    assert run().returncode != 0 and source.read_text(encoding='utf-8') == text
    ioc.write_text('USART3.BaudRate=460800\nRCC.APB1Freq_Value=42000000\n', encoding='utf-8')
    source.write_text(text.replace('460800', '230400'), encoding='utf-8')
    before = source.read_bytes()
    assert run().returncode != 0 and source.read_bytes() == before


def test_runtime_mismatch_rejects_console_before_platform_initialization(tmp_path, workspace_root):
    compiler = shutil.which('gcc')
    assert compiler
    guard = MaintenanceUart_RuntimeGuard(dict(handle='huart3', peripheral='USART3', baudrate=230400))
    driver = (workspace_root / 'plugins/builtin/silverstar_device_console_uart/payload/Devices/Console/UART/Src/console_uart_device.c').read_text(encoding='utf-8')
    begin = driver.index('ConsoleUartInitResult ConsoleUart_Init(void)')
    init = driver[begin:driver.index('\n}', begin)+2]
    source = '''#include <stdint.h>
typedef enum { ProjectMaintenanceUartResult_Ok, ProjectMaintenanceUartResult_Mismatch } ProjectMaintenanceUartResult;
typedef enum { CONSOLE_UART_INIT_OK, CONSOLE_UART_INIT_IO_ERROR } ConsoleUartInitResult;
#define UART_WORDLENGTH_8B 8U
#define UART_PARITY_NONE 0U
#define UART_STOPBITS_1 1U
#define UART_MODE_TX_RX 3U
#define UART_HWCONTROL_NONE 0U
#define USART3 ((void*)3)
#define PROJECT_RESOURCE_CONSOLE_UART 2U
#define PLATFORM_OK 0
struct Config { uint32_t BaudRate,WordLength,Parity,StopBits,Mode,HwFlowCtl; };
struct Uart { void *Instance; struct Config Init; };
static struct Uart huart3 = {USART3,{230400,8,0,1,3,0}};
static unsigned calls;
int PlatformUart_Init(unsigned id) { calls++; return id == 2U ? PLATFORM_OK : 1; }
'''+guard+'\n'+init+'''
int main(void) {
 struct Uart correct=huart3;
 if(ConsoleUart_Init()!=CONSOLE_UART_INIT_OK || calls!=1U) return 1;
 for(unsigned i=0;i<7U;i++) {
   huart3=correct; calls=0;
   if(i==0U)huart3.Instance=(void*)4;
   if(i==1U)huart3.Init.BaudRate=460800;
   if(i==2U)huart3.Init.WordLength=9;
   if(i==3U)huart3.Init.Parity=1;
   if(i==4U)huart3.Init.StopBits=2;
   if(i==5U)huart3.Init.Mode=1;
   if(i==6U)huart3.Init.HwFlowCtl=1;
   if(ConsoleUart_Init()!=CONSOLE_UART_INIT_IO_ERROR || calls!=0U)return 2;
 }
 return 0;
}
'''
    c_file, executable = tmp_path / 'runtime_guard.c', tmp_path / 'runtime_guard.exe'
    c_file.write_text(source, encoding='utf-8')
    records = []
    for command in ([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer', str(c_file), '-o', str(executable)], [str(executable)]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        records.append(dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        (tmp_path / 'commands.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('baud', [0, 1199, 2000001, True, None, '921600'])
def test_uart_range_rejects_invalid_imported_values(baud):
    from silverstar_fccg.plugins.manifest import ResourceRequirement, ResourceProvision
    from silverstar_fccg.project.resources import _RequirementConstraintsErrors_Get
    req = ResourceRequirement('console', 'uart', constraints={'uart': {'baud': {'minimum': 1200, 'maximum': 2000000}}})
    provision = ResourceProvision('uart3', 'uart', metadata={'physical_resource': 'USART3', 'baud_rate': baud, 'pins': {'rx': 'PB11', 'tx': 'PB10'}})
    errors = _RequirementConstraintsErrors_Get('console', req, provision, SimpleNamespace())
    assert any('uart.baud.' in item for item in errors)


@pytest.mark.parametrize('baud', [123457, 250000, 921600])
def test_uart_range_accepts_imported_rate_outside_host_preset_list(baud):
    from silverstar_fccg.plugins.manifest import ResourceRequirement, ResourceProvision
    from silverstar_fccg.project.resources import _RequirementConstraintsErrors_Get
    req = ResourceRequirement('console', 'uart', constraints={'uart': {'baud': {'minimum': 1200, 'maximum': 2000000}}})
    provision = ResourceProvision('uart3', 'uart', metadata={'physical_resource': 'USART3', 'baud_rate': baud, 'pins': {'rx': 'PB11', 'tx': 'PB10'}})
    assert not _RequirementConstraintsErrors_Get('console', req, provision, SimpleNamespace())


@pytest.mark.parametrize('bounds', [{'minimum': 1200}, {'maximum': 2000000}, {'minimum': 5, 'maximum': 4}, {'minimum': True, 'maximum': 2000000}, {'minimum': 0, 'maximum': 2000000}])
def test_uart_manifest_range_rejects_invalid_bounds(bounds):
    from silverstar_fccg.plugins.manifest import _BusConstraints_Validate, PluginManifestError
    with pytest.raises(PluginManifestError):
        _BusConstraints_Validate('console', 'uart', {'uart': {'baud': bounds}})


def test_checker_rejects_clock_divisor_or_instance_mismatch(tmp_path):
    (tmp_path/'Tools').mkdir(); (tmp_path/'Core').mkdir()
    profile = dict(handle='huart3', peripheral='USART3', baudrate=921600)
    (tmp_path/'Tools/maintenance_uart.json').write_text(json.dumps(profile))
    script = tmp_path/'Tools/check_maintenance_uart.ps1'; script.write_text(CHECKER_SOURCE)
    fields = dict(BaudRate='921600', WordLength='UART_WORDLENGTH_8B', Parity='UART_PARITY_NONE', StopBits='UART_STOPBITS_1', HwFlowCtl='UART_HWCONTROL_NONE', Mode='UART_MODE_TX_RX', OverSampling='UART_OVERSAMPLING_16')
    text = 'huart3.Instance = USART3;\n' + '\n'.join(f'huart3.Init.{k} = {v};' for k,v in fields.items())
    source = tmp_path/'Core/usart.c'; source.write_text(text)
    ioc = tmp_path/'target.ioc'
    run = lambda: subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,timeout=10)
    ioc.write_text('USART3.BaudRate=921600\nRCC.APB1Freq_Value=42000000\n')
    assert run().returncode == 0
    ioc.write_text('USART3.BaudRate=921600\nRCC.APB1Freq_Value=8000000\n')
    assert run().returncode != 0 and source.read_text() == text
    ioc.write_text('USART3.BaudRate=921600\nRCC.APB1Freq_Value=42000000\n')
    source.write_text(text.replace('Instance = USART3','Instance = USART2'))
    assert run().returncode != 0
