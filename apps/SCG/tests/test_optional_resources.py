"""Resource choices select real source ownership, without changing TF logging."""
from copy import deepcopy
from dataclasses import replace
import json
import os
import shutil
import subprocess

import pytest

from silverstar_fccg.project.model import BuildOptions, ProjectModel_Parse, ProjectModelError, DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.capabilities import _Providers_Get
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
from silverstar_fccg.generator.render import _DeviceDescriptorEntries_Get, _FlightConfigHeader_Render


@pytest.mark.parametrize('tier', ['full', 'standard', 'compact', 'minimal'])
def test_tier_defaults_and_explicit_switch_restore(builtin_catalog, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    protocols, streams = deepcopy(model.protocols), deepcopy(model.logging_streams)
    model.build = replace(model.build, magnetometer_enabled=False)
    FeatureTier_Apply(model, tier, builtin_catalog)
    expected = tier in ('full', 'standard')
    assert model.build.maintenance_log_export_enabled == expected
    assert model.build.magnetometer_enabled == (expected and tier != 'full')
    assert model.protocols['logging'] == protocols['logging']
    assert model.logging_streams == streams
    FeatureTier_Apply(model, 'full', builtin_catalog)
    assert not model.build.magnetometer_enabled
    assert model.build.maintenance_log_export_enabled


@pytest.mark.parametrize('key', ['magnetometer_enabled', 'maintenance_log_export_enabled'])
def test_strict_roundtrip_and_prohibited_loaded_selection(builtin_catalog, key):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    before = model.Dictionary_Get()
    model.build = replace(model.build, **{key: False})
    saved = model.Dictionary_Get()
    assert saved['format_version'] == 21
    assert ProjectModel_Parse(saved).Dictionary_Get() == saved
    invalid = deepcopy(saved)
    invalid['build'][key] = 0
    with pytest.raises(ProjectModelError, match='boolean'):
        ProjectModel_Parse(invalid)
    invalid['build'].update(feature_tier='compact', **{key: True})
    with pytest.raises(ProjectModelError, match='prohibited'):
        ProjectModel_Parse(invalid)
    invalid = deepcopy(saved)
    invalid['format_version'] = 20
    with pytest.raises(ProjectModelError, match='format_version 21'):
        ProjectModel_Parse(invalid)
    assert before['build'].get(key) is None  # Default legacy serialization stays compatible.


@pytest.mark.parametrize('mag,export', [(True, True), (False, True), (True, False), (False, False)])
def test_real_sources_descriptors_and_logging_are_independent(builtin_catalog, mag, export):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances = [replace(i, profile='jy901b_mag_capture')
                              if i.plugin == 'silverstar.device.imu.jy901b' else i
                              for i in model.device_instances]
    model.build = replace(model.build, magnetometer_enabled=mag, maintenance_log_export_enabled=export)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    for original, disabled, enabled in [
        ('System/Src/system_log_file.c', 'System/Src/system_log_file_disabled.c', export),
        ('System/Calibration/Src/system_mag_calibration.c',
         'System/Calibration/Src/system_mag_calibration_disabled.c', mag)]:
        assert (original in graph.sources) == enabled
        assert (disabled in graph.sources) != enabled
        assert (disabled if enabled else original) in graph.exclude_sources
    assert ('Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c' in graph.sources) == export
    assert ('Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c' in graph.sources) == mag
    assert ('Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c' in graph.sources) == mag
    assert 'APP/Src/logger_task.c' in graph.sources
    assert 'Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c' in graph.sources
    entries = _DeviceDescriptorEntries_Get(model, builtin_catalog)
    assert bool([e for e in entries if e['class'] == 'SYSTEM_DEVICE_CLASS_MAGNETOMETER']) == mag
    providers = _Providers_Get(model.device_instances, builtin_catalog.ProjectView_Get(model), model)
    assert bool(providers.get('magnetometer.field')) == mag
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    import re
    assert re.search(r'JY901B_MAGNETOMETER_ADAPTER_ENABLE\s+' + ('1U' if mag else '0U'), header)
    from silverstar_fccg.project.compact_logging import CompactLogStreams_Get
    if not mag:
        magnetic = {'FLIGHT_LOG_RECORD_MAG_NATIVE', 'FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY'}
        retained = [replace(stream, enabled=True) if stream.record in magnetic else stream
                    for stream in model.logging_streams]
        model.logging_streams = retained
        assert not any(s.enabled for s in CompactLogStreams_Get(model) if s.record in magnetic)
        assert all(s.enabled for s in model.logging_streams if s.record in magnetic)


def test_export_requires_both_protocols_and_off_mag_rejects_dedicated_device(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    for category in ('logging', 'maintenance'):
        candidate = deepcopy(model)
        candidate.protocols[category] = None
        sources = SourceGraph_Resolve(candidate, builtin_catalog).sources
        assert 'System/Src/system_log_file_disabled.c' in sources
        assert 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c' not in sources
    model.device_instances.append(DeviceInstance('mag0', 'silverstar.device.magnetometer.lis3mdl'))
    model.build = replace(model.build, magnetometer_enabled=False)
    with pytest.raises(SourceGraphError, match='remove dedicated magnetometer'):
        SourceGraph_Resolve(model, builtin_catalog)


def test_resource_schema_matches_parser_policy(workspace_root, builtin_catalog):
    from jsonschema import Draft202012Validator
    schema = json.loads((workspace_root/'schemas/project.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, magnetometer_enabled=False, maintenance_log_export_enabled=False)
    saved = model.Dictionary_Get()
    validator.validate(saved)
    invalid = deepcopy(saved)
    invalid['format_version'] = 20
    assert list(validator.iter_errors(invalid))
    invalid = deepcopy(saved)
    invalid['build'].update(feature_tier='compact', magnetometer_enabled=True)
    assert list(validator.iter_errors(invalid))


def test_disabled_implementations_have_no_state_and_preserve_failed_outputs(tmp_path, workspace_root):
    gcc = shutil.which('gcc')
    assert gcc, 'Actual Host GCC required'
    builtin = workspace_root / 'plugins/builtin'
    core = builtin / 'silverstar_core_0_1_0/payload'
    source = tmp_path / 'disabled.c'
    source.write_text(r'''
#include <assert.h>
#include <string.h>
#include "silverstar_assert.h"
#include "system_log_file.h"
#include "system_mag_calibration.h"
#include "system_mag_calibration_storage_if.h"
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason) {
    (void)module; (void)file; (void)line; (void)reason; assert(condition);
}
void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line) {
    (void)module; (void)file; (void)line;
    assert(object != 0 && alignment != 0 && (uintptr_t)object % alignment == 0);
}
int main(void) {
    char response[512]; uint8_t data[565], packet[256]; uint16_t length=99;
    uint8_t instance=37; uint32_t request=41;
    SystemLogFileSnapshot status, before;
    SystemMagCalibrationSnapshot mag, mag_before;
    SystemMagnetometerSample sample, sample_before;
    memset(&status, 0x5a, sizeof(status)); before=status;
    memset(&mag, 0x5a, sizeof(mag)); mag_before=mag;
    memset(&sample, 0x5a, sizeof(sample)); sample_before=sample;
    memset(data, 0x5a, sizeof(data)); memset(packet, 0x5a, sizeof(packet));
    SystemLogFile_StatusPublish(&status); SystemLogFile_Process(1);
    assert(!SystemLogFile_IsActive()); assert(!SystemLogFile_StatusGet(&status));
    assert(memcmp(&before,&status,sizeof(status))==0);
    assert(SystemLogFile_ExecuteLine("LOGFILE CAPS",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
    assert(strstr(response,"supported=0")!=0);
    assert(SystemLogFile_ExecuteLine("LOGFILE ENTER",response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_OK);
    assert(strstr(response,"UNSUPPORTED")!=0);
    assert(SystemLogFile_ExecuteLine(0,response,sizeof(response))==SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    assert(SystemLogFile_BinaryResponseGet(data,sizeof(data),&length)==SystemLogFileResult_NotReady);
    assert(length==99 && data[0]==0x5a);
    assert(SystemLogFile_BinaryResponseGet(0,sizeof(data),&length)==SystemLogFileResult_BadArgument);
    SystemMagCalibration_Init(); SystemMagCalibrationStorage_Service();
    assert(SystemMagCalibration_ReadyForMissionGet()==1);
    assert(SystemMagCalibrationStorage_LoadCompleteGet()==1);
    assert(SystemMagCalibration_GenerationHashGet()==0);
    assert(SystemMagCalibration_SnapshotGet(0,&mag)==SystemMagCalibrationResult_NotPresent);
    assert(memcmp(&mag,&mag_before,sizeof(mag))==0);
    assert(SystemMagCalibration_SampleApply(0,&sample)==SystemMagCalibrationResult_NotPresent);
    assert(memcmp(&sample,&sample_before,sizeof(sample))==0);
    assert(SystemMagCalibration_PendingRecordGet(&instance,packet,&request)==SystemMagCalibrationResult_NotPresent);
    assert(instance==37 && request==41 && packet[0]==0x5a);
    assert(SystemMagCalibration_SaveRequest(0)==SystemMagCalibrationResult_NotPresent);
    assert(SystemMagCalibration_ClearRequest(0)==SystemMagCalibrationResult_NotPresent);
    assert(SystemMagCalibration_PacketApply(0,0)==SystemMagCalibrationResult_InvalidArgument);
    assert(SystemMagCalibration_RecordLoad(0,packet,1,0)==SystemMagCalibrationResult_InvalidArgument);
    return 0;
}
''', encoding='utf-8')
    includes = [workspace_root/'tests/log_file_service', core/'System/Inc',
                core/'System/Calibration/Inc', core/'Interfaces/Inc', core/'Common/Inc',
                builtin/'silverstar_platform_api/payload/Platform/Inc']
    sources = [source, core/'System/Src/system_log_file_disabled.c',
               core/'System/Calibration/Src/system_mag_calibration_disabled.c',
               core/'System/Src/system_mag_calibration_storage_disabled.c',
               core/'Common/Src/common_format.c']
    exe = tmp_path/'disabled.exe'
    command = [gcc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fanalyzer',
               *['-I'+str(p) for p in includes], *map(str, sources), '-o', str(exe)]
    rows = []
    for cmd in (command, [str(exe)]):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                           env={**os.environ, 'TEMP':str(tmp_path), 'TMP':str(tmp_path)})
        rows.append(dict(command=cmd, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr))
        (tmp_path/'RESULT.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        assert r.returncode == 0, r.stdout+r.stderr
