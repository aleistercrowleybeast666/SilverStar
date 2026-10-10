from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib,tempfile
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar');accepted=Path(r'D:\python_software\SilverStar\.work\ccdi')
base='2016a1279fa529c96d5b108d7d67326e2fda3653'
sha=lambda b:hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
assert git('rev-parse','HEAD')==base and not git('diff','--name-only') and not git('diff','--cached','--name-only')
assert git('status','--porcelain').splitlines()==['?? work_build_candidates_20261006.csv','?? work_inventory_20261006.txt','?? work_subtree_classification_20261006.csv']
paths={
 'apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload/Devices/Telemetry/SX1281/Src/sx1281_device.c':'56ee9b35e54535249816363d0328120a6018f157ce51f8bad93185ebea78428c',
 'apps/SCG/plugins/builtin/silverstar_device_telemetry_sx1281/payload/Middlewares/Third_Party/SX1280lib/sx1280-hal.c':'b8caf4dd85dd3307897fa8f923adcaf7153b0d4c91a787eb58537d0b34eb783d'}
data=[]
for path,digest in paths.items():
    before=(repo/path).read_bytes();body=(accepted/path).read_bytes();blob=subprocess.check_output(['git','-C',str(repo),'show','HEAD:'+path])
    assert sha(body)==digest
    assert before.replace(b'\r\n',b'\n')==body.replace(b'\r\n',b'\n')==blob,'Not solely Git newline conversion; stop'
    original=task/('daily-before-'+Path(path).name+'.bin');assert not original.exists();original.write_bytes(before)
    data.append({'path':path,'expected_sha256':digest,'before_working_sha256':sha(before),'before_git_blob_sha256':sha(blob),
      'accepted_raw_sha256':sha(body),'normalized_content_identical':True,'raw_backup':str(original)})
attrs=repo/'apps/SCG/.gitattributes';old=attrs.read_text(encoding='utf8')
lines=['# Preserve the exact reviewed radio payload bytes used by native derivatives.']+[p.removeprefix('apps/SCG/')+' -text' for p in paths]
assert not any(line in old for line in lines)
attrs.write_text(old.rstrip()+'\n'+'\n'.join(lines)+'\n',encoding='utf8',newline='\n')
for path,digest in paths.items():(repo/path).write_bytes((accepted/path).read_bytes())
subprocess.run(['git','-C',str(repo),'add','--','apps/SCG/.gitattributes',*paths],check=True)
staged=git('diff','--cached','--name-only').splitlines();assert set(staged)=={'apps/SCG/.gitattributes',*paths}
assert git('diff','--cached','--ignore-space-at-eol','--',*paths)==''
for path,digest in paths.items():assert sha(subprocess.check_output(['git','-C',str(repo),'show',':'+path]))==digest
# Whitespace is payload provenance here; -text intentionally retains accepted
# original CRLF/mixed-EOL bytes. No check, compiler, source algorithm changed.
subprocess.run(['git','-C',str(repo),'commit','-m','Preserve reviewed native radio payload bytes on Windows checkout'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
head=git('rev-parse','HEAD');fresh=Path(tempfile.mkdtemp(prefix='daily-radio-checkout-'))
subprocess.run(['git','-C',str(repo),'checkout-index','--prefix='+str(fresh).replace('\\','/')+'/','--',*paths],check=True)
for path,digest in paths.items():assert sha((fresh/path).read_bytes())==sha((repo/path).read_bytes())==digest
assert git('status','--porcelain').splitlines()==['?? work_build_candidates_20261006.csv','?? work_inventory_20261006.txt','?? work_subtree_classification_20261006.csv']
d={'before_head':base,'delivery_fix_commit':head,'source_code_commit':'f61cbd851b8ac32b865deb1a3997058685dfebbd',
 'scope':'Git delivery-only correction: preserve already independently-reviewed exact payload bytes; no normalized C, Python, validator or profile hash changes',
 'payloads':data,'fresh_checkout_raw_hash_verified':True,'fresh_checkout':str(fresh),'recorded_utc':datetime.now(timezone.utc).isoformat()}
(task/'daily-radio-delivery-fix.json').write_text(json.dumps(d,indent=2),encoding='utf8')
print(json.dumps(d,indent=2))
