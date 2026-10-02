import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'apps/FCCG/src'))
path = ROOT / 'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/auto_memory_layout.py'
spec = importlib.util.spec_from_file_location('memory_layout_contract', path)
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)
source = '430956d7ab649fba1415635826541996d061592d'
baseline = subprocess.check_output(['git', 'rev-parse', '5d6d12b'], cwd=ROOT, text=True).strip()
sf = 'apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6'
assert not subprocess.check_output(['git', 'diff', baseline, source, '--', sf], cwd=ROOT)
results = {'source_commit': source, 'baseline_commit': baseline, 'SF6_owner_unchanged': True, 'source_protection': []}
for name, relative in [('SF6', 'Algorithm/Estimator/SF6/Src/navigation_sf6.c'), ('ESKF15', 'Interfaces/Inc/system_navigation_backend.h')]:
    original = OUT / (name + '_auto_v1') / 'Flight_Controller'
    fixture = OUT / ('SourceDrift_' + name + '_v3')
    shutil.copytree(original, fixture, ignore=shutil.ignore_patterns('build'))
    linker = fixture / 'STM32F407XX_FLASH.ld'
    groups = {'nav_health': {'symbol': 's_groups'}}
    auto.SourceOwners_Check(fixture, groups, linker)
    file = fixture / relative
    before = hashlib.sha256(file.read_bytes()).hexdigest()
    file.write_bytes(file.read_bytes() + b'\n/* Synthetic source drift: proof must reject. */\n')
    try:
        auto.SourceOwners_Check(fixture, groups, linker)
    except ValueError as error:
        assert relative in str(error), str(error)
        results['source_protection'].append({'algorithm': name, 'file': relative, 'before_sha256': before, 'after_sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'clean_proof': 'PASS', 'changed_proof': 'EXPECTED REJECTION', 'reason': str(error)})
    else:
        raise AssertionError('Source protection failed: ' + relative)
(OUT / 'compatibility.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
