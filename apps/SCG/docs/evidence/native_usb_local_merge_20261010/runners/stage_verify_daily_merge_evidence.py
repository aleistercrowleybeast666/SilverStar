from pathlib import Path
import subprocess,json,hashlib
repo=Path(r'D:\python_software\SilverStar');task=Path(__file__).parent
root='apps/SCG/docs/evidence/native_usb_local_merge_20261010';report='apps/SCG/docs/NATIVE_USB_LOCAL_MERGE_20261010.md';code='e1357b417ee98df5990a1fff18c55d6b35183896'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
assert not subprocess.check_output(['git','-C',str(repo),'diff','--name-only'],text=True)
assert not subprocess.check_output(['git','-C',str(repo),'diff','--cached','--name-only'],text=True)
subprocess.run(['git','-C',str(repo),'add','-f','--',root,report],check=True)
subprocess.run(['git','-C',str(repo),'add','--renormalize','--',root],check=True)
manifest=json.loads((repo/root/'verification.json').read_text());assert manifest['tested_daily_code_commit']==code
expected={root+'/'+p:digest for p,digest in manifest['files_sha256'].items()};expected[root+'/verification.json']=sha(repo/root/'verification.json')
paths=set(filter(None,subprocess.check_output(['git','-C',str(repo),'ls-files','-z','--',root]).decode().split('\0')));assert paths==set(expected)
staged=subprocess.check_output(['git','-C',str(repo),'diff','--cached','--name-only'],text=True).splitlines();assert set(staged)==paths|{report}
ordered=sorted(expected);payload=subprocess.run(['git','-C',str(repo),'cat-file','--batch'],input=''.join(':'+p+'\n' for p in ordered).encode(),stdout=subprocess.PIPE,check=True).stdout
offset=total=0
for name in ordered:
    end=payload.index(b'\n',offset);header=payload[offset:end].split();assert header[1]==b'blob';size=int(header[2]);body=payload[end+1:end+1+size];offset=end+1+size+1;total+=size
    assert hashlib.sha256(body).hexdigest()==expected[name]==sha(repo/name),name
assert offset==len(payload)
for b in manifest['builds']:
    base=repo/root/'final'/b['part'];snapshot=json.loads((base/'source-snapshot.json').read_text())
    assert snapshot['source_commit']==code and not snapshot['dirty_diff']
    assert sha(base/'source-snapshot.json')==b['source_snapshot_sha256']
    for name,item in snapshot['modules'].items():assert sha(repo/'apps/SCG'/name)==item['sha256'],name
    receipt=json.loads((base/'receipt.json').read_text());assert sha(base/'receipt.json')==b['compiler_receipt_sha256']
    assert sha(base/'backend-receipt.json')==b['backend_receipt_sha256']
    for name,digest in receipt['experimental_files_sha256'].items():assert sha(base/name)==digest,(b['part'],name)
    for name,digest in b['elf_sha256'].items():assert sha(base/name)==digest
assert hashlib.sha256(subprocess.check_output(['git','-C',str(repo),'show',':'+report])).hexdigest()==sha(repo/report)
assert subprocess.check_output(['git','-C',str(repo),'diff','--ignore-space-at-eol','5b99438ba4005ea02935e9734307e749e2e758e7','HEAD','--','apps/SCG/src','apps/SCG/plugins','apps/SCG/tests'],text=True)==''
subprocess.run(['git','-C',str(repo),'diff','--cached','--check'],check=True)
record={'tested_daily_code_commit':code,'verified_index_and_working_files':len(ordered),'archived_bytes':total,
 'manifest_sha256':expected[root+'/verification.json'],'report_sha256':sha(repo/report),'all_source_snapshot_modules_rechecked':True,
 'all_declared_generated_files_and_elf_rechecked':True,'normalized_product_sources_identical_to_accepted_candidate':True}
(task/'daily-merge-final-archive.json').write_text(json.dumps(record,indent=2),encoding='utf8');print(json.dumps(record,indent=2))
