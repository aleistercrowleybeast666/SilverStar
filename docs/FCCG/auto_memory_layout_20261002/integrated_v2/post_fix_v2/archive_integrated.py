from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
PRE = ROOT / '.work/AutoMemory_Integrated_20261002_v1'
DEST = ROOT / 'docs/FCCG/auto_memory_layout_20261002/integrated_v2'
source = subprocess.check_output(['git', 'rev-parse', 'c61968c'], cwd=ROOT, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
stages = json.loads((OUT / 'matrix_results.json').read_text(encoding='utf-8'))
assert len(stages) == 32 and all(row['exit_code'] == 0 for row in stages)
generation = json.loads((OUT / 'generation.json').read_text(encoding='utf-8'))
assert len(generation) == 8 and all(row['source_commit'] == source for row in generation)
assert '43 passed' in (OUT / 'python_tests.log').read_text(errors='replace')
assert '1 passed' in (OUT / 'flp_exact_decoder.log').read_text(errors='replace')
assert 'CAPTURED 16' in (OUT / 'gui_opened_capture.log').read_text(errors='replace')
for row in generation:
    flight = Path(row['project']) / 'Flight_Controller'
    assert all(hashlib.sha256((flight / file).read_bytes()).hexdigest() == expected for file, expected in row['files'].items())
DEST.mkdir(exist_ok=False)
(DEST / '.gitattributes').write_text('* -text\n', encoding='utf-8')
for origin, target in [(PRE, DEST / 'pre_fix_v1'), (OUT, DEST / 'post_fix_v2')]:
    target.mkdir()
    for pattern in ['*.log', '*.json', '*.xml', '*.py', '*.patch', '*.BIN']:
        for file in origin.glob(pattern):
            shutil.copy2(file, target / file.name)
shutil.copytree(OUT / 'GUI', DEST / 'GUI')
shutil.copytree(OUT / 'GUI_Opened', DEST / 'GUI_Opened')
resources = []
archive = DEST / 'sources_artifacts.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as pack:
    for name in ['PureINS', 'KF6', 'ESKF15', 'SF6']:
        for layout in ['legacy', 'auto']:
            project = OUT / (name + '_' + layout + '_v1')
            flight = project / 'Flight_Controller'
            build = flight / 'build/FCCG/SilverStar_F407/Release'
            if layout == 'auto':
                build /= 'auto'
            text = (OUT / (name.lower() + '_' + layout + '_arm.log')).read_text(errors='replace')
            regions = {}
            for region in ['FLASH', 'main SRAM', 'CCMRAM']:
                entries = re.findall(re.escape(region) + r'\s+used=(\d+)\s+remaining=(\d+)\s+capacity=(\d+)', text)
                assert len(entries) == 1, (name, layout, region)
                used, remaining, capacity = map(int, entries[0])
                regions[region] = {'used': used, 'remaining': remaining, 'capacity': capacity}
            binaries = list(build.glob('*.elf'))
            assert len(binaries) == 1
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            decision = json.loads((build / 'memory_layout/decision.json').read_text(encoding='utf-8')) if layout == 'auto' else None
            if decision:
                assert decision['elf_sha256'] == sha(binaries[0])
                assert all(row['source_sha256'] for row in decision['groups'].values())
            binfile = binaries[0].with_suffix('.bin')
            baseline = ROOT / '.work/SF6_20261001_v1' / (name + '_v8') / 'Flight_Controller/build/FCCG/SilverStar_F407/Release' / binfile.name
            record = {'name': name, 'layout': layout, 'regions': regions, 'physical_ram_total_bytes': regions['main SRAM']['used'] + regions['CCMRAM']['used'], 'elf_sha256': sha(binaries[0]), 'bin_sha256': sha(binfile), 'bin_bytes': binfile.stat().st_size, 'v8_bin_equal': binfile.read_bytes() == baseline.read_bytes(), 'assignment': decision['assignment'] if decision else None, 'attempts': len(decision['attempts']) if decision else None, 'groups': decision['groups'] if decision else None}
            resources.append(record)
            prefix = name + '_' + layout
            for file in project.rglob('*'):
                if file.is_file() and 'build' not in file.relative_to(project).parts:
                    pack.write(file, prefix + '/Source/' + file.relative_to(project).as_posix())
            for file in build.rglob('*'):
                if file.is_file() and (file.suffix in ['.elf', '.bin', '.hex', '.map'] or file.parent.name == 'memory_layout' or file.name == 'stack-budget.json'):
                    pack.write(file, prefix + '/Build/' + file.relative_to(build).as_posix())
(DEST / 'resources.json').write_text(json.dumps(resources, indent=2), encoding='utf-8')
versions = {}
for name, cmd in [('Python', [str(ROOT / '.venv/Scripts/python.exe'), '--version']), ('ARM', ['arm-none-eabi-gcc', '--version']), ('Host', ['D:/msys64/ucrt64/bin/gcc.exe', '--version']), ('Make', ['mingw32-make', '--version'])]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    versions[name] = {'command': cmd, 'exit_code': result.returncode, 'output': result.stdout + result.stderr}
manifest = {'utc': datetime.now(timezone.utc).isoformat(), 'source_commit': source, 'parent_product_commit': '12ff2d5bd4b36bfd0343653439542be1a14599d8', 'parent_range_end': '998be61610064927e8b0d7de48fa6c1f884a7c48', 'tools': versions, 'scope': 'One actual 32-command post-fix matrix: 4 auto x 6 gates plus 4 legacy x 2 artifact/resource commands; full post-fix Python 43 tests. Legacy Host/analyzer/architecture not rerun in this 32-command matrix.', 'critical_contract_review': 'NOT PROVEN', 'hardware': 'NOT PERFORMED', 'files': {p.relative_to(DEST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.rglob('*')) if p.is_file()}}
(DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files': len(manifest['files']), 'source': source, 'resources': resources, 'archive_bytes': archive.stat().st_size}))
