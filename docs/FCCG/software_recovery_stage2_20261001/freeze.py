from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, shutil, subprocess
root = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
gates = json.loads((out / 'gate_results_v6.json').read_text(encoding='utf-8'))
assert len(gates) == 21 and len({x['name'] for x in gates}) == 21
assert all(x['exit_code'] == 0 for x in gates), 'failed gate blocks freeze'
source_commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert source_commit == '50cc2d3fb4ac7b7e3a84267a82183b4131b23369'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
evidence = root / 'docs/FCCG/software_recovery_stage2_20261001'
frozen = out / 'FrozenArtifacts_50cc2d3'
if evidence.exists() or frozen.exists():
    raise SystemExit('fresh freeze/evidence directories required')
evidence.mkdir()
frozen.mkdir()
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
    source_commit=source_commit, source_worktree='clean at freeze',
    branch='fix/software-reconnect-ground-20261001', product_version='0.1.1',
    status='SOFTWARE_GATES_PASS_BENCH_REVIEW_PENDING',
    critical_contract_review='NOT PROVEN', hardware_acceptance='NOT PROVEN',
    hardware_commands_executed=False, user_TEST_4_modified=False,
    gates=gates, artifacts=[], logs=[], generated_inputs={}, gshc_runtime_sources={})
for candidate in ['candidate_a_v6', 'candidate_b_v6']:
    project = out / candidate
    manifest['generated_inputs'][candidate] = {
        str(p.relative_to(project)).replace('\\','/'):digest(p)
        for p in project.rglob('*') if p.is_file() and 'build' not in p.parts}
for relative in subprocess.check_output(['git','ls-files','apps/GSHC'],cwd=root,text=True).splitlines():
    path = root / relative
    if path.suffix == '.py' and 'tests' not in path.parts:
        manifest['gshc_runtime_sources'][relative] = digest(path)
manifest['gshc_runtime_sources']['VERSION'] = digest(root / 'VERSION')
for target, directory in [('Flight', 'Flight_Controller'),('Ground','Ground_Station')]:
    project = out / 'candidate_a_v6' / directory
    paths = ([project / f'build/FCCG/SilverStar_F407/Release/SilverStar_0_1_1.{extension}'
              for extension in ('elf','bin')] if target == 'Flight' else
             [project / f'build/ground.{extension}' for extension in ('elf','bin')])
    for path in paths:
        destination = frozen / (target + '_' + path.name)
        shutil.copy2(path, destination)
        manifest['artifacts'].append(dict(target=target, source=str(path),
            frozen=str(destination), bytes=path.stat().st_size, sha256=digest(path)))
for path in sorted(out.iterdir()):
    if path.is_file() and path.suffix in ('.log','.json','.py','.c'):
        destination = evidence / path.name
        shutil.copy2(path, destination)
        manifest['logs'].append(dict(file=path.name, source=str(path), bytes=path.stat().st_size, sha256=digest(path)))
for path in sorted((out / 'focused-host').iterdir()):
    if path.suffix in ('.log','.json','.c'):
        destination = evidence / ('focused_' + path.name)
        shutil.copy2(path, destination)
        manifest['logs'].append(dict(file=destination.name,source=str(path),bytes=path.stat().st_size,sha256=digest(path)))
(evidence / 'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
(frozen / 'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(manifest['artifacts'], indent=2))
