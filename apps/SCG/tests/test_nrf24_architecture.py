"""Backend selection preserves SX rules and fails closed for NRF corruption."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

import pytest

from silverstar_fccg.app.service import FccgService


def _Architecture_Run(project,case):
    command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(project/'Tools/check_architecture.ps1')]
    result=subprocess.run(command,cwd=project,capture_output=True,timeout=90)
    (project/('architecture-'+case+'.stdout.bin')).write_bytes(result.stdout)
    (project/('architecture-'+case+'.stderr.bin')).write_bytes(result.stderr)
    (project/('architecture-'+case+'.command.json')).write_text(json.dumps({
        'command':command,'cwd':str(project),'exit_code':result.returncode}),encoding='utf8')
    result.stdout=result.stdout.decode('utf8',errors='replace')
    result.stderr=result.stderr.decode('utf8',errors='replace')
    (project/('architecture-'+case+'.log')).write_text(result.stdout+result.stderr,encoding='utf8')
    return result


@pytest.fixture(scope='module',params=['sx','nrf'])
def radio_architecture(request,workspace_root,tmp_path_factory):
    root=tmp_path_factory.mktemp('backend_'+request.param)
    if request.param=='sx':
        service=FccgService(workspace_root)
        model=service.ProjectConfiguration_Reconcile(service.ReferenceProject_Create('BackendGate')).model
        service.Project_Save(model,root,confirm_dangerous=True)
        return root,'sx'
    # Keep the hash-addressed Cube snapshot below Windows MAX_PATH. This is a
    # fresh, small generated fixture, retained for evidence; no existing copy.
    short_root=Path(tempfile.mkdtemp(prefix='nrf_gate_',dir=workspace_root.parents[1]/'.work'))
    output=short_root/'fresh'
    (root/'nrf_project_path.txt').write_text(str(output/'project/Flight_Controller'),encoding='utf8')
    result=subprocess.run([sys.executable,str(workspace_root/'tools/nrf24_checkpoint.py'),str(output)],
        capture_output=True,text=True,encoding='utf8',timeout=90)
    (root/'generation.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode==0,result.stdout+result.stderr
    return output/'project/Flight_Controller','nrf'


def test_backend_gate_complete_selected_driver(radio_architecture):
    project,backend=radio_architecture
    result=_Architecture_Run(project,'complete_'+backend)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('case',['missing_driver','missing_resource','missing_source','mixed_backend','unselected_source','header_backend'])
def test_backend_gate_rejects_corrupt_selected_contract(radio_architecture,case):
    project,backend=radio_architecture
    saved=project/'SilverStar.ssproject'
    graph=project/'Generated/project_sources.mk'
    header=project/'Generated/Inc/project_resources.h'
    air_header=project/'Generated/Inc/air_link_config.h'
    source=project/('Devices/Telemetry/NRF24L01P/Src/nrf24_device.c' if backend=='nrf'
        else 'Devices/Telemetry/SX1281/Src/sx1281_device.c')
    original={path:path.read_bytes() for path in (saved,graph,header,air_header)}
    detached=project/('negative_detached_'+backend+'.c')
    try:
        if case=='missing_driver':
            assert source.resolve().is_relative_to(project.resolve())
            assert detached.resolve().is_relative_to(project.resolve())
            source.rename(detached)
        elif case=='missing_source':
            graph.write_text(graph.read_text(encoding='utf8').replace('  '+source.relative_to(project).as_posix(),
                '  Devices/Telemetry/missing_driver.c'),encoding='utf8')
        elif case=='mixed_backend':
            data=json.loads(saved.read_text(encoding='utf8'))
            data['components']['devices'].append({'instance_id':'mixed_radio','plugin':
                'silverstar.device.telemetry.sx1281' if backend=='nrf' else 'silverstar.device.telemetry.nrf24l01p'})
            saved.write_text(json.dumps(data),encoding='utf8')
        elif case=='unselected_source':
            other='SX1281' if backend=='nrf' else 'NRF24L01P'
            with graph.open('a',encoding='utf8') as output:
                output.write('\nC_SOURCES += Devices/Telemetry/'+other+'/Src/unselected.c\n')
        elif case=='header_backend':
            token='AIR_LINK_NRF24_CHANNEL' if backend=='nrf' else 'AIR_LINK_SX128X_SF'
            air_header.write_text(air_header.read_text(encoding='utf8').replace(token,'BROKEN_BACKEND'),encoding='utf8')
        elif backend=='nrf':
            data=json.loads(saved.read_text(encoding='utf8'))
            del data['resources'][data['air_link']['flight_radio_instance']+':radio_ce']
            saved.write_text(json.dumps(data),encoding='utf8')
        else:
            source.write_text(source.read_text(encoding='utf8').replace('PROJECT_SX1281_INSTANCE_COUNT_MAX',
                'BROKEN_CONTEXT_BOUND'),encoding='utf8')
        result=_Architecture_Run(project,case+'_'+backend)
        assert result.returncode!=0,result.stdout+result.stderr
        expected=('radio driver' if case in ('missing_source','missing_driver') else 'multiple backends'
            if case=='mixed_backend' else 'Unselected radio backend' if case=='unselected_source'
            else 'AIR header backend' if case=='header_backend' else 'resource binding is missing' if backend=='nrf'
            else 'multi-instance bound is not consumed')
        assert expected in result.stdout,result.stdout+result.stderr
    finally:
        if case=='missing_driver': detached.rename(source)
        elif case=='missing_resource' and backend=='sx':
            source.write_text(source.read_text(encoding='utf8').replace('BROKEN_CONTEXT_BOUND',
                'PROJECT_SX1281_INSTANCE_COUNT_MAX'),encoding='utf8')
        for path,data in original.items(): path.write_bytes(data)


@pytest.fixture(scope='module')
def paired_ground(workspace_root,tmp_path_factory):
    import importlib.util
    short=Path(tempfile.mkdtemp(prefix='nrf_pair_',dir=workspace_root.parents[1]/'.work'))/'fresh'
    result=subprocess.run([sys.executable,str(workspace_root/'tools/nrf24_checkpoint.py'),str(short),'--paired'],capture_output=True,text=True,encoding='utf8',timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    project=short/'project/Ground_Station'
    spec=importlib.util.spec_from_file_location('nrf_ground_gate',project/'Tools/check_ground.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    flight=(short/'project/Flight_Controller/Generated/Inc/air_link_config.h').read_text(encoding='utf8')
    ground=(project/'Generated/Inc/air_link_config.h').read_text(encoding='utf8')
    for macro in ('CHANNEL','RF_SETUP','ADDRESS_BYTES','RETRY_SETUP','DATA_RATE_KBPS'):
        import re
        key='AIR_LINK_NRF24_'+macro
        assert re.search(r'#define '+key+r' (.+)',flight)[1]==re.search(r'#define '+key+r' (.+)',ground)[1]
    return project,module


def test_nrf_ground_gate_and_matching_endpoint_parameters(paired_ground):
    project,module=paired_ground
    module.Architecture_Check(project.resolve())


@pytest.mark.parametrize('case',['backend','metric_dispatch','pin_collision','count','source'])
def test_nrf_ground_gate_rejects_selected_backend_corruption(paired_ground,case):
    project,module=paired_ground
    header=project/'Generated/Inc/ground_radio_config.h'
    resource=project/'Generated/Src/project_resources.c'
    bounds=project/'Generated/Inc/project_resources.h'
    metadata=project/'Generated/ground_target_metadata.json'
    source=project/'Devices/Telemetry/NRF24L01P/Src/nrf24_device.c'
    original={p:p.read_bytes() for p in (header,resource,bounds,metadata,source)}
    try:
        if case=='backend':
            data=json.loads(metadata.read_text(encoding='utf8'));data['radio_family']='sx128x';metadata.write_text(json.dumps(data),encoding='utf8')
        elif case=='metric_dispatch':header.write_text(header.read_text(encoding='utf8').replace('GROUND_RADIO_BACKEND_NRF24','BROKEN_BACKEND'),encoding='utf8')
        elif case=='pin_collision':resource.write_text(resource.read_text(encoding='utf8').replace('.ce = PLATFORM_GPIO_1','.ce = PLATFORM_GPIO_0'),encoding='utf8')
        elif case=='count':bounds.write_text(bounds.read_text(encoding='utf8').replace('COUNT_MAX           1U','COUNT_MAX           2U'),encoding='utf8')
        else:source.rename(source.with_suffix('.detached'))
        with pytest.raises(ValueError):module.Architecture_Check(project.resolve())
    finally:
        if source.with_suffix('.detached').exists():source.with_suffix('.detached').rename(source)
        for path,data in original.items():path.write_bytes(data)


@pytest.mark.parametrize('case',['typed','alias_collision','wrong_type','out_of_range','unconfigured','expression'])
def test_nrf_ground_imported_resource_binding_grammar(paired_ground,case):
    project,module=paired_ground
    resource=project/'Generated/Src/project_resources.c'
    original=resource.read_bytes()
    try:
        text=resource.read_text(encoding='utf8')
        text=text.replace('.spi = PLATFORM_SPI_1','.spi = ((PlatformSpiId)0U)')
        text=text.replace('.csn = PLATFORM_GPIO_0','.csn = ((PlatformGpioId)0U)')
        text=text.replace('.ce = PLATFORM_GPIO_1','.ce = ((PlatformGpioId)1U)')
        text=text.replace('.time = PLATFORM_TIME_1','.time = ((PlatformTimeId)0U)')
        if case=='alias_collision':text=text.replace('.ce = ((PlatformGpioId)1U)','.ce = PLATFORM_GPIO_0')
        elif case=='wrong_type':text=text.replace('.ce = ((PlatformGpioId)1U)','.ce = ((PlatformSpiId)1U)')
        elif case=='out_of_range':text=text.replace('.ce = ((PlatformGpioId)1U)','.ce = ((PlatformGpioId)96U)')
        elif case=='unconfigured':text=text.replace('.ce = ((PlatformGpioId)1U)','.ce = ((PlatformGpioId)90U)')
        elif case=='expression':text=text.replace('.ce = ((PlatformGpioId)1U)','.ce = ((PlatformGpioId)(0U+1U))')
        resource.write_text(text,encoding='utf8')
        if case=='typed':module.Architecture_Check(project.resolve())
        else:
            with pytest.raises(ValueError):module.Architecture_Check(project.resolve())
    finally:
        resource.write_bytes(original)
