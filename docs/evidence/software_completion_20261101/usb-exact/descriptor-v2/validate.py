"""Fresh private USB exports, complete archived input comparison and real builds."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
PRIOR = OUT.parent
WORK = ROOT / '.work/sc-261101-usb/d2'
SCG = ROOT / 'apps/SCG'
sys.path[:0] = [str(SCG / 'src'), str(SCG / 'tests')]
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
phases = json.loads((PRIOR / 'COMMANDS.json').read_text(encoding='utf8'))['phases']
environment = next(row['environment'] for row in phases if row['epoch'] == 'c071-v1')
os.environ.update(environment)
os.environ['PATH'] = os.pathsep.join(('D:/msys64/ucrt64/bin', 'D:/Arm GNU Toolchain/14.3 rel1/bin',
                                     str(Path(sys.executable).parent), os.environ['PATH']))

import test_native_classic_cdc as nf
import test_native_ground_backend as nb
import test_usb_ground_backend as cb
from silverstar_fccg.plugins.catalog import PluginCatalog


def Hash_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def Snapshot_Read():
    return {path.relative_to(ROOT).as_posix(): Hash_Get(path.read_bytes())
            for folder in (SCG / 'src', SCG / 'plugins', ROOT / 'contracts')
            for path in sorted(folder.rglob('*')) if path.is_file() and
            '__pycache__' not in path.parts and path.suffix != '.pyc'}


class TempFactory:
    def __init__(self, root):
        self.root = root
        self.number = 0
    def mktemp(self, prefix):
        self.number += 1
        path = self.root / (prefix + str(self.number))
        path.mkdir(parents=True, exist_ok=False)
        return path


def Closure_Compare(part, project):
    archive = PRIOR / ({'F103': 'arm-v2-F103-artifacts.zip', 'F407': 'arm-v2-F407-artifacts.zip',
                        'C071': 'c071-v1-C071-artifacts.zip'}[part])
    with zipfile.ZipFile(archive) as bundle:
        receipt = json.loads(bundle.read('receipt.json'))
        old_graph = json.loads(bundle.read('Generated/ground_source_graph.json'))
        prefix = 'HardwareGenerated/STM32CubeMX/' if part == 'C071' else 'HardwareGenerated/NativeClassicCdc/'
        old = {prefix + name: value for name, value in receipt['input_sha256'].items()}
        old.update(receipt['experimental_files_sha256'])
        old['Makefile'] = Hash_Get(bundle.read('Makefile'))
    graph = json.loads((project / 'Generated/ground_source_graph.json').read_text(encoding='utf8'))
    assert all(Path(name).parts[0] != 'build' for name in graph['include_dirs'])
    keys = ('sources', 'asm_sources', 'include_dirs', 'defines', 'linker_script', 'mcu_flags',
            'required_irq_handlers', 'required_link_symbols')
    graph_changes = [key for key in keys if old_graph.get(key) != graph.get(key)]
    selected = set(graph['sources']) | set(graph['asm_sources']) | {graph['linker_script'], 'Makefile'}
    selected.update(old_graph['sources']); selected.update(old_graph['asm_sources'])
    selected.add(old_graph['linker_script'])
    # A strict superset of included headers, not only convenient source files.
    selected.update(name for name in old if Path(name).suffix.lower() in ('.h', '.inc', '.mk'))
    selected.update(path.relative_to(project).as_posix() for path in project.rglob('*')
                    if path.is_file() and path.suffix.lower() in ('.h', '.inc', '.mk') and
                    path.relative_to(project).parts[0] != 'build')
    before = {name: old.get(name) for name in sorted(selected)}
    after = {name: Hash_Get((project / name).read_bytes()) if (project / name).is_file() else None
             for name in sorted(selected)}
    missing_archive_proof = [name for name in selected if before[name] is None]
    changed = [name for name in sorted(selected) if before[name] != after[name]]
    return {'part': part, 'archive': archive.name, 'archive_sha256': Hash_Get(archive.read_bytes()),
            'project': str(project), 'compiled_graph_fields': list(keys), 'graph_changes': graph_changes,
            'all_graph_metadata_equal': graph == old_graph, 'before': before, 'after': after,
            'changed': changed, 'missing_archive_proof': sorted(missing_archive_proof),
            'same_compiled_closure': not graph_changes and not changed and not missing_archive_proof}


if __name__ == '__main__':
    WORK.mkdir(parents=True, exist_ok=False)
    before = Snapshot_Read()
    catalog = PluginCatalog(SCG / 'plugins/builtin', SCG / 'plugins/installed')
    catalog.Scan()
    ready = []
    comparisons = []
    for part in ('F103', 'F407', 'C071'):
        base = WORK / part.lower(); base.mkdir()
        factory = TempFactory(base)
        if part != 'C071':
            source_root = base / 'n'; source_root.mkdir()
            native = nf.native.__wrapped__(SimpleNamespace(param=part.lower() + '-usb'), source_root)
            service, imported, args, _ = nb.bound.__wrapped__(native, factory, catalog)
            options = {'device_facts': args['device_facts']}
        else:
            service, imported, header, companion, _ = cb.c071.__wrapped__(factory, catalog)
            options = {'independent_irq_header': header, 'companion_root': companion}
        saved = base / 'p'
        service.ProjectRoot_Save(imported.model, saved, create_new=True)
        export = base / 'e'
        if part == 'C071':
            result = service.UsbGroundCandidate_Export(imported.model, export, **options)
        else:
            result = service.NativeClassicCdcGroundCandidate_Export(imported.model, export, **options)
        assert result.result.value == 'RenderedCandidate', str(result)
        comparison = Closure_Compare(part, export)
        comparisons.append(comparison)
        ready.append((part, service, imported.model, saved, options, export))
        print(part, 'fresh export', 'same closure', comparison['same_compiled_closure'],
              'changed', comparison['changed'], 'graph', comparison['graph_changes'], flush=True)
    after = Snapshot_Read()
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    (OUT / 'generation-source-snapshot.json').write_text(json.dumps({'before': before, 'after': after,
        'changed': changed, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}, indent=2) + '\n', encoding='utf8')
    (OUT / 'closure-comparison.json').write_text(json.dumps(comparisons, indent=2) + '\n', encoding='utf8')
    assert not changed, repr(changed)
    print('GENERATION FROZEN: three normal private exports, source unchanged', flush=True)
    rows = []
    for part, service, model, saved, options, export in ready:
        comparison = next(row for row in comparisons if row['part'] == part)
        if part != 'F407' and comparison['same_compiled_closure']:
            rows.append({'part': part, 'action': 'unchanged_compiled_closure', 'prior_archive': comparison['archive'],
                         'export': str(export), 'new_arm_executed': False})
        else:
            destination = saved.parent / 'b'
            if part == 'C071':
                result = service.UsbGroundCandidate_Build(model, saved, destination, **options)
            else:
                result = service.NativeClassicCdcGroundCandidate_Build(model, saved, destination, **options)
            row = {'part': part, 'action': 'real_normal_and_analyzer_arm_build', 'output': str(destination),
                   'result': result.result.value, 'detail': result.detail, 'new_arm_executed': True}
            rows.append(row)
            print(part, result.result.value, result.detail, flush=True)
        (OUT / 'build-results.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    assert all(row.get('result', 'CompiledCandidate') == 'CompiledCandidate' for row in rows)
