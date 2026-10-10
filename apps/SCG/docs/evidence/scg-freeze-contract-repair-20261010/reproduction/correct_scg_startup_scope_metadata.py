from pathlib import Path
import json, hashlib, shutil

task=Path(__file__).parent
path=task/'sr-startup.json'
original=path.read_bytes()
old=json.loads(original)
assert old['source_commit']=='819eec98347e96aa6548012be159e6a6c58bd435'
assert 'merged daily' in old['scope']
saved=task/'sr-startup-before-scope-correction.json'
assert not saved.exists()
shutil.copyfile(path,saved)
new=dict(old)
new['scope']='Actual isolated SCG application.main and MainWindow show/event loop/normal shutdown with exact isolated declarative catalog; writable settings/log/workspace in Temp. No hardware or user preference changes.'
new['metadata_correction']={'original_record':saved.name,
 'original_sha256':hashlib.sha256(original).hexdigest(),
 'reason':'Cloned runner retained an inaccurate daily/merged scope phrase. Actual source_commit, source file hashes, isolated repo assertion and all execution results remain unchanged.',
 'actual_checkout':str(task/'r')}
assert {k:v for k,v in new.items() if k not in {'scope','metadata_correction'}}=={k:v for k,v in old.items() if k!='scope'}
path.write_text(json.dumps(new,indent=2),encoding='utf8')
print(new['metadata_correction'])
