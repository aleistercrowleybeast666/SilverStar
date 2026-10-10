from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, os
TASK=Path(__file__).parent
rows=[json.loads(line) for line in (TASK/'srgui01-build-index.jsonl').read_text().splitlines()]
TEMP=Path('D:/Codex_Work/task-temp')
records=[];new_rows=[]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for row in rows:
 old_output=Path(row['output']); output=old_output.resolve();project=Path(row['project_root']).resolve()
 assert output.is_relative_to(TEMP/'srgui01') and project.is_relative_to(TEMP/'srgui01')
 assert output==output.absolute() and not output.is_junction() and not output.is_symlink()
 pointer=project/'.fccg/usb-candidate.json';before=pointer.read_bytes();value=json.loads(before)
 assert value['output']==str(old_output)
 backend=output/'backend-receipt.json';compile=output/'receipt.json'
 assert value['backend_receipt_sha256']==sha(backend)==row['backend_receipt_sha256']
 receipt=json.loads(backend.read_text());compiled=json.loads(compile.read_text())
 assert receipt['compile_receipt_sha256']==sha(compile)
 assert compiled['source_commit']=='819eec98347e96aa6548012be159e6a6c58bd435'
 assert value['model_sha256']==receipt['model_sha256']==compiled['runtime_model_sha256']
 hashes={name:sha(output/name) for name in ['backend-receipt.json','receipt.json','build/native.elf','build/analysis/native.elf']}
 model_before=sha(project/'SilverStar.ssproject')
 new={**value,'output':str(output)}
 assert {k:v for k,v in new.items() if k!='output'}=={k:v for k,v in value.items() if k!='output'}
 archive=TASK/'ds-migration-locators';archive.mkdir(exist_ok=True)
 saved=archive/(row['part']+'-original-pointer.json');assert not saved.exists();saved.write_bytes(before)
 staged=pointer.with_name('usb-candidate.migration-stage.json')
 staged.write_text(json.dumps(new,indent=2),encoding='utf8');os.replace(staged,pointer)
 assert model_before==sha(project/'SilverStar.ssproject')
 assert hashes=={name:sha(output/name) for name in hashes}
 records.append({'part':row['part'],'project':str(project),'old_output':str(old_output),'new_output':str(output),
  'original_pointer_sha256':hashlib.sha256(before).hexdigest(),'new_pointer_sha256':sha(pointer),
  'model_file_sha256_unchanged':model_before,'immutable_receipts_and_elf_sha256':hashes,
  'scope':'Only output locator path changed to verified physical D destination. Every identity/result/hash field, model bytes, receipt bytes and ELF bytes unchanged. Original pointer saved. Product alias rejection guard unchanged.'})
 new_rows.append({**row,'output':str(output),'project_root':str(project)})
(TASK/'ds-migrated-build-index.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in new_rows))
(TASK/'ds-locator-migration.json').write_text(json.dumps({'recorded_utc':datetime.now(timezone.utc).isoformat(),'records':records},indent=2))
print(json.dumps(records,indent=2))
