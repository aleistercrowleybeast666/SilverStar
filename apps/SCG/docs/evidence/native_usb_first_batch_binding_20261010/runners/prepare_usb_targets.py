from pathlib import Path
import hashlib, json, re, subprocess

root = Path(r'D:\python_software\SilverStar\.work\ccdi')
rev = 'b66f142f7ab9b5611bd2f9a84a105835e4f77b96'
target = root / 'apps/SCG/src/silverstar_fccg/hardware/usb_profiles'
target.mkdir(exist_ok=True)
base = 'apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini/'
for name, dest in [('native-profile.json','c071-native-profile.json'), ('companion-manifest.json','c071-companion-manifest.json')]:
    body = subprocess.check_output(['git','-C',str(root),'show',rev+':'+base+name])
    (target/dest).write_bytes(body)
f103 = root / 'apps/SCG/docs/evidence/native_classic_cdc_backend_20261010/facts/f103.json'
(target/'f103-device-facts.json').write_bytes(f103.read_bytes())
header = Path(r'C:\Users\chdxm\STM32Cube\Repository\STM32Cube_FW_C0_V1.4.1\Drivers\CMSIS\Device\ST\STM32C0xx\Include\stm32c071xx.h')
body=header.read_bytes()
assert hashlib.sha256(body).hexdigest() == 'fa5f83d0763b0446aff74182074f52343fc0f2056e54661469e4ed8605484361'
facts = {'part':'STM32C071FBP6','core':'cortex-m0plus','device_macro':'STM32C071xx',
    'startup':'startup_stm32c071xx.s','fpu':'','regions':[
        {'name':'FLASH','origin':0x08000000,'length':128*1024},
        {'name':'RAM','origin':0x20000000,'length':24*1024}],
    'evidence_source':'Registered exact C071FBP6 MCU profile at '+rev+'; physical memory specification DS14693',
    'evidence_sha256':hashlib.sha256(subprocess.check_output(['git','-C',str(root),'show',rev+':apps/SCG/plugins/builtin/silverstar_mcu_stm32c071fbp6/plugin.json'])).hexdigest(),
    'irq_numbers':[[n,int(v)] for n,v in re.findall(r'([A-Za-z0-9_]+_IRQn)\s*=\s*(-?\d+)',body.decode())],
    'irq_header_sha256':hashlib.sha256(body).hexdigest(),
    'irq_evidence_source':str(header)}
(target/'c071-device-facts.json').write_text(json.dumps(facts,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir()},indent=2))
