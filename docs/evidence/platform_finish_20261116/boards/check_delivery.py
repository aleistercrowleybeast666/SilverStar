"""Read-only staged model/report/manifest verification; never refresh sealed output."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.artifact_stack import ArtifactStackReportSummary_Decode, ArtifactStackReportSummary_Encode
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.model import ProjectModel_Load


def Main_Run():
    destination = ROOT / 'dist/pf1117-boards'
    receipt_path = ROOT / '.work/platform-finish-20261116/boards/staged-readonly.json'
    if receipt_path.exists():
        raise ValueError('Preserve prior delivery checks')
    service = FccgService(ROOT / 'apps/SCG')
    pair = destination / 'SSFC_SSGS'
    reference = destination / 'F103_E19'
    pair_model = ProjectModel_Load(pair / 'SSFC1_0_SSGS1_0.ssproject')
    f103_model = ProjectModel_Load(reference / 'software-inputs/E19_Software.ssproject')
    rows = []
    for name, target, folder, model in (
            ('SSFC1.0', 'flight', pair / 'Flight_Controller', pair_model),
            ('SSGS1.0', 'ground', pair / 'Ground_Station', pair_model),
            ('F103 E19 reference', 'ground', reference / 'Ground_Station', f103_model)):
        current = ProjectTargetGenerated_IsCurrent(model, service.catalog, folder, target)
        summaries = []
        for config in ('Release', 'Debug'):
            path = (folder / 'build/FCCG/SilverStar_H743ZI' / config / 'stack-budget.json'
                    if target == 'flight' else folder / 'build' /
                    ('Debug/ground-stack-budget.json' if config == 'Debug' else 'ground-stack-budget.json'))
            summary = ArtifactStackReportSummary_Decode(
                ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), folder))
            if not summary or not summary['passes']:
                raise ValueError('Staged exact report binding failed: ' + str(path))
            summaries.append({'configuration': config, 'report': str(path),
                'report_sha256': summary['report_sha256'],
                'msp': summary['main_msp_exceptions'],
                'tasks': [{'task': task['task'], 'margin_bytes': task['margin_bytes']}
                          for task in summary['tasks']],
                'review': summary['software_review'],
                'analysis_tools_sha256': {key: value['sha256'] for key, value in summary['analysis_tools'].items()}})
        if not current:
            raise ValueError('Staged source-authority receipt is stale: ' + name)
        rows.append({'target': name, 'source_authority_current': current, 'reports': summaries})
    manifests = []
    for folder in (pair, reference):
        manifest_path = folder / 'MANIFEST.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        if actual != set(manifest['files']) | {'MANIFEST.json'}:
            raise ValueError('Staging gained or lost files')
        for relative, item in manifest['files'].items():
            raw = (folder / relative).read_bytes()
            if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('Staged bytes changed: ' + relative)
        manifests.append({'manifest': str(manifest_path), 'files': len(actual), 'all_sha256_equal': True})
    receipt = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'read_only': True, 'hardware_tested': False,
        'authority_scope': 'Current source SCG catalog/authority only; no claim about the separately packaged SCG executable',
        'saved_report_scope': 'Exact reports bound to the copied ELF and copied analysis Tools; no relocated rebuild was run',
        'targets': rows, 'manifests': manifests}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    Main_Run()
