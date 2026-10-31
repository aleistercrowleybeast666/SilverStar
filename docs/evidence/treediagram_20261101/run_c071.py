"""Fresh experimental C071 candidate; the independent normal gate remains closed."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
SCG = REPO / 'apps/SCG'
sys.path.insert(0, str(SCG / 'src'))
os.environ['PATH'] = 'D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;' + os.environ['PATH']
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.reference import ReferenceProject_Create

root = REPO / '.work/0.1.3-treediagram-20261101/silverstar/c071-v1'
root.mkdir(parents=True, exist_ok=False)
service = FccgService(root)
service.catalog = PluginCatalog(SCG / 'plugins/builtin', SCG / 'plugins/installed')
service.catalog.Scan()
model = ReferenceProject_Create('TreeDiagramC071S', catalog=service.catalog)
model.ground_target = replace(model.ground_target, pc_interface='usb_cdc',
    radio_plugin='silverstar.device.telemetry.sx1281', module_variant='e28_2g4m12sx', tx_power_dbm=12)
native = Path('C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST')
header = Path('C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h')
companion = SCG / 'plugins/builtin/silverstar_usb_cdc_stm32c071_mini'
result = service.UsbGroundProject_Import(native, model, part='STM32C071FBP6',
    independent_irq_header=header, hclk_hz=48000000, spi_resource='SPI1',
    gpio_resources=('RADIO_NSS', 'RADIO_RESET', 'RADIO_BUSY', 'RADIO_DIO1'),
    risk_acknowledged=True, companion_root=companion)
print(result.result, flush=True)
service.ProjectRoot_Save(result.model, root / 'project', create_new=True)
plan = service.UsbGroundCandidate_Plan(result.model, independent_irq_header=header, companion_root=companion)
print(plan.result, plan.capability_facts, flush=True)
built = service.UsbGroundCandidate_Build(result.model, root / 'project', root / 'candidate',
    independent_irq_header=header, companion_root=companion)
print(built, flush=True)
evidence = dict(owner='silverstar_finish', native=str(native), independent_sdk_header=str(header),
    independent_sdk_header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(), companion=str(companion),
    api='UsbGroundCandidate_Build', normal_admission=False, hardware_tested=False,
    profile='ss_tm.s.0_1', result=built.result.value, detail=built.detail)
(Path(__file__).parent / 'c071-v1.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
if built.result.value != 'CompiledCandidate':
    raise RuntimeError(built.detail)
