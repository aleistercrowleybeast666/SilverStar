"""Owning backend/health/LoggerBus/wire, with explicit CPU-only device inputs.

The staged mode override is a unit configuration. Generated mode2 admission,
exact decoder opening, FLP parity and a complete firmware gate are separate.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT/'apps/SCG'
BUILTIN = APP/'plugins/builtin'
CORE = BUILTIN/'silverstar_core_0_1_0/payload'
KERNEL = BUILTIN/'silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15'
COMMON = BUILTIN/'silverstar_algorithm_common/payload/Algorithm/Common'
PROTOCOL = BUILTIN/'silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG'
PLATFORM = BUILTIN/'silverstar_platform_api/payload/Platform/Inc'


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    supplied = os.environ.get('SILVERSTAR_HORIZON_STAGE_PROJECT')
    if supplied:
        result = Path(supplied).resolve()
        assert result.is_dir()
        return result
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    service = FccgService(APP)
    model = service.ReferenceProject_Create('HorizonBackendUnitConfiguration')
    model.strategies['estimator'] = 'silverstar.algorithm.estimator.eskf15'
    model = ProjectConfiguration_Reconcile(model,service.catalog).model
    model.algorithm_parameters['silverstar.algorithm.estimator.eskf15']['fusion_timing_mode'] = 0
    result = tmp_path_factory.mktemp('eskf_backend_config')/'project'
    service.Project_Save(model,result,confirm_dangerous=True)
    return result


@pytest.fixture(scope='module',params=['-O0','-O2'])
def executable(request,project,tmp_path_factory):
    output = tmp_path_factory.mktemp('eskf_backend_horizon'+request.param)
    graph = (project/'Generated/project_sources.mk').read_text()
    defines = re.search(r'^C_DEFS \+= \\\n(.*?)(?:\n\n|\Z)',graph,re.M|re.S).group(1)
    definitions = ['-D'+line.strip().rstrip('\\').strip() for line in defines.splitlines() if line.strip()]
    includes = [KERNEL/'Inc',COMMON/'Inc',PLATFORM,CORE/'Tests/Host',CORE/'APP/Inc',CORE/'Common/Inc',
        CORE/'Interfaces/Inc',CORE/'System/Inc',CORE/'System/Calibration/Inc',PROTOCOL/'Inc',
        project/'Generated/Inc',project/'Targets/SilverStar_F407/Inc',CORE/'System/User',CORE/'Modules/Inc']
    includes += [p for p in CORE.rglob('Inc') if p not in includes]
    includes += [p for p in (project/'Algorithm').rglob('Inc') if p not in includes]
    sources = [CORE/p for p in ['Tests/Host/test_eskf_horizon.c','Tests/Host/host_platform_mock.c',
        'APP/Src/logger_bus.c','APP/Src/estimator_bus.c','Common/Src/common_spsc_queue.c',
        'Common/Src/silverstar_assert.c','System/Src/system_log_policy.c','System/Src/system_profile.c',
        'System/Src/system_navigation_profile.c','System/Src/system_estimator_profile.c',
        'System/Src/system_navigation_health.c','System/Src/system_gnss_quality.c','System/Src/system_time.c',
        'System/Src/system_gnss_receipt.c']]
    sources += [KERNEL/'Src/navigation_eskf.c',KERNEL/'Src/navigation_eskf_horizon.c',
        KERNEL/'Src/navigation_eskf_recovery.c',
        COMMON/'Src/geodesy_local.c',COMMON/'Src/navigation_quality.c',PROTOCOL/'Src/sslog_records.c',
        PROTOCOL/'Src/sslog_protocol.c']
    sources += [project/'Generated/Src'/p for p in ['project_metadata.c','project_log_decoder_profile.c','project_log_config.c']]
    compiler = shutil.which('gcc');assert compiler, 'Actual GCC is required'
    target = output/'eskf_horizon_backend.exe'
    native = os.environ.get('SILVERSTAR_HORIZON_NATIVE_CONFIGURATION') == '1'
    backend_source = Path(os.environ.get('SILVERSTAR_HORIZON_BACKEND_SOURCE',
        str(KERNEL/'Src/navigation_eskf_backend.c'))).resolve()
    overrides = [] if native else ['-DSYSTEM_FUSION_TIMING_MODE=2U','-DSYSTEM_FUSION_HORIZON_MS=30U']
    command = [compiler,'-std=c11',request.param,'-Wall','-Wextra','-Werror','-Wpedantic',
        '-Wconversion','-Wsign-conversion','-Wshadow','-Wstrict-prototypes','-Wmissing-prototypes',
        '-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
        *overrides,
        '-DESKF_HORIZON_BACKEND_SOURCE="'+backend_source.as_posix()+'"',
        *definitions,'-include',str(project/'Generated/Inc/project_flight_config.h'),
        *['-I'+str(p) for p in includes],*map(str,sources),'-lm','-o',str(target)]
    run = subprocess.run(command,capture_output=True,text=True,timeout=180)
    source_files = [*sources,backend_source,*KERNEL.glob('Inc/*.h')]
    receipt = dict(scope=('native generated configuration; CPU stress inputs at 5ms, not nominal-rate/board proof'
        if native else 'staged unit configuration; actual backend/health/LoggerBus/wire; not a generated mode2 gate'),
        native_configuration=native,
        command=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr,
        compiler=subprocess.check_output([compiler,'--version'],text=True),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        generated_header_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (project/'Generated/Inc').glob('*.h')})
    (output/'compile.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    assert run.returncode == 0,run.stdout+run.stderr
    return target


@pytest.mark.parametrize('scenario',range(13),ids=['normal','source_switch','no_source','calibration_change',
    'imu_source_change','stored_corruption','invalid_latest_receipt','late','initial_body_fault',
    'barometer_only','barometer_invalid_latest_receipt','low_satellite_prepared_variance','owned_source_corruption'])
def test_actual_backend_lifecycle_queue_and_wire(executable,scenario):
    wire = executable.parent/f'case{scenario}.frames'
    command = [str(executable),str(scenario),str(wire)]
    run = subprocess.run(command,capture_output=True,text=True,timeout=30)
    (executable.parent/f'case{scenario}.json').write_text(json.dumps(dict(command=command,exit_code=run.returncode,
        stdout=run.stdout,stderr=run.stderr),indent=2),encoding='utf-8')
    assert run.returncode == 0,run.stdout+run.stderr
    assert wire.stat().st_size > 0
    assert re.search(r'eskf_horizon_backend_actual: \d+ checks, 0 failures',run.stdout)


@pytest.mark.parametrize('mode', (0, 1, 2))
def test_owned_receipt_corruption_without_preflight_origin(executable, mode):
    """Staged mode unit configuration; unchanged real backend fault expectations."""
    receipt = json.loads((executable.parent/'compile.json').read_text(encoding='utf8'))
    command = [arg for arg in receipt['command'] if not arg.startswith(
        ('-DSYSTEM_FUSION_TIMING_MODE=', '-DSYSTEM_FUSION_HORIZON_MS='))]
    command[1:1] = [f'-DSYSTEM_FUSION_TIMING_MODE={mode}U', '-DSYSTEM_FUSION_HORIZON_MS=30U']
    previous = str(CORE/'Tests/Host/test_eskf_horizon.c')
    fixture = CORE/'Tests/Host/test_eskf_origin_receipt_fault.c'
    command[command.index(previous)] = str(fixture)
    command.insert(command.index('-lm'), str(KERNEL/'Src/navigation_eskf_replay.c'))
    target = executable.parent/f'origin_fault_{mode}.exe'
    command[command.index('-o')+1] = str(target)
    build = subprocess.run(command, capture_output=True, text=True, timeout=180)
    evidence = dict(scope='CPU actual backend, staged unit mode; no firmware admission',
        command=command, compile_exit=build.returncode, stdout=build.stdout, stderr=build.stderr,
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        backend_source_sha256=receipt['source_sha256'])
    if build.returncode == 0:
        run = subprocess.run([str(target)], capture_output=True, text=True, timeout=30)
        evidence.update(run_exit=run.returncode, run_stdout=run.stdout, run_stderr=run.stderr)
    (executable.parent/f'origin_fault_{mode}.json').write_text(json.dumps(evidence, indent=2), encoding='utf8')
    assert build.returncode == 0, build.stdout+build.stderr
    assert evidence['run_exit'] == 0, evidence.get('run_stdout', '')+evidence.get('run_stderr', '')
