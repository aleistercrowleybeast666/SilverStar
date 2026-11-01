"""Generated, statically dispatched research controller; never an actuator driver."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from silverstar_fccg.project.mission_functions import Function_Create
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.tuning_bundle import TuningBundle_Read, TuningBundle_ControlCoreAttach, TuningBundle_ControlTaskAttach

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures/tuning_bundle_v1'


@pytest.mark.parametrize("kind", ("pid", "lqr"))
def test_controller_has_declared_mission_adapter(builtin_catalog, kind):
    function = Function_Create("silverstar.algorithm.control." + kind, builtin_catalog)
    assert function["instance_id"] == "controller"
    assert function["category"] == "control"
    assert function["output"] == "control.research.command"
    assert function["execution"] == "continuous"


def _Model_Create(catalog, kind):
    model = ReferenceProject_Create(catalog=catalog)
    for identity in ('coast', 'done'):
        model.mission_process['stages'].append({'stage_id': identity, 'name': identity,
            'condition': {'signal': 'stage_elapsed_s', 'operator': '>=', 'value': .02, 'unit': 's'},
            'hold_ms': 0, 'action': {'kind': 'none', 'target': ''}})
    bundle = TuningBundle_Read(FIXTURES / f'kf6-{kind}.sstuning.json')
    model = TuningBundle_ControlTaskAttach(model, catalog, bundle)
    function = next(row for row in model.mission_functions['functions'] if row['instance_id'] == 'controller')
    function['stop'] = {'kind': 'stage_enter', 'stage_id': 'done'}
    return model


@pytest.mark.parametrize('kind', ('pid', 'lqr'))
def test_task_is_explicit_and_preserves_core_only(builtin_catalog, kind):
    from silverstar_fccg.generator.control_research import ControlResearchFiles_Render
    from silverstar_fccg.project.mission_functions import Functions_Derive
    model = ReferenceProject_Create(catalog=builtin_catalog)
    bundle = TuningBundle_Read(FIXTURES / f'kf6-{kind}.sstuning.json')
    core = TuningBundle_ControlCoreAttach(model, builtin_catalog, bundle)
    assert not any(row['instance_id'] == 'controller' for row in Functions_Derive(core, builtin_catalog)['functions'])
    before = deepcopy(core.Dictionary_Get())
    disabled = json.loads(ControlResearchFiles_Render(core, builtin_catalog)['Generated/control_research.json'])
    assert disabled['enabled'] is False
    task = TuningBundle_ControlTaskAttach(core, builtin_catalog, bundle)
    assert core.Dictionary_Get() == before
    enabled = json.loads(ControlResearchFiles_Render(task, builtin_catalog)['Generated/control_research.json'])
    assert enabled['enabled'] and not enabled['deployable'] and not enabled['electrical_output']
    assert enabled['output'] == {'quantity': 'requested_body_y_torque', 'axis': 'body-Y',
        'unit': 'N*m', 'nm_per_core_output_unit': 1.0, 'maximum_absolute_torque_nm': 1.0}
    metadata = json.loads((ROOT / f'plugins/builtin/silverstar_algorithm_control_{kind}/plugin.json').read_text(encoding='utf8'))['metadata']
    assert metadata['research_task_output'] == enabled['output']
    from silverstar_fccg.project.tuning_bundle import TuningBundle_Preview
    assert '1 N*m/core-output unit' in TuningBundle_Preview(model, builtin_catalog, bundle)['control_status']


@pytest.mark.parametrize('kind', ('pid', 'lqr'))
def test_non_10ms_remains_legal_core_but_task_rejects(builtin_catalog, kind):
    from silverstar_fccg.project.tuning_bundle import TuningBundle_Digest
    model = ReferenceProject_Create(catalog=builtin_catalog)
    bundle = TuningBundle_Read(FIXTURES / f'kf6-{kind}.sstuning.json')
    if kind == 'pid':
        bundle['control_research']['parameters']['sample_period_s'] = .02
    else:
        bundle['control_research']['design']['dt_s'] = .02
    bundle['content_sha256'] = TuningBundle_Digest(bundle)
    TuningBundle_ControlCoreAttach(model, builtin_catalog, bundle)
    with pytest.raises(ValueError, match='requires_10_ms'):
        TuningBundle_ControlTaskAttach(model, builtin_catalog, bundle)


@pytest.fixture(scope='module', params=('pid', 'lqr'))
def generated_control(request, builtin_catalog, workspace_root, tmp_path_factory):
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    model = _Model_Create(builtin_catalog, request.param)
    directory = tmp_path_factory.mktemp('control-research-' + request.param)
    TargetGeneration_Apply(model, builtin_catalog, WorkspacePolicy(workspace_root), directory, TargetScope.FLIGHT)
    root = directory / 'Flight_Controller'
    graph = SourceGraph_Resolve(model, builtin_catalog)
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fanalyzer',
        '-DCONTROL_RESEARCH_HOST_TRAP_CAPTURE=1',
        '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-I', str(root / 'Tests/Host'),
        '-I', str(root / 'APP/Src'), '-I', str(root / 'Common/Src'),
        '-include', str(root / 'Generated/Inc/project_flight_config.h')]
    for directory in graph.include_dirs:
        command += ['-I', str(root / directory)]
    command += ['-D' + value for value in graph.defines]
    for name in ('APP/Src/control_research_runtime.c', 'System/Src/system_mission_process.c',
        'Generated/Src/project_mission_process.c', 'Generated/Src/project_control_research.c',
        'System/Calibration/Src/system_calibration_correction.c',
        f'Algorithm/Control/{request.param.upper()}/Src/control_{request.param}.c',
        f'Algorithm/Control/{request.param.upper()}/Src/control_{request.param}_project.c'):
        command.append(str(root / name))
    command.append(str(root / 'Tests/Host/test_control_research.c'))
    executable = root / 'control-research.exe'
    command += ['-lm', '-o', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (root / 'control-compile.log').write_text(result.stdout + result.stderr, encoding='utf8')
    (root / 'control-compile.command.json').write_text(json.dumps(command, indent=2), encoding='utf8')
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize('scenario', ('normal', 'late_ok', 'overrun', 'stale', 'future', 'duplicate',
    'source', 'generation', 'epoch', 'unknown', 'nan', 'nonplanar', 'health', 'calibration_race',
    'stop', 'clock', 'startup_timeout', 'cached_expiry', 'corrupt_state', 'corrupt_backend', 'sequence_exhausted', 'corrupt_sink', 'read_fault',
    'compute_overrun', 'cached_source_revoked', 'stop_interleave', 'schedule_interleave'))
def test_generated_task_normal_and_faults(generated_control, scenario):
    result = subprocess.run([str(generated_control), scenario], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout


def test_generated_task_actual_body_y_torque_units(generated_control):
    result = subprocess.run([str(generated_control), 'torque_units'], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    # Imported fixture gains, 0.01 rad tilt and 0.002 rad/s calibrated gyro.
    # PID first sample: -(3.25*.01 + .2*.01*.01); LQR: -(2.96664548*.01 + 1.21384823*.002).
    expected_nm = -.03252 if 'control-research-pid' in str(generated_control) else -.03209415126
    actual_nm = float(result.stdout.split('requested_body_y_torque_nm=')[1].split()[0])
    assert actual_nm == pytest.approx(expected_nm, abs=1e-7)
    assert 'unit=N*m axis=body-Y nm_per_core_output_unit=1' in result.stdout
