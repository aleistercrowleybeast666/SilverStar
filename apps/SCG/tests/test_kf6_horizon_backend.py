"""Actual KF6 task/health/LoggerBus/wire with explicit staged Host overrides."""
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
KERNEL = BUILTIN/'silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6'
COMMON = BUILTIN/'silverstar_algorithm_common/payload/Algorithm/Common'
INS = BUILTIN/'silverstar_algorithm_ins_coning2_sculling2/payload/Algorithm/INS/Coning2Sculling2'
PROTOCOL = BUILTIN/'silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG'
PLATFORM = BUILTIN/'silverstar_platform_api/payload/Platform/Inc'


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    supplied = os.environ.get('SILVERSTAR_HORIZON_KF_STAGE_PROJECT')
    if supplied:
        result = Path(supplied).resolve();assert result.is_dir();return result
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    service=FccgService(APP);model=service.ReferenceProject_Create('KfHorizonBackendUnitConfiguration')
    model.strategies['estimator']='silverstar.algorithm.estimator.kf6'
    model=ProjectConfiguration_Reconcile(model,service.catalog).model
    model.algorithm_parameters['silverstar.algorithm.estimator.kf6']['fusion_timing_mode']=0
    result=tmp_path_factory.mktemp('kf_backend_config')/'project'
    service.Project_Save(model,result,confirm_dangerous=True)
    return result


@pytest.fixture(scope='module',params=['-O0','-O2'])
def executable(request,project,tmp_path_factory):
    output=tmp_path_factory.mktemp('kf_backend_horizon'+request.param)
    graph=(project/'Generated/project_sources.mk').read_text()
    defines=re.search(r'^C_DEFS \+= \\\n(.*?)(?:\n\n|\Z)',graph,re.M|re.S).group(1)
    definitions=['-D'+line.strip().rstrip('\\').strip() for line in defines.splitlines() if line.strip()]
    includes=[KERNEL/'Inc',COMMON/'Inc',INS/'Inc',PLATFORM,CORE/'Tests/Host',CORE/'APP/Inc',
        CORE/'Common/Inc',CORE/'Interfaces/Inc',CORE/'System/Inc',CORE/'System/User',PROTOCOL/'Inc',
        project/'Generated/Inc',project/'Targets/SilverStar_F407/Inc']
    includes += [p for root in (CORE,project/'Algorithm') for p in root.rglob('Inc') if p not in includes]
    sources=[CORE/p for p in ['Tests/Host/test_estimator_horizon.c','Tests/Host/host_platform_mock.c',
        'APP/Src/logger_bus.c','APP/Src/estimator_bus.c','APP/Src/estimator_barometer_pending.c',
        'Common/Src/common_spsc_queue.c','Common/Src/silverstar_assert.c','System/Src/system_log_policy.c',
        'System/Src/system_profile.c','System/Src/system_navigation_profile.c','System/Src/system_estimator_profile.c',
        'System/Src/system_estimator_diagnostics.c','System/Src/system_navigation_health.c',
        'System/Src/system_gnss_quality.c','System/Src/system_time.c','System/Src/system_barometer.c']]
    sources += [KERNEL/'Src/navigation_kf.c',KERNEL/'Src/navigation_kf_replay.c',KERNEL/'Src/navigation_kf_horizon.c',
        KERNEL/'Src/navigation_integrity.c',INS/'Src/ins_mechanization.c',COMMON/'Src/attitude_frame.c',
        COMMON/'Src/geodesy_local.c',COMMON/'Src/navigation_quality.c',PROTOCOL/'Src/sslog_records.c',PROTOCOL/'Src/sslog_protocol.c']
    sources += [project/'Generated/Src'/p for p in ['project_metadata.c','project_log_decoder_profile.c','project_log_config.c']]
    compiler=shutil.which('gcc');assert compiler,'Actual GCC is required'
    target=output/'kf_horizon_backend.exe'
    native = os.environ.get('SILVERSTAR_HORIZON_NATIVE_CONFIGURATION') == '1'
    overrides = [] if native else ['-DSYSTEM_FUSION_TIMING_MODE=2U','-DSYSTEM_FUSION_HORIZON_MS=30U']
    command=[compiler,'-std=c11',request.param,'-Wall','-Wextra','-Werror','-Wpedantic',
        '-Wconversion','-Wsign-conversion','-Wshadow','-Wstrict-prototypes','-Wmissing-prototypes',
        '-fno-fast-math','-ffp-contract=off',
        '-flto=1','-flto-partition=one','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
        *overrides,
        '-DKF_HORIZON_TASK_SOURCE="'+(CORE/'APP/Src/estimator_task.c').as_posix()+'"',*definitions,
        '-include',str(project/'Generated/Inc/project_flight_config.h'),*['-I'+str(p) for p in includes],
        *map(str,sources),'-lm','-o',str(target)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=180)
    source_files=[*sources,CORE/'APP/Src/estimator_task.c',*KERNEL.glob('Inc/*.h')]
    receipt=dict(scope=('native generated configuration; CPU stress inputs at 5ms, not nominal-rate/board proof'
        if native else 'staged explicit mode2/Horizon30 unit; actual task/health/LoggerBus/wire; not generated mode2 gate'),
        native_configuration=native,
        command=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr,
        compiler=subprocess.check_output([compiler,'--version'],text=True),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        generated_header_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (project/'Generated/Inc').glob('*.h')})
    (output/'compile.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    assert run.returncode==0,run.stdout+run.stderr
    return target


@pytest.mark.parametrize('scenario',range(12),ids=['normal','source_switch','no_source','calibration_change',
    'imu_source_change','stored_corruption','invalid_latest_receipt','late','initial_body_fault',
    'barometer_only','barometer_invalid_latest_receipt','low_satellite_prepared_variance'])
def test_actual_kf_task_horizon_lifecycle_and_wire(executable,scenario):
    wire=executable.parent/f'case{scenario}.frames'
    command=[str(executable),str(scenario),str(wire)];run=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (executable.parent/f'case{scenario}.json').write_text(json.dumps(dict(command=command,exit_code=run.returncode,
        stdout=run.stdout,stderr=run.stderr),indent=2),encoding='utf-8')
    assert run.returncode==0,run.stdout+run.stderr
    assert wire.stat().st_size > 0
    assert re.search(r'kf_horizon_backend_actual: \d+ checks, 0 failures',run.stdout)
