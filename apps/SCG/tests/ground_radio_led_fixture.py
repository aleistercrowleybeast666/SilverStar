"""Synthetic F103 multi-radio CubeMX input; never hardware acceptance evidence."""
from pathlib import Path
from dataclasses import replace
import shutil

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.model import GroundRadioConfiguration, GroundRadioSelection_Apply
from test_round2_targets import _GroundBoardProject_Get


def GroundMultiFixture_Create(catalog, root: Path, count: int = 2, owner: int = 0,
                              activity_led: bool = False):
    model = _GroundBoardProject_Get(catalog)
    source = catalog.Component_Get(model.ground_target.board).payload_root
    input_root = root / 'synthetic_input'
    input_root.mkdir(parents=True)
    shutil.copytree(source / 'Core', input_root / 'Core')
    family = catalog.Component_Get('silverstar.mcu_family.stm32f1')
    shutil.copytree(family.payload_root / 'Drivers', input_root / 'Drivers')
    mcu = catalog.Component_Get(model.ground_target.mcu)
    for relative in mcu.build.asm_sources:
        shutil.copyfile(mcu.payload_root / relative, input_root / Path(relative).name)
    shutil.copyfile(mcu.payload_root / mcu.build.linker_script,
                    input_root / Path(mcu.build.linker_script).name)
    ioc = (source / 'Ground_Station0.5.ioc').read_text(encoding='utf-8')
    main = (input_root / 'Core/Inc/main.h').read_text(encoding='utf-8')
    gpio = (input_root / 'Core/Src/gpio.c').read_text(encoding='utf-8')
    irq = (input_root / 'Core/Src/stm32f1xx_it.c').read_text(encoding='utf-8')
    # PB4..7, PA0..3, PB12..15 avoid the original radio/SPI/UART pins.
    banks = [('PB', (4, 5, 6, 7)), ('PA', (0, 1, 2, 3)), ('PB', (12, 13, 14, 15))]
    signals = ('GPIO_Output', 'GPIO_Output', 'GPIO_Input', None)
    names = ('NSS', 'RST', 'BUSY', 'DIO1')
    extra_ioc = []
    init = []
    prototypes = []
    handlers = []
    pin_index = 17
    for radio in range(1, count):
        bank, pins = banks[radio - 1]
        for name, signal, pin in zip(names, signals, pins):
            label = f'RADIO{radio}_{name}'
            physical = f'{bank}{pin}'
            signal = signal or f'GPXTI{pin}'
            extra_ioc.extend([f'Mcu.Pin{pin_index}={physical}', f'{physical}.GPIOParameters=GPIO_Label',
                              f'{physical}.GPIO_Label={label}', f'{physical}.Signal={signal}',
                              f'{physical}.Locked=true'])
            if name == 'NSS':
                extra_ioc.extend([f'{physical}.GPIO_PuPd=GPIO_PULLUP', f'{physical}.PinState=GPIO_PIN_SET'])
            if name == 'RST':
                extra_ioc.append(f'{physical}.PinState=GPIO_PIN_SET')
            main += f'\n#define {label}_Pin GPIO_PIN_{pin}\n#define {label}_GPIO_Port GPIO{bank[1]}\n'
            if name in ('NSS', 'RST'):
                init.append(f'  HAL_GPIO_WritePin(GPIO{bank[1]}, GPIO_PIN_{pin}, GPIO_PIN_SET);')
            mode = 'GPIO_MODE_IT_RISING' if name == 'DIO1' else 'GPIO_MODE_OUTPUT_PP' if name in ('NSS','RST') else 'GPIO_MODE_INPUT'
            pull = 'GPIO_PULLUP' if name == 'NSS' else 'GPIO_NOPULL'
            init.extend([f'  GPIO_InitStruct.Pin = GPIO_PIN_{pin};', f'  GPIO_InitStruct.Mode = {mode};',
                         f'  GPIO_InitStruct.Pull = {pull};', '  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;',
                         f'  HAL_GPIO_Init(GPIO{bank[1]}, &GPIO_InitStruct);'])
            if name == 'DIO1':
                irq_name = f'EXTI{pin}' if pin < 5 else 'EXTI9_5' if pin < 10 else 'EXTI15_10'
                extra_ioc.append(f'NVIC.{irq_name}_IRQn=true\\:0\\:0\\:false\\:false\\:true\\:true\\:true\\:true')
                init.extend([f'  HAL_NVIC_SetPriority({irq_name}_IRQn, 0, 0);', f'  HAL_NVIC_EnableIRQ({irq_name}_IRQn);'])
                prototypes.append(f'void {irq_name}_IRQHandler(void);')
                handlers.append(f'void {irq_name}_IRQHandler(void)\n{{ HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_{pin}); }}\n')
            pin_index += 1
    if activity_led:
        extra_ioc.extend([f'Mcu.Pin{pin_index}=PA8', 'PA8.GPIOParameters=GPIO_Label',
                          'PA8.GPIO_Label=ACTIVITY_LED', 'PA8.Signal=GPIO_Output',
                          'PA8.PinState=GPIO_PIN_SET', 'PA8.Locked=true'])
        main += '\n#define ACTIVITY_LED_Pin GPIO_PIN_8\n#define ACTIVITY_LED_GPIO_Port GPIOA\n'
        init.extend(['  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);',
                     '  GPIO_InitStruct.Pin = GPIO_PIN_8;',
                     '  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;',
                     '  GPIO_InitStruct.Pull = GPIO_NOPULL;',
                     '  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;',
                     '  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);'])
        pin_index += 1
    # This is a new synthetic input, never a mutation of imported user hardware.
    ioc = ioc.replace('Mcu.PinsNb=17', f'Mcu.PinsNb={pin_index}') + '\n' + '\n'.join(extra_ioc) + '\n'
    gpio = gpio.replace('  /* EXTI interrupt init*/', '\n'.join(init) + '\n  /* EXTI interrupt init*/', 1)
    irq += '\n' + '\n'.join(prototypes + handlers)
    (input_root / 'SyntheticGround.ioc').write_text(ioc, encoding='utf-8')
    (input_root / 'Core/Inc/main.h').write_text(main, encoding='utf-8')
    (input_root / 'Core/Src/gpio.c').write_text(gpio, encoding='utf-8')
    (input_root / 'Core/Src/stm32f1xx_it.c').write_text(irq, encoding='utf-8')
    imported = CubeMxImporter(WorkspacePolicy(root)).Project_Import(input_root, risk_acknowledged=True)
    radios = tuple(GroundRadioConfiguration(f'radio{index}', 'silverstar.device.telemetry.sx1281',
                                           'e28_2g4m12sx', 12) for index in range(count))
    resources = {item.resource_id: item for item in imported.hardware.resources}
    by_label = {str(item.metadata.get('label')): item.resource_id for item in resources.values()}
    assignments = {}
    for index in range(count):
        prefix = 'SPI_RADIO_NSS' if index == 0 else f'RADIO{index}_NSS'
        for name, label in {'radio_nss': prefix, 'radio_reset': 'RADIO_RST' if index == 0 else f'RADIO{index}_RST',
                            'radio_busy': 'RADIO_BUSY' if index == 0 else f'RADIO{index}_BUSY',
                            'radio_dio1': 'RADIO_DIO1' if index == 0 else f'RADIO{index}_DIO1'}.items():
            assignments[f'radio{index}:{name}'] = by_label[label]
        assignments[f'radio{index}:radio_bus'] = next(item.resource_id for item in resources.values() if item.kind == 'spi')
        assignments[f'radio{index}:time'] = next(item.resource_id for item in resources.values() if item.kind == 'time')
    ground = replace(model.ground_target, board='', hardware=imported.hardware,
                     resource_assignments=assignments, pc_resource='USART1', radio_instances=radios)
    model.ground_target = GroundRadioSelection_Apply(ground, f'radio{owner}')
    return model
