from pathlib import Path
from zipfile import ZipFile
import json,hashlib,difflib
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out=repo/'docs/architecture/field_gui_integration_20261002'
frozen=Path(r'D:\python_software\SilverStar\.work\FieldIntegration_20261002\.work\FieldFreeze_20261002')
archive=frozen/'SS_FieldIntegration_20261002_SourceFirmware.zip'
freeze_manifest=json.loads((frozen/'freeze_manifest.json').read_text(encoding='utf-8'))
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
assert digest==freeze_manifest['zip_sha256']
selected=lambda p:p.suffix.lower() in ('.c','.h','.s','.ld','.mk','.py','.ps1') or p.name.lower()=='makefile'
projects={'existing_legacy':repo/'.work/field_gui_existing_legacy','new_auto':repo/'.work/field_gui_new_auto'}
comparisons={}
with ZipFile(archive) as z:
    for name,project in projects.items():
        comparisons[name]={}
        patch=[]
        for target in ('Flight_Controller','Ground_Station'):
            prefix='Generated/'+target+'/'
            before={n[len(prefix):]:z.read(n) for n in z.namelist() if n.startswith(prefix) and selected(Path(n)) and not any(part in ('Build','build','__pycache__') for part in Path(n[len(prefix):]).parts)}
            assert before
            after={str(p.relative_to(project/target)).replace('\\','/'):p.read_bytes() for p in (project/target).rglob('*') if p.is_file() and selected(p) and not any(part in ('Build','build','__pycache__') for part in p.relative_to(project/target).parts)}
            changes=[]
            for p in sorted(before.keys()|after.keys()):
                old,new=before.get(p),after.get(p)
                if old==new:continue
                changes.append({'path':p,'frozen_sha256':hashlib.sha256(old).hexdigest() if old is not None else None,'new_sha256':hashlib.sha256(new).hexdigest() if new is not None else None,'change':'added' if old is None else 'removed' if new is None else 'changed'})
                patch.extend(difflib.unified_diff((old or b'').decode('utf-8',errors='replace').splitlines(keepends=True),(new or b'').decode('utf-8',errors='replace').splitlines(keepends=True),fromfile='frozen/'+target+'/'+p,tofile=name+'/'+target+'/'+p))
            comparisons[name][target]={'frozen_source_count':len(before),'new_source_count':len(after),'equal_count':sum(before.get(p)==b for p,b in after.items()),'differences':changes}
            print(name,target,'equal',comparisons[name][target]['equal_count'],'differences',len(changes))
            if name=='existing_legacy':print('\n'.join(c['path'] for c in changes))
        (out/(name+'_vs_frozen_source.patch')).write_text(''.join(patch),encoding='utf-8')
(out/'source_vs_frozen.json').write_text(json.dumps(comparisons,indent=2)+'\n',encoding='utf-8')
(out/'frozen_comparison_identity.json').write_text(json.dumps({'archive':str(archive),'sha256':digest,'source_commit':freeze_manifest['source_commit'],'evidence_commit':freeze_manifest['evidence_commit'],'comparison':'raw archived Generated sources; no CRLF normalization; excludes build artifacts; includes assembly'},indent=2)+'\n',encoding='utf-8')
