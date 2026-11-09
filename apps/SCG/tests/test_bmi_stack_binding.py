"""BMI088 binding negatives use injected tool bytes; actual ARM evidence is separate."""
from pathlib import Path

import pytest
from test_stack_budget import stacks


def BindingFixture_Create(root, monkeypatch, mutation, *, synchronized=False):
    builtin = Path(__file__).resolve().parents[1] / 'plugins/builtin'
    paths = [
        'Devices/SensorBus/Src/sensor_imu.c',
        'Devices/SensorBus/Src/sensor_register_bus.c',
        'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c',
        'Devices/IMU/BMI088/Adapter/Src/bmi088_instance.c',
        'Devices/IMU/BMI088/Src/bmi088_device.c',
    ]
    profile_name, instance_name, getter = 'Bmi088', 'Bmi088ImuInstance_Init', 'Bmi088_ProfileGet'
    if synchronized:
        paths[-2:] = [
            'Devices/IMU/BMI088_SYNC400/Adapter/Src/bmi088_sync400_instance.c',
            'Devices/SensorBus/Src/sensor_bmi088_sync.c',
            'Devices/IMU/BMI088_SYNC400/Src/bmi088_sync400_device.c',
        ]
        profile_name, instance_name, getter = ('SensorBmi088Sync', 'Bmi088Sync400ImuInstance_Init',
                                             'SensorBmi088Sync_ProfileGet')
    for relative in [*paths, 'Devices/SensorBus/Inc/sensor_imu.h']:
        plugin = 'silverstar_device_imu_bmi088' if '/IMU/' in relative else 'silverstar_sensor_register_bus'
        text = (builtin / plugin / 'payload' / relative).read_text(encoding='utf8')
        if mutation == 'profile':
            text = text.replace('.frame_read = ' + profile_name + '_FrameRead', '.frame_read = UnknownCallback')
        if mutation == 'bus_write' and relative.endswith('sensor_imu_adapter.c'):
            text = text.replace('bus.read = SensorImuAdapter_ReadRegister;', 'bus.read = UnknownCallback;')
        if mutation == 'layout' and relative.endswith('sensor_imu.h'):
            text = text.replace('SensorImuPrepare prepare;', 'uint32_t unexpected; SensorImuPrepare prepare;')
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding='utf8')
    resolved = {'SensorImu_ProcessConfigure': profile_name + '_Prepare', 'SensorImu_Read': profile_name + '_FrameRead',
                'SensorImu_Verify': profile_name + '_Readback' if synchronized else None,
                'SensorRegister_Read': 'SensorImuAdapter_ReadRegister',
                'SensorRegister_Write': 'SensorImuAdapter_WriteRegister'}
    instructions = {name: [('blx', 'r3')] for name in resolved}
    for name in resolved.values():
        if name:
            instructions[name] = [('bx', 'lr')]
    instructions[getter] = [('.word', '0x08001000')]
    edges = {name: set() for name in instructions}
    edges.update({'SensorImuAdapter_PrepareI2c': {'SensorImu_Init'},
                  'SensorImuAdapter_InitI2c': {'SensorImuAdapter_PrepareI2c'},
                  instance_name: {'SensorImuAdapter_InitI2c', 'Bmi088Sync400_ProfileGet' if synchronized else getter}})
    if synchronized:
        edges['Bmi088Sync400_ProfileGet'] = {getter}
    if mutation == 'caller':
        edges['UnreviewedCaller'] = {'SensorImu_Init'}
    if mutation == 'extra_site':
        instructions['SensorImu_Read'].append(('blx', 'r2'))
    if mutation == 'getter':
        instructions[getter] = [('.word', '0x08001004')]
    if mutation == 'target':
        del instructions[profile_name + '_FrameRead']
    raw = bytes(16) + (0x08002001).to_bytes(4, 'little') + (0x08003001).to_bytes(4, 'little') + (0x08004001 if synchronized else 0).to_bytes(4, 'little')
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
    nm = (f'08001000 {size} {kind} ' + ('s_sync_profile' if synchronized else 's_profile') +
          f'\n08002000 00000008 t {profile_name}_Prepare\n08003000 00000008 t {profile_name}_FrameRead\n')
    if synchronized:
        nm += '08004000 00000008 t SensorBmi088Sync_Readback\n'
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


def test_sync400_exact_i2c_profile_keeps_real_readback_call(tmp_path, monkeypatch):
    args = BindingFixture_Create(tmp_path, monkeypatch, None, synchronized=True)
    result = stacks.BmiCallbackBindings_Resolve(tmp_path, *args, 'unused-', tmp_path/'fixture.elf')
    assert result[0]['kind'] == 'immutable_bmi088_sync400_i2c'
    assert result[0]['null_callbacks'] == []
    assert args[2]['SensorImu_Verify'] == {'SensorBmi088Sync_Readback'}
    assert not args[3]


@pytest.mark.parametrize('mutation', ['profile','bus_write','layout','caller','extra_site','getter',
                                    'target','slot','nonnull_extra','writable','size'])
def test_sync400_changed_input_or_linked_pointer_rejects(tmp_path, monkeypatch, mutation):
    args = BindingFixture_Create(tmp_path, monkeypatch, mutation, synchronized=True)
    with pytest.raises(ValueError):
        stacks.BmiCallbackBindings_Resolve(tmp_path, *args, 'unused-', tmp_path/'fixture.elf')


@pytest.mark.parametrize('mutation', ['mixed_raw', 'mixed_spi', 'wrapper_caller', 'wrapper_source'])
def test_sync400_cannot_admit_another_profile_origin(tmp_path, monkeypatch, mutation):
    args = BindingFixture_Create(tmp_path, monkeypatch, None, synchronized=True)
    if mutation == 'mixed_raw':
        args[0].append('Devices/IMU/BMI088/Src/bmi088_device.c')
    elif mutation == 'mixed_spi':
        args[0].append('Devices/IMU/BMI088_SPI/Src/bmi088_spi_device.c')
    elif mutation == 'wrapper_caller':
        args[2]['UnexpectedProfileFactory'] = {'SensorBmi088Sync_ProfileGet'}
    else:
        (tmp_path / 'Devices/IMU/BMI088_SYNC400/Src/bmi088_sync400_device.c').write_text(
            'const SensorImuProfile *Bmi088Sync400_ProfileGet(void) { return arbitrary; }')
    with pytest.raises(ValueError):
        stacks.BmiCallbackBindings_Resolve(tmp_path, *args, 'unused-', tmp_path/'fixture.elf')
