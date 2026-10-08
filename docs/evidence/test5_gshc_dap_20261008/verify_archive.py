"""Offline hashes/source verification; never opens hardware or executes captures."""
from pathlib import Path
import hashlib,json,subprocess,sys

root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
for name,item in manifest['files'].items():
    data=(root/name).read_bytes()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],name
    if '--commit' in sys.argv:
        committed=subprocess.check_output(['git','show','HEAD:'+str((root/name).relative_to(Path.cwd())).replace('\\','/')])
        assert committed==data,'Committed bytes differ: '+name
if '--commit' in sys.argv:
    committed=subprocess.check_output(['git','show','HEAD:'+str((root/'manifest.json').relative_to(Path.cwd())).replace('\\','/')])
    assert committed==(root/'manifest.json').read_bytes()
before=(root/'session_audit.json').read_bytes()
audit=subprocess.run([sys.executable,str(root/'audit_sessions.py'),str(root)],capture_output=True)
assert audit.returncode==0,(audit.stdout+audit.stderr).decode(errors='replace')
assert (root/'session_audit.json').read_bytes()==before
for name,item in json.loads((root/'environment.json').read_text(encoding='utf-8'))['preserved_user_inputs'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==item['sha256'],name
app_diff=subprocess.run(['git','diff','--quiet',manifest['application_source_commit'],'--','apps/SCG','apps/GSHC','apps/FLP'])
assert app_diff.returncode==0
check=subprocess.run(['git','diff','--check'],capture_output=True)
assert check.returncode==0,(check.stdout+check.stderr).decode(errors='replace')
print(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),'verified_files':len(manifest['files']),'committed_bytes_checked':'--commit' in sys.argv,'offline_audit_exit':audit.returncode,'audit_bytes_unchanged':True,'user_inputs_hash_unchanged':True,'application_diff_exit':app_diff.returncode,'diff_check_exit':check.returncode},indent=2))
