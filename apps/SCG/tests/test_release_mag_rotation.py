"""Actual C implementation with synthetic input and Host device ports."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pytest

SCG=Path(__file__).resolve().parents[1]
BUILTIN=SCG/'plugins/builtin'
CORE=BUILTIN/'silverstar_core_0_1_0/payload'
PLUGIN=BUILTIN/'silverstar_mag_rotation/payload'
MATH=PLUGIN/'Algorithm/Installation/MagRotation'

@pytest.mark.parametrize("mode",["math","runtime","confirmed_fixed"])
def test_estimator_and_runtime(tmp_path,mode):
    includes=[MATH/'Inc',CORE/'Tests/Host/mag_calibration',CORE/'Interfaces/Inc',CORE/'Common/Inc',
        CORE/'System/Inc',CORE/'System/Inertial/Inc',CORE/'System/Calibration/Inc',CORE/'APP/Inc',CORE/'System/User',
        BUILTIN/'silverstar_platform_api/payload/Platform/Inc',
        BUILTIN/'silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/Inc',
        BUILTIN/'silverstar_algorithm_calibration/payload/Algorithm/Calibration/Inc']
    src=[MATH/'Src/mag_rotation.c']
    if mode=='math':
        src.append(SCG/'tests/fixtures/sensors/test_mag_rotation.c')
    else:
        src.extend([MATH/'Src/mag_rotation_runtime.c',PLUGIN/'Tests/Host/test_mag_rotation_runtime.c'])
    exe=tmp_path/'rotation.exe'
    command=[shutil.which('gcc'),'-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Wconversion',
        '-Wsign-conversion','-Wshadow','-Wundef','-Wdouble-promotion','-Wstrict-prototypes','-Wmissing-prototypes',
        '-fanalyzer','-DSYSTEM_MAG_ROTATION_ENABLED=1U',
        '-DSYSTEM_INSTALLATION_CAPTURE_ENABLED='+('1U' if mode=='confirmed_fixed' else '0U'),
        *['-I'+str(p) for p in includes],*[str(p) for p in src],'-lm','-o',str(exe)]
    rows=[]
    for stage,invocation in [('compile',command),('run',[str(exe)])]:
        with (tmp_path/(stage+'.log')).open('wb') as output:
            result=subprocess.run(invocation,stdout=output,stderr=subprocess.STDOUT,timeout=90)
        rows.append({'command':invocation,'exit_code':result.returncode})
        (tmp_path/'commands.json').write_text(json.dumps({'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in src},'rows':rows},indent=2),encoding='utf8')
        assert result.returncode==0,(tmp_path/(stage+'.log')).read_text(encoding='utf8',errors='replace')

@pytest.mark.parametrize("part",["neo_m8n","neo_m9n","max_m10s","neo_f10n"])
def test_saved_gnss_profile_readback_and_render(part,builtin_catalog,tmp_path):
    from dataclasses import replace
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.model import ProjectModel_Load
    from silverstar_fccg.generator.render import _DeviceRuntimeDefaults_Get
    m=ReferenceProject_Create('GnssProfile',catalog=builtin_catalog)
    c='silverstar.device.gnss.'+part
    for profile,expected in [('', 'AIRBORNE_4G'),('portable_ground_test','PORTABLE')]:
        m.device_instances=[replace(item,plugin=c,interface='uart',profile=profile) if item.plugin.startswith('silverstar.device.gnss.') else item for item in m.device_instances]
        file=tmp_path/'model.ssproject';file.write_text(json.dumps(m.Dictionary_Get()),encoding='utf8')
        original=file.read_bytes()
        loaded=ProjectModel_Load(file)
        assert dict(_DeviceRuntimeDefaults_Get(loaded,builtin_catalog))['SYSTEM_GNSS_DYNAMIC_MODEL']=='SYSTEM_GNSS_DYNAMIC_MODEL_'+expected
        assert file.read_bytes()==original

def test_mixed_saved_gnss_models_are_not_broadcast_over_one_another(builtin_catalog, tmp_path):
    from dataclasses import replace
    from silverstar_fccg.project.model import ProjectModel_Load
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.validation import Project_Validate

    model = ReferenceProject_Create("TwoReceivers", catalog=builtin_catalog)
    first = next(item for item in model.device_instances if item.plugin.startswith("silverstar.device.gnss."))
    model.device_instances.append(replace(first, instance_id="portable_bench", interface="uart", profile="portable_ground_test"))
    path = tmp_path / "mixed.ssproject"
    path.write_text(json.dumps(model.Dictionary_Get()), encoding="utf8")
    original = path.read_bytes()
    loaded = ProjectModel_Load(path)
    issues = [i for i in Project_Validate(loaded, builtin_catalog).issues if i.code == "GNSS_BOOT_MODEL_CONFLICT"]
    assert len(issues) == 1
    for value in (first.instance_id, "portable_bench", "AIRBORNE_4G", "PORTABLE"):
        assert value in issues[0].message
    assert path.read_bytes() == original
