from pathlib import Path
import json,hashlib,subprocess,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
DOC=ROOT/'docs/FCCG/software_recovery_stage1_20261001'
DOC.mkdir(exist_ok=True)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
changed=subprocess.check_output(['git','diff','--name-only','24f29c5',commit],cwd=ROOT,text=True).splitlines()
source={name:digest(ROOT/name) for name in changed if (ROOT/name).is_file()}
inputs={}
artifacts={}
for project in ['candidate_a_v4','candidate_b_v4']:
 for p in (OUT/project).rglob('*'):
  if not p.is_file():continue
  if p.suffix in ['.elf','.bin','.hex','.map','.ssproject','.ssdecoder','.su']:
   artifacts[str(p.resolve())]=digest(p)
  if p.suffix in ['.c','.h','.s','.ld','.ioc','.mk'] or p.name=='Makefile':
   inputs[str(p.relative_to(OUT))]=digest(p)
copied={}
for p in OUT.iterdir():
 if p.is_file() and p.suffix in ['.log','.json','.py','.png']:
  shutil.copy2(p,DOC/p.name);copied[p.name]=digest(p)
owner=ROOT/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload'
matches={}
for rel in ['Modules/Src/telemetry_service.c','Tests/Host/test_telemetry.c','Tests/Host/test_runtime_commands.c']:
 matches[rel]=digest(owner/rel)==digest(OUT/'candidate_a_v4/Flight_Controller'/rel)
manifest=dict(utc=datetime.now(timezone.utc).isoformat(),source_commit=commit,
 branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
 source_sha256=source,generated_owner_source_matches=matches,
 artifacts_sha256=artifacts,generated_inputs_sha256=inputs,evidence_sha256=copied,
 gate_stages=json.loads((OUT/'gate_results_v4.json').read_text()),
 host_rerun=json.loads((OUT/'host_rerun.json').read_text()) if (OUT/'host_rerun.json').exists() else 'PENDING',
 hardware_actions=False,manual_critical_contract_review='NOT_PROVEN',
 whole_firmware_stack_bound='NOT_PROVEN',full_acceptance='INCOMPLETE')
(DOC/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'source_commit':commit,'owner_matches':matches,'host_rerun':manifest['host_rerun'],
 'delivery':str(DOC),'firmware':{p:h for p,h in artifacts.items() if p.endswith(('.elf','.bin')) and 'StaticAnalysis' not in p}},indent=2),flush=True)
