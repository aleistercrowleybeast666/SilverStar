from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil,re
task=Path(__file__).parent
archive=task/'repair-artifact-evidence';archive.mkdir(exist_ok=True)
records=[]
index_rows=[]
final_commit=json.loads((task/'sr-final-code.json').read_text(encoding='utf-8-sig'))['final_code_commit']
for label, commit, prefix in [
 ('srgui01',final_commit,'Unified-'),
 ('srprivate02',final_commit,'Private-'),
 ('srb02',final_commit,'BackendUnified-'),
 ('srprivate01','a0afca6a11a9cf7066baf62afecf95fd549c9736','HistoricalPrivate-'),
 ('srb01','a0afca6a11a9cf7066baf62afecf95fd549c9736','HistoricalUnified-')]:
 for row in map(json.loads,(task/('ds-migrated-build-index.jsonl' if label=='srgui01' else label+'-build-index.jsonl')).read_text().splitlines()):
  index_rows.append({**row,'expected_commit':commit,'archive_name':prefix+row['part'],'index_label':label})
for row in index_rows:
 root=Path(row['output']);receipt=json.loads((root/'receipt.json').read_text())
 assert receipt['source_commit']==row['expected_commit']
 destination=archive/row['archive_name'];destination.mkdir(exist_ok=True)
 files=['receipt.json','backend-receipt.json']+[p for p in receipt['output_artifact_sha256'] if p.endswith('.elf') or p.endswith('vectors.bin')]
 hashes={}
 for relative in files:
  source=root/relative;target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
  body=source.read_bytes();digest=hashlib.sha256(body).hexdigest()
  if relative in receipt['output_artifact_sha256']:assert receipt['output_artifact_sha256'][relative]==digest
  shutil.copyfile(source,target);assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
  hashes[relative]=digest
 records.append({'part':row['part'],'index_label':row['index_label'],'root':str(root),'archive':str(destination),'source_commit':receipt['source_commit'],
 'status':receipt['status'],'commands_executed':len(receipt['commands']),'warning_diagnostics':receipt['warning_diagnostics'],
 'receipt_no_warning_gate':receipt['no_warning_gate'],'facts':receipt['facts'],'archived_files_sha256':hashes})
generated=json.loads((task/'sr-legacy-generated.json').read_text())
legacy=[]
for row in generated['projects']:
 root=Path(row['root']);destination=archive/row['kind'];destination.mkdir(exist_ok=True)
 hashes={}
 for path in root.rglob('*.elf'):
  relative=path.relative_to(root);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(path,target);hashes[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
 log_paths=list(task.glob('srlegacy-'+row['kind']+'-*.log'))
 if row['kind']=='Flight':log_paths += list(task.glob('ds-Flight-*.log'))
 for path in sorted(log_paths):
  text=path.read_text(encoding='utf8');warnings=[s for s in text.splitlines() if 'warning:' in s]
  legacy.append({'kind':row['kind'],'target':path.stem,'warnings':warnings,'fanalyzer_command_count':sum(s.startswith('arm-none-eabi-gcc ') and '-fanalyzer' in s for s in text.splitlines())})
 row['archived_elf_sha256']=hashes
data={'recorded_utc':datetime.now(timezone.utc).isoformat(),'native_candidates':records,'legacy_projects':generated['projects'],'legacy_log_diagnostics':legacy,
 'scope':'Persistent copies of receipts/ELFs/vector bytes only; no vendor duplication, no source/test/gate changes. Actual normal/analyzer compile/link evidence, not hardware or stack/WCET qualification.'}
(task/'sr-artifact-evidence.json').write_text(json.dumps(data,indent=2))
print(json.dumps({'native':[{'part':r['part'],'commands':r['commands_executed'],'files':r['archived_files_sha256']} for r in records],
 'legacy':[{'kind':r['kind'],'elf':r['archived_elf_sha256']} for r in generated['projects']],
 'diagnostics':[{'target':r['target'],'warning_count':len(r['warnings']),'analyzer_commands':r['fanalyzer_command_count']} for r in legacy]},indent=2))


