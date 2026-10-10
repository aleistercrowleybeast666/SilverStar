from pathlib import Path
from dataclasses import asdict
import json,hashlib,sys,re
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar');sys.path.insert(0,str(repo/'apps/SCG/src'))
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts,NativeMemoryRegion
from silverstar_fccg.app.usb_ground import UsbGroundDeviceFacts_Get
header=Path('D:/Tools/Embedded/STM32/Repository/STM32Cube_FW_F1_V1.8.7/Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xb.h')
text=re.sub(r'/\*.*?\*/|//[^\r\n]*','',header.read_text(encoding='utf-8-sig'),flags=re.S)
irq_numbers=tuple((n,int(v)) for n,v in re.findall(r'(?m)^\s*(\w+_IRQn)\s*=\s*(-?\d+)\s*(?=,|\})',text))
plugin=repo/'apps/SCG/plugins/builtin/silverstar_mcu_stm32f103c8t6/plugin.json'
generic=NativeDeviceFacts('STM32F103C8T6','cortex-m3','STM32F103xB','startup_stm32f103xb.s',
 (NativeMemoryRegion('FLASH',0x08000000,65536),NativeMemoryRegion('RAM',0x20000000,20480)),str(plugin),hashlib.sha256(plugin.read_bytes()).hexdigest(),
 irq_numbers=irq_numbers,irq_header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),irq_evidence_source=str(header))
profile=UsbGroundDeviceFacts_Get('STM32F103C8T6',header)
a,b=asdict(generic),asdict(profile);diff={k:{'generic_fixture':a[k],'pinned_backend':b[k]} for k in a if a[k]!=b[k]}
d={'scope':'Normal F103 descriptor provenance mismatch in extra generic-to-pinned dispatch equality test; no firmware/validator changes',
 'differences':diff,'all_other_fields_equal':True,'generic':a,'pinned':b}
(task/'daily-f103-authority-identity.json').write_text(json.dumps(d,indent=2),encoding='utf8')
print(json.dumps({'differences':diff,'all_other_fields_equal':True},indent=2))
