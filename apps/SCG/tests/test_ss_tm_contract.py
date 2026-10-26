import json
from pathlib import Path
import subprocess

import pytest

from silverstar_telemetry.codec import Frame_Encode, Frame_Decode, TelemetryProtocolError, CONTRACT
from test_joint_sensor_library import _Compiler_Get


def test_machine_contract_mirror_and_lengths(workspace_root):
    repository = workspace_root.parents[1]
    contract = repository / 'contracts/ss_tm_v0_1.json'
    mirror = workspace_root / 'src/silverstar_telemetry/data/ss_tm_v0_1.json'
    assert contract.read_bytes() == mirror.read_bytes()
    assert json.loads(contract.read_text(encoding='utf8')) == CONTRACT
    assert max(row['length'] for row in CONTRACT['messages'].values()) <= 61
    assert CONTRACT['messages']['NAV_HEALTH']['type'] == 0x17


def test_actual_c_and_python_golden_vectors(tmp_path, workspace_root):
    native = workspace_root / 'plugins/builtin/silverstar_protocol_telemetry_ss_tm/payload/Protocol/SS_TM'
    common = workspace_root / 'plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc'
    binary = tmp_path / 'ss_tm_codec.exe'
    command = [_Compiler_Get(), '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wconversion',
               '-Wsign-conversion', '-Wshadow', '-Wvla', '-fanalyzer',
               '-I'+str(workspace_root/'plugins/builtin/silverstar_core_0_1_0/payload/Modules/Inc'),
               '-I'+str(native/'Inc'), '-I'+str(native/'Legacy'), '-I'+str(common),
               str(native/'Legacy/ss_tm_legacy.c'), str(native/'Src/ss_tm_protocol.c'),
               str(workspace_root/'tests/fixtures/ss_tm_codec_host.c'), '-lm', '-o', str(binary)]
    build = subprocess.run(command, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    expected = []
    values = [
        ('POSITION', dict(latitude_e7=0, longitude_e7=1799999999, ellipsoid_height_mm=-12000,
                          sample_age_ms=12345, horizontal_accuracy_cm=65534, position_flags=15, satellite_count=12)),
        ('HEALTH', dict(battery_mv=0, battery_age_ds=65534, known_mask=0x7FF, fault_mask=0x42)),
        ('ACK', dict(acked_sequence=0xBEEF, command_id=1, result=0, time_ms=123456)),
        ('EVENT', dict(event_id=0x10203040, occurred_us=123456789, event_code=0x100,
                       stage_id=0x11223344, instance_id=2, transaction_id=65534, arg0=7, arg1=9)),
    ]
    for profile in ('S', 'H'):
        for sequence, (name, fields) in enumerate(values):
            frame = Frame_Encode(profile, name, sequence, 0x12345678, fields)
            assert Frame_Decode(frame).values == fields
            expected.append(frame.hex())
    assert run.stdout.splitlines() == expected


@pytest.mark.parametrize('mutation', ['length', 'version', 'session', 'mask', 'nonfinite'])
def test_bad_wire_data_is_rejected(mutation):
    values = dict(battery_mv=65535, battery_age_ds=65535, known_mask=0, fault_mask=0)
    packet = bytearray(Frame_Encode('S', 'HEALTH', 65535, 1, values))
    if mutation == 'length': packet.pop()
    elif mutation == 'version': packet[0] = 2
    elif mutation == 'session': packet[4:8] = bytes(4)
    elif mutation == 'mask': packet[14] = 1
    else:
        with pytest.raises(TelemetryProtocolError):
            Frame_Encode('S', 'FLIGHT_DATA', 1, 1, dict(time_ms=0, accel_i16=(0,0,0),
                gyro_i16=(0,0,0), quaternion_q15=(0,0,0,0), velocity_enu_mps=(float('nan'),0,0), position_enu_m=(0,0,0)))
        return
    with pytest.raises(TelemetryProtocolError): Frame_Decode(bytes(packet))


def test_installed_machine_contracts_match_the_repository():
    from importlib.resources import files
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for package, name in (('silverstar_telemetry', 'ss_tm_v0_1.json'),
                           ('silverstar_data_contracts', 'persistent_objects_v1.json')):
        assert (root/'contracts'/name).read_bytes() == files(package).joinpath('data', name).read_bytes()
