"""Explicit software wiring for normal E32 generation; never hardware evidence.

Uses the checked-in HAL/RTOS input owners through CubeMxImporter. The board
identity is cleared: adding E32 front-end pins does not create a verified PCB.
"""
from dataclasses import replace
from pathlib import Path
import re

from ebyte_variant_fixture import _Input_Create
from test_round2_targets import _GroundBoardProject_Get
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.resources import BoardResourceProvisions_Get
from silverstar_fccg.project.model import GroundRadioConfiguration
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile


def _Sx1278Input_Configure(root):
    ioc = root / 'SyntheticRadio.ioc'
    text = ioc.read_text(encoding='utf8')
    pin = re.search(r'^(P[A-Z]\d+)\.GPIO_Label=RADIO_RST$', text, re.M)[1]
    text = re.sub(r'^' + pin + r'\.GPIO_ModeDefaultOutputPP=.*$', '', text, flags=re.M)
    text = re.sub(r'^' + pin + r'\.GPIO_PuPd=.*$', '', text, flags=re.M)
    text += f'\n{pin}.GPIO_ModeDefaultOutputPP=GPIO_MODE_OUTPUT_OD\n{pin}.GPIO_PuPd=GPIO_PULLUP\n'
    ioc.write_text(text, encoding='utf8')
    gpio = root / 'Core/Src/gpio.c'
    source = gpio.read_text(encoding='utf8')
    # Reinitialize only the E32 reset pin; other pins sharing its original
    # CubeMX group retain their own push-pull settings.
    addition = '''  GPIO_InitStruct.Pin = RADIO_RST_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(RADIO_RST_GPIO_Port, &GPIO_InitStruct);
'''
    source = source.replace('  /* EXTI interrupt init*/', addition + '  /* EXTI interrupt init*/', 1)
    gpio.write_text(source, encoding='utf8')


def Sx1278Project_Create(catalog, root: Path):
    model = _GroundBoardProject_Get(catalog)
    importer = CubeMxImporter(WorkspacePolicy(root))
    board = _Input_Create(catalog, model, model.board, root/'flight_input', ('PC1','PC2'))
    _Sx1278Input_Configure(root/'flight_input')
    imported = importer.Project_Import(root/'flight_input', risk_acknowledged=True)
    mapping = {item.resource_id:item.metadata['physical_resource'] for item in BoardResourceProvisions_Get(board)}
    model.resource_assignments = {key:mapping[value] for key,value in model.resource_assignments.items()}
    model.hardware = imported.hardware; model.board = ''
    model.device_instances = [replace(item, plugin='silverstar.device.telemetry.sx1278',
        module_variant='e32_400m20s', tx_power_dbm=17) if item.instance_id=='telemetry0' else item
        for item in model.device_instances]
    model.resource_assignments['telemetry0:radio_dio0'] = model.resource_assignments.pop('telemetry0:radio_dio1')
    model.resource_assignments.pop('telemetry0:radio_busy')
    model.resource_assignments.update({'telemetry0:radio_rx_en':'RF_RX_EN','telemetry0:radio_tx_en':'RF_TX_EN'})
    model.air_link = replace(model.air_link, radio_family='sx127x', frequency_hz=433000000,
        bandwidth_hz=125000, spreading_factor=7, packet_mtu=61)
    ground = model.ground_target
    board = _Input_Create(catalog, replace(model,mcu=ground.mcu),ground.board,root/'ground_input',('PA8','PA11'))
    _Sx1278Input_Configure(root/'ground_input')
    imported = importer.Project_Import(root/'ground_input', risk_acknowledged=True)
    mapping = {item.resource_id:item.metadata['physical_resource'] for item in BoardResourceProvisions_Get(board)}
    assignments = {key:mapping[value] for key,value in ground.resource_assignments.items()}
    assignments['radio0:radio_dio0'] = assignments.pop('radio0:radio_dio1')
    assignments.pop('radio0:radio_busy')
    assignments.update({'radio0:radio_rx_en':'RF_RX_EN','radio0:radio_tx_en':'RF_TX_EN'})
    model.ground_target = replace(ground, board='', hardware=imported.hardware,
        radio_plugin='silverstar.device.telemetry.sx1278', module_variant='e32_400m20s',tx_power_dbm=17,
        radio_instances=(GroundRadioConfiguration('radio0','silverstar.device.telemetry.sx1278','e32_400m20s',17),),
        resource_assignments=assignments, pc_resource='USART1')
    return ProjectConfiguration_Reconcile(model, catalog).model
