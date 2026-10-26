"""Generated service + adapter + actual SX1281 driver; RF completion uses ToA.

No hardware timing/coverage claim. The shared legacy fixtures provide only
ports and unrelated subsystems; the new profile exercises its own wire.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(scope='module', params=['ss_tm.s.0_1', 'ss_tm.h.0_1'])
def tm_scheduler(request, tmp_path_factory):
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.project.telemetry import TelemetryProfile_Apply

    root = Path(__file__).resolve().parents[1]
    service = FccgService(root)
    model = service.Project_Open(root / 'tests/fixtures/radio_handshake.ssproject')
    model = TelemetryProfile_Apply(model, service.catalog, request.param)
    project = tmp_path_factory.mktemp(request.param.replace('.', '_')) / 'Flight_Controller'
    service.Project_Save(model, project, confirm_dangerous=True)
    build = tmp_path_factory.mktemp('tm_scheduler_build')
    # Existing mock subsystems use internal Air payload names. This test-only
    # alias selects the explicit new codec; target code includes its own name.
    (build / 'air_protocol.h').write_text('#include "ss_tm_protocol.h"\n', encoding='utf8')
    includes = [build, *[p for p in project.rglob('Inc') if 'build' not in p.parts]]
    includes += [project / p for p in ['System/User', 'Tests/Host', 'Modules/Src',
        'Devices/Telemetry/SX1281/Src', 'Middlewares/Third_Party/SX1280lib',
        'Generated/Src', 'Protocol/SS_TM/Legacy']]
    executable = build / 'tm_scheduler.exe'
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-DSYSTEM_TELEMETRY_TM_ENABLED=1U', '-DSILVERSTAR_AIR_LINK_ENABLED=1',
        '-DSYSTEM_TELEMETRY_TM_PROFILE=' + ('0U' if request.param == 'ss_tm.s.0_1' else '1U'),
        '-fanalyzer', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        '-include', str(project / 'Generated/Inc/project_flight_config.h')]
    command += ['-I' + str(path) for path in includes]
    command += [str(root / 'tests/fixtures/ss_tm_scheduler_host.c')]
    command += [str(project / path) for path in [
        'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c',
        'Protocol/SS_TM/Src/ss_tm_protocol.c', 'Protocol/SS_TM/Legacy/ss_tm_legacy.c',
        'Common/Src/silverstar_assert.c', 'System/Calibration/Src/system_calibration_correction.c']]
    command += ['-lm', '-o', str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize('scenario', ['normal', 'burst', 'landed', 'ack', 'observations', 'local_start', 'long', 'lost_start_ack', 'preflight'])
def test_generated_tm_scheduler(tm_scheduler, scenario):
    result = subprocess.run([str(tm_scheduler), scenario], capture_output=True, text=True,
                            encoding='utf8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '0 failures' in result.stdout
    print(result.stdout)
