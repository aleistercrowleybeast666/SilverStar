from pathlib import Path
import json,shutil,hashlib
T=Path(__file__).parent
archive=T/'ds-import-sideeffect';archive.mkdir(exist_ok=True)
old=json.loads((T/'ds-resume-sequence.json').read_text())
for label in ['ds-entry01','ds-async01']:
 for suffix in ['.log','-command.json']:
  shutil.copyfile(T/(label+suffix),archive/(label+suffix))
 record=next(x for x in old if x['label']==label)
 (archive/(label+'-original-command-from-sequence.json')).write_text(json.dumps(record,indent=2))
(T/'ds-evidence-correction.json').write_text(json.dumps({'scope':'Importing orchestration helper incorrectly executed its top-level default jobs, overwriting ds-entry01/ds-async01 command and log files. Entry repeated 16 passed; async aborted before collection due existing basetemp. Original ds-async01 XML remains (12 passed/4 failed), original command and log hash retained in ds-resume-sequence.json. Original raw log bytes are unavailable; no claim of matching its original log hash. Sideeffect files and reconstructed original metadata archived. Runner now uses main guard; no product source/test changes.','original_sequence_sha256':hashlib.sha256((T/'ds-resume-sequence.json').read_bytes()).hexdigest(),'async_original_xml_sha256':hashlib.sha256((T/'ds-async01.xml').read_bytes()).hexdigest()},indent=2))
