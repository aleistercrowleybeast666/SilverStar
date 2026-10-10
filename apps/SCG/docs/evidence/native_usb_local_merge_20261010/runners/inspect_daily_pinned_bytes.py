from pathlib import Path
import json,subprocess,hashlib,re
task=Path(__file__).parent;daily=Path(r'D:\python_software\SilverStar');candidate=Path(r'D:\python_software\SilverStar\.work\ccdi')
sha=lambda b:hashlib.sha256(b).hexdigest()
records=[]
for path in [x for x in subprocess.check_output(['git','-C',str(daily),'ls-files','apps/SCG/plugins/builtin'],text=True).splitlines() if x.endswith(('.c','.h'))]:
    old=(candidate/path).read_bytes();current=(daily/path).read_bytes()
    if sha(old) in ['56ee9b35e54535249816363d0328120a6018f157ce51f8bad93185ebea78428c','b8caf4dd85dd3307897fa8f923adcaf7153b0d4c91a787eb58537d0b34eb783d']:
        records.append({'path':path,'expected_sha256':sha(old),'daily_sha256':sha(current),'same_bytes':old==current,
          'only_crlf_conversion':current.replace(b'\r\n',b'\n')==old,'lf_git_blob_sha256':sha(subprocess.check_output(['git','-C',str(daily),'show','HEAD:'+path]))})
for profile in (daily/'apps/SCG/src/silverstar_fccg/hardware/usb_profiles').glob('*.json'):
    d=json.loads(profile.read_text())
    entries=d.get('files_sha256',{})
    if not entries:continue
    for relative,digest in entries.items():
        matches=[]
        for prefix in [daily/'apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini',daily/'apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini/payload']:
            p=prefix/relative
            if p.is_file():matches.append(p)
        for p in matches:
            current=p.read_bytes();path=p.relative_to(daily).as_posix();old=(candidate/path).read_bytes()
            records.append({'path':path,'profile':profile.name,'expected_sha256':digest,'candidate_sha256':sha(old),
               'daily_sha256':sha(current),'same_bytes':sha(current)==digest,'only_crlf_conversion':current.replace(b'\r\n',b'\n')==old,
               'lf_git_blob_sha256':sha(subprocess.check_output(['git','-C',str(daily),'show','HEAD:'+path]))})
d={'scope':'Exact ordinary input byte provenance across accepted Git blob/isolated worktree/Windows daily checkout; no validator changes or malformed USB research',
 'records':records,'mismatches':[r for r in records if not r['same_bytes']]}
(task/'daily-pinned-byte-audit.json').write_text(json.dumps(d,indent=2),encoding='utf8')
print(json.dumps({'records':len(records),'mismatches':d['mismatches']},indent=2))
