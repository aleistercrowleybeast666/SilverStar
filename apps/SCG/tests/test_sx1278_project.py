from pathlib import Path
import re
import pytest

from silverstar_fccg.generator.render import MissionRadioProfileMacros_Render
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_data_contracts.objects import MissionRadioProfile_Decode
from silverstar_telemetry.plan import Sx1278AirtimeUs_Compute, TelemetryPlan_Get
from sx1278_project_fixture import Sx1278Project_Create


def test_sx1278_precise_airtime_and_preflight_budget():
    assert Sx1278AirtimeUs_Compute(61) == 121088
    assert Sx1278AirtimeUs_Compute(56) == 115968
    phy = dict(radio_family='sx127x',sf=7,bandwidth_hz=125000,coding_rate='4/5',preamble=16)
    assert TelemetryPlan_Get('S',**phy)['scheduler_fraction'] < 0.7
    assert TelemetryPlan_Get('S',preflight=True,control_ack_hz=0.5,**phy)['scheduler_fraction'] < 0.95
    assert TelemetryPlan_Get('S',preflight=True,control_ack_hz=1,**phy)['scheduler_fraction'] >= 0.95


def test_sx1278_normal_project_configuration_and_recorded_identity(builtin_catalog, tmp_path):
    model = Sx1278Project_Create(builtin_catalog,tmp_path)
    result = Project_Validate(model,builtin_catalog)
    assert result.valid, result.issues
    assert not GroundTargetIssues_Get(model,builtin_catalog)
    macros = MissionRadioProfileMacros_Render(model)
    body = bytes(int(item,16) for item in re.findall(r'0x([0-9A-F]{2})U',macros))
    assert body == bytes.fromhex('0201100001400ecf190748e801000510003d0011')
    snapshot = b'SSMS\x03\x00\x06\x00' + bytes(58) + body
    profile = MissionRadioProfile_Decode(snapshot)
    assert profile['family']=='sx127x' and profile['module']=='e32_400m20s'
    assert profile['bandwidth_hz']==125000 and profile['tx_power_dbm']==17
    for end in range(66,len(snapshot)):
        with pytest.raises(ValueError): MissionRadioProfile_Decode(snapshot[:end])
    with pytest.raises(ValueError): MissionRadioProfile_Decode(snapshot[:70]+b'\x02'+snapshot[71:])
