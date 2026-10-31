from pathlib import Path
import json
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.mission_process import MissionProcessFiles_Render
from silverstar_fccg.project.mission_process import MissionProcess_FirmwareDefault, MissionProcessFirmware_Require, MissionProcess_Default
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_native_presets_and_owner_validation(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    assert [stage['stage_id'] for stage in model.mission_process['stages']] == ['ready', 'ascent']
    model.mission_process = MissionProcess_FirmwareDefault(True, True, 'parachute_pyro0')
    assert [row['condition']['value'] for row in model.mission_process['stages'][2:4]] == [2.0, 2.0]
    assert MissionProcessFirmware_Require(model, builtin_catalog)['execution'] == 'firmware_bounded'
    model.mission_process['stages'][4]['action']['target'] = 'imu0'
    with pytest.raises(ValueError, match='MISSION_PROCESS_ACTION_TARGET:deploy'):
        MissionProcessFirmware_Require(model, builtin_catalog)
    model.mission_process = MissionProcess_Default()
    with pytest.raises(ValueError, match='REFERENCE_ONLY'):
        MissionProcessFirmware_Require(model, builtin_catalog)


def test_native_stage_identity_is_independent_of_display_name(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    first = MissionProcessFiles_Render(model, builtin_catalog)
    model.mission_process['stages'][1]['name'] = 'User title'
    second = MissionProcessFiles_Render(model, builtin_catalog)
    assert first['Generated/Src/project_mission_process.c'] == second['Generated/Src/project_mission_process.c']
    assert json.loads(second['Generated/mission_process.json'])['process'] == model.mission_process


def test_recovery_action_rejects_preflight_and_terminal_stages(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    for index in (0, 4):
        model.mission_process = MissionProcess_FirmwareDefault(False, True, 'parachute_pyro0')
        model.mission_process['stages'][2]['action'] = {'kind': 'none', 'target': ''}
        model.mission_process['stages'][index]['action'] = {'kind': 'request_recovery', 'target': 'parachute_pyro0'}
        with pytest.raises(ValueError, match='MISSION_PROCESS_ACTION_LIFECYCLE'):
            MissionProcessFirmware_Require(model, builtin_catalog)


def test_native_generated_engine_host(builtin_catalog, tmp_path):
    gcc = shutil.which('gcc')
    assert gcc is not None, 'Host GCC is required for the native consumer evidence'
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.mission_process = MissionProcess_FirmwareDefault(True)
    for stage in model.mission_process['stages'][2:]: stage['hold_ms'] = 100
    from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsGeneration_Require
    model.mission_functions = Functions_Derive(model, builtin_catalog)
    model.mission_functions['schema_version'] = 2
    telemetry = next(row for row in model.mission_functions['functions'] if row['category'] == 'telemetry')
    telemetry['start'] = {'kind': 'stage_enter', 'stage_id': 'ascent'}
    telemetry['stop'] = {'kind': 'stage_exit', 'stage_id': 'coast'}
    for function in model.mission_functions['functions']:
        if function['output'] in ('navigation.pure_ins', 'navigation.estimate'):
            function['stop'] = {'kind': 'stage_enter', 'stage_id': 'coast'}
    FunctionsGeneration_Require(model, builtin_catalog)
    files = MissionProcessFiles_Render(model, builtin_catalog)
    for name, value in files.items():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value, encoding='utf-8')
    stub = tmp_path / 'host'; stub.mkdir()
    (stub / 'platform_memory.h').write_text('#define PLATFORM_CPU_FAST_BSS\n')
    (stub / 'platform_critical.h').write_text('#include <stdint.h>\nstatic inline uint32_t PlatformCritical_Enter(void){return 0;}\nstatic inline void PlatformCritical_Exit(uint32_t lock){(void)lock;}\n')
    (stub / 'silverstar_assert.h').write_text('#include <assert.h>\n#define SILVERSTAR_ASSERT(condition,module,reason) assert(condition)\n')
    root = Path(__file__).resolve().parents[1]
    core = root / 'plugins/builtin/silverstar_core_0_1_0/payload'
    executable = tmp_path / 'mission_process.exe'
    command = [gcc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', str(stub), '-I', str(tmp_path / 'Generated/Inc'), '-I', str(core / 'System/Inc'),
        '-I', str(core / 'Interfaces/Inc'), '-I', str(core / 'Common/Inc'),
        str(core / 'System/Src/system_mission_process.c'), str(tmp_path / 'Generated/Src/project_mission_process.c'),
        str(root / 'tests/fixtures/mission_process_host.c'), '-o', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout


@pytest.fixture(scope='module')
def native_generated_owner(workspace_root, builtin_catalog, tmp_path_factory):
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    model = ReferenceProject_Create(catalog=builtin_catalog)
    directory = tmp_path_factory.mktemp('native-generated-owner')
    TargetGeneration_Apply(model, builtin_catalog, WorkspacePolicy(workspace_root), directory, TargetScope.FLIGHT)
    return directory / 'Flight_Controller', SourceGraph_Resolve(model, builtin_catalog)


@pytest.mark.parametrize('recovery', [False, True])
def test_native_recovery_permission_owner(native_generated_owner, builtin_catalog, tmp_path, recovery):
    root, graph = native_generated_owner
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.mission_process = MissionProcess_FirmwareDefault(False, recovery, 'parachute_pyro0' if recovery else '')
    header = MissionProcessFiles_Render(model, builtin_catalog)['Generated/Inc/project_mission_process.h']
    (tmp_path / 'project_mission_process.h').write_text(header, encoding='utf-8')
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
               '-I', str(tmp_path), '-I', str(root / 'Tests/Host'), '-include', str(root / 'Generated/Inc/project_flight_config.h')]
    for directory in graph.include_dirs: command.extend(['-I', str(root / directory)])
    definitions = {row.split('=', 1)[0]: row for row in graph.defines}
    definitions.update({key: key + '=' + value for key, value in {
        'SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK': 'SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ',
        'SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS': '0U', 'SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE': '0U',
        'TEST_EXPECT_APOGEE': '1'}.items()})
    command.extend('-D' + value for value in definitions.values())
    command.extend(str(root / source) for source in (
        'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c',
        'FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c',
        'FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c',
        'Tests/Host/host_platform_mock.c', 'Common/Src/silverstar_assert.c'))
    command.append(str(Path(__file__).parent / 'fixtures/mission_recovery_owner_host.c'))
    executable = tmp_path / 'recovery-owner.exe'; command.extend(['-lm', '-o', str(executable)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_acceleration_uses_actual_corrected_provider(native_generated_owner, tmp_path):
    root, graph = native_generated_owner
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        '-I', str(root / 'Tests/Host'), '-I', str(root / 'System/Src'),
        '-include', str(root / 'Generated/Inc/project_flight_config.h')]
    for directory in graph.include_dirs: command.extend(['-I', str(root / directory)])
    command.extend('-D' + value for value in graph.defines)
    command.extend(str(root / source) for source in (
        'System/Src/system_mission_process.c', 'Generated/Src/project_mission_process.c',
        'System/Calibration/Src/system_calibration_correction.c',
        'Common/Src/silverstar_assert.c', 'Tests/Host/host_platform_mock.c'))
    command.append(str(Path(__file__).parent / 'fixtures/mission_acceleration_source_host.c'))
    executable = tmp_path / 'acceleration-source.exe'
    command.extend(['-lm', '-o', str(executable)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_dependency_gates_on_actual_owner_ready_mask(builtin_catalog, tmp_path):
    from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsGeneration_Require
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.mission_functions = Functions_Derive(model, builtin_catalog)
    for row in model.mission_functions['functions']:
        if row['instance_id'] in ('ins', 'estimator', 'telemetry'):
            row['stop'] = {'kind': 'lifecycle_end', 'stage_id': ''}
        if row['instance_id'] == 'telemetry':
            row['start'] = {'kind': 'mission_start', 'stage_id': ''}
            row['depends_on'] = ['estimator']
    FunctionsGeneration_Require(model, builtin_catalog)
    for name, value in MissionProcessFiles_Render(model, builtin_catalog).items():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value, encoding='utf8')
    stub = tmp_path / 'host'; stub.mkdir()
    (stub / 'platform_memory.h').write_text('#define PLATFORM_CPU_FAST_BSS\n')
    (stub / 'platform_critical.h').write_text('#include <stdint.h>\nstatic inline uint32_t PlatformCritical_Enter(void){return 0;}\nstatic inline void PlatformCritical_Exit(uint32_t lock){(void)lock;}\n')
    (stub / 'silverstar_assert.h').write_text('#include <assert.h>\n#define SILVERSTAR_ASSERT(condition,module,reason) assert(condition)\n')
    root = Path(__file__).resolve().parents[1]; core = root / 'plugins/builtin/silverstar_core_0_1_0/payload'
    executable = tmp_path / 'dependencies.exe'
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', str(stub), '-I', str(tmp_path / 'Generated/Inc'), '-I', str(core / 'System/Inc'),
        '-I', str(core / 'Interfaces/Inc'), '-I', str(core / 'Common/Inc'),
        str(core / 'System/Src/system_mission_process.c'), str(tmp_path / 'Generated/Src/project_mission_process.c'),
        str(root / 'tests/fixtures/mission_dependencies_host.c'), '-o', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
