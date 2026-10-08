"""Repair the recorder only from saved data; never reconnect to target."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
out = root / 'hardware_preflight'
record = json.loads((out / 'command.json').read_text())
raw = (out / 'openocd.log').read_bytes()
text = raw.decode(errors='replace')
before = (out / 'before_fullflash.bin').read_bytes()
old = Path('.work/bench08c_f407/Flight_Controller/build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin').read_bytes()
assert hashlib.sha256(old).hexdigest() == '5c4e8e2bba538eceefc981b7687cd157e4ce14c39fa4076b8c731319b92288f3'
assert len(before) == 524288 and before[:len(old)] == old
uid = [int(value, 0) for value in re.search(r'UID=([^\r\n]+)', text)[1].split()]
cores = [int(value.strip(), 0) for value in re.findall(r'CORE_(?:BEFORE|AFTER)=([^\r\n]+)', text)]
phase = int(re.search(r'OLD_LIFECYCLE=([^\r\n]+)', text)[1].strip(), 0)
assert len(uid) == 3 and len(cores) == 2 and not any(value & (1 << 17) for value in cores) and phase == 2
assert 'TARGET_ID=0x10076413 FLASH_KIB=0x200' in text and 'shutdown command invoked' in text
record.update(exit_code=0, recorder_python_exit=1,
              correction='OpenOCD returned 0 (entered success-only branch); decimal-only parser then failed. Reparsed exact retained log and backup without reconnecting. Original script retained.',
              uid_words=uid, core_values=cores, running_after=True, old_lifecycle=phase,
              old_image_verified=True, fullflash_sha256=hashlib.sha256(before).hexdigest(),
              log_sha256=hashlib.sha256(raw).hexdigest())
(out / 'result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({key:record[key] for key in ('uid_words','old_lifecycle','old_image_verified','fullflash_sha256','recorder_python_exit')}, indent=2))
