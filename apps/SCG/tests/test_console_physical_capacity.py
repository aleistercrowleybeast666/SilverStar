"""Exact physical-owner capacity, using the production baseline functions."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.render import _DeviceInstancesHeader_Render, _DeviceDescriptorEntries_Get
from silverstar_fccg.project.reference import ReferenceProject_Create


def _Function_Get(source, name):
    match = re.search(r'static (?:SystemDeviceResult|SystemConsoleIoBaseline \*)\s*' + name + r'\(', source)
    assert match, name
    opening = source.index('{', match.start()); depth = 1; end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}'); end += 1
    return source[match.start():end]


def _Harness_Create(source, count):
    baseline = re.search(r'typedef struct\s*\{[^}]*SystemDeviceIoDiagnostics diagnostics;[^}]*\}\s*SystemConsoleIoBaseline;', source).group()
    storage = re.search(r'static PLATFORM_CPU_FAST_BSS SystemConsoleIoBaseline\s+s_io_baselines\[[^]]+\];', source).group()
    functions = '\n'.join(_Function_Get(source, name) for name in (
        'SystemConsole_IoBaselineFind', 'SystemConsole_IoBaselineSlotGet', 'SystemConsole_IoBaselineCapture'))
    return f'''#include <assert.h>
#include <string.h>
#include "system_imu_if.h"
#include "system_gnss_if.h"
#include "system_descriptor_if.h"
#define PLATFORM_CPU_FAST_BSS
#define SILVERSTAR_ASSERT_OBJECT(value,type,module) assert((value) != NULL)
#define PROJECT_SELECTED_PHYSICAL_DEVICE_COUNT {max(1, count)}U
#define ACTUAL_COUNT {count}U
typedef enum {{ Module_Power }} SystemConsoleModule;
static int s_corrupt;
static unsigned s_counter;
static SystemDeviceResult SystemConsole_IoDiagnosticsRawGet(SystemConsoleModule module, uint8_t index,
    SystemDeviceIoDiagnostics *diagnostics, SystemDeviceDescriptor *owner)
{{
    (void)module; memset(diagnostics, 0, sizeof(*diagnostics)); memset(owner, 0, sizeof(*owner));
    owner->device_class=SYSTEM_DEVICE_CLASS_POWER; owner->instance_id=index;
    owner->physical_device_id=(uint16_t)(100U+index+(unsigned)s_corrupt);
    diagnostics->rx_bytes=s_counter;
    return SYSTEM_DEVICE_OK;
}}
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass device_class, uint8_t index,
    SystemDeviceDescriptor *descriptor)
{{
    if (device_class != SYSTEM_DEVICE_CLASS_POWER || (unsigned)index+1U > ACTUAL_COUNT)
        return SYSTEM_DEVICE_NOT_PRESENT;
    memset(descriptor,0,sizeof(*descriptor)); descriptor->physical_device_id=(uint16_t)(100U+index);
    return SYSTEM_DEVICE_OK;
}}
SystemDeviceResult ProjectImuInstance_IoDetailGet(uint8_t index, SystemImuIoDetail *detail)
{{ (void)index; (void)detail; return SYSTEM_DEVICE_NOT_PRESENT; }}
SystemDeviceResult ProjectGnssInstance_IoDetailGet(uint8_t index, SystemGnssIoDetail *detail)
{{ (void)index; (void)detail; return SYSTEM_DEVICE_NOT_PRESENT; }}
{baseline}
{storage}
{functions}
int main(void)
{{
    assert(sizeof(s_io_baselines) == PROJECT_SELECTED_PHYSICAL_DEVICE_COUNT * sizeof(SystemConsoleIoBaseline));
    for (unsigned index=0; index+1U<=ACTUAL_COUNT; index++)
    {{
        s_counter=index+1U;
        assert(SystemConsole_IoBaselineCapture(Module_Power,(uint8_t)index)==SYSTEM_DEVICE_OK);
        assert(SystemConsole_IoBaselineFind((uint16_t)(100U+index))->diagnostics.rx_bytes==s_counter);
    }}
    SystemConsoleIoBaseline saved[PROJECT_SELECTED_PHYSICAL_DEVICE_COUNT];
    memcpy(saved,s_io_baselines,sizeof(saved));
    assert(SystemConsole_IoBaselineCapture(Module_Power,(uint8_t)ACTUAL_COUNT)==SYSTEM_DEVICE_NOT_PRESENT);
    assert(memcmp(saved,s_io_baselines,sizeof(saved))==0);
    if (ACTUAL_COUNT != 0U)
    {{
        assert(SystemConsole_IoBaselineSlotGet(60000U)==NULL);
        s_corrupt=1;
        assert(SystemConsole_IoBaselineCapture(Module_Power,0U)==SYSTEM_DEVICE_VERIFY_FAILED);
        assert(memcmp(saved,s_io_baselines,sizeof(saved))==0);
        s_corrupt=0; s_counter=99U;
        assert(SystemConsole_IoBaselineCapture(Module_Power,0U)==SYSTEM_DEVICE_OK);
        assert(SystemConsole_IoBaselineFind(100U)->diagnostics.rx_bytes==99U);
    }}
    return 0;
}}
'''


def test_generated_capacity_matches_unique_selected_descriptors(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    descriptors = _DeviceDescriptorEntries_Get(model, builtin_catalog)
    count = len({row['physical_device_id'] for row in descriptors})
    assert 0 < count < 32
    assert f'#define PROJECT_SELECTED_PHYSICAL_DEVICE_COUNT {count}U' in _DeviceInstancesHeader_Render(model, builtin_catalog)


@pytest.mark.parametrize('count', [0, 1, 8, 32])
def test_owner_baseline_exact_capacity_unknown_ids_and_no_partial_commit(tmp_path, count):
    core = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload'
    source = (core / 'System/Src/system_console.c').read_text(encoding='utf8')
    harness = tmp_path / 'baseline.c'; harness.write_text(_Harness_Create(source, count), encoding='utf8')
    output = tmp_path / 'baseline.exe'
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I' + str(core / 'Common/Inc'), '-I' + str(core / 'Interfaces/Inc'), str(harness), '-o', str(output)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([str(output)], capture_output=True, text=True, timeout=15)
    assert executed.returncode == 0, executed.stderr
