from pathlib import Path
import json,re,hashlib
root=Path('D:/python_software/SilverStar')
facts=json.loads((root/'.work/ccdi_facts/f407-usb.json').read_text())
header=Path(facts['irq_evidence_source'])
text=re.sub(r'/\*.*?\*/|//[^\r\n]*','',header.read_text(encoding='utf-8-sig'),flags=re.S)
facts['irq_numbers']=[[name,int(value)] for name,value in re.findall(r'(?m)^\s*(\w+_IRQn)\s*=\s*(-?\d+)\s*(?=,|\})',text)]
assert dict(facts['irq_numbers'])['FPU_IRQn']==81
assert facts['irq_header_sha256']==hashlib.sha256(header.read_bytes()).hexdigest()
out=root/'.work/ccdi_facts/f407-usb13.json'
assert not out.exists();out.write_text(json.dumps(facts,indent=2))
print(out)
