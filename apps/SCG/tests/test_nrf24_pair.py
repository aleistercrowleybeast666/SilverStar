from dataclasses import replace
from pathlib import Path
import json
import shutil
import subprocess

import pytest

from silverstar_fccg.project.nrf24 import NRF24_PLUGIN, Nrf24Link_Validate
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import AirLinkHeader_Render
from silverstar_fccg.project.air_link import AirLinkIssues_Get


def Nrf24Model_Get(catalog):
    model = ReferenceProject_Create("Nrf24Pair", catalog=catalog)
    model.device_instances = [replace(instance, plugin=NRF24_PLUGIN, module_variant="nrf24l01p", tx_power_dbm=0)
        if instance.instance_id == model.air_link.flight_radio_instance else instance for instance in model.device_instances]
    model.air_link = replace(model.air_link, radio_technology="esb", radio_family="nrf24", phy_mode="esb",
        nrf24={"data_rate_kbps": 1000, "address": "E7E7E7E701", "retry_delay_us": 1000, "retry_count": 3})
    return model


def test_nrf24_contract_and_legacy_serialization(builtin_catalog):
    original = ReferenceProject_Create("Legacy", catalog=builtin_catalog)
    assert "nrf24" not in original.Dictionary_Get()["air_link"]
    assert ProjectModel_Parse(original.Dictionary_Get()).Dictionary_Get() == original.Dictionary_Get()
    model = Nrf24Model_Get(builtin_catalog)
    manifest = builtin_catalog.Component_Get(NRF24_PLUGIN)
    assert manifest.radio.maximum_payload == 32 and manifest.radio.logical_mtu == 61
    assert manifest.radio.bandwidths_hz == manifest.radio.spreading_factors == ()
    assert {r.name for r in manifest.resource_requirements} == {"radio_bus", "radio_ce", "radio_csn", "time"}
    assert not AirLinkIssues_Get(model, builtin_catalog)
    restored = ProjectModel_Parse(model.Dictionary_Get())
    assert restored.air_link.nrf24 == model.air_link.nrf24
    header = AirLinkHeader_Render(model)
    assert "AIR_LINK_NRF24_RF_SETUP 0x06U" in header and "AIR_LINK_PACKET_MTU 61U" in header
    assert "SPREADING" not in header and "BANDWIDTH" not in header and "SX128" not in header


@pytest.mark.parametrize("field,value", [("data_rate_kbps", True), ("data_rate_kbps", 500),
    ("address", "$(unsafe)"), ("address", "FFFFFFFFFF"), ("retry_count", 16), ("retry_delay_us", 250)])
def test_nrf24_invalid_parameters(builtin_catalog, field, value):
    model = Nrf24Model_Get(builtin_catalog)
    model.air_link = replace(model.air_link, nrf24={**model.air_link.nrf24, field: value})
    with pytest.raises(ValueError): Nrf24Link_Validate(model.air_link)
    assert AirLinkIssues_Get(model, builtin_catalog)


def test_nrf24_pin_requirements_and_pair_boundary(builtin_catalog):
    from silverstar_fccg.project.resources import ResourceAssignments_Resolve
    from silverstar_fccg.project.air_link import GroundTargetIssues_Get
    model = Nrf24Model_Get(builtin_catalog)
    owner = model.air_link.flight_radio_instance
    model.resource_assignments = {key:value for key,value in model.resource_assignments.items() if not key.startswith(owner + ':')}
    model.resource_assignments.update({owner+':'+name:identity for name,identity in {
        'radio_bus':'PLATFORM_SPI_1','radio_csn':'PLATFORM_GPIO_0','radio_ce':'PLATFORM_GPIO_1','time':'PLATFORM_TIME_1'}.items()})
    # Existing SX RESET output idles high; CE must idle low on the actual board.
    assert any('radio_ce' in error for error in ResourceAssignments_Resolve(model,builtin_catalog).errors)
    model.ground_target = replace(model.ground_target, enabled=True, radio_plugin=NRF24_PLUGIN,
        module_variant='nrf24l01p', tx_power_dbm=0)
    assert not any(issue.code == 'GROUND_NRF24_METRICS_CONTRACT_PENDING' for issue in GroundTargetIssues_Get(model,builtin_catalog))
    model.ground_target = replace(model.ground_target, radio_plugin='silverstar.device.telemetry.sx1281.lora', module_variant='sx1281')
    assert GroundTargetIssues_Get(model,builtin_catalog)
    model.device_instances.append(replace(model.device_instances[0],instance_id='extra_radio',plugin=NRF24_PLUGIN))
    assert AirLinkIssues_Get(model,builtin_catalog)


