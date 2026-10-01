import csv, datetime, hashlib, importlib.metadata, json, pathlib, shutil, subprocess, sys, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
evidence=root/'docs/GSHC/gui_layout_20261001_v1'
output=root/'.work/SCG_011_KF6_e02cca1_v1'
def inventory(path, paths, base):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['path','bytes','sha256'])
        for item in sorted(paths):
            writer.writerow([item.relative_to(base).as_posix(),item.stat().st_size,hashlib.sha256(item.read_bytes()).hexdigest()])
names=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root).decode().splitlines()
names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root).decode().splitlines()
sources=sorted({root/name for name in names if not name.startswith('docs/GSHC/gui_layout_20261001_v1/')})
inventory(evidence/'source_hashes.csv',sources,root)
inventory(evidence/'generated_hashes.csv',[p for p in output.rglob('*') if p.is_file()],output)
(evidence/'final_source.diff').write_bytes(subprocess.check_output(['git','diff','--binary','HEAD','--','.',':(exclude)docs/GSHC/gui_layout_20261001_v1'],cwd=root))
helpers=evidence/'reproduction'
helpers.mkdir(exist_ok=True)
for name in ('release011_run.py','release011_generate.py','release011_capture.py','release011_capture_gshc.py','gshc_layout_capture.py','release011_evidence.py','release011_whitespace.py'):
    shutil.copyfile(root/'.work'/name,helpers/name)
versions={'python':sys.version,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()}
for name in ('PySide6','pytest','pyqtgraph','PyOpenGL','PyInstaller'):
    versions[name]=importlib.metadata.version(name)
(evidence/'tool_versions.json').write_text(json.dumps(versions,indent=2)+'\n',encoding='utf-8')
version='0.1.1'
assert (root/'VERSION').read_text().strip()==version
configuration=json.loads((output/'SilverStar.ssproject').read_text(encoding='utf-8'))
assert configuration['project']['firmware_version']==version
assert configuration['components']['core']=='silverstar.core.0_1_0'
decoder=output/'SCG_Closeout_KF6_v1.ssdecoder'
with zipfile.ZipFile(decoder) as package:
    objects={name:json.loads(package.read(name)) for name in package.namelist() if name.endswith('.json')}
assert any(version in json.dumps(value) for value in objects.values())
matches=[]
for role in ('Flight_Controller','Ground_Station'):
    for path in (output/role).rglob('*'):
        if path.is_file() and path.suffix in ('.h','.c','.json','.mk') and b'0.1.1' in path.read_bytes():
            matches.append(path.relative_to(output).as_posix())
assert any(item.startswith('Flight_Controller/') for item in matches)
assert any(item.startswith('Ground_Station/') for item in matches)
(evidence/'generated_identity.json').write_text(json.dumps(dict(version=version,matching_generated_files=matches,decoder_sha256=hashlib.sha256(decoder.read_bytes()).hexdigest(),decoder_json_members=list(objects)),indent=2)+'\n',encoding='utf-8')
for path in evidence.rglob('*'):
    if path.is_file() and path.suffix in ('.json','.log','.diff','.md','.py'):
        assert (b'X-Amz'+b'-Signature=') not in path.read_bytes() and (b'X-Goog'+b'-Signature=') not in path.read_bytes(),path
inventory(evidence/'artifact_hashes.csv',[p for p in evidence.rglob('*') if p.is_file() and p.name!='artifact_hashes.csv'],evidence)
print(json.dumps(dict(source_count=len(sources),output_files=sum(p.is_file() for p in output.rglob('*')),identity=version),indent=2))
