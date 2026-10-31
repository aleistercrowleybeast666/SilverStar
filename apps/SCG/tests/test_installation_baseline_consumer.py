"""Owning C CAL collector/getter host integration; hardware facades are synthetic."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("active", [False, True], ids=["baseline", "active_transaction"])
def test_owning_baseline_consumer_and_absolute_task_replacement(tmp_path, active):
    compiler = shutil.which('gcc')
    assert compiler is not None, 'Host GCC is required'
    root = Path(__file__).resolve().parents[1]
    builtin = root / 'plugins/builtin'
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    service = FccgService(root)
    model = service.ReferenceProject_Create('InstallationBaselineConsumer')
    if active:
        from dataclasses import replace
        from silverstar_fccg.project.logging import LoggingProfile_Reconcile
        model.base_components.append('silverstar.installation.capture')
        model.device_instances=[replace(item,profile='jy901b_mag_capture')
            if item.plugin=='silverstar.device.imu.jy901b' else item for item in model.device_instances]
        LoggingProfile_Reconcile(model,service.catalog)
    core = tmp_path / 'generated'
    service.Project_Save(model, core, confirm_dangerous=True)
    graph = SourceGraph_Resolve(model, service.catalog)
    calibration = core / 'Algorithm/Calibration'
    include_dirs = [core / path for path in graph.include_dirs] + [core / 'Tests/Host']
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
        '-include', str(core / 'Generated/Inc/project_flight_config.h'),
        '-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1U', '-DSYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK=6U']
    command += ['-I' + str(path) for path in include_dirs]
    sources = [root / ('tests/fixtures/installation_active_consumer.c' if active else 'tests/fixtures/installation_baseline_consumer.c'),
        core / 'System/Calibration/Src/system_calibration.c',
        core / 'System/Calibration/Src/system_calibration_correction.c',
        calibration / 'Src/imu_six_face_calibration.c', core / 'Common/Src/silverstar_assert.c']
    if active:
        owner = builtin / 'silverstar_installation_capture/payload'
        module = owner / 'Modules/InstallationCapture'
        command += ['-I' + str(module / 'Inc'), '-I' + str(module / 'Src'),
                    '-I' + str(owner / 'ThirdParty/InstallationCapture'),
                    '-I' + str(builtin / 'silverstar_device_storage_sd_sdio_fatfs/payload/Devices/Storage/SdSdioFatFs/Adapter/Src')]
        sources += [module / 'Src/capture_primitives.c',module / 'Src/capture_info.c',
                    core / 'Tests/Host/installation_capture_host_port.c',
                    owner / 'ThirdParty/InstallationCapture/ryu/d2s.c',
                    core / 'Common/Src/common_format.c']
    executable = tmp_path / 'baseline.exe' 
    command += [str(path) for path in sources] + ['-lm', '-o', str(executable)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    (tmp_path / 'compile.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr}, indent=2), encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], text=True, capture_output=True, timeout=30)
    (tmp_path / 'run.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