def test_nrf24_ui_real_fields_and_invalid_address(qapp,builtin_catalog):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.ui.pages.targets import AirLinkPage
    page=AirLinkPage(Translator('en_US'))
    model=Nrf24Model_Get(builtin_catalog)
    page.Configuration_Set(model.air_link,())
    assert page._air_form.isRowVisible(page.nrf24_fields['address'])
    assert not page._air_form.isRowVisible(page.fields['spreading_factor'])
    changes=[]
    page.configurationChanged.connect(lambda field,value:changes.append((field,value)))
    page._Nrf24_Change('address','XXXXXXXXXX')
    assert not changes
    page._Nrf24_Change('data_rate_kbps',250)
    assert changes == [('nrf24',{**model.air_link.nrf24,'data_rate_kbps':250})]
    page.Configuration_Set(ReferenceProject_Create('LegacyUI',catalog=builtin_catalog).air_link,())
    assert not page._air_form.isRowVisible(page.nrf24_fields['address'])
    assert page._air_form.isRowVisible(page.fields['spreading_factor'])


def Nrf24Host_Compile(tmp_path_factory,slow=False):
    gcc = shutil.which("gcc")
    assert gcc, "Host GCC required for NRF24 checkpoint"
    root = Path(__file__).resolve().parents[1]
    work = tmp_path_factory.mktemp("nrf24-host")
    (work / "project_resources.h").write_text('''#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_NRF24_INSTANCE_COUNT 1U
#define PROJECT_NRF24_INSTANCE_COUNT_MAX 1U
typedef struct { PlatformSpiId spi; PlatformGpioId csn; PlatformGpioId ce; PlatformTimeId time; } ProjectNrf24Resources;
SystemDeviceResult ProjectNrf24Resources_Get(uint8_t instance, ProjectNrf24Resources *resources);
''', encoding="utf8")
    (work / "air_link_config.h").write_text('''#define AIR_LINK_NRF24_CHANNEL 73U
#define AIR_LINK_NRF24_RF_SETUP 0x06U
#define AIR_LINK_NRF24_ADDRESS_BYTES {0xE7U,0xE7U,0xE7U,0xE7U,0x01U}
#define AIR_LINK_NRF24_RETRY_SETUP 0x33U
#define AIR_LINK_NRF24_DATA_RATE_KBPS 1000U
#define AIR_LINK_PACKET_MTU 61U
''', encoding="utf8")
    if slow:
        header=work/'air_link_config.h'
        header.write_text(header.read_text(encoding='utf8').replace('0x06U','0x26U').replace('0x33U','0xFFU').replace('1000U','250U'),encoding='utf8')
    (work/'ground_radio_config.h').write_text("#include \"platform_gpio.h\"\n#define GROUND_ACTIVITY_ENABLED 0U\n#define GROUND_ACTIVITY_TX_GPIO PLATFORM_GPIO_COUNT\n#define GROUND_ACTIVITY_RX_GPIO PLATFORM_GPIO_COUNT\n#define GROUND_ACTIVITY_TX_ACTIVE_HIGH 0U\n#define GROUND_ACTIVITY_RX_ACTIVE_HIGH 0U\n#define GROUND_ACTIVITY_PULSE_MS 40U\n",encoding='utf8')
    ground=root/'plugins/builtin/silverstar_core_ground_0_1_0/payload/Ground'
    radio = root / "plugins/builtin/silverstar_device_telemetry_nrf24l01p/payload/Devices/Telemetry/NRF24L01P"
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    air = root / "plugins/builtin/silverstar_protocol_telemetry_air_m0/payload/Protocol"
    includes = [work, radio / "Inc", radio / "Adapter/Inc", core / "Common/Inc", core / "Interfaces/Inc",
        root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",air / "Inc",ground/"Core/Inc",ground/"Protocol/Inc"]
    executable = work / "nrf24.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        *("-I" + str(p) for p in includes), str(root / "tests/fixtures/nrf24_host.c"),
        str(radio / "Src/nrf24_fragment.c"), str(radio / "Src/nrf24_device.c"),
        str(radio / "Adapter/Src/nrf24_telemetry_adapter.c"), str(air / "Src/air_protocol.c"),
        str(ground/"Radio/Src/ground_radio_nrf24.c"),str(ground/"Radio/Src/ground_radio_activity.c"),
        str(ground/"Protocol/Src/gsp_min_protocol.c"),str(ground/"Protocol/Src/protocol_crc16.c"), "-o", str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (work / "compile.json").write_text(json.dumps({"command": command, "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr}, indent=2), encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    return executable, work


@pytest.fixture(scope="module")
def nrf24_host(tmp_path_factory):
    return Nrf24Host_Compile(tmp_path_factory)


@pytest.fixture(scope="module")
def nrf24_slow_host(tmp_path_factory):
    return Nrf24Host_Compile(tmp_path_factory,slow=True)


def test_nrf24_air_codec_golden_bytes(nrf24_host):
    executable,work=nrf24_host
    result=subprocess.run([str(executable),'air_codec'],capture_output=True,text=True,timeout=10)
    (work/'air_codec.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode == 0,result.stdout+result.stderr
    golden=dict(line.split() for line in result.stdout.splitlines() if line.startswith('GOLDEN_'))
    assert golden == {
        'GOLDEN_FLIGHT_STATE':'104204030201'+'00'*44,
        'GOLDEN_CAPABILITY':'12060001010910d007',
        'GOLDEN_CMD':'300705000000000600',
        'GOLDEN_ACK':'400807050004030201'}


@pytest.mark.parametrize("scenario", ["fragment", "tx", "rx_fault", "feature", "absent", "recovery_wrap", "collision_limit", "late_completion", "slow_fragment_stream", "fault_publication", "init_gpio_fault", "late_max_rt", "conflicting_terminal", "deadline", "sequence_wrap", "ground_adapter"])
def test_nrf24_host(nrf24_host, scenario):
    executable, work = nrf24_host
    result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=10)
    (work / (scenario + ".log")).write_text(result.stdout + result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_nrf24_slowest_valid_configuration(nrf24_slow_host):
    executable,work=nrf24_slow_host
    result=subprocess.run([str(executable),'slow_configuration'],capture_output=True,text=True,timeout=10)
    (work/'slow_configuration.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('plugin',['silverstar_device_storage_sd_sdio_fatfs','silverstar_device_storage_sd_sdio_fatfs_f1'])
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


@pytest.mark.parametrize('slow',[False,True])
def test_nrf24_independent_peer_golden_exchange(request,slow):
    executable,work=request.getfixturevalue('nrf24_slow_host' if slow else 'nrf24_host')
    frames={'flight_state':'104204030201'+'00'*44,'capability':'12060001010910d007','cmd':'300705000000000600','ack':'400807050004030201','mtu61':'10'+'55'*60}
    for name,frame in frames.items():
        send=subprocess.run([str(executable),'pair_slow_send' if slow else 'pair_send',frame],capture_output=True,text=True,timeout=10)
        assert send.returncode==0,send.stdout+send.stderr
        packets=[line.split()[1] for line in send.stdout.splitlines() if line.startswith('WIRE ')]
        assert len(packets)==(len(bytes.fromhex(frame))+21)//22 and all(len(bytes.fromhex(p))<=32 for p in packets)
        # Receiver is a fresh process with its own static driver/RX assembly.
        # Unique packets arrive 200ms apart; three fragments span 400ms.
        receive=subprocess.run([str(executable),'pair_receive',','.join(packets)],capture_output=True,text=True,timeout=10)
        (work/('pair_'+str(slow)+'_'+name+'.json')).write_text(json.dumps({'sender':{'exit':send.returncode,'stdout':send.stdout,'stderr':send.stderr},'receiver':{'exit':receive.returncode,'stdout':receive.stdout,'stderr':receive.stderr},'air':frame}),encoding='utf8')
        assert receive.returncode==0,receive.stdout+receive.stderr
        assert receive.stdout.strip()=='RECEIVED '+frame


def test_storage_profile_generated_legacy_golden_bytes(builtin_catalog):
    from silverstar_fccg.generator.render import MissionRadioProfileMacros_Render
    import struct,re
    model=ReferenceProject_Create('LegacyProfile',catalog=builtin_catalog)
    link=model.air_link
    from silverstar_fccg.project.radio_variants import FlightRadioConfiguration_Get
    power=FlightRadioConfiguration_Get(model,model.DeviceInstance_Get(link.flight_radio_instance))[1]
    expected=struct.pack('<IBIBHHb',link.frequency_hz,link.spreading_factor,link.bandwidth_hz,int(link.coding_rate[-1]),link.preamble_symbols,link.packet_mtu,power)
    header=MissionRadioProfileMacros_Render(model)
    values=bytes(int(value,16) for value in re.findall(r'0x([0-9A-F]{2})U',header))
    assert len(values)==15 and values==expected and 'SCHEMA 2U' in header
    nrf_model=Nrf24Model_Get(builtin_catalog)
    header=MissionRadioProfileMacros_Render(nrf_model)
    values=bytes(int(value,16) for value in re.findall(r'0x([0-9A-F]{2})U',header))
    assert values==bytes.fromhex('01010e00490100e7e7e7e701030302203d01') and 'SCHEMA 3U' in header
