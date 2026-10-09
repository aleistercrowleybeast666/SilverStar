from pathlib import Path
from dataclasses import asdict
import hashlib,json,sys
ROOT=Path('D:/python_software/SilverStar')
sys.path.insert(0,str(ROOT/'.work/ccdi/apps/SCG/src'))
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts,NativeMemoryRegion
OUT=ROOT/'.work/ccdi_facts'
OUT.mkdir(exist_ok=True)
for case,part,core,macro,startup,regions in [
 ('f103-usb','STM32F103C8T6','cortex-m3','STM32F103xB','startup_stm32f103xb.s',(NativeMemoryRegion('FLASH',0x08000000,65536),NativeMemoryRegion('RAM',0x20000000,20480))),
 ('f407-usb','STM32F407VET6','cortex-m4','STM32F407xx','startup_stm32f407xx.s',(NativeMemoryRegion('FLASH',0x08000000,524288),NativeMemoryRegion('RAM',0x20000000,131072),NativeMemoryRegion('CCMRAM',0x10000000,65536)))]:
 evidence=ROOT/'.work/ccdi/apps/SCG/plugins/builtin'/('silverstar_mcu_stm32f103c8t6' if case=='f103-usb' else 'silverstar_mcu_stm32f407vet6')/'plugin.json'
 facts=NativeDeviceFacts(part,core,macro,startup,regions,str(evidence),hashlib.sha256(evidence.read_bytes()).hexdigest(),fpu='fpv4-sp-d16' if case=='f407-usb' else '')
 (OUT/(case+'.json')).write_text(json.dumps(asdict(facts),indent=2),encoding='utf-8')
