"""Explicit synthetic E19 wiring, with real matching CubeMX SPI prescalers."""
import re
from dataclasses import replace

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.radio_transaction import RadioTransaction_EndpointSet
from silverstar_fccg.project.sx1278 import SX1278_PLUGIN
from sx1278_project_fixture import Sx1278Project_Create


def E19Project_Create(catalog, root):
    model = Sx1278Project_Create(catalog, root)
    importer = CubeMxImporter(WorkspacePolicy(root))
    for target, clock in [('flight', '0.65625'), ('ground', '0.5625')]:
        source = root / (target+'_input')
        ioc = source/'SyntheticRadio.ioc'
        text = ioc.read_text(encoding='utf8')
        text = re.sub(r'^SPI1.BaudRatePrescaler=.*$', 'SPI1.BaudRatePrescaler=SPI_BAUDRATEPRESCALER_128', text, flags=re.MULTILINE)
        text = re.sub(r'^SPI1.CalculateBaudRate=.*$', 'SPI1.CalculateBaudRate='+clock+' MBits/s', text, flags=re.MULTILINE)
        ioc.write_text(text, encoding='utf8')
        spi = source/'Core/Src/spi.c'
        spi.write_text(re.sub(r'SPI_BAUDRATEPRESCALER_\d+', 'SPI_BAUDRATEPRESCALER_128',
                             spi.read_text(encoding='utf8')), encoding='utf8')
        imported = importer.Project_Import(source, risk_acknowledged=True)
        if target == 'flight':
            model.hardware = imported.hardware
        else:
            model.ground_target = replace(model.ground_target, hardware=imported.hardware)
        model = RadioTransaction_EndpointSet(model, catalog, target, SX1278_PLUGIN, 'e19_433m20s2', 17)
    return ProjectConfiguration_Reconcile(model, catalog).model
