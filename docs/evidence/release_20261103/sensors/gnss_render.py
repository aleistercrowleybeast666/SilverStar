"""Inspect the normal generated flight header, actual device bindings and selected C."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SCG=ROOT/'apps/SCG'
sys.path.insert(0,str(SCG/'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate

sys.path.insert(0, str(SCG/'tests'))
from test_joint_sensor_generation import _GnssNavigationModel_Create
service=FccgService(SCG)
result=[]
for model_name in ['neo_m8n','neo_m9n','max_m10s','neo_f10n']:
    for profile,expected in [('', 'AIRBORNE_4G'), ('portable_ground_test','PORTABLE')]:
        model=ReferenceProject_Create('GNSS_'+model_name,catalog=service.catalog)
        if model_name != 'neo_m9n':
            work=ROOT/'.work/release-20261103/sensors/gnss-render-v2'/model_name/(profile or 'default')
            work.mkdir(parents=True,exist_ok=False)
            model=_GnssNavigationModel_Create(service.catalog,'silverstar.device.gnss.'+model_name,work)
        model.device_instances=[replace(d,plugin='silverstar.device.gnss.'+model_name,
            interface='uart',profile=profile) if d.plugin.startswith('silverstar.device.gnss.') else d for d in model.device_instances]
        model=service.ProjectConfiguration_Reconcile(model).model
        valid=Project_Validate(model,service.catalog)
        assert valid.valid,valid
        graph=SourceGraph_Resolve(model,service.catalog)
        emitted=GeneratedFiles_Render(model,service.catalog,graph)
        h=emitted['Generated/Inc/project_flight_config.h']
        c=emitted['Generated/Src/project_resources.c']
        expected='SYSTEM_GNSS_DYNAMIC_MODEL_'+expected
        define=re.search(rb'#define SYSTEM_GNSS_DYNAMIC_MODEL\s+(\w+)',h).group(1).decode()
        assert define==expected
        if model_name!='neo_m9n':
            assert ('.dynamic_model = '+expected).encode() in c
        result.append(dict(part=model_name, saved_profile=profile, generated=define,
            binding=('system startup broadcasts to dedicated M9 driver' if model_name=='neo_m9n'
                else 'per-instance resource field + typed adapter'),
            header_sha256=hashlib.sha256(h).hexdigest(), resources_sha256=hashlib.sha256(c).hexdigest(),
            gnss_c=[s for s in graph.sources if s.startswith('Devices/GNSS/')]))
        print(model_name,profile or 'default',define,flush=True)
(HERE/sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
