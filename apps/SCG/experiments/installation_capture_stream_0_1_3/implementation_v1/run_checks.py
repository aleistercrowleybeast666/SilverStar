"""Reproducible C/real-owner software checks. Never opens hardware or flashes."""
from pathlib import Path
from datetime import datetime,timezone
import ast
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time

from stack_report import Report_Build

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parents[4]
CODE=ROOT/'apps/SCG/plugins/builtin/silverstar_installation_capture/payload/Modules/InstallationCapture'
THIRD=CODE.parents[1]/'ThirdParty/InstallationCapture'
CORE=ROOT/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload'
TASK=ROOT/'.work/dev013_installation_c_impl_20261019_v1'


def fingerprint(path):
    data=path.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def sections(path):
    data=path.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    entries=[struct.unpack_from('<10I',data,h[6]+i*h[11]) for i in range(h[12])]
    record=entries[h[13]];names=data[record[4]:record[4]+record[5]]
    return {names[e[0]:].split(b'\0',1)[0].decode():{'address':e[3],'size':e[5],'type':e[1]} for e in entries}


def main():
    run=sys.argv[1] if len(sys.argv) in (2,3) else ''
    focused=len(sys.argv)==3 and sys.argv[2]=='focused'
    if re.fullmatch(r'r[1-9][0-9]{0,2}',run) is None:raise ValueError('fresh r<number> required')
    out=TASK/run;temp=ROOT/'.work'/('ci131019_'+run)
    if out.exists() or temp.exists():raise ValueError('fresh output and test directory required')
    out.mkdir();commands=[];started=time.monotonic()
    scratch=out/'temp';scratch.mkdir()
    env={**os.environ,'PYTHONPATH':str(ROOT/'apps/GSHC'),'PYTHONDONTWRITEBYTECODE':'1',
        'PYTHONIOENCODING':'utf-8','QT_QPA_PLATFORM':'offscreen','INSTALLATION_CAPTURE_DLL':str(out/'capture.dll'),
        'TEMP':str(scratch),'TMP':str(scratch),'TMPDIR':str(scratch)}
    def execute(label,args,timeout=120):
        timed_out=False
        with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
            try:
                result=subprocess.run([str(item) for item in args],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,timeout=timeout)
                code=result.returncode
            except subprocess.TimeoutExpired:
                code=124;timed_out=True
        commands.append({'label':label,'args':[str(item) for item in args],'exit':code,'timeout':timed_out})
        (out/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
        if code:raise RuntimeError(label+' failed; complete evidence retained')
        return (out/(label+'.stdout')).read_text(encoding='utf-8')
    candidate=Path('D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01')
    protected=json.loads((ROOT/'.work/dev013_installation_stream_20261019_v5/results.json').read_text(encoding='utf-8'))['protected_after']
    assert {path:fingerprint(candidate/path) for path in protected}==protected
    inputs=[p for base in (SOURCE,CODE,THIRD) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    inputs += [*list((ROOT/'apps/GSHC/services').glob('installation_calibration_*.py')),
        ROOT/'contracts/installation_calibration_v1.json',ROOT/'apps/GSHC/transport/installation_owner.py',
        ROOT/'apps/GSHC/transport/file_service_backend.py',ROOT/'apps/GSHC/ui/file_transfer.py',
        ROOT/'apps/GSHC/tests/test_installation_owner_adapter.py']
    inputs += [CORE/path for path in ('Interfaces/Inc/system_installation_capture_if.h',
        'Interfaces/Inc/system_installation_calibration_if.h','System/Calibration/Inc/system_mag_calibration.h',
        'System/Calibration/Src/system_mag_calibration.c','Common/Src/common_format.c',
        'System/Src/system_source_selector.c','System/Src/system_console.c','System/Inertial/Src/system_inertial.c')]
    inputs += [CODE.parents[2]/'plugin.json',ROOT/'apps/GSHC/tests/test_installation_candidate.py',
        ROOT/'apps/SCG/src/silverstar_fccg/generator/render.py',ROOT/'apps/SCG/tests/test_installation_capture_generation.py']
    inputs=list(dict.fromkeys(inputs))
    snapshot={str(path.relative_to(ROOT)):{'hex':path.read_bytes().hex(),**fingerprint(path)} for path in inputs}
    (out/'source_snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    old=json.loads((ROOT/'.work/dev013_installation_stream_proof_20261019_v1/reviewed_source_snapshot.json').read_text(encoding='utf-8'))
    ui='apps/GSHC/ui/file_transfer.py'
    def nonowner(raw):return [ast.dump(node,include_attributes=False) for node in ast.parse(raw).body if not(isinstance(node,ast.ClassDef) and node.name=='MaintenanceOwner')]
    assert nonowner(bytes.fromhex(old[ui]['hex']))==nonowner((ROOT/ui).read_text(encoding='utf-8'))
    old_ui=json.loads((ROOT/'.work/dev013_installation_calibration_20261018/software_baseline_20261019.json').read_text(encoding='utf-8'))['files']
    for path,sha in old_ui.items():
        if Path(path).as_posix().replace('\\','/')!=ui:assert fingerprint(ROOT/path)['sha256']==sha,path
    host=shutil.which('gcc');arm=shutil.which('arm-none-eabi-gcc');assert host and arm
    versions={'host':execute('host_version',[host,'--version']),'arm':execute('arm_version',[arm,'--version']),'python':sys.version}
    warnings=['-std=c11','-Wall','-Wextra','-Wconversion','-Wshadow','-Wstrict-prototypes','-Werror',
        '-DSYSTEM_INSTALLATION_CAPTURE_ENABLED=1']
    include=['-I'+str(path) for path in (CODE/'Inc',THIRD,CORE/'Interfaces/Inc',CORE/'Common/Inc',
        CORE/'System/Inc',CORE/'System/Calibration/Inc',CORE/'System/Inertial/Inc',SOURCE/'fixtures',CODE/'Src',
        ROOT/'apps/SCG/plugins/builtin/silverstar_algorithm_calibration/payload/Algorithm/Calibration/Inc',
        ROOT/'apps/SCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc',
        ROOT/'apps/SCG/plugins/builtin/silverstar_mcu_family_stm32f4/payload/Drivers/CMSIS/Include')]
    sources=[CODE/name for name in ('Src/installation_capture.c','Src/capture_info.c','Src/capture_primitives.c')]
    sources += [THIRD/'ryu/d2s.c',CODE/'Src/system_installation_capture.c']
    sources += [CORE/'Common/Src/common_format.c',SOURCE/'integration_stubs.c',SOURCE/'capture_dependency_stubs.c']
    host_sources=[SOURCE/'capture_test_access.c',*sources[1:],SOURCE/'capture_port_host.c']
    execute('host_compile',[host,*warnings,'-O2','-DRYU_ONLY_64_BIT_OPS',*include,
        '-shared',*host_sources,'-o',out/'capture.dll'])
    sources += [CODE/'Src/capture_port.c',ROOT/'apps/SCG/plugins/builtin/silverstar_mcu_family_stm32f4/payload/Platform/STM32F4/Src/platform_critical_stm32f4.c']
    target=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard']
    objects=[]
    for source in [*sources,SOURCE/'arm_entry.c']:
        label=source.stem;obj=out/(label+'.o');objects.append(obj)
        execute('arm_'+label,[arm,*warnings,*target,*include,'-Os','-ffreestanding','-fno-builtin',
            '-ffunction-sections','-fdata-sections','-fstack-usage','-c',source,'-o',obj])
        execute('analyzer_'+label,[arm,*warnings,*target,*include,'-O0','-ffreestanding','-fno-builtin',
            '-fanalyzer','-c',source,'-o',out/(label+'_analyzer.o')])
    execute('arm_link',[arm,*target,'-nostdlib','-Wl,--gc-sections','-Wl,-Map='+str(out/'candidate.map'),
        '-T',SOURCE/'candidate.ld',*objects,'-lm','-lc','-lgcc','-o',out/'candidate.elf'])
    prefix=str(Path(arm).parent/'arm-none-eabi-')
    assembly=execute('arm_disassembly',[prefix+'objdump.exe','-d',out/'candidate.elf'])
    symbols=execute('arm_symbols',[prefix+'nm.exe','-S','--defined-only',out/'candidate.elf'])
    assert not re.search(r'\b(malloc|calloc|realloc|free|printf|snprintf|strtod)\b',symbols)
    assert 'InstallationCapture_TestReset' not in symbols
    sec=sections(out/'candidate.elf')
    assert 1960<=sec['.capture_ccm']['size']<=2048 and sec['.capture_ccm']['address']==0x1000F5B8
    assert all(sec.get(name,{}).get('size',0)==0 for name in ('.data','.bss'))
    stack=Report_Build(out,assembly)
    (out/'module_stack.json').write_text(json.dumps(stack,indent=2),encoding='utf-8')
    targets=['apps/GSHC/tests/test_installation_calibration_backend.py','apps/GSHC/tests/test_installation_capture_contract.py',
        'apps/GSHC/tests/test_magnetometer_workflow.py','apps/GSHC/tests/test_magnetometer_transport.py',
        'apps/GSHC/tests/test_maintenance_api.py','apps/GSHC/tests/test_file_service_owner_classification.py',
        'apps/GSHC/tests/test_release_layout.py','apps/SCG/experiments/installation_calibration_0_1_3',
        'apps/SCG/experiments/installation_capture_stream_0_1_3/test_offline_proof.py',
        str(SOURCE/'test_c_capture.py'),'apps/GSHC/tests/test_installation_owner_adapter.py','apps/GSHC/tests/test_installation_candidate.py',
        'apps/GSHC/tests/test_file_transfer_ui.py','apps/GSHC/tests/test_gui_maintenance_workflow.py',
        'apps/GSHC/tests/test_magnetometer_dialog.py']
    if focused:targets=[str(SOURCE/'test_c_capture.py'),'apps/GSHC/tests/test_installation_owner_adapter.py',
        'apps/GSHC/tests/test_installation_candidate.py']
    output=execute('pytest',[sys.executable,'-B','-m','pytest','-c','apps/GSHC/tests/installation_calibration.ini',
        *targets,'--basetemp',temp,'-q','-o','faulthandler_timeout=20','-W','error'],timeout=180)
    for path,record in snapshot.items():assert fingerprint(ROOT/path)['sha256']==record['sha256'],path
    assert {path:fingerprint(candidate/path) for path in protected}==protected
    report={'owner':'installation_c_impl_20261019_v1','utc':datetime.now(timezone.utc).isoformat(),'purpose':'isolated C + real owner adapter validation; never flash ELF',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'versions':versions,'commands':commands,
        'seconds':time.monotonic()-started,'pytest_summary':output.splitlines()[-1],
        'ccm_bytes':sec['.capture_ccm']['size'],'main_additional_bytes':0,'remaining_ccm':2632-sec['.capture_ccm']['size'],'sections':sec,
        'module_stack':'module_stack.json','caller_task_msp_isr_stack':'NOT PROVEN','wcet':'NOT PROVEN',
        'gui_scope':'all non-MaintenanceOwner AST and 18 other protected files unchanged; worker-only opt-in changes authorized by real-owner task',
        'legacy_gui_whole_file_hash':'file_transfer.py intentionally changed; original baseline retained; no widget/layout change',
        'protected_candidate':protected,'test_temp':str(temp.relative_to(ROOT)),
        'production_enabled':False,'apply_save_upload':False,'cleanup_authorized':False}
    (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    inventory={'owner':report['owner'],'purpose':report['purpose'],'cleanup_authorized':False,
        'files':[{'path':str(path.relative_to(ROOT)),**fingerprint(path)} for path in sorted([*out.rglob('*'),*temp.rglob('*')]) if path.is_file()]}
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    print(json.dumps({'summary':report['pytest_summary'],'ccm':report['ccm_bytes'],'main_new':0,'stack':'module_stack.json','production':False}))
    print(output[-6000:])


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
