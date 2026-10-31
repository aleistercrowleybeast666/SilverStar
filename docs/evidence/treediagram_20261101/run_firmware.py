"""Fresh normal-generation evidence; never modifies user-selected output or hardware."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
SCG = REPO / 'apps/SCG'
WORK = REPO / '.work/0.1.3-treediagram-20261101/silverstar/firmware-v1'
EVIDENCE = Path(__file__).resolve().parent / 'firmware-v1'
sys.path[:0] = [str(SCG/'src'), str(SCG/'tests')]


def Project_Generate(name):
    from dataclasses import replace
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.project.reference import ReferenceProject_Create
    service = FccgService(SCG)
    destination = WORK/name
    if name == 'sx1278':
        from sx1278_project_fixture import Sx1278Project_Create
        destination.mkdir(parents=True, exist_ok=False)
        model = Sx1278Project_Create(service.catalog, destination)
        return TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(destination),
            destination/'project', TargetScope.ALL)
    if name == 'h743':
        spec = importlib.util.spec_from_file_location('h743_static', SCG/'tools/validation/h743_static_validate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        model, _ = module.Scenario_Create(service,
            REPO/'.work/h7_20261025/verified_release/CubeMX_StaticInput', 'eskf20', 1, {})
    else:
        model = ReferenceProject_Create('TreeDiagramReview_' + name, catalog=service.catalog)
        if name == 'bundle':
            from silverstar_fccg.project.tuning_bundle import TuningBundle_Read, TuningBundle_Apply
            package = REPO.parent/'TreeDiagram/tests/fixtures/algorithms/kf6-pid.sstuning.json'
            model = TuningBundle_Apply(model, service.catalog, TuningBundle_Read(package))
            print('BUNDLE_INPUT_SHA256', hashlib.sha256(package.read_bytes()).hexdigest(), flush=True)
        if name == 'installation':
            from silverstar_fccg.project.logging import LoggingProfile_Reconcile
            model.base_components.append('silverstar.installation.capture')
            model.device_instances = [replace(item, profile='jy901b_mag_capture')
                if item.plugin == 'silverstar.device.imu.jy901b' else item for item in model.device_instances]
            LoggingProfile_Reconcile(model, service.catalog)
    return TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)


def Validation_Run(bundle=False):
    output = Path(__file__).resolve().parent/('bundle-firmware-v1' if bundle else 'firmware-v1')
    WORK.mkdir(parents=True, exist_ok=bundle)
    output.mkdir(exist_ok=False)
    environment = os.environ.copy()
    gcc = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
    host = Path('D:/msys64/ucrt64/bin')
    environment['PATH'] = os.pathsep.join((str(gcc), str(host), str(Path(sys.executable).parent), environment['PATH']))
    commands = []
    def Run(name, command):
        started = time.perf_counter()
        with (output/(name+'.log')).open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=REPO, env=environment, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        commands.append(dict(name=name, command=command, exit_code=result.returncode,
                             seconds=round(time.perf_counter()-started, 2)))
        (output/'commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
        print(name, result.returncode, flush=True)
        return result.returncode
    for tool in (sys.executable, str(gcc/'arm-none-eabi-gcc.exe'), str(host/'gcc.exe')):
        Run(Path(tool).stem+'-version', [tool, '--version'])
    projects = []
    for name in (('bundle',) if bundle else ('f407', 'installation', 'h743', 'sx1278')):
        if Run(name+'-generate', [sys.executable, str(Path(__file__).resolve()), 'generate', name]):
            continue
        base = WORK/name/('project' if name == 'sx1278' else '')
        for target in (('Flight_Controller', 'Ground_Station') if name == 'sx1278' else ('Flight_Controller',)):
            project = base/target
            label = name + ('-ground' if target == 'Ground_Station' else '')
            projects.append(dict(name=label, path=str(project)))
            (output/'projects.json').write_text(json.dumps(projects, indent=2), encoding='utf-8')
            tasks = ['all', 'architecture-check', 'power10-check', 'static-analysis', 'artifact-check', 'host-tests']
            if target == 'Flight_Controller':
                tasks.append('stack-report')
            for task in tasks:
                Run(label+'-'+task, [str(host/'mingw32-make.exe'), '-C', str(project), '-j2',
                    'CONFIG=Release', 'GCC_PATH='+str(gcc), 'HOST_CC='+str(host/'gcc.exe'), 'PYTHON='+sys.executable, task])
    artifacts = []
    for project in projects:
        for pattern in ('*.elf', '*.map', '*memory*.json', '*stack*.json'):
            for path in Path(project['path']).rglob(pattern):
                artifacts.append(dict(project=project['name'], path=str(path.relative_to(REPO)),
                    bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (output/'artifacts.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
    return int(any(row['exit_code'] for row in commands))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'generate':
        result = Project_Generate(sys.argv[2])
        print(result)
    else:
        raise SystemExit(Validation_Run(bundle=sys.argv[1:] == ['bundle']))
