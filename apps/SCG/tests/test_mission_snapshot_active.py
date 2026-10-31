from pathlib import Path
import json
import re
import shutil
import subprocess
import pytest
from silverstar_fccg.app.service import FccgService


def test_generated_snapshot_active_serializer_preserves_storage_contract(tmp_path):
    compiler=shutil.which('gcc')
    if not compiler: pytest.skip('Host GCC unavailable')
    root=Path(__file__).resolve().parents[1]
    service=FccgService(root)
    project=tmp_path/'project'
    service.Project_Save(service.ReferenceProject_Create('ActiveSnapshotHost'),project,confirm_dangerous=True)
    source=(project/'Generated/project_sources.mk').read_text(encoding='utf8')
    config=(project/'FATFS/Target/ffconf.h').read_text(encoding='utf8')
    for header in ('main.h','stm32f4xx_hal.h','stm32f1xx_hal.h','bsp_driver_sd.h'):
        config=config.replace(f'#include "{header}"','')
    (tmp_path/'ffconf.h').write_text(config,encoding='utf8')
    includes=[tmp_path,project/'Tests/Host/storage_integrity',project/'Tests/Host',project/'Devices/Storage/SdSdioFatFs/Adapter/Src']
    block = source.split('C_INCLUDES +=',1)[1].split('\n\n',1)[0]
    includes += [project/x for x in block.replace('\\',' ').split()]
    # This harness exercises the calibration section of the untouched owning
    # translation unit. LTO removes unrelated public entry points on PE/COFF;
    # the full storage harness separately exercises Create and FinalStatusWrite.
    command=[compiler,'-std=c11','-O2','-flto','-fwhole-program','-Wall','-Wextra','-Werror','-pedantic',
        '-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1U',
        '-include',str(project/'Generated/Inc/project_flight_config.h'),*['-I'+str(x) for x in includes],
        str(root/'tests/fixtures/mission_snapshot_active_host.c'),str(project/'Common/Src/silverstar_assert.c'),
        '-o',str(tmp_path/'snapshot.exe')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/'compile.json').write_text(json.dumps(dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2),encoding='utf8')
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run([str(tmp_path/'snapshot.exe')],capture_output=True,text=True,timeout=15)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode==0,result.stdout+result.stderr
