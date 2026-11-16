"""Check current exact Tools, retained proof artifacts and relocation without writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / '.work/platform-finish-20261116/boards'
sys.path.insert(0, str(ROOT / 'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.artifact_stack import ArtifactStackReportSummary_Decode, ArtifactStackReportSummary_Encode
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.model import ProjectModel_Load


def Digest_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Main_Run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    base = ROOT / 'dist/pf1117-boards-current/SSFC_SSGS' if args.staged else WORK / 'candidate-p'
    output = WORK / ('current-staged-readonly.json' if args.staged else 'current-p-proof.json')
    if output.exists():
        raise ValueError('Preserve prior checks')
    model = ProjectModel_Load(base / 'SSFC1_0_SSGS1_0.ssproject' if args.staged else
                              ROOT / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject')
    service = FccgService(ROOT / 'apps/SCG')
    rows = []
    for target, directory, case_prefix in (('flight', 'Flight_Controller', 'platform-ssfc1-20261116-'),
                                            ('ground', 'Ground_Station', 'ssgs1-')):
        folder = base / directory
        if not ProjectTargetGenerated_IsCurrent(model, service.catalog, folder, target):
            raise ValueError('Current source authority mismatch')
        for config in ('Release', 'Debug'):
            relative = Path('build/FCCG/SilverStar_H743ZI') / config if target == 'flight' else (
                Path('build/Debug') if config == 'Debug' else Path('build'))
            report = folder / relative / ('stack-budget.json' if target == 'flight' else 'ground-stack-budget.json')
            summary = ArtifactStackReportSummary_Decode(
                ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(report), folder))
            if not summary or not summary['passes']:
                raise ValueError('Exact report binding failed')
            identities = {}
            for name, row in summary['analysis_tools'].items():
                candidates = [ROOT / 'apps/SCG/plugins/builtin' / owner / 'payload/Tools' / name
                    for owner in ('silverstar_core_0_1_0', 'silverstar_core_ground_0_1_0')]
                same = [p for p in candidates if p.is_file() and Digest_Get(p) == row['sha256']]
                if not same:
                    raise ValueError('Generated analysis Tool differs from final owner: ' + name)
                identities[name] = row['sha256']
            case = json.loads((folder / 'Tools/software_stack_cases' / (case_prefix + config + '.json')).read_text(encoding='utf8'))
            compared = []
            for name, digest in case['compiled_artifacts'].items():
                old = WORK / 'candidate-o' / directory / relative / name
                new = folder / relative / name
                if Digest_Get(old) != digest or Digest_Get(new) != digest:
                    raise ValueError('Retained/current compiler artifact differs: ' + name)
                compared.append(name)
            rows.append({'target': target, 'configuration': config, 'source_authority_current': True,
                'exact_current_tools': identities, 'compiled_artifacts_equal_to_o_and_case': len(compared),
                'report_sha256': summary['report_sha256'], 'msp': summary['main_msp_exceptions'],
                'tasks': [{'task': task['task'], 'margin_bytes': task['margin_bytes']} for task in summary['tasks']]})
    if args.staged:
        manifest = json.loads((base / 'MANIFEST.json').read_text(encoding='utf8'))
        actual = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
        if actual != set(manifest['files']) | {'MANIFEST.json'}:
            raise ValueError('Staged entry set changed')
        for name, row in manifest['files'].items():
            if Digest_Get(base / name) != row['sha256'] or (base / name).stat().st_size != row['bytes']:
                raise ValueError('Staged manifest content changed')
    receipt = {'read_only': True, 'hardware_tested': False, 'scope': 'Current source authority, not packaged EXE authority',
               'staged': args.staged, 'targets': rows, 'manifest_all_sha256_equal': True if args.staged else None}
    output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'targets': len(rows), 'staged': args.staged, 'all_exact': True}))


if __name__ == '__main__':
    Main_Run()
