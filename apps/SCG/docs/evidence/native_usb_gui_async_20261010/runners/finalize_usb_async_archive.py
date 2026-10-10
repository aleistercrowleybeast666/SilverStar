from pathlib import Path
import json,hashlib
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar\.work\ccdi');root=repo/'apps/SCG/docs/evidence/native_usb_gui_async_20261010'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=root/'verification.json';d=json.loads(p.read_text(encoding='utf8'))
assert sha(p)=='3ac3d085b69bd3661ab33396b2f68bd763c5b47dfa1cef298e240de88af4182b'
for name,digest in d['files_sha256'].items():assert sha(root/name)==digest,name
runner=task/'package_usb_async_evidence.py'
s=runner.read_text(encoding='utf8')
s=s.replace('unchanged original candidate/model/receipt/ELF bytes asserted by fixture','unchanged original compiler/backend receipts and normal/analyzer ELF bytes asserted by fixture')
s=s.replace("'Devices/','Platform/'","'Devices/','Interfaces/','Tests/','Platform/'")
runner.write_text(s,encoding='utf8',newline='\n');(root/'runners/package_usb_async_evidence.py').write_bytes(runner.read_bytes())
d['refresh_fixture_scope']='Read-only inspection of actual previous ug08 compiled legal candidates; unchanged original compiler/backend receipts and normal/analyzer ELF bytes asserted by fixture. Fresh ua04 builds separately test real buttons.'
added=[]
for b in d['builds']:
    output=Path(b['output']);base=root/'final'/b['part'];receipt=json.loads((base/'receipt.json').read_text())
    for relative,digest in receipt['experimental_files_sha256'].items():
        dest=base/relative;src=output/relative
        assert sha(src)==digest,(b['part'],relative)
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(src.read_bytes());added.append(dest.relative_to(root).as_posix())
        assert sha(dest)==digest,(b['part'],relative)
(root/'runners/finalize_usb_async_archive.py').write_bytes(Path(__file__).read_bytes())
d['all_declared_generated_files_retained']=True
d['archive_finalization']='Verified all original archived bytes, corrected fixture scope to actual receipt/ELF assertions and added every declared generated file omitted by the initial selected-prefix filter; original vendor input bytes remain pinned at their receipt paths.'
d['files_sha256']={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='verification.json'}
d['listed_bytes']=sum((root/x).stat().st_size for x in d['files_sha256'])
p.write_text(json.dumps(d,indent=2),encoding='utf8',newline='\n')
summary=json.loads((task/'usb-async-archive-summary.json').read_text())
summary.update(listed_files=len(d['files_sha256']),listed_bytes=d['listed_bytes'],manifest_sha256=sha(p))
(task/'usb-async-archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps({'added':len(added),'listed_files':len(d['files_sha256']),'manifest_sha256':sha(p)}))
