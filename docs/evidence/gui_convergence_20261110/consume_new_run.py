"""Consume the new Underline -> TreeDiagram run through production SCG paths."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
SCG = ROOT / 'apps/SCG'
TD = ROOT.parent / 'TreeDiagram'
BUNDLE = TD / 'dist/gui-convergence-20261110/delivery/run.sstuning.json'
WORK = ROOT / '.work/gui-convergence-20261110/integration'
EVIDENCE = Path(__file__).parent / 'integration'
sys.path[:0] = [str(SCG / 'src'), str(TD / 'src')]
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.tuning_bundle import TuningBundle_Preview
from treediagram.algorithms.control import PidController

ENV = os.environ.copy()
ENV.update(PYTHONUTF8='1', PYTHONPATH=str(SCG / 'src'))
COMMANDS = []


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Write(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def Run(label, command):
    started = time.monotonic()
    command = list(map(str, command))
    result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding='utf8')
    (EVIDENCE / (label + '.log')).write_text(result.stdout + result.stderr, encoding='utf8')
    COMMANDS.append(dict(label=label, command=command, exit=result.returncode,
                         seconds=time.monotonic() - started))
    Write('commands.json', COMMANDS)
    print(label, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(label)
    return result.stdout


def Main():
    WORK.mkdir(parents=True, exist_ok=False)
    EVIDENCE.mkdir(exist_ok=False)
    assert Hash(BUNDLE) == 'ab27c43327d51c0c26988c26c3a2d5699c10ce7872592276d24750c95f6580b8'
    bundle = json.loads(BUNDLE.read_text(encoding='utf8'))
    service = FccgService(SCG)
    base = ReferenceProject_Create('GuiConvergence_PID', catalog=service.catalog)
    base_path = WORK / 'base.ssproject'
    ProjectModel_Save(base, base_path, WorkspacePolicy(WORK))
    before = Hash(base_path)
    original = deepcopy(base.Dictionary_Get())
    preview = TuningBundle_Preview(base, service.catalog, bundle)
    assert base.Dictionary_Get() == original and not preview['control_deployable']
    Write('preview.json', preview)
    cli = [sys.executable, '-m', 'silverstar_fccg.project.tuning_bundle']
    results = []
    for case, flags in (('ordinary', []), ('research', ['--include-control-task'])):
        candidate_path = WORK / (case + '.ssproject')
        inspected = json.loads(Run(case + '-preview', [*cli, 'preview', base_path, BUNDLE, *flags]))
        assert Hash(base_path) == before and not candidate_path.exists()
        Run(case + '-apply', [*cli, 'apply', base_path, BUNDLE, *flags, '--output', candidate_path])
        assert Hash(base_path) == before
        candidate = ProjectModel_Load(candidate_path)
        Write(case + '-model.json', candidate.Dictionary_Get())
        destination = WORK / case
        TargetGeneration_Apply(candidate, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        project = destination / 'Flight_Controller'
        contract = json.loads((project / 'Generated/control_research.json').read_text(encoding='utf8'))
        assert contract['enabled'] is (case == 'research')
        if case == 'research':
            assert inspected['control_task_preview']['runtime_dispatch'] is True
            assert contract['period_us'] == 10000 and contract['deployable'] is False
            assert contract['electrical_output'] is False
        decoder, = destination.glob('*.ssdecoder')
        LogDecoderPackage_Verify(decoder.read_bytes())
        with zipfile.ZipFile(decoder) as archive:
            semantics = json.loads(archive.read('project_semantics.json'))
        owners = {row['component']: row for row in semantics['firmware_algorithm_parameters']}
        requested = {row['plugin_id']: {p['id']: p['value'] for p in row['parameters']}
                     for row in bundle['profiles']}
        if case == 'research':
            requested['silverstar.algorithm.control.pid'] = bundle['control_research']['parameters']
        comparisons, prints = [], []
        for owner_id, values in requested.items():
            owner = service.catalog.Component_Get(owner_id)
            assert owners[owner_id]['manifest_sha256'] == owner.ManifestSha256_Get()
            decoded = {row['id']: row for row in owners[owner_id]['parameters']}
            assert set(decoded) == set(values)
            for definition in owner.algorithm_parameters:
                key = definition.parameter_id
                actual = definition.Value_Resolve(values[key])
                assert decoded[key]['value'] == actual and decoded[key]['unit'] == definition.unit
                comparisons.append(dict(owner=owner_id, id=key, target=actual, decoder=decoded[key],
                                        symbol=definition.generated_symbol))
                prints.append(f'printf("{definition.generated_symbol}=%.9g\\n",(double){definition.generated_symbol});')
        source = WORK / (case + '-consumer.c')
        includes = [project / name for name in ('Generated/Inc', 'APP/Inc', 'Interfaces/Inc', 'System/Inc', 'Platform/Inc')]
        sources = []
        body = ''
        if case == 'research':
            core = project / 'Algorithm/Control/PID'
            includes.append(core / 'Inc')
            sources = [core / 'Src/control_pid.c', core / 'Src/control_pid_project.c',
                       project / 'Generated/Src/project_control_research.c']
            body = ('float limit,value; if(ControlResearchBackend_Start(&limit)!=ControlResearchResult_Ok || '
                    'ControlResearchBackend_Step(0.01f,0.002f,&value)!=ControlResearchResult_Ok) return 1; '
                    'printf("OUTPUT_NM=%.9g\\n",(double)value); '
                    'if(ControlResearchBackend_Stop()!=ControlResearchResult_Ok) return 2; ')
        source.write_text('#include <stdio.h>\n#include "project_algorithm_parameters.h"\n'
                          + ('#include "control_research.h"\n' if case == 'research' else '')
                          + 'int main(void){' + body + ''.join(prints) + 'return 0;}\n', encoding='utf8')
        binary = WORK / (case + '-consumer.exe')
        compiler = shutil.which('gcc')
        assert compiler, 'Real GCC is required'
        Run(case + '-compile', [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
            '-O2', '-fanalyzer', *('-I' + str(p) for p in includes), *sources, source, '-lm', '-o', binary])
        output = dict(line.split('=', 1) for line in Run(case + '-consumer', [binary]).splitlines())
        for row in comparisons:
            target = float(row['target'])
            if row['decoder']['storage_type'] == 'float32':
                target = struct.unpack('<f', struct.pack('<f', target))[0]
            assert abs(float(output[row['symbol']]) - target) <= max(1e-8, abs(target) * 2e-8)
        if case == 'research':
            parameters = bundle['control_research']['parameters']
            control = PidController(**parameters)
            expected = control.Step(0., .01, .01)
            assert control.implementation_identity == bundle['implementation_identity']
            assert abs(float(output['OUTPUT_NM']) - expected) < 2e-7
        results.append(dict(case=case, model=str(candidate_path), project=str(project),
                            decoder=str(decoder), decoder_sha256=Hash(decoder), contract=contract,
                            parameters=comparisons, outputs=output, consumer_sha256=Hash(binary)))
        Write('results.json', results)
    Write('scope.json', dict(bundle=str(BUNDLE), bundle_sha256=Hash(BUNDLE), run_id=bundle['run_id'],
          source_commit=Run('source-commit', ['git', 'rev-parse', 'HEAD']).strip(),
          scope='Production CLI preview/apply, generated scalar consumers/decoder and PID mathematical backend; task/ARM/stack separate',
          hardware_tested=False))


if __name__ == '__main__':
    Main()
