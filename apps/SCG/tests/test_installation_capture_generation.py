"""Optional declarative source ownership/default-off composition; no hardware."""
from dataclasses import replace
import os
import shutil
import subprocess
import pytest

from silverstar_fccg.generator.render import GeneratedFiles_Render,MetadataFiles_Render,_InstallationCaptureHeader_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create

PLUGIN='silverstar.installation.capture'


def test_default_generation_has_no_capture_code_state_or_new_algorithm_choice(builtin_catalog):
    model=ReferenceProject_Create('CaptureOff',catalog=builtin_catalog)
    graph=SourceGraph_Resolve(model,builtin_catalog)
    assert PLUGIN not in model.ComponentIds_Get()
    assert not any('InstallationCapture' in source for source in graph.sources)
    assert 'SYSTEM_INSTALLATION_CAPTURE_ENABLED=1' not in graph.defines
    assert 'Generated/Inc/project_installation_capture.h' not in GeneratedFiles_Render(model,builtin_catalog,graph)
    assert builtin_catalog.Component_Get(PLUGIN).selection is None


def test_opt_in_owns_real_sources_and_generated_endpoint_labels(builtin_catalog):
    model=ReferenceProject_Create('CaptureOn',catalog=builtin_catalog)
    model.device_instances=[replace(item,profile='jy901b_mag_capture')
        if item.plugin=='silverstar.device.imu.jy901b' else item for item in model.device_instances]
    model.base_components.append(PLUGIN)
    strategies=dict(model.strategies)
    graph=SourceGraph_Resolve(model,builtin_catalog)
    assert 'Modules/InstallationCapture/Src/system_installation_capture.c' in graph.sources
    assert 'SYSTEM_INSTALLATION_CAPTURE_ENABLED=1' in graph.defines
    files=GeneratedFiles_Render(model,builtin_catalog,graph)
    text=files['Generated/Inc/project_installation_capture.h'].decode()
    assert 'silverstar.device.imu.jy901b' in text and 'Unknown boot/native raw/time' in text
    assert model.strategies==strategies


def test_missing_endpoint_or_maintenance_rejects_opt_in(builtin_catalog):
    model=ReferenceProject_Create('CaptureIncomplete',catalog=builtin_catalog)
    model.base_components.append(PLUGIN)
    with pytest.raises(ValueError,match='one IMU and one MAG'):
        _InstallationCaptureHeader_Render(model,builtin_catalog.ProjectView_Get(model))
    model.protocols['maintenance']=None
    with pytest.raises(ValueError,match='maintenance owner'):
        _InstallationCaptureHeader_Render(model,builtin_catalog.ProjectView_Get(model))


def test_large_source_graph_listing_executes_without_one_long_shell_command(builtin_catalog,tmp_path):
    make=shutil.which('mingw32-make') or shutil.which('make')
    if make is None:pytest.skip('GNU make is unavailable')
    model=ReferenceProject_Create('CaptureList',catalog=builtin_catalog)
    model.device_instances=[replace(item,profile='jy901b_mag_capture')
        if item.plugin=='silverstar.device.imu.jy901b' else item for item in model.device_instances]
    model.base_components.append(PLUGIN)
    graph=SourceGraph_Resolve(model,builtin_catalog)
    files={**GeneratedFiles_Render(model,builtin_catalog,graph),**MetadataFiles_Render(model,builtin_catalog,graph)}
    for name in ('Makefile','Targets/SilverStar_F407/target.mk','Generated/project_sources.mk'):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(files[name])
    result=subprocess.run([make,'-s','list-sources'],cwd=tmp_path,capture_output=True,text=True,
        timeout=15,env={**os.environ,'SHELL':os.environ.get('COMSPEC','/bin/sh')})
    assert result.returncode==0,result.stderr
    assert result.stdout.splitlines()==[*graph.sources,'Assembly: '+' '.join(graph.asm_sources)]
