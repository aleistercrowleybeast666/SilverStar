"""NRF is a historical recorded profile, never an active radio backend."""
from pathlib import Path
from dataclasses import replace
import json
import shutil
import subprocess
import pytest
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_nrf24_active_generation_is_explicitly_rejected(builtin_catalog):
    from silverstar_fccg.generator.render import AirLinkHeader_Render, MissionRadioProfileMacros_Render
    from silverstar_fccg.project.air_link import AirLinkIssues_Get
    model = ReferenceProject_Create('RemovedRadio', catalog=builtin_catalog)
    model.air_link = replace(model.air_link, radio_family='nrf24', radio_technology='esb', phy_mode='esb')
    assert any(issue.code == 'RADIO_SUPPORT_REMOVED' for issue in AirLinkIssues_Get(model,builtin_catalog))
    for render in (AirLinkHeader_Render, MissionRadioProfileMacros_Render):
        with pytest.raises(ValueError, match='NRF24 active generation was removed'):
            render(model)
    assert model.air_link.radio_family == 'nrf24'
    with pytest.raises(ValueError):
        builtin_catalog.Component_Get('silverstar.device.telemetry.nrf24l01p')


@pytest.mark.parametrize('plugin',['silverstar_device_storage_sd_sdio_fatfs','silverstar_device_storage_sd_sdio_fatfs_f1','silverstar_device_storage_sdmmc_fatfs_h7'])
def test_mission_radio_profile_legacy_and_typed_no_partial_publish(tmp_path,plugin):
    root=Path(__file__).resolve().parents[1]
    storage=root/'plugins/builtin'/plugin/'payload/Devices/Storage/SdSdioFatFs'
    executable=tmp_path/'profile.exe'
    command=[shutil.which('gcc'),'-std=c11','-Wall','-Wextra','-Werror','-pedantic','-I'+str(storage/'Inc'),str(storage/'Src/mission_radio_profile.c'),str(root/'tests/fixtures/mission_radio_profile_host.c'),'-o',str(executable)]
    compile_result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/'compile.json').write_text(json.dumps({'command':command,'exit':compile_result.returncode,'stdout':compile_result.stdout,'stderr':compile_result.stderr}),encoding='utf8')
    assert compile_result.returncode==0,compile_result.stderr
    result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=10)
    (tmp_path/'profile.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode==0,result.stderr


