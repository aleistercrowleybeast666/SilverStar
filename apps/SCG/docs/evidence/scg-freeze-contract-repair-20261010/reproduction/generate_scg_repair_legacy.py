from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib,tempfile,subprocess,re
repo=Path(__file__).parent/'r';task=Path(__file__).parent;sys.path.insert(0,str(repo/'apps/SCG/src'));sys.path.insert(0,str(repo/'apps/SCG/tests'))
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.multi_target import GroundFiles_Render
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from test_round2_targets import _GroundBoardProject_Get
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
catalog=PluginCatalog(repo/'apps/SCG/plugins/builtin',repo/'apps/SCG/plugins/installed');catalog.Scan()
temp=Path(tempfile.mkdtemp(prefix='scg-repair-legacy-'));policy=WorkspacePolicy(temp)
flight=temp/'Flight_Controller';assembler=ProjectAssembler(policy,catalog);model=ReferenceProject_Create('SCGFreezeFlight',catalog=catalog)
plan=assembler.Plan(model,flight);assert plan.valid;assembler.Apply(model,plan)
ground=temp/'Ground_Station';ground.mkdir();gm=_GroundBoardProject_Get(catalog)
files=GroundFiles_Render(gm,catalog,policy)
for name,body in files.items():p=ground/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
ProjectRoot_Save(gm,ground,create_new=False)
rows=[]
for kind,root in [('Flight',flight),('GroundUART',ground)]:
    make=(root/'Makefile').read_text(encoding='utf8');targets=re.findall(r'(?m)^([a-zA-Z][\w-]*)\s*:(?![=])',make)
    row={'kind':kind,'root':str(root),'makefile_sha256':hashlib.sha256((root/'Makefile').read_bytes()).hexdigest(),
      'targets':targets,'model_sha256':hashlib.sha256((root/'SilverStar.ssproject').read_bytes()).hexdigest(),
      'input_files_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}}
    rows.append(row)
d={'source_commit':head,'created_utc':datetime.now(timezone.utc).isoformat(),'temporary_root':str(temp),'projects':rows,
 'scope':'Fresh reference Flight and traditional verified-board Ground UART, original daily templates, Temp outputs only; no FINAL/user project changes or hardware'}
(task/'sr-legacy-generated.json').write_text(json.dumps(d,indent=2),encoding='utf8')
print(json.dumps({'source_commit':head,'projects':[{k:r[k] for k in ['kind','root','targets']} for r in rows]},indent=2))
