"""Run the emitted gate for both distinct switch topologies and corruption cases."""
import json
from pathlib import Path
import re
import subprocess

import pytest
from e19_project_fixture import E19Project_Create
from sx1278_project_fixture import Sx1278Project_Create
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope


@pytest.fixture(scope='module', params=('e32','e19'))
def radio_architecture(request, builtin_catalog, tmp_path_factory):
    root = tmp_path_factory.mktemp(request.param)
    model = (E19Project_Create if request.param=='e19' else Sx1278Project_Create)(builtin_catalog,root/'input')
    TargetGeneration_Apply(model,builtin_catalog,WorkspacePolicy(root/'input'),root/'generated',TargetScope.FLIGHT)
    return root/'generated/Flight_Controller',request.param


def Architecture_Run(project, label):
    command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','Tools/check_architecture.ps1']
    result=subprocess.run(command,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=180,check=False)
    (project/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf8')
    return result


def test_each_explicit_topology_passes_emitted_gate(radio_architecture):
    project,_module=radio_architecture
    result=Architecture_Run(project,'valid')
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mutation',('module','macro','duplicate_macro','alias_pin','missing_pin','frontend_publication'))
def test_changed_identity_or_resource_contract_is_still_rejected(radio_architecture,mutation):
    project,module=radio_architecture
    path=project/'SilverStar.ssproject'
    text=path.read_text(encoding='utf8')
    if mutation in ('macro','duplicate_macro'):
        path=project/'Generated/Inc/air_link_config.h';text=path.read_text(encoding='utf8')
        changed=(text+'\n#define AIR_LINK_SX1278_DIO4_FRONTEND 0U\n' if mutation=='duplicate_macro' else
            re.sub(r'(AIR_LINK_SX1278_DIO4_FRONTEND )([01])U',lambda m:m[1]+str(1-int(m[2]))+'U',text))
    elif mutation=='frontend_publication':
        path=project/'Generated/Src/project_resources.c';text=path.read_text(encoding='utf8')
        value='((PlatformGpioId)0U)' if module=='e19' else '(PlatformGpioId)PLATFORM_GPIO_COUNT'
        changed=re.sub(r'\.rx_en = [^,\n}]+','.rx_en = '+value,text,count=1)
    else:
        document=json.loads(text);owner=document['air_link']['flight_radio_instance']
        if mutation=='module':
            next(row for row in document['components']['devices'] if row['instance_id']==owner)['module_variant']='unreviewed'
        elif mutation=='alias_pin':
            document['resources'][owner+':radio_reset']=document['resources'][owner+':radio_nss']
        else:
            del document['resources'][owner+':radio_nss']
        changed=json.dumps(document)
    assert changed!=text
    original=path.read_bytes()
    try:
        path.write_text(changed,encoding='utf8')
        result=Architecture_Run(project,mutation)
        assert result.returncode!=0
        assert 'SX1278' in result.stdout or 'E19' in result.stdout
    finally:
        path.write_bytes(original)
