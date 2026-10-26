"""BMI088 binding negatives use injected tool bytes; actual ARM evidence is separate."""
from pathlib import Path

import pytest
from test_stack_budget import stacks


def BindingFixture_Create(root, monkeypatch, mutation):
    builtin = Path(__file__).resolve().parents[1] / 'plugins/builtin'
    paths = [
        'Devices/SensorBus/Src/sensor_imu.c',
        'Devices/SensorBus/Src/sensor_register_bus.c',
        'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c',
        'Devices/IMU/BMI088/Adapter/Src/bmi088_instance.c',
        'Devices/IMU/BMI088/Src/bmi088_device.c',
    ]
    for relative in [*paths, 'Devices/SensorBus/Inc/sensor_imu.h']:
        plugin = 'silverstar_device_imu_bmi088' if '/BMI088/' in relative else 'silverstar_sensor_register_bus'
        text = (builtin / plugin / 'payload' / relative).read_text(encoding='utf8')
        if mutation == 'profile' and relative.endswith('bmi088_device.c'):
            text = text.replace('.frame_read = Bmi088_FrameRead', '.frame_read = UnknownCallback')
        if mutation == 'bus_write' and relative.endswith('sensor_imu_adapter.c'):
            text = text.replace('bus.read = SensorImuAdapter_ReadRegister;', 'bus.read = UnknownCallback;')
        if mutation == 'layout' and relative.endswith('sensor_imu.h'):
            text = text.replace('SensorImuPrepare prepare;', 'uint32_t unexpected; SensorImuPrepare prepare;')
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding='utf8')
    resolved = {'SensorImu_ProcessConfigure': 'Bmi088_Prepare', 'SensorImu_Read': 'Bmi088_FrameRead',
                'SensorImu_Verify': None, 'SensorRegister_Read': 'SensorImuAdapter_ReadRegister',
                'SensorRegister_Write': 'SensorImuAdapter_WriteRegister'}
    instructions = {name: [('blx', 'r3')] for name in resolved}
    for name in resolved.values():
        if name:
            instructions[name] = [('bx', 'lr')]
    instructions['Bmi088_ProfileGet'] = [('.word', '0x08001000')]
    edges = {name: set() for name in instructions}
    edges.update({'SensorImuAdapter_PrepareI2c': {'SensorImu_Init'},
                  'SensorImuAdapter_InitI2c': {'SensorImuAdapter_PrepareI2c'},
                  'Bmi088ImuInstance_Init': {'SensorImuAdapter_InitI2c', 'Bmi088_ProfileGet'}})
    if mutation == 'caller':
        edges['UnreviewedCaller'] = {'SensorImu_Init'}
    if mutation == 'extra_site':
        instructions['SensorImu_Read'].append(('blx', 'r2'))
    if mutation == 'getter':
        instructions['Bmi088_ProfileGet'] = [('.word', '0x08001004')]
    if mutation == 'target':
        del instructions['Bmi088_FrameRead']
    raw = bytes(16) + (0x08002001).to_bytes(4, 'little') + (0x08003001).to_bytes(4, 'little') + bytes(4)
    if mutation == 'slot':
        raw = raw[:16] + (0x08003001).to_bytes(4, 'little') + raw[20:]
    if mutation == 'nonnull_extra':
        raw = raw[:24] + (0x08002001).to_bytes(4, 'little')
    # objdump prints groups of 4 bytes, not one unbroken hex string.
    output = 'file format elf32-littlearm\n'
    for offset in (0, 16):
        part = raw[offset:offset+16]
        output += f' {0x08001000+offset:x} ' + ' '.join(part[i:i+4].hex() for i in range(0,len(part),4)) + '\n'
    monkeypatch.setattr(stacks, 'Command_Read', lambda *_: output)
    kind = 'b' if mutation == 'writable' else 'r'
    size = '0000001c' if mutation == 'size' else '000000bc'
    nm = f'08001000 {size} {kind} s_profile\n08002000 00000008 t Bmi088_Prepare\n08003000 00000008 t Bmi088_FrameRead\n'
    return paths, instructions, edges, set(resolved), nm


def test_bmi_immutable_profile_resolves_two_callbacks_and_guarded_null(tmp_path, monkeypatch):
    args = BindingFixture_Create(tmp_path, monkeypatch, None)
    result = stacks.BmiCallbackBindings_Resolve(tmp_path, *args, 'unused-', tmp_path/'fixture.elf')
    assert result[0]['null_callbacks'] == ['extra_verify']
    assert args[2]['SensorImu_Read'] == {'Bmi088_FrameRead'}
    assert not args[3]


@pytest.mark.parametrize('mutation', ['profile','bus_write','layout','caller','extra_site','getter',
                                    'target','slot','nonnull_extra','writable','size'])
def test_bmi_changed_input_or_linked_pointer_rejects(tmp_path, monkeypatch, mutation):
    args = BindingFixture_Create(tmp_path, monkeypatch, mutation)
    with pytest.raises(ValueError):
        stacks.BmiCallbackBindings_Resolve(tmp_path, *args, 'unused-', tmp_path/'fixture.elf')
