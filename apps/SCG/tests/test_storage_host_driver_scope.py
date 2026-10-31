"""Keep blocking-driver inputs out of the delayed-DMA evidence model."""
import importlib.util
from pathlib import Path

import pytest


def _Runner_Load():
    path = Path(__file__).resolve().parents[1] / (
        'plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/'
        'storage_integrity/run_storage_integrity.py')
    spec = importlib.util.spec_from_file_location('storage_scope', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('blocking', [True, False])
def test_actual_transfer_api_controls_host_model_admission(tmp_path, monkeypatch, blocking):
    module = _Runner_Load()
    path = tmp_path/'HardwareGenerated/STM32CubeMX/FATFS/Target/sd_diskio.c'
    path.parent.mkdir(parents=True)
    api = 'BSP_SD_ReadBlocks' if blocking else 'BSP_SD_ReadBlocks_DMA'
    source = '/* Historical BSP_SD_ReadBlocks(buffer, 0, 1, 1); */\n' + api + '(buffer, 0, 1);\n'
    path.write_text(source)
    (path.parent/'ffconf.h').write_text('#define _FS_REENTRANT 0\n')
    generated = tmp_path/'Generated'
    generated.mkdir()
    (generated/'project_sources.mk').write_text('C_SOURCES += \\\n  ' + path.relative_to(tmp_path).as_posix() + '\n')
    calls = []
    def compiler(*args, **kwargs):
        calls.append(args)
        raise RuntimeError('synthetic compiler boundary reached')
    monkeypatch.setattr(module.subprocess, 'run', compiler)
    if blocking:
        with pytest.raises(ValueError, match='blocking BSP transfers'):
            module.StorageIntegrity_Run(tmp_path, 'unused compiler')
        assert not calls
    else:
        with pytest.raises(RuntimeError, match='compiler boundary reached'):
            module.StorageIntegrity_Run(tmp_path, 'unused compiler')
        assert len(calls) == 1
    assert path.read_text() == source
