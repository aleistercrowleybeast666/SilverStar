"""Retain compact exact-input/artifact identities without copying SDK trees."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
WORK = REPO / '.work/0.1.3-treediagram-20261101/silverstar'


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Collect():
    for batch in ('firmware-v1', 'bundle-firmware-v1'):
        index = EVIDENCE / batch / 'projects.json'
        if not index.is_file():
            continue
        for row in json.loads(index.read_text(encoding='utf-8')):
            root = Path(row['path'])
            target = EVIDENCE / batch / (row['name'] + '-retained')
            target.mkdir(exist_ok=True)
            entries = []
            for path in sorted(root.rglob('*')):
                if not path.is_file() or 'build' in path.relative_to(root).parts:
                    continue
                entries.append(dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=Hash(path)))
            (target / 'generated-inputs.json').write_text(json.dumps(entries, indent=2), encoding='utf-8')
            for pattern in ('memory-report.json', 'stack-budget.json', 'stack-diagnostic.json', '*.map'):
                for path in root.rglob(pattern):
                    destination = target / path.relative_to(root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
            for path in (root / 'Generated/memory_contract.json', root / 'Generated/project_semantics.json',
                         root / 'Generated/ground_target_metadata.json', root / 'Generated/mission_process.json',
                         root / 'Generated/Inc/project_algorithm_parameters.h', root.parent / 'SilverStar.ssproject'):
                if path.is_file():
                    shutil.copyfile(path, target / path.name)
            artifacts = [dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=Hash(path))
                         for path in root.rglob('*') if path.is_file() and path.suffix in ('.elf', '.map', '.bin')]
            (target / 'artifacts.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
    c071 = WORK / 'c071-v1/candidate'
    if c071.is_dir():
        target = EVIDENCE / 'c071-retained'
        target.mkdir(exist_ok=True)
        for path in c071.rglob('*.json'):
            if path.name in ('backend-receipt.json', 'compile-receipt.json', 'ground_target_metadata.json', 'memory-report.json'):
                shutil.copyfile(path, target / path.name)
        (target / 'artifacts.json').write_text(json.dumps([
            dict(path=path.relative_to(c071).as_posix(), bytes=path.stat().st_size, sha256=Hash(path))
            for path in c071.rglob('*') if path.is_file() and path.suffix in ('.elf', '.map', '.bin')], indent=2), encoding='utf-8')
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=REPO).decode('utf-8')
    sources = []
    for entry in status.split('\0'):
        if not entry:
            continue
        state, name = entry[:2], entry[3:]
        if not name.startswith(('apps/SCG/', 'apps/GSHC/', 'apps/FLP/', 'contracts/', 'tools/')):
            continue
        path = REPO / name
        sources.append(dict(path=name, status=state, sha256=Hash(path) if path.is_file() else None))
    (EVIDENCE / 'dirty-source-snapshot.json').write_text(json.dumps(dict(
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        scope='Current dirty source identity; generated-input hashes separately bind each compiled project.',
        entries=sources), indent=2), encoding='utf-8')


if __name__ == '__main__':
    Collect()
